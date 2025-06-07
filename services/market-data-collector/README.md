# Market Data Collector Service

MarketPrism微服务架构的核心数据采集服务，基于成熟的python-collector组件构建。

## 功能特性

### 🚀 核心功能
- **多交易所支持**: Binance、OKX、Deribit等主流交易所
- **实时数据流**: WebSocket实时数据订阅和处理
- **数据标准化**: 统一的数据格式，确保一致性
- **消息队列集成**: 通过NATS JetStream发布数据
- **动态订阅**: 运行时动态添加/移除交易对订阅

### 📊 数据类型
- 交易数据 (Trades)
- 订单簿数据 (Order Books) 
- K线数据 (Klines)
- 行情数据 (Tickers)
- 资金费率 (Funding Rates)
- 持仓量 (Open Interest)

### 🔧 微服务特性
- **服务发现**: 自动注册到服务注册中心
- **健康检查**: 完善的健康检查和监控
- **性能指标**: Prometheus指标导出
- **优雅关闭**: 支持优雅的服务关闭
- **配置热更新**: 支持配置的动态更新

## 快速开始

### 1. 环境准备

确保以下服务正在运行：
- NATS Server (端口 4222)
- 可选：Prometheus (用于指标收集)

### 2. 配置服务

编辑 `config/services.yaml`：

```yaml
market-data-collector:
  port: 8081
  nats_url: "nats://localhost:4222"
  log_level: "INFO"
  enable_deribit: false
  
  # Python Collector配置路径
  collector_config_path: "services/python-collector/config/collector.yaml"
```

### 3. 启动服务

```bash
# 直接启动
cd services/market-data-collector
python main.py

# 或使用服务管理器
cd scripts
python start_services.py --service market-data-collector
```

### 4. 验证服务

```bash
# 健康检查
curl http://localhost:8081/health

# 服务状态
curl http://localhost:8081/api/v1/status

# 交易所统计
curl http://localhost:8081/api/v1/exchanges/binance/stats
```

## API接口

### 健康检查

```http
GET /health
```

返回服务健康状态，包括：
- 服务基本信息
- Python Collector状态
- 交易所连接状态
- 数据处理统计

### 服务状态

```http
GET /api/v1/status
```

返回详细的服务状态：

```json
{
  "service": "market-data-collector",
  "running": true,
  "start_time": "2024-01-01T12:00:00Z",
  "uptime_seconds": 3600,
  "collector_metrics": {
    "messages_processed": 10000,
    "messages_published": 9999,
    "errors_count": 1
  },
  "exchanges": {
    "binance": {
      "connected": true,
      "messages_count": 5000,
      "errors_count": 0
    }
  }
}
```

### 交易所统计

```http
GET /api/v1/exchanges/{exchange_name}/stats
```

获取指定交易所的详细统计信息。

支持的交易所：
- `binance`
- `okx` 
- `deribit`

### 动态订阅控制

```http
POST /api/v1/exchanges/{exchange_name}/subscribe
```

请求体：
```json
{
  "action": "subscribe",
  "symbols": ["BTC-USDT", "ETH-USDT"],
  "data_types": ["trade", "orderbook", "ticker"]
}
```

支持的操作：
- `subscribe`: 订阅新的交易对
- `unsubscribe`: 取消订阅

## 数据输出

### NATS主题格式

数据通过NATS发布到以下主题：

- **交易数据**: `market.{exchange}.{symbol}.trade`
- **订单簿**: `market.{exchange}.{symbol}.orderbook`
- **K线数据**: `market.{exchange}.{symbol}.kline.{interval}`
- **行情数据**: `market.{exchange}.{symbol}.ticker`
- **资金费率**: `market.{exchange}.{symbol}.funding_rate`

### 数据格式示例

#### 交易数据
```json
{
  "exchange_name": "binance",
  "symbol_name": "BTCUSDT",
  "trade_id": "12345",
  "price": "50000.00",
  "quantity": "0.1",
  "timestamp": "2024-01-01T12:00:00Z",
  "is_buyer_maker": false
}
```

#### 订单簿数据
```json
{
  "exchange_name": "binance",
  "symbol_name": "BTCUSDT",
  "timestamp": "2024-01-01T12:00:00Z",
  "bids": [
    {"price": "49999.00", "quantity": "0.5"},
    {"price": "49998.00", "quantity": "1.0"}
  ],
  "asks": [
    {"price": "50001.00", "quantity": "0.3"},
    {"price": "50002.00", "quantity": "0.8"}
  ]
}
```

## 监控和指标

### Prometheus指标

```http
GET /metrics
```

主要指标：
- `messages_processed_total`: 处理的消息总数
- `messages_published_total`: 发布的消息总数  
- `errors_total`: 错误总数
- `uptime_seconds`: 服务运行时间
- `exchange_connections_active`: 活跃的交易所连接数

### 日志记录

服务使用结构化日志记录，支持以下级别：
- `DEBUG`: 详细调试信息
- `INFO`: 一般信息 (默认)
- `WARNING`: 警告信息
- `ERROR`: 错误信息

日志格式：
```json
{
  "timestamp": "2024-01-01T12:00:00Z",
  "level": "INFO",
  "logger": "market-data-collector",
  "message": "Service started successfully",
  "exchange": "binance",
  "symbol": "BTCUSDT"
}
```

## 配置参考

### 服务配置

```yaml
market-data-collector:
  # 服务端口
  port: 8081
  
  # NATS连接
  nats_url: "nats://localhost:4222"
  
  # 日志级别
  log_level: "INFO"
  
  # 是否启用Deribit
  enable_deribit: false
  
  # Python Collector配置文件路径
  collector_config_path: "services/python-collector/config/collector.yaml"
```

### Python Collector配置

服务会自动创建默认的Python Collector配置，包括：

- **Binance**: 期货市场，支持BTC/ETH/BNB交易对
- **OKX**: 期货市场，支持主流交易对
- **Deribit**: 永续合约 (可选启用)

默认监听的数据类型：
- 交易数据 (trade)
- 订单簿 (orderbook)
- 行情数据 (ticker)

## 故障排除

### 常见问题

1. **服务无法启动**
   - 检查NATS服务是否运行
   - 检查端口8081是否被占用
   - 检查Python Collector依赖是否安装

2. **交易所连接失败**
   - 检查网络连接
   - 检查交易所API状态
   - 查看日志中的详细错误信息

3. **数据处理异常**
   - 检查NATS连接状态
   - 查看错误统计指标
   - 检查内存和CPU使用情况

### 日志分析

```bash
# 查看服务日志
curl http://localhost:8081/health | jq

# 查看特定交易所状态
curl http://localhost:8081/api/v1/exchanges/binance/stats | jq

# 查看Prometheus指标
curl http://localhost:8081/metrics
```

## 开发和扩展

### 添加新交易所

1. 在Python Collector中实现新的交易所适配器
2. 更新`supported_exchanges`列表
3. 添加相应的配置模板
4. 更新API文档

### 性能优化

- 调整批处理大小
- 优化内存使用
- 调整连接池配置
- 启用数据压缩

### 集成测试

```bash
# 运行集成测试
cd tests/integration
python test_market_data_collector.py
```

## 相关服务

- **Data Storage Service**: 数据存储和查询
- **API Gateway Service**: 统一API网关
- **Monitoring Service**: 系统监控
- **Message Broker Service**: 消息路由

## 支持

如有问题或建议，请查看：
- 项目文档: `docs/`
- 问题追踪: GitHub Issues
- 联系团队: team@marketprism.com