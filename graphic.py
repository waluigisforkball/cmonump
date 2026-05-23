"""
graphic.py — Render the "SMH ump" strike-zone card as a PNG for Bluesky.

Mike's tool design DNA (warm off-white, near-black ink, bold rounded display
type, hard offset drop shadow, dot-grid texture). Accent: #e8234a (news red).

Layout is FIXED into three horizontal bands so nothing shifts with the data:
  - title band (top): "SMH, <UMP>." + one-line subtitle
  - zone band (middle): strike-zone box drawn into a fixed sub-rect, pitch dot
    placed by mapping real feet -> that sub-rect, clamped so it can never leave
    the canvas no matter how far the pitch missed
  - footer band (bottom): matchup + situation
All text auto-shrinks to fit width. Handles wide / high / low misses.
"""

from __future__ import annotations
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Circle
import matplotlib.font_manager as fm
import numpy as np

# --- design tokens ------------------------------------------------------------
BG = "#fdf8f0"; INK = "#15120a"; MUTED = "#5a5040"; DIM = "#a09080"
ACCENT = "#e8234a"; SHADOW = "#b8ae9e"; ZONE_EDGE = "#15120a"; WHITE = "#fffef9"

PLATE_HALF_WIDTH_FT = (17.0 / 2.0) / 12.0
FT_TO_IN = 12.0


def _font():
    for name in ("Nunito", "Nunito Sans", "DejaVu Sans"):
        try:
            fm.findfont(name, fallback_to_default=False)
            return name
        except Exception:
            continue
    return "DejaVu Sans"


def _fit_text(ax, x, y, s, *, fontsize, weight, color, fam, max_frac,
              ha="center", va="center"):
    """Place text, shrinking fontsize until it fits within max_frac of width."""
    fig = ax.figure
    t = ax.text(x, y, s, transform=ax.transAxes, ha=ha, va=va,
                fontsize=fontsize, fontweight=weight, color=color, family=fam)
    fig.canvas.draw()
    bb = t.get_window_extent()
    ax_bb = ax.get_window_extent()
    frac = bb.width / ax_bb.width
    if frac > max_frac:
        t.set_fontsize(max(6, fontsize * max_frac / frac))
    return t


