from database.access import clinton


async def AddUser(bot, update):
    if update.from_user:
        await clinton.add_user(update.from_user.id)
