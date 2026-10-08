import marimo

__generated_with = "0.25.1"
app = marimo.App(width="wide")


@app.cell
def _():
    from pathlib import Path

    import matplotlib.pyplot as plt
    import marimo as mo
    import pandas as pd
    import yaml

    return Path, mo, pd, plt, yaml


@app.cell
def _(Path, pd):
    project_root = next(
        (
            path
            for path in [Path.cwd(), *Path.cwd().parents]
            if (path / "data" / "assumptions.yaml").is_file()
        ),
        None,
    )
    if project_root is None:
        raise FileNotFoundError("Run this app from the workspace root or below it.")

    data_dir = project_root / "data"
    output_dir = project_root / "notebooks" / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    assumptions_path = data_dir / "assumptions.yaml"
    beds = pd.read_csv(data_dir / "vcu_master_daily.csv", parse_dates=["date"])
    nursing = pd.read_csv(
        data_dir / "vcu_nurse_requirements_daily.csv", parse_dates=["date"]
    )
    evs = pd.read_csv(
        data_dir / "vcu_cleaning_workload_daily.csv", parse_dates=["date"]
    )
    appointments = pd.read_csv(
        data_dir / "synthetic_appointments.csv", parse_dates=["date"]
    )

    required = {
        "beds": {"date", "total_staffed_beds", "total_occupied_beds", "total_free_beds"},
        "nursing": {"date", "nurses_per_shift_min_total", "nurses_per_shift_max_total"},
        "evs": {"date", "cleaning_hours_total", "occupied_clean_minutes_total", "discharge_clean_minutes_total"},
        "appointments": {"date", "appointment_id", "check_in_time"},
    }
    source_frames = {
        "beds": beds,
        "nursing": nursing,
        "evs": evs,
        "appointments": appointments,
    }
    for name, frame in source_frames.items():
        missing = required[name] - set(frame.columns)
        if missing:
            raise ValueError(f"{name} is missing columns: {sorted(missing)}")

    cleaning_report = []
    for name, frame in source_frames.items():
        frame.columns = (
            frame.columns.astype(str)
            .str.strip()
            .str.lower()
            .str.replace(r"[^a-z0-9]+", "_", regex=True)
            .str.strip("_")
        )
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
        if frame["date"].isna().any():
            raise ValueError(f"{name} contains invalid dates")
        before = len(frame)
        frame.drop_duplicates(inplace=True)
        if name == "appointments":
            frame.drop_duplicates(subset=["appointment_id"], keep="first", inplace=True)
        cleaning_report.append(
            {
                "source": name,
                "rows": len(frame),
                "duplicates_removed": before - len(frame),
                "missing_values": int(frame.isna().sum().sum()),
            }
        )
        excluded = {"date", "appointment_id", "category", "check_in_time"}
        for column in frame.columns:
            if column not in excluded and frame[column].dtype == "object":
                frame[column] = pd.to_numeric(frame[column], errors="coerce")

    for name, frame in {"beds": beds, "nursing": nursing, "evs": evs}.items():
        if frame["date"].duplicated().any():
            raise ValueError(f"{name} contains duplicate dates")
    appointments["arrival_delta"] = pd.to_timedelta(
        appointments["check_in_time"].astype("string").str.strip(), errors="coerce"
    )
    if appointments["arrival_delta"].isna().any():
        raise ValueError("Some synthetic appointment times could not be parsed")
    appointments["arrival_hour"] = appointments["arrival_delta"].dt.components.hours
    cleaning_report = pd.DataFrame(cleaning_report)

    return (
        appointments,
        assumptions_path,
        beds,
        cleaning_report,
        evs,
        nursing,
        output_dir,
        project_root,
    )


