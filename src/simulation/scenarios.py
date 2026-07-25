from __future__ import annotations

from dataclasses import replace

from .config import ArrivalPeriod, ProviderConfig, SimulationConfig

BURST_START = 300.0
BURST_END = 900.0
BURST_RATE = 20_000 / (BURST_END - BURST_START)

BURST_MIX = {
    "service_outage": 0.72,
    "access_issue": 0.08,
    "payment_issue": 0.06,
    "refund_request": 0.03,
    "account_security": 0.02,
    "general_question": 0.07,
    "unknown": 0.02,
}


def baseline() -> SimulationConfig:
    return SimulationConfig()


def burst() -> SimulationConfig:
    return SimulationConfig(
        name="burst",
        arrival_duration=1_800.0,
        drain_duration=3_600.0,
        arrival_periods=(
            ArrivalPeriod(
                BURST_START,
                BURST_END,
                BURST_RATE,
                BURST_MIX,
            ),
        ),
        burst_interval=(BURST_START, BURST_END),
    )


def llm_degradation() -> SimulationConfig:
    return SimulationConfig(
        name="llm-degradation",
        arrival_duration=1_800.0,
        drain_duration=1_800.0,
        provider=ProviderConfig(
            degraded_intervals=((300.0, 1_200.0),),
            degraded_latency_multiplier=5.0,
            healthy_error_probability=0.01,
            degraded_error_probability=0.40,
            circuit_failure_threshold=3,
            circuit_open_seconds=60.0,
        ),
    )


def incident_mode() -> SimulationConfig:
    return replace(
        burst(),
        name="incident-mode",
        incident_template=True,
    )


SCENARIOS = {
    "baseline": baseline,
    "burst": burst,
    "llm-degradation": llm_degradation,
    "incident-mode": incident_mode,
}


def get_scenario(name: str) -> SimulationConfig:
    try:
        return SCENARIOS[name]()
    except KeyError as error:
        raise ValueError(f"unknown simulation scenario: {name}") from error
