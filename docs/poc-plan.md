# POC Plan and Team Checklist

Use this file as the team's shared checklist. Mark items `[x]` only after they
pass the acceptance checks listed under each phase. Record new design decisions
in [occupied_beds_forecast_decisions.md](occupied_beds_forecast_decisions.md)
and new values in [`data/assumptions.yaml`](../data/assumptions.yaml). Update
[data_dictionary.md](data_dictionary.md) whenever a dataset gains or changes columns.

## Problem

The hospital is in "Code Red": a logistics emergency, not a medical one.
Patients wait in the ED because "available" beds are taken up by **ghost beds**:
uncleaned rooms, pending paperwork, or slow discharges.

| Who | Impact |
|---|---|
| Nurses | Crowded hallways, rising workload |
| ED staff | Admitted patients waiting (boarding) in the ED |
| Administrators | Lost revenue when elective surgeries are canceled for lack of post-op beds |

## What we measure

A **ghost bed** is a bed in `discharge_pending`, `needs_cleaning`, or
`cleaning`. It isn't serving a patient and can't take a new one.

| Metric | Definition |
|---|---|
| Ghost bed-hours | Time beds spend in the three ghost states, by unit and shift |
| ED boarding hours | Time admitted ED patients wait for a bed |
| Boarding during ghost time | Boarding hours that occur while at least one ghost bed exists |
| Car-wait hours | Time non-critical viral patients wait in their car, tracked separately from boarding |
| Elective cancellations / deferrals | Stand-in for lost revenue; we have no revenue data |
| Nurse ratio breaches | Shifts in which a unit's patient load exceeds its nurse ratio |
| Wait-estimate accuracy | How often the actual wait falls inside the estimated range, and how often the estimate is sent again |

## Design rules (summary)

The full rules are in [copilot-instructions.md](../.github/copilot-instructions.md).

- **Bed states:** `available → occupied → discharge_pending → needs_cleaning → cleaning → available`.
- **Priority** (lower rank is served first; no bed is taken from a patient once their stay starts):
  1. Life-threatening: ICU, ED patients going to ICU, active labor, critical-severity viral.
  2. Non-critical viral (waiting in car) and other ED admissions, served first come, first served.
  3. `non_elective_other`.
  4. Elective, placed by the optimizer.
- **Severity:** synthetic, 4 levels (`low`, `medium`, `high`, `critical`). Electives can't be `critical`.
- **Moveability:** `is_moveable` (true/false) plus `move_window`.
  Electives: high = 7 days, medium = 14 days *(pending confirmation)*, low = 30 days.
- **Elective request date:** the generated `date` is the requested date. Electives can only move later.
- **Viral PPE:** nurse workload ×1.05, cleaning time ×1.10.
- **`discharge_pending`:** 20-minute floor plus a log-normal part; overall mean 3 hours; scaled by severity.
- **Optimization:** OR-Tools CP-SAT re-plans electives each simulated day over a 3–4 day window and locks day 1. An elective's deadline becomes a hard constraint once it falls inside the window.
- **Staffing:** count staff per unit per shift (nurses, cleaning staff). First compare staffing levels across simulation runs, then optimize them. Scheduling individual nurses is out of scope.
- **Expected wait:** computed from simulation runs that start from the current state and shown as a range (p50–p80). Shown in the dashboard and alerts only; no real SMS.

## Phase 0: Data foundation (complete)

- [x] VCU monthly and daily occupancy reconstruction, 2017–2024 (`data/vcu_master_daily.csv`)
- [x] Section split into 9 sections and LOS-driven turnover
- [x] Nurse requirements by unit and shift (`data/vcu_nurse_requirements_daily.csv`)
- [x] Cleaning workload by unit (`data/vcu_cleaning_workload_daily.csv`)
- [x] Synthetic admissions with check-in times (`data/synthetic_appointments.csv`)
- [x] Generation notebooks archived for provenance (`notebooks/archive/`)

## Phase 1: Synthetic day and patient attributes (complete)

Notebook: `notebooks/01_synthetic_day.ipynb` · Code: `src/generators.py`

- [x] Add patient-attribute settings to `data/assumptions.yaml` (`patient_attributes`, `discharge_pending`), each marked `# ASSUMPTION:`: severity mix by category, priority ranks, move windows, PPE multipliers, discharge-pending distribution, elective deadline rule
- [x] Add columns to the appointment generator: `severity`, `priority_rank`, `is_moveable`, `move_window_days`, `deadline_date`, `unit` (via `assign_patient_attributes` in `src/generators.py`)
- [x] Anchor ED severity so the critical share matches the 28% ED-to-ICU assumption (observed 0.2797)
- [x] Electives' `date` is the requested date; `deadline_date = date + move_window_days`
- [x] Regenerate `synthetic_appointments.csv` from the generator (do not hand-edit it)
- [x] Build synthetic days from the arrival curve (time-varying Poisson arrivals): `generate_synthetic_day` in `src/generators.py`, scenarios `code_red_winter` (2024-01-08, 7 days, viral ×1.3 stress test) and `baseline_spring` (2024-05-06, 7 days), numbered output `data/synthetic_days_{run_id:02d}.csv`

