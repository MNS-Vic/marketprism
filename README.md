# 🚀 MarketPrism - 企业级加密货币市场数据收集平台

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=flat&logo=docker&logoColor=white)](https://docker.com/)
[![ClickHouse](https://img.shields.io/badge/ClickHouse-FFCC01?style=flat&logo=clickhouse&logoColor=white)](https://clickhouse.com/)
[![Architecture](https://img.shields.io/badge/Architecture-Core--Services-brightgreen.svg)](docs/architecture/)
[![Tests](https://img.shields.io/badge/Tests-80%25+-brightgreen.svg)](tests/)
[![Docs](https://img.shields.io/badge/Docs-Complete-blue.svg)](docs/)

> **高性能、高可靠性的加密货币市场数据实时收集、处理和存储平台**

## 🎉 最新更新 (2025-06-13)

### 重大改进：Python环境标准化和依赖管理

- ✅ **统一Python版本管理** - 自动检查Python 3.11+版本
- ✅ **标准化依赖管理** - 统一的requirements.txt文件
- ✅ **智能启动脚本** - 自动环境检查和依赖安装
- ✅ **修复datetime问题** - 自动修复36个文件的datetime导入
- ✅ **服务完全正常** - data-collector服务100%正常运行

## 🚀 快速开始

### 环境要求

- **Python**: 3.11.0 或更高版本
- **操作系统**: Linux, macOS, Windows
- **内存**: 最少 4GB RAM
- **磁盘**: 最少 10GB 可用空间

### 一键启动（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/your-org/marketprism.git
cd marketprism

# 2. 启动数据收集服务（自动处理所有依赖）
./start-data-collector.sh

# 3. 验证服务运行
curl http://localhost:8081/health
```

### 手动安装步骤

如果您希望手动控制安装过程：

```bash
# 1. 检查Python版本
python --version  # 需要 3.11.0+

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或 venv\Scripts\activate  # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动服务
cd services/python-collector
python -m marketprism_collector.main
```

## 📋 完整部署指南

### 方式一：标准部署（推荐新手）

#### 1. 环境准备

```bash
# 检查系统要求
python --version  # 确保 >= 3.11.0
git --version     # 确保已安装Git
```

#### 2. 项目下载

```bash
# 下载项目
git clone https://github.com/your-org/marketprism.git
cd marketprism

# 查看项目结构
ls -la
```

#### 3. 服务启动

```bash
# 启动数据收集服务
./start-data-collector.sh

# 启动其他服务（可选）
./start-api-gateway.sh      # API网关服务
./start-message-broker.sh   # 消息代理服务
./start-data-storage.sh     # 数据存储服务
./start-monitoring.sh       # 监控服务
./start-scheduler.sh        # 调度服务
```

#### 4. 验证部署

```bash
# 检查服务健康状态
curl http://localhost:8081/health

# 查看服务详细状态
curl http://localhost:8081/api/v1/collector/status

# 查看服务日志
tail -f data-collector.log
```

### 方式二：容器化部署（推荐生产环境）

#### 1. 安装Docker

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install docker.io docker-compose

# CentOS/RHEL
sudo yum install docker docker-compose

# macOS
brew install docker docker-compose

# 启动Docker服务
sudo systemctl start docker
sudo systemctl enable docker
```

#### 2. 构建镜像

```bash
# 构建MarketPrism镜像
docker build -t marketprism:latest .

# 查看构建的镜像
docker images | grep marketprism
```

#### 3. 使用Docker Compose部署

```bash
# 启动完整服务栈
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看服务日志
docker-compose logs -f data-collector
```

#### 4. Docker Compose配置示例

创建 `docker-compose.yml` 文件：

```yaml
version: '3.8'

services:
  data-collector:
    build: .
    ports:
      - "8081:8081"
    environment:
      - PYTHONPATH=/app
    volumes:
      - ./config:/app/config
      - ./logs:/app/logs
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8081/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  api-gateway:
    build: .
    ports:
      - "8080:8080"
    depends_on:
      - data-collector
    restart: unless-stopped

  message-broker:
    image: nats:latest
    ports:
      - "4222:4222"
      - "8222:8222"
    restart: unless-stopped

  data-storage:
    image: clickhouse/clickhouse-server:latest
    ports:
      - "8123:8123"
      - "9000:9000"
    volumes:
      - clickhouse_data:/var/lib/clickhouse
    restart: unless-stopped

  monitoring:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./config/prometheus.yml:/etc/prometheus/prometheus.yml
    restart: unless-stopped

volumes:
  clickhouse_data:
```

### 方式三：Kubernetes部署（推荐大规模生产）

#### 1. 准备Kubernetes环境

```bash
# 安装kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# 验证集群连接
kubectl cluster-info
```

#### 2. 部署到Kubernetes

```bash
# 应用Kubernetes配置
kubectl apply -f k8s/

# 查看部署状态
kubectl get pods -n marketprism

# 查看服务状态
kubectl get services -n marketprism
```

#### 3. Kubernetes配置示例

创建 `k8s/deployment.yaml`：

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: marketprism-data-collector
  namespace: marketprism
spec:
  replicas: 3
  selector:
    matchLabels:
      app: data-collector
  template:
    metadata:
      labels:
        app: data-collector
    spec:
      containers:
      - name: data-collector
        image: marketprism:latest
        ports:
        - containerPort: 8081
        env:
        - name: PYTHONPATH
          value: "/app"
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8081
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8081
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: data-collector-service
  namespace: marketprism
spec:
  selector:
    app: data-collector
  ports:
  - protocol: TCP
    port: 8081
    targetPort: 8081
  type: LoadBalancer
```

## ⚙️ 配置指南

### 基础配置

主要配置文件位于 `config/` 目录：

```bash
config/
├── services.yaml          # 主服务配置
├── collector.yaml         # 数据收集器配置
├── exchanges.yaml         # 交易所配置
└── logging.yaml           # 日志配置
```

### 交易所配置

编辑 `config/exchanges.yaml`：

```yaml
exchanges:
  binance:
    enabled: true
    api_key: "your_api_key"
    api_secret: "your_api_secret"
    testnet: false
    
  okx:
    enabled: true
    api_key: "your_api_key"
    api_secret: "your_api_secret"
    passphrase: "your_passphrase"
    
  deribit:
    enabled: true
    client_id: "your_client_id"
    client_secret: "your_client_secret"
```

### 代理配置（可选）

如果需要通过代理访问交易所，编辑 `config/collector.yaml`：

```yaml
proxy:
  enabled: true
  http_proxy: "http://127.0.0.1:1087"
  https_proxy: "http://127.0.0.1:1087"
  socks_proxy: "socks5://127.0.0.1:1080"
  no_proxy: "localhost,127.0.0.1"
```

### 数据库配置

编辑 `config/services.yaml`：

```yaml
database:
  clickhouse:
    host: "localhost"
    port: 8123
    user: "default"
    password: ""
    database: "marketprism"
    
message_broker:
  nats:
    url: "nats://localhost:4222"
    cluster_id: "marketprism"
```

## 🔧 使用指南

### 基本操作

#### 1. 查看服务状态

```bash
# 健康检查
curl http://localhost:8081/health

# 详细状态
curl http://localhost:8081/api/v1/collector/status

# 支持的交易所
curl http://localhost:8081/api/v1/collector/exchanges

# 支持的数据类型
curl http://localhost:8081/api/v1/collector/data-types
```

#### 2. 数据收集操作

```bash
# 开始收集特定交易对数据
curl -X POST http://localhost:8081/api/v1/collector/subscribe \
  -H "Content-Type: application/json" \
  -d '{
    "exchange": "binance",
    "symbol": "BTCUSDT",
    "data_types": ["trade", "orderbook", "ticker"]
  }'

# 停止收集数据
curl -X POST http://localhost:8081/api/v1/collector/unsubscribe \
  -H "Content-Type: application/json" \
  -d '{
    "exchange": "binance",
    "symbol": "BTCUSDT"
  }'
```

#### 3. 查询历史数据

```bash
# 查询最新交易数据
curl "http://localhost:8081/api/v1/data/trades?exchange=binance&symbol=BTCUSDT&limit=10"

# 查询价格历史
curl "http://localhost:8081/api/v1/data/price-history?exchange=binance&symbol=BTCUSDT&hours=24"

# 查询订单簿数据
curl "http://localhost:8081/api/v1/data/orderbook?exchange=binance&symbol=BTCUSDT"
```

### 高级操作

#### 1. 批量操作

```bash
# 批量订阅多个交易对
curl -X POST http://localhost:8081/api/v1/collector/batch-subscribe \
  -H "Content-Type: application/json" \
  -d '{
    "subscriptions": [
      {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "data_types": ["trade", "ticker"]
      },
      {
        "exchange": "okx",
        "symbol": "ETH-USDT",
        "data_types": ["trade", "orderbook"]
      }
    ]
  }'
```

#### 2. 实时数据流

```bash
# WebSocket连接获取实时数据
wscat -c ws://localhost:8081/ws/data/stream

# 订阅实时交易数据
echo '{"action": "subscribe", "exchange": "binance", "symbol": "BTCUSDT", "data_type": "trade"}' | wscat -c ws://localhost:8081/ws/data/stream
```

#### 3. 监控和告警

```bash
# 查看系统指标
curl http://localhost:8081/metrics

# 查看性能统计
curl http://localhost:8081/api/v1/stats/performance

# 查看错误日志
curl http://localhost:8081/api/v1/logs/errors
```

## 🛠️ 维护指南

### 日常维护

#### 1. 日志管理

```bash
# 查看实时日志
tail -f logs/data-collector.log

# 查看错误日志
grep ERROR logs/data-collector.log

# 日志轮转（每天自动执行）
logrotate /etc/logrotate.d/marketprism
```

#### 2. 数据库维护

```bash
# 连接ClickHouse
clickhouse-client

# 查看数据库大小
SELECT 
    database,
    formatReadableSize(sum(bytes)) as size
FROM system.parts 
WHERE database = 'marketprism'
GROUP BY database;

# 清理过期数据（自动TTL）
OPTIMIZE TABLE marketprism.trades FINAL;
```

#### 3. 性能监控

```bash
# 查看系统资源使用
htop

# 查看网络连接
netstat -tulpn | grep :8081

# 查看磁盘使用
df -h
```

### 故障排除

#### 1. 常见问题

**问题：服务启动失败**
```bash
# 检查Python版本
python --version

# 检查依赖安装
pip list | grep -E "(fastapi|aiohttp|pydantic)"

# 重新安装依赖
pip install -r requirements.txt --force-reinstall
```

**问题：端口被占用**
```bash
# 查看端口占用
lsof -i :8081

# 杀死占用进程
kill -9 <PID>

# 重新启动服务
./start-data-collector.sh
```

**问题：交易所连接失败**
```bash
# 检查网络连接
ping api.binance.com

# 检查代理配置
curl --proxy http://127.0.0.1:1087 https://api.binance.com/api/v3/ping

# 查看详细错误日志
tail -f logs/data-collector.log | grep ERROR
```

#### 2. 性能优化

**内存优化**
```bash
# 调整Python内存限制
export PYTHONMALLOC=malloc

# 启用垃圾回收优化
export PYTHONOPTIMIZE=1
```

**网络优化**
```bash
# 调整TCP参数
echo 'net.core.rmem_max = 16777216' >> /etc/sysctl.conf
echo 'net.core.wmem_max = 16777216' >> /etc/sysctl.conf
sysctl -p
```

### 备份和恢复

#### 1. 数据备份

```bash
# 备份ClickHouse数据
clickhouse-client --query "BACKUP DATABASE marketprism TO Disk('backups', 'marketprism_backup_$(date +%Y%m%d).zip')"

# 备份配置文件
tar -czf config_backup_$(date +%Y%m%d).tar.gz config/

# 备份日志文件
tar -czf logs_backup_$(date +%Y%m%d).tar.gz logs/
```

#### 2. 数据恢复

```bash
# 恢复ClickHouse数据
clickhouse-client --query "RESTORE DATABASE marketprism FROM Disk('backups', 'marketprism_backup_20250613.zip')"

# 恢复配置文件
tar -xzf config_backup_20250613.tar.gz

# 重启服务
./start-data-collector.sh
```

## 🔒 安全指南

### 1. API密钥管理

```bash
# 使用环境变量存储敏感信息
export BINANCE_API_KEY="your_api_key"
export BINANCE_API_SECRET="your_api_secret"

# 或使用配置文件（确保文件权限安全）
chmod 600 config/exchanges.yaml
```

### 2. 网络安全

```bash
# 配置防火墙
sudo ufw allow 8081/tcp
sudo ufw enable

# 使用HTTPS（生产环境）
# 配置SSL证书和反向代理
```

### 3. 访问控制

```bash
# 创建专用用户
sudo useradd -m -s /bin/bash marketprism
sudo usermod -aG docker marketprism

# 设置文件权限
chown -R marketprism:marketprism /opt/marketprism
chmod -R 750 /opt/marketprism
```

## 📊 监控和告警

### 1. Prometheus监控

```yaml
# config/prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'marketprism'
    static_configs:
      - targets: ['localhost:8081']
    metrics_path: '/metrics'
    scrape_interval: 5s
```

### 2. Grafana仪表板

```bash
# 启动Grafana
docker run -d -p 3000:3000 grafana/grafana

# 访问Grafana
# http://localhost:3000 (admin/admin)

# 导入MarketPrism仪表板
# 使用提供的dashboard.json文件
```

### 3. 告警配置

```yaml
# config/alertmanager.yml
global:
  smtp_smarthost: 'localhost:587'
  smtp_from: 'alerts@marketprism.com'

route:
  group_by: ['alertname']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 1h
  receiver: 'web.hook'

receivers:
  - name: 'web.hook'
    email_configs:
      - to: 'admin@marketprism.com'
        subject: 'MarketPrism Alert'
        body: '{{ range .Alerts }}{{ .Annotations.summary }}{{ end }}'
```

## 🚀 扩展和定制

### 1. 添加新交易所

```python
# 创建新的交易所适配器
# services/python-collector/src/marketprism_collector/exchanges/new_exchange.py

class NewExchangeAdapter:
    def __init__(self, config):
        self.config = config
    
    async def connect(self):
        # 实现连接逻辑
        pass
    
    async def subscribe_trades(self, symbol):
        # 实现交易数据订阅
        pass
```

### 2. 自定义数据处理

```python
# 创建自定义数据处理器
# services/python-collector/src/marketprism_collector/processors/custom_processor.py

class CustomDataProcessor:
    def process_trade(self, trade_data):
        # 自定义交易数据处理逻辑
        return processed_data
    
    def process_orderbook(self, orderbook_data):
        # 自定义订单簿数据处理逻辑
        return processed_data
```

### 3. 插件开发

```python
# 创建插件
# plugins/custom_plugin.py

class CustomPlugin:
    def __init__(self, collector):
        self.collector = collector
    
    def on_trade_received(self, trade):
        # 处理接收到的交易数据
        pass
    
    def on_orderbook_updated(self, orderbook):
        # 处理订单簿更新
        pass
```

## 📚 API文档

### REST API端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/api/v1/collector/status` | GET | 收集器状态 |
| `/api/v1/collector/subscribe` | POST | 订阅数据 |
| `/api/v1/collector/unsubscribe` | POST | 取消订阅 |
| `/api/v1/data/trades` | GET | 查询交易数据 |
| `/api/v1/data/orderbook` | GET | 查询订单簿 |
| `/api/v1/data/ticker` | GET | 查询行情数据 |
| `/metrics` | GET | Prometheus指标 |

### WebSocket API

```javascript
// 连接WebSocket
const ws = new WebSocket('ws://localhost:8081/ws/data/stream');

// 订阅实时数据
ws.send(JSON.stringify({
    action: 'subscribe',
    exchange: 'binance',
    symbol: 'BTCUSDT',
    data_type: 'trade'
}));

// 接收数据
ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log('Received:', data);
};
```

## 🤝 贡献指南

### 1. 开发环境设置

```bash
# Fork项目并克隆
git clone https://github.com/your-username/marketprism.git
cd marketprism

# 创建开发分支
git checkout -b feature/your-feature-name

# 安装开发依赖
pip install -r requirements-dev.txt

# 安装pre-commit钩子
pre-commit install
```

### 2. 代码规范

```bash
# 代码格式化
black .
isort .

# 代码检查
flake8 .
mypy .

# 运行测试
pytest tests/ -v --cov=src/
```

### 3. 提交代码

```bash
# 提交更改
git add .
git commit -m "feat: add new feature"

# 推送到远程仓库
git push origin feature/your-feature-name

# 创建Pull Request
# 在GitHub上创建PR
```

## 📄 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

## 🆘 支持和帮助

### 1. 文档资源

- [项目说明](项目说明.md) - 详细的项目架构说明
- [API文档](docs/api/) - 完整的API参考文档
- [配置指南](docs/configuration/) - 详细的配置说明

### 2. 社区支持

- **GitHub Issues**: [报告问题](https://github.com/your-org/marketprism/issues)
- **GitHub Discussions**: [技术讨论](https://github.com/your-org/marketprism/discussions)
- **Discord**: [实时聊天](https://discord.gg/marketprism)

### 3. 商业支持

- **技术咨询**: support@marketprism.com
- **定制开发**: custom@marketprism.com
- **企业支持**: enterprise@marketprism.com

---

## 🎯 快速链接

- [🚀 快速开始](#-快速开始)
- [📋 完整部署指南](#-完整部署指南)
- [⚙️ 配置指南](#️-配置指南)
- [🔧 使用指南](#-使用指南)
- [🛠️ 维护指南](#️-维护指南)
- [📊 监控和告警](#-监控和告警)

---

**MarketPrism** - 让加密货币数据收集变得简单而强大！

[![Star on GitHub](https://img.shields.io/github/stars/your-org/marketprism.svg?style=social)](https://github.com/your-org/marketprism/stargazers)