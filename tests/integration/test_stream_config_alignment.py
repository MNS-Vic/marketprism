"""
JetStream 双流配置一致性（collector 与 broker）集成测试
- 校验 MARKET_DATA 与 ORDERBOOK_SNAP 两个流的 subjects 完全一致
- 确保没有遗留历史的 "-data." 风格主题
"""
from pathlib import Path
import yaml
import pytest

COLLECTOR_CFG = Path("services/data-collector/config/collector/unified_data_collection.yaml")
BROKER_CFG = Path("services/message-broker/config/unified_message_broker.yaml")

@pytest.mark.integration
def test_stream_subjects_alignment():
    assert COLLECTOR_CFG.exists() and BROKER_CFG.exists()
    c = yaml.safe_load(COLLECTOR_CFG.read_text(encoding="utf-8"))
    b = yaml.safe_load(BROKER_CFG.read_text(encoding="utf-8"))

    # 从 collector 配置读取两个流的主题
    c_market = sorted(c["nats"]["jetstream"]["streams"]["MARKET_DATA"]["subjects"])
    c_order = sorted(c["nats"]["jetstream"]["streams"]["ORDERBOOK_SNAP"]["subjects"])

    # 从 broker 配置读取两个流的主题
    b_market = sorted(b["streams"]["MARKET_DATA"]["subjects"])
    b_order = sorted(b["streams"]["ORDERBOOK_SNAP"]["subjects"])

    assert c_market == b_market, f"MARKET_DATA subjects 不一致: {c_market} vs {b_market}"
    assert c_order == b_order, f"ORDERBOOK_SNAP subjects 不一致: {c_order} vs {b_order}"

@pytest.mark.integration
def test_no_deprecated_dash_data_subjects():
    """
    检查配置中不再出现历史的 "-data." 主题片段（仅检查实际 subject 值，忽略注释文本）
    """
    c = yaml.safe_load(COLLECTOR_CFG.read_text(encoding="utf-8"))
    b = yaml.safe_load(BROKER_CFG.read_text(encoding="utf-8"))

    subjects = []
    for stream in ("MARKET_DATA", "ORDERBOOK_SNAP"):
        subjects += c.get("nats", {}).get("jetstream", {}).get("streams", {}).get(stream, {}).get("subjects", []) or []
        subjects += b.get("streams", {}).get(stream, {}).get("subjects", []) or []

    assert all("-data." not in s for s in subjects), f"发现废弃 subject 片段于: {[s for s in subjects if '-data.' in s]}"

