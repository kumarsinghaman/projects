"""Render a day's log as a self-contained HTML dashboard (no external assets)."""

from __future__ import annotations

import html
import os
from datetime import datetime
from pathlib import Path

from . import nutrients
from .profile import Profile
from .report import pretty_date
from .summary import DaySummary, GoalProgress, MealSummary, RangeSummary

_STATUS_COLOR = {
    "met": "var(--good)",
    "on-track": "var(--good)",
    "under": "var(--warn)",
    "over": "var(--bad)",
    "no-goal": "var(--muted)",
}

_MACRO_COLOR = {
    "protein_g": "#38bdf8",
    "carb_g": "#fbbf24",
    "fat_g": "#f472b6",
}

_CSS = """
:root {
  --bg: #0b0f14;
  --panel: #131a24;
  --panel-2: #182130;
  --line: #243044;
  --text: #e7edf5;
  --muted: #8899ad;
  --good: #34d399;
  --warn: #60a5fa;
  --bad: #f87171;
  --accent: #34d399;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 32px 28px 56px;
  background: radial-gradient(1100px 520px at 15% -15%, #16212e 0%, transparent 70%),
              var(--bg);
  color: var(--text);
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica,
        Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 1120px; margin: 0 auto; }
header { margin-bottom: 24px; }
h1 { font-size: 26px; margin: 0 0 6px; letter-spacing: -0.02em; }
.sub { color: var(--muted); font-size: 13px; }
.grid { display: grid; gap: 16px; }
.hero { grid-template-columns: 1.1fr 1fr 1.4fr; margin-bottom: 16px; }
.quad { grid-template-columns: repeat(4, 1fr); margin-bottom: 16px; }
.card {
  background: linear-gradient(180deg, var(--panel) 0%, var(--panel-2) 100%);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 18px 20px;
}
.card h2 {
  font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase;
  color: var(--muted); margin: 0 0 14px; font-weight: 600;
}
.ring-wrap { display: flex; align-items: center; gap: 18px; }
.ring { position: relative; width: 132px; height: 132px; flex: 0 0 auto; }
.ring svg { transform: rotate(-90deg); }
.ring .inner {
  position: absolute; inset: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
}
.ring .big { font-size: 27px; font-weight: 700; letter-spacing: -0.02em; }
.ring .small { font-size: 11px; color: var(--muted); }
.kv { font-size: 13px; color: var(--muted); }
.kv b { color: var(--text); font-size: 15px; font-weight: 600; }
.kv div { margin-bottom: 8px; }
.donut-wrap { display: flex; align-items: center; gap: 18px; }
.donut {
  width: 116px; height: 116px; border-radius: 50%; flex: 0 0 auto;
  display: flex; align-items: center; justify-content: center;
}
.donut .hole {
  width: 74px; height: 74px; border-radius: 50%; background: var(--panel-2);
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; color: var(--muted); text-align: center; line-height: 1.25;
}
.legend { font-size: 13px; }
.legend div { display: flex; align-items: center; gap: 8px; margin-bottom: 7px; }
.dot { width: 10px; height: 10px; border-radius: 3px; flex: 0 0 auto; }
.bars { display: grid; gap: 13px; }
.bar-row { display: grid; grid-template-columns: 78px 1fr 118px; align-items: center;
           gap: 12px; font-size: 13px; }
.bar-label { color: var(--muted); }
.track { height: 12px; border-radius: 99px; background: #0d131c;
         border: 1px solid var(--line); overflow: hidden; }
.fill { height: 100%; border-radius: 99px; }
.bar-value { text-align: right; font-variant-numeric: tabular-nums; }
.bar-value span { color: var(--muted); }
.stat .n { font-size: 24px; font-weight: 700; letter-spacing: -0.02em; }
.stat .g { font-size: 12px; color: var(--muted); margin-top: 2px; }
.stat .pill {
  display: inline-block; margin-top: 10px; font-size: 11px; padding: 3px 9px;
  border-radius: 99px; border: 1px solid var(--line); color: var(--muted);
}
table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
th {
  text-align: right; font-size: 10.5px; letter-spacing: 0.1em; color: var(--muted);
  text-transform: uppercase; padding: 0 0 9px; font-weight: 600;
  border-bottom: 1px solid var(--line);
}
th:first-child, td:first-child { text-align: left; }
td { padding: 9px 0; text-align: right; border-bottom: 1px solid #1b2431;
     font-variant-numeric: tabular-nums; }
tr:last-child td { border-bottom: none; }
tr.total td { font-weight: 700; border-top: 1px solid var(--line);
              border-bottom: none; }
.note { color: var(--muted); font-size: 12px; }
.meal-head { display: flex; align-items: baseline; justify-content: space-between;
             margin-bottom: 12px; }
.meal-head h3 { margin: 0; font-size: 15px; letter-spacing: -0.01em; }
.meal-kcal { font-size: 13px; color: var(--muted); }
.meal-kcal b { color: var(--accent); font-size: 16px; }
.shots { display: flex; gap: 10px; margin-top: 14px; flex-wrap: wrap; }
.shots figure { margin: 0; }
.shots img { height: 108px; border-radius: 10px; border: 1px solid var(--line);
             display: block; }
.shots figcaption { font-size: 10.5px; color: var(--muted); margin-top: 5px;
                    max-width: 160px; overflow: hidden; text-overflow: ellipsis;
                    white-space: nowrap; }
.trend { display: flex; align-items: flex-end; gap: 14px; height: 168px;
         padding-top: 8px; }
.trend .col { flex: 1; display: flex; flex-direction: column;
              justify-content: flex-end; align-items: center; height: 100%; }
.trend .val { font-size: 11.5px; color: var(--muted); margin-bottom: 6px;
              font-variant-numeric: tabular-nums; }
.trend .stack { width: 100%; max-width: 54px; border-radius: 6px 6px 0 0;
                overflow: hidden; display: flex; flex-direction: column-reverse; }
.trend .seg { width: 100%; }
.trend .day { font-size: 11px; color: var(--muted); margin-top: 8px; }
.trend .goal-line { position: relative; }
footer { color: var(--muted); font-size: 11.5px; margin-top: 26px; }
@media (max-width: 900px) {
  .hero, .quad { grid-template-columns: 1fr; }
}
"""


