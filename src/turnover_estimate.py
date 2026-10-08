"""Shortcut estimate of minutes saved per turnover from alerting EVS at discharge_pending.

Monte Carlo on one room's wait, not a full state machine. Baseline wait is the
60-minute-rounds wait; the intervention wait is max(0, response + busy delay -
ready-to-leave gap), capped by the baseline because rounds continue.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _lognormal(rng: np.random.Generator, mean: float, cv: float, size: int) -> np.ndarray:
    sigma2 = np.log(1 + cv**2)
    return rng.lognormal(np.log(mean) - sigma2 / 2, np.sqrt(sigma2), size)


def _shift_utilization(config: dict[str, Any], daily_cleaning_hours: float) -> dict[str, float]:
    evs = config["evs_staffing"]
    layout = config["turnover_estimate"]["floor_counts"]
    productive = evs["productive_hours_per_shift"]
    util = {}
    for shift, share in config["turnover_estimate"]["workload_share_by_shift"].items():
        cleaners = sum(
            layout[kind] * evs["cleaners_per_floor"][kind][shift] for kind in layout
        )
        util[shift] = min(1.0, daily_cleaning_hours * share / (cleaners * productive))
    return util


def estimate_turnover_savings(
    config: dict[str, Any],
    mean_daily_discharges: float,
    mean_daily_cleaning_hours: float,
    seed: int,
    n: int = 100_000,
) -> pd.DataFrame:
    """Return minutes saved per turnover and bed-hours recovered per day, by shift."""
    est = config["turnover_estimate"]
    rng = np.random.default_rng(seed)
    util = _shift_utilization(config, mean_daily_cleaning_hours)
    clean_min = config["room_cleaning"]["unit_minutes"]["med_surg"]["discharge"]
    interval = config["evs_staffing"]["baseline_rounds"]["round_interval_minutes"]

    rows = []
    for shift, share in est["discharge_share_by_shift"].items():
        baseline = rng.uniform(0, interval, n)
        gap = _lognormal(rng, est["ready_to_leave_gap_minutes"]["mean"], est["ready_to_leave_gap_minutes"]["cv"], n)
        busy = rng.random(n) < util[shift]
        # Busy cleaner finishes the current clean first: residual uniform over one clean.
        delay = est["alert_response_minutes"] + busy * rng.uniform(0, clean_min, n)
        after = np.minimum(baseline, np.maximum(0.0, delay - gap))
        saved = baseline - after
        rows.append(
            {
                "shift": shift,
                "cleaner_utilization": util[shift],
                "baseline_wait_min": baseline.mean(),
                "intervention_wait_min": after.mean(),
                "minutes_saved_mean": saved.mean(),
                "minutes_saved_p10": np.percentile(saved, 10),
                "minutes_saved_p90": np.percentile(saved, 90),
                "turnovers_per_day": mean_daily_discharges * share,
                "bed_hours_recovered_per_day": mean_daily_discharges * share * saved.mean() / 60,
            }
        )
    out = pd.DataFrame(rows)
    total = {
        "shift": "all",
        "turnovers_per_day": out.turnovers_per_day.sum(),
        "bed_hours_recovered_per_day": out.bed_hours_recovered_per_day.sum(),
    }
    for col in ("baseline_wait_min", "intervention_wait_min", "minutes_saved_mean"):
        total[col] = np.average(out[col], weights=out.turnovers_per_day)
    return pd.concat([out, pd.DataFrame([total])], ignore_index=True)


def load_inputs(root: Path = ROOT) -> tuple[dict[str, Any], float, float]:
    """Load config plus mean daily discharges and cleaning hours from the workload CSV."""
    config = yaml.safe_load((root / "data" / "assumptions.yaml").read_text())
    df = pd.read_csv(root / "data" / "vcu_cleaning_workload_daily.csv")
    discharges = df.filter(like="discharges_").sum(axis=1).mean()
    return config, float(discharges), float(df["cleaning_hours_total"].mean())


if __name__ == "__main__":
    cfg, dis, hours = load_inputs()
    seed = cfg["turnover_estimate"]["seed"]
    print(estimate_turnover_savings(cfg, dis, hours, seed).round(2).to_string(index=False))
