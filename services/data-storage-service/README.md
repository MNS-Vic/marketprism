# MarketPrism 分层数据存储服务

MarketPrism的分层数据存储架构，实现热端实时存储和冷端归档存储，支持数据生命周期管理。

## 🏗️ 架构概述

### 分层存储架构

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   数据收集器     │───▶│   NATS队列      │───▶│   热端存储      │
│  (Data Collector)│    │  (Message Queue)│    │  (Hot Storage)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                        │
                                                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   冷端存储      │◀───│   数据同步      │◀───│   定时调度      │
│  (Cold Storage) │    │  (Data Sync)    │    │  (Scheduler)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### 数据流向

1. **实时数据收集** → **NATS JetStream** → **热端ClickHouse**
2. **定时同步任务** → **热端ClickHouse** → **冷端ClickHouse**
3. **数据生命周期管理** → **热端数据清理**

## 🚀 快速开始

### 1. 环境要求

- Docker & Docker Compose
- Python 3.11+
- ClickHouse 23.8+
- NATS 2.10+

### 2. 配置文件

复制并修改配置文件：

```bash
cp config/tiered_storage_config.yaml.example config/tiered_storage_config.yaml
```

关键配置项：

```yaml
# 热端存储配置（远程服务器）
hot_storage:
  clickhouse_host: "clickhouse-hot"
  clickhouse_database: "marketprism_hot"
  retention_days: 3

# 冷端存储配置（本地NAS）
cold_storage:
  clickhouse_host: "192.168.1.100"  # 本地NAS IP
  clickhouse_database: "marketprism_cold"
  retention_days: 365
```

### 3. 部署方式

#### 方式1：Docker Compose（推荐）

```bash
# 启动热端存储服务
docker-compose -f docker-compose.tiered-storage.yml up hot-storage-service

# 启动冷端归档服务（在本地NAS上）
docker-compose -f docker-compose.tiered-storage.yml --profile local-nas up cold-storage-service

# 启动完整服务栈
docker-compose -f docker-compose.tiered-storage.yml up
```

#### 方式2：直接运行

```bash
# 热端存储服务
python tiered_storage_main.py --mode hot --config config/tiered_storage_config.yaml

# 冷端归档服务
python tiered_storage_main.py --mode cold --config config/tiered_storage_config.yaml

# 同时运行两个服务
python tiered_storage_main.py --mode both --config config/tiered_storage_config.yaml
```

## 📊 服务组件

### 1. 热端数据存储服务 (Hot Storage Service)

**功能**：
- 从NATS JetStream订阅实时金融数据
- 将数据写入远程服务器的ClickHouse热端数据库
- 支持7种数据类型：orderbook, trades, funding_rate, open_interest, liquidation, lsr, volatility_index

**特点**：
- 高频实时写入
- 短期数据保留（2-3天）
- 优化的批量写入性能

### 2. 冷端数据归档服务 (Cold Storage Service)

**功能**：
- 定时从热端ClickHouse同步历史数据
- 将数据存储到本地NAS的ClickHouse冷端数据库
- 实现数据生命周期管理

**特点**：
- 定时批量同步
- 长期数据保留（1年+）
- 数据完整性验证

### 3. 分层存储管理器 (Tiered Storage Manager)

**功能**：
- 统一管理热端和冷端存储
- 数据传输任务调度和监控
- 存储层级间的数据迁移

**特点**：
- 异步任务处理
- 失败重试机制
- 完整的状态监控

## 🔧 配置说明

### 核心配置项

```yaml
# NATS配置
nats:
  url: "nats://nats:4222"
  max_reconnect_attempts: 10

# 热端存储配置
hot_storage:
  clickhouse_host: "clickhouse-hot"
  retention_days: 3
  batch_size: 1000

# 冷端存储配置
cold_storage:
  clickhouse_host: "192.168.1.100"
  retention_days: 365
  batch_size: 5000

# 同步配置
sync:
  interval_hours: 6
  batch_hours: 24
  cleanup_enabled: true
```

### 环境变量

```bash
# 运行模式
STORAGE_MODE=hot|cold|both

# 日志级别
LOG_LEVEL=DEBUG|INFO|WARNING|ERROR

# 环境
ENVIRONMENT=development|staging|production
```

## 📈 监控和运维

### 健康检查

```bash
# 检查热端服务
curl http://localhost:8085/health

# 检查冷端服务
curl http://localhost:8086/health
```

### 统计信息

```bash
# 获取服务统计
curl http://localhost:8085/stats

# 获取传输任务状态
curl http://localhost:8085/transfer-tasks
```

### 日志查看

```bash
# 查看热端服务日志
docker logs marketprism-hot-storage

# 查看冷端服务日志
docker logs marketprism-cold-storage
```

## 🔄 数据同步流程

### 自动同步

系统会自动执行以下同步流程：

1. **定时触发**：每6小时执行一次同步
2. **数据查询**：从热端ClickHouse查询指定时间范围的数据
3. **数据传输**：将数据批量写入冷端ClickHouse
4. **完整性验证**：验证传输数据的完整性
5. **清理热端**：可选择性清理已同步的热端数据

### 手动同步

```python
# 调度单个传输任务
task_id = await storage_manager.schedule_data_transfer(
    data_type="orderbook",
    exchange="binance_spot", 
    symbol="BTC-USDT",
    start_time=start_time,
    end_time=end_time
)

# 批量自动同步
task_ids = await storage_manager.auto_schedule_transfers(
    lookback_hours=24
)
```

## 🛠️ 开发指南

### 添加新的数据类型

1. 在`TieredStorageManager`中添加数据类型支持
2. 更新配置文件中的数据类型列表
3. 确保数据标准化器支持新类型

### 自定义同步策略

1. 继承`DataSyncTask`类
2. 实现自定义的同步逻辑
3. 在配置中指定自定义任务类

### 扩展存储后端

1. 实现新的存储写入器
2. 在`TieredStorageManager`中集成
3. 更新配置架构

## 🚨 故障排除

### 常见问题

1. **连接失败**
   - 检查ClickHouse服务状态
   - 验证网络连接和防火墙设置
   - 确认认证信息正确

2. **同步失败**
   - 查看传输任务状态
   - 检查磁盘空间
   - 验证数据格式

3. **性能问题**
   - 调整批量大小
   - 优化网络配置
   - 监控资源使用

### 日志分析

```bash
# 查找错误日志
grep "ERROR" /app/logs/*.log

# 监控同步进度
grep "传输任务" /app/logs/*.log

# 性能分析
grep "duration" /app/logs/*.log
```

## 📋 最佳实践

### 部署建议

1. **热端服务**：部署在靠近数据收集器的服务器上
2. **冷端服务**：部署在本地NAS或专用存储服务器上
3. **网络优化**：确保热端和冷端之间有稳定的网络连接
4. **监控告警**：设置关键指标的监控和告警

### 性能优化

1. **批量大小**：根据网络和存储性能调整批量大小
2. **并发控制**：限制并发传输任务数量
3. **压缩传输**：启用数据压缩减少网络传输
4. **索引优化**：在ClickHouse中创建合适的索引

### 安全考虑

1. **网络安全**：使用VPN或专用网络连接
2. **数据加密**：启用传输和存储加密
3. **访问控制**：配置适当的用户权限
4. **备份策略**：定期备份重要配置和数据

## 📞 支持

如有问题或建议，请联系MarketPrism开发团队或提交Issue。
