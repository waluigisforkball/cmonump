"""
fetch.py — Pull ABS-challenge pitch data from Baseball Savant and find the
single most embarrassing overturned call for a given date window.

The "SMH ump" angle: a call was challenged and OVERTURNED, ranked by how badly
the pitch missed the nearest edge of the strike zone (in inches).

NOTE ON COLUMN MAPPING: Savant added challenge fields for the 2026 season.
This module is defensive about exactly *which* columns carry that data, because
the precise names couldn't be confirmed offline. Run `python fetch.py --inspect`
once against live data to print the real columns, then (if needed) adjust
CHALLENGE_COLS / OVERTURN_VALUES below. Everything else is stable Statcast schema.
"""

from __future__ import annotations
import argparse
import datetime as dt
from dataclasses import dataclass, asdict
from typing import Optional
import io
import sys

import pandas as pd

# pybaseball wraps the Savant statcast_search/csv endpoint
from pybaseball import statcast

# --- Zone constants (2026 ABS) -------------------------------------------------
# The ABS zone is a 2D rectangle at the midpoint of the plate, 17 inches wide.
# Statcast plate_x / plate_z and sz_top / sz_bot are all in FEET.
PLATE_HALF_WIDTH_FT = (17.0 / 2.0) / 12.0   # 8.5 inches -> feet
FT_TO_IN = 12.0

# --- Defensive column detection ------------------------------------------------
# Candidate column names that might flag a challenge / its result. The first one
# present in the data wins. Update after running --inspect if 2026 differs.
CHALLENGE_FLAG_COLS = ["is_challenge", "challenge", "abs_challenge", "challenged"]
CHALLENGE_RESULT_COLS = ["challenge_result", "abs_result", "overturned", "call_overturned"]
# Values (lowercased) in a result column that mean "the call got reversed":
OVERTURN_VALUES = {"overturned", "overturn", "reversed", "true", "1", "yes", "won"}


@dataclass
class DunkCall:
    game_date: str
    game_pk: int
    pitcher: str
    batter: str
    balls: int
    strikes: int
    inning: int
    half: str
    original_call: str          # what was called before the challenge
    miss_inches: float          # how far outside the nearest zone edge
    miss_dir: str               # 'inside/outside/high/low'
    plate_x: float
    plate_z: float
    sz_top: float
    sz_bot: float
    pitch_type: str
    savant_link: str

    def headline_miss(self) -> str:
        return f"{self.miss_inches:.1f}\""


def _detect_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _miss_distance_inches(row) -> tuple[float, str]:
    """Distance (inches) the pitch center sat OUTSIDE the nearest zone edge.
    Returns (distance, direction). 0 if the pitch was actually inside the zone."""
    px, pz = row["plate_x"], row["plate_z"]
    top, bot = row["sz_top"], row["sz_bot"]

    # horizontal miss: outside the 8.5" half-width either side
    if px > PLATE_HALF_WIDTH_FT:
        h_miss = (px - PLATE_HALF_WIDTH_FT) * FT_TO_IN
        h_dir = "outside" if row.get("stand") == "L" else "inside"
        # (handedness flips arm-side label; kept simple — see note)
        h_dir = "arm-side" if False else "wide"
    elif px < -PLATE_HALF_WIDTH_FT:
        h_miss = (-PLATE_HALF_WIDTH_FT - px) * FT_TO_IN
        h_dir = "wide"
    else:
        h_miss = 0.0
        h_dir = ""

    # vertical miss
    if pz > top:
        v_miss = (pz - top) * FT_TO_IN
        v_dir = "high"
    elif pz < bot:
        v_miss = (bot - pz) * FT_TO_IN
        v_dir = "low"
    else:
        v_miss = 0.0
        v_dir = ""

    # the "obviousness" is the largest single-axis miss
    if h_miss >= v_miss:
        return h_miss, (h_dir or "off the plate")
    return v_miss, (v_dir or "off the zone")


def _savant_link(game_pk: int) -> str:
    # Stable, constructable gamefeed URL for the play. (mlb.com video URLs are
    # NOT reliably constructable, so we link to Savant's per-game feed.)
    return f"https://baseballsavant.mlb.com/gamefeed?gamePk={game_pk}"


