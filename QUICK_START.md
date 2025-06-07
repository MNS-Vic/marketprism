# MarketPrism 快速启动指南
*微服务架构 - 生产就绪版本*

## 🚀 一键启动

### 使用Docker（推荐）

```bash
# 1. 克隆项目
git clone <repository-url>
cd marketprism

# 2. 一键部署
chmod +x scripts/deployment/deploy.sh
./scripts/deployment/deploy.sh production docker

# 3. 验证部署
curl http://localhost:8080/health
```

### 使用本地环境

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动基础设施
docker-compose -f docker-compose-nats.yml up -d

# 3. 本地部署
./scripts/deployment/deploy.sh development local
```

## 📊 服务访问地址

| 服务 | 地址 | 说明 |
|------|------|------|
| API网关 | http://localhost:8080 | 统一API入口 |
| 数据存储服务 | http://localhost:8082 | 存储管理 |
| 市场数据采集 | http://localhost:8081 | 数据采集 |
| 调度服务 | http://localhost:8084 | 任务调度 |
| 监控服务 | http://localhost:8083 | 系统监控 |
| 消息代理服务 | http://localhost:8085 | 消息管理 |
| Grafana仪表板 | http://localhost:3000 | admin/marketprism_admin |
| Prometheus | http://localhost:9090 | 指标监控 |

## 🔍 健康检查

```bash
# 检查所有服务状态
curl http://localhost:8080/health
curl http://localhost:8081/health
curl http://localhost:8082/health
curl http://localhost:8083/health
curl http://localhost:8084/health
curl http://localhost:8085/health

# 或使用脚本
python scripts/health_check.py
```

## 📈 性能基准测试

```bash
# 运行性能基准测试
python scripts/performance_benchmark.py

# 查看测试报告
cat tests/reports/performance/benchmark_report.json
```

## 🐳 Docker管理

```bash
# 查看容器状态
docker-compose -f docker/docker-compose.yml ps

# 查看日志
docker-compose -f docker/docker-compose.yml logs -f [service_name]

# 停止服务
docker-compose -f docker/docker-compose.yml down

# 完全清理
docker-compose -f docker/docker-compose.yml down -v --remove-orphans
```

## 🔧 配置管理

### 主要配置文件
- `config/services.yaml` - 服务配置
- `docker/docker-compose.yml` - 容器配置
- `config/exchanges/` - 交易所配置

### 环境变量
```bash
export MARKETPRISM_ENV=production
export LOG_LEVEL=INFO
export CLICKHOUSE_HOST=clickhouse
export REDIS_HOST=redis
export NATS_URL=nats://nats:4222
```

## 📖 API文档

### API网关端点
```bash
# 服务健康检查
GET /health

# 数据存储API
GET /api/v1/storage/status
GET /api/v1/storage/hot/trades/{symbol}

# 监控API
GET /api/v1/monitoring/overview
GET /api/v1/monitoring/services

# 市场数据API
GET /api/v1/collector/status
POST /api/v1/collector/subscribe
```

## 🔨 开发指南

### 启动开发环境
```bash
# 1. 安装开发依赖
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 2. 启动开发服务
python scripts/start_services.py --env development

# 3. 运行测试
pytest tests/integration/
```

### 添加新服务
```bash
# 1. 创建服务目录
mkdir services/new-service

# 2. 使用服务模板
cp -r services/template/ services/new-service/

# 3. 更新配置
vim config/services.yaml

# 4. 添加测试
vim tests/integration/test_new_service.py
```

## 🚨 故障排除

### 常见问题

1. **端口冲突**
   ```bash
   # 检查端口占用
   netstat -tulpn | grep :8080
   
   # 修改配置文件中的端口
   vim config/services.yaml
   ```

2. **服务启动失败**
   ```bash
   # 查看服务日志
   docker-compose logs [service_name]
   
   # 检查依赖服务状态
   docker-compose ps
   ```

3. **数据库连接失败**
   ```bash
   # 检查ClickHouse状态
   docker exec -it marketprism-clickhouse clickhouse-client
   
   # 检查Redis状态
   docker exec -it marketprism-redis redis-cli ping
   ```

### 日志查看
```bash
# 实时日志
tail -f logs/marketprism.log

# Docker日志
docker-compose logs -f --tail=100

# 特定服务日志
docker-compose logs -f api-gateway-service
```

## 📊 监控面板

### Grafana仪表板
1. 访问 http://localhost:3000
2. 用户名: admin，密码: marketprism_admin
3. 导入预配置的仪表板

### Prometheus指标
- 访问 http://localhost:9090
- 查询示例:
  - `up` - 服务状态
  - `marketprism_service_health` - 服务健康状态
  - `process_cpu_seconds_total` - CPU使用率

## 🔄 数据流示例

### 启动数据采集
```bash
# 通过API网关启动采集
curl -X POST http://localhost:8080/api/v1/collector/subscribe \
  -H "Content-Type: application/json" \
  -d '{"exchange": "binance", "symbols": ["BTCUSDT", "ETHUSDT"]}'

# 查看采集状态
curl http://localhost:8080/api/v1/collector/status
```

### 查询存储数据
```bash
# 查询热数据
curl "http://localhost:8080/api/v1/storage/hot/trades/BTCUSDT?limit=10"

# 查看存储统计
curl http://localhost:8080/api/v1/storage/stats
```

## 🎯 生产部署建议

### 硬件要求
- CPU: 4核心以上
- 内存: 8GB以上
- 存储: 100GB以上SSD
- 网络: 稳定的互联网连接

### 安全配置
- 配置防火墙规则
- 启用HTTPS/TLS
- 设置API密钥认证
- 定期更新密码

### 性能优化
- 启用Redis缓存
- 配置ClickHouse集群
- 调整JVM参数
- 监控资源使用

## 📞 支持与联系

- 文档: `docs/` 目录
- 问题报告: GitHub Issues
- 架构文档: `docs/architecture/`
- API文档: `docs/api/`

---

**🎉 恭喜！MarketPrism微服务架构已成功部署**

立即开始使用，体验现代化的微服务架构带来的高性能和可扩展性！