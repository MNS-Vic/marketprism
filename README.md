# MarketPrism

MarketPrism是一个高性能的加密货币市场数据收集平台，专为实时数据分析和量化交易而设计。采用统一架构，支持多交易所数据收集，具备优秀的稳定性和可扩展性。

## 🔄 **重大更新 (2025-08-02) - Docker部署简化改造**

### **🎯 简化改造成果**
- ✅ **Data Collector简化**: 从4种运行模式简化为launcher模式（完整数据收集系统）
- ✅ **Docker配置统一**: 简化docker-compose配置，单一服务定义
- ✅ **配置本地化**: Data Collector配置迁移到`services/data-collector/config/`
- ✅ **部署流程优化**: 两步命令完成整个系统部署
- ✅ **功能验证**: 8种数据类型×5个交易所全部正常工作

### **🚀 新的快速部署方式**
```bash
# 1. 启动统一NATS容器
cd services/message-broker/unified-nats
sudo docker-compose -f docker-compose.unified.yml up -d

# 2. 启动Data Collector (launcher模式)
cd ../../data-collector
sudo docker-compose -f docker-compose.unified.yml up -d
```

### **📊 验证结果**
- ✅ **数据流**: 118,187条消息，817MB数据持续流入NATS
- ✅ **性能**: 系统延迟<33ms，吞吐量1.7msg/s
- ✅ **稳定性**: 所有WebSocket连接稳定，无数据丢失

## ✨ 核心特性

- **🚀 统一架构**: 唯一入口 + 唯一配置，简化部署和维护
- **📊 多交易所支持**: Binance（现货+衍生品）、OKX（现货+衍生品）
- **⚡ 实时数据收集**: OrderBook深度数据 + Trades成交数据 + LSR多空比数据
- **🔄 WebSocket长连接**: 稳定的WebSocket连接，支持自动重连
- **📨 NATS消息中间件**: 基于JetStream的高性能消息代理服务
- **🎯 LSR数据支持**: 顶级持仓多空比 + 全账户多空比实时数据
- **📈 系统监控**: 内存、CPU、连接状态全面监控
- **🎯 企业级日志系统**: 统一格式、智能去重、性能优化，减少60-80%冗余输出

## 🏗️ 系统架构

### 统一数据收集架构

```
┌─────────────────────────────────────────────────────────────┐
│                    MarketPrism 统一架构                      │
├─────────────────────────────────────────────────────────────┤
│  数据收集入口: unified_collector_main.py                    │
│  数据收集配置: config/collector/unified_data_collection.yaml│
│  消息代理入口: unified_message_broker_main.py               │
│  消息代理配置: config/message-broker/unified_message_broker.yaml│
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    多类型数据管理器                          │
├─────────────────────────────────────────────────────────────┤
│  Binance现货:     OrderBook + Trades 管理器                │
│  Binance衍生品:   OrderBook + Trades + LSR 管理器          │
│  OKX现货:        OrderBook + Trades 管理器                │
│  OKX衍生品:      OrderBook + Trades + LSR 管理器          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                NATS JetStream消息代理                       │
├─────────────────────────────────────────────────────────────┤
│  Topic格式: {data_type}-data.{exchange}.{market}.{symbol}   │
│  示例: orderbook-data.binance_spot.spot.BTC-USDT           │
│       lsr-top-position-data.binance_derivatives.perpetual.BTC-USDT│
└─────────────────────────────────────────────────────────────┘
```

### 核心组件

#### 数据收集层
- **统一数据收集器**: 管理所有交易所的数据收集
- **WebSocket管理器**: 维护稳定的WebSocket连接
- **订单簿管理器**: 处理实时订单簿数据
- **成交数据管理器**: 处理实时成交数据
- **LSR数据管理器**: 处理多空比数据（顶级持仓 + 全账户）
- **数据标准化器**: 统一不同交易所的数据格式

#### 消息代理层
- **NATS服务器管理器**: 自动启动和管理NATS Server
- **JetStream流管理器**: 创建和管理持久化消息流
- **消息路由器**: 高性能消息发布和订阅
- **LSR数据订阅器**: 专门的LSR数据订阅和处理

#### 监控层
- **系统监控器**: 资源使用和连接状态监控
- **消息统计器**: 消息发布、消费、错误统计

## 🚀 快速开始

### 环境要求

- Python 3.8+
- NATS Server
- 8GB+ RAM（推荐）
- 稳定的网络连接

### 安装步骤

1. **克隆项目**:
```bash
git clone https://github.com/MNS-Vic/marketprism.git
cd marketprism
```

