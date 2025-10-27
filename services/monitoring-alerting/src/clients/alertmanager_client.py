from __future__ import annotations

import aiohttp
from typing import Any, Dict, List, Optional


def _normalize_alert(item: Dict[str, Any]) -> Dict[str, Any]:
    labels = item.get("labels", {}) or {}
    annotations = item.get("annotations", {}) or {}
    status = (item.get("status") or {}).get("state") or "active"
    return {
        "id": item.get("fingerprint") or f"{labels.get('alertname','unknown')}::{item.get('startsAt','')}",
        "rule_id": labels.get("rule_id"),
        "name": labels.get("alertname") or annotations.get("summary") or "unknown",
        "severity": labels.get("severity") or annotations.get("severity") or "unknown",
        "status": status,
        "category": labels.get("category") or "system",
        "timestamp": item.get("startsAt") or item.get("updatedAt") or item.get("endsAt"),
        "description": annotations.get("description") or annotations.get("summary") or "",
        "source": labels.get("instance") or labels.get("job") or "",
        "labels": labels,
    }


async def fetch_alerts(
    base_url: str,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    从 Alertmanager 拉取告警并做最小归一化映射。
    文档: https://www.prometheus.io/docs/alerting/latest/clients/
    """
    url = f"{base_url.rstrip('/')}/api/v2/alerts"
    # Alertmanager 支持按 label 匹配; 这里先全量拉取后在本地过滤，保持简单与鲁棒性
    timeout = aiohttp.ClientTimeout(total=5)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.json()
            alerts = [_normalize_alert(x) for x in data]
            if status:
                alerts = [a for a in alerts if a.get("status") == status]
            if severity:
                alerts = [a for a in alerts if a.get("severity") == severity]
            return alerts[:limit]

