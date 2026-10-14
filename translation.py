# -*- coding: utf-8 -*-
from helper_funcs.ui import LINE, fb, quote, sc


class Translation(object):
    START_TEXT = (
        f"✨ <b>{fb('RS URL UPLOADER')}</b> ✨\n"
        + quote(
            "👋 Hello <b>{name}</b>!\n"
            f"{LINE}\n"
            "🌐 Send any <b>direct link</b> (HTTP/HTTPS)\n"
            "🔗 PixelDrain links work too – auto-converted\n"
            "📦 ZIP / RAR / 7z → <b>auto unzip</b> in correct order\n"
            "🖼 Custom thumbnail support\n"
            "⚡ Smart queue – big files alone, small files in parallel"
        )
        + f"\n📌 /help {sc('for more details')}"
    )

    HELP_USER = (
        f"📖 <b>{fb('HOW TO USE')}</b>\n"
        + quote(
            f"<b>1️⃣ {sc('send a link')}</b>\n"
            "<code>https://example.com/File.mp4</code>\n"
            "<code>https://example.com/File.mp4 | MyName.mp4</code>\n"
            "<code>https://site.com/f.zip | name.zip | user | pass</code>\n"
            "Several links (one per line) are queued one by one.\n\n"
            f"<b>2️⃣ {sc('choose format')}</b>\n"
            "🎬 Video · 📄 Document · 🎵 Audio\n"
            "📦 ZIP → Unzip &amp; send, files keep episode order\n\n"
            f"<b>3️⃣ {sc('queue rules')}</b>\n"
            "🐘 over 1 GB → runs alone\n"
            "🐇 under 1 GB → up to 4 at the same time\n\n"
            f"<b>4️⃣ {sc('commands')}</b>\n"
            "/queue – your running tasks · /cancelall – stop everything\n"
            "/viewthumbnail · /delthumbnail · send a photo = set thumbnail\n"
            "🔐 Protected archive? Reply to the status message with the password."
        )
        + "\n💬 Help: @RS_WONER"
    )

    SAVED_CUSTOM_THUMB_NAIL = "🖼 <b>Custom thumbnail saved!</b>"
    DEL_ETED_CUSTOM_THUMB_NAIL = "🗑 <b>Custom thumbnail removed.</b>"
    NO_THUMB = "🫥 No custom thumbnail saved."
