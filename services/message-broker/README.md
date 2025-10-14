# 📡 MarketPrism Message Broker
> 重要：以 scripts/manage_all.sh 为唯一运行总线索。唯一入口：`services/message-broker/main.py`（推荐使用 `-c services/message-broker/config/unified_message_broker.yaml` 指定配置）。唯一配置：`services/message-broker/config/unified_message_broker.yaml`。遇到端口冲突请先清理占用进程/容器，不要更改端口。


[![NATS](https://img.shields.io/badge/nats-2.10+-blue.svg)](https://nats.io/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](docker-compose.nats.yml)
[![Status](https://img.shields.io/badge/status-production_ready-brightgreen.svg)](#)

**企业级消息队列服务** - 基于NATS JetStream的高性能消息传递和流处理平台

## 📊 概览

MarketPrism Message Broker是一个基于NATS JetStream的高性能消息队列服务，提供可靠的消息传递、持久化存储和流处理能力，是Data Collector和Storage Service之间的核心通信桥梁。

### 🎯 核心功能

- **📡 NATS JetStream**: 高性能消息流处理和持久化
- **🔄 消息路由**: 智能主题路由和消息分发
- **💾 持久化存储**: 消息持久化和重放能力
- **🛡️ 高可用性**: 集群支持和故障转移
- **📈 监控指标**: 完整的性能监控和健康检查
- **🔧 流管理**: 动态流创建和管理
- **⚡ 低延迟**: 微秒级消息传递延迟

## ❗ 重要说明（职责边界）

- 本模块仅作为 NATS 客户端进行流管理与消息路由，不再托管或内嵌本地 nats-server 进程
- NATS 服务器必须通过 Docker（或外部托管集群）提供。项目内仅保留 docker-compose.nats.yml 作为标准运行方式
- 配置项统一：使用 config/unified_message_broker.yaml 的 nats_client.nats_url 指向外部 NATS（默认 nats://localhost:4222）


## 🚀 快速开始

### 前置要求

- Docker 20.10+
- Docker Compose 2.0+

### 启动服务（统一标准入口）

```bash
# 1. 进入NATS服务目录
cd services/message-broker

# 2. 启动NATS（JetStream开启，端口4222/8222）
docker compose -f docker-compose.nats.yml up -d

### 配置规范

- 配置文件：`services/message-broker/config/unified_message_broker.yaml`
- 关键项：`nats_client.nats_url` 指向外部 NATS
- 推荐环境变量（可选）：`MARKETPRISM_NATS_URL` 用于容器化覆盖，但当前以 YAML 配置为准

示例 YAML 片段:

```yaml
nats_client:
  nats_url: "nats://localhost:4222"
  client_name: "unified-message-broker"
  strict_subjects: true
streams:
  MARKET_DATA:
    subjects: ["orderbook.>", "trade.>", "funding_rate.>"]
```


# 3. 验证服务状态
curl http://localhost:8222/healthz

### 环境变量覆盖说明

- 若设置 `MARKETPRISM_NATS_URL`，将覆盖 YAML 中的 `nats_client.nats_url`
- 示例：

```bash
export MARKETPRISM_NATS_URL="nats://localhost:4222"
python3 services/message-broker/main.py -c services/message-broker/config/unified_message_broker.yaml
```


# 4. 检查JetStream状态
curl http://localhost:8222/jsz
```

## 📈 支持的消息主题和流

### 主题结构

| 数据类型 | 主题格式 | 示例 |
|---------|---------|------|
| **Orderbooks** | `orderbook.{exchange}.{market}.{symbol}` | `orderbook.binance_derivatives.perpetual.BTC-USDT` |
| **Trades** | `trade.{exchange}.{market}.{symbol}` | `trade.okx_spot.spot.BTC-USDT` |
| **Funding Rates** | `funding_rate.{exchange}.{market}.{symbol}` | `funding_rate.binance_derivatives.perpetual.BTC-USDT` |
| **Open Interests** | `open_interest.{exchange}.{market}.{symbol}` | `open_interest.okx_derivatives.perpetual.BTC-USDT` |
| **Liquidations** | `liquidation.{exchange}.{market}.{symbol}` | `liquidation.okx_derivatives.perpetual.BTC-USDT` |
| **LSR Top Positions** | `lsr_top_position.{exchange}.{market}.{symbol}` | `lsr_top_position.binance_derivatives.perpetual.BTC-USDT` |
| **LSR All Accounts** | `lsr_all_account.{exchange}.{market}.{symbol}` | `lsr_all_account.okx_derivatives.perpetual.BTC-USDT` |
| **Volatility Indices** | `volatility_index.{exchange}.{market}.{symbol}` | `volatility_index.deribit_derivatives.options.BTC` |

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](../../LICENSE) 文件了解详情
