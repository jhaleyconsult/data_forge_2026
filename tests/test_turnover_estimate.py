from src.turnover_estimate import estimate_turnover_savings, load_inputs


def test_savings_bounded_and_reproducible() -> None:
    config, discharges, hours = load_inputs()
    a = estimate_turnover_savings(config, discharges, hours, seed=1, n=20_000)
    b = estimate_turnover_savings(config, discharges, hours, seed=1, n=20_000)
    assert a.equals(b)
    assert (a.minutes_saved_mean.between(0, 60)).all()
    assert (a.intervention_wait_min <= a.baseline_wait_min).all()
