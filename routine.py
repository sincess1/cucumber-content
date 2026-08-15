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
CATALOG_LOOKBACK_DAYS = 7
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
        self.anchors = []
        self.blockquotes = []
        self.current_anchor = None
        self.current_quote = None

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED_TAGS:
            raise ValueError(f"запрещённый HTML-тег: {tag}")
        if tag == "a":
            href = dict(attrs).get("href", "")
            if not href.startswith("https://"):
                raise ValueError("ссылка в подписи должна начинаться с https://")
            self.links.append(href)
            self.current_anchor = {"href": href, "text": []}
        self.stack.append(tag)
        if tag == "blockquote":
            if self.current_quote is not None:
                raise ValueError("вложенные blockquote запрещены")
            self.current_quote = []

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            raise ValueError(f"несбалансированный HTML-тег: {tag}")
        self.stack.pop()
        if tag == "a":
            self.anchors.append((self.current_anchor["href"], "".join(self.current_anchor["text"]).strip()))
            self.current_anchor = None
        if tag == "blockquote":
            self.blockquotes.append("".join(self.current_quote or []))
            self.current_quote = None

    def handle_data(self, data):
        self.text.append(data)
        if self.current_anchor is not None:
            self.current_anchor["text"].append(data)
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
    epic = fetch_json(
        "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions",
        {"locale": "en-US", "country": "US", "allowCountries": "US"},
    )
    runtime = {
        "today": now.date().isoformat(),
        "moscow_time": now.strftime("%H:%M"),
        "generated_at": now.isoformat(),
        "new_games": fetch_json(
            "https://steamgate.online/api/integrations/new-games",
            {"days": CATALOG_LOOKBACK_DAYS},
        ),
        "gamerpower": fetch_json(
            "https://www.gamerpower.com/api/giveaways",
            {"platform": "steam", "type": "game", "sort-by": "value"},
        ),
        "epic_freebies": normalize_epic_freebies(epic, now),
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


def response_items(response):
    if not isinstance(response, dict) or not response.get("ok"):
        return []
    data = response.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("list", "games", "items", "data"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def parse_timestamp(value):
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(MOSCOW)
    except Exception:
        return None


def normalize_epic_freebies(response, now=None):
    if not isinstance(response, dict) or not response.get("ok"):
        return response
    data = response.get("data")
    catalog = data.get("data", {}).get("Catalog", {}) if isinstance(data, dict) else {}
    elements = catalog.get("searchStore", {}).get("elements", [])
    if not isinstance(elements, list):
        return {"ok": False, "error": "Epic вернул данные неизвестного формата"}
    current = now or moscow_now()
    freebies = []
    for item in elements:
        if not isinstance(item, dict):
            continue
        total = item.get("price", {}).get("totalPrice", {})
        if not isinstance(total, dict) or float(total.get("originalPrice") or 0) <= 0:
            continue
        active = None
        promotions = item.get("promotions") if isinstance(item.get("promotions"), dict) else {}
        for group in promotions.get("promotionalOffers", []) or []:
            for offer in group.get("promotionalOffers", []) if isinstance(group, dict) else []:
                start = parse_timestamp(offer.get("startDate"))
                end = parse_timestamp(offer.get("endDate"))
                setting = offer.get("discountSetting") if isinstance(offer.get("discountSetting"), dict) else {}
                if start and end and start <= current <= end and setting.get("discountPercentage") == 0:
                    active = (start, end)
                    break
            if active:
                break
        title = str(item.get("title") or "").strip()
        if not title or not active:
            continue
        mappings = item.get("catalogNs", {}).get("mappings", [])
        if not mappings:
            mappings = item.get("offerMappings", [])
        slug = next(
            (str(mapping.get("pageSlug")) for mapping in mappings if isinstance(mapping, dict) and mapping.get("pageSlug")),
            "",
        )
        images = {
            str(image.get("type")): str(image.get("url"))
            for image in item.get("keyImages", [])
            if isinstance(image, dict) and image.get("type") and image.get("url")
        }
        freebies.append({
            "title": title,
            "platform": "Epic Games Store",
            "start_date": active[0].isoformat(),
            "end_date": active[1].isoformat(),
            "url": f"https://store.epicgames.com/p/{slug}" if slug else "https://store.epicgames.com/free-games",
            "image": images.get("OfferImageWide") or images.get("DieselStoreFrontWide") or next(iter(images.values()), None),
            "original_price": total.get("fmtPrice", {}).get("originalPrice"),
        })
    return {"ok": True, "data": freebies}


def pending_catalog_titles(runtime, posted):
    today = parse_date(runtime.get("today", ""))
    if today is None:
        return []
    cutoff = today - dt.timedelta(days=CATALOG_LOOKBACK_DAYS - 1)
    posted_names = {
        old["name"].casefold()
        for old in posted
        if isinstance(old, dict) and isinstance(old.get("name"), str)
    }
    titles = []
    seen = set()
    for item in response_items(runtime.get("new_games")):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("name") or "").strip()
        created = parse_timestamp(item.get("createdAt") or item.get("created_at"))
        key = f"🆕 {title}".casefold()
        if not title or created is None or not cutoff <= created.date() <= today:
            continue
        if key in posted_names or key in seen:
            continue
        seen.add(key)
        titles.append(title)
    return titles


def normalize_giveaway_title(value):
    title = re.sub(r"\s*\(Steam\)\s*Giveaway$", "", str(value), flags=re.I)
    title = re.sub(r"\s+Steam\s+Giveaway$", "", title, flags=re.I)
    return title.strip()


def pending_freebies(runtime, posted):
    today = parse_date(runtime.get("today", ""))
    if today is None:
        return []
    active = {
        old["name"].casefold()
        for old in posted
        if isinstance(old, dict)
        and isinstance(old.get("name"), str)
        and (parse_date(old.get("free_until", "")) or dt.date.min) >= today
    }
    candidates = {}

    def add(title, until):
        name = normalize_giveaway_title(title)
        expiry = parse_date(until) if isinstance(until, str) else until
        if name and expiry and expiry >= today and name.casefold() not in active:
            candidates.setdefault(name.casefold(), {"name": name, "free_until": expiry.isoformat()})

    for item in response_items(runtime.get("itad_cut")):
        if not isinstance(item, dict) or str(item.get("type", "")).casefold() != "game":
            continue
        deal = item.get("deal") if isinstance(item.get("deal"), dict) else {}
        shop = deal.get("shop") if isinstance(deal.get("shop"), dict) else {}
        price = deal.get("price") if isinstance(deal.get("price"), dict) else {}
        regular = deal.get("regular") if isinstance(deal.get("regular"), dict) else {}
        expiry = parse_timestamp(deal.get("expiry"))
        if (
            str(shop.get("name", "")).casefold() == "steam"
            and deal.get("cut") == 100
            and price.get("amount") == 0
            and float(regular.get("amount") or 0) > 0
            and expiry is not None
        ):
            add(item.get("title", ""), expiry.date())

    for item in response_items(runtime.get("gamerpower")):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", ""))
        details = " ".join(str(item.get(key, "")) for key in ("title", "description", "instructions")).casefold()
        worth = re.search(r"\d+(?:\.\d+)?", str(item.get("worth", "")))
        if (
            str(item.get("status", "")).casefold() == "active"
            and str(item.get("type", "")).casefold() == "game"
            and "steam" in str(item.get("platforms", "")).casefold()
            and worth
            and float(worth.group()) > 0
            and "key giveaway" not in title.casefold()
            and not ("requires" in details and ("points" in details or " arp" in details))
        ):
            add(title, str(item.get("end_date", ""))[:10])
    for item in response_items(runtime.get("epic_freebies")):
        if isinstance(item, dict):
            add(item.get("title", ""), str(item.get("end_date", ""))[:10])
    return list(candidates.values())


def pending_sale_titles(runtime, posted):
    today = parse_date(runtime.get("today", ""))
    if today is None:
        return []
    daily_marker = f"🔥 скидки {today.isoformat()}".casefold()
    posted_names = {
        old["name"].casefold()
        for old in posted
        if isinstance(old, dict) and isinstance(old.get("name"), str)
    }
    if daily_marker in posted_names:
        return []
    cutoff = today - dt.timedelta(days=30)
    recent_sales = {
        old["name"].casefold()
        for old in posted
        if isinstance(old, dict)
        and isinstance(old.get("name"), str)
        and old.get("sale_until")
        and (parse_date(old.get("date", "")) or dt.date.min) >= cutoff
    }
    titles = []
    seen = set()
    for item in response_items(runtime.get("itad_trending")):
        if not isinstance(item, dict) or str(item.get("type", "")).casefold() != "game":
            continue
        deal = item.get("deal") if isinstance(item.get("deal"), dict) else {}
        shop = deal.get("shop") if isinstance(deal.get("shop"), dict) else {}
        expiry = parse_timestamp(deal.get("expiry"))
        title = str(item.get("title") or "").strip()
        key = title.casefold()
        try:
            cut = int(deal.get("cut") or 0)
        except (TypeError, ValueError):
            continue
        qualifies = 85 <= cut <= 95 or str(deal.get("flag") or "").upper() == "N"
        if (
            not title
            or key in seen
            or key in recent_sales
            or str(shop.get("name", "")).casefold() != "steam"
            or cut == 100
            or not qualifies
            or expiry is None
            or expiry.date() < today
        ):
            continue
        seen.add(key)
        titles.append(title)
    return titles


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


def run_model(output, feedback=None):
    prompt = (
        "Выполни один запуск подготовки контента. Полностью прочитай AGENT.md, затем обязательные "
        "runtime_input.json, posted.json и последние строки журналов. Используй веб-поиск для свежих "
        "новостей и событий. Верни только JSON по переданной схеме."
    )
    if feedback:
        prompt += (
            f" Предыдущий результат отклонён внешним валидатором: {feedback[:500]}. "
            "Подготовь результат заново по текущим данным, не повторяя эту ошибку."
        )
    candidate = output.with_suffix(output.suffix + ".next")
    candidate.unlink(missing_ok=True)
    command, env = codex_command(prompt, ROOT / "draft.schema.json", candidate, "high", search=True)
    run_checked(command, timeout=int(os.getenv("CUCUMBER_MODEL_TIMEOUT", "2100")), env=env)
    if not candidate.is_file():
        raise RuntimeError("модель не создала новый черновик")
    candidate.replace(output)


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
    reaction_lines = [line.strip() for line in parser.blockquotes[-1].splitlines() if line.strip()]
    if (
        len(reaction_lines) != 2
        or not re.fullmatch(r"🔥\s*—\s*.+", reaction_lines[0])
        or not re.fullmatch(r"💩\s*—\s*.+", reaction_lines[1])
    ):
        raise ValueError("реакции должны состоять из двух коротких строк 🔥/💩")
    if draft["tier"] in {"freebie", "catalog"}:
        negative = reaction_lines[1].casefold()
        natural_negative = (
            "не моё", "не мое", "не люблю", "уже ", "не играю", "не интерес",
            "не зайд", "не зацеп", "ничего не", "не для меня", "не буду",
        )
        if not any(phrase in negative for phrase in natural_negative):
            raise ValueError("отрицательная реакция должна выражать простую человеческую причину")
        positive = reaction_lines[0].casefold()
        natural_positive = (
            "имба", "хочу", "беру", "забира", "попроб", "зацен", "надо",
            "интерес", "нрав", "в спис", "уже игра",
        )
        if not any(phrase in positive for phrase in natural_positive):
            raise ValueError("положительная реакция должна быть короткой и прямой, без ролевого каламбура")
    lines = [line.strip() for line in visible.splitlines() if line.strip()]
    if not lines or not HASHTAG_RE.search(lines[-1]) or not lines[-1].startswith("#"):
        raise ValueError("хэштеги должны быть последней строкой")
    hashtag_count = len(HASHTAG_RE.findall(lines[-1]))
    if not 5 <= hashtag_count <= 7:
        raise ValueError("в последней строке должно быть от 5 до 7 хэштегов")
    if draft["tier"] in {"freebie", "sale"} and MONEY_RE.search(visible):
        raise ValueError("в подписи халявы или скидок найдена цена")
    if draft["tier"] == "freebie" and re.search(r"(?mi)^\s*🎁\s*[—–-]\s*", visible):
        raise ValueError("в посте о халяве не нужна расшифровка очевидного маркера 🎁")
    if draft["tier"] == "catalog":
        content = "\n".join(lines[:-1])
        if len(re.findall(r"\bзавоз\w*", content, re.I)) > 1:
            raise ValueError("слово «завоз» повторяется в подписи")
        raw_lines = caption.splitlines()
        if len(raw_lines) < 2 or raw_lines[1].strip():
            raise ValueError("заголовок пополнения нужно отделить пустой строкой")
        catalog_entries = [
            entry for entry in draft.get("dedup_entries", [])
            if isinstance(entry, dict)
            and str(entry.get("name", "")).startswith("🆕 ")
            and not str(entry.get("name", "")).startswith("🆕 завоз ")
        ]
        if len(catalog_entries) == 1:
            product_links = [
                (href, text) for href, text in parser.anchors
                if urlparse(href).netloc.casefold() == "steamgate.online"
                and "/products/" in urlparse(href).path
                and text.casefold() == "steamgate"
            ]
            if len(product_links) != 1:
                raise ValueError("ссылку на одиночную игру нужно встроить в слово SteamGate во втором абзаце")
            if any(text.casefold().startswith(("открыть", "смотреть")) for _, text in parser.anchors):
                raise ValueError("отдельная CTA-ссылка в одиночном пополнении дублирует текст")
            content_lines = []
            for line in raw_lines[2:]:
                stripped = line.strip()
                if stripped.startswith("<blockquote"):
                    break
                if stripped:
                    content_lines.append(stripped)
            if len(content_lines) != 2 or any(not EMOJI_RE.match(line) for line in content_lines):
                raise ValueError("у одиночного пополнения должно быть два абзаца с подходящими эмодзи")
            if product_links[0][0] not in content_lines[1]:
                raise ValueError("ссылку на одиночную игру нужно встроить в слово SteamGate во втором абзаце")
    if draft["tier"] in {"freebie", "sale"}:
        if len(parser.blockquotes) != 2:
            raise ValueError("в дайджесте должно быть два blockquote")
        markers = re.findall(r"(?m)^[^\S\r\n]*([🟢🔴🚫🎁🔹🔷🔵🟦◆🔘])", parser.blockquotes[0])
        if not markers or any(marker not in {"🟢", "🔴", "🚫", "🎁"} for marker in markers):
            raise ValueError("неверные маркеры дайджеста")
    elif draft["tier"] == "catalog":
        if len(parser.blockquotes) not in {1, 2}:
            raise ValueError("в пополнении допустим список и один блок реакций")
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
    if banner["rubric"] == "catalog" and re.search(r"\bзавоз\w*", banner["title"], re.I):
        raise ValueError("заголовок баннера не должен повторять системную рубрику «ЗАВОЗ»")
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
    if post_count >= 3 and draft["tier"] not in {"freebie", "catalog"}:
        raise ValueError("достигнут жёсткий лимит трёх постов за московские сутки")
    if draft["tier"] in {"event", "news"}:
        ordinary_today = any(
            (line.startswith(draft["date"] + " ") or line.startswith(short_date + " "))
            and "дайджест(" not in line
            and "| завоз |" not in line
            for line in caption_lines
        )
        if ordinary_today:
            raise ValueError("сегодня уже был одиночный новостной или событийный пост")
    by_name = {}
    for old in posted:
        if isinstance(old, dict) and old.get("name"):
            by_name.setdefault(old["name"].casefold(), []).append(old)
    for entry in draft["dedup_entries"]:
        name = entry["name"].casefold()
        if draft["tier"] == "catalog" and entry["name"] == f"🆕 завоз {draft['date']}":
            continue
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


def validate_priority(draft, runtime, posted):
    freebies = pending_freebies(runtime, posted)[:4]
    catalog = pending_catalog_titles(runtime, posted)
    tier = draft["tier"]
    names = {
        entry["name"].casefold()
        for entry in draft.get("dedup_entries", [])
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }
    if freebies:
        if tier != "freebie":
            raise ValueError("есть новая халява — тир 1 обязателен: " + ", ".join(item["name"] for item in freebies))
        missing = [item["name"] for item in freebies if item["name"].casefold() not in names]
        if missing:
            raise ValueError("в посте о халяве пропущены: " + ", ".join(missing))
        return
    if catalog and tier not in {"freebie", "catalog"}:
        raise ValueError("есть неопубликованные игры SteamGate — тир 2 обязателен: " + ", ".join(catalog))
    if tier == "catalog":
        missing = [title for title in catalog if f"🆕 {title}".casefold() not in names]
        if not catalog:
            raise ValueError("для поста о пополнении нет неопубликованных игр")
        if missing:
            raise ValueError("в посте о пополнении пропущены: " + ", ".join(missing))
    if tier == "sale":
        allowed = {title.casefold() for title in pending_sale_titles(runtime, posted)}
        sale_entries = [
            entry["name"] for entry in draft["dedup_entries"]
            if not entry["name"].startswith("🔥 скидки ")
        ]
        if len(sale_entries) < 3:
            raise ValueError("для скидочного поста нужно минимум три рекордные скидки или скидки 85–95%")
        rejected = [title for title in sale_entries if title.casefold() not in allowed]
        if rejected:
            raise ValueError("скидки не прошли жёсткий фильтр: " + ", ".join(rejected))


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
    if draft["tier"] in {"event", "news"}:
        if not draft["approval"]["send"] or not draft["approval"]["threads"]:
            raise ValueError("новость или событие должны быть редкой сливкой, иначе нужен СКИП")
        domains = {
            urlparse(source["url"]).netloc.casefold().removeprefix("www.")
            for source in draft["sources"]
        }
        if len(domains) < 2:
            raise ValueError("для шокирующей новости нужны два независимых источника")
    if draft["tier"] == "freebie":
        if any(not entry["free_until"] for entry in draft["dedup_entries"]):
            raise ValueError("у халявы нет free_until")
        if any(parse_date(entry["free_until"]) is None or parse_date(entry["free_until"]) < dt.date.fromisoformat(draft["date"])
               for entry in draft["dedup_entries"]):
            raise ValueError("у халявы неверный free_until")
    if draft["tier"] == "sale":
        marker = f"🔥 скидки {draft['date']}"
        if not any(entry["name"] == marker for entry in draft["dedup_entries"]):
            raise ValueError("у скидочного поста нет дневного замка")
        if any(not entry["sale_until"] for entry in draft["dedup_entries"] if not entry["name"].startswith("🔥 скидки ")):
            raise ValueError("у скидки нет sale_until")
        if any(parse_date(entry["sale_until"]) is None or parse_date(entry["sale_until"]) < dt.date.fromisoformat(draft["date"])
               for entry in draft["dedup_entries"] if not entry["name"].startswith("🔥 скидки ")):
            raise ValueError("у скидки неверный sale_until")
    if draft["tier"] == "catalog":
        lock = f"🆕 завоз {draft['date']}"
        if not any(entry["name"] == lock for entry in draft["dedup_entries"]):
            raise ValueError("у завоза нет дневного замка")


def prepare_model_draft(draft_path, runtime, posted, captions, attempts=2):
    feedback = None
    for attempt in range(attempts):
        run_model(draft_path, feedback)
        try:
            draft = load_json(draft_path)
            validate_draft(draft)
            validate_history(draft, posted, captions)
            validate_priority(draft, runtime, posted)
            return draft
        except (OSError, json.JSONDecodeError, TypeError, KeyError, ValueError) as error:
            if attempt + 1 == attempts:
                raise
            feedback = str(error)
    raise RuntimeError("не удалось подготовить черновик")


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
        "Карточки — выборка максимум из восьми главных игр: если в теме или подписи игр больше, "
        "баннер не обязан показывать каждую из них, и это само по себе не является ошибкой. "
        "Верни только JSON по схеме."
    )
    candidate = output.with_suffix(output.suffix + ".next")
    candidate.unlink(missing_ok=True)
    command, env = codex_command(prompt, ROOT / "vision.schema.json", candidate, "low", image=banner)
    run_checked(command, timeout=int(os.getenv("CUCUMBER_VISION_TIMEOUT", "480")), env=env)
    if not candidate.is_file():
        raise RuntimeError("визуальная модель не создала результат проверки")
    candidate.replace(output)
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
    decision = f"{draft['date']} {draft['moscow_time']} | v103 | {draft['decision_log']}"
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
        posted = load_json(ROOT / "posted.json").get("posted", [])
        captions = (ROOT / "captions.log").read_text(encoding="utf-8").splitlines()
        if args.draft:
            draft = load_json(args.draft)
            write_json(draft_path, draft)
            validate_draft(draft)
            validate_history(draft, posted, captions)
            validate_priority(draft, runtime, posted)
        else:
            draft = prepare_model_draft(draft_path, runtime, posted, captions)
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
