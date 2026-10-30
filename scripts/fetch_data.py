"""Download the SCDF series from data.gov.sg into data/raw, or check the committed snapshot against them.

Usage:
  python scripts/fetch_data.py           # (re)write data/raw/*.csv from the live API
  python scripts/fetch_data.py --check   # compare data/raw with the live API; exit 1 on any difference

Standard library only. data.gov.sg rate-limits anonymous calls, so requests are spaced and retried.
Population (SingStat Table Builder M810001) is not on the same API and stays a committed snapshot.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
API = "https://data.gov.sg/api/action/datastore_search?resource_id={id}&limit=100"

# dataset id -> (file, first year kept, {column: data.gov.sg DataSeries name}, integer columns?)
DATASETS = {
    "d_d0b4ca9fad1c5fee38d7ddfd7303845f": ("ems_calls_annual.csv", 2000, {
        "total_calls": "Total Calls To Emergency Medical Services",
        "emergency_calls": "Emergency Medical Services - Emergency Calls",
        "non_emergency_calls": "Emergency Medical Services - Non-Emergency Calls",
        "false_alarm_calls": "Emergency Medical Services - False Alarm Calls",
    }),
    "d_808473a208220960f07a0b064ef16bde": ("fire_occurrences_annual.csv", 2000, {
        "total_fires": "Total Number Of Fire Occurrences",
        "building_fires": "Fire Occurrences In Buildings",
        "residential_fires": "Fire Occurrences In Residential Buildings",
        "non_residential_fires": "Fire Occurrences In Non-Residential Buildings",
        "non_building_fires": "Fire Occurrences In Non-Building Structures",
    }),
    "d_2c81b575edc555f6c8f0cb7e09c8df02": ("fire_injuries_fatalities_annual.csv", 2001, {
        "fire_injuries": "Fire Injuries",
        "fire_fatalities": "Fire Fatalities",
        "fatality_rate_per_100k_pop": "Fatality Rate From Fire Incidents",
    }),
}
MISSING = {None, "", "na", "-", "n.a."}


def norm(s: str) -> str:
    return " ".join(str(s).lower().replace("-", " ").split())


def fetch(dataset_id: str, attempts: int = 4) -> list[dict]:
    req = urllib.request.Request(API.format(id=dataset_id), headers={"User-Agent": "scdf-incident-trends/1.0"})
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                payload = json.load(r)
            if payload.get("success"):
                return payload["result"]["records"]
            raise RuntimeError(f"{dataset_id}: API returned {payload}")
        except urllib.error.HTTPError as e:
            if e.code != 429 or i == attempts - 1:
                raise
            time.sleep(10 * (i + 1))  # rate limited: back off
    raise RuntimeError("unreachable")


def to_rows(records: list[dict], first_year: int, cols: dict[str, str]) -> list[dict]:
    live = {norm(r.get("DataSeries", "")): r for r in records}
    missing = [s for s in cols.values() if norm(s) not in live]
    if missing:
        raise KeyError(f"series not found on data.gov.sg: {missing}")
    series = {c: live[norm(s)] for c, s in cols.items()}
    years = sorted(int(k) for k in next(iter(series.values())) if str(k).isdigit() and int(k) >= first_year)
    rows = []
    for y in years:
        vals = {c: rec.get(str(y)) for c, rec in series.items()}
        if any(v in MISSING for v in vals.values()):
            continue
        row = {"year": y}
        for c, v in vals.items():
            num = float(v)
            row[c] = int(num) if num.is_integer() else f"{num:g}"
        rows.append(row)
    return rows


def write(rows: list[dict], path: Path):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def check(rows: list[dict], path: Path) -> int:
    with open(path, newline="") as fh:
        snap = {int(r["year"]): r for r in csv.DictReader(fh)}
    live = {r["year"]: r for r in rows}
    problems = 0
    for y in sorted(set(snap) | set(live)):
        if y not in live:
            print(f"[{path.name}] {y}: in snapshot but not in live data"); problems += 1; continue
        if y not in snap:
            print(f"[{path.name}] {y}: new year available on data.gov.sg"); problems += 1; continue
        for c, v in live[y].items():
            if c != "year" and float(snap[y][c]) != float(v):
                print(f"[{path.name}] {c} {y}: snapshot {snap[y][c]} vs live {v}"); problems += 1
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="compare data/raw with data.gov.sg instead of writing")
    args = ap.parse_args()
    problems = 0
    for i, (ds_id, (fname, first_year, cols)) in enumerate(DATASETS.items()):
        if i:
            time.sleep(3)
        rows = to_rows(fetch(ds_id), first_year, cols)
        if args.check:
            n = check(rows, RAW / fname)
            problems += n
            print(f"{fname}: {len(rows)} years checked, {n} difference(s)")
        else:
            write(rows, RAW / fname)
            print(f"wrote {fname}: {len(rows)} years ({rows[0]['year']}-{rows[-1]['year']})")
    if args.check:
        print("OK: snapshot matches data.gov.sg" if problems == 0 else f"FAIL: {problems} difference(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
