# MarketPrism API 文档规范

## 📋 概述
这是MarketPrism项目后端API的完整规范文档，用于前后端分离开发的协作。

## 🏗️ 系统架构

### 微服务架构
MarketPrism采用微服务架构，包含以下核心服务：

| 服务名称 | 端口 | 功能描述 |
|---------|------|----------|
| API Gateway | 8080 | 统一网关，路由分发 |
| Data Collector | 8081 | 市场数据采集 |
| Data Storage | 8082 | 数据存储管理 |
| Monitoring | 8083 | 系统监控告警 |
| Scheduler | 8084 | 任务调度 |
| Message Broker | 8085 | 消息队列 |
| Monitoring Dashboard | 8086 | 监控仪表板 |

### 统一API基础URL
```
生产环境: https://api.marketprism.com
开发环境: http://localhost:8080
```

## 🔗 核心API接口

### 1. 系统监控相关接口

#### 获取系统概览
```http
GET /api/v1/monitoring/overview
```

**响应示例:**
```json
{
  "status": "success",
  "data": {
    "cpu_usage": 19.0,
    "memory_usage": 56.2,
    "disk_usage": 1.13,
    "network_in": 125.6,
    "network_out": 89.3,
    "system_load": 0.65,
    "uptime": 3600
  }
}
```

#### 获取服务状态
```http
GET /api/v1/monitoring/services
```

**响应示例:**
```json
{
  "status": "success",
  "data": {
    "services": {
      "api-gateway": {
        "status": "running",
        "port": 8080,
        "response_time": 15,
        "cpu_usage": 12.3,
        "memory_usage": 156,
        "health_score": 100
      },
      "data-collector": {
        "status": "running",
        "port": 8081,
        "response_time": 28,
        "cpu_usage": 23.7,
        "memory_usage": 234,
        "health_score": 95
      }
    }
  }
}
```

### 2. 市场数据相关接口

#### 获取交易所连接状态
```http
GET /api/v1/trading/exchanges
```

**响应示例:**
```json
{
  "status": "success",
  "data": {
    "exchanges": {
      "binance": {
        "status": "connected",
        "latency": 8,
        "pairs_count": 156,
        "update_rate": 1200
      },
      "okx": {
        "status": "connected", 
        "latency": 15,
        "pairs_count": 89,
        "update_rate": 850
      },
      "deribit": {
        "status": "connected",
        "latency": 18,
        "pairs_count": 24,
        "update_rate": 320
      }
    }
  }
}
```

#### 获取实时价格数据
```http
GET /api/v1/trading/prices?symbol=BTC/USDT&exchange=binance
```

**响应示例:**
```json
{
  "status": "success",
  "data": {
    "symbol": "BTC/USDT",
    "exchange": "binance",
    "price": 43256.78,
    "change_24h": 2.34,
    "volume_24h": 1247.89,
    "high_24h": 43567.89,
    "low_24h": 42123.45,
    "timestamp": 1697123456789
  }
}
```

#### 获取订单簿数据
```http
GET /api/v1/trading/orderbook?symbol=BTC/USDT&depth=20
```

**响应示例:**
```json
{
  "status": "success",
  "data": {
    "symbol": "BTC/USDT",
    "asks": [
      {"price": 43267.89, "amount": 0.1234, "total": 5341.23},
      {"price": 43265.12, "amount": 0.2567, "total": 11102.45}
    ],
    "bids": [
      {"price": 43254.12, "amount": 0.3456, "total": 14945.78},
      {"price": 43251.89, "amount": 0.1789, "total": 7737.46}
    ],
    "timestamp": 1697123456789
  }
}
```

### 3. WebSocket 实时数据

#### 连接地址
```
ws://localhost:8086/ws
```

#### 订阅消息格式
```json
{
  "action": "subscribe",
  "channel": "prices",
  "symbol": "BTC/USDT"
}
```

#### 推送数据格式
```json
{
  "channel": "prices",
  "data": {
    "symbol": "BTC/USDT",
    "price": 43256.78,
    "timestamp": 1697123456789
  }
}
```

## 🔒 认证机制

### API密钥认证
```http
Authorization: Bearer <your-api-key>
```

### 错误响应格式
```json
{
  "status": "error",
  "error": {
    "code": 401,
    "message": "Unauthorized access",
    "details": "Invalid API key"
  }
}
```

## 📱 响应数据规范

### 统一响应格式
```json
{
  "status": "success|error",
  "data": {},
  "error": {
    "code": 0,
    "message": "",
    "details": ""
  },
  "timestamp": 1697123456789
}
```

### HTTP状态码规范
- 200: 成功
- 400: 请求参数错误
- 401: 认证失败
- 403: 权限不足
- 404: 资源不存在
- 500: 服务器内部错误

## 🔄 数据更新频率
- 系统监控数据: 5秒更新一次
- 服务状态: 10秒更新一次
- 价格数据: 实时推送
- 订单簿: 100ms更新一次

## 🎨 UI/UX 设计规范参考
参考现有的现代化界面设计：
- 主题色彩: Carbon Black (#1e293b) + 彩色点缀
- 玻璃拟态效果 (Glass Morphism)
- 响应式设计，支持桌面和移动端
- 实时数据可视化动画效果