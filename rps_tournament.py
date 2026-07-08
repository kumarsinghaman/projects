#!/usr/bin/env python3
"""Minimum formation changes for POI to win a line-based RPS tournament."""

from __future__ import annotations

import sys


def beats(a: str, b: str) -> bool:
    return (a, b) in (("P", "R"), ("S", "P"), ("R", "S"))


def counter(formation: str) -> str:
    return {"R": "P", "P": "S", "S": "R"}[formation]


def min_changes(initial: str, required: list[str]) -> int:
    changes = 0
    current = initial
    for move in required:
        if move != current:
            changes += 1
            current = move
    return changes


def solve(n: int, poi: int, formations: str) -> int:
    if len(formations) != n:
        raise ValueError(f"expected {n} formations, got {len(formations)}")

    poi_idx = poi - 1
    if not 0 <= poi_idx < n:
        raise ValueError(f"POI index {poi} is out of range for {n} players")

    initial = formations[poi_idx]
    survivors = list(range(n))
    required_moves: list[str] = []

    while len(survivors) > 1:
        next_round: list[int] = []
        i = 0
        while i < len(survivors):
            if i == len(survivors) - 1:
                next_round.append(survivors[i])
                break

            p1, p2 = survivors[i], survivors[i + 1]
            f1, f2 = formations[p1], formations[p2]

            if p1 == poi_idx or p2 == poi_idx:
                opponent = p2 if p1 == poi_idx else p1
                required_moves.append(counter(formations[opponent]))
                next_round.append(poi_idx)
            elif f1 == f2:
                pass
            elif beats(f1, f2):
                next_round.append(p1)
            else:
                next_round.append(p2)

            i += 2

        survivors = next_round
        if not survivors:
            return -1

    if len(survivors) == 1 and survivors[0] == poi_idx:
        return min_changes(initial, required_moves)
    return -1


def main() -> None:
    data = sys.stdin.read().split()
    if not data:
        return

    n = int(data[0])
    poi = int(data[1])
    formations = data[2].upper()
    print(solve(n, poi, formations))


if __name__ == "__main__":
    main()
