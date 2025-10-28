from __future__ import annotations

import aiohttp
import asyncio
import random
from typing import Any, Dict, List


def _normalize_rule(group_name: str, r: Dict[str, Any]) -> Dict[str, Any]:
    labels = r.get("labels", {}) or {}
    annotations = r.get("annotations", {}) or {}
    # Prometheus rules API: /api/v1/rules
    # Alerting rule example keys: name, query(expr), duration, labels, annotations, alerts, health, evaluationTime, lastEvaluation, type
    return {
        "id": r.get("name") or f"{group_name}::{r.get('name','')}",
        "name": r.get("name") or "unknown",
        "description": annotations.get("description") or annotations.get("summary") or "",
        "severity": labels.get("severity") or "unknown",
        "category": labels.get("category") or "system",
        "enabled": True,
        "conditions": [
            {
                "metric_name": "expr",
                "operator": "expression",
                "threshold": None,
                "duration": r.get("duration") or 0,
                "expr": r.get("query") or r.get("expr"),
            }
        ],
        "created_at": None,
        "updated_at": r.get("lastEvaluation"),
    }


async def _get_json_with_retry(
    session: aiohttp.ClientSession,
    url: str,
    max_attempts: int = 3,
    base_delay: float = 0.3,
) -> Any:
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            async with session.get(url) as resp:
                resp.raise_for_status()
                return await resp.json()
        except Exception as e:
            last_exc = e
            if attempt == max_attempts:
                break
            delay = base_delay * (2 ** (attempt - 1)) + random.random() * 0.15
            await asyncio.sleep(delay)
    if last_exc:
        raise last_exc


async def fetch_alert_rules(base_url: str) -> List[Dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/api/v1/rules"
    timeout = aiohttp.ClientTimeout(total=5)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        payload = await _get_json_with_retry(session, url)
        data = payload.get("data", {})
        groups = data.get("groups", [])
        results: List[Dict[str, Any]] = []
        for g in groups:
            group_name = g.get("name") or ""
            for r in g.get("rules", []):
                if r.get("type") == "alerting":
                    results.append(_normalize_rule(group_name, r))
        return results

