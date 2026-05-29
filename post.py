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
              .link("#1 on Savant \u2192", link)
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
          .link("Game on Savant \u2192", call["savant_link"])
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
          .link("Game on Savant \u2192", call["savant_link"])
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


def _ordinal_inches(x: float) -> str:
    return f'{x:.1f}"'


def build_caption_monthly(ump_rows: list, period_label: str) -> str:
    """Ceremonial-deadpan monthly recap caption. `ump_rows` is the list of dicts
    from fetch_window_leaderboard (ump, total_inches, count, worst_call).
    `period_label` is the month name, e.g. "May"."""
    head = f"Presenting the {period_label} Recap."
    lines = [head, ""]
    for i, r in enumerate(ump_rows[:5], 1):
        ump = str(r.get("ump", "") or "Blue").strip() or "Blue"
        tot = float(r.get("total_inches", 0.0))
        cnt = int(r.get("count", 0))
        plural = "overturn" if cnt == 1 else "overturns"
        lines.append(f'{i}) {ump} — {tot:.1f}" missed across {cnt} {plural}.')
    body = "\n".join(lines)
    tail = "\n\n#MLB #ABS"
    cap = body + tail
    # Bluesky hard cap is 300 graphemes; trim extra rows before the tail if long
    if len(cap) > 300:
        while len(lines) > 3 and len("\n".join(lines) + tail) > 300:
            lines.pop()
        cap = "\n".join(lines) + tail
    return cap[:300]


def build_caption_yearly(ump_rows: list, year) -> str:
    """Ceremonial awards-announcement caption for the yearly Hall of Shame.
    The #1 ump receives "The Spectacle". Runner-ups listed after."""
    if not ump_rows:
        return f"The {year} Hall of Shame is empty. Somehow.\n\n#MLB #ABS"
    win = ump_rows[0]
    wump = str(win.get("ump", "") or "Blue").strip() or "Blue"
    wtot = float(win.get("total_inches", 0.0))
    wcnt = int(win.get("count", 0))
    wpl = "overturn" if wcnt == 1 else "overturns"
    line1 = f"{year} Hall of Shame. Worst ump of the season: {wump}."
    line2 = f'{wtot:.1f}" missed across {wcnt} {wpl}.'

    runners = []
    for r in ump_rows[1:5]:
        ump = str(r.get("ump", "") or "Blue").strip() or "Blue"
        runners.append(f'{ump} ({float(r.get("total_inches", 0.0)):.1f}")')
    line3 = ("Hall of Shame complete: " + ", ".join(runners) + "."
             if runners else "")

    body = "\n".join([line1, line2] + ([line3] if line3 else []))
    tail = "\n\n#MLB #ABS"
    cap = body + tail
    if len(cap) > 300:
        # drop runner-ups first, then fall back to just the headline
        cap = ("\n".join([line1, line2]) + tail)
        if len(cap) > 300:
            cap = (line1 + tail)
    return cap[:300]


def post_leaderboard(caption: str, image_path: str, kind: str):
    """Post a monthly/yearly leaderboard card. No clickable link facet — there's
    no single call to point at — so the caption text posts as-is. `kind` is
    "monthly" or "yearly", used only for the alt text."""
    handle = os.environ.get("BLUESKY_HANDLE")
    app_pw = os.environ.get("BLUESKY_APP_PASSWORD")
    if not handle or not app_pw:
        print("[post] Missing BLUESKY_HANDLE / BLUESKY_APP_PASSWORD env vars.",
              file=sys.stderr)
        return None
    if kind == "yearly":
        alt = ("Yearly Hall of Shame card: a podium ranking the five umpires "
               "with the most total inches missed on overturned ABS challenge "
               "called-strikes, top three shown with medals and strike-zone "
               "graphics of their worst call.")
    else:
        alt = ("Monthly recap card: a ranked list of the five umpires with the "
               "most total inches missed on overturned ABS challenge "
               "called-strikes for the month, with each one's worst call.")
    client = Client()
    client.login(handle, app_pw)
    with open(image_path, "rb") as f:
        img_bytes = f.read()
    resp = client.send_image(text=caption, image=img_bytes, image_alt=alt)
    uri = getattr(resp, "uri", None)
    print(f"[post] posted ({kind}): {uri}")
    return uri


if __name__ == "__main__":
    print("This module is invoked by main.py. For a dry run, set env vars and "
          "call post() with a sample call dict + image path.")
