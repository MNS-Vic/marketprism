# MarketPrism订单簿管理系统 API文档

## 概述

MarketPrism订单簿管理系统提供RESTful API和WebSocket接口，用于访问实时订单簿数据、系统状态和监控指标。

## 基础信息

- **基础URL**: `http://localhost:8080`
- **API版本**: v1
- **认证方式**: Bearer Token（可选）
- **数据格式**: JSON
- **字符编码**: UTF-8

## 健康检查端点

### GET /health

检查系统健康状态。

**请求示例**:
```bash
curl -X GET http://localhost:8080/health
```

**响应示例**:
```json
{
  "status": "healthy",
  "timestamp": "2025-07-03T12:00:00Z",
  "version": "1.0.0",
  "services": {
    "nats": "connected",
    "clickhouse": "connected",
    "websockets": {
      "binance": "connected",
      "okx": "connected"
    }
  },
  "uptime": 3600,
  "memory_usage": "256MB",
  "active_symbols": 25
}
```

**状态码**:
- `200`: 系统健康
- `503`: 系统不健康

## 监控指标端点

### GET /metrics

获取Prometheus格式的监控指标。

**请求示例**:
```bash
curl -X GET http://localhost:8080/metrics
```

**响应示例**:
```
# HELP marketprism_orderbook_updates_total 订单簿更新总数
# TYPE marketprism_orderbook_updates_total counter
marketprism_orderbook_updates_total{exchange="binance",symbol="BTCUSDT"} 12345

# HELP marketprism_websocket_connected WebSocket连接状态
# TYPE marketprism_websocket_connected gauge
marketprism_websocket_connected{exchange="binance"} 1

# HELP marketprism_nats_messages_published_total NATS消息发布总数
# TYPE marketprism_nats_messages_published_total counter
marketprism_nats_messages_published_total{subject="orderbook-data"} 54321
```

## 订单簿数据端点

### GET /api/v1/orderbook/{exchange}/{symbol}

获取指定交易所和交易对的当前订单簿。

**路径参数**:
- `exchange`: 交易所名称 (binance, okx)
- `symbol`: 交易对符号 (BTCUSDT, ETHUSDT)

**查询参数**:
- `depth`: 深度档位数量 (默认: 20, 最大: 400)
- `format`: 响应格式 (json, raw)

**请求示例**:
```bash
curl -X GET "http://localhost:8080/api/v1/orderbook/binance/BTCUSDT?depth=10"
```

**响应示例**:
```json
{
  "exchange": "binance",
  "symbol": "BTCUSDT",
  "timestamp": "2025-07-03T12:00:00Z",
  "last_update_id": 12345678,
  "bids": [
    ["50000.00", "1.5"],
    ["49999.99", "2.0"]
  ],
  "asks": [
    ["50000.01", "1.2"],
    ["50000.02", "1.8"]
  ],
  "depth": 10,
  "checksum": "abc123"
}
```

### GET /api/v1/orderbook/{exchange}/{symbol}/history

获取订单簿历史数据。

**路径参数**:
- `exchange`: 交易所名称
- `symbol`: 交易对符号

**查询参数**:
- `start_time`: 开始时间 (ISO 8601格式)
- `end_time`: 结束时间 (ISO 8601格式)
- `interval`: 时间间隔 (1m, 5m, 15m, 1h)
- `limit`: 返回记录数量 (默认: 100, 最大: 1000)

**请求示例**:
```bash
curl -X GET "http://localhost:8080/api/v1/orderbook/binance/BTCUSDT/history?start_time=2025-07-03T10:00:00Z&end_time=2025-07-03T12:00:00Z&interval=5m"
```

## 系统状态端点

### GET /api/v1/status

获取系统详细状态信息。

**响应示例**:
```json
{
  "system": {
    "version": "1.0.0",
    "uptime": 3600,
    "memory_usage": "256MB",
    "cpu_usage": "15%"
  },
  "exchanges": {
    "binance": {
      "status": "connected",
      "symbols": ["BTCUSDT", "ETHUSDT"],
      "last_update": "2025-07-03T12:00:00Z",
      "error_count": 0
    },
    "okx": {
      "status": "connected",
      "symbols": ["BTCUSDT", "ETHUSDT"],
      "last_update": "2025-07-03T12:00:00Z",
      "error_count": 0
    }
  },
  "nats": {
    "status": "connected",
    "messages_published": 54321,
    "publish_errors": 0
  },
  "clickhouse": {
    "status": "connected",
    "records_stored": 1000000
  }
}
```

