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

    if event == "schedule":
        # weekly cron is the Monday 15:00 UTC one; everything else = daily
        cron = os.environ.get("CRON", "")
        window = "week" if cron.strip() == "0 15 * * 1" else "day"
        date = None
        inspect = False
        dry_run = False
    else:
        window = os.environ.get("IN_WINDOW") or "day"
        date = os.environ.get("IN_DATE") or None
        inspect = _truthy(os.environ.get("IN_INSPECT"))
        dry_run = _truthy(os.environ.get("IN_DRY_RUN"))

    print(f"[ci] event={event} window={window} date={date} "
          f"inspect={inspect} dry_run={dry_run}")

    if inspect:
        anchor = (dt.date.fromisoformat(date) if date
                  else dt.date.today() - dt.timedelta(days=1))
        fetch_mod.fetch_window(anchor.isoformat(), anchor.isoformat(),
                               inspect=True)
        return 0

    return main_mod.run(window, date, dry_run)


if __name__ == "__main__":
    sys.exit(main())
