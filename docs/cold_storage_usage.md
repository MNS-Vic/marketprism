# MarketPrism 冷数据存储使用指南

## 概述

MarketPrism冷数据存储系统提供长期数据归档和历史数据查询功能，与热数据存储形成完整的分层存储架构。

## 主要特性

- **长期存储**: 数据保存30-365天，支持历史数据分析
- **数据压缩**: 使用LZ4/ZSTD压缩算法，节省存储空间
- **智能分区**: 按月/天/周分区，优化查询性能
- **自动归档**: 自动从热存储迁移过期数据
- **历史查询**: 强大的历史数据查询和趋势分析功能

## 快速开始

### 1. 配置设置

在项目根目录的`config/collector_config.yaml`中添加冷存储配置：

```yaml
cold_storage:
  # 是否启用冷数据存储
  enabled: true
  # 冷数据TTL（秒），30天
  cold_data_ttl: 2592000
  # 归档阈值（天），超过此天数的热数据将被归档到冷存储
  archive_threshold_days: 7
  
  # ClickHouse冷数据配置
  clickhouse:
    host: "localhost"
    port: 8123
    user: "default"
    password: ""
    database: "marketprism_cold"
    connection_pool_size: 5
    batch_size: 5000
    flush_interval: 60
    max_retries: 3
  
  # 分区配置
  partitioning:
    # 按月分区：toYYYYMM(timestamp)
    # 按天分区：toYYYYMMDD(timestamp)
    # 按周分区：toYearWeek(timestamp)
    partition_by: "toYYYYMM(timestamp)"
  
  # 压缩配置
  compression:
    enabled: true
    # 支持的压缩算法：LZ4, ZSTD, Delta, DoubleDelta
    codec: "LZ4"
  
  # 自动归档配置
  archiving:
    enabled: true
    batch_size: 10000
    # 归档任务执行间隔（小时）
    interval_hours: 24
```

### 2. 基本使用

```python
from core.storage import ColdStorageManager
from datetime import datetime, timedelta
import asyncio

async def main():
    # 初始化冷存储管理器
    cold_storage = ColdStorageManager(
        config_path="config/collector_config.yaml"
    )
    
    # 启动服务
    await cold_storage.start()
    
    try:
        # 查询历史交易数据
        start_date = datetime.now() - timedelta(days=30)
        end_date = datetime.now()
        
        historical_trades = await cold_storage.get_historical_trades(
            exchange='binance',
            symbol='BTCUSDT',
            start_date=start_date,
            end_date=end_date,
            limit=1000
        )
        
        print(f"历史交易记录: {len(historical_trades)}")
        
        # 查询价格趋势
        price_trends = await cold_storage.get_price_trends(
            exchange='binance',
            symbol='BTCUSDT',
            start_date=start_date,
            end_date=end_date,
            interval='1h'  # 1小时间隔
        )
        
        print(f"价格趋势数据: {len(price_trends)}")
        
        # 获取归档统计
        archive_stats = await cold_storage.get_archive_statistics(30)
        print(f"归档统计: {archive_stats}")
        
    finally:
        # 停止服务
        await cold_storage.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

### 3. 全局实例使用

```python
from core.storage import get_cold_storage_manager, initialize_cold_storage_manager

# 初始化全局实例
cold_storage = initialize_cold_storage_manager(
    config_path="config/collector_config.yaml"
)
await cold_storage.start()

# 在其他地方获取全局实例
cold_storage = get_cold_storage_manager()

# 使用全局实例
historical_data = await cold_storage.get_historical_trades(
    'binance', 'BTCUSDT', start_date, end_date
)
```

## 数据归档功能

### 自动归档

冷存储系统支持自动从热存储归档数据：

```python
from core.storage import SimpleHotStorageManager, ColdStorageManager

# 同时初始化热存储和冷存储
hot_storage = SimpleHotStorageManager(config_path="config.yaml")
cold_storage = ColdStorageManager(config_path="config.yaml")

await hot_storage.start()
await cold_storage.start()

