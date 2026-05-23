"""
inspect_reviews.py — Dump EVERY pitch with reviewDetails for a date, showing the
raw fields the matcher depends on, so we can fix fetch.py's filter precisely.
"""
import sys, json, datetime as dt, urllib.request

SCHED = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date}"
FEED = "https://statsapi.mlb.com/api/v1.1/game/{pk}/feed/live"

def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())

def main():
    date = sys.argv[1] if len(sys.argv) > 1 else (dt.date.today()-dt.timedelta(days=1)).isoformat()
    sched = _get(SCHED.format(date=date))
    pks = [g["gamePk"] for d in sched.get("dates", []) for g in d.get("games", [])]
    print(f"[reviews] {date}: {len(pks)} games")
    n = 0
    for pk in pks:
        try:
            feed = _get(FEED.format(pk=pk))
        except Exception as e:
            print("  feed err", pk, e); continue
        plays = feed.get("liveData", {}).get("plays", {}).get("allPlays", [])
        for play in plays:
            for ev in play.get("playEvents", []):
                if not ev.get("isPitch"): continue
                rev = ev.get("reviewDetails")
                if not rev: continue
                n += 1
                d = ev.get("details", {})
                call = d.get("call", {})
                pdat = ev.get("pitchData", {})
                coords = pdat.get("coordinates", {})
                print(f"\n--- review #{n} (game {pk}) ---")
                print(f"  call.code={call.get('code')!r} call.desc={call.get('description')!r}")
                print(f"  details.desc={d.get('description')!r} isStrike={d.get('isStrike')} isBall={d.get('isBall')}")
                print(f"  reviewType={rev.get('reviewType')!r} isOverturned={rev.get('isOverturned')} "
                      f"inFavor={rev.get('inFavorOfChallenger')} challengeTeamId={rev.get('challengeTeamId')}")
                print(f"  pX={coords.get('pX')} pZ={coords.get('pZ')} "
                      f"szTop={pdat.get('strikeZoneTop')} szBot={pdat.get('strikeZoneBottom')}")
                print(f"  play.result.desc={play.get('result',{}).get('description','')[:100]!r}")
    print(f"\n[reviews] total reviewed pitches: {n}")

if __name__ == "__main__":
    main()
