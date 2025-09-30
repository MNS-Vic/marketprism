# MarketPrism 模块化部署指南

## 📋 概述

MarketPrism 的三个核心模块现在都有独立的管理脚本，可以在不同的物理主机或容器中独立部署和运行。

### 核心模块

1. **Message Broker** - NATS JetStream 消息代理
2. **Data Storage Service** - ClickHouse 数据存储服务
3. **Data Collector** - 数据采集器

---

## 🎯 部署架构

### 单机部署（开发/测试）

```
┌─────────────────────────────────────────┐
│         单台主机                         │
│                                         │
│  ┌──────────────────────────────────┐  │
│  │  Message Broker (端口 4222)      │  │
│  └──────────────────────────────────┘  │
│                                         │
│  ┌──────────────────────────────────┐  │
│  │  Data Storage (端口 8085)        │  │
│  └──────────────────────────────────┘  │
│                                         │
│  ┌──────────────────────────────────┐  │
│  │  Data Collector (端口 8087)      │  │
│  └──────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

### 分布式部署（生产环境）

```
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│  主机 1          │      │  主机 2          │      │  主机 3          │
│                  │      │                  │      │                  │
│  Message Broker  │◄────►│  Data Storage    │◄────►│  Data Collector  │
│  (NATS)          │      │  (ClickHouse)    │      │  (采集器)        │
│                  │      │                  │      │                  │
│  端口: 4222      │      │  端口: 8085      │      │  端口: 8087      │
│        8222      │      │        8123      │      │        9093      │
└──────────────────┘      └──────────────────┘      └──────────────────┘
```

---

## 📦 模块 1: Message Broker

### 位置
```
/path/to/marketprism/services/message-broker/
```

### 管理脚本
```bash
cd services/message-broker
./scripts/manage.sh [命令]
```

### 快速部署

```bash
# 1. 安装依赖
./scripts/manage.sh install-deps

# 2. 初始化服务
./scripts/manage.sh init

# 3. 启动服务
./scripts/manage.sh start

# 4. 检查状态
./scripts/manage.sh status
./scripts/manage.sh health
```

### 端口配置

| 端口 | 用途 | 说明 |
|------|------|------|
| 4222 | NATS 客户端 | 客户端连接端口 |
| 8222 | NATS 监控 | HTTP 监控端点 |

### 配置文件

- **主配置**: `config/unified_message_broker.yaml`
- **JetStream 初始化**: `../../scripts/js_init_market_data.yaml`

### 依赖

- NATS Server v2.10.7
- Python 3.9+
- Python 包: nats-py, PyYAML

### 数据存储

- JetStream 数据目录: `/tmp/nats-jetstream`（可配置）

### 健康检查

```bash
# HTTP 健康检查
curl http://localhost:8222/healthz

# JetStream 状态
curl http://localhost:8222/jsz
```

---

## 📦 模块 2: Data Storage Service

### 位置
```
/path/to/marketprism/services/data-storage-service/
```

### 管理脚本
```bash
cd services/data-storage-service
./scripts/manage.sh [命令]
```

### 快速部署

```bash
# 1. 安装依赖（包括 ClickHouse）
./scripts/manage.sh install-deps

# 2. 初始化服务（创建数据库表）
./scripts/manage.sh init

# 3. 启动服务
./scripts/manage.sh start

# 4. 检查状态
./scripts/manage.sh status
./scripts/manage.sh health
```

### 端口配置

| 端口 | 用途 | 说明 |
|------|------|------|
| 8123 | ClickHouse HTTP | HTTP 查询端口 |
| 9000 | ClickHouse Native | Native 协议端口 |
| 8085 | 热端存储服务 | 热端数据存储 API |
| 8086 | 冷端存储服务 | 冷端数据存储 API（可选） |

### 配置文件

- **数据库 Schema**: `config/clickhouse_schema.sql`
- **热端配置**: `config/hot_storage_config.yaml`
- **冷端配置**: `config/tiered_storage_config.yaml`

### 依赖

- ClickHouse v25.10.1+
- Python 3.9+
- Python 包: nats-py, aiohttp, clickhouse-driver, structlog

### 数据库

- 热端数据库: `marketprism_hot`
- 冷端数据库: `marketprism_cold`
- 8 个数据表（对应 8 种数据类型）

### 健康检查

```bash
# ClickHouse 健康检查
curl "http://localhost:8123/" --data "SELECT 1"

# 存储服务健康检查
curl http://localhost:8085/health

# 查询数据
clickhouse-client --query "SELECT count(*) FROM marketprism_hot.trades"
```

---

## 📦 模块 3: Data Collector

### 位置
```
/path/to/marketprism/services/data-collector/
```

### 管理脚本
```bash
cd services/data-collector
./scripts/manage.sh [命令]
```

### 快速部署

```bash
# 1. 安装依赖
./scripts/manage.sh install-deps

# 2. 初始化服务
./scripts/manage.sh init

# 3. 启动服务
./scripts/manage.sh start

# 4. 检查状态
./scripts/manage.sh status
./scripts/manage.sh health
```

### 端口配置

| 端口 | 用途 | 说明 |
|------|------|------|
| 8087 | 健康检查 | HTTP 健康检查端点 |
| 9093 | Prometheus 指标 | 指标导出端口 |

### 配置文件

- **主配置**: `config/collector/unified_data_collection.yaml`

### 依赖

- Python 3.9+
- Python 包: nats-py, websockets, ccxt, aiohttp, pydantic

### 环境变量

```bash
export HEALTH_CHECK_PORT=8087
export METRICS_PORT=9093
```

### 健康检查

```bash
# 健康检查（如果实现）
curl http://localhost:8087/health

