# Data Normalizer 技术文档

## 📋 模块概述

Data Normalizer 是 MarketPrism data-collector 服务的核心组件，负责将来自不同交易所的原始市场数据转换为统一的标准格式，确保数据的一致性和可互操作性。

### 核心职责
- **数据标准化**: 将不同交易所的原始数据格式转换为统一的标准格式
- **交易对格式统一**: 将各种交易对格式（如 BTCUSDT、BTC/USDT）统一为 BTC-USDT 格式
- **数据类型转换**: 确保价格、数量等数值数据的精度和类型一致性
- **时间戳标准化**: 统一时间戳格式为 UTC datetime 对象
- **数据验证**: 验证数据完整性和有效性

### 支持的交易所
| 交易所 | 支持状态 | 数据类型 |
|--------|----------|----------|
| **Binance** | ✅ 完全支持 | 交易、订单簿、行情、深度更新 |
| **OKX** | ✅ 完全支持 | 交易、订单簿、行情、深度更新 |
| **Deribit** | 🔄 规划中 | - |
| **Bybit** | 🔄 规划中 | - |

### 数据标准化流程
```
原始数据 → 格式验证 → 字段映射 → 类型转换 → 标准化输出
    ↓           ↓          ↓         ↓           ↓
交易所API → 数据完整性 → 字段标准化 → Decimal精度 → NormalizedData
```

## 🔧 DataNormalizer 类架构

### 类定义
```python
class DataNormalizer:
    """数据标准化器 - 集成到collector中的模块"""
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
```

### 核心方法分类
| 方法类型 | 方法数量 | 功能描述 |
|----------|----------|----------|
| **交易数据标准化** | 2个 | normalize_binance_trade, normalize_okx_trade |
| **订单簿数据标准化** | 2个 | normalize_binance_orderbook, normalize_okx_orderbook |
| **行情数据标准化** | 2个 | normalize_binance_ticker, normalize_okx_ticker |
| **深度更新标准化** | 3个 | normalize_binance_depth_update, normalize_okx_depth_update, normalize_depth_update |
| **增强订单簿** | 2个 | normalize_enhanced_orderbook_from_snapshot, normalize_enhanced_orderbook_from_update |
| **强平订单标准化** | 2个 | normalize_okx_liquidation, normalize_binance_liquidation |
| **工具方法** | 2个 | _normalize_symbol_format, convert_to_legacy_orderbook |

## 📊 数据类型处理详解

### 1. 交易数据 (Trade Data)

#### Binance 原始数据格式
```json
{
  "e": "trade",
  "E": 1672531200000,
  "s": "BTCUSDT",
  "t": 12345,
  "p": "16569.01",
  "q": "0.014",
  "b": 88,
  "a": 50,
  "T": 1672531200000,
  "m": true,
  "M": true
}
```

#### OKX 原始数据格式
```json
{
  "arg": {
    "channel": "trades",
    "instId": "BTC-USDT"
  },
  "data": [{
    "instId": "BTC-USDT",
    "tradeId": "130639474",
    "px": "16569.01",
    "sz": "0.014",
    "side": "buy",
    "ts": "1672531200000"
  }]
}
```

#### 标准化输出格式
```python
NormalizedTrade(
    exchange_name="binance",           # 交易所名称
    symbol_name="BTC-USDT",           # 统一交易对格式
    trade_id="12345",                 # 交易ID
    price=Decimal("16569.01"),        # 成交价格 (高精度)
    quantity=Decimal("0.014"),        # 成交数量 (高精度)
    quote_quantity=Decimal("231.966"), # 成交金额 (自动计算)
    side="buy",                       # 交易方向 (统一为 buy/sell)
    timestamp=datetime(2023, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
)
```

#### 标准化规则
| 字段 | Binance映射 | OKX映射 | 转换规则 |
|------|-------------|---------|----------|
| **exchange_name** | "binance" | "okx" | 固定值 |
| **symbol_name** | s → 格式转换 | instId → 格式转换 | BTCUSDT → BTC-USDT |
| **trade_id** | t → str() | tradeId | 转换为字符串 |
| **price** | p → Decimal() | px → Decimal() | 高精度数值 |
| **quantity** | q → Decimal() | sz → Decimal() | 高精度数值 |
| **side** | m ? "sell" : "buy" | side | 统一为 buy/sell |
| **timestamp** | T / 1000 | ts / 1000 | 毫秒时间戳转UTC |

