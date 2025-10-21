# OrderBook 内存优化完整方案

**日期**: 2025-10-21  
**调查人**: DevOps Team  
**状态**: 待确认

---

## 📊 调查结果

### 1. 交易所 WebSocket 订单簿推送规格对比

| 交易所 | 市场类型 | 订阅频道 | 推送类型 | 默认档位数 | 可选深度级别 | 当前配置 |
|--------|---------|---------|---------|-----------|-------------|---------|
| **Binance 现货** | spot | `<symbol>@depth@100ms` | 增量更新 | 全量（无限制） | 5/10/20 档（部分深度）<br>全量（增量深度） | `depth_limit: 500`<br>`websocket_depth: 1000` |
| **Binance 衍生品** | perpetual | `<symbol>@depth@100ms` | 增量更新 | 全量（无限制） | 5/10/20 档（部分深度）<br>全量（增量深度） | `depth_limit: 500`<br>`websocket_depth: 1000` |
| **OKX 现货** | spot | `books` | 增量更新 | **400 档** | `books`: 400档<br>`books5`: 5档<br>`books-l2-tbt`: 400档（VIP4+） | `depth_limit: 500`<br>`websocket_depth: 400` |
| **OKX 衍生品** | perpetual | `books` | 增量更新 | **400 档** | `books`: 400档<br>`books5`: 5档<br>`books-l2-tbt`: 400档（VIP4+） | `depth_limit: 400`<br>`websocket_depth: 400` |

#### 关键发现：

1. **Binance**：
   - WebSocket 增量更新 **没有档位限制**，推送所有价格变化
   - REST API 快照支持：5, 10, 20, 50, 100, 500, 1000, 5000 档
   - 当前配置：接收全量增量，本地维护 1000 档快照

2. **OKX**：
   - WebSocket `books` 频道 **最多推送 400 档**（买单 200 档 + 卖单 200 档）
   - REST API 快照也是 400 档
   - 当前配置：接收 400 档，本地维护 400 档快照

---

### 2. 当前代码实现分析

#### 2.1 订阅配置

**Binance 现货/衍生品**：
```python
# services/data-collector/exchanges/binance_websocket.py:924
params.append(f"{symbol.lower()}@depth@100ms")
```
- 订阅：`@depth@100ms`（增量深度，100ms 更新）
- 接收：**全量增量更新**（所有价格变化）
- 快照深度：1000 档（配置文件）

**OKX 现货/衍生品**：
```python
# services/data-collector/exchanges/okx_websocket.py:830
subscribe_args.append({
    "channel": "books",
    "instId": symbol
})
```
- 订阅：`books` 频道
- 接收：**最多 400 档**（交易所限制）
- 快照深度：400 档（配置文件）

#### 2.2 数据处理流程

**当前流程**：
```
1. 接收 WebSocket 增量更新
2. 应用到本地 OrderBook 快照（dict 结构）
3. 保存完整快照到 OrderBookState.local_orderbook
4. 发布到 NATS（裁剪到 nats_publish_depth: 200 档）
```

**问题点**：
1. ✅ **增量更新正确丢弃**：应用后不保存历史增量
2. ✅ **只保存最新快照**：`local_orderbook` 只有一个
3. ❌ **本地快照过大**：Binance 维护 1000 档，OKX 维护 400 档
4. ❌ **内存未限制**：没有强制限制 OrderBook 深度

#### 2.3 内存占用估算

**单个 OrderBook 内存占用**：
```python
# 每个价格档位（PriceLevel）
price: Decimal (28 bytes) + quantity: Decimal (28 bytes) = 56 bytes

# Binance 1000 档 OrderBook
bids: 1000 × 56 = 56 KB
asks: 1000 × 56 = 56 KB
total: 112 KB + Python 对象开销 ≈ 150-200 KB

# OKX 400 档 OrderBook
bids: 400 × 56 = 22.4 KB
asks: 400 × 56 = 22.4 KB
total: 44.8 KB + Python 对象开销 ≈ 60-80 KB
```

**总内存占用（8 个 OrderBook）**：
```
Binance 现货 (2 交易对): 2 × 200 KB = 400 KB
Binance 衍生品 (2 交易对): 2 × 200 KB = 400 KB
OKX 现货 (2 交易对): 2 × 80 KB = 160 KB
OKX 衍生品 (2 交易对): 2 × 80 KB = 160 KB
---
总计: 1.12 MB
```

**结论**：OrderBook 本身占用内存很小（约 1 MB），**不是主要内存泄漏源**！

---

### 3. 真正的内存泄漏源

根据调查，OrderBook 数据结构本身不是问题。真正的问题可能是：

#### 3.1 OrderBookState 对象泄漏
```python
# services/data-collector/collector/data_types.py:1269
@dataclass
class OrderBookState:
    symbol: str
    exchange: str
    local_orderbook: Optional['EnhancedOrderBook'] = None
    update_buffer: deque = field(default_factory=deque)  # ⚠️ 可能堆积
    ...
```

**问题**：
- `update_buffer` 可能堆积大量未处理的增量消息
- `orderbook_states` 字典可能无限增长（配置 `max_orderbook_states: 1000`，但实际只需要 8 个）

#### 3.2 WebSocket 连接泄漏
- 97 个 TCP 连接（正常应该只有 8 个）
- 可能是重连时没有正确关闭旧连接

#### 3.3 Python 对象开销
- dict、list、deque 等容器的内存开销
- 未及时垃圾回收

