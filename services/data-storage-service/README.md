# 🗄️ MarketPrism Data Storage Service

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
python3 services/data-storage-service/scripts/init_clickhouse_db.py

### 仅外部 NATS 模式与环境变量覆盖
- 本服务不托管/内置 NATS，始终以“客户端”身份连接外部 NATS（推荐用 message-broker 模块的 docker-compose.nats.yml 启动）
- 配置文件中的 NATS 地址默认来自 YAML；若设置环境变量 MARKETPRISM_NATS_URL，将覆盖 YAML/默认地址
- 若同时设置其他历史变量（例如 NATS_URL），则以 MARKETPRISM_NATS_URL 为最终生效值

示例：
```bash
# 覆盖 Storage 的 NATS 连接地址
export MARKETPRISM_NATS_URL="nats://127.0.0.1:4222"
python3 services/data-storage-service/main.py
```


# 3) 启动 Collector 与 Storage
nohup python3 -u services/data-collector/unified_collector_main.py > logs/collector.log 2>&1 &
nohup python3 -u services/data-storage-service/main.py > logs/storage.log 2>&1 &
```

### 数据验证
```bash
# 端到端数据质量验证（覆盖率/样本/异常）
python3 services/data-storage-service/scripts/comprehensive_validation.py
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

### 🧊 容器一键：分层存储（热→冷）

```bash
# 一键启动（ClickHouse 热库 + 冷归档服务）
cd /home/ubuntu/marketprism
docker compose -f services/data-storage-service/docker-compose.tiered-storage.yml up -d clickhouse-hot cold-storage-service

# 查看冷端服务日志
docker logs --tail=120 -f marketprism-cold-storage

# 验证：冷库是否有数据（示例）
docker exec marketprism-clickhouse-hot clickhouse-client --query "SELECT 'trades', count() FROM marketprism_cold.trades UNION ALL SELECT 'orderbooks', count() FROM marketprism_cold.orderbooks"

# 手动快速迁移（示例：1小时内BTC-USDT）
docker exec marketprism-clickhouse-hot clickhouse-client --query "INSERT INTO marketprism_cold.trades (timestamp, exchange, market_type, symbol, trade_id, price, quantity, side, is_maker, trade_time, data_source, created_at) SELECT timestamp, exchange, market_type, symbol, trade_id, price, quantity, side, is_maker, trade_time, 'marketprism', now() FROM marketprism_hot.trades WHERE exchange='binance_spot' AND symbol='BTC-USDT' AND timestamp >= now()-interval 1 hour"
```

说明：
- 冷端归档服务已集成在模块主入口 main.py（--mode cold），由 tiered_storage_config.yaml 控制同步周期、窗口、清理策略
- 如遇端口冲突（8123/9000/8086），请先 kill 占用后再启动，不要改端口
- 开发/验证阶段可先手动迁移一小段窗口，确认表结构与数据一致，再开启定时


### 冷数据与迁移
```bash
# 初始化热/冷端库与表
python3 services/data-storage-service/scripts/init_clickhouse_db.py

# 执行热->冷迁移（默认迁移早于8小时的数据）
python3 services/data-storage-service/scripts/hot_to_cold_migrator.py
```

### 定时迁移（可配置间隔，开发阶段推荐5分钟）
```bash
# 启动循环迁移：默认每5分钟迁移一次，窗口=8小时
./scripts/start_hot_to_cold_migrator.sh

# 自定义：每2分钟迁移一次，窗口=4小时
./scripts/start_hot_to_cold_migrator.sh 120 4

# 停止循环迁移
./scripts/stop_migrator.sh

# 查看迁移日志
tail -f logs/migrator.log
```

说明：
- 循环迁移脚本是对一次性迁移脚本的包装，不修改业务逻辑，仅周期性执行
- 建议在开发/联调阶段使用较短间隔（例如5分钟），线上可改为15-60分钟
- 迁移窗口默认8小时，可按需调整


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

## � 系统维护

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

**环境变量配置**:
```bash
# 单次手动迁移
MIGRATION_WINDOW_HOURS="0.1" python3 services/data-storage-service/scripts/hot_to_cold_migrator.py
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
python3 services/data-storage-service/scripts/init_clickhouse_db.py

# 3. 启动服务
nohup python3 -u services/data-collector/unified_collector_main.py > logs/collector.log 2>&1 &
nohup python3 -u services/data-storage-service/main.py > logs/storage.log 2>&1 &

# 4. 启动迁移循环
./scripts/start_hot_to_cold_migrator.sh
```

**系统停止**:
```bash
# 停止所有MarketPrism进程
pkill -f "unified_collector_main.py"
pkill -f "main.py"
./scripts/stop_migrator.sh

# 停止Docker容器
docker stop marketprism-nats marketprism-clickhouse
docker rm marketprism-nats marketprism-clickhouse
```

**健康检查**:
```bash
# 检查进程状态
ps aux | grep -E "(collector|storage|migrator)" | grep -v grep

# 检查数据写入
curl -s "http://localhost:8123/?database=marketprism_hot" --data-binary "SELECT count() FROM trades"

# 检查最新数据
python3 services/data-storage-service/scripts/comprehensive_validation.py
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

**3. 迁移循环异常**
```bash
# 检查迁移进程
ps aux | grep migrator

# 查看迁移日志
tail -f logs/migrator.log

# 手动执行一次迁移测试
python3 services/data-storage-service/scripts/hot_to_cold_migrator.py
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

**热端存储配置**: `services/data-storage-service/config/clickhouse_schema_hot.sql`
**冷端存储配置**: `services/data-storage-service/config/clickhouse_schema_cold_fixed.sql`
**分层存储配置**: `services/data-storage-service/config/tiered_storage_config.yaml`

### 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `MARKETPRISM_NATS_URL` | `nats://localhost:4222` | 推荐设置；覆盖 YAML 与其他同类变量 |
| `NATS_URL` | `nats://localhost:4222` | 历史兼容变量；若同时设置，以 MARKETPRISM_NATS_URL 为准 |
| `CLICKHOUSE_HTTP_URL` | `http://localhost:8123/` | ClickHouse HTTP接口 |
| `CLICKHOUSE_HOT_DB` | `marketprism_hot` | 热端数据库名 |
| `CLICKHOUSE_COLD_DB` | `marketprism_cold` | 冷端数据库名 |
| `MIGRATION_WINDOW_HOURS` | `8` | 迁移窗口时长（小时） |
| `MIGRATION_BATCH_LIMIT` | `5000000` | 单次迁移记录上限 |
## �📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](../../LICENSE) 文件了解详情
