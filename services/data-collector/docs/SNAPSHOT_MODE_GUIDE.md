# Orderbook Snapshot 模式运维指南

## 概述

Orderbook Snapshot 模式是一种定时轮询交易所快照的数据采集方式，与传统的增量 WebSocket 订阅模式不同。该模式适用于高频交易场景下本地 orderbook 维护跟不上交易所推送速率的情况。

### 核心特性

- **固定频率轮询**：默认 1 秒/次，不动态调整
- **固定深度**：默认 100 档（可配置）
- **无本地状态维护**：每次获取完整快照，无需本地增量计算
- **长连复用**：Binance Derivatives 使用单个 WebSocket 连接处理多个符号
- **会话复用**：REST 管理器使用 aiohttp 会话池复用 HTTP 连接
- **超时跳过**：单次请求超时后跳过本 tick，不影响下一 tick
- **自动重连**：WebSocket 连接断线后自动重连（指数退避）

---

## 支持的交易所

| 交易所 | 市场类型 | 实现方式 | 端点 |
|--------|---------|---------|------|
| Binance | Spot | REST | `GET /api/v3/depth` |
| Binance | Derivatives (USDS-M) | WebSocket API | `wss://ws-fapi.binance.com/ws-fapi/v1` |
| OKX | Spot | REST | `GET /api/v5/market/books` |
| OKX | Derivatives (Perpetual) | REST | `GET /api/v5/market/books` |

---

## 配置说明

### 启用 Snapshot 模式

在 `unified_data_collection.yaml` 中为指定交易所的 `orderbook` 配置添加以下字段：

```yaml
exchanges:
  binance_spot:
    # ... 其他配置 ...
    orderbook:
      method: snapshot                    # 必需：启用 snapshot 模式
      snapshot_interval: 1                # 可选：轮询间隔（秒），默认 1
      snapshot_depth: 100                 # 可选：快照深度（档位），默认 100
      rest_base: https://api.binance.com  # 可选：REST API 基础 URL
      request_timeout: 0.9                # 可选：单次请求超时（秒），默认 0.9
```

### 完整配置示例

#### Binance Spot（REST）

```yaml
binance_spot:
  name: binance_spot
  exchange: binance_spot
  market_type: spot
  enabled: true
  api:
    base_url: https://api.binance.com
    ws_url: wss://stream.binance.com:9443/ws
  symbols:
  - BTCUSDT
  - ETHUSDT
  data_types:
  - orderbook
  orderbook:
    method: snapshot
    snapshot_interval: 1
    snapshot_depth: 100
    rest_base: https://api.binance.com
    request_timeout: 0.9
```

#### Binance Derivatives（WebSocket API）

```yaml
binance_derivatives:
  name: binance_derivatives
  exchange: binance_derivatives
  market_type: perpetual
  enabled: true
  api:
    base_url: https://fapi.binance.com
    ws_url: wss://fstream.binance.com/ws
  symbols:
  - BTCUSDT
  - ETHUSDT
  data_types:
  - orderbook
  orderbook:
    method: snapshot
    snapshot_interval: 1
    snapshot_depth: 100
    ws_api_url: wss://ws-fapi.binance.com/ws-fapi/v1
    request_timeout: 0.8
```

#### OKX Spot（REST）

```yaml
okx_spot:
  name: okx_spot
  exchange: okx_spot
  market_type: spot
  enabled: true
  api:
    base_url: https://www.okx.com
    ws_url: wss://ws.okx.com:8443/ws/v5/public
  symbols:
  - BTC-USDT
  - ETH-USDT
  data_types:
  - orderbook
  orderbook:
    method: snapshot
    snapshot_interval: 1
    snapshot_depth: 100
    rest_base: https://www.okx.com
    request_timeout: 0.9
```

#### OKX Derivatives（REST）

```yaml
okx_derivatives:
  name: okx_derivatives
  exchange: okx_derivatives
  market_type: perpetual
  enabled: true
  api:
    base_url: https://www.okx.com
    ws_url: wss://ws.okx.com:8443/ws/v5/public
  symbols:
  - BTC-USDT-SWAP
  - ETH-USDT-SWAP
  data_types:
  - orderbook
  orderbook:
    method: snapshot
    snapshot_interval: 1
    snapshot_depth: 100
    rest_base: https://www.okx.com
    request_timeout: 0.9
```

---

## 部署流程

### 1. 灰度发布（推荐）

**步骤 1：单交易所单符号测试**

```yaml
# 只启用一个交易所的一个符号
binance_spot:
  enabled: true
  symbols:
  - BTCUSDT  # 只测试 BTC
  orderbook:
    method: snapshot
    snapshot_interval: 1
    snapshot_depth: 100
```

**步骤 2：观察指标（5-10 分钟）**