@app.cell
def _(appointments, assumptions_path, beds, evs, mo, nursing, pd, yaml):
    with assumptions_path.open(encoding="utf-8") as assumptions_file:
        assumptions = yaml.safe_load(assumptions_file)
    revenue_hypothesis = assumptions.get("business_impact", {}).get(
        "faster_turnover_may_increase_revenue"
    )
    if revenue_hypothesis is None:
        raise KeyError("Revenue hypothesis is missing from data/assumptions.yaml")

    daily_sources = {"beds": beds, "nursing": nursing, "evs": evs}
    date_sets = {name: set(frame["date"]) for name, frame in daily_sources.items()}
    date_sets["appointments"] = set(appointments["date"].unique())
    base_dates = date_sets["beds"]
    coverage_check = pd.DataFrame(
        [
            {
                "source": name,
                "days": len(date_sets[name]),
                "first_date": min(date_sets[name]),
                "last_date": max(date_sets[name]),
                "matches_bed_dates": date_sets[name] == base_dates,
            }
            for name in ["beds", "nursing", "evs", "appointments"]
        ]
    )
    if not coverage_check["matches_bed_dates"].all():
        raise ValueError("Source date coverage differs")

    appointments_daily = appointments.groupby("date", as_index=False).agg(
        synthetic_appointment_count=("appointment_id", "count")
    )
    appointments_hourly = appointments.groupby("arrival_hour").size().reindex(
        range(24), fill_value=0
    )
    nurse_columns = [
        "date",
        "nurses_per_shift_min_icu",
        "nurses_per_shift_max_icu",
        "nurses_per_shift_min_med_surg",
        "nurses_per_shift_max_med_surg",
        "nurses_per_shift_min_labor_delivery",
        "nurses_per_shift_max_labor_delivery",
        "nurses_per_shift_min_pediatric",
        "nurses_per_shift_max_pediatric",
        "nurses_per_shift_min_total",
        "nurses_per_shift_max_total",
    ]
    operational = (
        beds.merge(nursing[nurse_columns], on="date", validate="one_to_one")
        .merge(evs, on="date", validate="one_to_one")
        .merge(appointments_daily, on="date", validate="one_to_one")
        .sort_values("date")
        .reset_index(drop=True)
    )
    if len(operational) != len(base_dates) or operational["date"].duplicated().any():
        raise ValueError("Unified daily timeline does not match shared date coverage")

    operational["occupancy_pct"] = (
        operational["total_occupied_beds"] / operational["total_staffed_beds"] * 100
    )
    operational["patients_per_min_required_nurse"] = (
        operational["total_occupied_beds"]
        / operational["nurses_per_shift_min_total"]
    )
    monthly_history = operational.set_index("date").resample("MS").agg(
        mean_occupied_beds=("total_occupied_beds", "mean"),
        mean_free_beds=("total_free_beds", "mean"),
        mean_occupancy_pct=("occupancy_pct", "mean"),
        mean_evs_hours=("cleaning_hours_total", "mean"),
        mean_occupied_clean_hours=("occupied_clean_minutes_total", lambda values: values.mean() / 60),
        mean_discharge_clean_hours=("discharge_clean_minutes_total", lambda values: values.mean() / 60),
        mean_appointments_per_day=("synthetic_appointment_count", "mean"),
    )
    assumption_summary = pd.DataFrame(
        [
            {"topic": "Daily census", "status": "Reconstructed from monthly Virginia aggregates; not live or patient-level."},
            {"topic": "Nurse staffing", "status": "Modeled requirements; delivery staffing is known to be overstated."},
            {"topic": "EVS cleaning", "status": "Estimated cleaning durations; no room-level turnaround events."},
            {"topic": "Appointments", "status": "Synthetic arrivals generated from an assumed hourly profile."},
            {"topic": "Revenue", "status": "Stakeholder hypothesis only; not measured or tested."},
        ]
    )
    mo.md(
        "Historical data are reconstructed daily estimates through 2024, not a live feed. "
        "EVS workload is estimated demand, not measured turnaround, backlog, or overtime."
    )

    return (
        assumption_summary,
        appointments_hourly,
        base_dates,
        coverage_check,
        monthly_history,
        operational,
        revenue_hypothesis,
    )


@app.cell
def _(mo, operational):
    years = sorted(operational["date"].dt.year.unique(), reverse=True)
    period_filter = mo.ui.dropdown(
        options=["All history", *[str(year) for year in years]],
        value="All history",
        label="History period",
    )
    period_filter
    return (period_filter,)


