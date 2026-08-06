import argparse
import datetime as dt
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlparse

import requests
from PIL import Image

try:
    import fcntl
except ImportError:
    fcntl = None


ROOT = Path(__file__).resolve().parent
MOSCOW = dt.timezone(dt.timedelta(hours=3))
ALLOWED_TAGS = {
    "a", "b", "blockquote", "code", "del", "em", "i", "ins", "pre",
    "s", "span", "strike", "strong", "tg-emoji", "tg-spoiler", "u",
}
EMOJI_RE = re.compile(r"[\u2600-\u27bf\U0001f000-\U0001faff]")
MONEY_RE = re.compile(r"(?:\$|₽|\bруб(?:\.|ля|лей)?\b)", re.I)
HASHTAG_RE = re.compile(r"(?:^|\s)#[\wа-яё]+", re.I)


class CaptionParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.text = []
        self.links = []
        self.blockquotes = []
        self.current_quote = None

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED_TAGS:
            raise ValueError(f"запрещённый HTML-тег: {tag}")
        if tag == "a":
            href = dict(attrs).get("href", "")
            if not href.startswith("https://"):
                raise ValueError("ссылка в подписи должна начинаться с https://")
            self.links.append(href)
        self.stack.append(tag)
        if tag == "blockquote":
            if self.current_quote is not None:
                raise ValueError("вложенные blockquote запрещены")
            self.current_quote = []

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            raise ValueError(f"несбалансированный HTML-тег: {tag}")
        self.stack.pop()
        if tag == "blockquote":
            self.blockquotes.append("".join(self.current_quote or []))
            self.current_quote = None

    def handle_data(self, data):
        self.text.append(data)
        if self.current_quote is not None:
            self.current_quote.append(data)

    def finish(self):
        self.close()
        if self.stack:
            raise ValueError(f"незакрытый HTML-тег: {self.stack[-1]}")
        return "".join(self.text)


def moscow_now():
    return dt.datetime.now(MOSCOW)


def telegram_units(value):
    return len(value.encode("utf-16-le")) // 2


def load_json(path):
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temp.replace(target)


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


def available_memory_mb():
    path = Path("/proc/meminfo")
    if not path.exists():
        return None
    values = {}
    for line in path.read_text().splitlines():
        key, value = line.split(":", 1)
        values[key] = int(value.strip().split()[0])
    return values.get("MemAvailable", 0) // 1024


def check_resources():
    memory = available_memory_mb()
    if memory is not None and memory < int(os.getenv("CUCUMBER_MIN_MEMORY_MB", "1200")):
        raise RuntimeError(f"мало свободной памяти: {memory} МБ")
    if hasattr(os, "getloadavg"):
        load = os.getloadavg()[0]
        cpus = max(os.cpu_count() or 1, 1)
        if load / cpus > float(os.getenv("CUCUMBER_MAX_LOAD_PER_CPU", "1.5")):
            raise RuntimeError(f"высокая нагрузка: load1={load:.2f}, CPU={cpus}")


def run_checked(command, cwd=ROOT, timeout=120, env=None):
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(f"команда завершилась с кодом {result.returncode}: {result.stdout[-1200:]}")
    return result.stdout


def ensure_repository():
    if run_checked(["git", "branch", "--show-current"]).strip() != "main":
        raise RuntimeError("рутина должна работать в ветке main")
    dirty = run_checked(["git", "status", "--porcelain", "--untracked-files=no"]).strip()
    if dirty:
        raise RuntimeError("в репозитории есть незакоммиченные изменения")
    run_checked(["git", "pull", "--ff-only", "origin", "main"], timeout=180)


def fetch_json(url, params=None, timeout=25):
    try:
        response = requests.get(
            url,
            params=params,
            timeout=timeout,
            headers={"User-Agent": "SteamGateContentRoutine/1.0"},
        )
        response.raise_for_status()
        return {"ok": True, "data": response.json()}
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {str(error)[:240]}"}


