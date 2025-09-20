# MarketPrism统一字段命名标准

## 1. 基础字段标准（所有数据类型通用）

| 字段名 | 数据类型 | 格式标准 | 说明 |
|--------|----------|----------|------|
| `timestamp` | String | `YYYY-MM-DD HH:MM:SS` | ClickHouse DateTime格式，UTC时区 |
| `exchange` | String | 小写字母 | 交易所标识：binance, okx, deribit |
| `market_type` | String | 小写字母 | 市场类型：spot, perpetual, futures |
| `symbol` | String | 大写-分隔 | 交易对格式：BTC-USDT, ETH-USDT |
| `data_source` | String | 固定值 | 固定为 'marketprism' |

## 2. 各数据类型专用字段标准

### 2.1 订单簿数据 (orderbooks)
| 字段名 | 数据类型 | 格式 | 说明 |
|--------|----------|------|------|
| `last_update_id` | Integer | 数字 | 最后更新ID |
| `best_bid_price` | String | 数字字符串 | 最优买价 |
| `best_ask_price` | String | 数字字符串 | 最优卖价 |
| `bids` | String | JSON字符串 | 买单深度数据 |
| `asks` | String | JSON字符串 | 卖单深度数据 |

### 2.2 交易数据 (trades)
| 字段名 | 数据类型 | 格式 | 说明 |
|--------|----------|------|------|
| `trade_id` | String | 字符串 | 交易唯一标识 |
| `price` | String | 数字字符串 | 成交价格 |
| `quantity` | String | 数字字符串 | 成交数量 |
| `side` | String | buy/sell | 交易方向 |
| `is_maker` | Boolean | true/false | 是否为做市方 |

### 2.3 资金费率数据 (funding_rates)
| 字段名 | 数据类型 | 格式 | 说明 |
|--------|----------|------|------|
| `funding_rate` | String | 数字字符串 | 当前资金费率 |
| `funding_time` | String | `YYYY-MM-DD HH:MM:SS` | 资金费率时间 |
| `next_funding_time` | String | `YYYY-MM-DD HH:MM:SS` | 下次资金费率时间 |

### 2.4 未平仓量数据 (open_interests)
| 字段名 | 数据类型 | 格式 | 说明 |
|--------|----------|------|------|
| `open_interest` | String | 数字字符串 | 未平仓量 |
| `open_interest_value` | String | 数字字符串 | 未平仓价值 |

### 2.5 强平数据 (liquidations)
| 字段名 | 数据类型 | 格式 | 说明 |
|--------|----------|------|------|
| `side` | String | buy/sell | 强平方向 |
| `price` | String | 数字字符串 | 强平价格 |
| `quantity` | String | 数字字符串 | 强平数量 |

### 2.6 LSR顶级持仓数据 (lsr_top_positions)
| 字段名 | 数据类型 | 格式 | 说明 |
|--------|----------|------|------|
| `long_position_ratio` | String | 数字字符串 | 多头持仓比例 |
| `short_position_ratio` | String | 数字字符串 | 空头持仓比例 |
| `period` | String | 时间周期 | 统计周期：5m, 15m, 1h |

### 2.7 LSR全账户数据 (lsr_all_accounts)
| 字段名 | 数据类型 | 格式 | 说明 |
|--------|----------|------|------|
| `long_account_ratio` | String | 数字字符串 | 多头账户比例 |
| `short_account_ratio` | String | 数字字符串 | 空头账户比例 |
| `period` | String | 时间周期 | 统计周期：5m, 15m, 1h |

### 2.8 波动率指数数据 (volatility_indices)
| 字段名 | 数据类型 | 格式 | 说明 |
|--------|----------|------|------|
| `index_value` | String | 数字字符串 | 波动率指数值 |
| `underlying_asset` | String | 大写字母 | 标的资产：BTC, ETH |

## 3. 禁用字段列表

以下字段不应出现在最终数据中：
- `data_type` - 通过NATS主题确定数据类型
- `normalized` - 内部处理标记
- `normalizer_version` - 内部版本标记
- `publisher` - 内部发布者标记
- `normalized_at` - 内部处理时间
- `exchange_name` - 使用 `exchange` 替代
- `symbol_name` - 使用 `symbol` 替代

## 4. 时间戳处理标准

### 4.1 统一时间格式
```python
# ✅ 正确格式（ClickHouse兼容）
timestamp = "2025-08-04 16:00:00"

# ❌ 错误格式（ISO 8601）
timestamp = "2025-08-04T16:00:00+00:00"
```

### 4.2 时间戳转换规则
```python
def format_timestamp_for_clickhouse(dt: datetime) -> str:
    """统一的ClickHouse时间戳格式化"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime('%Y-%m-%d %H:%M:%S')

def parse_timestamp_ms(timestamp_ms: int) -> str:
    """毫秒时间戳转ClickHouse格式"""
    dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    return format_timestamp_for_clickhouse(dt)
```

## 5. 数据类型转换标准

### 5.1 数值字段处理
```python
# 所有价格、数量字段统一转为字符串
price = str(decimal_value)
quantity = str(decimal_value)
```

### 5.2 JSON字段处理
```python
# bids/asks等复杂数据转为JSON字符串
bids = json.dumps(bids_list)
asks = json.dumps(asks_list)
```

### 5.3 布尔字段处理
```python
# 布尔值保持原始类型
is_maker = True  # 或 False
```

## 6. 字段验证规则

### 6.1 必需字段检查
每种数据类型都必须包含基础字段：
- `timestamp`
- `exchange` 
- `market_type`
- `symbol`
- `data_source`

### 6.2 字段值验证
- `exchange`: 必须在允许列表中 ['binance', 'okx', 'deribit']
- `market_type`: 必须在允许列表中 ['spot', 'perpetual', 'futures']
- `symbol`: 必须符合 XXX-XXX 格式
- `side`: 必须是 'buy' 或 'sell'
- 数值字段：必须是有效的数字字符串

## 7. 实施检查清单

### 7.1 Normalizer修改检查
- [ ] 移除所有禁用字段
- [ ] 统一时间戳格式为ClickHouse兼容格式
- [ ] 确保字段名与ClickHouse表结构完全匹配
- [ ] 添加字段值验证

### 7.2 存储服务修改检查
- [ ] 移除字段映射和转换逻辑
- [ ] 简化数据处理流程
- [ ] 确保批处理正常工作

### 7.3 测试验证检查
- [ ] 验证所有8种数据类型的字段匹配
- [ ] 验证时间戳格式兼容性
- [ ] 验证数据写入成功率
- [ ] 验证批处理性能
