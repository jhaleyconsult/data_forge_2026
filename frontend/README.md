# Room Turnover Prototype

A local React + shadcn prototype for the nurse-to-EVS room-cleaning handoff. It

uses fictional room data and in-memory state only; it does not connect to an
EHR, notify real staff, or persist events to an API.

## Run

```bash
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Node 22 is provided by the repository Dev Container. Open the Vite URL printed
in the terminal.

## Workflow

Switch between Nurse and EVS views. The sample room board follows
`available → occupied → discharge_pending → needs_cleaning → cleaning → available`.
Nurse actions route simulated alerts to EVS; completing a clean routes a simulated
availability alert back to nursing. Use **Reset demo** to restore the initial
# Room Turnover Prototype

A local React + shadcn prototype for the nurse-to-EVS room-cleaning handoff. It
uses fictional room data and in-memory state only; it does not connect to an
EHR, notify real staff, or persist events to an API.

## Run

```bash
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Node 22 is provided by the repository Dev Container. Open the Vite URL printed
in the terminal.

## Workflow

Switch between Nurse and EVS views. The sample room board follows
`available → occupied → discharge_pending → needs_cleaning → cleaning → available`.
Nurse actions route simulated alerts to EVS; completing a clean routes a simulated
availability alert back to nursing. Use **Reset demo** to restore the initial
room states.
    "typeAware": true
