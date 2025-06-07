# API网关服务 (api-gateway-service) 详解

## 🎯 核心作用

API网关是系统的**"统一大门"**，所有外部请求都必须通过它才能访问内部服务。就像酒店的前台一样，负责接待客人、验证身份、引导方向。

## 🏢 形象比喻

想象MarketPrism是一个大型办公楼：

```
外部用户 → API网关(前台) → 内部服务(各部门)
                ↓
         - 验证访客身份
         - 引导到正确部门  
         - 记录访问日志
         - 控制访问频率
```

## 📋 主要功能

### 1. 统一入口点 🚪
**问题**：没有网关时，客户端需要知道每个服务的地址
```python
# 客户端直接调用各服务 (混乱)
market_data = requests.get("http://collector:8001/api/market-data")
storage_data = requests.get("http://storage:8002/api/historical-data") 
monitoring = requests.get("http://monitor:8003/api/metrics")
```

**解决**：通过网关统一访问
```python
# 客户端只需要知道网关地址 (简洁)
market_data = requests.get("http://gateway:8000/api/market-data")
storage_data = requests.get("http://gateway:8000/api/historical-data")
monitoring = requests.get("http://gateway:8000/api/metrics")
```

### 2. 智能路由 🧭
**功能**：根据请求路径自动转发到对应服务
```yaml
路由规则:
  /api/market-data/*     → market-data-collector
  /api/storage/*         → data-storage-service  
  /api/monitor/*         → monitoring-service
  /api/schedule/*        → scheduler-service
```

**代码实现**：
```python
class APIGateway:
    def __init__(self):
        self.routes = {
            r'/api/market-data/(.*)': 'http://market-data-collector:8001',
            r'/api/storage/(.*)': 'http://data-storage-service:8002',
            r'/api/monitor/(.*)': 'http://monitoring-service:8003',
        }
    
    async def route_request(self, path: str, request: Request):
        for pattern, target_service in self.routes.items():
            if re.match(pattern, path):
                # 转发请求到目标服务
                return await self._forward_request(target_service, request)
```

### 3. 认证和授权 🔐
**功能**：验证用户身份和访问权限
```python
class AuthenticationMiddleware:
    async def authenticate(self, request: Request):
        # 1. 验证API Key
        api_key = request.headers.get('X-API-KEY')
        if not api_key:
            raise HTTPException(401, "Missing API Key")
        
        # 2. 检查权限
        user_permissions = await self.get_user_permissions(api_key)
        required_permission = self.get_required_permission(request.path)
        
        if required_permission not in user_permissions:
            raise HTTPException(403, "Permission Denied")
        
        return user_info

# 权限配置示例
permissions = {
    'read_market_data': ['/api/market-data/ticker', '/api/market-data/depth'],
    'read_historical': ['/api/storage/historical/*'],
    'admin_access': ['/api/monitor/*', '/api/schedule/*']
}
```

### 4. 限流和熔断 ⚡
**功能**：防止系统过载，保护后端服务
```python
class RateLimiter:
    def __init__(self):
        self.limits = {
            'basic_user': {'requests_per_minute': 1000},
            'premium_user': {'requests_per_minute': 10000},
            'enterprise_user': {'requests_per_minute': 100000}
        }
    
    async def check_rate_limit(self, user_tier: str, user_id: str):
        current_requests = await self.redis.get(f"rate_limit:{user_id}")
        limit = self.limits[user_tier]['requests_per_minute']
        
        if current_requests and int(current_requests) >= limit:
            raise HTTPException(429, "Rate limit exceeded")

class CircuitBreaker:
    async def call_service(self, service_url: str, request: Request):
        """熔断器保护"""
        if self.is_circuit_open(service_url):
            # 服务故障，返回缓存或降级响应
            return await self.get_fallback_response(request)
        
        try:
            response = await self.http_client.request(service_url, request)
            self.record_success(service_url)
            return response
        except Exception as e:
            self.record_failure(service_url)
            raise
```

### 5. 协议转换 🔄
**功能**：统一外部接口，隐藏内部复杂性
```python
class ProtocolAdapter:
    async def convert_request(self, external_request: Request):
        """将外部REST请求转换为内部gRPC调用"""
        if external_request.path.startswith('/api/market-data'):
            # REST → gRPC转换
            grpc_request = await self._rest_to_grpc(external_request)
            response = await self.grpc_client.call(grpc_request)
            return await self._grpc_to_rest(response)
        
        # 其他协议转换...
```

### 6. 负载均衡 ⚖️
**功能**：将请求分散到多个服务实例
```python
class LoadBalancer:
    def __init__(self):
        self.service_instances = {
            'market-data-collector': [
                'http://collector-1:8001',
                'http://collector-2:8001', 
                'http://collector-3:8001'
            ]
        }
        self.strategy = 'round_robin'  # 轮询策略
    
    def get_service_instance(self, service_name: str):
        instances = self.service_instances[service_name]
        if self.strategy == 'round_robin':
            return self._round_robin_select(instances)
        elif self.strategy == 'least_connections':
            return self._least_connections_select(instances)
```

### 7. 监控和日志 📊
**功能**：记录所有API调用，生成监控指标
```python
class GatewayMonitoring:
    async def log_request(self, request: Request, response: Response):
        log_entry = {
            'timestamp': datetime.utcnow(),
            'method': request.method,
            'path': request.url.path,
            'user_id': request.headers.get('X-User-ID'),
            'response_time': response.processing_time,
            'status_code': response.status_code,
            'response_size': len(response.content)
        }
        
        # 发送到监控服务
        await self.send_to_monitoring(log_entry)
    
    def collect_metrics(self):
        return {
            'total_requests': self.request_counter,
            'requests_per_second': self.calculate_rps(),
            'average_response_time': self.calculate_avg_response_time(),
            'error_rate': self.calculate_error_rate(),
            'top_endpoints': self.get_top_endpoints()
        }
```

