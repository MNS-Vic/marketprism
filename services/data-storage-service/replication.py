#!/usr/bin/env python3
"""
MarketPrism 热端 -> 冷端 批量复制后台任务（集成至 storage 服务）
- 表结构热冷一致，按时间窗口批量复制，失败不推进水位
- 默认本地 ClickHouse，支持跨库 INSERT SELECT
- 复制频率与窗口、安全延迟、清理策略从配置读取（replication 节）
"""
from __future__ import annotations
import os
import json
import time
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timezone

try:
    from clickhouse_driver import Client as CHClient  # 优先 TCP 驱动
except Exception:  # pragma: no cover
    CHClient = None

DEFAULT_TABLES = [
    "trades",
    "orderbooks",
    "funding_rates",
    "open_interests",
    "liquidations",
    "lsr_top_positions",
    "lsr_all_accounts",
    "volatility_indices",
]


class HotToColdReplicator:
    def __init__(self, service_config: Dict[str, Any]):
        self.cfg = service_config or {}
        self.rep_cfg = self.cfg.get("replication", {})
        # 启用/频率/窗口/延迟
        self.enabled: bool = bool(self.rep_cfg.get("enabled", True))
        self.interval_seconds: int = int(self.rep_cfg.get("interval_seconds", 60))
        # 统一测试窗口 1 分钟（如未配置）
        self.window_minutes_all: int = int(self.rep_cfg.get("window_minutes_all", 1))
        self.safety_lag_minutes: int = int(self.rep_cfg.get("safety_lag_minutes", 2))
        # 清理策略（复制确认后删除）
        self.cleanup_enabled: bool = bool(self.rep_cfg.get("cleanup_enabled", False))
        self.cleanup_delay_minutes: int = int(self.rep_cfg.get("cleanup_delay_minutes", 60))
        self.cleanup_granularity: str = str(self.rep_cfg.get("cleanup_granularity", "hour"))

        # ClickHouse 连接（本地）
        hot = (self.cfg.get("hot_storage") or {})
        cold = (self.cfg.get("cold_storage") or {})
        self.ch_host = hot.get("clickhouse_host", "localhost")
        self.ch_port = int(hot.get("clickhouse_tcp_port", 9000))
        self.ch_user = hot.get("clickhouse_user", "default")
        self.ch_pwd = hot.get("clickhouse_password", "")
        # 使用 default 库，SQL 全限定库名
        self._ch: Optional[CHClient] = None

        # 状态文件
        run_dir = os.path.join("services", "data-storage-service", "run")
        os.makedirs(run_dir, exist_ok=True)
        self.state_path = os.path.join(run_dir, "sync_state.json")

        # 运行状态
        self._stop = False
        self.last_run_ts: Optional[float] = None
        self.success_windows = 0
        self.failed_windows = 0
        self.table_lag_minutes: Dict[str, int] = {t: -1 for t in DEFAULT_TABLES}

    # ---------- 公共接口 ----------
    async def run_loop(self):
        if not self.enabled:
            return
        while not self._stop:
            try:
                await self.run_once()
            except Exception as e:  # pragma: no cover
                print(f"[replicator] 运行异常: {e}")
            await asyncio.sleep(self.interval_seconds)

    async def stop(self):
        self._stop = True
        try:
            if self._ch:
                self._ch.disconnect()
        except Exception:
            pass

    def get_status(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "interval_seconds": self.interval_seconds,
            "last_run_utc": datetime.fromtimestamp(self.last_run_ts, tz=timezone.utc).isoformat() if self.last_run_ts else None,
            "success_windows": self.success_windows,
            "failed_windows": self.failed_windows,
            "lag_minutes": self.table_lag_minutes,
            "cleanup_enabled": self.cleanup_enabled,
        }

    # ---------- 核心逻辑 ----------
    async def run_once(self):
        now_ms = int(time.time() * 1000)
        safety_end = now_ms - self.safety_lag_minutes * 60 * 1000
        if safety_end <= 0:
            return

        # 逐表推进
        for tbl in DEFAULT_TABLES:
            try:
                await self._replicate_table_window(tbl, safety_end)
            except Exception as e:
                print(f"[replicator] 表 {tbl} 复制失败: {e}")
                self.failed_windows += 1

        # 更新延迟指标
        await self._update_lags()

        # 基于水位的补偿清理：删除 (watermark - delay) 之前的热端数据
        if self.cleanup_enabled:
            try:
                await self._cleanup_by_watermark()
            except Exception as e:
                print(f"[replicator] 清理任务异常: {e}")

        self.last_run_ts = time.time()

    async def _replicate_table_window(self, table: str, safety_end_ms: int):
        # 读取水位
        last_ms = self._get_state_ms(table)
        if last_ms <= 0:
            # 初次：回溯窗口
            last_ms = safety_end_ms - self.window_minutes_all * 60 * 1000
        # 计算窗口
        end_ms = min(last_ms + self.window_minutes_all * 60 * 1000, safety_end_ms)
        if end_ms <= last_ms:
            return  # 无窗口

        start_dt = f"toDateTime64({last_ms}/1000.0, 3, 'UTC')"
        end_dt = f"toDateTime64({end_ms}/1000.0, 3, 'UTC')"

        insert_sql = (
            f"INSERT INTO marketprism_cold.{table} "
            f"SELECT * FROM marketprism_hot.{table} "
            f"WHERE timestamp >= {start_dt} AND timestamp < {end_dt}"
        )
        # 执行插入
        self._exec(insert_sql)

        # 确认计数，一致且冷端>=热端时推进水位
        hot_cnt = self._scalar(
            f"SELECT count() FROM marketprism_hot.{table} WHERE timestamp >= {start_dt} AND timestamp < {end_dt}"
        )
        cold_cnt = self._scalar(
            f"SELECT count() FROM marketprism_cold.{table} WHERE timestamp >= {start_dt} AND timestamp < {end_dt}"
        )
        if cold_cnt >= hot_cnt:
            self._set_state_ms(table, end_ms)
            self.success_windows += 1
            # 可选安全清理
            if self.cleanup_enabled:
                await self._cleanup_hot_after_confirm(table, last_ms, end_ms, hot_cnt)
        else:
            raise RuntimeError(f"冷端计数不足 (hot={hot_cnt}, cold={cold_cnt})，不推进水位")

    async def _cleanup_hot_after_confirm(self, table: str, start_ms: int, end_ms: int, hot_cnt_expected: int):
        # 清理前等待 delay（以分钟为单位），并再次确认计数
        delay_ms = self.cleanup_delay_minutes * 60 * 1000
        if int(time.time() * 1000) < end_ms + delay_ms:
            return
        start_dt = f"toDateTime64({start_ms}/1000.0, 3, 'UTC')"
        end_dt = f"toDateTime64({end_ms}/1000.0, 3, 'UTC')"
        hot_cnt = self._scalar(
            f"SELECT count() FROM marketprism_hot.{table} WHERE timestamp >= {start_dt} AND timestamp < {end_dt}"
        )
        cold_cnt = self._scalar(
            f"SELECT count() FROM marketprism_cold.{table} WHERE timestamp >= {start_dt} AND timestamp < {end_dt}"
        )
        if cold_cnt >= hot_cnt >= hot_cnt_expected:
            # 按窗口删除热端数据（粒度=窗口，建议窗口=1分钟用于测试；生产可按小时/天）
            self._exec(
                f"ALTER TABLE marketprism_hot.{table} DELETE WHERE timestamp >= {start_dt} AND timestamp < {end_dt}"
            )

    async def _cleanup_by_watermark(self):
        """
        基于各表当前水位进行补偿清理：删除 (watermark - delay) 之前的热端数据，
        以避免因处理时刻(now - safety_lag)导致的窗口无法当次清理的问题。
        """
        delay_ms = self.cleanup_delay_minutes * 60 * 1000
        if delay_ms <= 0:
            return
        now_ms = int(time.time() * 1000)
        for table in DEFAULT_TABLES:
            wm = self._get_state_ms(table)
            # 仅当水位存在且已经超过 delay 时才清理
            cutoff = wm - delay_ms
            if wm > 0 and cutoff > 0 and cutoff < now_ms:
                cutoff_dt = f"toDateTime64({cutoff}/1000.0, 3, 'UTC')"
                # 直接删除截止时间之前的所有热端数据（更稳妥，可按 granularity 拆分优化）
                self._exec(
                    f"ALTER TABLE marketprism_hot.{table} DELETE WHERE timestamp < {cutoff_dt}"
                )

    async def _update_lags(self):
        for t in DEFAULT_TABLES:
            hot_max = self._scalar(
                f"SELECT toInt64(max(toUnixTimestamp64Milli(timestamp))) FROM marketprism_hot.{t}"
            ) or 0
            cold_max = self._scalar(
                f"SELECT toInt64(max(toUnixTimestamp64Milli(timestamp))) FROM marketprism_cold.{t}"
            ) or 0
            lag_min = 0
            if hot_max > 0:
                lag_min = (hot_max - cold_max) // 60000 if cold_max > 0 else 999999
                if lag_min < 0:
                    lag_min = 0
            self.table_lag_minutes[t] = int(lag_min)

    # ---------- 状态持久化 ----------
    def _get_state_ms(self, table: str) -> int:
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            v = d.get(table)
            return int(v) if isinstance(v, int) else 0
        except Exception:
            return 0

    def _set_state_ms(self, table: str, ts_ms: int):
        try:
            d = {}
            if os.path.exists(self.state_path):
                with open(self.state_path, "r", encoding="utf-8") as f:
                    d = json.load(f)
        except Exception:
            d = {}
        d[table] = int(ts_ms)
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(d, f)

    # ---------- ClickHouse 执行 ----------
    def _client(self) -> Optional[CHClient]:
        if CHClient is None:
            return None
        if self._ch is None:
            self._ch = CHClient(host=self.ch_host, port=self.ch_port, user=self.ch_user, password=self.ch_pwd, database="default")
        return self._ch

    def _exec(self, sql: str):
        cl = self._client()
        if cl:
            return cl.execute(sql)
        # 退化为命令行
        cmd = f"clickhouse-client --query \"{sql}\""
        rc = os.system(cmd)
        if rc != 0:  # pragma: no cover
            raise RuntimeError(f"clickhouse-client 执行失败: rc={rc}")

    def _scalar(self, sql: str) -> int:
        cl = self._client()
        if cl:
            res = cl.execute(sql)
            if isinstance(res, list) and res:
                v = res[0][0]
                try:
                    return int(v) if v is not None else 0
                except Exception:
                    return 0
            return 0
        # 命令行方式
        try:
            import subprocess
            out = subprocess.check_output(["bash", "-lc", f"clickhouse-client --query \"{sql}\""])
            s = out.decode().strip()
            return int(s) if s else 0
        except Exception:
            return 0

