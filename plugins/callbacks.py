# -*- coding: utf-8 -*-
import asyncio
import logging
import os
import shutil

from pyrogram import Client, filters

from config import Config
from core import pipeline
from core.state import PENDING, SPLIT_IDS
from core.tasks import Task, manager
from helper_funcs.utils import new_id, pick_first_volume

logger = logging.getLogger(__name__)

MODES = {"v": "video", "d": "doc", "a": "audio", "zv": "unzip_video", "zd": "unzip_doc"}


async def _answer(q, text=None, alert=False):
    try:
        await q.answer(text, show_alert=alert)
    except Exception:
        pass


def _allowed(q, owner_id):
    return q.from_user and q.from_user.id in (owner_id, Config.OWNER_ID)


# ----------------------------------------------------------- cancel one task
@Client.on_callback_query(filters.regex(r"^cx:"))
async def cancel_task_cb(bot, q):
    task = manager.get(q.data.split(":", 1)[1])
    if task is None:
        await _answer(q, "This task is already finished.")
        return
    if not _allowed(q, task.user_id):
        await _answer(q, "This is not your task.", True)
        return
    if task.cancel():
        await _answer(q, "🚫 Cancelling…")
    else:
        await _answer(q, "Already stopping…")


@Client.on_callback_query(filters.regex(r"^cxa$"))
async def cancel_all_cb(bot, q):
    n = sum(1 for t in manager.user_tasks(q.from_user.id) if t.cancel())
    await _answer(q, f"🚫 Cancelled {n} task(s)")
    try:
        await q.message.edit("🚫 <b>All your tasks were cancelled.</b>")
    except Exception:
        pass


# ------------------------------------------------- cancel before it started
@Client.on_callback_query(filters.regex(r"^cq:"))
async def cancel_pending_cb(bot, q):
    p = PENDING.get(q.data.split(":", 1)[1])
    if p is None:
        await _answer(q, "Expired.")
        try:
            await q.message.delete()
        except Exception:
            pass
        return
    if not _allowed(q, p.user_id):
        await _answer(q, "This is not your request.", True)
        return
    PENDING.pop(p.token, None)
    await _answer(q, "Cancelled")
    try:
        await p.status.delete()
    except Exception:
        pass


# ------------------------------------------------------------ start a task
@Client.on_callback_query(filters.regex(r"^go:"))
async def go_cb(bot, q):
    _, token, code = q.data.split(":")
    p = PENDING.get(token)
    if p is None:
        await _answer(q, "This request expired – send the link again.", True)
        return
    if not _allowed(q, p.user_id):
        await _answer(q, "This is not your request.", True)
        return
    mode = MODES.get(code)
    if mode is None:
        await _answer(q, "Unknown option.", True)
        return
    PENDING.pop(token, None)          # a double-tap can never start it twice
    task = Task(task_id=new_id(), user_id=p.user_id, chat_id=p.chat_id, anchor=p.anchor,
                status=p.status, name=p.name, size=p.size, mode=mode,
                source="url" if p.kind == "url" else "tgfile", url=p.url, auth=p.auth)
    manager.submit(task, pipeline.run)
    await _answer(q, "✅ Added to queue")


# --------------------------------------------------------- split archives
@Client.on_callback_query(filters.regex(r"^sp:"))
async def split_cb(bot, q):
    _, sid, code = q.data.split(":")
    s = SPLIT_IDS.get(sid)
    if s is None:
        await _answer(q, "This archive session expired.", True)
        return
    if not _allowed(q, s.user_id):
        await _answer(q, "This is not your archive.", True)
        return
    if code == "x":
        s.drop()
        await asyncio.to_thread(shutil.rmtree, s.dir, True)
        await _answer(q, "Discarded")
        try:
            await q.message.delete()
        except Exception:
            pass
        return
    if s.pending_tasks > 0:
        await _answer(q, "⏳ Wait – other parts are still downloading.", True)
        return
    if not s.files:
        await _answer(q, "No parts found.", True)
        return
    first = pick_first_volume(s.files)
    size = sum(os.path.getsize(f) for f in s.files if os.path.exists(f))
    s.drop()                         # the task now owns the folder and deletes it at the end
    task = Task(task_id=new_id(), user_id=s.user_id, chat_id=q.message.chat.id,
                anchor=s.anchor or q.message, status=q.message, name=os.path.basename(first),
                size=size, mode="unzip_video" if code == "v" else "unzip_doc",
                source="local", local_path=first, work_dir=s.dir)
    manager.submit(task, pipeline.run)
    await _answer(q, "✅ Added to queue")
