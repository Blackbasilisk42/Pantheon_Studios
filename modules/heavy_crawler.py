#!/usr/bin/env python3
"""Aggressive multi-threaded and multi-process crawling helpers for Pantheon Studios."""

from __future__ import annotations

import asyncio
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None


def build_worker_plan(targets: list[str], max_workers: int | None = None) -> dict[str, Any]:
    cpu_count = max(1, os.cpu_count() or 4)
    if max_workers is not None and max_workers > 0:
        worker_count = max(1, max_workers)
    else:
        requested = max(2, min(cpu_count * 2, max(1, len(targets)) or 1))
        worker_count = max(1, min(requested, max(1, len(targets)) or 1, cpu_count * 2))
    return {
        "target_count": len(targets),
        "cpu_count": cpu_count,
        "max_workers": worker_count,
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }


def _prepare_target(target: str) -> dict[str, Any]:
    cleaned = (target or "").strip()
    return {
        "target": cleaned,
        "scheme": cleaned.split(":", 1)[0] if "://" in cleaned else "http",
        "keyword_score": len(re.findall(r"\b(bridge|city|river|archive|lantern|keeper|eclipse|faction|memory)\b", cleaned.lower())),
    }


async def _fetch_targets_async(targets: list[dict[str, Any]], worker_count: int) -> list[dict[str, Any]]:
    if not targets:
        return []

    async def _fetch_one(target: dict[str, Any]) -> dict[str, Any]:
        if httpx is None:
            return {
                "target": target["target"],
                "status": "offline",
                "status_code": 0,
                "worker_count": worker_count,
                "snippet": "httpx unavailable; queued for offline inspection",
            }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(target["target"], follow_redirects=True)
                sample = response.text[:220].replace("\n", " ")
                return {
                    "target": target["target"],
                    "status": "ok",
                    "status_code": response.status_code,
                    "worker_count": worker_count,
                    "snippet": sample,
                }
        except Exception as exc:  # noqa: BLE001
            return {
                "target": target["target"],
                "status": "error",
                "status_code": 0,
                "worker_count": worker_count,
                "snippet": f"{exc}",
            }

    results = await asyncio.gather(*(_fetch_one(entry) for entry in targets))
    return list(results)


def run_parallel_scan(targets: list[str], max_workers: int | None = None) -> list[dict[str, Any]]:
    plan = build_worker_plan(targets, max_workers=max_workers)
    prepared = []
    with ProcessPoolExecutor(max_workers=plan["max_workers"]) as executor:
        prepared = list(executor.map(_prepare_target, targets))

    return asyncio.run(_fetch_targets_async(prepared, plan["max_workers"]))
