# Copilot Instructions

## Project
Discrete-event simulation of a hospital unit's bed/room scheduling, built from
Virginia state-level monthly averages (patient volume, length of stay, wait
times). Goal: generate a synthetic day, simulate bed state transitions,
handle emergency-priority patients, optimize elective scheduling, and surface
a master calendar with alerts. Full phase breakdown and acceptance criteria
are in `docs/poc-plan.md` — read that for context on any task involving
phase scope or acceptance criteria.

## Current phase
[FILL IN — e.g. "Phase 2: bed state machine" — update this as the project moves forward]

## Unit being modeled
[FILL IN — ED / general inpatient (med-surg) / ICU]

## Stack — use these, don't substitute
- Simulation: **SimPy**. Beds and staff are `simpy.Resource` /
  `PriorityResource`, patients are SimPy processes. Do not build a custom
  event loop or use threading for this.
- Distributions/data: **NumPy, SciPy, pandas**.
- Event log + analytics: **DuckDB**. All simulation events (bed_id,
  patient_id, state, timestamp) get written here. DuckDB is for the event
  log and metric queries — it is not the live in-memory state during a run;
  SimPy owns that.
- Optimization: **OR-Tools CP-SAT** for elective/scheduled patient placement.
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
- Staff scheduling optimization beyond a simple ratio constraint.

## Code style
- Notebooks: exploratory, minimal type hints/docstrings needed.
- `src/`: type hints and docstrings expected on functions.
- Every stochastic function takes an explicit `seed` parameter — no
  unseeded `np.random` calls, so runs are reproducible.