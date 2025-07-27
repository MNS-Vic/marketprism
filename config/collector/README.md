# MarketPrism Collector 配置文件

本目录包含MarketPrism数据收集器的所有配置文件。

## 📁 文件结构

```
config/collector/
├── README.md                           # 本文件
├── nats-server.conf                    # NATS服务器配置文件 (生产环境)
├── nats-server-docker.conf             # NATS服务器配置文件 (Docker环境)
├── docker-compose.nats.yml             # Docker Compose配置
└── unified_data_collection.yaml        # 统一数据收集配置
```

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
