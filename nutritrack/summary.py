"""Roll logged items up into per-meal, per-day and multi-day summaries."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date as date_cls
from datetime import timedelta

from . import nutrients
from .foods import FoodDatabase
from .log import LoggedItem, MealLog, group_by_meal
from .profile import Profile


@dataclass(frozen=True)
class ItemLine:
    item: LoggedItem
    values: dict[str, float]

    @property
    def kcal(self) -> float:
        return self.values["kcal"]


@dataclass(frozen=True)
class MealSummary:
    meal: str
    lines: list[ItemLine]
    totals: dict[str, float]

    @property
    def grams(self) -> float:
        return sum(line.item.grams for line in self.lines)

    @property
    def photos(self) -> list[str]:
        seen: list[str] = []
        for line in self.lines:
            if line.item.photo and line.item.photo not in seen:
                seen.append(line.item.photo)
        return seen


@dataclass(frozen=True)
class GoalProgress:
    key: str
    value: float
    goal: float | None
    is_limit: bool
    exceed_ok: bool = False

    @property
    def percent(self) -> float | None:
        if not self.goal:
            return None
        return self.value / self.goal * 100.0

    @property
    def remaining(self) -> float | None:
        if not self.goal:
            return None
        return self.goal - self.value

    @property
    def status(self) -> str:
        """`on-track`, `under`, `met` or `over` relative to the daily target."""
        percent = self.percent
        if percent is None:
            return "no-goal"
        if self.is_limit:
            return "over" if percent > 100.0 else "on-track"
        if percent >= 90.0:
            return "met" if self.exceed_ok or percent <= 110.0 else "over"
        return "under"


@dataclass(frozen=True)
class DaySummary:
    date: str
    meals: list[MealSummary]
    totals: dict[str, float]
    goals: dict[str, float] = field(default_factory=dict)

    @property
    def item_count(self) -> int:
        return sum(len(meal.lines) for meal in self.meals)

    @property
    def is_empty(self) -> bool:
        return self.item_count == 0

    @property
    def macro_split(self) -> dict[str, float]:
        return nutrients.macro_split(self.totals)

    @property
    def macro_energy(self) -> dict[str, float]:
        return nutrients.macro_energy(self.totals)

    def progress(self) -> list[GoalProgress]:
        out: list[GoalProgress] = []
        for nutrient in nutrients.NUTRIENTS:
            goal = self.goals.get(nutrient.key)
            out.append(
                GoalProgress(
                    key=nutrient.key,
                    value=self.totals.get(nutrient.key, 0.0),
                    goal=goal if goal and goal > 0 else None,
                    is_limit=nutrient.is_limit,
                    exceed_ok=nutrient.exceed_ok,
                )
            )
        return out

    def progress_for(self, key: str) -> GoalProgress:
        for entry in self.progress():
            if entry.key == key:
                return entry
        raise KeyError(key)

    @property
    def photos(self) -> list[str]:
        seen: list[str] = []
        for meal in self.meals:
            for photo in meal.photos:
                if photo not in seen:
                    seen.append(photo)
        return seen


@dataclass(frozen=True)
class RangeSummary:
    start: str
    end: str
    days: list[DaySummary]
    goals: dict[str, float] = field(default_factory=dict)

    @property
    def logged_days(self) -> list[DaySummary]:
        return [day for day in self.days if not day.is_empty]

    @property
    def totals(self) -> dict[str, float]:
        return nutrients.total([day.totals for day in self.days])

    def averages(self) -> dict[str, float]:
        """Averages over days that actually have entries."""
        logged = self.logged_days
        if not logged:
            return nutrients.zeros()
        totals = nutrients.total([day.totals for day in logged])
        return {key: value / len(logged) for key, value in totals.items()}

    def average_progress(self) -> list[GoalProgress]:
        averages = self.averages()
        out: list[GoalProgress] = []
        for nutrient in nutrients.NUTRIENTS:
            goal = self.goals.get(nutrient.key)
            out.append(
                GoalProgress(
                    key=nutrient.key,
                    value=averages.get(nutrient.key, 0.0),
                    goal=goal if goal and goal > 0 else None,
                    is_limit=nutrient.is_limit,
                    exceed_ok=nutrient.exceed_ok,
                )
            )
        return out


def summarize_items(items: Sequence[LoggedItem], db: FoodDatabase) -> list[MealSummary]:
    meals: list[MealSummary] = []
    for meal, meal_items in group_by_meal(items):
        lines = [ItemLine(item=item, values=item.nutrients(db)) for item in meal_items]
        meals.append(
            MealSummary(
                meal=meal,
                lines=lines,
                totals=nutrients.total([line.values for line in lines]),
            )
        )
    return meals


def summarize_day(
    log: MealLog,
    db: FoodDatabase,
    day: str,
    profile: Profile | None = None,
) -> DaySummary:
    meals = summarize_items(log.for_date(day), db)
    return DaySummary(
        date=day,
        meals=meals,
        totals=nutrients.total([meal.totals for meal in meals]),
        goals=dict(profile.goals) if profile else {},
    )


def date_range(start: str, end: str) -> list[str]:
    first = date_cls.fromisoformat(start)
    last = date_cls.fromisoformat(end)
    if last < first:
        raise ValueError(f"end date {end} is before start date {start}")
    days: list[str] = []
    cursor = first
    while cursor <= last:
        days.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return days


def summarize_range(
    log: MealLog,
    db: FoodDatabase,
    start: str,
    end: str,
    profile: Profile | None = None,
) -> RangeSummary:
    days = [summarize_day(log, db, day, profile) for day in date_range(start, end)]
    return RangeSummary(
        start=start,
        end=end,
        days=days,
        goals=dict(profile.goals) if profile else {},
    )


def top_contributors(
    day: DaySummary, key: str = "kcal", limit: int = 5
) -> list[ItemLine]:
    lines = [line for meal in day.meals for line in meal.lines]
    lines.sort(key=lambda line: line.values.get(key, 0.0), reverse=True)
    return lines[:limit]