def render(call: dict, out_path: str) -> str:
    fam = _font()
    fig, ax = plt.subplots(figsize=(6.4, 6.4), dpi=200)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    # Use a FIXED 0..1 x 0..1 canvas in axes coords; ignore data-driven rescaling.
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")     # square fig => square coord => no distortion
    ax.axis("off")

    # dot-grid texture
    gx, gy = np.meshgrid(np.linspace(0.02, 0.98, 26),
                         np.linspace(0.02, 0.98, 26))
    ax.scatter(gx.ravel(), gy.ravel(), s=1.4, c="#c4bdb0", alpha=0.5, zorder=0)

    # ---- bands (fixed) ----
    #  title:  y 0.86 - 0.99
    #  zone:   y 0.20 - 0.80   (the box itself smaller, centered)
    #  footer: y 0.02 - 0.14

    miss = float(call["miss_inches"])
    mdir = str(call.get("miss_dir", "")).lower()
    ump = str(call.get("ump", "") or "").strip()

    # ===== TITLE BAND =====
    title = f"SMH, {ump.upper()}." if ump else "SMH, UMP."
    _fit_text(ax, 0.5, 0.945, title, fontsize=30, weight="black",
              color=ACCENT, fam=fam, max_frac=0.92)
    sub = f"Missed by {miss:.1f}\" - challenged, overturned, announced to everyone"
    _fit_text(ax, 0.5, 0.885, sub, fontsize=10.5, weight="bold",
              color=MUTED, fam=fam, max_frac=0.96)

    # ===== ZONE BAND =====
    # Fixed sub-rectangle the zone is drawn into (axes coords).
    ZX0, ZX1 = 0.30, 0.70     # zone box horizontal span
    ZY0, ZY1 = 0.34, 0.66     # zone box vertical span
    zcx, zcy = (ZX0 + ZX1) / 2, (ZY0 + ZY1) / 2

    top, bot = call["sz_top"], call["sz_bot"]
    px, pz = call["pX"], call["pZ"]
    hw = PLATE_HALF_WIDTH_FT
    zw_ft = 2 * hw
    zh_ft = max(0.1, top - bot)

    # scale: feet -> axes units, using the box span. Keep x/y same scale (equal aspect).
    sx = (ZX1 - ZX0) / zw_ft
    sy = (ZY1 - ZY0) / zh_ft
    s = min(sx, sy)           # uniform scale so the box isn't stretched

    def fx(x_ft):   # plate_x (0 = middle) -> axes x
        return zcx + x_ft * s
    def fy(z_ft):   # height -> axes y, centered on zone midpoint
        return zcy + (z_ft - (top + bot) / 2) * s

    # shadow + box
    bx0, bx1 = fx(-hw), fx(hw)
    by0, by1 = fy(bot), fy(top)
    off = 0.012
    ax.add_patch(FancyBboxPatch((bx0 + off, by0 - off), bx1 - bx0, by1 - by0,
                 boxstyle="round,pad=0,rounding_size=0.012", linewidth=0,
                 facecolor=SHADOW, zorder=1))
    ax.add_patch(FancyBboxPatch((bx0, by0), bx1 - bx0, by1 - by0,
                 boxstyle="round,pad=0,rounding_size=0.012", linewidth=3.5,
                 edgecolor=ZONE_EDGE, facecolor=WHITE, zorder=2))
    for f in (1/3, 2/3):
        ax.plot([bx0 + (bx1-bx0)*f]*2, [by0, by1], color=DIM, lw=0.8,
                alpha=0.5, zorder=3)
        ax.plot([bx0, bx1], [by0 + (by1-by0)*f]*2, color=DIM, lw=0.8,
                alpha=0.5, zorder=3)

    # pitch dot — map then CLAMP into a safe inner margin so it never leaves canvas
    dot_x = fx(px); dot_y = fy(pz)
    MARGIN = 0.10
    dot_x = min(max(dot_x, MARGIN), 1 - MARGIN)
    dot_y = min(max(dot_y, ZY0 - 0.06), ZY1 + 0.06)  # keep within zone band-ish
    dot_y = min(max(dot_y, 0.24), 0.76)
    ax.add_patch(Circle((dot_x, dot_y), 0.032, facecolor=ACCENT,
                 edgecolor=INK, linewidth=3, zorder=5))

    # leader + miss label: pick nearest edge based on miss direction
    if "high" in mdir or "low" in mdir:
        edge_y = by1 if "high" in mdir else by0
        ex = min(max(dot_x, bx0), bx1)
        gap = 0.045
        sy_stop = dot_y - gap if dot_y > edge_y else dot_y + gap
        ax.annotate("", xy=(ex, sy_stop), xytext=(ex, edge_y),
                    arrowprops=dict(arrowstyle="-", linestyle=(0, (4, 3)),
                                    color=ACCENT, lw=2), zorder=4)
        ax.text(ex + 0.06, (edge_y + sy_stop) / 2, f'{miss:.1f}"',
                ha="left", va="center", fontsize=11, fontweight="black",
                color=ACCENT, family=fam, zorder=6)
    else:  # wide
        edge_x = bx1 if dot_x > zcx else bx0
        gap = 0.05
        sx_stop = dot_x - gap if dot_x > edge_x else dot_x + gap
        ax.annotate("", xy=(sx_stop, dot_y), xytext=(edge_x, dot_y),
                    arrowprops=dict(arrowstyle="-", linestyle=(0, (4, 3)),
                                    color=ACCENT, lw=2), zorder=4)
        # place label above the dot, offset enough to clear the 0.032 radius
        ax.text(dot_x, dot_y + 0.075, f'{miss:.1f}"',
                ha="center", va="bottom", fontsize=11, fontweight="black",
                color=ACCENT, family=fam, zorder=6)

    # ===== FOOTER BAND =====
    matchup = f'{call["pitcher"]}  ->  {call["batter"]}'
    _fit_text(ax, 0.5, 0.105, matchup, fontsize=13, weight="black",
              color=INK, fam=fam, max_frac=0.94)
    half = "Top" if "top" in str(call.get("half", "")).lower() else "Bot"
    inn = call.get("inning", "")
    count = f'{call.get("balls", 0)}-{call.get("strikes", 0)} count'
    situ = f'{half} {inn}  -  {count}'.strip()
    _fit_text(ax, 0.5, 0.055, situ, fontsize=9.5, weight="bold",
              color=DIM, fam=fam, max_frac=0.9)

    fig.savefig(out_path, facecolor=BG, bbox_inches="tight", pad_inches=0.22)
    plt.close(fig)
    return out_path


if __name__ == "__main__":
    render(dict(pitcher="Some Reliever", batter="Some Hitter", balls=3,
                strikes=2, inning=9, half="bottom", ump="C.B. Bucknor",
                miss_inches=4.7, miss_dir="wide", pX=0.95, pZ=2.4,
                sz_top=3.4, sz_bot=1.6), "demo_card.png")
    print("wrote demo_card.png")
