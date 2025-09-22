# 统一WebSocket架构文档

## 🎯 **架构概述**

MarketPrism项目已成功实现统一WebSocket架构重构，实现了WebSocket连接管理和数据处理的职责分离，提供了更好的代码复用性、可扩展性和维护性。

## 🏗️ **架构设计**

### **核心原则**
- **职责分离**：WebSocket连接管理 vs 数据处理逻辑
- **代码复用**：统一的WebSocket连接管理器
- **可扩展性**：易于添加新的交易所和数据类型
- **向后兼容**：保持现有功能完全可用

### **架构层次**

```
┌─────────────────────────────────────────────────────────────┐
│                    应用层 (Application Layer)                │
├─────────────────────────────────────────────────────────────┤
│  统一数据收集器 (UnifiedDataCollector)                      │
│  - 配置驱动启动                                             │
│  - 多交易所管理                                             │
│  - NATS消息发布                                             │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   数据处理层 (Data Processing Layer)         │
├─────────────────────────────────────────────────────────────┤
│  OrderBook Manager                                          │
│  - 订单簿特定处理逻辑                                       │
│  - Binance官方8步算法                                       │
│  - 快照同步和验证                                           │
│  - 数据标准化                                               │
│                                                             │
│  WebSocket Adapter                                          │
│  - 适配现有OrderBook Manager                                │
│  - 保持向后兼容性                                           │
│  - 消息路由和回调                                           │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                 网络连接层 (Network Connection Layer)        │
├─────────────────────────────────────────────────────────────┤
│  core/networking/                                           │
│                                                             │
│  WebSocketConnectionManager                                 │
│  - 统一WebSocket连接管理                                    │
│  - 多数据类型订阅和分发                                     │
│  - 消息路由机制                                             │
│  - 连接状态监控                                             │
│                                                             │
│  NetworkConnectionManager                                   │
│  - HTTP会话管理                                             │
│  - 代理配置管理                                             │
│  - SSL/TLS配置                                              │
└─────────────────────────────────────────────────────────────┘
```

## 🔧 **核心组件**

### **1. 统一WebSocket管理器 (core/networking/websocket_manager.py)**

**功能特性**：
- 支持多种数据类型订阅 (orderbook, trade, funding_rate, etc.)
- 自动消息路由和分发
- 交易所特定的消息解析 (Binance, OKX)
- 连接状态监控和统计
- 代理支持和SSL配置

**关键类**：
- `WebSocketConnectionManager`: 主要管理器
- `DataType`: 数据类型枚举
- `DataSubscription`: 订阅配置
- `WebSocketConfig`: 连接配置

### **2. WebSocket适配器 (services/data-collector/collector/websocket_adapter.py)**

**功能特性**：
- 为现有OrderBook Manager提供新的WebSocket能力
- 保持现有接口不变
- 支持多交易所和多市场类型
- 自动处理订阅和消息路由

**关键类**：
- `WebSocketAdapter`: 基础适配器
- `OrderBookWebSocketAdapter`: OrderBook专用适配器

### **3. 统一数据收集器 (services/data-collector/unified_collector_main.py)**

**功能特性**：
- 配置驱动的启动系统
- 多交易所数据收集
- NATS消息发布
- 监控和健康检查

## 📊 **支持的交易所和市场类型**

### **交易所支持**
- **Binance**: 现货 (spot) + 永续合约 (swap)
- **OKX**: 现货 (spot) + 永续合约 (swap)

### **数据类型支持**
- `orderbook`: 订单簿数据
- `trade`: 交易数据
- `funding_rate`: 资金费率 (永续合约)
- `open_interest`: 持仓量 (永续合约)
- `liquidation`: 强平数据 (永续合约)
- `ticker`: 行情数据


## 🚀 **使用方式**

### **1. 配置驱动启动**

```yaml
# config/collector/unified_data_collection.yaml
system:
  use_unified_websocket: true

exchanges:
  binance_spot:
    exchange: "binance"
    market_type: "spot"
    symbols: ["BTCUSDT", "ETHUSDT"]
    data_types: ["orderbook", "trade"]
  
  binance_swap:
    exchange: "binance"
    market_type: "swap"
    symbols: ["BTCUSDT", "ETHUSDT"]
    data_types: ["orderbook", "trade", "funding_rate"]
```

