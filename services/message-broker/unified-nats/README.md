# MarketPrism统一NATS容器 - 简化架构方案

## 🎯 项目概述

MarketPrism统一NATS容器是将原有的"独立NATS容器 + Message Broker容器"架构简化为单一NATS容器的解决方案。该方案在保持所有核心功能的同时，显著降低了部署复杂度和资源占用。

### 🏗️ 架构简化

```
原架构：NATS容器 + Message Broker容器（2个容器，复杂依赖）
新架构：统一NATS容器（1个容器，集成所有功能）
```

### ✅ 功能保持

- **100%数据类型支持**：完整支持所有8种数据类型（包括liquidation强平数据）
- **完全兼容性**：与现有Data Collector无缝兼容，无需修改客户端代码
- **JetStream流管理**：自动创建和管理MARKET_DATA流，支持消息持久化
- **健康检查监控**：提供完整的健康检查和监控功能，支持容器编排
- **配置管理**：支持环境变量驱动的配置管理，适配不同环境
- **优雅启停**：支持优雅启动和停止，确保数据安全

### 🎯 适用场景

- **开发环境**：快速启动，资源占用少，便于调试
- **测试环境**：完整功能验证，支持自动化测试
- **生产环境**：高性能，高可用，支持大规模数据处理
- **容器编排**：支持Kubernetes、Docker Swarm等编排工具

## 📊 支持的数据类型（8种）

| # | 数据类型 | 主题模式 | 描述 | 支持交易所 | 数据特点 |
|---|---------|---------|------|-----------|----------|
| 1 | **orderbook** | `orderbook-data.>` | 订单簿深度数据 | 所有交易所 | 实时WebSocket，高频更新 |
| 2 | **trade** | `trade-data.>` | 实时成交数据 | 所有交易所 | 实时WebSocket，包含买卖方向 |
| 3 | **funding_rate** | `funding-rate-data.>` | 资金费率数据 | 衍生品交易所 | REST API，定期更新 |
| 4 | **open_interest** | `open-interest-data.>` | 未平仓量数据 | 衍生品交易所 | REST API，反映市场活跃度 |
| 5 | **lsr_top_position** | `lsr-top-position-data.>` | LSR顶级持仓比例 | 衍生品交易所 | REST API，大户持仓分析 |
| 6 | **lsr_all_account** | `lsr-all-account-data.>` | LSR全账户持仓比例 | 衍生品交易所 | REST API，市场情绪指标 |
| 7 | **volatility_index** | `volatility_index-data.>` | 波动率指数 | Deribit | REST API，市场波动性指标 |
| 8 | **liquidation** | `liquidation-data.>` | 强平订单数据 | 衍生品交易所 | 实时WebSocket，风险监控 |

### 📡 主题格式说明

所有主题都遵循统一的命名规范：
```
{data_type}-data.{exchange}.{market_type}.{symbol}
```

**示例：**
- `orderbook-data.binance_spot.spot.BTCUSDT` - Binance现货BTC/USDT订单簿
- `trade-data.okx_derivatives.perpetual.BTC-USDT-SWAP` - OKX永续合约BTC交易数据
- `liquidation-data.binance_derivatives.perpetual.ETHUSDT` - Binance永续合约ETH强平数据

## 🚀 快速开始

### 1. 环境准备

确保系统已安装：
- **Docker 20.10+** - 容器运行环境
- **Docker Compose 2.0+** - 容器编排工具
- **Python 3.8+** - 用于测试脚本和验证工具
- **curl/wget** - 用于健康检查（可选）

```bash
# 检查环境
docker --version
docker-compose --version
python3 --version
```

### 2. 配置环境变量

#### **方法1：使用默认配置（推荐新手）**
```bash
# 复制默认配置（适合开发和测试）
cp .env.unified .env
```

