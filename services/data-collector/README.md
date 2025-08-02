# MarketPrism Data Collector Service

MarketPrism的统一数据采集服务，采用现代化微服务架构，支持多交易所实时数据收集、处理和分发。

## 🔄 **重大更新 (2025-08-02) - Docker部署简化改造**

### **🎯 简化改造成果**
- ✅ **运行模式简化**: 从4种模式（collector, service, launcher, test）简化为**launcher模式**
- ✅ **Docker配置统一**: 简化docker-compose.unified.yml，单一服务定义
- ✅ **配置本地化**: 配置文件迁移到`services/data-collector/config/`
- ✅ **部署流程优化**: 两步命令完成整个系统部署
- ✅ **功能完整性**: 8种数据类型 × 5个交易所全部正常工作

### **🚀 新的部署方式**
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

## 🎯 核心特性

### 🚀 架构优势
- **统一入口**: 单一启动文件 `unified_collector_main.py`
- **模块化设计**: 订单簿管理器、交易数据管理器、错误处理系统独立解耦
- **多交易所支持**: Binance现货/衍生品、OKX现货/衍生品
- **生产级稳定性**: 断路器、重试机制、内存管理、连接监控
- **实时数据流**: WebSocket实时订阅，毫秒级数据处理
- **智能容错**: 自动重连、序列号验证、数据完整性检查

### 📊 数据管理
- **订单簿数据**: 完整深度维护，支持400/5000级别深度
- **交易数据**: 实时逐笔成交数据收集
- **资金费率**: 8小时周期资金费率数据收集
- **未平仓量**: 5分钟间隔未平仓量数据收集
- **多空持仓比例**: LSR数据收集（顶级大户和全市场）
- **强平数据**: 实时强制平仓事件监控
- **波动率指数**: Deribit波动率指数数据收集（5分钟间隔）
- **数据标准化**: 统一格式，支持BTC-USDT标准化符号
- **NATS JetStream**: 持久化消息存储，确保数据不丢失
- **结构化主题**: `{data_type}-data.{exchange}_{market_category}.{market_type}.{symbol}`
- **序列号验证**: Binance lastUpdateId、OKX seqId/checksum双重验证

### 🔧 运行模式 (简化后)
- **launcher**: 完整数据收集系统（唯一模式）- 包含所有功能
  - 健康检查端口: 8086
  - Prometheus监控端口: 9093
  - 支持8种数据类型和5个交易所
  - 自动连接统一NATS容器

### 🏗️ 架构变更说明
**简化前**: 4种运行模式（collector, service, launcher, test）
**简化后**: 1种运行模式（launcher）

**优势**:
- 部署更简单，只需一个命令
- 配置更统一，减少选择困难
- 维护更容易，专注核心功能
- 功能更完整，包含所有数据收集能力
- **单交易所模式**: 指定单个交易所运行 (`--exchange binance_spot`)
- **多交易所模式**: 并行运行多个交易所（默认）
- **调试模式**: 详细日志输出 (`--log-level DEBUG`)

## 🚀 快速开始

### 1. 环境准备

```bash
# 确保Python版本
python --version  # 需要 3.11+

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置服务

#### 📁 配置文件结构
```
config/collector/
├── unified_data_collection.yaml        # 统一数据收集配置
├── nats-server.conf                    # NATS服务器配置 (传统部署)
├── nats-server-docker.conf             # NATS服务器配置 (Docker部署)
└── docker-compose.nats.yml             # NATS Docker Compose配置
```

#### ⚙️ 主要配置说明

**统一数据收集配置**: `../../config/collector/unified_data_collection.yaml`
- **系统配置**: 日志级别、网络设置、内存管理
- **交易所配置**: Binance现货/衍生品、OKX现货/衍生品、Deribit衍生品
- **数据类型配置**: orderbook、trades、funding_rate、open_interest、liquidation、lsr、vol_index
- **NATS配置**: 消息队列服务器、主题格式、JetStream设置
- **WebSocket配置**: 连接管理、心跳机制、重连策略

**NATS服务器配置**:
- **传统部署**: `nats-server.conf` - 适用于直接在主机上部署
- **Docker部署**: `nats-server-docker.conf` - 优化的容器部署配置

### 3. 启动服务

#### 统一启动入口（推荐）
```bash
cd services/data-collector

