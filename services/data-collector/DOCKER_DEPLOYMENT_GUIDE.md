# MarketPrism数据收集器 Docker部署指南

## 🚀 快速开始

### 1. 构建Docker镜像

```bash
# 在项目根目录执行
cd /home/ubuntu/marketprism
docker build -f services/data-collector/Dockerfile -t marketprism-collector:latest .
```

### 2. 单容器启动（推荐）

#### 完整数据收集系统模式（launcher）
```bash
docker run -d \
  --name marketprism-collector \
  -p 8086:8086 \
  -p 9093:9093 \
  -e COLLECTOR_MODE=launcher \
  -e MARKETPRISM_NATS_SERVERS=nats://host.docker.internal:4222 \
  -e LOG_LEVEL=INFO \
  --restart unless-stopped \
  marketprism-collector:latest
```

#### 数据收集模式（collector）
```bash
docker run -d \
  --name marketprism-collector \
  -e COLLECTOR_MODE=collector \
  -e MARKETPRISM_NATS_SERVERS=nats://host.docker.internal:4222 \
  -e LOG_LEVEL=INFO \
  --restart unless-stopped \
  marketprism-collector:latest
```

#### 微服务模式（service）
```bash
docker run -d \
  --name marketprism-collector-service \
  -p 8084:8084 \
  -e COLLECTOR_MODE=service \
  -e MARKETPRISM_NATS_SERVERS=nats://host.docker.internal:4222 \
  -e LOG_LEVEL=INFO \
  --restart unless-stopped \
  marketprism-collector:latest
```

### 3. 环境变量配置

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `COLLECTOR_MODE` | `launcher` | 运行模式：collector/service/test/launcher |
| `COLLECTOR_CONFIG_PATH` | `/app/config/collector/unified_data_collection.yaml` | 配置文件路径 |
| `MARKETPRISM_NATS_SERVERS` | `nats://localhost:4222` | NATS服务器地址 |
| `LOG_LEVEL` | `INFO` | 日志级别：DEBUG/INFO/WARNING/ERROR |
| `MARKETPRISM_BINANCE_API_KEY` | - | Binance API密钥（可选） |
| `MARKETPRISM_BINANCE_API_SECRET` | - | Binance API密钥（可选） |
| `MARKETPRISM_OKX_API_KEY` | - | OKX API密钥（可选） |
| `MARKETPRISM_OKX_API_SECRET` | - | OKX API密钥（可选） |
| `MARKETPRISM_OKX_PASSPHRASE` | - | OKX API密码（可选） |

### 4. 自定义配置文件

如果需要使用自定义配置文件：

```bash
docker run -d \
  --name marketprism-collector \
  -p 8086:8086 \
  -p 9093:9093 \
  -v /path/to/your/config.yaml:/app/config/collector/custom_config.yaml \
  -e COLLECTOR_MODE=launcher \
  -e COLLECTOR_CONFIG_PATH=/app/config/collector/custom_config.yaml \
  -e MARKETPRISM_NATS_SERVERS=nats://host.docker.internal:4222 \
  --restart unless-stopped \
  marketprism-collector:latest
```

## 🐳 Docker Compose部署（推荐）

### 1. 完整系统启动（包含NATS）

```bash
cd services/data-collector
docker-compose -f docker-compose.unified.yml up -d data-collector-launcher nats
```

### 2. 微服务模式启动

```bash
docker-compose -f docker-compose.unified.yml up -d data-collector-service nats
```

### 3. 测试验证模式

```bash
docker-compose -f docker-compose.unified.yml --profile test up data-collector-test nats
```

### 4. 启动所有服务

```bash
docker-compose -f docker-compose.unified.yml up -d
```

### 5. 自定义环境变量

```bash
COLLECTOR_MODE=launcher LOG_LEVEL=DEBUG docker-compose -f docker-compose.unified.yml up -d
```

## 🔍 验证部署

### 1. 健康检查

```bash
# launcher模式
curl http://localhost:8086/health

# service模式
curl http://localhost:8084/health

# 指标监控（launcher模式）
curl http://localhost:9093/metrics
```

### 2. 查看日志

```bash
# 查看容器日志
docker logs marketprism-collector

# 实时跟踪日志
docker logs -f marketprism-collector

# Docker Compose日志
docker-compose -f docker-compose.unified.yml logs -f data-collector-launcher
```

### 3. NATS连接验证

```bash
# 检查NATS连接
docker exec marketprism-collector curl -f http://nats:8222/varz

# 验证NATS消息（需要nats CLI）
docker run --rm --network marketprism_marketprism natsio/nats-box:latest nats sub "orderbook-data.>"
```

## 🛠️ 故障排除

### 1. 常见问题

**问题**: 容器无法连接到NATS服务器
```bash
# 解决方案：检查网络连接
docker network ls
docker network inspect marketprism_marketprism
```

**问题**: 健康检查失败
```bash
# 解决方案：检查端口映射和服务状态
docker ps
docker exec marketprism-collector netstat -tlnp
```

**问题**: 配置文件找不到
```bash
# 解决方案：检查配置文件路径
docker exec marketprism-collector ls -la /app/config/collector/
```

### 2. 调试模式

```bash
# 启动调试模式
docker run -it --rm \
  -e COLLECTOR_MODE=test \
  -e LOG_LEVEL=DEBUG \
  -e MARKETPRISM_NATS_SERVERS=nats://host.docker.internal:4222 \
  marketprism-collector:latest
```

## 📊 监控和维护

### 1. 容器状态监控

```bash
# 查看容器状态
docker stats marketprism-collector

# 查看容器资源使用
docker exec marketprism-collector top
```

### 2. 数据持久化

NATS数据会自动持久化到Docker volume中：

```bash
# 查看volumes
docker volume ls | grep nats

# 备份NATS数据
docker run --rm -v marketprism_nats_data:/data -v $(pwd):/backup alpine tar czf /backup/nats_backup.tar.gz -C /data .
```

### 3. 更新部署

```bash
# 重新构建镜像
docker build -f services/data-collector/Dockerfile -t marketprism-collector:latest .

# 重启服务
docker-compose -f docker-compose.unified.yml down
docker-compose -f docker-compose.unified.yml up -d
```

## 🔒 安全配置

### 1. 生产环境建议

- 使用非root用户运行（已配置）
- 限制容器资源使用
- 使用secrets管理API密钥
- 配置防火墙规则

### 2. 资源限制

```bash
docker run -d \
  --name marketprism-collector \
  --memory=1g \
  --cpus=1.0 \
  -e COLLECTOR_MODE=launcher \
  marketprism-collector:latest
```
