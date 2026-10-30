import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from build_model import RAW, build  # noqa: E402


@pytest.fixture(scope="session")
def con(tmp_path_factory):
    db = tmp_path_factory.mktemp("db") / "scdf.sqlite"
    c = build(db)
    yield c
    c.close()


@pytest.fixture(scope="session")
def raw():
    return {
        "ems": pd.read_csv(RAW / "ems_calls_annual.csv"),
        "fire": pd.read_csv(RAW / "fire_occurrences_annual.csv"),
        "cas": pd.read_csv(RAW / "fire_injuries_fatalities_annual.csv"),
        "pop": pd.read_csv(RAW / "population_annual.csv"),
    }


@pytest.fixture(scope="session")
def anchors():
    return pd.read_csv(ROOT / "data" / "reference" / "scdf_2025_release_anchors.csv")