#### **方法2：自定义配置（推荐生产环境）**
```bash
# 复制配置模板
cp .env.unified .env

# 编辑配置文件
vim .env

# 主要配置项说明：
# JETSTREAM_MAX_MEMORY=1GB     # JetStream内存限制
# JETSTREAM_MAX_FILE=10GB      # JetStream文件存储限制
# STREAM_MAX_MSGS=1000000      # 流最大消息数
# NATS_DEBUG=false             # 是否启用调试日志
```

#### **方法3：环境特定配置**
```bash
# 开发环境
echo "NATS_DEBUG=true" >> .env
echo "JETSTREAM_MAX_MEMORY=512MB" >> .env

# 生产环境
echo "NATS_DEBUG=false" >> .env
echo "JETSTREAM_MAX_MEMORY=4GB" >> .env
echo "NATS_AUTH_ENABLED=true" >> .env
```

### 3. 构建和启动

#### **一键启动（推荐）**
```bash
# 构建并启动（后台运行）
sudo docker-compose -f docker-compose.unified.yml up -d --build

# 查看启动状态
sudo docker-compose -f docker-compose.unified.yml ps
```

#### **分步启动（用于调试）**
```bash
# 1. 构建镜像
sudo docker-compose -f docker-compose.unified.yml build

# 2. 启动服务
sudo docker-compose -f docker-compose.unified.yml up -d

# 3. 查看实时日志
sudo docker-compose -f docker-compose.unified.yml logs -f nats-unified
```

### 4. 验证部署

#### **快速验证**
```bash
# 检查容器状态
sudo docker-compose -f docker-compose.unified.yml ps

# 检查端口连通性
curl http://localhost:8222/healthz
nc -zv localhost 4222
```

#### **完整验证**
```bash
# 安装Python测试依赖
python3 -m venv test_env
source test_env/bin/activate
pip install nats-py aiohttp

# 运行完整部署测试
python test_unified_deployment.py --detailed

# 检查流状态
sudo docker exec -it marketprism-nats-unified python3 /app/scripts/check_streams.py --detailed

# 运行健康检查
sudo docker exec -it marketprism-nats-unified /app/scripts/health_check.sh full
```

### 5. 连接验证

#### **验证Data Collector连接**
```bash
# 进入Data Collector目录
cd ../../data-collector

# 测试NATS连接
python3 -c "
import asyncio
import nats

async def test():
    nc = await nats.connect('nats://localhost:4222')
    print('✅ NATS连接成功')
    await nc.close()

asyncio.run(test())
"
```

## 🔧 详细配置说明

### 📁 配置文件结构

```
services/message-broker/unified-nats/
├── .env                           # 🔧 主配置文件（运行时使用）
├── .env.unified                   # 📋 配置模板（默认值和示例）
├── docker-compose.unified.yml     # 🐳 Docker编排配置
├── Dockerfile.unified             # 🐳 容器构建配置
└── scripts/
    ├── config_renderer.py         # 🔄 NATS配置生成器
    ├── enhanced_jetstream_init.py  # 🔄 JetStream流初始化器
    ├── check_streams.py           # 🔍 流状态检查工具
    └── health_check.sh            # 🏥 健康检查脚本
```

### 🎯 统一入口和配置

#### **统一配置文件：`.env`**
所有配置都集中在一个文件中，支持环境变量覆盖：

