"""Build compact, on-demand static data for the ATP Power Ratings site.

The landing payload stays small. Player profiles and tournament draws are emitted as
separate JSON documents, allowing GitHub Pages to serve a 32k-match project without
asking every visitor to download the whole ledger before they click a player.
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from model import (
    DISPLAY_CENTRE, DISPLAY_SCALE, GAME_SCALE, HALF_LIFE_DAYS,
    MATCH_EVIDENCE_CAP_GAMES, MIN_MATCHES, ROLLING_WINDOW_DAYS,
    fit_power_ratings, score_to_games,
)

CURRENT = Path("data/current")
SITE = Path("data/site")
ROUND_ORDER = {"F": 99, "SF": 90, "QF": 80, "R16": 70, "R32": 60, "R64": 50, "R128": 40,
               "RR": 30, "BR": 20, "Q1": 10, "Q2": 11, "Q3": 12}


def clean(value):
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def token(value: object) -> str:
    return hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:16]


def record(frame: pd.DataFrame) -> dict:
    """A completed-match record from player-perspective rows."""
    if frame.empty:
        return {"matches": 0, "wins": 0, "losses": 0, "gamesFor": 0, "gamesAgainst": 0, "winPct": None}
    games_for = int(frame.games_for.sum())
    games_against = int(frame.games_against.sum())
    wins = int(frame.won.sum())
    matches = int(len(frame))
    return {
        "matches": matches, "wins": wins, "losses": matches - wins,
        "gamesFor": games_for, "gamesAgainst": games_against,
        "winPct": round(100 * wins / matches, 1) if matches else None,
    }


def game_probability(power_a: float, power_b: float) -> float:
    return 1 / (1 + math.exp(-((power_a - power_b) / DISPLAY_SCALE) / GAME_SCALE))


def set_win_probability(game_p: float) -> float:
    """Independent-game approximation for a conventional tiebreak set."""
    p = min(max(float(game_p), 1e-8), 1 - 1e-8)
    q = 1 - p
    before_five_all = sum(math.comb(5 + losses, losses) * p**6 * q**losses for losses in range(5))
    at_five_all = math.comb(10, 5) * p**5 * q**5
    return before_five_all + at_five_all * (p**2 + 2 * p * q * p)


def match_win_probability(game_p: float, best_of: int) -> float:
    """Approximate Bo3/Bo5 win chance from the model's game probability."""
    set_p = set_win_probability(game_p)
    q = 1 - set_p
    if int(best_of or 3) >= 5:
        return set_p**3 + 3 * set_p**3 * q + 6 * set_p**3 * q**2
    return set_p**2 + 2 * set_p**2 * q


def perspective_rows(matches: pd.DataFrame, power_by_id: dict[str, float]) -> dict[str, pd.DataFrame]:
    """Index each completed scoreline twice: once for each player's profile."""
    buckets: dict[str, list[dict]] = defaultdict(list)
    for row in matches.itertuples(index=False):
        if str(row.status) != "completed":
            continue
        winner_games, loser_games = score_to_games(row.score)
        if not winner_games or not loser_games:
            continue
        base = {
            "date": str(row.date), "event": str(row.event_name), "eventId": str(row.event_id),
            "eventType": str(row.event_type), "round": str(row.round), "surface": str(row.surface),
            "bestOf": int(row.best_of or 3), "score": str(row.score), "status": str(row.status),
        }
        winner_id, loser_id = str(row.winner_id), str(row.loser_id)
        winner_name, loser_name = str(row.winner_name), str(row.loser_name)
        buckets[winner_id].append({**base, "won": True, "opponent": loser_name, "opponentId": loser_id,
                                   "games_for": winner_games, "games_against": loser_games,
                                   "opponentPower": int(round(power_by_id.get(loser_id, DISPLAY_CENTRE)))})
        buckets[loser_id].append({**base, "won": False, "opponent": winner_name, "opponentId": winner_id,
                                  "games_for": loser_games, "games_against": winner_games,
                                  "opponentPower": int(round(power_by_id.get(winner_id, DISPLAY_CENTRE)))})
    return {player_id: pd.DataFrame(rows) for player_id, rows in buckets.items()}


