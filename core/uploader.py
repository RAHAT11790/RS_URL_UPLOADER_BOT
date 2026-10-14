# -*- coding: utf-8 -*-
"""Telegram upload: reply-threaded, cancellable, flood-safe, splits oversize files."""
import asyncio
import logging
import os
import time

from pyrogram.errors import BadRequest, FloodWait, Forbidden, MessageIdInvalid, RPCError

try:  # exists in every pyrogram flavour; guard just in case
    from pyrogram import StopTransmission
except ImportError:  # pragma: no cover
    class StopTransmission(Exception):
        pass

from config import Config
from core import media
from core.tasks import Cancelled, TaskFailed
from helper_funcs.ui import esc
from helper_funcs.utils import VIDEO_EXTS, humanbytes

logger = logging.getLogger(__name__)


def _flood(e):
    return int(getattr(e, "value", None) or getattr(e, "x", None) or 10)


def split_file(path, part_size, task):
    """Binary split -> name.001, name.002 ... (runs in a thread)."""
    parts, idx = [], 1
    total = os.path.getsize(path)
    task.begin_stage(total)
    done = 0
    with open(path, "rb") as src:
        while True:
            task.check_cancel()
            chunk_path = f"{path}.{idx:03d}"
            written = 0
            with open(chunk_path, "wb") as dst:
                while written < part_size:
                    task.check_cancel()
                    buf = src.read(min(8 * 1024 * 1024, part_size - written))
                    if not buf:
                        break
                    dst.write(buf)
                    written += len(buf)
                    done += len(buf)
                    task.advance(done)
            if written == 0:
                os.remove(chunk_path)
                break
            parts.append(chunk_path)
            idx += 1
    return parts


async def _send_once(task, bot, kind, path, caption, thumb, meta):
    async def progress(cur, tot):
        if task.cancelled:
            raise StopTransmission()
        task.advance(cur, tot)

    kw = {kind: path, "caption": caption, "progress": progress}
    if thumb and kind in ("video", "audio", "document"):
        kw["thumb"] = thumb
    if kind == "video":
        w, h, d = meta
        kw.update(duration=d, width=w, height=h, supports_streaming=True)
    elif kind == "audio":
        kw.update(duration=meta)

    try:
        return await getattr(task.anchor, f"reply_{kind}")(quote=True, **kw)
    except MessageIdInvalid:   # the user deleted the original message
        return await getattr(bot, f"send_{kind}")(chat_id=task.chat_id, **kw)


async def send_file(task, bot, path, kind, display_name=None):
    """Upload ONE file (retry + flood handling). kind: video|document|audio."""
    size = os.path.getsize(path)
    name = display_name or os.path.basename(path)
    task.current_name = name
    caption = f"<code>{esc(name)}</code>"

    thumb, meta, tmp_thumb = None, None, None
    if kind == "video":
        meta = await media.video_meta(path)
        thumb = await media.user_thumb(bot, task.user_id)
        if not thumb:
            tmp_thumb = await media.frame_thumb(path, path + ".thumb.jpg", meta[2])
            thumb = tmp_thumb
    elif kind == "audio":
        meta = await media.audio_duration(path)
        thumb = await media.user_thumb(bot, task.user_id)
    else:
        thumb = await media.user_thumb(bot, task.user_id)

    try:
        attempt = 0
        while True:
            task.check_cancel()
            task.set_state("upload")
            task.begin_stage(size)
            try:
                return await _send_once(task, bot, kind, path, caption, thumb, meta)
            except FloodWait as e:
                wait = _flood(e) + 1
                task.set_state("flood", flood_until=time.time() + wait)
                await asyncio.sleep(wait)          # cancel interrupts this sleep
                continue                           # flood waits do not count as attempts
            except StopTransmission:
                raise Cancelled()
            except (BadRequest, Forbidden) as e:
                raise TaskFailed(f"Telegram rejected the file: {type(e).__name__}")
            except (RPCError, OSError, asyncio.TimeoutError, ConnectionError) as e:
                attempt += 1
                if attempt >= Config.UL_RETRIES:
                    raise TaskFailed(f"Upload failed after {attempt} tries ({type(e).__name__}).")
                task.note = f"upload retry {attempt}/{Config.UL_RETRIES}"
                await asyncio.sleep(3 * attempt)
    finally:
        task.note = ""
        if tmp_thumb:
            try:
                os.remove(tmp_thumb)
            except OSError:
                pass


async def send_any(task, bot, path, want_video, display_name=None):
    """Chooses video/document, splits files over the Telegram limit."""
    size = os.path.getsize(path)
    ext = os.path.splitext(path)[1].lower()
    if size > Config.TG_MAX_FILE_SIZE:
        if not Config.AUTO_SPLIT:
            raise TaskFailed(f"{humanbytes(size)} is over the Telegram limit.")
        task.set_state("split")
        parts = await asyncio.to_thread(split_file, path, Config.PART_SIZE, task)
        try:
            for p in parts:
                await send_file(task, bot, p, "document")
                await asyncio.sleep(Config.UPLOAD_GAP)
        finally:
            for p in parts:
                try:
                    os.remove(p)
                except OSError:
                    pass
        return
    kind = "video" if (want_video and ext in VIDEO_EXTS) else "document"
    await send_file(task, bot, path, kind, display_name)