### 2. 订单簿数据 (OrderBook Data)

#### Binance 原始数据格式
```json
{
  "lastUpdateId": 1027024,
  "bids": [
    ["4.00000000", "431.00000000"],
    ["3.99000000", "9.00000000"]
  ],
  "asks": [
    ["4.00000200", "12.00000000"],
    ["4.01000000", "18.00000000"]
  ]
}
```

#### OKX 原始数据格式
```json
{
  "arg": {
    "channel": "books",
    "instId": "BTC-USDT"
  },
  "data": [{
    "asks": [
      ["4.00000200", "12.00000000", "0", "1"],
      ["4.01000000", "18.00000000", "0", "1"]
    ],
    "bids": [
      ["4.00000000", "431.00000000", "0", "2"],
      ["3.99000000", "9.00000000", "0", "1"]
    ],
    "ts": "1672531200000",
    "seqId": 123456
  }]
}
```

#### 标准化输出格式
```python
NormalizedOrderBook(
    exchange_name="binance",
    symbol_name="BTC-USDT",
    last_update_id=1027024,
    bids=[
        PriceLevel(price=Decimal("4.00000000"), quantity=Decimal("431.00000000")),
        PriceLevel(price=Decimal("3.99000000"), quantity=Decimal("9.00000000"))
    ],
    asks=[
        PriceLevel(price=Decimal("4.00000200"), quantity=Decimal("12.00000000")),
        PriceLevel(price=Decimal("4.01000000"), quantity=Decimal("18.00000000"))
    ],
    timestamp=datetime(2023, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
)
```

### 3. 行情数据 (Ticker Data)

#### Binance 原始数据格式
```json
{
  "e": "24hrTicker",
  "E": 1672531200000,
  "s": "BTCUSDT",
  "p": "0.0015",
  "P": "0.36",
  "w": "11.35",
  "x": "0.0009",
  "c": "0.0025",
  "Q": "3",
  "b": "0.0024",
  "B": "10",
  "a": "0.0026",
  "A": "100",
  "o": "0.0010",
  "h": "0.0025",
  "l": "0.0010",
  "v": "10000",
  "q": "18",
  "O": 1672444800000,
  "C": 1672531199999,
  "F": 0,
  "L": 18150,
  "n": 18151
}
```

#### 标准化输出格式
```python
NormalizedTicker(
    exchange_name="binance",
    symbol_name="BTC-USDT",
    last_price=Decimal("0.0025"),
    open_price=Decimal("0.0010"),
    high_price=Decimal("0.0025"),
    low_price=Decimal("0.0010"),
    volume=Decimal("10000"),
    price_change=Decimal("0.0015"),
    price_change_percent=Decimal("0.36"),
    weighted_avg_price=Decimal("11.35"),
    best_bid_price=Decimal("0.0024"),
    best_bid_quantity=Decimal("10"),
    best_ask_price=Decimal("0.0026"),
    best_ask_quantity=Decimal("100"),
    trade_count=18151,
    timestamp=datetime(2023, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
)
```

### 4. 强平订单数据 (Liquidation Order Data)

#### ⚠️ 重要说明：杠杆交易强平订单的独特性
- **OKX**: 支持杠杆交易(MARGIN)和永续合约(SWAP)的强平订单按symbol订阅
- **Binance**: 仅支持期货产品的强平订单按symbol订阅，**不支持杠杆交易强平订单按symbol订阅**
- **产品类型**: MARGIN(杠杆)、SWAP(永续)、FUTURES(期货)

#### OKX 强平订单原始数据格式
```json
{
  "arg": {
    "channel": "liquidation-orders",
    "instType": "MARGIN",
    "instId": "BTC-USDT"
  },
  "data": [{
    "instType": "MARGIN",
    "instId": "BTC-USDT",
    "side": "sell",
    "sz": "0.1",
    "bkPx": "45000.5",
    "state": "filled",
    "fillSz": "0.1",
    "fillPx": "45000.5",
    "mgnRatio": "0.02",
    "ts": "1672531200000",
    "details": [{
      "tradeId": "123456789",
      "fillPx": "45000.5",
      "fillSz": "0.1",
      "ts": "1672531200000"
    }]
  }]
}
```

