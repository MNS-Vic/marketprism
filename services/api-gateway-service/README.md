# API Gateway Service

MarketPrism微服务架构的统一API网关服务，提供统一的入口和路由管理。

## 功能特性

### 🚪 统一入口
- **请求路由**: 智能路由到后端微服务
- **服务发现**: 自动发现和管理微服务
- **负载均衡**: 支持多实例服务的负载均衡
- **协议转换**: HTTP/WebSocket请求代理

### 🔒 安全特性
- **JWT认证**: 基于JWT的用户认证
- **API密钥**: API密钥认证支持
- **CORS支持**: 跨域请求处理
- **请求验证**: 输入验证和清理

### 🛡️ 可靠性保障
- **速率限制**: 基于令牌桶的限流算法
- **熔断器**: 服务故障自动熔断
- **健康检查**: 服务健康状态监控
- **超时控制**: 请求超时和重试机制

### ⚡ 性能优化
- **响应缓存**: 智能响应缓存
- **压缩**: 响应内容压缩
- **连接池**: HTTP连接池管理
- **异步处理**: 全异步请求处理

## 快速开始

### 1. 环境准备

确保以下服务正在运行：
- 至少一个后端微服务 (如 market-data-collector)

### 2. 配置服务

编辑 `config/services.yaml`：

```yaml
api-gateway-service:
  port: 8080
  enable_auth: false
  enable_rate_limiting: true
  enable_circuit_breaker: true
  rate_limit_requests: 100
  rate_limit_window: 60
  cache_ttl: 300
  jwt_secret: "your-secret-key"
  jwt_algorithm: "HS256"
```

### 3. 启动服务

```bash
# 直接启动
cd services/api-gateway-service
python main.py

# 或使用服务管理器
cd scripts
python start_services.py --service api-gateway-service
```

### 4. 验证网关

```bash
# 健康检查
curl http://localhost:8080/health

# 网关状态
curl http://localhost:8080/api/v1/gateway/status

# 列出注册的服务
curl http://localhost:8080/api/v1/gateway/services
```

## 路由规则

### HTTP请求路由

网关使用以下路由模式：

```
http://gateway:8080/api/v1/{service_name}/{path}
```

示例：
- `GET /api/v1/market-data-collector/status` → `http://localhost:8081/api/v1/status`
- `GET /api/v1/data-storage-service/data/trades` → `http://localhost:8082/api/v1/data/trades`

### WebSocket路由

WebSocket连接使用以下模式：

```
ws://gateway:8080/ws/{service_name}/{path}
```

示例：
- `ws://gateway:8080/ws/market-data-collector/live` → `ws://localhost:8081/ws/live`

## API接口

### 网关管理

#### 获取网关状态

```http
GET /api/v1/gateway/status
```

响应：
```json
{
  "service": "api-gateway",
  "version": "1.0.0",
  "status": "running",
  "timestamp": "2024-01-01T12:00:00Z",
  "uptime": 3600,
  "config": {
    "enable_auth": false,
    "enable_rate_limiting": true,
    "enable_circuit_breaker": true,
    "cache_ttl": 300
  },
  "registered_services": 5,
  "active_circuit_breakers": 2,
  "cache_size": 10
}
```

#### 列出注册的服务

```http
GET /api/v1/gateway/services
```

响应：
```json
{
  "services": {
    "market-data-collector": {
      "host": "localhost",
      "port": 8081,
      "base_url": "http://localhost:8081",
      "healthy": true,
      "last_health_check": "2024-01-01T12:00:00Z"
    }
  },
  "total": 1
}
```

#### 注册新服务

```http
POST /api/v1/gateway/services
```

请求体：
```json
{
  "service_name": "my-service",
  "host": "localhost",
  "port": 8090,
  "health_endpoint": "/health"
}
```

#### 获取网关统计

```http
GET /api/v1/gateway/stats
```