- ClickHouse 入库频率：应为 1 条/秒
- NATS 发布成功率：应 >99%
- 请求延迟：应 <500ms（P99）
- 错误日志：应无 ERROR 级别日志

**步骤 3：逐步扩展**

- 增加符号数量（如 ETHUSDT）
- 增加交易所（如 OKX）
- 观察系统资源（CPU、内存、网络）

### 2. 全量部署

确认灰度测试稳定后，更新所有需要的交易所配置，重启 Collector。

```bash
# 停止 Collector
docker stop marketprism-data-collector

# 或本地运行
pkill -f "python.*collector.*main.py"

# 更新配置文件
vim services/data-collector/config/collector/unified_data_collection.yaml

# 启动 Collector
docker start marketprism-data-collector

# 或本地运行
cd services/data-collector
python3 main.py --mode launcher --config config/collector/unified_data_collection.yaml
```

---

## 监控指标

### Prometheus Metrics

Snapshot 模式提供以下 Prometheus 指标：

| 指标名称 | 类型 | 标签 | 说明 |
|---------|------|------|------|
| `marketprism_snapshot_requests_total` | Counter | `exchange`, `market_type`, `symbol`, `status` | 快照请求总数（按状态分类：success/error/timeout/cancelled） |
| `marketprism_snapshot_request_duration_seconds` | Histogram | `exchange`, `market_type`, `symbol` | 快照请求延迟分布 |
| `marketprism_snapshot_reconnections_total` | Counter | `exchange`, `market_type` | WebSocket 重连总数（仅 Binance Derivatives） |
| `marketprism_snapshot_timeouts_total` | Counter | `exchange`, `market_type`, `symbol` | 快照请求超时总数 |

### 关键指标

| 指标 | 正常范围 | 告警阈值 | 说明 |
|------|---------|---------|------|
| 快照成功率 | >99% | <95% | 单位时间内成功获取快照的比例 |
| 请求延迟（P99） | <500ms | >1000ms | 99分位请求延迟 |
| 重连次数 | <1次/小时 | >5次/小时 | WebSocket 重连频率（仅 Binance Derivatives） |
| ClickHouse 入库频率 | 1条/秒/符号 | <0.9条/秒 | 数据入库频率 |
| 内存使用 | <200MB | >500MB | Collector 进程内存 |

### Prometheus 查询示例

**快照成功率（5分钟滚动窗口）**
```promql
sum(rate(marketprism_snapshot_requests_total{status="success"}[5m])) by (exchange, market_type)
/
sum(rate(marketprism_snapshot_requests_total[5m])) by (exchange, market_type)
* 100
```

**快照延迟 P99**
```promql
histogram_quantile(0.99,
  sum(rate(marketprism_snapshot_request_duration_seconds_bucket[5m])) by (exchange, market_type, le)
)
```

**重连频率（每分钟）**
```promql
rate(marketprism_snapshot_reconnections_total[5m]) * 60
```

**超时率**
```promql
sum(rate(marketprism_snapshot_timeouts_total[5m])) by (exchange, symbol)
/
sum(rate(marketprism_snapshot_requests_total[5m])) by (exchange, symbol)
* 100
```

### ClickHouse 查询示例

**检查入库频率**

```sql
SELECT 
    exchange, 
    symbol, 
    market_type, 
    count(*) as total_records,
    round(count(*) / (toUnixTimestamp(max(timestamp)) - toUnixTimestamp(min(timestamp)) + 1), 2) as records_per_sec
FROM marketprism_hot.orderbooks
WHERE timestamp > now() - INTERVAL 5 MINUTE
GROUP BY exchange, symbol, market_type
ORDER BY exchange, market_type, symbol;
```

**检查最近数据**

```sql
SELECT 
    exchange, 
    symbol, 
    market_type, 
    timestamp, 
    bids_count, 
    asks_count
FROM marketprism_hot.orderbooks
WHERE timestamp > now() - INTERVAL 1 MINUTE
ORDER BY timestamp DESC
LIMIT 20;
```

### Grafana 仪表盘

项目提供了预配置的 Grafana 仪表盘 JSON 文件：

**文件位置**：`services/data-collector/docs/grafana_snapshot_dashboard.json`

**包含面板**：
1. 快照成功率（按交易所）
2. 快照请求延迟（P99/P95/P50）
3. 快照重连次数
4. 快照超时率（按符号）
5. 快照请求速率
6. 快照状态分布（饼图）
7. 快照延迟热力图
8. 快照成功率（按符号表格）

**导入方法**：
1. 登录 Grafana
2. 点击 "+" → "Import"
3. 上传 `grafana_snapshot_dashboard.json` 文件
4. 选择 Prometheus 数据源
5. 点击 "Import"

### Prometheus 告警规则

项目提供了预配置的告警规则文件：

**文件位置**：`services/data-collector/docs/prometheus_snapshot_alerts.yml`

