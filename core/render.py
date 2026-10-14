# -*- coding: utf-8 -*-
"""Builds the text + buttons of the single status card of a task."""
import time

from config import Config
from helper_funcs.ui import (B, LINE, bar, cancel_btn, esc, fb, kb, quote, sc, short)
from helper_funcs.utils import domain_of, fmt_secs, humanbytes

TITLES = {
    "queued": ("⏳", "QUEUED"),
    "running": ("⚙️", "STARTING"),
    "download": ("📥", "DOWNLOADING"),
    "extract": ("📂", "EXTRACTING"),
    "split": ("✂️", "SPLITTING"),
    "upload": ("📤", "UPLOADING"),
    "flood": ("⏰", "FLOOD WAIT"),
    "password": ("🔐", "PASSWORD REQUIRED"),
    "done": ("✅", "COMPLETED"),
    "failed": ("❌", "FAILED"),
    "cancelled": ("🚫", "CANCELLED"),
}


def _source(task):
    if task.source == "url" and task.url:
        return f"🔗 {sc('source')}: <code>{esc(short(domain_of(task.url), 40))}</code>"
    return f"🔗 {sc('source')}: <code>Telegram file</code>"


def _head(task):
    emo, title = TITLES.get(task.state, ("⚙️", task.state.upper()))
    return f"{emo} <b>{fb(title)}</b>  ·  <code>#{task.id}</code>"


def _info(task):
    return f"📄 <code>{esc(short(task.current_name or task.name, 70))}</code>\n{_source(task)}"


def _progress_lines(task, with_files=False):
    pct = (task.done * 100 / task.total) if task.total else 0
    spd = task.meter.speed
    left = (task.total - task.done) / spd if spd > 0 and task.total else 0
    lines = []
    if with_files and task.file_count:
        lines.append(f"🗂 {sc('file')}: <b>{task.file_index}/{task.file_count}</b>")
    lines.append(f"{bar(pct)} <b>{pct:.1f}%</b>" if task.total else f"{bar(0)} <b>…</b>")
    total_txt = humanbytes(task.total) if task.total else "?"
    lines.append(f"💾 {humanbytes(task.done)} / {total_txt}")
    lines.append(f"⚡ {humanbytes(spd)}/s   ⏳ {fmt_secs(left) if left else '—'}")
    if task.note:
        lines.append(f"🔄 {esc(task.note)}")
    return lines


def render(task):
    st = task.state
    head = _head(task)
    buttons = kb([cancel_btn(task.id)]) if not task.finished else None

    if st == "queued":
        who = f"#{task.queue_pos}" if task.queue_pos else "…"
        kind = "🐘 large (runs alone)" if task.is_big else "🐇 small (parallel)"
        body = (
            f"{_info(task)}\n{LINE}\n"
            f"🎟 {sc('position')}: <b>{who}</b>\n"
            f"📦 {sc('size')}: {humanbytes(task.size) if task.size else 'unknown'} — {kind}\n"
            f"🕐 {esc(task.queue_reason or 'waiting for a free slot')}"
        )
    elif st in ("download", "extract", "split", "upload"):
        body = f"{_info(task)}\n{LINE}\n" + "\n".join(
            _progress_lines(task, with_files=st in ("upload",) and task.file_count > 1)
        )
        if st == "extract" and task.file_count:
            body += f"\n🗂 {sc('files')}: {task.file_count}"
    elif st == "flood":
        wait = max(0, int(task.flood_until - time.time()))
        body = (f"{_info(task)}\n{LINE}\n⚠️ Telegram rate-limit\n"
                f"⏱ {sc('resuming in')}: <b>{wait}s</b>\n🔄 continues automatically")
    elif st == "password":
        body = (f"{_info(task)}\n{LINE}\n🔒 This archive is protected.\n"
                f"💬 <b>Reply to this message</b> with the password.\n"
                f"⌛ {sc('waiting')}: {fmt_secs(Config.PASSWORD_TIMEOUT)}"
                + (f"\n⚠️ {esc(task.note)}" if task.note else ""))
    elif st == "done":
        body = f"{_info(task)}\n{LINE}\n{esc(task.result_text) or 'All done.'}"
    elif st == "failed":
        body = f"{_info(task)}\n{LINE}\n⚠️ {esc(task.error or 'Unknown error')}"
    elif st == "cancelled":
        body = f"{_info(task)}\n{LINE}\n🧹 Stopped and temporary files removed."
    else:  # running / starting
        body = f"{_info(task)}\n{LINE}\n🚀 Preparing…"

    return f"{head}\n{quote(body)}", buttons