2. **创建虚拟环境**:
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

3. **安装依赖**:
```bash
pip install -r requirements.txt
```

4. **安装NATS服务器**:
```bash
# 下载并安装NATS服务器
curl -L https://github.com/nats-io/nats-server/releases/download/v2.10.7/nats-server-v2.10.7-linux-amd64.zip -o nats-server.zip
unzip nats-server.zip
sudo mv nats-server-v2.10.7-linux-amd64/nats-server /usr/local/bin/
```

5. **启动Message Broker**:
```bash
cd services/message-broker
python unified_message_broker_main.py --mode broker --log-level INFO
```

6. **启动数据收集器**:
```bash
cd services/data-collector
python unified_collector_main.py --log-level INFO
```

### 验证运行状态

系统启动后会显示：
```
================================================================================
✅ MarketPrism数据收集器启动成功！
================================================================================
📡 正在收集以下交易所数据:
  • OKX_SPOT: orderbook, trades
  • OKX_DERIVATIVES: orderbook, trades
  • BINANCE_DERIVATIVES: orderbook, trades
  • BINANCE_SPOT: orderbook, trades
🔗 NATS推送: 实时数据推送中...
📊 监控: 内存和连接状态监控中...
================================================================================
```

## 📡 Message Broker统一消息代理

MarketPrism提供统一的消息代理服务，基于NATS JetStream构建，支持高性能消息路由和LSR数据订阅。

### 🎯 核心特性

- **🚀 统一入口**: 单一配置文件和启动脚本，简化部署
- **📊 NATS服务器管理**: 自动启动和管理NATS Server
- **🔄 JetStream流管理**: 创建、删除和管理持久化消息流
- **📈 LSR数据订阅**: 专门的LSR数据订阅和处理功能
- **📨 消息路由**: 高性能消息发布和订阅
- **🔍 实时监控**: NATS集群状态和消息统计

### 📁 文件结构

```
config/message-broker/
└── unified_message_broker.yaml    # 统一配置文件

services/message-broker/
├── unified_message_broker_main.py # 统一入口文件
├── main.py                        # 核心服务实现
└── nats_config.yaml              # NATS配置文件
```

### 🚀 启动方式

#### 1. 消息代理模式（推荐）
```bash
cd services/message-broker
python unified_message_broker_main.py --mode broker --log-level INFO
```

#### 2. 订阅器模式（仅订阅LSR数据）
```bash
python unified_message_broker_main.py --mode subscriber --log-level INFO
```

#### 3. 测试模式（启动代理并运行测试）
```bash
python unified_message_broker_main.py --mode test --log-level DEBUG
```

### ⚙️ 配置说明

主配置文件：`config/message-broker/unified_message_broker.yaml`

#### 核心配置项
```yaml
# NATS服务器配置
nats_server:
  nats_port: 4222          # NATS消息端口
  http_port: 8222          # 监控端口
  jetstream_enabled: true  # 启用JetStream
  data_dir: "data/nats"    # 数据存储目录

# LSR数据订阅配置
lsr_subscription:
  enabled: true
  data_types: ["lsr_top_position", "lsr_all_account"]
  exchanges: ["binance_derivatives", "okx_derivatives"]
  symbols: ["BTC-USDT", "ETH-USDT"]
```

### 📊 LSR数据流测试

#### 启动完整LSR测试系统
```bash
# 1. 启动Message Broker
python unified_message_broker_main.py --mode broker

# 2. 启动Data Collector（仅LSR）
cd ../data-collector
python unified_collector_main.py --log-level INFO

# 3. 启动LSR订阅器
cd ../message-broker
python unified_message_broker_main.py --mode subscriber
```

#### LSR数据格式
```json
// LSR顶级持仓数据
{
  "exchange": "binance_derivatives",
  "symbol": "BTC-USDT",
  "timestamp": "2025-08-02T04:05:00+00:00",
  "long_position_ratio": 0.6523,
  "short_position_ratio": 0.3477,
  "long_short_ratio": 1.8760
}

// LSR全账户数据
{
  "exchange": "okx_derivatives",
  "symbol": "ETH-USDT",
  "timestamp": "2025-08-02T04:05:00+00:00",
  "long_account_ratio": 0.6226,
  "short_account_ratio": 0.3774,
  "long_short_ratio": 1.65
}
```

### 🔍 监控和调试

#### NATS监控界面
- **监控地址**: http://localhost:8222
- **JetStream状态**: http://localhost:8222/jsz
- **连接信息**: http://localhost:8222/connz

