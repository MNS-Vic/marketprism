# MarketPrism NATS自动推送功能配置指南

## 📋 概述

本文档详细说明了MarketPrism Data-Collector的NATS自动推送功能配置，包括已修复的问题、版本要求和部署指南。

## 🎯 功能状态

- ✅ **NATS自动推送功能**: 完全激活
- ✅ **版本兼容性**: 已修复asyncio兼容性问题
- ✅ **多交易所支持**: Binance、OKX、Deribit
- ✅ **实时数据流**: orderbook、trade、volatility-index
- ✅ **生产就绪**: 100%验证通过

## 🔧 关键配置

### 1. 依赖版本要求

```txt
# 关键依赖版本（已修复兼容性问题）
nats-py==2.2.0          # 固定版本，解决asyncio兼容性
aiohttp>=3.8.0
structlog>=21.0.0
pyyaml>=5.4.0
```

**重要**: `nats-py`必须使用2.2.0版本，更高版本存在asyncio兼容性问题。

### 2. NATS服务器配置

```yaml
# docker-compose.yml
nats:
  image: nats:2-alpine
  container_name: marketprism-nats
  ports:
    - "4222:4222"    # NATS协议端口
    - "8222:8222"    # HTTP监控端口
  command: ["-js", "-m", "8222"]
  healthcheck:
    test: ["CMD-SHELL", "wget --quiet --tries=1 --spider http://localhost:8222/healthz || exit 1"]
    interval: 10s
    timeout: 5s
    retries: 3
```

### 3. Data Collector NATS配置

```yaml
# config/data_collection_config.yml
data_collection:
  nats_streaming:
    enabled: true
    servers: 
      - "nats://localhost:4222"
    connection:
      name: "data-collector"
      max_reconnect_attempts: 5
      reconnect_time_wait: 2
    subjects:
      orderbook: "orderbook.{exchange}.{symbol}"
      trade: "trade.{exchange}.{symbol}"
      volatility_index: "volatility-index.{exchange}.{symbol}"
```

### 4. Docker环境变量

```yaml
# docker-compose.yml - data-collector服务
environment:
  - NATS_URL=nats://nats:4222
  - LOG_LEVEL=INFO
depends_on:
  nats:
    condition: service_healthy
```

## 🚀 部署指南

### 1. 一键部署

```bash
# 使用统一管理入口
./scripts/manage_all.sh start

# 脚本会自动：
# - 检查nats-py版本并修复
# - 启动NATS服务器
# - 启动Data Collector
# - 验证NATS推送功能
```

### 2. 手动部署

```bash
# 1. 检查依赖
python scripts/check_dependencies.py --auto-fix

# 2. 启动NATS
docker-compose up -d nats

# 3. 验证NATS连接
curl http://localhost:8222/varz

# 4. 启动Data Collector
source venv/bin/activate
python services/data-collector/main.py

# 5. 验证NATS推送
python scripts/post_deployment_verification.py
```

### 3. Docker部署

```bash
# 构建镜像（包含固定的nats-py版本）
docker-compose build data-collector

# 启动服务
docker-compose up -d nats data-collector

# 验证功能
docker-compose exec data-collector python scripts/post_deployment_verification.py
```

## 🔍 验证方法

### 1. 快速验证

```bash
# 检查NATS服务器
curl http://localhost:8222/varz | jq .version

# 检查Data Collector状态
curl http://localhost:8084/api/v1/status | jq .data.status

# 验证NATS推送（30秒测试）
cd services/data-collector
source collector_env/bin/activate
python final_complete_verification.py
```

### 2. 详细验证

```bash
# 运行完整的部署后验证
python scripts/post_deployment_verification.py

# 运行集成测试
pytest tests/integration/test_nats_auto_push.py -v
```

### 3. 实时监控

```bash
# 监控NATS消息流
nats sub "orderbook.>"

# 监控Data Collector日志
tail -f /tmp/data-collector.log

# 检查NATS统计
curl http://localhost:8222/varz | jq '.in_msgs, .out_msgs'
```

## 🐛 故障排除

### 1. nats-py版本问题

**症状**: `Queue.__init__() got an unexpected keyword argument 'loop'`

**解决方案**:
```bash
pip install nats-py==2.2.0
```

### 2. NATS连接失败

**症状**: NATS客户端连接失败

**检查步骤**:
```bash
# 1. 检查NATS服务器状态
curl http://localhost:8222/varz

# 2. 检查端口占用
netstat -tlnp | grep 4222

# 3. 重启NATS服务
docker-compose restart nats
```

### 3. 无NATS消息

**症状**: 验证脚本收不到消息

**检查步骤**:
```bash
# 1. 检查Data Collector状态
curl http://localhost:8084/api/v1/status

# 2. 检查数据收集统计
curl http://localhost:8084/api/v1/status | jq .data.collection_stats

# 3. 检查日志
tail -f /tmp/data-collector.log | grep -i nats
```

## 📊 性能指标

### 正常运行指标

- **NATS消息频率**: 0.2-2.0 条/秒
- **Data Collector收集**: >0 次/分钟
- **NATS连接**: 稳定连接，无频繁重连
- **内存使用**: <500MB
- **CPU使用**: <10%

### 监控命令

```bash
# NATS统计
curl -s http://localhost:8222/varz | jq '{version, connections, in_msgs, out_msgs}'

# Data Collector统计
curl -s http://localhost:8084/api/v1/status | jq .data.collection_stats

# 系统资源
docker stats marketprism-data-collector
```

## 🔄 版本升级

### 升级nats-py（谨慎）

```bash
# 1. 备份当前环境
pip freeze > backup_requirements.txt

# 2. 测试新版本
pip install nats-py==2.3.0  # 示例

# 3. 运行验证
python scripts/post_deployment_verification.py

# 4. 如果失败，回滚
pip install nats-py==2.2.0
```

### 升级其他依赖

```bash
# 安全升级其他依赖
pip install --upgrade aiohttp structlog pyyaml

# 验证功能
python scripts/check_dependencies.py
```

## 📝 配置文件模板

### requirements.txt
```txt
# MarketPrism Data-Collector Dependencies
aiohttp>=3.8.0
structlog>=21.0.0
nats-py==2.2.0  # FIXED VERSION - DO NOT UPGRADE
pyyaml>=5.4.0
pandas>=1.3.0
numpy>=1.21.0
websockets>=9.0.0
```

### .env
```env
# NATS Configuration
NATS_URL=nats://localhost:4222
NATS_MONITOR_URL=http://localhost:8222

# Data Collector Configuration
DATA_COLLECTOR_PORT=8084
LOG_LEVEL=INFO
```

## 🎉 成功标志

部署成功的标志：

1. ✅ `curl http://localhost:8222/varz` 返回NATS版本信息
2. ✅ `curl http://localhost:8084/api/v1/status` 返回running状态
3. ✅ 验证脚本收到NATS消息
4. ✅ Data Collector日志显示"NATS客户端连接成功"
5. ✅ 无错误日志或异常

## 📞 支持

如果遇到问题：

1. 运行诊断脚本: `python scripts/check_dependencies.py`
2. 查看详细日志: `tail -f /tmp/data-collector.log`
3. 运行验证脚本: `python scripts/post_deployment_verification.py`
4. 检查配置文件: 确保NATS配置正确

---

**最后更新**: 2024-12-19  
**版本**: 1.0  
**状态**: 生产就绪 ✅
