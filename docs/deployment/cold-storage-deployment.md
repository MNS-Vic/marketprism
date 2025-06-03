# MarketPrism 冷数据服务器部署指南

## 📋 概述

MarketPrism 冷数据服务器用于存储历史市场数据，实现数据分层存储架构：
- **热存储**: 近期数据（14天），高性能查询
- **冷存储**: 历史数据（长期），高压缩比存储
- **自动归档**: 定期将热数据迁移到冷存储

## 🏗️ 架构设计

```
┌─────────────────┐    归档    ┌─────────────────┐
│   热存储服务器   │  --------> │   冷存储服务器   │
│  ClickHouse      │    数据    │  ClickHouse     │
│  (主服务器)      │    迁移    │  (NAS/存储)     │
└─────────────────┘            └─────────────────┘
        │                              │
        │                              │
    实时查询                         历史查询
        │                              │
        └──────────┬───────────────────┘
                   │
            ┌─────────────┐
            │ 查询路由器  │
            │ (智能分发)  │
            └─────────────┘
```

## 💻 硬件要求

### 最低配置
- **CPU**: 4核心以上（推荐8核心）
- **内存**: 16GB以上（推荐32GB）
- **存储**: 2TB+ HDD/SSD（根据数据量规划）
- **网络**: 千兆网络连接

### 推荐配置（NAS部署）
- **专业NAS设备**: Synology DS920+, QNAP TS-464等
- **存储阵列**: RAID5/6配置，提供冗余保护
- **网络**: 双千兆网络，确保数据传输带宽

## 🚀 部署步骤

### 步骤1: 环境准备

```bash
# 检查Docker环境
docker --version
docker-compose --version

# 创建项目目录
mkdir -p /opt/marketprism-cold
cd /opt/marketprism-cold
```

### 步骤2: 下载配置文件

```bash
# 下载冷存储配置
wget https://raw.githubusercontent.com/your-repo/marketprism/main/docker-compose.cold-storage.yml
wget https://raw.githubusercontent.com/your-repo/marketprism/main/scripts/manage_cold_storage.sh

# 设置执行权限
chmod +x scripts/manage_cold_storage.sh
```

### 步骤3: 配置存储目录

```bash
# 创建数据目录
mkdir -p data/clickhouse-cold
mkdir -p logs/clickhouse-cold
mkdir -p backup/cold
mkdir -p config/clickhouse-cold

# 设置权限（确保ClickHouse可以写入）
sudo chown -R 101:101 data/clickhouse-cold
sudo chown -R 101:101 logs/clickhouse-cold
```

### 步骤4: 启动冷存储服务

```bash
# 启动服务
./scripts/manage_cold_storage.sh start

# 或者直接使用docker-compose
docker-compose -f docker-compose.cold-storage.yml up -d
```

### 步骤5: 验证部署

```bash
# 检查服务状态
./scripts/manage_cold_storage.sh status

# 测试连接
./scripts/manage_cold_storage.sh test

# 查看日志
./scripts/manage_cold_storage.sh logs
```

## 🔧 网络配置

### 代理配置（如需要）

```bash
# 设置代理环境变量
export http_proxy=http://127.0.0.1:1087
export https_proxy=http://127.0.0.1:1087
export ALL_PROXY=socks5://127.0.0.1:1080

# 为Docker配置代理
sudo mkdir -p /etc/systemd/system/docker.service.d
sudo tee /etc/systemd/system/docker.service.d/http-proxy.conf > /dev/null << EOF
[Service]
Environment="HTTP_PROXY=http://127.0.0.1:1087"
Environment="HTTPS_PROXY=http://127.0.0.1:1087"
Environment="ALL_PROXY=socks5://127.0.0.1:1080"
EOF

# 重启Docker服务
sudo systemctl daemon-reload
sudo systemctl restart docker
```

### 镜像源配置

如果网络访问慢，可以配置国内镜像源：

```bash
# 配置Docker镜像源
sudo tee /etc/docker/daemon.json > /dev/null << EOF
{
  "registry-mirrors": [
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com",
    "https://mirror.baidubce.com"
  ]
}
EOF

# 重启Docker
sudo systemctl restart docker
```

## 📊 数据库初始化

### 自动初始化

服务启动后会自动创建数据库和表：

```sql
-- 数据库
CREATE DATABASE marketprism_cold;

-- 市场数据表
CREATE TABLE marketprism_cold.market_data (
    timestamp DateTime64(3),
    exchange String,
    symbol String,
    data_type String,
    price Float64,
    volume Float64,
    raw_data String,
    created_at DateTime64(3) DEFAULT now()
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (exchange, symbol, data_type, timestamp);
```

### 手动初始化

如果需要手动初始化：

```bash
# 连接到ClickHouse容器
docker exec -it marketprism-clickhouse-cold clickhouse-client

# 执行初始化SQL
CREATE DATABASE IF NOT EXISTS marketprism_cold;
CREATE TABLE IF NOT EXISTS marketprism_cold.market_data (...);
```

## 🔄 数据归档配置

