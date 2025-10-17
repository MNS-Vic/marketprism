# 🗄️ MarketPrism Data Storage Service
> 重要：以 scripts/manage_all.sh 为唯一运行总线索。唯一入口：`services/hot-storage-service/main.py`；唯一配置：`services/hot-storage-service/config/hot_storage_config.yaml` 与 `services/hot-storage-service/config/clickhouse_schema.sql`。冷端请使用 `services/cold-storage-service/scripts/manage.sh` 独立管理。


[![Python](https://img.shields.io/badge/python-3.12+-green.svg)](requirements.txt)
[![ClickHouse](https://img.shields.io/badge/clickhouse-23.8+-blue.svg)](#clickhouse-integration)
[![Status](https://img.shields.io/badge/status-production_ready-brightgreen.svg)](#)

**企业级数据存储服务** - 高性能批处理引擎，支持8种数据类型的智能存储和管理

## 📊 概览

MarketPrism Data Storage Service是一个高性能的数据存储和处理服务，负责从NATS消息队列接收数据，进行智能批处理，并高效存储到ClickHouse数据库中。

### 🎯 核心功能

- **📡 NATS消息消费**: 高效订阅和处理多种数据类型
- **🔧 智能批处理**: 差异化批处理策略，优化不同频率数据
- **🗄️ ClickHouse集成**: 高性能列式数据库存储
- **🔄 时间戳标准化**: 统一时间戳格式处理
- **📈 性能监控**: 实时性能统计和健康检查
- **🛡️ 错误处理**: 完善的异常处理和恢复机制
- **📊 数据质量**: 数据验证和完整性检查

## 🚀 快速开始

### 前置要求

- Python 3.12+
- ClickHouse 23.8+
- NATS Server 2.9+

### 启动服务

```bash
# 推荐：分步启动（各模块可独立部署）
cd /home/ubuntu/marketprism
source venv/bin/activate

# 1) 启动基础设施（如未运行）
# NATS（仅外部模式，由 message-broker 的 Compose 启动）
cd services/message-broker
# 新版 Compose 插件可用：docker compose -f docker-compose.nats.yml up -d
sudo docker-compose -f docker-compose.nats.yml up -d
cd ../../
# ClickHouse
docker run -d --name marketprism-clickhouse -p 8123:8123 -p 9000:9000 clickhouse/clickhouse-server:23.8

# 2) 初始化数据库（仅首次/变更后）
python3 services/hot-storage-service/scripts/init_clickhouse_db.py

### 仅外部 NATS 模式与环境变量覆盖
- 本服务不托管/内置 NATS，始终以“客户端”身份连接外部 NATS（推荐用 message-broker 模块的 docker-compose.nats.yml 启动）
- 配置文件中的 NATS 地址默认来自 YAML；若设置环境变量 MARKETPRISM_NATS_URL，将覆盖 YAML/默认地址
- 若同时设置其他历史变量（例如 NATS_URL），则以 MARKETPRISM_NATS_URL 为最终生效值

示例：
```bash
# 覆盖 Storage 的 NATS 连接地址
export MARKETPRISM_NATS_URL="nats://127.0.0.1:4222"
python3 services/hot-storage-service/main.py
```


# 3) 启动 Collector 与 Storage
nohup python3 -u services/data-collector/main.py > logs/collector.log 2>&1 &
nohup python3 -u services/hot-storage-service/main.py > logs/storage.log 2>&1 &
```


### NATS Subject 命名规范
- funding_rate.>
- open_interest.>
- lsr_top_position.>
- lsr_all_account.>
- orderbook.>
- trade.>
- liquidation.>
- volatility_index.>





## 📈 支持的数据类型和批处理配置

| 数据类型 | 批次大小 | 超时时间 | 最大队列 | 频率特性 |
|---------|---------|---------|---------|---------|
| **Orderbooks** | 100条 | 10.0秒 | 1000条 | 高频 |
| **Trades** | 100条 | 10.0秒 | 1000条 | 超高频 |
| **Funding Rates** | 10条 | 2.0秒 | 500条 | 中频 |
| **Open Interests** | 50条 | 10.0秒 | 500条 | 低频 |
| **Liquidations** | 5条 | 10.0秒 | 200条 | 事件驱动 |
| **LSR Top Positions** | 1条 | 1.0秒 | 50条 | 低频 |
| **LSR All Accounts** | 1条 | 1.0秒 | 50条 | 低频 |
| **Volatility Indices** | 1条 | 1.0秒 | 50条 | 低频 |

## 系统维护

### NATS订阅问题修复

**问题描述**: Storage服务可能遇到"nats: must use coroutine for subscriptions"错误

**解决方案**: 已在Storage服务中添加完整的async回调函数集合：
- `error_cb`: 异步错误处理
- `disconnected_cb`: 断线处理
- `reconnected_cb`: 重连处理
- `closed_cb`: 连接关闭处理

**验证方法**:
```bash
# 检查Storage服务日志
tail -f logs/storage.log

# 应该看到正常的消息处理，而不是订阅错误
```

### 配置化热→冷数据迁移

**开发阶段快速迁移**（推荐5分钟间隔）:
```bash
# 启动每5分钟迁移一次，窗口8小时
./scripts/start_hot_to_cold_migrator.sh

# 查看迁移日志
tail -f logs/migrator.log

# 停止迁移
./scripts/stop_migrator.sh
```

**自定义迁移配置**:
```bash
# 每2分钟迁移一次，窗口4小时
./scripts/start_hot_to_cold_migrator.sh 120 4

# 极速验证：每30秒，窗口3分钟
./scripts/start_hot_to_cold_migrator.sh 30 0.05
```


### 系统启动和停止标准流程

**完整系统启动**:
```bash
cd /home/ubuntu/marketprism
source venv/bin/activate

# 分步启动（推荐）
# 1. 启动基础设施
# NATS（仅外部模式，由 message-broker 的 Compose 启动）
cd services/message-broker
# 新版 Compose 插件可用：docker compose -f docker-compose.nats.yml up -d
sudo docker-compose -f docker-compose.nats.yml up -d
cd ../../
# ClickHouse
docker run -d --name marketprism-clickhouse -p 8123:8123 -p 9000:9000 clickhouse/clickhouse-server:23.8

# 2. 初始化数据库
python3 services/hot-storage-service/scripts/init_clickhouse_db.py

# 3. 启动服务
nohup python3 -u services/data-collector/main.py > logs/collector.log 2>&1 &
nohup python3 -u services/hot-storage-service/main.py > logs/storage.log 2>&1 &

```

**系统停止**:
```bash
# 停止所有MarketPrism进程
pkill -f "services/data-collector/main.py"
pkill -f "main.py"

# 停止Docker容器
docker stop marketprism-nats marketprism-clickhouse
docker rm marketprism-nats marketprism-clickhouse
```

**健康检查**:
```bash
# 检查进程状态
ps aux | grep -E "(collector|storage)" | grep -v grep

# 检查数据写入
curl -s "http://localhost:8123/?database=marketprism_hot" --data-binary "SELECT count() FROM trades"

```

### 故障排查指南

**1. Storage服务无法启动**
```bash
# 检查NATS连接
curl -s http://localhost:8222/varz | jq '.connections'

# 检查ClickHouse连接
curl -s "http://localhost:8123/" --data-binary "SELECT 1"

# 查看详细错误日志
tail -n 50 logs/storage.log
```

**2. 数据未写入ClickHouse**
```bash
# 检查NATS消息流
curl -s http://localhost:8222/jsz | jq '.streams'

# 检查Storage订阅状态
grep "订阅成功\|subscription" logs/storage.log

# 验证数据库表结构
curl -s "http://localhost:8123/?database=marketprism_hot" --data-binary "DESCRIBE trades"
```


**4. 性能问题**
```bash
# 检查系统资源
htop

# 检查ClickHouse性能
curl -s "http://localhost:8123/" --data-binary "SELECT * FROM system.processes"

# 检查批处理统计
grep "批处理统计\|batch" logs/storage.log
```

### 配置文件说明

**权威 Schema（热端）**: `services/hot-storage-service/config/clickhouse_schema.sql`
**热端存储配置**: `services/hot-storage-service/config/hot_storage_config.yaml`

> 说明：列结构在热/冷两端完全一致（时间列统一为 DateTime64(3,'UTC')；created_at 默认 now64(3)）。TTL 策略不同是预期行为：热端 3 天、冷端 3650 天。

### 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `MARKETPRISM_NATS_URL` | `nats://localhost:4222` | 推荐设置；覆盖 YAML 与其他同类变量（优先于 `NATS_URL`） |
| `NATS_URL` | `nats://localhost:4222` | 历史兼容变量；若同时设置，以 `MARKETPRISM_NATS_URL` 为准 |
| `HOT_STORAGE_HTTP_PORT` | `8081` | 热端服务HTTP端口（本地直跑可设置为18080） |
| `CLICKHOUSE_HOST` | `localhost` | ClickHouse主机（容器内通常为 `clickhouse-hot`） |
| `CLICKHOUSE_HTTP_PORT` | `8123` | ClickHouse HTTP端口 |
| `CLICKHOUSE_TCP_PORT` | `9000` | ClickHouse TCP端口 |
| `CLICKHOUSE_HOT_DB` | `marketprism_hot` | 热端数据库名 |
| `CLICKHOUSE_COLD_DB` | `marketprism_cold` | 冷端数据库名 |
| `MIGRATION_WINDOW_HOURS` | `8` | 迁移窗口时长（小时） |
| `MIGRATION_BATCH_LIMIT` | `5000000` | 单次迁移记录上限 |
| `MIGRATION_SYMBOL_PREFIX` | 空 | 迁移过滤：符号前缀（示例：`MPTEST`） |
| `MIGRATION_EXCHANGE` | 空 | 迁移过滤：交易所（示例：`binance_derivatives`） |
| `MIGRATION_MARKET_TYPE` | 空 | 迁移过滤：市场类型（示例：`perpetual`） |
| `MIGRATION_DRY_RUN` | `0` | 干跑（1/true/yes 启用，仅统计不写入/删除） |
## 📄 许可证

### 时间戳统一标准（ts_ms + DateTime64(3,'UTC')）

- 全链路统一以 `ts_ms`（Int64，UTC毫秒）作为唯一“权威时间戳”字段。
- ClickHouse 所有时间列统一为 `DateTime64(3, 'UTC')`；写入时使用：`toDateTime64(ts_ms/1000.0, 3, 'UTC')`。
- 若上游仅提供秒级时间戳，毫秒位按规则补零（000），确保统一到毫秒粒度。
- 核验示例：
  - `SELECT toUnixTimestamp64Milli(timestamp) AS ts_ms_db, /* 对比 */ FROM marketprism_hot.trades ORDER BY timestamp DESC LIMIT 1`。
  - 对具备毫秒来源的数据，`ts_ms_db % 1000` 应与上游毫秒位一致；秒级来源可能为 0。


本项目采用 MIT 许可证 - 查看 [LICENSE](../../LICENSE) 文件了解详情