@app.cell
def _(operational, output_dir, pd, period_filter):
    if period_filter.value == "All history":
        selected_data = operational.copy()
        period_label = "All history (2017-2024)"
        period_key = "all_history"
    else:
        selected_year = int(period_filter.value)
        selected_data = operational.loc[
            operational["date"].dt.year == selected_year
        ].copy()
        period_label = str(selected_year)
        period_key = str(selected_year)

    monthly_view = selected_data.set_index("date").resample("MS").agg(
        mean_occupied_beds=("total_occupied_beds", "mean"),
        mean_free_beds=("total_free_beds", "mean"),
        mean_occupancy_pct=("occupancy_pct", "mean"),
        mean_nurses_min=("nurses_per_shift_min_total", "mean"),
        mean_nurses_max=("nurses_per_shift_max_total", "mean"),
        mean_evs_hours=("cleaning_hours_total", "mean"),
        occupied_clean_hours=("occupied_clean_minutes_total", lambda values: values.mean() / 60),
        discharge_clean_hours=("discharge_clean_minutes_total", lambda values: values.mean() / 60),
        mean_appointments_per_day=("synthetic_appointment_count", "mean"),
    )
    monthly_nursing = selected_data.set_index("date").resample("MS").mean(
        numeric_only=True
    )
    latest = selected_data.iloc[-1]
    latest_snapshot = pd.DataFrame(
        [
            {"metric": "Date", "value": latest["date"].date().isoformat(), "unit": "latest in selected period"},
            {"metric": "Staffed beds", "value": int(latest["total_staffed_beds"]), "unit": "beds"},
            {"metric": "Occupied beds", "value": round(latest["total_occupied_beds"], 1), "unit": "beds"},
            {"metric": "Available beds", "value": round(latest["total_free_beds"], 1), "unit": "beds"},
            {"metric": "Occupancy", "value": round(latest["occupancy_pct"], 1), "unit": "%"},
            {"metric": "Nurses required, minimum", "value": int(latest["nurses_per_shift_min_total"]), "unit": "per shift; modeled"},
            {"metric": "Nurses required, maximum", "value": int(latest["nurses_per_shift_max_total"]), "unit": "per shift; modeled"},
            {"metric": "Patients per nurse at minimum staffing", "value": round(latest["patients_per_min_required_nurse"], 2), "unit": "derived ratio"},
            {"metric": "EVS cleaning workload", "value": round(latest["cleaning_hours_total"], 1), "unit": "estimated hours per day"},
            {"metric": "Synthetic appointments", "value": int(latest["synthetic_appointment_count"]), "unit": "arrivals per day"},
        ]
    )
    annual_kpis = selected_data.assign(year=selected_data["date"].dt.year).groupby(
        "year", as_index=False
    ).agg(
        mean_occupied_beds=("total_occupied_beds", "mean"),
        mean_available_beds=("total_free_beds", "mean"),
        mean_occupancy_pct=("occupancy_pct", "mean"),
        mean_nurses_min_per_shift=("nurses_per_shift_min_total", "mean"),
        mean_nurses_max_per_shift=("nurses_per_shift_max_total", "mean"),
        mean_evs_hours_per_day=("cleaning_hours_total", "mean"),
        mean_synthetic_appointments_per_day=("synthetic_appointment_count", "mean"),
    )
    latest_snapshot.to_csv(
        output_dir / f"latest_available_day_kpis_{period_key}.csv", index=False
    )
    annual_kpis.to_csv(output_dir / f"annual_stakeholder_kpis_{period_key}.csv", index=False)
    monthly_view.to_csv(
        output_dir / f"monthly_operational_trends_{period_key}.csv",
        index_label="month",
    )

    return (
        annual_kpis,
        latest_snapshot,
        monthly_nursing,
        monthly_view,
        period_key,
        period_label,
    )


@app.cell
def _(annual_kpis, latest_snapshot, mo, period_label):
    mo.vstack(
        [
            mo.md(
                f"## {period_label}\nLatest available data are reconstructed daily estimates, not live census."
            ),
            latest_snapshot,
            mo.md("### Annual stakeholder summary"),
            annual_kpis,
        ]
    )
    return