# 🚀 一键启动数据收集（推荐）
python unified_collector_main.py

# 🧪 测试验证模式
python unified_collector_main.py --mode test

# 🎯 指定单个交易所
python unified_collector_main.py --exchange binance_spot
python unified_collector_main.py --exchange binance_derivatives
python unified_collector_main.py --exchange okx_spot
python unified_collector_main.py --exchange okx_derivatives

# 🔍 调试模式
python unified_collector_main.py --log-level DEBUG

# 📋 指定配置文件
python unified_collector_main.py --config custom_config.yaml

# ❓ 查看帮助
python unified_collector_main.py --help
```

### 4. NATS服务器部署

#### 🖥️ 传统部署 (直接在主机上)
```bash
# 进入data-collector目录
cd services/data-collector

# 部署NATS配置 (需要sudo权限)
sudo ./deploy-nats-config.sh

# 验证部署
systemctl status nats-server
curl http://localhost:8222/jsz
```

#### 🐳 Docker部署 (推荐)
```bash
# 进入data-collector目录
cd services/data-collector

# 部署NATS Docker容器
./deploy-nats-docker.sh

# 验证部署
docker-compose -f ../../config/collector/docker-compose.nats.yml ps
curl http://localhost:8222/jsz
```

### 5. 数据收集器部署

#### 🐳 使用Docker Compose (推荐)
```bash
# 启动完整系统 (包括NATS)
cd /path/to/marketprism
docker-compose up -d

# 只启动数据收集器 (需要先启动NATS)
docker-compose up -d data-collector

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f data-collector
```

#### 🔧 单独构建和运行
```bash
# 构建镜像
cd services/data-collector
docker build -t marketprism-collector .

# 运行容器
docker run -d \
  --name marketprism-collector \
  -v $(pwd)/../../config:/app/config \
  -e MARKETPRISM_LOG_LEVEL=INFO \
  --network marketprism_default \
  marketprism-collector
```

### 5. 验证服务

```bash
# 🔍 检查容器状态
docker-compose ps

# 📊 查看实时日志
docker-compose logs -f data-collector

# 🧪 验证NATS消息（需要安装nats CLI）
nats sub "orderbook-data.>"

# 📈 查看订单簿数据
nats sub "orderbook-data.binance_spot.spot.BTC-USDT"

# 💱 查看交易数据
nats sub "trades-data.okx_derivatives.perpetual.BTC-USDT-SWAP"
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

## 🏗️ 系统架构

### 📊 核心组件架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    unified_collector_main.py                    │
│                        统一启动入口                              │
└─────────────────────┬───────────────────────────────────────────┘
                      │
┌─────────────────────┴───────────────────────────────────────────┐
│                    collector/                                   │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐   │
│  │ orderbook_      │ │ trades_         │ │ funding_rate_   │   │
│  │ managers/       │ │ managers/       │ │ managers/       │   │
│  │                 │ │                 │ │                 │   │
│  │ • binance_spot  │ │ • binance_spot  │ │ • okx_deriv     │   │
│  │ • binance_deriv │ │ • binance_deriv │ │ • binance_deriv │   │
│  │ • okx_spot      │ │ • okx_spot      │ │                 │   │
│  │ • okx_deriv     │ │ • okx_deriv     │ │                 │   │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘   │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐   │
│  │ open_interest_  │ │ liquidation_    │ │ lsr_            │   │
│  │ managers/       │ │ managers/       │ │ managers/       │   │
│  │                 │ │                 │ │                 │   │
│  │ • okx_deriv     │ │ • binance_deriv │ │ • binance_deriv │   │
│  │ • binance_deriv │ │ • okx_deriv     │ │ • okx_deriv     │   │
│  │                 │ │                 │ │ • top_position  │   │
│  │                 │ │                 │ │ • all_account   │   │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                nats_publisher.py                        │   │
│  │  • 数据标准化  • JetStream持久化  • 主题路由管理         │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────┬───────────────────────────────────────────┘
                      │
