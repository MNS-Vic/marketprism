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

        # 重试配置（缓解偶发 remote() 连接拒绝/网络抖动）
        self.max_retries: int = int(self.rep_cfg.get("max_retries", 3))
        self.retry_delay: float = float(self.rep_cfg.get("retry_delay", 1.0))
        self.retry_backoff: float = float(self.rep_cfg.get("retry_backoff", 2.0))

        # ClickHouse 连接与查询超时/压缩配置（提升稳健性，避免长时间挂起/连接僵死）
        self.ch_connect_timeout: int = int(self.rep_cfg.get("connect_timeout", 3))
        self.ch_send_receive_timeout: int = int(self.rep_cfg.get("send_receive_timeout", 120))
        self.ch_sync_request_timeout: int = int(self.rep_cfg.get("sync_request_timeout", 60))
        self.ch_compression: bool = bool(self.rep_cfg.get("compression", True))
        self.ch_max_execution_time: int = int(self.rep_cfg.get("max_execution_time", 60))

        # ClickHouse 连接配置（支持跨实例：hot 与 cold 可不同）
        hot = (self.cfg.get("hot_storage") or {})
        cold = (self.cfg.get("cold_storage") or {})
        self.hot_host = hot.get("clickhouse_host", "localhost")
        self.hot_port = int(hot.get("clickhouse_tcp_port", 9000))
        self.hot_user = hot.get("clickhouse_user", "default")
        self.hot_pwd = hot.get("clickhouse_password", "")
        self.cold_host = cold.get("clickhouse_host", self.hot_host)
        self.cold_port = int(cold.get("clickhouse_tcp_port", self.hot_port))
        self.cold_user = cold.get("clickhouse_user", self.hot_user)
        self.cold_pwd = cold.get("clickhouse_password", self.hot_pwd)
        # 是否跨实例（任一连接参数不同即视为跨实例）
        self.cross_instance = any([
            self.hot_host != self.cold_host,
            self.hot_port != self.cold_port,
            self.hot_user != self.cold_user,
            self.hot_pwd != self.cold_pwd,
        ])
        # 执行连接：跨实例时连接冷端；单实例时连接热端
        self._ch: Optional[CHClient] = None

        # 状态文件（优先使用冷端模块运行目录）
        run_dir = os.environ.get("MARKETPRISM_COLD_RUN_DIR") or os.path.join("services", "cold-storage-service", "run")
        os.makedirs(run_dir, exist_ok=True)
        self.state_path = os.path.join(run_dir, "sync_state.json")

        # 运行状态
        self._stop = False
        self.last_run_ts: Optional[float] = None
        self.success_windows = 0
        self.failed_windows = 0
        self.table_lag_minutes: Dict[str, int] = {t: -1 for t in DEFAULT_TABLES}

        # Additional config: low/high frequency tables, bootstrap seeding, per-table lag
        self.low_freq_tables = set(["funding_rates", "open_interests", "lsr_top_positions", "lsr_all_accounts", "volatility_indices", "liquidations"])
        self.high_freq_tables = set(["trades", "orderbooks"])
        # Bootstrap seeding to quickly make cold data available after startup
        self.bootstrap_enabled = bool(self.rep_cfg.get("bootstrap_enabled", True))
        self.bootstrap_minutes_high = int(self.rep_cfg.get("bootstrap_minutes_high", 5))
        self.bootstrap_minutes_low = int(self.rep_cfg.get("bootstrap_minutes_low", 180))
        # Per-table safety lag (minutes)
        self.safety_lag_minutes_low = int(self.rep_cfg.get("safety_lag_minutes_low", 0))
        self.safety_lag_minutes_high = int(self.rep_cfg.get("safety_lag_minutes_high", self.safety_lag_minutes))
        # 追赶策略：每轮每表最多推进的窗口数（用于消除历史积压）
        self.max_catchup_windows_low = int(self.rep_cfg.get("max_catchup_windows_low", 2))
        self.max_catchup_windows_high = int(self.rep_cfg.get("max_catchup_windows_high", 5))


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

    async def _bootstrap_if_needed(self):
        """Seed cold storage on first run so low-frequency tables are visible without manual repair."""
        if not self.bootstrap_enabled:
            return
        # Check state file for bootstrap flag
        boot_done = False
        try:
            if os.path.exists(self.state_path):
                import json as _json
                with open(self.state_path, "r", encoding="utf-8") as f:
                    d = _json.load(f) or {}
                    boot_done = bool(d.get("_BOOTSTRAP_DONE", False))
        except Exception:
            boot_done = False
        if boot_done:
            return

        # Perform seeding: copy recent minutes for each table if cold is empty but hot has data
        for tbl in DEFAULT_TABLES:
            try:
                minutes = self.bootstrap_minutes_high if tbl in self.high_freq_tables else self.bootstrap_minutes_low
                if self.cross_instance:
                    hot_recent = self._scalar_with_retry(
                        f"SELECT count() FROM remote('{self.hot_host}:{self.hot_port}', 'marketprism_hot', '{tbl}', '{self.hot_user}', '{self.hot_pwd}') "
                        f"WHERE timestamp >= now() - INTERVAL {minutes} MINUTE"
                    )
                    insert_sql = (
                        f"INSERT INTO marketprism_cold.{tbl} "
                        f"SELECT * FROM remote('{self.hot_host}:{self.hot_port}', 'marketprism_hot', '{tbl}', '{self.hot_user}', '{self.hot_pwd}') "
                        f"WHERE timestamp >= now() - INTERVAL {minutes} MINUTE"
                    )
                else:
                    hot_recent = self._scalar_with_retry(
                        f"SELECT count() FROM marketprism_hot.{tbl} WHERE timestamp >= now() - INTERVAL {minutes} MINUTE"
                    )
                    insert_sql = (
                        f"INSERT INTO marketprism_cold.{tbl} SELECT * FROM marketprism_hot.{tbl} "
                        f"WHERE timestamp >= now() - INTERVAL {minutes} MINUTE"
                    )
                cold_total = self._scalar_with_retry(f"SELECT count() FROM marketprism_cold.{tbl}")
                if cold_total == 0 and hot_recent > 0:
                    self._exec_with_retry(insert_sql)
            except Exception as e:
                # seeding is best-effort; continue
                print(f"[replicator] bootstrap seed for {tbl} failed: {e}")

        # Mark bootstrap done to avoid repeated full copies
        try:
            import json as _json
            d = {}
            if os.path.exists(self.state_path):
                try:
                    with open(self.state_path, "r", encoding="utf-8") as f:
                        d = _json.load(f) or {}
                except Exception:
                    d = {}
            d["_BOOTSTRAP_DONE"] = True
            with open(self.state_path, "w", encoding="utf-8") as f:
                _json.dump(d, f)
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

        # One-time bootstrap to quickly expose recent data in cold storage
        try:
            await self._bootstrap_if_needed()
        except Exception as e:
            print(f"[replicator] bootstrap skipped due to error: {e}")

        # Per-table replication with per-table safety lag
        for tbl in DEFAULT_TABLES:
            try:
                lag_min = self.safety_lag_minutes_high if tbl in self.high_freq_tables else self.safety_lag_minutes_low
                safety_end = now_ms - max(lag_min, 0) * 60 * 1000
                if safety_end <= 0:
                    continue
                await self._replicate_table_window(tbl, safety_end)
            except Exception as e:
                print(f"[replicator] table {tbl} replication failed: {e}")
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
        """
        支持一次 run 内对单表连续推进多个窗口（用于追赶历史积压）。
        - 高频表使用 max_catchup_windows_high，低频表使用 max_catchup_windows_low
        - 任一窗口失败即停止并抛出异常，由上层统计 failed_windows
        """
        max_windows = self.max_catchup_windows_high if table in self.high_freq_tables else self.max_catchup_windows_low
        processed = 0

        # 读取初始水位
        last_ms = self._get_state_ms(table)
        if last_ms <= 0:
            last_ms = safety_end_ms - self.window_minutes_all * 60 * 1000

        while processed < max_windows:
            # 计算当前窗口区间
            end_ms = min(last_ms + self.window_minutes_all * 60 * 1000, safety_end_ms)
            if end_ms <= last_ms:
                break  # 无可推进窗口

            start_dt = f"toDateTime64({last_ms}/1000.0, 3, 'UTC')"
            end_dt = f"toDateTime64({end_ms}/1000.0, 3, 'UTC')"

            # 构造 INSERT
            if self.cross_instance:
                hot_remote = f"remote('{self.hot_host}:{self.hot_port}', 'marketprism_hot', '{table}', '{self.hot_user}', '{self.hot_pwd}')"
                insert_sql = (
                    f"INSERT INTO marketprism_cold.{table} "
                    f"SELECT * FROM {hot_remote} "
                    f"WHERE timestamp >= {start_dt} AND timestamp < {end_dt}"
                )
            else:
                insert_sql = (
                    f"INSERT INTO marketprism_cold.{table} "
                    f"SELECT * FROM marketprism_hot.{table} "
                    f"WHERE timestamp >= {start_dt} AND timestamp < {end_dt}"
                )

            # 执行复制并核验
            self._exec_with_retry(insert_sql)
            if self.cross_instance:
                hot_cnt_sql = (
                    f"SELECT count() FROM remote('{self.hot_host}:{self.hot_port}', 'marketprism_hot', '{table}', '{self.hot_user}', '{self.hot_pwd}') "
                    f"WHERE timestamp >= {start_dt} AND timestamp < {end_dt}"
                )
            else:
                hot_cnt_sql = (
                    f"SELECT count() FROM marketprism_hot.{table} WHERE timestamp >= {start_dt} AND timestamp < {end_dt}"
                )
            cold_cnt_sql = (
                f"SELECT count() FROM marketprism_cold.{table} WHERE timestamp >= {start_dt} AND timestamp < {end_dt}"
            )
            hot_cnt = self._scalar_with_retry(hot_cnt_sql)
            cold_cnt = self._scalar_with_retry(cold_cnt_sql)

            if cold_cnt >= hot_cnt:
                # 推进水位到 end_ms，并继续下一窗口
                self._set_state_ms(table, end_ms)
                self.success_windows += 1
                processed += 1
                last_ms = end_ms
                # 可选清理（非跨实例）
                if self.cleanup_enabled and not self.cross_instance:
                    await self._cleanup_hot_after_confirm(table, last_ms - self.window_minutes_all * 60 * 1000, end_ms, hot_cnt)
            else:
                # 当次窗口失败，退出并交由上层统计
                raise RuntimeError(f"冷端计数不足 (hot={hot_cnt}, cold={cold_cnt})，不推进水位")

    async def _cleanup_hot_after_confirm(self, table: str, start_ms: int, end_ms: int, hot_cnt_expected: int):
        # 清理前等待 delay（以分钟为单位），并再次确认计数
        delay_ms = self.cleanup_delay_minutes * 60 * 1000
        if int(time.time() * 1000) < end_ms + delay_ms:
            return
        start_dt = f"toDateTime64({start_ms}/1000.0, 3, 'UTC')"
        end_dt = f"toDateTime64({end_ms}/1000.0, 3, 'UTC')"
        # 计数确认（热端、冷端）
        if self.cross_instance:
            hot_cnt = self._scalar_hot(
                f"SELECT count() FROM marketprism_hot.{table} WHERE timestamp >= {start_dt} AND timestamp < {end_dt}"
            )
        else:
            hot_cnt = self._scalar(
                f"SELECT count() FROM marketprism_hot.{table} WHERE timestamp >= {start_dt} AND timestamp < {end_dt}"
            )
        cold_cnt = self._scalar(
            f"SELECT count() FROM marketprism_cold.{table} WHERE timestamp >= {start_dt} AND timestamp < {end_dt}"
        )
        if cold_cnt >= hot_cnt >= hot_cnt_expected:
            # 删除热端数据（跨实例时直连热端执行）
            if self.cross_instance:
                self._exec_hot(
                    f"ALTER TABLE marketprism_hot.{table} DELETE WHERE timestamp >= {start_dt} AND timestamp < {end_dt}"
                )
            else:
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
                sql = f"ALTER TABLE marketprism_hot.{table} DELETE WHERE timestamp < {cutoff_dt}"
                if self.cross_instance:
                    self._exec_hot(sql)
                else:
                    self._exec(sql)

    async def _update_lags(self):
        for t in DEFAULT_TABLES:
            if self.cross_instance:
                hot_max = self._scalar_with_retry(
                    f"SELECT toInt64(max(toUnixTimestamp64Milli(timestamp))) FROM remote('{self.hot_host}:{self.hot_port}', 'marketprism_hot', '{t}', '{self.hot_user}', '{self.hot_pwd}')"
                ) or 0
            else:
                hot_max = self._scalar_with_retry(
                    f"SELECT toInt64(max(toUnixTimestamp64Milli(timestamp))) FROM marketprism_hot.{t}"
                ) or 0
            cold_max = self._scalar_with_retry(
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

    def _retry(self, func, *args, **kwargs):
        """通用重试包装：用于缓解偶发的 remote() 连接拒绝/网络抖动。
        捕获异常后按 retry_delay * backoff^attempt 退避，最多 max_retries 次。
        """
        last_e = None
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:  # pragma: no cover
                last_e = e
                # 重置连接，避免连接假死/复用坏连接
                try:
                    self._ch = None
                    self._ch_hot = None
                except Exception:
                    pass
                try:
                    time.sleep(self.retry_delay * (self.retry_backoff ** attempt))
                except Exception:
                    pass
        if last_e:
            raise last_e

    def _exec_with_retry(self, sql: str):
        return self._retry(self._exec, sql)

    def _scalar_with_retry(self, sql: str) -> int:
        return self._retry(self._scalar, sql)
    def _client(self) -> Optional[CHClient]:
        if CHClient is None:
            return None
        if self._ch is None:
            exec_host = self.cold_host if self.cross_instance else self.hot_host
            exec_port = self.cold_port if self.cross_instance else self.hot_port
            exec_user = self.cold_user if self.cross_instance else self.hot_user
            exec_pwd = self.cold_pwd if self.cross_instance else self.hot_pwd
            #    a a a: a a aaaa
            self._ch = CHClient(
                host=exec_host,
                port=exec_port,
                user=exec_user,
                password=exec_pwd,
                database="default",
                connect_timeout=self.ch_connect_timeout,
                send_receive_timeout=self.ch_send_receive_timeout,
                sync_request_timeout=self.ch_sync_request_timeout,
                compression=self.ch_compression,
                settings={"max_execution_time": self.ch_max_execution_time},
            )
        return self._ch
    def _client_hot(self) -> Optional[CHClient]:
        if CHClient is None:
            return None
        ch = getattr(self, "_ch_hot", None)
        if ch is None:
            try:
                self._ch_hot = CHClient(
                    host=self.hot_host,
                    port=self.hot_port,
                    user=self.hot_user,
                    password=self.hot_pwd,
                    database="default",
                    connect_timeout=self.ch_connect_timeout,
                    send_receive_timeout=self.ch_send_receive_timeout,
                    sync_request_timeout=self.ch_sync_request_timeout,
                    compression=self.ch_compression,
                    settings={"max_execution_time": self.ch_max_execution_time},
                )
            except Exception:
                self._ch_hot = None
        return self._ch_hot

    def _exec_hot(self, sql: str):
        cl = self._client_hot()
        if cl:
            return cl.execute(sql)
        # fallback: cli
        exec_host = self.hot_host; exec_port = self.hot_port; exec_user = self.hot_user; exec_pwd = self.hot_pwd
        pwd_arg = f" --password {exec_pwd}" if exec_pwd else ""
        cmd = f"clickhouse-client --host {exec_host} --port {exec_port} --user {exec_user}{pwd_arg} --query \"{sql}\""
        rc = os.system(cmd)
        if rc != 0:  # pragma: no cover
            raise RuntimeError(f"clickhouse-client 执行失败: rc={rc}")

    def _scalar_hot(self, sql: str) -> int:
        cl = self._client_hot()
        if cl:
            try:
                res = cl.execute(sql)
                if isinstance(res, list) and res:
                    v = res[0][0]
                    return int(v) if v is not None else 0
            except Exception:
                return 0
            return 0
        # fallback cli
        try:
            import subprocess
            exec_host = self.hot_host; exec_port = self.hot_port; exec_user = self.hot_user; exec_pwd = self.hot_pwd
            pwd_arg = f" --password {exec_pwd}" if exec_pwd else ""
            cmd = f"clickhouse-client --host {exec_host} --port {exec_port} --user {exec_user}{pwd_arg} --query \"{sql}\""
            out = subprocess.check_output(["bash", "-lc", cmd])
            s = out.decode().strip()
            return int(s) if s else 0
        except Exception:
            return 0


    def _exec(self, sql: str):
        cl = self._client()
        if cl:
            return cl.execute(sql)
        # 退化为命令行（连接到执行实例：跨实例=冷端；单实例=热端）
        exec_host = self.cold_host if self.cross_instance else self.hot_host
        exec_port = self.cold_port if self.cross_instance else self.hot_port
        exec_user = self.cold_user if self.cross_instance else self.hot_user
        exec_pwd = self.cold_pwd if self.cross_instance else self.hot_pwd
        pwd_arg = f" --password {exec_pwd}" if exec_pwd else ""
        cmd = f"clickhouse-client --host {exec_host} --port {exec_port} --user {exec_user}{pwd_arg} --query \"{sql}\""
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
        # 命令行方式（连接到执行实例）
        try:
            import subprocess
            exec_host = self.cold_host if self.cross_instance else self.hot_host
            exec_port = self.cold_port if self.cross_instance else self.hot_port
            exec_user = self.cold_user if self.cross_instance else self.hot_user
            exec_pwd = self.cold_pwd if self.cross_instance else self.hot_pwd
            pwd_arg = f" --password {exec_pwd}" if exec_pwd else ""
            cmd = f"clickhouse-client --host {exec_host} --port {exec_port} --user {exec_user}{pwd_arg} --query \"{sql}\""
            out = subprocess.check_output(["bash", "-lc", cmd])
            s = out.decode().strip()
            return int(s) if s else 0
        except Exception:
            return 0

