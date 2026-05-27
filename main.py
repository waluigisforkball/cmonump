"""
main.py — Orchestrate the ABS-dunk pipeline.
  python main.py --window day            # post yesterday's worst overturned call
  python main.py --window week           # post the trailing-7-day worst (run Mondays)
  python main.py --window day --dry-run  # build everything, render card, DON'T post
  python main.py --inspect               # print live Savant columns (one-time check)
On a day with no overturned challenges, it exits quietly without posting.

DAILY runs ALSO check the robbed-pitcher track (ball -> overturned to strike,
in-zone, within the egregious center-distance gate). When one qualifies it is
posted as a SECOND, separate post after the flagship. This is rare (~8/season).
"""
from __future__ import annotations
import argparse
import datetime as dt
import sys
import json
import fetch as fetch_mod
import graphic as graphic_mod


def _run_pitcher_daily(start: str, end: str, dry_run: bool) -> int:
    """Robbed-pitcher check for the daily window. Posts a second card only if an
    egregious in-zone ball->strike overturn is found; otherwise exits quietly.
    Returns 0 on success/nothing-to-do, 1 on post failure."""
    import post as post_mod
    pcall_obj = fetch_mod.fetch_window_pitcher(start, end)
    if pcall_obj is None:
        print("[main] No egregious robbed-pitcher call. Nothing to add.")
        return 0
    pcall = pcall_obj.__dict__
    print("[main] robbed-pitcher call:\n" + json.dumps(pcall, indent=2))
    pimg = graphic_mod.render(pcall, "card_pitcher.png", pitcher=True)
    print(f"[main] rendered {pimg}")
    if dry_run:
        print("[main] DRY RUN — skipping robbed-pitcher Bluesky post.")
        print("\n--- pitcher caption preview ---")
        print(post_mod.build_caption_pitcher(pcall))
        return 0
    uri = post_mod.post_pitcher(pcall, pimg)
    return 0 if uri else 1


def run(window: str, anchor_date: str | None, dry_run: bool):
    anchor = (dt.date.fromisoformat(anchor_date) if anchor_date
              else dt.date.today() - dt.timedelta(days=1))
    if window == "day":
        start = end = anchor.isoformat()
    else:
        start = (anchor - dt.timedelta(days=6)).isoformat()
        end = anchor.isoformat()
    print(f"[main] window={window} range={start}..{end} dry_run={dry_run}")

    import post as post_mod

    # ----- WEEKLY: top-3 ranked card (flagship hitter direction only) -----
    if window == "week":
        top = fetch_mod.fetch_window_top_n(start, end, n=3)
        if not top:
            print("[main] No overturned challenges this week. Nothing to post.")
            return 0
        calls = [c.__dict__ for c in top]
        print(f"[main] top {len(calls)} calls:\n" + json.dumps(calls, indent=2))
        try:
            d0 = dt.date.fromisoformat(start); d1 = dt.date.fromisoformat(end)
            drange = f'{d0.strftime("%b %-d")}-{d1.strftime("%-d")}'
        except Exception:
            drange = ""
        img = graphic_mod.render_top3(top, "card.png", date_range=drange)
        print(f"[main] rendered {img}")
        caption = post_mod.build_caption_weekly(calls, drange)
        if dry_run:
            print("[main] DRY RUN — skipping Bluesky post.")
            print("\n--- caption preview ---\n" + caption)
            return 0
        uri = post_mod.post_text_image(caption, img, calls[0])
        return 0 if uri else 1

    # ----- DAILY: single worst flagship call, THEN the pitcher check -----
    flagship_rc = 0
    call_obj = fetch_mod.fetch_window(start, end)
    if call_obj is None:
        print("[main] No overturned challenge found in window. "
              "Nothing to post for the flagship.")
    else:
        call = call_obj.__dict__
        print("[main] worst call:\n" + json.dumps(call, indent=2))
        img = graphic_mod.render(call, "card.png")
        print(f"[main] rendered {img}")
        if dry_run:
            print("[main] DRY RUN — skipping Bluesky post.")
            print("\n--- caption preview ---")
            print(post_mod.build_caption(call, window))
        else:
            uri = post_mod.post(call, img, window)
            flagship_rc = 0 if uri else 1

    # robbed-pitcher: separate post, runs whether or not the flagship fired
    pitcher_rc = _run_pitcher_daily(start, end, dry_run)

    # non-zero if either post attempt failed
    return flagship_rc or pitcher_rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", choices=["day", "week"], default="day")
    ap.add_argument("--date", help="anchor date YYYY-MM-DD (default yesterday)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--inspect", action="store_true")
    args = ap.parse_args()
    if args.inspect:
        anchor = (dt.date.fromisoformat(args.date) if args.date
                  else dt.date.today() - dt.timedelta(days=1))
        fetch_mod.fetch_window(anchor.isoformat(), anchor.isoformat(),
                               inspect=True)
        return 0
    return run(args.window, args.date, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
