import json
import tempfile
import unittest
from pathlib import Path

from nutritrack.foods import (
    AmbiguousFood,
    Food,
    FoodDatabase,
    FoodNotFound,
    normalize,
    singularize,
)
from nutritrack.store import repo_root

BUNDLED = repo_root() / "data" / "foods.json"


def make_food(food_id: str, name: str, aliases=None, **per_100g) -> Food:
    values = {
        "kcal": 100.0,
        "protein_g": 5.0,
        "carb_g": 10.0,
        "fiber_g": 1.0,
        "sugar_g": 2.0,
        "fat_g": 3.0,
        "sat_fat_g": 1.0,
        "sodium_mg": 50.0,
        "potassium_mg": 100.0,
    }
    values.update(per_100g)
    return Food(
        id=food_id,
        name=name,
        category="test",
        per_100g=values,
        aliases=list(aliases or []),
    )


class NormalizationTests(unittest.TestCase):
    def test_normalize_strips_case_and_punctuation(self):
        self.assertEqual(normalize("  Dal / Tadka!! "), "dal tadka")

    def test_singularize_handles_common_plurals(self):
        self.assertEqual(singularize("eggs"), "egg")
        self.assertEqual(singularize("idlis"), "idli")
        self.assertEqual(singularize("berries"), "berry")
        self.assertEqual(singularize("rice"), "rice")


class LookupTests(unittest.TestCase):
    def setUp(self):
        self.db = FoodDatabase(
            [
                make_food("egg_boiled", "Egg, whole, boiled", ["egg", "anda"]),
                make_food("egg_white", "Egg white, cooked", ["egg white"]),
                make_food("roti", "Roti / chapati", ["chapati", "phulka"]),
            ]
        )

    def test_resolve_by_id(self):
        self.assertEqual(self.db.resolve("roti").id, "roti")

    def test_resolve_by_alias_is_case_insensitive(self):
        self.assertEqual(self.db.resolve("Chapati").id, "roti")

    def test_resolve_by_plural_alias(self):
        self.assertEqual(self.db.resolve("eggs").id, "egg_boiled")

    def test_exact_alias_beats_prefix_matches(self):
        # "egg" is an exact alias of egg_boiled even though egg_white also starts
        # with "egg", so the lookup must not be considered ambiguous.
        self.assertEqual(self.db.resolve("egg").id, "egg_boiled")

    def test_full_alias_disambiguates_a_shared_prefix(self):
        self.assertEqual(self.db.resolve("egg white").id, "egg_white")

    def test_ambiguous_query_raises_with_all_matches(self):
        with self.assertRaises(AmbiguousFood) as ctx:
            self.db.resolve("eg")
        self.assertEqual(
            {food.id for food in ctx.exception.matches},
            {"egg_boiled", "egg_white"},
        )

    def test_unknown_food_raises_with_suggestions(self):
        with self.assertRaises(FoodNotFound) as ctx:
            self.db.resolve("rotti")
        self.assertIn("Roti / chapati", ctx.exception.suggestions)

    def test_duplicate_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            FoodDatabase([make_food("x", "X"), make_food("x", "Y")])


class AmbiguityTests(unittest.TestCase):
    def test_substring_match_across_two_foods_is_ambiguous(self):
        db = FoodDatabase(
            [
                make_food("dal_plain", "Dal, plain", ["dal"]),
                make_food("dal_tadka", "Dal tadka", ["dal fry"]),
            ]
        )
        # "dal" is an exact alias of dal_plain, so it resolves.
        self.assertEqual(db.resolve("dal").id, "dal_plain")
        # "dal t" only prefixes dal_tadka, so it is still unambiguous.
        self.assertEqual(db.resolve("dal t").id, "dal_tadka")
        with self.assertRaises(AmbiguousFood):
            db.resolve("da")


class PortionMathTests(unittest.TestCase):
    def test_nutrients_for_scales_from_100g(self):
        food = make_food("rice", "Rice", kcal=130.0, protein_g=2.7)
        values = food.nutrients_for(150.0)
        self.assertAlmostEqual(values["kcal"], 195.0)
        self.assertAlmostEqual(values["protein_g"], 4.05)


