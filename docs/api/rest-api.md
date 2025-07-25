# MarketPrism REST API 文档

> 最后更新：2025-01-27

## 📡 API 概述

MarketPrism 提供 RESTful API 接口，用于系统监控、状态查询和配置管理。所有 API 端点都通过 HTTP 协议提供服务。

## 🔗 基础信息

### 服务端点
- **基础 URL**: `http://localhost:8080`
- **协议**: HTTP/1.1
- **数据格式**: JSON
- **字符编码**: UTF-8

### 认证方式
当前版本为开发环境，暂不需要认证。生产环境将支持：
- API Key 认证
- JWT Token 认证

## 📊 监控端点

### 健康检查

#### `GET /health`

获取系统健康状态。

**请求示例**:
```bash
curl http://localhost:8080/health
```

**响应示例**:
```json
{
  "status": "healthy",
  "timestamp": "2025-01-27T10:30:00Z",
  "version": "2.0.0",
  "uptime": 3600,
  "checks": {
    "nats": {
      "status": "healthy",
      "latency_ms": 2.5
    },
    "clickhouse": {
      "status": "healthy",
      "latency_ms": 5.2
    },
    "exchanges": {
      "binance": "connected",
      "okx": "connected",
      "deribit": "connected"
    }
  }
}
```

**状态码**:
- `200` - 系统健康
- `503` - 系统不健康

### 系统状态

#### `GET /status`

获取详细的系统状态信息。

**请求示例**:
```bash
curl http://localhost:8080/status
```

**响应示例**:
```json
{
  "system": {
    "version": "2.0.0",
    "environment": "development",
    "uptime": 3600,
    "start_time": "2025-01-27T09:30:00Z"
  },
  "performance": {
    "messages_per_second": 152.6,
    "total_messages": 549360,
    "error_rate": 0.0,
    "memory_usage_mb": 256.8,
    "cpu_usage_percent": 15.2
  },
  "connections": {
    "websocket_connections": 3,
    "nats_connection": "connected",
    "clickhouse_connection": "connected"
  },
  "data_types": {
    "trade": {
      "enabled": true,
      "messages_count": 450000
    },
    "orderbook": {
      "enabled": true,
      "messages_count": 89000
    },
    "ticker": {
      "enabled": true,
      "messages_count": 10360
    }
  }
}
```

### Prometheus 指标

#### `GET /metrics`

获取 Prometheus 格式的监控指标。

**请求示例**:
```bash
curl http://localhost:8080/metrics
```

**响应示例**:
```
# HELP marketprism_messages_total Total number of processed messages
# TYPE marketprism_messages_total counter
marketprism_messages_total{exchange="binance",type="trade"} 450000
marketprism_messages_total{exchange="okx",type="trade"} 89000

# HELP marketprism_messages_per_second Current messages per second
# TYPE marketprism_messages_per_second gauge
marketprism_messages_per_second 152.6

# HELP marketprism_memory_usage_bytes Memory usage in bytes
# TYPE marketprism_memory_usage_bytes gauge
marketprism_memory_usage_bytes 269484032

# HELP marketprism_error_rate Error rate percentage
# TYPE marketprism_error_rate gauge
marketprism_error_rate 0.0
```

## ⏰ 调度器端点

### 调度器状态

#### `GET /scheduler`

获取任务调度器状态和任务信息。

**请求示例**:
```bash
curl http://localhost:8080/scheduler
```

**响应示例**:
```json
{
  "scheduler": {
    "status": "running",
    "jobs_count": 4,
    "next_run": "2025-01-27T11:00:00Z"
  },
  "jobs": [
    {
      "id": "funding_rate_collection",
      "name": "Funding Rate Collection",
      "status": "scheduled",
      "next_run": "2025-01-27T11:00:00Z",
      "last_run": "2025-01-27T10:00:00Z",
      "last_result": "success",
      "interval": "1h"
    },
    {
      "id": "open_interest_collection",
      "name": "Open Interest Collection",
      "status": "scheduled",
      "next_run": "2025-01-27T10:45:00Z",
      "last_run": "2025-01-27T10:30:00Z",
      "last_result": "success",
      "interval": "15m"
    },
    {
      "id": "health_check",
      "name": "System Health Check",
      "status": "scheduled",
      "next_run": "2025-01-27T10:35:00Z",
      "last_run": "2025-01-27T10:30:00Z",
      "last_result": "success",
      "interval": "5m"
    }
  ]
}
```

