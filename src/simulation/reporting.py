from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

SUMMARY_FIELDS = (
    "scenario",
    "arrived",
    "completed",
    "auto_replied",
    "sent_to_operator",
    "fallback_completed",
    "lost",
    "unfinished",
    "automation_rejection_probability",
    "system_loss_probability",
    "p95_total_seconds",
    "llm_requests",
    "recovery_time_seconds",
    "bottleneck_node",
)


def format_table(reports: Iterable[dict[str, object]]) -> str:
    reports = list(reports)
    headers = (
        "scenario",
        "arrived",
        "done",
        "auto",
        "operator",
        "fallback",
        "lost",
        "unfinished",
        "reject_p",
        "p95_s",
        "llm",
        "recovery_s",
        "bottleneck",
    )
    rows = []
    for report in reports:
        recovery = report["recovery_time_seconds"]
        rows.append(
            (
                report["scenario"],
                report["arrived"],
                report["completed"],
                report["auto_replied"],
                report["sent_to_operator"],
                report["fallback_completed"],
                report["lost"],
                report["unfinished"],
                f"{float(report['automation_rejection_probability']):.3f}",
                f"{float(report['p95_total_seconds']):.1f}",
                report["llm_requests"],
                "-" if recovery is None else f"{float(recovery):.1f}",
                report["bottleneck_node"],
            )
        )

    widths = [
        max(len(str(header)), *(len(str(row[index])) for row in rows))
        for index, header in enumerate(headers)
    ]
    line = "  ".join(
        str(header).ljust(widths[index])
        for index, header in enumerate(headers)
    )
    separator = "  ".join("-" * width for width in widths)
    body = [
        "  ".join(
            str(value).ljust(widths[index])
            for index, value in enumerate(row)
        )
        for row in rows
    ]
    return "\n".join([line, separator, *body])


def write_reports(
    path: Path, reports: list[dict[str, object]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".csv":
        with path.open("w", encoding="utf-8", newline="") as destination:
            writer = csv.DictWriter(destination, fieldnames=SUMMARY_FIELDS)
            writer.writeheader()
            for report in reports:
                writer.writerow({field: report.get(field) for field in SUMMARY_FIELDS})
        return
    payload: object = reports[0] if len(reports) == 1 else reports
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_time_series(
    path: Path,
    series_by_scenario: dict[str, list[dict[str, object]]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            series_by_scenario,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def plot_queue_series(
    path: Path, scenario: str, series: list[dict[str, object]]
) -> None:
    import matplotlib.pyplot as plt

    path.parent.mkdir(parents=True, exist_ok=True)
    times = [float(sample["time_seconds"]) / 60 for sample in series]
    for node in ("input", "retrieval", "llm", "operator"):
        plt.plot(times, [int(sample[node]) for sample in series], label=node)
    plt.xlabel("simulation time, minutes")
    plt.ylabel("queued tickets")
    plt.title(f"Queue lengths: {scenario}")
    plt.legend()
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def plot_scenario_comparison(
    path: Path, reports: list[dict[str, object]]
) -> None:
    import matplotlib.pyplot as plt

    path.parent.mkdir(parents=True, exist_ok=True)
    names = [str(report["scenario"]) for report in reports]
    p95 = [float(report["p95_total_seconds"]) for report in reports]
    rejection = [
        float(report["automation_rejection_probability"]) * 100
        for report in reports
    ]
    figure, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].bar(names, p95)
    axes[0].set_ylabel("p95 total latency, seconds")
    axes[0].tick_params(axis="x", rotation=20)
    axes[1].bar(names, rejection)
    axes[1].set_ylabel("automation rejection, %")
    axes[1].tick_params(axis="x", rotation=20)
    figure.tight_layout()
    figure.savefig(path)
    plt.close(figure)
