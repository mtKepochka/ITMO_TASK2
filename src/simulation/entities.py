from __future__ import annotations

from dataclasses import dataclass

from ticket_automation.models import Category


@dataclass(frozen=True)
class SimTicket:
    id: int
    category: Category
    arrived_at: float
    contains_pii: bool
    high_risk: bool
    low_confidence: bool
    retrieval_hit: bool
    validation_reject: bool
    operator_required: bool


@dataclass(frozen=True)
class ServiceResult:
    accepted: bool
    timed_out: bool = False
    wait_seconds: float = 0.0
    service_seconds: float = 0.0
