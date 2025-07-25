# MarketPrism IP级别速率限制实现

## 核心特性体现

本文档详细说明MarketPrism如何完全体现交易所文档中**"访问限制是基于IP的"**这一核心特性。

## 1. 交易所官方文档依据

### Binance 官方声明
> **"访问限制是基于IP的，而不是API Key"**
> - 每个请求将包含一个`X-MBX-USED-WEIGHT-(intervalNum)(intervalLetter)`的头，其中包含**当前IP**所有请求的已使用权重
> - 收到429后仍然继续违反访问限制，会被**封禁IP**，并收到418错误码
> - 频繁违反限制，**封禁时间**会逐渐延长，从最短2分钟到最长3天

### OKX 官方声明
> **"公共未经身份验证的 REST 限速基于 IP 地址"**
> - 私有 REST 限速基于 User ID（子帐户具有单独的 User ID）
> - 当请求因限速而被我们的系统拒绝时，系统会返回错误代码 50011

## 2. MarketPrism IP级别实现架构

### 2.1 核心组件

```
IP感知速率限制系统
├── IPRateLimit: IP级别限制配置
├── IPManager: 多IP管理和轮换
├── IPAwareRateLimitCoordinator: IP感知协调器
└── IP池配置和监控
```

### 2.2 IP级别数据结构

```python
@dataclass
class IPRateLimit:
    exchange: ExchangeType
    ip_address: str                    # 核心：基于IP地址的限制
    
    # Binance IP限制（直接映射官方文档）
    requests_per_minute: int = 1200    # 每IP 1200请求/分钟
    weight_per_minute: int = 6000      # 每IP 6000权重/分钟
    order_requests_per_second: int = 10 # 每IP 10订单/秒
    
    # IP状态管理
    current_requests: int              # 当前IP已用请求数
    current_weight: int                # 当前IP已用权重
    status: IPStatus                   # IP状态：活跃/警告/封禁
    ban_until: Optional[float]         # IP封禁截止时间
```

### 2.3 IP池管理

```python
class IPManager:
    """
    管理多个IP地址，实现：
    1. 基于IP的资源分配
    2. IP级别的使用统计
    3. 自动IP轮换
    4. IP封禁处理
    """
    
    async def get_current_ip(self) -> str:
        """选择当前可用的IP地址"""
        
    async def can_make_request(self, weight: int) -> Tuple[bool, str, str]:
        """检查特定IP是否可以发出请求"""
        
    async def handle_exchange_response(self, status_code: int, headers: Dict, ip: str):
        """处理交易所返回的IP级别响应头"""
```

## 3. IP级别限制的具体体现

### 3.1 请求许可检查

```python
async def acquire_permit(self, exchange, request_type, weight=1):
    """
    完全基于IP的许可检查流程：
    
    1. 获取当前可用IP地址
    2. 检查该IP的当前使用情况
    3. 验证IP级别的权重和频率限制
    4. 如果IP达到限制，自动切换到备用IP
    5. 记录IP级别的使用统计
    """
    
    # 1. IP级别检查
    can_request, ip, reason = await self.ip_manager.can_make_request(weight, exchange)
    
    if not can_request:
        # 2. 尝试IP轮换
        if self.ip_manager.config.auto_rotation:
            await self.ip_manager._rotate_ip()
            can_request, ip, reason = await self.ip_manager.can_make_request(weight, exchange)
    
    # 3. 消费IP级别的资源
    if can_request:
        await self.ip_manager.consume_request(weight, is_order, ip)
    
    return {
        "granted": can_request,
        "ip_address": ip,          # 明确标识使用的IP
        "reason": reason
    }
```

### 3.2 交易所响应处理

```python
async def handle_exchange_response(self, status_code: int, headers: Dict[str, str], ip: str):
    """
    处理交易所返回的IP级别信息：
    
    1. 解析 X-MBX-USED-WEIGHT-1M 头部（Binance IP权重）
    2. 处理 429 响应（IP级别速率限制）
    3. 处理 418 响应（IP封禁）
    4. 更新IP级别的使用统计
    """
    
    if status_code == 429:
        # IP级别的速率限制
        ip_limit.handle_429_response(retry_after)
        
    elif status_code == 418:
        # IP被封禁
        ip_limit.handle_418_response(retry_after)
        # 触发自动IP轮换
        await self._rotate_ip()
    
    # 更新IP级别的权重统计
    for header_name, header_value in headers.items():
        if header_name.startswith('X-MBX-USED-WEIGHT-'):
            used_weight = int(header_value)
            # 更新IP级别的权重使用情况
```

