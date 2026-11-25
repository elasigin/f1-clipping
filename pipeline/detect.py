"""Run detection on every aligned lap, write reports and check the trust gates.

    uv run python -I run.py detect
"""
from __future__ import annotations

import json

import numpy as np

from . import config as C
from . import clipping, fetch


def load(cid: str) -> dict:
    with np.load(C.PROCESSED / f"{cid}.npz") as f:      # no pickles allowed by default
        d = {k: f[k] for k in f.files}
    d["meta"] = json.loads(str(d["meta"]))
    return d


def run_lap(d: dict, i: int, p: C.Detect = C.DETECT) -> clipping.Result:
    return clipping.detect(d["speed"][i], d["throttle"][i], d["brake"][i], d["valid"][i], d["grade"],
                           d["curvature"], p, C.STEP, d["gap_ahead"][i])


def all_laps(p: C.Detect = C.DETECT) -> tuple[list[dict], list[dict]]:
    rows, zones = [], []
    for c in C.CIRCUITS:
        d = load(c.id)
        for i, m in enumerate(d["meta"]):
            r = run_lap(d, i, p)
            bands = (C.STRICT._replace(gravity=p.gravity), C.LOOSE._replace(gravity=p.gravity))
            lo, hi = (run_lap(d, i, q).metrics["share"] for q in bands)
            # Speed-only detection, to show what the confounder rules remove.
            naive = run_lap(d, i, C.DETECT._replace(accel_max=0.0, lat_g_max=1e9)).metrics["share"]
            rows.append({"circuit": c.id, **m, **r.metrics, "lo": lo, "hi": hi, "naive": naive})
            for kind, zs in (("zone", r.zones), ("rejected", r.rejected)):
                zones += [{"circuit": c.id, "season": m["season"], "team": m["team"],
                           "driver": m["driver"], "kind": kind, **z} for z in zs]
    return rows, zones


def gates(rows: list[dict], p: C.Detect) -> list[tuple[str, bool, str]]:
    team = [r for r in rows if r["status"] != "extra"]
    mean = lambda q, k="share": float(np.mean([r[k] for r in q])) if q else np.nan
    pick = lambda s, c=None: [r for r in team if r["season"] == s and (c is None or r["circuit"] == c)]
    out = []

    d = load("spa")
    at = {m["season"]: i for i, m in enumerate(d["meta"]) if m["driver"] == "ANT"}
    k = lambda s, metre: float(d["speed"][at[s]][int(metre / C.STEP)])
    ok = (abs(k(2026, 2000) - 319) <= 2 and abs(k(2025, 2000) - 336) <= 2 and k(2026, 800) > k(2025, 800))
    out.append(("1 Spa sanity numbers", ok, f"2000 m: {k(2026, 2000):.0f} vs {k(2025, 2000):.0f} km/h; "
                f"800 m: {k(2026, 800):.0f} vs {k(2025, 800):.0f}"))

    by25 = {c.id: mean(pick(2025, c.id)) for c in C.CIRCUITS if pick(2025, c.id)}
    worst = max(by25, key=by25.get)
    out.append(("2a 2025 mean share < 0.5%", mean(pick(2025)) < C.GATE_2025_MEAN,
                f"{mean(pick(2025)) * 100:.2f}% (2026 {mean(pick(2026)) * 100:.2f}%)"))
    out.append(("2b no 2025 circuit > 2%", by25[worst] <= C.GATE_2025_CIRCUIT,
                f"worst {worst} {by25[worst] * 100:.2f}%"))
    neg = {c: mean(pick(2026, c)) for c in C.NEGATIVE_CONTROLS}
    out.append(("3 negative controls ~0 in 2026", max(neg.values()) < 0.01,
                ", ".join(f"{c} {v * 100:.2f}%" for c, v in neg.items())))

    def metres(cid, s0, s1):
        d, per = load(cid), []
        for i, m in enumerate(d["meta"]):
            if m["season"] == 2026:
                clip = run_lap(d, i, p).clip[int(s0 / C.STEP):int(s1 / C.STEP)]
                per.append(clip.sum() * C.STEP)
        return float(np.median(per))
    got = {n: (metres(c, a, b), need) for n, (c, a, b, need) in C.KNOWN_STRAIGHTS.items()}
    out.append(("4 known straights found in 2026", all(g >= n for g, n in got.values()),
                ", ".join(f"{k} {g:.0f} m (need {n})" for k, (g, n) in got.items())))
    return out


