from __future__ import annotations

from pathlib import Path

from app.services.evaluation import run_benchmark_suite


def test_benchmark_suite_meets_quality_floor() -> None:
    metrics = run_benchmark_suite(
        Path(__file__).resolve().parents[1] / "app" / "data" / "benchmark_cases.json"
    )

    assert metrics["precision_at_5"] >= 0.6
    assert metrics["mrr"] >= 0.75
    assert metrics["relevant_result_rate"] == 1.0
    assert metrics["too_senior_rate"] <= 0.2
