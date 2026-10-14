# -*- coding: utf-8 -*-
"""Archive handling. Never blocks the event loop and always checks the cancel flag.

zip            -> python zipfile in a worker thread (byte-accurate progress)
rar/7z/tar/... -> 7-Zip CLI (async subprocess, killed on cancel); bsdtar fallback
Result list is NATURALLY sorted (Episode 2 before Episode 10) so uploads keep order.
"""
import asyncio
import logging
import os
import re
import shutil
import zipfile

from core.tasks import Cancelled, TaskFailed
from helper_funcs.utils import JUNK_NAMES, natural_key

logger = logging.getLogger(__name__)
CHUNK = 1024 * 1024


class NeedPassword(Exception):
    pass


class WrongPassword(Exception):
    pass


# ------------------------------------------------------------------ helpers
def _free_bytes(path):
    try:
        return shutil.disk_usage(path).free
    except Exception:
        return 1 << 60


def _clean_member(name, flag_bits):
    if not (flag_bits & 0x800):                      # not flagged UTF-8 -> maybe mis-decoded
        try:
            name = name.encode("cp437").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".", "..")]
    return parts


def _is_junk(parts):
    return (not parts) or parts[0] == "__MACOSX" or parts[-1].lower() in JUNK_NAMES \
        or parts[-1].startswith("._")


def dir_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def list_extracted(root):
    """All real files, naturally sorted by relative path (episode order)."""
    out = []
    for dp, _, files in os.walk(root):
        for f in files:
            if f.lower() in JUNK_NAMES or f.startswith("._"):
                continue
            out.append(os.path.join(dp, f))
    out.sort(key=lambda p: natural_key(os.path.relpath(p, root).replace(os.sep, "/")))
    return out


# ---------------------------------------------------------------------- zip
def _zip_info(path):
    """-> (is_zip, encrypted, needs_7z)"""
    if not zipfile.is_zipfile(path):
        return False, False, True
    with zipfile.ZipFile(path) as zf:
        infos = zf.infolist()
        enc = any(i.flag_bits & 0x1 for i in infos)
        exotic = any(i.compress_type not in (0, 8, 12, 14) for i in infos)  # AES(99), deflate64...
        return True, enc, exotic


def _pick_password(zf, password):
    first = next((i for i in zf.infolist() if i.flag_bits & 0x1 and not i.is_dir()), None)
    if first is None:
        return None
    for enc in ("utf-8", "cp437", "latin-1"):
        try:
            pwd = password.encode(enc)
        except UnicodeEncodeError:
            continue
        try:
            with zf.open(first, pwd=pwd) as fh:
                fh.read(1)
            return pwd
        except RuntimeError:
            continue
        except zipfile.BadZipFile:
            continue
    raise WrongPassword()


def _extract_zip_sync(path, out, password, task):
    with zipfile.ZipFile(path) as zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        total = sum(i.file_size for i in infos)
        if total > _free_bytes(out) - 50 * 1024 * 1024:
            raise TaskFailed("Not enough free disk space to extract this archive.")
        encrypted = any(i.flag_bits & 0x1 for i in infos)
        pwd = None
        if encrypted:
            if not password:
                raise NeedPassword()
            pwd = _pick_password(zf, password)
        task.begin_stage(total)
        task.file_count = len(infos)
        done = 0
        root = os.path.realpath(out)
        for info in infos:
            task.check_cancel()
            parts = _clean_member(info.filename, info.flag_bits)
            if _is_junk(parts):
                continue
            target = os.path.realpath(os.path.join(root, *parts))
            if not target.startswith(root + os.sep):
                continue                                  # zip-slip protection
            os.makedirs(os.path.dirname(target), exist_ok=True)
            try:
                with zf.open(info, pwd=pwd) as src, open(target, "wb") as dst:
                    while True:
                        task.check_cancel()
                        buf = src.read(CHUNK)
                        if not buf:
                            break
                        dst.write(buf)
                        done += len(buf)
                        task.advance(done)
            except (RuntimeError, zipfile.BadZipFile) as e:
                if encrypted:
                    raise WrongPassword()
                raise TaskFailed(f"Corrupted archive: {str(e)[:80]}")
        task.advance(done, max(total, done))


