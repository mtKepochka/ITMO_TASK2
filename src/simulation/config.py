from __future__ import annotations

from dataclasses import dataclass, field, replace

from ticket_automation.models import Category

CATEGORIES: tuple[Category, ...] = (
    "service_outage",
    "access_issue",
    "payment_issue",
    "refund_request",
    "account_security",
    "general_question",
    "unknown",
)


@dataclass(frozen=True)
class CategoryProbabilities:
    pii: float
    high_risk: float
    low_confidence: float
    retrieval_hit: float
    validation_reject: float
    operator_required: float


@dataclass(frozen=True)
class ServiceConfig:
    capacity: int
    mean_seconds: float
    lognormal_sigma: float
    queue_capacity: int | None = None
    timeout_seconds: float | None = None


@dataclass(frozen=True)
class ArrivalPeriod:
    start: float
    end: float
    rate_per_second: float
    category_mix: dict[Category, float] | None = None


@dataclass(frozen=True)
class ProviderConfig:
    degraded_intervals: tuple[tuple[float, float], ...] = ()
    degraded_latency_multiplier: float = 4.0
    healthy_error_probability: float = 0.01
    degraded_error_probability: float = 0.30
    circuit_failure_threshold: int = 4
    circuit_open_seconds: float = 45.0


def _default_mix() -> dict[Category, float]:
    return {
        "service_outage": 0.12,
        "access_issue": 0.24,
        "payment_issue": 0.16,
        "refund_request": 0.08,
        "account_security": 0.06,
        "general_question": 0.28,
        "unknown": 0.06,
    }


def _default_probabilities() -> dict[Category, CategoryProbabilities]:
    return {
        "service_outage": CategoryProbabilities(0.01, 0.01, 0.04, 0.94, 0.01, 0.02),
        "access_issue": CategoryProbabilities(0.12, 0.05, 0.12, 0.82, 0.03, 0.30),
        "payment_issue": CategoryProbabilities(0.48, 0.52, 0.08, 0.80, 0.04, 1.00),
        "refund_request": CategoryProbabilities(0.38, 0.45, 0.10, 0.78, 0.05, 1.00),
        "account_security": CategoryProbabilities(0.20, 0.78, 0.10, 0.76, 0.05, 1.00),
        "general_question": CategoryProbabilities(0.05, 0.01, 0.10, 0.86, 0.03, 0.55),
        "unknown": CategoryProbabilities(0.08, 0.08, 0.68, 0.35, 0.08, 0.90),
    }


def _default_services() -> dict[str, ServiceConfig]:
    return {
        "input": ServiceConfig(16, 0.005, 0.25, queue_capacity=5_000),
        "risk_scan": ServiceConfig(8, 0.025, 0.30, queue_capacity=2_000),
        "classifier": ServiceConfig(8, 0.040, 0.30, queue_capacity=2_000),
        "retrieval": ServiceConfig(16, 0.200, 0.45, queue_capacity=2_000),
        "llm": ServiceConfig(
            24,
            1.800,
            0.65,
            queue_capacity=2_000,
            timeout_seconds=8.0,
        ),
        "validator": ServiceConfig(8, 0.035, 0.30, queue_capacity=1_000),
        "operator": ServiceConfig(
            1_100,
            480.0,
            0.55,
            queue_capacity=25_000,
        ),
        "fallback": ServiceConfig(8, 0.010, 0.20, queue_capacity=1_000),
    }


@dataclass(frozen=True)
class SimulationConfig:
    name: str = "baseline"
    arrival_duration: float = 3_600.0
    drain_duration: float = 1_800.0
    baseline_rate: float = 200_000 / 86_400
    arrival_periods: tuple[ArrivalPeriod, ...] = ()
    category_mix: dict[Category, float] = field(default_factory=_default_mix)
    probabilities: dict[Category, CategoryProbabilities] = field(
        default_factory=_default_probabilities
    )
    services: dict[str, ServiceConfig] = field(default_factory=_default_services)
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    sla_seconds: float = 900.0
    monitor_interval: float = 10.0
    burst_interval: tuple[float, float] | None = None
    incident_template: bool = False

    @property
    def observation_duration(self) -> float:
        return self.arrival_duration + self.drain_duration

    def with_service(self, name: str, **changes: object) -> SimulationConfig:
        services = dict(self.services)
        services[name] = replace(services[name], **changes)
        return replace(self, services=services)
