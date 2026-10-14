# -*- coding: utf-8 -*-
"""HTTP probing + resumable, cancellable download (aiohttp)."""
import asyncio
import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

import aiohttp

from config import Config
from core.tasks import TaskFailed
from helper_funcs.utils import filename_from_disposition, filename_from_url

logger = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _headers(extra=None):
    h = {"User-Agent": UA, "Accept": "*/*", "Accept-Encoding": "identity"}
    if extra:
        h.update(extra)
    return h


@dataclass
class Probe:
    size: Optional[int] = None
    name: Optional[str] = None
    ctype: str = ""
    error: Optional[str] = None


def _auth(auth):
    return aiohttp.BasicAuth(auth[0], auth[1]) if auth else None


def _total_from_range(value):
    m = re.search(r"/(\d+)\s*$", value or "")
    return int(m.group(1)) if m else None


async def probe(url, auth=None):
    """Find size / filename without downloading. Never raises."""
    timeout = aiohttp.ClientTimeout(total=40, connect=15)
    res = Probe()
    try:
        async with aiohttp.ClientSession(timeout=timeout) as s:
            # 1) HEAD
            try:
                async with s.head(url, headers=_headers(), allow_redirects=True, auth=_auth(auth)) as r:
                    if r.status < 400:
                        cl = r.headers.get("Content-Length")
                        res.size = int(cl) if cl and cl.isdigit() and int(cl) > 0 else None
                        res.ctype = r.headers.get("Content-Type", "")
                        res.name = filename_from_disposition(r.headers.get("Content-Disposition")) \
                            or filename_from_url(str(r.url))
            except (aiohttp.ClientError, asyncio.TimeoutError):
                pass
            # 2) many servers reject HEAD -> ranged GET of one byte
            if res.size is None or not res.name:
                try:
                    async with s.get(url, headers=_headers({"Range": "bytes=0-0"}),
                                     allow_redirects=True, auth=_auth(auth)) as r:
                        if r.status >= 400:
                            if res.size is None and not res.ctype:
                                res.error = f"HTTP {r.status}"
                            return res
                        res.error = None
                        res.ctype = res.ctype or r.headers.get("Content-Type", "")
                        if r.status == 206:
                            res.size = res.size or _total_from_range(r.headers.get("Content-Range"))
                        else:
                            cl = r.headers.get("Content-Length")
                            if res.size is None and cl and cl.isdigit() and int(cl) > 0:
                                res.size = int(cl)
                        res.name = res.name or filename_from_disposition(
                            r.headers.get("Content-Disposition")) or filename_from_url(str(r.url))
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    if res.size is None and not res.ctype:
                        res.error = type(e).__name__
    except Exception as e:  # DNS / SSL / invalid URL
        res.error = f"{type(e).__name__}"
    return res


class _Http(Exception):
    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.status = status


async def _write(loop, f, data):
    await loop.run_in_executor(None, f.write, data)


async def download(task, url, dest, auth=None):
    """Resumable download. Cancel-safe: task.runner.cancel() stops it instantly."""
    loop = asyncio.get_running_loop()
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    timeout = aiohttp.ClientTimeout(total=None, connect=20, sock_connect=20, sock_read=60)
    attempt = 0
    task.begin_stage(task.size or 0)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        while True:
            task.check_cancel()
            offset = os.path.getsize(dest) if os.path.exists(dest) else 0
            extra = {"Range": f"bytes={offset}-"} if offset else None
            try:
                async with session.get(url, headers=_headers(extra), allow_redirects=True,
                                       auth=_auth(auth)) as resp:
                    if resp.status == 416 and offset:       # already complete
                        task.advance(offset, offset)
                        return dest
                    if resp.status not in (200, 206):
                        raise _Http(resp.status)
                    if resp.status == 200:
                        offset = 0                          # server ignored Range
                    total = None
                    if resp.status == 206:
                        total = _total_from_range(resp.headers.get("Content-Range"))
                    if total is None:
                        cl = resp.headers.get("Content-Length")
                        if cl and cl.isdigit():
                            total = offset + int(cl)
                    if total:
                        task.total = total
                    elif task.size:
                        task.total = task.size
                    if task.total and task.total > Config.TG_MAX_FILE_SIZE and \
                            not Config.AUTO_SPLIT and task.mode in ("video", "doc", "audio"):
                        raise TaskFailed("File is larger than the Telegram limit.")

                    mode = "ab" if (resp.status == 206 and offset) else "wb"
                    done = offset if mode == "ab" else 0
                    f = await loop.run_in_executor(None, open, dest, mode)
                    try:
                        async for chunk in resp.content.iter_chunked(Config.CHUNK_SIZE):
                            await _write(loop, f, chunk)
                            done += len(chunk)
                            task.advance(done)
                    finally:
                        await loop.run_in_executor(None, f.close)

                    if task.total and done < task.total:
                        raise aiohttp.ClientPayloadError("connection closed early")
                    task.note = ""
                    task.advance(done, max(task.total, done))
                    return dest

            except asyncio.CancelledError:
                raise
            except TaskFailed:
                raise
            except _Http as e:
                if e.status in (408, 425, 429) or e.status >= 500:
                    err = str(e)
                else:
                    raise TaskFailed(f"Server answered {e} – link is not downloadable.")
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                err = type(e).__name__

            attempt += 1
            if attempt > Config.DL_RETRIES:
                raise TaskFailed(f"Download failed after {Config.DL_RETRIES} retries ({err}).")
            wait = min(2 ** attempt, 20)
            task.note = f"retry {attempt}/{Config.DL_RETRIES} in {wait}s ({err})"
            task.wake_up()
            await asyncio.sleep(wait)
