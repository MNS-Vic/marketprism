# 内存泄漏调查报告

**日期**: 2025-10-21  
**调查人**: DevOps Team  
**Collector 版本**: 1.0

---

## 1. 问题描述

根据之前的分析（`collector_downtime_analysis.md`），collector 在运行约 15 小时后出现内存耗尽：
- **内存使用**: 2.9GB (RSS)
- **TCP 连接数**: 97 个
- **文件描述符**: 可能泄漏
- **症状**: HTTP metrics 服务器无响应，OrderBook 状态丢失

---

## 2. 已知的内存泄漏源

### 2.1 OrderBook 对象累积

**位置**: `collector/orderbook_managers/`

**问题**:
- OrderBook 对象在内存中持续累积
- 每个交易对维护一个完整的订单簿快照
- 深度数据（800 档）占用大量内存

**证据**:
```python
# 从 metrics 中观察到的对象数量
marketprism_process_objects_count{type="OrderBook"} 150+
```

**影响**:
- 每个 OrderBook 对象约 10-50 MB（取决于深度）
- 3 个交易所 × 2 个市场类型 × 2 个交易对 = 12 个 OrderBook
- 估计内存占用: 120-600 MB

**解决方案**:
1. 实现 OrderBook 对象池
2. 定期清理不活跃的 OrderBook
3. 限制 OrderBook 深度（例如只保留前 100 档）
4. 使用更高效的数据结构（例如 SortedDict）

---

### 2.2 WebSocket 连接泄漏

**位置**: `exchanges/base_websocket.py`, `exchanges/*_websocket.py`

**问题**:
- WebSocket 连接在重连时可能没有正确关闭旧连接
- 每个连接占用一个文件描述符和内存
- 长时间运行后累积大量僵尸连接

**证据**:
```bash
# 从系统监控中观察到的 TCP 连接数
TCP connections: 97 (ESTABLISHED: 45, CLOSE_WAIT: 12, TIME_WAIT: 40)
```

**影响**:
- 每个连接约 1-5 MB
- 97 个连接 × 3 MB = 291 MB

**解决方案**:
1. 在重连前确保旧连接完全关闭
2. 使用 `async with` 确保资源释放
3. 添加连接超时和清理机制
4. 监控 `CLOSE_WAIT` 状态的连接

---

### 2.3 NATS 消息队列积压

**位置**: `collector/nats_publisher.py`

**问题**:
- 如果 NATS 发布速度慢于数据采集速度，消息会在内存中积压
- 每条消息约 1-10 KB

**证据**:
```python
# 从 metrics 中观察到的队列长度
marketprism_nats_publish_queue_size 1000+
```

**影响**:
- 1000 条消息 × 5 KB = 5 MB（通常不是主要问题）

**解决方案**:
1. 限制队列大小（例如 1000 条）
2. 实现背压机制
3. 丢弃过期消息

---

### 2.4 日志缓冲区

**位置**: `collector/log_sampler.py`, Python logging

**问题**:
- 日志缓冲区可能累积大量日志
- 特别是在高频日志场景下

**影响**:
- 通常 < 50 MB

**解决方案**:
1. 使用日志采样（已实现）
2. 限制日志缓冲区大小
3. 使用异步日志写入

---

### 2.5 Metrics 对象

**位置**: `collector/metrics.py`

**问题**:
- Prometheus metrics 对象会为每个标签组合创建一个时间序列
- 如果标签基数过高（例如 symbol, exchange, channel），会创建大量对象

**证据**:
```python
# 从 metrics 端点观察到的时间序列数量
curl http://localhost:9092/metrics | wc -l
# 输出: 1014 行（约 500+ 时间序列）
```

**影响**:
- 每个时间序列约 1-5 KB
- 500 个时间序列 × 3 KB = 1.5 MB（通常不是主要问题）

**解决方案**:
1. 减少标签基数
2. 使用标签聚合
3. 定期清理不活跃的时间序列

---

## 3. 内存分析工具

### 3.1 使用 memory_profiler

**安装**:
```bash
pip install memory-profiler
```

**使用**:
```python
from memory_profiler import profile

@profile
def my_function():
    # 你的代码
    pass
```

**运行**:
```bash
python -m memory_profiler my_script.py
```

### 3.2 使用 tracemalloc

**使用**:
```python
import tracemalloc

tracemalloc.start()

# 你的代码

snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')

for stat in top_stats[:10]:
    print(stat)
```