def performance_power(row: pd.Series) -> int:
    total = float(row.games_for + row.games_against)
    share = min(max(float(row.games_for) / total, 0.025), 0.975)
    return int(round(float(row.opponentPower) + DISPLAY_SCALE * GAME_SCALE * math.log(share / (1 - share))))


def make_trend(rows: pd.DataFrame, current_power: int) -> list[dict]:
    """A transparent smoothed match-performance trend, not a historical refit."""
    if rows.empty:
        return []
    frame = rows.copy()
    frame["month"] = pd.to_datetime(frame.date, errors="coerce").dt.to_period("M").astype(str)
    frame["performance"] = frame.apply(performance_power, axis=1)
    trend, previous = [], None
    for month, group in frame.sort_values("date").groupby("month", sort=True):
        average = float(group.performance.mean())
        previous = average if previous is None else 0.62 * previous + 0.38 * average
        trend.append({"month": month, "power": int(round(previous)), "matches": int(len(group))})
    if trend:
        trend[-1]["currentPower"] = current_power
    return trend[-18:]


def profile_for(player: dict, rows: pd.DataFrame) -> dict:
    completed = rows.sort_values("date", ascending=False, kind="stable").copy() if not rows.empty else rows
    surface = {name: record(group) for name, group in completed.groupby("surface", dropna=False)} if not completed.empty else {}
    levels = {name: record(group) for name, group in completed.groupby("eventType", dropna=False)} if not completed.empty else {}
    wins = completed[completed.won].sort_values(["opponentPower", "date"], ascending=False, kind="stable").head(5)
    losses = completed[~completed.won].sort_values(["opponentPower", "date"], ascending=False, kind="stable").head(5)

    def compact(frame: pd.DataFrame) -> list[dict]:
        if frame.empty:
            return []
        fields = ["date", "event", "eventId", "eventType", "round", "surface", "bestOf", "score", "won", "opponent", "opponentId", "opponentPower", "games_for", "games_against"]
        return [{key: clean(row[key]) for key in fields} | {"performancePower": performance_power(row)} for _, row in frame.iterrows()]

    h2h = []
    if not completed.empty:
        for opponent_id, group in completed.groupby("opponentId", sort=False):
            summary = record(group)
            h2h.append({"opponentId": str(opponent_id), "opponent": str(group.iloc[0].opponent), **summary})
        h2h.sort(key=lambda item: (item["matches"], item["wins"]), reverse=True)

    return {
        "player": player,
        "record": record(completed), "surfaceRecords": surface, "levelRecords": levels,
        "recentMatches": compact(completed.head(14)), "bestWins": compact(wins), "toughLosses": compact(losses),
        "headToHead": h2h,
        "trend": make_trend(completed, player["rating"]),
        "trendNote": "Smoothed match-performance Power against opponents' current model ratings. It is not a historical refit of the full model.",
    }


def compact_event_match(row) -> dict:
    return {
        "date": str(row.date), "round": str(row.round), "winner": str(row.winner_name), "winnerId": str(row.winner_id),
        "loser": str(row.loser_name), "loserId": str(row.loser_id), "score": str(row.score), "status": str(row.status),
        "bestOf": int(row.best_of or 3), "surface": str(row.surface),
    }


