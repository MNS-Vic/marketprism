import asyncio
import json
from datetime import datetime, timezone

import pytest
import yaml

from collector.nats_publisher import NATSPublisher, create_nats_config_from_yaml
from collector.normalizer import DataNormalizer
from collector.vol_index_managers.deribit_derivatives_vol_index_manager import (
    DeribitDerivativesVolIndexManager,
)


@pytest.mark.asyncio
async def test_vol_index_offline_publish(caplog):
    """离线冒烟：标准化两条VI并发布到NATS，验证publish成功日志。
    依赖本机已运行的统一NATS（JetStream）。
    """
    # 读取配置
    config = yaml.safe_load(open("services/data-collector/config/collector/unified_data_collection.yaml", "r"))

    # NATSPublisher
    ncfg = create_nats_config_from_yaml(config)
    pub = NATSPublisher(ncfg)
    ok = await pub.connect()
    assert ok, "NATS连接失败"

    # Manager 仅用于复用 _publish_to_nats
    mgr = DeribitDerivativesVolIndexManager(symbols=["BTC", "ETH"], nats_publisher=pub, config=config)

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    samples = [
        {"currency": "BTC", "timestamp": now_ms, "volatility_index": 0.1111},
        {"currency": "ETH", "timestamp": now_ms, "volatility_index": 0.2222},
    ]

    norm = DataNormalizer()
    for s in samples:
        obj = norm.normalize_deribit_volatility_index(s)
        assert obj is not None
        payload = {
            "exchange": obj.exchange_name,
            "symbol": obj.symbol_name,
            "currency": obj.currency,
            "vol_index": obj.volatility_value,
            "volatility_index": obj.volatility_value,
            "timestamp": obj.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "market_type": obj.market_type,
            "data_source": "marketprism",
        }
        await mgr._publish_to_nats(s["currency"], payload)

    # 等待日志刷新
    await asyncio.sleep(1)

    # 检查日志里是否包含“低频数据发布成功”关键字
    joined = "\n".join(m for _, m in caplog.records)
    # 宽松匹配关键文本
    assert "低频数据发布成功" in caplog.text

    await pub.disconnect()

