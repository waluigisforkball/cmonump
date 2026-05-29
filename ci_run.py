"""
ci_run.py — CI entrypoint. Reads env vars set by the GitHub Actions workflow and
dispatches into main.py's run/inspect logic. Keeps all branching in Python so
there's no fragile shell quoting in the workflow YAML.
"""
import os
import sys
import datetime as dt

import fetch as fetch_mod
import main as main_mod


def _truthy(v: str) -> bool:
    return str(v).strip().lower() in {"true", "1", "yes", "on"}


def main():
    event = os.environ.get("EVENT_NAME", "workflow_dispatch")

    # one-time feed-structure inspector (temporary)
    if _truthy(os.environ.get("IN_FEEDINSPECT")):
        import runpy, sys as _sys
        date = os.environ.get("IN_DATE") or (
            dt.date.today() - dt.timedelta(days=1)).isoformat()
        _sys.argv = ["inspect_feed.py", date]
        runpy.run_path("inspect_feed.py", run_name="__main__")
        return 0

    if _truthy(os.environ.get("IN_REVIEWINSPECT")):
        import runpy, sys as _sys
        date = os.environ.get("IN_DATE") or (
            dt.date.today() - dt.timedelta(days=1)).isoformat()
        _sys.argv = ["inspect_reviews.py", date]
        runpy.run_path("inspect_reviews.py", run_name="__main__")
        return 0

    if event == "schedule":
        cron = (os.environ.get("CRON", "") or "").strip()
        date = None
        inspect = False
        pitcher_inspect = False
        dry_run = False
        # Route by cron expression:
        #   "0 15 * * 1"        -> weekly (Mondays)
        #   "0 14 1 * *"        -> monthly recap (1st of month)
        #   "0 14 25-30 9 *" /
        #   "0 14 1-10 10 *"    -> yearly check window (late Sep / early Oct);
        #                          only posts once the season is actually done
        #   anything else       -> daily
        if cron == "0 15 * * 1":
            window = "week"
        elif cron == "0 14 1 * *":
            window = "month"
        elif cron in ("0 14 25-30 9 *", "0 14 1-10 10 *"):
            # gate: only fire the Hall of Shame when every team has 162 finals
            year = dt.date.today().year
            print(f"[ci] yearly check: testing if {year} regular season is "
                  f"complete ...")
            if not fetch_mod.is_regular_season_complete(year):
                print("[ci] season not complete — exiting without posting.")
                return 0
            print("[ci] season complete — posting Hall of Shame.")
            window = "year"
        else:
            window = "day"
    else:
        window = os.environ.get("IN_WINDOW") or "day"
        date = os.environ.get("IN_DATE") or None
        inspect = _truthy(os.environ.get("IN_INSPECT"))
        pitcher_inspect = _truthy(os.environ.get("IN_PITCHERINSPECT"))
        dry_run = _truthy(os.environ.get("IN_DRY_RUN"))

    print(f"[ci] event={event} window={window} date={date} "
          f"inspect={inspect} pitcher_inspect={pitcher_inspect} dry_run={dry_run}")

    # flagship (hitter) inspect — prints the worst overturned called-strikes
    if inspect:
        anchor = (dt.date.fromisoformat(date) if date
                  else dt.date.today() - dt.timedelta(days=1))
        if window == "week":
            start = (anchor - dt.timedelta(days=6)).isoformat()
        else:
            start = anchor.isoformat()
        fetch_mod.fetch_window(start, anchor.isoformat(), inspect=True)
        return 0

    # robbed-pitcher inspect — prints every in-zone ball->strike overturn with
    # its center distance and whether it clears the egregious gate.
    if pitcher_inspect:
        anchor = (dt.date.fromisoformat(date) if date
                  else dt.date.today() - dt.timedelta(days=1))
        if window == "week":
            start = (anchor - dt.timedelta(days=6)).isoformat()
        else:
            start = anchor.isoformat()
        fetch_mod.fetch_window_pitcher(start, anchor.isoformat(), inspect=True)
        return 0

    # Manual yearly posts must also respect the season gate: a real (non-dry-run)
    # Hall of Shame should never fire mid-season. Dry-runs are always allowed so
    # the card can be tested before the season ends.
    if window == "year" and event != "schedule" and not dry_run:
        year = (dt.date.fromisoformat(date).year if date
                else dt.date.today().year)
        if not fetch_mod.is_regular_season_complete(year):
            print(f"[ci] manual yearly post blocked — {year} regular season "
                  f"not complete. Use dry_run=true to preview the card.")
            return 0

    return main_mod.run(window, date, dry_run)


if __name__ == "__main__":
    sys.exit(main())