```bash
# ==================== 基础服务配置 ====================
NATS_SERVER_NAME=marketprism-nats-unified  # 服务器名称
NATS_HOST=0.0.0.0                          # 监听地址
NATS_PORT=4222                             # 客户端连接端口
NATS_HTTP_PORT=8222                        # HTTP监控端口
NATS_CLUSTER_PORT=6222                     # 集群端口（可选）

# ==================== JetStream配置 ====================
JETSTREAM_ENABLED=true                     # 启用JetStream持久化
JETSTREAM_STORE_DIR=/data/jetstream        # 数据存储目录
JETSTREAM_MAX_MEMORY=1GB                   # 内存存储限制
JETSTREAM_MAX_FILE=10GB                    # 文件存储限制

# ==================== 流配置 ====================
STREAM_NAME=MARKET_DATA                    # 主数据流名称
STREAM_MAX_CONSUMERS=50                    # 最大消费者数
STREAM_MAX_MSGS=1000000                    # 最大消息数
STREAM_MAX_BYTES=1073741824               # 最大存储字节数（1GB）
STREAM_MAX_AGE=7200                       # 消息保留时间（秒）

# ==================== 监控配置 ====================
MONITORING_ENABLED=true                   # 启用监控
HEALTH_CHECK_ENABLED=true                 # 启用健康检查
HEALTH_CHECK_INTERVAL=60                  # 健康检查间隔（秒）

# ==================== 日志配置 ====================
NATS_DEBUG=false                          # 调试日志
NATS_TRACE=false                          # 跟踪日志
NATS_LOG_FILE=/var/log/nats/nats.log     # 日志文件路径
```

#### **统一入口脚本：`unified_entrypoint.sh`**
容器启动的唯一入口，负责完整的启动流程：

1. **环境验证** - 检查必需的命令和环境变量
2. **目录创建** - 创建数据和日志目录
3. **配置生成** - 根据环境变量生成NATS配置文件
4. **NATS启动** - 启动NATS服务器
5. **JetStream初始化** - 创建和配置所有8种数据类型的流
6. **健康监控** - 启动后台健康检查
7. **优雅停止** - 处理停止信号，确保数据安全

### 🌍 环境特定配置

#### **开发环境配置**
```bash
# 复制基础配置
cp .env.unified .env

# 开发环境优化
cat >> .env << EOF
# 开发环境配置
NATS_DEBUG=true
JETSTREAM_MAX_MEMORY=512MB
JETSTREAM_MAX_FILE=2GB
STREAM_MAX_MSGS=100000
HEALTH_CHECK_INTERVAL=30
EOF
```

#### **测试环境配置**
```bash
# 测试环境配置
cat >> .env << EOF
# 测试环境配置
NATS_DEBUG=true
NATS_TRACE=false
JETSTREAM_MAX_MEMORY=1GB
JETSTREAM_MAX_FILE=5GB
STREAM_MAX_MSGS=500000
HEALTH_CHECK_INTERVAL=15
EOF
```

#### **生产环境配置**
```bash
# 生产环境配置
cat >> .env << EOF
# 生产环境配置
NATS_DEBUG=false
NATS_TRACE=false
JETSTREAM_MAX_MEMORY=4GB
JETSTREAM_MAX_FILE=50GB
STREAM_MAX_MSGS=10000000
STREAM_MAX_BYTES=10737418240
HEALTH_CHECK_INTERVAL=60

# 生产环境安全配置
NATS_AUTH_ENABLED=true
NATS_AUTH_USERNAME=marketprism
NATS_AUTH_PASSWORD=your_secure_password_here

# 生产环境TLS配置（可选）
NATS_TLS_ENABLED=true
NATS_TLS_CERT=/app/certs/server.crt
NATS_TLS_KEY=/app/certs/server.key
EOF
```

### 📊 配置验证和调试

#### **查看当前配置**
```bash
# 查看容器环境变量
sudo docker exec -it marketprism-nats-unified env | grep NATS | sort

# 查看生成的NATS配置文件
sudo docker exec -it marketprism-nats-unified cat /app/nats.conf

# 查看JetStream配置
sudo docker exec -it marketprism-nats-unified python3 /app/scripts/check_streams.py --json
```

#### **配置问题排查**
```bash
# 检查配置文件语法
docker-compose -f docker-compose.unified.yml config

# 查看启动日志
sudo docker logs marketprism-nats-unified

# 运行配置验证
sudo docker exec -it marketprism-nats-unified python3 /app/scripts/config_renderer.py --validate
```

## 🏥 健康检查

### 内置健康检查

容器提供多层级的健康检查：

```bash
# 快速检查（Docker健康检查）
./scripts/health_check.sh quick

# 完整检查
./scripts/health_check.sh full

# 特定检查
./scripts/health_check.sh jetstream
./scripts/health_check.sh stream
```

