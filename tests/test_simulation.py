from dataclasses import replace

from simulation.config import ArrivalPeriod, SimulationConfig
from simulation.metrics import percentile
from simulation.model import Simulation


def small_config(**changes: object) -> SimulationConfig:
    values: dict[str, object] = {
        "name": "test",
        "arrival_duration": 40.0,
        "drain_duration": 80.0,
        "baseline_rate": 3.0,
        "monitor_interval": 2.0,
    }
    values.update(changes)
    return replace(SimulationConfig(), **values)


def test_same_seed_produces_identical_report() -> None:
    config = small_config()

    assert Simulation(config, seed=42).run() == Simulation(config, seed=42).run()


def test_report_preserves_the_selected_seed() -> None:
    config = small_config()

    first = Simulation(config, seed=1).run()
    second = Simulation(config, seed=2).run()

    assert first["seed"] == 1
    assert second["seed"] == 2
    assert first != second


def test_accounting_and_nonnegative_metrics() -> None:
    report = Simulation(small_config(), seed=7).run()

    assert report["arrived"] == (
        report["completed"] + report["lost"] + report["unfinished"]
    )
    assert report["completed"] == (
        report["auto_replied"]
        + report["fallback_completed"]
        + report["sent_to_operator"]
    )
    for key in (
        "arrived",
        "completed",
        "auto_replied",
        "sent_to_operator",
        "fallback_completed",
        "automation_rejections",
        "lost",
        "timed_out",
        "sla_violations",
        "unfinished",
    ):
        assert report[key] >= 0


def test_utilization_is_bounded() -> None:
    report = Simulation(small_config(), seed=9).run()

    for node in report["nodes"].values():
        assert 0.0 <= node["utilization"] <= 1.0


def test_denylisted_categories_never_auto_reply() -> None:
    report = Simulation(small_config(arrival_duration=100.0), seed=19).run()

    for category in ("payment_issue", "refund_request", "account_security"):
        assert report["outcomes_by_category"].get(category, {}).get(
            "auto_reply", 0
        ) == 0


def test_percentile_handles_empty_values() -> None:
    assert percentile([], 0.95) == 0.0
    assert percentile([3.0], 0.95) == 3.0


def test_full_input_queue_is_system_loss_not_operator_escalation() -> None:
    config = small_config(
        baseline_rate=50.0,
        arrival_periods=(ArrivalPeriod(0.0, 10.0, 50.0),),
    ).with_service(
        "input",
        capacity=1,
        mean_seconds=1.0,
        queue_capacity=0,
    )

    report = Simulation(config, seed=11).run()

    assert report["lost"] > 0
    assert report["system_loss_probability"] > 0
    assert report["rejection_reasons"]["input_buffer_full"] == report["lost"]
    assert report["lost"] + report["completed"] + report["unfinished"] == report[
        "arrived"
    ]
