from __future__ import annotations

import aiohttp
import asyncio
import random
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


async def _get_json_with_retry(
    session: aiohttp.ClientSession,
    url: str,
    max_attempts: int = 3,
    base_delay: float = 0.3,
) -> Any:
    """轻量重试的 GET JSON（退避+抖动），总等待时间有限，避免脆弱性。"""
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            async with session.get(url) as resp:
                resp.raise_for_status()
                return await resp.json()
        except Exception as e:  # 网络抖动/5xx/超时
            last_exc = e
            if attempt == max_attempts:
                break
            delay = base_delay * (2 ** (attempt - 1)) + random.random() * 0.15
            await asyncio.sleep(delay)
    if last_exc:
        raise last_exc


async def fetch_alerts(
    base_url: str,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    从 Alertmanager 拉取告警并做最小归一化映射。
    优化（P2）：尽量利用 Alertmanager v2 远端过滤以减小返回体积，保持本地过滤兜底，语义不变。
    参考: https://prometheus.io/docs/alerting/latest/api/#get-/api/v2/alerts
    """
    from urllib.parse import urlencode

    # 基础路径
    base = f"{base_url.rstrip('/')}/api/v2/alerts"

    # 构造查询参数：
    # - severity 通过 label 过滤器传递（filter=severity=XXX）
    # - status 仅在为 "active" 时启用 active=true（其他状态仍走本地过滤，避免语义偏差）
    query_params: list[tuple[str, str]] = []
    if severity:
        query_params.append(("filter", f"severity={severity}"))
    if category:
        query_params.append(("filter", f"category={category}"))
    if status and status.lower() == "active":
        query_params.append(("active", "true"))
        # 不显式设置 silenced/inhibited，交由 AM 默认行为处理，避免误筛

    qs = ("?" + urlencode(query_params, doseq=True)) if query_params else ""
    url = base + qs

    timeout = aiohttp.ClientTimeout(total=5)
    # 兜底限制，避免异常大返回
    limit = max(1, min(int(limit or 100), 1000))
    async with aiohttp.ClientSession(timeout=timeout) as session:
        data = await _get_json_with_retry(session, url)
        alerts = [_normalize_alert(x) for x in data]
        # 语义兜底：本地再过滤一次，保证行为与既有一致
        if status:
            alerts = [a for a in alerts if a.get("status") == status]
        if severity:
            alerts = [a for a in alerts if a.get("severity") == severity]
        return alerts[:limit]

