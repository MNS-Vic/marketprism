import asyncio
import os

import pytest

from unified_collector_main import UnifiedDataCollector


@pytest.mark.asyncio
async def test_unified_deribit_e2e_online_run(monkeypatch):
    """仅启用 deribit_derivatives，运行 collector 的启动流程，运行短时间后停止。
    需要外网访问 Deribit API，若网络不可达则允许跳过。
    """
    # 仅选择 deribit_derivatives
    collector = UnifiedDataCollector(mode="launcher", target_exchange="deribit_derivatives")

    try:
        started = await collector.start()
        if not started:
            pytest.skip("Collector 未能启动（可能是外网不可达或NATS不可用）")

        # 运行片刻让其抓取一次
        await asyncio.sleep(5)

        # 简单判断：manager_launcher 至少应存在
        assert collector.manager_launcher is not None

    finally:
        await collector.stop()