#### Binance 强平订单原始数据格式 (仅期货)
```json
{
  "e": "forceOrder",
  "E": 1672531200000,
  "o": {
    "s": "BTCUSDT",
    "S": "SELL",
    "o": "LIMIT",
    "f": "IOC",
    "q": "0.1",
    "p": "45000.5",
    "ap": "45000.5",
    "X": "FILLED",
    "l": "0.1",
    "z": "0.1",
    "T": 1672531200000,
    "t": 123456789
  }
}
```

#### 标准化输出格式
```python
NormalizedLiquidation(
    exchange_name="okx",                    # 交易所名称
    symbol_name="BTC-USDT",                # 统一交易对格式
    product_type=ProductType.MARGIN,        # 产品类型 (MARGIN/SWAP/FUTURES)
    instrument_id="BTC-USDT",              # 产品ID
    liquidation_id="123456789",            # 强平订单ID
    side=LiquidationSide.SELL,             # 强平方向
    status=LiquidationStatus.FILLED,       # 强平状态
    price=Decimal("45000.5"),              # 强平价格
    quantity=Decimal("0.1"),               # 强平数量
    filled_quantity=Decimal("0.1"),        # 已成交数量
    average_price=Decimal("45000.5"),      # 平均成交价格
    notional_value=Decimal("4500.05"),     # 名义价值
    liquidation_time=datetime(2023, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
    timestamp=datetime(2023, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
    margin_ratio=Decimal("0.02"),          # 保证金率 (仅OKX)
    bankruptcy_price=Decimal("45000.5"),   # 破产价格
    raw_data={...}                         # 原始数据
)
```

#### 标准化规则
| 字段 | OKX映射 | Binance映射 | 转换规则 |
|------|---------|-------------|----------|
| **exchange_name** | "okx" | "binance" | 固定值 |
| **symbol_name** | instId → 格式转换 | s → 格式转换 | 统一为 BTC-USDT 格式 |
| **product_type** | instType | 根据symbol推断 | MARGIN/SWAP/FUTURES |
| **liquidation_id** | details[0].tradeId | t | 转换为字符串 |
| **side** | side | S | 统一为 buy/sell |
| **price** | bkPx | p | 破产价格/强平价格 |
| **quantity** | sz | q | 强平数量 |
| **filled_quantity** | fillSz | z | 已成交数量 |
| **average_price** | fillPx | ap | 平均成交价格 |
| **margin_ratio** | mgnRatio | - | 仅OKX提供 |
| **timestamp** | ts / 1000 | T / 1000 | 毫秒时间戳转UTC |

### 5. 深度更新数据 (Depth Update Data)

#### Binance 深度更新格式
```json
{
  "e": "depthUpdate",
  "E": 1672531200000,
  "s": "BTCUSDT",
  "U": 157,
  "u": 160,
  "b": [
    ["0.0024", "10"],
    ["0.0023", "0"]
  ],
  "a": [
    ["0.0026", "100"],
    ["0.0027", "0"]
  ]
}
```

#### 标准化输出格式
```python
EnhancedOrderBookUpdate(
    exchange_name="binance",
    symbol_name="BTC-USDT",
    first_update_id=157,
    last_update_id=160,
    bid_updates=[
        PriceLevel(price=Decimal("0.0024"), quantity=Decimal("10")),
        PriceLevel(price=Decimal("0.0023"), quantity=Decimal("0"))  # 删除价位
    ],
    ask_updates=[
        PriceLevel(price=Decimal("0.0026"), quantity=Decimal("100")),
        PriceLevel(price=Decimal("0.0027"), quantity=Decimal("0"))  # 删除价位
    ],
    total_bid_changes=2,
    total_ask_changes=2,
    timestamp=datetime(2023, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
    is_valid=True
)
```

## 🏗️ 交易所特定处理

### Binance 数据处理特点
| 特性 | 处理方式 | 注意事项 |
|------|----------|----------|
| **交易对格式** | BTCUSDT → BTC-USDT | 自动识别计价货币 |
| **交易方向** | m字段: true=sell, false=buy | 基于maker标识 |
| **时间戳** | 毫秒级时间戳 | 需要除以1000 |
| **数量为0** | 表示删除价位 | 深度更新中的特殊处理 |
| **精度** | 字符串格式 | 转换为Decimal保持精度 |

