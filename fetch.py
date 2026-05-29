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

Ranking: miss distance is the headline and the primary sort. A leverage score
(LI-style approximation, NOT real Leverage Index) is used ONLY to break exact
ties on miss distance — the literal worst miss always wins.
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
    ump: str
    balls: int
    strikes: int
    inning: int
    half: str
    away_team: str
    home_team: str
    away_id: int
    home_id: int
    away_score: int
    home_score: int
    original_call: str       # e.g. "Called Strike"
    description: str         # MLB's ready-made sentence
    miss_inches: float
    miss_dir: str
    pX: float
    pZ: float
    sz_top: float
    sz_bot: float
    savant_link: str
    leverage: float = 0.0    # LI-style tiebreaker only; see _compute_leverage
    # --- robbed-pitcher track (ball -> overturned to STRIKE). Defaults keep the
    # existing hitter path untouched; these are only populated/used by the
    # pitcher functions below. ---
    direction: str = "hitter"     # "hitter" (now a ball) or "pitcher" (now a strike)
    center_inches: float = 0.0    # distance from dead-center of zone (pitcher rank)
    in_zone: bool = True          # was the pitch actually inside the rulebook zone

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


def _center_distance_inches(pX, pZ, top, bot):
    """Straight-line distance (inches) from the pitch to dead-center of the zone.
    Center is pX=0 horizontally, (top+bot)/2 vertically. SMALLER = more middle-
    middle = more embarrassing if it was called a ball (robbed-pitcher rank)."""
    import math
    cz = (top + bot) / 2.0
    dx_in = (pX - 0.0) * FT_TO_IN
    dz_in = (pZ - cz) * FT_TO_IN
    return math.hypot(dx_in, dz_in)


def _inside_zone(pX, pZ, top, bot):
    """Was the pitch inside the rulebook zone? Robbed-pitcher cards only use
    IN-ZONE calls so the dot always sits inside the box (caption never fights
    the picture)."""
    hw = PLATE_HALF_WIDTH_FT
    return (-hw <= pX <= hw) and (bot <= pZ <= top)


def _compute_leverage(balls, strikes, inning, away_score, home_score):
    """LI-style approximation (NOT real Leverage Index). A single float used
    ONLY to break exact ties on miss distance. Three factors multiplied so
    they compound: count drama x game closeness x inning weight.

    NOTE: the feed's per-pitch count is the post-pitch count and isn't fully
    trustworthy, so we clamp defensively and only treat 'two strikes' as the
    high-drama case (robbed of a punchout). We never trust a literal 3 strikes.
    """
    s = max(0, min(2, int(strikes)))      # clamp; ignore impossible values
    b = max(0, min(3, int(balls)))

    # count drama: 2 strikes = robbed of a K (highest); full count tops it.
    if s == 2 and b == 3:
        count_factor = 3.0                # full count, punchout on the line
    elif s == 2:
        count_factor = 2.5                # two strikes, punchout on the line
    elif b == 3:
        count_factor = 1.3                # 3-ball: walk was likely anyway
    else:
        count_factor = 1.0

    # game closeness: tie/1-run = max, decaying as the lead grows.
    diff = abs(int(away_score) - int(home_score))
    close_factor = 1.0 / (1.0 + 0.45 * diff)   # 1.00 tie, ~0.69 by 1, ~0.20 by 8

    # inning weight: later = heavier. Caps so extras don't run away.
    inning_factor = 1.0 + 0.12 * max(0, min(int(inning), 12) - 1)

    return round(count_factor * close_factor * inning_factor, 4)


def _savant_link(pk: int) -> str:
    return f"https://baseballsavant.mlb.com/gamefeed?gamePk={pk}"


def _game_pks(date: str):
    sched = _get(SCHED.format(date=date))
    pks = []
    for d in sched.get("dates", []):
        for g in d.get("games", []):
            pks.append(g["gamePk"])
    return pks


