"""
variant_C.py — Direction C: broadcast TV-overlay look.
Dark stadium-ish background, zone box as hero, top ribbon for the SMH callout,
bottom ribbon for matchup/score. Reads like an MLB telecast strike-zone graphic.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Circle, Rectangle
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
import matplotlib.font_manager as fm
import numpy as np
import os
import io
import urllib.request

LOGO_URL = "https://www.mlbstatic.com/team-logos/{tid}.svg"
_LOGO_CACHE = "/tmp/abs_logos"


def _team_logo(team_id):
    """Fetch + rasterize a team logo to an RGBA numpy array. Returns None on any
    failure so the card falls back to text abbreviations."""
    if not team_id:
        return None
    try:
        os.makedirs(_LOGO_CACHE, exist_ok=True)
        png_path = os.path.join(_LOGO_CACHE, f"{team_id}.png")
        if not os.path.exists(png_path):
            req = urllib.request.Request(LOGO_URL.format(tid=team_id),
                                         headers={"User-Agent": "Mozilla/5.0"})
            svg_bytes = urllib.request.urlopen(req, timeout=20).read()
            import cairosvg
            cairosvg.svg2png(bytestring=svg_bytes, write_to=png_path,
                             output_width=160, output_height=160)
        import matplotlib.image as mpimg
        return mpimg.imread(png_path)
    except Exception:
        return None

# darker broadcast palette
BG = "#0e1116"; PANEL = "#161b22"; INK = "#e8e3d8"; DIM = "#8b93a0"
ACCENT = "#e8234a"; ZONE_LINE = "#e8e3d8"; GREEN = "#2ec27e"


def _font():
    for n in ("Nunito", "Nunito Sans", "DejaVu Sans"):
        try:
            fm.findfont(n, fallback_to_default=False); return n
        except Exception:
            continue
    return "DejaVu Sans"

PLATE_HALF_WIDTH_FT = (17.0/2.0)/12.0; FT_TO_IN = 12.0


# Card is 6.4" square mapped to axes 0..1, so 1 point = (1/72)/6.4 axes units.
# A stroke is centered on the radius, so HALF its width spills outside the
# true ball edge. Pull the fill radius in by that half-width so the OUTER edge
# of the white outline lands exactly on the real 2.9" ball edge — keeping the
# gap to the zone honest (never undercutting the miss).
def _honest_fill_r(true_r, linewidth_pt):
    half = (linewidth_pt / 2.0) / 72.0 / 6.4
    return max(true_r - half, true_r * 0.55)   # floor so tiny balls still render


def render(call, out_path, pitcher=False):
    """Daily broadcast card. pitcher=False is the flagship (pitch outside the
    zone, called a strike, now a ball). pitcher=True is the robbed-pitcher
    variant (pitch INSIDE the zone, called a ball, now a strike): the dot sits
    inside the box, the label is distance-from-center, and the verdict flips."""
    fam = _font()
    fig, ax = plt.subplots(figsize=(6.4, 6.4), dpi=200)
    fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.set_aspect("equal"); ax.axis("off")

    miss = float(call["miss_inches"]); mdir = str(call.get("miss_dir", "")).lower()
    center_in = float(call.get("center_inches", 0.0))  # used only when pitcher
    ump = str(call.get("ump", "") or "").strip()

    # ---- TOP RIBBON (accent) ----
    ax.add_patch(Rectangle((0, 0.86), 1, 0.14, facecolor=ACCENT, zorder=2,
                 transform=ax.transAxes))
    title = f"SMH, {ump.upper()}" if ump else "SMH, BLUE"
    t = ax.text(0.5, 0.93, title, transform=ax.transAxes, ha="center", va="center",
                fontsize=27, fontweight="black", color="#ffffff", family=fam, zorder=3)
    fig.canvas.draw()
    r = t.get_window_extent().width/ax.get_window_extent().width
    if r > 0.82:
        t.set_fontsize(27*0.82/r)
    subtitle = ("OVERTURNED ABS CHALLENGE" if not pitcher
                else "OVERTURNED ABS CHALLENGE")
    ax.text(0.5, 0.885, subtitle, transform=ax.transAxes,
            ha="center", va="center", fontsize=8.5, fontweight="black",
            color="#ffd2da", family=fam, zorder=3)

    # ---- ZONE (hero, centered) ----
    ZX0, ZX1, ZY0, ZY1 = 0.34, 0.66, 0.36, 0.70
    zcx, zcy = (ZX0+ZX1)/2, (ZY0+ZY1)/2
    top, bot = call["sz_top"], call["sz_bot"]; px, pz = call["pX"], call["pZ"]
    hw = PLATE_HALF_WIDTH_FT; zw_ft = 2*hw; zh_ft = max(0.1, top-bot)
    s = min((ZX1-ZX0)/zw_ft, (ZY1-ZY0)/zh_ft)
    fx = lambda x: zcx + x*s
    fy = lambda z: zcy + (z-(top+bot)/2)*s
    bx0, bx1, by0, by1 = fx(-hw), fx(hw), fy(bot), fy(top)
    # translucent fill + bright outline (TV strike-zone)
    ax.add_patch(Rectangle((bx0, by0), bx1-bx0, by1-by0, facecolor="#ffffff",
                 alpha=0.06, zorder=1))
    ax.add_patch(Rectangle((bx0, by0), bx1-bx0, by1-by0, fill=False,
                 edgecolor=ZONE_LINE, linewidth=3, zorder=3))
    for f in (1/3, 2/3):
        ax.plot([bx0+(bx1-bx0)*f]*2, [by0, by1], color=ZONE_LINE, lw=0.7, alpha=0.35, zorder=3)
        ax.plot([bx0, bx1], [by0+(by1-by0)*f]*2, color=ZONE_LINE, lw=0.7, alpha=0.35, zorder=3)

    ball_r = (2.9/2/12)*s            # TRUE ball radius = outer edge of the dot
    fill_r = _honest_fill_r(ball_r, 2)   # fill pulled in so stroke sits inside
    dx, dy = fx(px), fy(pz)

    if not pitcher:
        # FLAGSHIP: pitch is outside the zone. Clamp into frame, draw the dot,
        # and label the miss. (No leader line — the number carries the distance.)
        m = ball_r+0.02; dx = min(max(dx, m), 1-m); dy = min(max(dy, 0.30), 0.78)
        ax.add_patch(Circle((dx, dy), fill_r, facecolor=ACCENT, edgecolor="#ffffff",
                     linewidth=2, zorder=5))
        if "high" in mdir or "low" in mdir:
            ax.text(dx+ball_r+0.03, dy, f'{miss:.1f}"', ha="left", va="center",
                    fontsize=13, fontweight="black", color="#ffffff", family=fam, zorder=6)
        else:
            ax.text(dx, dy+ball_r+0.03, f'{miss:.1f}"', ha="center", va="bottom",
                    fontsize=13, fontweight="black", color="#ffffff", family=fam, zorder=6)
        # verdict
        ax.text(zcx, by0-0.05, "OVERTURNED \u2192 BALL", ha="center", va="top",
                fontsize=9, fontweight="black", color=GREEN, family=fam, zorder=6)
    else:
        # ROBBED PITCHER: pitch is INSIDE the zone (in_zone enforced upstream).
        # Draw the dot at its true spot — no clamping that would shove it out of
        # the box — and label the center distance. The dot sitting inside the
        # box IS the argument; no leader line needed.
        ax.add_patch(Circle((dx, dy), fill_r, facecolor=ACCENT, edgecolor="#ffffff",
                     linewidth=2, zorder=5))
        # label offset outward from center so it never sits under the dot
        lx = dx + (ball_r+0.03 if dx >= zcx else -(ball_r+0.03))
        ha = "left" if dx >= zcx else "right"
        ax.text(lx, dy, f'{center_in:.1f}"', ha=ha, va="center",
                fontsize=13, fontweight="black", color="#ffffff", family=fam, zorder=6)
        # verdict
        ax.text(zcx, by0-0.05, "OVERTURNED \u2192 STRIKE", ha="center", va="top",
                fontsize=9, fontweight="black", color=GREEN, family=fam, zorder=6)

    # ---- BOTTOM RIBBON (panel) ----
    ax.add_patch(Rectangle((0, 0), 1, 0.20, facecolor=PANEL, zorder=7,
                 transform=ax.transAxes))
    ax.add_patch(Rectangle((0, 0.20), 1, 0.006, facecolor=ACCENT, zorder=7,
                 transform=ax.transAxes))
    matchup = f'{call["pitcher"]}  →  {call["batter"]}'
    ax.text(0.5, 0.16, matchup, transform=ax.transAxes, ha="center", va="center",
            fontsize=13, fontweight="black", color=INK, family=fam, zorder=8)
    half = "Top" if "top" in str(call.get("half", "")).lower() else "Bot"
    inn = call.get("inning", ""); cnt = f'{call.get("balls",0)}-{call.get("strikes",0)}'
    at, ht = call.get("away_team"), call.get("home_team")
    a_sc, h_sc = call.get("away_score", 0), call.get("home_score", 0)

    # try logos; fall back to text-only score line if either fails
    a_logo = _team_logo(call.get("away_id"))
    h_logo = _team_logo(call.get("home_id"))

    # situation line (inning + count) always present, slightly higher
    ax.text(0.5, 0.115, f'{half} {inn}   ·   {cnt} count', transform=ax.transAxes,
            ha="center", va="center", fontsize=10, fontweight="bold",
            color=DIM, family=fam, zorder=8)

    if a_logo is not None and h_logo is not None:
        # logo + score, logo + score, centered as a group
        def _logo_box(img, x, y, zoom=0.22):
            ab = AnnotationBbox(OffsetImage(img, zoom=zoom), (x, y),
                                xycoords="axes fraction", frameon=False, zorder=9)
            ax.add_artist(ab)
        # layout: [away_logo] AWY 1  –  HOM 2 [home_logo]
        _logo_box(a_logo, 0.30, 0.055)
        ax.text(0.39, 0.055, f'{a_sc}', transform=ax.transAxes, ha="center",
                va="center", fontsize=15, fontweight="black", color=INK,
                family=fam, zorder=9)
        ax.text(0.50, 0.055, "–", transform=ax.transAxes, ha="center",
                va="center", fontsize=14, fontweight="bold", color=DIM,
                family=fam, zorder=9)
        ax.text(0.61, 0.055, f'{h_sc}', transform=ax.transAxes, ha="center",
                va="center", fontsize=15, fontweight="black", color=INK,
                family=fam, zorder=9)
        _logo_box(h_logo, 0.70, 0.055)
    else:
        score = f'{at} {a_sc}   –   {ht} {h_sc}' if at and ht else ""
        ax.text(0.5, 0.05, score, transform=ax.transAxes, ha="center",
                va="center", fontsize=12, fontweight="black", color=INK,
                family=fam, zorder=8)

    fig.savefig(out_path, facecolor=BG, bbox_inches="tight", pad_inches=0.0)
    plt.close(fig); return out_path


def _mini_zone(ax, x0, y0, w, h, call, rank):
    """Draw one ranked mini-row: rank badge + small zone w/ ball + text, inside
    the rectangle (x0,y0,w,h) in axes coords."""
    # medal colors so the rank badge never reads as the (red) pitch dot
    MEDALS = {1: ("#e8b923", "#7a5c00"),   # gold (fill, edge)
              2: ("#c7ccd1", "#6b7178"),   # silver
              3: ("#cd7f43", "#6e3d18")}   # bronze
    badge_fill, badge_edge = MEDALS.get(rank, ("#c7ccd1", "#6b7178"))

    top, bot = call["sz_top"], call["sz_bot"]
    px, pz = call["pX"], call["pZ"]
    mdir = str(call.get("miss_dir", "")).lower()
    miss = float(call["miss_inches"])
    hw = PLATE_HALF_WIDTH_FT

    # rank badge (left) — medal colored
    bxc, byc = x0 + 0.055, y0 + h/2
    ax.add_patch(Circle((bxc, byc), 0.040, facecolor=badge_fill,
                 edgecolor=badge_edge, linewidth=3, zorder=9,
                 transform=ax.transAxes))
    ax.text(bxc, byc, str(rank), transform=ax.transAxes, ha="center", va="center",
            fontsize=18, fontweight="black", color="#1a1407", family=_font(), zorder=10)

    # mini zone box (center-left)
    ZX0 = x0 + 0.12; ZX1 = ZX0 + 0.14
    zh = h * 0.62; ZY0 = byc - zh/2; ZY1 = byc + zh/2
    zcx, zcy = (ZX0+ZX1)/2, (ZY0+ZY1)/2
    zw_ft = 2*hw; zh_ft = max(0.1, top-bot)
    s = min((ZX1-ZX0)/zw_ft, (ZY1-ZY0)/zh_ft)
    fx = lambda v: zcx + v*s
    fy = lambda v: zcy + (v-(top+bot)/2)*s
    bx0, bx1, by0, by1 = fx(-hw), fx(hw), fy(bot), fy(top)
    ax.add_patch(Rectangle((bx0, by0), bx1-bx0, by1-by0, facecolor="#ffffff",
                 alpha=0.06, zorder=8, transform=ax.transAxes))
    ax.add_patch(Rectangle((bx0, by0), bx1-bx0, by1-by0, fill=False,
                 edgecolor=ZONE_LINE, linewidth=2, zorder=9, transform=ax.transAxes))
    ball_r = (2.9/2/12)*s            # TRUE ball radius
    fill_r = _honest_fill_r(ball_r, 1.5)
    dx, dy = fx(px), fy(pz)
    # clamp within this row
    dx = min(max(dx, x0+0.10), ZX1+0.05)
    dy = min(max(dy, y0+0.02), y0+h-0.02)
    ax.add_patch(Circle((dx, dy), fill_r, facecolor=ACCENT, edgecolor="#ffffff",
                 linewidth=1.5, zorder=10, transform=ax.transAxes))

    # text block (right)
    tx = ZX1 + 0.08
    ump = str(call.get("ump", "") or "").strip() or "Blue"
    fam = _font()
    ax.text(tx, byc + 0.045, f'{miss:.1f}" {("above" if "high" in mdir else "below" if "low" in mdir else "off")} the zone',
            transform=ax.transAxes, ha="left", va="center", fontsize=13,
            fontweight="black", color=ACCENT, family=fam, zorder=10)
    ax.text(tx, byc - 0.008, ump, transform=ax.transAxes, ha="left", va="center",
            fontsize=11.5, fontweight="black", color=INK, family=fam, zorder=10)
    matchup = f'{call["pitcher"]} → {call["batter"]}'
    ax.text(tx, byc - 0.055, matchup, transform=ax.transAxes, ha="left", va="center",
            fontsize=9, fontweight="bold", color=DIM, family=fam, zorder=10)


def render_top3(calls, out_path, date_range=""):
    """Weekly card: up to 3 ranked mini-rows in the broadcast style."""
    fam = _font()
    fig, ax = plt.subplots(figsize=(6.4, 6.4), dpi=200)
    fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.set_aspect("equal"); ax.axis("off")

    # top ribbon
    ax.add_patch(Rectangle((0, 0.86), 1, 0.14, facecolor=ACCENT, zorder=2,
                 transform=ax.transAxes))
    t = ax.text(0.5, 0.935, "WORST CALLS OF THE WEEK", transform=ax.transAxes,
                ha="center", va="center", fontsize=23, fontweight="black",
                color="#ffffff", family=fam, zorder=3)
    fig.canvas.draw()
    r = t.get_window_extent().width / ax.get_window_extent().width
    if r > 0.88:
        t.set_fontsize(23 * 0.88 / r)
    sub = date_range or "Overturned ABS challenges, ranked by miss"
    ax.text(0.5, 0.883, sub, transform=ax.transAxes, ha="center", va="center",
            fontsize=8.5, fontweight="black", color="#ffd2da", family=fam, zorder=3)

    # three rows in the body (y from ~0.06 to ~0.82)
    rows = [(0.58, 0.24), (0.32, 0.24), (0.06, 0.24)]  # (y0, height)
    for i, (y0, h) in enumerate(rows):
        if i < len(calls):
            # faint row divider
            if i > 0:
                ax.plot([0.06, 0.94], [y0+h+0.005]*2, color="#2a313c", lw=1,
                        zorder=2, transform=ax.transAxes)
            _mini_zone(ax, 0.04, y0, 0.92, h, calls[i].__dict__ if hasattr(calls[i], "__dict__") else calls[i], i+1)

    fig.savefig(out_path, facecolor=BG, bbox_inches="tight", pad_inches=0.0)
    plt.close(fig); return out_path


MEDALS = {1: ("#e8b923", "#7a5c00"),   # gold  (fill, edge)
          2: ("#c7ccd1", "#6b7178"),   # silver
          3: ("#cd7f43", "#6e3d18")}   # bronze


def render_leaderboard_list(ump_rows, out_path, period_label):
    """Monthly '[Month] Recap' card — Layout A: sparse 5-row vertical list.
    Each row: rank, ump name, total inches (accent), count, worst-call summary.
    `ump_rows` = list of dicts from fetch_window_leaderboard."""
    fam = _font()
    fig, ax = plt.subplots(figsize=(6.4, 6.4), dpi=200)
    fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.set_aspect("equal"); ax.axis("off")

    # top ribbon
    ax.add_patch(Rectangle((0, 0.86), 1, 0.14, facecolor=ACCENT, zorder=2,
                 transform=ax.transAxes))
    title = f"{period_label.upper()} RECAP"
    t = ax.text(0.5, 0.935, title, transform=ax.transAxes, ha="center",
                va="center", fontsize=24, fontweight="black", color="#ffffff",
                family=fam, zorder=3)
    fig.canvas.draw()
    r = t.get_window_extent().width / ax.get_window_extent().width
    if r > 0.86:
        t.set_fontsize(24 * 0.86 / r)
    ax.text(0.5, 0.883, "WORST UMPS BY INCHES MISSED", transform=ax.transAxes,
            ha="center", va="center", fontsize=8.5, fontweight="black",
            color="#ffd2da", family=fam, zorder=3)

    rows = list(ump_rows[:5])
    # body spans y ~0.06 .. ~0.82; evenly split into 5 bands
    n = max(1, len(rows))
    top_y, bot_y = 0.82, 0.06
    band = (top_y - bot_y) / 5.0     # fixed 5-band grid so spacing is stable
    for i, row in enumerate(rows):
        yc = top_y - band * (i + 0.5)
        rank = i + 1
        ump = str(row.get("ump", "") or "Blue").strip() or "Blue"
        tot = float(row.get("total_inches", 0.0))
        cnt = int(row.get("count", 0))
        wc = row.get("worst_call")
        wc_miss = float(getattr(wc, "miss_inches", 0.0)) if wc is not None else 0.0
        wc_bat = str(getattr(wc, "batter", "") or "") if wc is not None else ""

        # rank numeral (medal color for top 3, dim for 4–5)
        rfill = MEDALS.get(rank, (DIM, DIM))[0]
        ax.text(0.07, yc, str(rank), transform=ax.transAxes, ha="center",
                va="center", fontsize=26, fontweight="black", color=rfill,
                family=fam, zorder=4)

        # ump name (primary)
        ax.text(0.15, yc + 0.028, ump, transform=ax.transAxes, ha="left",
                va="center", fontsize=15, fontweight="black", color=INK,
                family=fam, zorder=4)
        # worst-call summary (secondary, dim)
        if wc_bat:
            sub = f'worst: {wc_miss:.1f}" vs {wc_bat}'
        else:
            sub = f'worst: {wc_miss:.1f}"'
        ax.text(0.15, yc - 0.030, sub, transform=ax.transAxes, ha="left",
                va="center", fontsize=10, fontweight="bold", color=DIM,
                family=fam, zorder=4)

        # total inches (right, accent, the ranking metric) + count beneath
        ax.text(0.93, yc + 0.028, f'{tot:.1f}"', transform=ax.transAxes,
                ha="right", va="center", fontsize=19, fontweight="black",
                color=ACCENT, family=fam, zorder=4)
        cpl = "call" if cnt == 1 else "calls"
        ax.text(0.93, yc - 0.030, f'{cnt} {cpl}', transform=ax.transAxes,
                ha="right", va="center", fontsize=10, fontweight="bold",
                color=DIM, family=fam, zorder=4)

        # faint divider under each row except the last
        if i < len(rows) - 1:
            ax.plot([0.06, 0.94], [yc - band/2]*2, color="#2a313c", lw=1,
                    zorder=2, transform=ax.transAxes)

    fig.savefig(out_path, facecolor=BG, bbox_inches="tight", pad_inches=0.0)
    plt.close(fig); return out_path


def _podium_zone(ax, cx, yc, w, h, call):
    """Small strike-zone with the worst-call dot, centered at (cx, yc) within a
    box of width w / height h (axes coords). Honest ball outline; no glow, no
    leader line — matches the cleaned daily card."""
    if call is None:
        return
    top = float(getattr(call, "sz_top", 3.4)); bot = float(getattr(call, "sz_bot", 1.6))
    px = float(getattr(call, "pX", 0.0)); pz = float(getattr(call, "pZ", top))
    hw = PLATE_HALF_WIDTH_FT
    ZX0, ZX1 = cx - w/2, cx + w/2
    ZY0, ZY1 = yc - h/2, yc + h/2
    zcx, zcy = cx, yc
    zw_ft = 2*hw; zh_ft = max(0.1, top - bot)
    s = min(w/zw_ft, h/zh_ft)
    fx = lambda v: zcx + v*s
    fy = lambda v: zcy + (v-(top+bot)/2)*s
    bx0, bx1, by0, by1 = fx(-hw), fx(hw), fy(bot), fy(top)
    ax.add_patch(Rectangle((bx0, by0), bx1-bx0, by1-by0, facecolor="#ffffff",
                 alpha=0.06, zorder=8, transform=ax.transAxes))
    ax.add_patch(Rectangle((bx0, by0), bx1-bx0, by1-by0, fill=False,
                 edgecolor=ZONE_LINE, linewidth=2, zorder=9, transform=ax.transAxes))
    ball_r = (2.9/2/12)*s
    fill_r = _honest_fill_r(ball_r, 1.5)
    dx, dy = fx(px), fy(pz)
    # clamp the dot to within a hair of the zone-box edges so an extreme miss
    # still renders cleanly inside the row rather than spilling out the side
    dx = min(max(dx, bx0 + fill_r), bx1 - fill_r)
    dy = min(max(dy, by0 + fill_r), by1 - fill_r)
    ax.add_patch(Circle((dx, dy), fill_r, facecolor=ACCENT, edgecolor="#ffffff",
                 linewidth=1.5, zorder=10, transform=ax.transAxes))


def render_leaderboard_podium(ump_rows, out_path, period_label):
    """Yearly 'Hall of Shame' card — Layout C: top 3 on a podium with medals +
    mini strike-zone of their worst call; rows 4–5 as compact text mentions.
    #1 is tagged 'THE SPECTACLE'. `period_label` is the year, e.g. '2026'."""
    fam = _font()
    fig, ax = plt.subplots(figsize=(6.4, 6.4), dpi=200)
    fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.set_aspect("equal"); ax.axis("off")

    # top ribbon
    ax.add_patch(Rectangle((0, 0.86), 1, 0.14, facecolor=ACCENT, zorder=2,
                 transform=ax.transAxes))
    t = ax.text(0.5, 0.935, f"{period_label} HALL OF SHAME", transform=ax.transAxes,
                ha="center", va="center", fontsize=24, fontweight="black",
                color="#ffffff", family=fam, zorder=3)
    fig.canvas.draw()
    r = t.get_window_extent().width / ax.get_window_extent().width
    if r > 0.86:
        t.set_fontsize(24 * 0.86 / r)
    ax.text(0.5, 0.883, "WORST UMPS BY INCHES MISSED", transform=ax.transAxes,
            ha="center", va="center", fontsize=8.5, fontweight="black",
            color="#ffd2da", family=fam, zorder=3)

    rows = list(ump_rows[:5])
    top3 = rows[:3]
    mentions = rows[3:5]

    # ---- PODIUM (top 3): three columns. Each block holds, top→bottom:
    # medal badge (corner) · mini strike-zone · ump · total · count.
    # Block heights differ (gold tallest) but all share the same bottom edge so
    # the internal stack starts just under each block's top.
    # rank -> (center_x, block_top_y)
    cols = {1: (0.50, 0.80), 2: (0.205, 0.72), 3: (0.795, 0.67)}
    block_bottom = 0.20
    bw = 0.28
    order = [2, 1, 3]  # silver, gold, bronze L→R
    for rank in order:
        if rank > len(top3):
            continue
        row = top3[rank - 1]
        cx, block_top = cols[rank]
        ump = str(row.get("ump", "") or "Blue").strip() or "Blue"
        tot = float(row.get("total_inches", 0.0))
        cnt = int(row.get("count", 0))
        wc = row.get("worst_call")
        fill, edge = MEDALS[rank]

        # podium block
        ax.add_patch(Rectangle((cx - bw/2, block_bottom), bw,
                     block_top - block_bottom, facecolor=PANEL, edgecolor=edge,
                     linewidth=2, zorder=4, transform=ax.transAxes))

        # medal badge — top-left corner of the block
        bxc, byc = cx - bw/2 + 0.045, block_top - 0.045
        ax.add_patch(Circle((bxc, byc), 0.034, facecolor=fill, edgecolor=edge,
                     linewidth=2.5, zorder=8, transform=ax.transAxes))
        ax.text(bxc, byc, str(rank), transform=ax.transAxes, ha="center",
                va="center", fontsize=15, fontweight="black", color="#1a1407",
                family=fam, zorder=9)

        # mini strike-zone INSIDE the block, just under the top edge
        _podium_zone(ax, cx + 0.03, block_top - 0.075, 0.115, 0.13, wc)

        # text stack below the zone
        ax.text(cx, block_top - 0.175, ump, transform=ax.transAxes, ha="center",
                va="center", fontsize=11, fontweight="black", color=INK,
                family=fam, zorder=7)
        ax.text(cx, block_top - 0.215, f'{tot:.1f}"', transform=ax.transAxes,
                ha="center", va="center", fontsize=15, fontweight="black",
                color=ACCENT, family=fam, zorder=7)
        cpl = "call" if cnt == 1 else "calls"
        ax.text(cx, block_top - 0.250, f'{cnt} {cpl}', transform=ax.transAxes,
                ha="center", va="center", fontsize=8.5, fontweight="bold",
                color=DIM, family=fam, zorder=7)

        # "THE SPECTACLE" tag — its own clear band above the gold block
        if rank == 1:
            ax.text(cx, block_top + 0.035, "THE SPECTACLE", transform=ax.transAxes,
                    ha="center", va="center", fontsize=12, fontweight="black",
                    color="#e8b923", family=fam, zorder=8)

    # ---- HONORABLE MENTIONS (rows 4–5) : compact text rows along the bottom ---
    if mentions:
        ax.plot([0.06, 0.94], [0.165, 0.165], color="#2a313c", lw=1, zorder=3,
                transform=ax.transAxes)
        ax.text(0.06, 0.135, "HONORABLE MENTIONS", transform=ax.transAxes,
                ha="left", va="center", fontsize=8, fontweight="black",
                color=DIM, family=fam, zorder=4)
        my = 0.095
        for j, row in enumerate(mentions):
            rank = 4 + j
            ump = str(row.get("ump", "") or "Blue").strip() or "Blue"
            tot = float(row.get("total_inches", 0.0))
            cnt = int(row.get("count", 0))
            cpl = "call" if cnt == 1 else "calls"
            ax.text(0.06, my, f'{rank}.', transform=ax.transAxes, ha="left",
                    va="center", fontsize=12, fontweight="black", color=DIM,
                    family=fam, zorder=4)
            ax.text(0.13, my, ump, transform=ax.transAxes, ha="left",
                    va="center", fontsize=12, fontweight="black", color=INK,
                    family=fam, zorder=4)
            ax.text(0.93, my, f'{tot:.1f}"  ·  {cnt} {cpl}', transform=ax.transAxes,
                    ha="right", va="center", fontsize=11, fontweight="bold",
                    color=ACCENT, family=fam, zorder=4)
            my -= 0.052

    fig.savefig(out_path, facecolor=BG, bbox_inches="tight", pad_inches=0.0)
    plt.close(fig); return out_path


if __name__ == "__main__":
    render(dict(pitcher="Eury Pérez", batter="Bo Bichette", balls=3, strikes=1,
        inning=7, half="top", ump="Carlos Torres", miss_inches=4.9, miss_dir="high",
        pX=-0.56, pZ=3.484, sz_top=3.072, sz_bot=1.55,
        away_team="NYM", home_team="MIA", away_id=121, home_id=146,
        away_score=1, home_score=2), "C.png")
    print("wrote C.png")