┌─────────────────────┴───────────────────────────────────────────┐
│                    exchanges/                                   │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐   │
│  │ binance_        │ │ okx_            │ │ base_           │   │
│  │ websocket.py    │ │ websocket.py    │ │ websocket.py    │   │
│  │                 │ │                 │ │                 │   │
│  │ • WebSocket连接 │ │ • WebSocket连接 │ │ • 基础适配器     │   │
│  │ • 心跳机制      │ │ • 心跳机制      │ │ • 连接管理      │   │
│  │ • 数据解析      │ │ • 数据解析      │ │ • 错误处理      │   │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 📡 数据流架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            数据收集层                                        │
├─────────────────┬─────────────────┬─────────────────┬─────────────────────────┤
│ WebSocket实时流 │ HTTP API轮询    │ 定时任务收集    │ 事件驱动收集            │
│                 │                 │                 │                         │
│ • OrderBook     │ • FundingRate   │ • OpenInterest  │ • Liquidation           │
│ • Trades        │ • LSR Data      │                 │                         │
└─────────────────┴─────────────────┴─────────────────┴─────────────────────────┘
         ↓                 ↓                 ↓                 ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                            数据处理层                                        │
├─────────────────┬─────────────────┬─────────────────┬─────────────────────────┤
│ 数据解析        │ 序列号验证      │ 数据标准化      │ 错误处理                │
│                 │                 │                 │                         │
│ • JSON解析      │ • lastUpdateId  │ • Symbol格式    │ • 重连机制              │
│ • 格式验证      │ • seqId检查     │ • 时间戳统一    │ • 断路器                │
│ • 完整性检查    │ • Checksum验证  │ • 数值精度      │ • 降级策略              │
└─────────────────┴─────────────────┴─────────────────┴─────────────────────────┘
         ↓                 ↓                 ↓                 ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                         NATS JetStream层                                    │
├─────────────────┬─────────────────┬─────────────────┬─────────────────────────┤
│ 消息持久化      │ 主题路由        │ 流管理          │ 消费者管理              │
│                 │                 │                 │                         │
│ • 文件存储      │ • 结构化主题    │ • MARKET_DATA   │ • 订阅管理              │
│ • 内存缓存      │ • 通配符支持    │ • 保留策略      │ • 负载均衡              │
│ • 数据压缩      │ • 权限控制      │ • 副本配置      │ • 故障转移              │
└─────────────────┴─────────────────┴─────────────────┴─────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                            主题格式                                          │
│                                                                             │
│ {data_type}-data.{exchange}_{market_category}.{market_type}.{symbol}        │
│                                                                             │
│ 示例:                                                                       │
│ • orderbook-data.binance_spot.spot.BTC-USDT                               │
│ • trades-data.okx_derivatives.perpetual.BTC-USDT-SWAP                     │
│ • funding-rate-data.binance_derivatives.perpetual.BTC-USDT                │
│ • open-interest-data.okx_derivatives.perpetual.ETH-USDT-SWAP              │
│ • liquidation-orders.binance_derivatives.perpetual.BTC-USDT               │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 🔧 订单簿管理器设计

基于交易所官方文档的最佳实践：

**Binance订单簿管理**:
1. **API快照初始化**: 获取完整订单簿快照
2. **WebSocket增量更新**: 处理实时深度更新
3. **序列号验证**: lastUpdateId连续性检查
4. **数据完整性**: 自动重新同步机制

**OKX订单簿管理**:
1. **WebSocket快照**: 订阅时自动推送完整快照
2. **增量更新处理**: 基于seqId的增量更新
3. **Checksum验证**: CRC32校验和验证数据完整性
4. **智能重连**: 连接异常时自动重新订阅

### 🗄️ NATS JetStream架构

MarketPrism使用NATS JetStream作为消息持久化存储系统，确保金融数据的可靠性和持久性。

