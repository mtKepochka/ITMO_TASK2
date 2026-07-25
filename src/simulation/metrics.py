from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


def percentile(values: Iterable[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


@dataclass
class NodeMetrics:
    waits: list[float] = field(default_factory=list)
    busy_intervals: list[tuple[float, float]] = field(default_factory=list)
    completed: int = 0
    rejected: int = 0
    max_queue_length: int = 0


@dataclass
class SimulationMetrics:
    arrived: int = 0
    completed: int = 0
    auto_replied: int = 0
    sent_to_operator: int = 0
    fallback_completed: int = 0
    automation_rejections: int = 0
    tickets_considered_for_automation: int = 0
    lost: int = 0
    timed_out: int = 0
    sla_violations: int = 0
    llm_requests: int = 0
    llm_failures: int = 0
    circuit_breaker_bypasses: int = 0
    total_times: list[float] = field(default_factory=list)
    terminal_ticket_ids: set[int] = field(default_factory=set)
    rejection_reasons: dict[str, int] = field(default_factory=dict)
    outcomes_by_category: dict[str, dict[str, int]] = field(default_factory=dict)

    def reject_automation(self, reason: str) -> None:
        self.automation_rejections += 1
        self.rejection_reasons[reason] = self.rejection_reasons.get(reason, 0) + 1

    def record_outcome(self, category: str, outcome: str) -> None:
        outcomes = self.outcomes_by_category.setdefault(category, {})
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
