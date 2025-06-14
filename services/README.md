# MarketPrism 微服务架构

MarketPrism采用微服务架构设计，每个服务负责特定的功能领域，通过标准化的API和消息队列进行通信。

## 🏗️ 服务架构

### 核心服务

#### 1. Data Collector Service (`data-collector/`)
**统一的数据采集服务**
- **功能**: 多交易所实时数据采集、OrderBook Manager、数据标准化
- **端口**: 8081
- **特性**: 
  - 支持Binance、OKX、Deribit等交易所
  - 本地订单簿维护（快照+增量更新）
  - 实时WebSocket数据流
  - REST API接口
  - 支持完整模式和微服务模式
- **API**: `/health`, `/api/v1/collector/status`, `/api/v1/orderbook/*`

#### 2. API Gateway Service (`api-gateway-service/`)
**统一API网关**
- **功能**: 请求路由、负载均衡、认证授权、限流
- **端口**: 8080
- **特性**: 
  - 服务发现和路由
  - API版本管理
  - 请求/响应转换
  - 安全策略执行

#### 3. Message Broker Service (`message-broker-service/`)
**消息队列服务**
- **功能**: NATS JetStream消息代理、流处理
- **端口**: 4222
- **特性**:
  - 高性能消息传递
  - 持久化存储
  - 消息重放
  - 集群支持

#### 4. Data Storage Service (`data-storage-service/`)
**数据存储服务**
- **功能**: ClickHouse数据写入、查询优化
- **端口**: 8083
- **特性**:
  - 高性能时序数据存储
  - 数据压缩和分区
  - 实时查询
  - 数据备份

#### 5. Monitoring Service (`monitoring-service/`)
**监控和指标服务**
- **功能**: Prometheus指标收集、Grafana可视化
- **端口**: 9090 (Prometheus), 3000 (Grafana)
- **特性**:
  - 系统性能监控
  - 业务指标统计
  - 告警管理
  - 可视化仪表板

#### 6. Scheduler Service (`scheduler-service/`)
**任务调度服务**
- **功能**: 定时任务、批处理作业
- **端口**: 8085
- **特性**:
  - Cron表达式支持
  - 任务依赖管理
  - 失败重试
  - 任务监控

### 支持服务

#### Data Archiver (`data_archiver/`)
**数据归档服务**
- **功能**: 历史数据归档、冷存储管理
- **特性**:
  - 自动数据生命周期管理
  - 压缩和归档
  - 冷热数据分离

## 🚀 快速开始

### 1. 启动所有服务
```bash
# 使用服务管理脚本
./scripts/start_all_services.sh

# 或单独启动服务
./start-data-collector.sh
./start-api-gateway.sh
./start-message-broker.sh
./start-data-storage.sh
./start-monitoring.sh
./start-scheduler.sh
```

### 2. 验证服务状态
```bash
# 检查所有服务健康状态
curl http://localhost:8080/health  # API Gateway
curl http://localhost:8081/health  # Data Collector
curl http://localhost:8083/health  # Data Storage
curl http://localhost:8085/health  # Scheduler
```

### 3. 访问监控界面
- **Grafana**: http://localhost:3000
- **Prometheus**: http://localhost:9090

## 📊 数据流架构

```
交易所API/WebSocket
        ↓
Data Collector Service (8081)
        ↓
Message Broker (NATS)
        ↓
┌─────────────────┬─────────────────┐
│                 │                 │
Data Storage     API Gateway      Monitoring
Service (8083)   Service (8080)   Service (9090)
        ↓                ↓                ↓
   ClickHouse      Client Apps      Grafana
```

## 🔧 服务配置

### 统一配置文件
- **主配置**: `config/services.yaml`
- **数据采集**: `config/collector.yaml`
- **存储配置**: `config/storage.yaml`
- **监控配置**: `config/monitoring.yaml`

### 环境变量
```bash
# 服务发现
export SERVICE_REGISTRY_URL="http://localhost:8500"

# 消息队列
export NATS_URL="nats://localhost:4222"

# 数据库
export CLICKHOUSE_URL="http://localhost:8123"

# 监控
export PROMETHEUS_URL="http://localhost:9090"
```

## 🔍 服务发现

### 注册中心
使用Consul作为服务注册中心：
- **地址**: http://localhost:8500
- **功能**: 服务注册、健康检查、配置管理

### 服务注册
每个服务启动时自动注册到Consul：
```json
{
  "name": "data-collector",
  "address": "localhost",
  "port": 8081,
  "health_check": {
    "http": "http://localhost:8081/health",
    "interval": "10s"
  }
}
```

## 📡 API标准

### 统一响应格式
```json
{
  "success": true,
  "data": {},
  "message": "操作成功",
  "timestamp": "2024-01-01T12:00:00Z",
  "request_id": "uuid"
}
```

### 错误处理
```json
{
  "success": false,
  "error": {
    "code": "INVALID_PARAMETER",
    "message": "参数无效",
    "details": {}
  },
  "timestamp": "2024-01-01T12:00:00Z",
  "request_id": "uuid"
}
```

### 健康检查标准
所有服务都实现`/health`端点：
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T12:00:00Z",
  "uptime_seconds": 3600,
  "version": "1.0.0",
  "dependencies": {
    "database": "healthy",
    "message_queue": "healthy"
  }
}
```

## 🔒 安全考虑

### 认证授权
- **JWT Token**: 用户认证
- **API Key**: 服务间认证
- **RBAC**: 基于角色的访问控制

### 网络安全
- **TLS加密**: 服务间通信
- **防火墙**: 端口访问控制
- **VPN**: 生产环境隔离

### 数据安全
- **敏感数据加密**: API密钥、密码
- **数据脱敏**: 日志和监控
- **备份加密**: 数据备份

## 📈 性能优化

### 缓存策略
- **Redis**: 热点数据缓存
- **本地缓存**: 配置和元数据
- **CDN**: 静态资源

### 负载均衡
- **API Gateway**: 请求分发
- **数据库**: 读写分离
- **消息队列**: 分区和集群

### 监控指标
- **响应时间**: P50, P95, P99
- **吞吐量**: QPS, TPS
- **错误率**: 4xx, 5xx错误
- **资源使用**: CPU, 内存, 磁盘

## 🚀 部署指南

### Docker部署
```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看状态
docker-compose ps
```

### Kubernetes部署
```bash
# 应用配置
kubectl apply -f k8s/

# 查看状态
kubectl get pods -n marketprism
```

## 📝 开发指南

### 添加新服务
1. 创建服务目录
2. 实现BaseService接口
3. 添加健康检查
4. 配置服务注册
5. 更新文档

### 服务间通信
- **同步**: HTTP/gRPC
- **异步**: NATS消息
- **数据**: ClickHouse查询

### 测试策略
- **单元测试**: 每个服务
- **集成测试**: 服务间交互
- **端到端测试**: 完整流程
- **性能测试**: 负载和压力

## 📄 许可证

MIT License - 详见项目根目录LICENSE文件