def collect_runtime(env):
    now = moscow_now()
    key = env.get("ITAD_API_KEY") or os.getenv("ITAD_API_KEY", "")
    runtime = {
        "today": now.date().isoformat(),
        "moscow_time": now.strftime("%H:%M"),
        "generated_at": now.isoformat(),
        "new_games": fetch_json("https://steamgate.online/api/integrations/new-games", {"days": 2}),
        "gamerpower": fetch_json(
            "https://www.gamerpower.com/api/giveaways",
            {"platform": "steam", "type": "game", "sort-by": "value"},
        ),
    }
    if key:
        base = "https://api.isthereanydeal.com/deals/v2"
        common = {"key": key, "country": "US", "limit": 120, "shops": 61}
        runtime["itad_trending"] = fetch_json(base, {**common, "sort": "-trending"})
        runtime["itad_cut"] = fetch_json(base, {**common, "sort": "-cut"})
    else:
        missing = {"ok": False, "error": "ITAD_API_KEY не настроен"}
        runtime["itad_trending"] = missing
        runtime["itad_cut"] = missing
    return runtime


def codex_command(prompt, schema, output, effort, image=None, search=False):
    binary = os.getenv("CUCUMBER_CODEX_BIN", "/usr/bin/codex")
    model = os.getenv("CUCUMBER_CODEX_MODEL", "gpt-5.6-sol")
    command = [binary]
    if search:
        command.append("--search")
    command.extend([
        "exec",
        "--ignore-user-config",
        "--model", model,
        "-c", f'model_reasoning_effort="{effort}"',
        "--sandbox", "read-only",
        "--ephemeral",
        "--output-schema", str(schema),
        "-o", str(output),
        "-C", str(ROOT),
    ])
    if image:
        command.append(f"--image={image}")
    command.append(prompt)
    user = os.getenv("CUCUMBER_CODEX_USER", "")
    if not user:
        return command, None
    home = os.getenv("CUCUMBER_CODEX_HOME", f"/var/lib/{user}")
    clean_env = [
        "env", "-i",
        f"HOME={home}",
        f"CODEX_HOME={home}/.codex",
        "PATH=/usr/local/bin:/usr/bin:/bin",
        "LANG=C.UTF-8",
    ]
    return ["runuser", "-u", user, "--", *clean_env, "nice", "-n", "10", "ionice", "-c2", "-n7", *command], os.environ.copy()


def run_model(output):
    prompt = (
        "Выполни один запуск подготовки контента. Полностью прочитай AGENT.md, затем обязательные "
        "runtime_input.json, posted.json и последние строки журналов. Используй веб-поиск для свежих "
        "новостей и событий. Верни только JSON по переданной схеме."
    )
    command, env = codex_command(prompt, ROOT / "draft.schema.json", output, "high", search=True)
    run_checked(command, timeout=int(os.getenv("CUCUMBER_MODEL_TIMEOUT", "2100")), env=env)


def validate_shape(draft):
    required = {
        "status", "date", "moscow_time", "tier", "topic", "caption_html", "banner",
        "dedup_entries", "decision_log", "caption_log", "sources", "approval", "blog_eligible",
    }
    if set(draft) != required:
        raise ValueError(f"неверный набор верхних полей: {sorted(set(draft) ^ required)}")
    if draft["status"] not in {"post", "skip"}:
        raise ValueError("неверный status")
    if draft["tier"] not in {"freebie", "catalog", "sale", "event", "news", "meme", "skip"}:
        raise ValueError("неверный tier")
    if not isinstance(draft["approval"], dict) or set(draft["approval"]) != {"send", "reason", "threads"}:
        raise ValueError("неверный approval")
    if not all(isinstance(draft["approval"][key], bool) for key in ("send", "threads")):
        raise ValueError("флаги approval должны быть логическими")
    if not isinstance(draft["approval"]["reason"], str):
        raise ValueError("approval.reason должен быть строкой")
    if draft["approval"]["send"] and not draft["approval"]["reason"].strip():
        raise ValueError("для апрува нужна причина")
    if not isinstance(draft["blog_eligible"], bool):
        raise ValueError("blog_eligible должен быть логическим")
    if not isinstance(draft["dedup_entries"], list) or not isinstance(draft["sources"], list):
        raise ValueError("dedup_entries и sources должны быть списками")
    if not isinstance(draft["decision_log"], str) or not draft["decision_log"].strip():
        raise ValueError("decision_log пуст")
    if "\n" in draft["decision_log"] or "\r" in draft["decision_log"]:
        raise ValueError("decision_log должен быть одной строкой")
    if draft["date"] != moscow_now().date().isoformat():
        raise ValueError("дата черновика не совпадает с датой Москвы")
    if not re.fullmatch(r"\d{2}:\d{2}", draft["moscow_time"]):
        raise ValueError("неверное московское время")
    for source in draft["sources"]:
        if set(source) != {"url", "fact"} or not source["url"].startswith("https://") or not source["fact"].strip():
            raise ValueError("неверный источник")
    for entry in draft["dedup_entries"]:
        if not isinstance(entry, dict) or set(entry) != {"name", "date", "free_until", "sale_until"}:
            raise ValueError("неверная запись дедупа")
        if entry["date"] != draft["date"] or not entry["name"].strip():
            raise ValueError("неверная дата или имя в дедупе")


