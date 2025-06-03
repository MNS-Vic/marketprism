# 统一REST API模块使用指南

## 概述

MarketPrism的统一REST API模块提供了一个标准化的方式来处理所有REST API请求，支持多个交易所的数据收集。该模块具有以下特性：

- **统一接口**: 为所有交易所提供一致的API接口
- **连接池管理**: 自动管理HTTP连接池，提高性能
- **限流控制**: 内置限流机制，避免触发API限制
- **重试机制**: 自动重试失败的请求，提高可靠性
- **错误处理**: 完善的错误处理和日志记录
- **监控统计**: 详细的请求统计和性能监控

## 核心组件

### 1. RestClientConfig

REST客户端配置类，用于配置客户端的各种参数：

```python
from marketprism_collector.rest_client import RestClientConfig

config = RestClientConfig(
    base_url="https://fapi.binance.com",
    timeout=30,
    max_retries=3,
    retry_delay=1.0,
    
    # 连接池配置
    max_connections=100,
    max_connections_per_host=30,
    keepalive_timeout=30,
    
    # 限流配置
    rate_limit_per_second=5.0,
    rate_limit_per_minute=300.0,
    
    # 认证配置
    api_key="your_api_key",
    api_secret="your_api_secret",
    
    # 代理配置
    proxy="http://proxy.example.com:8080",
    
    # 其他配置
    user_agent="MarketPrism-Collector/1.0",
    verify_ssl=True
)
```

### 2. UnifiedRestClient

统一REST客户端，提供基本的HTTP请求功能：

```python
from marketprism_collector.rest_client import UnifiedRestClient

# 创建客户端
client = UnifiedRestClient(config, name="my_client")

# 启动客户端
await client.start()

# 发送请求
response = await client.get("/api/v1/time")
response = await client.post("/api/v1/order", data={"symbol": "BTCUSDT"})

# 获取统计信息
stats = client.get_stats()

# 停止客户端
await client.stop()
```

### 3. ExchangeRestClient

交易所专用REST客户端，继承自UnifiedRestClient，添加了交易所特定的认证逻辑：

```python
from marketprism_collector.rest_client import ExchangeRestClient
from marketprism_collector.types import Exchange

# 创建交易所客户端
client = ExchangeRestClient(Exchange.BINANCE, config)

# 使用方式与UnifiedRestClient相同
await client.start()
response = await client.get("/fapi/v1/time")
await client.stop()
```

### 4. RestClientManager

REST客户端管理器，用于管理多个REST客户端：

```python
from marketprism_collector.rest_client import RestClientManager

# 创建管理器
manager = RestClientManager()

# 创建客户端
binance_client = manager.create_exchange_client(Exchange.BINANCE, binance_config)
okx_client = manager.create_exchange_client(Exchange.OKX, okx_config)

# 启动所有客户端
await manager.start_all()

# 获取客户端
client = manager.get_client("binance_rest")

# 获取所有统计信息
all_stats = manager.get_all_stats()

# 停止所有客户端
await manager.stop_all()
```

## 大户持仓比数据收集器

### TopTraderDataCollector

专门用于收集币安和OKX大户持仓比数据的收集器：

```python
from marketprism_collector.top_trader_collector import TopTraderDataCollector

# 创建收集器
collector = TopTraderDataCollector(rest_client_manager)

# 注册数据回调
def data_callback(data):
    print(f"收到数据: {data.exchange_name} {data.symbol_name}")
    print(f"多空比: {data.long_short_ratio}")

collector.register_callback(data_callback)

# 启动收集器
symbols = ["BTC-USDT", "ETH-USDT"]
await collector.start(symbols)

# 手动收集一次数据
results = await collector.collect_once()

# 获取统计信息
stats = collector.get_stats()

# 停止收集器
await collector.stop()
```

## 配置示例

### 开发环境配置

