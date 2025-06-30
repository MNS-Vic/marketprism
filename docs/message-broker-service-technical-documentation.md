# Message Broker Service 技术文档

## 📋 服务概述

Message Broker Service 是 MarketPrism 微服务架构的消息中枢，基于 BaseService 框架构建，提供统一的 NATS 消息代理功能。

### 核心功能
- **NATS Server 集群管理**: 自动启动和管理 NATS 服务器
- **JetStream 流管理**: 创建、删除和管理持久化消息流
- **消息路由和分发**: 高性能消息发布和订阅
- **消息持久化存储**: 基于 JetStream 的可靠消息存储
- **集群健康监控**: 实时监控 NATS 集群状态
- **统一 API 响应**: 标准化的 REST API 接口

## 🏗️ 架构设计

### 服务架构
```
┌─────────────────────────────────────────────────────────────┐
│                Message Broker Service                        │
├─────────────────────────────────────────────────────────────┤
│  BaseService Framework                                      │
│  ├── 统一 API 响应格式                                        │
│  ├── 标准化错误处理                                          │
│  ├── 服务生命周期管理                                        │
│  └── 健康检查和监控                                          │
├─────────────────────────────────────────────────────────────┤
│  NATS Integration Layer                                     │
│  ├── NATSServerManager (服务器管理)                          │
│  ├── NATSStreamManager (流管理)                              │
│  └── JetStream Context (消息处理)                            │
├─────────────────────────────────────────────────────────────┤
│  NATS Server Cluster                                       │
│  ├── JetStream 持久化                                        │
│  ├── 消息路由                                               │
│  └── 集群同步                                               │
└─────────────────────────────────────────────────────────────┘
```

### 技术栈
- **框架**: BaseService (MarketPrism 统一服务框架)
- **消息系统**: NATS Server + JetStream
- **Web 框架**: aiohttp
- **异步处理**: asyncio
- **日志系统**: structlog
- **容器化**: Docker

## 🔧 配置管理

### 环境变量
```bash
# 服务配置
ENVIRONMENT=production          # 运行环境
API_PORT=8086                  # API 服务端口
LOG_LEVEL=INFO                 # 日志级别

# NATS 配置
NATS_URL=nats://nats:4222      # NATS 服务器地址
NATS_CLUSTER_PORT=6222         # NATS 集群端口
NATS_HTTP_PORT=8222            # NATS HTTP 监控端口
```

### 配置文件结构
```yaml
services:
  message-broker:
    port: 8086
    host: "0.0.0.0"
    nats_server:
      port: 4222
      cluster_port: 6222
      http_port: 8222
    nats_client:
      url: "nats://localhost:4222"
      timeout: 10
    streams:
      market_data:
        subjects: ["market.>"]
        retention: "limits"
        max_msgs: 1000000
```

## 🌐 API 接口文档

### 标准化响应格式

#### 成功响应
```json
{
  "status": "success",
  "message": "操作成功描述",
  "data": { ... },
  "timestamp": "2025-06-29T05:32:44.123Z"
}
```

#### 错误响应
```json
{
  "status": "error",
  "error_code": "NATS_CONNECTION_ERROR",
  "message": "错误描述信息",
  "data": null,
  "timestamp": "2025-06-29T05:32:44.123Z"
}
```

### 核心 API 端点

#### 1. 服务状态查询
```http
GET /api/v1/status
```

**响应示例**:
```json
{
  "status": "success",
  "message": "Service status retrieved successfully",
  "data": {
    "service": "message-broker",
    "status": "running",
    "uptime_seconds": 3600.45,
    "version": "1.0.0",
    "environment": "production",
    "port": 8086,
    "features": {
      "nats_server": true,
      "jetstream": true,
      "message_routing": true,
      "stream_management": true,
      "message_persistence": true
    },
    "nats_info": {
      "server_status": "running",
      "client_connected": true,
      "streams_count": 3,
      "server_version": "2.9.0"
    },
    "statistics": {
      "messages_published": 15420,
      "messages_consumed": 15380,
      "active_streams": 3,
      "connection_errors": 0
    }
  },
  "timestamp": "2025-06-29T05:32:44.123Z"
}
```

#### 2. Broker 详细状态
```http
GET /api/v1/broker/status
```

#### 3. Broker 健康检查
```http
GET /api/v1/broker/health
```

#### 4. 流管理

##### 创建流
```http
POST /api/v1/broker/streams
Content-Type: application/json

{
  "name": "market_data",
  "subjects": ["market.>", "trades.>"],
  "retention": "limits",
  "max_msgs": 1000000,
  "max_bytes": 1073741824,
  "max_age": 86400
}
```