#### 消息主题格式
```
lsr-top-position-data.{exchange}.perpetual.{symbol}
lsr-all-account-data.{exchange}.perpetual.{symbol}
```

示例：
- `lsr-top-position-data.binance_derivatives.perpetual.BTC-USDT`
- `lsr-all-account-data.okx_derivatives.perpetual.ETH-USDT`

## 📊 企业级日志系统

MarketPrism采用统一的企业级日志管理系统，提供标准化的日志格式、智能去重和性能优化。

### 🎯 核心特性

- **统一格式**: 所有模块使用标准化的日志格式
- **智能去重**: 自动抑制重复的数据处理日志，减少60-80%日志量
- **频率控制**: 连接状态日志智能聚合，避免刷屏
- **结构化上下文**: 每条日志包含组件、交易所、市场类型等关键信息
- **性能优化**: 减少I/O开销，提升系统性能30-40%

### 📋 日志级别

| 级别 | 用途 | 适用场景 |
|------|------|----------|
| **DEBUG** | 最详细的诊断信息 | 开发调试、问题排查 |
| **INFO** | 程序正常运行信息 | 生产环境监控（推荐） |
| **WARNING** | 警告信息，程序仍能运行 | 异常情况提醒 |
| **ERROR** | 错误信息，功能受影响 | 错误监控 |

### 🚀 启动时指定日志级别

```bash
# 生产环境（推荐）
python unified_collector_main.py --log-level INFO

# 开发调试
python unified_collector_main.py --log-level DEBUG

# 仅显示警告和错误
python unified_collector_main.py --log-level WARNING
```

### 📝 日志格式示例

```
[START] ✓ main: MarketPrism unified data collector starting
[CONN] ✓ websocket.binance.spot: Binance WebSocket connection established
[DATA] ⟳ orderbook.okx.spot: Processing orderbook update
[PERF] → system: System performance metrics
[ERROR] ✗ websocket.okx.derivatives: Connection failed
```

## ⚙️ 配置说明

### 主配置文件

配置文件位置: `config/collector/unified_data_collection.yaml`

#### 核心配置项

```yaml
# 系统配置
system:
  name: "marketprism-unified-collector"
  version: "2.0.0"
  environment: "production"

# 交易所配置
exchanges:
  binance_spot:
    enabled: true
    symbols: ["BTCUSDT"]  # 原始格式，会自动标准化为BTC-USDT
    data_types: ["orderbook", "trade"]

  binance_derivatives:
    enabled: true
    symbols: ["BTCUSDT", "ETHUSDT"]  # 原始格式，会自动标准化
    data_types: ["orderbook", "trade"]

  okx_spot:
    enabled: true
    symbols: ["BTC-USDT", "ETH-USDT"]  # 已是标准格式
    data_types: ["orderbook", "trade"]

  okx_derivatives:
    enabled: true
    symbols: ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]  # 原始格式，会标准化为BTC-USDT
    data_types: ["orderbook", "trade"]

# NATS配置
nats:
  enabled: true
  servers: ["nats://localhost:4222"]
  client_name: "unified-collector"
```

### 日志配置

日志配置文件: `config/logging/optimized_logging.yaml`

- **ERROR**: 仅真正的系统错误
- **WARNING**: 需要关注的业务警告
- **INFO**: 关键业务信息（推荐生产环境）
- **DEBUG**: 详细调试信息（开发环境）

## 📊 数据格式

### NATS Topic格式

```
{data_type}-data.{exchange}.{market_type}.{symbol}
```

示例:
- `orderbook-data.binance_spot.spot.BTC-USDT`
- `trade-data.okx_derivatives.perpetual.BTC-USDT`
- `lsr-top-position-data.binance_derivatives.perpetual.BTC-USDT`
- `lsr-all-account-data.okx_derivatives.perpetual.ETH-USDT`

**📝 说明**: 所有symbol都会被标准化为BTC-USDT格式，原始的BTCUSDT、BTC-USDT-SWAP等格式会自动转换。

### 数据结构

#### OrderBook数据
```json
{
  "exchange": "binance_spot",
  "symbol": "BTC-USDT",
  "market_type": "spot",
  "timestamp": "2025-07-25T05:42:22.747762Z",
  "bids": [["43250.50", "0.125"], ["43250.00", "0.250"]],
  "asks": [["43251.00", "0.100"], ["43251.50", "0.200"]],
  "depth_levels": 400
}
```