## 🔧 配置端点

### 获取配置

#### `GET /config`

获取当前系统配置（敏感信息已脱敏）。

**请求示例**:
```bash
curl http://localhost:8080/config
```

**响应示例**:
```json
{
  "collector": {
    "use_real_exchanges": true,
    "enable_scheduler": true,
    "http_port": 8080
  },
  "exchanges": [
    {
      "exchange": "binance",
      "market_type": "spot",
      "enabled": true,
      "symbols": ["BTC/USDT", "ETH/USDT"],
      "data_types": ["trade", "orderbook", "ticker"]
    },
    {
      "exchange": "okx",
      "market_type": "spot",
      "enabled": true,
      "symbols": ["BTC-USDT", "ETH-USDT"],
      "data_types": ["trade", "orderbook", "ticker", "funding_rate"]
    }
  ],
  "nats": {
    "url": "nats://localhost:4222",
    "client_name": "marketprism-collector"
  }
}
```

## 🐛 调试端点

### 原始数据查看

#### `GET /debug/raw_data`

查看最近收到的原始数据（仅在调试模式下可用）。

**请求示例**:
```bash
curl http://localhost:8080/debug/raw_data?exchange=binance&limit=5
```

**查询参数**:
- `exchange` (可选): 指定交易所 (binance, okx, deribit)
- `type` (可选): 指定数据类型 (trade, orderbook, ticker)
- `limit` (可选): 限制返回数量，默认 10，最大 100

**响应示例**:
```json
{
  "data": [
    {
      "exchange": "binance",
      "type": "trade",
      "timestamp": "2025-01-27T10:30:15Z",
      "raw": {
        "e": "trade",
        "E": 1706353815000,
        "s": "BTCUSDT",
        "t": 12345,
        "p": "43250.50",
        "q": "0.001",
        "T": 1706353815000,
        "m": false
      },
      "normalized": {
        "exchange_name": "binance",
        "symbol_name": "BTCUSDT",
        "trade_id": "12345",
        "price": "43250.50",
        "quantity": "0.001",
        "timestamp": "2025-01-27T10:30:15Z"
      }
    }
  ]
}
```

### 连接状态

#### `GET /debug/connections`

查看所有连接状态详情。

**请求示例**:
```bash
curl http://localhost:8080/debug/connections
```

**响应示例**:
```json
{
  "websocket_connections": [
    {
      "exchange": "binance",
      "url": "wss://stream.binance.com:9443/ws/btcusdt@trade",
      "status": "connected",
      "connected_at": "2025-01-27T09:30:00Z",
      "messages_received": 45000,
      "last_message": "2025-01-27T10:30:14Z"
    },
    {
      "exchange": "okx",
      "url": "wss://ws.okx.com:8443/ws/v5/public",
      "status": "connected",
      "connected_at": "2025-01-27T09:30:05Z",
      "messages_received": 38000,
      "last_message": "2025-01-27T10:30:13Z"
    }
  ],
  "nats_connection": {
    "status": "connected",
    "url": "nats://localhost:4222",
    "connected_at": "2025-01-27T09:29:58Z",
    "messages_published": 83000,
    "last_publish": "2025-01-27T10:30:14Z"
  },
  "clickhouse_connection": {
    "status": "connected",
    "host": "localhost:8123",
    "database": "marketprism",
    "connected_at": "2025-01-27T09:29:59Z"
  }
}
```

## 📈 统计端点

### 数据统计

#### `GET /stats`

获取数据处理统计信息。

**请求示例**:
```bash
curl http://localhost:8080/stats
```

