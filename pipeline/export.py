"""Write the compact JSON the site reads (site/data/).

    uv run python -I run.py export
"""
from __future__ import annotations

import json
import shutil

import numpy as np

from . import config as C
from . import detect, fetch, qc

EVERY = int(C.SITE_STEP / C.STEP)
TEAM_ID = {(s, names[s - 2025 + 1]): tid for tid, names in C.TEAMS.items() for s in C.SEASONS}


def dump(path, obj) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    path.write_text(text)
    return len(text.encode())


def series(a, ok, digits=None):
    """Every other cell; masked cells become null, never zero."""
    out = []
    for v, good in zip(a[::EVERY], ok[::EVERY]):
        out.append((round(float(v), digits) if digits else int(round(float(v)))) if good else None)
    return out


def corners(circuit: C.Circuit, d: dict) -> list[dict]:
    """Corner markers placed on our reference line by position, not by their own distance."""
    season = min(m["season"] for m in d["meta"])
    k = fetch.session_file(season, circuit, "corners.json")
    line = np.column_stack([d["x_ref"], d["y_ref"]])
    out = []
    for lab, x, y, dist in zip(k["CornerLabel"], k["X"], k["Y"], k["MVDistance"]):
        p = np.array([qc.num(x), qc.num(y)]) / C.UNITS_PER_M
        near = np.hypot(*(line - p).T)
        off = np.abs(d["grid"] - qc.num(dist))
        near[np.minimum(off, d["length"] - off) > 400] = np.inf   # never jump across the track
        out.append({"label": str(lab), "s": int(d["grid"][near.argmin()])})
    return out


def sections(circuit: C.Circuit, d: dict, marks: list[dict]) -> list[dict]:
    """Stretches where most laps are at full throttle, named by the corners around them."""
    thr = np.where(d["valid"], d["throttle"], np.nan)
    with np.errstate(all="ignore"):
        full = np.nan_to_num(np.nanmedian(thr, axis=0)) >= C.DETECT.throttle_min
    out = []
    for a, b in detect.clipping.runs(full):
        s0, s1 = float(d["grid"][a]), float(d["grid"][b])
        if s1 - s0 < C.SECTION_MIN_M:
            continue
        # A corner at the edge of the run bounds it; one well inside is taken flat out.
        before = [m["label"] for m in marks if m["s"] <= s0 + 30]
        after = [m["label"] for m in marks if m["s"] >= s1 - 30]
        name = (f"T{before[-1]}" if before else "Start") + " to " + (f"T{after[0]}" if after else "finish")
        note = C.SECTION_NOTES.get((circuit.id, name))
        out.append({"id": f"{int(s0)}-{int(s1)}", "name": f"{name} ({note})" if note else name,
                    "s0": int(s0), "s1": int(s1)})
    return out


def lap_key(m) -> str:
    key = f"{m['season']}-{TEAM_ID[m['season'], m['team']]}"
    return key + f"-{m['driver'].lower()}" if m["status"] == "extra" else key


