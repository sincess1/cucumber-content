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


class RoutineTests(unittest.TestCase):
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
                result = routine.prepare_model_draft(output, [], [])

            self.assertEqual(result["date"], routine.moscow_now().date().isoformat())
            self.assertIn("дата черновика", feedback[1])

    def test_premiumifies_only_plain_text(self):
        source = '🟢 <b>Игра</b> <tg-emoji emoji-id="1">🔥</tg-emoji> 🔥'
        result = premiumify_html(source)
        self.assertIn('emoji-id="5416081784641168838"', result)
        self.assertEqual(result.count('emoji-id="5424972470023104089"'), 1)
        self.assertIn('<tg-emoji emoji-id="1">🔥</tg-emoji>', result)


if __name__ == "__main__":
    unittest.main()