def _esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def _fill_color(status: str) -> str:
    return _STATUS_COLOR.get(status, "var(--muted)")


def _ring(progress: GoalProgress) -> str:
    percent = progress.percent
    fraction = min(max((percent or 0.0) / 100.0, 0.0), 1.0)
    radius = 56.0
    circumference = 2 * 3.141592653589793 * radius
    dash = circumference * fraction
    color = _fill_color(progress.status)
    goal_text = (
        f"of {progress.goal:.0f} kcal goal" if progress.goal else "no calorie goal set"
    )
    return f"""
      <div class="ring">
        <svg width="132" height="132" viewBox="0 0 132 132">
          <circle cx="66" cy="66" r="{radius}" fill="none" stroke="#0d131c"
                  stroke-width="12"/>
          <circle cx="66" cy="66" r="{radius}" fill="none" stroke="{color}"
                  stroke-width="12" stroke-linecap="round"
                  stroke-dasharray="{dash:.2f} {circumference - dash:.2f}"/>
        </svg>
        <div class="inner">
          <div class="big">{progress.value:.0f}</div>
          <div class="small">kcal</div>
        </div>
      </div>
      <div class="kv">
        <div><b>{(percent or 0.0):.0f}%</b> {_esc(goal_text)}</div>
        <div>{_remaining_text(progress)}</div>
      </div>
    """


def _remaining_text(progress: GoalProgress) -> str:
    if progress.goal is None:
        return "<span>set a goal with <code>profile</code></span>"
    remaining = progress.remaining or 0.0
    if remaining >= 0:
        return f"<b>{remaining:.0f} kcal</b> still available"
    return f"<b>{-remaining:.0f} kcal</b> over the goal"


def _donut(day: DaySummary) -> str:
    split = day.macro_split
    energy = day.macro_energy
    if day.totals["kcal"] <= 0:
        gradient = "conic-gradient(var(--line) 0 100%)"
    else:
        stops: list[str] = []
        cursor = 0.0
        for key in nutrients.MACRO_KEYS:
            end = cursor + split[key]
            stops.append(f"{_MACRO_COLOR[key]} {cursor:.2f}% {end:.2f}%")
            cursor = end
        if cursor < 99.9:
            stops.append(f"var(--line) {cursor:.2f}% 100%")
        gradient = "conic-gradient(" + ", ".join(stops) + ")"
    legend = "".join(
        f'<div><span class="dot" style="background:{_MACRO_COLOR[key]}"></span>'
        f"{_esc(nutrients.BY_KEY[key].label)} &mdash; {split[key]:.0f}%"
        f' <span class="note">({energy[key]:.0f} kcal)</span></div>'
        for key in nutrients.MACRO_KEYS
    )
    return f"""
      <div class="donut-wrap">
        <div class="donut" style="background:{gradient}">
          <div class="hole">macro<br>split</div>
        </div>
        <div class="legend">{legend}</div>
      </div>
    """