响应：
```json
{
  "request_stats": {
    "total_requests": 1000,
    "successful_requests": 950,
    "failed_requests": 50,
    "rate_limited_requests": 20,
    "circuit_breaker_trips": 5,
    "cache_hits": 300,
    "cache_misses": 700
  },
  "circuit_breaker_stats": {
    "market-data-collector": {
      "state": "CLOSED",
      "failure_count": 0,
      "last_failure_time": null
    }
  },
  "cache_stats": {
    "size": 10,
    "hit_rate": 0.3
  }
}
```

### 认证接口

#### 用户登录

```http
POST /api/v1/auth/login
```

请求体：
```json
{
  "username": "admin",
  "password": "password"
}
```

响应：
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

#### 刷新Token

```http
POST /api/v1/auth/refresh
```

请求体：
```json
{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

## 服务发现

### 自动发现

网关在启动时自动注册以下默认服务：

- `market-data-collector` (localhost:8081)
- `data-storage-service` (localhost:8082)
- `monitoring-service` (localhost:8083)
- `scheduler-service` (localhost:8084)
- `message-broker-service` (localhost:8085)

### 手动注册

通过API动态注册新服务：

```bash
curl -X POST http://localhost:8080/api/v1/gateway/services \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "custom-service",
    "host": "localhost",
    "port": 8090
  }'
```

### 健康检查

网关每30秒检查所有注册服务的健康状态：

- 健康的服务会接收请求
- 不健康的服务会被暂时排除
- 恢复健康后自动重新加入

## 安全配置

### 启用认证

```yaml
api-gateway-service:
  enable_auth: true
  jwt_secret: "your-strong-secret-key"
  jwt_algorithm: "HS256"
```

使用Bearer Token：

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8080/api/v1/market-data-collector/status
```

### API密钥认证

```bash
curl -H "X-API-Key: YOUR_API_KEY" \
  http://localhost:8080/api/v1/market-data-collector/status
```

## 限流配置

### 基本配置

```yaml
api-gateway-service:
  enable_rate_limiting: true
  rate_limit_requests: 100  # 每个时间窗口的最大请求数
  rate_limit_window: 60     # 时间窗口（秒）
```

### 限流算法

使用令牌桶算法：
- 每个客户端有独立的令牌桶
- 客户端ID基于API密钥或IP地址
- 超出限制返回429状态码

### 响应头

限流相关的响应头：
- `X-RateLimit-Remaining`: 剩余请求次数
- `X-Gateway-Service`: 目标服务名
- `X-Gateway-Timestamp`: 网关处理时间

## 熔断器配置

### 启用熔断器

```yaml
api-gateway-service:
  enable_circuit_breaker: true
```

### 熔断器状态

- **CLOSED**: 正常状态，请求正常通过
- **OPEN**: 熔断状态，直接返回错误
- **HALF_OPEN**: 半开状态，允许少量请求测试

### 配置参数

- 失败阈值：5次连续失败触发熔断
- 恢复超时：60秒后尝试恢复
- 自动检测：基于HTTP状态码和异常

## 缓存机制

### 启用缓存

只缓存GET请求的成功响应（200状态码）。

### 缓存配置

```yaml
api-gateway-service:
  cache_ttl: 300  # 缓存生存时间（秒）
```

### 缓存键

缓存键格式：`{HTTP_METHOD}:{TARGET_URL}`

### 缓存头

- `X-Cache-Status`: HIT/MISS
- `X-Cache-TTL`: 缓存剩余时间

## 监控和日志

### Prometheus指标

```http
GET /metrics
```

主要指标：
- `gateway_requests_total`: 总请求数
- `gateway_requests_duration`: 请求处理时间
- `gateway_cache_hits_total`: 缓存命中数
- `gateway_circuit_breaker_state`: 熔断器状态

### 结构化日志

```json
{
  "timestamp": "2024-01-01T12:00:00Z",
  "level": "INFO",
  "logger": "api-gateway",
  "message": "Request proxied successfully",
  "service": "market-data-collector",
  "method": "GET",
  "path": "/api/v1/status",
  "duration_ms": 150,
  "status": 200
}
```

