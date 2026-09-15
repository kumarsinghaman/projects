"""Command line interface: `python3 -m nutritrack ...`."""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from . import dashboard, nutrients, report
from .foods import AmbiguousFood, Food, FoodNotFound, normalize
from .log import (
    LoggedItem,
    canonical_meal,
    parse_date,
    parse_items_spec,
)
from .profile import ACTIVITY_FACTORS, GOAL_ADJUSTMENTS, Profile
from .store import Workspace
from .summary import (
    DaySummary,
    ItemLine,
    RangeSummary,
    summarize_day,
    summarize_range,
    top_contributors,
)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_AMBIGUOUS = 2


class CommandError(Exception):
    """User-facing error; the CLI prints the message and exits non-zero."""

    def __init__(self, message: str, code: int = EXIT_ERROR):
        super().__init__(message)
        self.code = code


def _slugify(text: str) -> str:
    # Apostrophes vanish rather than becoming separators, so "Amma's dal" is
    # `ammas_dal` and not `amma_s_dal`.
    without_apostrophes = text.replace("'", "").replace("\u2019", "")
    return normalize(without_apostrophes).replace(" ", "_") or "custom_food"


def _relative_photo(value: str, root: Path) -> str:
    path = Path(value).expanduser()
    if not path.exists():
        raise CommandError(f"photo not found: {value}")
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(root.resolve()))
    except ValueError:
        return str(resolved)


def _resolve_food(workspace: Workspace, query: str) -> Food:
    try:
        return workspace.db.resolve(query)
    except AmbiguousFood as exc:
        lines = [f"{query!r} matches more than one food. Use the exact id:"]
        for food in exc.matches:
            lines.append(f"  {food.id:<26}{food.name}")
        raise CommandError("\n".join(lines), code=EXIT_AMBIGUOUS) from exc
    except FoodNotFound as exc:
        lines = [f"No food matches {query!r}."]
        if exc.suggestions:
            lines.append("Closest entries: " + ", ".join(exc.suggestions))
        lines.append(
            "Add it once with:  nutritrack food add --name \"<name>\" "
            "--kcal <n> --protein <g> --carb <g> --fat <g>"
        )
        raise CommandError("\n".join(lines)) from exc


def _day_to_dict(day: DaySummary) -> dict[str, object]:
    return {
        "date": day.date,
        "totals": {
            key: round(value, 2) for key, value in day.totals.items()
        },
        "macro_split_percent": {
            key: round(value, 1) for key, value in day.macro_split.items()
        },
        "goals": {key: round(value, 1) for key, value in day.goals.items()},
        "progress": [
            {
                "nutrient": entry.key,
                "value": round(entry.value, 2),
                "goal": round(entry.goal, 1) if entry.goal else None,
                "percent": round(entry.percent, 1) if entry.percent else None,
                "remaining": round(entry.remaining, 2)
                if entry.remaining is not None
                else None,
                "status": entry.status,
            }
            for entry in day.progress()
        ],
        "meals": [
            {
                "meal": meal.meal,
                "grams": round(meal.grams, 1),
                "totals": {key: round(value, 2) for key, value in meal.totals.items()},
                "items": [
                    {
                        "id": line.item.id,
                        "food": line.item.food_name,
                        "food_id": line.item.food_id,
                        "grams": line.item.grams,
                        "time": line.item.time,
                        "note": line.item.note,
                        "photo": line.item.photo,
                        "nutrients": {
                            key: round(value, 2) for key, value in line.values.items()
                        },
                    }
                    for line in meal.lines
                ],
            }
            for meal in day.meals
        ],
    }


def _range_to_dict(summary: RangeSummary) -> dict[str, object]:
    return {
        "start": summary.start,
        "end": summary.end,
        "days_logged": len(summary.logged_days),
        "averages": {key: round(value, 2) for key, value in summary.averages().items()},
        "goals": {key: round(value, 1) for key, value in summary.goals.items()},
        "days": [_day_to_dict(day) for day in summary.days],
    }


