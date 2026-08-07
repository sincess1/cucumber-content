import datetime as dt
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import routine
from schedule_main import premiumify_html


def draft(tier="news", caption=None):
    today = routine.moscow_now().date().isoformat()
    return {
        "status": "post",
        "date": today,
        "moscow_time": "12:30",
        "tier": tier,
        "topic": "Проверяемая игровая новость",
        "caption_html": caption or (
            '🎮 <b>Проверяемая игровая новость</b>\n\n'
            'Короткая суть.\n\n<a href="https://example.com/news">Подробнее</a>\n\n'
            '<blockquote>🔥 — читаю\n💩 — пропускаю</blockquote>\n\n#steam #игры #новости #pc #gaming'
        ),
        "banner": {
            "rubric": "news",
            "title": "ИГРОВАЯ НОВОСТЬ",
            "subtitle": None,
            "brand": "steamgate",
            "items": [{"img": "https://example.com/banner.jpg", "tag": None, "old": None, "new": None}],
        },
        "dedup_entries": [{
            "name": "Проверяемая игровая новость",
            "date": today,
            "free_until": None,
            "sale_until": None,
        }],
        "decision_log": "тиры 1–5 пусты | взял тир 6",
        "caption_log": f"{today} | А | Проверяемая игровая новость | байт: читаю",
        "sources": [{"url": "https://example.com/news", "fact": "Подтверждение новости"}],
        "approval": {"send": True, "reason": "Достойно основного канала", "threads": False},
        "blog_eligible": False,
    }


def runtime(new_games=None, freebies=None):
    today = routine.moscow_now().date()
    games = []
    for title, created in new_games or []:
        games.append({"title": title, "createdAt": created})
    deals = []
    for title in freebies or []:
        deals.append({
            "title": title,
            "type": "game",
            "deal": {
                "shop": {"name": "Steam"},
                "price": {"amount": 0},
                "regular": {"amount": 19.99},
                "cut": 100,
                "expiry": (today + dt.timedelta(days=2)).isoformat() + "T19:00:00+03:00",
            },
        })
    return {
        "today": today.isoformat(),
        "new_games": {"ok": True, "data": games},
        "gamerpower": {"ok": True, "data": []},
        "itad_cut": {"ok": True, "data": {"list": deals}},
    }


def catalog_draft(titles):
    value = draft()
    value["tier"] = "catalog"
    value["banner"]["rubric"] = "catalog"
    value["dedup_entries"] = [{
        "name": f"🆕 {title}",
        "date": value["date"],
        "free_until": None,
        "sale_until": None,
    } for title in titles]
    value["dedup_entries"].append({
        "name": f"🆕 завоз {value['date']}",
        "date": value["date"],
        "free_until": None,
        "sale_until": None,
    })
    return value


