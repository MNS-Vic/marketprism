# 策略驱动的订单簿深度管理系统

## 🎯 **概述**

MarketPrism现在支持策略驱动的订单簿深度管理，允许不同的交易策略使用定制化的档位配置，确保增量订阅和快照获取的完全一致性。

## 🏗️ **系统架构**

```
┌─────────────────────────────────────┐
│       策略配置文件                   │
│   trading_strategies.yaml           │
│  - 套利策略: 5档                     │
│  - 做市策略: 20档                    │
│  - 趋势分析: 100档                   │
│  - 深度分析: 400档                   │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│    StrategyConfigManager            │
│  - 策略配置加载                      │
│  - 深度配置验证                      │
│  - 交易所限制检查                    │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│      ExchangeConfig                 │
│  - 策略参数集成                      │
│  - 深度配置优化                      │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│    OrderBook Manager                │
│  - 策略驱动深度                      │
│  - 动态策略切换                      │
│  - 一致性保证                       │
└─────────────────────────────────────┘
```

## 📊 **预定义策略配置**

### **套利策略 (arbitrage)**
- **用途**: 跨交易所套利，只需要最优价格
- **深度**: 5档快照 + 5档WebSocket
- **特点**: 低延迟、高频率更新
- **适用场景**: 高频交易、价差套利

### **做市策略 (market_making)**
- **用途**: 提供流动性，需要中等深度
- **深度**: 20档快照 + 20档WebSocket
- **特点**: 平衡的延迟和深度
- **适用场景**: 流动性提供、价差交易

### **趋势分析策略 (trend_analysis)**
- **用途**: 分析市场趋势，需要较深数据
- **深度**: 100档快照 + 适配WebSocket深度
- **特点**: 中等延迟容忍度
- **适用场景**: 技术分析、趋势跟踪

### **深度分析策略 (depth_analysis)**
- **用途**: 深度市场分析，需要最深数据
- **深度**: 400-1000档快照 + 适配WebSocket深度
- **特点**: 高延迟容忍度、完整市场视图
- **适用场景**: 市场研究、深度分析

## 🔧 **使用方法**

### **1. 基础策略配置**

#### **创建策略驱动的ExchangeConfig**
```python
from collector.data_types import Exchange, MarketType, ExchangeConfig

# 套利策略配置
arbitrage_config = ExchangeConfig.from_strategy(
    exchange=Exchange.BINANCE,
    market_type=MarketType.SPOT,
    strategy_name="arbitrage"
)

# 做市策略配置
market_making_config = ExchangeConfig.from_strategy(
    exchange=Exchange.OKX,
    market_type=MarketType.SPOT,
    strategy_name="market_making"
)

# 趋势分析策略配置
trend_config = ExchangeConfig.from_strategy(
    exchange=Exchange.BINANCE,
    market_type=MarketType.PERPETUAL,
    strategy_name="trend_analysis"
)
```

#### **创建策略驱动的OrderBook Manager**
```python
from collector.orderbook_manager import OrderBookManager
from collector.normalizer import DataNormalizer
from collector.nats_publisher import NATSPublisher, NATSConfig

# 创建基础组件
normalizer = DataNormalizer()
nats_config = NATSConfig(servers=["nats://localhost:4222"])
nats_publisher = NATSPublisher(nats_config)

# 创建策略配置
config = ExchangeConfig.from_strategy(
    Exchange.BINANCE, MarketType.SPOT, "arbitrage"
)

# 创建OrderBook Manager
manager = OrderBookManager(
    config=config,
    normalizer=normalizer,
    nats_publisher=nats_publisher
)

# 查看当前策略信息
strategy_info = manager.get_current_strategy_info()
print(f"当前策略: {strategy_info}")
```

### **2. 动态策略切换**

```python
# 运行时切换策略
success = await manager.switch_strategy("market_making")
if success:
    print("策略切换成功")
    new_info = manager.get_current_strategy_info()
    print(f"新策略信息: {new_info}")
else:
    print("策略切换失败")
```

### **3. 策略组合配置**

