# MarketPrism 微服务架构

MarketPrism已成功转型为现代化微服务架构，提供高可用、可扩展、易维护的金融数据处理平台。

## 🏗️ 架构概览

### 6个核心微服务

#### 核心业务服务 (3个)
1. **data-storage-service** (端口: 8080)
   - 统一数据存储管理
   - 热冷数据生命周期
   - 查询路由和优化

2. **market-data-collector** (端口: 8082)
   - 多交易所数据采集
   - 实时数据标准化
   - WebSocket连接管理

3. **api-gateway-service** (端口: 8083)
   - 统一API入口
   - 认证授权管理
   - 智能路由负载均衡

#### 基础设施服务 (3个)
4. **scheduler-service** (端口: 8081)
   - 分布式任务调度
   - Cron作业管理
   - 服务间协调

5. **monitoring-service** (端口: 8084)
   - 系统监控告警
   - 指标收集分析
   - 可视化仪表板

6. **message-broker-service** (端口: 8085)
   - 消息队列中间件
   - 事件驱动通信
   - 异步任务处理

## 🚀 快速开始

### 1. 环境准备
```bash
# 确保Python 3.8+
python --version

# 安装依赖
pip install -r requirements.txt

# 检查配置
cat config/services.yaml
```

### 2. 启动所有服务
```bash
# 使用服务管理器启动
python scripts/start_services.py

# 或者手动启动单个服务
cd services/data-storage-service
python main.py
```

### 3. 验证服务状态
```bash
# 运行集成测试
python tests/integration/test_microservices_phase1.py

# 检查健康状态
curl http://localhost:8080/health  # 存储服务
curl http://localhost:8081/health  # 调度服务
```

## 📊 服务详情

### Data Storage Service (数据存储服务)
**端口**: 8080  
**职责**: 统一数据存储管理

#### 主要API
```bash
# 存储热数据
POST /api/v1/storage/hot/trades
POST /api/v1/storage/hot/tickers
POST /api/v1/storage/hot/orderbooks

# 查询热数据
GET /api/v1/storage/hot/trades/{exchange}/{symbol}
GET /api/v1/storage/hot/tickers/{exchange}/{symbol}

# 冷数据管理
POST /api/v1/storage/cold/archive
GET /api/v1/storage/cold/trades/{exchange}/{symbol}

# 统计信息
GET /api/v1/storage/stats
```

#### 使用示例
```python
import aiohttp

# 存储交易数据
trade_data = {
    \"timestamp\": \"2025-01-30T10:00:00Z\",
    \"symbol\": \"BTCUSDT\",
    \"exchange\": \"binance\",
    \"price\": 50000.0,
    \"amount\": 0.001,
    \"side\": \"buy\",
    \"trade_id\": \"12345\"
}

async with aiohttp.ClientSession() as session:
    async with session.post(
        \"http://localhost:8080/api/v1/storage/hot/trades\",
        json=trade_data
    ) as response:
        result = await response.json()
        print(result)
```

### Scheduler Service (调度服务)
**端口**: 8081  
**职责**: 分布式任务调度

#### 主要API
```bash
# 任务管理
GET /api/v1/scheduler/tasks           # 列出所有任务
POST /api/v1/scheduler/tasks          # 创建新任务
GET /api/v1/scheduler/tasks/{id}      # 获取任务详情
PUT /api/v1/scheduler/tasks/{id}      # 更新任务
DELETE /api/v1/scheduler/tasks/{id}   # 删除任务

# 任务控制
POST /api/v1/scheduler/tasks/{id}/run     # 立即运行
POST /api/v1/scheduler/tasks/{id}/cancel  # 取消任务

# 调度器控制
GET /api/v1/scheduler/status          # 获取状态
POST /api/v1/scheduler/start          # 启动调度器
POST /api/v1/scheduler/stop           # 停止调度器
```