### OKX 数据处理特点
| 特性 | 处理方式 | 注意事项 |
|------|----------|----------|
| **数据结构** | 嵌套在data数组中 | 需要提取data[0] |
| **交易对格式** | 已经是BTC-USDT格式 | 直接使用 |
| **交易方向** | 直接提供buy/sell | 无需转换 |
| **序列ID** | seqId字段 | 用于数据同步 |
| **订单簿扩展** | 4元素数组 | [价格, 数量, 废弃, 订单数] |

## 📚 API方法文档

### 核心标准化方法

#### `normalize_binance_trade(raw_data: dict) -> Optional[NormalizedTrade]`
**功能**: 标准化Binance交易数据

**输入参数**:
- `raw_data`: Binance WebSocket交易事件的原始数据

**返回值**: 
- 成功: `NormalizedTrade` 对象
- 失败: `None`

**使用示例**:
```python
normalizer = DataNormalizer()
raw_trade = {
    "e": "trade", "s": "BTCUSDT", "t": 12345,
    "p": "16569.01", "q": "0.014", "T": 1672531200000, "m": False
}
normalized = normalizer.normalize_binance_trade(raw_trade)
```

#### `normalize_okx_orderbook(raw_data: dict, symbol: str) -> Optional[NormalizedOrderBook]`
**功能**: 标准化OKX订单簿数据

**输入参数**:
- `raw_data`: OKX WebSocket订单簿事件的原始数据
- `symbol`: 交易对符号

**返回值**:
- 成功: `NormalizedOrderBook` 对象
- 失败: `None`

**异常处理**:
- 数据格式错误: 记录错误日志并返回None
- 缺少必要字段: 记录警告并尝试使用默认值
- 数值转换错误: 记录错误详情并返回None

### 工具方法

#### `_normalize_symbol_format(symbol: str) -> str`
**功能**: 统一交易对格式为 XXX-YYY

**转换规则**:
```python
# 输入 → 输出
"BTCUSDT" → "BTC-USDT"
"ETHBTC" → "ETH-BTC"
"BTC-USDT" → "BTC-USDT"  # 已标准化
"DOGEUSDT" → "DOGE-USDT"
```

**支持的计价货币**: USDT, USDC, BTC, ETH, BNB, USD, EUR, GBP, JPY

## ⚠️ 错误处理和边界情况

### 数据验证规则
1. **必要字段检查**: 验证关键字段是否存在
2. **数据类型验证**: 确保数值字段可以转换为Decimal
3. **范围验证**: 价格和数量必须为正数
4. **时间戳验证**: 时间戳必须在合理范围内

### 异常情况处理
| 异常类型 | 处理策略 | 日志级别 |
|----------|----------|----------|
| **数据缺失** | 返回None，记录警告 | WARNING |
| **格式错误** | 返回None，记录错误 | ERROR |
| **数值转换失败** | 返回None，记录错误详情 | ERROR |
| **未知交易所** | 返回None，记录警告 | WARNING |

### 降级模式
当normalizer初始化失败时，data-collector服务会以降级模式运行：
- 跳过数据标准化步骤
- 直接传递原始数据
- 记录警告日志
- 不影响其他功能模块

### 性能优化
- **缓存机制**: 交易对格式转换结果缓存
- **批量处理**: 支持批量数据标准化
- **内存管理**: 及时释放大型数据对象
- **异步处理**: 支持异步数据处理流程

## 🔍 增强订单簿处理

### EnhancedOrderBook vs NormalizedOrderBook

#### EnhancedOrderBook 特性
```python
EnhancedOrderBook(
    exchange_name="binance",
    symbol_name="BTC-USDT",
    last_update_id=1027024,
    bids=[...],
    asks=[...],
    timestamp=datetime.now(timezone.utc),
    update_type=OrderBookUpdateType.SNAPSHOT,  # 新增：更新类型
    first_update_id=1027020,                   # 新增：首次更新ID
    prev_update_id=1027023,                    # 新增：前一次更新ID
    depth_levels=20,                           # 新增：深度级别
    bid_changes=[...],                         # 新增：买单变化
    ask_changes=[...],                         # 新增：卖单变化
    removed_bids=[Decimal("100.0")],           # 新增：删除的买单价位
    removed_asks=[Decimal("101.0")],           # 新增：删除的卖单价位
    checksum=12345,                            # 新增：数据校验和
    is_valid=True                              # 新增：数据有效性标识
)
```