### HTTP监控端点

- **健康检查**: `http://localhost:8222/healthz`
- **JetStream状态**: `http://localhost:8222/jsz`
- **服务器信息**: `http://localhost:8222/varz`
- **连接信息**: `http://localhost:8222/connz`

## 🧪 测试验证

### 功能测试

```bash
# 完整功能测试
python test_unified_deployment.py --detailed

# JSON格式输出
python test_unified_deployment.py --json

# 静默模式
python test_unified_deployment.py --quiet
```

### 流状态检查

```bash
# 检查流状态
python scripts/check_streams.py --detailed

# 获取流统计
python scripts/check_streams.py --stats --json
```

### JetStream初始化

```bash
# 手动初始化JetStream
python scripts/enhanced_jetstream_init.py

# 健康检查
python scripts/enhanced_jetstream_init.py --health-check

# 显示统计信息
python scripts/enhanced_jetstream_init.py --stats
```

## 📁 文件结构

```
unified-nats/
├── Dockerfile.unified              # 统一容器Dockerfile
├── docker-compose.unified.yml      # Docker Compose配置
├── .env.unified                    # 环境变量模板
├── unified_entrypoint.sh           # 统一启动脚本
├── scripts/
│   ├── enhanced_jetstream_init.py  # JetStream初始化脚本
│   ├── config_renderer.py          # 配置渲染器
│   ├── check_streams.py            # 流状态检查
│   └── health_check.sh             # 健康检查脚本
├── test_unified_deployment.py      # 部署测试脚本
└── README.md                       # 本文档
```

## 🔄 与Data Collector的兼容性

### 连接配置

Data Collector无需修改，继续使用相同的连接配置：

```yaml
# unified_data_collection.yaml
nats:
  enabled: true
  servers: ["nats://localhost:4222"]
  client_name: "unified-collector"
```

### 主题格式

所有主题格式保持不变：

```
orderbook-data.{exchange}.{market_type}.{symbol}
trade-data.{exchange}.{market_type}.{symbol}
funding-rate-data.{exchange}.{market_type}.{symbol}
# ... 其他数据类型
```

## 🚨 故障排除

### 常见问题

#### 1. 容器启动失败

```bash
# 检查日志
docker-compose -f docker-compose.unified.yml logs nats-unified

# 检查端口占用
netstat -tlnp | grep :4222
netstat -tlnp | grep :8222
```

#### 2. JetStream初始化失败

```bash
# 手动初始化
docker exec -it marketprism-nats-unified python3 /app/scripts/enhanced_jetstream_init.py

# 检查存储目录权限
docker exec -it marketprism-nats-unified ls -la /data/jetstream
```

#### 3. 健康检查失败

```bash
# 详细健康检查
docker exec -it marketprism-nats-unified /app/scripts/health_check.sh full

# 检查NATS连通性
curl http://localhost:8222/healthz
```

### 日志分析

```bash
# 实时日志
docker-compose -f docker-compose.unified.yml logs -f nats-unified

# 过滤错误日志
docker-compose -f docker-compose.unified.yml logs nats-unified | grep ERROR

# 检查JetStream日志
docker exec -it marketprism-nats-unified tail -f /var/log/nats/nats.log
```

## 📈 性能优化

### 资源配置

根据环境调整资源限制：

```yaml
# docker-compose.unified.yml
deploy:
  resources:
    limits:
      memory: 4G      # 生产环境
      cpus: '2.0'
    reservations:
      memory: 1G      # 最小保留
      cpus: '0.5'
```

### JetStream优化

```bash
# 大容量环境
JETSTREAM_MAX_MEMORY=8GB
JETSTREAM_MAX_FILE=100GB
STREAM_MAX_MSGS=50000000

# 高频环境
STREAM_MAX_CONSUMERS=200
NATS_MAX_CONNECTIONS=5000
```