#### 使用示例
```python
# 创建定时任务
task_data = {
    \"name\": \"daily_cleanup\",
    \"cron_expression\": \"0 2 * * *\",  # 每天凌晨2点
    \"target_service\": \"data-storage-service\",
    \"target_endpoint\": \"/api/v1/storage/lifecycle/cleanup\",
    \"payload\": {\"retention_hours\": 72}
}

async with aiohttp.ClientSession() as session:
    async with session.post(
        \"http://localhost:8081/api/v1/scheduler/tasks\",
        json=task_data
    ) as response:
        result = await response.json()
        print(f\"Task created: {result['task_id']}\")
```

## 🔧 配置管理

### 服务配置文件
- **主配置**: `config/services.yaml`
- **环境配置**: `.env.production`, `.env.development`
- **交易所配置**: `config/exchanges/`

### 配置示例
```yaml
# config/services.yaml
data-storage-service:
  port: 8080
  storage:
    hot_storage:
      ttl_hours: 1
      max_size_mb: 1000
    cold_storage:
      ttl_days: 30
      
scheduler-service:
  port: 8081
  scheduler:
    check_interval_seconds: 30
    max_concurrent_tasks: 10
```

## 🧪 测试

### 运行测试
```bash
# Phase 1 集成测试
python tests/integration/test_microservices_phase1.py

# 单元测试
pytest tests/unit/

# 性能测试
python tests/performance/
```

### 测试覆盖
- ✅ 服务健康检查
- ✅ API功能验证
- ✅ 服务间通信
- ✅ 数据存储读写
- ✅ 任务调度执行
- ✅ 错误处理机制

## 📈 监控和运维

### 健康检查
每个服务都提供标准的健康检查端点：
```bash
curl http://localhost:{port}/health
```

### 指标收集
Prometheus格式的指标端点：
```bash
curl http://localhost:{port}/metrics
```

### 日志管理
结构化JSON日志输出，包含：
- 服务名称和版本
- 请求ID和追踪信息
- 性能指标
- 错误详情

## 🔄 服务生命周期

### 启动顺序
1. message-broker-service (消息中间件)
2. monitoring-service (监控服务)
3. data-storage-service (存储服务)
4. scheduler-service (调度服务)
5. market-data-collector (数据采集)
6. api-gateway-service (API网关)

### 优雅停止
所有服务支持SIGTERM信号的优雅停止：
```bash
# 停止单个服务
kill -TERM <pid>

# 停止所有服务
python scripts/stop_services.py
```

## 🚧 开发指南

### 添加新服务
1. 在`services/`下创建服务目录
2. 继承`BaseService`类
3. 实现必要的抽象方法
4. 添加配置到`config/services.yaml`
5. 更新服务启动脚本

### 服务间通信
- **同步通信**: HTTP REST API
- **异步通信**: NATS消息队列
- **服务发现**: 内置注册表

### 最佳实践
- 遵循单一职责原则
- 实现幂等性操作
- 添加适当的错误处理
- 提供完整的API文档
- 编写充分的测试用例

## 📚 相关文档

- [架构调整计划](../MarketPrism架构调整计划.md)
- [执行追踪](../MarketPrism架构调整执行追踪.md)
- [项目说明](../项目说明.md)
- [API文档](../docs/api/)
- [部署指南](../docs/deployment/)

## 🆘 故障排除

### 常见问题
1. **服务启动失败**: 检查端口占用和配置文件
2. **健康检查失败**: 验证依赖服务状态
3. **服务间通信失败**: 检查网络和服务发现
4. **性能问题**: 查看监控指标和日志

### 获取帮助
- 查看服务日志: `docker logs <service_name>`
- 检查健康状态: `curl http://localhost:{port}/health`
- 运行诊断测试: `python tests/integration/test_microservices_phase1.py`

---

🎉 **恭喜！** 您已成功部署MarketPrism微服务架构。这是一个现代化、可扩展、高可用的金融数据处理平台。