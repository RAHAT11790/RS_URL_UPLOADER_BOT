---
title: RS URL Uploader Bot
emoji: 😈
colorFrom: red
colorTo: red
sdk: docker
pinned: false
---

# RS URL UPLOADER BOT

Direct-link / PixelDrain / ZIP uploader for Telegram.

## Environment variables (required – no secrets are stored in the code)
| Name | Meaning |
|------|---------|
| `BOT_TOKEN` | token from @BotFather |
| `API_ID`, `API_HASH` | from my.telegram.org |
| `OWNER_ID` | your Telegram id |
| `DATABASE_URL` | MongoDB URI (optional – only thumbnails/broadcast need it) |
| `PREMIUM_USER` | `true` if the uploading account is Premium (4 GB limit) |
| `MAX_PARALLEL_SMALL` | parallel files under 1 GB (default 4) |
| `BUTTON_STYLE` | `0` turns coloured buttons off if your library rejects `style` |

## Queue rules (per user)
* file **> 1 GB** (or unknown size) runs **alone**, the next link waits;
* files **≤ 1 GB** run together, up to **4** at the same time;
* strict first-in-first-out; every task has its own Cancel button.

## Commands
`/start` `/help` `/queue` `/cancelall` `/viewthumbnail` `/delthumbnail` — owner: `/total` `/broadcast`
