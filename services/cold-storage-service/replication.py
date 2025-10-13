#!/usr/bin/env python3
"""
轻量版 Hot->Cold 复制器（仅供冷端容器运行时兜底使用）
- 仅依赖 clickhouse-client CLI，不依赖 clickhouse-driver
- 具备：启停、状态查询、一次性自举(bootstrap) + 按窗口复制
- 与 data-storage-service/replication.HotToColdReplicator 的接口保持一致（子集）

注意：此文件用于规避上游模块导入异常（例如源文件含有不可打印字节导致的 SyntaxError）。
当上游修复后，本文件可移除而不影响主流程。
"""
from __future__ import annotations
import os
import json
import time
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import subprocess

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
        rep = self.cfg.get("replication", {})
        self.enabled: bool = bool(rep.get("enabled", True))
        self.interval_seconds: int = int(rep.get("interval_seconds", 60))
        self.window_minutes_all: int = int(rep.get("window_minutes_all", 1))
        self.safety_lag_minutes: int = int(rep.get("safety_lag_minutes", 2))
        # 分表参数
        self.high = {"trades", "orderbooks"}
        self.safety_lag_minutes_low: int = int(rep.get("safety_lag_minutes_low", 0))
        self.safety_lag_minutes_high: int = int(rep.get("safety_lag_minutes_high", self.safety_lag_minutes))
        self.bootstrap_enabled: bool = bool(rep.get("bootstrap_enabled", True))
        # 支持“全历史回填”开关；为兼容旧配置，默认 False
        self.bootstrap_full_history: bool = bool(rep.get("bootstrap_full_history", False))
        self.bootstrap_minutes_high: int = int(rep.get("bootstrap_minutes_high", 5))
        self.bootstrap_minutes_low: int = int(rep.get("bootstrap_minutes_low", 180))
        self.max_catchup_windows_low: int = int(rep.get("max_catchup_windows_low", 2))
        self.max_catchup_windows_high: int = int(rep.get("max_catchup_windows_high", 5))
        # 复制确认后的热端清理策略（默认关闭，避免误删）
        self.cleanup_enabled: bool = bool(rep.get("cleanup_enabled", False))
        self.cleanup_delay_minutes: int = int(rep.get("cleanup_delay_minutes", 60))

        hot = self.cfg.get("hot_storage", {})
        cold = self.cfg.get("cold_storage", {})
        self.hot_host = str(hot.get("clickhouse_host", "localhost"))
        self.hot_port = int(hot.get("clickhouse_tcp_port", 9000))
        self.hot_user = str(hot.get("clickhouse_user", "default"))
        self.hot_pwd = str(hot.get("clickhouse_password", ""))
        self.cold_host = str(cold.get("clickhouse_host", self.hot_host))
        self.cold_port = int(cold.get("clickhouse_tcp_port", self.hot_port))
        self.cold_user = str(cold.get("clickhouse_user", self.hot_user))
        self.cold_pwd = str(cold.get("clickhouse_password", self.hot_pwd))

        self.cross_instance = any([
            self.hot_host != self.cold_host,
            self.hot_port != self.cold_port,
            self.hot_user != self.cold_user,
            self.hot_pwd != self.cold_pwd,
        ])

        # 状态目录：优先环境变量；否则与 main.py 一致，使用 <module_dir>/run
        run_dir = os.environ.get("MARKETPRISM_COLD_RUN_DIR")
        if not run_dir:
            run_dir = os.path.join(os.path.dirname(__file__), "run")
        os.makedirs(run_dir, exist_ok=True)
        self.state_path = os.path.join(run_dir, "sync_state.json")

        self._stop = False
        self.last_run_ts: Optional[float] = None
        self.success_windows = 0
        self.failed_windows = 0
        self.table_lag_minutes: Dict[str, int] = {t: -1 for t in DEFAULT_TABLES}

    # ----------------- 外部接口 -----------------
    async def run_loop(self):
        if not self.enabled:
            return
        while not self._stop:
            try:
                await self.run_once()
            except Exception as e:
                print(f"[replicator-lite] run_once error: {e}")
            await asyncio.sleep(self.interval_seconds)

    async def stop(self):
        self._stop = True

    def get_status(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "interval_seconds": self.interval_seconds,
            "last_run_utc": datetime.fromtimestamp(self.last_run_ts, tz=timezone.utc).isoformat() if self.last_run_ts else None,
            "success_windows": self.success_windows,
            "failed_windows": self.failed_windows,
            "lag_minutes": self.table_lag_minutes,
            "cleanup_enabled": self.cleanup_enabled,
            "cleanup_delay_minutes": self.cleanup_delay_minutes,
        }

    # ----------------- 主流程 -----------------
    async def run_once(self):
        now_ms = int(time.time() * 1000)
        try:
            await self._bootstrap_if_needed()
        except Exception as e:
            print(f"[replicator-lite] bootstrap skipped: {e}")

        for tbl in DEFAULT_TABLES:
            try:
                lag = self.safety_lag_minutes_high if tbl in self.high else self.safety_lag_minutes_low
                end_ms = now_ms - max(lag, 0) * 60 * 1000
                if end_ms <= 0:
                    continue
                await self._replicate_table_window(tbl, end_ms)
            except Exception as e:
                print(f"[replicator-lite] table {tbl} failed: {e}")
                self.failed_windows += 1

        await self._update_lags()
        # 基于水位的补偿清理（确认冷端已接收且超过延迟）
        if self.cleanup_enabled:
            try:
                await self._cleanup_by_watermark()
            except Exception as e:
                print(f"[replicator-lite] cleanup error: {e}")
        self.last_run_ts = time.time()

    async def _bootstrap_if_needed(self):
        if not self.bootstrap_enabled:
            return
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                d = json.load(f) or {}
                if d.get("_BOOTSTRAP_DONE"):
                    return
        except Exception:
            pass

        def _min_ts_ms(sql_fn_hot, sql_fn_cold, tbl: str) -> tuple[int, int]:
            hot_min = sql_fn_hot(f"SELECT toInt64(min(toUnixTimestamp64Milli(timestamp))) FROM marketprism_hot.{tbl}")
            cold_min = sql_fn_cold(f"SELECT toInt64(min(toUnixTimestamp64Milli(timestamp))) FROM marketprism_cold.{tbl}")
            hot_min = int(hot_min) if hot_min else 0
            cold_min = int(cold_min) if cold_min else 0
            return hot_min, cold_min

        async def _range_insert_windows(table: str, start_ms: int, end_ms: int, max_windows: int):
            if start_ms <= 0 or end_ms <= 0 or start_ms >= end_ms:
                return
            size_ms = self.window_minutes_all * 60 * 1000
            processed = 0
            cur = start_ms
            # max_windows <= 0 =>
            limit = max_windows if isinstance(max_windows, int) and max_windows > 0 else float('inf')
            while cur < end_ms and processed < limit and not self._stop:
                next_ms = min(cur + size_ms, end_ms)
                start_dt = f"toDateTime64({cur}/1000.0, 3, 'UTC')"
                end_dt = f"toDateTime64({next_ms}/1000.0, 3, 'UTC')"
                try:
                    if self.cross_instance:
                        remote_src = f"remote('{self.hot_host}:{self.hot_port}', 'marketprism_hot', '{table}', '{self.hot_user}', '{self.hot_pwd}')"
                        insert_sql = (
                            f"INSERT INTO marketprism_cold.{table} SELECT * FROM {remote_src} "
                            f"WHERE timestamp >= {start_dt} AND timestamp < {end_dt}"
                        )
                        self._exec_cold(insert_sql)
                    else:
                        insert_sql = (
                            f"INSERT INTO marketprism_cold.{table} SELECT * FROM marketprism_hot.{table} "
                            f"WHERE timestamp >= {start_dt} AND timestamp < {end_dt}"
                        )
                        self._exec_cold(insert_sql)
                except Exception as e:
                    print(f"[replicator-lite] backfill window {table} {start_dt}~{end_dt} error: {e}")
                    break
                processed += 1
                cur = next_ms

        now_ms = int(time.time() * 1000)
        # 计算安全尾时间（避免边界正在写入）
        def _safety_end_ms(tbl: str) -> int:
            if tbl in self.high:
                lag = getattr(self, 'safety_lag_minutes_high', getattr(self, 'safety_lag_minutes', 2))
            else:
                lag = getattr(self, 'safety_lag_minutes_low', getattr(self, 'safety_lag_minutes', 2))
            return now_ms - max(int(lag), 0) * 60 * 1000

        for tbl in DEFAULT_TABLES:
            try:
                if self.bootstrap_full_history:
                    # 全历史回填：
                    hot_min, cold_min = _min_ts_ms(self._scalar_hot, self._scalar_cold, tbl)
                    end_ms = _safety_end_ms(tbl)
                    # 冷端无数据：从热端最早时间到安全尾全量回填
                    if self._scalar_cold(f"SELECT count() FROM marketprism_cold.{tbl}") == 0:
                        await _range_insert_windows(tbl, hot_min, end_ms, 0)
                        # 将状态推进到安全尾，避免重复复制最近窗口
                        self._set_state_ms(tbl, end_ms)
                    else:
                        # 冷端已有数据：仅回填更早的缺口 [hot_min, cold_min)
                        if hot_min > 0 and (cold_min == 0 or hot_min < cold_min):
                            await _range_insert_windows(tbl, hot_min, cold_min, 0)
                else:
                    # 旧逻辑：仅回填最近一段（冷端为空时）
                    minutes = self.bootstrap_minutes_high if tbl in self.high else self.bootstrap_minutes_low
                    if self.cross_instance:
                        remote_src = f"remote('{self.hot_host}:{self.hot_port}', 'marketprism_hot', '{tbl}', '{self.hot_user}', '{self.hot_pwd}')"
                        hot_recent = self._scalar_cold(
                            f"SELECT count() FROM {remote_src} WHERE timestamp >= now() - INTERVAL {minutes} MINUTE"
                        )
                        cold_total = self._scalar_cold(f"SELECT count() FROM marketprism_cold.{tbl}")
                        if hot_recent > 0 and cold_total == 0:
                            self._exec_cold(
                                f"INSERT INTO marketprism_cold.{tbl} SELECT * FROM {remote_src} "
                                f"WHERE timestamp >= now() - INTERVAL {minutes} MINUTE"
                            )
                    else:
                        hot_recent = self._scalar_hot(f"SELECT count() FROM marketprism_hot.{tbl} WHERE timestamp >= now() - INTERVAL {minutes} MINUTE")
                        cold_total = self._scalar_cold(f"SELECT count() FROM marketprism_cold.{tbl}")
                        if hot_recent > 0 and cold_total == 0:
                            self._exec_cold(
                                f"INSERT INTO marketprism_cold.{tbl} SELECT * FROM marketprism_hot.{tbl} "
                                f"WHERE timestamp >= now() - INTERVAL {minutes} MINUTE"
                            )
            except Exception as e:
                print(f"[replicator-lite] bootstrap {tbl} error: {e}")

        try:
            d = {}
            if os.path.exists(self.state_path):
                with open(self.state_path, "r", encoding="utf-8") as f:
                    d = json.load(f) or {}
            d["_BOOTSTRAP_DONE"] = True
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(d, f)
        except Exception:
            pass

    async def _replicate_table_window(self, table: str, safety_end_ms: int):
        max_windows = self.max_catchup_windows_high if table in self.high else self.max_catchup_windows_low
        processed = 0
        last_ms = self._get_state_ms(table)
        if last_ms <= 0:
            last_ms = safety_end_ms - self.window_minutes_all * 60 * 1000
        while processed < max_windows:
            end_ms = min(last_ms + self.window_minutes_all * 60 * 1000, safety_end_ms)
            if end_ms <= last_ms:
                break
            start_dt = f"toDateTime64({last_ms}/1000.0, 3, 'UTC')"
            end_dt = f"toDateTime64({end_ms}/1000.0, 3, 'UTC')"
            if self.cross_instance:
                remote_src = f"remote('{self.hot_host}:{self.hot_port}', 'marketprism_hot', '{table}', '{self.hot_user}', '{self.hot_pwd}')"
                insert_sql = (
                    f"INSERT INTO marketprism_cold.{table} "
                    f"SELECT * FROM {remote_src} "
                    f"WHERE timestamp >= {start_dt} AND timestamp < {end_dt}"
                )
                self._exec_cold(insert_sql)
                hot_cnt = self._scalar_cold(
                    f"SELECT count() FROM {remote_src} WHERE timestamp >= {start_dt} AND timestamp < {end_dt}"
                )
            else:
                insert_sql = (
                    f"INSERT INTO marketprism_cold.{table} "
                    f"SELECT * FROM marketprism_hot.{table} "
                    f"WHERE timestamp >= {start_dt} AND timestamp < {end_dt}"
                )
                self._exec_cold(insert_sql)
                hot_cnt = self._scalar_hot(
                    f"SELECT count() FROM marketprism_hot.{table} WHERE timestamp >= {start_dt} AND timestamp < {end_dt}"
                )
            cold_cnt = self._scalar_cold(
                f"SELECT count() FROM marketprism_cold.{table} WHERE timestamp >= {start_dt} AND timestamp < {end_dt}"
            )
            print(f"[replicator-lite] window {table} {start_dt}~{end_dt} hot={hot_cnt} cold={cold_cnt}")
            if cold_cnt >= hot_cnt:
                self._set_state_ms(table, end_ms)
                self.success_windows += 1
                processed += 1
                last_ms = end_ms
            else:
                raise RuntimeError(f"cold insufficient: hot={hot_cnt}, cold={cold_cnt}")

    async def _update_lags(self):
        for t in DEFAULT_TABLES:
            hot_max = self._scalar_hot(f"SELECT toInt64(max(toUnixTimestamp64Milli(timestamp))) FROM marketprism_hot.{t}") or 0
            cold_max = self._scalar_cold(f"SELECT toInt64(max(toUnixTimestamp64Milli(timestamp))) FROM marketprism_cold.{t}") or 0
            lag_min = 0
            if hot_max > 0:
                lag_min = (hot_max - cold_max) // 60000 if cold_max > 0 else 999999
                if lag_min < 0:
                    lag_min = 0
            self.table_lag_minutes[t] = int(lag_min)

    # ----------------- 状态持久化 -----------------
    def _get_state_ms(self, table: str) -> int:
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                d = json.load(f) or {}
            v = d.get(table)
            return int(v) if isinstance(v, int) else 0
        except Exception:
            return 0

    def _set_state_ms(self, table: str, ts_ms: int):
        try:
            d = {}
            if os.path.exists(self.state_path):
                with open(self.state_path, "r", encoding="utf-8") as f:
                    d = json.load(f) or {}
        except Exception:
            d = {}
        d[table] = int(ts_ms)
        # fix: ensure dir exists before write
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(d, f)

    # ----------------- CH 执行（CLI） -----------------
    def _cli(self, host: str, port: int, sql: str, user: Optional[str] = None, pwd: Optional[str] = None) -> str:
        user = user or "default"
        pwd_arg = f" --password {pwd}" if pwd else ""
        cmd = f"clickhouse-client --host {host} --port {port} --user {user}{pwd_arg} --query \"{sql}\""
        out = subprocess.check_output(["bash", "-lc", cmd], stderr=subprocess.STDOUT).decode().strip()
        return out

    def _exec_cold(self, sql: str):
        try:
            print(f"[replicator-lite] exec_cold SQL: {sql[:200]}...")
            self._cli(self.cold_host, self.cold_port, sql, self.cold_user, self.cold_pwd)
        except Exception as e:
            print(f"[replicator-lite] exec_cold error: {e}\nSQL: {sql}")
            raise

    def _scalar_cold(self, sql: str) -> int:
        try:
            s = self._cli(self.cold_host, self.cold_port, sql, self.cold_user, self.cold_pwd)
            return int(s) if s else 0
        except Exception:
            return 0

    def _scalar_hot(self, sql: str) -> int:
        try:
            s = self._cli(self.hot_host, self.hot_port, sql, self.hot_user, self.hot_pwd)
            return int(s) if s else 0
        except Exception:
            return 0

    def _exec_hot(self, sql: str):
        try:
            print(f"[replicator-lite] exec_hot SQL: {sql[:200]}...")
            self._cli(self.hot_host, self.hot_port, sql, self.hot_user, self.hot_pwd)
        except Exception as e:
            print(f"[replicator-lite] exec_hot error: {e}\nSQL: {sql}")
            raise

    async def _cleanup_by_watermark(self):
        """
        基于各表水位进行清理：删除 (watermark - delay) 之前的热端数据。
        注意：此处使用 ClickHouse 删除变更（mutation），建议按较大窗口进行，避免碎片化。
        """
        delay_ms = self.cleanup_delay_minutes * 60 * 1000
        if delay_ms <= 0:
            return
        now_ms = int(time.time() * 1000)
        for table in DEFAULT_TABLES:
            wm = self._get_state_ms(table)
            cutoff = wm - delay_ms
            if wm > 0 and cutoff > 0 and cutoff < now_ms:
                cutoff_dt = f"toDateTime64({cutoff}/1000.0, 3, 'UTC')"
                sql = f"ALTER TABLE marketprism_hot.{table} DELETE WHERE timestamp < {cutoff_dt}"
                try:
                    self._exec_hot(sql)
                except Exception as e:
                    print(f"[replicator-lite] cleanup {table} failed: {e}")

