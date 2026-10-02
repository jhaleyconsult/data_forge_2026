# Copilot Instructions

## Project
Discrete-event simulation of a hospital unit's bed/room scheduling, built from
Virginia state-level monthly averages (patient volume, length of stay, wait
times). Goal: generate a synthetic day, simulate bed state transitions,
handle emergency-priority patients, optimize elective scheduling, and surface
a master calendar with alerts. Full phase breakdown and acceptance criteria
are in `docs/poc-plan.md` — read that for context on any task involving
phase scope or acceptance criteria.

Problem: a logistics "Code Red". ED patients board because beds are held by
**ghost beds** (`discharge_pending`, `needs_cleaning`, `cleaning`). Nurses
absorb hallway crowding; electives are canceled for lack of post-op beds.

## Current phase
Phase 2: bed state machine and ghost states. Phase 1 (synthetic days and
patient attributes) is complete. See the checklist in `docs/poc-plan.md`.

## Unit being modeled
Whole hospital — every section with data (ICU, med-surg categories, delivery,
newborn). ED and OR are not modeled until visit/case data exists.

## Stack — use these, don't substitute
- Simulation: **SimPy**. Beds and staff are `simpy.Resource` /
  `PriorityResource`, patients are SimPy processes. Do not build a custom
  event loop or use threading for this.
- Distributions/data: **NumPy, SciPy, pandas**.
- Event log + analytics: **pandas**. All simulation events (bed_id,
  patient_id, state, timestamp) are collected into a DataFrame and saved as
  CSV per run. The event log is for metrics after a run — it is not the live
  in-memory state during a run; SimPy owns that. No database.
- Optimization: **OR-Tools CP-SAT** for elective/scheduled patient placement
  and unit-level staffing counts per shift.
  Not PuLP/Pyomo unless CP-SAT can't express a constraint.
- Dashboard: **Streamlit** + **Plotly** (Gantt-style timeline, one row per bed).
- Config/assumptions: single `data/assumptions.yaml`, not hardcoded constants
  scattered across files.

## Modeling rules
- Length of stay and wait times are **right-skewed** — always model as
  log-normal (or gamma), never as normal/Gaussian.
- Given a mean `m` and coefficient of variation `c`, derive log-normal
  parameters as: `sigma2 = ln(1 + c^2)`, `mu = ln(m) - sigma2/2`.
- Arrivals follow a **non-homogeneous Poisson process** (rate varies by hour),
  not a fixed-interval or uniform-random arrival pattern.
- Emergency patients get priority in the **queue**, not by preempting an
  already-occupied bed. Once a stay starts, it is not interrupted.
- Bed state machine has exactly these states, in this order:
  `available → occupied → discharge_pending → needs_cleaning → cleaning → available`.
- Planning/optimization (Phase 4) uses a **p75–p80 LOS quantile**, not the
  mean, as the planning duration for elective cases.
- Severity is synthetic: `low`, `medium`, `high`, `critical`. Electives are
  never `critical`.
- Queue priority (lower served first): 1) life-threatening (ICU, ED→ICU,
  active labor, critical viral); 2) non-critical viral (car wait) and other
  ED admits, tied and served FIFO by arrival; 3) `non_elective_other`;
  4) elective.
- Patients carry `is_moveable` (bool) and a `move_window`. Elective windows:
  high 7 days, medium 14 days, low 30 days, counted from the generated `date`
  (the requested date). Electives only move later.
- Elective planning re-plans daily over a 3–4 day rolling horizon and commits
  day 1. A deadline becomes a hard constraint once inside the horizon.
- Viral PPE: nurse workload ×1.05, cleaning time ×1.10.
- `discharge_pending` = 20-minute floor + log-normal, overall mean 3 hours,
  scaled by severity.
- Nurses are a measured ratio (breaches reported), not a blocking resource.
  EVS cleaners are a blocking SimPy `Resource` per shift.
- Expected patient wait is a simulated range (p50–p80), shown in the
  dashboard only.
- Any assumption not backed by real data (CV values, cleaning time, ED
  split %) must be flagged with a `# ASSUMPTION:` comment in code and
  listed in `data/assumptions.yaml`, not silently hardcoded.

## Repo structure — keep this layout
```
data/assumptions.yaml
notebooks/01_synthetic_day.ipynb ... 05_dashboard_alerts.ipynb
src/generators.py, sim.py, events.py, schedule.py, alerts.py
app.py
docs/poc-plan.md
```
Notebooks are for exploration and validation; reusable logic belongs in
`src/`, imported into notebooks, not duplicated.

## Out of scope for now — do not implement unless asked
- Real EHR/HL7/FHIR integration.
- Multi-hospital or variable-hospital-size modeling.
- LLM/agent layer for natural-language queries.
- Postgres or any live multi-user state store.
- Individual nurse rostering (named staff, rotations). Unit-level staff
  counts per shift are in scope.
- Sending real patient notifications (SMS/push).

## Code style
- Notebooks: exploratory, minimal type hints/docstrings needed.
- `src/`: type hints and docstrings expected on functions.
- Every stochastic function takes an explicit `seed` parameter — no
  unseeded `np.random` calls, so runs are reproducible.