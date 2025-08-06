# MarketPrism容器和模块配置指南

## 📋 系统架构概览

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Data Collector │───▶│      NATS       │───▶│ Storage Service │───▶│   ClickHouse    │
│   (Container)   │    │   (Container)   │    │    (Process)    │    │   (Container)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🐳 容器配置详情

### 1. Data Collector容器 (marketprism-data-collector)

#### **入口文件**
- **主入口**: `services/data-collector/unified_collector_main.py`
- **Docker入口**: `services/data-collector/Dockerfile` → `CMD ["python", "unified_collector_main.py", "launcher"]`

#### **配置文件**
```yaml
# Docker配置
services/data-collector/docker-compose.unified.yml

# 应用配置目录
services/data-collector/config/
├── collector/           # 数据收集器配置
├── logging/            # 日志配置
└── nats/               # NATS连接配置
```

#### **环境变量**
```bash
# 基础配置
PYTHONPATH=/app
LOG_LEVEL=INFO
PYTHONUNBUFFERED=1

# NATS连接
NATS_URL=nats://localhost:4222
NATS_STREAM=MARKET_DATA

# 运行模式
COLLECTOR_MODE=launcher  # 完整数据收集系统
```

#### **启动命令**
```bash
# 构建和启动
cd services/data-collector
sudo docker-compose -f docker-compose.unified.yml build
sudo docker-compose -f docker-compose.unified.yml up -d

# 查看日志
sudo docker logs marketprism-data-collector -f
```

#### **健康检查**
- **端口**: 8086 (健康检查)
- **监控端口**: 9093 (Prometheus指标)
- **检查URL**: `http://localhost:8086/health`

---

### 2. NATS容器 (marketprism-nats-unified)

#### **入口文件**
- **Docker镜像**: `nats:latest`
- **配置文件**: `services/message-broker/unified-nats/nats-server.conf`

#### **配置文件**
```yaml
# Docker配置
services/message-broker/unified-nats/docker-compose.unified.yml

# NATS服务器配置
services/message-broker/unified-nats/nats-server.conf
```

#### **NATS配置详情**
```conf
# 基础连接
host: 0.0.0.0
port: 4222

# JetStream配置
jetstream {
    store_dir: "/data/jetstream"
    max_memory_store: 1GB
    max_file_store: 10GB
    sync_interval: "2m"
}

# 性能限制
max_connections: 1000
max_payload: 1048576
max_pending: 67108864
```

#### **端口映射**
- **4222**: NATS客户端连接
- **8222**: HTTP监控端口
- **6222**: 集群端口（可选）

#### **启动命令**
```bash
# 启动NATS
cd services/message-broker/unified-nats
docker-compose -f docker-compose.unified.yml up -d

# 查看状态
curl http://localhost:8222/healthz
```

#### **数据卷**
- **JetStream存储**: `/data/jetstream`
- **日志目录**: `/var/log/nats`

---

### 3. ClickHouse容器 (marketprism-clickhouse-hot)

#### **入口文件**
- **Docker镜像**: `clickhouse/clickhouse-server:23.8-alpine`
- **初始化脚本**: `services/data-storage-service/config/clickhouse_schema.sql`

#### **配置文件**
```yaml
# Docker配置
services/data-storage-service/docker-compose.hot-storage.yml

# 数据库配置
services/data-storage-service/config/
├── clickhouse_schema.sql      # 表结构定义
├── clickhouse-config.xml      # 服务器配置
└── create_hot_tables.sql      # 热存储表创建
```

#### **环境变量**
```bash
# 数据库配置
CLICKHOUSE_DB=marketprism_hot
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=
CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1
```

#### **端口映射**
- **8123**: HTTP接口 (查询和管理)
- **9000**: TCP接口 (Native协议)

#### **启动命令**
```bash
# 启动ClickHouse
cd services/data-storage-service
docker-compose -f docker-compose.hot-storage.yml up clickhouse-hot -d

# 测试连接
curl "http://localhost:8123/" --data "SELECT 1"
```

#### **数据卷**
- **数据存储**: `/var/lib/clickhouse`
- **配置挂载**: `/etc/clickhouse-server/config.d/`

#### **表结构**
```sql
-- 8种数据类型的表
- orderbooks          # 订单簿数据
- trades              # 交易数据
- funding_rates       # 资金费率
- open_interests      # 未平仓量
- liquidations        # 强平数据
- lsr_top_positions   # LSR顶级持仓
- lsr_all_accounts    # LSR全账户
- volatility_indices  # 波动率指数
```

---

## 🔧 非容器化模块