## 🔒 安全配置

### 认证配置

```bash
# 启用认证
NATS_AUTH_ENABLED=true
NATS_AUTH_USERNAME=marketprism
NATS_AUTH_PASSWORD=your_secure_password

# 或使用令牌认证
NATS_AUTH_TOKEN=your_secure_token
```

### TLS配置

```bash
# 启用TLS
NATS_TLS_ENABLED=true
NATS_TLS_CERT=/app/certs/server.crt
NATS_TLS_KEY=/app/certs/server.key
NATS_TLS_CA=/app/certs/ca.crt
```

## 📊 监控集成

### Prometheus监控

```bash
# 启用Prometheus指标
PROMETHEUS_ENABLED=true
PROMETHEUS_PORT=7777
```

### 外部监控

```bash
# 告警配置
ALERT_WEBHOOK_URL=https://your-webhook-url
ALERT_EMAIL=admin@yourcompany.com
```

## 🔄 迁移指南

### 从原架构迁移

1. **停止原有服务**
   ```bash
   docker-compose down
   ```

2. **备份数据**
   ```bash
   docker run --rm -v nats_data:/data -v $(pwd):/backup alpine tar czf /backup/nats_backup.tar.gz /data
   ```

3. **部署新架构**
   ```bash
   docker-compose -f docker-compose.unified.yml up -d
   ```

4. **验证功能**
   ```bash
   python test_unified_deployment.py --detailed
   ```

### 回滚策略

如需回滚到原架构：

1. **停止统一容器**
2. **恢复数据备份**
3. **启动原有架构**
4. **验证功能正常**

## 📞 支持和贡献

### 问题报告

如遇到问题，请提供：
- 环境信息（Docker版本、系统版本）
- 配置文件内容
- 错误日志
- 复现步骤

### 贡献指南

欢迎提交：
- Bug修复
- 功能改进
- 文档完善
- 测试用例

## 📚 完整使用指南

### 🎯 新用户快速上手

#### **第一次使用（5分钟快速启动）**
```bash
# 1. 进入项目目录
cd services/message-broker/unified-nats

# 2. 使用默认配置
cp .env.unified .env

# 3. 一键启动
sudo docker-compose -f docker-compose.unified.yml up -d --build

# 4. 验证启动
curl http://localhost:8222/healthz
# 应该返回: OK

# 5. 查看启动日志
sudo docker logs marketprism-nats-unified
```

#### **连接Data Collector**
```bash
# 进入Data Collector目录
cd ../../data-collector

# 启动数据收集（使用现有配置）
python unified_collector_main.py --config ../../config/collector/unified_data_collection.yaml
```

### 🔧 常用管理命令

#### **服务管理**
```bash
# 启动服务
sudo docker-compose -f docker-compose.unified.yml up -d

# 停止服务
sudo docker-compose -f docker-compose.unified.yml down

# 重启服务
sudo docker-compose -f docker-compose.unified.yml restart

# 查看服务状态
sudo docker-compose -f docker-compose.unified.yml ps

# 查看实时日志
sudo docker-compose -f docker-compose.unified.yml logs -f nats-unified
```

#### **健康检查和监控**
```bash
# 快速健康检查
curl http://localhost:8222/healthz

# 详细健康检查
sudo docker exec -it marketprism-nats-unified /app/scripts/health_check.sh full

# 查看JetStream状态
curl http://localhost:8222/jsz | jq

# 查看服务器信息
curl http://localhost:8222/varz | jq

# 检查流状态
sudo docker exec -it marketprism-nats-unified python3 /app/scripts/check_streams.py --detailed
```

#### **配置管理**
```bash
# 查看当前配置
sudo docker exec -it marketprism-nats-unified env | grep NATS | sort

# 查看生成的NATS配置文件
sudo docker exec -it marketprism-nats-unified cat /app/nats.conf

# 验证配置语法
docker-compose -f docker-compose.unified.yml config
```

### 🐛 故障排查指南

#### **常见问题和解决方案**

