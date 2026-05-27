"""
post.py — Compose the caption and post text + image to Bluesky (AT Protocol).

Auth comes from env vars (set as GitHub Actions secrets):
  BLUESKY_HANDLE     e.g. abs-dunk.bsky.social
  BLUESKY_APP_PASSWORD   an APP PASSWORD (not your main password)
"""

from __future__ import annotations
import os
import sys
from atproto import Client, client_utils


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


def build_caption_pitcher(call: dict) -> str:
    """Robbed-pitcher caption (voice C, tight deadpan). The pitch was IN the
    zone, called a ball, overturned to a strike. Header stays 'SMH Call of the
    Day' for brand unity; line 2 immediately signals this is the pitcher
    direction so it never reads as a dupe of the flagship."""
    center = float(call.get("center_inches", 0.0))
    half = "top" if "top" in str(call.get("half", "")).lower() else "bottom"
    inn = call.get("inning", "")
    ump = str(call.get("ump", "") or "").strip() or "Blue"

    date_str = ""
    gd = str(call.get("game_date", "")).strip()
    if gd:
        try:
            import datetime as _dt
            date_str = _dt.date.fromisoformat(gd[:10]).strftime("%b %-d")
        except Exception:
            date_str = gd

    head = "SMH Call of the Day \U0001F926"
    line1 = f"{head} ({date_str})" if date_str else head
    # line 2 flips the framing: pitcher robbed
    line2 = (f'{call["pitcher"]} got robbed vs {call["batter"]}, '
             f'{call["balls"]}-{call["strikes"]} in the {half} of {inn}.')
    # voice C: claim, then flat verdict — mirrors "It was not."
    line3 = (f'{center:.1f}" from dead center. {ump} called it a ball. '
             f'It was a strike.')
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

    # caption text already built (top-3 list + hashtags); append a clickable
    # link to the #1 call's gamefeed if we have it.
    link = alt_call.get("savant_link") if isinstance(alt_call, dict) else None
    if link:
        # Strip the trailing hashtags off, then rebuild with a link facet.
        # BUGFIX: build_caption_weekly truncates long captions with "..." which
        # can chop the "\n\n#MLB #ABS" tail, so a literal .replace() would miss
        # and leave hashtags stranded mid-caption. Use rsplit on the tag instead
        # so we always cleanly separate body from tail regardless of truncation.
        tail = "\n\n#MLB #ABS"
        if tail in caption:
            base = caption.rsplit(tail, 1)[0].rstrip()
        else:
            # caption was truncated; drop any trailing "...", strip a dangling
            # "#MLB"/"#ABS" fragment if present, and use what remains as body.
            base = caption.rstrip(". ").rstrip()
            for frag in ("#MLB #ABS", "#MLB", "#ABS"):
                if base.endswith(frag):
                    base = base[: -len(frag)].rstrip()
                    break
        tb = (client_utils.TextBuilder()
              .text(base + "\n\n")
              .link("Watch #1 \u2192", link)
              .text("\n#MLB #ABS"))
        resp = client.send_image(text=tb, image=img_bytes, image_alt=alt)
    else:
        resp = client.send_image(text=caption, image=img_bytes, image_alt=alt)
    uri = getattr(resp, "uri", None)
    print(f"[post] posted: {uri}")
    return uri


def post(call: dict, image_path: str, window: str):
    handle = os.environ.get("BLUESKY_HANDLE")
    app_pw = os.environ.get("BLUESKY_APP_PASSWORD")
    if not handle or not app_pw:
        print("[post] Missing BLUESKY_HANDLE / BLUESKY_APP_PASSWORD env vars.",
              file=sys.stderr)
        return None

    tag = "of the Week" if window == "week" else "of the Day"
    miss = call["miss_inches"]
    mdir = str(call.get("miss_dir", "")).lower()
    half = "top" if "top" in str(call.get("half", "")).lower() else "bottom"
    inn = call.get("inning", "")
    ump = str(call.get("ump", "") or "").strip() or "Blue"
    dir_word = {"high": "above", "low": "below", "wide": "off"}.get(
        mdir.split()[0] if mdir else "", "outside")
    date_str = ""
    gd = str(call.get("game_date", "")).strip()
    if gd:
        try:
            import datetime as _dt
            date_str = _dt.date.fromisoformat(gd[:10]).strftime("%b %-d")
        except Exception:
            date_str = gd
    head = f"SMH Call {tag} \U0001F926" + (f" ({date_str})" if date_str else "")

    # rich text with a CLICKABLE link facet
    tb = (client_utils.TextBuilder()
          .text(f"{head}\n"
                f'{call["pitcher"]} vs {call["batter"]}, '
                f'{call["balls"]}-{call["strikes"]} in the {half} of {inn}.\n'
                f'{ump} called this {miss:.1f}" {dir_word} the zone a strike. '
                f"It was not.\n\n")
          .link("Watch the play \u2192", call["savant_link"])
          .text("\n#MLB #ABS"))

    client = Client()
    client.login(handle, app_pw)
    with open(image_path, "rb") as f:
        img_bytes = f.read()
    alt = (f'Strike zone graphic: pitch from {call["pitcher"]} to '
           f'{call["batter"]} was {miss:.1f} inches {dir_word} the zone but '
           f'was called a strike, then overturned on challenge.')
    resp = client.send_image(text=tb, image=img_bytes, image_alt=alt)
    uri = getattr(resp, "uri", None)
    print(f"[post] posted: {uri}")
    return uri


def post_pitcher(call: dict, image_path: str):
    """Post the robbed-pitcher card (ball -> overturned to strike). Voice C,
    clickable gamefeed link facet, mirrors post() structurally."""
    handle = os.environ.get("BLUESKY_HANDLE")
    app_pw = os.environ.get("BLUESKY_APP_PASSWORD")
    if not handle or not app_pw:
        print("[post] Missing BLUESKY_HANDLE / BLUESKY_APP_PASSWORD env vars.",
              file=sys.stderr)
        return None

    center = float(call.get("center_inches", 0.0))
    half = "top" if "top" in str(call.get("half", "")).lower() else "bottom"
    inn = call.get("inning", "")
    ump = str(call.get("ump", "") or "").strip() or "Blue"
    date_str = ""
    gd = str(call.get("game_date", "")).strip()
    if gd:
        try:
            import datetime as _dt
            date_str = _dt.date.fromisoformat(gd[:10]).strftime("%b %-d")
        except Exception:
            date_str = gd
    head = "SMH Call of the Day \U0001F926" + (f" ({date_str})" if date_str else "")

    tb = (client_utils.TextBuilder()
          .text(f"{head}\n"
                f'{call["pitcher"]} got robbed vs {call["batter"]}, '
                f'{call["balls"]}-{call["strikes"]} in the {half} of {inn}.\n'
                f'{center:.1f}" from dead center. {ump} called it a ball. '
                f"It was a strike.\n\n")
          .link("Watch the play \u2192", call["savant_link"])
          .text("\n#MLB #ABS"))

    client = Client()
    client.login(handle, app_pw)
    with open(image_path, "rb") as f:
        img_bytes = f.read()
    alt = (f'Strike zone graphic: pitch from {call["pitcher"]} to '
           f'{call["batter"]} was {center:.1f} inches from the center of the '
           f'zone but was called a ball, then overturned to a strike on challenge.')
    resp = client.send_image(text=tb, image=img_bytes, image_alt=alt)
    uri = getattr(resp, "uri", None)
    print(f"[post] posted: {uri}")
    return uri


if __name__ == "__main__":
    print("This module is invoked by main.py. For a dry run, set env vars and "
          "call post() with a sample call dict + image path.")
