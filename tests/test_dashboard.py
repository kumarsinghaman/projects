import re
import tempfile
import unittest
from pathlib import Path

from nutritrack.dashboard import render_dashboard_html, write_dashboard
from nutritrack.log import LoggedItem, MealLog
from nutritrack.profile import Profile
from nutritrack.summary import summarize_day, summarize_range
from tests.test_log import sample_db

_DEFAULT_GOALS = {"kcal": 2000.0, "protein_g": 120.0}


def build_day(items=None, goals=_DEFAULT_GOALS):
    entries = items if items is not None else [
        LoggedItem(
            id="20260915-001",
            date="2026-09-15",
            meal="lunch",
            grams=150.0,
            food_name="Rice, cooked",
            food_id="rice",
        ),
        LoggedItem(
            id="20260915-002",
            date="2026-09-15",
            meal="lunch",
            grams=200.0,
            food_name="Dal, cooked",
            food_id="dal",
        ),
    ]
    log = MealLog(items=entries)
    profile = Profile(name="Tester", goals=dict(goals))
    return summarize_day(log, sample_db(), "2026-09-15", profile), profile, log


class MarkupTests(unittest.TestCase):
    def test_document_is_self_contained(self):
        day, profile, _ = build_day()
        markup = render_dashboard_html(day, profile=profile)
        self.assertTrue(markup.startswith("<!DOCTYPE html>"))
        self.assertIn("<style>", markup)
        # No network requests: a dashboard must render offline.
        self.assertNotIn("http://", markup)
        self.assertNotIn("https://", markup)
        self.assertNotIn("<script", markup)

    def test_totals_and_meal_rows_are_present(self):
        day, profile, _ = build_day()
        markup = render_dashboard_html(day, profile=profile)
        self.assertIn("Rice, cooked", markup)
        self.assertIn("Dal, cooked", markup)
        self.assertIn("Lunch", markup)
        self.assertIn("427", markup)  # lunch calories

    def test_calorie_ring_reflects_the_goal(self):
        day, profile, _ = build_day(goals={"kcal": 1000.0})
        markup = render_dashboard_html(day, profile=profile)
        self.assertIn("of 1000 kcal goal", markup)
        self.assertIn("43%", markup)

    def test_empty_day_renders_without_dividing_by_zero(self):
        day, profile, _ = build_day(items=[])
        markup = render_dashboard_html(day, profile=profile)
        self.assertIn("Nothing logged for this day yet.", markup)

    def test_missing_goals_are_reported_rather_than_crashing(self):
        day, profile, _ = build_day(goals={})
        markup = render_dashboard_html(day, profile=profile)
        self.assertIn("no calorie goal set", markup)

    def test_food_names_are_html_escaped(self):
        entry = LoggedItem(
            id="20260915-001",
            date="2026-09-15",
            meal="lunch",
            grams=100.0,
            food_name="<script>alert('x')</script>",
            food_id="rice",
        )
        day, profile, _ = build_day(items=[entry])
        markup = render_dashboard_html(day, profile=profile)
        self.assertNotIn("<script>alert", markup)
        self.assertIn("&lt;script&gt;", markup)

    def test_macro_split_becomes_a_conic_gradient(self):
        day, profile, _ = build_day()
        markup = render_dashboard_html(day, profile=profile)
        self.assertIn("conic-gradient(", markup)

    def test_trend_chart_shows_one_column_per_day(self):
        day, profile, log = build_day()
        trend = summarize_range(log, sample_db(), "2026-09-09", "2026-09-15", profile)
        markup = render_dashboard_html(day, profile=profile, trend=trend)
        self.assertIn("Last 7 days", markup)
        self.assertEqual(markup.count('class="col"'), 7)


class PhotoTests(unittest.TestCase):
    def test_existing_photo_is_embedded_relative_to_the_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "photos").mkdir()
            (root / "photos" / "lunch.jpg").write_bytes(b"jpeg-ish")
            entry = LoggedItem(
                id="20260915-001",
                date="2026-09-15",
                meal="lunch",
                grams=150.0,
                food_name="Rice, cooked",
                food_id="rice",
                photo="photos/lunch.jpg",
            )
            day, profile, _ = build_day(items=[entry])
            output = root / "reports" / "day.html"
            write_dashboard(day, output, profile=profile, repo_root=root)
            markup = output.read_text()
        self.assertIn('<img src="../photos/lunch.jpg"', markup)

    def test_missing_photo_is_skipped_silently(self):
        entry = LoggedItem(
            id="20260915-001",
            date="2026-09-15",
            meal="lunch",
            grams=150.0,
            food_name="Rice, cooked",
            food_id="rice",
            photo="photos/gone.jpg",
        )
        day, profile, _ = build_day(items=[entry])
        markup = render_dashboard_html(day, profile=profile)
        self.assertNotIn("<img", markup)


class OutputTests(unittest.TestCase):
    def test_write_dashboard_creates_parent_directories(self):
        day, profile, _ = build_day()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "deep" / "nested" / "day.html"
            write_dashboard(day, target, profile=profile)
            self.assertTrue(target.exists())

    def test_percentages_never_exceed_the_bar_width(self):
        day, profile, _ = build_day(goals={"kcal": 100.0})
        markup = render_dashboard_html(day, profile=profile)
        for width in re.findall(r"width:([\d.]+)%", markup):
            self.assertLessEqual(float(width), 100.0)


if __name__ == "__main__":
    unittest.main()