class SerializationTests(unittest.TestCase):
    def test_missing_nutrient_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            Food.from_dict({"id": "x", "name": "X", "per_100g": {"kcal": 10}})
        self.assertIn("missing nutrients", str(ctx.exception))

    def test_round_trip_through_dict(self):
        food = make_food("oats", "Oats", ["rolled oats"])
        restored = Food.from_dict(food.to_dict())
        self.assertEqual(restored, food)

    def test_save_and_reload(self):
        db = FoodDatabase([make_food("a", "A"), make_food("b", "B")])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "foods.json"
            db.save(path)
            reloaded = FoodDatabase.load(path)
        self.assertEqual(len(reloaded), 2)
        self.assertIsNotNone(reloaded.get("a"))


class BundledDatabaseTests(unittest.TestCase):
    """The shipped database is data, so guard it like data."""

    @classmethod
    def setUpClass(cls):
        cls.db = FoodDatabase.load(BUNDLED)
        cls.raw = json.loads(BUNDLED.read_text(encoding="utf-8"))

    def test_database_is_not_trivially_small(self):
        self.assertGreaterEqual(len(self.db), 90)

    def test_every_food_loads_with_all_nutrients(self):
        for food in self.db.sorted_foods():
            self.assertEqual(len(food.per_100g), 9, food.id)

    def test_macro_calories_roughly_match_stated_calories(self):
        """4/4/9 kcal from macros should land near the listed calorie value."""
        # Alcohol carries ~7 kcal/g and is not one of the tracked macros, so
        # alcoholic entries legitimately state more calories than 4/4/9 predicts.
        alcoholic = {"beer"}
        for food in self.db.sorted_foods():
            if food.id in alcoholic:
                continue
            per = food.per_100g
            computed = (
                per["protein_g"] * 4.0 + per["carb_g"] * 4.0 + per["fat_g"] * 9.0
            )
            stated = per["kcal"]
            if stated < 20:
                continue
            # Fiber, alcohol, rounding and recipe variation all loosen this, so the
            # check only catches genuinely wrong rows.
            self.assertLess(
                abs(computed - stated) / stated,
                0.30,
                f"{food.id}: stated {stated} kcal vs {computed:.0f} kcal from macros",
            )

    def test_component_grams_never_exceed_100(self):
        for food in self.db.sorted_foods():
            per = food.per_100g
            mass = per["protein_g"] + per["carb_g"] + per["fat_g"]
            self.assertLessEqual(mass, 100.5, food.id)

    def test_sugar_never_exceeds_carbs_and_sat_fat_never_exceeds_fat(self):
        for food in self.db.sorted_foods():
            per = food.per_100g
            self.assertLessEqual(per["sugar_g"], per["carb_g"] + 0.01, food.id)
            self.assertLessEqual(per["sat_fat_g"], per["fat_g"] + 0.01, food.id)

    def test_no_negative_values(self):
        for food in self.db.sorted_foods():
            for key, value in food.per_100g.items():
                self.assertGreaterEqual(value, 0.0, f"{food.id}.{key}")

    def test_search_terms_are_not_shared_between_foods(self):
        """Two foods sharing a name or alias would make that term unloggable."""
        seen: dict[str, str] = {}
        for food in self.db.sorted_foods():
            for term in {normalize(item) for item in [food.name, *food.aliases]}:
                self.assertEqual(
                    seen.setdefault(term, food.id),
                    food.id,
                    f"{term!r} is claimed by both {seen[term]} and {food.id}",
                )

    def test_common_queries_resolve_to_a_single_food(self):
        for query in [
            "roti",
            "rice",
            "dal",
            "paneer",
            "chicken breast",
            "egg",
            "banana",
            "curd",
            "chai",
            "almonds",
            "oats",
            "idli",
        ]:
            with self.subTest(query=query):
                self.assertIsNotNone(self.db.resolve(query))


if __name__ == "__main__":
    unittest.main()