### 3.3 多服务共享IP限制

```python
# 示例：多个MarketPrism服务共享同一IP的限制
async def multi_service_demo():
    """
    演示同一IP下多个服务的请求如何共享限制：
    
    - 数据采集器：60请求/分钟
    - 交易执行器：30请求/分钟  
    - 监控服务：20请求/分钟
    
    总计：110请求/分钟 < Binance的1200请求/分钟限制
    但所有服务共享同一IP的6000权重/分钟限制
    """
    
    coordinator = await create_ip_aware_coordinator("203.0.113.1")
    
    # 服务1：数据采集器
    result1 = await coordinator.acquire_permit("binance", "rest_public", weight=1)
    print(f"数据采集器 IP: {result1['ip_address']}")
    
    # 服务2：交易执行器（同一IP）
    result2 = await coordinator.acquire_permit("binance", "order", weight=1)  
    print(f"交易执行器 IP: {result2['ip_address']}")  # 相同IP
    
    # 服务3：监控服务（同一IP）
    result3 = await coordinator.acquire_permit("binance", "rest_public", weight=10)
    print(f"监控服务 IP: {result3['ip_address']}")    # 相同IP
    
    # 验证：所有服务使用同一IP，共享IP级别的限制
    assert result1['ip_address'] == result2['ip_address'] == result3['ip_address']
```

## 4. IP级别监控和统计

### 4.1 IP状态实时监控

```python
async def get_ip_status_summary(self) -> Dict[str, Any]:
    """
    返回详细的IP级别状态信息：
    
    - 每个IP的当前使用情况
    - IP级别的权重和请求计数
    - IP封禁状态和剩余时间
    - IP切换事件统计
    """
    
    return {
        "current_ip": self.current_ip,
        "ip_details": {
            "203.0.113.1": {
                "status": "active",
                "current_requests": 150,
                "max_requests": 1200,
                "current_weight": 800,
                "max_weight": 6000,
                "utilization_requests": 0.125,  # 12.5%
                "utilization_weight": 0.133,    # 13.3%
                "warning_count": 0,
                "is_banned": False
            }
        }
    }
```

### 4.2 IP级别告警

```yaml
# IP级别告警配置
monitoring:
  alerts:
    ip_utilization_warning: 0.7      # IP使用率70%告警
    ip_utilization_critical: 0.9     # IP使用率90%严重告警
    ip_ban_incident: true            # IP被封立即告警
    consecutive_ip_failures: 5       # 连续IP失败告警
```

## 5. 实际使用场景

### 5.1 单IP多服务场景

```python
# 场景：单个服务器IP部署多个MarketPrism服务
coordinator = await create_ip_aware_coordinator(
    primary_ip="203.0.113.1"  # 服务器的外部IP
)

# 所有服务共享这个IP的Binance限制：
# - 1200请求/分钟
# - 6000权重/分钟  
# - 10订单/秒
```

### 5.2 多IP负载均衡场景

```python
# 场景：多个IP地址进行负载均衡
coordinator = await create_ip_aware_coordinator(
    primary_ip="203.0.113.1",
    backup_ips=["203.0.113.2", "203.0.113.3", "203.0.113.4"]
)

# 好处：
# - 总限制 = 4 × 1200 = 4800请求/分钟
# - 总权重 = 4 × 6000 = 24000权重/分钟
# - IP封禁时自动切换
```

### 5.3 IP封禁处理场景

