# MarketPrism 本地部署指南

本指南将帮助你在本地环境中部署和运行 MarketPrism 加密货币数据平台，无需完整的 Docker 容器化部署，仅使用 Docker 部署基础设施组件。

## 系统要求

- Python 3.8+ (推荐 Python 3.10+)
- Docker 和 Docker Compose
- Go 1.18+ (如需编译 Go 收集器)
- 至少 4GB 可用内存
- 至少 10GB 可用磁盘空间

## 部署步骤

### 1. 准备环境

1. 克隆代码仓库:
   ```bash
   git clone https://github.com/yourusername/marketprism.git
   cd marketprism
   ```

2. 创建并激活 Python 虚拟环境:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # 或
   .\venv\Scripts\activate   # Windows
   ```

3. 安装 Python 依赖:
   ```bash
   pip install -r requirements.txt
   ```

### 2. 配置环境变量

1. 确保已配置正确的环境变量:
   ```bash
   cp .env.development .env
   ```

2. 根据需要编辑 `.env` 文件中的配置。

### 3. 使用启动脚本运行

我们提供了一个自动化的启动脚本，它会:
- 启动基础设施 (ClickHouse, NATS)
- 初始化数据库和消息流
- 启动核心服务
- 启动模拟数据收集器

运行以下命令启动所有服务:
```bash
./start_local_services.sh
```

这将在后台启动所有必要的服务。按 `Ctrl+C` 可以停止所有服务。

### 4. 手动启动各组件

如果你想手动控制各组件的启动，可以按照以下步骤进行:

1. 启动基础设施:
   ```bash
   docker-compose up -d clickhouse nats
   ```

2. 初始化 ClickHouse 数据库:
   ```bash
   python init_clickhouse.py
   ```

3. 创建 NATS 消息流:
   ```bash
   python fix_nats_streams.py
   ```

4. 启动数据归档服务:
   ```bash
   python services/data_archiver/main.py
   ```

5. 启动数据接收服务:
   ```bash
   cd services/ingestion
   python start_ingestion.py
   ```

6. 启动模拟数据收集器:
   ```bash
   services/go-collector/dist/collector_mock
   ```

## 访问服务

部署完成后，你可以通过以下地址访问各服务:

- 模拟数据收集器网页界面: http://localhost:8081
- ClickHouse Web 界面: http://localhost:8123
- NATS 监控界面: http://localhost:8222

## 故障排除

### 服务无法启动

1. 检查 Docker 服务是否运行:
   ```bash
   docker ps
   ```

2. 检查日志文件:
   ```bash
   cat logs/ingestion.log
   cat logs/data_archiver.log
   ```

3. 检查端口占用:
   ```bash
   lsof -i :8081  # 检查收集器端口
   lsof -i :8123  # 检查 ClickHouse 端口
   lsof -i :4222  # 检查 NATS 端口
   ```

### 数据未正确传输

1. 检查 NATS 消息流:
   ```bash
   docker exec -it marketprism_nats_1 nats stream ls
   docker exec -it marketprism_nats_1 nats stream info BINANCE_TRADES
   ```

2. 检查 ClickHouse 数据表:
   ```bash
   docker exec -it marketprism_clickhouse_1 clickhouse-client --query "SELECT count() FROM marketprism.trades"
   ```

## 使用真实数据源

如果你想连接真实的加密货币交易所数据源而不是使用模拟数据:

1. 编辑 `.env` 文件中的 API 密钥和配置
2. 替换模拟收集器为真实收集器 (需完成 Go 收集器的编译和修复)
3. 重启服务