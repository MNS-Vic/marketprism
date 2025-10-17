#!/usr/bin/env python3
"""
MarketPrism 冷端数据存储服务（独立模块）
- 职责：从 ClickHouse Hot 批量复制到 ClickHouse Cold（按时间窗口），推进水位，可选清理
- 核心：复用 data-storage-service/replication.py 中的 HotToColdReplicator
- 健康端口：默认 8086（/health, /stats）

注意：本模块默认不依赖 NATS，仅依赖 ClickHouse；测试阶段可在本机部署，但需假设冷端在远端。
"""
import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict

import yaml
from aiohttp import web
import re
from datetime import datetime, timezone
import time
import subprocess
try:
    from clickhouse_driver import Client
except Exception:
    Client = None

# 确保可以从仓库根导入 data-storage-service.replication（容器/本地均可）
try:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
except IndexError:
    PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

try:
    from services.cold_storage_service.replication import HotToColdReplicator  # noqa: E402
except Exception:
    try:
        from replication import HotToColdReplicator  # noqa: E402
    except Exception as e:
        raise

_env_pat = re.compile(r"^\$\{([^}:]+)(:-([^}]*))?\}$")

def _expand_env_value(val: Any) -> Any:
    if isinstance(val, str):
        m = _env_pat.match(val)
        if m:
            key = m.group(1)
            default = m.group(3) or ""
            return os.environ.get(key, default)
    return val