class RoutineTests(unittest.TestCase):
    def test_runtime_fetches_seven_days_of_catalog(self):
        with patch.object(routine, "fetch_json", return_value={"ok": True, "data": []}) as fetch:
            routine.collect_runtime({})

        fetch.assert_any_call(
            "https://steamgate.online/api/integrations/new-games",
            {"days": 7},
        )

    def test_valid_news(self):
        routine.validate_draft(draft())

    def test_rejects_broken_html(self):
        value = draft(caption=(
            '<b>Тема</i>\n<a href="https://example.com">Источник</a>\n'
            '<blockquote>🔥 — да\n💩 — нет</blockquote>\n#steam #игры #новости #pc #gaming'
        ))
        with self.assertRaisesRegex(ValueError, "несбалансированный"):
            routine.validate_draft(value)

    def test_rejects_money_in_sale_caption(self):
        value = draft("sale", (
            '<b>Скидки</b>\n<blockquote>🔴 <a href="https://example.com/game"><b>Игра</b></a> $10</blockquote>\n'
            '<blockquote>🔥 — да\n💩 — нет</blockquote>\n#steam #игры #скидки #pc #gaming'
        ))
        value["dedup_entries"] = [{
            "name": "Игра",
            "date": value["date"],
            "free_until": None,
            "sale_until": (dt.date.today() + dt.timedelta(days=5)).isoformat(),
        }]
        with self.assertRaisesRegex(ValueError, "цена"):
            routine.validate_draft(value)

    def test_rejects_freebie_marker_explanation(self):
        value = draft("freebie", (
            '🎁 <b>Moonlighter бесплатно</b>\n'
            '<blockquote>🎁 <a href="https://example.com/game"><b>Moonlighter</b></a> бесплатно</blockquote>\n'
            'Забрать можно до 9 августа.\n🎁 — забрать и оставить навсегда\n'
            '<blockquote>🔥 — забираю\n💩 — не люблю пиксели</blockquote>\n'
            '#халява #steam #игры #рогалик #rpg'
        ))
        with self.assertRaisesRegex(ValueError, "не нужна расшифровка"):
            routine.validate_caption(value)

    def test_rejects_forced_negative_reaction(self):
        value = draft("catalog", (
            '🆕 <b>В SteamGate добавили 2 игры</b>\n\n'
            'Marvel Tōkon и The Jackbox Party Pack 5 уже в каталоге.\n\n'
            '<a href="https://example.com/catalog">Открыть каталог</a>\n\n'
            '<blockquote>🔥 — собираю команду\n💩 — сегодня без викторин</blockquote>\n\n'
            '#SteamGate #новинки #Steam #MarvelTokon #Jackbox'
        ))
        with self.assertRaisesRegex(ValueError, "человеческую причину"):
            routine.validate_caption(value)

    def test_accepts_human_catalog_copy(self):
        value = draft("catalog", (
            '🆕 <b>В SteamGate добавили 2 игры</b>\n\n'
            'Marvel Tōkon и The Jackbox Party Pack 5 уже в каталоге.\n\n'
            '<a href="https://example.com/catalog">Открыть каталог</a>\n\n'
            '<blockquote>🔥 — собираю команду\n💩 — не люблю викторины</blockquote>\n\n'
            '#SteamGate #новинки #Steam #MarvelTokon #Jackbox'
        ))
        routine.validate_caption(value)

    def test_accepts_compact_catalog_list(self):
        value = draft("catalog", (
            '🆕 <b>В SteamGate добавили 3 игры</b>\n\n'
            '<blockquote expandable>OCTOPATH TRAVELER 0\nMorbid Metal\nSephiria</blockquote>\n\n'
            '<a href="https://example.com/catalog">Открыть каталог</a>\n\n'
            '<blockquote>🔥 — начинаю с Octopath\n💩 — не моё</blockquote>\n\n'
            '#SteamGate #новинки #Steam #игры #PCGaming'
        ))
        routine.validate_caption(value)

    def test_accepts_natural_nothing_caught_me_reaction(self):
        value = draft("catalog", (
            '🆕 <b>В SteamGate добавили 2 игры</b>\n\n'
            'OCTOPATH TRAVELER 0 и Sephiria уже в каталоге.\n\n'
            '<a href="https://example.com/catalog">Открыть каталог</a>\n\n'
            '<blockquote>🔥 — начинаю с Octopath\n💩 — ничего не зацепило</blockquote>\n\n'
            '#SteamGate #новинки #Steam #игры #PCGaming'
        ))
        routine.validate_caption(value)

    def test_rejects_repeated_catalog_wording(self):
        value = draft("catalog", (
            '🆕 <b>Завоз в каталог — 2 игры</b>\n\n'
            'Свежий завоз уже доступен.\n\n'
            '<a href="https://example.com/catalog">Смотреть завоз</a>\n\n'
            '<blockquote>🔥 — забираю\n💩 — не моё</blockquote>\n\n'
            '#SteamGate #завоз #Steam #игры #новинки'
        ))
        with self.assertRaisesRegex(ValueError, "повторяется"):
            routine.validate_caption(value)

    def test_rejects_catalog_banner_title_that_repeats_rubric(self):
        banner = draft()["banner"]
        banner["rubric"] = "catalog"
        banner["title"] = "ЗАВОЗ В КАТАЛОГ STEAMGATE"
        with self.assertRaisesRegex(ValueError, "системную рубрику"):
            routine.validate_banner(banner)

    def test_merge_keeps_active_and_recent(self):
        today = dt.date(2026, 8, 6)
        existing = [
            {"name": "Старая", "date": "2026-06-01"},
            {"name": "Активная", "date": "2026-06-01", "free_until": "2026-08-07"},
            {"name": "Свежая", "date": "2026-08-01"},
        ]
        result = routine.merge_posted(existing, [{"name": "Новая", "date": "2026-08-06"}], today)
        self.assertEqual([item["name"] for item in result], ["Активная", "Свежая", "Новая"])

    def test_rejects_recent_duplicate(self):
        value = draft()
        history = [{"name": value["dedup_entries"][0]["name"], "date": value["date"]}]
        with self.assertRaisesRegex(ValueError, "уже была"):
            routine.validate_history(value, history, [])

    def test_rejects_sixth_daily_post(self):
        value = draft()
        lines = [f"{value['date']} | А | пост {index}" for index in range(5)]
        with self.assertRaisesRegex(ValueError, "лимит пяти"):
            routine.validate_history(value, [], lines)

    def test_catalog_bypasses_daily_post_limit(self):
        value = catalog_draft(["Новая игра"])
        lines = [f"{value['date']} | А | пост {index}" for index in range(5)]
        routine.validate_history(value, [], lines)

    def test_catalog_daily_marker_does_not_block_late_game(self):
        value = catalog_draft(["Поздняя игра"])
        posted = [{"name": f"🆕 завоз {value['date']}", "date": value["date"]}]
        routine.validate_history(value, posted, [])

    def test_pending_catalog_blocks_lower_tier_even_after_daily_marker(self):
        today = routine.moscow_now().date().isoformat()
        value = draft()
        posted = [{"name": f"🆕 завоз {today}", "date": today}]
        data = runtime([("ReStory", today + "T08:38:36Z")])
        with self.assertRaisesRegex(ValueError, "тир 2 обязателен"):
            routine.validate_priority(value, data, posted)

    def test_catalog_must_include_every_pending_game(self):
        today = routine.moscow_now().date().isoformat()
        data = runtime([
            ("ReStory", today + "T08:38:36Z"),
            ("Bills Must Be Paid", today + "T07:00:00Z"),
        ])
        value = catalog_draft(["ReStory"])
        with self.assertRaisesRegex(ValueError, "Bills Must Be Paid"):
            routine.validate_priority(value, data, [])

    def test_previous_day_unpublished_catalog_game_stays_pending(self):
        yesterday = routine.moscow_now().date() - dt.timedelta(days=1)
        data = runtime([("Поздняя игра", yesterday.isoformat() + "T22:30:00Z")])
        self.assertEqual(routine.pending_catalog_titles(data, []), ["Поздняя игра"])

    def test_six_day_old_unpublished_catalog_game_stays_pending(self):
        oldest = routine.moscow_now().date() - dt.timedelta(days=6)
        data = runtime([("Пропущенная игра", oldest.isoformat() + "T12:00:00Z")])
        self.assertEqual(routine.pending_catalog_titles(data, []), ["Пропущенная игра"])

    def test_freebie_has_priority_over_catalog(self):
        today = routine.moscow_now().date().isoformat()
        data = runtime([("Новая игра", today + "T08:00:00Z")], ["Moonlighter"])
        value = catalog_draft(["Новая игра"])
        with self.assertRaisesRegex(ValueError, "тир 1 обязателен"):
            routine.validate_priority(value, data, [])

    def test_active_posted_freebie_is_not_pending(self):
        data = runtime(freebies=["Moonlighter"])
        posted = [{
            "name": "Moonlighter",
            "date": routine.moscow_now().date().isoformat(),
            "free_until": (routine.moscow_now().date() + dt.timedelta(days=1)).isoformat(),
        }]
        self.assertEqual(routine.pending_freebies(data, posted), [])

    def test_model_replaces_stale_draft_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "draft.json"
            output.write_text('{"stale": true}', encoding="utf-8")
            candidate = output.with_suffix(".json.next")

            def complete_model(*args, **kwargs):
                candidate.write_text('{"fresh": true}', encoding="utf-8")

            with patch.object(routine, "run_checked", side_effect=complete_model):
                routine.run_model(output)

            self.assertEqual(routine.load_json(output), {"fresh": True})
            self.assertFalse(candidate.exists())

    def test_retries_rejected_model_draft_with_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "draft.json"
            feedback = []

            def complete_model(path, error=None):
                feedback.append(error)
                value = draft()
                if error is None:
                    value["date"] = "2020-01-01"
                routine.write_json(path, value)

            with patch.object(routine, "run_model", side_effect=complete_model):
                result = routine.prepare_model_draft(output, runtime(), [], [])

            self.assertEqual(result["date"], routine.moscow_now().date().isoformat())
            self.assertIn("дата черновика", feedback[1])

    def test_vision_replaces_stale_result_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "vision.json"
            output.write_text('{"ok": false}', encoding="utf-8")
            candidate = output.with_suffix(".json.next")

            def complete_vision(*args, **kwargs):
                routine.write_json(candidate, {
                    "ok": True,
                    "topic_match": True,
                    "readable": True,
                    "issues": [],
                })

            with patch.object(routine, "run_checked", side_effect=complete_vision):
                routine.run_vision(draft(), Path(directory) / "banner.jpg", output)

            self.assertTrue(routine.load_json(output)["ok"])
            self.assertFalse(candidate.exists())

    def test_premiumifies_only_plain_text(self):
        source = '🟢 <b>Игра</b> <tg-emoji emoji-id="1">🔥</tg-emoji> 🔥'
        result = premiumify_html(source)
        self.assertIn('emoji-id="5416081784641168838"', result)
        self.assertEqual(result.count('emoji-id="5424972470023104089"'), 1)
        self.assertIn('<tg-emoji emoji-id="1">🔥</tg-emoji>', result)


if __name__ == "__main__":
    unittest.main()