```python
from collector.strategy_config_manager import get_strategy_config_manager

manager = get_strategy_config_manager()

# 使用策略组合
combo_config = manager.get_strategy_combination_config(
    "arbitrage_and_making",  # 套利+做市组合
    Exchange.BINANCE,
    MarketType.SPOT
)

print(f"组合策略深度: 快照={combo_config.snapshot_depth}, WebSocket={combo_config.websocket_depth}")
```

## ⚙️ **配置文件管理**

### **策略配置文件位置**
```
config/collector/trading_strategies.yaml
```

### **自定义策略配置**
```yaml
strategies:
  my_custom_strategy:
    name: "自定义策略"
    description: "我的专用交易策略"
    priority: "high"
    
    depth_config:
      default:
        snapshot_depth: 50
        websocket_depth: 50
        update_frequency: "100ms"
      
      exchanges:
        binance:
          spot:
            snapshot_depth: 50
            websocket_depth: 20    # 受Binance限制
            api_weight: 1
        okx:
          spot:
            snapshot_depth: 50
            websocket_depth: 50
            api_weight: 1
    
    performance:
      snapshot_interval: 180
      max_latency_ms: 150
      error_tolerance: "medium"
```

### **环境特定配置**
```yaml
environments:
  development:
    global_overrides:
      max_snapshot_depth: 100      # 开发环境限制
      max_websocket_depth: 20
  
  production:
    global_overrides:
      # 生产环境使用完整配置
      pass
```

## 🔍 **深度一致性保证**

### **自动限制应用**
系统自动应用交易所限制：

- **Binance**: WebSocket最大20档，自动降级
- **OKX**: WebSocket最大400档，完全支持
- **API权重**: 自动计算和验证权重限制

### **一致性验证**
```python
# 验证策略配置一致性
is_valid, message = config.validate_strategy_consistency()
if not is_valid:
    print(f"配置不一致: {message}")

# 获取优化后的深度
snapshot_depth, websocket_depth = config.get_strategy_optimal_depths()
print(f"优化深度: 快照={snapshot_depth}, WebSocket={websocket_depth}")
```

## 📈 **性能优化**

### **策略性能配置**
每个策略包含性能配置：

```python
from collector.strategy_config_manager import get_strategy_config_manager

manager = get_strategy_config_manager()
performance_config = manager.get_strategy_performance_config("arbitrage")

print(f"快照间隔: {performance_config.snapshot_interval}秒")
print(f"最大延迟: {performance_config.max_latency_ms}毫秒")
print(f"错误容忍度: {performance_config.error_tolerance}")
```

### **API权重管理**
```python
# 获取策略深度配置
depth_config = manager.get_strategy_depth_config(
    "depth_analysis", Exchange.BINANCE, MarketType.SPOT
)

print(f"API权重: {depth_config.api_weight}")
print(f"更新频率: {depth_config.update_frequency}")
```

## 🚨 **错误处理和降级**

### **配置验证失败**
- 自动降级到默认策略
- 记录警告日志
- 继续正常运行

### **策略切换失败**
- 保持当前策略不变
- 记录错误原因
- 提供回滚机制

### **交易所限制超出**
- 自动应用限制
- 调整到支持的最大值
- 记录调整信息

## 🎯 **最佳实践**

### **1. 策略选择指南**
- **高频交易**: 使用`arbitrage`策略（5档）
- **中频交易**: 使用`market_making`策略（20档）
- **分析应用**: 使用`trend_analysis`策略（100档）
- **研究用途**: 使用`depth_analysis`策略（400档+）

### **2. 配置管理**
- 在配置文件中定义策略，避免硬编码
- 使用环境特定配置区分开发/生产环境
- 定期验证策略配置的有效性

### **3. 监控和调优**
- 监控API权重使用情况
- 跟踪策略切换频率
- 分析深度配置对性能的影响

### **4. 向后兼容**
- 现有代码无需修改即可继续工作
- 逐步迁移到策略驱动配置
- 保持默认策略作为降级选项

## 🔗 **相关文档**

- [深度配置管理指南](./depth_configuration_guide.md)
- [统一NATS客户端指南](./unified_nats_client_guide.md)
- [交易所API限制说明](./exchange_api_limits.md)
- [配置文件管理指南](./configuration_management.md)
