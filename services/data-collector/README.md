# 🚀 MarketPrism Data Collector
> 重要：以 scripts/manage_all.sh 为唯一运行总线索。本模块唯一入口：`services/data-collector/main.py`；唯一配置：`services/data-collector/config/collector/unified_data_collection.yaml`；唯一管理脚本：`services/data-collector/scripts/manage.sh`（由 manage_all 统一调用）。遇到端口冲突请先清理占用进程/容器，不要更改端口。


[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](docker-compose.unified.yml)
[![Python](https://img.shields.io/badge/python-3.12+-green.svg)](requirements.txt)
[![Status](https://img.shields.io/badge/status-production_ready-brightgreen.svg)](#)

**企业级数据收集器** - 支持多交易所实时数据收集，8种数据类型100%覆盖

## 📊 概览

MarketPrism Data Collector是一个高性能的加密货币市场数据收集服务，支持多交易所WebSocket连接，实现实时数据收集、标准化和发布。

### 🎯 核心功能

- **🔄 多交易所支持**: Binance、OKX、Deribit等主流交易所
- **📊 8种数据类型**: 订单簿、交易、资金费率、未平仓量、强平、LSR、波动率指数
- **⚡ 实时WebSocket**: 毫秒级数据收集，自动重连机制
- **🔧 数据标准化**: 统一数据格式，时间戳格式转换
- **📡 NATS发布**: 高性能消息发布，支持主题路由
- **🛡️ 生产级稳定性**: 断路器、重试机制、内存管理
- **📈 监控指标**: Prometheus指标，健康检查端点

## 🏗️ 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    Data Collector 架构                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │   Exchange  │    │ Data        │    │    NATS     │     │
│  │  WebSocket  │───▶│ Normalizer  │───▶│  Publisher  │     │
│  │  Adapters   │    │             │    │             │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │   Health    │    │   Memory    │    │   Circuit   │     │
│  │   Monitor   │    │   Manager   │    │   Breaker   │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 📈 支持的数据类型

| 数据类型 | 交易所支持 | 频率 | NATS主题格式 |
|---------|-----------|------|-------------|
| **Orderbooks** | Binance, OKX | 高频 | `orderbook.{exchange}.{market}.{symbol}` |
| **Trades** | Binance, OKX | 超高频 | `trade.{exchange}.{market}.{symbol}` |
| **Funding Rates** | Binance, OKX | 中频 | `funding_rate.{exchange}.{market}.{symbol}` |
| **Open Interests** | Binance, OKX | 低频 | `open_interest.{exchange}.{market}.{symbol}` |
| **Liquidations** | OKX | 事件驱动 | `liquidation.{exchange}.{market}.{symbol}` |
| **LSR Top Positions** | Binance, OKX | 低频 | `lsr_top_position.{exchange}.{market}.{symbol}` |
| **LSR All Accounts** | Binance, OKX | 低频 | `lsr_all_account.{exchange}.{market}.{symbol}` |
| **Volatility Indices** | Deribit | 低频 | `volatility_index.{exchange}.{market}.{symbol}` |

## 🚀 快速开始

### 前置要求

- Docker 20.10+
- Docker Compose 2.0+
- Python 3.12+ (本地开发)

### Docker部署 (推荐)

```bash
# 1. 确保外部 NATS（JetStream）已由 Docker 启动（仅外部模式）
cd ../message-broker
# 你的环境若是新版 Compose 插件请用：docker compose -f docker-compose.nats.yml up -d
sudo docker-compose -f docker-compose.nats.yml up -d

# 2. 启动 Data Collector（作为 NATS 客户端连接外部 NATS）
cd ../data-collector
sudo docker-compose -f docker-compose.unified.yml up -d

# 3. 验证启动状态
sudo docker logs marketprism-data-collector -f
```

#### 仅外部 NATS 模式与环境变量覆盖
- 本服务不托管/内嵌 NATS，始终以“客户端”身份连接外部 NATS（推荐用 message-broker 模块的 docker-compose.nats.yml 启动）
- 配置文件中 NATS 地址默认来自 YAML；若设置环境变量 MARKETPRISM_NATS_URL，将覆盖 YAML/默认地址
- Collector 仍兼容 `NATS_URL` 环境变量；若同时设置，以 `MARKETPRISM_NATS_URL` 为最终生效值

示例：
```bash
# 覆盖 Collector 的 NATS 连接地址
export MARKETPRISM_NATS_URL="nats://127.0.0.1:4222"
sudo docker-compose -f docker-compose.unified.yml up -d
```

### 本地开发

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动服务 (launcher模式)
python main.py launcher

# 3. 查看日志
tail -f logs/collector.log
```

## ⚙️ 配置说明

### 配置加载优先级（强烈建议遵循）

1) CLI 参数 --config=/path/to/config.yaml（容器由 entrypoint.sh 根据优先级解析并传入）
2) 环境变量 MARKETPRISM_UNIFIED_DATA_COLLECTION_CONFIG
3) 服务本地默认 /app/services/data-collector/config/collector/unified_data_collection.yaml
4) 全局默认 /app/config/collector/unified_data_collection.yaml

启动后，主程序会在 INFO 日志打印：config_source、env_config、cli_config、nats_env（最终使用的NATS地址），便于排障。

### 环境变量命名规范

- MARKETPRISM_NATS_URL（优先于配置文件与其他变量；若设置将覆盖 YAML/NATS_URL 中的 NATS 地址）
- NATS_URL（历史兼容变量；若同时设置 MARKETPRISM_NATS_URL 与 NATS_URL，则以 MARKETPRISM_NATS_URL 为准）
- API Keys：{EXCHANGE}_{MARKETTYPE}_API_KEY/_API_SECRET/_PASSPHRASE
  - 例如：OKX_DERIVATIVES_API_KEY、BINANCE_DERIVATIVES_API_SECRET
- 常用：LOG_LEVEL、ENVIRONMENT、DEBUG、HTTP_PROXY/HTTPS_PROXY/NO_PROXY


### 配置文件结构

```
config/
├── collector/                    # 数据收集器配置
│   ├── unified_data_collection.yaml
│   └── exchange_configs/
├── logging/                      # 日志配置
│   └── logging_config.yaml
└── nats/                        # NATS连接配置
    ├── nats-server.conf
    └── nats-server-docker.conf
```

### 环境变量

```bash
# 基础配置
PYTHONPATH=/app
LOG_LEVEL=INFO
PYTHONUNBUFFERED=1

# NATS连接
MARKETPRISM_NATS_URL=nats://localhost:4222  # 推荐；覆盖一切配置
# 兼容历史：NATS_URL 仍被识别，但若同时设置，以 MARKETPRISM_NATS_URL 为准
NATS_STREAM=MARKET_DATA

# 运行模式
COLLECTOR_MODE=launcher  # 完整数据收集系统

# 健康检查
HEALTH_CHECK_PORT=8086
METRICS_PORT=9093
```

### Docker配置

```yaml
# docker-compose.unified.yml 关键配置
services:
  data-collector:
    image: marketprism/data-collector:simplified
    container_name: marketprism-data-collector
    environment:
      - MARKETPRISM_NATS_URL=nats://localhost:4222
      - LOG_LEVEL=INFO
      - COLLECTOR_MODE=launcher
    ports:
      - "8086:8086"  # 健康检查
      - "9093:9093"  # Prometheus指标
    network_mode: host
    restart: unless-stopped
```

## 📊 监控和健康检查

### 健康检查端点

```bash
# 基础健康检查
curl http://localhost:8086/health

# 详细状态信息
curl http://localhost:8086/status

# 连接状态检查
curl http://localhost:8086/connections
```

### Prometheus指标

```bash
# 获取所有指标
curl http://localhost:9093/metrics
```

#### 新增：订单簿队列丢弃指标（drops）
- 指标名称：`marketprism_orderbook_queue_drops_total`
- 指标类型：Gauge
- 标签：`exchange`, `symbol`
- 含义：WebSocket 消息队列满时被丢弃的消息累计数量（自进程启动以来累计）

PromQL 示例：
- 查看当前累计值：
  - `marketprism_orderbook_queue_drops_total`
- 查看 5 分钟增长速率：
  - `rate(marketprism_orderbook_queue_drops_total[5m])`

Grafana 告警建议：
- 告警条件：`rate(marketprism_orderbook_queue_drops_total[5m]) > 1` 持续 5 分钟
- 告警级别：Warning（通常说明队列容量不足或消费速度跟不上）

排查建议：
- 查看日志：`services/data-collector/logs/collector.log` 中搜索 `入队失败：队列已满`
- 常见原因：
  - 市场极端活跃导致瞬时吞吐过高
  - 单symbol处理耗时异常（CPU紧张或下游阻塞）
  - 内部队列容量偏小（可通过配置 `internal_queue_maxsize` 调整，默认 20000）

### 日志监控

```bash
# Docker容器日志
sudo docker logs marketprism-data-collector -f

# 本地开发日志
tail -f logs/collector.log

# 错误日志过滤
sudo docker logs marketprism-data-collector 2>&1 | grep ERROR
```

## 🔧 故障排查

### 端口冲突处理策略（强制统一，不修改端口配置）

当 8086(health)/9093(metrics)/4222(NATS)/8222(NATS监控)/8123(ClickHouse) 等端口被占用时，统一策略是“终止占用该端口的旧进程或容器”，而不是修改服务端口。

标准流程：

```bash
# 1) 快速查看容器占用与端口映射
sudo docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

# 2) 查找端口占用（容器/进程）
netstat -tlnp | grep -E "(4222|8222|8123|8086|9093)" || true
# 或
ss -ltnp | grep -E "(4222|8222|8123|8086|9093)" || true

# 3) 停止/清理冲突容器
# 例如 Collector 与老实例冲突：
sudo docker stop marketprism-data-collector 2>/dev/null || true
sudo docker rm -f marketprism-data-collector 2>/dev/null || true
# 例如 NATS 与老实例冲突：
sudo docker stop marketprism-nats 2>/dev/null || true
sudo docker rm -f marketprism-nats 2>/dev/null || true

# 4) 清理本机残留进程（极端情况）
# 谨慎：仅清理我们已知的本项目进程名称
pkill -f 'services/data-collector/main.py' 2>/dev/null || true
pkill -f 'simple_hot_storage' 2>/dev/null || true

# 5) 复核端口是否释放
netstat -tlnp | grep -E "(4222|8222|8123|8086|9093)" || echo OK
```

建议脚本化（示例）：

```bash
# 一键清理常见端口占用（请先审阅后再执行）
PORTS="4222 8222 8123 8086 9093"
for p in $PORTS; do
  echo "== Port $p =="
  ss -ltnp | grep ":$p " || echo "free"
  # 常见容器名尝试性停止
  if [ "$p" = "4222" ] || [ "$p" = "8222" ]; then sudo docker stop marketprism-nats 2>/dev/null || true; fi
  if [ "$p" = "8086" ] || [ "$p" = "9093" ]; then sudo docker stop marketprism-data-collector 2>/dev/null || true; fi
  if [ "$p" = "8123" ]; then sudo docker stop marketprism-clickhouse-hot 2>/dev/null || true; fi
done
```

注意：请保持系统端口配置一致性与可预测性，不随意改动 compose/服务端口。

---

### 常见问题

#### 1. 容器启动失败
```bash
# 检查端口占用
netstat -tlnp | grep -E "(8086|9093)"

# 检查Docker网络
sudo docker network ls
sudo docker network inspect bridge
```

#### 2. WebSocket连接失败
```bash
# 检查网络连接
curl -I https://stream.binance.com:9443/ws/btcusdt@depth
curl -I https://ws.okx.com:8443/ws/v5/public

# 检查DNS解析
nslookup stream.binance.com
nslookup ws.okx.com
```

#### 3. NATS连接问题
```bash
# 检查NATS服务状态
curl http://localhost:8222/healthz

# 测试NATS连接
nats pub test.subject "hello world"
nats sub test.subject
```

#### 4. 数据收集停止
```bash
# 检查内存使用
sudo docker stats marketprism-data-collector

# 检查错误日志
sudo docker logs marketprism-data-collector --since 10m | grep ERROR

# 重启服务
sudo docker restart marketprism-data-collector
```

## 🔄 运维操作

### 启动和停止

```bash
# 启动服务
sudo docker-compose -f docker-compose.unified.yml up -d

# 停止服务
sudo docker-compose -f docker-compose.unified.yml down

# 重启服务
sudo docker-compose -f docker-compose.unified.yml restart

# 查看状态
sudo docker-compose -f docker-compose.unified.yml ps
```

### 日志管理

```bash
# 查看实时日志
sudo docker logs marketprism-data-collector -f

# 查看最近日志
sudo docker logs marketprism-data-collector --since 1h

# 导出日志
sudo docker logs marketprism-data-collector > collector_logs.txt
```

### 性能调优

```bash
# 检查资源使用
sudo docker stats marketprism-data-collector --no-stream

# 调整内存限制 (在docker-compose.yml中)
deploy:
  resources:
    limits:
      memory: 2G
    reservations:
      memory: 512M
```


## 🔄 WebSocket 合流/聚合流消息预解包标准化

为兼容 Binance Combined Streams 外层包裹结构，并保持对 OKX / Deribit 的严格向后兼容，数据收集器已在各 WebSocket 消息入口统一接入“预解包”逻辑。架构与规范详见：docs/architecture/ws_combined_stream_unwrap_standard.md。

- 公共工具函数：services/data-collector/exchanges/common/ws_message_utils.py
  - unwrap_combined_stream_message(message, inner_key="data")
- 接入原则（仅一处、尽早调用）：
  - 成交：各 *_trades_manager.py 的 _process_trade_message 开头（try 之前）
  - 订单簿：各 *_orderbook_manager.py / *_manager.py 的 process_websocket_message 开头（状态校验通过后）
  - 强平：各 *_liquidation_manager.py 的 _process_liquidation_message 开头（try 之前）
- 兼容性：
  - Binance：顶层 {"stream","data"} → 自动下钻到 data（生效）
  - OKX：{"arg":{...}, "data":[...]} → data 为 list，保持原样（no-op）
  - Deribit：JSON-RPC 顶层无 data → 保持原样（no-op）

### ✅ 测试用例

核心测试已覆盖工具函数、Binance 回归、OKX/Deribit 兼容：

```bash
source venv/bin/activate
pytest -q \
  services/data-collector/tests/test_ws_message_utils.py \
  services/data-collector/tests/test_binance_spot_unwrap_integration.py \
  services/data-collector/tests/test_binance_derivatives_liquidation_unwrap_integration.py \
  services/data-collector/tests/test_ws_unwrap_okx_compat.py \
  services/data-collector/tests/test_ws_unwrap_deribit_compat.py
```

### 🔬 在线快速验证（2–3 分钟抽样）

建议在本地已有 NATS 的前提下，启动采集器并用“核心 NATS 订阅”抽样验证（避免 JetStream Durable consumer 达上限）。

1) 启动采集器（单实例）：
```bash
source venv/bin/activate
python services/data-collector/main.py --mode launcher --log-level INFO
```

2) 使用 NATS CLI 做核心订阅抽样（建议至少 120–180 秒）：
```bash
# 可多开几个终端分别订阅，或在同一终端多 subject
nats sub 'trade.binance_spot.spot.>' 'trade.binance_derivatives.perpetual.>' \
         'orderbook.binance_spot.spot.>' 'orderbook.binance_derivatives.perpetual.>' \
         'liquidation.binance_derivatives.perpetual.>'

nats sub 'trade.okx_spot.spot.>' 'trade.okx_derivatives.perpetual.>' \
         'orderbook.okx_spot.spot.>' 'orderbook.okx_derivatives.perpetual.>' \
         'liquidation.okx_derivatives.perpetual.>'
```

3) 若需 JetStream 验证（计数、ACK 等），可用脚本（注意：可能受 Durable consumer 限额影响）：
```bash
# 受限参数：--stream MARKET_DATA --subjects <patterns...>
# 警告：若提示 maximum consumers limit reached，请改用上面的核心订阅命令
python services/message-broker/scripts/js_subscribe_validate.py \
  --stream MARKET_DATA --subjects \
  trade.binance_spot.spot.> trade.binance_derivatives.perpetual.> \
  orderbook.binance_spot.spot.> orderbook.binance_derivatives.perpetual.> \
  liquidation.binance_derivatives.perpetual.> \
  trade.okx_spot.spot.> trade.okx_derivatives.perpetual.> \
  orderbook.okx_spot.spot.> orderbook.okx_derivatives.perpetual.> \
  liquidation.okx_derivatives.perpetual.>
```

成功标准：
- 所有目标主题收到非零消息量（强平在短时间窗口内为 0 属正常）。
- 消息 JSON 可解析、结构完整，关键字段存在（symbol、timestamp、exchange）。
- 接收频率稳定，无明显丢包；订单簿偶发重建/延迟告警属正常自愈流程。

提示：
- 生产环境请避免创建多余 Durable consumer，定期清理无用 consumer；或改用核心订阅抽样。
- 保持单实例运行（已内置文件锁），JetStream 发布已启用 Msg-Id 幂等去重。

## 📚 开发指南

### 代码结构

```
services/data-collector/
├── main.py      # 主入口文件
├── collector/                     # 核心收集器模块
│   ├── normalizer.py             # 数据标准化
│   ├── nats_publisher.py         # NATS发布器
│   └── websocket_adapter.py      # WebSocket适配器
├── exchanges/                     # 交易所适配器
│   ├── binance_websocket.py      # Binance适配器
│   └── okx_websocket.py          # OKX适配器
└── config/                       # 配置文件
```

### 添加新交易所

1. 创建交易所适配器 `exchanges/new_exchange_websocket.py`
2. 实现WebSocket连接和数据解析
3. 在配置文件中添加交易所配置
4. 更新主入口文件的交易所列表

### 添加新数据类型

1. 在 `collector/data_types.py` 中定义数据结构
2. 在相应的交易所适配器中添加数据解析
3. 在 `collector/normalizer.py` 中添加标准化逻辑
4. 更新NATS主题配置

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](../../LICENSE) 文件了解详情