"""Align every selected lap to its circuit's reference line and resample it.

    uv run python -I run.py process

Reads the cache and data/processed/selection.json. Writes one .npz per circuit to
data/processed/ plus analysis/reports/alignment.csv.
"""
from __future__ import annotations

import json

import numpy as np
from scipy.ndimage import gaussian_filter1d, uniform_filter1d
from scipy.signal import find_peaks

from . import config as C
from . import fetch, qc

G = 9.81


# --- Reference line ------------------------------------------------------------
def odd(m: float, step: float) -> int:
    return max(3, int(round(m / step)) | 1)


def resample_path(xy: np.ndarray, step: float, pad: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Arc-length resampling. A lap closes on itself, so `pad` metres of the far
    end are attached to both ends to let projections run past the line."""
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))]
    keep = np.r_[True, np.diff(d) > 1e-6]
    d, xy = d[keep], xy[keep]
    L = d[-1]
    s = np.arange(-pad, L + pad, step)
    inner = np.clip(s, 0, L)
    out = np.column_stack([np.interp(inner, d, xy[:, k]) for k in (0, 1)])
    if pad:
        gap = xy[0] - xy[-1]                # start/finish mismatch, usually a few m
        wrap = lambda q: np.column_stack([np.interp(q, d, xy[:, k]) for k in (0, 1)])
        out[s < 0] = wrap(L + s[s < 0]) + gap
        out[s > L] = wrap(s[s > L] - L) - gap
    return s, out


def project(xy: np.ndarray, t: np.ndarray, s_ref: np.ndarray, line: np.ndarray) -> np.ndarray:
    """Distance along the reference for each sample, searching only just ahead of the
    previous match so that nearby or crossing parts of the track cannot capture it."""
    step = s_ref[1] - s_ref[0]
    out = np.full(len(xy), np.nan)
    last = int(np.searchsorted(s_ref, 0))
    last_t = t[0]
    for i, p in enumerate(xy):
        if not np.isfinite(p).all():
            continue
        reach = 40 + 110 * (t[i] - last_t)      # 110 m/s is faster than any F1 car
        if i == 0:
            reach = 60
        lo = max(0, last - int((60 if i == 0 else 10) / step))
        hi = min(len(s_ref), last + int(reach / step) + 1)
        last = lo + int(((line[lo:hi] - p) ** 2).sum(1).argmin())
        last_t = t[i]
        out[i] = s_ref[last]
    return out


def station(t, speed, s_proj, bad: list[tuple[float, float]]) -> np.ndarray:
    """Smooth distance: integrated speed for detail, GPS projection for position.
    Where the speed channel is bad the projection supplies the increments."""
    inc = (speed[1:] + speed[:-1]) / 2 / 3.6 * np.diff(t)
    for a, b in bad:
        m = (t[:-1] >= a - 1e-9) & (t[1:] <= b + 1e-9)
        inc[m] = np.diff(s_proj)[m]
    integ = np.r_[0, np.cumsum(inc)]
    resid = s_proj - integ
    tt = np.arange(t[0], t[-1], 0.1)            # even spacing for the filter
    sm = gaussian_filter1d(np.interp(tt, t, resid), C.RESIDUAL_SIGMA_S / 0.1, mode="nearest")
    s = integ + np.interp(t, tt, sm)
    return np.maximum.accumulate(s)


def glitches(speed: np.ndarray) -> np.ndarray:
    """Cells around physically impossible jumps in gridded speed."""
    v = speed / 3.6
    a = v * np.gradient(v, C.STEP)
    bad = np.flatnonzero(((a > C.MAX_ACCEL) | (a < C.MAX_DECEL)) & (v > 25))
    out = np.zeros(len(v), bool)
    if not len(bad):
        return out
    pad, merge = int(C.MASK_PAD_M / C.STEP), int(C.GLITCH_MERGE_M / C.STEP)
    for group in np.split(bad, np.flatnonzero(np.diff(bad) > merge) + 1):
        out[max(0, group[0] - pad):group[-1] + pad + 1] = True
    return out


# --- One lap ---------------------------------------------------------------------
def align(tel: dict, s_ref: np.ndarray, line: np.ndarray, grid: np.ndarray) -> dict:
    t, speed, rpm, thr, brake = (qc.column(tel, k) for k in ("time", "speed", "rpm", "throttle", "brake"))
    xy = qc.path(tel)
    bad = qc.frozen_intervals(t, speed, rpm, C.MASK_FROZEN_S - 1e-9) + qc.gap_intervals(t, C.MASK_GAP_S)
    proj = project(xy, t, s_ref, line)
    ok = np.isfinite(proj) & np.isfinite(speed)
    t, speed, thr, brake, xy, proj = (a[ok] for a in (t, speed, thr, brake, xy, proj))
    s = station(t, speed, proj, bad)
    keep = np.r_[True, np.diff(s) > 1e-6]
    I = lambda a: np.interp(grid, s[keep], a[keep])

    valid = (grid >= s[0] - C.STEP) & (grid <= s[-1] + C.STEP)
    tg = I(t)
    for a, b in bad:
        sa, sb = np.interp([a, b], t, s)
        valid &= ~((grid >= sa - C.MASK_PAD_M) & (grid <= sb + C.MASK_PAD_M))
    th = I(thr)
    # A sentinel reading poisons the interpolated values beside it.
    sentinel = np.interp(grid, s[keep], (thr[keep] > C.THROTTLE_SENTINEL).astype(float)) > 0
    valid &= ~sentinel
    valid &= ~glitches(I(speed))
    gap = qc.column(tel, "DistanceToDriverAhead")[ok]
    gap = np.where(np.isfinite(gap) & (gap > 0), gap, 1e9)
    return {"speed": I(speed), "throttle": np.minimum(th, 100), "brake": I(brake), "time": tg,
            "x": I(xy[:, 0]), "y": I(xy[:, 1]), "z": I(qc.column(tel, "z")[ok]) / C.UNITS_PER_M,
            "drs": I(qc.column(tel, "drs")[ok]), "gap_ahead": I(gap), "valid": valid}


# --- One circuit -------------------------------------------------------------------
def smooth(a, metres):
    return uniform_filter1d(a, odd(metres, C.STEP), mode="nearest")


def geometry(laps: list[dict], n: int) -> dict:
    """Track shape from all laps of one circuit: mean line, curvature, elevation."""
    x = smooth(smooth(np.median([l["x"] for l in laps], axis=0), C.REF_SMOOTH_M), C.REF_SMOOTH_M)
    y = smooth(smooth(np.median([l["y"] for l in laps], axis=0), C.REF_SMOOTH_M), C.REF_SMOOTH_M)
    z = smooth(np.median([l["z"] for l in laps], axis=0), C.Z_SMOOTH_M)
    dx, dy = np.gradient(x), np.gradient(y)
    heading = np.unwrap(np.arctan2(dy, dx))
    ds = np.hypot(dx, dy)
    return {"curvature": np.gradient(heading) / ds, "grade": np.gradient(z, C.STEP), "elev": z}


def minima(v: np.ndarray) -> np.ndarray:
    return find_peaks(-smooth(v, 25), prominence=25)[0]


def process_circuit(circuit: C.Circuit, sel: dict) -> tuple[dict, list[dict]]:
    r = sel["reference"][circuit.id]
    ref_tel = fetch.telemetry(r["season"], circuit, r["driver"], r["lap"])
    ref = qc.path(ref_tel)
    s_ref, line = resample_path(ref, 1.0, pad=60)
    length = float(s_ref[-1] - 60)
    grid = np.arange(0, length, C.STEP)

    meta, laps = [], []
    for m in sel["laps"]:
        if m["circuit"] != circuit.id or m["status"] == "missing":
            continue
        tel = fetch.telemetry(m["season"], circuit, m["driver"], m["lap"])
        laps.append(align(tel, s_ref, line, grid))
        meta.append({k: m[k] for k in ("season", "team", "driver", "lap", "time", "compound", "segment",
                                       "status", "team_best", "team_best_driver")})
    # Geometry from the reference season, whose positions are the cleanest.
    geo = geometry([l for l, m in zip(laps, meta) if m["season"] == r["season"]], len(grid))

    base = np.median([l["speed"] for l, m in zip(laps, meta) if m["season"] == r["season"]], axis=0)
    marks = minima(base)
    rows = []
    for l, m in zip(laps, meta):
        mine, off = minima(l["speed"]), []
        for k in marks:
            if len(mine) and l["valid"][max(0, k - 10):k + 10].all():
                j = mine[np.abs(mine - k).argmin()]
                if abs(j - k) * C.STEP <= 80:
                    off.append((j - k) * C.STEP)
        rows.append({"circuit": circuit.id, **m, "corners": len(off),
                     "offset_median": float(np.median(off)) if off else np.nan,
                     "offset_abs_median": float(np.median(np.abs(off))) if off else np.nan,
                     "valid_share": float(l["valid"].mean())})
    out = {"grid": grid, "length": length, "meta": json.dumps(meta, ensure_ascii=False),
           **geo, **{k: np.array([l[k] for l in laps]) for k in laps[0]}}
    return out, rows


def main():
    sel = json.loads((C.PROCESSED / "selection.json").read_text())
    rows = []
    for c in C.CIRCUITS:
        data, r = process_circuit(c, sel)
        np.savez_compressed(C.PROCESSED / f"{c.id}.npz", **data)
        rows += r
        for s in C.SEASONS:
            q = [x for x in r if x["season"] == s]
            if q:
                print(f"{c.id:13s} {s} laps {len(q):2d}  corner offset "
                      f"{np.nanmedian([x['offset_median'] for x in q]):+5.1f} m, |offset| "
                      f"{np.nanmedian([x['offset_abs_median'] for x in q]):4.1f} (worst lap "
                      f"{np.nanmax([x['offset_abs_median'] for x in q]):4.1f})  valid "
                      f"{np.mean([x['valid_share'] for x in q]) * 100:5.1f}% (min "
                      f"{np.min([x['valid_share'] for x in q]) * 100:4.1f}%)")
    fetch.write_csv(C.REPORTS / "alignment.csv", rows, list(rows[0]))


if __name__ == "__main__":
    main()
