from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .audit import JsonlAudit
from .generator import create_generator
from .ml_classifier import TfidfIntentClassifier
from .models import Ticket
from .pipeline import DEFAULT_KB_PATH, PROJECT_ROOT, TicketPipeline
from .retrieval import (
    DEFAULT_E5_MODEL,
    DEFAULT_E5_REVISION,
    create_retriever,
)

DEMO_PATH = Path(
    os.getenv(
        "TICKET_DEMO_PATH",
        PROJECT_ROOT / "data" / "demo_tickets.json",
    )
)


def _load_tickets(path: Path) -> list[Ticket]:
    with path.open(encoding="utf-8") as source:
        values = json.load(source)
    if isinstance(values, dict):
        values = [values]
    if not isinstance(values, list):
        raise ValueError("ticket file must contain an object or a list")
    tickets = []
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            raise ValueError(f"ticket at index {index} must be an object")
        try:
            tickets.append(Ticket.from_dict(value))
        except KeyError as error:
            raise ValueError(
                f"ticket at index {index} is missing field {error.args[0]}"
            ) from error
    if not tickets:
        raise ValueError("ticket file must contain at least one ticket")
    return tickets


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
    parser.add_argument(
        "--rollout-config",
        type=Path,
        help="versioned rollout JSON; defaults to TICKET_ROLLOUT_CONFIG",
    )
    parser.add_argument(
        "--retriever",
        choices=("lexical", "e5"),
        help="knowledge retriever; defaults to TICKET_RETRIEVER or lexical",
    )
    parser.add_argument(
        "--embedding-model",
        help="semantic model name; defaults to the pinned E5 model",
    )
    parser.add_argument(
        "--embedding-revision",
        help="semantic model revision; defaults to a pinned commit",
    )
    parser.add_argument(
        "--embedding-cache",
        type=Path,
        help="model and KB embedding cache directory",
    )
    parser.add_argument(
        "--semantic-offline",
        action="store_true",
        help="load the semantic model only from the local cache",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safe ticket automation PoC")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
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
    if classifier_name not in {"rules", "ml"}:
        parser.error(
            "TICKET_CLASSIFIER must be one of: rules, ml"
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

    retriever_name = args.retriever or os.getenv(
        "TICKET_RETRIEVER", "lexical"
    )
    if retriever_name not in {"lexical", "e5"}:
        parser.error("TICKET_RETRIEVER must be one of: lexical, e5")
    embedding_model = (
        args.embedding_model
        or os.getenv("TICKET_EMBEDDING_MODEL")
        or DEFAULT_E5_MODEL
    )
    embedding_revision = (
        args.embedding_revision
        or os.getenv("TICKET_EMBEDDING_REVISION")
        or DEFAULT_E5_REVISION
    )
    embedding_cache = args.embedding_cache or Path(
        os.getenv(
            "TICKET_EMBEDDING_CACHE",
            PROJECT_ROOT / "artifacts" / "embeddings",
        )
    )
    offline = args.semantic_offline or os.getenv(
        "TICKET_EMBEDDING_OFFLINE", ""
    ).lower() in {"1", "true", "yes"}
    try:
        retriever, retriever_warning = create_retriever(
            retriever_name,
            knowledge_base_path=DEFAULT_KB_PATH,
            cache_directory=embedding_cache,
            model_name=embedding_model,
            revision=embedding_revision,
            local_files_only=offline,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    if retriever_warning:
        print(retriever_warning, file=sys.stderr)
    try:
        pipeline = TicketPipeline(
            generator=generator,
            audit=audit,
            classifier=classifier,
            retriever=retriever,
            rollout_path=args.rollout_config,
        )
    except ValueError as error:
        parser.error(str(error))

    if args.command == "demo":
        source_path = DEMO_PATH
    elif args.file:
        source_path = args.file
    else:
        if not args.text.strip():
            parser.error("--text must not be empty")
        tickets = [
            Ticket(
                id="cli-ticket",
                channel="cli",
                subject="",
                text=args.text,
                created_at=datetime.now(UTC).isoformat(),
            )
        ]
        source_path = None

    if source_path is not None:
        try:
            tickets = _load_tickets(source_path)
        except (OSError, json.JSONDecodeError, ValueError) as error:
            parser.error(f"cannot load tickets from {source_path}: {error}")

    try:
        for ticket in tickets:
            _print_result(ticket.id, pipeline.process(ticket))
    finally:
        pipeline.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
