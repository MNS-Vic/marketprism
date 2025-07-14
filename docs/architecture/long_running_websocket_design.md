# 长期运行WebSocket设计文档

## 🎯 **设计目标**

MarketPrism数据收集器需要7x24小时不间断运行，可能持续数月甚至一年。为了应对各交易所WebSocket连接的自动断开机制，我们实现了完整的长期运行WebSocket架构。

## 📋 **交易所WebSocket限制**

### **Binance官方限制**：
- **连接超时**: 24小时后自动断开连接
- **Ping/Pong**: 每20秒发送ping，60秒内必须收到pong
- **重连要求**: 必须实现自动重连机制
- **订阅恢复**: 重连后URL中的订阅自动恢复

### **OKX官方限制**：
- **连接超时**: 30秒无数据自动断开
- **Ping/Pong**: 客户端每25秒发送ping
- **重连要求**: 必须实现指数退避重连
- **订阅恢复**: 重连后需要重新发送订阅请求

## 🏗️ **长期运行架构设计**

### **核心组件**

```
┌─────────────────────────────────────────────────────────────┐
│                    连接监控层 (Connection Monitor)           │
├─────────────────────────────────────────────────────────────┤
│  - 连接健康检查                                             │
│  - 自动重连管理                                             │
│  - 指数退避策略                                             │
│  - 订阅状态恢复                                             │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                  WebSocket连接层 (Connection Layer)          │
├─────────────────────────────────────────────────────────────┤
│  - 统一连接管理                                             │
│  - Ping/Pong处理                                            │
│  - 消息路由分发                                             │
│  - 连接状态跟踪                                             │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   数据处理层 (Data Processing)               │
├─────────────────────────────────────────────────────────────┤
│  - OrderBook Manager                                        │
│  - Trade Manager                                            │
│  - 数据标准化                                               │
│  - NATS消息发布                                             │
└─────────────────────────────────────────────────────────────┘
```

## 🔧 **核心功能实现**

### **1. 自动重连机制**

```python
# WebSocket配置
@dataclass
class WebSocketConfig:
    # 长期运行配置
    auto_reconnect: bool = True
    max_reconnect_attempts: int = -1  # -1表示无限重连
    reconnect_delay: float = 1.0  # 初始重连延迟（秒）
    max_reconnect_delay: float = 300.0  # 最大重连延迟（秒）
    backoff_multiplier: float = 2.0  # 退避倍数
    connection_timeout: int = 86400  # 连接超时时间（秒）
```

**重连策略**：
- **指数退避**: 1s → 2s → 4s → 8s → ... → 300s (最大)
- **无限重连**: 永不放弃，确保长期稳定性
- **智能延迟**: 避免频繁重连对服务器造成压力

### **2. 连接健康监控**

```python
async def _is_connection_healthy(self, connection_id: str) -> bool:
    """检查连接健康状态"""
    # 检查连接是否关闭
    if connection.closed:
        return False
    
    # 检查最后消息时间（超过5分钟认为异常）
    if time.time() - last_msg_time > 300:
        return False
    
    return True
```

**监控指标**：
- **连接状态**: 检查WebSocket连接是否关闭
- **消息活跃度**: 监控最后消息接收时间
- **Ping/Pong响应**: 确保心跳机制正常
- **定期检查**: 每30秒执行一次健康检查

### **3. 订阅状态恢复**

```python
async def _restore_subscriptions(self, connection_id: str):
    """重连后恢复所有订阅"""
    subscriptions = self.subscriptions.get(connection_id, [])
    
    for subscription in subscriptions:
        if subscription.exchange.lower() == "okx":
            # OKX需要重新发送订阅请求
            await self._send_okx_subscription(connection_id, subscription)
        # Binance的订阅在URL中，重连后自动恢复
```

**恢复策略**：
- **Binance**: URL中包含订阅信息，重连后自动恢复
- **OKX**: 需要重新发送所有订阅请求
- **状态保持**: 维护完整的订阅状态列表
- **错误处理**: 订阅失败时的重试机制

### **4. 消息时间戳跟踪**

