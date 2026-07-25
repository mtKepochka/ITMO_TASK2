from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

from .audit import JsonlAudit
from .generator import DeterministicGenerator
from .models import Ticket
from .pipeline import PROJECT_ROOT, TicketPipeline

DEMO_PATH = PROJECT_ROOT / "data" / "demo_tickets.json"


def _load_tickets(path: Path) -> list[Ticket]:
    with path.open(encoding="utf-8") as source:
        values = json.load(source)
    if isinstance(values, dict):
        values = [values]
    return [Ticket.from_dict(value) for value in values]


def _print_result(ticket_id: str, result: object) -> None:
    value = result.to_dict()  # type: ignore[attr-defined]
    value = {"ticket_id": ticket_id, **value}
    print(json.dumps(value, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safe ticket automation PoC")
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="run bundled scenarios")
    demo.add_argument("--simulate-generator-failure", action="store_true")
    demo.add_argument("--audit", type=Path)

    process = subparsers.add_parser("process", help="process tickets")
    source = process.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path)
    source.add_argument("--text")
    process.add_argument("--audit", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    audit = JsonlAudit(args.audit) if args.audit else None
    generator = DeterministicGenerator(
        simulate_failure=getattr(args, "simulate_generator_failure", False)
    )
    pipeline = TicketPipeline(generator=generator, audit=audit)

    if args.command == "demo":
        tickets = _load_tickets(DEMO_PATH)
    elif args.file:
        tickets = _load_tickets(args.file)
    else:
        tickets = [
            Ticket(
                id="cli-ticket",
                channel="cli",
                subject="",
                text=args.text,
                created_at=datetime.now(UTC).isoformat(),
            )
        ]

    for ticket in tickets:
        _print_result(ticket.id, pipeline.process(ticket))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
