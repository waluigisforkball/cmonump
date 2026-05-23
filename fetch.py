"""
fetch.py — Find the most embarrassing overturned ABS challenge in a date window,
using the official MLB Stats API live feed (statsapi.mlb.com).

Confirmed structure (from feed inspection, 2026):
  liveData.plays.allPlays[].playEvents[]  -> pitch events
    .isPitch == True
    .details.call.{code,description}      -> the ON-FIELD call (before overturn)
    .details.hasReview == True            -> this pitch was challenged
    .reviewDetails.isOverturned == True   -> the call was reversed
    .reviewDetails.reviewType == "MJ"     -> ABS challenge (not a replay review)
    .reviewDetails.challengeTeamId        -> who challenged
    .pitchData.coordinates.{pX,pZ}        -> pitch location (feet)
    .pitchData.{strikeZoneTop,strikeZoneBottom}  -> batter zone (feet)
  allPlays[].result.description           -> ready-made human sentence
  allPlays[].matchup.{pitcher,batter}     -> names
  allPlays[].about.{inning,halfInning}    -> situation

"SMH ump" angle = a CALLED STRIKE overturned to a ball (hitter robbed),
ranked by how far the pitch missed the nearest zone edge, in inches.
"""

from __future__ import annotations
import argparse
import datetime as dt
import json
import sys
import urllib.request
from dataclasses import dataclass, asdict
from typing import Optional

SCHED = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date}"
FEED = "https://statsapi.mlb.com/api/v1.1/game/{pk}/feed/live"

PLATE_HALF_WIDTH_FT = (17.0 / 2.0) / 12.0   # 8.5 inches in feet
FT_TO_IN = 12.0
ABS_REVIEW_TYPE = "MJ"   # ABS challenge (replay reviews use other codes)


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


@dataclass
class DunkCall:
    game_date: str
    game_pk: int
    play_id: str
    pitcher: str
    batter: str
    balls: int
    strikes: int
    inning: int
    half: str
    original_call: str       # e.g. "Called Strike"
    description: str         # MLB's ready-made sentence
    miss_inches: float
    miss_dir: str
    pX: float
    pZ: float
    sz_top: float
    sz_bot: float
    savant_link: str

    def headline_miss(self) -> str:
        return f'{self.miss_inches:.1f}"'


def _miss_distance_inches(pX, pZ, top, bot):
    """Largest single-axis distance (inches) the pitch sat OUTSIDE the zone."""
    hw = PLATE_HALF_WIDTH_FT
    if pX > hw:
        h_miss, h_dir = (pX - hw) * FT_TO_IN, "wide"
    elif pX < -hw:
        h_miss, h_dir = (-hw - pX) * FT_TO_IN, "wide"
    else:
        h_miss, h_dir = 0.0, ""

    if pZ > top:
        v_miss, v_dir = (pZ - top) * FT_TO_IN, "high"
    elif pZ < bot:
        v_miss, v_dir = (bot - pZ) * FT_TO_IN, "low"
    else:
        v_miss, v_dir = 0.0, ""

    if h_miss >= v_miss:
        return h_miss, (h_dir or "off the plate")
    return v_miss, (v_dir or "off the zone")


def _savant_link(pk: int) -> str:
    return f"https://baseballsavant.mlb.com/gamefeed?gamePk={pk}"


def _game_pks(date: str):
    sched = _get(SCHED.format(date=date))
    pks = []
    for d in sched.get("dates", []):
        for g in d.get("games", []):
            pks.append(g["gamePk"])
    return pks


def _overturned_strikes_in_game(pk: int):
    """All 'called strike -> overturned to ball' ABS challenges in a game."""
    try:
        feed = _get(FEED.format(pk=pk))
    except Exception as e:
        print(f"[fetch] feed error for {pk}: {e}", file=sys.stderr)
        return []

    game_date = (feed.get("gameData", {}).get("datetime", {})
                 .get("officialDate", ""))
    plays = feed.get("liveData", {}).get("plays", {}).get("allPlays", [])
    out = []

    for play in plays:
        matchup = play.get("matchup", {})
        about = play.get("about", {})
        result_desc = play.get("result", {}).get("description", "") or ""

        for ev in play.get("playEvents", []):
            if not ev.get("isPitch"):
                continue
            details = ev.get("details", {})
            if not details.get("hasReview"):
                continue
            rev = ev.get("reviewDetails", {})
            if not rev:
                continue
            if rev.get("reviewType") != ABS_REVIEW_TYPE:
                continue          # skip non-ABS replay reviews
            if not rev.get("isOverturned"):
                continue          # only overturns (the embarrassing ones)

            call = details.get("call", {}).get("description", "") or \
                details.get("description", "")
            # "SMH ump" angle: on-field call was a STRIKE, overturned to ball
            if "strike" not in call.lower():
                continue

            pdat = ev.get("pitchData", {})
            coords = pdat.get("coordinates", {})
            pX = coords.get("pX")
            pZ = coords.get("pZ")
            top = pdat.get("strikeZoneTop")
            bot = pdat.get("strikeZoneBottom")
            if None in (pX, pZ, top, bot):
                continue

            miss, mdir = _miss_distance_inches(pX, pZ, top, bot)
            cnt = ev.get("count", {})

            out.append(DunkCall(
                game_date=game_date,
                game_pk=pk,
                play_id=str(ev.get("playId", "")),
                pitcher=matchup.get("pitcher", {}).get("fullName", "Pitcher"),
                batter=matchup.get("batter", {}).get("fullName", "Batter"),
                balls=int(cnt.get("balls", 0)),
                strikes=int(cnt.get("strikes", 0)),
                inning=int(about.get("inning", 0)),
                half=str(about.get("halfInning", "")),
                original_call=call or "Called Strike",
                description=result_desc,
                miss_inches=float(miss),
                miss_dir=mdir,
                pX=float(pX), pZ=float(pZ),
                sz_top=float(top), sz_bot=float(bot),
                savant_link=_savant_link(pk),
            ))
    return out


def fetch_window(start: str, end: str, inspect: bool = False):
    """start/end inclusive YYYY-MM-DD. Returns the single worst overturned called
    strike across all games in the window, or None."""
    d0 = dt.date.fromisoformat(start)
    d1 = dt.date.fromisoformat(end)
    all_calls = []
    day = d0
    while day <= d1:
        pks = _game_pks(day.isoformat())
        print(f"[fetch] {day} -> {len(pks)} games", file=sys.stderr)
        for pk in pks:
            all_calls.extend(_overturned_strikes_in_game(pk))
        day += dt.timedelta(days=1)

    if inspect:
        print(f"=== {len(all_calls)} overturned called-strikes in window ===")
        for c in sorted(all_calls, key=lambda x: x.miss_inches, reverse=True)[:10]:
            print(f'  {c.miss_inches:5.1f}"  {c.pitcher} -> {c.batter}  '
                  f"({c.balls}-{c.strikes}, {c.half} {c.inning})  "
                  f"{c.description[:80]}")
        return None

    if not all_calls:
        print(f"[fetch] no overturned called-strikes in {start}..{end}",
              file=sys.stderr)
        return None

    return max(all_calls, key=lambda c: c.miss_inches)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", choices=["day", "week"], default="day")
    ap.add_argument("--date")
    ap.add_argument("--inspect", action="store_true")
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
        print("NO_DUNK")
        return
    print(json.dumps(asdict(call)))


if __name__ == "__main__":
    main()
