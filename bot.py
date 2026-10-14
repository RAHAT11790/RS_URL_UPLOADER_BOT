#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# RS URL UPLOADER BOT — entry point
import asyncio
import logging
import os
import shutil
import sys

from config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logger = logging.getLogger("rs-bot")


def _prepare_dirs():
    # remove leftovers of a previous crash, then create fresh folders
    if os.path.isdir(Config.DOWNLOAD_LOCATION):
        shutil.rmtree(Config.DOWNLOAD_LOCATION, ignore_errors=True)
    os.makedirs(Config.THUMB_DIR, exist_ok=True)


async def amain():
    from pyrogram import Client, idle
    from core.reporter import spawn
    from core.state import janitor

    kwargs = dict(
        name=Config.SESSION_NAME,
        bot_token=Config.BOT_TOKEN,
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        plugins=dict(root="plugins"),
    )
    try:
        app = Client(max_concurrent_transmissions=8, **kwargs)
    except TypeError:  # very old forks without this argument
        app = Client(**kwargs)

    await app.start()
    spawn(janitor())
    me = await app.get_me()
    logger.info("Bot started as @%s", me.username)
    await idle()
    await app.stop()


def main():
    miss = Config.missing()
    if miss:
        logger.error("Missing environment variables: %s", ", ".join(miss))
        sys.exit(1)
    _prepare_dirs()
    asyncio.run(amain())


if __name__ == "__main__":
    main()
