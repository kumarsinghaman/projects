"""Locates the data files and loads the food database, meal log and profile."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .foods import Food, FoodDatabase
from .log import MealLog
from .profile import Profile

DATA_DIR_ENV = "NUTRITRACK_DATA"
FOODS_FILE = "foods.json"
CUSTOM_FOODS_FILE = "foods.custom.json"
LOG_FILE = "log.json"
PROFILE_FILE = "profile.json"


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_data_dir() -> Path:
    from_env = os.environ.get(DATA_DIR_ENV)
    if from_env:
        return Path(from_env).expanduser().resolve()
    return repo_root() / "data"


@dataclass
class Workspace:
    data_dir: Path
    db: FoodDatabase
    log: MealLog
    profile: Profile
    root: Path

    @property
    def foods_path(self) -> Path:
        return self.data_dir / FOODS_FILE

    @property
    def custom_foods_path(self) -> Path:
        return self.data_dir / CUSTOM_FOODS_FILE

    @property
    def log_path(self) -> Path:
        return self.data_dir / LOG_FILE

    @property
    def profile_path(self) -> Path:
        return self.data_dir / PROFILE_FILE

    @classmethod
    def load(cls, data_dir: Path | None = None) -> Workspace:
        directory = (data_dir or default_data_dir()).expanduser()
        base_path = directory / FOODS_FILE
        if base_path.exists():
            db = FoodDatabase.load(base_path)
        else:
            # Fall back to the bundled database so a fresh data dir still works.
            bundled = repo_root() / "data" / FOODS_FILE
            if not bundled.exists():
                raise FileNotFoundError(
                    f"no food database found at {base_path} or {bundled}"
                )
            db = FoodDatabase.load(bundled)
        custom_path = directory / CUSTOM_FOODS_FILE
        if custom_path.exists():
            raw = json.loads(custom_path.read_text(encoding="utf-8"))
            for item in raw.get("foods", []):
                db.add(Food.from_dict(item), overwrite=True)
        return cls(
            data_dir=directory,
            db=db,
            log=MealLog.load(directory / LOG_FILE),
            profile=Profile.load(directory / PROFILE_FILE),
            root=repo_root(),
        )

    def custom_foods(self) -> list[Food]:
        if not self.custom_foods_path.exists():
            return []
        raw = json.loads(self.custom_foods_path.read_text(encoding="utf-8"))
        return [Food.from_dict(item) for item in raw.get("foods", [])]

    def save_custom_food(self, food: Food) -> Path:
        existing = [item for item in self.custom_foods() if item.id != food.id]
        existing.append(food)
        existing.sort(key=lambda item: item.id)
        payload = {
            "version": 1,
            "basis_grams": 100,
            "note": "Custom foods added via `nutritrack food add`.",
            "foods": [item.to_dict() for item in existing],
        }
        self.custom_foods_path.parent.mkdir(parents=True, exist_ok=True)
        self.custom_foods_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        self.db.add(food, overwrite=True)
        return self.custom_foods_path

    def save_log(self) -> Path:
        return self.log.save(self.log_path)

    def save_profile(self) -> Path:
        return self.profile.save(self.profile_path)
