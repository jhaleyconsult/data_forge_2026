# Data Dictionary

Column-level reference for every dataset in `data/`. Values and settings come
from [`data/assumptions.yaml`](../data/assumptions.yaml); design decisions are
in [occupied_beds_forecast_decisions.md](occupied_beds_forecast_decisions.md).

**None of these files are patient-level observations.** All are reconstructed
or synthetic estimates for VCU Medical Center, built from Virginia statewide
monthly aggregates (HCUP, 2017–2024) and American Hospital Directory figures.

## Provenance labels

| Label | Meaning |
|---|---|
| **Derived** | Calculated from observed aggregate data (for example, monthly statewide census scaled to VCU) |
| **Synthetic** | Randomly generated from a seeded process; reproducible, but not observed |
| **Assumption** | Driven mainly by a value in `assumptions.yaml` marked `# ASSUMPTION:` |
| **Key** | Identifier or join field |

## Files

| File | Grain | Rows | Period | Produced by |
|---|---|---|---|---|
| [vcu_master_daily.csv](../data/vcu_master_daily.csv) | 1 row per day | 2,922 | 2017-01-01 – 2024-12-31 | `notebooks/archive/Health_data_generation_notebook.ipynb` |
| [vcu_nurse_requirements_daily.csv](../data/vcu_nurse_requirements_daily.csv) | 1 row per day | 2,922 | 2017–2024 | `notebooks/archive/nurse_constrant_generator_notebook.ipynb` |
| [vcu_cleaning_workload_daily.csv](../data/vcu_cleaning_workload_daily.csv) | 1 row per day | 2,922 | 2017–2024 | `notebooks/archive/nurse_constrant_generator_notebook.ipynb` |
| [synthetic_appointments.csv](../data/synthetic_appointments.csv) | 1 row per admission | 372,197 | 2017–2024 | `notebooks/archive/daily_appointment_data_generator_notebook.ipynb` |
| [synthetic_days_01.csv](../data/synthetic_days_01.csv) | 1 row per arrival | 1,606 | Two 7-day scenarios in 2024 | `notebooks/01_synthetic_day.ipynb` |

## Shared values

### `category` (admission section)

| Value | Meaning | Staffing `unit` | Base priority |
|---|---|---|---|
| `intensive` | ICU admission (peer section, not a diagnosis subset) | `icu` | 1 |
| `delivery` | Birthing parent's delivery stay | `labor_delivery` | 1 (3 if scheduled) |
| `newborn` | Infant stay; arrives with the mother in the simulation | `pediatric` | 1 (inherits delivery) |
| `non_elective_via_ed` | Inpatient admitted through the ED (not an ED visit) | `med_surg` | 2 |
| `non_elective_other` | Direct admit or transfer | `med_surg` | 3 |
| `elective` | Planned admission | `med_surg` | 4 |
| `covid_19` | COVID-19 admission (no data before 2020) | `med_surg` | 2 |
| `influenza` | Influenza admission | `med_surg` | 2 |
| `other_viral` | Other viral admission | `med_surg` | 2 |

Any `critical` patient is priority 1 regardless of category. Unit mapping is an
assumption (`nurse_staffing.category_to_unit`); for example, delivery at the
L&D active-labor ratio overstates nurse demand.

### `severity`
Ordered `low` < `medium` < `high` < `critical`. **Synthetic**; no severity data
exists. Electives are never `critical`; ICU is `high` or `critical` only.

### `priority_rank`
Queue order, lower is served first. 1 = life-threatening; 2 = non-critical
viral (car wait) and other ED admits, tied first-come-first-served;
3 = `non_elective_other` and scheduled delivery/ICU; 4 = elective.

## vcu_master_daily.csv

Daily census, admissions, discharges, and length of stay by section.

| Column | Type | Unit | Provenance | Description |
|---|---|---|---|---|
| `date` | date | — | Key | Calendar day |
| `total_staffed_beds` | int | beds | Derived | VCU staffed beds (constant 905, AHD) |
| `total_occupied_beds` | float | beds | Derived + Synthetic | Sum of the 9 `occupied_beds_*` sections. Range 482–749 |
| `total_free_beds` | float | beds | Derived | `total_staffed_beds - total_occupied_beds` |
| `occupied_beds_{category}` | int | beds | Derived + Synthetic | Midnight census for the section, from an LOS-driven turnover recurrence |
| `admissions_{category}` | int | patients/day | Synthetic | Poisson draw with rate = monthly target census / LOS |
| `expected_discharges_{category}` | float | patients/day | Derived | Prior-day census / current LOS |
| `avg_los_{category}_days` | float | days | Derived + Synthetic | Daily LOS, AR(1) around the monthly mean and rescaled to it. **No `avg_los_intensive_days`**: ICU uses the hospital-wide average (5.91 days) |

`{category}` covers all 9 sections above (8 for `avg_los_*`).

**Known gaps**
- `*_covid_19` columns are blank for 2017–2019 (37% of rows). These are structural placeholders, not zero stays.
- Influenza LOS has 13 suppressed months imputed with the calendar-month median.
- December 2024 was corrected as a data-entry anomaly; October–December 2024 COVID-19 values are projected.

## vcu_nurse_requirements_daily.csv