def validate_caption(draft):
    caption = draft["caption_html"]
    parser = CaptionParser()
    parser.feed(caption)
    visible = parser.finish()
    if telegram_units(visible) > 1024:
        raise ValueError(f"подпись длиннее 1024 единиц Telegram: {telegram_units(visible)}")
    if not parser.links:
        raise ValueError("в посте нет ссылки")
    if not any("🔥" in quote and "💩" in quote for quote in parser.blockquotes):
        raise ValueError("нет единого блока реакций 🔥/💩")
    lines = [line.strip() for line in visible.splitlines() if line.strip()]
    if not lines or not HASHTAG_RE.search(lines[-1]) or not lines[-1].startswith("#"):
        raise ValueError("хэштеги должны быть последней строкой")
    hashtag_count = len(HASHTAG_RE.findall(lines[-1]))
    if not 5 <= hashtag_count <= 7:
        raise ValueError("в последней строке должно быть от 5 до 7 хэштегов")
    if draft["tier"] in {"freebie", "sale"} and MONEY_RE.search(visible):
        raise ValueError("в подписи халявы или скидок найдена цена")
    if draft["tier"] in {"freebie", "sale"}:
        if len(parser.blockquotes) != 2:
            raise ValueError("в дайджесте должно быть два blockquote")
        markers = re.findall(r"(?m)^[^\S\r\n]*([🟢🔴🚫🎁🔹🔷🔵🟦◆🔘])", parser.blockquotes[0])
        if not markers or any(marker not in {"🟢", "🔴", "🚫", "🎁"} for marker in markers):
            raise ValueError("неверные маркеры дайджеста")
    elif len(parser.blockquotes) != 1:
        raise ValueError("в обычном посте должен быть один blockquote")


def validate_banner(banner):
    if not isinstance(banner, dict):
        raise ValueError("баннер отсутствует")
    allowed = {"rubric", "title", "subtitle", "brand", "items"}
    if set(banner) != allowed:
        raise ValueError("неверные поля баннера")
    if banner["rubric"] not in {"freebie", "catalog", "sale", "news", "meme"}:
        raise ValueError("неверная рубрика баннера")
    if EMOJI_RE.search(banner["title"] + (banner["subtitle"] or "")):
        raise ValueError("эмодзи в тексте баннера запрещены")
    items = banner["items"]
    if not isinstance(items, list) or not 1 <= len(items) <= 8:
        raise ValueError("баннер должен содержать от 1 до 8 карточек")
    for item in items:
        if set(item) != {"img", "tag", "old", "new"}:
            raise ValueError("неверная карточка баннера")
        parsed = urlparse(item["img"])
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("изображение баннера должно иметь прямой https URL")


def validate_history(draft, posted, caption_lines):
    if draft["status"] == "skip":
        return
    today = dt.date.fromisoformat(draft["date"])
    short_date = today.strftime("%m-%d")
    post_count = sum(
        line.startswith(draft["date"] + " ") or line.startswith(short_date + " ")
        for line in caption_lines
    )
    if post_count >= 5:
        raise ValueError("достигнут жёсткий лимит пяти постов за московские сутки")
    by_name = {}
    for old in posted:
        if isinstance(old, dict) and old.get("name"):
            by_name.setdefault(old["name"].casefold(), []).append(old)
    for entry in draft["dedup_entries"]:
        name = entry["name"].casefold()
        for old in by_name.get(name, []):
            old_date = parse_date(old.get("date", ""))
            active_free = parse_date(old.get("free_until", ""))
            active_sale = parse_date(old.get("sale_until", ""))
            if active_free and active_free >= today:
                raise ValueError(f"активная халява уже была в дедупе: {entry['name']}")
            if active_sale and active_sale >= today:
                raise ValueError(f"активная скидка уже была в дедупе: {entry['name']}")
            window = 30 if draft["tier"] == "sale" else 7
            if old_date and old_date >= today - dt.timedelta(days=window):
                raise ValueError(f"тема уже была в дедупе: {entry['name']}")


