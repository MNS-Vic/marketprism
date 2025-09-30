"""
主题模板与命名规范单元测试
- 覆盖8类数据类型的下划线命名
- 校验示例主题不含历史 "-data." 前缀
- 基于唯一配置入口的模板（collector）生成主题
"""
import re
from pathlib import Path
import yaml
import pytest

CONFIG_PATH = Path("services/data-collector/config/collector/unified_data_collection.yaml")

@pytest.mark.unit
def test_subject_templates_exist():
    assert CONFIG_PATH.exists(), "collector唯一配置不存在"
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    streams = cfg["nats"]["streams"]
    # 关键数据类型模板必须存在
    required = {
        "orderbook","trade","funding_rate","open_interest",
        "liquidation","volatility_index","lsr_top_position","lsr_all_account"
    }
    assert required.issubset(set(streams.keys()))

@pytest.mark.unit
@pytest.mark.parametrize(
    "dtype,exchange,market_type,symbol,expected",
    [
        ("funding_rate","okx_derivatives","perpetual","BTC-USDT",
         "funding_rate.okx_derivatives.perpetual.BTC-USDT"),
        ("open_interest","binance_derivatives","perpetual","ETH-USDT",
         "open_interest.binance_derivatives.perpetual.ETH-USDT"),
        ("trade","binance_spot","spot","BTCUSDT",
         "trade.binance_spot.spot.BTCUSDT"),
        ("orderbook","okx_spot","spot","ETH-USDT",
         "orderbook.okx_spot.spot.ETH-USDT"),
        ("lsr_top_position","okx_derivatives","perpetual","BTC-USDT-SWAP",
         "lsr_top_position.okx_derivatives.perpetual.BTC-USDT-SWAP"),
        ("lsr_all_account","binance_derivatives","perpetual","BTC-USDT",
         "lsr_all_account.binance_derivatives.perpetual.BTC-USDT"),
        ("volatility_index","deribit_derivatives","perpetual","BTC",
         "volatility_index.deribit_derivatives.perpetual.BTC"),
    ],
)
def test_subject_template_render(dtype, exchange, market_type, symbol, expected):
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    template = cfg["nats"]["streams"][dtype]
    subject = template.format(exchange=exchange, market_type=market_type, symbol=symbol)
    assert subject == expected
    # 命名规范：全为下划线风格的数据类型名，不应包含历史 "-data." 片段
    assert "-data" not in subject
    # 基本合法性：以字母开头，仅允许字母/数字/.-_ 字符
    assert re.match(r"^[A-Za-z][A-Za-z0-9_\.\-]*$", subject)