def model_health(matches: pd.DataFrame, ratings: pd.DataFrame, status: dict) -> dict:
    power = {str(row.player_id): float(row.power) for row in ratings.itertuples(index=False)}
    diagnostics = []
    for row in matches.itertuples(index=False):
        if str(row.status) != "completed" or str(row.winner_id) not in power or str(row.loser_id) not in power:
            continue
        winner_games, loser_games = score_to_games(row.score)
        if not winner_games or not loser_games:
            continue
        game_p = game_probability(power[str(row.winner_id)], power[str(row.loser_id)])
        expected = match_win_probability(game_p, int(row.best_of or 3))
        diagnostics.append({"p": expected, "surface": str(row.surface),
                            "gameError": abs(winner_games / (winner_games + loser_games) - game_p)})
    frame = pd.DataFrame(diagnostics)
    bins = []
    if not frame.empty:
        calibration_rows = pd.DataFrame({
            "prediction": list(frame.p) + list(1 - frame.p),
            "outcome": [1.0] * len(frame) + [0.0] * len(frame),
        })
        for lower in [0, .2, .4, .6, .8]:
            upper = lower + .2
            group = calibration_rows[(calibration_rows.prediction >= lower) & (calibration_rows.prediction < upper if upper < 1 else calibration_rows.prediction <= upper)]
            if group.empty:
                continue
            bins.append({"label": f"{lower:.0%}–{upper:.0%}", "matches": int(len(group) / 2),
                         "meanPredicted": round(float(group.prediction.mean()), 3),
                         "actualWinRate": round(float(group.outcome.mean()), 3)})
        brier = sum((p - 1) ** 2 + ((1 - p) - 0) ** 2 for p in frame.p) / (2 * len(frame))
        log_loss = -sum(math.log(max(p, 1e-9)) + math.log(max(p, 1e-9)) for p in frame.p) / (2 * len(frame))
        by_surface = [{"surface": name, "matches": int(len(group)), "meanGameShareError": round(float(group.gameError.mean()), 3)}
                      for name, group in frame.groupby("surface", dropna=False)]
    else:
        brier = log_loss = None
        bins, by_surface = [], []
    statuses = Counter(matches.status.astype(str))
    return {
        "label": "In-sample diagnostic", "note": "These figures use the current fitted ratings on the imported ledger. They check internal fit, not future forecasting skill; a time-split backtest is the next model-validation layer.",
        "eligibleMatches": int(len(frame)), "brierScore": round(float(brier), 4) if brier is not None else None,
        "logLoss": round(float(log_loss), 4) if log_loss is not None else None,
        "meanGameShareError": round(float(frame.gameError.mean()), 3) if not frame.empty else None,
        "calibration": bins, "surfaceDiagnostics": sorted(by_surface, key=lambda item: item["matches"], reverse=True),
        "quality": {"uniqueMatchRows": int(len(matches)), "completed": int(statuses.get("completed", 0)),
                    "retirements": int(statuses.get("retirement", 0)), "walkovers": int(statuses.get("walkover", 0)),
                    "scorelessCompleted": int(sum(not any(score_to_games(score)) for score in matches[matches.status == "completed"].score)),
                    "lastChecked": status.get("checked_at_utc"), "sourceFiles": status.get("source_files", [])},
    }