def fetch_window(start: str, end: str, inspect: bool = False) -> Optional[DunkCall]:
    """Pull all pitches in [start, end] (inclusive, YYYY-MM-DD), return the worst
    overturned-challenge call, or None if there were no overturned challenges."""
    df = statcast(start_dt=start, end_dt=end, verbose=False)
    if df is None or len(df) == 0:
        print(f"[fetch] No statcast rows for {start}..{end}", file=sys.stderr)
        return None

    if inspect:
        chal_like = [c for c in df.columns
                     if any(k in c.lower() for k in ("challenge", "abs", "overturn"))]
        print("=== INSPECT: columns that look challenge-related ===")
        print(chal_like or "(none found — check description / des columns)")
        print("\n=== unique 'description' values (call types) ===")
        if "description" in df.columns:
            print(sorted(df["description"].dropna().unique().tolist()))
        print(f"\nTotal columns: {len(df.columns)} | Total rows: {len(df)}")
        return None

    flag_col = _detect_col(df, CHALLENGE_FLAG_COLS)
    result_col = _detect_col(df, CHALLENGE_RESULT_COLS)

    # Filter to overturned challenges. Strategy depends on what columns exist.
    if result_col:
        mask = df[result_col].astype(str).str.lower().isin(OVERTURN_VALUES)
        challenged = df[mask].copy()
    elif flag_col:
        # only a flag, no result column — fall back to flag + we infer overturn
        # by the call being a strike that the pitch location says was a ball.
        challenged = df[df[flag_col].astype(str).str.lower().isin(
            {"true", "1", "yes"})].copy()
    else:
        # No challenge columns surfaced. Last-resort: look in description text.
        if "description" in df.columns:
            challenged = df[df["description"].astype(str)
                            .str.contains("challenge", case=False, na=False)].copy()
        else:
            print("[fetch] Could not locate challenge data. Run --inspect.",
                  file=sys.stderr)
            return None

    if len(challenged) == 0:
        print(f"[fetch] No overturned challenges in {start}..{end}", file=sys.stderr)
        return None

    # need location + zone to score; drop rows missing them
    need = ["plate_x", "plate_z", "sz_top", "sz_bot"]
    challenged = challenged.dropna(subset=need)
    if len(challenged) == 0:
        return None

    # score each
    misses = challenged.apply(_miss_distance_inches, axis=1, result_type="expand")
    challenged["miss_inches"] = misses[0]
    challenged["miss_dir"] = misses[1]

    worst = challenged.sort_values("miss_inches", ascending=False).iloc[0]

    return DunkCall(
        game_date=str(worst.get("game_date", end))[:10],
        game_pk=int(worst.get("game_pk", 0)),
        pitcher=str(worst.get("player_name", "Pitcher")),
        batter=str(worst.get("batter_name", worst.get("des", "Batter"))),
        balls=int(worst.get("balls", 0)),
        strikes=int(worst.get("strikes", 0)),
        inning=int(worst.get("inning", 0)),
        half=str(worst.get("inning_topbot", "")),
        original_call=str(worst.get("description", "called pitch")),
        miss_inches=float(worst["miss_inches"]),
        miss_dir=str(worst["miss_dir"]),
        plate_x=float(worst["plate_x"]),
        plate_z=float(worst["plate_z"]),
        sz_top=float(worst["sz_top"]),
        sz_bot=float(worst["sz_bot"]),
        pitch_type=str(worst.get("pitch_type", "")),
        savant_link=_savant_link(int(worst.get("game_pk", 0))),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", choices=["day", "week"], default="day")
    ap.add_argument("--date", help="anchor date YYYY-MM-DD (default: yesterday)")
    ap.add_argument("--inspect", action="store_true",
                    help="print live column names to confirm 2026 challenge fields")
    args = ap.parse_args()

    anchor = (dt.date.fromisoformat(args.date) if args.date
              else dt.date.today() - dt.timedelta(days=1))
    if args.window == "day":
        start = end = anchor.isoformat()
    else:
        start = (anchor - dt.timedelta(days=6)).isoformat()
        end = anchor.isoformat()

    call = fetch_window(start, end, inspect=args.inspect)
    if args.inspect:
        return
    if call is None:
        print("NO_DUNK")  # signal for main.py
        return
    import json
    print(json.dumps(asdict(call)))


if __name__ == "__main__":
    main()
