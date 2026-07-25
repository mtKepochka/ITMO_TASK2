import json
from dataclasses import replace
from pathlib import Path

from simulation.cli import main
from simulation.config import (
    CategoryProbabilities,
    ProviderConfig,
    SimulationConfig,
)
from simulation.model import Simulation
from simulation.scenarios import burst, incident_mode, llm_degradation


def test_degraded_provider_does_not_reduce_rejections_or_fallbacks() -> None:
    degraded_config = llm_degradation()
    healthy_config = replace(
        degraded_config,
        name="healthy-control",
        provider=ProviderConfig(),
    )

    healthy = Simulation(healthy_config, seed=42).run()
    degraded = Simulation(degraded_config, seed=42).run()

    assert degraded["arrived"] == healthy["arrived"]
    assert degraded["automation_rejections"] >= healthy[
        "automation_rejections"
    ]
    assert degraded["fallback_completed"] >= healthy["fallback_completed"]


def test_incident_mode_reduces_llm_load_for_same_burst() -> None:
    regular = Simulation(burst(), seed=42).run()
    incident = Simulation(incident_mode(), seed=42).run()

    assert incident["arrived"] == regular["arrived"]
    assert incident["llm_requests"] < regular["llm_requests"]
    for category in ("payment_issue", "refund_request", "account_security"):
        assert incident["outcomes_by_category"].get(category, {}).get(
            "auto_reply", 0
        ) == 0


def test_burst_reports_queue_peaks_and_recovery() -> None:
    report = Simulation(burst(), seed=7).run()

    assert report["nodes"]["llm"]["max_queue_length"] > 0
    assert report["recovery_time_seconds"] is not None


def test_full_generation_queue_uses_fallback_without_system_loss() -> None:
    config = replace(
        llm_degradation(),
        name="llm-overflow",
        arrival_duration=20.0,
        drain_duration=80.0,
        baseline_rate=20.0,
        category_mix={"service_outage": 1.0},
        probabilities={
            "service_outage": CategoryProbabilities(
                pii=0.0,
                high_risk=0.0,
                low_confidence=0.0,
                retrieval_hit=1.0,
                validation_reject=0.0,
                operator_required=0.0,
            )
        },
        provider=ProviderConfig(
            healthy_error_probability=0.0,
            circuit_failure_threshold=100_000,
        ),
    ).with_service(
        "llm",
        capacity=1,
        mean_seconds=10.0,
        queue_capacity=0,
        timeout_seconds=None,
    )

    report = Simulation(config, seed=5).run()

    assert report["rejection_reasons"]["llm_queue_full"] > 0
    assert report["fallback_completed"] > 0
    assert report["lost"] == 0


def outage_only_config(
    *,
    pii: float = 0.0,
    high_risk: float = 0.0,
    low_confidence: float = 0.0,
    operator_required: float = 0.0,
    incident_template: bool = False,
) -> SimulationConfig:
    config = SimulationConfig(
        name="outage-only",
        arrival_duration=10.0,
        drain_duration=40.0,
        baseline_rate=2.0,
        category_mix={"service_outage": 1.0},
        probabilities={
            "service_outage": CategoryProbabilities(
                pii=pii,
                high_risk=high_risk,
                low_confidence=low_confidence,
                retrieval_hit=1.0,
                validation_reject=0.0,
                operator_required=operator_required,
            )
        },
        burst_interval=(0.0, 10.0) if incident_template else None,
        incident_template=incident_template,
    )
    return config.with_service(
        "operator",
        capacity=4,
        mean_seconds=0.01,
        queue_capacity=100,
    )


def test_safety_rejected_outage_goes_to_operator_not_fallback() -> None:
    for reason, config in (
        ("pii", outage_only_config(pii=1.0)),
        ("high_risk", outage_only_config(high_risk=1.0)),
        ("low_confidence", outage_only_config(low_confidence=1.0)),
    ):
        report = Simulation(config, seed=42).run()
        outcomes = report["outcomes_by_category"]["service_outage"]

        assert outcomes.get("operator", 0) == report["arrived"]
        assert outcomes.get("fallback", 0) == 0
        assert report["rejection_reasons"][reason] == report["arrived"]


def test_operator_required_precedes_incident_template() -> None:
    report = Simulation(
        outage_only_config(
            operator_required=1.0,
            incident_template=True,
        ),
        seed=42,
    ).run()
    outcomes = report["outcomes_by_category"]["service_outage"]

    assert outcomes.get("operator", 0) == report["arrived"]
    assert outcomes.get("fallback", 0) == 0
    assert report["rejection_reasons"]["operator_required"] == report["arrived"]


def test_cli_writes_deterministic_json(tmp_path: Path, capsys) -> None:
    output = tmp_path / "baseline.json"

    assert main(["baseline", "--seed", "42", "--output", str(output)]) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["scenario"] == "baseline"
    assert report["seed"] == 42
    assert "report:" in capsys.readouterr().out
