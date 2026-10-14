# -*- coding: utf-8 -*-
"""The work of ONE task: download -> (extract) -> upload, strictly in order."""
import asyncio
import logging
import os
import shutil
import time

from pyrogram.errors import FloodWait

try:
    from pyrogram import StopTransmission
except ImportError:  # pragma: no cover
    class StopTransmission(Exception):
        pass

from config import Config
from core import downloader, extractor, uploader
from core.extractor import NeedPassword, WrongPassword
from core.state import PASSWORD_WAITERS
from core.tasks import Cancelled, TaskFailed
from helper_funcs.ui import B, GREEN, LINE, RED, esc, fb, kb, quote
from helper_funcs.utils import fmt_secs, humanbytes, natural_key, safe_filename

logger = logging.getLogger(__name__)


def _flood(e):
    return int(getattr(e, "value", None) or getattr(e, "x", None) or 10)


async def _ask_password(task, wrong=False):
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    key = (task.chat_id, task.status.id)
    PASSWORD_WAITERS[key] = fut
    task.note = "Wrong password – try again." if wrong else ""
    task.set_state("password")
    try:
        return await asyncio.wait_for(fut, Config.PASSWORD_TIMEOUT)
    except asyncio.TimeoutError:
        raise TaskFailed("Password was not sent in time.")
    finally:
        PASSWORD_WAITERS.pop(key, None)
        task.note = ""


async def _fetch_source(task):
    """Make sure the file is on disk; returns its path."""
    os.makedirs(task.dir, exist_ok=True)
    name = safe_filename(task.name)

    if task.source == "local":
        return task.local_path

    dest = os.path.join(task.dir, name)

    if task.size:
        need = task.size * (2.3 if task.mode.startswith("unzip") else 1.15)
        free = shutil.disk_usage(task.dir).free
        if free < need:
            raise TaskFailed(f"Not enough disk space (need {humanbytes(need)}, free {humanbytes(free)}).")

    task.set_state("download")
    t0 = time.time()

    if task.source == "url":
        await downloader.download(task, task.url, dest, task.auth)
    else:  # Telegram document sent to the bot
        async def progress(cur, tot):
            if task.cancelled:
                raise StopTransmission()
            task.advance(cur, tot)

        task.begin_stage(task.size or 0)
        while True:
            try:
                got = await task.anchor.download(file_name=dest, progress=progress)
                break
            except FloodWait as e:
                wait = _flood(e) + 1
                task.set_state("flood", flood_until=time.time() + wait)
                await asyncio.sleep(wait)
                task.set_state("download")
            except StopTransmission:
                raise Cancelled()
        if got and os.path.abspath(str(got)) != os.path.abspath(dest) and os.path.exists(str(got)):
            dest = str(got)

    task.t_download = time.time() - t0
    return dest


async def _extract(task, archive):
    out = os.path.join(task.dir, "_x")
    password = task.password
    wrong = False
    for _ in range(4):
        task.set_state("extract")
        try:
            await extractor.extract(task, archive, out, password)
            return out
        except NeedPassword:
            password = await _ask_password(task, wrong=False)
        except WrongPassword:
            await asyncio.to_thread(shutil.rmtree, out, True)
            wrong = True
            password = await _ask_password(task, wrong=True)
    raise TaskFailed("Wrong password too many times.")


async def _split_card(task, s):
    names = "\n".join(
        f"• <code>{esc(os.path.basename(f))}</code>"
        for f in sorted(s.files, key=lambda f: natural_key(os.path.basename(f))))
    text = (f"📦 <b>{fb('SPLIT ARCHIVE')}</b>  ·  <code>#{s.id}</code>\n"
            + quote(f"🗂 Parts received: <b>{len(s.files)}</b>\n{LINE}\n{names}", expandable=len(s.files) > 6)
            + "\n📌 Send the next part, or choose what to do:")
    markup = kb([B("🎬 Extract → Video", f"sp:{s.id}:v", GREEN),
                 B("📄 Extract → Document", f"sp:{s.id}:d", GREEN)],
                [B("🗑 Discard all", f"sp:{s.id}:x", RED)])
    old = s.ctrl
    s.anchor = task.anchor
    s.ctrl = await task.anchor.reply(text, quote=True, reply_markup=markup)
    if old:
        try:
            await old.delete()
        except Exception:
            pass


async def run(task):
    bot = task.anchor._client

    if task.mode == "part":                       # one volume of a split archive
        s = task.split_set
        try:
            path = await _fetch_source(task)
            s.files.append(path)
        finally:
            s.pending_tasks -= 1
        task.result_text = f"Part saved ({len(s.files)} so far)"
        await _split_card(task, s)
        return

    path = await _fetch_source(task)

    if task.mode in ("video", "doc", "audio"):
        t0 = time.time()
        if task.mode == "audio":
            await uploader.send_file(task, bot, path, "audio")
        else:
            await uploader.send_any(task, bot, path, want_video=(task.mode == "video"),
                                    display_name=task.name)
        task.t_upload = time.time() - t0
        task.result_text = (f"Uploaded {humanbytes(os.path.getsize(path)) if os.path.exists(path) else ''}\n"
                            f"⏱ Download {fmt_secs(task.t_download)} · Upload {fmt_secs(task.t_upload)}")
        return

    # ---- unzip modes -------------------------------------------------------
    out = await _extract(task, path)
    if task.source != "local":
        try:
            os.remove(path)           # free disk space as soon as extraction is done
        except OSError:
            pass
    files = extractor.list_extracted(out)
    if not files:
        raise TaskFailed("The archive contains no files.")

    task.file_count = len(files)
    want_video = task.mode == "unzip_video"
    t0 = time.time()
    sent = 0
    for i, fpath in enumerate(files, 1):          # natural episode order, one by one
        task.check_cancel()
        task.file_index = i
        rel = os.path.relpath(fpath, out)
        await uploader.send_any(task, bot, fpath, want_video, display_name=os.path.basename(rel))
        sent += 1
        try:
            os.remove(fpath)              # keep disk usage low on big seasons
        except OSError:
            pass
        if i < len(files):
            await asyncio.sleep(Config.UPLOAD_GAP)
    task.t_upload = time.time() - t0
    task.result_text = (f"📦 {sent} file(s) sent in order\n"
                        f"⏱ Download {fmt_secs(task.t_download)} · Upload {fmt_secs(task.t_upload)}")