def main() -> None:
    matches = pd.read_csv(CURRENT / "matches.csv", dtype=str).fillna("")
    matches["best_of"] = pd.to_numeric(matches["best_of"], errors="coerce").fillna(3).astype(int)
    fitted = fit_power_ratings(str(CURRENT / "matches.csv"))
    ratings = fitted.ratings.copy()
    ratings["rank"] = range(1, len(ratings) + 1)
    rating_rows = []
    for _, row in ratings.iterrows():
        player_id = str(row.player_id)
        rating_rows.append({
            "rank": int(row["rank"]), "player": str(row.player), "playerId": player_id, "profileRef": f"players/{token(player_id)}.json",
            "rating": int(round(row.power)), "se": int(round(row.power_se)), "lo": int(round(row.ci95_low)), "hi": int(round(row.ci95_high)),
            "matches": int(row.matches), "wins": int(row.wins), "losses": int(row.losses), "gamesFor": int(row.games_for), "gamesAgainst": int(row.games_against),
            "qualified": bool(row.qualified),
        })
    power_by_id = {item["playerId"]: item["rating"] for item in rating_rows}

    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "players").mkdir(parents=True, exist_ok=True)
    (SITE / "events").mkdir(parents=True, exist_ok=True)
    by_player = perspective_rows(matches, power_by_id)
    for player in rating_rows:
        profile = profile_for(player, by_player.get(player["playerId"], pd.DataFrame()))
        (SITE / player["profileRef"]).write_text(json.dumps(profile, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")

    grouped = matches.groupby(["event_id", "event_name", "event_type", "surface", "indoor"], dropna=False)
    tournaments = []
    for keys, frame in grouped:
        event_id, name, event_class, surface, indoor = keys
        detail_ref = f"events/{token(f'{event_id}|{name}|{frame.date.min()}')}.json"
        sorted_frame = frame.sort_values(["date", "round", "winner_name"], ascending=False, kind="stable")
        rounds = []
        for round_name, group in sorted_frame.groupby("round", dropna=False, sort=False):
            rounds.append({"round": str(round_name) or "Unlabelled", "matches": [compact_event_match(row) for row in group.itertuples(index=False)]})
        rounds.sort(key=lambda item: ROUND_ORDER.get(item["round"], 0), reverse=True)
        final = next((item for item in rounds if item["round"] == "F" and item["matches"]), None)
        tournament = {"id": str(event_id), "name": str(name), "type": str(event_class), "surface": str(surface), "indoor": str(indoor),
                      "startDate": str(frame.date.min()), "endDate": str(frame.date.max()), "matches": int(len(frame)), "detailRef": detail_ref,
                      "champion": final["matches"][0]["winner"] if final else None}
        tournaments.append(tournament)
        detail = {**tournament, "rounds": rounds, "allMatches": [compact_event_match(row) for row in sorted_frame.itertuples(index=False)]}
        (SITE / detail_ref).write_text(json.dumps(detail, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
    tournaments.sort(key=lambda row: (row["endDate"], row["name"]), reverse=True)

    recent_matches = []
    for _, row in matches.sort_values(["date", "event_name"], ascending=False, kind="stable").head(250).iterrows():
        recent_matches.append({"date": str(row.date), "event": str(row.event_name), "eventId": str(row.event_id), "type": str(row.event_type),
                               "round": str(row["round"]), "winner": str(row.winner_name), "winnerId": str(row.winner_id), "loser": str(row.loser_name),
                               "loserId": str(row.loser_id), "score": str(row.score), "status": str(row.status), "bestOf": int(row.best_of)})
    status = json.loads((CURRENT / "sync_status.json").read_text(encoding="utf-8"))
    latest_date = str(matches.date.max())
    round_centre = {"headlineDate": latest_date, "sync": {key: status.get(key) for key in ("checked_at_utc", "new_matches", "corrected_matches", "matches", "events")},
                    "latestResults": recent_matches[:80], "featuredEvents": tournaments[:18],
                    "note": "Results are ordered by the source event date. The daily importer adds new scored matches and regenerates this centre."}
    health = model_health(matches, ratings, status)
    model = {"version": "ATP V1", "centre": DISPLAY_CENTRE, "displayScale": DISPLAY_SCALE, "gameScale": GAME_SCALE,
             "halfLifeDays": HALF_LIFE_DAYS, "rollingWindowDays": ROLLING_WINDOW_DAYS, "evidenceCapGames": MATCH_EVIDENCE_CAP_GAMES,
             "minimumMatches": MIN_MATCHES, "bestOfFiveRule": "Conventional-set games remain scoreline evidence, while every single match is capped at 28 game-equivalents so a five-set match is not treated as several independent matches. Match tiebreak points are excluded from game totals."}
    payload = {"meta": {"sport": "tennis", "circuit": "ATP only", "scope": "ATP Tour, Grand Slams, Challenger, ATP qualifying and men's singles in selected team/exhibition events",
                         "latestEvent": tournaments[0]["name"] if tournaments else None, "updatedAt": status.get("checked_at_utc"), "coverageStart": status.get("coverage_start"),
                         "coverageEnd": status.get("coverage_end"), "matches": status.get("matches"), "players": status.get("players"), "events": status.get("events"),
                         "newMatches": status.get("new_matches"), "correctedMatches": status.get("corrected_matches")},
               "model": model, "rankings": rating_rows, "tournaments": tournaments, "recentMatches": recent_matches, "eventCounts": status.get("event_counts", {}), "sync": status,
               "roundCentreRef": "round_centre.json", "modelHealthRef": "model_health.json"}
    (SITE / "tournaments.json").write_text(json.dumps(tournaments, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
    (SITE / "model.json").write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
    (SITE / "round_centre.json").write_text(json.dumps(round_centre, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
    (SITE / "model_health.json").write_text(json.dumps(health, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
    Path("data.js").write_text("window.ATP_RATINGS_DATA = " + json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"Wrote {len(rating_rows):,} player profiles and {len(tournaments):,} tournament draws")


if __name__ == "__main__":
    main()
