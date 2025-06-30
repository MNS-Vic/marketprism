# Message Broker Service

MarketPrism微服务架构的消息中间件服务，提供NATS集群管理和消息路由功能。

## 功能特性

### 🚀 NATS集群管理
- **自动启动**: 自动启动和管理NATS Server
- **集群配置**: 支持NATS集群部署
- **健康监控**: NATS服务器健康状态监控
- **配置管理**: 动态配置生成和管理

### 📡 JetStream消息流
- **持久化流**: 基于JetStream的持久化消息流
- **多种存储**: 支持内存和文件存储
- **流管理**: 自动创建和管理消息流
- **消息持久化**: 可靠的消息持久化存储

### 🔄 消息路由
- **主题路由**: 基于主题的消息路由
- **消息分发**: 高效的消息分发机制
- **订阅管理**: 动态订阅管理
- **消息过滤**: 支持消息过滤和转换

### 📊 监控和统计
- **消息统计**: 发布、消费、错误统计
- **流状态**: 实时流状态监控
- **性能指标**: 吞吐量、延迟等性能指标
- **HTTP监控**: HTTP接口的监控端点

## 快速开始

### 1. 环境准备

安装NATS Server：

```bash
# macOS (使用Homebrew)
brew install nats-server

# Linux (下载二进制文件)
curl -L https://github.com/nats-io/nats-server/releases/download/v2.10.7/nats-server-v2.10.7-linux-amd64.zip -o nats-server.zip
unzip nats-server.zip
sudo mv nats-server-v2.10.7-linux-amd64/nats-server /usr/local/bin/

# Docker运行
docker run -p 4222:4222 -p 8222:8222 nats:latest
```

安装Python NATS客户端：

```bash
pip install nats-py
```

### 2. 配置服务

编辑 `config/services.yaml`：

```yaml
message-broker-service:
  port: 8085
  auto_start_nats: true
  auto_create_streams: true
  
  nats:
    nats_port: 4222
    cluster_port: 6222
    http_port: 8222
    jetstream_enabled: true
    jetstream_max_memory: "1GB"
    jetstream_max_storage: "10GB"
    nats_url: "nats://localhost:4222"
    data_dir: "data/nats"
    
    # 自定义流配置
    streams:
      CUSTOM_STREAM:
        subjects: ["custom.>"]
        retention: "limits"
        max_age: 7200
        max_msgs: 500000
        storage: "file"
```

### 3. 启动服务

```bash
# 直接启动
cd services/message-broker-service
python main.py

# 或使用服务管理器
cd scripts
python start_services.py --service message-broker-service
```

### 4. 验证服务

```bash
# 检查服务状态
curl http://localhost:8085/health

# 查看消息代理状态
curl http://localhost:8085/api/v1/status

# 查看流信息
curl http://localhost:8085/api/v1/streams
```

## API接口

### 服务状态

```http
GET /api/v1/status
```

返回消息代理完整状态：

```json
{
  "service": "message-broker-service",
  "timestamp": "2024-01-01T12:00:00Z",
  "uptime_seconds": 3600,
  "nats_server": {
    "status": "running",
    "server_info": {
      "server_id": "NACSS7QVHJQQ7XPXMG6FTX2O3AAOTDZ3XWPE5NVBCZJH7K2X6DJGJ2NJ",
      "server_name": "marketprism-nats",
      "version": "2.10.7",
      "go": "go1.21.5",
      "host": "0.0.0.0",
      "port": 4222,
      "max_connections": 1000,
      "connections": 1,
      "total_connections": 5,
      "routes": 0,
      "remotes": 0
    }
  },
  "jetstream_streams": [
    {
      "name": "MARKET_DATA",
      "subjects": ["market.>"],
      "messages": 10000,
      "bytes": 5242880,
      "consumer_count": 2
    }
  ],
  "message_stats": {
    "published": 10000,
    "consumed": 9500,
    "errors": 5
  }
}
```

### 流管理

```http
GET /api/v1/streams
```

获取所有JetStream流信息：

```json
{
  "streams": [
    {
      "name": "MARKET_DATA",
      "subjects": ["market.>"],
      "messages": 10000,
      "bytes": 5242880,
      "first_seq": 1,
      "last_seq": 10000,
      "consumer_count": 2
    },
    {
      "name": "SYSTEM_EVENTS", 
      "subjects": ["system.>"],
      "messages": 500,
      "bytes": 102400,
      "first_seq": 1,
      "last_seq": 500,
      "consumer_count": 1
    }
  ]
}
```

### 消息发布

```http
POST /api/v1/publish
```

发布消息到指定主题：

请求体：
```json
{
  "subject": "market.binance.BTCUSDT.trade",
  "message": {
    "symbol": "BTCUSDT",
    "price": "50000.00",
    "quantity": "0.1",
    "timestamp": "2024-01-01T12:00:00Z"
  }
}
```