## 🏦 在MarketPrism中的具体应用

### 1. 市场数据API
```python
# 外部用户调用
GET /api/market-data/ticker/BTCUSDT
→ 网关路由到 market-data-collector
→ 返回实时价格数据

GET /api/market-data/depth/ETHUSDT?limit=100  
→ 网关路由到 market-data-collector
→ 返回订单簿深度数据
```

### 2. 历史数据查询
```python
# 外部用户调用
GET /api/storage/historical/BTCUSDT?start=2024-01-01&end=2024-01-31
→ 网关验证权限 (需要historical_data权限)
→ 路由到 data-storage-service
→ 内部智能查询热存储+冷存储
→ 返回历史K线数据
```

### 3. 系统监控接口
```python
# 管理员调用
GET /api/monitor/metrics
→ 网关验证管理员权限
→ 路由到 monitoring-service  
→ 返回系统性能指标

GET /api/monitor/health
→ 网关聚合所有服务健康状态
→ 返回整体系统健康报告
```

### 4. 任务调度管理
```python
# 管理员调用
POST /api/schedule/tasks
→ 网关验证管理员权限
→ 路由到 scheduler-service
→ 创建新的定时任务

GET /api/schedule/tasks/status
→ 返回所有任务执行状态
```

## 🔧 技术实现架构

### 网关核心组件
```python
class MarketPrismGateway:
    def __init__(self):
        # 核心组件
        self.router = RequestRouter()
        self.auth = AuthenticationMiddleware()
        self.rate_limiter = RateLimiter()
        self.circuit_breaker = CircuitBreaker()
        self.load_balancer = LoadBalancer()
        self.monitor = GatewayMonitoring()
        
        # 服务发现
        self.service_registry = ServiceRegistry()
        
    async def handle_request(self, request: Request):
        try:
            # 1. 认证和授权
            user_info = await self.auth.authenticate(request)
            
            # 2. 限流检查
            await self.rate_limiter.check_rate_limit(user_info.tier, user_info.id)
            
            # 3. 路由决策
            target_service = await self.router.resolve_service(request.path)
            
            # 4. 负载均衡
            service_instance = self.load_balancer.get_service_instance(target_service)
            
            # 5. 熔断保护
            response = await self.circuit_breaker.call_service(service_instance, request)
            
            # 6. 监控记录
            await self.monitor.log_request(request, response)
            
            return response
            
        except Exception as e:
            await self.monitor.log_error(request, e)
            return self._error_response(e)
```

### 配置示例
```yaml
# API网关配置
gateway:
  port: 8000
  
  # 路由配置
  routes:
    - path: "/api/market-data/*"
      service: "market-data-collector"
      timeout: 5s
      
    - path: "/api/storage/*"
      service: "data-storage-service"  
      timeout: 30s
      
    - path: "/api/monitor/*"
      service: "monitoring-service"
      auth_required: true
      roles: ["admin"]
      
  # 限流配置
  rate_limits:
    basic: 1000/min
    premium: 10000/min
    enterprise: 100000/min
    
  # 熔断配置
  circuit_breaker:
    failure_threshold: 5
    timeout: 60s
```

## 💡 为什么需要API网关？

### 没有网关的问题 ❌
```
客户端 → 直接调用各个服务
├── 需要知道每个服务的地址 (复杂)
├── 每个服务都要实现认证 (重复)
├── 没有统一的监控 (盲区)
├── 难以进行限流控制 (风险)
└── 服务变更影响客户端 (耦合)
```

### 有网关的优势 ✅
```
客户端 → API网关 → 内部服务
├── 统一入口，简化客户端 (简单)
├── 集中认证和授权 (安全)  
├── 统一监控和日志 (可观测)
├── 统一限流和熔断 (稳定)
└── 服务变更对客户端透明 (解耦)
```

## 🚀 部署和扩展

### 高可用部署
```yaml
# 网关集群部署
api-gateway-cluster:
  replicas: 3                    # 3个网关实例
  load_balancer: nginx           # 前置负载均衡器
  
  instances:
    - gateway-1: 192.168.1.10:8000
    - gateway-2: 192.168.1.11:8000  
    - gateway-3: 192.168.1.12:8000
```

### 性能优化
```python
# 连接池优化
gateway_config = {
    'connection_pool_size': 1000,
    'connection_timeout': 30,
    'read_timeout': 60,
    'max_concurrent_requests': 10000
}

# 缓存优化
cache_config = {
    'response_cache_ttl': 60,      # 响应缓存1分钟
    'auth_cache_ttl': 300,         # 认证缓存5分钟
    'route_cache_ttl': 3600        # 路由缓存1小时
}
```

## 总结

**API网关是MarketPrism的"智能前台"**：

✅ **统一入口**：客户端只需要知道一个地址
✅ **安全守护**：统一认证、授权、限流
✅ **智能路由**：自动转发请求到正确服务
✅ **稳定保障**：熔断保护、负载均衡  
✅ **可观测性**：统一监控、日志、指标
✅ **简化运维**：协议转换、版本管理

**它让复杂的微服务架构对外呈现为一个简单统一的API！** 🎯