def _expand_env_in_cfg(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _expand_env_in_cfg(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env_in_cfg(v) for v in obj]
    return _expand_env_value(obj)


class ColdServiceApp:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.replicator = HotToColdReplicator(self.config)
        self.app = web.Application()
        # 观测性缓存（用于兼容旧复制器无 last_success_ts/recent_errors 的情况）
        self._last_success_windows: int = 0
        self._last_success_ts: float | None = None
        self.runner: web.AppRunner | None = None
        self.http_port = int(self.config.get("cold_storage", {}).get("http_port", 8086))

    async def start(self):
        # 路由
        self.app.router.add_get("/health", self.handle_health)
        self.app.router.add_get("/stats", self.handle_stats)

        # 启动复制loop
        if self.replicator.enabled:
            asyncio.create_task(self.replicator.run_loop())
        else:
            print("ℹ️ 冷端复制未启用(replication.enabled=false)")

        # HTTP服务器
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", self.http_port)
        await site.start()
        print(f"✅ Cold Storage Service started on :{self.http_port}")

    async def stop(self):
        try:
            await self.replicator.stop()
        except Exception:
            pass
        if self.runner:
            await self.runner.cleanup()

    async def handle_health(self, request: web.Request):
        # 检查热/冷 ClickHouse 连接可用性（优先使用驱动；若无则回退到 CLI）
        def ch_ok(cfg: Dict[str, Any], section: str) -> bool:
            try:
                sec = cfg.get(section, {})
                host = str(sec.get("clickhouse_host", "localhost"))
                port = int(sec.get("clickhouse_tcp_port", 9000))
                user = str(sec.get("clickhouse_user", "default"))
                password = str(sec.get("clickhouse_password", ""))
                database = str(sec.get("clickhouse_database", "default"))
                if Client is not None:
                    client = Client(host=host, port=port, user=user, password=password, database=database,
                                    connect_timeout=2, send_receive_timeout=2)
                    client.execute("SELECT 1")
                    return True
                # 回退：使用 clickhouse-client CLI 探活
                cmd = f"clickhouse-client --host {host} --port {port} --user {user} --query 'SELECT 1'"
                if password:
                    cmd = f"clickhouse-client --host {host} --port {port} --user {user} --password {password} --query 'SELECT 1'"
                subprocess.check_output(["bash", "-lc", cmd], stderr=subprocess.STDOUT)
                return True
            except Exception:
                return False

        hot_ok = ch_ok(self.config, "hot_storage")
        cold_ok = ch_ok(self.config, "cold_storage")
        ok = self.replicator.enabled and hot_ok and cold_ok
        rep_cfg = self.config.get("replication", {})
        status = {
            "status": "healthy" if ok else "degraded",
            "hot_clickhouse": hot_ok,
            "cold_clickhouse": cold_ok,
            "replication": {
                "enabled": bool(rep_cfg.get("enabled", False)),
                "cleanup_enabled": bool(rep_cfg.get("cleanup_enabled", False)),
                "impl": ("http" if hasattr(self.replicator, "_http_query") else ("driver" if getattr(self.replicator, "_client", None) else "cli")),
                "cross_instance": bool(getattr(self.replicator, "cross_instance", False)),
                "dependency_warnings": getattr(self.replicator, "dependency_warnings", []),
            },
        }
        return web.json_response(status, status=200 if ok else 503)

    async def handle_stats(self, request: web.Request):
        try:
            st = self.replicator.get_status()
        except Exception:
            st = {"error": "no-status"}
            return web.json_response(st, status=200)

        # 增强 /stats 观测字段：last_success_utc / recent_errors / errors_count_1h
        try:
            # last_success_utc：优先使用复制器提供的；否则用 success_windows 变化推断
            last_success_utc = st.get("last_success_utc")
            if not last_success_utc:
                sw = int(st.get("success_windows", 0) or 0)
                if sw > self._last_success_windows:
                    self._last_success_windows = sw
                    self._last_success_ts = time.time()
                if self._last_success_ts:
                    last_success_utc = datetime.fromtimestamp(self._last_success_ts, tz=timezone.utc).isoformat()
                st["last_success_utc"] = last_success_utc

            # recent_errors / errors_count_1h：优先复制器；否则基于 last_error 填充空列表/0
            recent_errors = st.get("recent_errors")
            if recent_errors is None:
                rep_recent = getattr(self.replicator, "recent_errors", None)
                if isinstance(rep_recent, list):
                    recent_errors = []
                    cutoff = time.time() - 3600
                    errors_1h = 0
                    for e in rep_recent[-50:]:
                        ts = float((e or {}).get("ts", 0) or 0)
                        if ts >= cutoff:
                            errors_1h += 1
                        recent_errors.append({
                            "time_utc": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None,
                            "table": (e or {}).get("table"),
                            "message": (e or {}).get("message"),
                        })
                    st["errors_count_1h"] = st.get("errors_count_1h", errors_1h)
                else:
                    # 无法获取结构化错误，则提供空占位，避免前端判空困难
                    recent_errors = []
                    st.setdefault("errors_count_1h", 0)
                st["recent_errors"] = recent_errors
        except Exception:
            pass

        # 版本标记，便于前端识别新结构
        st.setdefault("stats_version", 2)
        st.setdefault("server_time_utc", datetime.fromtimestamp(time.time(), tz=timezone.utc).isoformat())
        return web.json_response(st, status=200)


async def _main():
    # 读取配置路径（优先顺序：命令行 --config > 环境变量 COLD_STORAGE_CONFIG > 模块内默认路径）
    cfg_path = None
    try:
        import argparse
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--config", dest="config")
        args, _ = parser.parse_known_args()
        cfg_path = args.config
    except Exception:
        pass
    if not cfg_path:
        cfg_path = os.environ.get("COLD_STORAGE_CONFIG")
    if not cfg_path:
        cfg_path = str(Path(__file__).parent / "config" / "cold_storage_config.yaml")

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    cfg = _expand_env_in_cfg(cfg)

    # 独立运行目录（用于状态文件）
    run_dir = os.environ.get("MARKETPRISM_COLD_RUN_DIR") or str(Path(__file__).parent / "run")
    os.makedirs(run_dir, exist_ok=True)

    app = ColdServiceApp(cfg)
    await app.start()

    stop_event = asyncio.Event()

    def _sig_handler():
        try:
            stop_event.set()
        except Exception:
            pass

    for sig in ("SIGINT", "SIGTERM"):
        try:
            import signal
            asyncio.get_running_loop().add_signal_handler(getattr(signal, sig), _sig_handler)
        except Exception:
            pass

    await stop_event.wait()
    await app.stop()


if __name__ == "__main__":
    asyncio.run(_main())

