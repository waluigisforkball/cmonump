"""
post.py — Compose the caption and post text + image to Bluesky (AT Protocol).

Auth comes from env vars (set as GitHub Actions secrets):
  BLUESKY_HANDLE     e.g. abs-dunk.bsky.social
  BLUESKY_APP_PASSWORD   an APP PASSWORD (not your main password)
"""

from __future__ import annotations
import os
import sys
from atproto import Client, models


def build_caption(call: dict, window: str) -> str:
    tag = "of the Week" if window == "week" else "of the Day"
    miss = call["miss_inches"]
    mdir = str(call.get("miss_dir", "")).lower()
    half = "top" if "top" in str(call.get("half", "")).lower() else "bottom"
    inn = call.get("inning", "")
    ump = str(call.get("ump", "") or "").strip()

    dir_word = {"high": "above", "low": "below", "wide": "off"}.get(
        mdir.split()[0] if mdir else "", "outside")

    # format the game date as e.g. "May 21" (falls back to raw string)
    date_str = ""
    gd = str(call.get("game_date", "")).strip()
    if gd:
        try:
            import datetime as _dt
            date_str = _dt.date.fromisoformat(gd[:10]).strftime("%b %-d")
        except Exception:
            date_str = gd

    head = f"SMH Call {tag} \U0001F926"
    line1 = f"{head} ({date_str})" if date_str else head
    line2 = (f'{call["pitcher"]} vs {call["batter"]}, '
             f'{call["balls"]}-{call["strikes"]} in the {half} of {inn}.')
    who = ump if ump else "Blue"
    line3 = (f'{who} called this {miss:.1f}" {dir_word} the zone a strike. '
             f'It was not.')
    return f"{line1}\n{line2}\n{line3}\n\n{call['savant_link']}\n#MLB #ABS"


def build_caption_weekly(calls: list, date_range: str = "") -> str:
    """Caption for the weekly top-3 card."""
    head = "\U0001F926 Worst Calls of the Week"
    if date_range:
        head += f" ({date_range})"
    lines = [head, ""]
    medals = ["1.", "2.", "3."]
    for i, c in enumerate(calls[:3]):
        mdir = str(c.get("miss_dir", "")).lower()
        dword = ("above" if "high" in mdir else "below" if "low" in mdir else "off")
        ump = str(c.get("ump", "") or "").strip() or "Blue"
        lines.append(f'{medals[i]} {ump} — {c["miss_inches"]:.1f}" {dword} the zone')
    body = "\n".join(lines)
    tail = "\n\n#MLB #ABS"
    cap = body + tail
    return cap[:297] + "..." if len(cap) > 300 else cap


def post_text_image(caption: str, image_path: str, alt_call: dict):
    handle = os.environ.get("BLUESKY_HANDLE")
    app_pw = os.environ.get("BLUESKY_APP_PASSWORD")
    if not handle or not app_pw:
        print("[post] Missing BLUESKY creds.", file=sys.stderr)
        return None
    client = Client()
    client.login(handle, app_pw)
    with open(image_path, "rb") as f:
        img_bytes = f.read()
    alt = ("Weekly card ranking the three worst overturned ABS challenge calls, "
           "each shown as a strike-zone graphic with the miss distance.")
    resp = client.send_image(text=caption, image=img_bytes, image_alt=alt)
    uri = getattr(resp, "uri", None)
    print(f"[post] posted: {uri}")
    return uri


def post(call: dict, image_path: str, window: str) -> Optional[str]:  # noqa
    handle = os.environ.get("BLUESKY_HANDLE")
    app_pw = os.environ.get("BLUESKY_APP_PASSWORD")
    if not handle or not app_pw:
        print("[post] Missing BLUESKY_HANDLE / BLUESKY_APP_PASSWORD env vars.",
              file=sys.stderr)
        return None

    caption = build_caption(call, window)
    if len(caption) > 300:
        caption = caption[:297] + "..."

    client = Client()
    client.login(handle, app_pw)

    with open(image_path, "rb") as f:
        img_bytes = f.read()

    alt = (f'Strike zone graphic: pitch from {call["pitcher"]} to '
           f'{call["batter"]} missed the zone by {call["miss_inches"]:.1f} '
           f'inches but was originally called a strike, then overturned.')

    # post with embedded image
    resp = client.send_image(text=caption, image=img_bytes, image_alt=alt)
    uri = getattr(resp, "uri", None)
    print(f"[post] posted: {uri}")
    return uri


# typing import placed late to keep header clean
from typing import Optional  # noqa: E402

if __name__ == "__main__":
    print("This module is invoked by main.py. For a dry run, set env vars and "
          "call post() with a sample call dict + image path.")