def cmd_log(args: argparse.Namespace, workspace: Workspace) -> int:
    chunks = list(args.items or [])
    if args.items_spec:
        chunks.append(args.items_spec)
    specs: list[tuple[str, float]] = []
    for chunk in chunks:
        specs.extend(parse_items_spec(chunk))
    if not specs:
        raise CommandError(
            "nothing to log. Pass items as name:grams, e.g. "
            "nutritrack log -m lunch roti:80 'dal tadka:200'"
        )

    day = parse_date(args.date)
    meal = canonical_meal(args.meal)
    photo = _relative_photo(args.photo, workspace.root) if args.photo else None

    added: list[LoggedItem] = []
    for name, grams in specs:
        food = _resolve_food(workspace, name)
        entry = LoggedItem(
            id=workspace.log.next_id(day),
            date=day,
            meal=meal,
            grams=grams,
            food_name=food.name,
            food_id=food.id,
            time=args.time,
            photo=photo,
            note=args.note,
        )
        workspace.log.add(entry)
        added.append(entry)

    workspace.save_log()
    summary = summarize_day(workspace.log, workspace.db, day, workspace.profile)
    lines = [
        ItemLine(item=entry, values=entry.nutrients(workspace.db)) for entry in added
    ]
    print(report.render_log_confirmation(summary, meal, lines))
    return EXIT_OK


def cmd_day(args: argparse.Namespace, workspace: Workspace) -> int:
    day = parse_date(args.date)
    summary = summarize_day(workspace.log, workspace.db, day, workspace.profile)
    if args.json:
        print(json.dumps(_day_to_dict(summary), indent=2))
        return EXIT_OK
    print(report.render_day(summary, show_items=not args.totals_only))
    if args.top and not summary.is_empty:
        print(report.render_top_contributors(top_contributors(summary, limit=args.top)))
    return EXIT_OK


def cmd_range(args: argparse.Namespace, workspace: Workspace) -> int:
    end = parse_date(args.end)
    if args.start:
        start = parse_date(args.start)
    else:
        from datetime import date as date_cls
        from datetime import timedelta

        start = (
            date_cls.fromisoformat(end) - timedelta(days=max(args.days, 1) - 1)
        ).isoformat()
    summary = summarize_range(
        workspace.log, workspace.db, start, end, workspace.profile
    )
    if args.json:
        print(json.dumps(_range_to_dict(summary), indent=2))
        return EXIT_OK
    print(report.render_range(summary))
    return EXIT_OK


def cmd_entries(args: argparse.Namespace, workspace: Workspace) -> int:
    day = parse_date(args.date)
    items = workspace.log.for_date(day)
    if not items:
        print(f"No entries logged on {day}.")
        return EXIT_OK
    print(f"{len(items)} entries on {day}:")
    for item in items:
        values = item.nutrients(workspace.db)
        print(
            f"  {item.id:<14}{report.clip(item.meal, 14):<16}"
            f"{report.clip(item.food_name, 34):<36}"
            f"{item.grams:>6.0f}g{values['kcal']:>8.0f} kcal"
        )
    return EXIT_OK


def cmd_remove(args: argparse.Namespace, workspace: Workspace) -> int:
    try:
        removed = workspace.log.remove(args.entry_id)
    except KeyError as exc:
        raise CommandError(str(exc)) from exc
    workspace.save_log()
    print(
        f"Removed {removed.id}: {removed.food_name} {removed.grams:.0f} g "
        f"from {removed.meal} on {removed.date}"
    )
    return EXIT_OK


def cmd_edit(args: argparse.Namespace, workspace: Workspace) -> int:
    item = workspace.log.get(args.entry_id)
    if item is None:
        raise CommandError(f"no log entry with id {args.entry_id!r}")
    if args.grams is not None:
        if args.grams <= 0:
            raise CommandError("grams must be positive")
        item.grams = args.grams
    if args.meal:
        item.meal = canonical_meal(args.meal)
    if args.note is not None:
        item.note = args.note or None
    if args.photo:
        item.photo = _relative_photo(args.photo, workspace.root)
    if args.food:
        food = _resolve_food(workspace, args.food)
        item.food_id = food.id
        item.food_name = food.name
        item.per_100g = None
    workspace.save_log()
    values = item.nutrients(workspace.db)
    print(
        f"Updated {item.id}: {item.food_name} {item.grams:.0f} g in {item.meal} "
        f"on {item.date} -> {values['kcal']:.0f} kcal"
    )
    return EXIT_OK


def cmd_foods(args: argparse.Namespace, workspace: Workspace) -> int:
    query = " ".join(args.query) if args.query else ""
    matches = workspace.db.search(query)
    if args.category:
        wanted = normalize(args.category)
        matches = [food for food in matches if normalize(food.category) == wanted]
    if args.limit:
        matches = matches[: args.limit]
    print(report.render_foods(matches, query))
    return EXIT_OK