**问题1：容器启动失败**
```bash
# 查看详细错误日志
sudo docker logs marketprism-nats-unified

# 检查端口占用
sudo netstat -tlnp | grep :4222
sudo netstat -tlnp | grep :8222

# 解决方案：停止占用端口的进程或修改端口配置
```

**问题2：JetStream初始化失败**
```bash
# 手动运行初始化
sudo docker exec -it marketprism-nats-unified python3 /app/scripts/enhanced_jetstream_init.py

# 检查存储目录权限
sudo docker exec -it marketprism-nats-unified ls -la /data/jetstream

# 解决方案：确保存储目录有写权限
```

**问题3：Data Collector连接失败**
```bash
# 测试NATS连接
python3 -c "
import asyncio
import nats

async def test():
    try:
        nc = await nats.connect('nats://localhost:4222', connect_timeout=5)
        print('✅ 连接成功')
        await nc.close()
    except Exception as e:
        print(f'❌ 连接失败: {e}')

asyncio.run(test())
"

# 解决方案：检查防火墙设置和网络配置
```

**问题4：性能问题**
```bash
# 查看资源使用情况
sudo docker stats marketprism-nats-unified

# 查看JetStream统计
curl http://localhost:8222/jsz | jq '.memory, .storage'

# 解决方案：调整内存和存储限制
```

### 📊 监控和维护

#### **日常监控检查项**
```bash
# 1. 服务健康状态
curl -s http://localhost:8222/healthz

# 2. JetStream存储使用情况
curl -s http://localhost:8222/jsz | jq '.storage'

# 3. 消息处理统计
curl -s http://localhost:8222/jsz | jq '.messages'

# 4. 连接数统计
curl -s http://localhost:8222/connz | jq '.num_connections'
```

#### **定期维护任务**
```bash
# 每日：检查日志大小
sudo docker exec -it marketprism-nats-unified du -sh /var/log/nats/

# 每周：清理旧日志（如果需要）
sudo docker exec -it marketprism-nats-unified find /var/log/nats/ -name "*.log" -mtime +7 -delete

# 每月：检查存储使用情况
sudo docker exec -it marketprism-nats-unified df -h /data/jetstream
```

### 🚀 性能优化建议

#### **生产环境优化**
```bash
# 1. 增加资源限制
echo "JETSTREAM_MAX_MEMORY=4GB" >> .env
echo "JETSTREAM_MAX_FILE=50GB" >> .env
echo "STREAM_MAX_MSGS=10000000" >> .env

# 2. 启用认证
echo "NATS_AUTH_ENABLED=true" >> .env
echo "NATS_AUTH_USERNAME=marketprism" >> .env
echo "NATS_AUTH_PASSWORD=your_secure_password" >> .env

# 3. 优化连接数
echo "NATS_MAX_CONNECTIONS=5000" >> .env

# 4. 重启应用配置
sudo docker-compose -f docker-compose.unified.yml down
sudo docker-compose -f docker-compose.unified.yml up -d
```

### 📞 获取帮助

#### **文档和资源**
- **项目文档**: 查看项目根目录的README.md
- **NATS官方文档**: https://docs.nats.io/
- **JetStream指南**: https://docs.nats.io/jetstream

#### **问题报告**
如遇到问题，请提供以下信息：
1. **环境信息**: `docker --version`, `docker-compose --version`
2. **配置文件**: `.env`文件内容（隐藏敏感信息）
3. **错误日志**: `sudo docker logs marketprism-nats-unified`
4. **系统状态**: `sudo docker stats marketprism-nats-unified`

---

**MarketPrism Team** - 专业的加密货币市场数据收集和分析平台

🎯 **统一NATS容器特性**：
- ✅ 8种数据类型完整支持
- ✅ 与Data Collector完全兼容
- ✅ 环境变量驱动配置
- ✅ 容器化部署最佳实践
- ✅ 详细的健康检查和监控
- ✅ 优雅启停和错误处理
