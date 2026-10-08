# Copilot Instructions

## Project
Simulation of a 905-bed hospital's bed turnover, built from Virginia
state-level monthly averages. Goal: measure how much bed wait comes from
"ghost rooms" (empty but not yet cleaned), then test whether alerting cleaning
staff when a nurse marks a patient ready to leave reduces it. The plan, step
status, metrics, and open team decisions are in `README.md` — read it for any
task involving scope or acceptance criteria.

## Current phase
Step 2: Baseline simulation (see `README.md`).

## Unit being modeled
Whole hospital — every section with data (ICU, med-surg categories, delivery,
newborn). ED and OR are not modeled until visit/case data exists.

## Stack
In use: Python 3.13, uv, FastAPI, Uvicorn, Docker/Dev Container, JupyterLab,
pandas, NumPy, SciPy, Matplotlib, PyYAML.

Open team decisions (see "Open Team Decisions" in `README.md`): simulation
approach, how simulation results are stored, dashboard tool, GitHub credentials
in the container.
- Do not pick a tool for an open decision on your own. Present options and
  tradeoffs and let the user decide; once decided, it is recorded in `README.md`.
- New dependencies go through `uv add` (updates `pyproject.toml` and
  `uv.lock`) and require a container rebuild.
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
- Elective scheduling (parking lot, not current scope) uses a **p75–p80 LOS
  quantile**, not the mean, as the planning duration for elective cases.
- Any assumption not backed by real data (CV values, cleaning time, ED
  split %) must be flagged with a `# ASSUMPTION:` comment in code and
  listed in `data/assumptions.yaml`, not silently hardcoded.
- In `README.md` and other team-facing text, explain modeling terms in plain
  language (e.g. "most stays are near typical, a few run much longer" rather
  than only "log-normal LOS").

## Repo structure — keep this layout
```
data/assumptions.yaml
notebooks/            # numbered per step, e.g. 02_baseline_simulation.ipynb
src/generators.py     # Step 1
src/events.py         # Steps 2-3: shared check_in / current_care / check_out
src/api/              # Step 3: FastAPI route modules and JSON state file
src/sim.py            # Step 2
app.py                # Step 4 dashboard
```
Notebooks are for exploration and validation; reusable logic belongs in
`src/`, imported into notebooks, not duplicated.

## Out of scope for now — do not implement unless asked
- Real EHR/HL7/FHIR integration.
- Multi-hospital or variable-hospital-size modeling.
- LLM/agent layer for natural-language queries.
- Postgres or any live multi-user state store.
- Independently deployed microservices; the API is one modular FastAPI app.
- Staff scheduling optimization beyond a simple ratio constraint.

## Code style
- Notebooks: exploratory, minimal type hints/docstrings needed.
- `src/`: type hints and docstrings expected on functions.
- Every stochastic function takes an explicit `seed` parameter — no
  unseeded `np.random` calls, so runs are reproducible.