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

# 确保可以从仓库根导入 data-storage-service.replication（容器/本地均可）
try:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
except IndexError:
    PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

try:
    from services.data_storage_service.replication import HotToColdReplicator  # noqa: E402
except Exception:
    # 回退：直接将 services/data-storage-service 加入 sys.path
    alt = Path(__file__).resolve().parent / "services" / "data-storage-service"
    if alt.exists() and str(alt) not in sys.path:
        sys.path.append(str(alt))
    try:
        from replication import HotToColdReplicator  # type: ignore  # noqa: E402
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
        status = {
            "status": "healthy" if self.replicator.enabled else "degraded",
        }
        return web.json_response(status, status=200)

    async def handle_stats(self, request: web.Request):
        try:
            st = self.replicator.get_status()
        except Exception:
            st = {"error": "no-status"}
        return web.json_response(st, status=200)


async def _main():
    # 读取配置路径
    cfg_path = os.environ.get("COLD_STORAGE_CONFIG", "config/cold_storage_config.yaml")
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