### 4. Storage Service (生产级进程)

#### **入口文件**
- **主入口**: `services/data-storage-service/production_cached_storage.py`

#### **配置文件**
```python
# 内置配置 (在代码中)
services/data-storage-service/production_cached_storage.py

# 外部配置文件
services/data-storage-service/config/
├── unified_storage_service.yaml
├── tiered_storage_config.yaml
└── production_tiered_storage_config.yaml
```

#### **批处理配置**
```python
# 高频数据
'orderbooks': {'batch_size': 100, 'timeout': 10.0, 'max_queue': 1000}
'trades': {'batch_size': 100, 'timeout': 10.0, 'max_queue': 1000}

# 中频数据
'funding_rates': {'batch_size': 10, 'timeout': 2.0, 'max_queue': 500}
'open_interests': {'batch_size': 50, 'timeout': 10.0, 'max_queue': 500}

# 低频数据
'liquidations': {'batch_size': 5, 'timeout': 10.0, 'max_queue': 200}
'lsr_top_position': {'batch_size': 1, 'timeout': 1.0, 'max_queue': 50}
'lsr_all_account': {'batch_size': 1, 'timeout': 1.0, 'max_queue': 50}
'volatility_index': {'batch_size': 1, 'timeout': 1.0, 'max_queue': 50}
```

#### **启动命令**
```bash
# 启动存储服务
cd services/data-storage-service
nohup python3 production_cached_storage.py > production_lsr_final.log 2>&1 &

# 查看日志
tail -f production_lsr_final.log

# 停止服务
pkill -f production_cached_storage.py
```

#### **连接配置**
```python
# NATS连接
NATS_URL = "nats://localhost:4222"
NATS_SUBJECTS = [
    "orderbook-data.>",
    "trade-data.>", 
    "funding-rate-data.>",
    "open-interest-data.>",
    "liquidation-data.>",
    "lsr-data.>",
    "volatility-index-data.>"
]

# ClickHouse连接
CLICKHOUSE_URL = "http://localhost:8123"
DATABASE = "marketprism_hot"
```

---

## 🚀 系统启动顺序

### 完整启动流程
```bash
# 1. 启动NATS (第一个)
cd services/message-broker/unified-nats
docker-compose -f docker-compose.unified.yml up -d

# 2. 启动ClickHouse (第二个)
cd services/data-storage-service
docker-compose -f docker-compose.hot-storage.yml up clickhouse-hot -d

# 3. 启动Storage Service (第三个)
cd services/data-storage-service
nohup python3 production_cached_storage.py > production_lsr_final.log 2>&1 &

# 4. 启动Data Collector (最后)
cd services/data-collector
sudo docker-compose -f docker-compose.unified.yml up -d
```

### 验证启动状态
```bash
# 检查所有容器
sudo docker ps --format 'table {{.Names}}\t{{.Status}}'

# 检查NATS
curl http://localhost:8222/healthz

# 检查ClickHouse
curl "http://localhost:8123/" --data "SELECT 1"

# 检查Storage Service
tail -5 services/data-storage-service/production_lsr_final.log

# 检查Data Collector
sudo docker logs marketprism-data-collector --since 1m
```

---

## 📊 监控和管理

### 健康检查端点
- **NATS**: `http://localhost:8222/healthz`
- **ClickHouse**: `http://localhost:8123/ping`
- **Data Collector**: `http://localhost:8086/health`

### 日志文件位置
- **Data Collector**: `sudo docker logs marketprism-data-collector`
- **NATS**: `sudo docker logs marketprism-nats-unified`
- **ClickHouse**: `sudo docker logs marketprism-clickhouse-hot`
- **Storage Service**: `services/data-storage-service/production_lsr_final.log`

### 配置文件优先级
1. **环境变量** (最高优先级)
2. **Docker Compose配置文件**
3. **应用配置文件**
4. **代码内置默认值** (最低优先级)

---

## 🔧 故障排查

### 常见问题
1. **容器启动失败**: 检查端口占用和Docker网络
2. **NATS连接失败**: 验证4222端口和JetStream配置
3. **ClickHouse连接失败**: 检查8123端口和数据库初始化
4. **数据写入停止**: 检查Storage Service进程和批处理配置

### 快速诊断命令
```bash
# 系统状态检查
sudo docker ps -a
netstat -tlnp | grep -E "(4222|8123|8086)"
ps aux | grep -E "(python|clickhouse|nats)"

# 数据流验证
curl "http://localhost:8123/" --data "SELECT count(*) FROM marketprism_hot.trades WHERE timestamp > now() - INTERVAL 1 MINUTE"
```
