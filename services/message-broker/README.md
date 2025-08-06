# 📡 MarketPrism Message Broker

[![NATS](https://img.shields.io/badge/nats-2.10+-blue.svg)](https://nats.io/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](unified-nats/docker-compose.unified.yml)
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

## 🚀 快速开始

### 前置要求

- Docker 20.10+
- Docker Compose 2.0+

### 启动服务

```bash
# 1. 进入NATS服务目录
cd services/message-broker/unified-nats

# 2. 启动NATS JetStream
docker-compose -f docker-compose.unified.yml up -d

# 3. 验证服务状态
curl http://localhost:8222/healthz

# 4. 检查JetStream状态
curl http://localhost:8222/jsz
```

## 📈 支持的消息主题和流

### 主题结构

| 数据类型 | 主题格式 | 示例 |
|---------|---------|------|
| **Orderbooks** | `orderbook-data.{exchange}.{market}.{symbol}` | `orderbook-data.binance.derivatives.BTCUSDT` |
| **Trades** | `trade-data.{exchange}.{market}.{symbol}` | `trade-data.okx.spot.BTCUSDT` |
| **Funding Rates** | `funding-rate-data.{exchange}.{market}.{symbol}` | `funding-rate-data.binance.derivatives.BTCUSDT` |
| **Open Interests** | `open-interest-data.{exchange}.{market}.{symbol}` | `open-interest-data.okx.derivatives.BTCUSDT` |
| **Liquidations** | `liquidation-data.{exchange}.{market}.{symbol}` | `liquidation-data.okx.derivatives.BTCUSDT` |
| **LSR Top Positions** | `lsr-data.{exchange}.{market}.top-position.{symbol}` | `lsr-data.binance.derivatives.top-position.BTCUSDT` |
| **LSR All Accounts** | `lsr-data.{exchange}.{market}.all-account.{symbol}` | `lsr-data.okx.derivatives.all-account.BTCUSDT` |
| **Volatility Indices** | `volatility-index-data.{exchange}.{market}.{symbol}` | `volatility-index-data.deribit.options.BTCUSDT` |

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](../../LICENSE) 文件了解详情
