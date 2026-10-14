# -*- coding: utf-8 -*-
"""ffprobe / ffmpeg helpers and thumbnails (all non-blocking)."""
import asyncio
import json
import logging
import os

from config import Config
from database.access import clinton

logger = logging.getLogger(__name__)
_thumb_ids = {}


async def _exec(*args, timeout=60):
    proc = await asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
        return proc.returncode, out
    except BaseException:
        if proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        raise


async def video_meta(path):
    """-> (width, height, duration_seconds); zeros when unknown."""
    try:
        rc, out = await _exec(
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height:format=duration", "-of", "json", path)
        if rc != 0:
            return 0, 0, 0
        data = json.loads(out.decode() or "{}")
        st = (data.get("streams") or [{}])[0]
        dur = float((data.get("format") or {}).get("duration") or 0)
        return int(st.get("width") or 0), int(st.get("height") or 0), int(dur)
    except (asyncio.CancelledError, KeyboardInterrupt):
        raise
    except Exception:
        return 0, 0, 0


async def audio_duration(path):
    return (await video_meta(path))[2]


async def frame_thumb(video_path, out_path, duration):
    """Grab one frame as a Telegram-friendly JPEG. Returns path or None."""
    try:
        ts = min(5, max(0, duration // 2)) if duration else 1
        rc, _ = await _exec(
            "ffmpeg", "-y", "-ss", str(ts), "-i", video_path, "-frames:v", "1",
            "-vf", "scale=320:-2", "-q:v", "5", out_path, timeout=60)
        return out_path if rc == 0 and os.path.exists(out_path) else None
    except (asyncio.CancelledError, KeyboardInterrupt):
        raise
    except Exception:
        return None


def _prep_thumb(src, dst):
    from PIL import Image
    with Image.open(src) as im:
        im = im.convert("RGB")
        im.thumbnail((320, 320))
        im.save(dst, "JPEG", quality=85)
    return dst


async def user_thumb(bot, user_id):
    """The user's saved custom thumbnail as a local jpg (cached) or None."""
    file_id = await clinton.get_thumbnail(user_id)
    if not file_id:
        return None
    dst = os.path.join(Config.THUMB_DIR, f"{user_id}.jpg")
    if _thumb_ids.get(user_id) == file_id and os.path.exists(dst):
        return dst
    try:
        raw = await bot.download_media(file_id, file_name=os.path.join(Config.THUMB_DIR, f"{user_id}.raw"))
        await asyncio.to_thread(_prep_thumb, raw, dst)
        try:
            os.remove(raw)
        except OSError:
            pass
        _thumb_ids[user_id] = file_id
        return dst
    except Exception as e:
        logger.warning("thumbnail prep failed: %s", e)
        return None


def forget_thumb(user_id):
    _thumb_ids.pop(user_id, None)
    try:
        os.remove(os.path.join(Config.THUMB_DIR, f"{user_id}.jpg"))
    except OSError:
        pass
