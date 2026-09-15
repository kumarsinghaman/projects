import tempfile
import unittest
from datetime import date
from pathlib import Path

from nutritrack.foods import FoodDatabase
from nutritrack.log import (
    LoggedItem,
    MealLog,
    canonical_meal,
    group_by_meal,
    meal_sort_key,
    parse_date,
    parse_items_spec,
)
from tests.test_foods import make_food


def sample_db() -> FoodDatabase:
    return FoodDatabase(
        [
            make_food("rice", "Rice, cooked", kcal=130.0, protein_g=2.7, carb_g=28.2),
            make_food("dal", "Dal, cooked", kcal=116.0, protein_g=7.0, carb_g=20.0),
        ]
    )


def item(entry_id="20260915-001", **kwargs) -> LoggedItem:
    defaults = dict(
        id=entry_id,
        date="2026-09-15",
        meal="lunch",
        grams=100.0,
        food_name="Rice, cooked",
        food_id="rice",
    )
    defaults.update(kwargs)
    return LoggedItem(**defaults)


class MealNameTests(unittest.TestCase):
    def test_aliases_expand(self):
        self.assertEqual(canonical_meal("B"), "breakfast")
        self.assertEqual(canonical_meal(" Supper "), "dinner")

    def test_unknown_meal_names_pass_through_normalized(self):
        self.assertEqual(canonical_meal("Second Dinner!"), "second dinner")

    def test_empty_meal_name_is_rejected(self):
        with self.assertRaises(ValueError):
            canonical_meal("   ")

    def test_known_meals_sort_chronologically(self):
        meals = ["dinner", "breakfast", "snack", "lunch"]
        self.assertEqual(
            sorted(meals, key=meal_sort_key),
            ["breakfast", "lunch", "snack", "dinner"],
        )

    def test_unknown_meals_sort_last(self):
        meals = ["midnight feast", "breakfast"]
        self.assertEqual(
            sorted(meals, key=meal_sort_key), ["breakfast", "midnight feast"]
        )


class DateParsingTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 9, 15)

    def test_none_and_today(self):
        self.assertEqual(parse_date(None, self.today), "2026-09-15")
        self.assertEqual(parse_date("today", self.today), "2026-09-15")

    def test_yesterday_and_offsets(self):
        self.assertEqual(parse_date("yesterday", self.today), "2026-09-14")
        self.assertEqual(parse_date("-3", self.today), "2026-09-12")

    def test_iso_date_passes_through(self):
        self.assertEqual(parse_date("2026-01-02", self.today), "2026-01-02")

    def test_garbage_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_date("last tuesday", self.today)


class ItemSpecTests(unittest.TestCase):
    def test_single_item(self):
        self.assertEqual(parse_items_spec("roti:80"), [("roti", 80.0)])

    def test_multiple_items_and_whitespace(self):
        self.assertEqual(
            parse_items_spec(" roti:80 , dal tadka:200 "),
            [("roti", 80.0), ("dal tadka", 200.0)],
        )

    def test_trailing_g_is_accepted(self):
        self.assertEqual(parse_items_spec("rice:150g"), [("rice", 150.0)])

    def test_name_containing_colon_uses_last_colon_as_separator(self):
        self.assertEqual(parse_items_spec("dal: tadka:200"), [("dal: tadka", 200.0)])

    def test_missing_grams_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_items_spec("roti")

    def test_non_numeric_grams_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_items_spec("roti:some")

    def test_zero_grams_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_items_spec("roti:0")

    def test_empty_spec_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_items_spec("  ,  ")