def validate_draft(draft):
    validate_shape(draft)
    if draft["status"] == "skip":
        if draft["tier"] != "skip" or draft["caption_html"] or draft["banner"] is not None or draft["dedup_entries"]:
            raise ValueError("неверная структура СКИПа")
        if draft["caption_log"] or draft["approval"]["send"] or draft["blog_eligible"]:
            raise ValueError("СКИП не должен запускать публикацию")
        return
    if draft["tier"] == "skip" or not draft["topic"].strip() or not draft["dedup_entries"] or not draft["sources"]:
        raise ValueError("посту не хватает темы, дедупа или источников")
    if not draft["caption_log"].strip():
        raise ValueError("у поста пустой caption_log")
    validate_caption(draft)
    validate_banner(draft["banner"])
    expected_rubric = {
        "freebie": "freebie",
        "catalog": "catalog",
        "sale": "sale",
        "event": "news",
        "news": "news",
        "meme": "meme",
    }[draft["tier"]]
    if draft["banner"]["rubric"] != expected_rubric:
        raise ValueError("рубрика баннера не соответствует тиру")
    if draft["tier"] == "freebie":
        if any(not entry["free_until"] for entry in draft["dedup_entries"]):
            raise ValueError("у халявы нет free_until")
        if any(parse_date(entry["free_until"]) is None or parse_date(entry["free_until"]) < dt.date.fromisoformat(draft["date"])
               for entry in draft["dedup_entries"]):
            raise ValueError("у халявы неверный free_until")
    if draft["tier"] == "sale":
        if any(not entry["sale_until"] for entry in draft["dedup_entries"] if not entry["name"].startswith("🔥 скидки ")):
            raise ValueError("у скидки нет sale_until")
        if any(parse_date(entry["sale_until"]) is None or parse_date(entry["sale_until"]) < dt.date.fromisoformat(draft["date"])
               for entry in draft["dedup_entries"] if not entry["name"].startswith("🔥 скидки ")):
            raise ValueError("у скидки неверный sale_until")
    if draft["tier"] == "catalog":
        lock = f"🆕 завоз {draft['date']}"
        if not any(entry["name"] == lock for entry in draft["dedup_entries"]):
            raise ValueError("у завоза нет дневного замка")


def render_banner(draft, state_dir):
    config = state_dir / "banner-config.json"
    output = state_dir / "banner.jpg"
    write_json(config, draft["banner"])
    run_checked([sys.executable, str(ROOT / "make_banner.py"), str(config), str(output)], timeout=180)
    with Image.open(output) as image:
        image.verify()
    with Image.open(output) as image:
        if image.format != "JPEG" or image.width != 1080 or image.height < 350:
            raise ValueError(f"неверный баннер: {image.format} {image.size}")
    if output.stat().st_size > 9_500_000:
        raise ValueError("баннер тяжелее 9,5 МБ")
    return output


def run_vision(draft, banner, output):
    prompt = (
        f"Проверь баннер перед публикацией. Тема: {draft['topic']}. "
        "Убедись, что обложки и заголовок относятся к теме, текст полностью читается, "
        "нет обрезания, наложений, квадратов вместо символов и явно неверных изображений. "
        "Верни только JSON по схеме."
    )
    command, env = codex_command(prompt, ROOT / "vision.schema.json", output, "low", image=banner)
    run_checked(command, timeout=int(os.getenv("CUCUMBER_VISION_TIMEOUT", "480")), env=env)
    result = load_json(output)
    if set(result) != {"ok", "topic_match", "readable", "issues"}:
        raise ValueError("неверный ответ проверки баннера")
    if not result["ok"] or not result["topic_match"] or not result["readable"] or result["issues"]:
        raise ValueError("баннер не прошёл визуальную проверку: " + "; ".join(result.get("issues", [])))


