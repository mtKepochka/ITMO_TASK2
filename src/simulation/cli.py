from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .model import Simulation
from .reporting import (
    format_table,
    plot_queue_series,
    plot_scenario_comparison,
    write_reports,
    write_time_series,
)
from .scenarios import SCENARIOS, get_scenario

DEFAULT_ARTIFACT_DIR = Path("artifacts") / "simulation"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discrete-event model of ticket queues"
    )
    subparsers = parser.add_subparsers(dest="scenario", required=True)
    for name in (*SCENARIOS, "compare"):
        command = subparsers.add_parser(name)
        command.add_argument("--seed", type=int, default=42)
        command.add_argument("--output", type=Path)
        command.add_argument("--timeseries", type=Path)
        command.add_argument(
            "--plots",
            type=Path,
            help="directory for one scenario-specific PNG",
        )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    names = list(SCENARIOS) if args.scenario == "compare" else [args.scenario]
    reports: list[dict[str, object]] = []
    series: dict[str, list[dict[str, object]]] = {}

    for name in names:
        simulation = Simulation(get_scenario(name), seed=args.seed)
        reports.append(simulation.run())
        series[name] = simulation.queue_series

    print(format_table(reports))
    output = args.output or DEFAULT_ARTIFACT_DIR / f"{args.scenario}.json"
    write_reports(output, reports)
    print(f"report: {output}")

    if args.timeseries:
        write_time_series(args.timeseries, series)
        print(f"time series: {args.timeseries}")

    if args.plots:
        if args.scenario == "compare":
            plot_path = args.plots / "scenario-comparison.png"
            plot_scenario_comparison(plot_path, reports)
        else:
            plot_path = args.plots / f"{args.scenario}-queues.png"
            plot_queue_series(plot_path, args.scenario, series[args.scenario])
        print(f"plot: {plot_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