# 执行数据归档
archive_stats = await cold_storage.archive_from_hot_storage(
    hot_storage_manager=hot_storage,
    data_type="all"  # 或者 "trades", "tickers", "orderbooks"
)

print(f"归档统计: {archive_stats}")
# 输出: {'trades': 1500, 'tickers': 800, 'orderbooks': 600}
```

### 手动归档特定数据类型

```python
# 只归档交易数据
trade_archive_stats = await cold_storage.archive_from_hot_storage(
    hot_storage_manager=hot_storage,
    data_type="trades"
)

# 只归档行情数据
ticker_archive_stats = await cold_storage.archive_from_hot_storage(
    hot_storage_manager=hot_storage,
    data_type="tickers"
)

# 只归档订单簿数据
orderbook_archive_stats = await cold_storage.archive_from_hot_storage(
    hot_storage_manager=hot_storage,
    data_type="orderbooks"
)
```

## 历史数据查询

### 历史交易查询

```python
from datetime import datetime, timedelta

# 查询过去30天的历史交易
start_date = datetime.now() - timedelta(days=30)
end_date = datetime.now()

historical_trades = await cold_storage.get_historical_trades(
    exchange='binance',
    symbol='BTCUSDT',
    start_date=start_date,
    end_date=end_date,
    limit=5000
)

# 处理历史交易数据
for trade in historical_trades:
    print(f"交易: {trade['timestamp']} - {trade['price']} x {trade['amount']} ({trade['side']})")
```

### 价格趋势分析

```python
# 获取不同时间间隔的价格趋势
intervals = ['1h', '1d', '1w']

for interval in intervals:
    trends = await cold_storage.get_price_trends(
        exchange='binance',
        symbol='BTCUSDT',
        start_date=start_date,
        end_date=end_date,
        interval=interval
    )
    
    print(f"\n{interval} 价格趋势:")
    for trend in trends:
        print(f"  时期: {trend['period']}")
        print(f"  平均价格: {trend['avg_price']}")
        print(f"  最高价: {trend['max_price']}")
        print(f"  最低价: {trend['min_price']}")
        print(f"  总成交量: {trend['total_volume']}")
        print(f"  数据点: {trend['data_points']}")
```

### 归档统计查询

```python
# 获取过去30天的归档统计
archive_stats = await cold_storage.get_archive_statistics(days=30)

for data_type, stats in archive_stats.items():
    print(f"\n{data_type} 归档统计:")
    print(f"  归档会话: {stats['archive_sessions']}")
    print(f"  总记录数: {stats['total_records']}")
    print(f"  总大小: {stats['total_size_bytes']} 字节")
    print(f"  平均耗时: {stats['avg_duration_seconds']:.2f} 秒")
```

## 配置选项详解

### 基础配置

```yaml
cold_storage:
  enabled: true                    # 是否启用冷存储
  cold_data_ttl: 2592000          # 数据TTL时间（秒），30天
  archive_threshold_days: 7       # 归档阈值（天）
```

### ClickHouse配置

```yaml
  clickhouse:
    host: localhost                # ClickHouse主机
    port: 8123                     # ClickHouse端口
    user: default                  # 用户名
    password: ""                   # 密码
    database: marketprism_cold     # 数据库名
```

### 分区配置

```yaml
  partitioning:
    # 分区策略选择：
    partition_by: "toYYYYMM(timestamp)"      # 按月分区（推荐）
    # partition_by: "toYYYYMMDD(timestamp)"  # 按天分区（高频数据）
    # partition_by: "toYearWeek(timestamp)"  # 按周分区（中频数据）
```

### 压缩配置

```yaml
  compression:
    enabled: true                  # 是否启用压缩
    codec: "LZ4"                  # 压缩算法
    # 其他选项: "ZSTD", "Delta", "DoubleDelta"
```

### 自动归档配置

```yaml
  archiving:
    enabled: true                  # 是否启用自动归档
    batch_size: 10000             # 批量归档大小
    interval_hours: 24            # 归档间隔（小时）
