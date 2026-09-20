"""ATP Power Ratings V1.

An opponent-adjusted, scoreline-aware rating for ATP-only professional singles.
The input is the normalised ``data/current/matches.csv`` written by sync_atp.py.

Unlike the BRTA model, this version explicitly supports best-of-five scorelines
and match tiebreaks.  Every conventional set game is still useful evidence, but
one unusually long match cannot count as several independent matches merely
because it used a longer format.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit

GAME_SCALE = 0.75
HALF_LIFE_DAYS = 300.0
ROLLING_WINDOW_DAYS = 3 * 365 + 1
MATCH_EVIDENCE_CAP_GAMES = 28.0
L2 = 5.0
DISPLAY_CENTRE = 1500.0
DISPLAY_SCALE = 600.0
MIN_MATCHES = 8


def centred_covariance(covariance: np.ndarray) -> np.ndarray:
    """Project covariance onto the same mean-zero scale used for ratings."""
    n = covariance.shape[0]
    projection = np.eye(n) - np.ones((n, n)) / n
    return projection @ covariance @ projection.T


def score_to_games(score: object) -> tuple[int, int]:
    """Return conventional-set games for a winner-first tennis score.

    Match tiebreaks such as ``[10-8]`` or ``[8-10]`` decide the match but are
    points, not games; they are deliberately excluded from the game likelihood.
    This works for standard ATP scores, Laver Cup match tiebreaks and Hopman Cup
    third-set match tiebreaks.
    """
    cleaned = re.sub(r"\[[^\]]*\]", "", str(score or ""))
    totals = [0, 0]
    for left, right in re.findall(r"(\d+)\s*-\s*(\d+)", cleaned):
        totals[0] += int(left)
        totals[1] += int(right)
    return tuple(totals)


def _as_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True).dt.tz_convert(None)


def prepare_matches(df: pd.DataFrame) -> pd.DataFrame:
    """Validate rows, retain rolling ATP-only completed singles and add games."""
    required = {"date", "winner_id", "loser_id", "winner_name", "loser_name", "score", "status"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing model columns: {sorted(missing)}")
    out = df.copy()
    out["match_date"] = _as_date(out["date"])
    out = out[out["status"].astype(str).str.casefold().eq("completed")].copy()
    out = out.dropna(subset=["match_date", "winner_id", "loser_id"])
    out = out[(out["winner_id"].astype(str) != "") & (out["loser_id"].astype(str) != "")].copy()
    games = out["score"].map(score_to_games)
    out["winner_games"] = games.map(lambda value: value[0])
    out["loser_games"] = games.map(lambda value: value[1])
    out = out[(out["winner_games"] > 0) & (out["loser_games"] > 0)].copy()
    reference = out["match_date"].max()
    out = out[out["match_date"] >= reference - pd.Timedelta(days=ROLLING_WINDOW_DAYS)].copy()
    if out.empty:
        raise ValueError("No rating-eligible ATP singles matches remain after validation")
    return out


@dataclass(frozen=True)
class ModelResult:
    ratings: pd.DataFrame
    reference_date: pd.Timestamp
    matches: int


def fit_power_ratings_from_df(df: pd.DataFrame) -> ModelResult:
    """Fit scoreline-only likelihood; match wins are never counted twice."""
    matches = prepare_matches(df)
    players = sorted(set(matches["winner_id"].astype(str)) | set(matches["loser_id"].astype(str)))
    index = {player: position for position, player in enumerate(players)}
    n = len(players)
    winner = matches["winner_id"].astype(str).map(index).to_numpy()
    loser = matches["loser_id"].astype(str).map(index).to_numpy()
    winner_games = matches["winner_games"].astype(float).to_numpy()
    loser_games = matches["loser_games"].astype(float).to_numpy()
    total_games = winner_games + loser_games
    # Long best-of-five matches provide extra scoreline information, but one
    # match is capped at roughly a competitive long best-of-three's worth.
    evidence = np.minimum(1.0, MATCH_EVIDENCE_CAP_GAMES / total_games)
    reference = matches["match_date"].max()
    age_days = (reference - matches["match_date"]).dt.days.to_numpy()
    recency = 2.0 ** (-np.maximum(age_days, 0) / HALF_LIFE_DAYS)
    weight = recency * evidence

    def objective_and_gradient(theta: np.ndarray) -> tuple[float, np.ndarray]:
        probability = expit((theta[winner] - theta[loser]) / GAME_SCALE)
        eps = 1e-12
        log_likelihood = winner_games * np.log(probability + eps) + loser_games * np.log(1 - probability + eps)
        objective = weight @ log_likelihood - (L2 / 2.0) * np.sum(theta**2)
        contribution = -weight * (winner_games - total_games * probability) / GAME_SCALE
        gradient = L2 * theta.copy()
        np.add.at(gradient, winner, contribution)
        np.add.at(gradient, loser, -contribution)
        return -objective, gradient

    result = minimize(
        objective_and_gradient,
        np.zeros(n),
        jac=True,
        method="L-BFGS-B",
        options={"maxiter": 4000, "ftol": 1e-12},
    )
    if not result.success:
        raise RuntimeError(f"ATP rating optimisation failed: {result.message}")

    theta = result.x.copy()
    theta -= theta.mean()
    power = DISPLAY_CENTRE + DISPLAY_SCALE * theta
    probability = expit((theta[winner] - theta[loser]) / GAME_SCALE)
    curvature = weight * total_games * probability * (1 - probability) / (GAME_SCALE**2)
    hessian = L2 * np.eye(n)
    for left, right, value in zip(winner, loser, curvature):
        hessian[left, left] += value
        hessian[right, right] += value
        hessian[left, right] -= value
        hessian[right, left] -= value
    covariance = centred_covariance(np.linalg.inv(hessian))
    standard_error = DISPLAY_SCALE * np.sqrt(np.clip(np.diag(covariance), 0, None))

    names: dict[str, str] = {}
    for _, row in matches.iterrows():
        names.setdefault(str(row.winner_id), str(row.winner_name))
        names.setdefault(str(row.loser_id), str(row.loser_name))
    rows = []
    for player in players:
        player_matches = matches[(matches.winner_id.astype(str) == player) | (matches.loser_id.astype(str) == player)]
        wins = int((player_matches.winner_id.astype(str) == player).sum())
        games_for = games_against = 0
        for _, row in player_matches.iterrows():
            did_win = str(row.winner_id) == player
            games_for += int(row.winner_games if did_win else row.loser_games)
            games_against += int(row.loser_games if did_win else row.winner_games)
        position = index[player]
        rows.append({
            "player_id": player,
            "player": names.get(player, player),
            "matches": int(len(player_matches)),
            "wins": wins,
            "losses": int(len(player_matches) - wins),
            "games_for": games_for,
            "games_against": games_against,
            "power": float(power[position]),
            "power_se": float(standard_error[position]),
            "ci95_low": float(power[position] - 1.96 * standard_error[position]),
            "ci95_high": float(power[position] + 1.96 * standard_error[position]),
        })
    ratings = pd.DataFrame(rows).sort_values("power", ascending=False, kind="stable").reset_index(drop=True)
    ratings["qualified"] = ratings["matches"] >= MIN_MATCHES
    return ModelResult(ratings=ratings, reference_date=reference, matches=len(matches))


def fit_power_ratings(csv_path: str) -> ModelResult:
    return fit_power_ratings_from_df(pd.read_csv(csv_path))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fit ATP Power Ratings from normalised ATP-only singles data.")
    parser.add_argument("csv", nargs="?", default="data/current/matches.csv")
    parser.add_argument("--all", action="store_true", help="include provisional rows")
    args = parser.parse_args()
    fitted = fit_power_ratings(args.csv)
    output = fitted.ratings if args.all else fitted.ratings[fitted.ratings.qualified]
    print(output.to_string(index=False, formatters={"power": "{:.0f}".format, "power_se": "{:.0f}".format}))