def cmd_food_show(args: argparse.Namespace, workspace: Workspace) -> int:
    food = _resolve_food(workspace, " ".join(args.query))
    if args.grams:
        values = food.nutrients_for(args.grams)
        print(f"{food.name} - {args.grams:.0f} g")
        print(report.rule("-"))
        for nutrient in nutrients.NUTRIENTS:
            amount = nutrients.format_amount(nutrient.key, values[nutrient.key])
            print(f"  {nutrient.label:<16}{amount:>8} {nutrient.unit}")
        return EXIT_OK
    print(report.render_food_detail(food))
    return EXIT_OK


def cmd_food_add(args: argparse.Namespace, workspace: Workspace) -> int:
    food_id = args.id or _slugify(args.name)
    if food_id in workspace.db and not args.force:
        raise CommandError(
            f"food id {food_id!r} already exists; pass --force to overwrite"
        )
    per_100g = {
        "kcal": args.kcal,
        "protein_g": args.protein,
        "carb_g": args.carb,
        "fiber_g": args.fiber,
        "sugar_g": args.sugar,
        "fat_g": args.fat,
        "sat_fat_g": args.sat_fat,
        "sodium_mg": args.sodium,
        "potassium_mg": args.potassium,
    }
    food = Food(
        id=food_id,
        name=args.name,
        category=args.category,
        per_100g={key: float(value) for key, value in per_100g.items()},
        aliases=[alias.strip() for alias in (args.alias or []) if alias.strip()],
        typical_grams=args.typical_grams,
        typical_label=args.typical_label,
    )
    path = workspace.save_custom_food(food)
    print(f"Saved {food.name} as {food.id} in {path}")
    print(report.render_food_detail(food))
    return EXIT_OK


def cmd_profile(args: argparse.Namespace, workspace: Workspace) -> int:
    profile: Profile = workspace.profile
    changed = False
    if args.name is not None:
        profile.name = args.name
        changed = True
    for field_name in ("sex", "activity", "weight_goal"):
        value = getattr(args, field_name)
        if value is not None:
            setattr(profile, field_name, value)
            changed = True
    for field_name in ("age", "height_cm", "weight_kg"):
        value = getattr(args, field_name)
        if value is not None:
            setattr(profile, field_name, value)
            changed = True

    if args.recompute:
        if not profile.has_body_stats():
            raise CommandError(
                "--recompute needs --sex, --age, --height-cm and --weight-kg "
                "to be set (either now or previously)"
            )
        profile.recompute_goals()
        changed = True

    updates: dict[str, float] = {}
    for assignment in args.set or []:
        if "=" not in assignment:
            raise CommandError(
                f"--set expects nutrient=value, got {assignment!r}"
            )
        key, _, raw = assignment.partition("=")
        key = key.strip()
        if key not in nutrients.NUTRIENT_KEYS:
            raise CommandError(
                f"unknown nutrient {key!r}; valid keys: "
                + ", ".join(nutrients.NUTRIENT_KEYS)
            )
        try:
            updates[key] = float(raw)
        except ValueError as exc:
            raise CommandError(f"{raw!r} is not a number") from exc
    if updates:
        profile.set_goals(updates)
        changed = True

    if changed:
        path = workspace.save_profile()
        print(f"Saved profile to {path}")

    print(report.rule("="))
    print(f" PROFILE{(' - ' + profile.name) if profile.name else ''}")
    print(report.rule("="))
    body = [
        ("sex", profile.sex),
        ("age", profile.age),
        ("height", f"{profile.height_cm:.0f} cm" if profile.height_cm else None),
        ("weight", f"{profile.weight_kg:.1f} kg" if profile.weight_kg else None),
        ("activity", profile.activity),
        ("weight goal", profile.weight_goal),
    ]
    for label, value in body:
        print(f"  {label:<14}{value if value is not None else '-'}")
    if profile.has_body_stats():
        print(f"  {'BMR':<14}{profile.bmr():.0f} kcal/day")
        if profile.activity:
            print(f"  {'maintenance':<14}{profile.maintenance_kcal():.0f} kcal/day")
    print()
    print(f"  daily goals ({profile.goals_source}):")
    for nutrient in nutrients.NUTRIENTS:
        goal = profile.goals.get(nutrient.key)
        amount = nutrients.format_amount(nutrient.key, goal) if goal else "-"
        suffix = " (limit)" if nutrient.is_limit else ""
        print(f"    {nutrient.label:<16}{amount:>8} {nutrient.unit}{suffix}")
    return EXIT_OK