#### 快照 vs 增量更新
| 更新类型 | 使用场景 | 数据特点 | 处理方法 |
|----------|----------|----------|----------|
| **SNAPSHOT** | 初始化、重连 | 完整订单簿数据 | `normalize_enhanced_orderbook_from_snapshot` |
| **UPDATE** | 实时更新 | 增量变化数据 | `normalize_enhanced_orderbook_from_update` |
| **DELTA** | 高频更新 | 最小变化集 | 特殊处理逻辑 |

### 深度更新处理流程

#### 1. Binance 深度更新处理
```python
def normalize_binance_depth_update(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理Binance深度更新的特殊逻辑：
    1. 数量为0表示删除该价位
    2. U和u字段表示更新ID范围
    3. 需要验证更新连续性
    """
    try:
        # 解析增量数据
        bids = [
            PriceLevel(price=Decimal(price), quantity=Decimal(qty))
            for price, qty in raw_data.get("b", [])
        ]
        asks = [
            PriceLevel(price=Decimal(price), quantity=Decimal(qty))
            for price, qty in raw_data.get("a", [])
        ]

        return {
            "first_update_id": raw_data.get("U"),
            "last_update_id": raw_data.get("u"),
            "bids": bids,
            "asks": asks,
            "timestamp": datetime.fromtimestamp(raw_data["E"] / 1000)
        }
    except Exception as e:
        self.logger.error("Binance深度更新处理失败", exc_info=True)
        return {}
```

#### 2. OKX 深度更新处理
```python
def normalize_okx_depth_update(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理OKX深度更新的特殊逻辑：
    1. 数据嵌套在data数组中
    2. 使用seqId作为更新序列号
    3. 4元素数组格式：[价格, 数量, 废弃字段, 订单数]
    """
    try:
        if "data" not in raw_data or not raw_data["data"]:
            return {}

        data = raw_data["data"][0]

        # 处理买单更新
        bids = [
            PriceLevel(price=Decimal(bid[0]), quantity=Decimal(bid[1]))
            for bid in data.get("bids", [])
        ]

        # 处理卖单更新
        asks = [
            PriceLevel(price=Decimal(ask[0]), quantity=Decimal(ask[1]))
            for ask in data.get("asks", [])
        ]

        return {
            "last_update_id": int(data.get("seqId", 0)),
            "bids": bids,
            "asks": asks,
            "timestamp": datetime.fromtimestamp(int(data["ts"]) / 1000),
            "checksum": data.get("checksum")
        }
    except Exception as e:
        self.logger.error("OKX深度更新处理失败", exc_info=True)
        return {}
```

## 🧪 测试和验证

### 单元测试示例

#### 测试交易数据标准化
```python
import pytest
from decimal import Decimal
from datetime import datetime, timezone

def test_normalize_binance_trade():
    normalizer = DataNormalizer()

    # 测试数据
    raw_data = {
        "e": "trade",
        "E": 1672531200000,
        "s": "BTCUSDT",
        "t": 12345,
        "p": "16569.01",
        "q": "0.014",
        "T": 1672531200000,
        "m": False
    }

    # 执行标准化
    result = normalizer.normalize_binance_trade(raw_data)

    # 验证结果
    assert result is not None
    assert result.exchange_name == "binance"
    assert result.symbol_name == "BTC-USDT"
    assert result.trade_id == "12345"
    assert result.price == Decimal("16569.01")
    assert result.quantity == Decimal("0.014")
    assert result.side == "buy"
    assert isinstance(result.timestamp, datetime)
```

#### 测试交易对格式转换
```python
def test_normalize_symbol_format():
    normalizer = DataNormalizer()

    # 测试用例
    test_cases = [
        ("BTCUSDT", "BTC-USDT"),
        ("ETHBTC", "ETH-BTC"),
        ("BTC-USDT", "BTC-USDT"),
        ("DOGEUSDT", "DOGE-USDT"),
        ("ADAUSDC", "ADA-USDC"),
        ("UNKNOWN", "UNKNOWN")  # 无法识别的格式
    ]

    for input_symbol, expected_output in test_cases:
        result = normalizer._normalize_symbol_format(input_symbol)
        assert result == expected_output, f"输入: {input_symbol}, 期望: {expected_output}, 实际: {result}"
```

### 集成测试