def parse_date(value):
    try:
        return dt.date.fromisoformat(value)
    except Exception:
        return None


def merge_posted(existing, entries, today):
    cutoff = today - dt.timedelta(days=30)
    names = {entry["name"].casefold() for entry in entries}
    kept = []
    for entry in existing:
        if not isinstance(entry, dict) or not entry.get("name") or entry["name"].casefold() in names:
            continue
        date = parse_date(entry.get("date", ""))
        free_until = parse_date(entry.get("free_until", ""))
        sale_until = parse_date(entry.get("sale_until", ""))
        if date and date >= cutoff or free_until and free_until >= today or sale_until and sale_until >= today:
            kept.append(entry)
    return kept + entries


def append_trimmed(path, line, limit):
    source = Path(path)
    lines = source.read_text(encoding="utf-8").splitlines() if source.exists() else []
    lines.append(line.strip())
    source.write_text("\n".join(lines[-limit:]) + "\n", encoding="utf-8", newline="\n")


def persist_and_push(draft):
    today = dt.date.fromisoformat(draft["date"])
    posted_doc = load_json(ROOT / "posted.json")
    current = posted_doc.get("posted")
    if not isinstance(current, list):
        raise ValueError("posted.json имеет неверный формат")
    if draft["status"] == "post":
        entries = [{key: value for key, value in entry.items() if value is not None} for entry in draft["dedup_entries"]]
        posted_doc["posted"] = merge_posted(current, entries, today)
        write_json(ROOT / "posted.json", posted_doc)
    decision = f"{draft['date']} {draft['moscow_time']} | v96 | {draft['decision_log']}"
    append_trimmed(ROOT / "decisions.log", decision, 40)
    if draft["status"] == "post":
        append_trimmed(ROOT / "captions.log", draft["caption_log"], 15)
    files = ["decisions.log"] if draft["status"] == "skip" else ["posted.json", "decisions.log", "captions.log"]
    run_checked(["git", "diff", "--check", "--", *files])
    run_checked(["git", "add", "--", *files])
    topic = re.sub(r"\s+", " ", draft["topic"]).strip()[:62]
    message = f"Контент: {topic}" if draft["status"] == "post" else f"Контент: пропустить {draft['date']} {draft['moscow_time']}"
    run_checked(["git", "commit", "-m", message])
    run_checked(["git", "push", "origin", "main"], timeout=180)


def telegram_call(token, method, data=None, files=None, timeout=45):
    response = requests.post(
        f"https://api.telegram.org/bot{token}/{method}",
        data=data,
        files=files,
        timeout=timeout,
    )
    try:
        body = response.json()
    except Exception as error:
        raise RuntimeError(f"Telegram вернул не JSON: HTTP {response.status_code}") from error
    if not response.ok or not body.get("ok"):
        raise RuntimeError(f"Telegram {method}: {str(body.get('description', body))[:300]}")
    return body["result"]


def send_photo(token, chat_id, image, caption, markup=None, photo_id=None):
    data = {"chat_id": str(chat_id), "caption": caption, "parse_mode": "HTML"}
    if markup:
        data["reply_markup"] = json.dumps(markup, ensure_ascii=False)
    if photo_id:
        data["photo"] = photo_id
        return telegram_call(token, "sendPhoto", data=data)
    with Path(image).open("rb") as handle:
        return telegram_call(token, "sendPhoto", data=data, files={"photo": ("banner.jpg", handle, "image/jpeg")})


def approval_markup(threads):
    rows = [
        [
            {"text": "✅ В мейн", "callback_data": "ok"},
            {"text": "📱 В VK", "callback_data": "vkpub"},
        ],
        [
            {"text": "📘 FB +2ч", "callback_data": "fbpub"},
            {"text": "⚡ FB сейчас", "callback_data": "fbnow"},
        ],
    ]
    if threads:
        rows.append([{"text": "🧵 В Threads", "callback_data": "thpub"}])
    rows.append([
        {"text": "✏️ Редактировать", "callback_data": "edit"},
        {"text": "❌ Отклонить", "callback_data": "no"},
    ])
    return {"inline_keyboard": rows}


