# MarketPrism 微服务一键启动器

## 概述

这个目录包含了MarketPrism微服务架构的一键启动脚本，让每个微服务都可以在不同的地方独立部署和运行。

## 🚀 快速开始

### 交互式启动单个服务
```bash
# 进入项目根目录
cd /path/to/marketprism

# 运行交互式启动器
./scripts/service-launchers/start-service.sh
```

### 直接启动特定服务
```bash
# API网关服务
./scripts/service-launchers/start-api-gateway.sh

# 市场数据采集服务
./scripts/service-launchers/start-market-data-collector.sh

# 数据存储服务
./scripts/service-launchers/start-data-storage.sh

# 监控服务
./scripts/service-launchers/start-monitoring.sh

# 调度服务
./scripts/service-launchers/start-scheduler.sh

# 消息代理服务
./scripts/service-launchers/start-message-broker.sh
```

### 批量管理所有服务
```bash
# 后台启动所有服务
./scripts/service-launchers/start-all-services.sh

# 检查服务状态
./scripts/service-launchers/status-services.sh

# 停止所有服务
./scripts/service-launchers/stop-services.sh
```

## 📋 服务列表

| 服务名称 | 端口 | 启动脚本 | 主要功能 |
|---------|------|----------|----------|
| API Gateway | 8080 | `start-api-gateway.sh` | 统一API网关，请求路由、认证、限流 |
| Market Data Collector | 8081 | `start-market-data-collector.sh` | 市场数据采集，支持Binance/OKX/Deribit |
| Data Storage Service | 8082 | `start-data-storage.sh` | 数据存储服务，ClickHouse/Redis热冷存储 |
| Monitoring Service | 8083 | `start-monitoring.sh` | 系统监控，Prometheus指标，智能告警 |
| Scheduler Service | 8084 | `start-scheduler.sh` | 任务调度服务，定时任务，自动化管理 |
| Message Broker Service | 8085 | `start-message-broker.sh` | 消息代理，NATS/JetStream，消息队列 |

## 🛠️ 脚本功能

### 单服务启动脚本特性
- ✅ 自动检测项目根目录
- ✅ Python虚拟环境管理
- ✅ 依赖自动安装
- ✅ 配置文件验证
- ✅ 端口冲突检测
- ✅ 详细的启动信息显示
- ✅ 实时日志输出
- ✅ 优雅的错误处理

### 批量管理脚本特性
- ✅ 按依赖顺序启动/停止
- ✅ PID文件管理
- ✅ 健康状态检查
- ✅ 内存使用监控
- ✅ 运行时间统计
- ✅ 后台运行支持
- ✅ 详细状态报告

## 🔧 环境要求

### 必需组件
- Python 3.8+
- pip (Python包管理器)

### 可选组件 (增强功能)
- ClickHouse (数据存储服务)
- Redis (热存储缓存)
- NATS Server (消息代理)

### 依赖包
脚本会自动安装以下Python包：
- aiohttp
- pyyaml
- structlog
- prometheus_client
- psutil
- asyncio-nats
- websockets
- clickhouse-driver
- clickhouse-connect
- redis

## 📁 目录结构

```
scripts/service-launchers/
├── README.md                      # 本文档
├── start-service.sh               # 交互式服务选择器
├── start-api-gateway.sh           # API网关启动脚本
├── start-market-data-collector.sh # 数据采集服务启动脚本
├── start-data-storage.sh          # 数据存储服务启动脚本
├── start-monitoring.sh            # 监控服务启动脚本
├── start-scheduler.sh             # 调度服务启动脚本
├── start-message-broker.sh        # 消息代理服务启动脚本
├── start-all-services.sh          # 批量启动脚本
├── status-services.sh             # 状态检查脚本
└── stop-services.sh               # 批量停止脚本
```

## 🌐 服务访问信息

启动服务后，可以通过以下端点访问：

### API Gateway (8080)
- 健康检查: http://localhost:8080/health
- 网关状态: http://localhost:8080/_gateway/status
- 服务列表: http://localhost:8080/_gateway/services
- Prometheus指标: http://localhost:8080/metrics

### Market Data Collector (8081)
- 健康检查: http://localhost:8081/health
- 数据采集状态: http://localhost:8081/api/v1/collector/status
- 交易所状态: http://localhost:8081/api/v1/collector/exchanges
- Prometheus指标: http://localhost:8081/metrics

### Data Storage Service (8082)
- 健康检查: http://localhost:8082/health
- 存储状态: http://localhost:8082/api/v1/storage/status
- 数据库状态: http://localhost:8082/api/v1/storage/database/status
- Prometheus指标: http://localhost:8082/metrics

