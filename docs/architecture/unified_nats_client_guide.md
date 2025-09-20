# 统一NATS客户端使用指南

## 🎯 **概述**

MarketPrism现在使用统一的NATS客户端实现：`collector.nats_publisher.NATSPublisher`，替代了之前的`utils.nats_client`。

## 🏗️ **架构设计**

### **统一NATS客户端架构**
```
┌─────────────────────────────────────┐
│         NATSPublisher               │
│  - 连接管理                         │
│  - JetStream流管理                  │
│  - 消息发布                         │
│  - 主题生成                         │
│  - 统计监控                         │
│  - 健康检查                         │
└─────────────────┬───────────────────┘
                  │ 依赖注入
                  ▼
┌─────────────────────────────────────┐
│      业务组件                       │
│  - OrderBook Manager                │
│  - Trade Manager                    │
│  - 其他数据收集器                    │
└─────────────────────────────────────┘
```

## 📋 **基本使用方法**

### **1. 导入模块**
```python
from collector.nats_publisher import NATSPublisher, NATSConfig, create_nats_config_from_yaml
```

### **2. 创建配置**

#### **方式1：直接创建配置**
```python
config = NATSConfig(
    servers=["nats://localhost:4222"],
    client_name="my-collector",
    max_reconnect_attempts=10,
    timeout=5
)
```

#### **方式2：从YAML配置创建**
```python
# 从unified_data_collection.yaml加载
yaml_config = load_yaml_config()
nats_config = create_nats_config_from_yaml(yaml_config)
```

### **3. 创建发布器**
```python
publisher = NATSPublisher(nats_config)
```

### **4. 连接和断开**
```python
# 连接
success = await publisher.connect()
if not success:
    print("连接失败")

# 断开连接
await publisher.disconnect()
```

## 📊 **数据发布方法**

### **通用发布方法**
```python
# 通用数据发布
success = await publisher.publish_data(
    data_type=DataType.ORDERBOOK,
    exchange="binance",
    market_type="spot",
    symbol="BTCUSDT",
    data=orderbook_data
)
```

### **专用发布方法**

#### **订单簿数据**
```python
success = await publisher.publish_orderbook(
    exchange="binance",
    market_type="spot", 
    symbol="BTCUSDT",
    orderbook_data={
        'bids': [['50000.0', '1.5']],
        'asks': [['50001.0', '2.0']],
        'timestamp': '2024-01-01T00:00:00Z'
    }
)
```

#### **交易数据**
```python
success = await publisher.publish_trade(
    exchange="binance",
    market_type="spot",
    symbol="BTCUSDT", 
    trade_data={
        'price': '50000.0',
        'quantity': '1.0',
        'side': 'buy',
        'timestamp': '2024-01-01T00:00:00Z'
    }
)
```

#### **资金费率**
```python
success = await publisher.publish_funding_rate(
    exchange="binance",
    market_type="perpetual",
    symbol="BTCUSDT",
    funding_data={
        'funding_rate': '0.0001',
        'next_funding_time': '2024-01-01T08:00:00Z'
    }
)
```

#### **持仓量**
```python
success = await publisher.publish_open_interest(
    exchange="binance", 
    market_type="perpetual",
    symbol="BTCUSDT",
    oi_data={
        'open_interest': '1000000.0',
        'timestamp': '2024-01-01T00:00:00Z'
    }
)
```

## 🔧 **高级功能**

### **JetStream流管理**
```python
# 配置中启用JetStream
config = NATSConfig(
    enable_jetstream=True,
    streams={
        "MARKET_DATA": {
            "name": "MARKET_DATA",
            "subjects": ["orderbook.>", "trade.>"],
            "retention": "limits",
            "max_msgs": 1000000,
            "max_bytes": 1073741824,  # 1GB
            "max_age": 86400  # 24 hours
        }
    }
)
```

### **批量发布**
```python
# 批量发布多条消息
messages = [
    (DataType.ORDERBOOK, "binance", "spot", "BTCUSDT", orderbook_data1),
    (DataType.TRADE, "binance", "spot", "BTCUSDT", trade_data1),
]

success_count = await publisher.publish_batch(messages)
```

### **健康检查**
```python
health = publisher.get_health_status()
print(f"连接状态: {health['connected']}")
print(f"发布统计: {health['stats']}")
```

## 🔄 **迁移指南**

### **从旧版nats_client迁移**

#### **旧版代码**
```python
from utils.nats_client import NATSClient

client = NATSClient(
    servers=['nats://localhost:4222'],
    client_name='my-client'
)
await client.connect()
await client.publish_orderbook(orderbook)
```

#### **新版代码**
```python
from collector.nats_publisher import NATSPublisher, NATSConfig

config = NATSConfig(
    servers=['nats://localhost:4222'],
    client_name='my-client'
)
publisher = NATSPublisher(config)
await publisher.connect()
await publisher.publish_orderbook_legacy(orderbook)  # 兼容方法
```

### **依赖注入模式**

#### **OrderBook Manager集成**
```python
# 创建NATS发布器
nats_config = NATSConfig()
nats_publisher = NATSPublisher(nats_config)

# 注入到OrderBook Manager
manager = OrderBookManager(
    config=exchange_config,
    normalizer=normalizer,
    nats_publisher=nats_publisher  # 依赖注入
)
```

## 📈 **监控和统计**

### **发布统计**
```python
stats = publisher.get_publish_stats()
print(f"成功发布: {stats.successful_publishes}")
print(f"失败发布: {stats.failed_publishes}")
print(f"重试次数: {stats.retry_attempts}")
```

### **连接状态**
```python
if publisher.is_connected:
    print("NATS连接正常")
else:
    print("NATS连接断开")
```

## ⚙️ **配置参数**

### **NATSConfig参数说明**
- `servers`: NATS服务器列表
- `client_name`: 客户端名称
- `max_reconnect_attempts`: 最大重连次数
- `reconnect_time_wait`: 重连等待时间（秒）
- `timeout`: 发布超时时间（秒）
- `max_retries`: 最大重试次数
- `batch_size`: 批量发布大小
- `enable_jetstream`: 是否启用JetStream
- `streams`: JetStream流配置

### **主题格式**
默认主题格式：`{data_type}.{exchange}.{market_type}.{symbol}`

示例：
- `orderbook.binance.spot.BTC-USDT`
- `trade.okx.perpetual.BTC-USDT`
- `funding-rate.binance.perpetual.BTC-USDT`

## 🚨 **错误处理**

### **连接错误**
```python
try:
    success = await publisher.connect()
    if not success:
        logger.error("NATS连接失败")
except Exception as e:
    logger.error("NATS连接异常", error=str(e))
```

### **发布错误**
```python
try:
    success = await publisher.publish_orderbook(...)
    if not success:
        logger.warning("订单簿发布失败")
except Exception as e:
    logger.error("订单簿发布异常", error=str(e))
```

## 🎯 **最佳实践**

1. **使用依赖注入**: 通过构造函数注入NATSPublisher
2. **配置驱动**: 使用YAML配置文件管理参数
3. **错误处理**: 始终检查发布结果和处理异常
4. **资源管理**: 确保正确关闭连接
5. **监控统计**: 定期检查发布统计和健康状态
6. **批量发布**: 对于大量数据使用批量发布提高性能

## 🔗 **相关文档**

- [NATS官方文档](https://docs.nats.io/)
- [JetStream指南](https://docs.nats.io/jetstream)
- [MarketPrism配置指南](./configuration_guide.md)
- [数据收集架构](./data_collection_architecture.md)
