from __future__ import annotations

import math
import random
from typing import Generator

import simpy

from ticket_automation.models import Category
from ticket_automation.policy import AUTO_REPLY_CATEGORIES
from ticket_automation.risk import DENYLIST_CATEGORIES

from .config import (
    CATEGORIES,
    ServiceConfig,
    SimulationConfig,
)
from .entities import ServiceResult, SimTicket
from .metrics import NodeMetrics, SimulationMetrics, percentile


class ServiceNode:
    def __init__(
        self,
        env: simpy.Environment,
        config: ServiceConfig,
        rng: random.Random,
    ) -> None:
        self.env = env
        self.config = config
        self.rng = rng
        self.resource = simpy.Resource(env, capacity=config.capacity)
        self.metrics = NodeMetrics()

    def sample_duration(self, multiplier: float = 1.0) -> float:
        sigma = self.config.lognormal_sigma
        mean = self.config.mean_seconds * multiplier
        mu = math.log(mean) - sigma * sigma / 2
        return self.rng.lognormvariate(mu, sigma)

    def serve(
        self, *, duration_multiplier: float = 1.0
    ) -> Generator[simpy.Event, object, ServiceResult]:
        queue_capacity = self.config.queue_capacity
        if (
            queue_capacity is not None
            and self.resource.count >= self.config.capacity
            and len(self.resource.queue) >= queue_capacity
        ):
            self.metrics.rejected += 1
            return ServiceResult(accepted=False)

        queued_at = self.env.now
        with self.resource.request() as request:
            self.metrics.max_queue_length = max(
                self.metrics.max_queue_length,
                len(self.resource.queue),
            )
            yield request
            wait = self.env.now - queued_at
            self.metrics.waits.append(wait)

            sampled = self.sample_duration(duration_multiplier)
            timeout = self.config.timeout_seconds
            timed_out = timeout is not None and sampled > timeout
            service_time = min(sampled, timeout) if timed_out else sampled
            self.metrics.busy_channel_seconds += service_time
            yield self.env.timeout(service_time)
            self.metrics.completed += 1
            return ServiceResult(
                accepted=True,
                timed_out=timed_out,
                wait_seconds=wait,
                service_seconds=service_time,
            )


class CircuitBreaker:
    def __init__(self, threshold: int, open_seconds: float) -> None:
        self.threshold = threshold
        self.open_seconds = open_seconds
        self.consecutive_failures = 0
        self.open_until = 0.0

    def is_open(self, now: float) -> bool:
        return now < self.open_until

    def record(self, *, success: bool, now: float) -> None:
        if success:
            self.consecutive_failures = 0
            return
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.threshold:
            self.open_until = now + self.open_seconds
            self.consecutive_failures = 0


