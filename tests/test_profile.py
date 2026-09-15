import tempfile
import unittest
from pathlib import Path

from nutritrack.profile import DEFAULT_GOALS, Profile


def full_profile(**kwargs) -> Profile:
    defaults = dict(
        name="Test",
        sex="male",
        age=28,
        height_cm=175.0,
        weight_kg=74.0,
        activity="moderate",
        weight_goal="maintain",
    )
    defaults.update(kwargs)
    return Profile(**defaults)


class DefaultsTests(unittest.TestCase):
    def test_fresh_profile_uses_default_goals(self):
        profile = Profile()
        self.assertEqual(profile.goals, DEFAULT_GOALS)
        self.assertEqual(profile.goals_source, "default")

    def test_goal_for_ignores_zero_and_missing(self):
        profile = Profile(goals={"kcal": 0.0})
        self.assertIsNone(profile.goal_for("kcal"))
        self.assertIsNone(profile.goal_for("protein_g"))

    def test_setting_an_unknown_nutrient_is_rejected(self):
        with self.assertRaises(ValueError):
            Profile().set_goals({"vitamin_q": 10.0})

    def test_manual_goals_are_marked_manual(self):
        profile = Profile()
        profile.set_goals({"kcal": 1800.0})
        self.assertEqual(profile.goals["kcal"], 1800.0)
        self.assertEqual(profile.goals_source, "manual")


class EnergyEstimateTests(unittest.TestCase):
    def test_bmr_matches_mifflin_st_jeor_for_men(self):
        # 10*74 + 6.25*175 - 5*28 + 5 = 1698.75
        self.assertAlmostEqual(full_profile().bmr(), 1698.75)

    def test_bmr_matches_mifflin_st_jeor_for_women(self):
        # 10*60 + 6.25*165 - 5*30 - 161 = 1320.25
        profile = full_profile(sex="female", age=30, height_cm=165.0, weight_kg=60.0)
        self.assertAlmostEqual(profile.bmr(), 1320.25)

    def test_bmr_needs_complete_body_stats(self):
        with self.assertRaises(ValueError):
            Profile(sex="male", age=28).bmr()

    def test_activity_multiplies_maintenance(self):
        profile = full_profile(activity="sedentary")
        self.assertAlmostEqual(profile.maintenance_kcal(), 1698.75 * 1.2)

    def test_missing_activity_defaults_to_moderate(self):
        profile = full_profile(activity=None)
        self.assertAlmostEqual(profile.maintenance_kcal(), 1698.75 * 1.55)


class DerivedGoalTests(unittest.TestCase):
    def test_cutting_targets_are_below_maintenance(self):
        profile = full_profile(weight_goal="lose")
        maintenance = profile.maintenance_kcal()
        goals = profile.recompute_goals()
        self.assertLess(goals["kcal"], maintenance)
        self.assertEqual(profile.goals_source, "derived")

    def test_bulking_targets_are_above_maintenance(self):
        profile = full_profile(weight_goal="gain")
        self.assertGreater(
            profile.recompute_goals()["kcal"], profile.maintenance_kcal()
        )

    def test_maintenance_targets_match_maintenance(self):
        profile = full_profile(weight_goal="maintain")
        goals = profile.recompute_goals()
        self.assertAlmostEqual(goals["kcal"], round(profile.maintenance_kcal()))

    def test_protein_scales_with_body_weight(self):
        goals = full_profile(weight_kg=80.0, weight_goal="maintain").recompute_goals()
        self.assertAlmostEqual(goals["protein_g"], 128.0)

    def test_cutting_raises_protein_per_kg(self):
        cutting = full_profile(weight_goal="lose").recompute_goals()["protein_g"]
        maintaining = full_profile(weight_goal="maintain").recompute_goals()[
            "protein_g"
        ]
        self.assertGreater(cutting, maintaining)

    def test_macro_targets_add_up_to_the_calorie_target(self):
        goals = full_profile().recompute_goals()
        macro_kcal = (
            goals["protein_g"] * 4.0 + goals["carb_g"] * 4.0 + goals["fat_g"] * 9.0
        )
        self.assertAlmostEqual(macro_kcal, goals["kcal"], delta=5.0)

    def test_every_nutrient_gets_a_derived_goal(self):
        goals = full_profile().recompute_goals()
        for key in DEFAULT_GOALS:
            self.assertIn(key, goals)
            self.assertGreater(goals[key], 0.0)

    def test_unknown_weight_goal_is_rejected(self):
        with self.assertRaises(ValueError):
            full_profile(weight_goal="bulk_like_crazy").recompute_goals()


class PersistenceTests(unittest.TestCase):
    def test_round_trip(self):
        profile = full_profile(weight_goal="lose")
        profile.recompute_goals()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.json"
            profile.save(path)
            reloaded = Profile.load(path)
        self.assertEqual(reloaded.name, "Test")
        self.assertEqual(reloaded.weight_kg, 74.0)
        self.assertEqual(reloaded.goals_source, "derived")
        self.assertAlmostEqual(reloaded.goals["kcal"], profile.goals["kcal"])

    def test_loading_a_missing_file_gives_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Profile.load(Path(tmp) / "absent.json")
        self.assertEqual(profile.goals, DEFAULT_GOALS)

    def test_partial_stored_goals_are_merged_over_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.json"
            path.write_text('{"version": 1, "goals": {"kcal": 1900}}')
            profile = Profile.load(path)
        self.assertEqual(profile.goals["kcal"], 1900.0)
        self.assertEqual(profile.goals["protein_g"], DEFAULT_GOALS["protein_g"])


if __name__ == "__main__":
    unittest.main()
