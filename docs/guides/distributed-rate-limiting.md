# MarketPrism 分布式速率限制系统

## 概述

MarketPrism 分布式速率限制系统解决了在多进程、多服务环境中共享交易所API速率限制的问题。该系统确保所有服务的API请求总量不超过交易所的限制，避免被禁IP或账户。

## 问题背景

在MarketPrism项目中，多个服务可能同时调用交易所API：

- **数据收集服务**: Python Collector, Market Data Collector, Funding Rate Collector
- **交易服务**: Order Manager, Trade Executor
- **监控服务**: Health Checker, Monitoring Service
- **分析服务**: Data Analyzer, Report Generator

每个交易所都有严格的API速率限制：

| 交易所 | REST请求/分钟 | 权重限制/分钟 | 订单请求/秒 | WebSocket连接 |
|--------|---------------|---------------|-------------|---------------|
| Binance | 1200 | 6000 | 10 | 5 |
| OKX | 600 | 3000 | 5 | 5 |
| Deribit | 300 | 1500 | 20 | 100 |

## 系统架构

### 核心组件

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   服务进程 A    │    │   服务进程 B    │    │   服务进程 C    │
│                │    │                │    │                │
│ ┌─────────────┐ │    │ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │Rate Limit   │ │    │ │Rate Limit   │ │    │ │Rate Limit   │ │
│ │Adapter      │ │    │ │Adapter      │ │    │ │Adapter      │ │
│ └─────────────┘ │    │ └─────────────┘ │    │ └─────────────┘ │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                    ┌─────────────┴─────────────┐
                    │  分布式速率限制协调器      │
                    │                          │
                    │ ┌──────────────────────┐ │
                    │ │   令牌桶管理器       │ │
                    │ └──────────────────────┘ │
                    │ ┌──────────────────────┐ │
                    │ │   配额分配器         │ │
                    │ └──────────────────────┘ │
                    │ ┌──────────────────────┐ │
                    │ │   客户端注册器       │ │
                    │ └──────────────────────┘ │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │      Redis 存储          │
                    │   (分布式状态管理)        │
                    └───────────────────────────┘
```

### 算法原理

1. **分布式令牌桶算法**
   - 使用Redis存储全局令牌桶状态
   - 按照交易所限制设置令牌容量和填充速率
   - 原子操作确保并发安全

2. **优先级配额分配**
   - 交易服务：优先级10（最高）
   - 数据收集：优先级5-8
   - 监控服务：优先级5
   - 分析服务：优先级1-3（最低）

3. **动态负载均衡**
   - 根据客户端心跳动态调整配额
   - 非活跃客户端自动回收配额
   - 突发流量的弹性处理

## 安装和配置

### 1. 安装依赖

```bash
pip install aioredis pyyaml
```

### 2. Redis 配置

确保Redis服务运行并配置连接：

```yaml
# config/core/distributed_rate_limit_config.yaml
storage:
  type: "redis"
  redis:
    host: "localhost"
    port: 6379
    db: 2
    password: ""
```

### 3. 服务配置

为每个服务设置不同的优先级：

```yaml
clients:
  service_priorities:
    order_manager: 10      # 最高优先级
    trade_executor: 10
    python_collector: 8    # 高优先级
    market_data_collector: 8
    monitoring_service: 5   # 中等优先级
    data_analyzer: 3       # 低优先级
    log_processor: 1       # 最低优先级
```

## 使用方法

### 1. 基础使用

```python
from core.reliability.distributed_rate_limit_adapter import (
    DistributedRateLimitAdapter,
    DistributedRateLimitConfig
)

# 创建配置
config = DistributedRateLimitConfig(
    enabled=True,
    storage_type="redis",
    service_name="my_service",
    priority=5
)

# 创建适配器
adapter = DistributedRateLimitAdapter(config)
await adapter.initialize()

# 获取API请求许可
result = await adapter.acquire_permit(
    exchange="binance",
    request_type="rest_public",
    endpoint="/api/v3/ticker/24hr",
    weight=1
)

if result["granted"]:
    # 执行API请求
    response = await make_api_request()
