# -*- coding: utf-8 -*-
import os
import re
import secrets
from urllib.parse import urlparse, unquote

VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".m4v", ".ts", ".3gp")
AUDIO_EXTS = (".mp3", ".m4a", ".aac", ".flac", ".ogg", ".wav", ".opus", ".wma")
ARCHIVE_EXTS = (".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".tbz2", ".txz")
JUNK_NAMES = {"thumbs.db", ".ds_store", "desktop.ini"}


# ---------------------------------------------------------------- formatting
def humanbytes(size):
    if not size:
        return "0 B"
    size = float(size)
    units = ("B", "KB", "MB", "GB", "TB")
    i = 0
    while size >= 1024 and i < len(units) - 1:
        size /= 1024
        i += 1
    return f"{int(size)} B" if i == 0 else f"{size:.2f} {units[i]}"


def fmt_secs(seconds):
    seconds = int(max(0, seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    parts = []
    if d:
        parts.append(f"{d}d")
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if s or not parts:
        parts.append(f"{s}s")
    return " ".join(parts[:3])


def TimeFormatter(milliseconds):  # backwards-compatible alias
    return fmt_secs(int(milliseconds) // 1000)


def new_id(n=3):
    return secrets.token_hex(n)


# ------------------------------------------------------------------ sorting
def natural_key(s):
    """'Episode 2' < 'Episode 10'; 'E01' and 'E1' stay adjacent and stable."""
    parts = re.split(r"(\d+)", s.lower())
    key = [int(p) if i % 2 else p for i, p in enumerate(parts)]
    return key, s


def sort_paths(paths, root):
    def k(p):
        rel = os.path.relpath(p, root).replace(os.sep, "/")
        return natural_key(rel)
    return sorted(paths, key=k)


# -------------------------------------------------------------------- names
def safe_filename(name, default="file", max_bytes=180):
    name = os.path.basename((name or "").replace("\\", "/"))
    name = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "_", name).strip(" .")
    if not name:
        return default
    base, ext = os.path.splitext(name)
    while len((base + ext).encode("utf-8")) > max_bytes and base:
        base = base[:-1]
    return (base + ext) or default


def filename_from_disposition(cd):
    if not cd:
        return None
    m = re.search(r"filename\*\s*=\s*[^']*'[^']*'([^;]+)", cd, re.I)
    if m:
        return unquote(m.group(1).strip().strip('"'))
    m = re.search(r'filename\s*=\s*"([^"]+)"', cd, re.I) or re.search(r"filename\s*=\s*([^;]+)", cd, re.I)
    if m:
        return unquote(m.group(1).strip().strip('"').strip("'"))
    return None


def filename_from_url(url):
    path = urlparse(url).path
    return unquote(path.rsplit("/", 1)[-1]) if path else ""


def domain_of(url):
    try:
        host = urlparse(url).netloc.split("@")[-1]
        return host or "link"
    except Exception:
        return "link"


# ---------------------------------------------------------------------- URLs
_PD_FILE = re.compile(
    r"^https?://(?:www\.)?(pixeldrain\.[a-z0-9.]+)/u/([A-Za-z0-9_-]+)/?(?:[?#].*)?$", re.I
)
_PD_API = re.compile(
    r"^(https?://(?:www\.)?pixeldrain\.[a-z0-9.]+/api/file/[A-Za-z0-9_-]+)/?(\?.*)?$", re.I
)


def normalize_url(url):
    """pixeldrain.<tld>/u/<id>  ->  pixeldrain.<tld>/api/file/<id>?download
    Direct links are returned untouched (a missing ?download is added)."""
    url = url.strip()
    m = _PD_FILE.match(url)
    if m:
        return f"https://{m.group(1)}/api/file/{m.group(2)}?download"
    m = _PD_API.match(url)
    if m and "download" not in (m.group(2) or ""):
        return f"{m.group(1)}?download"
    return url


def parse_user_line(line):
    """'url | name | user | pass'  ->  (url, name|None, user|None, pass|None)"""
    parts = [p.strip() for p in line.split("|")]
    url = normalize_url(parts[0])
    name = parts[1] if len(parts) >= 2 and parts[1] else None
    user = parts[2] if len(parts) >= 4 and parts[2] else None
    pwd = parts[3] if len(parts) >= 4 and parts[3] else None
    return url, name, user, pwd


# ------------------------------------------------------------------ archives
_SPLIT_RE = re.compile(r"(\.\d{3}|\.z\d{2}|\.r\d{2}|\.part\d+\.rar)$", re.I)


def is_split_volume(name):
    n = name.lower()
    if n.endswith(".part1.rar") or re.search(r"\.part0*1\.rar$", n):
        return True
    return bool(_SPLIT_RE.search(n))


def split_base(name):
    """Group key for the volumes of one archive."""
    n = name
    n = re.sub(r"\.part\d+\.rar$", "", n, flags=re.I)
    n = re.sub(r"\.(\d{3}|z\d{2}|r\d{2})$", "", n, flags=re.I)
    n = re.sub(r"\.(zip|rar|7z)$", "", n, flags=re.I)
    return n.lower()


def is_archive_name(name):
    n = (name or "").lower()
    return n.endswith(ARCHIVE_EXTS) or is_split_volume(n)


def pick_first_volume(files):
    """files: list of paths of one split set -> the path 7-Zip should open."""
    def rank(p):
        n = os.path.basename(p).lower()
        if re.search(r"\.part0*1\.rar$", n):
            return (0, natural_key(n))
        if re.search(r"\.001$", n):
            return (0, natural_key(n))
        if n.endswith((".zip", ".rar", ".7z")):
            return (1, natural_key(n))
        return (2, natural_key(n))
    return sorted(files, key=rank)[0]