响应：
```json
{
  "success": true
}
```

### NATS服务器信息

```http
GET /api/v1/nats/info
```

获取NATS服务器详细信息：

```json
{
  "status": "running",
  "pid": 12345,
  "ports": {
    "nats": 4222,
    "cluster": 6222,
    "http": 8222
  },
  "server_info": {
    "server_id": "NACSS7QVHJQQ7XPXMG6FTX2O3AAOTDZ3XWPE5NVBCZJH7K2X6DJGJ2NJ",
    "connections": 5,
    "in_msgs": 10000,
    "out_msgs": 9500,
    "in_bytes": 5242880,
    "out_bytes": 4980736
  }
}
```

## 消息流配置

### 默认流

服务会自动创建以下默认流：

#### 1. MARKET_DATA流
- **主题**: `market.>`
- **保留策略**: 限制保留 (limits)
- **最大时间**: 1小时
- **最大消息数**: 1,000,000
- **存储**: 文件存储

#### 2. SYSTEM_EVENTS流
- **主题**: `system.>`
- **保留策略**: 限制保留 (limits)
- **最大时间**: 24小时
- **最大消息数**: 100,000
- **存储**: 文件存储

#### 3. SERVICE_LOGS流
- **主题**: `service.>`
- **保留策略**: 限制保留 (limits)
- **最大时间**: 7天
- **最大消息数**: 500,000
- **存储**: 文件存储

### 自定义流配置

可以通过配置文件添加自定义流：

```yaml
nats:
  streams:
    CUSTOM_ANALYTICS:
      subjects: ["analytics.>", "metrics.>"]
      retention: "workqueue"
      max_age: 86400
      max_msgs: 1000000
      storage: "memory"
    
    USER_EVENTS:
      subjects: ["user.>"]
      retention: "interest"
      max_age: 3600
      max_msgs: 100000
      storage: "file"
```

## 消息主题规范

### 主题命名规范

```
{domain}.{exchange}.{symbol}.{type}
```

### 市场数据主题

| 主题模式 | 描述 | 示例 |
|----------|------|------|
| `market.{exchange}.{symbol}.trade` | 交易数据 | `market.binance.BTCUSDT.trade` |
| `market.{exchange}.{symbol}.orderbook` | 订单簿数据 | `market.okx.BTC-USDT.orderbook` |
| `market.{exchange}.{symbol}.ticker` | 行情数据 | `market.deribit.BTC-PERPETUAL.ticker` |
| `market.{exchange}.{symbol}.kline.{interval}` | K线数据 | `market.binance.ETHUSDT.kline.1m` |

### 系统事件主题

| 主题模式 | 描述 | 示例 |
|----------|------|------|
| `system.service.{service_name}.{event}` | 服务事件 | `system.service.api-gateway.started` |
| `system.alert.{level}.{type}` | 系统告警 | `system.alert.critical.high_cpu` |
| `system.health.{service_name}` | 健康检查 | `system.health.data-storage` |

### 服务日志主题

| 主题模式 | 描述 | 示例 |
|----------|------|------|
| `service.{service_name}.log.{level}` | 服务日志 | `service.monitoring.log.error` |
| `service.{service_name}.metrics` | 服务指标 | `service.market-data-collector.metrics` |

## 客户端使用示例

### Python客户端

```python
import asyncio
import nats
from nats.js import JetStreamContext
import json

async def publish_example():
    # 连接到NATS
    nc = await nats.connect("nats://localhost:4222")
    js = nc.jetstream()
    
    # 发布消息
    trade_data = {
        "exchange": "binance",
        "symbol": "BTCUSDT", 
        "price": "50000.00",
        "quantity": "0.1",
        "timestamp": "2024-01-01T12:00:00Z"
    }
    
    await js.publish(
        "market.binance.BTCUSDT.trade",
        json.dumps(trade_data).encode()
    )
    
    await nc.close()

async def subscribe_example():
    # 连接到NATS
    nc = await nats.connect("nats://localhost:4222")
    js = nc.jetstream()
    
    # 创建消费者
    async def message_handler(msg):
        data = json.loads(msg.data.decode())
        print(f"收到消息: {data}")
        await msg.ack()
    
    # 订阅消息
    await js.subscribe(
        "market.>", 
        cb=message_handler,
        stream="MARKET_DATA",
        durable="market-consumer"
    )
    
    # 保持连接
    await asyncio.sleep(60)
    await nc.close()
```

### Node.js客户端

