# MarketPrism Python Collector

高性能的加密货币市场数据收集器，采用Python编写，支持多个主流交易所的实时数据采集。

## 特性

- 🚀 **高性能异步处理** - 基于asyncio和uvloop的高性能事件循环
- 🔗 **多交易所支持** - 支持Binance、OKX、Deribit等主流交易所
- 📡 **实时数据流** - WebSocket实时数据订阅
- 🎯 **数据标准化** - 统一的数据格式，便于后续处理
- 📊 **NATS集成** - 通过NATS JetStream进行高可靠数据分发
- 🔄 **自动重连** - 智能重连机制，确保数据连续性
- 📈 **监控指标** - 完善的Prometheus指标和健康检查
- ⚙️ **灵活配置** - 支持YAML配置文件和环境变量

## 快速开始

### 1. 安装依赖

```bash
# 克隆仓库
git clone https://github.com/marketprism/marketprism
cd marketprism/services/python-collector

# 安装依赖
pip install -r requirements.txt

# 安装包
pip install -e .
```

### 2. 初始化配置

```bash
# 生成默认配置文件
python -m marketprism_collector init

# 这将在config/目录下生成：
# - collector.yaml (主配置文件)
# - exchanges/binance_spot.yaml (交易所配置示例)
# - .env.example (环境变量示例)
```

### 3. 配置环境变量

```bash
# 复制并编辑环境变量文件
cp config/.env.example config/.env

# 编辑.env文件，填入必要的配置
# 例如：NATS_URL, API密钥等
```

### 4. 启动收集器

```bash
# 使用默认配置启动
python -m marketprism_collector run

# 使用指定配置文件启动
python -m marketprism_collector run -c config/collector.yaml

# 启用调试模式
python -m marketprism_collector run --debug
```

## 配置说明

### 主配置文件 (collector.yaml)

```yaml
# 收集器配置
collector:
  use_real_exchanges: false  # 是否使用真实交易所
  log_level: "INFO"
  http_port: 8080
  max_reconnect_attempts: 5

# NATS配置
nats:
  url: "nats://localhost:4222"
  client_name: "marketprism-collector"

# 交易所配置文件列表
exchanges:
  configs:
    - "exchanges/binance_spot.yaml"
```

### 交易所配置文件示例

```yaml
# Binance现货配置
exchange: "binance"
market_type: "spot"
enabled: true

# API配置
base_url: "https://api.binance.com"
ws_url: "wss://stream.binance.com:9443/ws"

# 数据类型
data_types:
  - "trade"
  - "orderbook" 
  - "ticker"

# 监听的交易对
symbols:
  - "BTCUSDT"
  - "ETHUSDT"
```

## 数据输出

收集器会将标准化的数据发布到NATS，主题格式为：

- 交易数据：`market.{exchange}.{symbol}.trade`
- 订单簿：`market.{exchange}.{symbol}.orderbook`
- K线数据：`market.{exchange}.{symbol}.kline.{interval}`
- 行情数据：`market.{exchange}.{symbol}.ticker`

### 数据格式示例

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

## 监控和健康检查

### HTTP端点

- `GET /health` - 健康检查
- `GET /metrics` - Prometheus指标
- `GET /status` - 详细状态信息

### 指标示例

```
marketprism_messages_received_total 1234
marketprism_messages_processed_total 1230
marketprism_messages_published_total 1230
marketprism_errors_total 4
```

## Docker部署

### 构建镜像

```bash
docker build -t marketprism-collector:latest .
```

### 运行容器

```bash
docker run -d \
  --name marketprism-collector \
  -p 8080:8080 \
  -v $(pwd)/config:/app/config \
  -e NATS_URL=nats://nats-server:4222 \
  marketprism-collector:latest
```

## 命令行接口

```bash
# 查看帮助
python -m marketprism_collector --help

# 初始化配置
python -m marketprism_collector init -o config/collector.yaml

# 验证配置
python -m marketprism_collector validate -c config/collector.yaml

# 运行收集器
python -m marketprism_collector run -c config/collector.yaml --debug

# 查看版本
python -m marketprism_collector version
```

## 开发

### 运行测试

```bash
pytest tests/
```

### 代码格式化

```bash
black src/
```

### 类型检查

```bash
mypy src/
```

## 许可证

MIT License

## 支持

如有问题或建议，请提交Issue或联系团队。 