else:
    # 等待或降级处理
    await asyncio.sleep(result["wait_time"])
```

### 2. 装饰器使用

```python
from core.reliability.distributed_rate_limit_adapter import rate_limited

class BinanceAPI:
    @rate_limited("binance", "rest_public", weight=1)
    async def get_ticker(self, symbol: str):
        # API请求会自动进行速率限制检查
        return await self._make_request(f"/api/v3/ticker/24hr?symbol={symbol}")
    
    @rate_limited("binance", "order", weight=1)
    async def place_order(self, symbol: str, side: str, quantity: float):
        # 订单请求使用专门的订单速率限制
        return await self._make_request("/api/v3/order", {
            "symbol": symbol,
            "side": side,
            "quantity": quantity
        })
```

### 3. 便利API使用

```python
from core.reliability.distributed_rate_limit_adapter import (
    acquire_api_permit,
    get_rate_limit_status
)

# 简单的许可获取
permitted = await acquire_api_permit("binance", "rest_public", weight=1)
if permitted:
    # 执行API请求
    pass

# 获取系统状态
status = await get_rate_limit_status()
print(f"成功率: {status['coordinator_status']['success_rate']:.2%}")
```

## 配置详解

### 交易所限制配置

```yaml
exchanges:
  binance:
    rest_requests_per_minute: 1200
    rest_weight_per_minute: 6000
    order_requests_per_second: 10
    safety_margin: 0.8  # 使用80%限制提供安全边际
    
    endpoint_limits:
      "/api/v3/order":
        requests_per_second: 10
        weight: 1
      "/api/v3/ticker/24hr":
        requests_per_minute: 40
        weight: 1
```

### 客户端优先级配置

```yaml
clients:
  service_priorities:
    # 交易相关 - 最高优先级
    order_manager: 10
    trade_executor: 10
    
    # 数据收集 - 高优先级
    python_collector: 8
    market_data_collector: 8
    funding_rate_collector: 7
    
    # 监控服务 - 中等优先级
    monitoring_service: 5
    health_checker: 5
    
    # 分析服务 - 低优先级
    data_analyzer: 3
    report_generator: 2
    
    # 后台任务 - 最低优先级
    data_archiver: 1
    log_processor: 1
```

### 监控配置

```yaml
monitoring:
  enabled: true
  alerts:
    rate_limit_alerts:
      utilization_threshold: 0.8      # 使用率超过80%告警
      rejection_rate_threshold: 0.1   # 拒绝率超过10%告警
      wait_time_threshold_seconds: 10 # 等待时间超过10秒告警
```

## 监控和运维

### 1. 实时状态监控

```python
import asyncio
from core.reliability.distributed_rate_limit_adapter import get_rate_limit_status

async def monitor_rate_limits():
    while True:
        status = await get_rate_limit_status()
        
        # 打印关键指标
        coord_status = status.get("coordinator_status", {})
        print(f"总请求: {coord_status.get('total_requests', 0)}")
        print(f"成功率: {coord_status.get('success_rate', 0):.2%}")
        
        # 检查令牌桶状态
        bucket_statuses = status.get("bucket_statuses", {})
        for exchange, buckets in bucket_statuses.items():
            for request_type, bucket_info in buckets.items():
                utilization = bucket_info.get("utilization", 0)
                if utilization > 0.8:
                    print(f"警告: {exchange} {request_type} 使用率过高: {utilization:.1%}")
        
        await asyncio.sleep(30)
```

### 2. Prometheus 指标

系统自动收集以下指标：

```
# 请求总数
rate_limit_requests_total{exchange="binance", type="rest_public", granted="true"}

# 令牌桶使用率
rate_limit_bucket_utilization{exchange="binance", type="rest_public"}

# 客户端数量
rate_limit_active_clients

# 等待时间
rate_limit_wait_time_seconds{exchange="binance", type="rest_public"}
```

### 3. 告警规则

建议的Prometheus告警规则：

```yaml
groups:
- name: rate_limiting
  rules:
  - alert: RateLimitHighUtilization
    expr: rate_limit_bucket_utilization > 0.8
    for: 5m
    annotations:
      summary: "速率限制使用率过高"
      description: "{{ $labels.exchange }} {{ $labels.type }} 使用率超过80%"
  
  - alert: RateLimitHighRejectionRate
    expr: rate(rate_limit_requests_total{granted="false"}[5m]) / rate(rate_limit_requests_total[5m]) > 0.1
    for: 5m
    annotations:
      summary: "速率限制拒绝率过高"
      description: "请求拒绝率超过10%"
