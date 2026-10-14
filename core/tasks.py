# -*- coding: utf-8 -*-
"""Task objects + the smart per-user queue.

Rules (per user):
  * a file  > 1 GiB (or of unknown size) runs ALONE: it waits until everything
    running has finished and nothing else starts until it is done;
  * files  <= 1 GiB run together, up to MAX_PARALLEL_SMALL (4) at a time;
  * strict FIFO – a later small file never jumps over an earlier big one.
Every task has its OWN cancel flag + asyncio task, so cancelling one URL can
never touch another one.
"""
import asyncio
import logging
import os
import shutil
import threading
import time
from collections import deque

from config import Config

logger = logging.getLogger(__name__)


class TaskFailed(Exception):
    """Fatal, user-facing error (message is shown in the status card)."""


class Cancelled(Exception):
    """Raised inside worker threads when the task was cancelled."""


class Meter:
    """Smooth speed over a sliding window."""

    def __init__(self, window=6.0):
        self.window = window
        self.samples = deque()
        self._last = 0.0

    def reset(self):
        self.samples.clear()
        self._last = 0.0

    def update(self, done):
        now = time.monotonic()
        if self.samples and now - self._last < 0.25:
            return
        self._last = now
        self.samples.append((now, done))
        while len(self.samples) > 2 and now - self.samples[0][0] > self.window:
            self.samples.popleft()

    @property
    def speed(self):
        if len(self.samples) < 2:
            return 0.0
        (t0, d0), (t1, d1) = self.samples[0], self.samples[-1]
        return (d1 - d0) / (t1 - t0) if t1 > t0 else 0.0


class Task:
    def __init__(self, *, task_id, user_id, chat_id, anchor, status, name, size,
                 mode, source, url=None, auth=None, local_path=None, work_dir=None,
                 keep_dir=False, password=None):
        self.id = task_id
        self.user_id = user_id
        self.chat_id = chat_id
        self.anchor = anchor          # the user's ORIGINAL message (URL / file)
        self.status = status          # our single status message (reply to anchor)
        self.name = name
        self.size = size              # bytes or None
        self.mode = mode              # video | doc | audio | unzip_video | unzip_doc
        self.source = source          # url | tgfile | local
        self.url = url
        self.auth = auth              # (user, pass) or None
        self.local_path = local_path
        self.password = password
        self.keep_dir = keep_dir
        self.split_set = None
        self.dir = work_dir or os.path.join(Config.DOWNLOAD_LOCATION, str(user_id), task_id)

        self.state = "queued"
        self.error = ""
        self.note = ""
        self.queue_pos = 0
        self.queue_reason = ""
        self.created = time.time()
        self.t_download = 0.0
        self.t_upload = 0.0

        # live progress
        self.done = 0
        self.total = size or 0
        self.meter = Meter()
        self.file_index = 0
        self.file_count = 0
        self.current_name = name
        self.flood_until = 0.0
        self.result_text = ""

        # control
        self.cancel_flag = threading.Event()
        self.start_event = asyncio.Event()
        self.wake = asyncio.Event()
        self._loop = asyncio.get_running_loop()
        self.runner = None
        self.reporter = None
        self.manager = None
        self._has_global = False

    # ------------------------------------------------------------ helpers
    @property
    def is_big(self):
        return self.size is None or self.size > Config.BIG_FILE_THRESHOLD

    @property
    def cancelled(self):
        return self.cancel_flag.is_set()

    @property
    def finished(self):
        return self.state in ("done", "failed", "cancelled")

    def wake_up(self):
        """Thread-safe: worker threads call begin_stage()/advance() too."""
        try:
            self._loop.call_soon_threadsafe(self.wake.set)
        except RuntimeError:
            pass

    def set_state(self, state, **kw):
        self.state = state
        for k, v in kw.items():
            setattr(self, k, v)
        self.wake_up()

    def begin_stage(self, total=0):
        self.done = 0
        self.total = total
        self.meter.reset()
        self.wake_up()

    def advance(self, done, total=None):
        self.done = done
        if total:
            self.total = total
        self.meter.update(done)

    def check_cancel(self):
        if self.cancel_flag.is_set():
            raise Cancelled()

    def cancel(self):
        """Idempotent. Stops threads (flag) AND the asyncio task (hard cancel)."""
        if self.cancel_flag.is_set() or self.finished:
            return False
        self.cancel_flag.set()
        if self.runner and not self.runner.done():
            self.runner.cancel()
        return True


