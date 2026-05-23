"""
inspect_feed.py — One-time inspector for the MLB Stats API live feed.

Goal: discover exactly how a 2026 ABS challenge / overturn is represented in the
play-by-play JSON, so we can build fetch.py against confirmed field names.

Usage (locally or via the workflow):
    python inspect_feed.py 2026-05-21

It will:
  1. pull the schedule for that date -> list of game_pks
  2. pull feed/live for the FIRST game with data
  3. scan plays + pitch events for anything mentioning challenge / review / abs /
     overturn / automatic ball-strike, and print the surrounding JSON keys + a
     sample so we can see the real structure.
"""
import sys
import json
import datetime as dt
import urllib.request

SCHED = ("https://statsapi.mlb.com/api/v1/schedule"
         "?sportId=1&date={date}")
FEED = "https://statsapi.mlb.com/api/v1.1/game/{pk}/feed/live"

KEYWORDS = ("challenge", "review", "abs", "overturn",
            "automatic", "ball-strike", "ballstrike")


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def _walk_find(obj, path=""):
    """Yield (path, key, value) for any dict key or string value that mentions
    a keyword, so we can see where challenge data lives."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            kp = f"{path}.{k}"
            if any(w in str(k).lower() for w in KEYWORDS):
                yield (kp, k, v if not isinstance(v, (dict, list)) else type(v).__name__)
            if isinstance(v, str) and any(w in v.lower() for w in KEYWORDS):
                yield (kp, "<string-value>", v[:120])
            yield from _walk_find(v, kp)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:50]):  # cap list scan
            yield from _walk_find(v, f"{path}[{i}]")


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else (
        dt.date.today() - dt.timedelta(days=1)).isoformat()
    print(f"[inspect] schedule for {date}")
    sched = _get(SCHED.format(date=date))
    pks = []
    for d in sched.get("dates", []):
        for g in d.get("games", []):
            pks.append(g["gamePk"])
    print(f"[inspect] {len(pks)} games: {pks[:10]}")
    if not pks:
        print("NO_GAMES")
        return

    # find first game whose feed has plays
    for pk in pks:
        print(f"\n[inspect] pulling feed for game {pk} ...")
        try:
            feed = _get(FEED.format(pk=pk))
        except Exception as e:
            print("  fetch error:", e)
            continue
        plays = (feed.get("liveData", {}).get("plays", {})
                 .get("allPlays", []))
        print(f"  allPlays: {len(plays)}")
        if not plays:
            continue

        # 1) show the top-level keys of a play and a pitch event
        sample_play = plays[len(plays)//2]
        print("\n=== SAMPLE PLAY top-level keys ===")
        print(list(sample_play.keys()))
        events = sample_play.get("playEvents", [])
        pitch_events = [e for e in events if e.get("isPitch")]
        if pitch_events:
            pe = pitch_events[0]
            print("\n=== SAMPLE PITCH EVENT keys ===")
            print(list(pe.keys()))
            print("\n=== details keys ===")
            print(list(pe.get("details", {}).keys()))
            pd = pe.get("pitchData", {})
            print("\n=== pitchData keys ===")
            print(list(pd.keys()))
            print("  coordinates:", list(pd.get("coordinates", {}).keys()))

        # 1b) where do the umpires live?
        print("\n=== OFFICIALS / UMPIRES ===")
        live_offs = (feed.get("liveData", {}).get("boxscore", {})
                     .get("officials", []))
        if live_offs:
            print("  liveData.boxscore.officials:")
            for o in live_offs:
                off = o.get("official", {})
                print(f"    {o.get('officialType')}: {off.get('fullName')}")
        else:
            print("  (none at liveData.boxscore.officials)")
        gd_offs = feed.get("gameData", {}).get("officials", [])
        if gd_offs:
            print("  gameData.officials:")
            for o in gd_offs:
                off = o.get("official", {})
                print(f"    {o.get('officialType')}: {off.get('fullName')}")
        else:
            print("  (none at gameData.officials)")

        # 2) scan the WHOLE feed for challenge/review keywords
        print("\n=== KEYWORD HITS across feed ===")
        hits = list(_walk_find(feed))
        if not hits:
            print("  (no challenge/review keywords found in this game's feed)")
        else:
            seen = set()
            for path, key, val in hits:
                # de-dupe by (key, type-of-path-tail) to keep output short
                tag = (key, path.split("[")[0])
                if tag in seen:
                    continue
                seen.add(tag)
                print(f"  {path}\n     key={key!r} val={val!r}")
                if len(seen) > 60:
                    print("  ... (truncated)")
                    break
        return  # done after first game with plays


if __name__ == "__main__":
    main()
