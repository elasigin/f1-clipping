"""Sanity figures for checking detection by eye: analysis/figures/*.png

    uv run python -I run.py figures
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from . import config as C
from . import detect, fetch

INK, SOFT, GRID = "#0b0b0b", "#52514e", "#e4e3df"
SEASON = {2025: "#2a78d6", 2026: "#eb6834"}      # documented slots 1 and 2
REASON = {"cornering": "#8a8984", "gravity": "#c9c8c2", "too gentle": "#c9c8c2", "too short": "#e0dfda"}

plt.rcParams.update({"font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": SOFT, "xtick.color": SOFT,
                     "ytick.color": SOFT, "text.color": INK, "figure.facecolor": "#fcfcfb",
                     "axes.facecolor": "#fcfcfb", "axes.grid": True, "grid.color": GRID,
                     "grid.linewidth": 0.6, "axes.spines.top": False, "axes.spines.right": False,
                     "hatch.linewidth": 0.8})

# circuit, (2025 driver or None for the fastest lap), same for 2026, title note
DETAIL = (("spa", "ANT", "ANT", "hero case; same driver in both seasons"),
          ("silverstone", None, None, "worst 2025 false positives before the corner rule"),
          ("baku", None, None, "long straight"),
          ("singapore", None, None, "negative control"))


def pick(d, season, driver=None):
    idx = [i for i, m in enumerate(d["meta"]) if m["season"] == season]
    if driver:
        return next(i for i in idx if d["meta"][i]["driver"] == driver)
    idx = [i for i in idx if d["meta"][i]["status"] != "extra"]
    return min(idx, key=lambda i: d["meta"][i]["time"]) if idx else None


def masked(a, ok):
    return np.where(ok, a, np.nan)


def detail(cid, drv25, drv26, note):
    c = next(c for c in C.CIRCUITS if c.id == cid)
    d, s = detect.load(cid), None
    s = d["grid"]
    i = {2025: pick(d, 2025, drv25), 2026: pick(d, 2026, drv26)}
    res = {(y, r): detect.run_lap(d, i[y], p) for y in C.SEASONS
           for r, p in (("A", C.RULE_A), ("B", C.RULE_B))}
    fig, ax = plt.subplots(6, 1, figsize=(17, 13.5), sharex=True, layout="constrained",
                           gridspec_kw={"height_ratios": [1.9, 3.6, 1.1, 2, 1.5, 1.1]})

    # Strips: what each rule accepts, and what was rejected.
    rows = [(2026, "A"), (2026, "B"), (2026, "rej"), (2025, "A"), (2025, "B"), (2025, "rej")]
    for k, (y, r) in enumerate(rows):
        yy = len(rows) - 1 - k
        if r == "rej":
            for z in res[y, "B"].rejected:
                ax[0].barh(yy, z["s1"] - z["s0"], left=z["s0"], height=0.7, color=REASON[z["reason"]])
                ax[0].text((z["s0"] + z["s1"]) / 2, yy, z["reason"], ha="center", va="center", fontsize=7)
        else:
            for z in res[y, r].zones:
                ax[0].barh(yy, z["s1"] - z["s0"], left=z["s0"], height=0.7, color=SEASON[y],
                           hatch="////", edgecolor="white", linewidth=0)
    ax[0].set_yticks(range(len(rows)), [f"{y} {'rejected by B' if r == 'rej' else 'rule ' + r}"
                                        for y, r in rows][::-1])
    ax[0].set_ylim(-0.6, len(rows) - 0.4)
    ax[0].grid(axis="y", visible=False)

    for z in res[2026, "B"].zones:
        for a in ax[1:]:
            a.axvspan(z["s0"], z["s1"], color=SEASON[2026], alpha=0.13, lw=0)
        ax[1].annotate(f"−{z['drop']:.0f} km/h\n{z['s1'] - z['s0']:.0f} m",
                       ((z["s0"] + z["s1"]) / 2, 375), ha="center", va="center", fontsize=8)
    for y in C.SEASONS:
        j, m, ok = i[y], d["meta"][i[y]], d["valid"][i[y]]
        lab = f"{y} {m['driver']} {m['team']} {m['time']:.3f}"
        ax[1].plot(s, masked(d["speed"][j], ok), color=SEASON[y], lw=1.6, label=lab)
        ax[2].plot(s, masked(d["throttle"][j], ok), color=SEASON[y], lw=1.2)
        ax[3].plot(s, res[y, "B"].accel - 9.81 * d["grade"], color=SEASON[y], lw=1.4)
        ax[4].plot(s, res[y, "B"].lat_g, color=SEASON[y], lw=1.2)
        # masked telemetry, drawn at the bottom so a gap is never mistaken for zero
        for a, b in detect.clipping.runs(~ok):
            ax[1].plot([s[a], s[b]], [62 if y == 2026 else 54] * 2, color=SEASON[y], lw=3, solid_capstyle="butt")
    ax[1].text(0, 70, "masked telemetry", fontsize=7, color=SOFT, va="bottom")
    ax[1].set_ylim(45, 400); ax[1].set_ylabel("speed (km/h)")
    ax[1].legend(loc="lower left", bbox_to_anchor=(0, 0.98), frameon=False, ncols=2, borderaxespad=0)
    ax[2].set_ylabel("throttle %"); ax[2].set_ylim(-5, 108)
    p = C.RULE_B
    ax[3].axhline(p.accel_max, color=INK, lw=0.8, ls="--")
    ax[3].axhline(0, color=SOFT, lw=0.6)
    ax[3].text(s[-1], p.accel_max, f" {p.accel_max}", va="center", fontsize=7)
    ax[3].set_ylim(-5.5, 5); ax[3].set_ylabel("full-throttle\nacceleration (m/s²)")
    ax[4].axhline(p.lat_g_max, color=INK, lw=0.8, ls="--")
    ax[4].text(s[-1], p.lat_g_max, f" {p.lat_g_max} g", va="center", fontsize=7)
    ax[4].set_ylim(0, 6); ax[4].set_ylabel("lateral load (g)")
    ax[5].plot(s, d["elev"] - d["elev"].min(), color=SOFT, lw=1.4)
    ax[5].set_ylabel("elevation (m)"); ax[5].set_xlabel("distance along the reference line (m)")
    ax[5].set_xlim(0, s[-1])
    corners = fetch.session_file(2026, c, "corners.json")
    for lab, dist in zip(corners.get("CornerLabel", []), corners.get("MVDistance", [])):
        if dist is not None:
            ax[0].text(float(dist), len(rows) - 0.3, lab, fontsize=7, color=SOFT, ha="center")
    sh = {k: r.metrics["share"] * 100 for k, r in res.items()}
    fig.suptitle(f"{c.name}: {note}.  Clipping share of full-throttle distance: 2026 rule A {sh[2026, 'A']:.1f}%, "
                 f"rule B {sh[2026, 'B']:.1f}%; 2025 A {sh[2025, 'A']:.1f}%, B {sh[2025, 'B']:.1f}%", fontsize=12)
    fig.savefig(C.FIGURES / f"{cid}.png", dpi=110)
    plt.close(fig)


def contact():
    fig, axes = plt.subplots(7, 3, figsize=(20, 22), layout="constrained")
    for a, c in zip(axes.flat, C.CIRCUITS):
        d, txt = detect.load(c.id), []
        s = d["grid"]
        for y in C.SEASONS:
            i = pick(d, y)
            if i is None:
                txt.append(f"{y} wet")
                continue
            r = detect.run_lap(d, i, C.RULE_B)
            m = d["meta"][i]
            a.plot(s, masked(d["speed"][i], d["valid"][i]), color=SEASON[y], lw=1.2)
            for z in r.zones:
                a.axvspan(z["s0"], z["s1"], ymin=0 if y == 2026 else 0.92, color=SEASON[y], alpha=0.2, lw=0)
            txt.append(f"{y} {m['driver']} {r.metrics['share'] * 100:.1f}%")
        a.set_title(f"{c.name}   " + ",  ".join(txt), fontsize=10, loc="left")
        a.set_ylim(40, 370); a.set_xlim(0, s[-1])
    for a in list(axes.flat)[len(C.CIRCUITS):]:
        a.axis("off")
    fig.suptitle("Fastest usable lap per season, speed (km/h) by distance (m). Shaded: clipping, rule B. "
                 "Blue 2025, orange 2026. Line gaps are masked telemetry.", fontsize=13)
    fig.savefig(C.FIGURES / "all_circuits.png", dpi=75)
    plt.close(fig)


def main():
    C.FIGURES.mkdir(parents=True, exist_ok=True)
    for args in DETAIL:
        detail(*args)
    contact()
    print("wrote", ", ".join(sorted(p.name for p in C.FIGURES.glob("*.png"))))


if __name__ == "__main__":
    main()
