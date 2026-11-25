"""Clipping detection on gridded laps. Pure functions, no I/O.

Clipping is inferred: full throttle, no brake, and speed falling over a sustained
distance by more than gravity and cornering explain. There is no battery channel.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .config import Detect

G = 9.81


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Inclusive (first, last) index of each run of True."""
    edge = np.diff(np.r_[0, mask.astype(int), 0])
    return list(zip(np.flatnonzero(edge == 1), np.flatnonzero(edge == -1) - 1))


def trim_end(mask: np.ndarray, cells: int) -> np.ndarray:
    out = mask.copy()
    for a, b in runs(mask):
        if b < len(mask) - 1:               # a run ending at the line is not a lift
            out[max(a, b - cells + 1):b + 1] = False
    return out


def local_fit(v: np.ndarray, mask: np.ndarray, step: float, window: float):
    """Straight-line fit of v over `window` metres, using only cells of the same run,
    so braking never leaks into the full-throttle part. Returns (value, slope per m)."""
    half = int(round(window / step)) // 2
    val, slope = np.full(len(v), np.nan), np.full(len(v), np.nan)
    for a, b in runs(mask):
        if b - a + 1 < 6:
            continue
        for i in range(a, b + 1):
            lo, hi = max(a, i - half), min(b, i + half)
            x = (np.arange(lo, hi + 1) - i) * step
            y = v[lo:hi + 1]
            mx = x.mean()
            k = ((x - mx) * (y - y.mean())).sum() / ((x - mx) ** 2).sum()
            slope[i], val[i] = k, y.mean() - k * mx
    return val, slope


@dataclass
class Result:
    zones: list[dict]
    rejected: list[dict]
    full: np.ndarray                # valid full-throttle cells (the denominator)
    clip: np.ndarray                # cells inside accepted zones
    smooth: np.ndarray
    accel: np.ndarray               # gravity-corrected, m/s^2
    lat_g: np.ndarray
    metrics: dict = field(default_factory=dict)


def detect(speed, throttle, brake, valid, grade, curvature, p: Detect, step: float,
           gap_ahead=None) -> Result:
    """speed km/h, throttle %, brake 0-1, valid bool, grade dz/ds, curvature 1/m."""
    full = valid & (throttle >= p.throttle_min) & (brake <= p.brake_max)
    base = trim_end(full, int(round(p.edge_trim_m / step)))
    sm, slope = local_fit(speed, base, step, p.smooth_m)
    v, dv = sm / 3.6, slope / 3.6
    raw = v * dv                            # acceleration along the track
    acc = raw + G * grade                   # what is left after gravity
    lat = v ** 2 * np.abs(curvature) / G
    with np.errstate(invalid="ignore"):
        falling = base & (sm > p.speed_min) & (raw < 0)
        slowing = "gravity" if p.gravity else "too gentle"      # names the rejection
        rules = {slowing: (acc if p.gravity else raw) <= p.accel_max, "cornering": lat <= p.lat_g_max}
        ok = falling & rules[slowing] & rules["cornering"]

    # Join pieces split by noise, only across cells where speed is falling anyway.
    joined = ok.copy()
    r = runs(ok)
    for (_, b), (c, _) in zip(r, r[1:]):
        if (c - b - 1) * step <= p.merge_gap_m and falling[b:c + 1].all():
            joined[b:c + 1] = True

    def big_enough(a, b):
        return (b - a + 1) * step >= p.min_length_m and sm[a] - sm[b] >= p.min_drop

    def describe(a, b):
        c = slice(a, b + 1)
        z = {"i0": int(a), "i1": int(b), "s0": a * step, "s1": (b + 1) * step,
             "v0": float(sm[a]), "v1": float(sm[b]), "drop": float(sm[a] - sm[b]),
             "sec": float((step / v[c]).sum()), "accel": float(acc[c].mean()),
             "lat_g": float(lat[c].mean()), "grade": float(grade[c].mean())}
        if gap_ahead is not None:
            z["gap_ahead"] = float(gap_ahead[c].min())
            z["tow"] = z["gap_ahead"] < p.tow_gap_m
        return z

    zones, clip = [], np.zeros(len(speed), bool)
    for a, b in runs(joined):
        if big_enough(a, b):
            zones.append(describe(a, b))
            clip[a:b + 1] = True

    # What speed-only detection would have kept, and why we did not.
    rejected = []
    for a, b in runs(falling & ~clip):
        if not big_enough(a, b):
            continue
        z = describe(a, b)
        failing = {k: int((~m[a:b + 1]).sum()) for k, m in rules.items()}
        z["reason"] = max(failing, key=failing.get) if any(failing.values()) else "too short"
        rejected.append(z)

    fullm, clipm = float(full.sum() * step), float(clip.sum() * step)
    tow = sum(z["s1"] - z["s0"] for z in zones if z.get("tow"))
    metrics = {"clip_m": clipm, "full_m": fullm, "share": clipm / fullm if fullm else np.nan,
               "share_no_tow": (clipm - tow) / fullm if fullm else np.nan,
               "sec": sum(z["sec"] for z in zones), "zones": len(zones),
               "max_drop": max((z["drop"] for z in zones), default=0.0),
               "coverage": float(valid.mean())}
    return Result(zones, rejected, full, clip, sm, acc, lat, metrics)
