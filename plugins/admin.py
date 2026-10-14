# -*- coding: utf-8 -*-
import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.errors import FloodWait, InputUserDeactivated, PeerIdInvalid, UserIsBlocked

from config import Config
from database.access import clinton
from helper_funcs.ui import fb, quote

logger = logging.getLogger(__name__)


@Client.on_message(filters.private & filters.command("total"))
async def total_cmd(bot, m):
    if m.from_user.id != Config.OWNER_ID:
        return
    await m.reply(f"👥 Total users: <b>{await clinton.total_users_count()}</b>", quote=True)


@Client.on_message(filters.private & filters.command("broadcast") & filters.reply)
async def broadcast_cmd(bot, m):
    if m.from_user.id != Config.OWNER_ID:
        return
    if not clinton.enabled:
        await m.reply("⚠️ Database is not configured.", quote=True)
        return
    src = m.reply_to_message
    status = await m.reply("📣 <b>Broadcasting…</b>", quote=True)
    ok = gone = fail = i = 0
    async for u in clinton.all_users():
        uid = u["id"]
        i += 1
        for attempt in (1, 2):
            try:
                await src.copy(uid)
                ok += 1
                break
            except FloodWait as e:
                await asyncio.sleep(int(getattr(e, "value", 5)) + 1)
                continue
            except (InputUserDeactivated, UserIsBlocked, PeerIdInvalid):
                gone += 1
                await clinton.delete_user(uid)
                break
            except Exception:
                fail += 1
                break
        if i % 25 == 0:
            try:
                await status.edit(f"📣 <b>Broadcasting…</b> {i} users processed")
            except Exception:
                pass
        await asyncio.sleep(0.05)
    await status.edit(f"✅ <b>{fb('BROADCAST DONE')}</b>\n" + quote(
        f"👥 Total: {i}\n✅ Sent: {ok}\n🚫 Blocked/removed: {gone}\n❌ Failed: {fail}"))