#### 📊 JetStream特性
- **持久化存储**: 消息存储到磁盘，服务重启不丢失数据
- **流管理**: 自动创建和管理MARKET_DATA流
- **消息保留**: 支持基于时间、大小、数量的保留策略
- **消费者管理**: 支持多个消费者并行处理
- **故障恢复**: 自动故障检测和恢复机制

#### 🔧 流配置策略
```yaml
MARKET_DATA流配置:
  - 主题模式: ["orderbook-data.>", "trades-data.>", "funding-rate-data.>", ...]
  - 最大消息数: 500万条
  - 最大存储: 10GB
  - 保留时间: 7天
  - 存储类型: 文件存储
  - 副本数量: 1 (单节点) / 3 (集群)
```

#### 📡 主题命名规范
```
{data_type}-data.{exchange}_{market_category}.{market_type}.{symbol}

示例:
- orderbook-data.binance_spot.spot.BTC-USDT
- trades-data.okx_derivatives.perpetual.BTC-USDT-SWAP
- funding-rate-data.binance_derivatives.perpetual.ETH-USDT
- open-interest-data.okx_derivatives.perpetual.BTC-USDT-SWAP
- liquidation-orders.binance_derivatives.perpetual.BTC-USDT
```

## 🔧 配置说明

### 📋 统一配置文件结构

```yaml
# config/collector/unified_data_collection.yaml

system:
  log_level: INFO                    # 日志级别
  memory_limit_mb: 500              # 内存限制
  enable_monitoring: true           # 启用监控

networking:
  connection_timeout: 30            # 连接超时
  max_retries: 3                   # 最大重试次数
  heartbeat_interval: 30           # 心跳间隔

exchanges:
  binance_spot:
    enabled: true                   # 启用Binance现货
    symbols: ["BTCUSDT", "ETHUSDT"] # 订阅交易对
    data_types: ["orderbook", "trades"] # 数据类型

  binance_derivatives:
    enabled: true                   # 启用Binance衍生品
    symbols: ["BTCUSDT", "ETHUSDT"]
    data_types: ["orderbook", "trades", "liquidation", "lsr_top_position", "lsr_all_account"]

  okx_spot:
    enabled: true                   # 启用OKX现货
    symbols: ["BTC-USDT", "ETH-USDT"]
    data_types: ["orderbook", "trades"]

  okx_derivatives:
    enabled: true                   # 启用OKX衍生品
    symbols: ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
    data_types: ["orderbook", "trades", "funding_rate", "open_interest", "liquidation", "lsr_top_position", "lsr_all_account"]

nats:
  servers: ["nats://localhost:4222"] # NATS服务器
  client_name: "unified-collector"   # 客户端名称
  max_reconnect_attempts: 10         # 重连次数

  # JetStream配置
  jetstream:
    enabled: true                    # 启用JetStream持久化
    streams:
      MARKET_DATA:
        subjects: ["orderbook-data.>", "trades-data.>", "funding-rate-data.>",
                  "open-interest-data.>", "liquidation-orders.>"]
        max_msgs: 5000000           # 最大消息数
        max_bytes: 10737418240      # 最大存储 (10GB)
        max_age: 604800             # 消息保留时间 (7天)
        storage: "file"             # 存储类型
        replicas: 1                 # 副本数量
```

### 🎯 核心配置项说明

**系统配置**:
- `log_level`: 日志级别 (DEBUG/INFO/WARNING/ERROR)
- `memory_limit_mb`: 内存使用限制，超过时触发清理
- `enable_monitoring`: 启用性能监控和健康检查

**网络配置**:
- `connection_timeout`: WebSocket连接超时时间
- `max_retries`: 连接失败最大重试次数
- `heartbeat_interval`: WebSocket心跳间隔

**交易所配置**:
- `enabled`: 是否启用该交易所
- `symbols`: 订阅的交易对列表
- `data_types`: 订阅的数据类型
  - `orderbook`: 订单簿数据
  - `trades`: 交易数据
  - `funding_rate`: 资金费率 (仅衍生品)
  - `open_interest`: 未平仓量 (仅衍生品)
  - `liquidation`: 强平数据 (仅衍生品)
  - `lsr_top_position`: 顶级大户多空持仓比例 (仅衍生品)
  - `lsr_all_account`: 全市场多空持仓比例 (仅衍生品)
  - `vol_index`: 波动率指数 (Deribit衍生品)

