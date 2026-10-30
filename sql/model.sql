-- SCDF incident trends: analytical model (SQLite)
-- Raw tables (loaded by src/build_model.py): raw_ems, raw_fire, raw_fire_casualties, raw_population
--
-- Comparability rules (documented in README "Data quality"):
--   R1  EMS call types were reclassified from 2016. Breakdown analysis uses 2016+ only.
--   R2  From 2019, fire counts exclude minor fires (rubbish bins/chutes). Fire trend analysis uses 2019+ only.
--   R3  Population is end-June total population; available 2017-2024 in this snapshot.

DROP VIEW IF EXISTS ems_annual;
CREATE VIEW ems_annual AS
SELECT
    e.year,
    e.total_calls,
    e.emergency_calls,
    e.non_emergency_calls,
    e.false_alarm_calls,
    CASE WHEN e.year >= 2016 THEN 1 ELSE 0 END                          AS comparable_series,  -- R1
    ROUND(e.total_calls * 1.0 / CASE WHEN e.year % 4 = 0 THEN 366 ELSE 365 END, 1) AS calls_per_day,
    ROUND(100.0 * e.emergency_calls / e.total_calls, 2)                 AS emergency_pct,
    ROUND(100.0 * e.non_emergency_calls / e.total_calls, 2)             AS non_emergency_pct,
    ROUND(100.0 * e.false_alarm_calls / e.total_calls, 2)               AS false_alarm_pct,
    ROUND(100.0 * (e.non_emergency_calls + e.false_alarm_calls) / e.total_calls, 2) AS non_emergency_or_false_pct,
    ROUND(100.0 * (e.total_calls - p.total_calls) / p.total_calls, 2)   AS yoy_growth_pct
FROM raw_ems e
LEFT JOIN raw_ems p ON p.year = e.year - 1;

DROP VIEW IF EXISTS fire_annual;
CREATE VIEW fire_annual AS
SELECT
    f.year,
    f.total_fires,
    f.building_fires,
    f.residential_fires,
    f.non_residential_fires,
    f.non_building_fires,
    CASE WHEN f.year >= 2019 THEN 1 ELSE 0 END                           AS comparable_series,  -- R2
    ROUND(100.0 * f.residential_fires / f.total_fires, 2)                AS residential_pct,
    ROUND(100.0 * f.non_residential_fires / f.total_fires, 2)            AS non_residential_pct,
    ROUND(100.0 * f.non_building_fires / f.total_fires, 2)               AS non_building_pct,
    ROUND(100.0 * (f.total_fires - p.total_fires) / p.total_fires, 2)    AS yoy_growth_pct
FROM raw_fire f
LEFT JOIN raw_fire p ON p.year = f.year - 1;

DROP VIEW IF EXISTS fire_severity;
CREATE VIEW fire_severity AS
SELECT
    f.year,
    f.total_fires,
    c.fire_injuries,
    c.fire_fatalities,
    ROUND(100.0 * c.fire_injuries / f.total_fires, 2)   AS injuries_per_100_fires,
    ROUND(100.0 * c.fire_fatalities / f.total_fires, 3) AS fatalities_per_100_fires,
    f.comparable_series
FROM fire_annual f
JOIN raw_fire_casualties c ON c.year = f.year;

DROP VIEW IF EXISTS workload_mix;
CREATE VIEW workload_mix AS
SELECT
    e.year,
    e.total_calls                                         AS ems_calls,
    f.total_fires                                         AS fire_calls,
    e.total_calls + f.total_fires                         AS combined_calls,
    ROUND(100.0 * e.total_calls / (e.total_calls + f.total_fires), 2) AS ems_share_pct
FROM ems_annual e
JOIN fire_annual f ON f.year = e.year
WHERE e.year >= 2019;  -- both series comparable from 2019 (R1, R2)

DROP VIEW IF EXISTS ems_per_capita;
CREATE VIEW ems_per_capita AS
SELECT
    e.year,
    e.total_calls,
    p.total_population,
    ROUND(1000.0 * e.total_calls / p.total_population, 2)     AS ems_calls_per_1000_pop,
    ROUND(1000.0 * e.emergency_calls / p.total_population, 2) AS emergency_calls_per_1000_pop
FROM ems_annual e
JOIN raw_population p ON p.year = e.year;  -- R3
