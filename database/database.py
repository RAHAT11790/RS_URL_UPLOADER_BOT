# -*- coding: utf-8 -*-
"""MongoDB (motor). Completely optional: without DATABASE_URL the bot still
works (only saved thumbnails / broadcast need the database)."""
import logging

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, uri, database_name):
        self.col = None
        if not uri:
            logger.warning("DATABASE_URL not set – thumbnails/broadcast disabled")
            return
        try:
            import motor.motor_asyncio
            client = motor.motor_asyncio.AsyncIOMotorClient(uri, serverSelectionTimeoutMS=8000)
            self.col = client[database_name].USERS
        except Exception as e:
            logger.error("MongoDB init failed: %s", e)

    @property
    def enabled(self):
        return self.col is not None

    async def add_user(self, user_id):
        if not self.enabled:
            return
        try:
            await self.col.update_one(
                {"id": int(user_id)},
                {"$setOnInsert": {"id": int(user_id), "thumbnail": None}},
                upsert=True,
            )
        except Exception as e:
            logger.warning("add_user failed: %s", e)

    async def total_users_count(self):
        if not self.enabled:
            return 0
        try:
            return await self.col.count_documents({})
        except Exception:
            return 0

    def all_users(self):
        return self.col.find({}, {"id": 1}) if self.enabled else None

    async def delete_user(self, user_id):
        if self.enabled:
            try:
                await self.col.delete_many({"id": int(user_id)})
            except Exception:
                pass

    async def set_thumbnail(self, user_id, file_id):
        if not self.enabled:
            return False
        try:
            await self.col.update_one(
                {"id": int(user_id)},
                {"$set": {"thumbnail": file_id}, "$setOnInsert": {"id": int(user_id)}},
                upsert=True,
            )
            return True
        except Exception as e:
            logger.warning("set_thumbnail failed: %s", e)
            return False

    async def get_thumbnail(self, user_id):
        if not self.enabled:
            return None
        try:
            user = await self.col.find_one({"id": int(user_id)})
            return (user or {}).get("thumbnail")
        except Exception:
            return None