```yaml
# config/environments/development.yaml
collector:
  enable_top_trader_collector: true
  top_trader_symbols:
    - "BTC-USDT"
    - "ETH-USDT"
    - "BNB-USDT"
  
  top_trader_collection_intervals:
    binance: 5  # 每5分钟收集一次
    okx: 5

exchanges:
  binance:
    rest_api:
      base_url: "https://fapi.binance.com"
      timeout: 30
      max_retries: 3
      rate_limit_per_minute: 1200
  
  okx:
    rest_api:
      base_url: "https://www.okx.com"
      timeout: 30
      max_retries: 3
      rate_limit_per_minute: 600
```

## 使用示例

### 基本使用

```python
import asyncio
from marketprism_collector.rest_client import RestClientManager, RestClientConfig
from marketprism_collector.top_trader_collector import TopTraderDataCollector
from marketprism_collector.types import Exchange

async def main():
    # 创建REST客户端管理器
    rest_manager = RestClientManager()
    
    try:
        # 创建大户持仓比数据收集器
        collector = TopTraderDataCollector(rest_manager)
        
        # 注册回调函数
        def data_callback(data):
            print(f"📊 {data.exchange_name} {data.symbol_name}")
            print(f"   多空比: {data.long_short_ratio}")
            print(f"   多头比例: {data.long_position_ratio:.2%}")
            print(f"   空头比例: {data.short_position_ratio:.2%}")
        
        collector.register_callback(data_callback)
        
        # 手动收集数据
        results = await collector.collect_once()
        print(f"收集到 {len(results)} 条数据")
        
        # 启动定时收集
        await collector.start(["BTC-USDT", "ETH-USDT"])
        
        # 等待一段时间
        await asyncio.sleep(60)
        
    finally:
        # 清理资源
        await collector.stop()
        await rest_manager.stop_all()

if __name__ == "__main__":
    asyncio.run(main())
```

### 高级使用

```python
import asyncio
from marketprism_collector.rest_client import (
    RestClientManager, RestClientConfig, ExchangeRestClient
)
from marketprism_collector.types import Exchange

async def advanced_example():
    # 创建自定义配置
    binance_config = RestClientConfig(
        base_url="https://fapi.binance.com",
        timeout=10,
        max_retries=5,
        rate_limit_per_minute=1200,
        proxy="http://proxy.example.com:8080"  # 使用代理
    )
    
    okx_config = RestClientConfig(
        base_url="https://www.okx.com",
        timeout=10,
        max_retries=3,
        rate_limit_per_second=5,
        api_key="your_okx_api_key",
        api_secret="your_okx_api_secret",
        passphrase="your_okx_passphrase"
    )
    
    # 创建管理器
    manager = RestClientManager()
    
    try:
        # 创建交易所客户端
        binance_client = manager.create_exchange_client(Exchange.BINANCE, binance_config)
        okx_client = manager.create_exchange_client(Exchange.OKX, okx_config)
        
        # 启动所有客户端
        await manager.start_all()
        
        # 并发请求
        tasks = [
            binance_client.get("/fapi/v1/time"),
            okx_client.get("/api/v5/public/time"),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"请求 {i} 失败: {result}")
            else:
                print(f"请求 {i} 成功: {result}")
        
        # 获取统计信息
        stats = manager.get_all_stats()
        for client_name, client_stats in stats.items():
            print(f"{client_name}: {client_stats['success_rate']}% 成功率")
    
    finally:
        await manager.stop_all()

if __name__ == "__main__":
    asyncio.run(advanced_example())
```

## API接口

### HTTP接口

当大户持仓比数据收集器集成到主收集器后，会提供以下HTTP接口：

```bash
# 获取收集器状态
GET /api/v1/top-trader/status

# 获取统计信息
GET /api/v1/top-trader/stats

# 手动刷新数据
POST /api/v1/top-trader/refresh
Content-Type: application/json
{
  "symbols": ["BTC-USDT", "ETH-USDT"],
  "exchanges": ["binance", "okx"]
}
```

### 响应示例

