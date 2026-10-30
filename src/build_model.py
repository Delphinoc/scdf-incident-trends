"""Load the raw CSV snapshots into SQLite and build the analytical views in sql/model.sql.

Usage: python src/build_model.py [--db data/processed/scdf.sqlite]
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
SQL = ROOT / "sql" / "model.sql"
DEFAULT_DB = ROOT / "data" / "processed" / "scdf.sqlite"

RAW_TABLES = {
    "raw_ems": "ems_calls_annual.csv",
    "raw_fire": "fire_occurrences_annual.csv",
    "raw_fire_casualties": "fire_injuries_fatalities_annual.csv",
    "raw_population": "population_annual.csv",
}


def build(db_path: Path = DEFAULT_DB) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()  # rebuild from scratch so the model is always reproducible from raw
    con = sqlite3.connect(db_path)
    for table, fname in RAW_TABLES.items():
        df = pd.read_csv(RAW / fname)
        df.to_sql(table, con, index=False)
    con.executescript(SQL.read_text())
    con.commit()
    return con


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = ap.parse_args()
    con = build(args.db)
    views = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='view' ORDER BY name")]
    print(f"Built {args.db} with views: {', '.join(views)}")