**响应示例**:
```json
{
  "period": "last_24h",
  "summary": {
    "total_messages": 2150000,
    "messages_per_second_avg": 24.9,
    "messages_per_second_peak": 156.2,
    "error_count": 0,
    "error_rate": 0.0
  },
  "by_exchange": {
    "binance": {
      "messages": 1200000,
      "percentage": 55.8,
      "avg_latency_ms": 2.1
    },
    "okx": {
      "messages": 750000,
      "percentage": 34.9,
      "avg_latency_ms": 3.2
    },
    "deribit": {
      "messages": 200000,
      "percentage": 9.3,
      "avg_latency_ms": 4.5
    }
  },
  "by_type": {
    "trade": {
      "messages": 1800000,
      "percentage": 83.7
    },
    "orderbook": {
      "messages": 300000,
      "percentage": 14.0
    },
    "ticker": {
      "messages": 50000,
      "percentage": 2.3
    }
  }
}
```

## 🚨 错误处理

### 错误响应格式

所有错误响应都遵循统一格式：

```json
{
  "error": {
    "code": "INVALID_PARAMETER",
    "message": "Invalid exchange parameter: unknown_exchange",
    "details": {
      "parameter": "exchange",
      "value": "unknown_exchange",
      "valid_values": ["binance", "okx", "deribit"]
    },
    "timestamp": "2025-01-27T10:30:00Z"
  }
}
```

### 常见错误码

| 错误码 | HTTP状态码 | 描述 |
|--------|------------|------|
| `INVALID_PARAMETER` | 400 | 请求参数无效 |
| `NOT_FOUND` | 404 | 资源不存在 |
| `INTERNAL_ERROR` | 500 | 内部服务器错误 |
| `SERVICE_UNAVAILABLE` | 503 | 服务不可用 |
| `RATE_LIMITED` | 429 | 请求频率超限 |

## 📝 使用示例

### 监控脚本示例

```bash
#!/bin/bash
# health_monitor.sh - 系统健康监控脚本

API_BASE="http://localhost:8080"

# 检查系统健康
health=$(curl -s "$API_BASE/health")
status=$(echo "$health" | jq -r '.status')

if [ "$status" = "healthy" ]; then
    echo "✅ System is healthy"
    
    # 获取性能指标
    stats=$(curl -s "$API_BASE/stats")
    msg_rate=$(echo "$stats" | jq -r '.summary.messages_per_second_avg')
    echo "📊 Message rate: $msg_rate msg/s"
    
else
    echo "❌ System is unhealthy"
    echo "$health" | jq '.checks'
fi
```

### Python 客户端示例

```python
import requests
import json

class MarketPrismClient:
    def __init__(self, base_url="http://localhost:8080"):
        self.base_url = base_url
    
    def get_health(self):
        """获取系统健康状态"""
        response = requests.get(f"{self.base_url}/health")
        return response.json()
    
    def get_stats(self):
        """获取统计信息"""
        response = requests.get(f"{self.base_url}/stats")
        return response.json()
    
    def get_scheduler_status(self):
        """获取调度器状态"""
        response = requests.get(f"{self.base_url}/scheduler")
        return response.json()

# 使用示例
client = MarketPrismClient()

# 检查健康状态
health = client.get_health()
print(f"System status: {health['status']}")

# 获取统计信息
stats = client.get_stats()
print(f"Messages per second: {stats['summary']['messages_per_second_avg']}")
```

## 🔮 未来计划

### 即将推出的端点
- `POST /config/reload` - 重新加载配置
- `GET /logs` - 获取系统日志
- `POST /exchanges/{exchange}/restart` - 重启特定交易所连接
- `GET /performance/report` - 生成性能报告

### API 版本控制
- 当前版本: v1 (隐式)
- 计划版本: v2 (显式版本控制)
- 向后兼容性保证

---

**API 文档状态**: ✅ 已完成  
**API 版本**: v1.0  
**支持的端点**: 10+ 个核心端点  
**文档覆盖率**: 100% 当前功能