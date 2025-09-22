# MarketPrism 统一存储服务验证清单

## 📋 启动前检查清单

### 环境准备
- [ ] **虚拟环境**: 已激活 Python 虚拟环境 (`source venv/bin/activate`)
- [ ] **Docker 服务**: Docker 守护进程正在运行
- [ ] **端口检查**: 确认以下端口未被占用
  - [ ] 4222 (NATS 客户端端口)
  - [ ] 8222 (NATS 监控端口)
  - [ ] 8123 (ClickHouse HTTP 端口)
  - [ ] 9000 (ClickHouse TCP 端口)

### 环境变量配置
- [ ] **NATS 配置**:
  ```bash
  export MARKETPRISM_NATS_SERVERS="nats://127.0.0.1:4222"
  ```
- [ ] **ClickHouse 配置**:
  ```bash
  export MARKETPRISM_CLICKHOUSE_HOST="127.0.0.1"
  export MARKETPRISM_CLICKHOUSE_PORT="8123"
  export MARKETPRISM_CLICKHOUSE_DATABASE="marketprism_hot"  # 重要！
  ```

## 🚀 服务启动顺序

### 1. 基础设施启动
- [ ] **启动 NATS 容器**:
  ```bash
  cd services/message-broker
  docker-compose -f docker-compose.nats.yml up -d
  ```
- [ ] **启动 ClickHouse 容器**:
  ```bash
  cd services/data-storage-service
  docker-compose -f docker-compose.hot-storage.yml up -d
  ```

### 2. 数据库初始化
- [ ] **等待 ClickHouse 就绪** (最多等待 2 分钟)
- [ ] **初始化 ClickHouse 数据库和表**:
  ```bash
  python services/data-storage-service/scripts/init_clickhouse_db.py
  ```
- [ ] **初始化 NATS JetStream**:
  ```bash
  python services/data-storage-service/scripts/init_nats_stream.py \
    --config services/data-storage-service/config/production_tiered_storage_config.yaml
  ```

### 3. 服务启动
- [ ] **启动统一存储服务**（建议本地直跑对齐健康检查端口 18080）:
  ```bash
  env HOT_STORAGE_HTTP_PORT=18080 python services/data-storage-service/main.py
  ```
- [ ] **启动数据收集器**:
  ```bash
  python services/data-collector/unified_collector_main.py --mode launcher
  ```

## 🔍 健康检查

### 基础设施检查
- [ ] **NATS 健康检查**:
  ```bash
  curl -s http://127.0.0.1:8222/varz | grep -q "server_id"
  ```
- [ ] **ClickHouse 连接检查**:
  ```bash
  curl -s "http://127.0.0.1:8123/?query=SELECT%201" | grep -q "1"
  ```

### 数据库检查
- [ ] **验证数据库存在**:
  ```bash
  curl -s "http://127.0.0.1:8123/?query=SHOW%20DATABASES" | grep -q "marketprism_hot"
  ```
- [ ] **验证表结构**:
  ```bash
  curl -s "http://127.0.0.1:8123/?query=SHOW%20TABLES%20FROM%20marketprism_hot" | wc -l
  # 应该返回 8 (8张表)
  ```

### 数据流检查
- [ ] **检查数据写入** (启动服务后等待 2-3 分钟):
  ```bash
  # 检查各表数据计数
  for table in trades orderbooks funding_rates open_interests liquidations lsr_top_positions lsr_all_accounts volatility_indices; do
    count=$(curl -s "http://127.0.0.1:8123/?query=SELECT%20count()%20FROM%20marketprism_hot.$table")
    echo "$table: $count"
  done
  ```

## 🧪 一键验证脚本

### 10分钟长跑测试
- [ ] **运行完整验证**:
  ```bash
  bash scripts/run_unified_longrun.sh
  ```

该脚本将自动执行：
- ✅ 启动所有必要的容器和服务
- ✅ 初始化数据库和 JetStream
- ✅ 运行 10 分钟数据收集测试
- ✅ 每 30 秒采样 8 张表的数据计数
- ✅ 注入测试消息验证链路完整性
- ✅ 完成后自动清理所有进程和容器

### 预期结果
长跑完成后应看到类似结果：
```
--- Final counts ---
trades: 1847
orderbooks: 4923
funding_rates: 6
open_interests: 8
liquidations: 1
lsr_top_positions: 1
lsr_all_accounts: 1
volatility_indices: 3
```

## ❌ 常见问题排查

### 数据库连接问题
- **症状**: 日志显示 "ClickHouse连接失败，使用Mock客户端"
- **原因**: 数据库名配置错误或 ClickHouse 未就绪
- **解决**: 
  - [ ] 确认 `MARKETPRISM_CLICKHOUSE_DATABASE=marketprism_hot`
  - [ ] 检查 ClickHouse 容器状态: `docker ps | grep clickhouse`
  - [ ] 验证数据库存在: `curl -s "http://127.0.0.1:8123/?query=SHOW%20DATABASES"`

### NATS 连接问题
- **症状**: 服务启动失败，提示 NATS 连接错误
- **原因**: NATS 容器未启动或端口被占用
- **解决**:
  - [ ] 检查 NATS 容器状态: `docker ps | grep nats`
  - [ ] 检查端口占用: `netstat -tlnp | grep 4222`
  - [ ] 重启 NATS 容器: `docker-compose -f docker-compose.nats.yml restart`

### 数据未写入问题
- **症状**: 服务运行正常但表计数为 0
- **原因**: 存储服务使用 Mock 客户端或数据收集器未启动
- **解决**:
  - [ ] 检查存储服务日志，确认使用真实 ClickHouse 客户端
  - [ ] 确认数据收集器正在运行: `ps aux | grep unified_collector_main`
  - [ ] 检查 NATS JetStream 消息计数: `curl -s http://127.0.0.1:8222/jsz`

### aiochclient/sqlparse 依赖问题
- **症状**: 报错 "first argument must be string or compiled pattern"
- **原因**: aiochclient 与 sqlparse 版本不兼容
- **解决**: MarketPrism 已使用 SimpleClickHouseHttpClient 绕过此问题
  - [ ] 确认代码使用 SimpleClickHouseHttpClient 而非 aiochclient
  - [ ] 检查日志中的连接成功消息包含 "(HTTP)" 标识

## 🧹 清理操作

### 手动清理
如需手动停止和清理：
```bash
# 停止 Python 进程
pkill -f main.py
pkill -f unified_collector_main.py

# 停止并清理容器
cd services/data-storage-service
docker-compose -f docker-compose.hot-storage.yml down -v

cd ../message-broker
docker-compose -f docker-compose.nats.yml down -v

# 清理临时文件
rm -f /tmp/storage_*.log /tmp/collector_*.log
```

### 自动清理
长跑脚本会自动执行清理，无需手动操作。

## ✅ 验证完成标准

统一存储服务验证成功的标准：
- [ ] 所有 8 张表都有数据写入 (计数 > 0)
- [ ] 高频数据 (trades, orderbooks) 计数 > 1000
- [ ] 低频数据 (funding_rates, open_interests) 计数 > 0
- [ ] 特殊数据 (liquidations, LSR, volatility_indices) 计数 > 0
- [ ] 服务运行稳定，无错误日志
- [ ] 清理操作完成，无残留进程或容器

---

**注意**: 本清单基于 MarketPrism v1.0 统一存储架构，确保按顺序执行每个步骤以获得最佳结果。