### GET /api/v1/symbols

获取支持的交易对列表。

**查询参数**:
- `exchange`: 过滤特定交易所 (可选)
- `active_only`: 仅返回活跃交易对 (默认: true)

**响应示例**:
```json
{
  "symbols": [
    {
      "exchange": "binance",
      "symbol": "BTCUSDT",
      "status": "active",
      "last_update": "2025-07-03T12:00:00Z"
    },
    {
      "exchange": "okx",
      "symbol": "ETHUSDT",
      "status": "active",
      "last_update": "2025-07-03T12:00:00Z"
    }
  ],
  "total": 25,
  "active": 25
}
```

## WebSocket接口

### 连接端点

**URL**: `ws://localhost:8080/ws`

### 订阅订单簿数据

**订阅消息**:
```json
{
  "method": "subscribe",
  "params": {
    "channel": "orderbook",
    "exchange": "binance",
    "symbol": "BTCUSDT",
    "depth": 20
  },
  "id": 1
}
```

**数据推送**:
```json
{
  "channel": "orderbook",
  "data": {
    "exchange": "binance",
    "symbol": "BTCUSDT",
    "timestamp": "2025-07-03T12:00:00Z",
    "bids": [["50000.00", "1.5"]],
    "asks": [["50000.01", "1.2"]],
    "last_update_id": 12345678
  }
}
```

### 取消订阅

**取消订阅消息**:
```json
{
  "method": "unsubscribe",
  "params": {
    "channel": "orderbook",
    "exchange": "binance",
    "symbol": "BTCUSDT"
  },
  "id": 2
}
```

## 错误处理

### 错误响应格式

```json
{
  "error": {
    "code": "INVALID_SYMBOL",
    "message": "交易对不存在或不支持",
    "details": {
      "exchange": "binance",
      "symbol": "INVALID"
    }
  },
  "timestamp": "2025-07-03T12:00:00Z",
  "request_id": "req_123456"
}
```

### 常见错误码

- `INVALID_EXCHANGE`: 不支持的交易所
- `INVALID_SYMBOL`: 不支持的交易对
- `INVALID_DEPTH`: 深度参数超出范围
- `SERVICE_UNAVAILABLE`: 服务暂时不可用
- `RATE_LIMIT_EXCEEDED`: 请求频率超限
- `INTERNAL_ERROR`: 内部服务器错误

## 限流规则

- **健康检查**: 无限制
- **订单簿数据**: 100请求/分钟
- **历史数据**: 10请求/分钟
- **WebSocket连接**: 10连接/IP

## SDK和示例

### Python示例

```python
import requests
import websocket
import json

# REST API示例
response = requests.get('http://localhost:8080/api/v1/orderbook/binance/BTCUSDT')
orderbook = response.json()
print(f"最佳买价: {orderbook['bids'][0][0]}")

# WebSocket示例
def on_message(ws, message):
    data = json.loads(message)
    print(f"收到数据: {data}")

ws = websocket.WebSocketApp("ws://localhost:8080/ws")
ws.on_message = on_message
ws.run_forever()
```

### JavaScript示例

```javascript
// REST API示例
fetch('http://localhost:8080/api/v1/orderbook/binance/BTCUSDT')
  .then(response => response.json())
  .then(data => console.log('最佳买价:', data.bids[0][0]));

// WebSocket示例
const ws = new WebSocket('ws://localhost:8080/ws');
ws.onmessage = function(event) {
  const data = JSON.parse(event.data);
  console.log('收到数据:', data);
};
```

## 支持和联系

- **文档**: https://docs.marketprism.com
- **GitHub**: https://github.com/marketprism/orderbook-manager
- **邮箱**: support@marketprism.com

---

*最后更新: 2025-07-03*