def save_recent(path, file_id, caption):
    target = Path(path)
    try:
        recent = load_json(target)
    except Exception:
        recent = []
    if not isinstance(recent, list):
        recent = []
    recent.append({"file_id": file_id, "caption": caption, "buttons": [], "ts": int(time.time())})
    write_json(target, recent[-30:])
    if os.name != "nt":
        target.chmod(0o640)


def publish(draft, banner, env):
    token = env.get("CUCUMBER_BOT_TOKEN") or os.getenv("CUCUMBER_BOT_TOKEN")
    owner = env.get("CUCUMBER_OWNER_ID") or os.getenv("CUCUMBER_OWNER_ID")
    test_chat = env.get("CUCUMBER_TEST_CHAT") or os.getenv("CUCUMBER_TEST_CHAT", "@sdsfasdfdsfas")
    if not token or not owner:
        raise RuntimeError("не настроены CUCUMBER_BOT_TOKEN или CUCUMBER_OWNER_ID")
    test_message = send_photo(token, test_chat, banner, draft["caption_html"])
    message_id = test_message["message_id"]
    try:
        telegram_call(token, "setMessageReaction", data={
            "chat_id": str(test_chat),
            "message_id": str(message_id),
            "reaction": json.dumps([{"type": "emoji", "emoji": "🔥"}], ensure_ascii=False),
        })
    except Exception:
        pass
    photo_id = test_message["photo"][-1]["file_id"]
    save_recent(
        env.get("CUCUMBER_RECENT_FILE", "/var/lib/cucumber-approve/recent.json"),
        photo_id,
        draft["caption_html"],
    )
    if draft["approval"]["send"]:
        send_photo(
            token,
            owner,
            banner,
            draft["caption_html"],
            markup=approval_markup(draft["approval"]["threads"]),
            photo_id=photo_id,
        )
        reason = draft["approval"]["reason"].strip()
        if reason:
            telegram_call(token, "sendMessage", data={"chat_id": str(owner), "text": f"📋 {reason}"})
    return message_id


def lock_run(state_dir):
    state_dir.mkdir(parents=True, exist_ok=True)
    handle = (state_dir / "routine.lock").open("a+")
    if fcntl:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("предыдущий запуск ещё не завершён") from error
    return handle


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--draft", type=Path)
    parser.add_argument("--skip-vision", action="store_true")
    parser.add_argument("--state-dir", type=Path, default=Path(os.getenv("CUCUMBER_STATE_DIR", "/var/lib/cucumber-content")))
    parser.add_argument("--env-file", type=Path, default=Path(os.getenv("CUCUMBER_ENV_FILE", "/root/cucumber-approve.env")))
    return parser.parse_args()


def main():
    args = parse_args()
    lock = lock_run(args.state_dir)
    try:
        check_resources()
        ensure_repository()
        env = load_env_file(args.env_file)
        runtime = collect_runtime(env)
        write_json(ROOT / "runtime_input.json", runtime)
        draft_path = args.state_dir / "draft.json"
        if args.draft:
            draft = load_json(args.draft)
            write_json(draft_path, draft)
        else:
            run_model(draft_path)
            draft = load_json(draft_path)
        validate_draft(draft)
        posted = load_json(ROOT / "posted.json").get("posted", [])
        captions = (ROOT / "captions.log").read_text(encoding="utf-8").splitlines()
        validate_history(draft, posted, captions)
        banner = None
        if draft["status"] == "post":
            banner = render_banner(draft, args.state_dir)
            if not args.skip_vision:
                run_vision(draft, banner, args.state_dir / "vision.json")
        if args.dry_run:
            print(json.dumps({
                "status": draft["status"],
                "topic": draft["topic"],
                "draft": str(draft_path),
                "banner": str(banner) if banner else None,
            }, ensure_ascii=False))
            return
        persist_and_push(draft)
        if draft["status"] == "post":
            message_id = publish(draft, banner, env)
            print(f"PUBLISHED_TEST message_id={message_id}")
        else:
            print("SKIPPED")
    finally:
        lock.close()


if __name__ == "__main__":
    main()
