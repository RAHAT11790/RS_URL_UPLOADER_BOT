# -*- coding: utf-8 -*-
"""Shared in-memory state (pending format choices, password waiters, split sets)."""
import asyncio
import logging
import os
import shutil
import time

from config import Config
from helper_funcs.utils import new_id

logger = logging.getLogger(__name__)

PASSWORD_WAITERS = {}   # (chat_id, status_msg_id) -> Future[str]
PENDING = {}            # token -> Pending (waiting for the user to choose a format)
SPLIT_SETS = {}         # (user_id, base) -> SplitSet
SPLIT_IDS = {}          # short id -> SplitSet (used in callback data)


class Pending:
    def __init__(self, *, token, kind, user_id, chat_id, anchor, status, name, size,
                 url=None, auth=None, extra=None):
        self.token = token
        self.kind = kind            # url | tgfile | split
        self.user_id = user_id
        self.chat_id = chat_id
        self.anchor = anchor
        self.status = status
        self.name = name
        self.size = size
        self.url = url
        self.auth = auth
        self.extra = extra or {}
        self.created = time.time()


class SplitSet:
    """Volumes of one multi-part archive collected from Telegram uploads."""

    def __init__(self, user_id, base, work_dir):
        self.user_id = user_id
        self.base = base
        self.dir = work_dir
        self.id = new_id()
        self.files = []
        self.pending_tasks = 0
        self.ctrl = None            # the control card message
        self.anchor = None
        self.created = time.time()
        SPLIT_IDS[self.id] = self

    def drop(self):
        SPLIT_SETS.pop((self.user_id, self.base), None)
        SPLIT_IDS.pop(self.id, None)


async def janitor():
    """Expire stale choice cards and abandoned split sets (disk + memory)."""
    while True:
        await asyncio.sleep(60)
        now = time.time()
        for token, p in list(PENDING.items()):
            if now - p.created > Config.PENDING_TTL:
                PENDING.pop(token, None)
                try:
                    await p.status.edit("⌛ <b>Expired</b> – send the link again.")
                    await asyncio.sleep(0.5)
                except Exception:
                    pass
        for key, s in list(SPLIT_SETS.items()):
            if now - s.created > Config.PENDING_TTL * 2 and s.pending_tasks == 0:
                s.drop()
                await asyncio.to_thread(shutil.rmtree, s.dir, True)
