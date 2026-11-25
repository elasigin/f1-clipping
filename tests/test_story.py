"""Every number in the article marked data-fact must match site/data.

Skipped when site/data has not been exported.
"""
import json
import re
from pathlib import Path
from statistics import median

import pytest

SITE = Path(__file__).parent.parent / "site"
if not (SITE / "data" / "index.json").exists():
    pytest.skip("site/data not exported", allow_module_level=True)


def load(name):
    return json.loads((SITE / "data" / name).read_text(encoding="utf-8"))


INDEX, SEASON, SPA = load("index.json"), load("season.json"), load("circuits/spa.json")
STEP = SPA["step"]
A, B = SPA["laps"]["2025-mercedes-ant"], SPA["laps"]["2026-mercedes"]
ORDER = [c["id"] for c in INDEX["circuits"]]
HTML = (SITE / "index.html").read_text(encoding="utf-8")


def at(lap, s):
    return lap["speed"][round(s / STEP)]


def window(lap, s0, s1, key="speed"):
    return [v for v in lap[key][round(s0 / STEP):round(s1 / STEP) + 1] if v is not None]


def rows(season):
    return [r for r in SEASON["rows"] if r["season"] == season]


def medians(season):
    by = {}
    for r in rows(season):
        by.setdefault(r["circuit"], []).append(r["share"])
    return {c: median(v) for c, v in by.items()}


def longest_run(circuit):
    segments = load(f"circuits/{circuit}.json")["segments"]
    return max(g["s1"] - g["s0"] for g in segments)


def full_throttle_seconds(lap):
    return sum(STEP / (v / 3.6) for v, th in zip(lap["speed"], lap["throttle"])
               if v and th is not None and th >= 98)


def pct(v):
    return f"{v * 100:.1f}%"


def facts():
    m26 = medians(2026)
    n = lambda yr: f"{sum(r['clipM'] > 0 for r in rows(yr))} of {len(rows(yr))}"
    teams = [t["mean"] for t in SEASON["teams"]]
    post = ORDER[ORDER.index("miami"):]
    long_runs = [c for c in m26 if longest_run(c) > 1200]
    assert all(m26[c] > 0 for c in long_runs)
    assert max(m26, key=m26.get) == "miami"
    assert m26["mexico"] == 0
    kemmel = [z for z in B["zones"] if 1600 <= z["s0"] < 2300]
    blanch = [z for z in B["zones"] if 5600 <= z["s0"] < 6400]
    assert len(kemmel) == 2 and len(blanch) == 1 and not A["zones"]
    m = B["metrics"]
    starts = [z["v0"] for c in ORDER for lap in load(f"circuits/{c}.json")["laps"].values()
              if lap["season"] == 2026 for z in lap["zones"]]
    return {
        "spa.kemmel.max25": f"{max(window(A, 1250, 2260)):.0f}",
        "spa.kemmel.max26": f"{max(window(B, 1250, 2260)):.0f}",
        "spa.kemmel.drop2": f"{kemmel[1]['drop']:.0f}",
        "spa.full26.sec": f"{full_throttle_seconds(B):.0f}",
        "spa.v26.800": f"{at(B, 800):.0f}", "spa.v25.800": f"{at(A, 800):.0f}",
        "spa.v26.1600": f"{at(B, 1600):.0f}", "spa.v25.1600": f"{at(A, 1600):.0f}",
        "spa.gap.2000": f"{at(A, 2000) - at(B, 2000):.0f}",
        "spa.blanch.max26": f"{max(window(B, 5600, 5800)):.0f}",
        "spa.v26.6250": f"{at(B, 6250):.0f}", "spa.v25.6250": f"{at(A, 6250):.0f}",
        "spa.blanch.counted": f"{blanch[0]['s1'] - blanch[0]['s0']:.0f}",
        "spa.clip26.m": f"{m['clipM']:,.0f}", "spa.full26.m": f"{m['fullM']:,.0f}",
        "spa.clip26.share": pct(m["share"]), "spa.clip26.lo": pct(m["lo"]), "spa.clip26.hi": pct(m["hi"]),
        "season.n26": n(2026), "season.n25": n(2025), "season.top": pct(max(m26.values())),
        "season.zero": f"{sum(v == 0 for v in m26.values())} of {len(m26)}",
        "season.teamlo": pct(min(teams)), "season.teamhi": pct(max(teams)),
        "season.postsec": f"{median(r['sec'] for r in rows(2026) if r['circuit'] in post):.1f}",
        "zones.below": f"{sum(v < 337.5 for v in starts)} of {len(starts)}",
        "runs.long": f"{len(long_runs)} circuits", "runs.mexico": f"{longest_run('mexico'):,}",
    }


def test_article_numbers_match_the_data():
    used = dict(re.findall(r'data-fact="([^"]+)">([^<]+)<', HTML))
    assert len(used) > 20
    assert set(used) == set(facts())
    wrong = {k: (v, facts()[k]) for k, v in used.items() if v != facts()[k]}
    assert not wrong, f"article vs data: {wrong}"


def test_kemmel_is_flat_out_in_both_seasons():
    for lap in (A, B):
        assert min(window(lap, 1250, 2260, "throttle")) >= 98


def test_eau_rouge_both_cars_slow_at_full_throttle():
    for lap in (A, B):
        assert min(window(lap, 1050, 1250, "throttle")) >= 98
        assert at(lap, 1050 if at(lap, 1050) else 1040) > at(lap, 1200)


def test_lap_times_in_the_text():
    assert (A["time"], B["time"]) == (102.139, 104.361)
    assert "1:42.139 in 2025" in HTML and "1:44.361 in 2026" in HTML


def test_battery_arithmetic():
    assert round(4000 / 350) == 11               # 4 MJ at 350 kW, in seconds (C5.2.7, C5.2.9)
    assert 7100 - 20 * 337.5 == 350              # where overtake's power limit starts to bite (C5.2.8 ii)