## WebSocket代理

### 连接建立

```javascript
const ws = new WebSocket('ws://localhost:8080/ws/market-data-collector/live');

ws.onopen = function() {
  console.log('Connected to market data service');
};

ws.onmessage = function(event) {
  const data = JSON.parse(event.data);
  console.log('Received:', data);
};
```

### 双向通信

网关支持双向WebSocket消息转发：
- 客户端 → 网关 → 目标服务
- 目标服务 → 网关 → 客户端

### 连接管理

- 自动重连：目标服务断开时自动重连
- 错误处理：连接错误时返回相应状态
- 超时控制：连接超时自动关闭

## 错误处理

### 常见错误码

- `400`: 请求格式错误
- `401`: 认证失败
- `429`: 请求频率超限
- `503`: 服务不可用
- `504`: 网关超时

### 错误响应格式

```json
{
  "error": "Service temporarily unavailable",
  "code": "SERVICE_UNAVAILABLE",
  "timestamp": "2024-01-01T12:00:00Z",
  "request_id": "req-123456"
}
```

## 故障排除

### 常见问题

1. **服务不可用 (503)**
   - 检查目标服务是否运行
   - 检查服务注册信息
   - 查看健康检查日志

2. **请求被限流 (429)**
   - 调整限流配置
   - 检查客户端请求频率
   - 使用API密钥获得更高限额

3. **熔断器触发 (503)**
   - 检查目标服务健康状态
   - 等待熔断器自动恢复
   - 手动重启有问题的服务

### 调试命令

```bash
# 检查网关状态
curl http://localhost:8080/api/v1/gateway/status | jq

# 检查服务列表
curl http://localhost:8080/api/v1/gateway/services | jq

# 检查统计信息
curl http://localhost:8080/api/v1/gateway/stats | jq

# 查看Prometheus指标
curl http://localhost:8080/metrics
```

## 配置参考

### 完整配置示例

```yaml
api-gateway-service:
  # 基本配置
  port: 8080
  
  # 认证配置
  enable_auth: false
  jwt_secret: "your-secret-key-here"
  jwt_algorithm: "HS256"
  
  # 限流配置
  enable_rate_limiting: true
  rate_limit_requests: 100
  rate_limit_window: 60
  
  # 熔断器配置
  enable_circuit_breaker: true
  
  # 缓存配置
  cache_ttl: 300
  
  # 服务配置
  services:
    market-data-collector:
      host: "localhost"
      port: 8081
    data-storage-service:
      host: "localhost"
      port: 8082
```

## 部署指南

### Docker部署

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8080

CMD ["python", "main.py"]
```

### Kubernetes部署

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-gateway
spec:
  replicas: 2
  selector:
    matchLabels:
      app: api-gateway
  template:
    metadata:
      labels:
        app: api-gateway
    spec:
      containers:
      - name: api-gateway
        image: marketprism/api-gateway:latest
        ports:
        - containerPort: 8080
        env:
        - name: ENABLE_AUTH
          value: "true"
        - name: JWT_SECRET
          valueFrom:
            secretKeyRef:
              name: jwt-secret
              key: secret
```

### 生产环境配置

```yaml
api-gateway-service:
  # 启用所有安全特性
  enable_auth: true
  enable_rate_limiting: true
  enable_circuit_breaker: true
  
  # 更严格的限流
  rate_limit_requests: 50
  rate_limit_window: 60
  
  # 更短的缓存时间
  cache_ttl: 60
  
  # 强密钥
  jwt_secret: "${JWT_SECRET}"
  
  # 日志级别
  log_level: "WARNING"
```

## 相关服务

- **Market Data Collector**: 数据采集服务
- **Data Storage Service**: 数据存储服务
- **Monitoring Service**: 监控服务
- **Message Broker Service**: 消息代理服务

## 支持

如有问题或建议，请查看：
- 项目文档: `docs/`
- 问题追踪: GitHub Issues  
- 联系团队: team@marketprism.com