# MarketPrism 多交易所数据采集与模型训练计划

## 项目概述

为量化交易模型提供全面的多维度市场数据，通过集成多个交易所(Binance、OKEx、Deribit)的数据源，扩展数据维度，最终实现BTC、ETH现货和永续合约的模型交易。

## 1. 交易所数据源扩展

### 1.1 OKEx集成

- **API文档**: https://www.okx.com/docs-v5/
- **数据维度**:
  - 订单簿深度(实时)
  - 逐笔成交(实时)
  - 多空持仓比(每15分钟)
  - 爆仓订单(实时)
  - 资金费率(每8小时)
  - **精英交易员持仓**(每小时)
- **采集配置**:
  ```yaml
  okex:
    api_version: "5"
    symbols: ["BTC-USDT", "ETH-USDT"]
    data_types: ["tickers", "trades", "books", "mark-price", "liquidation-orders", "elite-traders"]
    elite_traders:
      update_interval: 3600  # 每小时更新一次(秒)
      top_n: 100            # 获取前100名精英交易员数据
  ```

### 1.2 Deribit集成

- **API文档**: https://docs.deribit.com/
- **数据维度**:
  - 期权订单簿(实时)
  - 期权成交(实时)
  - 隐含波动率面(每分钟)
  - 平台指数(实时)
- **采集配置**:
  ```yaml
  deribit:
    symbols: ["BTC-PERPETUAL", "ETH-PERPETUAL"]
    options: ["BTC-*-*-*", "ETH-*-*-*"]  # 所有BTC和ETH期权
    data_types: ["book", "trades", "volatility", "index"]
  ```

## 2. 数据统一格式中间层

### 2.1 统一数据结构

| 数据类型 | 统一模型 | 标准化字段 |
|---------|---------|------------|
| 订单簿 | `UnifiedOrderBook` | symbol, timestamp, bids[], asks[], source |
| 逐笔成交 | `UnifiedTrade` | symbol, trade_id, price, quantity, timestamp, side, source |
| 多空持仓 | `UnifiedLongShortRatio` | symbol, timestamp, long_ratio, short_ratio, source |
| 爆仓订单 | `UnifiedLiquidation` | symbol, timestamp, price, quantity, side, source |

### 2.2 中间层处理流程

```mermaid
graph LR
    RD[原始数据] --> PM[解析器]
    PM --> NM[标准化]
    NM --> QC[质量检查]
    QC --> OP[输出]
    
    style RD fill:#4da6ff,stroke:#0066cc
    style PM fill:#5fd94d,stroke:#3da336
    style NM fill:#d971ff,stroke:#a33bc2
    style QC fill:#ffa64d,stroke:#cc7a30
    style OP fill:#ff5555,stroke:#cc0000
```

## 3. 数据库结构扩展

### 3.1 新增数据表

```sql
-- 期权隐含波动率表
CREATE TABLE marketprism.implied_volatility (
    symbol String,
    expiry_date DateTime,
    strike_price Float64,
    call_iv Float64,
    put_iv Float64,
    timestamp DateTime,
    source String,
    date Date DEFAULT toDate(timestamp)
) ENGINE = MergeTree()
PARTITION BY date
ORDER BY (symbol, expiry_date, strike_price, timestamp);

-- 精英交易员持仓表
CREATE TABLE marketprism.okex_elite_traders (
    symbol String,
    long_account_num UInt32,
    short_account_num UInt32,
    long_short_ratio Float64,
    long_account Float64,
    short_account Float64,
    timestamp DateTime,
    date Date DEFAULT toDate(timestamp)
) ENGINE = MergeTree()
PARTITION BY date
ORDER BY (symbol, timestamp);
```

### 3.2 数据关联查询设计

```sql
-- 跨交易所价格差异查询示例
SELECT 
    a.timestamp,
    a.symbol,
    a.price as binance_price,
    b.price as okex_price,
    ((a.price - b.price) / a.price) * 100 as price_diff_percent
FROM 
    marketprism.trades a
JOIN 
    (SELECT timestamp, symbol, price FROM marketprism.trades WHERE source = 'okex') b
ON 
    a.symbol = b.symbol
    AND a.timestamp = b.timestamp
WHERE 
    a.source = 'binance'
    AND abs(a.timestamp - b.timestamp) < 1
```

## 4. 代码实现计划

### 4.1 Go收集器扩展

| 文件 | 功能 | 优先级 |
|------|------|--------|
| `services/go-collector/internal/okex/client.go` | OKEx连接与基础数据采集 | 高 |
| `services/go-collector/internal/okex/elite_traders.go` | 精英交易员数据采集 | 高 |
| `services/go-collector/internal/deribit/client.go` | Deribit连接与基础数据采集 | 中 |
| `services/go-collector/internal/deribit/options.go` | 期权数据采集 | 中 |
| `services/go-collector/internal/models/unified.go` | 统一数据模型定义 | 高 |

### 4.2 Python数据处理服务扩展

| 文件 | 功能 | 优先级 |
|------|------|--------|
| `services/data-normalizer/normalizer.py` | 数据标准化处理 | 高 |
| `services/data-normalizer/models.py` | Python统一数据模型 | 高 |
| `services/ingestion/feature_engineering.py` | 特征工程处理 | 中 |
| `services/ingestion/indicators.py` | 交易指标计算 | 中 |

## 5. 模型训练特征工程

### 5.1 市场微观结构特征

- 订单簿不平衡指标
- 订单簿形状特征提取
- 交易规模分布特征

### 5.2 情绪与预期特征

- 精英交易员持仓变化率
- 期权隐含波动率曲面
- 多空持仓分布

### 5.3 跨市场特征

- 交易所间价格偏差
- 流动性差异指标
- 期现价差

## 6. 实施时间线

| 阶段 | 任务 | 预计时间 | 负责人 |
|------|------|----------|--------|
| 1 | OKEx基础数据集成 | 2周 | 待分配 |
| 2 | OKEx精英交易员数据集成 | 1周 | 待分配 |
| 3 | 数据标准化中间层 | 2周 | 待分配 |
| 4 | Deribit期权数据集成 | 3周 | 待分配 |
| 5 | 数据库结构扩展 | 1周 | 待分配 |
| 6 | 特征工程开发 | 3周 | 待分配 |
| 7 | 测试与质量验证 | 2周 | 待分配 |

## 7. 风险与缓解措施

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|------|------|----------|
| API限流 | 中 | 高 | 实现请求节流和备用服务器 |
| 数据格式变更 | 低 | 高 | 监控API更新，自动化测试 |
| 性能瓶颈 | 中 | 中 | 增加缓存层，优化查询 |
| 数据一致性 | 中 | 高 | 实现校验机制和数据修复流程 |

## 8. 监控与维护计划

- **数据质量监控**：定期检查各数据源的完整性和准确性
- **性能监控**：监控数据处理延迟和存储性能
- **告警机制**：为数据中断和API错误设置告警
- **定期审计**：每月审计数据质量和模型性能

---

版本: 1.0.0  
创建日期: 2025-05-01  
上次更新: 2025-05-01 