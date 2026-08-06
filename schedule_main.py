import asyncio
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys

PREMIUM = {
    "🟢": "5416081784641168838",
    "🔴": "6165805327301222042",
    "🚫": "6167851582865022367",
    "🎁": "5203996991054432397",
    "🎮": "5319247469165433798",
    "🔥": "5424972470023104089",
    "🆕": "5382357040008021292",
    "⏳": "5429455831764584284",
}


def load_env_file(path):
    values = {}
    source = Path(path)
    if not source.exists():
        return values
    for raw in source.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def premiumify_html(value):
    parts = re.split(r"(<[^>]+>)", value)
    depth = 0
    output = []
    for part in parts:
        lower = part.lower()
        if lower.startswith("</tg-emoji"):
            depth = max(0, depth - 1)
            output.append(part)
            continue
        if lower.startswith("<tg-emoji"):
            depth += 1
            output.append(part)
            continue
        if part.startswith("<") or depth:
            output.append(part)
            continue
        for symbol, emoji_id in PREMIUM.items():
            part = part.replace(symbol, f'<tg-emoji emoji-id="{emoji_id}">{symbol}</tg-emoji>')
        output.append(part)
    return "".join(output)


async def schedule(jobfile):
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    env = load_env_file(os.getenv("CUCUMBER_ENV_FILE", "/root/cucumber-approve.env"))
    api_id = env.get("TG_API_ID") or os.getenv("TG_API_ID")
    api_hash = env.get("TG_API_HASH") or os.getenv("TG_API_HASH")
    session_file = env.get("TG_SESSION_FILE") or os.getenv("TG_SESSION_FILE", "/root/.tg_session_string")
    if not api_id or not api_hash:
        raise RuntimeError("не настроены TG_API_ID или TG_API_HASH")
    job = json.loads(Path(jobfile).read_text(encoding="utf-8"))
    chat = job.get("chat") or "@SteamGateOnline"
    caption = premiumify_html(job.get("html") or "")
    image = job.get("image")
    timestamp = job.get("schedule_ts")
    when = dt.datetime.fromtimestamp(timestamp, dt.timezone.utc) if timestamp else None
    session = Path(session_file).read_text(encoding="utf-8").strip()
    client = TelegramClient(StringSession(session), int(api_id), api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("Telegram-сессия не авторизована")
        if image:
            message = await client.send_file(chat, image, caption=caption, parse_mode="html", schedule=when)
        else:
            message = await client.send_message(chat, caption, parse_mode="html", schedule=when, link_preview=False)
        print("SCHEDULED_OK", message.id, when.isoformat() if when else "now")
    finally:
        await client.disconnect()


def main():
    try:
        asyncio.run(schedule(sys.argv[1]))
    except Exception as error:
        print("SEND_ERROR", type(error).__name__, str(error))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
