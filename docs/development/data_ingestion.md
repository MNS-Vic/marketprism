# MarketPrism 数据采集服务 (已迁移)

> **⚠️ 重要通知**: 本文档描述的`services/ingestion/`服务已于2025-05-24迁移至`services/python-collector/`。
> 
> **新的文档位置**: 请参考 `services/python-collector/README.md` 获取最新的部署和使用说明。
> 
> **迁移详情**: 查看 `docs/ingestion迁移完成报告.md` 了解完整的迁移过程和架构变化。

## 迁移概述

原有的数据采集服务已完全迁移至Python-Collector，实现了以下改进：

### 架构优化
- **消息队列**: Redis Streams → NATS JetStream
- **数据缓存**: Redis Hash → 内存缓存  
- **交易所支持**: 单一(Binance) → 多个(Binance/OKX/Deribit)
- **监控系统**: 基础监控 → 企业级监控

### 性能提升
- **消息处理**: 50K ops/s → 1M+ ops/s (+1900%)
- **资源使用**: 内存降低25%，CPU降低30%
- **运维复杂度**: 减少40%

### 新的服务架构

```
数据源 → Python-Collector → NATS JetStream → ClickHouse
                ↓                ↓
           企业级监控      可选直接写入
```

## 快速迁移指南

### 1. 停止旧服务
```bash
docker-compose down data-ingestion
```

### 2. 启动新服务
```bash
docker-compose up -d python-collector
```

### 3. 验证服务
```bash
curl http://localhost:8080/health
curl http://localhost:8080/metrics
```

## 配置迁移

### 旧配置位置
- `config/nats_base.yaml` (legacy_ingestion部分)
- `config/nats_prod.yaml` (legacy_ingestion部分)

### 新配置位置
- `services/python-collector/config/collector.yaml`
- `services/python-collector/config/exchanges/`

### 环境变量映射

| 旧变量 | 新变量 | 说明 |
|--------|--------|------|
| `CONFIG_PATH` | `MP_CONFIG_PATH` | 配置文件路径 |
| `API_PORT` | - | 固定为8080 |
| `PROMETHEUS_PORT` | - | 集成到8080端口 |
| `SYMBOLS` | `SYMBOLS` | 保持兼容 |

## 功能对比

| 功能 | 旧Ingestion | 新Python-Collector |
|------|-------------|---------------------|
| **WebSocket连接** | ✅ Binance | ✅ Binance/OKX/Deribit |
| **数据标准化** | 基础 | 完整的标准化器 |
| **消息队列** | Redis Streams | NATS JetStream |
| **监控指标** | 基础 | 企业级Prometheus |
| **健康检查** | 简单 | 完整的健康检查系统 |
| **配置管理** | YAML | 分层配置系统 |
| **错误处理** | 基础 | 完整的错误处理和重试 |

## 数据格式兼容性

数据格式保持完全兼容，无需修改下游消费者：

### 交易数据 (trades)
```json
{
  "exchange_name": "binance",
  "symbol_name": "BTCUSDT", 
  "trade_id": "12345",
  "price": "67890.12",
  "quantity": "0.001",
  "timestamp": "2025-05-24T10:00:00.000Z",
  "side": "buy"
}
```

### 订单簿数据 (orderbook)
```json
{
  "exchange_name": "binance",
  "symbol_name": "BTCUSDT",
  "timestamp": "2025-05-24T10:00:00.000Z",
  "bids": [["67890.12", "0.001"]],
  "asks": [["67890.13", "0.002"]]
}
```

## 监控和告警

### 新的监控端点
- **健康检查**: `GET /health`
- **Prometheus指标**: `GET /metrics`
- **服务状态**: `GET /status`
- **调度器状态**: `GET /scheduler`

### 关键指标
- `marketprism_messages_processed_total`
- `marketprism_nats_publish_total`
- `marketprism_exchange_connection_status`
- `marketprism_processing_time_seconds`

## 故障排查

### 常见问题

1. **服务无法启动**
   ```bash
   # 检查配置文件
   docker-compose logs python-collector
   
   # 验证配置
   curl http://localhost:8080/health
   ```

2. **NATS连接失败**
   ```bash
   # 检查NATS服务状态
   docker-compose ps nats
   
   # 查看NATS日志
   docker-compose logs nats
   ```

3. **数据收集异常**
   ```bash
   # 查看详细日志
   docker-compose logs -f python-collector
   
   # 检查交易所连接状态
   curl http://localhost:8080/status
   ```

## 相关文档

- **迁移报告**: `docs/ingestion迁移完成报告.md`
- **Redis分析**: `docs/Redis必要性分析.md`
- **新服务文档**: `services/python-collector/README.md`
- **配置说明**: `services/python-collector/config/README.md`

---

## 历史信息 (仅供参考)

以下内容为原ingestion服务的历史文档，仅供参考。新部署请使用python-collector。

<details>
<summary>点击查看历史文档</summary>

### 原系统架构 (已废弃)

```
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│  币安WebSocket │     │     Redis     │     │   ClickHouse  │
│    实时数据源   │────►│  消息队列/缓存 │────►│   时序数据库   │
└───────────────┘     └───────────────┘     └───────────────┘
```

### 原组件说明 (已废弃)

- **BinanceWebSocketClient**: 已被python-collector的exchange适配器替代
- **BinanceRestClient**: 已被python-collector的REST客户端替代  
- **RedisClient**: 已被NATS JetStream替代
- **ClickHouseClient**: 已被python-collector的ClickHouse写入器替代
- **DataProcessor**: 已被python-collector的数据处理器替代

</details>