Acceptance:
- Daily counts per category are unchanged from the current file.
- No elective has `critical` severity.
- The ED severity mix reproduces the configured ICU share within a stated tolerance.
- Re-running with the same seed reproduces the file exactly.

## Phase 2: Bed state machine and ghost states (next)

Notebook: `notebooks/02_bed_state_machine.ipynb` · Code: `src/sim.py`

- [ ] Model beds as a SimPy `PriorityResource`, patients as processes, and cleaning staff as a `Resource` with a count per shift
- [ ] Start every run empty (opening day, `synthetic_days.initial_state: empty`); report results with and without the first ~6 days of build-up
- [ ] Implement the `discharge_pending` distribution (20-minute floor + log-normal, scaled by severity)
- [ ] Replace the constant 30-minute `needs_cleaning` wait with a wait for a free cleaner
- [ ] Apply the viral PPE multipliers to cleaning and nurse workload
- [ ] Hold the mother–newborn bed for the longer of the two stays (`max(delivery_los, newborn_los)`)
- [ ] Track nurse-to-patient ratios per unit and shift; report breaches but do not block admissions

Acceptance:
- Bed states only ever follow the required order.
- No stay is interrupted once it starts.
- Equal-priority patients are served first come, first served.
- The simulated mean census stays within a stated tolerance of the source day.

## Phase 3: Event log and metrics

Notebook: `notebooks/03_event_log_metrics.ipynb` · Code: `src/events.py`

- [ ] Collect every state change in a pandas event log (`bed_id`, `patient_id`, `state`, `timestamp`, `unit`, `severity`) and save it as `data/event_log_{run_id:02d}.csv`
- [ ] Add metric queries for everything in *What we measure*
- [ ] Compare staffing levels across simulation runs (e.g., cleaners per shift and nurses per shift) and chart ghost bed-hours against staffing
- [ ] Run sensitivity tests on the `discharge_pending` mean (2 h / 3 h / 4 h)

Acceptance:
- The total time each bed spends across all states equals the length of the run.
- Metrics can be reproduced from the log alone.

## Phase 4: Optimization

Notebook: `notebooks/04_elective_optimization.ipynb` · Code: `src/schedule.py`

- [ ] Build a CP-SAT model that places electives using the p75–p80 LOS as each elective's planned duration
- [ ] Re-plan every simulated day over a 3–4 day window and lock day 1
- [ ] Make a deadline a hard constraint once it falls inside the window; give a growing priority weight to electives whose deadline is still further out
- [ ] Penalize moving electives whose date has already been announced
- [ ] Hold back capacity for expected emergency arrivals
- [ ] Staffing optimization: choose nurse and cleaning-staff counts per unit per shift to minimize ghost bed-hours plus boarding, within a budget (after the Phase 3 comparison runs)

Acceptance:
- No elective is placed after its deadline unless the model is infeasible, and infeasibility is reported.
- Cancellations and deferrals are lower than with a first-come baseline.

## Phase 5: Dashboard and alerts

Notebook: `notebooks/05_dashboard_alerts.ipynb` · Code: `src/alerts.py`, `app.py`

- [ ] Plotly Gantt timeline, one row per bed (grouped or filterable by unit, since 905 rows can't be read at once)
- [ ] Ghost-bed and boarding alerts
- [ ] Expected-wait range per waiting patient, with a re-notify flag when the estimate changes past a threshold, and a "come in now if symptoms worsen" note
- [ ] Staffing comparison view

## Open decisions

| # | Decision | Status |
|---|---|---|
| 1 | Medium elective deadline is 14 days | Pending confirmation |
| 2 | Maximum wait for non-critical virals before they are escalated (or first come, first served alone) | Open |
| 3 | Starting cleaning-staff count per shift | Open, no data |
| 4 | Severity mix per category and how severity scales `discharge_pending` | Draft in `assumptions.yaml`; needs review |
| 5 | `discharge_pending` CV (0.5 proposed) | Open |
| 6 | Wait-time threshold for re-sending the expected wait | Open |
| 7 | Priority-1 share was 36%; after splitting out scheduled deliveries and planned ICU admissions (rank 3) it is 30%. Scheduled shares (40% of non-critical delivery and ICU) are placeholders | Resolved for now; shares need a source |
| 8 | Opening-day (empty) start: a 7-day run won't reach the observed census (~700), so ghost-bed pressure is understated. Lengthen runs or accept as an opening-week scenario | Open |

## Known limitations

- Severity, priority, and moveability are synthetic; no patient-level data backs them.
- Length of stay is not tied to severity, because LOS comes from observed monthly means.
- ED visits and OR cases are not modeled; "ED" means inpatients admitted through the ED.
- Equal admission rates across categories mean that elective volume matches every other category by assumption.
- Influenza and COVID-19 arrive at nearly the same daily rate in January and May (equal admission-rate assumption). The winter scenario adds a ×1.3 viral surge as a labeled stress test, not as observed seasonality.
- Transport delays are folded into `discharge_pending`.
