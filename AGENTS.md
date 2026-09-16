# projects

This repository holds `nutritrack`, a gram-based food diary. See `README.md` for
the full command reference.

## Setup, lint, test

No dependencies to install; `nutritrack` is standard library only.

```bash
python3 -m unittest discover -s tests -t .   # test suite
ruff check nutritrack tests                  # lint (config in pyproject.toml)
```

`ruff` is not part of the runtime and may need `pip install ruff` on a fresh VM.

## Logging a meal from a photo

This is the main workflow the repository exists for. When the user sends a photo
of a meal:

1. Identify each component in the picture. Ask for gram weights when they are
   not given; do not invent them. If the user gives a household measure ("2
   rotis", "1 bowl of dal"), convert it using the `typical_grams` value on the
   matching food in `data/foods.json` and say which weight was assumed.
2. Look up the names first so the command cannot fail halfway:
   `python3 -m nutritrack foods <query>`.
3. Log the whole meal in one call, attaching the photo:

   ```bash
   python3 -m nutritrack log -m lunch -d today \
       --photo photos/2026-09-15-lunch.jpg \
       "chicken biryani:320" curd:100 "green salad:80"
   ```

4. Report the numbers the command prints: per item, the meal total, and the day
   so far against the calorie goal.
5. If a component is not in the database, add it once with `nutritrack food add`
   using values per 100 g from the packet or a comparable recipe, then log it.
   Say where the values came from.
6. Commit the updated `data/log.json` (and `data/foods.custom.json` if it
   changed) so the diary is preserved.

Exit codes matter when scripting: `2` means the food name matched several
entries and the exact id is needed, `1` means any other failure.

## Conventions

- `data/foods.json` is data, not code. `tests/test_foods.py` enforces its
  invariants: macros must roughly reconcile with the stated calories, sugar
  cannot exceed carbs, saturated fat cannot exceed fat, and no two foods may
  claim the same name or alias. Run the tests after editing it.
- Nutrition facts are always stored per 100 g and scaled at read time. Never
  write pre-scaled numbers into `data/log.json`.
- Adding a nutrient means adding it to `nutritrack/nutrients.py` and to every
  food in `data/foods.json`; `Food.from_dict` rejects incomplete records.
- Tests must never touch the real diary. Pass `--data-dir` to a temporary
  directory, as `tests/test_cli.py` does.

## Cursor Cloud specific instructions

- Python 3.12 and Node.js 22 are available; nothing else is needed to run or
  test this project.
- `google-chrome` is installed and can screenshot a generated dashboard:

  ```bash
  python3 -m nutritrack dashboard 2026-09-15 --out /tmp/day.html
  timeout 30 google-chrome --headless=new --disable-gpu --no-sandbox \
      --hide-scrollbars --force-device-scale-factor=2 --window-size=1200,2160 \
      --screenshot=/tmp/day.png file:///tmp/day.html
  ```

  Chrome writes the PNG and then hangs instead of exiting, so always wrap it in
  `timeout` and check for the file rather than trusting the exit code.
- `ffmpeg` is available for resizing or converting those screenshots.