def _bar_row(progress: GoalProgress) -> str:
    nutrient = nutrients.BY_KEY[progress.key]
    value = nutrients.format_amount(progress.key, progress.value)
    if progress.goal is None:
        return f"""
        <div class="bar-row">
          <div class="bar-label">{_esc(nutrient.label)}</div>
          <div class="track"></div>
          <div class="bar-value">{value} <span>{_esc(nutrient.unit)}</span></div>
        </div>
        """
    percent = min(max(progress.percent or 0.0, 0.0), 100.0)
    goal = nutrients.format_amount(progress.key, progress.goal)
    return f"""
        <div class="bar-row">
          <div class="bar-label">{_esc(nutrient.label)}</div>
          <div class="track">
            <div class="fill" style="width:{percent:.1f}%;
                 background:{_fill_color(progress.status)}"></div>
          </div>
          <div class="bar-value">{value}<span> / {goal}
            {_esc(nutrient.unit)}</span></div>
        </div>
    """


def _stat_card(progress: GoalProgress) -> str:
    nutrient = nutrients.BY_KEY[progress.key]
    value = nutrients.format_amount(progress.key, progress.value)
    if progress.goal is None:
        detail = "no goal set"
        pill = ""
    else:
        goal = nutrients.format_amount(progress.key, progress.goal)
        detail = f"of {goal} {nutrient.unit}"
        label = "within limit" if nutrient.is_limit else "of target"
        if progress.status == "over":
            label = "over limit" if nutrient.is_limit else "over target"
        pill = (
            f'<div class="pill" style="color:{_fill_color(progress.status)};'
            f'border-color:{_fill_color(progress.status)}33">'
            f"{(progress.percent or 0):.0f}% {label}</div>"
        )
    return f"""
      <div class="card stat">
        <h2>{_esc(nutrient.label)}</h2>
        <div class="n">{value} <span class="g">{_esc(nutrient.unit)}</span></div>
        <div class="g">{_esc(detail)}</div>
        {pill}
      </div>
    """


def _photo_block(meal: MealSummary, output_dir: Path, repo_root: Path) -> str:
    figures: list[str] = []
    for photo in meal.photos:
        candidate = Path(photo)
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        if not candidate.exists():
            continue
        relative = os.path.relpath(candidate, output_dir)
        figures.append(
            f'<figure><img src="{_esc(relative)}" alt="{_esc(photo)}">'
            f"<figcaption>{_esc(Path(photo).name)}</figcaption></figure>"
        )
    if not figures:
        return ""
    return '<div class="shots">' + "".join(figures) + "</div>"


def _meal_card(meal: MealSummary, output_dir: Path, repo_root: Path) -> str:
    rows: list[str] = []
    for line in meal.lines:
        values = line.values
        name = _esc(line.item.food_name)
        extras: list[str] = []
        if line.item.time:
            extras.append(_esc(line.item.time))
        if line.item.note:
            extras.append(_esc(line.item.note))
        detail = (
            f'<div class="note">{" &middot; ".join(extras)}</div>' if extras else ""
        )
        rows.append(
            f"<tr><td>{name}{detail}</td>"
            f"<td>{line.item.grams:.0f}</td>"
            f"<td>{values['kcal']:.0f}</td>"
            f"<td>{values['protein_g']:.1f}</td>"
            f"<td>{values['carb_g']:.1f}</td>"
            f"<td>{values['fat_g']:.1f}</td>"
            f"<td>{values['fiber_g']:.1f}</td></tr>"
        )
    totals = meal.totals
    rows.append(
        f'<tr class="total"><td>Total</td>'
        f"<td>{meal.grams:.0f}</td>"
        f"<td>{totals['kcal']:.0f}</td>"
        f"<td>{totals['protein_g']:.1f}</td>"
        f"<td>{totals['carb_g']:.1f}</td>"
        f"<td>{totals['fat_g']:.1f}</td>"
        f"<td>{totals['fiber_g']:.1f}</td></tr>"
    )
    return f"""
      <div class="card">
        <div class="meal-head">
          <h3>{_esc(meal.meal.title())}</h3>
          <div class="meal-kcal"><b>{totals['kcal']:.0f}</b> kcal &middot;
            {meal.grams:.0f} g</div>
        </div>
        <table>
          <thead><tr><th>Item</th><th>Grams</th><th>Kcal</th><th>Prot</th>
            <th>Carb</th><th>Fat</th><th>Fiber</th></tr></thead>
          <tbody>{"".join(rows)}</tbody>
        </table>
        {_photo_block(meal, output_dir, repo_root)}
      </div>
    """


