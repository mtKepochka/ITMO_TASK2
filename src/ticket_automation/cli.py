from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

from .audit import JsonlAudit
from .generator import create_generator
from .ml_classifier import TfidfIntentClassifier
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


def _add_generator_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--generator",
        choices=("deterministic", "ollama", "openrouter"),
        help="response generator; defaults to TICKET_GENERATOR or deterministic",
    )
    parser.add_argument(
        "--model",
        help="LLM model name; defaults to TICKET_LLM_MODEL",
    )
    parser.add_argument(
        "--llm-base-url",
        help="provider API base URL",
    )
    parser.add_argument(
        "--llm-timeout",
        type=float,
        help="provider timeout in seconds; defaults to TICKET_LLM_TIMEOUT or 15",
    )
    parser.add_argument(
        "--classifier",
        choices=("rules", "ml"),
        help="intent classifier; defaults to TICKET_CLASSIFIER or rules",
    )
    parser.add_argument(
        "--classifier-model",
        type=Path,
        help="trusted local ML artifact path",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safe ticket automation PoC")
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="run bundled scenarios")
    demo.add_argument("--simulate-generator-failure", action="store_true")
    demo.add_argument("--audit", type=Path)
    _add_generator_arguments(demo)

    process = subparsers.add_parser("process", help="process tickets")
    source = process.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path)
    source.add_argument("--text")
    process.add_argument("--audit", type=Path)
    _add_generator_arguments(process)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    audit = JsonlAudit(args.audit) if args.audit else None
    provider = args.generator or os.getenv(
        "TICKET_GENERATOR", "deterministic"
    )
    model = args.model or os.getenv("TICKET_LLM_MODEL")
    timeout_value = (
        args.llm_timeout
        if args.llm_timeout is not None
        else os.getenv("TICKET_LLM_TIMEOUT", "15")
    )
    try:
        timeout_seconds = float(timeout_value)
        if args.llm_base_url:
            base_url = args.llm_base_url
        elif provider == "ollama":
            base_url = os.getenv("OLLAMA_BASE_URL")
        elif provider == "openrouter":
            base_url = os.getenv("OPENROUTER_BASE_URL")
        else:
            base_url = None
        generator = create_generator(
            provider,
            model=model,
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            simulate_failure=getattr(
                args, "simulate_generator_failure", False
            ),
        )
    except ValueError as error:
        parser.error(str(error))

    classifier_name = args.classifier or os.getenv(
        "TICKET_CLASSIFIER", "rules"
    )
    classifier = None
    if classifier_name == "ml":
        model_path = args.classifier_model or Path(
            os.getenv(
                "TICKET_CLASSIFIER_MODEL",
                PROJECT_ROOT
                / "artifacts"
                / "models"
                / "intent-classifier.joblib",
            )
        )
        try:
            classifier = TfidfIntentClassifier.load_trusted(model_path)
        except (FileNotFoundError, ValueError) as error:
            parser.error(f"{error}; run `make train-ml` first")
    pipeline = TicketPipeline(
        generator=generator,
        audit=audit,
        classifier=classifier,
    )

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
