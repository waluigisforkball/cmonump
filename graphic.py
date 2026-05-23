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


def render(call, out_path):
    fam = _font()
    fig, ax = plt.subplots(figsize=(6.4, 6.4), dpi=200)
    fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.set_aspect("equal"); ax.axis("off")

    miss = float(call["miss_inches"]); mdir = str(call.get("miss_dir", "")).lower()
    ump = str(call.get("ump", "") or "").strip()

    # ---- TOP RIBBON (accent) ----
    ax.add_patch(Rectangle((0, 0.86), 1, 0.14, facecolor=ACCENT, zorder=2,
                 transform=ax.transAxes))
    title = f"SMH, {ump.upper()}" if ump else "SMH, BLUE"
    t = ax.text(0.5, 0.93, title, transform=ax.transAxes, ha="center", va="center",
                fontsize=27, fontweight="black", color="#ffffff", family=fam, zorder=3)
    fig.canvas.draw()
    r = t.get_window_extent().width/ax.get_window_extent().width
    if r > 0.9:
        t.set_fontsize(27*0.9/r)
    ax.text(0.5, 0.885, "OVERTURNED ABS CHALLENGE", transform=ax.transAxes,
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

    ball_r = (2.9/2/12)*s
    dx, dy = fx(px), fy(pz)
    m = ball_r+0.02; dx = min(max(dx, m), 1-m); dy = min(max(dy, 0.30), 0.78)
    # glow + ball
    ax.add_patch(Circle((dx, dy), ball_r*1.7, facecolor=ACCENT, alpha=0.22, zorder=4))
    ax.add_patch(Circle((dx, dy), ball_r, facecolor=ACCENT, edgecolor="#ffffff",
                 linewidth=2, zorder=5))
    if "high" in mdir or "low" in mdir:
        edge_y = by1 if "high" in mdir else by0; ex = min(max(dx, bx0), bx1)
        g = ball_r+0.012; stop = dy-g if dy > edge_y else dy+g
        if abs(stop-edge_y) > 0.01:
            ax.annotate("", xy=(ex, stop), xytext=(ex, edge_y),
                arrowprops=dict(arrowstyle="-", linestyle=(0,(3,2)), color=ACCENT, lw=2), zorder=4)
        ax.text(dx+ball_r+0.03, dy, f'{miss:.1f}"', ha="left", va="center",
                fontsize=13, fontweight="black", color="#ffffff", family=fam, zorder=6)
    else:
        edge_x = bx1 if dx > zcx else bx0; g = ball_r+0.012
        stop = dx-g if dx > edge_x else dx+g
        if abs(stop-edge_x) > 0.01:
            ax.annotate("", xy=(stop, dy), xytext=(edge_x, dy),
                arrowprops=dict(arrowstyle="-", linestyle=(0,(3,2)), color=ACCENT, lw=2), zorder=4)
        ax.text(dx, dy+ball_r+0.03, f'{miss:.1f}"', ha="center", va="bottom",
                fontsize=13, fontweight="black", color="#ffffff", family=fam, zorder=6)

    # "BALL" tag near the zone to underline the verdict
    ax.text(zcx, by0-0.05, "RULED A BALL", ha="center", va="top", fontsize=9,
            fontweight="black", color=GREEN, family=fam, zorder=6)

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


if __name__ == "__main__":
    render(dict(pitcher="Eury Pérez", batter="Bo Bichette", balls=3, strikes=1,
        inning=7, half="top", ump="Carlos Torres", miss_inches=4.9, miss_dir="high",
        pX=-0.56, pZ=3.484, sz_top=3.072, sz_bot=1.55,
        away_team="NYM", home_team="MIA", away_id=121, home_id=146,
        away_score=1, home_score=2), "C.png")
    print("wrote C.png")