def _trend(summary: RangeSummary | None, focus_date: str) -> str:
    if summary is None or not summary.days:
        return ""
    goal = summary.goals.get("kcal") or 0.0
    peak = max([day.totals["kcal"] for day in summary.days] + [goal, 1.0])
    columns: list[str] = []
    for day in summary.days:
        energy = day.macro_energy
        total = day.totals["kcal"]
        height = total / peak * 100.0
        segments = ""
        if total > 0:
            for key in nutrients.MACRO_KEYS:
                share = energy[key] / total * 100.0 if total else 0.0
                segments += (
                    f'<div class="seg" style="height:{share:.2f}%;'
                    f'background:{_MACRO_COLOR[key]}"></div>'
                )
        emphasis = (
            "box-shadow:0 0 0 2px var(--accent);" if day.date == focus_date else ""
        )
        label = pretty_date(day.date).split(" ")
        columns.append(
            f"""<div class="col">
              <div class="val">{total:.0f}</div>
              <div class="stack" style="height:{max(height, 1.5):.2f}%;{emphasis}">
                {segments}
              </div>
              <div class="day">{_esc(label[0])} {_esc(label[1])}</div>
            </div>"""
        )
    goal_note = f"goal {goal:.0f} kcal" if goal else "no calorie goal"
    return f"""
      <div class="card">
        <h2>Last {len(summary.days)} days &middot; {_esc(goal_note)}</h2>
        <div class="trend">{"".join(columns)}</div>
      </div>
    """


def render_dashboard_html(
    day: DaySummary,
    profile: Profile | None = None,
    trend: RangeSummary | None = None,
    output_dir: Path | None = None,
    repo_root: Path | None = None,
) -> str:
    out_dir = output_dir or Path.cwd()
    root = repo_root or Path.cwd()
    kcal = day.progress_for("kcal")
    macro_rows = "".join(
        _bar_row(day.progress_for(key))
        for key in ("protein_g", "carb_g", "fat_g", "fiber_g")
    )
    stat_cards = "".join(
        _stat_card(day.progress_for(key))
        for key in ("sugar_g", "sat_fat_g", "sodium_mg", "potassium_mg")
    )
    meal_cards = (
        "".join(_meal_card(meal, out_dir, root) for meal in day.meals)
        if day.meals
        else '<div class="card"><p class="note">Nothing logged for this day yet.</p>'
        "</div>"
    )
    who = profile.name if profile and profile.name else "Daily nutrition"
    source = (
        f"goals {profile.goals_source}" if profile else "no profile"
    )
    generated = datetime.now().strftime("%d %b %Y, %H:%M")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(who)} &middot; {_esc(pretty_date(day.date))}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>{_esc(who)} &middot; {_esc(pretty_date(day.date))}</h1>
    <div class="sub">{day.item_count} items across {len(day.meals)} meals
      &middot; {_esc(source)}</div>
  </header>

  <div class="grid hero">
    <div class="card">
      <h2>Calories</h2>
      <div class="ring-wrap">{_ring(kcal)}</div>
    </div>
    <div class="card">
      <h2>Where the energy came from</h2>
      {_donut(day)}
    </div>
    <div class="card">
      <h2>Macros vs daily goals</h2>
      <div class="bars">{macro_rows}</div>
    </div>
  </div>

  <div class="grid quad">{stat_cards}</div>

  <div class="grid" style="margin-bottom:16px">{meal_cards}</div>

  <div class="grid">{_trend(trend, day.date)}</div>

  <footer>Generated by nutritrack on {_esc(generated)}. Values are estimates from
    the bundled food database (per 100 g) scaled by the logged gram weights.</footer>
</div>
</body>
</html>
"""


def write_dashboard(
    day: DaySummary,
    output_path: Path,
    profile: Profile | None = None,
    trend: RangeSummary | None = None,
    repo_root: Path | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    markup = render_dashboard_html(
        day,
        profile=profile,
        trend=trend,
        output_dir=output_path.parent,
        repo_root=repo_root,
    )
    output_path.write_text(markup, encoding="utf-8")
    return output_path
