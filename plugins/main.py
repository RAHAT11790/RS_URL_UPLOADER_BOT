# -*- coding: utf-8 -*-
"""User-facing handlers. Handlers stay tiny: they validate, create a Task and
return immediately, so the bot never feels slow while something downloads."""
import asyncio
import logging
import os
import re

from pyrogram import Client, filters

from config import Config
from core import downloader, pipeline
from core.reporter import spawn
from core.state import PASSWORD_WAITERS, PENDING, SPLIT_SETS, Pending, SplitSet
from core.tasks import Task, manager
from database.access import clinton
from database.adduser import AddUser
from helper_funcs.ui import B, BLUE, GREEN, RED, esc, fb, kb, quote, sc, short
from helper_funcs.utils import (AUDIO_EXTS, VIDEO_EXTS, domain_of, filename_from_url, humanbytes,
                                is_archive_name, is_split_volume, new_id, parse_user_line,
                                safe_filename, split_base)
from core import media
from translation import Translation

logger = logging.getLogger(__name__)
CHAT = filters.private | filters.group


async def _pw_reply(_, __, m):
    return bool(m.reply_to_message and m.chat and (m.chat.id, m.reply_to_message.id) in PASSWORD_WAITERS)


pw_reply = filters.create(_pw_reply)


# ------------------------------------------------------------------ commands
@Client.on_message(filters.command("start") & CHAT)
async def start_cmd(bot, m):
    await AddUser(bot, m)
    name = esc(m.from_user.first_name) if m.from_user else "friend"
    await m.reply(Translation.START_TEXT.format(name=name), quote=True,
                  disable_web_page_preview=True,
                  reply_markup=kb([B("💬 Support", url="https://t.me/RS_WONER", style=BLUE)]))


@Client.on_message(filters.command("help") & CHAT)
async def help_cmd(bot, m):
    await m.reply(Translation.HELP_USER, quote=True, disable_web_page_preview=True)


@Client.on_message(filters.command("queue") & CHAT)
async def queue_cmd(bot, m):
    if not m.from_user:
        return
    tasks = manager.user_tasks(m.from_user.id)
    if not tasks:
        await m.reply("📭 <b>Nothing is running.</b>", quote=True)
        return
    icons = {"queued": "⏳", "running": "⚙️", "download": "📥", "extract": "📂", "split": "✂️",
             "upload": "📤", "flood": "⏰", "password": "🔐"}
    lines, rows = [], []
    for t in tasks:
        pct = f" {t.done * 100 / t.total:.0f}%" if t.total and t.state in ("download", "upload", "extract") else ""
        pos = f" (#{t.queue_pos})" if t.state == "queued" and t.queue_pos else ""
        lines.append(f"{icons.get(t.state, '⚙️')} <code>#{t.id}</code> {esc(short(t.name, 38))}{pos}{pct}")
        rows.append(B(f"🚫 #{t.id}", f"cx:{t.id}", RED))
    markup = kb(*[rows[i:i + 3] for i in range(0, len(rows), 3)], [B("🚫 Cancel ALL", "cxa", RED)])
    await m.reply(f"📋 <b>{fb('YOUR TASKS')}</b>\n" + quote("\n".join(lines), expandable=len(lines) > 6),
                  quote=True, reply_markup=markup)


@Client.on_message(filters.command("cancelall") & CHAT)
async def cancelall_cmd(bot, m):
    if not m.from_user:
        return
    n = sum(1 for t in manager.user_tasks(m.from_user.id) if t.cancel())
    await m.reply(f"🚫 Cancelled <b>{n}</b> task(s)." if n else "📭 Nothing to cancel.", quote=True)


# ----------------------------------------------------------------- thumbnail
@Client.on_message(filters.private & filters.photo)
async def save_thumb(bot, m):
    await AddUser(bot, m)
    ok = await clinton.set_thumbnail(m.from_user.id, m.photo.file_id)
    media.forget_thumb(m.from_user.id)
    await m.reply(Translation.SAVED_CUSTOM_THUMB_NAIL if ok else "⚠️ Database is offline – thumbnail not saved.",
                  quote=True)


@Client.on_message(filters.private & filters.command(["delthumbnail", "deletethumbnail"]))
async def del_thumb(bot, m):
    await clinton.set_thumbnail(m.from_user.id, None)
    media.forget_thumb(m.from_user.id)
    await m.reply(Translation.DEL_ETED_CUSTOM_THUMB_NAIL, quote=True)


@Client.on_message(filters.private & filters.command("viewthumbnail"))
async def view_thumb(bot, m):
    fid = await clinton.get_thumbnail(m.from_user.id)
    if fid:
        await m.reply_photo(fid, caption="🖼 Your current thumbnail", quote=True)
    else:
        await m.reply(Translation.NO_THUMB, quote=True)


# -------------------------------------------------------------------- links
def _choice_keyboard(token, name, ctype, archive):
    ext = os.path.splitext(name)[1].lower()
    cancel = [B("🚫 Cancel", f"cq:{token}", RED)]
    if archive:
        return kb([B("🎬 Unzip → Video", f"go:{token}:zv", GREEN),
                   B("📄 Unzip → Document", f"go:{token}:zd", GREEN)],
                  [B("📤 Upload As-Is", f"go:{token}:d", BLUE)], cancel)
    if ext in VIDEO_EXTS or "video" in ctype:
        return kb([B("🎬 Video", f"go:{token}:v", GREEN), B("📄 Document", f"go:{token}:d", BLUE)], cancel)
    if ext in AUDIO_EXTS or "audio" in ctype:
        return kb([B("🎵 Audio", f"go:{token}:a", GREEN), B("📄 Document", f"go:{token}:d", BLUE)], cancel)
    return kb([B("📄 Document", f"go:{token}:d", GREEN), B("🎬 Video", f"go:{token}:v", BLUE)], cancel)


