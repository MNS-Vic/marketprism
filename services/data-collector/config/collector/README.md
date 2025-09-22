# MarketPrism Data Collector 本地配置文件

本目录包含MarketPrism数据收集器的本地配置文件。

## 📁 文件结构

```
services/data-collector/config/
├── collector/
│   ├── README.md                       # 本文件
│   └── unified_data_collection.yaml    # 统一数据收集配置
├── nats/
│   ├── nats-server.conf                # NATS服务器配置文件 (生产环境)
│   ├── nats-server-docker.conf         # NATS服务器配置文件 (Docker环境)
│   └── docker-compose.nats.yml         # Docker Compose配置
└── logging/
    └── logging.yaml                    # 日志配置文件（可选）
```

## 🔄 配置迁移说明

此配置目录是从全局配置目录 `config/collector/` 迁移而来，实现了：
- ✅ 服务配置本地化
- ✅ 向后兼容性保持
- ✅ 配置文件完整性保证

## 🔧 NATS服务器配置

### 配置文件: `nats-server.conf`

这是MarketPrism专用的NATS服务器配置文件，包含以下特性：

#### ✅ 基础配置
- **监听地址**: 127.0.0.1:4222
- **监控端口**: 8222 (HTTP)
- **最大连接数**: 1000
- **最大消息负载**: 1MB

#### ✅ JetStream配置
- **存储目录**: `/var/lib/nats/jetstream`
- **最大内存**: 256MB
- **最大存储**: 10GB
- **同步间隔**: 2分钟

#### ✅ 日志配置
- **日志文件**: `/var/log/nats-server.log`
- **时间戳**: 启用
- **调试模式**: 关闭

### 部署配置

#### 🖥️ 传统部署 (直接在主机上)

使用项目提供的部署脚本：

```bash
# 进入data-collector目录
cd services/data-collector

# 运行部署脚本 (需要sudo权限)
sudo ./deploy-nats-config.sh
```

#### 🐳 Docker部署 (推荐)

使用Docker Compose部署：

```bash
# 进入data-collector目录
cd services/data-collector

# 运行Docker部署脚本
./deploy-nats-docker.sh
```

**Docker部署优势:**
- ✅ 环境隔离，避免依赖冲突
- ✅ 日志输出到stdout，便于收集
- ✅ 数据持久化到项目目录
- ✅ 易于扩展和管理
- ✅ 支持容器编排

部署脚本会自动：
1. 备份现有配置
2. 复制新配置到系统
3. 创建必要的目录和文件
4. 验证配置语法
5. 重启NATS服务
6. 检查服务状态

### 验证部署

#### 传统部署验证
```bash
# 检查NATS服务状态
systemctl status nats-server

# 检查JetStream状态
curl http://localhost:8222/jsz

# 查看日志
journalctl -u nats-server -f
```

#### Docker部署验证
```bash
# 检查容器状态
docker-compose -f config/collector/docker-compose.nats.yml ps

# 检查JetStream状态
curl http://localhost:8222/jsz

# 查看容器日志
docker-compose -f config/collector/docker-compose.nats.yml logs -f
```

## 📊 统一数据收集配置

### 配置文件: `unified_data_collection.yaml`

包含所有数据收集器的配置，支持：

#### 数据类型
- **订单簿数据** (orderbook)
- **交易数据** (trades)
- **资金费率** (funding_rate)
- **未平仓量** (open_interest)
- **强平数据** (liquidation)
- **多空持仓比例** (lsr_top_position, lsr_all_account)

#### 支持的交易所
- **Binance现货** (binance_spot)
- **Binance衍生品** (binance_derivatives)
- **OKX现货** (okx_spot)
- **OKX衍生品** (okx_derivatives)

## 🚀 使用方法

### 1. 启动NATS服务器

```bash
# 使用项目配置启动
sudo systemctl restart nats-server

# 验证启动
systemctl status nats-server
```

### 2. 启动数据收集器

```bash
# 进入data-collector目录
cd services/data-collector

# 激活虚拟环境
source ../../venv/bin/activate

# 启动统一收集器
python unified_collector_main.py
```

### 3. 监控运行状态

