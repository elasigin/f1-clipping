"""Synthetic straights with known answers."""
import numpy as np
import pytest

from pipeline import clipping, config as C

N, STEP = 400, 5.0      # 2 km
RNG = np.random.default_rng(1)


def track(**kw):
    d = dict(speed=np.full(N, 300.0), throttle=np.full(N, 100.0), brake=np.zeros(N),
             valid=np.ones(N, bool), grade=np.zeros(N), curvature=np.zeros(N))
    d.update(kw)
    return d


def run(p=C.RULE_A, **kw):
    return clipping.detect(**track(**kw), p=p, step=STEP)


def fall(a=200, b=320, v0=320.0, v1=290.0):
    """Accelerate to v0, lose speed between cells a and b, then hold."""
    v = np.empty(N)
    v[:a] = np.linspace(250, v0, a)
    v[a:b] = np.linspace(v0, v1, b - a)
    v[b:] = v1
    return v


def test_real_clip_is_found_where_it_is():
    r = run(speed=fall() + RNG.normal(0, 0.5, N))
    z, = r.zones
    assert z["s0"] == pytest.approx(1000, abs=60) and z["s1"] == pytest.approx(1600, abs=60)
    assert z["drop"] == pytest.approx(30, abs=4)
    assert r.metrics["share"] == pytest.approx(600 / 2000, abs=0.05)


def test_plateau_and_acceleration_are_not_clipping():
    v = 250 + 80 * (1 - np.exp(-np.arange(N) / 80))     # drag-limited
    assert run(speed=v + RNG.normal(0, 0.7, N)).zones == []


def test_lift_and_brake_are_not_clipping():
    thr = np.full(N, 100.0); thr[200:] = 40
    assert run(speed=fall(), throttle=thr).zones == []
    brk = np.zeros(N); brk[200:] = 1
    assert run(speed=fall(), brake=brk).zones == []


def test_late_throttle_flag_does_not_make_a_zone():
    """Speed starts to fall 25 m before the channels show the lift."""
    thr = np.full(N, 100.0); thr[205:] = 0
    assert run(speed=fall(200, 260, 320, 150), throttle=thr).zones == []


def test_uphill_slowdown_is_gravity():
    v = fall(200, 320, 300, 285)
    a = 292 / 3.6 * (-15 / 3.6) / 600                   # about -0.56 m/s^2
    up = np.zeros(N); up[190:330] = -a / clipping.G      # exactly cancels
    assert run(speed=v, grade=up).zones == []
    assert run(speed=v, grade=up).rejected[0]["reason"] == "gravity"
    assert len(run(speed=v).zones) == 1                  # same trace on the flat
    assert len(run(p=C.RULE_B, speed=v, grade=up).zones) == 1    # rule B ignores the hill


def test_flat_out_corner_is_rejected():
    k = np.zeros(N); k[190:330] = 3 * clipping.G / (300 / 3.6) ** 2    # 3 g at 300 km/h
    r = run(speed=fall(), curvature=k)
    assert r.zones == [] and r.rejected[0]["reason"] == "cornering"


def test_masked_cells_count_nowhere():
    ok = np.ones(N, bool); ok[180:340] = False
    r = run(speed=fall(), valid=ok)
    assert r.zones == [] and r.metrics["full_m"] == (N - 160) * STEP


def test_short_or_shallow_falls_are_ignored():
    assert run(speed=fall(200, 215, 300, 296)).zones == []       # 75 m, 4 km/h
    assert run(speed=fall(200, 260, 300, 297)).zones == []       # long but only 3 km/h
    slow = np.r_[np.linspace(120, 170, 200), np.linspace(170, 140, 120), np.full(80, 140.0)]
    assert run(speed=slow).zones == []                           # below SPEED_MIN


def test_presets_are_ordered():
    v = fall(200, 260, 300, 288) + RNG.normal(0, 0.3, N)
    s = [run(p=p, speed=v).metrics["clip_m"] for p in (C.STRICT, C.DETECT, C.LOOSE)]
    assert s == sorted(s)


def test_tow_is_flagged_not_removed():
    r = clipping.detect(**track(speed=fall()), p=C.DETECT, step=STEP, gap_ahead=np.full(N, 40.0))
    assert r.zones[0]["tow"] and r.metrics["share"] > 0 and r.metrics["share_no_tow"] == 0
