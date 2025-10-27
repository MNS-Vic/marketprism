# MarketPrism Data Collector

MarketPrism 统一数据收集器，支持多交易所、多数据类型的实时数据采集。

## 功能特性

### 支持的交易所
- **Binance**：现货、USDS-M 永续合约
- **OKX**：现货、USDT 永续合约
- **Deribit**：期权、永续合约

### 支持的数据类型
- **Orderbook**：订单簿数据（增量模式 / 快照模式）
- **Trade**：成交数据
- **Funding Rate**：资金费率
- **Open Interest**：持仓量
- **Liquidation**：清算数据
- **Volatility Index**：波动率指数
- **LSR**：多空比数据

---

## Orderbook 采集模式

### 1. 增量模式（Incremental Mode）- 默认

通过 WebSocket 订阅增量更新，本地维护完整 orderbook 状态。

**优点**：
- 数据实时性高
- 网络带宽占用低

**缺点**：
- 需要本地状态维护
- 高频场景下可能跟不上推送速率

**配置示例**：
```yaml
orderbook:
  method: websocket  # 或不配置（默认）
  depth_limit: 500
  update_frequency: 100
```

### 2. 快照模式（Snapshot Mode）- 新增

定时轮询交易所完整快照，无需本地状态维护。

**优点**：
- 无本地状态，简单可靠
- 适合高频场景
- 数据一致性有保障

**缺点**：
- 网络带宽占用较高
- 受交易所 API 限流约束

**配置示例**：
```yaml
orderbook:
  method: snapshot
  snapshot_interval: 1      # 轮询间隔（秒）
  snapshot_depth: 100       # 快照深度（档位）
  request_timeout: 0.9      # 请求超时（秒）
```

**支持的交易所**：
- Binance Spot（REST）
- Binance Derivatives（WebSocket API）
- OKX Spot（REST）
- OKX Derivatives（REST）

**详细文档**：[Snapshot 模式运维指南](docs/SNAPSHOT_MODE_GUIDE.md)

---

## 快速开始

### 1. 安装依赖

```bash
cd services/data-collector
pip install -r requirements.txt
```

### 2. 配置文件

编辑 `config/collector/unified_data_collection.yaml`：

```yaml
exchanges:
  binance_spot:
    enabled: true
    symbols:
    - BTCUSDT
    - ETHUSDT
    data_types:
    - orderbook
    orderbook:
      method: snapshot        # 启用快照模式
      snapshot_interval: 1
      snapshot_depth: 100
```

### 3. 启动服务

```bash
# 本地运行
python3 main.py --mode launcher --config config/collector/unified_data_collection.yaml

# Docker 运行
docker-compose up -d
```

---

## 监控与运维

### 检查运行状态

```bash
# 查看日志
docker logs -f marketprism-data-collector

# 查看进程
ps aux | grep "python.*collector"
```

### 检查数据入库

```sql
-- ClickHouse 查询
SELECT 
    exchange, 
    symbol, 
    count(*) as records,
    max(timestamp) as latest
FROM marketprism_hot.orderbooks
WHERE timestamp > now() - INTERVAL 5 MINUTE
GROUP BY exchange, symbol;
```

### 性能指标

- **快照成功率**：>99%
- **请求延迟（P99）**：<500ms
- **数据入库频率**：1 条/秒/符号（snapshot 模式）
- **内存使用**：<200MB

---

## 故障排查

### 问题：快照获取失败

**症状**：日志中出现 "fetch failed" 或 "timeout"

**解决方案**：
1. 检查网络连接
2. 检查交易所 API 限流
3. 调整 `request_timeout` 设置

### 问题：数据入库频率低

**症状**：ClickHouse 查询显示 records_per_sec < 1

**解决方案**：
1. 检查 Collector 日志
2. 检查 NATS 连接
3. 检查 data-storage-service 状态

详细故障排查指南：[Snapshot 模式运维指南](docs/SNAPSHOT_MODE_GUIDE.md#故障排查)

---

## 配置参考

### Snapshot 模式配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `method` | string | `websocket` | 采集模式：`websocket` 或 `snapshot` |
| `snapshot_interval` | float | `1.0` | 轮询间隔（秒） |
| `snapshot_depth` | int | `100` | 快照深度（档位） |
| `request_timeout` | float | `0.9` | 请求超时（秒） |
| `rest_base` | string | - | REST API 基础 URL（可选） |
| `ws_api_url` | string | - | WebSocket API URL（仅 Binance Derivatives） |

### 增量模式配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `depth_limit` | int | `500` | 本地维护的最大深度 |
| `update_frequency` | int | `100` | 更新频率（毫秒） |
| `buffer_max_size` | int | `5000` | 缓冲区大小 |
| `validation_enabled` | bool | `true` | 是否启用数据校验 |

---

## 开发与测试

### 运行单元测试

```bash
cd services/data-collector
python3 -m pytest tests/ -v
```

### 运行 Snapshot 模式测试

```bash
python3 -m pytest tests/test_orderbook_snap_managers.py -v
```

---

## 架构设计

### Snapshot 模式架构

```
┌─────────────────┐
│  Main Process   │
└────────┬────────┘
         │
         ├─── OrderBookSnapManagerFactory
         │    └─── 根据 exchange + market_type 创建对应 Manager
         │
         ├─── BinanceSpotSnapManager (REST)
         │    └─── GET /api/v3/depth
         │
         ├─── BinanceDerivativesSnapManager (WS API)
         │    └─── wss://ws-fapi.binance.com/ws-fapi/v1
         │         └─── 单长连复用 + 请求-响应匹配
         │
         ├─── OKXSpotSnapManager (REST)
         │    └─── GET /api/v5/market/books
         │
         └─── OKXDerivativesSnapManager (REST)
              └─── GET /api/v5/market/books
```

### 数据流

```
Exchange API
    ↓
Snapshot Manager (fetch)
    ↓
Normalizer (standardize)
    ↓
NATS Publisher (Core NATS)
    ↓
Data Storage Service
    ↓
ClickHouse (hot/cold storage)
```

---

## 相关文档

- [Snapshot 模式运维指南](docs/SNAPSHOT_MODE_GUIDE.md)
- [Snapshot 模式实施方案](/home/ubuntu/marketprism/orderbook_snapshot_implementation_plan.md)
- [多进程架构设计](docs/phase2_multiprocess_plan.md)

---

## 许可证

Copyright © 2024 MarketPrism. All rights reserved.