Nurses needed per 12-hour shift, by unit, from ratio ranges. Both shifts use the
midnight census (assumption; likely understates the day shift).

| Column | Type | Unit | Provenance | Description |
|---|---|---|---|---|
| `date` | date | — | Key | Calendar day |
| `total_occupied_beds` | float | beds | Derived | Copied from the master file |
| `census_{unit}` | int | patients | Derived | Census summed over categories mapped to the unit |
| `nurses_per_shift_min_{unit}` | int | nurses | Assumption | Fewest nurses: census / most patients per nurse, rounded up |
| `nurses_per_shift_max_{unit}` | int | nurses | Assumption | Most nurses: census / fewest patients per nurse, rounded up |
| `nurses_per_shift_{min,max}_total` | int | nurses | Derived | Sum over units |
| `nurse_shifts_per_day_{min,max}_total` | int | nurse-shifts | Derived | Per-shift total × 2 shifts |

`{unit}` is `icu` (1–2 patients per nurse), `med_surg` (4–5), `labor_delivery`
(1–2), `pediatric` (3–4). ED is not modeled. The viral PPE multiplier (×1.05) is
not applied in this file yet.

## vcu_cleaning_workload_daily.csv

Expected daily cleaning minutes by unit. Means only; per-clean times are
log-normal (CV 0.30) in simulation.

| Column | Type | Unit | Provenance | Description |
|---|---|---|---|---|
| `date` | date | — | Key | Calendar day |
| `discharges_{unit}` | float | patients/day | Derived | Sum of `expected_discharges_*` mapped to the unit |
| `occupied_clean_minutes_{unit}` | float | minutes | Assumption | Census × 1 clean per bed per day × occupied-clean mean |
| `discharge_clean_minutes_{unit}` | float | minutes | Assumption | Discharges × discharge-clean mean (duration of the `cleaning` bed state) |
| `occupied_clean_minutes_total` | float | minutes | Derived | Sum over units |
| `discharge_clean_minutes_total` | float | minutes | Derived | Sum over units |
| `cleaning_hours_total` | float | hours | Derived | (occupied + discharge minutes) / 60 |

Mean minutes per clean (occupied / discharge): med-surg 30/45, ICU 40/60; L&D
and pediatric reuse med-surg. All are unverified estimates. The viral PPE
multiplier (×1.10) is not applied in this file yet.

## synthetic_appointments.csv

One row per admission counted in the master file, with a synthetic check-in time
and patient attributes. Daily counts per category match the master file exactly.

| Column | Type | Unit | Provenance | Description |
|---|---|---|---|---|
| `appointment_id` | string | — | Key | `key-{source_key}-{category}-{nnnn}`; unique |
| `source_key` | int | — | Key | Row number of the source day in the master file |
| `date` | date | — | Derived | Admission day; for electives, the **requested** date |
| `category` | string | — | Derived | See shared values |
| `check_in_time` | time | HH:MM:SS | Synthetic | Sampled from the diurnal curve (peak 10:00, intensity 0.3–1.7× mean) |
| `severity` | string | — | Synthetic | See shared values |
| `priority_rank` | int | — | Assumption | 1–4, see shared values |
| `is_scheduled` | bool | — | Synthetic | Scheduled delivery or planned ICU admission (placeholder 40% of non-critical) |
| `is_moveable` | bool | — | Assumption | True for all electives and non-critical virals |
| `move_window_days` | int (nullable) | days | Assumption | Electives: high 7, medium 14 (unconfirmed), low 30. Non-critical viral: 0 (same day). Blank if not moveable |
| `deadline_date` | date (nullable) | — | Derived | `date + move_window_days`; blank if not moveable |
| `unit` | string | — | Assumption | Staffing unit from `category_to_unit` |

Seed: `patient_attributes.seed` (2027) for attributes and
`appointment_arrivals.seed` (2026) for times. Newborns appear as separate rows
here; the simulation treats them as part of the delivery couplet.

## synthetic_days_{run_id}.csv

Arrivals for simulation scenarios, generated as a non-homogeneous Poisson
process (daily counts vary randomly). File number = `synthetic_days.run_id`.

| Column | Type | Unit | Provenance | Description |
|---|---|---|---|---|
| `run_id` | int | — | Key | Arrival-set number; part of the seed |
| `scenario` | string | — | Key | `code_red_winter` (stress test: viral arrivals ×1.3) or `baseline_spring` |
| `patient_id` | string | — | Key | `{YYYYMMDD}-{category}-{nnnn}`; unique within a run |
| `date` | date | — | Derived | Arrival day |
| `category` | string | — | Derived | See shared values; newborns excluded (couplet) |
| `arrival_time` | datetime | — | Synthetic | Arrival timestamp from the diurnal curve |
| `severity` … `unit` | — | — | — | Same definitions as `synthetic_appointments.csv` |

Daily rate per category = mean daily admissions in the scenario's month.
Simulations start with no occupied beds (opening day, assumption). Seed:
`synthetic_days.seed` (2028) combined with `run_id`.

| Scenario | Dates | Expected arrivals/day | Month mean census (reference) |
|---|---|---|---|
| `code_red_winter` | 2024-01-08 – 01-14 | 130.7 | 714.6 |
| `baseline_spring` | 2024-05-06 – 05-12 | 111.5 | 660.5 |
