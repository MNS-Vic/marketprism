# MarketPrism 部署指南 - 完全固化版本

## 🚀 一键启动（推荐）

### 快速启动
```bash
# 克隆项目
git clone https://github.com/MNS-Vic/marketprism.git
cd marketprism

# 给脚本执行权限
chmod +x start_marketprism.sh stop_marketprism.sh

# 一键启动所有服务
./start_marketprism.sh
```

### 停止服务
```bash
# 停止所有服务
./stop_marketprism.sh

# 停止并清理所有资源
./stop_marketprism.sh --cleanup

# 停止、清理并删除未使用的镜像
./stop_marketprism.sh --cleanup --prune
```

## 📋 系统要求

- **操作系统**: Linux (推荐 Ubuntu 20.04+)
- **Docker**: 20.10+ 
- **Docker Compose**: v2.0+ (必须是 v2，不支持 v1)
- **内存**: 最少 4GB，推荐 8GB+
- **磁盘**: 最少 10GB 可用空间
- **网络**: 需要访问外部 API (Binance, OKX 等)

## 🏗️ 架构概览

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Data Sources  │    │   Message Broker │    │  Data Storage   │
│                 │    │                  │    │                 │
│ • Binance Spot  │───▶│  NATS JetStream  │───▶│   ClickHouse    │
│ • Binance Deriv │    │                  │    │   (Hot Storage) │
│ • OKX Spot      │    │ • Deduplication  │    │                 │
│ • OKX Deriv     │    │ • Persistence    │    │ • 8 Data Types  │
│ • Deribit       │    │ • Health Check   │    │ • Auto Schema   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## 🔧 服务组件

### 1. NATS JetStream (消息代理)
- **端口**: 4222 (NATS), 8222 (管理界面)
- **功能**: 消息队列、去重、持久化
- **健康检查**: http://localhost:8222/healthz

### 2. Data Collector (数据收集器)
- **功能**: 从多个交易所收集实时数据
- **支持交易所**: Binance, OKX, Deribit
- **数据类型**: orderbook, trade, funding_rate, open_interest, liquidation, lsr_*

### 3. ClickHouse (数据存储)
- **端口**: 8123 (HTTP), 9000 (TCP)
- **功能**: 高性能时序数据库
- **健康检查**: http://localhost:8123/ping

### 4. Hot Storage Service (热存储服务)
- **端口**: 8080
- **功能**: 从 NATS 订阅数据并写入 ClickHouse
- **健康检查**: http://localhost:8080/health

## 📊 数据类型

| 数据类型 | 表名 | 描述 |
|---------|------|------|
| orderbook | `marketprism_hot.orderbooks` | 订单簿数据 |
| trade | `marketprism_hot.trades` | 交易数据 |
| funding_rate | `marketprism_hot.funding_rates` | 资金费率 |
| open_interest | `marketprism_hot.open_interests` | 持仓量 |
| liquidation | `marketprism_hot.liquidations` | 清算数据 |
| lsr_top_positions | `marketprism_hot.lsr_top_positions` | 大户持仓 |
| lsr_all_accounts | `marketprism_hot.lsr_all_accounts` | 全账户数据 |
| volatility_indices | `marketprism_hot.volatility_indices` | 波动率指数 |

## 🔍 监控和验证

### 健康检查
```bash
# NATS 健康检查
curl http://localhost:8222/healthz

# ClickHouse 健康检查  
curl http://localhost:8123/ping

# 热存储服务健康检查
curl http://localhost:8080/health
```

### 数据验证
```bash
# 查看最近 10 分钟的数据统计
docker exec marketprism-clickhouse-hot clickhouse-client --query="
SELECT 
    'orderbooks' as table, 
    count() as count,
    if(count() > 0, toInt64(now()) - toInt64(max(timestamp)), NULL) as lag_seconds
FROM marketprism_hot.orderbooks 
WHERE timestamp > now() - INTERVAL 10 MINUTE
"

# 查看所有表的数据统计
for table in orderbooks trades funding_rates open_interests liquidations; do
    echo "=== $table ==="
    docker exec marketprism-clickhouse-hot clickhouse-client --query="
    SELECT count() FROM marketprism_hot.$table WHERE timestamp > now() - INTERVAL 1 HOUR
    "
done
```

### 日志查看
```bash
# 查看数据收集器日志
docker compose -f services/data-collector/docker-compose.unified.yml logs -f data-collector

# 查看热存储服务日志
docker compose -f services/data-storage-service/docker-compose.hot-storage.yml logs -f hot-storage-service

# 查看 NATS 日志
docker compose -f services/message-broker/docker-compose.nats.yml logs -f nats
```

## 🛠️ 手动部署（高级用户）

如果需要手动控制启动顺序：

```bash
# 1. 启动 NATS
docker compose -f services/message-broker/docker-compose.nats.yml up -d

# 2. 启动数据收集器
docker compose -f services/data-collector/docker-compose.unified.yml up -d

# 3. 启动 ClickHouse
docker compose -f services/data-storage-service/docker-compose.hot-storage.yml up -d clickhouse-hot

# 4. 启动热存储服务
docker compose -f services/data-storage-service/docker-compose.hot-storage.yml up -d hot-storage-service
```

## 🔧 配置说明

### 环境变量统一
所有服务统一使用 `MARKETPRISM_NATS_URL` 环境变量：
- **优先级**: `MARKETPRISM_NATS_URL` > `NATS_URL` > 默认值
- **默认值**: `nats://localhost:4222`

### Docker Compose v2 兼容
- 所有 compose 文件已移除 `version` 字段
- 网络配置使用 v2 默认管理
- 完全兼容 Docker Compose v2

## 🚨 故障排除

### 常见问题

1. **容器启动失败**
   ```bash
   # 检查 Docker 版本
   docker --version
   docker compose version
   
   # 清理旧资源
   ./stop_marketprism.sh --cleanup
   ./start_marketprism.sh
   ```

2. **数据不入库**
   ```bash
   # 检查服务健康状态
   curl http://localhost:8080/health
   
   # 查看存储服务日志
   docker compose -f services/data-storage-service/docker-compose.hot-storage.yml logs hot-storage-service
   ```

3. **网络连接问题**
   ```bash
   # 检查网络状态
   docker network ls
   
   # 重建网络
   ./stop_marketprism.sh --cleanup
   ./start_marketprism.sh
   ```

### 性能优化

1. **增加内存限制**
   - 编辑 `docker-compose.hot-storage.yml`
   - 调整 `mem_limit` 和 `cpus` 参数

2. **调整批量写入**
   - 编辑 `services/data-storage-service/simple_hot_storage.py`
   - 修改 `BATCH_SIZE` 和 `BATCH_TIMEOUT` 参数

## 📝 更新日志

### v2.0 (当前版本)
- ✅ 完全固化配置，消除混淆代码
- ✅ 统一 NATS 变量为 `MARKETPRISM_NATS_URL`
- ✅ Docker Compose v2 完全兼容
- ✅ 一键启动/停止脚本
- ✅ 完整的健康检查和验证
- ✅ 详细的故障排除指南

### v1.x (历史版本)
- 基础功能实现
- Docker Compose v1 支持
- 手动配置管理

## 📞 支持

如有问题，请：
1. 查看本文档的故障排除部分
2. 检查服务日志
3. 提交 GitHub Issue

---

**注意**: 此版本已完全固化配置，后人可直接使用 `./start_marketprism.sh` 无障碍启动系统。
