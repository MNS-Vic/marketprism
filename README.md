# MarketPrism

MarketPrism是一个高性能的加密货币市场数据收集平台，专为实时数据分析和量化交易而设计。采用统一架构，支持多交易所数据收集，具备优秀的稳定性和可扩展性。

## ✨ 核心特性

- **🚀 统一架构**: 唯一入口 + 唯一配置，简化部署和维护
- **📊 多交易所支持**: Binance（现货+衍生品）、OKX（现货+衍生品）
- **⚡ 实时数据收集**: OrderBook深度数据 + Trades成交数据
- **🔄 WebSocket长连接**: 稳定的WebSocket连接，支持自动重连
- **📨 NATS消息推送**: 实时数据推送到消息队列
- **📈 系统监控**: 内存、CPU、连接状态全面监控
- **🎯 企业级日志系统**: 统一格式、智能去重、性能优化，减少60-80%冗余输出

## 🏗️ 系统架构

### 统一数据收集架构

```
┌─────────────────────────────────────────────────────────────┐
│                    MarketPrism 统一架构                      │
├─────────────────────────────────────────────────────────────┤
│  唯一入口: unified_collector_main.py                        │
│  唯一配置: config/collector/unified_data_collection.yaml    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    8个数据管理器                             │
├─────────────────────────────────────────────────────────────┤
│  Binance现货:     OrderBook + Trades 管理器                │
│  Binance衍生品:   OrderBook + Trades 管理器                │
│  OKX现货:        OrderBook + Trades 管理器                │
│  OKX衍生品:      OrderBook + Trades 管理器                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    NATS消息推送                             │
├─────────────────────────────────────────────────────────────┤
│  Topic格式: {data_type}-data.{exchange}.{market}.{symbol}   │
│  示例: orderbook-data.binance_spot.spot.BTC-USDT           │
└─────────────────────────────────────────────────────────────┘
```

### 核心组件

- **统一数据收集器**: 管理所有交易所的数据收集
- **WebSocket管理器**: 维护稳定的WebSocket连接
- **订单簿管理器**: 处理实时订单簿数据
- **成交数据管理器**: 处理实时成交数据
- **数据标准化器**: 统一不同交易所的数据格式
- **NATS发布器**: 实时数据推送
- **系统监控器**: 资源使用和连接状态监控

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

4. **启动NATS服务器**:
```bash
# 使用Docker启动NATS
docker run -d --name nats-server -p 4222:4222 nats:latest
```

5. **启动数据收集器**:
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
├── services/data-collector/          # 核心数据收集服务
│   ├── unified_collector_main.py     # 统一入口文件
│   ├── collector/                    # 收集器模块
│   ├── exchanges/                    # 交易所适配器
│   └── core/                        # 核心功能模块
├── config/                          # 配置文件
│   ├── collector/                   # 收集器配置
│   └── logging/                     # 日志配置
├── core/                           # 共享核心模块
└── venv/                          # Python虚拟环境
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
