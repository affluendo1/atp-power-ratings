"""Daily ATP-only result ingestion for ATP Power Ratings.

Primary source: https://stats.tennismylife.org/api/data-files
That index exposes separate ATP Tour, ATP Challenger and ATP qualifying CSVs.
The importer never requests WTA files.  Project-maintained supplements cover
men's singles at Laver Cup and Hopman Cup, whose results are not consistently
present in the ATP stream.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from datetime import date, datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

API_URL = "https://stats.tennismylife.org/api/data-files"
ROOT = Path("data")
CURRENT = ROOT / "current"
MANUAL = ROOT / "manual"
MATCHES_PATH = CURRENT / "matches.csv"
STATUS_PATH = CURRENT / "sync_status.json"
CHECK_PATH = CURRENT / "last_check.json"
REPORT_PATH = CURRENT / "sync_report.md"
SPECIAL_PATH = MANUAL / "special_events.csv"
YEARS_BACK = 3
HTTP_TIMEOUT = 60


def canonical_text(value: object) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(character for character in value if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def player_key(player_id: object, name: object) -> str:
    raw = str(player_id or "").strip()
    if raw and raw.casefold() not in {"nan", "none"}:
        return f"atp:{raw}"
    return f"name:{canonical_text(name)}"


def score_to_games(score: object) -> tuple[int, int]:
    cleaned = re.sub(r"\[[^\]]*\]", "", str(score or ""))
    totals = [0, 0]
    for left, right in re.findall(r"(\d+)\s*-\s*(\d+)", cleaned):
        totals[0] += int(left)
        totals[1] += int(right)
    return tuple(totals)


def classify_status(score: object) -> str:
    text = str(score or "").casefold()
    if any(token in text for token in ("w/o", "walkover", "not played", "cancelled")):
        return "walkover"
    if any(token in text for token in ("ret", "retired", "def.")):
        return "retirement"
    return "completed"


def source_kind(filename: str) -> str | None:
    lowered = filename.casefold()
    if "wta" in lowered:
        return None
    if re.fullmatch(r"20\d{2}\.csv", filename):
        return "atp_tour"
    if re.fullmatch(r"20\d{2}_challenger\.csv", filename):
        return "challenger"
    if re.fullmatch(r"atp_quali/20\d{2}_atp_quali\.csv", filename):
        return "qualifying"
    if filename == "ongoing_tourneys.csv":
        return "atp_tour_live"
    if filename == "ch_ongoing_tourney.csv":
        return "challenger_live"
    return None


def event_type(name: object, level: object, kind: str) -> str:
    label = str(name or "").casefold()
    level = str(level or "").casefold()
    if "laver cup" in label:
        return "Laver Cup"
    if "hopman cup" in label:
        return "Hopman Cup"
    if "united cup" in label:
        return "United Cup"
    if "davis cup" in label or level == "d":
        return "Davis Cup"
    if "tour finals" in label or "atp finals" in label or level == "f":
        return "ATP Finals"
    if level == "g":
        return "Grand Slam"
    if kind.startswith("challenger"):
        return "Challenger"
    if kind == "qualifying":
        return "ATP Tour Qualifying"
    return "ATP Tour"


def safe_get(url: str) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = requests.get(url, timeout=HTTP_TIMEOUT, headers={"User-Agent": "ATP-Power-Ratings/1.0"})
            response.raise_for_status()
            return response
        except requests.RequestException as error:
            last_error = error
            if attempt == 2:
                break
    raise RuntimeError(f"Could not download {url}: {last_error}")


def select_source_files(index: dict) -> list[dict]:
    today = date.today()
    earliest_year = today.year - YEARS_BACK
    selected = []
    for entry in index.get("files", []):
        name = str(entry.get("name", ""))
        kind = source_kind(name)
        if kind is None:
            continue
        match = re.search(r"(20\d{2})", name)
        if match and int(match.group(1)) < earliest_year:
            continue
        selected.append({"name": name, "url": entry["url"], "kind": kind})
    if not selected:
        raise RuntimeError("The ATP source index supplied no eligible ATP-only files")
    return selected


def normalise_source_frame(frame: pd.DataFrame, descriptor: dict) -> pd.DataFrame:
    required = {"tourney_name", "tourney_date", "winner_name", "loser_name", "score"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{descriptor['name']} is missing required columns: {sorted(missing)}")
    out = pd.DataFrame()
    out["date"] = pd.to_datetime(frame["tourney_date"].astype(str), format="%Y%m%d", errors="coerce").dt.strftime("%Y-%m-%d")
    out["event_id"] = frame.get("tourney_id", "").fillna("").astype(str)
    out["event_name"] = frame["tourney_name"].fillna("").astype(str)
    out["event_type"] = [event_type(name, level, descriptor["kind"]) for name, level in zip(out.event_name, frame.get("tourney_level", ""))]
    out["surface"] = frame.get("surface", "Unknown").fillna("Unknown").astype(str)
    out["indoor"] = frame.get("indoor", "").fillna("").astype(str)
    out["best_of"] = pd.to_numeric(frame.get("best_of", 3), errors="coerce").fillna(3).astype(int)
    out["round"] = frame.get("round", "").fillna("").astype(str)
    out["winner_name"] = frame["winner_name"].fillna("").astype(str)
    out["loser_name"] = frame["loser_name"].fillna("").astype(str)
    out["winner_id"] = [player_key(identifier, name) for identifier, name in zip(frame.get("winner_id", ""), out.winner_name)]
    out["loser_id"] = [player_key(identifier, name) for identifier, name in zip(frame.get("loser_id", ""), out.loser_name)]
    out["score"] = frame["score"].fillna("").astype(str)
    out["status"] = out["score"].map(classify_status)
    out["source_file"] = descriptor["name"]
    out["source_url"] = descriptor["url"]
    return out


def load_primary_source() -> tuple[pd.DataFrame, list[dict]]:
    index = safe_get(API_URL).json()
    descriptors = select_source_files(index)
    frames = []
    for descriptor in descriptors:
        raw = safe_get(descriptor["url"]).text
        frames.append(normalise_source_frame(pd.read_csv(StringIO(raw), low_memory=False), descriptor))
    return pd.concat(frames, ignore_index=True), descriptors


def load_manual_special_events() -> pd.DataFrame:
    if not SPECIAL_PATH.exists():
        return pd.DataFrame()
    manual = pd.read_csv(SPECIAL_PATH, dtype=str).fillna("")
    if manual.empty:
        return pd.DataFrame()
    expected = {"date", "event_id", "event_name", "event_type", "surface", "indoor", "best_of", "round", "winner_name", "loser_name", "score", "status", "source_url"}
    missing = expected.difference(manual.columns)
    if missing:
        raise ValueError(f"special_events.csv is missing columns: {sorted(missing)}")
    manual["winner_id"] = [f"name:{canonical_text(name)}" for name in manual.winner_name]
    manual["loser_id"] = [f"name:{canonical_text(name)}" for name in manual.loser_name]
    manual["source_file"] = "manual/special_events.csv"
    return manual


def reconcile_manual_player_ids(primary: pd.DataFrame, manual: pd.DataFrame) -> pd.DataFrame:
    """Map manual-source names to official ATP IDs where an ATP source knows them."""
    lookup: dict[str, str] = {}
    for identifier, name in pd.concat([
        primary[["winner_id", "winner_name"]].rename(columns={"winner_id": "id", "winner_name": "name"}),
        primary[["loser_id", "loser_name"]].rename(columns={"loser_id": "id", "loser_name": "name"}),
    ]).drop_duplicates().itertuples(index=False):
        lookup.setdefault(canonical_text(name), identifier)
    for side in ("winner", "loser"):
        manual[f"{side}_id"] = [lookup.get(canonical_text(name), identifier) for name, identifier in zip(manual[f"{side}_name"], manual[f"{side}_id"])]
    return manual


def deduplicate(rows: pd.DataFrame) -> pd.DataFrame:
    rows = rows.copy()
    rows = rows.dropna(subset=["date"])
    rows = rows[(rows.winner_name != "") & (rows.loser_name != "")].copy()
    priority = {"manual/special_events.csv": 4}
    rows["_priority"] = rows.source_file.map(priority).fillna(1)
    special_events = {"Laver Cup", "Hopman Cup"}
    # The ATP feed stores a tournament-week date while the official
    # supplementary ledger stores the actual match day.  For these two events,
    # use event season + players + score, so the same real match is merged
    # rather than displayed twice with two harmlessly different dates.
    event_identity = [
        f"special:{event_class}:{str(day)[:4]}" if str(event_class) in special_events else f"event:{event}:{day}"
        for event_class, event, day in zip(rows.event_type, rows.event_id, rows.date)
    ]
    rows["match_id"] = [hashlib.sha1(
        "|".join([identity, str(round_name), *sorted([str(winner), str(loser)]), str(score)]).encode("utf-8")
    ).hexdigest()[:20] for identity, round_name, winner, loser, score in zip(
        event_identity, rows["round"], rows.winner_id, rows.loser_id, rows.score
    )]
    rows = rows.sort_values(["match_id", "_priority"], ascending=[True, False], kind="stable").drop_duplicates("match_id", keep="first")
    earliest = (pd.Timestamp.utcnow().normalize() - pd.DateOffset(years=YEARS_BACK)).strftime("%Y-%m-%d")
    rows = rows[rows.date >= earliest].copy()
    return rows.drop(columns=["_priority"]).sort_values(["date", "event_name", "match_id"], kind="stable").reset_index(drop=True)


def content_signature(frame: pd.DataFrame) -> dict[str, str]:
    fields = ["match_id", "winner_id", "loser_id", "score", "status", "event_type"]
    return {row.match_id: hashlib.sha1("|".join(str(getattr(row, field)) for field in fields[1:]).encode("utf-8")).hexdigest()
            for row in frame[fields].itertuples(index=False)}


def write_report(rows: pd.DataFrame, previous: pd.DataFrame | None, descriptors: list[dict]) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    old = content_signature(previous) if previous is not None and not previous.empty else {}
    new = content_signature(rows)
    added = sorted(set(new).difference(old))
    corrected = sorted(match for match in set(new).intersection(old) if new[match] != old[match])
    counts = Counter(rows.event_type)
    report = {
        "checked_at_utc": now,
        "new_results": bool(added or corrected),
        "new_matches": len(added),
        "corrected_matches": len(corrected),
        "matches": int(len(rows)),
        "players": int(len(set(rows.winner_id) | set(rows.loser_id))),
        "events": int(rows.event_id.nunique()),
        "coverage_start": str(rows.date.min()),
        "coverage_end": str(rows.date.max()),
        "event_counts": dict(sorted(counts.items())),
        "source_files": [descriptor["name"] for descriptor in descriptors],
        "manual_special_matches": int((rows.source_file == "manual/special_events.csv").sum()),
    }
    lines = [
        "# ATP Power Ratings sync report",
        "",
        f"Checked (UTC): {now}",
        f"Coverage: {report['coverage_start']} to {report['coverage_end']}",
        f"Results indexed: {report['matches']:,}",
        f"Players: {report['players']:,}",
        f"Events: {report['events']:,}",
        f"New matches: {report['new_matches']:,}",
        f"Corrected matches: {report['corrected_matches']:,}",
        f"Manual men's-special-event matches: {report['manual_special_matches']:,}",
        "", "## Event coverage",
    ]
    lines += [f"- {name}: {count:,}" for name, count in report["event_counts"].items()]
    lines += ["", "## Source files", *[f"- {name}" for name in report["source_files"]]]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> None:
    CURRENT.mkdir(parents=True, exist_ok=True)
    previous = pd.read_csv(MATCHES_PATH, dtype=str).fillna("") if MATCHES_PATH.exists() else None
    primary, descriptors = load_primary_source()
    manual = load_manual_special_events()
    if not manual.empty:
        manual = reconcile_manual_player_ids(primary, manual)
        primary = pd.concat([primary, manual], ignore_index=True)
    rows = deduplicate(primary)
    if rows.empty:
        raise RuntimeError("Sync produced no ATP-only result rows")
    rows.to_csv(MATCHES_PATH, index=False)
    report = write_report(rows, previous, descriptors)
    STATUS_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    CHECK_PATH.write_text(json.dumps({
        "checked_at_utc": report["checked_at_utc"],
        "new_results": report["new_results"],
        "new_matches": report["new_matches"],
        "corrected_matches": report["corrected_matches"],
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