def variants() -> list[dict]:
    """One rule changed at a time, against the 2025 control."""
    B = C.RULE_B
    table = {
        "A approved": C.RULE_A, "B no gravity correction": B,
        "B, trim 50 m": B._replace(edge_trim_m=50), "B, lateral 1.0 g": B._replace(lat_g_max=1.0),
        "B, lateral 2.0 g": B._replace(lat_g_max=2.0), "B, lateral 2.5 g": B._replace(lat_g_max=2.5),
        "B, accel -0.15": B._replace(accel_max=-0.15), "B, accel -0.6": B._replace(accel_max=-0.6),
        "B, 75 m / 3 km/h": B._replace(min_length_m=75, min_drop=3),
        "B, 150 m / 8 km/h": B._replace(min_length_m=150, min_drop=8),
        "speed only (no corner or hill rule)": B._replace(lat_g_max=1e9),
    }
    data = {c.id: load(c.id) for c in C.CIRCUITS}
    out = []
    for name, p in table.items():
        share: dict = {}
        for cid, d in data.items():
            for i, m in enumerate(d["meta"]):
                if m["status"] != "extra":
                    share.setdefault((m["season"], cid), []).append(run_lap(d, i, p).metrics["share"] * 100)
        mean = {k: float(np.mean(v)) for k, v in share.items()}
        pick = lambda s: [v for (y, _), v in mean.items() if y == s]
        out.append({"variant": name, "2025_mean": np.mean(pick(2025)), "2025_worst": max(pick(2025)),
                    "2026_mean": np.mean(pick(2026)), **{c: mean[2026, c] for c in (
                        "spa", "silverstone", "baku", "vegas", "monza", "suzuka", "singapore")}})
    return [{k: round(float(v), 2) if k != "variant" else v for k, v in r.items()} for r in out]


def table(rows):
    print(f"{'circuit':13s}   2025: share naive  |  2026: share [strict-loose] naive   sec  zones  n")
    for c in C.CIRCUITS:
        line = f"{c.id:13s}"
        for s in C.SEASONS:
            q = [r for r in rows if r["circuit"] == c.id and r["season"] == s and r["status"] != "extra"]
            if not q:
                line += "        (wet)       |" if s == 2025 else "  (wet)"
                continue
            f = lambda k: np.mean([r[k] for r in q])
            line += (f"   {f('share') * 100:5.2f}% {f('naive') * 100:5.2f}%   |" if s == 2025 else
                     f"  {f('share') * 100:5.1f}% [{f('lo') * 100:4.1f}-{f('hi') * 100:4.1f}] "
                     f"{f('naive') * 100:5.1f}%  {f('sec'):4.1f}  {f('zones'):3.1f}  {len(q)}")
        print(line)


def main():
    text = ""
    for name, p in (("A", C.RULE_A), ("B", C.RULE_B)):
        rows, zones = all_laps(p)
        fetch.write_csv(C.REPORTS / f"clipping_by_lap_{name}.csv", rows, list(rows[0]))
        cols = list(dict.fromkeys(k for z in zones for k in z if k not in ("i0", "i1")))
        fetch.write_csv(C.REPORTS / f"zones_{name}.csv", zones, cols)
        print(f"\n=== Rule {name} ===")
        table(rows)
        text += f"Rule {name}\n" + "".join(
            f"  {'PASS' if ok else 'FAIL'}  {g}: {detail}\n" for g, ok, detail in gates(rows, p))
        tow = [z for z in zones if z["kind"] == "zone" and z["tow"]]
        text += f"  zones {sum(z['kind'] == 'zone' for z in zones)}, with a car within {p.tow_gap_m:.0f} m: {len(tow)}\n"
    print("\n" + text)
    (C.REPORTS / "gates.txt").write_text(text)
    v = variants()
    fetch.write_csv(C.REPORTS / "variants.csv", v, list(v[0]))
    for r in v:
        print("  ".join(f"{x:<36}" if isinstance(x, str) else f"{x:6.2f}" for x in r.values()))


if __name__ == "__main__":
    main()
