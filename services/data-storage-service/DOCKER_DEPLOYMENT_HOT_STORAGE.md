# MarketPrism Data Storage Service - 热存储Docker部署指南

## 🔄 **Docker部署简化改造 (2025-08-02)**

### **🎯 简化改造成果**
- ✅ **支持8种数据类型**: orderbook, trade, funding_rate, open_interest, liquidation, lsr_top_position, lsr_all_account, volatility_index
- ✅ **优化ClickHouse建表**: 分离LSR数据类型，优化分区和索引
- ✅ **简化NATS订阅**: 统一主题订阅，自动数据类型识别
- ✅ **Docker集成**: 与统一NATS容器和Data Collector完美集成
- ✅ **自动建表**: 启动时自动创建ClickHouse表结构

### **🏗️ 系统架构**
```
Data Collector (launcher模式)
    ↓ (NATS JetStream)
Hot Storage Service
    ↓ (ClickHouse HTTP API)
ClickHouse热存储数据库
```

## 🚀 **快速部署**

### **前置条件**
1. 统一NATS容器已启动
2. Data Collector已启动并正在收集数据
3. Docker和Docker Compose已安装

### **部署步骤**

#### **1. 启动热存储服务**
```bash
cd services/data-storage-service
sudo docker-compose -f docker-compose.hot-storage.yml up -d
```

#### **2. 验证部署**
```bash
# 检查容器状态
sudo docker ps | grep marketprism

# 检查ClickHouse健康状态
curl -s http://localhost:8123/ping

# 检查热存储服务健康状态
curl -s http://localhost:8080/health

# 查看服务日志
sudo docker logs marketprism-hot-storage-service --tail 50
```

#### **3. 验证数据流**
```bash
# 检查数据库和表
curl -s "http://localhost:8123/" --data "SHOW DATABASES"
curl -s "http://localhost:8123/" --data "SHOW TABLES FROM marketprism_hot"

# 检查数据写入
curl -s "http://localhost:8123/" --data "SELECT count() FROM marketprism_hot.orderbooks"
curl -s "http://localhost:8123/" --data "SELECT count() FROM marketprism_hot.trades"
```

## 📋 **配置说明**

### **环境变量配置**
```bash
# 基础配置
LOG_LEVEL=INFO

# NATS配置
MARKETPRISM_NATS_SERVERS=nats://localhost:4222

# ClickHouse配置
CLICKHOUSE_HOST=clickhouse-hot
CLICKHOUSE_DATABASE=marketprism_hot
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=

# 服务配置
STORAGE_SERVICE_PORT=8080
```

### **支持的数据类型**
| 数据类型 | 表名 | 描述 |
|---------|------|------|
| orderbook | orderbooks | 订单簿深度数据 |
| trade | trades | 实时成交数据 |
| funding_rate | funding_rates | 资金费率数据 |
| open_interest | open_interests | 未平仓量数据 |
| liquidation | liquidations | 强平数据 |
| lsr_top_position | lsr_top_positions | LSR顶级持仓比例 |
| lsr_all_account | lsr_all_accounts | LSR全账户比例 |
| volatility_index | volatility_indices | 波动率指数 |

### **ClickHouse表结构特性**
- **分区策略**: 按月份和交易所分区 `(toYYYYMM(timestamp), exchange)`
- **排序键**: 优化查询性能的复合排序键
- **TTL设置**: 热存储3天自动清理
- **压缩算法**: ZSTD高压缩比，Delta编码优化时间序列
- **索引优化**: 跳数索引提升查询性能

## 🔧 **技术架构**

### **数据流架构**
```
┌─────────────────────────────────────┐
│        Data Collector               │
│      (launcher模式)                 │
│  • 8种数据类型收集                  │
│  • 实时WebSocket连接                │
└─────────────────┬───────────────────┘
                  │ NATS JetStream
                  ▼
┌─────────────────────────────────────┐
│      Hot Storage Service            │
│  • NATS订阅和消息处理               │
│  • 数据验证和格式化                 │
│  • 批量写入优化                     │
└─────────────────┬───────────────────┘
                  │ ClickHouse HTTP API
                  ▼
┌─────────────────────────────────────┐
│      ClickHouse热存储数据库         │
│  • 8个优化表结构                    │
│  • 分区和索引优化                   │
│  • 3天TTL自动清理                   │
└─────────────────────────────────────┘
```

### **容器架构**
- **clickhouse-hot**: ClickHouse数据库容器
- **hot-storage-service**: 热存储服务容器
- **网络**: marketprism-storage-network
- **数据卷**: marketprism-clickhouse-hot-data

## 📊 **监控和维护**

### **健康检查**
```bash
# 服务健康检查
curl http://localhost:8080/health

# ClickHouse健康检查
curl http://localhost:8123/ping

# 数据统计检查
curl http://localhost:8080/stats
```

### **日志查看**
```bash
# 热存储服务日志
sudo docker logs marketprism-hot-storage-service

# ClickHouse日志
sudo docker logs marketprism-clickhouse-hot

# 实时日志跟踪
sudo docker-compose -f docker-compose.hot-storage.yml logs -f
```

### **性能监控**
```bash
# 数据库大小
curl -s "http://localhost:8123/" --data "
SELECT 
    database,
    table,
    formatReadableSize(sum(bytes)) as size,
    sum(rows) as rows
FROM system.parts 
WHERE database = 'marketprism_hot'
GROUP BY database, table
ORDER BY sum(bytes) DESC"

# 写入性能
curl -s "http://localhost:8123/" --data "
SELECT 
    table,
    count() as inserts_today
FROM system.query_log 
WHERE event_date = today() 
    AND query_kind = 'Insert'
    AND databases = ['marketprism_hot']
GROUP BY table"
```

## 🛠️ **故障排除**

### **常见问题**
1. **ClickHouse连接失败**: 检查容器状态和网络配置
2. **NATS订阅失败**: 确认统一NATS容器正常运行
3. **数据写入失败**: 检查表结构和数据格式
4. **内存不足**: 调整ClickHouse内存配置

### **调试命令**
```bash
# 检查容器网络
sudo docker network ls | grep marketprism

# 检查数据卷
sudo docker volume ls | grep marketprism

# 进入容器调试
sudo docker exec -it marketprism-hot-storage-service bash
sudo docker exec -it marketprism-clickhouse-hot clickhouse-client
```

## 🎉 **部署成功标志**

当看到以下情况时，说明部署成功：
1. ✅ 两个容器状态显示为"Up"且健康检查通过
2. ✅ ClickHouse中有8个表且数据持续写入
3. ✅ 热存储服务日志显示"数据处理完成"信息
4. ✅ 没有连接错误或异常日志

---

**🎊 MarketPrism热存储服务Docker部署完成！**
