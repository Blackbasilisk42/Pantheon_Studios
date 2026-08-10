from __future__ import annotations

from modules.heavy_crawler import build_worker_plan, run_parallel_scan


def test_build_worker_plan_uses_cpu_bound_defaults() -> None:
    plan = build_worker_plan(targets=["https://example.com", "https://example.org"], max_workers=6)
    assert plan["max_workers"] == 6
    assert plan["target_count"] == 2


def test_run_parallel_scan_returns_results_for_targets() -> None:
    results = run_parallel_scan(targets=["https://example.com"], max_workers=1)
    assert isinstance(results, list)
    assert results[0]["target"] == "https://example.com"
