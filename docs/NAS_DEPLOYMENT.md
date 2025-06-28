# MarketPrism NAS冷存储部署指南

## 📋 部署概述

本文档说明如何在NAS服务器上部署MarketPrism冷存储服务，实现热/冷数据分离架构。

## 🏗️ 架构说明

### 数据流转机制
1. **热数据存储**：部署在主服务器，保留3天数据
2. **冷数据存储**：部署在NAS服务器，长期保存数据
3. **自动迁移**：每天凌晨2-6点自动将热数据迁移到冷存储

### Docker镜像策略
- **统一镜像**：使用同一个Docker镜像
- **环境变量区分**：通过`STORAGE_MODE=cold`切换到冷存储模式

## 🚀 NAS部署步骤

### 1. 准备NAS环境

在UGOS Pro上创建项目目录：
```bash
mkdir -p /volume1/docker/marketprism-cold
cd /volume1/docker/marketprism-cold
```

### 2. 创建Docker Compose配置

创建`docker-compose.yml`文件：

```yaml
version: '3.8'

services:
  # ClickHouse 冷存储数据库
  clickhouse-cold:
    image: clickhouse/clickhouse-server:24.3-alpine
    container_name: marketprism-clickhouse-cold
    ports:
      - "8123:8123"
      - "9000:9000"
    environment:
      CLICKHOUSE_DB: marketprism_cold
      CLICKHOUSE_USER: default
      CLICKHOUSE_PASSWORD: ""
    volumes:
      - clickhouse_cold_data:/var/lib/clickhouse
      - clickhouse_cold_logs:/var/log/clickhouse-server
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:8123/ping"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

  # MarketPrism 冷存储服务
  data-storage-cold:
    image: marketprism:latest  # 使用统一镜像
    container_name: marketprism-data-storage-cold
    environment:
      - STORAGE_MODE=cold
      - CLICKHOUSE_HOST=clickhouse-cold
      - CLICKHOUSE_PORT=8123
      - CLICKHOUSE_USER=default
      - CLICKHOUSE_PASSWORD=""
      - CLICKHOUSE_DATABASE=marketprism_cold
      - LOG_LEVEL=INFO
      - API_PORT=8087
    ports:
      - "8087:8087"
    depends_on:
      clickhouse-cold:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8087/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

volumes:
  clickhouse_cold_data:
    driver: local
  clickhouse_cold_logs:
    driver: local
```

### 3. 创建配置文件

创建`config/storage_unified.yaml`：

```yaml
# NAS冷存储配置
clickhouse:
  host: "clickhouse-cold"
  port: 8123
  user: "default"
  password: ""
  database: "marketprism_cold"

ttl:
  cold_retention_days: 365  # 冷数据保留1年
  cleanup_interval_hours: 24

compression:
  cold_codec: "ZSTD"
  cold_level: 3

partition:
  cold_partition_by: "toYYYYMM(timestamp), exchange"

migration:
  enabled: false  # 冷存储不启用迁移
```

### 4. 部署到NAS

在UGOS Pro Docker应用中：

1. **创建项目**：
   - 项目名称：`marketprism-cold`
   - 存放路径：`/volume1/docker/marketprism-cold`

2. **导入配置**：
   - 将上述`docker-compose.yml`内容粘贴到配置中

3. **设置环境变量**：
   - `STORAGE_MODE=cold`
   - `CLICKHOUSE_DATABASE=marketprism_cold`

4. **启动服务**：
   - 点击"立即部署"

### 5. 验证部署

检查服务状态：
```bash
# 检查ClickHouse
curl http://NAS_IP:8123/ping

# 检查冷存储服务
curl http://NAS_IP:8087/health
```

## 🔗 网络配置

### 主服务器配置

在主服务器的`docker-compose.yml`中添加NAS连接：

```yaml
environment:
  - COLD_CLICKHOUSE_HOST=NAS_IP  # 替换为实际NAS IP
  - COLD_CLICKHOUSE_PORT=8123
  - COLD_CLICKHOUSE_DATABASE=marketprism_cold
```

### 防火墙设置

确保以下端口可访问：
- `8123`: ClickHouse HTTP接口
- `8087`: 冷存储服务API

## 📊 数据迁移配置

### 自动迁移设置

在主服务器的配置中：

```yaml
migration:
  enabled: true
  schedule_cron: "0 2 * * *"  # 每天凌晨2点
  cold_storage_endpoint: "http://NAS_IP:8123"
  batch_size: 10000
  verification_enabled: true
```

### 手动迁移

```bash
# 触发手动迁移
curl -X POST http://主服务器IP:8088/api/v1/migration/execute

# 查看迁移状态
curl http://主服务器IP:8088/api/v1/migration/status
```

## 🔍 监控和维护

### 健康检查

```bash
# 检查冷存储服务
curl http://NAS_IP:8087/health

# 检查数据库连接
curl http://NAS_IP:8087/api/v1/storage/status
```

### 数据验证

```bash
# 查看冷存储数据量
curl "http://NAS_IP:8123/" --data-binary "
SELECT 
    table,
    count() as records,
    formatReadableSize(sum(bytes_on_disk)) as size
FROM system.parts 
WHERE database = 'marketprism_cold' AND active = 1
GROUP BY table
"
```

### 日志查看

在UGOS Pro中查看容器日志：
1. 进入Docker应用
2. 选择`marketprism-cold`项目
3. 查看各服务的日志

## 🛠️ 故障排除

### 常见问题

1. **连接超时**
   - 检查防火墙设置
   - 确认NAS IP地址正确

2. **数据迁移失败**
   - 检查网络连接
   - 验证ClickHouse服务状态

3. **存储空间不足**
   - 监控NAS存储使用率
   - 调整TTL设置

### 性能优化

1. **ClickHouse优化**
   ```sql
   -- 优化合并设置
   SET max_bytes_to_merge_at_max_space_in_pool = 161061273600;
   SET merge_with_ttl_timeout = 3600;
   ```

2. **网络优化**
   - 使用有线连接
   - 配置专用VLAN

## 📈 扩展配置

### 多NAS部署

支持多个NAS节点的负载均衡：

```yaml
cold_storage_endpoints:
  - "http://nas1:8123"
  - "http://nas2:8123"
  - "http://nas3:8123"
```

### 备份策略

```yaml
backup:
  enabled: true
  schedule: "0 0 * * 0"  # 每周备份
  retention_weeks: 4
  remote_backup: true
```

## ✅ 部署检查清单

- [ ] NAS Docker环境准备完成
- [ ] ClickHouse冷存储服务启动
- [ ] 冷存储API服务正常
- [ ] 网络连接测试通过
- [ ] 主服务器迁移配置完成
- [ ] 自动迁移任务设置
- [ ] 监控和告警配置
- [ ] 备份策略实施

## 🎯 下一步

1. 配置Grafana监控面板
2. 设置告警通知
3. 实施数据备份策略
4. 性能调优和容量规划