def _overturned_calls_in_game(pk: int):
    """All overturned ABS challenges in a game, BOTH directions, tagged.

    One feed-walk captures everything (so a day running both the hitter and
    pitcher paths only fetches each feed once). Each returned DunkCall is tagged
    with .direction:
      "hitter"  = now a Ball  (ump said strike, overturned to ball) — flagship
      "pitcher" = now a Strike (ump said ball, overturned to strike) — egregious-only
    Hitter calls carry miss_inches (distance outside the zone); pitcher calls
    carry center_inches (distance from dead-center) and in_zone.
    """
    try:
        feed = _get(FEED.format(pk=pk))
    except Exception as e:
        print(f"[fetch] feed error for {pk}: {e}", file=sys.stderr)
        return []

    game_date = (feed.get("gameData", {}).get("datetime", {})
                 .get("officialDate", ""))

    # home plate umpire — check both known locations
    def _home_ump():
        for path in (feed.get("liveData", {}).get("boxscore", {}).get("officials", []),
                     feed.get("gameData", {}).get("officials", [])):
            for o in path or []:
                if "home" in str(o.get("officialType", "")).lower():
                    return o.get("official", {}).get("fullName", "")
        return ""
    ump_name = _home_ump()

    teams = feed.get("gameData", {}).get("teams", {})
    away_abbr = teams.get("away", {}).get("abbreviation", "AWY")
    home_abbr = teams.get("home", {}).get("abbreviation", "HOM")
    away_team_id = int(teams.get("away", {}).get("id", 0) or 0)
    home_team_id = int(teams.get("home", {}).get("id", 0) or 0)

    plays = feed.get("liveData", {}).get("plays", {}).get("allPlays", [])
    out = []

    for play in plays:
        matchup = play.get("matchup", {})
        about = play.get("about", {})
        result_desc = play.get("result", {}).get("description", "") or ""
        _res = play.get("result", {})
        a_score = int(_res.get("awayScore", 0) or 0)
        h_score = int(_res.get("homeScore", 0) or 0)

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

            call = details.get("call", {})
            call_code = str(call.get("code", "")).upper().lstrip("*")
            # The feed shows the call AS CORRECTED (post-overturn):
            #   now a Ball  ('B...') -> ump said STRIKE, hitter robbed  (hitter)
            #   now a Strike('C...') -> ump said BALL,  pitcher robbed  (pitcher)
            # 'S' is a swinging strike (not a take) so we only treat 'C' as the
            # pitcher direction.
            if call_code.startswith("B"):
                direction = "hitter"
            elif call_code.startswith("C"):
                direction = "pitcher"
            else:
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
            cdist = _center_distance_inches(pX, pZ, top, bot)
            inzone = _inside_zone(pX, pZ, top, bot)
            cnt = ev.get("count", {})

            out.append(DunkCall(
                game_date=game_date,
                game_pk=pk,
                play_id=str(ev.get("playId", "")),
                pitcher=matchup.get("pitcher", {}).get("fullName", "Pitcher"),
                batter=matchup.get("batter", {}).get("fullName", "Batter"),
                ump=ump_name,
                balls=int(cnt.get("balls", 0)),
                strikes=int(cnt.get("strikes", 0)),
                inning=int(about.get("inning", 0)),
                half=str(about.get("halfInning", "")),
                away_team=away_abbr,
                home_team=home_abbr,
                away_id=away_team_id,
                home_id=home_team_id,
                away_score=a_score,
                home_score=h_score,
                original_call=("Called Strike" if direction == "hitter"
                               else "Ball"),  # what the ump said before overturn
                description=result_desc,
                miss_inches=float(miss),
                miss_dir=mdir,
                pX=float(pX), pZ=float(pZ),
                sz_top=float(top), sz_bot=float(bot),
                savant_link=_savant_link(pk),
                leverage=_compute_leverage(
                    int(cnt.get("balls", 0)), int(cnt.get("strikes", 0)),
                    int(about.get("inning", 0)), a_score, h_score),
                direction=direction,
                center_inches=float(cdist),
                in_zone=bool(inzone),
            ))
    return out


def _overturned_strikes_in_game(pk: int):
    """Back-compat: hitter-direction calls only (now-a-ball). Used by the
    existing flagship daily/weekly paths."""
    return [c for c in _overturned_calls_in_game(pk) if c.direction == "hitter"]


def fetch_window(start: str, end: str, inspect: bool = False):
    """start/end inclusive YYYY-MM-DD. Returns the single worst overturned called
    strike across all games in the window, or None.

    Sort key is (miss_inches, leverage): miss distance is compared at full float
    precision, so leverage only ever decides genuine ties — a pure tiebreaker.
    """
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
        for c in sorted(all_calls, key=lambda x: (x.miss_inches, x.leverage),
                        reverse=True)[:10]:
            print(f'  {c.miss_inches:5.1f}"  lev={c.leverage:5.2f}  '
                  f"{c.pitcher} -> {c.batter}  "
                  f"({c.balls}-{c.strikes}, {c.half} {c.inning})  "
                  f"{c.description[:80]}")
        return None

    if not all_calls:
        print(f"[fetch] no overturned called-strikes in {start}..{end}",
              file=sys.stderr)
        return None

    return max(all_calls, key=lambda c: (c.miss_inches, c.leverage))