#### 端到端数据流测试
```python
async def test_end_to_end_normalization():
    """测试完整的数据标准化流程"""
    normalizer = DataNormalizer()

    # 模拟Binance WebSocket数据
    binance_trade_data = {
        "stream": "btcusdt@trade",
        "data": {
            "e": "trade",
            "E": 1672531200000,
            "s": "BTCUSDT",
            "t": 12345,
            "p": "16569.01",
            "q": "0.014",
            "T": 1672531200000,
            "m": False
        }
    }

    # 标准化处理
    normalized_trade = normalizer.normalize_binance_trade(binance_trade_data["data"])

    # 验证标准化结果
    assert normalized_trade.exchange_name == "binance"
    assert normalized_trade.symbol_name == "BTC-USDT"
    assert normalized_trade.quote_quantity == Decimal("16569.01") * Decimal("0.014")
```

### 性能测试

#### 批量数据处理性能
```python
import time
from typing import List

def benchmark_normalization_performance():
    """测试标准化性能"""
    normalizer = DataNormalizer()

    # 生成测试数据
    test_data = []
    for i in range(10000):
        test_data.append({
            "e": "trade",
            "E": 1672531200000 + i,
            "s": "BTCUSDT",
            "t": 12345 + i,
            "p": f"{16569.01 + i * 0.01:.2f}",
            "q": "0.014",
            "T": 1672531200000 + i,
            "m": i % 2 == 0
        })

    # 性能测试
    start_time = time.time()

    results = []
    for data in test_data:
        result = normalizer.normalize_binance_trade(data)
        if result:
            results.append(result)

    end_time = time.time()

    # 性能指标
    total_time = end_time - start_time
    throughput = len(results) / total_time

    print(f"处理 {len(test_data)} 条数据")
    print(f"总耗时: {total_time:.2f} 秒")
    print(f"吞吐量: {throughput:.0f} 条/秒")
    print(f"平均延迟: {(total_time / len(results)) * 1000:.2f} 毫秒")

    # 性能要求验证
    assert throughput > 1000, f"吞吐量不足: {throughput} < 1000"
    assert (total_time / len(results)) * 1000 < 1, "平均延迟过高"
```

## 🔧 故障排除指南

### 常见问题和解决方案

#### 1. 交易对格式识别失败
**问题**: 某些交易对无法正确转换为标准格式

**原因**:
- 新的计价货币未在支持列表中
- 特殊的交易对命名规则

**解决方案**:
```python
# 在 _normalize_symbol_format 方法中添加新的计价货币
quote_currencies = [
    "USDT", "USDC", "BTC", "ETH", "BNB",
    "USD", "EUR", "GBP", "JPY",
    "BUSD", "DAI", "TUSD"  # 添加新的计价货币
]
```

#### 2. 数值精度丢失
**问题**: 价格或数量精度在转换过程中丢失

**原因**:
- 使用float而非Decimal进行数值处理
- 字符串到数值转换错误

**解决方案**:
```python
# 始终使用Decimal进行高精度计算
from decimal import Decimal, getcontext

# 设置精度
getcontext().prec = 28

# 正确的转换方式
price = Decimal(str(raw_data["price"]))  # 先转字符串再转Decimal
```

#### 3. 时间戳处理错误
**问题**: 时间戳转换后时区不正确

**原因**:
- 未指定UTC时区
- 毫秒和秒时间戳混用

**解决方案**:
```python
from datetime import datetime, timezone

# 正确的时间戳处理
if timestamp > 1e12:  # 毫秒时间戳
    dt = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
else:  # 秒时间戳
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
```

### 调试技巧

#### 启用详细日志
```python
import structlog

# 配置详细日志
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)
```

#### 数据验证工具
```python
def validate_normalized_data(data):
    """验证标准化数据的完整性"""
    if isinstance(data, NormalizedTrade):
        assert data.price > 0, "价格必须为正数"
        assert data.quantity > 0, "数量必须为正数"
        assert data.side in ["buy", "sell"], "交易方向必须是buy或sell"
        assert "-" in data.symbol_name, "交易对格式必须包含连字符"

    elif isinstance(data, NormalizedOrderBook):
        assert len(data.bids) > 0 or len(data.asks) > 0, "订单簿不能为空"
        for bid in data.bids:
            assert bid.price > 0 and bid.quantity >= 0, "买单价格和数量必须有效"
        for ask in data.asks:
            assert ask.price > 0 and ask.quantity >= 0, "卖单价格和数量必须有效"
```

---

**文档版本**: 1.0.0
**最后更新**: 2025-06-29
**维护团队**: MarketPrism Development Team