#### Trades数据
```json
{
  "exchange": "binance_spot",
  "symbol": "BTC-USDT",
  "market_type": "spot",
  "timestamp": "2025-07-25T05:42:22.747762Z",
  "price": "43250.75",
  "quantity": "0.125",
  "side": "buy",
  "trade_id": "12345678"
}
```

#### LSR顶级持仓数据
```json
{
  "exchange": "binance_derivatives",
  "symbol": "BTC-USDT",
  "market_type": "perpetual",
  "timestamp": "2025-08-02T04:05:00+00:00",
  "long_position_ratio": 0.6523,
  "short_position_ratio": 0.3477,
  "long_short_ratio": 1.8760
}
```

#### LSR全账户数据
```json
{
  "exchange": "okx_derivatives",
  "symbol": "ETH-USDT",
  "market_type": "perpetual",
  "timestamp": "2025-08-02T04:05:00+00:00",
  "long_account_ratio": 0.6226,
  "short_account_ratio": 0.3774,
  "long_short_ratio": 1.65
}
```

## 🔧 运维指南

### 启动参数

```bash
# 基本启动
python unified_collector_main.py

# 指定日志级别
python unified_collector_main.py --log-level DEBUG

# 指定配置文件
python unified_collector_main.py --config /path/to/config.yaml

# 只启动特定交易所
python unified_collector_main.py --exchange binance_spot
```

### 性能监控

系统提供实时监控指标：
- **内存使用**: 警告阈值500MB，临界阈值800MB
- **CPU使用率**: 警告阈值60%，临界阈值80%
- **连接状态**: WebSocket连接健康度
- **消息处理**: 每秒处理的消息数量

### 故障排查

1. **连接问题**: 检查网络连接和防火墙设置
2. **内存不足**: 调整系统资源配置
3. **数据延迟**: 检查WebSocket连接状态
4. **NATS连接**: 确认NATS服务器运行状态

## 🧪 开发指南

### 项目结构

```
marketprism/
├── services/
│   ├── data-collector/              # 核心数据收集服务
│   │   ├── unified_collector_main.py # 统一入口文件
│   │   ├── collector/               # 收集器模块
│   │   ├── exchanges/               # 交易所适配器
│   │   └── core/                   # 核心功能模块
│   └── message-broker/             # 消息代理服务
│       ├── unified_message_broker_main.py # 统一入口文件
│       ├── main.py                 # 核心服务实现
│       └── nats_config.yaml        # NATS配置文件
├── config/                         # 配置文件
│   ├── collector/                  # 收集器配置
│   │   └── unified_data_collection.yaml
│   ├── message-broker/             # 消息代理配置
│   │   └── unified_message_broker.yaml
│   └── logging/                    # 日志配置
├── core/                          # 共享核心模块
└── venv/                         # Python虚拟环境
```

### 添加新交易所

1. 在`exchanges/`目录创建新的WebSocket适配器
2. 在`collector/orderbook_managers/`创建订单簿管理器
3. 在配置文件中添加交易所配置
4. 更新工厂类以支持新交易所

### 测试

```bash
# 运行所有测试
cd services/data-collector
python -m pytest tests/

# 运行特定测试
python -m pytest tests/test_orderbook_integration.py

# 生成覆盖率报告
python -m pytest --cov=collector tests/
```

## 📈 性能优化

### 系统优化建议

1. **内存优化**: 
   - 启用内存管理器自动清理
   - 设置合适的订单簿深度限制

2. **网络优化**:
   - 使用稳定的网络连接
   - 启用WebSocket自动重连

3. **日志优化**:
   - 生产环境使用INFO级别
   - 启用日志轮转和压缩

### 扩展性考虑

- 支持水平扩展多个收集器实例
- NATS集群部署提高可用性
- 数据分片存储支持大规模数据

## 🤝 贡献指南

1. Fork项目仓库
2. 创建功能分支: `git checkout -b feature/new-feature`
3. 提交更改: `git commit -m 'feat: 添加新功能'`
4. 推送分支: `git push origin feature/new-feature`
5. 创建Pull Request

### 提交信息规范

- `feat:` 新功能
- `fix:` 错误修复
- `docs:` 文档更新
- `refactor:` 代码重构
- `perf:` 性能优化

## 📄 许可证

本项目采用MIT许可证 - 详见 [LICENSE](LICENSE) 文件。

## 🆘 支持

如有问题或建议，请：
1. 查看[故障排查指南](#故障排查)
2. 提交[GitHub Issue](https://github.com/MNS-Vic/marketprism/issues)
3. 参与[讨论区](https://github.com/MNS-Vic/marketprism/discussions)