```javascript
const { connect, StringCodec } = require('nats');

async function publishExample() {
  const nc = await connect({ servers: 'nats://localhost:4222' });
  const js = nc.jetstream();
  const sc = StringCodec();
  
  const tradeData = {
    exchange: 'binance',
    symbol: 'BTCUSDT',
    price: '50000.00',
    quantity: '0.1',
    timestamp: new Date().toISOString()
  };
  
  await js.publish(
    'market.binance.BTCUSDT.trade',
    sc.encode(JSON.stringify(tradeData))
  );
  
  await nc.close();
}

async function subscribeExample() {
  const nc = await connect({ servers: 'nats://localhost:4222' });
  const js = nc.jetstream();
  const sc = StringCodec();
  
  const subscription = await js.subscribe('market.>', {
    stream: 'MARKET_DATA',
    durable_name: 'market-consumer'
  });
  
  for await (const msg of subscription) {
    const data = JSON.parse(sc.decode(msg.data));
    console.log('收到消息:', data);
    msg.ack();
  }
  
  await nc.close();
}
```

## 性能优化

### 连接池配置

```yaml
nats:
  max_connections: 1000
  max_subscriptions: 1000
  max_payload: "1MB"
  write_deadline: "2s"
  ping_interval: "2m"
  max_pings_out: 2
```

### JetStream优化

```yaml
nats:
  jetstream_max_memory: "2GB"
  jetstream_max_storage: "50GB"
  jetstream_max_streams: 100
  jetstream_max_consumers: 1000
```

### 集群配置

```yaml
nats:
  cluster_name: "marketprism-cluster"
  cluster_routes:
    - "nats-route://node1:6222"
    - "nats-route://node2:6222"
    - "nats-route://node3:6222"
```

## 监控和日志

### 监控指标

通过HTTP监控端点获取指标：

```bash
# 服务器变量
curl http://localhost:8222/varz

# 连接信息
curl http://localhost:8222/connz

# 路由信息
curl http://localhost:8222/routez

# 订阅信息
curl http://localhost:8222/subsz

# JetStream信息
curl http://localhost:8222/jsz
```

### 关键指标

- **连接数**: 当前活跃连接数
- **消息吞吐量**: 每秒处理的消息数
- **内存使用**: JetStream内存使用情况
- **存储使用**: 持久化存储使用情况
- **延迟**: 消息传递延迟

## 故障排除

### 常见问题

1. **NATS Server启动失败**
   - 检查端口是否被占用
   - 验证配置文件语法
   - 检查磁盘空间和权限

2. **JetStream功能不可用**
   - 确认JetStream已启用
   - 检查存储配置
   - 验证用户权限

3. **消息丢失**
   - 检查流的保留策略
   - 验证消费者确认机制
   - 查看错误日志

4. **性能问题**
   - 调整连接池大小
   - 优化消息批处理
   - 检查网络延迟

### 调试命令

```bash
# 检查服务状态
curl http://localhost:8085/api/v1/status | jq

# 查看流状态
curl http://localhost:8085/api/v1/streams | jq

# NATS服务器状态
curl http://localhost:8222/varz | jq

# 测试消息发布
curl -X POST http://localhost:8085/api/v1/publish \
  -H "Content-Type: application/json" \
  -d '{"subject":"test.message","message":"Hello World"}'
```

### 日志分析

```bash
# 查看NATS服务器日志
tail -f data/nats/nats-server.log

# 查看服务日志
curl http://localhost:8085/health | jq
```

## 集群部署

### 多节点配置

节点1配置：
```yaml
nats:
  cluster_name: "marketprism-cluster"
  cluster_listen: "0.0.0.0:6222"
  cluster_routes:
    - "nats-route://node2:6222"
    - "nats-route://node3:6222"
```

节点2配置：
```yaml
nats:
  cluster_name: "marketprism-cluster"
  cluster_listen: "0.0.0.0:6222"
  cluster_routes:
    - "nats-route://node1:6222"
    - "nats-route://node3:6222"
```

### 负载均衡

```yaml
nats:
  client_urls:
    - "nats://node1:4222"
    - "nats://node2:4222" 
    - "nats://node3:4222"
```

## 安全配置

### 认证配置

```yaml
nats:
  users:
    - user: "producer"
      password: "producer_pass"
      permissions:
        publish: ["market.>"]
    - user: "consumer"
      password: "consumer_pass"
      permissions:
        subscribe: ["market.>"]
```

### TLS配置

```yaml
nats:
  tls:
    cert_file: "/path/to/server-cert.pem"
    key_file: "/path/to/server-key.pem"
    ca_file: "/path/to/ca.pem"
    verify: true
```

## 相关服务

- **Market Data Collector**: 消息生产者
- **Data Storage Service**: 消息消费者
- **Monitoring Service**: 消息队列监控
- **API Gateway Service**: 消息路由管理

## 支持

如有问题或建议，请查看：
- 项目文档: `docs/messaging/`
- NATS文档: https://docs.nats.io/
- JetStream指南: https://docs.nats.io/jetstream
- 问题追踪: GitHub Issues