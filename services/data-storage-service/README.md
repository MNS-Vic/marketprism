# 🗄️ MarketPrism Data Storage Service

[![Python](https://img.shields.io/badge/python-3.12+-green.svg)](requirements.txt)
[![ClickHouse](https://img.shields.io/badge/clickhouse-23.8+-blue.svg)](#clickhouse-integration)
[![Status](https://img.shields.io/badge/status-production_ready-brightgreen.svg)](#)

**企业级数据存储服务** - 高性能批处理引擎，支持8种数据类型的智能存储和管理

## 📊 概览

MarketPrism Data Storage Service是一个高性能的数据存储和处理服务，负责从NATS消息队列接收数据，进行智能批处理，并高效存储到ClickHouse数据库中。

### 🎯 核心功能

- **📡 NATS消息消费**: 高效订阅和处理多种数据类型
- **🔧 智能批处理**: 差异化批处理策略，优化不同频率数据
- **🗄️ ClickHouse集成**: 高性能列式数据库存储
- **🔄 时间戳标准化**: 统一时间戳格式处理
- **📈 性能监控**: 实时性能统计和健康检查
- **🛡️ 错误处理**: 完善的异常处理和恢复机制
- **📊 数据质量**: 数据验证和完整性检查

## 🚀 快速开始

### 前置要求

- Python 3.12+
- ClickHouse 23.8+
- NATS Server 2.9+

### 启动服务

```bash
# 1. 确保依赖服务已启动
# NATS服务
cd ../message-broker/unified-nats
docker-compose -f docker-compose.unified.yml up -d

# ClickHouse服务
docker-compose -f docker-compose.hot-storage.yml up clickhouse-hot -d

# 2. 启动存储服务
cd services/data-storage-service
nohup python3 production_cached_storage.py > production.log 2>&1 &

# 3. 验证启动状态
tail -f production.log
```

## 📈 支持的数据类型和批处理配置

| 数据类型 | 批次大小 | 超时时间 | 最大队列 | 频率特性 |
|---------|---------|---------|---------|---------|
| **Orderbooks** | 100条 | 10.0秒 | 1000条 | 高频 |
| **Trades** | 100条 | 10.0秒 | 1000条 | 超高频 |
| **Funding Rates** | 10条 | 2.0秒 | 500条 | 中频 |
| **Open Interests** | 50条 | 10.0秒 | 500条 | 低频 |
| **Liquidations** | 5条 | 10.0秒 | 200条 | 事件驱动 |
| **LSR Top Positions** | 1条 | 1.0秒 | 50条 | 低频 |
| **LSR All Accounts** | 1条 | 1.0秒 | 50条 | 低频 |
| **Volatility Indices** | 1条 | 1.0秒 | 50条 | 低频 |

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](../../LICENSE) 文件了解详情
