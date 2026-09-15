"""The food database: per-100 g nutrition facts plus lookup by name or alias."""

from __future__ import annotations

import difflib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from . import nutrients

_PUNCTUATION = re.compile(r"[^a-z0-9\s]+")
_WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lowercase, drop punctuation and collapse whitespace so lookups are forgiving."""
    lowered = _PUNCTUATION.sub(" ", text.strip().lower())
    return _WHITESPACE.sub(" ", lowered).strip()


def singularize(term: str) -> str:
    """Crude singular form so "2 eggs" matches the "egg" entry."""
    words = normalize(term).split()
    out = []
    for word in words:
        if len(word) > 3 and word.endswith("ies"):
            out.append(word[:-3] + "y")
        elif len(word) > 3 and word.endswith("es") and not word.endswith("ses"):
            out.append(word[:-2])
        elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            out.append(word[:-1])
        else:
            out.append(word)
    return " ".join(out)


class FoodNotFound(LookupError):
    """Raised when a query matches no food. Carries near-miss suggestions."""

    def __init__(self, query: str, suggestions: Sequence[str]):
        self.query = query
        self.suggestions = list(suggestions)
        message = f"no food matches {query!r}"
        if self.suggestions:
            message += " (did you mean: " + ", ".join(self.suggestions) + "?)"
        super().__init__(message)


class AmbiguousFood(LookupError):
    """Raised when a query matches several foods and the caller must disambiguate."""

    def __init__(self, query: str, matches: Sequence[Food]):
        self.query = query
        self.matches = list(matches)
        names = ", ".join(f"{food.id} ({food.name})" for food in self.matches)
        super().__init__(f"{query!r} matches several foods: {names}")


@dataclass(frozen=True)
class Food:
    id: str
    name: str
    category: str
    per_100g: dict[str, float]
    aliases: list[str] = field(default_factory=list)
    typical_grams: float | None = None
    typical_label: str | None = None

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> Food:
        per_100g = raw.get("per_100g") or {}
        if not isinstance(per_100g, Mapping):
            raise TypeError(
                f"food {raw.get('id')!r} has a malformed per_100g block"
            )
        missing = [key for key in nutrients.NUTRIENT_KEYS if key not in per_100g]
        if missing:
            raise ValueError(
                f"food {raw.get('id')!r} is missing nutrients: {', '.join(missing)}"
            )
        return cls(
            id=str(raw["id"]),
            name=str(raw["name"]),
            category=str(raw.get("category", "other")),
            per_100g={key: float(per_100g[key]) for key in nutrients.NUTRIENT_KEYS},
            aliases=[str(alias) for alias in raw.get("aliases", [])],
            typical_grams=(
                float(raw["typical_grams"]) if raw.get("typical_grams") else None
            ),
            typical_label=(
                str(raw["typical_label"]) if raw.get("typical_label") else None
            ),
        )

    def to_dict(self) -> dict[str, object]:
        out: dict[str, object] = {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "aliases": list(self.aliases),
        }
        if self.typical_grams:
            out["typical_grams"] = self.typical_grams
        if self.typical_label:
            out["typical_label"] = self.typical_label
        out["per_100g"] = dict(self.per_100g)
        return out

    def nutrients_for(self, grams: float) -> dict[str, float]:
        return nutrients.scale(self.per_100g, grams)

    @property
    def search_terms(self) -> list[str]:
        return [self.name, *self.aliases, self.id.replace("_", " ")]


class FoodDatabase:
    def __init__(self, foods: Sequence[Food], path: Path | None = None):
        self.path = path
        self._foods: dict[str, Food] = {}
        for food in foods:
            if food.id in self._foods:
                raise ValueError(f"duplicate food id {food.id!r}")
            self._foods[food.id] = food

    @classmethod
    def load(cls, path: Path) -> FoodDatabase:
        raw = json.loads(path.read_text(encoding="utf-8"))
        foods = [Food.from_dict(item) for item in raw.get("foods", [])]
        return cls(foods, path=path)

    def save(self, path: Path | None = None) -> Path:
        target = path or self.path
        if target is None:
            raise ValueError("no path to save the food database to")
        payload = {
            "version": 1,
            "basis_grams": 100,
            "foods": [food.to_dict() for food in self.sorted_foods()],
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return target

    def __len__(self) -> int:
        return len(self._foods)

    def __contains__(self, food_id: object) -> bool:
        return food_id in self._foods

    def sorted_foods(self) -> list[Food]:
        return sorted(self._foods.values(), key=lambda food: (food.category, food.name))

    def get(self, food_id: str) -> Food | None:
        return self._foods.get(food_id)

    def add(self, food: Food, overwrite: bool = False) -> Food:
        if food.id in self._foods and not overwrite:
            raise ValueError(f"food {food.id!r} already exists")
        self._foods[food.id] = food
        return food

    def candidates(self, query: str) -> list[Food]:
        """Foods matching `query`, best tier first. Empty when nothing is close."""
        wanted = normalize(query)
        if not wanted:
            return []
        if wanted.replace(" ", "_") in self._foods:
            return [self._foods[wanted.replace(" ", "_")]]

        singular = singularize(wanted)
        exact: list[Food] = []
        prefix: list[Food] = []
        substring: list[Food] = []
        for food in self.sorted_foods():
            terms = [normalize(term) for term in food.search_terms]
            singular_terms = [singularize(term) for term in terms]
            if wanted in terms or singular in singular_terms:
                exact.append(food)
            elif any(term.startswith((wanted, singular)) for term in terms):
                prefix.append(food)
            elif any(wanted in term or singular in term for term in terms):
                substring.append(food)
        return exact or prefix or substring

    def suggestions(self, query: str, limit: int = 5) -> list[str]:
        terms: dict[str, str] = {}
        for food in self._foods.values():
            for term in food.search_terms:
                terms.setdefault(normalize(term), food.name)
        close = difflib.get_close_matches(
            normalize(query), list(terms), n=limit, cutoff=0.6
        )
        seen: list[str] = []
        for term in close:
            name = terms[term]
            if name not in seen:
                seen.append(name)
        return seen

    def resolve(self, query: str) -> Food:
        """Resolve a single food, raising on no match or an ambiguous match."""
        matches = self.candidates(query)
        if not matches:
            raise FoodNotFound(query, self.suggestions(query))
        if len(matches) > 1:
            raise AmbiguousFood(query, matches)
        return matches[0]

    def search(self, query: str, limit: int | None = None) -> list[Food]:
        matches = self.candidates(query) if query else self.sorted_foods()
        if not matches and query:
            wanted = normalize(query)
            matches = [
                food
                for food in self.sorted_foods()
                if difflib.SequenceMatcher(None, wanted, normalize(food.name)).ratio()
                >= 0.6
            ]
        return matches[:limit] if limit else matches

    def categories(self) -> list[str]:
        return sorted({food.category for food in self._foods.values()})