```

## 故障处理

### 1. Redis 连接失败

系统会自动降级到本地速率限制：

```python
# 自动降级配置
redis:
  fallback_to_memory: true
```

### 2. 网络分区

每个客户端都有本地降级机制：

- 使用本地`GlobalRateLimitManager`
- 保持基本的速率限制功能
- 避免系统完全失效

### 3. 配置错误

系统提供配置验证：

```python
# 验证配置
config = DistributedRateLimitConfig.from_yaml_file("config.yaml")
if not config.validate():
    logger.error("配置验证失败")
```

## 性能优化

### 1. 连接池配置

```yaml
redis:
  max_connections: 50
  connection_timeout_seconds: 5
  idle_timeout_seconds: 300
```

### 2. 批处理请求

```yaml
performance:
  batch_processing:
    enabled: true
    batch_size: 100
    batch_timeout_ms: 50
```

### 3. 缓存配置

```yaml
cache:
  client_cache_ttl_seconds: 300
  quota_cache_ttl_seconds: 60
  bucket_cache_ttl_seconds: 5
```

## 测试

### 1. 运行单元测试

```bash
# 运行所有分布式速率限制测试
pytest tests/unit/core/test_distributed_rate_limit.py -v

# 运行特定测试
pytest tests/unit/core/test_distributed_rate_limit.py::TestTokenBucketManager::test_token_consumption -v
```

### 2. 运行示例

```bash
# 运行完整的多服务示例
python examples/distributed_rate_limit_example.py
```

### 3. 压力测试

```bash
# 运行并发性能测试
pytest tests/unit/core/test_distributed_rate_limit.py::TestConcurrentAccess -v
```

## 最佳实践

### 1. 服务设计

- **合理设置优先级**: 交易服务 > 数据收集 > 监控 > 分析
- **使用合适的权重**: 复杂查询使用更高权重
- **实现优雅降级**: 速率限制时的备选方案

### 2. 监控策略

- **实时监控使用率**: 避免接近限制
- **设置合理告警**: 预防性告警比故障告警更重要
- **定期评估配额分配**: 根据实际使用调整

### 3. 故障预防

- **使用安全边际**: 不要使用100%的限制
- **准备降级方案**: Redis失败时的本地处理
- **定期健康检查**: 确保系统正常运行

### 4. 配置管理

- **版本控制配置文件**: 跟踪配置变更
- **环境隔离**: 开发、测试、生产使用不同配置
- **配置验证**: 部署前验证配置正确性

## 常见问题

### Q: 如何调试速率限制问题？

A: 启用详细日志并检查系统状态：

```python
# 启用调试日志
import logging
logging.getLogger("core.reliability").setLevel(logging.DEBUG)

# 获取详细状态
status = await get_rate_limit_status()
print(json.dumps(status, indent=2))
```

### Q: 如何处理不同交易所的不同限制？

A: 每个交易所使用独立的令牌桶：

```python
# 为不同交易所获取许可
binance_permit = await acquire_api_permit("binance", "rest_public")
okx_permit = await acquire_api_permit("okx", "rest_public")
```

### Q: 如何在开发环境中禁用速率限制？

A: 使用配置禁用或模拟模式：

```yaml
debug:
  simulation_mode: true  # 不实际限制，只记录
```

### Q: 如何处理突发流量？

A: 配置突发允许：

```yaml
token_bucket:
  burst_allowance:
    enabled: true
    max_burst_percentage: 150
    burst_recovery_seconds: 300
```

## 相关文档

- [Redis 集群配置](../deployment/redis-cluster.md)
- [监控系统集成](../monitoring/monitoring-integration.md)
- [API 集成指南](../api/api-integration.md)
- [故障排除指南](../operations/troubleshooting.md)