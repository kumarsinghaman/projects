import unittest

from nutritrack import nutrients


class ScalingTests(unittest.TestCase):
    def test_scale_is_linear_in_grams(self):
        per_100g = dict.fromkeys(nutrients.NUTRIENT_KEYS, 10.0)
        self.assertEqual(nutrients.scale(per_100g, 100.0)["kcal"], 10.0)
        self.assertEqual(nutrients.scale(per_100g, 250.0)["kcal"], 25.0)
        self.assertEqual(nutrients.scale(per_100g, 0.0)["kcal"], 0.0)

    def test_scale_fills_every_known_nutrient(self):
        scaled = nutrients.scale({"kcal": 100.0}, 50.0)
        self.assertEqual(set(scaled), set(nutrients.NUTRIENT_KEYS))
        self.assertEqual(scaled["kcal"], 50.0)
        self.assertEqual(scaled["protein_g"], 0.0)

    def test_total_sums_vectors(self):
        a = nutrients.scale({"kcal": 100.0, "protein_g": 10.0}, 100.0)
        b = nutrients.scale({"kcal": 200.0, "protein_g": 5.0}, 100.0)
        combined = nutrients.total([a, b])
        self.assertEqual(combined["kcal"], 300.0)
        self.assertEqual(combined["protein_g"], 15.0)

    def test_total_of_nothing_is_zero(self):
        self.assertEqual(nutrients.total([]), nutrients.zeros())


class MacroSplitTests(unittest.TestCase):
    def test_macro_energy_uses_four_four_nine(self):
        energy = nutrients.macro_energy(
            {"protein_g": 10.0, "carb_g": 20.0, "fat_g": 5.0}
        )
        self.assertEqual(energy["protein_g"], 40.0)
        self.assertEqual(energy["carb_g"], 80.0)
        self.assertEqual(energy["fat_g"], 45.0)

    def test_macro_split_percentages_sum_to_100(self):
        split = nutrients.macro_split(
            {"protein_g": 10.0, "carb_g": 20.0, "fat_g": 5.0}
        )
        self.assertAlmostEqual(sum(split.values()), 100.0)
        self.assertAlmostEqual(split["carb_g"], 80.0 / 165.0 * 100.0)

    def test_macro_split_of_empty_day_is_zero(self):
        split = nutrients.macro_split(nutrients.zeros())
        self.assertEqual(set(split.values()), {0.0})


class FormattingTests(unittest.TestCase):
    def test_calories_and_sodium_are_whole_numbers(self):
        self.assertEqual(nutrients.format_amount("kcal", 1842.4), "1842")
        self.assertEqual(nutrients.format_with_unit("sodium_mg", 2301.7), "2302 mg")

    def test_grams_keep_one_decimal(self):
        self.assertEqual(nutrients.format_with_unit("protein_g", 31.25), "31.2 g")


if __name__ == "__main__":
    unittest.main()
