"""Plain-text rendering of days, ranges and food lookups for the terminal."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date as date_cls

from . import nutrients
from .foods import Food
from .summary import DaySummary, GoalProgress, ItemLine, MealSummary, RangeSummary

WIDTH = 78


def pretty_date(day: str) -> str:
    return date_cls.fromisoformat(day).strftime("%a %d %b %Y")


def bar(percent: float | None, width: int = 20) -> str:
    if percent is None:
        return " " * width
    filled = round(min(max(percent, 0.0), 100.0) / 100.0 * width)
    overflow = percent > 100.5
    body = "#" * filled + "." * (width - filled)
    if overflow:
        body = "#" * width
    return body


def rule(char: str = "=") -> str:
    return char * WIDTH


def clip(text: str, width: int = 34) -> str:
    return text if len(text) <= width else text[: width - 1] + "\u2026"


def _item_row(line: ItemLine) -> str:
    values = line.values
    name = line.item.food_name
    if line.item.note:
        name = f"{name} ({line.item.note})"
    name = clip(name)
    return (
        f"  {name:<34}{line.item.grams:>6.0f}g{values['kcal']:>8.0f}"
        f"{values['protein_g']:>7.1f}{values['carb_g']:>7.1f}{values['fat_g']:>7.1f}"
    )


def _columns_header() -> str:
    return (
        f"  {'ITEM':<34}{'GRAMS':>7}{'KCAL':>8}"
        f"{'PROT':>7}{'CARB':>7}{'FAT':>7}"
    )


def _meal_total_row(meal: MealSummary) -> str:
    totals = meal.totals
    return (
        f"  {'meal total':<34}{meal.grams:>6.0f}g{totals['kcal']:>8.0f}"
        f"{totals['protein_g']:>7.1f}{totals['carb_g']:>7.1f}{totals['fat_g']:>7.1f}"
    )


def render_meal(meal: MealSummary) -> list[str]:
    lines = [f"{meal.meal.upper()}"]
    lines.append(_columns_header())
    for line in meal.lines:
        lines.append(_item_row(line))
    lines.append("  " + "-" * (WIDTH - 4))
    lines.append(_meal_total_row(meal))
    for photo in meal.photos:
        lines.append(f"  photo: {photo}")
    return lines


def render_progress(entries: Iterable[GoalProgress]) -> list[str]:
    rows: list[str] = []
    for entry in entries:
        nutrient = nutrients.BY_KEY[entry.key]
        value = nutrients.format_amount(entry.key, entry.value)
        if entry.goal is None:
            rows.append(
                f"  {nutrient.label:<15}{value:>7} {nutrient.unit:<5}"
                f"{'':<24}  no goal set"
            )
            continue
        goal = nutrients.format_amount(entry.key, entry.goal)
        percent = entry.percent or 0.0
        remaining = entry.remaining or 0.0
        if entry.is_limit:
            note = (
                f"over by {nutrients.format_amount(entry.key, -remaining)}"
                if remaining < 0
                else f"{nutrients.format_amount(entry.key, remaining)} headroom"
            )
        elif remaining > 0:
            note = f"{nutrients.format_amount(entry.key, remaining)} to go"
        elif nutrient.exceed_ok:
            note = f"target met (+{nutrients.format_amount(entry.key, -remaining)})"
        else:
            note = f"over by {nutrients.format_amount(entry.key, -remaining)}"
        rows.append(
            f"  {nutrient.label:<15}{value:>7} / {goal:<7} {nutrient.unit:<5}"
            f"[{bar(percent)}] {percent:>4.0f}%  {note}"
        )
    return rows


def render_macro_split(day: DaySummary) -> list[str]:
    split = day.macro_split
    energy = day.macro_energy
    if day.totals["kcal"] <= 0:
        return []
    parts = []
    for key in nutrients.MACRO_KEYS:
        label = nutrients.BY_KEY[key].label
        parts.append(f"{label} {split[key]:.0f}% ({energy[key]:.0f} kcal)")
    return ["  energy from macros: " + "  |  ".join(parts)]


def render_day(day: DaySummary, show_items: bool = True) -> str:
    out: list[str] = [rule("=")]
    headline = (
        f" {pretty_date(day.date)}   {day.totals['kcal']:.0f} kcal"
        f"   {len(day.meals)} meals   {day.item_count} items"
    )
    out.append(headline)
    out.append(rule("="))
    if day.is_empty:
        out.append("")
        out.append("  Nothing logged for this day yet.")
        out.append("")
        return "\n".join(out)

    if show_items:
        for meal in day.meals:
            out.append("")
            out.extend(render_meal(meal))

    out.append("")
    out.append(rule("-"))
    out.append(" DAY TOTALS vs DAILY GOALS")
    out.append(rule("-"))
    out.extend(render_progress(day.progress()))
    out.extend(render_macro_split(day))
    out.append("")
    return "\n".join(out)


def render_range(summary: RangeSummary, goal_key: str = "kcal") -> str:
    out: list[str] = [rule("=")]
    out.append(
        f" {pretty_date(summary.start)}  ->  {pretty_date(summary.end)}"
        f"   ({len(summary.logged_days)} of {len(summary.days)} days logged)"
    )
    out.append(rule("="))
    out.append("")
    goal = summary.goals.get(goal_key)
    nutrient = nutrients.BY_KEY[goal_key]
    out.append(
        f"  {'DATE':<16}{nutrient.label.upper():>8}{'PROT':>8}{'CARB':>8}"
        f"{'FAT':>8}{'FIBER':>8}   TREND"
    )
    peak = max(
        [day.totals[goal_key] for day in summary.days] + [goal or 0.0], default=0.0
    )
    for day in summary.days:
        totals = day.totals
        if day.is_empty:
            out.append(
                f"  {pretty_date(day.date)[:16]:<16}{'-':>8}{'':>32}   (no entries)"
            )
            continue
        share = (totals[goal_key] / peak * 100.0) if peak else 0.0
        out.append(
            f"  {pretty_date(day.date)[:16]:<16}"
            f"{totals[goal_key]:>8.0f}{totals['protein_g']:>8.1f}"
            f"{totals['carb_g']:>8.1f}{totals['fat_g']:>8.1f}"
            f"{totals['fiber_g']:>8.1f}   {bar(share, 12)}"
        )
    out.append("")
    out.append(rule("-"))
    out.append(" DAILY AVERAGE (logged days only) vs GOALS")
    out.append(rule("-"))
    out.extend(render_progress(summary.average_progress()))
    out.append("")
    return "\n".join(out)


def render_top_contributors(lines: Sequence[ItemLine], key: str = "kcal") -> str:
    nutrient = nutrients.BY_KEY[key]
    out = [f" BIGGEST CONTRIBUTORS BY {nutrient.label.upper()}", rule("-")]
    for line in lines:
        amount = nutrients.format_amount(key, line.values[key])
        out.append(
            f"  {clip(line.item.food_name):<34}{line.item.grams:>6.0f}g"
            f"{amount:>8} {nutrient.unit:<5}({line.item.meal})"
        )
    out.append("")
    return "\n".join(out)


def render_foods(foods: Sequence[Food], query: str = "") -> str:
    if not foods:
        return f"No foods match {query!r}."
    out: list[str] = []
    header = f"{len(foods)} food(s)"
    if query:
        header += f" matching {query!r}"
    out.append(header + "  (values per 100 g)")
    out.append(rule("-"))
    out.append(
        f"  {'ID':<24}{'KCAL':>6}{'PROT':>7}{'CARB':>7}{'FAT':>7}{'FIBER':>7}   NAME"
    )
    for food in foods:
        per = food.per_100g
        out.append(
            f"  {food.id:<24}{per['kcal']:>6.0f}{per['protein_g']:>7.1f}"
            f"{per['carb_g']:>7.1f}{per['fat_g']:>7.1f}{per['fiber_g']:>7.1f}"
            f"   {food.name}"
        )
    return "\n".join(out)


def render_food_detail(food: Food) -> str:
    out = [rule("="), f" {food.name}  [{food.id}]", rule("=")]
    out.append(f"  category: {food.category}")
    if food.aliases:
        out.append(f"  aliases : {', '.join(food.aliases)}")
    if food.typical_grams:
        label = food.typical_label or "typical portion"
        out.append(f"  typical : {food.typical_grams:.0f} g ({label})")
    out.append("")
    out.append("  per 100 g:")
    for nutrient in nutrients.NUTRIENTS:
        value = nutrients.format_amount(nutrient.key, food.per_100g[nutrient.key])
        out.append(f"    {nutrient.label:<16}{value:>8} {nutrient.unit}")
    if food.typical_grams:
        out.append("")
        out.append(f"  per typical portion ({food.typical_grams:.0f} g):")
        portion = food.nutrients_for(food.typical_grams)
        for nutrient in nutrients.NUTRIENTS:
            value = nutrients.format_amount(nutrient.key, portion[nutrient.key])
            out.append(f"    {nutrient.label:<16}{value:>8} {nutrient.unit}")
    return "\n".join(out)


def render_log_confirmation(
    day: DaySummary, meal: str, added: Sequence[ItemLine]
) -> str:
    out: list[str] = [f"Logged {len(added)} item(s) to {meal} on {day.date}:"]
    for line in added:
        out.append(
            f"  + {line.item.food_name} {line.item.grams:.0f} g"
            f"  ->  {line.values['kcal']:.0f} kcal,"
            f" P {line.values['protein_g']:.1f} g,"
            f" C {line.values['carb_g']:.1f} g,"
            f" F {line.values['fat_g']:.1f} g"
            f"   [{line.item.id}]"
        )
    meal_summary = next((m for m in day.meals if m.meal == meal), None)
    if meal_summary:
        out.append(
            f"  {meal} total: {meal_summary.totals['kcal']:.0f} kcal,"
            f" P {meal_summary.totals['protein_g']:.1f} g,"
            f" C {meal_summary.totals['carb_g']:.1f} g,"
            f" F {meal_summary.totals['fat_g']:.1f} g"
        )
    kcal = day.progress_for("kcal")
    if kcal.goal:
        out.append(
            f"  day so far: {kcal.value:.0f} / {kcal.goal:.0f} kcal"
            f" ({kcal.percent or 0:.0f}%), {kcal.remaining or 0:.0f} kcal left"
        )
    else:
        out.append(f"  day so far: {kcal.value:.0f} kcal")
    return "\n".join(out)
