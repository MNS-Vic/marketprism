# 实时OrderBook写入器使用指南

## 概述

实时OrderBook写入器是MarketPrism系统的核心组件之一，负责将OrderBook Manager维护的标准化订单簿数据每秒写入一次到ClickHouse数据库。该组件支持完整的400档深度数据存储，采用分层压缩技术，实现高效的数据存储和查询。

## 核心特性

### 🚀 实时写入
- **写入频率**: 每秒1次，确保数据实时性
- **批量优化**: 可配置批量大小，默认50条记录
- **异步处理**: 非阻塞式写入，不影响数据收集

### 📊 完整深度数据
- **400档深度**: 买盘400档 + 卖盘400档
- **分层存储**: L1(前50档)、L2(51-200档)、L3(201-400档)
- **快速查询**: 针对不同查询需求优化的存储结构

### 🗜️ 高效压缩
- **ZSTD压缩**: 压缩比6-9倍，节省90%存储空间
- **分层压缩**: 不同层级使用不同压缩级别
- **压缩监控**: 实时监控压缩比和性能

### 🔧 配置化管理
- **YAML配置**: 灵活的配置文件管理
- **多交易所支持**: 支持Binance、OKX、Deribit等
- **环境变量**: 支持环境变量覆盖配置

## 快速开始

### 1. 环境准备

确保已安装必要的依赖：

```bash
# 安装Python依赖
pip install -r requirements.txt

# 启动ClickHouse
docker-compose -f docker-compose.infrastructure.yml up -d clickhouse
```

### 2. 配置文件

编辑配置文件 `config/realtime_orderbook_writer.yaml`：

```yaml
# ClickHouse连接配置
clickhouse:
  host: "localhost"
  port: 8123
  database: "marketprism"
  user: "default"
  password: ""
  batch_size: 50
  compression_level: 6

# 实时写入配置
realtime_writer:
  enabled: true
  write_interval: 1.0
  symbols:
    - "BTCUSDT"
    - "ETHUSDT"
    - "BNBUSDT"

# 交易所配置
exchange:
  name: "binance"
  market_type: "spot"
  api:
    base_url: "https://api.binance.com"
    ws_url: "wss://stream.binance.com:9443/ws"
    depth_limit: 400
    snapshot_interval: 300
```

### 3. 启动服务

```bash
# 启动实时OrderBook写入服务
python run_realtime_orderbook_writer.py
```

### 4. 验证运行

```bash
# 测试写入器功能
python test_realtime_orderbook_writer.py

# 查询写入的数据
python query_realtime_orderbook.py
```

## 详细配置说明

### ClickHouse配置

```yaml
clickhouse:
  host: "localhost"           # ClickHouse服务器地址
  port: 8123                  # HTTP端口
  database: "marketprism"     # 数据库名称
  user: "default"             # 用户名
  password: ""                # 密码
  batch_size: 50              # 批量写入大小
  compression_level: 6        # 压缩级别 (1-9)
  table_name: "orderbook_realtime"  # 表名
  ttl_days: 7                 # 数据保留天数
```

### 实时写入器配置

```yaml
realtime_writer:
  enabled: true               # 是否启用
  write_interval: 1.0         # 写入间隔(秒)
  symbols:                    # 监控的交易对
    - "BTCUSDT"
    - "ETHUSDT"
  quality_control:            # 数据质量控制
    min_depth_levels: 10      # 最小深度档位数
    max_spread_percent: 5.0   # 最大价差百分比
    validate_checksum: true   # 是否验证校验和
```

### 交易所配置

```yaml
exchange:
  name: "binance"             # 交易所名称
  market_type: "spot"         # 市场类型
  api:
    base_url: "https://api.binance.com"
    ws_url: "wss://stream.binance.com:9443/ws"
    depth_limit: 400          # 深度档位限制
    snapshot_interval: 300    # 快照刷新间隔(秒)
  proxy:                      # 代理配置(可选)
    enabled: false
    http_proxy: "http://127.0.0.1:1087"
    https_proxy: "http://127.0.0.1:1087"
```

## 数据表结构

实时OrderBook写入器创建的ClickHouse表结构：

```sql
CREATE TABLE marketprism.orderbook_realtime (
    exchange_name LowCardinality(String),
    symbol_name LowCardinality(String),
    update_id UInt64,
    update_type LowCardinality(String),
    
    -- 快速查询字段
    best_bid_price Float64,
    best_ask_price Float64,
    best_bid_qty Float64,
    best_ask_qty Float64,
    spread Float64,
    mid_price Float64,
    
    -- 深度统计
    total_bid_volume Float64,
    total_ask_volume Float64,
    bid_volume_1pct Float64,
    ask_volume_1pct Float64,
    depth_levels UInt16,
    
    -- 分层压缩深度数据
    bids_l1 String CODEC(ZSTD(3)),   -- 前50档
    asks_l1 String CODEC(ZSTD(3)),
    bids_l2 String CODEC(ZSTD(6)),   -- 51-200档
    asks_l2 String CODEC(ZSTD(6)),
    bids_l3 String CODEC(ZSTD(9)),   -- 201-400档
    asks_l3 String CODEC(ZSTD(9)),
    
    -- 完整深度数据
    bids_full String CODEC(ZSTD(9)),
    asks_full String CODEC(ZSTD(9)),
    
    -- 质量控制
    checksum UInt64,
    is_valid UInt8,
    
    -- 时间戳
    timestamp DateTime64(3) CODEC(Delta, ZSTD(1)),
    collected_at DateTime64(3) CODEC(Delta, ZSTD(1)),
    write_time DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (exchange_name, symbol_name, timestamp, update_id)
TTL timestamp + INTERVAL 7 DAY
SETTINGS index_granularity = 8192
```