class _UserQueue:
    def __init__(self):
        self.waiting = deque()
        self.running = set()

    def can_start(self, t):
        if any(r.is_big for r in self.running):
            return False
        if t.is_big:
            return not self.running
        return len(self.running) < Config.MAX_PARALLEL_SMALL


class TaskManager:
    def __init__(self):
        self.tasks = {}
        self.queues = {}
        self._sem = None

    # -------------------------------------------------------------- public
    def submit(self, task, pipeline):
        task.manager = self
        self.tasks[task.id] = task
        task.runner = asyncio.create_task(self._main(task, pipeline))
        return task

    def get(self, task_id):
        return self.tasks.get(task_id)

    def user_tasks(self, user_id):
        return [t for t in self.tasks.values() if t.user_id == user_id and not t.finished]

    def running_count(self, user_id):
        q = self.queues.get(user_id)
        return len(q.running) if q else 0

    # ------------------------------------------------------------ internals
    def _queue(self, uid):
        return self.queues.setdefault(uid, _UserQueue())

    def _semaphore(self):
        if self._sem is None:
            self._sem = asyncio.Semaphore(max(1, Config.GLOBAL_MAX_TASKS))
        return self._sem

    def _pump(self, q):
        while q.waiting and q.can_start(q.waiting[0]):
            t = q.waiting.popleft()
            q.running.add(t)
            t.start_event.set()
        running_big = any(r.is_big for r in q.running)
        for i, t in enumerate(q.waiting, 1):
            t.queue_pos = i
            if running_big:
                t.queue_reason = "a large file is running"
            elif t.is_big:
                t.queue_reason = "large file waits for a free line"
            else:
                t.queue_reason = "all parallel slots busy"
            t.wake_up()

    async def _wait_turn(self, task):
        q = self._queue(task.user_id)
        q.waiting.append(task)
        self._pump(q)
        await task.start_event.wait()
        await self._semaphore().acquire()
        task._has_global = True

    def _release(self, task):
        q = self._queue(task.user_id)
        if task in q.waiting:
            q.waiting.remove(task)
        q.running.discard(task)
        if task._has_global:
            task._has_global = False
            self._semaphore().release()
        self._pump(q)

    async def _main(self, task, pipeline):
        from core.reporter import Reporter
        reporter = Reporter(task)
        task.reporter = reporter
        rep = asyncio.create_task(reporter.run())
        t0 = time.time()
        try:
            await self._wait_turn(task)
            task.set_state("running")
            await pipeline(task)
            task.set_state("done")
        except asyncio.CancelledError:
            task.set_state("cancelled")
        except Cancelled:
            task.set_state("cancelled")
        except TaskFailed as e:
            task.set_state("failed", error=str(e))
        except Exception as e:  # never let a task die silently
            logger.exception("Task %s crashed", task.id)
            task.set_state("failed", error=f"{type(e).__name__}: {str(e)[:150]}")
        finally:
            self._release(task)
            task.cancel_flag.set()          # stop any helper thread
            rep.cancel()
            try:
                await reporter.finalize(time.time() - t0)
            except Exception:
                logger.exception("finalize failed")
            if not task.keep_dir:
                await asyncio.to_thread(shutil.rmtree, task.dir, True)
            self.tasks.pop(task.id, None)


manager = TaskManager()