### **2. 程序启动**

```bash
# 直接启动
python services/data-collector/unified_collector_main.py

# 使用自定义配置
COLLECTOR_CONFIG_PATH=/path/to/config.yaml python services/data-collector/unified_collector_main.py
```

### **3. 代码集成**

```python
from collector.websocket_adapter import OrderBookWebSocketAdapter
from collector.data_types import Exchange, MarketType

# 创建适配器
adapter = OrderBookWebSocketAdapter(
    exchange=Exchange.BINANCE,
    market_type=MarketType.SPOT,
    symbols=["BTCUSDT"],
    orderbook_manager=your_manager
)

# 建立连接
await adapter.connect()
```

## 🔄 **迁移指南**

### **从旧架构迁移**

1. **启用统一WebSocket**：
   ```python
   config.use_unified_websocket = True
   ```

2. **移除旧的WebSocket客户端**：
   - 不再需要 `BinanceWebSocketClient`
   - 不再需要 `OKXWebSocketClient`
   - 不再需要 `BinanceWebSocketManager`
   - 不再需要 `OKXWebSocketManager`

3. **使用新的适配器**：
   ```python
   # 旧方式
   client = BinanceWebSocketClient(symbols, callback)
   
   # 新方式
   adapter = OrderBookWebSocketAdapter(exchange, market_type, symbols, manager)
   ```

## 📈 **性能优势**

### **连接效率**
- **减少连接数量**: 一个WebSocket连接支持多种数据类型
- **统一连接管理**: 避免重复的连接逻辑
- **智能重连**: 统一的重连和错误处理机制

### **代码质量**
- **消除重复代码**: 移除了多个重复的WebSocket实现
- **统一接口**: 所有交易所使用相同的接口
- **易于测试**: 清晰的职责分离便于单元测试

### **可维护性**
- **集中管理**: WebSocket逻辑集中在core层
- **易于扩展**: 添加新交易所只需实现消息解析
- **配置驱动**: 通过配置文件控制所有行为

## 🧪 **测试和验证**

### **单元测试**
- `tests/unit/core/networking/test_websocket_manager.py`
- `tests/unit/core/networking/test_websocket_manager_tdd.py`

### **集成测试**
- 多交易所连接测试
- 数据类型订阅测试
- 消息路由验证测试

### **性能测试**
- 连接数量对比
- 内存使用对比
- 消息处理延迟测试

## 🔧 **配置参考**

### **WebSocket配置**
```yaml
networking:
  websocket:
    timeout: 30
    max_retries: 3
    ping_interval: 20
    ping_timeout: 60
```

### **交易所配置**
```yaml
exchanges:
  binance_spot:
    api:
      ws_url: "wss://stream.binance.com:9443"
    symbols: ["BTCUSDT", "ETHUSDT"]
    data_types: ["orderbook", "trade"]
```

## 🚨 **注意事项**

### **兼容性**
- 现有的OrderBook Manager功能完全保留
- 可以选择性启用新架构 (`use_unified_websocket=True`)
- 旧的WebSocket客户端已被移除

### **配置要求**
- 需要正确配置交易所API端点
- 确保NATS服务可用
- 检查网络连接和代理设置

### **监控建议**
- 监控WebSocket连接状态
- 跟踪消息路由统计
- 关注错误率和重连频率

## 📚 **相关文档**

- [配置管理文档](../configuration/config_management.md)
- [NATS集成文档](../messaging/nats_integration.md)
- [监控和告警文档](../monitoring/monitoring_setup.md)
- [部署指南](../deployment/deployment_guide.md)

## 🎉 **总结**

统一WebSocket架构重构成功实现了：

✅ **职责清晰分离**: WebSocket连接 vs 数据处理  
✅ **代码复用性**: 统一的连接管理器  
✅ **可扩展性**: 易于添加新交易所和数据类型  
✅ **向后兼容性**: 现有功能完全保留  
✅ **性能优化**: 减少连接数量和重复代码  
✅ **配置驱动**: 完全基于配置文件的启动系统  

这个架构为MarketPrism项目提供了坚实的基础，支持未来的扩展和优化需求。
