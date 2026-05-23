"""
graphic.py — Render the "SMH ump" strike-zone card as a PNG for Bluesky.

Translates Mike's tool design DNA (warm off-white, near-black ink, bold rounded
display type, hard offset drop shadow, dot-grid texture) into a static image.
Accent color: #e8234a (news red) — "ump got dunked on" energy.
"""

from __future__ import annotations
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Circle
import matplotlib.font_manager as fm

# --- design tokens (from mike-tools-design) -----------------------------------
BG = "#fdf8f0"          # warm off-white
INK = "#15120a"         # near-black
MUTED = "#5a5040"
DIM = "#a09080"
ACCENT = "#e8234a"      # news red
SHADOW = "#b8ae9e"      # offset shadow tan
ZONE_EDGE = "#15120a"

PLATE_HALF_WIDTH_FT = (17.0 / 2.0) / 12.0


def _font(weight="bold"):
    # Nunito if available, else a clean rounded fallback
    for name in ("Nunito", "Nunito Sans", "DejaVu Sans"):
        try:
            fm.findfont(name, fallback_to_default=False)
            return name
        except Exception:
            continue
    return "DejaVu Sans"


def render(call: dict, out_path: str) -> str:
    fam = _font()
    fig, ax = plt.subplots(figsize=(6.4, 6.4), dpi=200)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    # dot-grid texture (subtle)
    import numpy as np
    gx, gy = np.meshgrid(np.linspace(0, 1, 26), np.linspace(0, 1, 26))
    ax.scatter(gx.ravel(), gy.ravel(), s=1.4, c="#c4bdb0", alpha=0.5,
               transform=ax.transAxes, zorder=0)

    # --- coordinate frame: feet, centered on plate ---
    top, bot = call["sz_top"], call["sz_bot"]
    px, pz = call["plate_x"], call["plate_z"]
    hw = PLATE_HALF_WIDTH_FT

    # view bounds with padding so the (outside) dot is visible
    xs = [-hw, hw, px]; zs = [bot, top, pz]
    xpad = max(0.45, (max(xs) - min(xs)) * 0.28)
    zpad = max(0.45, (max(zs) - min(zs)) * 0.28)
    ax.set_xlim(min(xs) - xpad, max(xs) + xpad)
    ax.set_ylim(min(zs) - zpad, max(zs) + zpad)
    ax.set_aspect("equal")
    ax.axis("off")

    # --- zone box: hard offset drop shadow, then the box ---
    zw = 2 * hw
    zh = top - bot
    off = 0.05  # offset shadow in data units
    ax.add_patch(FancyBboxPatch((-hw + off, bot - off), zw, zh,
                 boxstyle="round,pad=0.0,rounding_size=0.04",
                 linewidth=0, facecolor=SHADOW, zorder=1))
    ax.add_patch(FancyBboxPatch((-hw, bot), zw, zh,
                 boxstyle="round,pad=0.0,rounding_size=0.04",
                 linewidth=3.5, edgecolor=ZONE_EDGE, facecolor="#fffef9",
                 zorder=2))
    # inner thirds (faint) for that strike-zone feel
    for f in (1/3, 2/3):
        ax.plot([-hw + zw*f, -hw + zw*f], [bot, top], color=DIM, lw=0.8,
                alpha=0.5, zorder=3)
        ax.plot([-hw, hw], [bot + zh*f, bot + zh*f], color=DIM, lw=0.8,
                alpha=0.5, zorder=3)

    # --- the pitch dot (accent, with chunky stroke) ---
    ax.add_patch(Circle((px, pz), 0.12, facecolor=ACCENT, edgecolor=INK,
                 linewidth=3, zorder=5))
    # dashed leader from nearest edge to the dot, labeled with miss
    # nearest horizontal edge — stop the dashes short of the dot so they read
    edge_x = hw if px > 0 else -hw
    if abs(px) > hw:
        stop_x = px - 0.13 if px > 0 else px + 0.13
        ax.annotate("", xy=(stop_x, pz), xytext=(edge_x, pz),
                    arrowprops=dict(arrowstyle="-", linestyle=(0, (4, 3)),
                                    color=ACCENT, lw=2), zorder=4)
        midx = (edge_x + stop_x) / 2
        ax.text(midx, pz + 0.18, f'{call["miss_inches"]:.1f}"',
                ha="center", va="bottom", fontsize=11, fontweight="black",
                color=ACCENT, family=fam, zorder=6)

    # --- text block ---
    miss = call["miss_inches"]
    ax.text(0.5, 0.965, "SMH, UMP.", transform=ax.transAxes, ha="center",
            va="top", fontsize=30, fontweight="black", color=ACCENT,
            family=fam)
    ax.text(0.5, 0.905,
            f"Missed by {miss:.1f} inches — and they STILL had to challenge it",
            transform=ax.transAxes, ha="center", va="top", fontsize=10.5,
            color=MUTED, family=fam, fontweight="bold")

    # bottom matchup strip
    matchup = f'{call["pitcher"]} → {call["batter"]}'
    count = f'{call["balls"]}-{call["strikes"]} count'
    half = "Top" if "top" in str(call.get("half", "")).lower() else "Bot"
    inn = call.get("inning", "")
    situ = f'{half} {inn}  ·  {count}  ·  {call.get("pitch_type","")}'.strip()
    ax.text(0.5, 0.055, matchup, transform=ax.transAxes, ha="center",
            va="bottom", fontsize=13, fontweight="black", color=INK, family=fam)
    ax.text(0.5, 0.018, situ, transform=ax.transAxes, ha="center",
            va="bottom", fontsize=9.5, color=DIM, family=fam, fontweight="bold")

    fig.savefig(out_path, facecolor=BG, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    return out_path


if __name__ == "__main__":
    # quick visual smoke test with a fake call
    demo = dict(pitcher="Some Reliever", batter="Some Hitter", balls=3,
                strikes=2, inning=9, half="Bot", pitch_type="SL",
                miss_inches=4.7, plate_x=0.95, plate_z=2.4, sz_top=3.4,
                sz_bot=1.6)
    render(demo, "demo_card.png")
    print("wrote demo_card.png")
