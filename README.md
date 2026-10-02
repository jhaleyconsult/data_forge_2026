# data_forge_2026

Discrete-event simulation of hospital bed and room scheduling for VCU Medical
Center (905 staffed beds), built from Virginia statewide monthly aggregates
(HCUP summary trend tables, 2017–2024). All daily and section-level values are
modeled estimates, not patient-level observations.

Scope: the whole hospital — every section with data (ICU, med-surg categories,
delivery, newborn). ED and OR are not modeled until visit/case data exists.

## Stack

| Purpose | Tool |
|---|---|
| Data / distributions | pandas, NumPy, SciPy |
| Configuration | PyYAML (`data/assumptions.yaml`) |
| Plots | Matplotlib |
| Notebooks | Jupyter |
| Environment | uv, Rancher Desktop container |

## File structure

```
.
├── .devcontainer/devcontainer.json            # VS Code Dev Container config
├── .github/
│   ├── agents/mary.agent.md                   # Mary, the project's Copilot agent
│   └── copilot-instructions.md                # Project rules and modeling constraints
├── data/
│   ├── assumptions.yaml                       # All config + flagged assumptions
│   ├── create_daily_totals_table.sql          # DuckDB table schema
│   ├── vcu_master_daily.csv                   # Daily census/admissions/discharges/LOS by section
│   ├── vcu_nurse_requirements_daily.csv       # Daily min/max nurses per shift by unit
│   ├── vcu_cleaning_workload_daily.csv        # Daily cleaning minutes by unit
│   └── synthetic_appointments.csv             # Synthetic appointment data
├── docs/
│   └── occupied_beds_forecast_decisions.md    # Forecasting decisions log
├── src/
│   └── generators.py                          # Reusable data generation / constraint functions
├── notebooks/
│   └── archive/                                # Completed data-generation notebooks; retained for provenance
│       ├── Health_data_generation_notebook.ipynb
│       ├── daily_appointment_data_generator_notebook.ipynb
│       └── nurse_constrant_generator_notebook.ipynb
├── Dockerfile                                 # Container image (Python 3.13 + uv)
├── pyproject.toml                             # Dependencies
└── uv.lock                                    # Pinned dependency versions
```

Archived notebooks preserve the historical data-generation process; generated datasets are the current inputs. Reusable logic for future simulation work belongs in `src/`.
Assumptions not backed by data are marked `# ASSUMPTION:` in code and recorded
in `data/assumptions.yaml`.

## Install

The project runs in a container so dependencies are not installed into your
local Python.

### 1. Install Rancher Desktop

Install [Rancher Desktop](https://rancherdesktop.io/) and set the container
engine to **dockerd (moby)** under *Preferences → Container Engine*. Wait until
Rancher reports it is running.

If the `docker` CLI cannot reach Rancher, point it at Rancher's engine:

```powershell
docker context use default
```

### 2. Build the image

```powershell
docker build -t data-forge-2026 .
```

### 3. Run a command in the container

The project folder is mounted, so outputs are written back to your local `data/`.

```powershell
docker run --rm -v "${PWD}:/workspace" data-forge-2026 python -c "import src.generators"
```

### Changing dependencies

```powershell
# edit pyproject.toml, then:
uv lock
docker build -t data-forge-2026 .
```

## Mary — the project agent

Mary is a GitHub Copilot custom agent for this
project: data-readiness checks, notebook development and validation, and
simulation modeling within the project's rules and documented assumptions.

Mary Eliza Mahoney was the first African American in the United States to earn
a professional nursing license, and she spent her career advancing equality for
African Americans and women.

Archived notebooks preserve the historical data-generation process; generated datasets are the current inputs. Reusable logic for future simulation work belongs in `src/`.
- **Early life:** Born in spring 1845 in Boston to parents who had been
  enslaved in North Carolina, she attended the Phillips School, one of the
  country's first integrated schools.
- **Path to nursing:** As a teenager she joined the New England Hospital for
  Women and Children, run by an all-women physician staff, and worked there for
  15 years as a janitor, cook, washerwoman, and nurse's aide.
- **Licensure:** In 1878, at age 33, she entered the hospital's 16-month
  nursing program. Of 42 students admitted, only four graduated in 1879 — she
  was one of them.
- **Career:** To avoid the discrimination common in public nursing, she worked
  as a private nurse along the East Coast, known for her efficiency, patience,
  and bedside manner. From 1911 to 1912 she directed the Howard Orphan Asylum
  for Black children on Long Island.
- **Advocacy:** She joined the Nurses Associated Alumnae of the United States
  and Canada (later the American Nurses Association) in 1896, and in 1908
  co-founded the National Association of Colored Graduate Nurses (NACGN), which
  made her its national chaplain and a life member. After the 19th Amendment
  passed in 1920, she was among the first women in Boston to register to vote.
- **Legacy:** She died on January 4, 1926, and is buried in Woodlawn Cemetery
  in Everett, Massachusetts. The NACGN created the Mary Mahoney Award in 1936,
  still given by the American Nurses Association to nurses who advance
  integration in the profession. She was inducted into the ANA Hall of Fame in
  1976 and the National Women's Hall of Fame in 1993. A monument at her grave,
  led by 1968 award winner Helen S. Miller with support from Chi Eta Phi and the
  ANA, was completed in 1973.

The agent carries her name as a reminder that this project models real nursing
work and the patients it serves.

### Use Mary

The agent is defined in `.github/agents/mary.agent.md`, so VS Code loads it
automatically when this folder is open. In Copilot Chat, open the agent picker
and select **Mary**.

### Create Mary from scratch

1. Create `.github/agents/mary.agent.md` in the project root.
2. Add frontmatter that names the agent and limits its tools:

   ```markdown
   ---
   name: "Mary"
   description: "Use for data-readiness assessment, healthcare simulation modeling, Jupyter notebook development, validation, and reproducible analysis in the data_forge_2026 project."
   tools: [read, search, edit, execute]
   user-invocable: true
   ---
   ```

3. Below the frontmatter, write Mary's instructions in Markdown: her
   responsibilities, the project constraints, the data-readiness and notebook
   workflows, and the response format. Use the existing file as the template.
4. Reload VS Code; **Mary** appears in the Copilot Chat agent picker.

Project-wide rules that apply to every agent live in
`.github/copilot-instructions.md`.

## Reproducibility

Every stochastic function takes an explicit `seed`; seeds are set in
`data/assumptions.yaml`.