def fetch_window_top_n(start: str, end: str, n: int = 3):
    """Return the top-n worst overturned called strikes in the window, ranked
    by miss distance (descending), leverage breaking exact ties. Fewer than n
    if the week was thin."""
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
    if not all_calls:
        print(f"[fetch] no overturned called-strikes in {start}..{end}",
              file=sys.stderr)
        return []
    return sorted(all_calls, key=lambda c: (c.miss_inches, c.leverage),
                  reverse=True)[:n]


# Robbed-pitcher gate: a pitch this close (inches) to dead-center of the zone
# that was called a BALL and overturned to a STRIKE is "egregious" enough to
# post. Calibrated from a full-season scan: ~8 calls/season clear 6". Tunable.
PITCHER_GATE_INCHES = 6.0


def fetch_window_pitcher(start: str, end: str, gate: float = PITCHER_GATE_INCHES,
                         inspect: bool = False):
    """Robbed-pitcher path. Returns the single most egregious 'ball -> overturned
    to strike' call in the window that (a) was IN the rulebook zone and (b) sat
    within `gate` inches of dead-center — or None if nothing qualifies.

    Ranked by center distance ASCENDING (closer to middle = worse), leverage
    breaking exact ties.
    """
    d0 = dt.date.fromisoformat(start)
    d1 = dt.date.fromisoformat(end)
    all_calls = []
    day = d0
    while day <= d1:
        pks = _game_pks(day.isoformat())
        print(f"[fetch] (pitcher) {day} -> {len(pks)} games", file=sys.stderr)
        for pk in pks:
            for c in _overturned_calls_in_game(pk):
                if c.direction == "pitcher" and c.in_zone:
                    all_calls.append(c)
        day += dt.timedelta(days=1)

    # apply the egregious gate
    qualified = [c for c in all_calls if c.center_inches <= gate]

    if inspect:
        print(f"=== {len(all_calls)} in-zone ball->strike overturns; "
              f"{len(qualified)} within {gate:.1f}\" gate ===")
        for c in sorted(all_calls, key=lambda x: (x.center_inches, -x.leverage))[:15]:
            flag = "POST" if c.center_inches <= gate else "skip"
            print(f'  {c.center_inches:5.2f}" from center  [{flag}]  '
                  f"lev={c.leverage:4.2f}  {c.pitcher} -> {c.batter}  "
                  f"({c.half} {c.inning})  {c.game_date}")
        return None

    if not qualified:
        print(f"[fetch] no egregious robbed-pitcher call (<= {gate}\") "
              f"in {start}..{end}", file=sys.stderr)
        return None

    # closest to center wins; leverage breaks exact ties (note: ascending on
    # center distance, so we min() and use -leverage to keep "higher lev wins").
    return min(qualified, key=lambda c: (c.center_inches, -c.leverage))


def fetch_window_leaderboard(start: str, end: str, top_n: int = 5,
                             inspect: bool = False):
    """Aggregate overturned called-strikes (HITTER direction only) by umpire
    across the window and rank umps by SUM of miss_inches (descending).

    Returns a list of dicts (length <= top_n), each:
      {
        "ump":          str,    # umpire name ("Blue" if the feed had none)
        "total_inches": float,  # sum of miss_inches across their overturns
        "count":        int,    # number of overturned called-strikes
        "worst_call":   DunkCall,  # their single highest-miss call
      }

    Ranking is locked: severity-weighted sum, descending. No games-worked floor.
    Calls with no umpire name in the feed are bucketed under "Blue" so the worst
    call is still surfaced rather than silently dropped.
    """
    d0 = dt.date.fromisoformat(start)
    d1 = dt.date.fromisoformat(end)

    # ump_name -> {"total": float, "count": int, "worst": DunkCall}
    agg: dict = {}
    day = d0
    while day <= d1:
        pks = _game_pks(day.isoformat())
        print(f"[fetch] (leaderboard) {day} -> {len(pks)} games", file=sys.stderr)
        for pk in pks:
            for c in _overturned_strikes_in_game(pk):   # hitter direction only
                ump = (str(c.ump or "").strip() or "Blue")
                bucket = agg.get(ump)
                if bucket is None:
                    agg[ump] = {"total": c.miss_inches, "count": 1, "worst": c}
                else:
                    bucket["total"] += c.miss_inches
                    bucket["count"] += 1
                    if c.miss_inches > bucket["worst"].miss_inches:
                        bucket["worst"] = c
        day += dt.timedelta(days=1)

    rows = [
        {"ump": ump, "total_inches": round(v["total"], 1),
         "count": v["count"], "worst_call": v["worst"]}
        for ump, v in agg.items()
    ]
    # rank by total miss inches desc; count then worst-miss break ties
    rows.sort(key=lambda r: (r["total_inches"], r["count"],
                             r["worst_call"].miss_inches), reverse=True)
    rows = rows[:top_n]

    if inspect:
        print(f"=== leaderboard {start}..{end}: "
              f"{len(agg)} umps with overturns ===")
        for i, r in enumerate(rows, 1):
            wc = r["worst_call"]
            print(f'  {i}. {r["ump"]:<22} {r["total_inches"]:6.1f}"  '
                  f'over {r["count"]} call(s)  '
                  f'worst {wc.miss_inches:.1f}" vs {wc.batter}')
        return None

    return rows


