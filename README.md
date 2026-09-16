# nutritrack

A gram-based food diary. You say what you ate and how much it weighed; it tells
you the calories and nutrition for that item, for that meal, and for the whole
day, measured against your daily targets.

Built for the photo-and-grams workflow: send a picture of the plate, name the
items with their gram weights, and the day's numbers update.

- Pure Python 3.10+, standard library only. Nothing to install.
- 98 foods built in, weighted towards Indian home cooking (roti, dal, paneer,
  idli, sambar, poha, chole, biryani) alongside global staples.
- Every number is stored per 100 g and scaled by the gram weight you log, so
  correcting a food's nutrition facts fixes every past entry that used it.
- Data lives in plain JSON under `data/`, so the diary is diffable and yours.

## Quick start

```bash
# 1. Set your daily targets (or derive them from your body stats)
python3 -m nutritrack profile --name "Aman" --sex male --age 28 \
    --height-cm 175 --weight-kg 74 --activity moderate \
    --weight-goal lose --recompute

# 2. Log what you ate, as name:grams
python3 -m nutritrack log -m breakfast idli:150 sambar:150 chai:150
python3 -m nutritrack log -m lunch roti:120 "dal tadka:200" rice:100 curd:150

# 3. See where the day stands
python3 -m nutritrack today
```

Logging prints the per-item numbers, the meal total and the day so far:

```
Logged 3 item(s) to breakfast on 2026-09-15:
  + Idli, steamed 150 g  ->  158 kcal, P 5.1 g, C 30.0 g, F 0.6 g   [20260915-001]
  + Sambar 150 g  ->  128 kcal, P 5.2 g, C 16.5 g, F 4.5 g          [20260915-002]
  + Masala chai (milk + sugar) 150 g  ->  98 kcal, ...              [20260915-003]
  breakfast total: 382 kcal, P 12.6 g, C 60.0 g, F 8.4 g
  day so far: 382 / 2159 kcal (18%), 1776 kcal left
```

## Commands

| Command | What it does |
| --- | --- |
| `log -m MEAL name:grams ...` | Add items to a meal. `-d` sets the date, `-t` the time, `--photo` attaches a picture, `--note` adds a remark. |
| `today` / `day [DATE]` | Per-meal breakdown plus day totals against goals. `--totals-only` hides items, `--top N` lists the biggest calorie items, `--json` emits machine-readable output. |
| `week` / `range` | Multi-day table with a calorie trend and averages vs goals. |
| `entries [DATE]` | List entry ids, needed for `remove` and `edit`. |
| `edit ID` | Change `--grams`, `--meal`, `--food`, `--note` or `--photo` of one entry. |
| `remove ID` | Delete one entry. |
| `foods [QUERY]` | Search the database. `--category`, `--limit`. |
| `food show QUERY` | Nutrition facts for one food, optionally scaled with `--grams`. |
| `food add` | Add a food the database does not have, with values per 100 g. |
| `profile` | Show or change body stats and daily goals. |
| `dashboard [DATE]` | Write a self-contained HTML dashboard for a day. |
| `export` | Dump the log as CSV. |

Dates accept `2026-09-15`, `today`, `yesterday` or an offset like `-3`.

## Naming foods

Lookups are forgiving: ids, full names, aliases, plurals and prefixes all work,
and punctuation and case are ignored.

```bash
python3 -m nutritrack log -m snack eggs:100      # plural alias
python3 -m nutritrack log -m snack "dal tadka:200"   # multi-word name
python3 -m nutritrack log -m snack chai:150      # alias
```

If a name matches several foods the command stops and lists the exact ids rather
than guessing. If it matches none, it suggests the closest entries.

## Daily goals

`profile --recompute` derives every target from your body stats: resting energy
from Mifflin-St Jeor, scaled by activity level, adjusted for your weight goal.
Protein follows body weight (1.6 g/kg maintaining, 1.8 g/kg cutting), fat takes
27% of calories, carbs take the remainder, fiber follows 14 g per 1000 kcal, and
sugar, saturated fat and sodium become ceilings.

Override any single target by hand:

```bash
python3 -m nutritrack profile --set protein_g=140 --set sodium_mg=2000
```

Protein, fiber and potassium are treated as floors, so exceeding them reads as
"target met". Calories, carbs and fat are budgets. Sugar, saturated fat and
sodium are limits.

## Foods the database does not have

Add it once with values per 100 g from the packet or a recipe, then log it by
name forever after:

```bash
python3 -m nutritrack food add --name "Amma's coconut chutney" \
    --alias "coconut chutney" \
    --kcal 180 --protein 3 --carb 8 --fat 15 --fiber 4 --sodium 260
python3 -m nutritrack log -m breakfast "coconut chutney:50"
```

Custom foods are written to `data/foods.custom.json` and layered over the
bundled database, so `data/foods.json` stays pristine.

## Photos

```bash
python3 -m nutritrack log -m lunch --photo photos/2026-09-15-lunch.jpg \
    "chicken biryani:320" curd:100
```

The path is stored with the entry, and photos for a day are embedded in that
day's HTML dashboard next to the numbers.

## Dashboard

```bash
python3 -m nutritrack dashboard today
# -> reports/2026-09-15.html
```

One offline HTML file: a calorie ring against the goal, where the day's energy
came from, macros against targets, sugar/saturated fat/sodium/potassium cards,
every meal as a table, and a stacked calorie trend for the last seven days.

## Data files

| File | Contents |
| --- | --- |
| `data/foods.json` | Bundled nutrition facts, per 100 g. |
| `data/foods.custom.json` | Foods you added; layered over the bundled set. |
| `data/log.json` | Every logged item. |
| `data/profile.json` | Body stats and daily goals. |

Point the CLI at a different diary with `--data-dir` or the `NUTRITRACK_DATA`
environment variable.

## Accuracy

Values come from USDA FoodData Central and the Indian Food Composition Tables.
Single ingredients are close to exact; mixed dishes (`dal tadka`, `butter
chicken`, `chicken biryani`) are typical home-style recipes, and the oil and
cream in a real kitchen vary, so treat those as good estimates. Weighing the
food is what makes the totals meaningful.

## Development

```bash
python3 -m unittest discover -s tests -t .   # 165 tests
ruff check nutritrack tests                  # lint
```