async def process_url(bot, m, line):
    uid = m.from_user.id
    url, name, user, pwd = parse_user_line(line)
    converted = url != line.split("|")[0].strip()
    status = await m.reply("🔎 <b>Checking link…</b>", quote=True)
    auth = (user, pwd) if user and pwd else None
    try:
        pr = await downloader.probe(url, auth)
    except Exception:
        logger.exception("probe crashed")
        pr = downloader.Probe(error="probe error")

    if pr.error and not pr.size and not pr.ctype:
        await status.edit(f"❌ <b>{fb('LINK ERROR')}</b>\n" + quote(
            f"🔗 <code>{esc(short(domain_of(url), 40))}</code>\n⚠️ {esc(pr.error)}\n"
            "Check that the link is public and direct."))
        return

    fname = safe_filename(name or pr.name or filename_from_url(url) or "file")
    archive = is_archive_name(fname) or "zip" in (pr.ctype or "").lower()
    if pr.size and pr.size > Config.TG_MAX_FILE_SIZE and not Config.AUTO_SPLIT and not archive:
        await status.edit(f"⚠️ <b>{fb('TOO LARGE')}</b>\n" + quote(
            f"📦 {humanbytes(pr.size)}\n🚫 Limit: {humanbytes(Config.TG_MAX_FILE_SIZE)}"))
        return

    token = new_id()
    PENDING[token] = Pending(token=token, kind="url", user_id=uid, chat_id=m.chat.id, anchor=m,
                             status=status, name=fname, size=pr.size, url=url, auth=auth)
    big = pr.size is None or pr.size > Config.BIG_FILE_THRESHOLD
    busy = len(manager.user_tasks(uid))
    lines = [f"📄 <code>{esc(short(fname, 70))}</code>",
             f"🔗 {sc('source')}: <code>{esc(short(domain_of(url), 40))}</code>"
             + ("  🔁 <i>direct link</i>" if converted else ""),
             f"📦 {sc('size')}: <b>{humanbytes(pr.size) if pr.size else 'Unknown'}</b>",
             f"🚦 {sc('queue')}: " + ("🐘 large – runs alone" if big else "🐇 small – parallel")]
    if busy:
        lines.append(f"⏳ {busy} task(s) already active – yours will wait if needed")
    title = "ARCHIVE DETECTED" if archive else "FILE DETECTED"
    await status.edit(f"{'📦' if archive else '📁'} <b>{fb(title)}</b>  ·  <code>#{token}</code>\n"
                      + quote("\n".join(lines)) + "\nChoose what to do 👇",
                      reply_markup=_choice_keyboard(token, fname, pr.ctype or "", archive))


@Client.on_message(filters.text & CHAT & ~filters.regex(r"^/") & ~pw_reply)
async def on_text(bot, m):
    if not m.from_user:
        return
    lines = [l.strip() for l in m.text.splitlines() if l.strip().lower().startswith(("http://", "https://"))]
    if not lines:
        if m.chat.type.name == "PRIVATE":
            await m.reply("🌐 Send me a <b>direct link</b> (http/https).", quote=True)
        return
    await AddUser(bot, m)
    for line in lines[:Config.MAX_URLS_PER_MESSAGE]:
        spawn(process_url(bot, m, line))
        await asyncio.sleep(0.4)


@Client.on_message(pw_reply & filters.text & CHAT)
async def on_password(bot, m):
    fut = PASSWORD_WAITERS.get((m.chat.id, m.reply_to_message.id))
    if fut and not fut.done():
        fut.set_result(m.text.strip())
    try:
        await m.delete()          # do not leave the password in the chat
    except Exception:
        pass


# ---------------------------------------------------------- telegram archives
@Client.on_message(filters.document & CHAT)
async def on_document(bot, m):
    if not m.from_user:
        return
    doc = m.document
    fname = safe_filename(doc.file_name or "file")
    if not is_archive_name(fname):
        if m.chat.type.name == "PRIVATE":
            await m.reply("📦 Send an archive (zip / rar / 7z) or a direct link.", quote=True)
        return
    await AddUser(bot, m)
    uid = m.from_user.id

    if is_split_volume(fname):
        key = (uid, split_base(fname))
        s = SPLIT_SETS.get(key)
        if s is None:
            s = SplitSet(uid, key[1], os.path.join(Config.DOWNLOAD_LOCATION, str(uid), "split_" + new_id()))
            SPLIT_SETS[key] = s
        s.pending_tasks += 1
        status = await m.reply("📥 <b>Part received…</b>", quote=True)
        task = Task(task_id=new_id(), user_id=uid, chat_id=m.chat.id, anchor=m, status=status,
                    name=fname, size=doc.file_size, mode="part", source="tgfile",
                    work_dir=s.dir, keep_dir=True)
        task.split_set = s
        manager.submit(task, pipeline.run)
        return

    token = new_id()
    status = await m.reply(
        f"📦 <b>{fb('ARCHIVE DETECTED')}</b>  ·  <code>#{token}</code>\n"
        + quote(f"📄 <code>{esc(short(fname, 70))}</code>\n📦 {sc('size')}: <b>{humanbytes(doc.file_size)}</b>")
        + "\nChoose what to do 👇",
        quote=True,
        reply_markup=kb([B("🎬 Unzip → Video", f"go:{token}:zv", GREEN),
                         B("📄 Unzip → Document", f"go:{token}:zd", GREEN)],
                        [B("🚫 Cancel", f"cq:{token}", RED)]))
    PENDING[token] = Pending(token=token, kind="tgfile", user_id=uid, chat_id=m.chat.id, anchor=m,
                             status=status, name=fname, size=doc.file_size)