##### 获取流列表
```http
GET /api/v1/broker/streams
```

##### 删除流
```http
DELETE /api/v1/broker/streams/{stream_name}
```

#### 5. 消息发布
```http
POST /api/v1/broker/publish
Content-Type: application/json

{
  "subject": "market.btc.price",
  "message": {
    "symbol": "BTC",
    "price": 45000.00,
    "timestamp": "2025-06-29T05:32:44.123Z"
  }
}
```

## 🔒 错误代码规范

### 标准错误代码
```python
ERROR_CODES = {
    'NATS_CONNECTION_ERROR': 'NATS连接失败',
    'NATS_SERVER_ERROR': 'NATS服务器错误',
    'STREAM_NOT_FOUND': '流不存在',
    'STREAM_CREATION_ERROR': '流创建失败',
    'MESSAGE_PUBLISH_ERROR': '消息发布失败',
    'INVALID_STREAM_DATA': '无效的流数据',
    'INVALID_MESSAGE_DATA': '无效的消息数据',
    'JETSTREAM_ERROR': 'JetStream错误',
    'INVALID_PARAMETERS': '无效参数',
    'SERVICE_UNAVAILABLE': '服务不可用',
    'INTERNAL_ERROR': '内部错误'
}
```

### HTTP 状态码映射
- `200`: 成功操作
- `400`: 客户端错误 (参数验证失败)
- `404`: 资源不存在 (流不存在)
- `409`: 资源冲突 (流已存在)
- `500`: 服务器内部错误
- `503`: 服务不可用 (NATS 连接失败)

## 🚀 部署指南

### Docker 部署
```bash
# 构建镜像
docker build -t marketprism_message-broker:latest \
  -f services/message-broker/Dockerfile .

# 运行容器
docker run -d \
  --name marketprism-message-broker \
  --network marketprism_marketprism-network \
  -p 8086:8086 \
  -e ENVIRONMENT=production \
  -e API_PORT=8086 \
  -e NATS_URL=nats://marketprism-nats:4222 \
  marketprism_message-broker:latest
```

### 健康检查
```bash
# 基础健康检查
curl http://localhost:8086/health

# 详细状态检查
curl http://localhost:8086/api/v1/status

# Broker 健康状态
curl http://localhost:8086/api/v1/broker/health
```

## 🔍 监控和日志

### 关键指标
- **消息吞吐量**: 每秒处理的消息数
- **连接状态**: NATS 服务器和客户端连接状态
- **流统计**: 活跃流数量、消息数量、存储大小
- **错误率**: API 错误率和 NATS 连接错误
- **响应时间**: API 响应时间和消息延迟

### 日志格式
```json
{
  "timestamp": "2025-06-29T05:32:44.123Z",
  "level": "INFO",
  "logger": "message-broker",
  "message": "NATS服务器启动成功",
  "service": "message-broker",
  "nats_port": 4222,
  "streams_created": 3
}
```

## 🧪 测试指南

### API 测试示例
```bash
# 1. 测试服务状态
curl -X GET http://localhost:8086/api/v1/status

# 2. 创建测试流
curl -X POST http://localhost:8086/api/v1/broker/streams \
  -H "Content-Type: application/json" \
  -d '{"name":"test_stream","subjects":["test.>"]}'

# 3. 发布测试消息
curl -X POST http://localhost:8086/api/v1/broker/publish \
  -H "Content-Type: application/json" \
  -d '{"subject":"test.message","message":"Hello World"}'

# 4. 获取流列表
curl -X GET http://localhost:8086/api/v1/broker/streams
```

### 性能测试
- **并发连接**: 支持 1000+ 并发连接
- **消息吞吐**: 10,000+ 消息/秒
- **API 响应**: < 100ms (P95)
- **内存使用**: < 200MB (正常负载)

## 🔧 故障排除

### 常见问题

#### 1. NATS 连接失败
```bash
# 检查 NATS 服务状态
curl http://localhost:8086/api/v1/broker/health

# 检查网络连接
docker network ls | grep marketprism
```

#### 2. 流创建失败
- 检查流名称是否已存在
- 验证 subjects 格式是否正确
- 确认 JetStream 是否启用

#### 3. 消息发布失败
- 检查 subject 是否匹配现有流
- 验证消息格式是否正确
- 确认 NATS 连接状态

---

**文档版本**: 1.0.0  
**最后更新**: 2025-06-29  
**维护团队**: MarketPrism Development Team
