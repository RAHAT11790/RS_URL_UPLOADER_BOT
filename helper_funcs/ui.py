# -*- coding: utf-8 -*-
"""Look & feel helpers: fonts, quote blocks, progress bars, coloured buttons."""
import html
import inspect
import logging

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import Config

logger = logging.getLogger(__name__)

_ASCII_U = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_ASCII_L = "abcdefghijklmnopqrstuvwxyz"
_ASCII_D = "0123456789"
_BOLD = str.maketrans(
    _ASCII_U + _ASCII_L + _ASCII_D,
    "𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭" "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇" "𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵",
)
_SMALL = str.maketrans(_ASCII_L, "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ")


def fb(text):
    """𝗕𝗼𝗹𝗱 𝗦𝗮𝗻𝘀 (unicode) – used for titles."""
    return str(text).translate(_BOLD)


def sc(text):
    """ꜱᴍᴀʟʟ ᴄᴀᴘꜱ – used for labels."""
    return str(text).translate(_SMALL)


def esc(text):
    return html.escape(str(text), quote=False)


def short(text, n=60):
    text = str(text)
    return text if len(text) <= n else text[: n - 1] + "…"


def bar(pct, width=14):
    pct = max(0.0, min(100.0, float(pct)))
    filled = int(round(pct / 100 * width))
    return "▰" * filled + "▱" * (width - filled)


def quote(text, expandable=False):
    tag = "blockquote expandable" if expandable else "blockquote"
    return f"<{tag}>{text}</{tag}>"


LINE = "━━━━━━━━━━━━━━━━━━"


# ------------------------------------------------------------------ buttons
try:
    _STYLE_OK = Config.BUTTON_STYLE and "style" in inspect.signature(
        InlineKeyboardButton.__init__
    ).parameters
except Exception:  # pragma: no cover
    _STYLE_OK = False
logger.info("Coloured inline buttons: %s", "ON" if _STYLE_OK else "OFF (library has no 'style')")

RED, GREEN, BLUE = "danger", "success", "primary"


def B(text, data=None, style=None, url=None):
    kw = {"text": text}
    if url:
        kw["url"] = url
    else:
        kw["callback_data"] = data
    if style and _STYLE_OK:
        kw["style"] = style
    return InlineKeyboardButton(**kw)


def kb(*rows):
    return InlineKeyboardMarkup([list(r) for r in rows if r])


def cancel_btn(task_id):
    return B("🚫 Cancel", f"cx:{task_id}", RED)
