"""Turn normalised ATP-only results and model output into static-site data."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from model import (
    DISPLAY_CENTRE, DISPLAY_SCALE, GAME_SCALE, HALF_LIFE_DAYS,
    MATCH_EVIDENCE_CAP_GAMES, MIN_MATCHES, ROLLING_WINDOW_DAYS, fit_power_ratings,
)

CURRENT = Path("data/current")
SITE = Path("data/site")


def clean(value):
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def main() -> None:
    matches = pd.read_csv(CURRENT / "matches.csv", dtype=str).fillna("")
    fitted = fit_power_ratings(str(CURRENT / "matches.csv"))
    ratings = fitted.ratings.copy()
    ratings["rank"] = range(1, len(ratings) + 1)
    rating_rows = []
    for _, row in ratings.iterrows():
        rating_rows.append({
            "rank": int(row["rank"]), "player": str(row.player), "playerId": str(row.player_id),
            "rating": int(round(row.power)), "se": int(round(row.power_se)),
            "lo": int(round(row.ci95_low)), "hi": int(round(row.ci95_high)),
            "matches": int(row.matches), "wins": int(row.wins), "losses": int(row.losses),
            "gamesFor": int(row.games_for), "gamesAgainst": int(row.games_against),
            "qualified": bool(row.qualified),
        })

    grouped = matches.groupby(["event_id", "event_name", "event_type", "surface", "indoor"], dropna=False)
    tournaments = []
    for keys, frame in grouped:
        event_id, name, event_class, surface, indoor = keys
        tournaments.append({
            "id": str(event_id), "name": str(name), "type": str(event_class), "surface": str(surface),
            "indoor": str(indoor), "startDate": str(frame.date.min()), "endDate": str(frame.date.max()),
            "matches": int(len(frame)),
        })
    tournaments.sort(key=lambda row: (row["endDate"], row["name"]), reverse=True)
    recent_matches = []
    for _, row in matches.sort_values(["date", "event_name"], ascending=False, kind="stable").head(150).iterrows():
        recent_matches.append({
            "date": str(row.date), "event": str(row.event_name), "type": str(row.event_type),
            "round": str(row["round"]), "winner": str(row.winner_name), "loser": str(row.loser_name),
            "score": str(row.score), "status": str(row.status),
        })
    status = json.loads((CURRENT / "sync_status.json").read_text(encoding="utf-8"))
    model = {
        "version": "ATP V1", "centre": DISPLAY_CENTRE, "displayScale": DISPLAY_SCALE,
        "gameScale": GAME_SCALE, "halfLifeDays": HALF_LIFE_DAYS,
        "rollingWindowDays": ROLLING_WINDOW_DAYS, "evidenceCapGames": MATCH_EVIDENCE_CAP_GAMES,
        "minimumMatches": MIN_MATCHES,
        "bestOfFiveRule": "Conventional-set games remain scoreline evidence, while every single match is capped at 28 game-equivalents so a five-set match is not treated as several independent matches. Match tiebreak points are excluded from game totals.",
    }
    payload = {
        "meta": {
            "sport": "tennis", "circuit": "ATP only", "scope": "ATP Tour, Grand Slams, Challenger, ATP qualifying and men's singles in selected team/exhibition events",
            "latestEvent": tournaments[0]["name"] if tournaments else None,
            "updatedAt": status.get("checked_at_utc"), "coverageStart": status.get("coverage_start"),
            "coverageEnd": status.get("coverage_end"), "matches": status.get("matches"),
            "players": status.get("players"), "events": status.get("events"),
            "newMatches": status.get("new_matches"), "correctedMatches": status.get("corrected_matches"),
        },
        "model": model,
        "rankings": rating_rows,
        "tournaments": tournaments,
        "recentMatches": recent_matches,
        "eventCounts": status.get("event_counts", {}),
        "sync": status,
    }
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "tournaments.json").write_text(json.dumps(tournaments, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
    (SITE / "model.json").write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
    Path("data.js").write_text("window.ATP_RATINGS_DATA = " + json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"Wrote {len(rating_rows):,} player ratings and {len(tournaments):,} tournaments")


if __name__ == "__main__":
    main()