```json
{
  "is_running": true,
  "symbols": ["BTC-USDT", "ETH-USDT", "BNB-USDT"],
  "collection_interval": 300,
  "total_collections": 120,
  "successful_collections": 118,
  "failed_collections": 2,
  "success_rate": 98.33,
  "data_points_collected": 720,
  "last_collection_time": "2024-01-15T10:30:00Z",
  "exchanges": ["binance", "okx"],
  "rest_clients": {
    "binance_rest": {
      "base_url": "https://fapi.binance.com",
      "total_requests": 240,
      "successful_requests": 238,
      "success_rate": 99.17,
      "average_response_time": 0.156
    },
    "okx_rest": {
      "base_url": "https://www.okx.com",
      "total_requests": 240,
      "successful_requests": 236,
      "success_rate": 98.33,
      "average_response_time": 0.203
    }
  }
}
```

## 错误处理

### 常见错误类型

1. **网络错误**: 连接超时、DNS解析失败等
2. **HTTP错误**: 4xx、5xx状态码
3. **限流错误**: 429状态码
4. **认证错误**: 401、403状态码
5. **数据解析错误**: JSON解析失败

### 错误处理策略

```python
try:
    response = await client.get("/api/endpoint")
except aiohttp.ClientTimeout:
    # 处理超时
    logger.error("请求超时")
except aiohttp.ClientResponseError as e:
    if e.status == 429:
        # 处理限流
        logger.warning("触发限流，等待重试")
    elif e.status in [401, 403]:
        # 处理认证错误
        logger.error("认证失败")
    else:
        # 处理其他HTTP错误
        logger.error(f"HTTP错误: {e.status}")
except Exception as e:
    # 处理其他错误
    logger.error(f"未知错误: {e}")
```

## 性能优化

### 连接池优化

```python
config = RestClientConfig(
    max_connections=200,        # 增加总连接数
    max_connections_per_host=50, # 增加每个主机的连接数
    keepalive_timeout=60        # 延长连接保持时间
)
```

### 限流优化

```python
config = RestClientConfig(
    rate_limit_per_second=10,   # 每秒最多10个请求
    rate_limit_per_minute=600   # 每分钟最多600个请求
)
```

### 重试优化

```python
config = RestClientConfig(
    max_retries=5,      # 最多重试5次
    retry_delay=2.0     # 重试间隔2秒（指数退避）
)
```

## 监控和调试

### 日志配置

```python
import structlog

logger = structlog.get_logger(__name__)
logger.info("REST客户端启动", base_url=config.base_url)
logger.debug("发送请求", method="GET", url="/api/endpoint")
logger.error("请求失败", error=str(e))
```

### 统计监控

```python
# 获取详细统计
stats = client.get_stats()
print(f"成功率: {stats['success_rate']}%")
print(f"平均响应时间: {stats['average_response_time']}s")
print(f"限流命中次数: {stats['rate_limit_hits']}")

# 监控所有客户端
all_stats = manager.get_all_stats()
for name, stats in all_stats.items():
    if stats['success_rate'] < 95:
        logger.warning(f"客户端 {name} 成功率过低: {stats['success_rate']}%")
```

## 最佳实践

1. **合理设置限流**: 根据交易所的API限制设置合适的限流参数
2. **使用连接池**: 复用HTTP连接，提高性能
3. **错误重试**: 对临时性错误进行重试，提高可靠性
4. **监控统计**: 定期检查统计信息，及时发现问题
5. **资源清理**: 程序结束时正确清理资源
6. **代理支持**: 在需要时使用代理服务器
7. **日志记录**: 记录详细的日志信息，便于调试

## 故障排除

### 常见问题

1. **连接超时**: 检查网络连接和代理设置
2. **限流频繁**: 降低请求频率或增加重试间隔
3. **认证失败**: 检查API密钥和签名算法
4. **内存泄漏**: 确保正确关闭客户端和清理资源

### 调试技巧

```python
# 启用详细日志
import logging
logging.getLogger("aiohttp").setLevel(logging.DEBUG)

# 检查连接状态
if client.is_started:
    print("客户端已启动")
else:
    print("客户端未启动")

# 检查统计信息
stats = client.get_stats()
if stats['failed_requests'] > 0:
    print(f"有 {stats['failed_requests']} 个失败请求")
```

通过使用统一的REST API模块，你可以轻松地为MarketPrism添加新的REST数据源，同时享受统一的错误处理、限流控制和监控功能。 