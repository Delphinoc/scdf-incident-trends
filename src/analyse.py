"""Run the analysis on the SQLite model: summary tables, a demand projection and charts.

Outputs:
  reports/tables/*.csv     one table per view (comparable years only)
  reports/stats.json       every headline number quoted in the README
  reports/figures/*.png    charts

Usage: python src/analyse.py
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from build_model import DEFAULT_DB, build

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "reports" / "tables"
FIGS = ROOT / "reports" / "figures"

# Validated categorical palette (light surface); see README "Charts"
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"


# ---------------------------------------------------------------- projection
def linear_projection(years: np.ndarray, values: np.ndarray, targets: list[int], level: float = 0.95) -> dict:
    """OLS linear trend with prediction intervals (t-distribution, n-2 df)."""
    n = len(years)
    res = stats.linregress(years, values)
    fitted = res.intercept + res.slope * years
    resid = values - fitted
    s = np.sqrt(np.sum(resid**2) / (n - 2))
    xbar, sxx = years.mean(), np.sum((years - years.mean()) ** 2)
    tcrit = stats.t.ppf(0.5 + level / 2, n - 2)
    out = {
        "fit_years": [int(years.min()), int(years.max())],
        "n": int(n),
        "slope_per_year": round(float(res.slope), 1),
        "r_squared": round(float(res.rvalue**2), 3),
        "residual_se": round(float(s), 1),
        "projections": {},
    }
    for x0 in targets:
        yhat = res.intercept + res.slope * x0
        se = s * np.sqrt(1 + 1 / n + (x0 - xbar) ** 2 / sxx)
        out["projections"][str(x0)] = {
            "point": int(round(yhat)),
            "lower": int(round(yhat - tcrit * se)),
            "upper": int(round(yhat + tcrit * se)),
        }
    return out


# ---------------------------------------------------------------- charts
def _style(ax, title: str, ylabel: str):
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=12, color=INK, pad=12, fontweight="bold")
    ax.set_ylabel(ylabel, color=INK2, fontsize=9)
    ax.tick_params(colors=INK2, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)


def chart_ems_trend(ems: pd.DataFrame, proj: dict, path: Path):
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    ax.plot(ems.year, ems.total_calls / 1000, color=S1, lw=2, marker="o", ms=5, label="Actual")
    pyears = [int(y) for y in proj["projections"]]
    last = ems.iloc[-1]
    px = [int(last.year)] + pyears
    py = [last.total_calls / 1000] + [proj["projections"][str(y)]["point"] / 1000 for y in pyears]
    lo = [last.total_calls / 1000] + [proj["projections"][str(y)]["lower"] / 1000 for y in pyears]
    hi = [last.total_calls / 1000] + [proj["projections"][str(y)]["upper"] / 1000 for y in pyears]
    ax.fill_between(px, lo, hi, color=S1, alpha=0.12, lw=0, label="95% prediction interval")
    ax.plot(px, py, color=S1, lw=2, ls="--", label="Linear-trend projection")
    for y in (2020, 2022, 2025):
        v = ems.loc[ems.year == y, "total_calls"].item()
        ax.annotate(f"{v/1000:,.1f}k", (y, v / 1000), textcoords="offset points", xytext=(0, 9),
                    ha="center", fontsize=8, color=INK2)
    _style(ax, "Total SCDF EMS calls, 2016–2025, with 2026–27 projection", "Calls (thousands)")
    ax.set_xticks(list(ems.year) + pyears)
    ax.legend(frameon=False, fontsize=8, loc="upper left", labelcolor=INK2)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def chart_ems_mix(ems: pd.DataFrame, path: Path):
    fig, ax = plt.subplots(figsize=(8, 4), dpi=150)
    for col, color, label in [("non_emergency_pct", S1, "Non-emergency"), ("false_alarm_pct", S2, "False alarm")]:
        ax.plot(ems.year, ems[col], color=color, lw=2, marker="o", ms=5, label=label)
        ax.annotate(f"{label} {ems[col].iloc[-1]:.1f}%", (ems.year.iloc[-1], ems[col].iloc[-1]),
                    textcoords="offset points", xytext=(6, 0), va="center", fontsize=8, color=INK2)
    _style(ax, "Share of EMS calls that were non-emergency or false alarms", "% of all EMS calls")
    ax.set_ylim(0, max(ems.non_emergency_pct.max(), ems.false_alarm_pct.max()) * 1.25)
    ax.set_xlim(ems.year.min() - 0.3, ems.year.max() + 2.2)
    ax.set_xticks(list(ems.year))
    ax.legend(frameon=False, fontsize=8, loc="lower left", labelcolor=INK2)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def chart_fire_premises(fire: pd.DataFrame, path: Path):
    fig, ax = plt.subplots(figsize=(8, 4), dpi=150)
    for col, color, label in [("residential_fires", S1, "Residential"),
                              ("non_building_fires", S2, "Non-building"),
                              ("non_residential_fires", S3, "Non-residential")]:
        ax.plot(fire.year, fire[col], color=color, lw=2, marker="o", ms=5, label=label)
        ax.annotate(f"{label} {fire[col].iloc[-1]:,}", (fire.year.iloc[-1], fire[col].iloc[-1]),
                    textcoords="offset points", xytext=(6, 0), va="center", fontsize=8, color=INK2)
    _style(ax, "Fire calls by premises type, 2019–2025 (comparable definition)", "Fire calls")
    ax.set_ylim(0)
    ax.set_xlim(fire.year.min() - 0.3, fire.year.max() + 1.6)
    ax.set_xticks(list(fire.year))
    ax.legend(frameon=False, fontsize=8, loc="upper right", labelcolor=INK2, bbox_to_anchor=(1, 1.02), ncol=3)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def chart_fire_severity(sev: pd.DataFrame, path: Path):
    fig, ax = plt.subplots(figsize=(8, 3.8), dpi=150)
    bars = ax.bar(sev.year, sev.injuries_per_100_fires, color=S1, width=0.6)
    for b, v in zip(bars, sev.injuries_per_100_fires):
        ax.annotate(f"{v:.1f}", (b.get_x() + b.get_width() / 2, v), textcoords="offset points",
                    xytext=(0, 4), ha="center", fontsize=8, color=INK2)
    _style(ax, "Fire injuries per 100 fire calls, 2019–2025", "Injuries per 100 fires")
    ax.set_xticks(list(sev.year))
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


# ---------------------------------------------------------------- main
def run(con: sqlite3.Connection) -> dict:
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGS.mkdir(parents=True, exist_ok=True)

    ems = pd.read_sql("SELECT * FROM ems_annual WHERE comparable_series = 1 ORDER BY year", con)
    fire = pd.read_sql("SELECT * FROM fire_annual WHERE comparable_series = 1 ORDER BY year", con)
    sev = pd.read_sql("SELECT * FROM fire_severity WHERE comparable_series = 1 ORDER BY year", con)
    mix = pd.read_sql("SELECT * FROM workload_mix ORDER BY year", con)
    cap = pd.read_sql("SELECT * FROM ems_per_capita ORDER BY year", con)
    for name, df in [("ems_annual", ems), ("fire_annual", fire), ("fire_severity", sev),
                     ("workload_mix", mix), ("ems_per_capita", cap)]:
        df.to_csv(TABLES / f"{name}.csv", index=False)

    e16, e25 = ems.iloc[0], ems.iloc[-1]
    years, calls = ems.year.to_numpy(float), ems.total_calls.to_numpy(float)
    proj_all = linear_projection(years, calls, [2026, 2027])
    keep = ~np.isin(ems.year, [2020, 2021])
    proj_ex_covid = linear_projection(years[keep], calls[keep], [2026, 2027])

    f19, f20, f25 = (fire.set_index("year").loc[y] for y in (2019, 2020, 2025))
    s = sev.set_index("year")
    st = {
        "ems": {
            "calls_2016": int(e16.total_calls), "calls_2025": int(e25.total_calls),
            "growth_2016_2025_pct": round(100 * (e25.total_calls / e16.total_calls - 1), 1),
            "cagr_2016_2025_pct": round(100 * ((e25.total_calls / e16.total_calls) ** (1 / 9) - 1), 2),
            "calls_per_day_2016": float(e16.calls_per_day), "calls_per_day_2025": float(e25.calls_per_day),
            "yoy_2020_pct": float(ems.set_index("year").loc[2020, "yoy_growth_pct"]),
            "yoy_2021_pct": float(ems.set_index("year").loc[2021, "yoy_growth_pct"]),
            "yoy_2022_pct": float(ems.set_index("year").loc[2022, "yoy_growth_pct"]),
            "yoy_2025_pct": float(e25.yoy_growth_pct),
            "non_emergency_or_false_pct_2016": float(e16.non_emergency_or_false_pct),
            "non_emergency_or_false_pct_2025": float(e25.non_emergency_or_false_pct),
            "false_alarm_pct_2016": float(e16.false_alarm_pct), "false_alarm_pct_2025": float(e25.false_alarm_pct),
            "non_emergency_pct_2016": float(e16.non_emergency_pct), "non_emergency_pct_2025": float(e25.non_emergency_pct),
            "non_emergency_or_false_calls_2025": int(e25.non_emergency_calls + e25.false_alarm_calls),
            "emergency_calls_2016": int(e16.emergency_calls), "emergency_calls_2025": int(e25.emergency_calls),
            "emergency_growth_2016_2025_pct": round(100 * (e25.emergency_calls / e16.emergency_calls - 1), 1),
        },
        "per_capita": {
            "per_1000_2017": float(cap.iloc[0].ems_calls_per_1000_pop),
            "per_1000_2024": float(cap.iloc[-1].ems_calls_per_1000_pop),
            "population_growth_2017_2024_pct": round(100 * (cap.iloc[-1].total_population / cap.iloc[0].total_population - 1), 1),
            "calls_growth_2017_2024_pct": round(100 * (cap.iloc[-1].total_calls / cap.iloc[0].total_calls - 1), 1),
        },
        "fire": {
            "total_2019": int(f19.total_fires), "total_2020": int(f20.total_fires), "total_2025": int(f25.total_fires),
            "min_year": int(fire.loc[fire.total_fires.idxmin(), "year"]), "min_total": int(fire.total_fires.min()),
            "growth_from_min_to_2025_pct": round(100 * (f25.total_fires / fire.total_fires.min() - 1), 1),
            "residential_pct_2025": float(f25.residential_pct),
            "residential_2022": int(fire.set_index("year").loc[2022, "residential_fires"]),
            "residential_2025": int(f25.residential_fires),
            "residential_growth_2022_2025_pct": round(100 * (f25.residential_fires / fire.set_index("year").loc[2022, "residential_fires"] - 1), 1),
            "non_building_2019": int(f19.non_building_fires), "non_building_2025": int(f25.non_building_fires),
            "non_building_cv_2020_2025_pct": round(100 * fire[fire.year >= 2020].non_building_fires.std() / fire[fire.year >= 2020].non_building_fires.mean(), 1),
            "residential_cv_2020_2025_pct": round(100 * fire[fire.year >= 2020].residential_fires.std() / fire[fire.year >= 2020].residential_fires.mean(), 1),
        },
        "severity": {
            "injuries_per_100_2021": float(s.loc[2021, "injuries_per_100_fires"]),
            "injuries_per_100_2022": float(s.loc[2022, "injuries_per_100_fires"]),
            "injuries_per_100_2023": float(s.loc[2023, "injuries_per_100_fires"]),
            "injuries_per_100_2025": float(s.loc[2025, "injuries_per_100_fires"]),
            "injuries_2022": int(s.loc[2022, "fire_injuries"]), "injuries_2023": int(s.loc[2023, "fire_injuries"]),
        },
        "workload": {
            "ems_share_pct_2025": float(mix.iloc[-1].ems_share_pct),
            "ems_to_fire_ratio_2025": round(float(mix.iloc[-1].ems_calls / mix.iloc[-1].fire_calls), 1),
        },
        "projection_all_years": proj_all,
        "projection_excl_2020_2021": proj_ex_covid,
    }
    (ROOT / "reports" / "stats.json").write_text(json.dumps(st, indent=2))

    chart_ems_trend(ems, proj_all, FIGS / "01_ems_calls_trend.png")
    chart_ems_mix(ems, FIGS / "02_ems_call_mix.png")
    chart_fire_premises(fire, FIGS / "03_fire_by_premises.png")
    chart_fire_severity(sev, FIGS / "04_fire_injuries_per_100_fires.png")
    return st


if __name__ == "__main__":
    st = run(build(DEFAULT_DB))
    print(json.dumps(st, indent=2))
