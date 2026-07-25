from ticket_automation.benchmark import run_benchmark


def test_fault_benchmark_finishes_without_unsafe_auto_reply() -> None:
    report = run_benchmark(
        ticket_count=20,
        concurrency=4,
        failure_every=5,
    )

    assert report["completed"] == 20
    assert report["exceptions"] == 0
    assert report["technical_fallbacks"] == 4
    assert report["unsafe_auto_replies"] == 0
    assert report["throughput_tickets_per_second"] > 0
