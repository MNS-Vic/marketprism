"""
轻量级指标聚合器（用于多进程/多管理器场景的简单指标汇总与Prometheus文本生成）
- MetricsCollector: 子组件本地收集器，简单kv存储 + 自增
- MetricsAggregator: 聚合所有子组件指标，支持求和/求平均，并导出Prom文本
注意：生产环境主流程已使用 collector.metrics 中的 Prometheus Collector；本文件主要用于单元测试与备选方案。
"""
from __future__ import annotations
import asyncio
import time
from typing import Dict, Any, Optional


class MetricNames:
    CPU_PERCENT = "marketprism_process_cpu_percent"
    MEMORY_MB = "marketprism_process_memory_mb"
    DATA_COUNT_TOTAL = "marketprism_data_count_total"
    ERROR_COUNT_TOTAL = "marketprism_error_count_total"
    PROCESS_UPTIME_SECONDS = "marketprism_process_uptime_seconds"


class MetricsCollector:
    def __init__(self, exchange: str):
        self.exchange = exchange
        self.metrics: Dict[str, float] = {}

    def set_metric(self, name: str, value: float) -> None:
        self.metrics[name] = float(value)

    def increment_metric(self, name: str, value: float = 1.0) -> None:
        self.metrics[name] = float(self.metrics.get(name, 0.0) + value)

    def get_metric(self, name: str) -> Optional[float]:
        return self.metrics.get(name)

    def get_all_metrics(self) -> Dict[str, float]:
        return dict(self.metrics)

    def clear_metrics(self) -> None:
        self.metrics.clear()

    def to_dict(self) -> Dict[str, float]:
        return dict(self.metrics)


class MetricsAggregator:
    def __init__(self, metric_ttl: float = 60.0):
        self.process_metrics: Dict[str, Dict[str, float]] = {}
        self._process_ts: Dict[str, float] = {}
        self.aggregated_metrics: Dict[str, float] = {}
        self.metric_ttl = metric_ttl

    def update_process_metrics(self, exchange: str, metrics: Dict[str, Any]) -> None:
        self.process_metrics[exchange] = {k: float(v) for k, v in (metrics or {}).items()}
        self._process_ts[exchange] = time.time()
        self._aggregate_metrics()

    def get_process_metrics(self, exchange: str) -> Optional[Dict[str, float]]:
        return self.process_metrics.get(exchange)

    def get_all_process_metrics(self) -> Dict[str, Dict[str, float]]:
        return dict(self.process_metrics)

    def clear_process_metrics(self, exchange: str) -> None:
        self.process_metrics.pop(exchange, None)
        self._process_ts.pop(exchange, None)
        self._aggregate_metrics()

    def clear_all_metrics(self) -> None:
        self.process_metrics.clear()
        self._process_ts.clear()
        self.aggregated_metrics.clear()

    def _aggregate_metrics(self) -> None:
        # 过期清理
        now = time.time()
        expired = [ex for ex, ts in self._process_ts.items() if now - ts > self.metric_ttl]
        for ex in expired:
            self.process_metrics.pop(ex, None)
            self._process_ts.pop(ex, None)

        if not self.process_metrics:
            self.aggregated_metrics = {}
            return

        # 规则：
        # - 以 "*_total" 结尾的指标做求和
        # - CPU/MEM/UPTIME 做平均（同时支持裸名与带前缀名）
        avg_keys = {
            "cpu_percent",
            "memory_mb",
            "process_uptime_seconds",
            MetricNames.CPU_PERCENT,
            MetricNames.MEMORY_MB,
            MetricNames.PROCESS_UPTIME_SECONDS,
        }

        sums: Dict[str, float] = {}
        counts: Dict[str, int] = {}
        avgs: Dict[str, float] = {}

        for ex, m in self.process_metrics.items():
            for k, v in m.items():
                if k.endswith("_total"):
                    sums[k] = sums.get(k, 0.0) + float(v)
                elif k in avg_keys:
                    avgs[k] = avgs.get(k, 0.0) + float(v)
                    counts[k] = counts.get(k, 0) + 1
                else:
                    # 默认策略：未知指标按求和处理
                    sums[k] = sums.get(k, 0.0) + float(v)

        aggregated: Dict[str, float] = {}
        aggregated.update(sums)
        for k, total in avgs.items():
            aggregated[k] = total / max(1, counts.get(k, 1))

        self.aggregated_metrics = aggregated

    def get_aggregated_metrics(self) -> Dict[str, float]:
        self._aggregate_metrics()
        return dict(self.aggregated_metrics)

    async def cleanup_expired_metrics(self, interval: float = 5.0) -> None:
        try:
            while True:
                await asyncio.sleep(interval)
                self._aggregate_metrics()
        except asyncio.CancelledError:
            return

    def generate_prometheus_metrics(self) -> str:
        # 先刷新聚合
        self._aggregate_metrics()
        lines = []
        # 聚合指标（无标签）
        for k, v in sorted(self.aggregated_metrics.items()):
            lines.append(f"{k} {float(v)}")
        # 按进程维度
        for ex, metrics in sorted(self.process_metrics.items()):
            for k, v in sorted(metrics.items()):
                lines.append(f"{k}{'{'}process=\"{ex}\"{'}'} {float(v)}")
        return "\n".join(lines) + "\n"
