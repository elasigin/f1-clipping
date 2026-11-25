"""Lap validity, telemetry quality checks and candidate ordering. No I/O."""
from __future__ import annotations

import math

import numpy as np

from . import config as C


def num(v) -> float:
    """Missing values arrive as the string "None", null or NaN."""
    if v is None or isinstance(v, bool) or v == "None":
        return math.nan
    try:
        return float(v)
    except (TypeError, ValueError):
        return math.nan


def column(tel: dict, key: str) -> np.ndarray:
    return np.array([num(v) for v in tel[key]], float)


# --- Lap validity ------------------------------------------------------------
def invalid_reason(laps: dict, i: int, pb_time: float) -> str | None:
    """Why lap i of a column-style laptimes table cannot be used, or None."""
    t = num(laps["time"][i])
    if math.isnan(t):
        return "no time"
    if laps["del"][i] is True:
        return "deleted"
    if laps["compound"][i] not in C.DRY_COMPOUNDS:
        return f"compound {laps['compound'][i]}"
    if laps["wR"][i] is True:
        return "raining"
    if t < pb_time - 1e-6:
        return "quicker than the driver's counted best"
    return None


def candidates(laps: dict) -> tuple[dict[str, list[dict]], dict[str, int]]:
    """Valid laps per team, fastest first, plus a tally of rejection reasons."""
    pb: dict[str, float] = {}
    for i, drv in enumerate(laps["drv"]):
        t = num(laps["time"][i])
        if laps["pb"][i] is True and not math.isnan(t):
            pb[drv] = min(t, pb.get(drv, math.inf))
    teams: dict[str, list[dict]] = {}
    rejected: dict[str, int] = {}
    for i, drv in enumerate(laps["drv"]):
        why = invalid_reason(laps, i, pb.get(drv, math.inf))
        if why == "no time":
            continue
        # A driver with no counted lap at all cannot have a valid one.
        if why is None and drv not in pb:
            why = "driver has no counted lap"
        if why:
            rejected[why] = rejected.get(why, 0) + 1
            continue
        teams.setdefault(laps["team"][i], []).append({
            "team": laps["team"][i], "driver": drv, "lap": int(laps["lap"][i]),
            "time": num(laps["time"][i]), "compound": laps["compound"][i],
            "segment": laps["qs"][i], "accurate": laps["iacc"][i],
        })
    for rows in teams.values():
        rows.sort(key=lambda r: r["time"])
    return teams, rejected


# --- Telemetry quality -------------------------------------------------------
def frozen_intervals(t, speed, rpm, min_s=C.QC_FROZEN_S) -> list[tuple[float, float]]:
    """Time spans where the car channels repeat exactly while the car is moving."""
    same = (np.diff(speed) == 0) & (np.diff(rpm) == 0) & (speed[:-1] > C.QC_FROZEN_MIN_SPEED)
    out, start = [], None
    for i, flag in enumerate(same):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            out.append((float(t[start]), float(t[i])))
            start = None
    if start is not None:
        out.append((float(t[start]), float(t[-1])))
    return [(a, b) for a, b in out if b - a > min_s]


def gap_intervals(t, min_s=C.QC_MAX_GAP_S) -> list[tuple[float, float]]:
    return [(float(t[i]), float(t[i + 1])) for i in np.flatnonzero(np.diff(t) > min_s)]


def path(tel: dict) -> np.ndarray:
    """x/y positions in metres."""
    return np.column_stack([column(tel, "x"), column(tel, "y")]) / C.UNITS_PER_M


def path_length(xy: np.ndarray) -> float:
    return float(np.hypot(*np.diff(xy, axis=0).T).sum())


def line_distance_p95(xy: np.ndarray, ref: np.ndarray, step: float = 2.0) -> float:
    """p95 distance from a lap's points to the densified reference line."""
    seg = np.hypot(*np.diff(ref, axis=0).T)
    s = np.r_[0, np.cumsum(seg)]
    keep = np.r_[True, seg > 0]
    g = np.arange(0, s[-1], step)
    line = np.column_stack([np.interp(g, s[keep], ref[keep, k]) for k in (0, 1)])
    d2 = ((xy[:, None, :] - line[None, :, :]) ** 2).sum(-1).min(1)
    return float(np.percentile(np.sqrt(d2), 95))


def check_lap(tel: dict, lap_time: float, ref: np.ndarray | None = None) -> dict:
    """Metrics and failures for one lap. `maskable` failures can be cut out;
    the others make the whole lap untrustworthy."""
    t, speed, rpm = (column(tel, k) for k in ("time", "speed", "rpm"))
    xy = path(tel)
    ok = np.isfinite(xy).all(1)
    xy_len = path_length(xy[ok])
    dist = float(np.nanmax(column(tel, "distance")))
    frozen, gaps = frozen_intervals(t, speed, rpm), gap_intervals(t)
    bad = sum(b - a for a, b in frozen) + sum(b - a for a, b in gaps)
    m = {
        "samples": len(t), "duration": float(t[-1]), "dist": dist, "xy_len": xy_len,
        "dist_vs_xy": dist / xy_len - 1, "max_gap": float(np.diff(t).max()),
        "frozen_s": sum(b - a for a, b in frozen), "bad_intervals": frozen + gaps,
        "coverage": 1 - bad / float(t[-1]), "xy_vs_ref": None, "line_p95": None,
    }
    fail = []
    if frozen:
        fail.append("frozen")
    if gaps:
        fail.append("gap")
    if abs(m["dist_vs_xy"]) > C.QC_DIST_VS_XY:
        fail.append("dist_vs_xy")
    if abs(m["duration"] - lap_time) > C.QC_DURATION_S:
        fail.append("duration")
    if ref is not None:
        m["xy_vs_ref"] = xy_len / path_length(ref) - 1
        m["line_p95"] = line_distance_p95(xy[ok], ref)
        if abs(m["xy_vs_ref"]) > C.QC_XY_VS_REF:
            fail.append("xy_vs_ref")
        if m["line_p95"] > C.QC_LINE_P95_M:
            fail.append("line")
    m["fail"] = fail
    return m
