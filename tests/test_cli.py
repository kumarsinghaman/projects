import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from nutritrack.cli import main


class CliTestCase(unittest.TestCase):
    """Each test gets its own data directory, so the real log is never touched."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def run_cli(self, *args: str):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--data-dir", str(self.data_dir), *args])
        return code, out.getvalue(), err.getvalue()

    def log_ok(self, *args: str) -> str:
        code, out, err = self.run_cli("log", *args)
        self.assertEqual(code, 0, err)
        return out


class LogCommandTests(CliTestCase):
    def test_logging_reports_per_item_and_meal_totals(self):
        out = self.log_ok("-m", "breakfast", "-d", "2026-09-15", "idli:150")
        self.assertIn("Idli, steamed 150 g", out)
        self.assertIn("158 kcal", out)
        self.assertIn("breakfast total: 158 kcal", out)

    def test_multiple_items_in_one_call(self):
        out = self.log_ok(
            "-m", "lunch", "-d", "2026-09-15", "roti:80", "dal tadka:200"
        )
        self.assertIn("Roti / chapati", out)
        self.assertIn("Dal tadka", out)
        self.assertIn("lunch total:", out)

    def test_comma_separated_spec(self):
        out = self.log_ok(
            "-m", "lunch", "-d", "2026-09-15", "--items-spec", "roti:80, curd:150"
        )
        self.assertIn("Roti / chapati", out)
        self.assertIn("Curd / dahi", out)

    def test_log_is_persisted_between_invocations(self):
        self.log_ok("-m", "lunch", "-d", "2026-09-15", "rice:150")
        self.log_ok("-m", "dinner", "-d", "2026-09-15", "rice:100")
        code, out, _ = self.run_cli("day", "2026-09-15")
        self.assertEqual(code, 0)
        self.assertIn("LUNCH", out)
        self.assertIn("DINNER", out)
        self.assertIn("325 kcal", out)

    def test_running_totals_accumulate(self):
        self.log_ok("-m", "lunch", "-d", "2026-09-15", "rice:150")
        out = self.log_ok("-m", "dinner", "-d", "2026-09-15", "rice:150")
        self.assertIn("day so far: 390", out)

    def test_note_and_time_are_stored(self):
        self.log_ok(
            "-m", "snack", "-d", "2026-09-15", "-t", "17:00",
            "--note", "post-gym", "almonds:20",
        )
        code, out, _ = self.run_cli("day", "2026-09-15", "--json")
        payload = json.loads(out)
        item = payload["meals"][0]["items"][0]
        self.assertEqual(item["note"], "post-gym")
        self.assertEqual(item["time"], "17:00")

    def test_ambiguous_food_exits_with_code_two_and_lists_ids(self):
        code, out, err = self.run_cli("log", "-m", "lunch", "da:100")
        self.assertEqual(code, 2)
        self.assertIn("matches more than one food", err)
        self.assertIn("dal_plain", err)

    def test_unknown_food_suggests_alternatives(self):
        code, _, err = self.run_cli("log", "-m", "lunch", "rotti:80")
        self.assertEqual(code, 1)
        self.assertIn("No food matches", err)
        self.assertIn("Roti / chapati", err)

    def test_logging_nothing_is_an_error(self):
        code, _, err = self.run_cli("log", "-m", "lunch")
        self.assertEqual(code, 1)
        self.assertIn("nothing to log", err)

    def test_bad_gram_amount_is_an_error(self):
        code, _, err = self.run_cli("log", "-m", "lunch", "rice:lots")
        self.assertEqual(code, 1)
        self.assertIn("non-numeric", err)

    def test_missing_photo_is_an_error(self):
        code, _, err = self.run_cli(
            "log", "-m", "lunch", "rice:100", "--photo", "/nope/absent.jpg"
        )
        self.assertEqual(code, 1)
        self.assertIn("photo not found", err)

    def test_photo_is_recorded_when_it_exists(self):
        photo = self.data_dir / "meal.jpg"
        photo.write_bytes(b"not really a jpeg")
        self.log_ok(
            "-m", "lunch", "-d", "2026-09-15", "rice:100", "--photo", str(photo)
        )
        code, out, _ = self.run_cli("day", "2026-09-15", "--json")
        self.assertEqual(
            json.loads(out)["meals"][0]["items"][0]["photo"], str(photo)
        )


class DayCommandTests(CliTestCase):
    def setUp(self):
        super().setUp()
        self.log_ok("-m", "breakfast", "-d", "2026-09-15", "idli:150", "sambar:150")
        self.log_ok("-m", "lunch", "-d", "2026-09-15", "roti:120", "dal tadka:200")

    def test_empty_day_says_so(self):
        code, out, _ = self.run_cli("day", "2026-01-01")
        self.assertEqual(code, 0)
        self.assertIn("Nothing logged", out)

    def test_totals_only_hides_items(self):
        code, out, _ = self.run_cli("day", "2026-09-15", "--totals-only")
        self.assertEqual(code, 0)
        self.assertNotIn("Idli, steamed", out)
        self.assertIn("DAY TOTALS", out)

    def test_top_contributors(self):
        code, out, _ = self.run_cli("day", "2026-09-15", "--top", "2")
        self.assertEqual(code, 0)
        self.assertIn("BIGGEST CONTRIBUTORS BY CALORIES", out)

    def test_json_structure(self):
        code, out, _ = self.run_cli("day", "2026-09-15", "--json")
        payload = json.loads(out)
        self.assertEqual(payload["date"], "2026-09-15")
        self.assertEqual(
            [meal["meal"] for meal in payload["meals"]], ["breakfast", "lunch"]
        )
        self.assertAlmostEqual(
            payload["totals"]["kcal"],
            sum(meal["totals"]["kcal"] for meal in payload["meals"]),
            places=2,
        )
        self.assertEqual(len(payload["progress"]), 9)

    def test_json_meal_totals_match_their_items(self):
        code, out, _ = self.run_cli("day", "2026-09-15", "--json")
        for meal in json.loads(out)["meals"]:
            self.assertAlmostEqual(
                meal["totals"]["protein_g"],
                sum(item["nutrients"]["protein_g"] for item in meal["items"]),
                places=2,
            )

    def test_range_and_week_report(self):
        code, out, _ = self.run_cli(
            "range", "--start", "2026-09-13", "--end", "2026-09-15"
        )
        self.assertEqual(code, 0)
        self.assertIn("(no entries)", out)
        self.assertIn("DAILY AVERAGE", out)
        code, out, _ = self.run_cli("week", "--end", "2026-09-15", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)["days"]), 7)


class EditingTests(CliTestCase):
    def setUp(self):
        super().setUp()
        self.log_ok("-m", "lunch", "-d", "2026-09-15", "rice:150")

    def test_entries_lists_ids(self):
        code, out, _ = self.run_cli("entries", "2026-09-15")
        self.assertEqual(code, 0)
        self.assertIn("20260915-001", out)

    def test_entries_on_an_empty_day(self):
        code, out, _ = self.run_cli("entries", "2026-01-01")
        self.assertEqual(code, 0)
        self.assertIn("No entries", out)

    def test_remove_drops_the_entry(self):
        code, out, _ = self.run_cli("remove", "20260915-001")
        self.assertEqual(code, 0)
        self.assertIn("Removed 20260915-001", out)
        _, out, _ = self.run_cli("day", "2026-09-15")
        self.assertIn("Nothing logged", out)

    def test_removing_an_unknown_id_fails(self):
        code, _, err = self.run_cli("remove", "nope")
        self.assertEqual(code, 1)
        self.assertIn("no log entry", err)

    def test_edit_grams_changes_the_totals(self):
        code, out, _ = self.run_cli("edit", "20260915-001", "--grams", "300")
        self.assertEqual(code, 0)
        self.assertIn("390 kcal", out)

    def test_edit_rejects_non_positive_grams(self):
        code, _, err = self.run_cli("edit", "20260915-001", "--grams", "0")
        self.assertEqual(code, 1)
        self.assertIn("must be positive", err)

    def test_edit_can_move_an_entry_to_another_meal(self):
        code, _, _ = self.run_cli("edit", "20260915-001", "--meal", "dinner")
        self.assertEqual(code, 0)
        _, out, _ = self.run_cli("day", "2026-09-15")
        self.assertIn("DINNER", out)
        self.assertNotIn("LUNCH", out)

    def test_edit_can_swap_the_food(self):
        code, out, _ = self.run_cli("edit", "20260915-001", "--food", "brown rice")
        self.assertEqual(code, 0)
        self.assertIn("Rice, brown, cooked", out)


class FoodCommandTests(CliTestCase):
    def test_search_lists_matches(self):
        code, out, _ = self.run_cli("foods", "paneer")
        self.assertEqual(code, 0)
        self.assertIn("paneer", out)

    def test_search_by_category(self):
        code, out, _ = self.run_cli("foods", "--category", "fruits", "--limit", "3")
        self.assertEqual(code, 0)
        self.assertIn("3 food(s)", out)

    def test_search_with_no_match(self):
        code, out, _ = self.run_cli("foods", "zzzzzz")
        self.assertEqual(code, 0)
        self.assertIn("No foods match", out)

    def test_show_scales_to_a_weight(self):
        code, out, _ = self.run_cli("food", "show", "chicken breast", "--grams", "200")
        self.assertEqual(code, 0)
        self.assertIn("330 kcal", out)
        self.assertIn("62.0 g", out)

    def test_custom_food_can_be_added_and_then_logged(self):
        code, out, _ = self.run_cli(
            "food", "add",
            "--name", "Amma's coconut chutney",
            "--alias", "coconut chutney",
            "--kcal", "180", "--protein", "3", "--carb", "8", "--fat", "15",
            "--fiber", "4", "--sodium", "260",
        )
        self.assertEqual(code, 0)
        self.assertIn("ammas_coconut_chutney", out)
        self.assertTrue((self.data_dir / "foods.custom.json").exists())

        out = self.log_ok("-m", "breakfast", "-d", "2026-09-15", "coconut chutney:50")
        self.assertIn("90 kcal", out)

    def test_custom_food_survives_a_reload(self):
        self.run_cli(
            "food", "add", "--name", "Office canteen thali", "--kcal", "150",
            "--protein", "6", "--carb", "20", "--fat", "5",
        )
        code, out, _ = self.run_cli("food", "show", "office canteen thali")
        self.assertEqual(code, 0)
        self.assertIn("150 kcal", out)

    def test_duplicate_custom_food_needs_force(self):
        args = ["food", "add", "--name", "Test Snack", "--kcal", "100"]
        self.assertEqual(self.run_cli(*args)[0], 0)
        code, _, err = self.run_cli(*args)
        self.assertEqual(code, 1)
        self.assertIn("--force", err)
        self.assertEqual(self.run_cli(*args, "--force")[0], 0)


class ProfileCommandTests(CliTestCase):
    def test_defaults_are_shown_before_anything_is_set(self):
        code, out, _ = self.run_cli("profile")
        self.assertEqual(code, 0)
        self.assertIn("daily goals (default)", out)

    def test_recompute_derives_goals_from_body_stats(self):
        code, out, _ = self.run_cli(
            "profile", "--name", "Aman", "--sex", "male", "--age", "28",
            "--height-cm", "175", "--weight-kg", "74", "--activity", "moderate",
            "--weight-goal", "lose", "--recompute",
        )
        self.assertEqual(code, 0)
        self.assertIn("BMR           1699 kcal/day", out)
        self.assertIn("daily goals (derived)", out)

    def test_recompute_without_body_stats_fails(self):
        code, _, err = self.run_cli("profile", "--recompute")
        self.assertEqual(code, 1)
        self.assertIn("--recompute needs", err)

    def test_single_goal_override(self):
        code, out, _ = self.run_cli("profile", "--set", "protein_g=150")
        self.assertEqual(code, 0)
        self.assertIn("150.0 g", out)
        self.assertIn("daily goals (manual)", out)

    def test_unknown_nutrient_override_is_rejected(self):
        code, _, err = self.run_cli("profile", "--set", "vitamin_q=10")
        self.assertEqual(code, 1)
        self.assertIn("unknown nutrient", err)

    def test_malformed_override_is_rejected(self):
        code, _, err = self.run_cli("profile", "--set", "protein_g")
        self.assertEqual(code, 1)
        self.assertIn("nutrient=value", err)

    def test_goals_feed_the_day_report(self):
        self.run_cli("profile", "--set", "kcal=1000")
        self.log_ok("-m", "lunch", "-d", "2026-09-15", "rice:150")
        code, out, _ = self.run_cli("day", "2026-09-15", "--json")
        kcal = next(p for p in json.loads(out)["progress"] if p["nutrient"] == "kcal")
        self.assertEqual(kcal["goal"], 1000.0)
        self.assertEqual(kcal["percent"], 19.5)


class OutputCommandTests(CliTestCase):
    def setUp(self):
        super().setUp()
        self.log_ok("-m", "lunch", "-d", "2026-09-15", "rice:150", "dal:200")

    def test_export_writes_one_row_per_entry(self):
        code, out, _ = self.run_cli("export")
        self.assertEqual(code, 0)
        rows = [line for line in out.strip().splitlines() if line]
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[0].startswith("id,date,meal"))

    def test_export_to_a_file(self):
        target = self.data_dir / "out.csv"
        code, out, _ = self.run_cli("export", "--out", str(target))
        self.assertEqual(code, 0)
        self.assertIn("Exported 2 entries", out)
        self.assertIn("Rice, white, cooked", target.read_text())

    def test_export_respects_the_date_window(self):
        code, out, _ = self.run_cli(
            "export", "--start", "2026-01-01", "--end", "2026-01-31"
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(out.strip().splitlines()), 1)

    def test_dashboard_writes_html(self):
        target = self.data_dir / "dash.html"
        code, out, _ = self.run_cli("dashboard", "2026-09-15", "--out", str(target))
        self.assertEqual(code, 0)
        self.assertIn("Dashboard written to", out)
        markup = target.read_text()
        self.assertIn("<!DOCTYPE html>", markup)
        self.assertIn("Rice, white, cooked", markup)
        self.assertIn("Tue 15 Sep 2026", markup)


class DataDirIsolationTests(CliTestCase):
    def test_a_fresh_data_dir_starts_empty_but_can_read_foods(self):
        code, out, _ = self.run_cli("today")
        self.assertEqual(code, 0)
        self.assertIn("Nothing logged", out)
        code, out, _ = self.run_cli("foods", "roti")
        self.assertEqual(code, 0)
        self.assertIn("roti", out)

    def test_log_and_profile_files_are_created_in_the_data_dir(self):
        self.log_ok("-m", "lunch", "-d", "2026-09-15", "rice:100")
        self.run_cli("profile", "--set", "kcal=2000")
        self.assertTrue((self.data_dir / "log.json").exists())
        self.assertTrue((self.data_dir / "profile.json").exists())


if __name__ == "__main__":
    unittest.main()
