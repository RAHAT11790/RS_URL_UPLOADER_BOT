# -*- coding: utf-8 -*-
"""Background status updater.

Transfers only update counters (no awaits) – this loop edits the card.
So a slow Telegram edit / FloodWait can NEVER slow a download or upload down.
"""
import asyncio
import logging
import time

from pyrogram.errors import FloodWait, MessageIdInvalid, MessageNotModified, RPCError

from config import Config
from core.render import render

logger = logging.getLogger(__name__)
_bg = set()


def spawn(coro):
    t = asyncio.create_task(coro)
    _bg.add(t)
    t.add_done_callback(_bg.discard)
    return t


def _flood_secs(e):
    return int(getattr(e, "value", None) or getattr(e, "x", None) or 5)


class Reporter:
    MIN_GAP = 1.2

    def __init__(self, task):
        self.task = task
        self.last_text = None
        self.last_kb = None
        self.last_edit = 0.0
        self.blocked_until = 0.0
        self.dead = False   # status message deleted by the user

    def interval(self):
        n = 1
        mgr = self.task.manager
        if mgr:
            n = max(1, mgr.running_count(self.task.user_id))
        return max(Config.PROGRESS_UPDATE_INTERVAL, 2.0 * n)

    async def run(self):
        t = self.task
        while not self.dead:
            try:
                await asyncio.wait_for(t.wake.wait(), timeout=self.interval())
            except asyncio.TimeoutError:
                pass
            t.wake.clear()
            if t.finished:
                return
            await self.push()
            gap = self.MIN_GAP - (time.monotonic() - self.last_edit)
            if gap > 0:
                await asyncio.sleep(gap)

    async def push(self, force=False):
        if self.dead:
            return
        now = time.monotonic()
        if now < self.blocked_until:
            return
        text, markup = render(self.task)
        key = repr(markup)
        if not force and text == self.last_text and key == self.last_kb:
            return
        try:
            await self.task.status.edit(text=text, reply_markup=markup)
            self.last_text, self.last_kb = text, key
            self.last_edit = time.monotonic()
        except MessageNotModified:
            self.last_text, self.last_kb = text, key
        except FloodWait as e:
            self.blocked_until = time.monotonic() + _flood_secs(e) + 1
        except MessageIdInvalid:
            self.dead = True
        except RPCError as e:
            logger.debug("status edit failed: %s", e)
        except Exception as e:
            logger.debug("status edit error: %s", e)

    async def finalize(self, elapsed):
        t = self.task
        # wait out a flood block so the FINAL state is always shown
        wait = self.blocked_until - time.monotonic()
        if 0 < wait < 60:
            await asyncio.sleep(wait)
            self.blocked_until = 0
        await self.push(force=True)
        delay = 25 if t.state == "done" else 12
        if t.state in ("cancelled", "failed", "done"):
            spawn(self._delete_later(delay))

    async def _delete_later(self, delay):
        await asyncio.sleep(delay)
        try:
            await self.task.status.delete()
        except Exception:
            pass
