# MarketPrism 数据标准化概览

## 快速概览

MarketPrism系统将来自不同交易所的原始数据转换为统一的标准格式，支持现货、期货、期权等多种市场类型。

## 支持的交易所

| 交易所 | 市场类型 | 数据类型 | 特殊功能 |
|--------|----------|----------|----------|
| **Binance** | 现货 | 交易、订单簿、行情 | 高频数据 |
| **OKX** | 现货、期货 | 交易、订单簿、行情、资金费率 | 衍生品支持 |
| **Deribit** | 衍生品、期权 | 交易、订单簿、行情、希腊字母 | 期权专业数据 |

## 标准化数据格式

### 交易数据 (NormalizedTrade)
```json
{
  "exchange_name": "binance",
  "symbol_name": "BTC/USDT",
  "trade_id": "12345",
  "price": "50000.00",
  "quantity": "0.001",
  "quote_quantity": "50.00",
  "timestamp": "2024-01-01T12:00:00Z",
  "is_buyer_maker": false
}
```

### 订单簿数据 (NormalizedOrderBook)
```json
{
  "exchange_name": "okx",
  "symbol_name": "BTC-USDT",
  "bids": [
    {"price": "49999.99", "quantity": "1.5"},
    {"price": "49999.98", "quantity": "2.0"}
  ],
  "asks": [
    {"price": "50000.01", "quantity": "1.2"},
    {"price": "50000.02", "quantity": "0.8"}
  ],
  "timestamp": "2024-01-01T12:00:00Z"
}
```

### 行情数据 (NormalizedTicker)
```json
{
  "exchange_name": "deribit",
  "symbol_name": "BTC-PERPETUAL",
  "last_price": "50000.00",
  "open_price": "49500.00",
  "high_price": "50200.00",
  "low_price": "49300.00",
  "volume": "1234.56",
  "price_change": "500.00",
  "price_change_percent": "1.01",
  "timestamp": "2024-01-01T12:00:00Z"
}
```

## 字段映射对照表

### 交易数据字段映射
| 标准字段 | Binance | OKX | Deribit | 说明 |
|---------|---------|-----|---------|------|
| symbol_name | `s` | `instId` | 从channel提取 | 交易对标识 |
| trade_id | `t` | `tradeId` | `trade_id` | 交易唯一ID |
| price | `p` | `px` | `price` | 成交价格 |
| quantity | `q` | `sz` | `amount` | 成交数量 |
| timestamp | `T` | `ts` | `timestamp` | 成交时间（毫秒） |
| is_buyer_maker | `m` | `side=="sell"` | `direction=="sell"` | 买方是否为做市方 |

### 时间戳处理
- **所有交易所**：毫秒级时间戳，统一转换为UTC datetime
- **处理方式**：`timestamp > 1e10` 时除以1000转换为秒

### 交易方向转换
- **Binance**：`m` 字段直接使用
- **OKX**：`side == "sell"` 表示买方为maker
- **Deribit**：`direction == "sell"` 表示买方为maker

## 数据流架构

```
原始数据 → 适配器 → 标准化 → NATS → 存储/分析
   ↓         ↓        ↓       ↓        ↓
Binance → BinanceAdapter → NormalizedTrade → market.binance.btc-usdt.trade → ClickHouse
  OKX   → OKXAdapter     → NormalizedTrade → market.okx.btc-usdt.trade     → ClickHouse
Deribit → DeribitAdapter → NormalizedTrade → market.deribit.btc-usdt.trade → ClickHouse
```

## 配置示例

### Binance配置
```yaml
exchange: "binance"
market_type: "spot"
symbols: ["BTCUSDT", "ETHUSDT"]  # 原始格式，会标准化为BTC-USDT
data_types: ["trade", "orderbook", "ticker"]
ws_url: "wss://stream.binance.com:9443"
```

### OKX配置
```yaml
exchange: "okx"
market_type: "futures"
symbols: ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]  # 原始格式，会标准化为BTC-USDT
data_types: ["trade", "orderbook", "ticker", "funding_rate"]
ws_url: "wss://ws.okx.com:8443"
```

### Deribit配置
```yaml
exchange: "deribit"
market_type: "derivatives"
symbols: ["BTC-PERPETUAL", "ETH-PERPETUAL"]
data_types: ["trade", "orderbook", "ticker", "funding_rate", "open_interest"]
ws_url: "wss://www.deribit.com/ws/api/v2"
```

## 性能指标

### 处理性能
- **单条数据标准化**：< 1ms
- **批量处理（1000条）**：< 100ms
- **内存使用**：每条记录约 200 bytes

### 数据质量
- **成功率**：> 99.9%
- **精度**：Decimal类型，8位小数精度
- **延迟**：端到端 < 10ms

## 错误处理

### 常见错误类型
1. **缺少必填字段**：记录错误，跳过该条数据
2. **数据格式错误**：尝试修复，失败则丢弃
3. **网络异常**：自动重连，指数退避
4. **精度溢出**：使用Decimal类型避免

### 监控指标
- 处理成功率
- 平均处理时间
- 错误分类统计
- 数据质量评分

## 扩展新交易所

### 步骤概览
1. 创建适配器类继承 `ExchangeAdapter`
2. 实现标准化方法：`normalize_trade()`, `normalize_orderbook()`, `normalize_ticker()`
3. 添加配置文件到 `config/exchanges/`
4. 编写单元测试和集成测试
5. 更新文档

### 示例代码框架
```python
class NewExchangeAdapter(ExchangeAdapter):
    async def normalize_trade(self, raw_data: Dict[str, Any]) -> Optional[NormalizedTrade]:
        return NormalizedTrade(
            exchange_name="new_exchange",
            symbol_name=raw_data["symbol"],
            trade_id=str(raw_data["id"]),
            price=self._safe_decimal(raw_data["price"]),
            quantity=self._safe_decimal(raw_data["amount"]),
            quote_quantity=price * quantity,
            timestamp=self._safe_timestamp(raw_data["timestamp"]),
            is_buyer_maker=raw_data["side"] == "sell"
        )
```

## 相关文档

- [详细技术规范](development/数据标准化规范.md) - 完整的实现细节和API文档
- [TDD测试报告](../TDD_真实数据测试总结.md) - 真实数据测试结果
- [Deribit集成报告](../Deribit_集成测试报告.md) - 衍生品交易所集成详情

## 快速开始

1. **查看现有适配器**：`services/python-collector/src/marketprism_collector/exchanges/`
2. **运行测试**：`pytest tests/integration/test_python_collector_integration.py`
3. **查看配置**：`config/exchanges/`
4. **监控数据流**：`python quick_listen.py`

---

*更新时间：2024年11月* 