## 数据查询示例

### 1. 查询最近的订单簿数据

```sql
SELECT 
    exchange_name,
    symbol_name,
    best_bid_price,
    best_ask_price,
    spread,
    total_bid_volume,
    total_ask_volume,
    timestamp
FROM marketprism.orderbook_realtime
WHERE symbol_name = 'BTCUSDT'
ORDER BY timestamp DESC
LIMIT 10
```

### 2. 分析价差变化

```sql
SELECT 
    symbol_name,
    toStartOfMinute(timestamp) as minute,
    AVG(spread) as avg_spread,
    MIN(spread) as min_spread,
    MAX(spread) as max_spread
FROM marketprism.orderbook_realtime
WHERE timestamp >= now() - INTERVAL 1 HOUR
GROUP BY symbol_name, minute
ORDER BY symbol_name, minute DESC
```

### 3. 解压深度数据

使用Python脚本解压深度数据：

```python
import json
import zlib

def decompress_depth_data(compressed_hex: str):
    """解压深度数据"""
    compressed_bytes = bytes.fromhex(compressed_hex)
    decompressed_data = zlib.decompress(compressed_bytes).decode()
    return json.loads(decompressed_data)

# 查询压缩的深度数据
query = """
SELECT bids_l1, asks_l1 
FROM marketprism.orderbook_realtime 
WHERE symbol_name = 'BTCUSDT' 
ORDER BY timestamp DESC 
LIMIT 1
"""

# 解压数据
bids_l1 = decompress_depth_data(result[0][0])
asks_l1 = decompress_depth_data(result[0][1])

print(f"前5档买单: {bids_l1[:5]}")
print(f"前5档卖单: {asks_l1[:5]}")
```

## 监控和运维

### 统计信息

实时写入器提供详细的统计信息：

```python
# 获取统计信息
stats = realtime_writer.get_stats()
print(f"总写入次数: {stats['total_writes']}")
print(f"成功写入次数: {stats['successful_writes']}")
print(f"失败写入次数: {stats['failed_writes']}")
print(f"平均压缩比: {stats['avg_compression_ratio']}")
print(f"平均写入延迟: {stats['avg_write_latency']}")
print(f"队列大小: {stats['queue_size']}")
```

### 性能监控

关键性能指标：

- **写入频率**: 应保持每秒1次
- **成功率**: 应 ≥ 95%
- **写入延迟**: 应 < 100ms
- **压缩比**: 通常6-9倍
- **队列大小**: 应 < 1000

### 告警设置

建议设置以下告警：

```yaml
alerts:
  max_queue_size: 1000        # 最大队列大小
  max_write_latency: 5.0      # 最大写入延迟(秒)
  min_success_rate: 0.95      # 最小成功率
```

## 故障排除

### 常见问题

#### 1. ClickHouse连接失败

**症状**: 启动时报连接错误
**解决方案**:
```bash
# 检查ClickHouse是否运行
docker ps | grep clickhouse

# 检查端口是否开放
telnet localhost 8123

# 检查配置文件中的连接信息
```

#### 2. 写入延迟过高

**症状**: 平均写入延迟 > 1秒
**解决方案**:
- 减少批量大小
- 检查ClickHouse性能
- 优化网络连接

#### 3. 压缩比异常

**症状**: 压缩比 < 3倍
**解决方案**:
- 检查数据质量
- 调整压缩级别
- 验证数据格式

#### 4. 队列积压

**症状**: 队列大小持续增长
**解决方案**:
- 增加批量大小
- 减少写入间隔
- 检查ClickHouse写入性能

### 日志分析

启用详细日志：

```python
import structlog

# 设置日志级别为DEBUG
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)
```

## 最佳实践

### 1. 配置优化

- **批量大小**: 根据写入频率调整，建议50-100
- **压缩级别**: 平衡压缩比和CPU使用，建议6
- **TTL设置**: 根据存储需求设置数据保留期

### 2. 性能优化

- **分区策略**: 按日期分区，便于查询和维护
- **索引优化**: 合理设置ORDER BY字段
- **压缩优化**: 使用CODEC压缩，节省存储空间

### 3. 监控策略

- **实时监控**: 监控写入频率、成功率、延迟
- **容量监控**: 监控存储使用量、压缩比
- **质量监控**: 监控数据完整性、校验和

### 4. 运维建议

- **定期备份**: 定期备份重要数据
- **性能调优**: 根据监控数据调优配置
- **版本管理**: 保持配置文件版本控制

## API参考

### RealtimeOrderBookWriter类

```python
class RealtimeOrderBookWriter:
    def __init__(self, orderbook_manager, clickhouse_config: Dict)
    async def start(self, symbols: List[str])
    async def stop(self)
    def get_stats(self) -> Dict
```

### 配置加载器

```python
class ConfigLoader:
    def load_realtime_orderbook_config(self) -> Dict[str, Any]
    def get_clickhouse_config(self, config: Dict[str, Any]) -> Dict[str, Any]
    def validate_config(self, config: Dict[str, Any]) -> bool
```

## 更新日志

### v1.0.0 (2025-01-28)
- ✅ 初始版本发布
- ✅ 支持每秒写入ClickHouse
- ✅ 分层压缩存储
- ✅ 配置化管理
- ✅ 完整的监控和统计

## 支持

如有问题或建议，请：

1. 查看日志文件获取详细错误信息
2. 检查配置文件是否正确
3. 参考故障排除章节
4. 提交Issue到项目仓库

---

*本文档最后更新: 2025-01-28*