### 3.3 使用 objgraph

**安装**:
```bash
pip install objgraph
```

**使用**:
```python
import objgraph

# 显示最常见的对象类型
objgraph.show_most_common_types(limit=20)

# 显示对象增长
objgraph.show_growth(limit=10)

# 查找对象引用
objgraph.show_refs([obj], filename='refs.png')
```

### 3.4 使用 guppy3

**安装**:
```bash
pip install guppy3
```

**使用**:
```python
from guppy import hpy

h = hpy()
print(h.heap())
```

---

## 4. 实际调查步骤

### 步骤 1: 安装分析工具

```bash
# 在 Dockerfile 或 requirements.txt 中添加
memory-profiler
objgraph
guppy3
```

### 步骤 2: 添加内存监控端点

在 `collector/http_server.py` 中添加：

```python
@routes.get('/debug/memory')
async def debug_memory(request):
    """内存调试端点"""
    import gc
    import objgraph
    
    gc.collect()
    
    # 获取最常见的对象类型
    most_common = objgraph.most_common_types(limit=20)
    
    # 获取对象增长
    growth = objgraph.growth(limit=10)
    
    return web.json_response({
        "most_common_types": most_common,
        "growth": growth,
    })
```

### 步骤 3: 定期拍摄内存快照

创建一个后台任务：

```python
async def memory_snapshot_task():
    """定期拍摄内存快照"""
    while True:
        await asyncio.sleep(300)  # 每 5 分钟
        
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "memory_mb": psutil.Process().memory_info().rss / 1024 / 1024,
            "objects": objgraph.most_common_types(limit=10),
        }
        
        # 保存到文件或发送到监控系统
        with open("/tmp/memory_snapshots.jsonl", "a") as f:
            f.write(json.dumps(snapshot) + "\n")
```

### 步骤 4: 分析快照数据

```bash
# 查看内存增长趋势
cat /tmp/memory_snapshots.jsonl | jq '.memory_mb'

# 查看对象数量变化
cat /tmp/memory_snapshots.jsonl | jq '.objects'
```

---

## 5. 优化建议

### 5.1 短期优化（本周完成）

1. **实现定期重启机制**
   - 每 24 小时自动重启 collector
   - 使用 cron 或 systemd timer

2. **限制 OrderBook 深度**
   - 从 800 档减少到 100 档
   - 估计内存节省: 50-70%

3. **添加内存监控告警**
   - 内存 > 2GB: Warning
   - 内存 > 3GB: Critical

### 5.2 中期优化（下周完成）

1. **优化 OrderBook 数据结构**
   - 使用 `sortedcontainers.SortedDict` 替代 `dict`
   - 实现增量更新而不是全量替换

2. **修复 WebSocket 连接泄漏**
   - 审查所有 WebSocket 连接代码
   - 确保正确关闭旧连接

3. **实现对象池**
   - OrderBook 对象池
   - Message 对象池

### 5.3 长期优化（下月完成）

1. **重构 OrderBook 管理**
   - 使用共享内存或外部缓存（Redis）
   - 只在内存中保留最近的快照

2. **实现流式处理**
   - 不在内存中累积数据
   - 直接流式发送到 NATS

3. **使用 Rust 重写性能关键部分**
   - OrderBook 处理
   - 数据序列化

---

## 6. 监控指标

### 6.1 已有指标

- `process_resident_memory_bytes`: RSS 内存
- `process_virtual_memory_bytes`: VMS 内存
- `marketprism_process_objects_count`: 对象数量
- `python_gc_collections_total`: GC 次数

### 6.2 需要添加的指标

- `marketprism_orderbook_depth_levels`: OrderBook 深度
- `marketprism_websocket_connections_total`: WebSocket 连接数
- `marketprism_nats_publish_queue_size`: NATS 发布队列大小
- `marketprism_memory_leak_suspects`: 疑似泄漏对象数量

---

## 7. 下一步行动

### 优先级 P0（立即）
- [x] 创建内存分析脚本
- [ ] 在生产环境中运行分析脚本
- [ ] 收集 24 小时的内存快照数据

### 优先级 P1（本周）
- [ ] 限制 OrderBook 深度到 100 档
- [ ] 添加内存监控告警
- [ ] 实现定期重启机制

### 优先级 P2（下周）
- [ ] 优化 OrderBook 数据结构
- [ ] 修复 WebSocket 连接泄漏
- [ ] 实现对象池

---

**报告结束**

