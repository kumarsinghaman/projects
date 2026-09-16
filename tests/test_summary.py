import unittest

from nutritrack.log import LoggedItem, MealLog
from nutritrack.profile import Profile
from nutritrack.summary import (
    GoalProgress,
    date_range,
    summarize_day,
    summarize_range,
    top_contributors,
)
from tests.test_log import sample_db


def entry(entry_id, meal, food_id, grams, day="2026-09-15") -> LoggedItem:
    return LoggedItem(
        id=entry_id,
        date=day,
        meal=meal,
        grams=grams,
        food_name=food_id,
        food_id=food_id,
    )


class DaySummaryTests(unittest.TestCase):
    def setUp(self):
        self.db = sample_db()
        self.log = MealLog(
            items=[
                entry("20260915-001", "dinner", "rice", 100.0),
                entry("20260915-002", "lunch", "rice", 150.0),
                entry("20260915-003", "lunch", "dal", 200.0),
                entry("20260914-001", "lunch", "rice", 100.0, day="2026-09-14"),
            ]
        )
        self.profile = Profile(goals={"kcal": 1000.0, "protein_g": 20.0})

    def test_meals_are_grouped_and_ordered(self):
        day = summarize_day(self.log, self.db, "2026-09-15")
        self.assertEqual([meal.meal for meal in day.meals], ["lunch", "dinner"])
        self.assertEqual(len(day.meals[0].lines), 2)

    def test_meal_totals_sum_their_items(self):
        day = summarize_day(self.log, self.db, "2026-09-15")
        lunch = day.meals[0]
        # 150 g rice (195 kcal) + 200 g dal (232 kcal)
        self.assertAlmostEqual(lunch.totals["kcal"], 427.0)
        self.assertAlmostEqual(lunch.grams, 350.0)

    def test_day_totals_sum_every_meal(self):
        day = summarize_day(self.log, self.db, "2026-09-15")
        self.assertAlmostEqual(day.totals["kcal"], 557.0)
        self.assertEqual(day.item_count, 3)

    def test_other_days_are_excluded(self):
        day = summarize_day(self.log, self.db, "2026-09-14")
        self.assertAlmostEqual(day.totals["kcal"], 130.0)

    def test_empty_day(self):
        day = summarize_day(self.log, self.db, "2026-09-01")
        self.assertTrue(day.is_empty)
        self.assertEqual(day.totals["kcal"], 0.0)
        self.assertEqual(day.macro_split["carb_g"], 0.0)

    def test_progress_uses_profile_goals(self):
        day = summarize_day(self.log, self.db, "2026-09-15", self.profile)
        kcal = day.progress_for("kcal")
        self.assertAlmostEqual(kcal.goal, 1000.0)
        self.assertAlmostEqual(kcal.percent, 55.7)
        self.assertAlmostEqual(kcal.remaining, 443.0)

    def test_progress_without_a_profile_has_no_goals(self):
        day = summarize_day(self.log, self.db, "2026-09-15")
        self.assertIsNone(day.progress_for("kcal").goal)
        self.assertEqual(day.progress_for("kcal").status, "no-goal")

    def test_top_contributors_are_sorted_by_calories(self):
        day = summarize_day(self.log, self.db, "2026-09-15")
        top = top_contributors(day, limit=2)
        self.assertEqual(
            [line.item.id for line in top], ["20260915-003", "20260915-002"]
        )

    def test_photos_are_collected_without_duplicates(self):
        items = [
            entry("20260915-001", "lunch", "rice", 100.0),
            entry("20260915-002", "lunch", "dal", 100.0),
        ]
        items[0].photo = "photos/a.jpg"
        items[1].photo = "photos/a.jpg"
        day = summarize_day(MealLog(items=items), self.db, "2026-09-15")
        self.assertEqual(day.photos, ["photos/a.jpg"])


class GoalStatusTests(unittest.TestCase):
    def status(self, value, goal, is_limit=False, exceed_ok=False):
        return GoalProgress(
            key="kcal", value=value, goal=goal, is_limit=is_limit, exceed_ok=exceed_ok
        ).status

    def test_budget_nutrient_statuses(self):
        self.assertEqual(self.status(500, 1000), "under")
        self.assertEqual(self.status(950, 1000), "met")
        self.assertEqual(self.status(1050, 1000), "met")
        self.assertEqual(self.status(1200, 1000), "over")

    def test_limit_nutrient_is_fine_until_exceeded(self):
        self.assertEqual(self.status(10, 1000, is_limit=True), "on-track")
        self.assertEqual(self.status(1000, 1000, is_limit=True), "on-track")
        self.assertEqual(self.status(1001, 1000, is_limit=True), "over")

    def test_exceeding_protein_or_fiber_still_counts_as_met(self):
        self.assertEqual(self.status(300, 100, exceed_ok=True), "met")
        self.assertEqual(self.status(50, 100, exceed_ok=True), "under")

    def test_missing_goal(self):
        progress = GoalProgress(key="kcal", value=100, goal=None, is_limit=False)
        self.assertEqual(progress.status, "no-goal")
        self.assertIsNone(progress.percent)
        self.assertIsNone(progress.remaining)

    def test_zero_goal_is_treated_as_absent(self):
        self.assertEqual(self.status(100, 0), "no-goal")


class RangeTests(unittest.TestCase):
    def setUp(self):
        self.db = sample_db()
        self.log = MealLog(
            items=[
                entry("20260913-001", "lunch", "rice", 100.0, day="2026-09-13"),
                entry("20260915-001", "lunch", "rice", 300.0, day="2026-09-15"),
            ]
        )
        self.profile = Profile(goals={"kcal": 1000.0})

    def test_date_range_is_inclusive(self):
        self.assertEqual(
            date_range("2026-09-13", "2026-09-15"),
            ["2026-09-13", "2026-09-14", "2026-09-15"],
        )

    def test_reversed_range_is_rejected(self):
        with self.assertRaises(ValueError):
            date_range("2026-09-15", "2026-09-13")

    def test_range_includes_days_with_no_entries(self):
        summary = summarize_range(self.log, self.db, "2026-09-13", "2026-09-15")
        self.assertEqual(len(summary.days), 3)
        self.assertEqual(len(summary.logged_days), 2)

    def test_averages_ignore_days_without_entries(self):
        summary = summarize_range(self.log, self.db, "2026-09-13", "2026-09-15")
        # 130 kcal and 390 kcal over two logged days.
        self.assertAlmostEqual(summary.averages()["kcal"], 260.0)

    def test_totals_cover_the_whole_span(self):
        summary = summarize_range(self.log, self.db, "2026-09-13", "2026-09-15")
        self.assertAlmostEqual(summary.totals["kcal"], 520.0)

    def test_average_progress_compares_against_goals(self):
        summary = summarize_range(
            self.log, self.db, "2026-09-13", "2026-09-15", self.profile
        )
        kcal = next(p for p in summary.average_progress() if p.key == "kcal")
        self.assertAlmostEqual(kcal.percent, 26.0)

    def test_empty_range_averages_to_zero(self):
        summary = summarize_range(MealLog(), self.db, "2026-09-13", "2026-09-15")
        self.assertEqual(summary.averages()["kcal"], 0.0)


if __name__ == "__main__":
    unittest.main()
