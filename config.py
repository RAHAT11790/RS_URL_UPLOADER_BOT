import os


def _int(name, default=0):
    try:
        return int(os.environ.get(name, default) or default)
    except ValueError:
        return default


def _bool(name, default=False):
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


class Config(object):
    # ---- Secrets: ONLY from environment variables (never hard-code them) ----
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "8403055446:AAHVcdv8galM0jD1u_dCFVBgGnz6vCZIMrU")
    API_ID = _int("API_ID", "25976192")
    API_HASH = os.environ.get("API_HASH", "8ba23141980539b4896e5adbc4ffd2e2")
    OWNER_ID = _int("OWNER_ID", "6621572366")
    DATABASE_URL = os.environ.get("DATABASE_URL", "mongodb+srv://RAHAT1132:RAHAT11a@rahat.txn4lkk.mongodb.net/?appName=Rahat")

    SESSION_NAME = "RS_URL_UPLOADER_BOT"
    PREMIUM_USER = _bool("PREMIUM_USER")

    # ---- Paths ----
    DOWNLOAD_LOCATION = os.path.abspath("./DOWNLOADS")
    THUMB_DIR = os.path.join(DOWNLOAD_LOCATION, "_thumbs")

    # ---- Telegram limits ----
    TG_MAX_FILE_SIZE = (4000 if PREMIUM_USER else 2000) * 1024 * 1024
    PART_SIZE = 1900 * 1024 * 1024          # split size for oversize files
    AUTO_SPLIT = _bool("AUTO_SPLIT", True)  # split files above the Telegram limit

    # ---- Queue rules ----
    BIG_FILE_THRESHOLD = 1024 ** 3   # > 1 GiB (or unknown size) => runs ALONE
    MAX_PARALLEL_SMALL = _int("MAX_PARALLEL_SMALL", 4)   # <= 1 GiB => up to 4 at once
    GLOBAL_MAX_TASKS = _int("GLOBAL_MAX_TASKS", 12)      # server-wide safety cap

    # ---- Network ----
    CHUNK_SIZE = 1024 * 1024
    DL_RETRIES = 5
    UL_RETRIES = 3
    UPLOAD_GAP = 1.0                 # seconds between files of one archive

    # ---- UI ----
    PROGRESS_UPDATE_INTERVAL = 3.0   # seconds between status edits
    PENDING_TTL = 30 * 60            # seconds a "choose format" card stays valid
    PASSWORD_TIMEOUT = 300
    MAX_URLS_PER_MESSAGE = 10
    BUTTON_STYLE = _bool("BUTTON_STYLE", True)  # coloured buttons (Bot API 9.4+)

    @classmethod
    def missing(cls):
        out = []
        if not cls.BOT_TOKEN:
            out.append("BOT_TOKEN")
        if not cls.API_ID:
            out.append("API_ID")
        if not cls.API_HASH:
            out.append("API_HASH")
        return out
