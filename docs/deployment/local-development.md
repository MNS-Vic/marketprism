# MarketPrism 本地开发环境部署

> 最后更新：2025-01-27

## 🎯 概述

本指南将帮助你在本地环境中搭建 MarketPrism 开发环境，支持代码热重载、调试和测试。

## 🔧 环境要求

### 系统要求
- **操作系统**: Linux, macOS, Windows (推荐 Linux/macOS)
- **内存**: 至少 4GB 可用内存
- **磁盘**: 至少 10GB 可用空间
- **网络**: 稳定的互联网连接

### 软件依赖
- **Python**: 3.12+ (推荐 3.12)
- **Docker**: 20.10+ 和 Docker Compose
- **Git**: 版本控制
- **curl**: API 测试工具

### 可选工具
- **Go**: 1.18+ (如需编译 Go 收集器)
- **Node.js**: 16+ (如需前端开发)
- **VS Code**: 推荐的开发环境

## 🚀 快速搭建

### 1. 克隆项目
```bash
git clone https://github.com/your-org/marketprism.git
cd marketprism
```

### 2. 环境配置
```bash
# 创建 Python 虚拟环境
python -m venv venv_tdd
source venv_tdd/bin/activate  # Linux/macOS
# 或 venv_tdd\Scripts\activate  # Windows

# 安装 Python 依赖
pip install -r requirements.txt

# 复制环境配置
cp .env.development .env
```

### 3. 启动基础设施
```bash
# 启动 NATS 和 ClickHouse
docker-compose -f docker-compose.infrastructure.yml up -d

# 等待服务启动 (约30秒)
sleep 30

# 验证服务状态
docker-compose -f docker-compose.infrastructure.yml ps
```

### 4. 初始化数据库
```bash
# 初始化 ClickHouse 数据库
python scripts/init_clickhouse.py

# 创建 NATS 流
python scripts/create_nats_streams.py
```

### 5. 启动开发服务
```bash
# 方式1: 本地 Python 进程 (推荐开发)
cd services/python-collector
export PYTHONPATH=$PWD/src:$PYTHONPATH
python -m marketprism_collector.main

# 方式2: Docker 开发模式 (代码挂载)
docker-compose -f docker-compose.dev.yml up -d python-collector
```

## 🔍 验证安装

### 检查服务状态
```bash
# 检查基础设施
docker-compose -f docker-compose.infrastructure.yml ps

# 检查收集器健康状态
curl http://localhost:8080/health

# 检查监控指标
curl http://localhost:8080/metrics | head -20
```

### 验证数据流
```bash
# 检查 NATS 流
docker exec -it marketprism_nats_1 nats stream ls

# 检查 ClickHouse 连接
docker exec -it marketprism_clickhouse_1 clickhouse-client --query "SELECT 1"

# 查看实时数据 (等待几分钟)
docker exec -it marketprism_clickhouse_1 clickhouse-client --query "SELECT count() FROM marketprism.trades"
```

## ⚙️ 开发配置

### 环境变量配置

编辑 `.env` 文件：
```env
# 开发模式配置
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG

# 服务配置
COLLECTOR_HTTP_PORT=8080
COLLECTOR_ENABLE_SCHEDULER=true
COLLECTOR_USE_REAL_EXCHANGES=true

# 基础设施配置
NATS_URL=nats://localhost:4222
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_DATABASE=marketprism

# 开发特性
ENABLE_HOT_RELOAD=true
ENABLE_DEBUG_ENDPOINTS=true
```

### 交易所配置

开发环境推荐配置 (`config/exchanges/`):

```yaml
# binance_spot_dev.yaml
exchange: "binance"
market_type: "spot"
enabled: true
symbols:
  - "BTC/USDT"  # 主要测试对
  - "ETH/USDT"  # 次要测试对
data_types:
  - "trade"
  - "ticker"
rate_limit:
  requests_per_second: 5  # 开发环境降低频率
```

### 日志配置

创建 `config/logging_dev.yaml`:
```yaml
version: 1
disable_existing_loggers: false

formatters:
  detailed:
    format: '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
  simple:
    format: '%(levelname)s - %(message)s'

handlers:
  console:
    class: logging.StreamHandler
    level: DEBUG
    formatter: detailed
    stream: ext://sys.stdout
  
  file:
    class: logging.FileHandler
    level: INFO
    formatter: detailed
    filename: logs/marketprism_dev.log

loggers:
  marketprism_collector:
    level: DEBUG
    handlers: [console, file]
    propagate: false

root:
  level: INFO
  handlers: [console]
```

## 🛠️ 开发工具

### VS Code 配置

创建 `.vscode/settings.json`:
```json
{
    "python.defaultInterpreterPath": "./venv_tdd/bin/python",
    "python.linting.enabled": true,
    "python.linting.pylintEnabled": false,
    "python.linting.flake8Enabled": true,
    "python.formatting.provider": "black",
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": [
        "tests"
    ],
    "files.exclude": {
        "**/__pycache__": true,
        "**/*.pyc": true
    }
}
```