# Prometheus 指标
curl http://localhost:9093/metrics

# 查看日志
./scripts/manage.sh logs
```

---

## 🚀 完整部署流程

### 场景 1: 单机部署

```bash
# 在同一台主机上部署所有模块

# 1. Message Broker
cd services/message-broker
./scripts/manage.sh install-deps && ./scripts/manage.sh init && ./scripts/manage.sh start

# 2. Data Storage Service
cd ../data-storage-service
./scripts/manage.sh install-deps && ./scripts/manage.sh init && ./scripts/manage.sh start

# 3. Data Collector
cd ../data-collector
./scripts/manage.sh install-deps && ./scripts/manage.sh init && ./scripts/manage.sh start

# 4. 验证
cd ../../
./scripts/manage_all.sh health
```

### 场景 2: 分布式部署

#### 主机 1: Message Broker

```bash
# SSH 到主机 1
ssh user@host1

# 克隆项目
git clone https://github.com/MNS-Vic/marketprism.git
cd marketprism/services/message-broker

# 部署
./scripts/manage.sh install-deps
./scripts/manage.sh init
./scripts/manage.sh start

# 验证
./scripts/manage.sh health
```

#### 主机 2: Data Storage Service

```bash
# SSH 到主机 2
ssh user@host2

# 克隆项目
git clone https://github.com/MNS-Vic/marketprism.git
cd marketprism/services/data-storage-service

# 修改配置（指向主机 1 的 NATS）
vim config/hot_storage_config.yaml
# 修改 nats_url: nats://host1:4222

# 部署
./scripts/manage.sh install-deps
./scripts/manage.sh init
./scripts/manage.sh start

# 验证
./scripts/manage.sh health
```

#### 主机 3: Data Collector

```bash
# SSH 到主机 3
ssh user@host3

# 克隆项目
git clone https://github.com/MNS-Vic/marketprism.git
cd marketprism/services/data-collector

# 修改配置（指向主机 1 的 NATS）
vim config/collector/unified_data_collection.yaml
# 修改 nats_url: nats://host1:4222

# 部署
./scripts/manage.sh install-deps
./scripts/manage.sh init
./scripts/manage.sh start

# 验证
./scripts/manage.sh health
```

---

## 🔧 管理命令参考

所有模块的管理脚本都支持以下命令：

| 命令 | 功能 | 说明 |
|------|------|------|
| `install-deps` | 安装依赖 | 安装系统依赖和 Python 依赖 |
| `init` | 初始化服务 | 创建虚拟环境、初始化数据库等 |
| `start` | 启动服务 | 启动模块服务 |
| `stop` | 停止服务 | 停止模块服务 |
| `restart` | 重启服务 | 重启模块服务 |
| `status` | 检查状态 | 检查进程和端口状态 |
| `health` | 健康检查 | 执行健康检查 |
| `logs` | 查看日志 | 实时查看日志 |
| `clean` | 清理 | 清理临时文件和锁文件 |
| `help` | 帮助 | 显示帮助信息 |

---

## 📊 监控和维护

### 日志位置

```
services/message-broker/logs/nats-server.log
services/data-storage-service/logs/storage-hot.log
services/data-collector/logs/collector.log
```

### PID 文件位置

```
services/message-broker/logs/nats-server.pid
services/data-storage-service/logs/storage-hot.pid
services/data-collector/logs/collector.pid
```

### 定期维护

```bash
# 每日健康检查
for module in message-broker data-storage-service data-collector; do
    cd services/$module
    ./scripts/manage.sh health
    cd ../..
done

# 每周重启（可选）
for module in message-broker data-storage-service data-collector; do
    cd services/$module
    ./scripts/manage.sh restart
    cd ../..
done
```

---

## 🐛 故障排查

### 问题 1: 模块无法启动

```bash
# 检查日志
./scripts/manage.sh logs

# 检查端口占用
ss -ltnp | grep -E "(4222|8085|8087)"

# 检查依赖
source venv/bin/activate
python -c "import nats, aiohttp, clickhouse_driver"
```

### 问题 2: 模块间无法通信

```bash
# 检查网络连接
ping host1
telnet host1 4222

# 检查防火墙
sudo iptables -L

# 检查配置文件中的地址
grep -r "nats_url" config/
```

### 问题 3: 数据未流动

```bash
# 检查 NATS 消息
curl http://localhost:8222/jsz

# 检查 ClickHouse 数据
clickhouse-client --query "SELECT count(*) FROM marketprism_hot.trades"

# 检查采集器日志
tail -f services/data-collector/logs/collector.log | grep "发布成功"
```

---

## 🎉 总结

通过独立的管理脚本，MarketPrism 的每个核心模块都可以：

✅ **独立部署** - 在不同主机上独立安装和运行  
✅ **独立管理** - 使用统一的命令接口管理  
✅ **独立扩展** - 根据需要独立扩展每个模块  
✅ **独立维护** - 独立更新和维护每个模块  

这为生产环境的灵活部署提供了强大的支持！🚀