class LoggedItemTests(unittest.TestCase):
    def test_nutrients_come_from_the_database(self):
        values = item(grams=150.0).nutrients(sample_db())
        self.assertAlmostEqual(values["kcal"], 195.0)
        self.assertAlmostEqual(values["carb_g"], 42.3)

    def test_database_values_win_over_stored_snapshot(self):
        stale = item(per_100g={"kcal": 999.0})
        self.assertAlmostEqual(stale.nutrients(sample_db())["kcal"], 130.0)

    def test_inline_values_are_used_for_foods_outside_the_database(self):
        one_off = item(
            food_id=None,
            food_name="Aunt's halwa",
            grams=50.0,
            per_100g={
                "kcal": 400.0,
                "protein_g": 4.0,
                "carb_g": 50.0,
                "fiber_g": 1.0,
                "sugar_g": 35.0,
                "fat_g": 20.0,
                "sat_fat_g": 12.0,
                "sodium_mg": 40.0,
                "potassium_mg": 80.0,
            },
        )
        self.assertAlmostEqual(one_off.nutrients(sample_db())["kcal"], 200.0)

    def test_unknown_food_without_inline_values_raises(self):
        orphan = item(food_id="ghost", per_100g=None)
        with self.assertRaises(KeyError):
            orphan.nutrients(sample_db())

    def test_round_trip_through_dict(self):
        original = item(time="08:30", note="2 bowls", photo="photos/a.jpg")
        restored = LoggedItem.from_dict(original.to_dict())
        self.assertEqual(restored, original)

    def test_optional_fields_are_omitted_when_empty(self):
        stored = item().to_dict()
        self.assertNotIn("note", stored)
        self.assertNotIn("photo", stored)
        self.assertNotIn("time", stored)


class MealLogTests(unittest.TestCase):
    def setUp(self):
        self.log = MealLog()

    def test_ids_increment_within_a_day(self):
        first = self.log.next_id("2026-09-15")
        self.assertEqual(first, "20260915-001")
        self.log.add(item(first))
        self.assertEqual(self.log.next_id("2026-09-15"), "20260915-002")

    def test_ids_are_per_day(self):
        self.log.add(item("20260915-001"))
        self.assertEqual(self.log.next_id("2026-09-16"), "20260916-001")

    def test_duplicate_ids_are_rejected(self):
        self.log.add(item("20260915-001"))
        with self.assertRaises(ValueError):
            self.log.add(item("20260915-001"))

    def test_remove_returns_the_entry(self):
        self.log.add(item("20260915-001"))
        removed = self.log.remove("20260915-001")
        self.assertEqual(removed.id, "20260915-001")
        self.assertEqual(self.log.items, [])

    def test_removing_unknown_id_raises(self):
        with self.assertRaises(KeyError):
            self.log.remove("nope")

    def test_for_date_filters_and_orders_by_meal(self):
        self.log.add(item("20260915-001", meal="dinner"))
        self.log.add(item("20260915-002", meal="breakfast"))
        self.log.add(item("20260916-001", meal="lunch", date="2026-09-16"))
        meals = [entry.meal for entry in self.log.for_date("2026-09-15")]
        self.assertEqual(meals, ["breakfast", "dinner"])

    def test_between_is_inclusive(self):
        for day in ("2026-09-13", "2026-09-14", "2026-09-15"):
            self.log.add(item(f"{day.replace('-', '')}-001", date=day))
        span = self.log.between("2026-09-14", "2026-09-15")
        self.assertEqual([entry.date for entry in span], ["2026-09-14", "2026-09-15"])

    def test_dates_and_last_date(self):
        self.assertIsNone(self.log.last_date())
        self.log.add(item("20260914-001", date="2026-09-14"))
        self.log.add(item("20260915-001", date="2026-09-15"))
        self.assertEqual(self.log.dates(), ["2026-09-14", "2026-09-15"])
        self.assertEqual(self.log.last_date(), "2026-09-15")

    def test_save_and_reload_round_trip(self):
        self.log.add(item("20260915-001", note="with ghee"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "log.json"
            self.log.save(path)
            reloaded = MealLog.load(path)
        self.assertEqual(len(reloaded.items), 1)
        self.assertEqual(reloaded.items[0].note, "with ghee")

    def test_loading_a_missing_file_gives_an_empty_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            reloaded = MealLog.load(Path(tmp) / "absent.json")
        self.assertEqual(reloaded.items, [])


class GroupingTests(unittest.TestCase):
    def test_group_by_meal_is_chronological(self):
        items = [
            item("1", meal="dinner"),
            item("2", meal="breakfast"),
            item("3", meal="dinner"),
        ]
        grouped = group_by_meal(items)
        self.assertEqual([meal for meal, _ in grouped], ["breakfast", "dinner"])
        self.assertEqual(len(grouped[1][1]), 2)


if __name__ == "__main__":
    unittest.main()
