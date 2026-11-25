"""Download and cache raw files, check lap quality, choose laps, write reports.

    uv run python -I run.py fetch

Cached files are never downloaded again. Writes:
  data/processed/selection.json          chosen lap per circuit/season/team
  analysis/reports/inventory.csv         every Grand Prix in both repos
  analysis/reports/qc_attempts.csv       every lap checked
  analysis/reports/lap_selection.csv     outcome per circuit/season/team
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from . import config as C
from . import qc

AGENT = {"User-Agent": "python-urllib"}
_lock = threading.Lock()
stats = {"downloaded": 0, "bytes": 0, "cached": 0}


class Missing(Exception):
    """The file does not exist upstream."""


# --- Cache -------------------------------------------------------------------
def _get(url: str) -> bytes:
    for attempt in range(C.HTTP_RETRIES):
        try:
            req = urllib.request.Request(url, headers=AGENT)
            with urllib.request.urlopen(req, timeout=C.HTTP_TIMEOUT) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise Missing(url) from e
            if e.code not in (429, 500, 502, 503, 504) or attempt == C.HTTP_RETRIES - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == C.HTTP_RETRIES - 1:
                raise
        time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def _cached(season: int, rel: str, url: str):
    """Return parsed JSON from cache, downloading once if absent."""
    dest = C.RAW / str(season) / rel
    if not dest.resolve().is_relative_to(C.RAW.resolve()):
        raise ValueError(f"unsafe path {rel!r}")
    if dest.exists():
        with _lock:
            stats["cached"] += 1
        return json.loads(dest.read_bytes())
    body = _get(url)
    data = json.loads(body)             # never cache something that is not JSON
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    tmp.write_bytes(body)
    os.replace(tmp, dest)
    with _lock:
        stats["downloaded"] += 1
        stats["bytes"] += len(body)
        with open(C.RAW / "manifest.jsonl", "a") as f:
            f.write(json.dumps({
                "file": f"{season}/{rel}", "url": url, "commit": C.SHA[season],
                "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
            }, ensure_ascii=False) + "\n")
    return data


def raw(season: int, rel: str):
    repo = C.REPO.format(season=season)
    url = f"https://raw.githubusercontent.com/{repo}/{C.SHA[season]}/{urllib.parse.quote(rel)}"
    return _cached(season, rel, url)


def root_listing(season: int) -> list[str]:
    repo, sha = C.REPO.format(season=season), C.SHA[season]
    tree = _cached(season, f"_tree_{sha[:12]}.json",
                   f"https://api.github.com/repos/{repo}/git/trees/{sha}")
    if tree.get("truncated"):
        raise RuntimeError("truncated tree listing")
    return [t["path"] for t in tree["tree"] if t["type"] == "tree"]


def session_file(season: int, circuit: C.Circuit, name: str):
    return raw(season, f"{circuit.event(season)}/{C.SESSION}/{name}")


def telemetry(season: int, circuit: C.Circuit, driver: str, lap: int) -> dict:
    if not re.fullmatch(r"[A-Z0-9]{3}", driver):
        raise ValueError(f"unexpected driver code {driver!r}")
    return session_file(season, circuit, f"{driver}/{int(lap)}_tel.json")["tel"]


# --- Inventory ---------------------------------------------------------------
def circuit_of(info: dict) -> tuple[int, str]:
    c = info["session_info"]["Meeting"]["Circuit"]
    return int(c["Key"]), c["ShortName"]


def inventory() -> list[dict]:
    """Every Grand Prix in both repos, with its real circuit and our decision."""
    used = {(s, c.event(s)): c for s in C.SEASONS for c in C.CIRCUITS}

    def row(season, event):
        try:
            info = raw(season, f"{event}/{C.SESSION}/session_info.json")
            key, where = circuit_of(info)
            date = str(info["session_info"]["StartDate"])[:10]
        except Missing:
            key, where, date = None, None, None
        c = used.get((season, event))
        short = event.removesuffix(" Grand Prix")
        reason = C.EXCLUDED.get((season, short), "")
        if c is not None and key != c.key:
            raise SystemExit(f"{season} {event}: circuit key {key}, expected {c.key} ({c.id})")
        if c is None and not reason:
            raise SystemExit(f"{season} {event} ({where}) is neither mapped nor excluded")
        return {"season": season, "event": event, "qualifying": key is not None, "date": date,
                "circuit_key": key, "circuit": where, "mapped_to": c.id if c else "",
                "excluded_because": reason}

    jobs = [(s, e) for s in C.SEASONS for e in root_listing(s) if e.endswith("Grand Prix")]
    missing = set(used) - set(jobs)
    if missing:
        raise SystemExit(f"mapped events not in the repos: {sorted(missing)}")
    with ThreadPoolExecutor(C.HTTP_WORKERS) as ex:
        rows = list(ex.map(lambda j: row(*j), jobs))
    return sorted(rows, key=lambda r: (r["season"], r["date"] or ""))


# --- Lap selection -----------------------------------------------------------
def attempt(season, circuit, cand, ref) -> dict:
    rec = {"season": season, "circuit": circuit.id, **cand}
    try:
        tel = telemetry(season, circuit, cand["driver"], cand["lap"])
        rec.update(qc.check_lap(tel, cand["time"], ref))
        rec["fail"] = [f for f in rec["fail"] if f not in C.QC_SKIP.get(circuit.id, ())]
    except Missing:
        rec.update(fail=["no telemetry file"], coverage=0.0, bad_intervals=[])
    return rec


def choose(season, circuit, cands, ref) -> tuple[dict, list[dict]]:
    """Fastest passing lap within REPLACE_WITHIN of the team's best; else the most
    complete maskable lap; else nothing."""
    tried = []
    for cand in cands:
        if cand["time"] > cands[0]["time"] * (1 + C.REPLACE_WITHIN):
            break
        rec = attempt(season, circuit, cand, ref)
        tried.append(rec)
        if not rec["fail"]:
            status = "best" if cand is cands[0] else "replaced"
            return {**rec, "status": status}, tried
    # dist_vs_xy is a symptom of freezing: positions, not distance, align the laps.
    maskable = {"frozen", "gap", "dist_vs_xy"}
    masks = [r for r in tried if set(r["fail"]) <= maskable and r["coverage"] >= C.MIN_COVERAGE
             and ({"frozen", "gap"} & set(r["fail"]))]
    if masks:
        return {**max(masks, key=lambda r: r["coverage"]), "status": "masked"}, tried
    return {**tried[0], "status": "missing"}, tried


def reference(circuit, cands_by_season) -> tuple[np.ndarray, dict]:
    """Reference line: fastest lap passing the stand-alone checks, 2025 first."""
    for season in C.SEASONS:
        pool = sorted((c for rows in cands_by_season[season].values() for c in rows),
                      key=lambda c: c["time"])
        for cand in pool[:25]:
            rec = attempt(season, circuit, cand, None)
            if not rec["fail"]:
                tel = telemetry(season, circuit, cand["driver"], cand["lap"])
                return qc.path(tel), {"season": season, "driver": cand["driver"], "lap": cand["lap"]}
    raise SystemExit(f"{circuit.id}: no usable reference lap")


def select_circuit(circuit) -> tuple[list[dict], list[dict], dict, dict]:
    cands, rejected = {}, {}
    for season in C.SEASONS:
        for f in C.SESSION_FILES:
            session_file(season, circuit, f)
        cands[season], rejected[season] = qc.candidates(
            session_file(season, circuit, "session_laptimes.json"))
        wet = not cands[season]
        if wet != ((season, circuit.id) in C.EXPECTED_WET):
            raise SystemExit(f"{season} {circuit.id}: unexpected dry-lap situation {rejected[season]}")
    ref, ref_info = reference(circuit, cands)
    chosen, tried = [], []
    for season in C.SEASONS:
        for rows in cands[season].values():
            c, t = choose(season, circuit, rows, ref)
            c["team_best"] = rows[0]["time"]
            c["team_best_driver"], c["team_best_lap"] = rows[0]["driver"], rows[0]["lap"]
            chosen.append(c)
            tried += t
    for season, cid, drv, lap in C.EXTRA_LAPS:
        if cid != circuit.id:
            continue
        cand = next(c for rows in cands[season].values() for c in rows
                    if c["driver"] == drv and c["lap"] == lap)
        rec = attempt(season, circuit, cand, ref)
        chosen.append({**rec, "status": "extra", "team_best": cand["time"],
                       "team_best_driver": drv, "team_best_lap": lap})
    return chosen, tried, ref_info, rejected


# --- Reports -----------------------------------------------------------------
def write_csv(path, rows, cols):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            r = {k: round(v, 4) if isinstance(v, float) else v for k, v in r.items()}
            w.writerow({**r, "fail": " ".join(r.get("fail", []))} if "fail" in cols else r)


QC_COLS = ["circuit", "season", "team", "driver", "lap", "time", "segment", "compound", "fail",
           "coverage", "frozen_s", "max_gap", "dist", "xy_len", "dist_vs_xy", "xy_vs_ref",
           "line_p95", "duration"]


def main():
    inv = inventory()
    write_csv(C.REPORTS / "inventory.csv", inv, list(inv[0]))
    with ThreadPoolExecutor(C.HTTP_WORKERS) as ex:
        results = list(ex.map(select_circuit, C.CIRCUITS))
    chosen = [r for res in results for r in res[0]]
    tried = [r for res in results for r in res[1]]
    write_csv(C.REPORTS / "qc_attempts.csv", tried, QC_COLS)
    write_csv(C.REPORTS / "lap_selection.csv", chosen,
              QC_COLS[:8] + ["status", "team_best", "team_best_driver", "team_best_lap"] + QC_COLS[8:])
    C.PROCESSED.mkdir(parents=True, exist_ok=True)
    (C.PROCESSED / "selection.json").write_text(json.dumps({
        "reference": {c.id: r[2] for c, r in zip(C.CIRCUITS, results)},
        "rejected": {c.id: r[3] for c, r in zip(C.CIRCUITS, results)},
        "laps": chosen}, indent=1, ensure_ascii=False))

    print(f"{'circuit':13s} {'season':6s}  best repl mask miss  ref")
    for c, res in zip(C.CIRCUITS, results):
        for s in C.SEASONS:
            n = {k: sum(r["status"] == k and r["season"] == s for r in res[0])
                 for k in ("best", "replaced", "masked", "missing")}
            note = "  WET" if (s, c.id) in C.EXPECTED_WET else ""
            low = "  <-- too few teams" if not note and sum(n.values()) - n["missing"] < C.MIN_TEAMS else ""
            print(f"{c.id:13s} {s}   {n['best']:4d} {n['replaced']:4d} {n['masked']:4d} {n['missing']:4d}"
                  f"  {res[2]['season']} {res[2]['driver']} {res[2]['lap']}{note}{low}")
    print(f"downloaded {stats['downloaded']} files ({stats['bytes'] / 1e6:.1f} MB), "
          f"{stats['cached']} cache hits")


if __name__ == "__main__":
    main()