---

## 🎯 优化方案

### 方案 A：优化内存管理配置（推荐）✅

**目标**：严格限制对象数量，防止泄漏

**改动内容**：

1. **严格限制 OrderBookState 数量**
```python
# services/data-collector/collector/orderbook_managers/base_orderbook_manager.py
self.memory_config = {
    'max_orderbook_states': 20,  # 从 1000 降到 20（实际只需要 8 个）
    'max_depth_levels': 400,     # 限制单个 OrderBook 最大深度到 400 档
    'cleanup_interval': 180.0,   # 3 分钟清理一次
    'inactive_threshold': 600.0, # 10 分钟不活跃就清理
}
```

2. **限制 update_buffer 大小**
```python
# 在 OrderBookState 中添加
max_buffer_size: int = 100  # 最多缓存 100 条增量消息
```

3. **强制限制 OrderBook 深度**
```python
def _limit_orderbook_depth(self, orderbook, max_depth: int = 400):
    """在保存前裁剪 OrderBook 深度"""
    if len(orderbook.bids) > max_depth:
        orderbook.bids = orderbook.bids[:max_depth]
    if len(orderbook.asks) > max_depth:
        orderbook.asks = orderbook.asks[:max_depth]
```

**预期效果**：
- 内存占用：从潜在的 GB 级别降低到 < 10 MB
- 防止 OrderBookState 泄漏
- 防止 update_buffer 堆积

---

### 方案 B：调整配置文件深度限制

**目标**：统一深度配置，避免不必要的大深度

**改动内容**：

```yaml
# services/data-collector/config/collector/unified_data_collection.yaml

exchanges:
  binance:
    spot:
      depth_limit: 400          # 从 500 降到 400
      nats_publish_depth: 200   # 保持不变
      orderbook:
        snapshot_depth: 400     # 从 1000 降到 400
        websocket_depth: 400    # 从 1000 降到 400
    perpetual:
      depth_limit: 400          # 从 500 降到 400
      nats_publish_depth: 200   # 保持不变
      orderbook:
        snapshot_depth: 400     # 从 1000 降到 400
        websocket_depth: 400    # 从 1000 降到 400
  okx:
    spot:
      depth_limit: 400          # 保持不变
      nats_publish_depth: 200   # 保持不变
      orderbook:
        snapshot_depth: 400     # 保持不变
        websocket_depth: 400    # 保持不变
    perpetual:
      depth_limit: 400          # 保持不变
      nats_publish_depth: 200   # 保持不变
      orderbook:
        snapshot_depth: 400     # 保持不变
        websocket_depth: 400    # 保持不变
```

**理由**：
- Binance 虽然支持 1000 档，但实际只需要 400 档
- 统一所有交易所的深度配置，简化管理
- 减少内存占用

**预期效果**：
- Binance OrderBook 内存占用：从 200 KB 降到 80 KB（每个）
- 总内存节省：约 480 KB（4 个 Binance OrderBook）

---

### 方案 C：修复 WebSocket 连接泄漏（必须）

**目标**：确保 WebSocket 连接正确关闭

**改动内容**：

1. **审查所有 WebSocket 重连逻辑**
2. **确保旧连接在重连前关闭**
3. **添加连接数监控**

**预期效果**：
- TCP 连接数：从 97 降到 8-12
- 内存节省：约 200-300 MB

---

## 📋 推荐执行顺序

### 第一步：立即执行（本周）

1. ✅ **方案 A**：优化内存管理配置
   - 修改 `base_orderbook_manager.py`
   - 添加深度限制方法
   - 添加 buffer 大小限制

2. ✅ **方案 B**：调整配置文件
   - 统一深度配置到 400 档
   - 重启 collector 验证

### 第二步：下周执行

3. ⏳ **方案 C**：修复 WebSocket 连接泄漏
   - 审查重连逻辑
   - 添加连接监控
   - 压力测试

---

## ❓ 需要你确认的问题

1. **深度限制 400 档够用吗？**
   - 当前配置：Binance 1000 档，OKX 400 档
   - 建议：统一到 400 档
   - 影响：超过 400 档的数据会被丢弃

2. **NATS 发布深度 200 档是否合适？**
   - 当前配置：200 档
   - 建议：保持不变
   - 下游服务是否需要更多深度？

3. **内存清理策略是否太激进？**
   - 10 分钟不活跃就清理
   - 是否会影响正常交易对？

4. **是否需要添加更多监控指标？**
   - OrderBookState 数量
   - update_buffer 大小
   - WebSocket 连接数

---

## 📊 预期效果总结

| 优化项 | 当前状态 | 优化后 | 节省 |
|--------|---------|--------|------|
| OrderBook 深度 | Binance: 1000档<br>OKX: 400档 | 统一: 400档 | ~480 KB |
| OrderBookState 数量 | 最多 1000 个 | 最多 20 个 | 防止泄漏 |
| update_buffer 大小 | 无限制 | 最多 100 条 | 防止堆积 |
| WebSocket 连接数 | 97 个 | 8-12 个 | ~200-300 MB |
| **总计** | **潜在 GB 级别** | **< 10 MB** | **99%+** |

---

## 🚀 下一步行动

请确认以上方案后，我将：
1. 修改代码实现方案 A
2. 修改配置文件实现方案 B
3. 重启 collector 并监控内存使用
4. 生成测试报告

**等待你的确认！** 🙏