```

## 高级特性

### 数据表结构

冷存储系统创建以下表结构：

#### 冷交易数据表
```sql
CREATE TABLE cold_trades (
    timestamp DateTime64(3) CODEC(LZ4),
    symbol String CODEC(LZ4),
    exchange String CODEC(LZ4),
    price Float64 CODEC(LZ4),
    amount Float64 CODEC(LZ4),
    side String CODEC(LZ4),
    trade_id String CODEC(LZ4),
    created_at DateTime64(3) DEFAULT now64(),
    archived_at DateTime64(3) DEFAULT now64()
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL archived_at + INTERVAL 2592000 SECOND
```

#### 冷行情数据表
```sql
CREATE TABLE cold_tickers (
    timestamp DateTime64(3) CODEC(LZ4),
    symbol String CODEC(LZ4),
    exchange String CODEC(LZ4),
    last_price Float64 CODEC(LZ4),
    volume_24h Float64 CODEC(LZ4),
    price_change_24h Float64 CODEC(LZ4),
    high_24h Float64 CODEC(LZ4),
    low_24h Float64 CODEC(LZ4),
    created_at DateTime64(3) DEFAULT now64(),
    archived_at DateTime64(3) DEFAULT now64()
) ENGINE = ReplacingMergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL archived_at + INTERVAL 2592000 SECOND
```

#### 归档状态表
```sql
CREATE TABLE archive_status (
    archive_date Date,
    data_type String,
    exchange String,
    records_archived UInt64,
    archive_size_bytes UInt64,
    archive_duration_seconds Float64,
    created_at DateTime64(3) DEFAULT now64()
) ENGINE = MergeTree()
ORDER BY (archive_date, data_type, exchange)
```

### 查询缓存

冷存储系统内置智能查询缓存：

- **历史查询缓存**: 1小时缓存TTL
- **趋势分析缓存**: 自动缓存常用查询
- **自动清理**: 过期缓存自动清理

### 监控指标

系统提供Prometheus监控指标：

```
# 操作计数
marketprism_cold_storage_operations_total{operation, status}

# 操作延迟
marketprism_cold_storage_latency_seconds{operation}

# 存储大小
marketprism_cold_storage_size_bytes{data_type}

# 归档操作
marketprism_cold_storage_archive_total{data_type, status}
```

### 自动归档任务

冷存储系统包含后台归档任务：

- **定时执行**: 每24小时自动执行归档
- **批量处理**: 智能批量处理提升效率
- **错误恢复**: 归档失败自动重试
- **状态记录**: 完整的归档状态记录

## 监控和统计

### 运行统计

```python
# 获取冷存储统计信息
stats = cold_storage.get_statistics()

print(f"运行时间: {stats['uptime_seconds']}秒")
print(f"写入次数: {stats['total_writes']}")
print(f"读取次数: {stats['total_reads']}")
print(f"归档次数: {stats['total_archives']}")
print(f"错误次数: {stats['total_errors']}")
print(f"读取速率: {stats['reads_per_second']:.2f}/秒")
print(f"归档速率: {stats['archives_per_day']:.2f}/天")
print(f"查询缓存大小: {stats['query_cache_size']}")
print(f"自动归档启用: {stats['auto_archive_enabled']}")
```

### 健康状态检查

```python
# 检查冷存储健康状态
health = cold_storage.get_health_status()

print(f"系统健康: {health['is_healthy']}")
print(f"服务运行: {health['is_running']}")
print(f"ClickHouse健康: {health['clickhouse_healthy']}")
print(f"归档任务健康: {health['archive_task_healthy']}")
print(f"错误率: {health['error_rate']:.2%}")
print(f"自动归档启用: {health['archive_enabled']}")
```

## 性能优化

### 查询优化建议

1. **使用时间范围限制**: 总是指定合理的时间范围
```python
# ✅ 好的做法
start_date = datetime.now() - timedelta(days=7)
end_date = datetime.now()

# ❌ 避免的做法
# 不指定时间范围，可能查询所有历史数据
```

2. **合理的LIMIT设置**: 避免一次查询过多数据
```python
# ✅ 好的做法
limit = 1000  # 合理的限制

# ❌ 避免的做法
limit = 1000000  # 过大的限制
```

3. **利用缓存**: 相同查询会自动缓存
```python
# 第一次查询会从ClickHouse读取
data1 = await cold_storage.get_historical_trades(...)

# 1小时内的相同查询会从缓存返回
data2 = await cold_storage.get_historical_trades(...)  # 更快
```

### 分区策略选择

- **按月分区** (推荐): 适合大多数场景，平衡查询性能和管理复杂度
- **按天分区**: 适合高频数据，查询性能更好但分区数量多
- **按周分区**: 适合中频数据，减少分区数量

### 压缩算法选择

- **LZ4**: 压缩速度快，适合实时归档
- **ZSTD**: 压缩比高，适合长期存储
- **Delta**: 适合时间序列数据
- **DoubleDelta**: 适合价格等连续数值数据

## 故障排除

### 常见问题

**1. ClickHouse连接失败**
```
WARNING - 冷存储ClickHouse连接失败，使用Mock客户端
```
解决方案：
- 检查ClickHouse服务状态
- 验证连接配置参数
- 系统会自动使用Mock模式保证服务连续性

**2. 归档任务失败**
```
ERROR - 数据归档失败: ...
```
解决方案：
- 检查热存储和冷存储连接状态
- 验证数据格式和表结构
- 查看详细错误日志确定具体原因

**3. 查询性能慢**
```
查询耗时过长
```
解决方案：
- 检查查询时间范围是否合理
- 确认分区策略是否适合查询模式
- 优化ClickHouse配置

### 调试模式

启用详细日志：

```python
import logging
logging.getLogger('core.storage.cold_storage_manager').setLevel(logging.DEBUG)
```

### 监控告警

设置关键指标告警：

- 归档任务失败率 > 5%
- 查询错误率 > 10%
- 存储空间使用率 > 80%
- 归档延迟 > 2小时

## 最佳实践

### 1. 存储层级设计

```
热存储（1小时） → 冷存储（30天） → 长期归档（>30天）
     ↓              ↓                ↓
  实时查询        历史分析         合规存档
```

### 2. 归档策略

- 设置合理的归档阈值（建议7天）
- 定期监控归档任务执行状态
- 根据业务需求调整TTL设置

### 3. 查询优化

```python
# 使用合适的时间间隔
trends_hourly = await cold_storage.get_price_trends(..., interval='1h')
trends_daily = await cold_storage.get_price_trends(..., interval='1d')

# 批量查询多个交易对
exchanges = ['binance', 'okx', 'deribit']
for exchange in exchanges:
    data = await cold_storage.get_historical_trades(exchange, symbol, ...)
```

### 4. 监控集成

```python
# 定期检查系统健康
health = cold_storage.get_health_status()
if not health['is_healthy']:
    # 发送告警通知
    send_alert("冷存储系统不健康")

# 监控归档进度
stats = cold_storage.get_statistics()
if stats['archives_per_day'] < expected_archives:
    # 检查归档任务
    check_archive_task()
```

## 性能基准

基于E2E测试的性能数据：

- **归档性能**: 10000条/批次，平均10秒完成
- **查询性能**: 历史查询<500ms，趋势分析<1s
- **压缩效率**: LZ4压缩率约30-50%
- **分区效果**: 按月分区查询性能提升60%+
- **缓存命中率**: 70%+（重复查询场景）

## 总结

MarketPrism冷数据存储系统提供了：

- **完整的生命周期管理**: 从热存储自动归档到冷存储
- **高效的历史查询**: 分区优化和缓存加速
- **智能压缩存储**: 节省存储成本
- **自动化运维**: 无人值守的归档和清理
- **企业级监控**: 完整的监控和告警体系

通过冷存储系统，您可以构建完整的数据分层存储架构，既保证热数据的实时性能，又提供长期历史数据的可靠存储和高效查询能力。