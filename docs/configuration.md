# MarketPrism订单簿管理系统配置指南

## 概述

本文档详细介绍了MarketPrism订单簿管理系统的配置选项、最佳实践和部署建议。

## 目录

- [环境变量配置](#环境变量配置)
- [交易所配置](#交易所配置)
- [NATS配置](#nats配置)
- [数据库配置](#数据库配置)
- [监控配置](#监控配置)
- [性能调优](#性能调优)
- [安全配置](#安全配置)
- [故障排除](#故障排除)

## 环境变量配置

### 基础配置

```bash
# 环境设置
ENVIRONMENT=production          # 环境类型: development, staging, production
MARKETPRISM_LOG_LEVEL=INFO    # 日志级别: DEBUG, INFO, WARN, ERROR
DEBUG_MODE=false              # 调试模式

# 服务端口
HEALTH_CHECK_PORT=8080        # 健康检查端口
PROMETHEUS_PORT=8081          # Prometheus指标端口
```

### 网络代理配置

如果需要通过代理访问交易所API：

```bash
# HTTP代理配置
HTTP_PROXY=http://proxy.company.com:8080
HTTPS_PROXY=http://proxy.company.com:8080
ALL_PROXY=socks5://proxy.company.com:1080

# 代理认证（如需要）
PROXY_USERNAME=your_username
PROXY_PASSWORD=your_password
```

## 交易所配置

### Binance配置

```bash
# API密钥配置
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here

# 订单簿深度配置
BINANCE_SNAPSHOT_DEPTH=5000   # 本地维护深度
BINANCE_NATS_PUBLISH_DEPTH=400 # NATS发布深度

# WebSocket配置
BINANCE_WS_ENDPOINT=wss://stream.binance.com:9443/ws
BINANCE_API_ENDPOINT=https://api.binance.com

# 限流配置
BINANCE_WEIGHT_LIMIT=1200     # 权重限制
BINANCE_REQUEST_LIMIT=10      # 请求频率限制
```

### OKX配置

```bash
# API密钥配置
OKX_API_KEY=your_api_key_here
OKX_API_SECRET=your_api_secret_here
OKX_PASSPHRASE=your_passphrase_here

# 订单簿深度配置
OKX_SNAPSHOT_DEPTH=400        # 本地维护深度
OKX_NATS_PUBLISH_DEPTH=400    # NATS发布深度

# WebSocket配置
OKX_WS_ENDPOINT=wss://ws.okx.com:8443/ws/v5/public
OKX_API_ENDPOINT=https://www.okx.com

# 限流配置
OKX_REQUEST_LIMIT=20          # 请求频率限制
```

### 交易对配置

在 `config/collector/symbols.yaml` 中配置支持的交易对：

```yaml
symbols:
  binance:
    spot:
      - BTCUSDT
      - ETHUSDT
      - BNBUSDT
      - ADAUSDT
      - SOLUSDT
  okx:
    spot:
      - BTC-USDT
      - ETH-USDT
      - BNB-USDT
      - ADA-USDT
      - SOL-USDT
```

## NATS配置

### 基础NATS配置

```bash
# NATS服务器配置
NATS_SERVERS=nats://localhost:4222
NATS_CLUSTER_ID=marketprism-cluster
NATS_CLIENT_ID=orderbook-manager

# JetStream配置
NATS_JETSTREAM_ENABLED=true
NATS_STREAM_RETENTION=24h
NATS_MAX_MEMORY=1GB
NATS_MAX_FILE=10GB
```

### 消息发布配置

```bash
# 批量发布配置
NATS_PUBLISH_BATCH_SIZE=100   # 批量大小
NATS_PUBLISH_TIMEOUT=5s       # 发布超时
NATS_PUBLISH_RETRIES=3        # 重试次数

# 主题配置
NATS_ORDERBOOK_SUBJECT=orderbook-data.{exchange}.{market_type}.{symbol}
NATS_TRADE_SUBJECT=trade-data.{exchange}.{market_type}.{symbol}
```

## 数据库配置

### ClickHouse配置

```bash
# 连接配置
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_USER=marketprism
CLICKHOUSE_PASSWORD=your_password_here
CLICKHOUSE_DATABASE=marketprism

# 连接池配置
CLICKHOUSE_MAX_CONNECTIONS=10
CLICKHOUSE_CONNECTION_TIMEOUT=30s
CLICKHOUSE_QUERY_TIMEOUT=60s

# 数据保留配置
CLICKHOUSE_TTL_DAYS=30        # 数据保留天数
CLICKHOUSE_PARTITION_BY=toYYYYMM(timestamp)
```

### Redis配置

```bash
# 连接配置
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=your_password_here
REDIS_DB=0

# 连接池配置
REDIS_MAX_CONNECTIONS=20
REDIS_CONNECTION_TIMEOUT=5s
REDIS_IDLE_TIMEOUT=300s

# 缓存配置
REDIS_CACHE_TTL=3600          # 缓存过期时间（秒）
REDIS_MAX_MEMORY=512MB        # 最大内存使用
```

## 监控配置

### Prometheus配置

```bash
# Prometheus配置
PROMETHEUS_ENABLED=true
PROMETHEUS_PORT=8081
PROMETHEUS_PATH=/metrics
PROMETHEUS_SCRAPE_INTERVAL=15s

# 指标配置
METRICS_ENABLED=true
METRICS_HISTOGRAM_BUCKETS=0.001,0.01,0.1,1,10
METRICS_SUMMARY_OBJECTIVES=0.5,0.9,0.95,0.99
```

### 告警配置

```bash
# 告警开关
ALERT_ENABLED=true
ALERT_EMAIL=admin@yourcompany.com
ALERT_WEBHOOK_URL=https://your-webhook-url.com

# 告警阈值
ALERT_ERROR_RATE_THRESHOLD=0.05      # 错误率阈值
ALERT_LATENCY_THRESHOLD=100          # 延迟阈值（毫秒）
ALERT_MEMORY_THRESHOLD=0.8           # 内存使用阈值
ALERT_CPU_THRESHOLD=0.8              # CPU使用阈值
```

## 性能调优

### 内存配置

```bash
# JVM内存配置（如果使用Java组件）
JAVA_OPTS="-Xms1g -Xmx2g -XX:+UseG1GC"

# Python内存配置
PYTHONMALLOC=malloc
MALLOC_ARENA_MAX=2

# 系统内存配置
MEMORY_LIMIT=2g               # 容器内存限制
SWAP_LIMIT=1g                 # 交换空间限制
```

### 并发配置

```bash
# 并发处理配置
MAX_CONCURRENT_SYMBOLS=50     # 最大并发交易对数
ORDERBOOK_UPDATE_BUFFER_SIZE=1000  # 更新缓冲区大小
WEBSOCKET_WORKER_THREADS=4    # WebSocket工作线程数

# 异步处理配置
ASYNC_QUEUE_SIZE=10000        # 异步队列大小
ASYNC_WORKER_COUNT=8          # 异步工作者数量
```

### 网络配置

```bash
# 连接配置
WEBSOCKET_RECONNECT_INTERVAL=5      # 重连间隔（秒）
WEBSOCKET_MAX_RECONNECT_ATTEMPTS=10 # 最大重连次数
WEBSOCKET_PING_INTERVAL=30          # 心跳间隔（秒）

# 超时配置
HTTP_TIMEOUT=30s              # HTTP请求超时
WEBSOCKET_TIMEOUT=60s         # WebSocket超时
DATABASE_TIMEOUT=30s          # 数据库查询超时
```

## 安全配置

### API安全

```bash
# JWT配置
JWT_SECRET_KEY=your_jwt_secret_key_here
JWT_EXPIRATION_TIME=3600      # Token过期时间（秒）
JWT_ALGORITHM=HS256           # 签名算法

# API限流
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=100       # 每分钟请求数
RATE_LIMIT_WINDOW=60          # 时间窗口（秒）
```

### 网络安全

```bash
# CORS配置
CORS_ENABLED=true
CORS_ALLOWED_ORIGINS=https://yourapp.com,https://dashboard.yourapp.com
CORS_ALLOWED_METHODS=GET,POST,PUT,DELETE
CORS_ALLOWED_HEADERS=Content-Type,Authorization

# TLS配置
TLS_ENABLED=true
TLS_CERT_FILE=/path/to/cert.pem
TLS_KEY_FILE=/path/to/key.pem
TLS_MIN_VERSION=1.2
```

## 故障排除

### 常见问题

#### 1. WebSocket连接失败

**症状**: 无法连接到交易所WebSocket
**解决方案**:
```bash
# 检查网络连接
curl -I https://stream.binance.com

# 检查代理配置
export HTTP_PROXY=http://your-proxy:8080
export HTTPS_PROXY=http://your-proxy:8080

# 检查防火墙设置
sudo ufw allow out 443
```

#### 2. 订单簿同步失败

**症状**: 订单簿数据不一致
**解决方案**:
```bash
# 增加同步超时时间
SYNC_TIMEOUT=60s

# 启用详细日志
MARKETPRISM_LOG_LEVEL=DEBUG

# 检查API限流
BINANCE_WEIGHT_LIMIT=1200
```

#### 3. NATS消息发布失败

**症状**: 消息无法发布到NATS
**解决方案**:
```bash
# 检查NATS连接
nats stream list

# 增加重试次数
NATS_PUBLISH_RETRIES=5

# 检查JetStream配置
NATS_JETSTREAM_ENABLED=true
```

### 日志配置

```bash
# 日志级别配置
MARKETPRISM_LOG_LEVEL=INFO    # DEBUG, INFO, WARN, ERROR

# 日志格式配置
LOG_FORMAT=json               # json, text
LOG_TIMESTAMP=true
LOG_CALLER=true

# 日志输出配置
LOG_FILE=/var/log/marketprism/app.log
LOG_MAX_SIZE=100MB
LOG_MAX_BACKUPS=5
LOG_MAX_AGE=30                # 天数
```

### 监控和诊断

```bash
# 启用性能分析
ENABLE_PROFILING=true
PROFILING_PORT=6060

# 启用调试端点
DEBUG_ENDPOINTS=true
DEBUG_PORT=8082

# 健康检查配置
HEALTH_CHECK_INTERVAL=30s
HEALTH_CHECK_TIMEOUT=10s
HEALTH_CHECK_RETRIES=3
```

## 配置验证

使用以下脚本验证配置：

```bash
#!/bin/bash
# 配置验证脚本

echo "验证环境变量配置..."

# 检查必需的环境变量
required_vars=(
    "BINANCE_API_KEY"
    "BINANCE_API_SECRET"
    "CLICKHOUSE_PASSWORD"
    "REDIS_PASSWORD"
)

for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ 缺少必需的环境变量: $var"
        exit 1
    else
        echo "✅ $var 已配置"
    fi
done

echo "✅ 配置验证完成"
```

## 最佳实践

1. **安全性**:
   - 使用强密码和复杂的API密钥
   - 定期轮换密钥和密码
   - 启用TLS加密
   - 限制网络访问

2. **性能**:
   - 根据负载调整并发配置
   - 监控内存和CPU使用情况
   - 优化数据库查询
   - 使用连接池

3. **可靠性**:
   - 配置适当的重试机制
   - 设置合理的超时时间
   - 启用健康检查
   - 实施故障转移

4. **监控**:
   - 配置全面的监控指标
   - 设置合理的告警阈值
   - 定期检查日志
   - 监控业务指标

---

*最后更新: 2025-07-03*