```bash
# NATS服务器状态
curl http://localhost:8222/varz

# JetStream状态
curl http://localhost:8222/jsz

# 查看流信息
curl http://localhost:8222/jsz | jq '.streams'
```

## 🔧 配置自定义

### 修改NATS配置

1. 编辑 `config/collector/nats-server.conf`
2. 运行部署脚本: `sudo ./deploy-nats-config.sh`

### 修改收集器配置

1. 编辑 `config/collector/unified_data_collection.yaml`
2. 重启收集器

## 📋 常见问题

### Q: JetStream不可用？
A: 检查存储目录权限和磁盘空间：
```bash
sudo chown -R nats:nats /var/lib/nats/jetstream
df -h /var/lib/nats/jetstream
```

### Q: 配置验证失败？
A: 使用NATS服务器验证配置：
```bash
nats-server -t -c config/collector/nats-server.conf
```

### Q: 服务启动失败？
A: 查看详细日志：
```bash
journalctl -u nats-server -f
sudo tail -f /var/log/nats-server.log
```

## 🔗 相关链接

- [NATS官方文档](https://docs.nats.io/)
- [JetStream指南](https://docs.nats.io/jetstream)
- [MarketPrism项目文档](../../README.md)


## ⏱️ 时间戳与更新序号（last_update_id）规范

本项目对“订单簿”数据统一采用如下规范：

- 时间戳字段
  - timestamp：事件时间（优先使用交易所消息自带的事件时间；缺失时才回退为采集时间）
  - collected_at：采集时间（由本地系统生成）
  - 两者格式：UTC 毫秒字符串，形如 "YYYY-MM-DD HH:MM:SS.mmm"，与 ClickHouse DateTime64(3, 'UTC') 完全兼容
- 交易所映射
  - Binance（现货/衍生）：使用消息中的 E（毫秒）作为事件时间
  - OKX（现货/衍生）：使用消息 data[0].ts 或 ts（毫秒）作为事件时间
- 归一化与发布
  - Normalizer 统一将 datetime 转为毫秒字符串；Publisher 仅做校验与缺失兜底

- last_update_id 字段（仅与深度更新序号相关，与时间无关）
  - OKX：使用 seqId/prevSeqId 作为 last_update_id/prev_update_id（如缺失则回退 ts）
  - Binance：按交易所定义，使用 lastUpdateId / U,u 序号族，不与时间戳混用

### 最小化验证步骤（本地）

1) 启动虚拟环境（推荐在仓库根目录）
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r services/data-collector/requirements.txt
```

2) 启动 NATS（JetStream）
```bash
cd services/message-broker/unified-nats
docker compose -f docker-compose.unified.yml up -d
```

3) 启动收集器（示例：OKX Spot / OKX Derivatives）
```bash
cd /home/ubuntu/marketprism
source .venv/bin/activate
python services/data-collector/unified_collector_main.py \
  --mode launcher \
  --config services/data-collector/config/collector/unified_data_collection.yaml \
  --exchange okx_spot --log-level INFO &
python services/data-collector/unified_collector_main.py \
  --mode launcher \
  --config services/data-collector/config/collector/unified_data_collection.yaml \
  --exchange okx_derivatives --log-level INFO &
```

4) 订阅验证（应看到 timestamp/collected_at 为毫秒 UTC；OKX 的 last_update_id 来自 seqId）
```bash
python - <<'PY'
import asyncio, json
from nats.aio.client import Client as NATS
async def main():
  n=NATS(); await n.connect(servers=["nats://127.0.0.1:4222"],connect_timeout=3)
  async def cb(msg):
    d=json.loads(msg.data.decode());
    keys=["exchange","market_type","symbol","last_update_id","prev_update_id","timestamp","collected_at"]
    print("MSG:", msg.subject, {k:d.get(k) for k in keys})
  await n.subscribe("orderbook.okx_spot.>", cb=cb)
  await n.subscribe("orderbook.okx_derivatives.>", cb=cb)
  await asyncio.sleep(20); await n.close()
import asyncio; asyncio.run(main())
PY
```

5) 清理进程
```bash
pkill -f "services/data-collector/unified_collector_main.py" || true
# 如需停止本地 NATS：
# cd services/message-broker/unified-nats && docker compose -f docker-compose.unified.yml down
```
