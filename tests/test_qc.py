import math

import numpy as np
import pytest

from pipeline import config as C
from pipeline import qc

RNG = np.random.default_rng(0)


def lap(n=800, dt=0.12, r=800.0):
    """A clean synthetic lap around a circle, with varying speed and rpm."""
    t = np.arange(n) * dt
    speed = 220 + 60 * np.sin(t / 5)
    s = np.r_[0, np.cumsum((speed[1:] + speed[:-1]) / 2 / 3.6 * dt)]
    a = s / s[-1] * 2 * math.pi
    r = s[-1] / (2 * math.pi)
    return {"time": t.tolist(), "speed": speed.tolist(),
            "rpm": (11000 + RNG.integers(-300, 300, n)).tolist(),
            "distance": s.tolist(), "x": (r * np.cos(a) * 10).tolist(),
            "y": (r * np.sin(a) * 10).tolist()}


def dur(tel):
    return tel["time"][-1]


def test_num_handles_every_missing_form():
    assert all(math.isnan(qc.num(v)) for v in (None, "None", float("nan"), "abc", True))
    assert qc.num("3.5") == 3.5


def test_clean_lap_passes():
    tel = lap()
    m = qc.check_lap(tel, dur(tel), qc.path(tel))
    assert m["fail"] == [] and m["coverage"] == 1
    assert m["xy_len"] == pytest.approx(m["dist"], rel=0.001)   # decimetres converted


def test_frozen_stretch_is_found_and_masked():
    tel = lap()
    for k in ("speed", "rpm"):
        tel[k][200:300] = [tel[k][200]] * 100
    m = qc.check_lap(tel, dur(tel))
    assert "frozen" in m["fail"]
    (a, b), = m["bad_intervals"]
    assert a == pytest.approx(200 * 0.12) and b == pytest.approx(299 * 0.12)
    assert m["coverage"] == pytest.approx(1 - 99 * 0.12 / dur(tel))


def test_constant_speed_with_live_rpm_is_not_frozen():
    tel = lap()
    tel["speed"][200:300] = [330.0] * 100
    assert "frozen" not in qc.check_lap(tel, dur(tel))["fail"]


def test_gap_distance_and_duration_failures():
    tel = lap()
    tel = {k: v[:300] + v[320:] for k, v in tel.items()}
    assert "gap" in qc.check_lap(tel, dur(tel))["fail"]
    tel = lap()
    tel["distance"] = [d * 1.03 for d in tel["distance"]]
    assert qc.check_lap(tel, dur(tel) + 0.5)["fail"] == ["dist_vs_xy", "duration"]


def test_position_shift_fails_line_check():
    tel = lap()
    ref = qc.path(tel)
    tel["x"] = [x + 400 for x in tel["x"]]
    assert "line" in qc.check_lap(tel, dur(tel), ref)["fail"]


def laps(rows):
    cols = ("drv", "team", "lap", "time", "del", "compound", "wR", "pb", "qs", "iacc")
    return {c: [r[i] for r in rows] for i, c in enumerate(cols)}


def test_candidates_rules():
    teams, rejected = qc.candidates(laps([
        ("AAA", "T", 2, 90.0, False, "SOFT", False, True, "Q1", True),
        ("AAA", "T", 4, 90.5, False, "SOFT", False, False, "Q2", True),    # slower, usable
        ("AAA", "T", 5, 89.0, False, "SOFT", False, False, "Q2", True),    # quicker than pb: not counted
        ("AAA", "T", 6, 88.0, True, "SOFT", False, False, "Q2", True),     # deleted
        ("BBB", "T", 2, 89.9, False, "MEDIUM", False, True, "Q1", True),
        ("BBB", "T", 3, 91.0, False, "INTERMEDIATE", False, False, "Q1", True),
        ("BBB", "T", 4, 91.0, False, "SOFT", True, False, "Q1", True),     # raining
        ("CCC", "T", 1, "None", False, "SOFT", False, False, "Q1", False),
    ]))
    assert [(c["driver"], c["lap"]) for c in teams["T"]] == [("BBB", 2), ("AAA", 2), ("AAA", 4)]
    assert sum(rejected.values()) == 4


def test_circuit_table_is_unambiguous():
    assert len({c.id for c in C.CIRCUITS}) == len({c.key for c in C.CIRCUITS}) == 19
    catalunya = next(c for c in C.CIRCUITS if c.id == "catalunya")
    assert catalunya.event(2025) == "Spanish Grand Prix"
    assert catalunya.event(2026) == "Barcelona Grand Prix"