# ------------------------------------------------------------- 7-Zip / bsdtar
def _seven():
    return shutil.which("7z") or shutil.which("7zz") or shutil.which("7za")


async def _run(args, task=None, poll=None):
    proc = await asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    waiter = asyncio.create_task(proc.communicate())
    try:
        while not waiter.done():
            await asyncio.wait({waiter}, timeout=1.5)
            if poll and not waiter.done():
                poll()
            if task is not None and task.cancelled:
                raise Cancelled()
        out, _ = waiter.result()
        return proc.returncode, (out or b"").decode("utf-8", "replace")
    except BaseException:
        if proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        waiter.cancel()
        raise


async def _list_7z(path, password):
    exe = _seven()
    args = [exe, "l", "-slt", "-y"]
    if password:
        args.append(f"-p{password}")
    args += ["--", path]
    rc, out = await _run(args)
    low = out.lower()
    if "wrong password" in low or "enter password" in low:
        return None, True
    total, enc = 0, "encrypted = +" in low
    for block in out.split("\n\n"):
        if "Folder = -" in block:
            m = re.search(r"^Size = (\d+)", block, re.M)
            if m:
                total += int(m.group(1))
    return total, enc


async def _extract_7z(path, out, password, task):
    exe = _seven()
    if not exe:
        return await _extract_bsdtar(path, out, password, task)
    total, enc = await _list_7z(path, password)
    if total is None or (enc and not password):
        raise NeedPassword() if not password else WrongPassword()
    if total > _free_bytes(out) - 50 * 1024 * 1024:
        raise TaskFailed("Not enough free disk space to extract this archive.")
    task.begin_stage(total)
    args = [exe, "x", "-y", "-aoa", f"-o{out}"]
    if password:
        args.append(f"-p{password}")
    args += ["--", path]
    rc, text = await _run(args, task, poll=lambda: task.advance(dir_size(out)))
    low = text.lower()
    if rc != 0:
        if "wrong password" in low or "data error in encrypted" in low or "crc failed in encrypted" in low:
            raise WrongPassword()
        if "unsupported" in low or "can not open" in low:
            return await _extract_bsdtar(path, out, password, task)
        raise TaskFailed("Extraction failed: " + (text.strip().splitlines() or ["unknown error"])[-1][:120])
    task.advance(total or dir_size(out), total or None)


async def _extract_bsdtar(path, out, password, task):
    exe = shutil.which("bsdtar")
    if not exe:
        raise TaskFailed("No extractor available on the server (install p7zip-full).")
    args = [exe, "-xf", path, "-C", out]
    if password:
        args += ["--passphrase", password]
    task.begin_stage(0)
    rc, text = await _run(args, task, poll=lambda: task.advance(dir_size(out)))
    if rc != 0:
        if "passphrase" in text.lower() or "encrypted" in text.lower():
            raise (WrongPassword() if password else NeedPassword())
        raise TaskFailed("Extraction failed: " + (text.strip().splitlines() or ["unknown error"])[-1][:120])


# ---------------------------------------------------------------- public API
async def extract(task, archive_path, out_dir, password=None):
    """Extract archive_path into out_dir. May raise NeedPassword / WrongPassword."""
    os.makedirs(out_dir, exist_ok=True)
    is_zip, _enc, exotic = await asyncio.to_thread(_zip_info, archive_path)
    if is_zip and not exotic:
        try:
            await asyncio.to_thread(_extract_zip_sync, archive_path, out_dir, password, task)
        except zipfile.BadZipFile:
            raise TaskFailed("This ZIP file is corrupted or incomplete.")
        return
    await _extract_7z(archive_path, out_dir, password, task)