**NATS配置**:
- `servers`: NATS服务器地址列表
- `client_name`: NATS客户端名称
- `max_reconnect_attempts`: NATS重连最大尝试次数

**JetStream配置**:
- `enabled`: 是否启用JetStream持久化存储
- `streams`: 流配置
  - `subjects`: 流订阅的主题模式
  - `max_msgs`: 流中最大消息数量
  - `max_bytes`: 流的最大存储空间
  - `max_age`: 消息最大保留时间 (秒)
  - `storage`: 存储类型 (file/memory)
  - `replicas`: 副本数量 (集群模式)

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

### 🚨 常见问题

#### 1. **连接问题**
```bash
# 问题：WebSocket连接失败
# 解决：检查网络连接和防火墙设置
python unified_collector_main.py --mode test --log-level DEBUG

# 问题：NATS连接失败
# 解决：确认NATS服务器运行状态
systemctl status nats-server  # 传统部署
docker-compose -f ../../config/collector/docker-compose.nats.yml ps  # Docker部署

# 问题：JetStream不可用
# 解决：检查JetStream配置和存储权限
curl http://localhost:8222/jsz
sudo chown -R nats:nats /var/lib/nats/jetstream  # 传统部署
sudo chown -R 1000:1000 ../../data/nats/jetstream  # Docker部署
```

#### 2. **数据问题**
```bash
# 问题：序列号跳跃警告
# 说明：这是正常现象，系统会自动处理
# 监控：使用序列号分析工具
python tools/sequence_validation_analyzer.py

# 问题：订单簿数据不完整
# 解决：检查交易所API限制和网络质量
python tools/gap_monitor.py
```

#### 3. **性能问题**
```bash
# 问题：内存使用过高
# 解决：调整内存限制配置
# 监控：使用内存分析工具
python tools/analyze_memory.py

# 问题：CPU使用率高
# 解决：减少订阅的交易对数量
# 配置：在unified_data_collection.yaml中调整symbols列表
```

#### 4. **配置问题**
```bash
# 问题：配置文件找不到
# 解决：确保配置文件路径正确
ls -la ../../config/collector/unified_data_collection.yaml

# 问题：交易所配置错误
# 解决：验证配置文件格式
python -c "import yaml; yaml.safe_load(open('../../config/collector/unified_data_collection.yaml'))"
```

### 🔧 调试模式

#### 启用详细日志
```bash
# 方法1：命令行参数
python unified_collector_main.py --log-level DEBUG

# 方法2：环境变量
export MARKETPRISM_LOG_LEVEL=DEBUG
python unified_collector_main.py

# 方法3：配置文件
# 在unified_data_collection.yaml中设置：
# system:
#   log_level: DEBUG
```

#### 单交易所调试
```bash
# 只运行Binance现货进行调试
python unified_collector_main.py --exchange binance_spot --log-level DEBUG

# 只运行OKX衍生品进行调试
python unified_collector_main.py --exchange okx_derivatives --log-level DEBUG
```

### 📊 监控和诊断

#### 实时监控
```bash
# 查看系统状态
docker-compose logs -f data-collector | grep "✅\|❌\|⚠️"

# 监控内存使用
docker stats marketprism-data-collector

# 监控NATS消息流
nats sub "orderbook-data.>" --count=100
```

#### 性能分析
```bash
# 分析序列号跳跃模式
python tools/sequence_validation_analyzer.py --exchange binance_derivatives

# 监控连接质量
python tools/gap_monitor.py --duration 300

# 内存使用分析
python tools/analyze_memory.py --interval 60
```

## 📝 开发说明

### 📁 项目结构

