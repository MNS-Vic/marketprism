# Trade数据标准化规范

## 概述

MarketPrism系统对所有交易所的trade数据进行统一标准化处理，确保数据格式一致性和业务逻辑统一。

## 标准化后的数据格式

### NormalizedTrade数据结构

```python
class NormalizedTrade(BaseModel):
    # 基础信息
    exchange_name: str              # 交易所名称 (binance/okx)
    symbol_name: str               # 标准交易对格式 (BTC-USDT)
    currency: str                  # 币种名称 (BTC)
    
    # 核心交易数据
    trade_id: str                  # 交易ID
    price: Decimal                 # 成交价格 (高精度)
    quantity: Decimal              # 成交数量 (高精度)
    quote_quantity: Decimal        # 成交金额 (price * quantity)
    side: str                      # 交易方向: buy(主动买入) 或 sell(主动卖出)
    
    # 时间信息
    timestamp: datetime            # 成交时间 (UTC)
    event_time: datetime           # 事件时间 (UTC)
    
    # 交易类型和元数据
    trade_type: str               # 交易类型: spot/perpetual/futures
    is_maker: Optional[bool]      # 买方是否为做市方(仅Binance提供,OKX为None)
    
    # 归集交易特有字段 (仅Binance期货)
    agg_trade_id: Optional[str]   # 归集交易ID
    first_trade_id: Optional[str] # 首个交易ID
    last_trade_id: Optional[str]  # 末次交易ID
    
    # 原始数据
    raw_data: Dict[str, Any]      # 原始WebSocket数据
```

## 交易所特定处理逻辑

### Binance现货 (normalize_binance_spot_trade)

**原始数据格式**：
```json
{
  "e": "trade",        // 事件类型
  "E": 1672515782136,  // 事件时间
  "s": "BNBBTC",       // 交易对
  "t": 12345,          // 交易ID
  "p": "0.001",        // 成交价格
  "q": "100",          // 成交数量
  "T": 1672515782136,  // 成交时间
  "m": true            // 买方是否是做市方
}
```

**关键转换逻辑**：
- `side`: `"sell" if data["m"] else "buy"`
- `is_maker`: `data["m"]`
- `trade_type`: `"spot"`

### Binance期货/永续 (normalize_binance_futures_trade)

**原始数据格式**：
```json
{
  "e": "aggTrade",  // 事件类型
  "E": 123456789,   // 事件时间
  "s": "BNBUSDT",   // 交易对
  "a": 5933014,     // 归集成交ID
  "p": "0.001",     // 成交价格
  "q": "100",       // 成交量
  "f": 100,         // 被归集的首个交易ID
  "l": 105,         // 被归集的末次交易ID
  "T": 123456785,   // 成交时间
  "m": true         // 买方是否是做市方
}
```

**关键转换逻辑**：
- `side`: `"sell" if data["m"] else "buy"`
- `is_maker`: `data["m"]`
- `trade_type`: `"perpetual"`
- `agg_trade_id`: `data["a"]`

### OKX (normalize_okx_trade)

**原始数据格式**：
```json
{
  "arg": {
    "channel": "trades",
    "instId": "BTC-USDT"
  },
  "data": [{
    "instId": "BTC-USDT",
    "tradeId": "130639474",
    "px": "42219.9",
    "sz": "0.12060306",
    "side": "buy",
    "ts": "1629386781174"
  }]
}
```

**关键转换逻辑**：
- `side`: 直接使用 `data["side"]`
- `is_maker`: `None` (OKX不提供此信息)
- `trade_type`: 根据`instId`自动检测或传入参数
- `event_time`: 与`timestamp`相同

## 字段映射对比

| 字段 | Binance现货 | Binance期货 | OKX | 说明 |
|------|-------------|-------------|-----|------|
| exchange_name | "binance" | "binance" | "okx" | 固定值 |
| symbol_name | 标准化后 | 标准化后 | 直接使用 | BTC-USDT格式 |
| trade_id | data["t"] | data["a"] | data["tradeId"] | 字符串格式 |
| side | 根据m字段转换 | 根据m字段转换 | 直接使用 | buy/sell |
| is_maker | data["m"] | data["m"] | None | 仅Binance提供 |
| trade_type | "spot" | "perpetual" | 自动检测 | 市场类型 |

## 统一性保证

### 1. 交易方向统一
- 所有交易所统一使用`side`字段表示交易方向
- `buy`: 主动买入（taker买入）
- `sell`: 主动卖出（taker卖出）

### 2. 时间格式统一
- 所有时间戳转换为UTC时区的datetime对象
- Binance: 毫秒时间戳 / 1000
- OKX: 毫秒时间戳 / 1000

### 3. 精度统一
- 价格和数量使用Decimal类型保证高精度
- 成交金额自动计算：`price * quantity`

### 4. 符号格式统一
- 所有交易对标准化为`BTC-USDT`格式
- 币种提取为基础货币：`BTC-USDT` → `BTC`

## 冗余字段处理

### 已解决的冗余问题
1. **删除重复的标准化方法**：
   - 删除旧版本的`normalize_okx_trade()` (第399行)
   - 删除旧版本的`normalize_binance_trade()` (第464行)
   - 保留专用方法：`normalize_binance_spot_trade()`, `normalize_binance_futures_trade()`, `normalize_okx_trade()`

2. **字段逻辑优化**：
   - 保留`side`字段作为主要交易方向标识
   - 保留`is_maker`字段作为可选的做市方信息（仅Binance提供）
   - 明确字段含义和使用场景

## 使用示例

```python
# Binance现货
normalized_trade = normalizer.normalize_binance_spot_trade(raw_data)

# Binance期货/永续
normalized_trade = normalizer.normalize_binance_futures_trade(raw_data)

# OKX (自动检测交易类型)
normalized_trade = normalizer.normalize_okx_trade(raw_data, trade_type="auto")

# OKX (指定交易类型)
normalized_trade = normalizer.normalize_okx_trade(raw_data, trade_type="spot")
```

## 质量保证

1. **数据完整性**：所有必需字段都有值
2. **类型安全**：使用Pydantic进行数据验证
3. **错误处理**：标准化失败时返回None并记录日志
4. **原始数据保留**：`raw_data`字段保存原始WebSocket数据用于调试
