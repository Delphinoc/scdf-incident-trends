"""Checks on the SQL views and the analysis: comparability rules, independent pandas recomputation,
projection maths and reproducibility."""
import json

import numpy as np
import pandas as pd
import pytest

from analyse import linear_projection, run
from build_model import build


def q(con, sql):
    return pd.read_sql(sql, con)


# ---------------------------------------------------------------- comparability rules
def test_ems_comparable_flag_starts_2016(con):
    df = q(con, "SELECT year, comparable_series FROM ems_annual")
    assert (df.comparable_series == (df.year >= 2016).astype(int)).all()


def test_fire_comparable_flag_starts_2019(con):
    df = q(con, "SELECT year, comparable_series FROM fire_annual")
    assert (df.comparable_series == (df.year >= 2019).astype(int)).all()


def test_workload_mix_only_uses_comparable_years(con):
    df = q(con, "SELECT year FROM workload_mix")
    assert df.year.min() == 2019 and df.year.max() == 2025 and len(df) == 7


def test_per_capita_covers_population_years_only(con):
    df = q(con, "SELECT year FROM ems_per_capita")
    assert list(df.year) == list(range(2017, 2025))


# ---------------------------------------------------------------- view arithmetic
def test_ems_shares_sum_to_100(con):
    df = q(con, "SELECT emergency_pct + non_emergency_pct + false_alarm_pct AS s FROM ems_annual")
    assert (df.s - 100).abs().max() <= 0.02


def test_fire_shares_sum_to_100(con):
    df = q(con, "SELECT residential_pct + non_residential_pct + non_building_pct AS s FROM fire_annual")
    assert (df.s - 100).abs().max() <= 0.02


def test_first_year_has_no_yoy(con):
    assert con.execute("SELECT yoy_growth_pct FROM ems_annual WHERE year = 2000").fetchone()[0] is None


def test_calls_per_day_uses_leap_years(con):
    v2024 = con.execute("SELECT calls_per_day FROM ems_annual WHERE year = 2024").fetchone()[0]
    assert v2024 == round(245279 / 366, 1)


@pytest.mark.parametrize("view,keys", [("ems_annual", 26), ("fire_annual", 26), ("fire_severity", 25)])
def test_views_do_not_multiply_rows(con, view, keys):
    df = q(con, f"SELECT year FROM {view}")
    assert len(df) == keys and df.year.is_unique


# ---------------------------------------------------------------- independent pandas recomputation
def test_pandas_parity_ems(con, raw):
    e = raw["ems"].copy()
    e["nef"] = (100 * (e.non_emergency_calls + e.false_alarm_calls) / e.total_calls).round(2)
    e["yoy"] = (100 * e.total_calls.pct_change()).round(2)
    v = q(con, "SELECT year, non_emergency_or_false_pct, yoy_growth_pct FROM ems_annual ORDER BY year")
    assert np.allclose(v.non_emergency_or_false_pct, e.nef, atol=0.01)
    assert np.allclose(v.yoy_growth_pct.iloc[1:], e.yoy.iloc[1:], atol=0.01)


def test_pandas_parity_severity(con, raw):
    m = raw["fire"].merge(raw["cas"], on="year")
    exp = (100 * m.fire_injuries / m.total_fires).round(2)
    v = q(con, "SELECT injuries_per_100_fires FROM fire_severity ORDER BY year")
    assert np.allclose(v.injuries_per_100_fires, exp, atol=0.01)


def test_pandas_parity_per_capita(con, raw):
    m = raw["ems"].merge(raw["pop"], on="year")
    exp = (1000 * m.total_calls / m.total_population).round(2)
    v = q(con, "SELECT ems_calls_per_1000_pop FROM ems_per_capita ORDER BY year")
    assert np.allclose(v.ems_calls_per_1000_pop, exp, atol=0.01)


# ---------------------------------------------------------------- projection maths
def test_projection_recovers_exact_line():
    x = np.arange(2010, 2020, dtype=float)
    y = 1000 + 50 * (x - 2010)
    p = linear_projection(x, y + np.array([1, -1] * 5), [2020])
    assert abs(p["slope_per_year"] - 50) < 1
    pt = p["projections"]["2020"]
    assert abs(pt["point"] - 1500) <= 2 and pt["lower"] < pt["point"] < pt["upper"]


def test_projection_interval_widens_with_horizon():
    x = np.arange(2016, 2026, dtype=float)
    y = 100 + 10 * (x - 2016) + np.random.default_rng(0).normal(0, 5, len(x))
    p = linear_projection(x, y, [2026, 2030])["projections"]
    w = {k: v["upper"] - v["lower"] for k, v in p.items()}
    assert w["2030"] > w["2026"]


# ---------------------------------------------------------------- outputs and reproducibility
@pytest.fixture(scope="module")
def stats_out(con):
    return run(con)


def test_headline_stats_match_raw(stats_out, raw):
    e = raw["ems"].set_index("year")
    assert stats_out["ems"]["growth_2016_2025_pct"] == round(100 * (e.loc[2025, "total_calls"] / e.loc[2016, "total_calls"] - 1), 1)
    f = raw["fire"]
    f = f[f.year >= 2019]
    assert stats_out["fire"]["min_year"] == int(f.loc[f.total_fires.idxmin(), "year"])
    assert stats_out["workload"]["ems_share_pct_2025"] > 99


def test_stats_json_written_and_consistent(stats_out):
    from analyse import ROOT
    on_disk = json.loads((ROOT / "reports" / "stats.json").read_text())
    assert on_disk == json.loads(json.dumps(stats_out))


def test_rebuild_is_deterministic(tmp_path, con):
    c2 = build(tmp_path / "again.sqlite")
    for view in ("ems_annual", "fire_annual", "fire_severity", "workload_mix", "ems_per_capita"):
        pd.testing.assert_frame_equal(q(con, f"SELECT * FROM {view} ORDER BY year"),
                                      q(c2, f"SELECT * FROM {view} ORDER BY year"))
    c2.close()


def test_raw_files_unchanged_by_pipeline(raw):
    from build_model import RAW
    for name, fname in [("ems", "ems_calls_annual.csv"), ("fire", "fire_occurrences_annual.csv")]:
        pd.testing.assert_frame_equal(raw[name], pd.read_csv(RAW / fname))