**包含告警**：
- `SnapshotSuccessRateLow`：成功率 <95%（5分钟）
- `SnapshotSuccessRateCritical`：成功率 <80%（3分钟）
- `SnapshotLatencyHigh`：P99 延迟 >1s（5分钟）
- `SnapshotLatencyCritical`：P99 延迟 >2s（3分钟）
- `SnapshotReconnectionsFrequent`：重连 >3次/10分钟
- `SnapshotTimeoutRateHigh`：超时率 >10%（5分钟）
- `SnapshotRequestsStopped`：请求停止（2分钟）
- `SnapshotAverageLatencyHigh`：P50 延迟 >500ms（10分钟）
- `SnapshotErrorRateHigh`：错误率 >5%（5分钟）

**配置方法**：
1. 将 `prometheus_snapshot_alerts.yml` 复制到 Prometheus 配置目录
2. 在 `prometheus.yml` 中添加：
   ```yaml
   rule_files:
     - "prometheus_snapshot_alerts.yml"
   ```
3. 重启 Prometheus 或执行热加载：
   ```bash
   curl -X POST http://localhost:9090/-/reload
   ```

---

## 故障排查

### 问题 1：快照获取失败

**症状**：日志中出现 "fetch failed" 或 "timeout" 错误

**可能原因**：
- 网络问题
- 交易所 API 限流
- 请求超时设置过短

**解决方案**：
1. 检查网络连接：`ping api.binance.com`
2. 检查 API 限流：查看交易所返回的 429 错误
3. 调整超时设置：增加 `request_timeout` 值（如 1.5s）

### 问题 2：WebSocket 频繁重连（Binance Derivatives）

**症状**：日志中频繁出现 "reconnecting" 消息

**可能原因**：
- 网络不稳定
- 交易所主动断开连接
- 请求频率过高

**解决方案**：
1. 检查网络稳定性
2. 检查是否触发交易所限流
3. 减少符号数量或增加 `snapshot_interval`

### 问题 3：数据入库频率低于预期

**症状**：ClickHouse 查询显示 records_per_sec < 1

**可能原因**：
- Collector 进程异常
- NATS 连接问题
- data-storage-service 异常

**解决方案**：
1. 检查 Collector 日志：`docker logs marketprism-data-collector`
2. 检查 NATS 连接：`docker logs marketprism-message-broker`
3. 检查 storage 服务：`docker logs marketprism-data-storage`

---

## 回滚方案

### 方法 1：禁用 Snapshot 模式

将 `method: snapshot` 改为 `method: websocket` 或直接删除该行：

```yaml
orderbook:
  # method: snapshot  # 注释掉或删除
  depth_limit: 500
  # ... 其他增量模式配置 ...
```

重启 Collector 后将恢复增量 WebSocket 订阅模式。

### 方法 2：禁用特定交易所

```yaml
binance_spot:
  enabled: false  # 禁用整个交易所
```

### 方法 3：回滚配置文件

```bash
# 恢复备份的配置文件
cp unified_data_collection.yaml.backup unified_data_collection.yaml

# 重启 Collector
docker restart marketprism-data-collector
```

---

## 性能调优

### 调整轮询频率

```yaml
orderbook:
  snapshot_interval: 2  # 降低频率到 2 秒/次
```

**影响**：
- 降低 API 请求频率，减少限流风险
- 数据时效性降低

### 调整快照深度

```yaml
orderbook:
  snapshot_depth: 50  # 降低深度到 50 档
```

**影响**：
- 减少数据传输量和处理时间
- 深度数据不完整

### 调整超时设置

```yaml
orderbook:
  request_timeout: 1.5  # 增加超时到 1.5 秒
```

**影响**：
- 减少超时错误
- 单次请求可能阻塞更长时间

---

## 常见问题

**Q: Snapshot 模式和增量模式可以同时使用吗？**

A: 不可以。每个交易所的 orderbook 只能选择一种模式。但不同交易所可以使用不同模式。

**Q: 如何验证 Snapshot 模式是否生效？**

A: 查看 Collector 启动日志，应该看到 "Create snapshot orderbook manager" 消息。

**Q: Snapshot 模式的数据格式和增量模式一样吗？**

A: 是的。经过 Normalizer 标准化后，两种模式的数据格式完全一致，对下游系统透明。

**Q: 为什么 Binance Derivatives 使用 WebSocket API 而不是 REST？**

A: Binance Derivatives 的 REST API 限流较严格，WebSocket API 提供更高的请求配额且延迟更低。

**Q: OKX 的 -SWAP 后缀会被保留吗？**

A: 不会。Normalizer 会自动移除 -SWAP 后缀，统一为 `BTC-USDT` 格式。

---

## 联系与支持

如有问题或建议，请联系开发团队或提交 Issue。

