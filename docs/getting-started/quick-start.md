# MarketPrism 快速开始指南

> 最后更新：2025-01-27

## 🚀 5分钟快速启动

### 环境要求

- Python 3.12+
- Docker & Docker Compose
- 至少 4GB 可用内存
- 至少 10GB 可用磁盘空间

### 快速启动步骤

#### 1. 克隆项目
```bash
git clone https://github.com/your-org/marketprism.git
cd marketprism
```

#### 2. 启动基础设施
```bash
# 启动 NATS 和 ClickHouse
docker-compose -f docker-compose.infrastructure.yml up -d
```

#### 3. 配置代理（本地开发必需）
```bash
# 设置代理环境变量（访问外部交易所API必需）
export http_proxy=http://127.0.0.1:1087
export https_proxy=http://127.0.0.1:1087
export ALL_PROXY=socks5://127.0.0.1:1080

# 一键设置命令
export http_proxy=http://127.0.0.1:1087;export https_proxy=http://127.0.0.1:1087;export ALL_PROXY=socks5://127.0.0.1:1080
```

> 💡 **重要提示**：本地开发时必须设置代理才能访问Binance、OKX、Deribit等外部交易所API。

#### 4. 安装依赖
```bash
# 创建虚拟环境
python -m venv venv_tdd
source venv_tdd/bin/activate  # Linux/Mac
# 或 venv_tdd\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

#### 5. 启动数据收集器
```bash
# 方式1: 使用Docker Compose (推荐)
docker-compose up -d python-collector

# 方式2: 本地开发模式
cd services/python-collector
python -m src.marketprism_collector.main
```

#### 6. 验证运行状态
```bash
# 检查健康状态
curl http://localhost:8080/health

# 查看监控指标
curl http://localhost:8080/metrics

# 查看调度器状态
curl http://localhost:8080/scheduler
```

## 📊 验证数据流

### 检查 NATS 消息
```bash
# 查看消息流状态
docker exec -it marketprism_nats_1 nats stream ls

# 查看具体流信息
docker exec -it marketprism_nats_1 nats stream info MARKET_DATA
```

### 检查 ClickHouse 数据
```bash
# 连接 ClickHouse
docker exec -it marketprism_clickhouse_1 clickhouse-client

# 查看数据表
SHOW TABLES FROM marketprism;

# 查看交易数据
SELECT count() FROM marketprism.trades;
SELECT * FROM marketprism.trades LIMIT 5;
```

## 🔧 基础配置

### 环境变量配置

创建 `.env` 文件：
```bash
# 复制示例配置
cp .env.development .env
```

主要配置项：
```env
# NATS 配置
NATS_URL=nats://localhost:4222

# ClickHouse 配置
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_DATABASE=marketprism

# 收集器配置
COLLECTOR_HTTP_PORT=8080
COLLECTOR_ENABLE_SCHEDULER=true
COLLECTOR_USE_REAL_EXCHANGES=true

# 日志配置
LOG_LEVEL=INFO
```

### 交易所配置

编辑 `config/exchanges/` 目录下的配置文件：

```yaml
# config/exchanges/binance_spot.yaml
exchange: "binance"
market_type: "spot"
enabled: true
symbols:
  - "BTC/USDT"
  - "ETH/USDT"
data_types:
  - "trade"
  - "orderbook"
  - "ticker"
```

## 📈 监控和管理

### 健康检查端点

- `GET /health` - 系统健康状态
- `GET /metrics` - Prometheus 指标
- `GET /status` - 详细系统状态
- `GET /scheduler` - 任务调度状态

### 监控指标示例

```bash
# 查看消息处理速度
curl -s http://localhost:8080/metrics | grep marketprism_messages_per_second

# 查看错误率
curl -s http://localhost:8080/metrics | grep marketprism_error_rate

# 查看内存使用
curl -s http://localhost:8080/metrics | grep marketprism_memory_usage
```

## 🛠️ 常见问题

### 1. 服务无法启动

**检查 Docker 服务**:
```bash
docker ps
docker-compose logs
```

**检查端口占用**:
```bash
lsof -i :8080  # 收集器端口
lsof -i :4222  # NATS 端口
lsof -i :8123  # ClickHouse 端口
```

### 2. 数据未正确传输

**检查 NATS 连接**:
```bash
docker exec -it marketprism_nats_1 nats stream ls
```

**检查 ClickHouse 连接**:
```bash
docker exec -it marketprism_clickhouse_1 clickhouse-client --query "SELECT 1"
```

### 3. 性能问题

**查看系统资源**:
```bash
# 内存使用
docker stats

# 日志分析
docker-compose logs python-collector | tail -100
```

## 🔄 开发模式

### 本地开发环境

```bash
# 仅启动基础设施
docker-compose -f docker-compose.infrastructure.yml up -d

# 本地运行收集器
cd services/python-collector
export PYTHONPATH=$PWD/src:$PYTHONPATH
python -m marketprism_collector.main
```

### 代码热重载

```bash
# 使用开发配置
docker-compose -f docker-compose.dev.yml up -d
```

### 测试运行

```bash
# 运行测试套件
pytest tests/

# 运行集成测试
pytest tests/integration/

# 生成覆盖率报告
pytest --cov=src --cov-report=html
```

## 📚 下一步

### 深入了解
- [架构概述](../architecture/overview.md) - 了解系统架构
- [部署指南](../deployment/) - 生产环境部署
- [开发文档](../development/) - 开发规范和指南

### 高级配置
- [监控配置](../deployment/monitoring.md) - 配置 Grafana 仪表板
- [性能调优](../operations/performance-tuning.md) - 系统性能优化
- [故障排除](../operations/troubleshooting.md) - 常见问题解决

### 贡献代码
- [贡献指南](../development/contributing.md) - 如何贡献代码
- [编码规范](../development/coding-standards.md) - 代码规范
- [测试指南](../development/testing.md) - 测试最佳实践

---

**快速开始指南状态**: 已完成  
**适用版本**: MarketPrism v2.0+  
**预计启动时间**: 5-10分钟  
**支持平台**: Linux, macOS, Windows