### Monitoring Service (8083)
- 健康检查: http://localhost:8083/health
- 系统概览: http://localhost:8083/api/v1/overview
- 服务状态: http://localhost:8083/api/v1/services
- 告警信息: http://localhost:8083/api/v1/alerts
- Prometheus指标: http://localhost:8083/metrics

### Scheduler Service (8084)
- 健康检查: http://localhost:8084/health
- 调度器状态: http://localhost:8084/api/v1/scheduler/status
- 任务列表: http://localhost:8084/api/v1/scheduler/tasks
- Prometheus指标: http://localhost:8084/metrics

### Message Broker Service (8085)
- 健康检查: http://localhost:8085/health
- 代理状态: http://localhost:8085/api/v1/broker/status
- 流管理: http://localhost:8085/api/v1/broker/streams
- Prometheus指标: http://localhost:8085/metrics

## 🔍 日志和监控

### 日志文件位置
```
logs/
├── api-gateway-20241231_120000.log
├── market-data-collector-20241231_120001.log
├── data-storage-20241231_120002.log
├── monitoring-20241231_120003.log
├── scheduler-20241231_120004.log
└── message-broker-20241231_120005.log
```

### 查看实时日志
```bash
# 查看特定服务日志
tail -f logs/api-gateway-*.log

# 查看所有服务日志
tail -f logs/*.log
```

### PID文件位置
```
data/pids/
├── api-gateway-service.pid
├── market-data-collector.pid
├── data-storage-service.pid
├── monitoring-service.pid
├── scheduler-service.pid
└── message-broker-service.pid
```

## 🚀 部署建议

### 开发环境
```bash
# 使用交互式启动器，按需启动服务
./scripts/service-launchers/start-service.sh
```

### 测试环境
```bash
# 启动所有服务进行集成测试
./scripts/service-launchers/start-all-services.sh

# 检查状态
./scripts/service-launchers/status-services.sh
```

### 生产环境
1. **分布式部署**: 将不同服务部署到不同的服务器
2. **负载均衡**: 在API Gateway前添加负载均衡器
3. **监控集成**: 配置Prometheus/Grafana监控
4. **日志收集**: 配置ELK或类似的日志收集系统

### 分布式部署示例
```bash
# 服务器1: 运行API Gateway
./scripts/service-launchers/start-api-gateway.sh

# 服务器2: 运行数据采集和存储
./scripts/service-launchers/start-market-data-collector.sh &
./scripts/service-launchers/start-data-storage.sh &

# 服务器3: 运行监控和调度
./scripts/service-launchers/start-monitoring.sh &
./scripts/service-launchers/start-scheduler.sh &

# 服务器4: 运行消息代理
./scripts/service-launchers/start-message-broker.sh
```

## ⚠️ 注意事项

### 端口冲突
- 确保目标端口未被其他应用占用
- 脚本会自动检测并尝试停止冲突进程

### 依赖服务
- 某些服务依赖外部组件（ClickHouse、Redis、NATS）
- 缺少依赖时服务仍可启动，但功能受限

### 资源需求
- 每个服务大约需要100-500MB内存
- 确保系统有足够的资源运行所需服务

### 配置文件
- 所有服务共享 `config/services.yaml` 配置
- 修改配置后需要重启相关服务

## 🔧 故障排除

### 服务启动失败
1. 检查Python版本和依赖
2. 查看日志文件了解详细错误
3. 确认配置文件格式正确
4. 检查端口是否被占用

### 端口占用问题
```bash
# 查看端口占用
lsof -i :8080

# 强制停止占用进程
pkill -f "api-gateway-service"
```

### 虚拟环境问题
```bash
# 重新创建虚拟环境
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 权限问题
```bash
# 给予脚本执行权限
chmod +x scripts/service-launchers/*.sh
```

## 📞 技术支持

如遇到问题，请：
1. 检查日志文件：`logs/[service-name]-*.log`
2. 运行状态检查：`./scripts/service-launchers/status-services.sh`
3. 查看进程状态：`ps aux | grep python`
4. 检查网络连接：`netstat -tlnp | grep :80`

## 🔄 更新和维护

### 更新服务
```bash
# 停止服务
./scripts/service-launchers/stop-services.sh

# 更新代码
git pull

# 重新启动
./scripts/service-launchers/start-all-services.sh
```

### 清理日志
```bash
# 清理旧日志（保留最近7天）
find logs/ -name "*.log" -mtime +7 -delete
```

### 定期维护
- 定期检查服务状态
- 监控资源使用情况
- 清理过期日志和数据
- 更新依赖包版本