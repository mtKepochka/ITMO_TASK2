from __future__ import annotations

import argparse
import json
import tempfile
import time
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .audit import JsonlAudit
from .models import Ticket
from .pipeline import TicketPipeline

EXAMPLES = (
    "Приложение не открывается. Это общий сбой?",
    "Не могу войти, забыл пароль",
    "С карты дважды списали оплату",
    "Подскажите, где найти мой тариф",
    "После обновления экран поворачивается неправильно",
)


def percentile(values: list[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(
        len(ordered) - 1,
        max(0, int(len(ordered) * probability + 0.9999) - 1),
    )
    return ordered[index]


def run_benchmark(
    ticket_count: int,
    concurrency: int,
    failure_every: int = 0,
) -> dict[str, Any]:
    if ticket_count <= 0 or concurrency <= 0 or failure_every < 0:
        raise ValueError("ticket_count/concurrency must be positive")
    latencies: list[float] = []
    fast_path: list[float] = []
    actions: Counter[str] = Counter()
    technical_fallbacks = 0
    unsafe_auto_replies = 0
    exceptions = 0
    with tempfile.TemporaryDirectory() as temporary_directory:
        with TicketPipeline(
            audit=JsonlAudit(Path(temporary_directory) / "audit.jsonl"),
            scorer_workers=max(4, concurrency * 2),
        ) as pipeline:

            def process(index: int):
                ticket = Ticket(
                    id=f"benchmark-{index}",
                    channel=("web", "chat", "email", "mobile")[index % 4],
                    subject="",
                    text=EXAMPLES[index % len(EXAMPLES)],
                    created_at="",
                )
                started = time.perf_counter()
                result = pipeline.process(
                    ticket,
                    simulate_component_failure=(
                        "risk"
                        if failure_every and (index + 1) % failure_every == 0
                        else None
                    ),
                )
                return result, (time.perf_counter() - started) * 1_000

            wall_started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = [
                    executor.submit(process, index)
                    for index in range(ticket_count)
                ]
                for future in as_completed(futures):
                    try:
                        result, latency = future.result()
                    except Exception:  # noqa: BLE001 - benchmark counts failures
                        exceptions += 1
                        continue
                    latencies.append(latency)
                    fast_path.append(result.fast_path_ms)
                    actions[result.decision.action] += 1
                    technical_fallbacks += int(bool(result.technical_errors))
                    unsafe_auto_replies += int(
                        result.decision.action == "auto_reply"
                        and (
                            result.risk.risk_level != "low"
                            or result.risk.contains_pii
                        )
                    )
            wall_seconds = time.perf_counter() - wall_started
    completed = len(latencies)
    return {
        "configuration": {
            "tickets": ticket_count,
            "concurrency": concurrency,
            "failure_every": failure_every,
            "measurement": "local in-process PoC benchmark",
        },
        "completed": completed,
        "exceptions": exceptions,
        "wall_seconds": round(wall_seconds, 3),
        "throughput_tickets_per_second": round(
            completed / wall_seconds if wall_seconds else 0.0,
            1,
        ),
        "end_to_end_ms": {
            "p50": round(percentile(latencies, 0.50), 3),
            "p95": round(percentile(latencies, 0.95), 3),
            "p99": round(percentile(latencies, 0.99), 3),
            "max": round(max(latencies, default=0.0), 3),
        },
        "fast_path_ms": {
            "p50": round(percentile(fast_path, 0.50), 3),
            "p95": round(percentile(fast_path, 0.95), 3),
            "p99": round(percentile(fast_path, 0.99), 3),
            "max": round(max(fast_path, default=0.0), 3),
        },
        "actions": dict(sorted(actions.items())),
        "technical_fallbacks": technical_fallbacks,
        "unsafe_auto_replies": unsafe_auto_replies,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Concurrent fault-injection benchmark"
    )
    parser.add_argument("--tickets", type=int, default=1_000)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--failure-every", type=int, default=0)
    args = parser.parse_args(argv)
    print(
        json.dumps(
            run_benchmark(
                args.tickets,
                args.concurrency,
                args.failure_every,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
