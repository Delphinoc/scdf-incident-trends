"""Data-quality checks on the raw snapshots: completeness, internal reconciliation and cross-source agreement.

Never edit a raw value or an anchor to make a test pass: a failure means the snapshot needs re-checking
against data.gov.sg (python scripts/fetch_data.py --check) or the SCDF release.
"""
import pandas as pd
import pytest

EXPECTED_YEARS = {
    "ems": (2000, 2025),
    "fire": (2000, 2025),
    "cas": (2001, 2025),
    "pop": (2017, 2024),
}


@pytest.mark.parametrize("name", list(EXPECTED_YEARS))
def test_years_complete_and_unique(raw, name):
    df = raw[name]
    lo, hi = EXPECTED_YEARS[name]
    assert df.year.is_unique
    assert sorted(df.year) == list(range(lo, hi + 1)), "missing or extra years"


@pytest.mark.parametrize("name", list(EXPECTED_YEARS))
def test_no_nulls_or_negatives(raw, name):
    df = raw[name]
    assert not df.isna().any().any()
    assert (df.drop(columns="year") >= 0).all().all()


@pytest.mark.parametrize("name", ["ems", "fire", "cas", "pop"])
def test_counts_are_integers(raw, name):
    df = raw[name].drop(columns=[c for c in raw[name].columns if "rate" in c])
    assert all(pd.api.types.is_integer_dtype(t) for t in df.dtypes)


def test_ems_call_types_sum_to_total(raw):
    e = raw["ems"]
    diff = e.total_calls - (e.emergency_calls + e.non_emergency_calls + e.false_alarm_calls)
    assert (diff == 0).all(), e.loc[diff != 0, "year"].tolist()


def test_building_fires_split_into_residential_and_non_residential(raw):
    f = raw["fire"]
    diff = f.building_fires - (f.residential_fires + f.non_residential_fires)
    assert (diff == 0).all(), f.loc[diff != 0, "year"].tolist()


def test_total_fires_split_into_building_and_non_building(raw):
    f = raw["fire"]
    diff = f.total_fires - (f.building_fires + f.non_building_fires)
    assert (diff == 0).all(), f.loc[diff != 0, "year"].tolist()


def test_fatality_rate_reconciles_with_population(raw):
    """SingStat's fatality rate is per 100,000 population: recompute it from two independent datasets."""
    m = raw["cas"].merge(raw["pop"], on="year")
    assert len(m) == 8
    recomputed = (m.fire_fatalities / m.total_population * 1e5).round(2)
    assert (recomputed - m.fatality_rate_per_100k_pop).abs().max() < 0.005


def test_fatalities_never_exceed_injuries_plus_fatalities_floor(raw):
    c = raw["cas"]
    assert (c.fire_fatalities <= c.fire_injuries + c.fire_fatalities).all()
    assert (c.fire_fatalities < 50).all(), "implausible fatality count"


def test_population_is_plausible(raw):
    p = raw["pop"]
    assert p.total_population.between(5_000_000, 7_000_000).all()
    assert (p.resident_population < p.total_population).all()


ANCHOR_MAP = {
    "ems_total_calls": ("ems", "total_calls"),
    "ems_emergency_calls": ("ems", "emergency_calls"),
    "ems_non_emergency_calls": ("ems", "non_emergency_calls"),
    "ems_false_alarm_calls": ("ems", "false_alarm_calls"),
    "fire_total": ("fire", "total_fires"),
    "fire_residential": ("fire", "residential_fires"),
    "fire_non_residential": ("fire", "non_residential_fires"),
    "fire_non_building": ("fire", "non_building_fires"),
    "fire_injuries": ("cas", "fire_injuries"),
    "fire_fatalities": ("cas", "fire_fatalities"),
}


def test_snapshot_matches_scdf_annual_release(raw, anchors):
    """Cross-source check: data.gov.sg (SingStat) values vs SCDF's own 2025 statistics release."""
    checked = 0
    for a in anchors.itertuples():
        if a.metric not in ANCHOR_MAP:
            continue
        ds, col = ANCHOR_MAP[a.metric]
        val = raw[ds].set_index("year").loc[a.year, col]
        assert val == a.value, f"{a.metric} {a.year}: snapshot {val} vs release {a.value}"
        checked += 1
    assert checked == 14


def test_calls_per_day_matches_release(con, anchors):
    a = anchors.query("metric == 'ems_calls_per_day' and year == 2025").value.item()
    # use the unrounded value: the view stores 1 d.p. (704.5), which would hit banker's rounding
    v = con.execute("SELECT total_calls * 1.0 / 365 FROM ems_annual WHERE year = 2025").fetchone()[0]
    assert abs(v - a) < 0.5