### 手动归档

```bash
# 归档7天前的数据
docker exec marketprism-clickhouse-1 clickhouse-client --query "
INSERT INTO remote('nas-clickhouse:9000', 'marketprism_cold.market_data')
SELECT * FROM marketprism.market_data 
WHERE toDate(timestamp) <= today() - INTERVAL 7 DAY
"

# 删除已归档的热数据
docker exec marketprism-clickhouse-1 clickhouse-client --query "
ALTER TABLE marketprism.market_data 
DELETE WHERE toDate(timestamp) <= today() - INTERVAL 7 DAY
"
```

### 自动归档（Cron任务）

```bash
# 编辑crontab
crontab -e

# 添加每日凌晨2点执行归档
0 2 * * * /opt/marketprism-cold/scripts/auto_archive.sh
```

创建归档脚本：

```bash
#!/bin/bash
# auto_archive.sh

echo "$(date): 开始数据归档..." >> /var/log/marketprism-archive.log

# 归档数据
docker exec marketprism-clickhouse-1 clickhouse-client --query "
INSERT INTO remote('冷存储IP:9001', 'marketprism_cold.market_data')
SELECT * FROM marketprism.market_data 
WHERE toDate(timestamp) <= today() - INTERVAL 14 DAY
" >> /var/log/marketprism-archive.log 2>&1

# 清理热数据
docker exec marketprism-clickhouse-1 clickhouse-client --query "
ALTER TABLE marketprism.market_data 
DELETE WHERE toDate(timestamp) <= today() - INTERVAL 14 DAY
" >> /var/log/marketprism-archive.log 2>&1

echo "$(date): 数据归档完成" >> /var/log/marketprism-archive.log
```

## 📈 监控和维护

### 存储空间监控

```bash
# 查看存储使用情况
./scripts/manage_cold_storage.sh storage

# 数据库大小查询
docker exec marketprism-clickhouse-cold clickhouse-client --query "
SELECT 
    database,
    table,
    formatReadableSize(sum(bytes)) as size,
    sum(rows) as rows
FROM system.parts 
WHERE database = 'marketprism_cold'
GROUP BY database, table
ORDER BY sum(bytes) DESC
"
```

### 性能优化

```sql
-- 优化查询性能，创建索引
ALTER TABLE marketprism_cold.market_data 
ADD INDEX idx_exchange_symbol (exchange, symbol) TYPE minmax GRANULARITY 1;

-- 启用数据压缩
ALTER TABLE marketprism_cold.market_data 
MODIFY COLUMN raw_data String CODEC(LZ4HC);
```

### 备份策略

```bash
# 数据备份
./scripts/manage_cold_storage.sh backup

# 使用clickhouse-backup工具（推荐）
docker exec marketprism-clickhouse-cold clickhouse-backup create
docker exec marketprism-clickhouse-cold clickhouse-backup upload
```

## 🔍 故障排除

### 常见问题

1. **容器启动失败**
   ```bash
   # 查看日志
   docker logs marketprism-clickhouse-cold
   
   # 检查端口冲突
   netstat -tlnp | grep 9001
   ```

2. **连接超时**
   ```bash
   # 检查防火墙
   sudo ufw status
   sudo ufw allow 9001
   sudo ufw allow 8124
   ```

3. **磁盘空间不足**
   ```bash
   # 清理旧数据
   docker system prune -a
   
   # 压缩数据表
   docker exec marketprism-clickhouse-cold clickhouse-client --query "
   OPTIMIZE TABLE marketprism_cold.market_data FINAL
   "
   ```

### 性能调优

```xml
<!-- 冷存储专用配置 -->
<clickhouse>
    <merge_tree>
        <max_suspicious_broken_parts>5</max_suspicious_broken_parts>
        <parts_to_delay_insert>150</parts_to_delay_insert>
        <parts_to_throw_insert>300</parts_to_throw_insert>
    </merge_tree>
    
    <compression>
        <case>
            <method>lz4hc</method>
            <level>9</level>
        </case>
    </compression>
</clickhouse>
```

## 🎯 最佳实践

### 1. 存储规划
- 热存储：保留14天实时数据
- 冷存储：按月分区，便于管理
- 备份策略：定期全量+增量备份

### 2. 网络优化
- 使用专用网络连接热存储和冷存储
- 配置负载均衡，避免单点故障
- 启用数据压缩，减少网络传输

### 3. 查询优化
- 实现智能查询路由
- 缓存常用历史数据查询
- 使用物化视图预聚合数据

### 4. 安全配置
- 配置用户权限管理
- 启用访问日志记录
- 定期更新安全补丁

## 📞 技术支持

如果在部署过程中遇到问题：

1. 查看项目文档：`docs/`目录
2. 检查日志文件：`logs/clickhouse-cold/`
3. 提交Issue：项目GitHub仓库
4. 联系技术支持：`support@marketprism.com`

---

**部署完成后，您将拥有一个高效的分层存储系统，能够自动管理海量历史数据，同时保持实时查询的高性能！** 🎉 