def circuit_json(c: C.Circuit) -> tuple[dict, dict]:
    d = detect.load(c.id)
    ref_season = min(m["season"] for m in d["meta"])
    idx = [i for i, m in enumerate(d["meta"]) if m["season"] == ref_season]
    d["x_ref"], d["y_ref"] = (np.median(d[k][idx], axis=0) for k in ("x", "y"))
    laps, best = {}, {}
    for i, m in enumerate(d["meta"]):
        r = detect.run_lap(d, i)
        lo, hi = (detect.run_lap(d, i, p).metrics["share"] for p in (C.STRICT, C.LOOSE))
        key = lap_key(m)
        laps[key] = {
            "season": m["season"], "team": TEAM_ID[m["season"], m["team"]], "teamName": m["team"],
            "driver": m["driver"], "lap": m["lap"], "time": m["time"], "compound": m["compound"],
            "segment": m["segment"], "status": m["status"],
            "teamBest": {"driver": m["team_best_driver"], "time": m["team_best"]},
            "speed": series(d["speed"][i], d["valid"][i], 1),
            "throttle": series(d["throttle"][i], d["valid"][i]),
            "zones": [{"s0": int(z["s0"]), "s1": int(z["s1"]), "v0": round(z["v0"]), "v1": round(z["v1"]),
                       "drop": round(z["drop"], 1), "sec": round(z["sec"], 1), "tow": bool(z["tow"])}
                      for z in r.zones],
            "metrics": {"clipM": int(r.metrics["clip_m"]), "fullM": int(r.metrics["full_m"]),
                        "share": round(r.metrics["share"], 4), "lo": round(lo, 4), "hi": round(hi, 4),
                        "sec": round(r.metrics["sec"], 1), "coverage": round(r.metrics["coverage"], 3)},
        }
        s = m["season"]
        if m["status"] != "extra":
            if s not in best or m["time"] < laps[best[s]]["time"]:
                best[s] = key

    def pair(pid, label, a, b, note=None):
        return {"id": pid, "label": label, "a": a if a in laps else None, "b": b if b in laps else None,
                **({"note": note} if note else {})}
    pairs = [pair("fastest", "Fastest lap of each season", best.get(2025), best.get(2026))]
    for season, cid, drv, _ in C.EXTRA_LAPS:
        if cid == c.id:
            extra = next(k for k in laps if laps[k]["status"] == "extra")
            mate = next(k for k in laps if laps[k]["season"] == 2026 and laps[k]["driver"] == drv)
            pairs.append(pair(f"driver-{drv.lower()}", "Antonelli in both seasons", extra, mate))
    for tid, names in C.TEAMS.items():
        a, b = f"2025-{tid}", f"2026-{tid}"
        note = None
        if tid == "cadillac":
            a, note = best.get(2025), "Cadillac did not race in 2025, so this compares with the fastest 2025 lap."
        if tid == "audi":
            note = "Kick Sauber became Audi for 2026."
        pairs.append(pair(tid, names[0], a, b, note))
    # What each session's true fastest usable-by-rule lap was, for honest labelling.
    for s, key in best.items():
        laps[key]["fastest"] = True
        top = min((l["teamBest"]["time"], l["teamBest"]["driver"]) for l in laps.values()
                  if l["season"] == s and l["status"] != "extra")
        laps[key]["sessionBest"] = {"driver": top[1], "time": top[0]}

    ok = np.ones(len(d["grid"]), bool)
    info = fetch.session_file(2026, c, "session_info.json")["session_info"]
    k = fetch.session_file(ref_season, c, "corners.json")
    wet = [s for s in C.SEASONS if (s, c.id) in C.EXPECTED_WET]
    head = {"id": c.id, "name": c.name, "short": C.SHORT.get(c.id, c.name), "event2025": c.event(2025), "event2026": c.event(2026),
            "date2026": str(info["StartDate"])[:10], "lengthM": int(round(float(d["length"]))),
            "status": "wet" if wet else "low" if c.id in C.LOW_CONFIDENCE else "ok",
            "reason": (f"{wet[0]} qualifying was wet, so there is no dry {wet[0]} lap to compare."
                       if wet else C.LOW_CONFIDENCE.get(c.id))}
    marks = corners(c, d)
    body = {"id": c.id, "step": C.SITE_STEP, "n": len(d["grid"][::EVERY]), "rotation": k.get("Rotation") or 0,
            "ref": {"x": series(d["x_ref"], ok, 1), "y": series(d["y_ref"], ok, 1),
                    "z": series(d["elev"] - d["elev"].min(), ok, 1)},
            "corners": marks, "segments": sections(c, d, marks), "laps": laps, "pairs": pairs}
    return head, body


def season_rows(cid: str, laps: dict) -> list[dict]:
    keep = ("season", "team", "driver", "time", "status")
    return [{"circuit": cid, **{k: l[k] for k in keep}, **l["metrics"],
             "maxDrop": max((z["drop"] for z in l["zones"]), default=0)}
            for l in laps.values() if l["status"] != "extra"]


def team_summary(rows: list[dict]) -> list[dict]:
    """Mean 2026 share per team and its gap to the circuit median, with a 95% interval from
    resampling circuits. Uses only circuits where every team has a value."""
    r26 = [r for r in rows if r["season"] == 2026]
    value = {(r["circuit"], r["team"]): r["share"] for r in r26}
    teams = [t for t in C.TEAMS]
    circuits = [c for c in dict.fromkeys(r["circuit"] for r in r26) if all((c, t) in value for t in teams)]
    a = np.array([[value[c, t] for c in circuits] for t in teams])
    rel = a - np.median(a, axis=0)
    pick = np.random.default_rng(0).integers(0, len(circuits), (C.BOOTSTRAP, len(circuits)))
    boot = rel[:, pick].mean(axis=2)
    return [{"team": t, "n": len(circuits), "mean": round(float(a[i].mean()), 4),
             "rel": round(float(rel[i].mean()), 4),
             "relLo": round(float(np.percentile(boot[i], 2.5)), 4),
             "relHi": round(float(np.percentile(boot[i], 97.5)), 4)} for i, t in enumerate(teams)]


def main():
    shutil.rmtree(C.SITE_DATA, ignore_errors=True)      # only generated files live here
    heads, rows, total = [], [], 0
    for c in C.CIRCUITS:
        head, body = circuit_json(c)
        heads.append(head)
        rows += season_rows(c.id, body["laps"])
        total += dump(C.SITE_DATA / "circuits" / f"{c.id}.json", body)
    index = {
        "source": {"2025": C.SHA[2025], "2026": C.SHA[2026], "license": "Apache-2.0",
                   "repo": "https://github.com/TracingInsights"},
        "thresholds": C.DETECT._asdict(),
        "teams": [{"id": t, "name": n[0], "pu2025": n[3], "pu2026": n[4]} for t, n in C.TEAMS.items()],
        "circuits": heads,
        "excluded": [{"season": s, "event": f"{e} Grand Prix", "reason": r} for (s, e), r in C.EXCLUDED.items()],
    }
    total += dump(C.SITE_DATA / "season.json", {"rows": rows, "teams": team_summary(rows), "ruleChanges": list(C.RULE_CHANGES)})
    total += dump(C.SITE_DATA / "index.json", index)
    print(f"{len(heads)} circuits, {total / 1e6:.2f} MB in site/data")


if __name__ == "__main__":
    main()
