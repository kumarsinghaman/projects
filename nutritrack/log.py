"""The meal log: append-only-ish JSON store of everything that was eaten."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date as date_cls
from pathlib import Path

from . import nutrients
from .foods import FoodDatabase, normalize

# Display order for meals; anything else is appended alphabetically after these.
MEAL_ORDER: tuple[str, ...] = (
    "breakfast",
    "morning snack",
    "lunch",
    "snack",
    "evening snack",
    "dinner",
    "late snack",
)

MEAL_ALIASES: dict[str, str] = {
    "b": "breakfast",
    "brunch": "breakfast",
    "l": "lunch",
    "d": "dinner",
    "s": "snack",
    "supper": "dinner",
    "tea": "evening snack",
    "pre workout": "morning snack",
    "post workout": "snack",
}


def canonical_meal(name: str) -> str:
    cleaned = normalize(name)
    if not cleaned:
        raise ValueError("meal name cannot be empty")
    return MEAL_ALIASES.get(cleaned, cleaned)


def meal_sort_key(meal: str) -> tuple[int, str]:
    try:
        return (MEAL_ORDER.index(meal), meal)
    except ValueError:
        return (len(MEAL_ORDER), meal)


@dataclass
class LoggedItem:
    id: str
    date: str
    meal: str
    grams: float
    food_name: str
    food_id: str | None = None
    time: str | None = None
    photo: str | None = None
    note: str | None = None
    # Per-100 g values for one-off foods that are not in the database.
    per_100g: dict[str, float] | None = None

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> LoggedItem:
        per_100g = raw.get("per_100g")
        return cls(
            id=str(raw["id"]),
            date=str(raw["date"]),
            meal=str(raw["meal"]),
            grams=float(raw["grams"]),
            food_name=str(raw["food_name"]),
            food_id=(str(raw["food_id"]) if raw.get("food_id") else None),
            time=(str(raw["time"]) if raw.get("time") else None),
            photo=(str(raw["photo"]) if raw.get("photo") else None),
            note=(str(raw["note"]) if raw.get("note") else None),
            per_100g=(
                {key: float(per_100g.get(key, 0.0)) for key in nutrients.NUTRIENT_KEYS}
                if isinstance(per_100g, Mapping)
                else None
            ),
        )

    def to_dict(self) -> dict[str, object]:
        out: dict[str, object] = {
            "id": self.id,
            "date": self.date,
            "meal": self.meal,
            "food_name": self.food_name,
            "grams": round(self.grams, 2),
        }
        if self.food_id:
            out["food_id"] = self.food_id
        if self.time:
            out["time"] = self.time
        if self.photo:
            out["photo"] = self.photo
        if self.note:
            out["note"] = self.note
        if self.per_100g:
            out["per_100g"] = self.per_100g
        return out

    def per_100g_values(self, db: FoodDatabase) -> dict[str, float]:
        """Resolve nutrition facts, preferring the database so corrections propagate."""
        if self.food_id:
            food = db.get(self.food_id)
            if food is not None:
                return food.per_100g
        if self.per_100g:
            return self.per_100g
        raise KeyError(
            f"entry {self.id} references unknown food {self.food_id!r} and carries "
            "no inline nutrition values"
        )

    def nutrients(self, db: FoodDatabase) -> dict[str, float]:
        return nutrients.scale(self.per_100g_values(db), self.grams)


@dataclass
class MealLog:
    path: Path | None = None
    items: list[LoggedItem] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> MealLog:
        if not path.exists():
            return cls(path=path, items=[])
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = [LoggedItem.from_dict(item) for item in raw.get("items", [])]
        return cls(path=path, items=items)

    def save(self, path: Path | None = None) -> Path:
        target = path or self.path
        if target is None:
            raise ValueError("no path to save the meal log to")
        payload = {
            "version": 1,
            "items": [item.to_dict() for item in self.sorted_items()],
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return target

    def sorted_items(self) -> list[LoggedItem]:
        return sorted(
            self.items,
            key=lambda item: (
                item.date,
                meal_sort_key(item.meal),
                item.time or "",
                item.id,
            ),
        )

    def next_id(self, day: str) -> str:
        compact = day.replace("-", "")
        used = {item.id for item in self.items}
        index = 1
        while f"{compact}-{index:03d}" in used:
            index += 1
        return f"{compact}-{index:03d}"

    def add(self, item: LoggedItem) -> LoggedItem:
        if any(existing.id == item.id for existing in self.items):
            raise ValueError(f"entry id {item.id!r} already used")
        self.items.append(item)
        return item

    def remove(self, entry_id: str) -> LoggedItem:
        for index, item in enumerate(self.items):
            if item.id == entry_id:
                return self.items.pop(index)
        raise KeyError(f"no log entry with id {entry_id!r}")

    def get(self, entry_id: str) -> LoggedItem | None:
        for item in self.items:
            if item.id == entry_id:
                return item
        return None

    def for_date(self, day: str) -> list[LoggedItem]:
        return [item for item in self.sorted_items() if item.date == day]

    def between(self, start: str, end: str) -> list[LoggedItem]:
        return [item for item in self.sorted_items() if start <= item.date <= end]

    def dates(self) -> list[str]:
        return sorted({item.date for item in self.items})

    def last_date(self) -> str | None:
        dates = self.dates()
        return dates[-1] if dates else None


def parse_date(value: str | None, today: date_cls | None = None) -> str:
    """Accept an ISO date, `today`, `yesterday`, or a negative day offset."""
    reference = today or date_cls.today()
    if value is None:
        return reference.isoformat()
    cleaned = value.strip().lower()
    if cleaned in ("today", "t", ""):
        return reference.isoformat()
    if cleaned in ("yesterday", "y"):
        return (reference.fromordinal(reference.toordinal() - 1)).isoformat()
    if cleaned.startswith("-") and cleaned[1:].isdigit():
        offset = int(cleaned[1:])
        return (reference.fromordinal(reference.toordinal() - offset)).isoformat()
    return date_cls.fromisoformat(cleaned).isoformat()


def parse_items_spec(spec: str) -> list[tuple[str, float]]:
    """Parse "idli:160, sambar:120" into [(name, grams), ...]."""
    parsed: list[tuple[str, float]] = []
    for chunk in spec.split(","):
        piece = chunk.strip()
        if not piece:
            continue
        if ":" not in piece:
            raise ValueError(
                f"item {piece!r} must be written as 'name:grams', e.g. 'roti:80'"
            )
        name, _, grams_text = piece.rpartition(":")
        name = name.strip()
        grams_text = grams_text.strip().rstrip("g").strip()
        if not name:
            raise ValueError(f"item {piece!r} is missing a food name")
        try:
            grams = float(grams_text)
        except ValueError as exc:
            raise ValueError(f"item {piece!r} has a non-numeric gram amount") from exc
        if grams <= 0:
            raise ValueError(f"item {piece!r} must have a positive gram amount")
        parsed.append((name, grams))
    if not parsed:
        raise ValueError("no items found in the item specification")
    return parsed


def group_by_meal(items: Sequence[LoggedItem]) -> list[tuple[str, list[LoggedItem]]]:
    grouped: dict[str, list[LoggedItem]] = {}
    for item in items:
        grouped.setdefault(item.meal, []).append(item)
    return [
        (meal, grouped[meal]) for meal in sorted(grouped, key=meal_sort_key)
    ]