class Simulation:
    def __init__(self, config: SimulationConfig, *, seed: int) -> None:
        self.config = config
        self.seed = seed
        self.rng = random.Random(seed)
        self.env = simpy.Environment()
        self.metrics = SimulationMetrics()
        self.nodes = {
            name: ServiceNode(self.env, node_config, self.rng)
            for name, node_config in config.services.items()
        }
        self.active_tickets: dict[int, SimTicket] = {}
        self.queue_series: list[dict[str, float | int | str]] = []
        provider = config.provider
        self.breaker = CircuitBreaker(
            provider.circuit_failure_threshold,
            provider.circuit_open_seconds,
        )

    def _arrival_settings(
        self, now: float
    ) -> tuple[float, dict[Category, float]]:
        for period in self.config.arrival_periods:
            if period.start <= now < period.end:
                return (
                    period.rate_per_second,
                    period.category_mix or self.config.category_mix,
                )
        return self.config.baseline_rate, self.config.category_mix

    def _choose_category(self, mix: dict[Category, float]) -> Category:
        weights = [mix.get(category, 0.0) for category in CATEGORIES]
        return self.rng.choices(CATEGORIES, weights=weights, k=1)[0]

    def _make_ticket(
        self, ticket_id: int, category: Category, now: float
    ) -> SimTicket:
        probabilities = self.config.probabilities[category]
        return SimTicket(
            id=ticket_id,
            category=category,
            arrived_at=now,
            contains_pii=self.rng.random() < probabilities.pii,
            high_risk=self.rng.random() < probabilities.high_risk,
            low_confidence=self.rng.random() < probabilities.low_confidence,
            retrieval_hit=self.rng.random() < probabilities.retrieval_hit,
            validation_reject=self.rng.random()
            < probabilities.validation_reject,
            operator_required=self.rng.random()
            < probabilities.operator_required,
        )

    def _source(self) -> Generator[simpy.Event, object, None]:
        ticket_id = 0
        while self.env.now < self.config.arrival_duration:
            rate, mix = self._arrival_settings(self.env.now)
            if rate <= 0:
                next_starts = [
                    period.start
                    for period in self.config.arrival_periods
                    if period.start > self.env.now
                ]
                if not next_starts:
                    return
                yield self.env.timeout(min(next_starts) - self.env.now)
                continue
            interarrival = self.rng.expovariate(rate)
            if self.env.now + interarrival >= self.config.arrival_duration:
                return
            yield self.env.timeout(interarrival)
            _, current_mix = self._arrival_settings(self.env.now)
            category = self._choose_category(current_mix)
            ticket = self._make_ticket(ticket_id, category, self.env.now)
            ticket_id += 1
            self.metrics.arrived += 1
            self.active_tickets[ticket.id] = ticket
            self.env.process(self._handle_ticket(ticket))

    def _provider_degraded(self) -> bool:
        return any(
            start <= self.env.now < end
            for start, end in self.config.provider.degraded_intervals
        )

    def _during_incident(self, ticket: SimTicket) -> bool:
        interval = self.config.burst_interval
        return bool(
            self.config.incident_template
            and interval
            and interval[0] <= ticket.arrived_at < interval[1]
            and ticket.category == "service_outage"
        )

    def _finish(self, ticket: SimTicket, outcome: str) -> None:
        if ticket.id in self.metrics.terminal_ticket_ids:
            raise RuntimeError(f"ticket {ticket.id} reached two terminal states")
        total_time = self.env.now - ticket.arrived_at
        self.metrics.terminal_ticket_ids.add(ticket.id)
        self.active_tickets.pop(ticket.id, None)
        self.metrics.completed += 1
        self.metrics.total_times.append(total_time)
        self.metrics.record_outcome(ticket.category, outcome)
        if total_time > self.config.sla_seconds:
            self.metrics.sla_violations += 1
        if outcome == "auto_reply":
            self.metrics.auto_replied += 1
        elif outcome == "fallback":
            self.metrics.fallback_completed += 1
        elif outcome == "operator":
            self.metrics.sent_to_operator += 1
        else:
            raise ValueError(f"unknown terminal outcome: {outcome}")

    def _lose(self, ticket: SimTicket, reason: str) -> None:
        if ticket.id in self.metrics.terminal_ticket_ids:
            raise RuntimeError(f"ticket {ticket.id} reached two terminal states")
        self.metrics.terminal_ticket_ids.add(ticket.id)
        self.active_tickets.pop(ticket.id, None)
        self.metrics.lost += 1
        self.metrics.rejection_reasons[reason] = (
            self.metrics.rejection_reasons.get(reason, 0) + 1
        )

    def _to_operator(
        self, ticket: SimTicket
    ) -> Generator[simpy.Event, object, None]:
        result = yield from self.nodes["operator"].serve()
        if not result.accepted:
            self._lose(ticket, "operator_queue_full")
            return
        self._finish(ticket, "operator")

    def _to_fallback(
        self, ticket: SimTicket
    ) -> Generator[simpy.Event, object, None]:
        result = yield from self.nodes["fallback"].serve()
        if result.accepted:
            self._finish(ticket, "fallback")
        else:
            yield from self._to_operator(ticket)

    def _reject_to_safe_path(
        self, ticket: SimTicket, reason: str
    ) -> Generator[simpy.Event, object, None]:
        self.metrics.reject_automation(reason)
        if ticket.category in AUTO_REPLY_CATEGORIES:
            yield from self._to_fallback(ticket)
        else:
            yield from self._to_operator(ticket)

    def _handle_ticket(
        self, ticket: SimTicket
    ) -> Generator[simpy.Event, object, None]:
        input_result = yield from self.nodes["input"].serve()
        if not input_result.accepted:
            self._lose(ticket, "input_buffer_full")
            return

        risk_result = yield from self.nodes["risk_scan"].serve()
        if not risk_result.accepted:
            yield from self._to_operator(ticket)
            return

        classifier_result = yield from self.nodes["classifier"].serve()
        if not classifier_result.accepted:
            yield from self._to_operator(ticket)
            return

        self.metrics.tickets_considered_for_automation += 1
        if (
            ticket.contains_pii
            or ticket.high_risk
            or ticket.low_confidence
            or ticket.category in DENYLIST_CATEGORIES
        ):
            if ticket.contains_pii:
                reason = "pii"
            elif ticket.high_risk:
                reason = "high_risk"
            elif ticket.low_confidence:
                reason = "low_confidence"
            else:
                reason = "denylist"
            yield from self._reject_to_safe_path(ticket, reason)
            return

        if self._during_incident(ticket):
            yield from self._to_fallback(ticket)
            return

        if ticket.operator_required:
            self.metrics.reject_automation("operator_required")
            yield from self._to_operator(ticket)
            return

        retrieval_result = yield from self.nodes["retrieval"].serve()
        if not retrieval_result.accepted:
            yield from self._reject_to_safe_path(ticket, "retrieval_queue_full")
            return
        if not ticket.retrieval_hit:
            yield from self._reject_to_safe_path(ticket, "retrieval_miss")
            return

        if self.breaker.is_open(self.env.now):
            self.metrics.circuit_breaker_bypasses += 1
            yield from self._reject_to_safe_path(ticket, "circuit_breaker")
            return

        degraded = self._provider_degraded()
        multiplier = (
            self.config.provider.degraded_latency_multiplier if degraded else 1.0
        )
        self.metrics.llm_requests += 1
        llm_result = yield from self.nodes["llm"].serve(
            duration_multiplier=multiplier
        )
        if not llm_result.accepted:
            self.breaker.record(success=False, now=self.env.now)
            self.metrics.llm_failures += 1
            yield from self._reject_to_safe_path(ticket, "llm_queue_full")
            return

        error_probability = (
            self.config.provider.degraded_error_probability
            if degraded
            else self.config.provider.healthy_error_probability
        )
        failed = llm_result.timed_out or self.rng.random() < error_probability
        self.breaker.record(success=not failed, now=self.env.now)
        if failed:
            self.metrics.llm_failures += 1
            if llm_result.timed_out:
                self.metrics.timed_out += 1
                reason = "llm_timeout"
            else:
                reason = "llm_error"
            yield from self._reject_to_safe_path(ticket, reason)
            return

        validation_result = yield from self.nodes["validator"].serve()
        if not validation_result.accepted:
            yield from self._reject_to_safe_path(ticket, "validator_queue_full")
            return
        if ticket.validation_reject:
            yield from self._reject_to_safe_path(ticket, "validation_reject")
            return

        if ticket.category in AUTO_REPLY_CATEGORIES:
            self._finish(ticket, "auto_reply")
        else:
            yield from self._to_operator(ticket)

    def _monitor(self) -> Generator[simpy.Event, object, None]:
        while self.env.now <= self.config.observation_duration:
            sample: dict[str, float | int | str] = {
                "time_seconds": round(self.env.now, 3),
                "provider_state": (
                    "degraded" if self._provider_degraded() else "healthy"
                ),
            }
            for name, node in self.nodes.items():
                sample[name] = len(node.resource.queue)
            self.queue_series.append(sample)
            yield self.env.timeout(self.config.monitor_interval)

    def run(self) -> dict[str, object]:
        self.env.process(self._source())
        self.env.process(self._monitor())
        self.env.run(until=self.config.observation_duration)
        return self.report()

    def _recovery_time(self) -> float | None:
        if not self.config.burst_interval:
            return None
        burst_end = self.config.burst_interval[1]
        key_nodes = ("input", "risk_scan", "classifier", "retrieval", "llm")
        for sample in self.queue_series:
            if float(sample["time_seconds"]) < burst_end:
                continue
            if all(int(sample[name]) <= 5 for name in key_nodes):
                return round(float(sample["time_seconds"]) - burst_end, 3)
        return None

    def report(self) -> dict[str, object]:
        observation = self.config.observation_duration
        unfinished = self.metrics.arrived - self.metrics.completed - self.metrics.lost
        unfinished_sla = sum(
            observation - ticket.arrived_at > self.config.sla_seconds
            for ticket in self.active_tickets.values()
        )
        node_reports: dict[str, dict[str, float | int]] = {}
        for name, node in self.nodes.items():
            utilization = node.metrics.busy_channel_seconds / (
                node.config.capacity * observation
            )
            node_reports[name] = {
                "completed": node.metrics.completed,
                "rejected": node.metrics.rejected,
                "mean_wait_seconds": round(
                    sum(node.metrics.waits) / len(node.metrics.waits)
                    if node.metrics.waits
                    else 0.0,
                    4,
                ),
                "p95_wait_seconds": round(
                    percentile(node.metrics.waits, 0.95), 4
                ),
                "max_queue_length": node.metrics.max_queue_length,
                "utilization": round(min(1.0, utilization), 6),
            }

        arrived = self.metrics.arrived
        completed = self.metrics.completed
        considered = self.metrics.tickets_considered_for_automation
        return {
            "scenario": self.config.name,
            "seed": self.seed,
            "time_unit": "seconds",
            "observation_seconds": observation,
            "arrived": arrived,
            "completed": completed,
            "auto_replied": self.metrics.auto_replied,
            "sent_to_operator": self.metrics.sent_to_operator,
            "fallback_completed": self.metrics.fallback_completed,
            "automation_rejections": self.metrics.automation_rejections,
            "tickets_considered_for_automation": considered,
            "lost": self.metrics.lost,
            "timed_out": self.metrics.timed_out,
            "sla_violations": self.metrics.sla_violations + unfinished_sla,
            "unfinished": unfinished,
            "llm_requests": self.metrics.llm_requests,
            "llm_failures": self.metrics.llm_failures,
            "circuit_breaker_bypasses": self.metrics.circuit_breaker_bypasses,
            "throughput_per_second": round(completed / observation, 6),
            "automation_rate": round(
                (self.metrics.auto_replied + self.metrics.fallback_completed)
                / arrived
                if arrived
                else 0.0,
                6,
            ),
            "escalation_rate": round(
                self.metrics.sent_to_operator / arrived if arrived else 0.0,
                6,
            ),
            "fallback_rate": round(
                self.metrics.fallback_completed / arrived if arrived else 0.0,
                6,
            ),
            "automation_rejection_probability": round(
                self.metrics.automation_rejections / considered
                if considered
                else 0.0,
                6,
            ),
            "system_loss_probability": round(
                self.metrics.lost / arrived if arrived else 0.0,
                6,
            ),
            "mean_total_seconds": round(
                sum(self.metrics.total_times) / len(self.metrics.total_times)
                if self.metrics.total_times
                else 0.0,
                4,
            ),
            "p50_total_seconds": round(
                percentile(self.metrics.total_times, 0.50), 4
            ),
            "p95_total_seconds": round(
                percentile(self.metrics.total_times, 0.95), 4
            ),
            "p99_total_seconds": round(
                percentile(self.metrics.total_times, 0.99), 4
            ),
            "recovery_time_seconds": self._recovery_time(),
            "rejection_reasons": dict(sorted(self.metrics.rejection_reasons.items())),
            "outcomes_by_category": {
                category: dict(sorted(outcomes.items()))
                for category, outcomes in sorted(
                    self.metrics.outcomes_by_category.items()
                )
            },
            "nodes": node_reports,
        }