创建 `.vscode/launch.json`:
```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: MarketPrism Collector",
            "type": "python",
            "request": "launch",
            "module": "marketprism_collector.main",
            "cwd": "${workspaceFolder}/services/python-collector/src",
            "env": {
                "PYTHONPATH": "${workspaceFolder}/services/python-collector/src"
            },
            "console": "integratedTerminal"
        }
    ]
}
```

### 代码质量工具

安装开发工具：
```bash
pip install black flake8 mypy pytest pytest-cov
```

配置 `pyproject.toml`:
```toml
[tool.black]
line-length = 88
target-version = ['py312']

[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-v --tb=short"
```

## 🧪 测试环境

### 运行测试
```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/unit/
pytest tests/integration/

# 生成覆盖率报告
pytest --cov=src --cov-report=html
open htmlcov/index.html  # 查看覆盖率报告
```

### 测试数据库

创建测试专用数据库：
```bash
# 连接 ClickHouse
docker exec -it marketprism_clickhouse_1 clickhouse-client

# 创建测试数据库
CREATE DATABASE marketprism_test;

# 使用测试环境变量
export CLICKHOUSE_DATABASE=marketprism_test
```

## 🔄 开发工作流

### 1. 代码开发
```bash
# 创建功能分支
git checkout -b feature/new-exchange-adapter

# 编写代码
# 编辑 services/python-collector/src/marketprism_collector/exchanges/new_exchange.py

# 运行代码格式化
black services/python-collector/src/

# 运行类型检查
mypy services/python-collector/src/
```

### 2. 测试验证
```bash
# 运行单元测试
pytest tests/unit/exchanges/test_new_exchange.py

# 运行集成测试
pytest tests/integration/test_new_exchange_integration.py

# 检查代码覆盖率
pytest --cov=marketprism_collector.exchanges.new_exchange
```

### 3. 本地验证
```bash
# 重启收集器
pkill -f marketprism_collector
python -m marketprism_collector.main

# 验证新功能
curl http://localhost:8080/health
curl http://localhost:8080/metrics | grep new_exchange
```

### 4. 提交代码
```bash
# 运行完整测试套件
pytest

# 提交代码
git add .
git commit -m "feat: add new exchange adapter"
git push origin feature/new-exchange-adapter
```

## 🐛 调试技巧

### 1. 日志调试
```bash
# 实时查看日志
tail -f logs/marketprism_dev.log

# 过滤特定日志
tail -f logs/marketprism_dev.log | grep ERROR

# 查看 Docker 日志
docker-compose logs -f python-collector
```

### 2. 性能分析
```bash
# 查看系统资源
docker stats

# 查看进程状态
ps aux | grep python

# 内存使用分析
python -m memory_profiler services/python-collector/src/marketprism_collector/main.py
```

### 3. 网络调试
```bash
# 检查端口占用
lsof -i :8080
lsof -i :4222
lsof -i :8123

# 测试网络连接
curl -v http://localhost:8080/health
telnet localhost 4222
```

## 🔧 故障排除

### 常见问题

#### 1. Python 依赖问题
```bash
# 重新创建虚拟环境
rm -rf venv_tdd
python -m venv venv_tdd
source venv_tdd/bin/activate
pip install -r requirements.txt
```

#### 2. Docker 服务问题
```bash
# 重启 Docker 服务
docker-compose -f docker-compose.infrastructure.yml down
docker-compose -f docker-compose.infrastructure.yml up -d

# 清理 Docker 资源
docker system prune -f
```

#### 3. 端口冲突
```bash
# 查找占用进程
lsof -i :8080
kill -9 <PID>

# 修改端口配置
export COLLECTOR_HTTP_PORT=8081
```

#### 4. 数据库连接问题
```bash
# 检查 ClickHouse 状态
docker exec -it marketprism_clickhouse_1 clickhouse-client --query "SELECT version()"

# 重新初始化数据库
python scripts/init_clickhouse.py --force
```

## 📊 性能监控

### 开发环境监控

```bash
# 查看实时指标
watch -n 1 'curl -s http://localhost:8080/metrics | grep -E "(messages_per_second|error_rate|memory_usage)"'

# 查看健康状态
watch -n 5 'curl -s http://localhost:8080/health | jq .'

# 查看调度器状态
curl -s http://localhost:8080/scheduler | jq .
```

### 性能基准测试

```bash
# 运行性能测试
pytest tests/performance/ -v

# 生成性能报告
python scripts/performance_benchmark.py --output reports/performance.json
```

## 📚 下一步

### 深入开发
- [编码规范](../development/coding-standards.md) - 代码规范和最佳实践
- [测试指南](../development/testing.md) - 测试策略和方法
- [贡献指南](../development/contributing.md) - 如何贡献代码

### 部署升级
- [Docker 部署](docker-deployment.md) - 容器化部署
- [生产部署](production.md) - 生产环境部署
- [监控配置](monitoring.md) - 监控系统配置

---

**开发环境状态**: 已验证  
**支持平台**: Linux, macOS, Windows  
**预计搭建时间**: 15-30分钟  
**开发体验**: 优化 (热重载、调试支持)