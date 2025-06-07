# MarketPrism 统一API代理使用指南

## 🎯 解决的核心问题

**问题**：多个MarketPrism服务独立调用交易所API，容易触发速率限制(429)和IP封禁(418)
**解决方案**：统一收口所有API请求，智能管理IP资源和权重分配

## ✨ 核心特性

### 1. **零侵入集成**
```python
# 方式1: 一行代码替换
from core.networking.exchange_api_proxy import proxy_request
result = await proxy_request("binance", "GET", "/api/v3/ping")

# 方式2: 装饰器方式
@use_api_proxy("binance")
async def get_ticker(session):
    async with session.get("/api/v3/ticker/24hr") as response:
        return await response.json()

# 方式3: 全局代理（现有代码完全不用改）
enable_global_proxy()
```

### 2. **智能IP管理**
- 🤖 **自动模式**：单IP环境自动统一管理
- 🔄 **分布式模式**：多IP环境智能负载均衡
- 🏥 **健康监控**：IP健康分数和故障自动切换

### 3. **精确权重控制**
- 📊 **动态计算**：根据官方文档精确计算请求权重
- ⚖️ **智能分配**：按优先级和服务重要性分配权重
- 🛡️ **预防机制**：80%阈值预警，95%停止请求

### 4. **优雅错误处理**
- ⚠️ **429处理**：自动重试+指数退避+IP切换
- 🚫 **418处理**：IP封禁检测+自动切换+恢复等待
- 📊 **实时监控**：错误率分析+性能指标+优化建议

## 🚀 快速开始

### 1. 最简单使用
```python
from core.networking.exchange_api_proxy import proxy_request

# 自动处理所有复杂逻辑
try:
    result = await proxy_request("binance", "GET", "/api/v3/ticker/24hr", {"symbol": "BTCUSDT"})
    print(f"BTC价格: {result['lastPrice']}")
except Exception as e:
    print(f"请求失败: {e}")
```

### 2. 高级配置
```python
from core.networking.exchange_api_proxy import ExchangeAPIProxy

# 多IP分布式模式
proxy = ExchangeAPIProxy.distributed_mode([
    "192.168.1.100",  # 服务器1
    "192.168.1.101",  # 服务器2
    "192.168.1.102"   # 服务器3
])

# 并发请求自动负载均衡
results = await asyncio.gather(*[
    proxy.request("binance", "GET", "/api/v3/ticker/price", {"symbol": sym})
    for sym in ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
])
```

### 3. 监控和诊断
```python
# 获取实时状态
status = proxy.get_status()
print(f"可用IP: {status['available_ips']}/{status['total_ips']}")
print(f"成功率: {status['recent_success_rate']}")

# 健康报告
health = proxy.get_health_report()
print(f"系统健康: {health['overall_health']}")
print(f"优化建议: {health['recommendations']}")
```

## 🏗️ 架构优势

### **智能模式切换**
```
环境检测 → 自动选择最优模式
├── 单IP环境 → 统一代理模式
└── 多IP环境 → 分布式负载均衡
```

### **请求流程**
```
业务请求 → 权重计算 → IP选择 → 限制检查 → 发送请求 → 错误处理 → 统计更新
```

### **超限处理流程**
```
429警告 → 解析retry_after → 等待/切换IP → 更新健康分数 → 继续服务
418封禁 → 封禁时间解析 → IP标记不可用 → 切换备用IP → 等待恢复
```

## 📊 监控指标

### **关键指标**
- **成功率**：最近请求成功率
- **响应时间**：平均API响应时间
- **权重使用率**：各IP权重消耗情况
- **错误分布**：429/418/其他错误统计
- **IP健康分数**：IP可用性评分

### **告警机制**
- ⚠️ 权重使用率超过80%
- 🚫 IP被封禁
- 📈 错误率超过10%
- ⏱️ 响应时间异常

## 🔧 配置说明

### **基础配置** (`config/core/api_proxy_config.yaml`)
```yaml
proxy_settings:
  mode: "auto"  # auto, unified, distributed
  auto_detect_ip: true

rate_limit_handling:
  warning_response:
    enable_auto_retry: true
    max_retries: 3
    backoff_strategy: "exponential"
    
  ban_response:
    enable_ip_rotation: true
    fallback_to_other_ips: true
```

### **环境配置**
```yaml
# 单IP环境
ip_resources:
  single_ip:
    - ip: "auto-detect"
      max_weight_per_minute: 6000

# 多IP环境      
ip_resources:
  multi_ip:
    - ip: "192.168.1.100"
      location: "server-1"
    - ip: "192.168.1.101"  
      location: "server-2"
```

## 📈 性能优化

### **最佳实践**
1. **批量请求**：尽量使用批量API减少请求数
2. **缓存策略**：缓存不变数据(exchangeInfo等)
3. **WebSocket优先**：实时数据优先使用WebSocket
4. **权重预算**：为不同服务分配权重预算
5. **错误处理**：合理处理429/418，避免级联失败

### **优化建议**
- 🔄 **连接复用**：使用连接池减少建连开销
- ⚡ **并发控制**：限制同时请求数避免突发流量
- 📊 **智能调度**：根据API重要性和延迟要求调度
- 🎯 **精确权重**：使用官方权重表避免浪费

## 🛡️ 故障处理

### **常见问题**
| 问题 | 症状 | 解决方案 |
|------|------|----------|
| IP权重耗尽 | 大量请求被拒绝 | 添加更多IP或降低请求频率 |
| 单点IP封禁 | 特定IP无法访问 | 自动切换到其他IP |
| 网络不稳定 | 响应时间异常 | 健康检查+自动降级 |
| 配置错误 | 代理启动失败 | 检查配置文件和依赖 |

### **恢复策略**
- **自动恢复**：IP封禁自动解除后恢复使用
- **降级服务**：部分IP不可用时降低请求频率
- **故障隔离**：问题IP自动隔离避免影响整体
- **人工干预**：提供手动切换和恢复机制

## 📝 集成示例

查看完整示例：`examples/api_proxy_example.py`

这个优雅的解决方案让您无需担心复杂的速率限制问题，专注于业务逻辑开发！

## 🎯 总结

**MarketPrism统一API代理**通过简单优雅的设计解决了分布式环境下的交易所API管理难题：

✅ **零侵入**：现有代码无需修改
✅ **智能化**：自动检测环境和错误处理  
✅ **可靠性**：多IP冗余和故障切换
✅ **可观测**：完整的监控和诊断
✅ **高性能**：精确权重控制和连接复用

让复杂的分布式速率限制变得如同单机一样简单！