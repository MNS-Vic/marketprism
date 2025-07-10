# MarketPrism Data Collector Service

MarketPrism的统一数据采集服务，支持多种运行模式，包含完整的OrderBook Manager功能。

## 🎯 功能特性

### 🚀 核心功能
- **多交易所支持**: Binance、OKX、Deribit等主流交易所
- **实时数据流**: WebSocket实时数据订阅和处理
- **OrderBook Manager**: 本地订单簿维护，支持快照+增量更新
- **数据标准化**: 统一的数据格式，确保一致性
- **消息队列集成**: 通过NATS JetStream发布数据
- **动态订阅**: 运行时动态添加/移除交易对订阅

### 📊 数据类型
- 交易数据 (Trades)
- 订单簿数据 (Order Books) - 支持本地维护
- K线数据 (Klines)
- 行情数据 (Tickers)
- 资金费率 (Funding Rates)
- 持仓量 (Open Interest)
- 大户持仓比数据 (Top Trader Long/Short Ratio)

### 🔧 运行模式
- **launcher**: 完整数据收集系统（包含HTTP服务和监控）- **推荐**
- **collector**: 数据收集模式（默认）
- **service**: 微服务模式（提供HTTP API）
- **test**: 测试验证模式

## 🚀 快速开始

### 1. 环境准备

```bash
# 确保Python版本
python --version  # 需要 3.11+

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置服务

主要配置文件：`../../config/collector/unified_data_collection.yaml`

该配置文件包含：
- 系统配置（日志、网络等）
- 交易所配置（Binance现货/永续、OKX现货/永续）
- NATS配置（消息队列）
- WebSocket配置（连接管理）

### 3. 启动服务

#### 统一启动入口（推荐）
```bash
cd services/data-collector

# 完整数据收集系统（推荐）
python unified_collector_main.py --mode launcher --config ../../config/collector/unified_data_collection.yaml

# 数据收集模式
python unified_collector_main.py --mode collector

# 微服务模式
python unified_collector_main.py --mode service

# 测试验证模式
python unified_collector_main.py --mode test

# 查看帮助
python unified_collector_main.py --help
```

### 4. 验证服务

```bash
# 健康检查
curl http://localhost:8086/health

# 指标监控
curl http://localhost:9093/metrics

# 验证NATS消息（需要安装nats CLI）
nats sub "orderbook-data.>"
```

## 📡 API接口

### 基础接口

#### 健康检查
```http
GET /health
```

#### 服务状态
```http
GET /api/v1/collector/status
```

返回示例：
```json
{
  "status": "standalone_mode",
  "service": "market-data-collector",
  "supported_exchanges": ["binance", "okx", "deribit"],
  "supported_data_types": ["trade", "orderbook", "ticker", "kline"],
  "features": [
    "API-based data collection",
    "OrderBook Manager",
    "Health monitoring"
  ]
}
```

### OrderBook Manager接口

#### 获取订单簿
```http
GET /api/v1/orderbook/{exchange}/{symbol}
```

#### 获取订单簿快照
```http
GET /api/v1/orderbook/{exchange}/{symbol}/snapshot
```

#### OrderBook统计
```http
GET /api/v1/orderbook/stats
GET /api/v1/orderbook/stats/{exchange}
```

#### OrderBook健康检查
```http
GET /api/v1/orderbook/health
```

### 数据中心接口

#### 快照代理
```http
GET /api/v1/snapshot/{exchange}/{symbol}
GET /api/v1/snapshot/{exchange}/{symbol}/cached
```

#### 数据中心信息
```http
GET /api/v1/data-center/info
```

## 🏗️ 架构设计

### OrderBook Manager
基于Binance官方文档的最佳实践：

1. **WebSocket订阅**: 订阅深度更新流
2. **快照获取**: 定期获取完整快照
3. **增量更新**: 处理WebSocket增量更新
4. **数据验证**: 确保数据一致性和完整性
5. **错误恢复**: 自动重连和数据恢复

### 数据流
```
交易所WebSocket → 原始数据处理 → 数据标准化 → OrderBook Manager → REST API
                                    ↓
                              NATS发布 → 下游服务
```

## 🔧 配置说明

### 核心配置
- `enable_orderbook_manager`: 启用OrderBook Manager
- `enable_top_trader_collector`: 启用大户持仓比收集
- `standalone_mode`: 独立模式，不依赖外部服务
- `data_output_mode`: 数据输出模式（api_only/nats/both）

### 交易所配置
- `exchange`: 交易所名称
- `market_type`: 市场类型（spot/futures）
- `symbols`: 订阅的交易对
- `data_types`: 订阅的数据类型

## 📊 监控和指标

### 性能指标
- 消息处理速度
- 错误率统计
- 连接状态监控
- OrderBook更新频率

### 日志级别
- `DEBUG`: 详细调试信息
- `INFO`: 一般信息（默认）
- `WARNING`: 警告信息
- `ERROR`: 错误信息

## 🔍 故障排除

### 常见问题

1. **OrderBook API返回404**
   - 检查`enable_orderbook_manager`是否为true
   - 确认服务启动时没有错误

2. **datetime错误**
   - 已修复所有datetime导入问题
   - 如遇到新问题，检查Python版本是否为3.11+

3. **配置文件找不到**
   - 确保从项目根目录运行
   - 检查`config/collector.yaml`是否存在

### 调试模式
```bash
# 启用调试日志
export MARKETPRISM_LOG_LEVEL=DEBUG
python main.py --mode full
```

## 📝 开发说明

### 项目结构
```
services/data-collector/
├── main.py                 # 统一入口
├── src/marketprism_collector/
│   ├── collector.py        # 主要collector实现
│   ├── orderbook_manager.py # OrderBook Manager
│   ├── rest_api.py         # REST API接口
│   └── ...
├── config/                 # 配置文件
├── requirements.txt        # Python依赖
└── README.md              # 本文档
```

### 扩展开发
- 添加新交易所：实现ExchangeAdapter接口
- 添加新数据类型：扩展DataType枚举
- 自定义API：修改rest_api.py

## 📄 许可证

MIT License - 详见项目根目录LICENSE文件 