def cmd_dashboard(args: argparse.Namespace, workspace: Workspace) -> int:
    day = parse_date(args.date)
    summary = summarize_day(workspace.log, workspace.db, day, workspace.profile)
    from datetime import date as date_cls
    from datetime import timedelta

    trend_start = (
        date_cls.fromisoformat(day) - timedelta(days=max(args.days, 1) - 1)
    ).isoformat()
    trend = summarize_range(
        workspace.log, workspace.db, trend_start, day, workspace.profile
    )
    output = (
        Path(args.out).expanduser()
        if args.out
        else workspace.root / "reports" / f"{day}.html"
    )
    path = dashboard.write_dashboard(
        summary,
        output,
        profile=workspace.profile,
        trend=trend,
        repo_root=workspace.root,
    )
    print(f"Dashboard written to {path}")
    return EXIT_OK


def cmd_export(args: argparse.Namespace, workspace: Workspace) -> int:
    items = (
        workspace.log.between(parse_date(args.start), parse_date(args.end))
        if args.start or args.end
        else workspace.log.sorted_items()
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    header = ["id", "date", "meal", "time", "food", "grams"]
    writer.writerow([*header, *nutrients.NUTRIENT_KEYS, "note"])
    for item in items:
        values = item.nutrients(workspace.db)
        writer.writerow(
            [
                item.id,
                item.date,
                item.meal,
                item.time or "",
                item.food_name,
                f"{item.grams:.1f}",
                *[f"{values[key]:.2f}" for key in nutrients.NUTRIENT_KEYS],
                item.note or "",
            ]
        )
    text = buffer.getvalue()
    if args.out:
        path = Path(args.out).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"Exported {len(items)} entries to {path}")
    else:
        sys.stdout.write(text)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nutritrack",
        description=(
            "Track per-meal and daily calories and nutrition from gram weights."
        ),
    )
    parser.add_argument(
        "--data-dir",
        help="directory holding foods.json, log.json and profile.json",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    log_parser = subparsers.add_parser(
        "log", help="log one or more foods into a meal"
    )
    log_parser.add_argument(
        "items",
        nargs="*",
        help="foods as name:grams, e.g. roti:80 'dal tadka:200'",
    )
    log_parser.add_argument("-m", "--meal", required=True, help="breakfast/lunch/...")
    log_parser.add_argument("-d", "--date", help="ISO date, today, yesterday or -N")
    log_parser.add_argument("-t", "--time", help="clock time, e.g. 08:45")
    log_parser.add_argument(
        "--items-spec",
        dest="items_spec",
        help="comma separated items, e.g. 'roti:80, dal:200'",
    )
    log_parser.add_argument("--photo", help="path to the meal photo")
    log_parser.add_argument("--note", help="free-text note for these items")
    log_parser.set_defaults(func=cmd_log)

    day_parser = subparsers.add_parser("day", help="per-meal and daily totals")
    day_parser.add_argument("date", nargs="?", help="defaults to today")
    day_parser.add_argument(
        "--totals-only", action="store_true", help="hide the item breakdown"
    )
    day_parser.add_argument(
        "--top", type=int, default=0, help="also show the N biggest calorie items"
    )
    day_parser.add_argument("--json", action="store_true")
    day_parser.set_defaults(func=cmd_day)

    today_parser = subparsers.add_parser("today", help="shortcut for `day` today")
    today_parser.add_argument("--totals-only", action="store_true")
    today_parser.add_argument("--top", type=int, default=0)
    today_parser.add_argument("--json", action="store_true")
    today_parser.set_defaults(func=cmd_day, date=None)

    range_parser = subparsers.add_parser(
        "range", help="multi-day table with averages vs goals"
    )
    range_parser.add_argument("--start", help="ISO start date")
    range_parser.add_argument("--end", help="ISO end date (defaults to today)")
    range_parser.add_argument(
        "--days", type=int, default=7, help="days back from --end when no --start"
    )
    range_parser.add_argument("--json", action="store_true")
    range_parser.set_defaults(func=cmd_range)

    week_parser = subparsers.add_parser("week", help="shortcut for the last 7 days")
    week_parser.add_argument("--end")
    week_parser.add_argument("--json", action="store_true")
    week_parser.set_defaults(func=cmd_range, start=None, days=7)

    entries_parser = subparsers.add_parser(
        "entries", help="list entry ids for a day (use before remove/edit)"
    )
    entries_parser.add_argument("date", nargs="?")
    entries_parser.set_defaults(func=cmd_entries)

    remove_parser = subparsers.add_parser("remove", help="delete a log entry by id")
    remove_parser.add_argument("entry_id")
    remove_parser.set_defaults(func=cmd_remove)

    edit_parser = subparsers.add_parser("edit", help="change a logged entry")
    edit_parser.add_argument("entry_id")
    edit_parser.add_argument("--grams", type=float)
    edit_parser.add_argument("--meal")
    edit_parser.add_argument("--food")
    edit_parser.add_argument("--note")
    edit_parser.add_argument("--photo")
    edit_parser.set_defaults(func=cmd_edit)

    foods_parser = subparsers.add_parser("foods", help="search the food database")
    foods_parser.add_argument("query", nargs="*")
    foods_parser.add_argument("--category")
    foods_parser.add_argument("--limit", type=int, default=0)
    foods_parser.set_defaults(func=cmd_foods)

    food_parser = subparsers.add_parser("food", help="inspect or add a single food")
    food_sub = food_parser.add_subparsers(dest="food_command", required=True)

    show_parser = food_sub.add_parser("show", help="nutrition facts for one food")
    show_parser.add_argument("query", nargs="+")
    show_parser.add_argument(
        "--grams", type=float, help="scale the facts to this weight"
    )
    show_parser.set_defaults(func=cmd_food_show)

    add_parser = food_sub.add_parser(
        "add", help="add a custom food (values per 100 g)"
    )
    add_parser.add_argument("--name", required=True)
    add_parser.add_argument("--id")
    add_parser.add_argument("--category", default="custom")
    add_parser.add_argument("--alias", action="append")
    add_parser.add_argument("--kcal", type=float, required=True)
    add_parser.add_argument("--protein", type=float, default=0.0)
    add_parser.add_argument("--carb", type=float, default=0.0)
    add_parser.add_argument("--fiber", type=float, default=0.0)
    add_parser.add_argument("--sugar", type=float, default=0.0)
    add_parser.add_argument("--fat", type=float, default=0.0)
    add_parser.add_argument("--sat-fat", dest="sat_fat", type=float, default=0.0)
    add_parser.add_argument("--sodium", type=float, default=0.0)
    add_parser.add_argument("--potassium", type=float, default=0.0)
    add_parser.add_argument("--typical-grams", dest="typical_grams", type=float)
    add_parser.add_argument("--typical-label", dest="typical_label")
    add_parser.add_argument("--force", action="store_true")
    add_parser.set_defaults(func=cmd_food_add)

    profile_parser = subparsers.add_parser(
        "profile", help="show or change daily goals and body stats"
    )
    profile_parser.add_argument("--name")
    profile_parser.add_argument("--sex", choices=["male", "female"])
    profile_parser.add_argument("--age", type=int)
    profile_parser.add_argument("--height-cm", dest="height_cm", type=float)
    profile_parser.add_argument("--weight-kg", dest="weight_kg", type=float)
    profile_parser.add_argument("--activity", choices=sorted(ACTIVITY_FACTORS))
    profile_parser.add_argument(
        "--weight-goal", dest="weight_goal", choices=sorted(GOAL_ADJUSTMENTS)
    )
    profile_parser.add_argument(
        "--recompute",
        action="store_true",
        help="derive all daily goals from the body stats above",
    )
    profile_parser.add_argument(
        "--set",
        action="append",
        metavar="NUTRIENT=VALUE",
        help="override one goal, e.g. --set protein_g=140",
    )
    profile_parser.set_defaults(func=cmd_profile)

    dash_parser = subparsers.add_parser(
        "dashboard", help="write a self-contained HTML dashboard for a day"
    )
    dash_parser.add_argument("date", nargs="?")
    dash_parser.add_argument("--out", help="output path (default reports/<date>.html)")
    dash_parser.add_argument(
        "--days", type=int, default=7, help="days of history in the trend chart"
    )
    dash_parser.set_defaults(func=cmd_dashboard)

    export_parser = subparsers.add_parser("export", help="export the log as CSV")
    export_parser.add_argument("--start")
    export_parser.add_argument("--end")
    export_parser.add_argument("--out")
    export_parser.set_defaults(func=cmd_export)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        workspace = Workspace.load(
            Path(args.data_dir).expanduser() if args.data_dir else None
        )
        return int(args.func(args, workspace))
    except CommandError as exc:
        print(str(exc), file=sys.stderr)
        return exc.code
    except (ValueError, KeyError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