@app.cell
def _(assumption_summary, cleaning_report, coverage_check, mo, revenue_hypothesis):
    revenue_note = mo.md(
        f"### Revenue assumption\nRecorded in `data/assumptions.yaml`: `{revenue_hypothesis}`. "
        "This is an untested stakeholder hypothesis. The available data have no actual turnover "
        "timestamps, unmet inpatient demand, payer mix, reimbursement, or marginal costs; "
        "therefore this app does not estimate revenue."
    )
    mo.vstack(
        [
            mo.md("### Source coverage"),
            coverage_check,
            mo.md("### Source cleaning checks"),
            cleaning_report,
            mo.md("### Assumptions and limitations"),
            assumption_summary,
            revenue_note,
        ]
    )
    return


@app.cell
def _(appointments, monthly_nursing, monthly_view, output_dir, period_key, plt, selected_data):
    plt.rcParams.update({"axes.grid": True, "grid.alpha": 0.25})
    figure, axes = plt.subplots(3, 2, figsize=(15, 13))

    axes[0, 0].plot(monthly_view.index, monthly_view["mean_occupied_beds"], label="Occupied", color="#176B87")
    axes[0, 0].plot(monthly_view.index, monthly_view["mean_free_beds"], label="Available", color="#E07A5F")
    axes[0, 0].set_title("Beds: occupied and available")
    axes[0, 0].set_ylabel("Average beds per day")
    axes[0, 0].legend()
    axes[0, 1].plot(monthly_view.index, monthly_view["mean_occupancy_pct"], color="#3A7D44")
    axes[0, 1].set_title("Bed occupancy")
    axes[0, 1].set_ylabel("Percent")

    axes[1, 0].plot(monthly_nursing.index, monthly_nursing["nurses_per_shift_min_total"], label="Minimum modeled", color="#176B87")
    axes[1, 0].plot(monthly_nursing.index, monthly_nursing["nurses_per_shift_max_total"], label="Maximum modeled", color="#D1495B")
    axes[1, 0].set_title("Nurse requirements")
    axes[1, 0].set_ylabel("Nurses per shift")
    axes[1, 0].legend()
    for unit, minimum_column, maximum_column in [
        ("ICU", "nurses_per_shift_min_icu", "nurses_per_shift_max_icu"),
        ("Med-surg", "nurses_per_shift_min_med_surg", "nurses_per_shift_max_med_surg"),
        ("Labor & delivery", "nurses_per_shift_min_labor_delivery", "nurses_per_shift_max_labor_delivery"),
        ("Pediatric", "nurses_per_shift_min_pediatric", "nurses_per_shift_max_pediatric"),
    ]:
        axes[1, 1].plot(monthly_nursing.index, monthly_nursing[minimum_column], label=f"{unit} minimum")
        axes[1, 1].plot(monthly_nursing.index, monthly_nursing[maximum_column], linestyle="--", label=f"{unit} maximum")
    axes[1, 1].set_title("Nurse requirements by unit")
    axes[1, 1].set_ylabel("Nurses per shift")
    axes[1, 1].legend(ncol=2, fontsize=7)

    axes[2, 0].plot(monthly_view.index, monthly_view["occupied_clean_hours"], label="Occupied-room cleaning")
    axes[2, 0].plot(monthly_view.index, monthly_view["discharge_clean_hours"], label="Discharge cleaning")
    axes[2, 0].plot(monthly_view.index, monthly_view["mean_evs_hours"], label="Total estimated EVS workload", linewidth=2)
    axes[2, 0].set_title("Estimated EVS cleaning workload")
    axes[2, 0].set_ylabel("Mean hours per day")
    axes[2, 0].legend(fontsize=8)

    selected_appointments = appointments.loc[
        appointments["date"].isin(selected_data["date"])
    ]
    average_arrivals_by_hour = (
        selected_appointments.groupby("arrival_hour").size().reindex(range(24), fill_value=0)
        / selected_data["date"].nunique()
    )
    axes[2, 1].bar(range(24), average_arrivals_by_hour, color="#E07A5F")
    axes[2, 1].set_title(f"Synthetic appointments by hour ({period_key})")
    axes[2, 1].set_xlabel("Hour of day")
    axes[2, 1].set_ylabel("Mean arrivals per day")
    figure.suptitle("Hospital Current State | Historical Operational View", fontsize=15)
    figure.tight_layout()
    figure.savefig(
        output_dir / f"hospital_current_state_{period_key}.png",
        dpi=160,
        bbox_inches="tight",
    )
    figure
    return (figure,)


if __name__ == "__main__":
    app.run()