```
services/data-collector/
├── unified_collector_main.py          # 🚀 统一启动入口
├── deploy-nats-config.sh              # 🔧 NATS传统部署脚本
├── deploy-nats-docker.sh              # 🐳 NATS Docker部署脚本
├── collector/                         # 📊 核心业务逻辑
│   ├── orderbook_managers/           # 📈 订单簿管理器
│   │   ├── base_orderbook_manager.py # 基础管理器
│   │   ├── binance_spot_manager.py   # Binance现货
│   │   ├── binance_derivatives_manager.py # Binance衍生品
│   │   ├── okx_spot_manager.py       # OKX现货
│   │   ├── okx_derivatives_manager.py # OKX衍生品
│   │   └── manager_factory.py        # 管理器工厂
│   ├── trades_managers/              # 💱 交易数据管理器
│   │   ├── base_trades_manager.py    # 基础管理器
│   │   ├── binance_spot_trades_manager.py
│   │   ├── binance_derivatives_trades_manager.py
│   │   ├── okx_spot_trades_manager.py
│   │   └── okx_derivatives_trades_manager.py
│   ├── funding_rate_managers/        # 💰 资金费率管理器
│   │   ├── base_funding_rate_manager.py
│   │   ├── okx_derivatives_funding_rate_manager.py
│   │   └── funding_rate_manager_factory.py
│   ├── open_interest_managers/       # 📊 未平仓量管理器
│   │   ├── base_open_interest_manager.py
│   │   ├── okx_derivatives_open_interest_manager.py
│   │   └── open_interest_manager_factory.py
│   ├── liquidation_managers/         # ⚡ 强平数据管理器
│   │   ├── binance_derivatives_liquidation_manager.py
│   │   ├── okx_derivatives_liquidation_manager.py
│   │   └── liquidation_manager_factory.py
│   ├── lsr_managers/                 # 📈 多空持仓比例管理器
│   │   ├── binance_derivatives_lsr_manager.py
│   │   ├── okx_derivatives_lsr_manager.py
│   │   └── lsr_manager_factory.py
│   ├── vol_index_managers/           # 📊 波动率指数管理器
│   │   ├── base_vol_index_manager.py
│   │   ├── deribit_derivatives_vol_index_manager.py
│   │   └── vol_index_manager_factory.py
│   ├── nats_publisher.py             # 📡 NATS消息发布器 (支持JetStream)
│   ├── normalizer.py                 # 🔄 数据标准化器
│   ├── circuit_breaker.py            # 🛡️ 断路器
│   ├── retry_mechanism.py            # 🔄 重试机制
│   └── error_management/             # ❌ 错误管理系统
├── exchanges/                        # 🏪 交易所适配器
│   ├── base_websocket.py            # 基础WebSocket适配器
│   ├── binance_websocket.py         # Binance WebSocket
│   └── okx_websocket.py             # OKX WebSocket
├── tests/                           # 🧪 测试套件
│   ├── test_orderbook_*.py          # 订单簿测试
│   ├── test_trades_*.py             # 交易数据测试
│   ├── test_funding_rate_*.py       # 资金费率测试
│   ├── test_open_interest_*.py      # 未平仓量测试
│   ├── test_vol_index_*.py          # 波动率指数测试
│   └── test_unified_*.py            # 集成测试
├── tools/                           # 🔧 监控工具
│   ├── gap_monitor.py               # 序列号监控
│   ├── sequence_validation_analyzer.py # 序列号分析
│   └── analyze_memory.py            # 内存分析
├── requirements.txt                 # 📦 Python依赖
└── README.md                        # 📚 本文档
```

### 🔧 扩展开发

**添加新交易所**:
1. 继承 `BaseWebSocketManager` 创建WebSocket适配器
2. 继承 `BaseOrderBookManager` 创建订单簿管理器
3. 继承 `BaseTradesManager` 创建交易数据管理器
4. 在配置文件中添加交易所配置

**添加新数据类型**:
1. 在 `DataType` 枚举中添加新类型
2. 在 `Normalizer` 中添加标准化逻辑
3. 在相应管理器中添加处理逻辑

**自定义监控**:
1. 在 `tools/` 目录添加监控脚本
2. 使用 `structlog` 记录结构化日志
3. 集成到主启动流程中

## 📄 许可证

MIT License - 详见项目根目录LICENSE文件 