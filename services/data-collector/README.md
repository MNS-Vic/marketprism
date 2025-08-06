# 🚀 MarketPrism Data Collector

[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](docker-compose.unified.yml)
[![Python](https://img.shields.io/badge/python-3.12+-green.svg)](requirements.txt)
[![Status](https://img.shields.io/badge/status-production_ready-brightgreen.svg)](#)

**企业级数据收集器** - 支持多交易所实时数据收集，8种数据类型100%覆盖

## 📊 概览

MarketPrism Data Collector是一个高性能的加密货币市场数据收集服务，支持多交易所WebSocket连接，实现实时数据收集、标准化和发布。

### 🎯 核心功能

- **🔄 多交易所支持**: Binance、OKX、Deribit等主流交易所
- **📊 8种数据类型**: 订单簿、交易、资金费率、未平仓量、强平、LSR、波动率指数
- **⚡ 实时WebSocket**: 毫秒级数据收集，自动重连机制
- **🔧 数据标准化**: 统一数据格式，时间戳格式转换
- **📡 NATS发布**: 高性能消息发布，支持主题路由
- **🛡️ 生产级稳定性**: 断路器、重试机制、内存管理
- **📈 监控指标**: Prometheus指标，健康检查端点

## 🏗️ 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    Data Collector 架构                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │   Exchange  │    │ Data        │    │    NATS     │     │
│  │  WebSocket  │───▶│ Normalizer  │───▶│  Publisher  │     │
│  │  Adapters   │    │             │    │             │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │   Health    │    │   Memory    │    │   Circuit   │     │
│  │   Monitor   │    │   Manager   │    │   Breaker   │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 📈 支持的数据类型

| 数据类型 | 交易所支持 | 频率 | NATS主题格式 |
|---------|-----------|------|-------------|
| **Orderbooks** | Binance, OKX | 高频 | `orderbook-data.{exchange}.{market}.{symbol}` |
| **Trades** | Binance, OKX | 超高频 | `trade-data.{exchange}.{market}.{symbol}` |
| **Funding Rates** | Binance, OKX | 中频 | `funding-rate-data.{exchange}.{market}.{symbol}` |
| **Open Interests** | Binance, OKX | 低频 | `open-interest-data.{exchange}.{market}.{symbol}` |
| **Liquidations** | OKX | 事件驱动 | `liquidation-data.{exchange}.{market}.{symbol}` |
| **LSR Top Positions** | Binance, OKX | 低频 | `lsr-data.{exchange}.{market}.top-position.{symbol}` |
| **LSR All Accounts** | Binance, OKX | 低频 | `lsr-data.{exchange}.{market}.all-account.{symbol}` |
| **Volatility Indices** | Deribit | 低频 | `volatility-index-data.{exchange}.{market}.{symbol}` |

## 🚀 快速开始

### 前置要求

- Docker 20.10+
- Docker Compose 2.0+
- Python 3.12+ (本地开发)

### Docker部署 (推荐)

```bash
# 1. 确保NATS服务已启动
cd ../message-broker/unified-nats
docker-compose -f docker-compose.unified.yml up -d

# 2. 启动Data Collector
cd ../data-collector
sudo docker-compose -f docker-compose.unified.yml up -d

# 3. 验证启动状态
sudo docker logs marketprism-data-collector -f
```

### 本地开发

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动服务 (launcher模式)
python unified_collector_main.py launcher

# 3. 查看日志
tail -f logs/collector.log
```

## ⚙️ 配置说明

### 配置文件结构

```
config/
├── collector/                    # 数据收集器配置
│   ├── unified_data_collection.yaml
│   └── exchange_configs/
├── logging/                      # 日志配置
│   └── logging_config.yaml
└── nats/                        # NATS连接配置
    ├── nats-server.conf
    └── nats-server-docker.conf
```

### 环境变量

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

# 健康检查
HEALTH_CHECK_PORT=8086
METRICS_PORT=9093
```

### Docker配置

```yaml
# docker-compose.unified.yml 关键配置
services:
  data-collector:
    image: marketprism/data-collector:simplified
    container_name: marketprism-data-collector
    environment:
      - NATS_URL=nats://localhost:4222
      - LOG_LEVEL=INFO
      - COLLECTOR_MODE=launcher
    ports:
      - "8086:8086"  # 健康检查
      - "9093:9093"  # Prometheus指标
    network_mode: host
    restart: unless-stopped
```

## 📊 监控和健康检查

### 健康检查端点

```bash
# 基础健康检查
curl http://localhost:8086/health

# 详细状态信息
curl http://localhost:8086/status

# 连接状态检查
curl http://localhost:8086/connections
```

### Prometheus指标

```bash
# 获取所有指标
curl http://localhost:9093/metrics

# 关键指标说明
# - marketprism_messages_published_total: 发布消息总数
# - marketprism_websocket_connections: WebSocket连接数
# - marketprism_data_processing_duration: 数据处理延迟
# - marketprism_memory_usage_bytes: 内存使用量
```

### 日志监控

```bash
# Docker容器日志
sudo docker logs marketprism-data-collector -f

# 本地开发日志
tail -f logs/collector.log

# 错误日志过滤
sudo docker logs marketprism-data-collector 2>&1 | grep ERROR
```

## 🔧 故障排查

### 常见问题

#### 1. 容器启动失败
```bash
# 检查端口占用
netstat -tlnp | grep -E "(8086|9093)"

# 检查Docker网络
sudo docker network ls
sudo docker network inspect bridge
```

#### 2. WebSocket连接失败
```bash
# 检查网络连接
curl -I https://stream.binance.com:9443/ws/btcusdt@depth
curl -I https://ws.okx.com:8443/ws/v5/public

# 检查DNS解析
nslookup stream.binance.com
nslookup ws.okx.com
```

#### 3. NATS连接问题
```bash
# 检查NATS服务状态
curl http://localhost:8222/healthz

# 测试NATS连接
nats pub test.subject "hello world"
nats sub test.subject
```

#### 4. 数据收集停止
```bash
# 检查内存使用
sudo docker stats marketprism-data-collector

# 检查错误日志
sudo docker logs marketprism-data-collector --since 10m | grep ERROR

# 重启服务
sudo docker restart marketprism-data-collector
```

## 🔄 运维操作

### 启动和停止

```bash
# 启动服务
sudo docker-compose -f docker-compose.unified.yml up -d

# 停止服务
sudo docker-compose -f docker-compose.unified.yml down

# 重启服务
sudo docker-compose -f docker-compose.unified.yml restart

# 查看状态
sudo docker-compose -f docker-compose.unified.yml ps
```

### 日志管理

```bash
# 查看实时日志
sudo docker logs marketprism-data-collector -f

# 查看最近日志
sudo docker logs marketprism-data-collector --since 1h

# 导出日志
sudo docker logs marketprism-data-collector > collector_logs.txt
```

### 性能调优

```bash
# 检查资源使用
sudo docker stats marketprism-data-collector --no-stream

# 调整内存限制 (在docker-compose.yml中)
deploy:
  resources:
    limits:
      memory: 2G
    reservations:
      memory: 512M
```

## 📚 开发指南

### 代码结构

```
services/data-collector/
├── unified_collector_main.py      # 主入口文件
├── collector/                     # 核心收集器模块
│   ├── normalizer.py             # 数据标准化
│   ├── nats_publisher.py         # NATS发布器
│   └── websocket_adapter.py      # WebSocket适配器
├── exchanges/                     # 交易所适配器
│   ├── binance_websocket.py      # Binance适配器
│   └── okx_websocket.py          # OKX适配器
└── config/                       # 配置文件
```

### 添加新交易所

1. 创建交易所适配器 `exchanges/new_exchange_websocket.py`
2. 实现WebSocket连接和数据解析
3. 在配置文件中添加交易所配置
4. 更新主入口文件的交易所列表

### 添加新数据类型

1. 在 `collector/data_types.py` 中定义数据结构
2. 在相应的交易所适配器中添加数据解析
3. 在 `collector/normalizer.py` 中添加标准化逻辑
4. 更新NATS主题配置

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](../../LICENSE) 文件了解详情