# All 30 MLB club team IDs (statsapi sportId=1). Used only by the yearly
# completion gate; hardcoded so the gate doesn't depend on a roster endpoint.
MLB_TEAM_IDS = (
    108, 109, 110, 111, 112, 113, 114, 115, 116, 117,
    118, 119, 120, 121, 133, 134, 135, 136, 137, 138,
    139, 140, 141, 142, 143, 144, 145, 146, 147, 158,
)


def is_regular_season_complete(year: int) -> bool:
    """True only when EVERY MLB club has 162 completed (Final) regular-season
    games on the schedule for `year`. Used to fire the yearly Hall of Shame the
    day after the actual last regular-season game (handles rainout makeups),
    rather than on a guessed calendar date.

    One schedule call per team (~30 calls). Any fetch error or a single team
    short of 162 Finals -> returns False (fail closed; never posts early).
    """
    sched_url = ("https://statsapi.mlb.com/api/v1/schedule"
                 "?sportId=1&season={year}&gameType=R&teamId={tid}")
    for tid in MLB_TEAM_IDS:
        try:
            data = _get(sched_url.format(year=year, tid=tid))
        except Exception as e:
            print(f"[fetch] season-complete check failed for team {tid}: {e}",
                  file=sys.stderr)
            return False
        finals = 0
        for d in data.get("dates", []):
            for g in d.get("games", []):
                state = str(g.get("status", {}).get("codedGameState", "")).upper()
                if state == "F":      # Final
                    finals += 1
        if finals < 162:
            print(f"[fetch] team {tid}: {finals}/162 finals — season not "
                  f"complete", file=sys.stderr)
            return False
    print(f"[fetch] all 30 teams at 162 finals — {year} regular season complete",
          file=sys.stderr)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", choices=["day", "week", "month", "year"],
                    default="day")
    ap.add_argument("--direction", choices=["hitter", "pitcher"], default="hitter",
                    help="hitter = flagship (now-a-ball); pitcher = egregious "
                         "robbed-pitcher (now-a-strike, gated)")
    ap.add_argument("--leaderboard", action="store_true",
                    help="run the worst-umps leaderboard for the window "
                         "(month/year) instead of a single call")
    ap.add_argument("--date")
    ap.add_argument("--inspect", action="store_true")
    args = ap.parse_args()

    anchor = (dt.date.fromisoformat(args.date) if args.date
              else dt.date.today() - dt.timedelta(days=1))
    if args.window == "day":
        start = end = anchor.isoformat()
    elif args.window == "week":
        start = (anchor - dt.timedelta(days=6)).isoformat()
        end = anchor.isoformat()
    elif args.window == "month":
        # prior calendar month, anchored to `anchor` (default: yesterday)
        first_this = anchor.replace(day=1)
        last_prev = first_this - dt.timedelta(days=1)
        start = last_prev.replace(day=1).isoformat()
        end = last_prev.isoformat()
    else:  # year
        start = f"{anchor.year}-03-01"
        end = f"{anchor.year}-11-30"

    if args.leaderboard or args.window in ("month", "year"):
        rows = fetch_window_leaderboard(start, end, inspect=args.inspect)
        if args.inspect:
            return
        if not rows:
            print("NO_DUNK")
            return
        # DunkCall isn't JSON-serializable as-is; dump worst_call via asdict
        print(json.dumps([
            {"ump": r["ump"], "total_inches": r["total_inches"],
             "count": r["count"], "worst_call": asdict(r["worst_call"])}
            for r in rows]))
        return

    if args.direction == "pitcher":
        call = fetch_window_pitcher(start, end, inspect=args.inspect)
    else:
        call = fetch_window(start, end, inspect=args.inspect)
    if args.inspect:
        return
    if call is None:
        print("NO_DUNK")
        return
    print(json.dumps(asdict(call)))


if __name__ == "__main__":
    main()
