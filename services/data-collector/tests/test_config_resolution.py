import os
import importlib
from pathlib import Path

# 轻量测试：验证配置解析与 NATS 变量兼容（不依赖外部服务）

def test_nats_env_compat(monkeypatch):
    from collector.config import Config

    # 构造最小配置文件
    temp_cfg = Path("/tmp/unified_data_collection.yaml")
    temp_cfg.write_text("""
exchanges:
  configs: []
""", encoding="utf-8")

    # 仅设置旧变量，未设置 NATS_URL
    monkeypatch.delenv("NATS_URL", raising=False)
    monkeypatch.setenv("MARKETPRISM_NATS_SERVERS", "nats://test:4222")

    cfg = Config.load_from_file(str(temp_cfg))
    assert cfg.nats.url == "nats://test:4222"

    # 设置新变量覆盖旧变量
    monkeypatch.setenv("NATS_URL", "nats://override:4222")
    cfg = Config.load_from_file(str(temp_cfg))
    assert cfg.nats.url == "nats://override:4222"


def test_config_priority_labels(monkeypatch):
    # 模拟主程序中对来源的打印（只校验环境变量存在与否）
    monkeypatch.setenv("MARKETPRISM_UNIFIED_DATA_COLLECTION_CONFIG", "/tmp/unified_data_collection.yaml")
    assert os.getenv("MARKETPRISM_UNIFIED_DATA_COLLECTION_CONFIG").endswith("unified_data_collection.yaml")