```python
async def route_message(self, connection_key: str, message: Dict[str, Any]):
    """路由消息并更新时间戳"""
    # 更新最后消息时间（用于连接健康检查）
    self.last_message_time[connection_key] = time.time()
    
    # 路由消息到订阅回调
    await self._route_to_callbacks(connection_key, message)
```

**时间戳用途**：
- **健康检查**: 判断连接是否活跃
- **性能监控**: 跟踪消息接收频率
- **异常检测**: 识别连接异常情况

## 📊 **长期运行统计**

### **连接统计**
```python
routing_stats = {
    'total_messages': 0,        # 总消息数
    'routed_messages': 0,       # 成功路由消息数
    'unrouted_messages': 0,     # 未路由消息数
    'callback_errors': 0,       # 回调错误数
    'reconnections': 0,         # 重连次数
    'connection_failures': 0    # 连接失败次数
}
```

### **监控指标**
- **连接稳定性**: 重连频率和成功率
- **消息处理**: 消息接收和处理统计
- **错误率**: 连接失败和回调错误统计
- **性能指标**: 消息延迟和处理速度

## 🚀 **使用方式**

### **1. 启用长期运行模式**

```python
# 创建支持长期运行的WebSocket适配器
adapter = WebSocketAdapter(
    exchange=Exchange.BINANCE,
    market_type=MarketType.SPOT,
    symbols=["BTCUSDT"]
)

# 连接会自动启用长期运行功能
await adapter.connect()
```

### **2. 配置重连参数**

```yaml
# config/collector/unified_data_collection.yaml
networking:
  websocket:
    auto_reconnect: true
    max_reconnect_attempts: -1  # 无限重连
    reconnect_delay: 1.0
    max_reconnect_delay: 300.0
    backoff_multiplier: 2.0
```

### **3. 监控连接状态**

```python
# 获取连接统计
stats = websocket_manager.get_connection_stats()
print(f"重连次数: {stats['routing_stats']['reconnections']}")
print(f"活跃连接: {stats['active_connections']}")
```

## 🔍 **故障排除**

### **常见问题**

1. **频繁重连**
   - 检查网络稳定性
   - 验证交易所API状态
   - 调整重连延迟参数

2. **订阅丢失**
   - 确认订阅恢复逻辑
   - 检查交易所订阅格式
   - 验证符号格式正确性

3. **消息延迟**
   - 监控消息处理性能
   - 检查回调函数效率
   - 优化数据处理逻辑

### **调试方法**

```python
# 启用详细日志
import structlog
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.dev.ConsoleRenderer(colors=True)
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

# 设置日志级别为DEBUG
import logging
logging.getLogger().setLevel(logging.DEBUG)
```

## 📈 **性能优化**

### **连接优化**
- **连接复用**: 一个连接支持多种数据类型
- **智能重连**: 避免不必要的重连操作
- **资源管理**: 及时清理断开的连接

### **内存优化**
- **状态清理**: 定期清理过期的连接状态
- **缓存管理**: 合理控制消息缓存大小
- **垃圾回收**: 避免内存泄漏

### **网络优化**
- **代理支持**: 智能代理配置和切换
- **SSL优化**: 根据环境优化SSL配置
- **超时设置**: 合理的超时和重试参数

## ✅ **验证测试**

### **长期运行测试**
- **持续时间**: 建议至少运行24小时
- **重连测试**: 模拟网络中断和恢复
- **负载测试**: 验证高频消息处理能力
- **稳定性测试**: 检查内存和CPU使用情况

### **故障恢复测试**
- **网络中断**: 测试网络断开后的自动恢复
- **服务器重启**: 验证交易所服务重启后的重连
- **配置变更**: 测试热重载配置的影响

## 🎯 **总结**

长期运行WebSocket架构成功解决了以下关键问题：

✅ **自动重连**: 无限重连确保长期稳定性  
✅ **健康监控**: 实时监控连接状态和消息活跃度  
✅ **订阅恢复**: 重连后自动恢复所有数据订阅  
✅ **指数退避**: 智能重连策略避免服务器压力  
✅ **状态跟踪**: 完整的连接和消息统计  
✅ **错误处理**: 全面的异常处理和恢复机制  

这个架构确保MarketPrism数据收集器能够7x24小时稳定运行，满足长期数据收集的需求。