```python
# 场景：处理IP被Binance封禁的情况
async def handle_ip_ban_demo():
    coordinator = await create_ip_aware_coordinator(
        primary_ip="203.0.113.1",
        backup_ips=["203.0.113.2"]
    )
    
    # 模拟IP被封禁
    await coordinator.report_exchange_response(
        status_code=418,  # Binance IP封禁响应
        headers={"Retry-After": "3600"},  # 1小时封禁
        ip="203.0.113.1"
    )
    
    # 系统自动切换到备用IP
    new_ip = await coordinator.get_current_ip()
    assert new_ip == "203.0.113.2"
    
    # 继续正常服务，使用备用IP
    result = await coordinator.acquire_permit("binance", "rest_public")
    assert result["ip_address"] == "203.0.113.2"
```

## 6. 配置示例

### 6.1 IP池配置

```yaml
# config/core/ip_rate_limit_config.yaml
ip_pool:
  primary_ip: "203.0.113.1"
  backup_ips:
    - "203.0.113.2"
    - "203.0.113.3"
  auto_rotation:
    enabled: true
    max_warnings_per_ip: 3

exchanges:
  binance:
    rest_limits:
      requests_per_minute: 1200      # 基于IP
      weight_per_minute: 6000        # 基于IP
      order_requests_per_second: 10  # 基于IP
    
    penalties:
      warning_threshold: 0.8         # 80%时警告
      ban_duration_min: 120          # 最短封禁2分钟
      ban_duration_max: 259200       # 最长封禁3天
```

### 6.2 使用示例

```python
# 简单使用
from core.reliability.ip_aware_rate_limit_coordinator import acquire_ip_aware_permit

# 获取IP感知的API许可
result = await acquire_ip_aware_permit(
    exchange="binance",
    request_type="rest_public",
    weight=1
)

if result["granted"]:
    print(f"请求被批准，使用IP: {result['ip_address']}")
    # 发送实际的API请求...
else:
    print(f"请求被拒绝，原因: {result['reason']}")
```

## 7. 测试验证

### 7.1 IP级别限制测试

```python
def test_ip_based_rate_limiting():
    """验证IP级别的速率限制功能"""
    
    # 1. 创建IP限制
    ip_limit = IPRateLimit.create_for_binance("192.168.1.100")
    
    # 2. 测试权重限制
    ip_limit.current_weight = 5999
    can_request, reason = ip_limit.can_make_request(weight=2)
    assert not can_request
    assert "超过每分钟权重限制" in reason
    
    # 3. 测试IP封禁
    ip_limit.handle_418_response(retry_after=3600)
    assert ip_limit.is_banned()
    assert ip_limit.status == IPStatus.BANNED
```

### 7.2 多服务共享IP测试

```python
async def test_multi_service_shared_ip():
    """测试多个服务共享同一IP的限制"""
    
    coordinator = IPAwareRateLimitCoordinator(...)
    
    # 发送多个请求
    results = []
    for i in range(10):
        result = await coordinator.acquire_permit("binance", "rest_public", weight=1)
        results.append(result)
    
    # 验证：所有请求使用同一IP
    ips_used = {r["ip_address"] for r in results}
    assert len(ips_used) == 1  # 只使用了一个IP
    
    # 验证：IP级别的统计正确
    ip_limit = coordinator.ip_manager.ip_limits[list(ips_used)[0]]
    granted_count = sum(1 for r in results if r["granted"])
    assert ip_limit.current_requests == granted_count
```

## 8. 总结

MarketPrism的IP级别速率限制系统完全体现了交易所文档中"**访问限制是基于IP的**"这一核心特性：

### 8.1 完全符合交易所规则
- ✅ Binance: IP级别的1200请求/分钟、6000权重/分钟限制
- ✅ OKX: 公共API基于IP地址的限制
- ✅ 处理429(速率限制)和418(IP封禁)响应
- ✅ 解析和监控IP级别的使用统计头部

### 8.2 实现IP级别的管理
- ✅ 基于IP地址的资源分配和统计
- ✅ IP级别的令牌桶算法
- ✅ 自动IP轮换和故障转移
- ✅ IP封禁检测和处理

### 8.3 支持实际部署场景
- ✅ 单IP多服务共享限制
- ✅ 多IP负载均衡部署
- ✅ IP级别的监控和告警
- ✅ 与现有系统的平滑集成

这套系统确保MarketPrism在多进程、多服务环境下，能够正确地按照IP级别管理和分配交易所的API访问限制，避免因超出限制而导致的IP封禁风险。