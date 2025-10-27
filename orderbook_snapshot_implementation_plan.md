# Orderbook 快照轮询模式实施方案（1s/100档，Binance 永续使用 WebSocket API）

## 0) 背景与目标
- 现状：基于 WebSocket 增量更新在本地维护完整 OrderBook，合并/排序计算在高峰期成为瓶颈，出现延迟累计与丢包风险。
- 目标：统一切换为“定时快照轮询”模式，所有市场与交易所统一参数：
  - snapshot_interval = 1s
  - snapshot_depth = 100 档
- 特殊要求：Binance 永续合约使用“WebSocket API（请求-响应）”的 `depth` 方法获取快照；禁止使用 WebSocket Stream（订阅流）。
- 覆盖范围：
  - 交易所：Binance（Spot、USDS-M Futures）、OKX（Spot、Swap/Perp）
  - 交易对：BTC-USDT、ETH-USDT（各现货与永续）

---

## 1) 官方文档调研与要点（以官方文档为准）

### Binance Spot（REST 快照）
- Endpoint：GET `/api/v3/depth?symbol=BTCUSDT&limit=100`
- 权重/限频：权重随 limit 调整；1-100 档 weight=5；全局看 `x-mbx-used-weight-1m`（常见上限 1200/min，详见 General Info）。
- 文档：
  - Market Data endpoints（Order book）：https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints
  - General API Information（权重说明）：https://developers.binance.com/docs/binance-spot-api-docs/rest-api/general-api-information

### Binance USDS-M Futures（WebSocket API 快照，非 Stream）
- Base WS API：`wss://ws-fapi.binance.com/ws-fapi/v1`
- 方法：`depth`（请求-响应，一次返回当前订单簿，适合快照采样）
- 请求示例：`{"id":"...","method":"depth","params":{"symbol":"BTCUSDT","limit":100}}`
- 权重：limit=100 时 weight=5/次；WebSocket API 的 REQUEST_WEIGHT 与 REST 共享，默认配额 2400/min；握手开销 5 weight/连接；Ping/Pong 不超过 5 次/秒。
- 文档：
  - WS API General Info（配额、握手、格式）：https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info
  - WS API（Order Book depth 方法）：https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api
- 备用（仅降级时用）：REST GET `/fapi/v1/depth?symbol=BTCUSDT&limit=100`（limit=100 weight=5）
  - 文档：REST Order Book：https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Order-Book

### OKX（REST 快照）
- Endpoint：GET `/api/v5/market/books?instId=BTC-USDT&sz=100`
- 限速：公共 REST 典型 20 请求/秒（按 IP）；有文档场景表述为 40 请求/2s。
- 文档：
  - Get Order Book：https://www.okx.com/docs-v5/zh/#public-data-rest-api-get-order-book
  - 限速说明（概览/限速章节）：https://www.okx.com/docs-v5/zh/#overview-rate-limit

> 注：Binance WebSocket API 与 WebSocket Stream 不同。前者用于“请求-响应”的按需查询，非常适合 1s 快照采样；后者是订阅持续推送（本方案禁止在 Binance 永续使用 Stream）。

---

## 2) 1 秒轮询下的速率限制计算与安全性
以 4 个“市场上下文”（Binance Spot、Binance Futures、OKX Spot、OKX Perp）× 2 符号（BTC/ETH）= 8 路快照为例：

- Binance Spot（REST）：
  - 2 次请求/秒 × 60 = 120 次/分钟；weight=5 → 600 weight/min；常见上限 1200/min → 使用 50%，有余量。
- Binance Futures（WS API depth）：
  - 2 次请求/秒 × 60 = 120 次/分钟；weight=5 → 600 weight/min；上限 2400/min → 使用 25%。
  - 建议：两符号共用单个长期 WS API 连接，避免重复 5 weight 握手开销。
- OKX（REST）：
  - 4 次请求/秒；上限 20 次/秒（按 IP）→ 使用 20%。
- 安全性结论：在 1s/100 档配置下，全部安全，且具备 50%~80% 以上余量。
- 采集频率策略：Collector 固定 1s，不降频；监控 Binance `rateLimits`/`x-mbx-used-weight-1m` 与 OKX 错误码。
- 异常处理：如遇 429/60014 或临时网络错误，记录并在既定 1s 节拍下按重试/重连机制继续；不调整间隔。
- Binance Futures WS API：单长连复用，多符号顺序请求，降低握手开销。

---

## 3) 新目录结构与类设计（基类 + 4 个实现类）

新目录（与现有 orderbook_managers 并行，保持风格一致）：
```
services/data-collector/collector/orderbook_snap_managers/
  __init__.py
  base_orderbook_snap_manager.py     # 基类：定时轮询/请求、标准化、发布、指标与日志
  binance_spot_snap_manager.py       # REST depth
  binance_derivatives_snap_manager.py# WS API depth（请求-响应）
  okx_spot_snap_manager.py           # REST books
  okx_derivatives_snap_manager.py    # REST books（合约）
  manager_factory.py                 # Snap 模式工厂（或扩展现有 manager_factory）
```

基类 BaseOrderBookSnapManager（对齐 BaseLSRAllAccountManager 模式）：
- 关键职责：
  - `start()/stop()`：生命周期管理；
  - `_fetch_loop()`：1s 定时调度；精确对齐节拍（monotonic 时钟）；不做相位错开，按固定 1s 并发/顺序调度所有符号；
  - `_fetch_one(symbol)`：拉取快照（REST 或 WS API）；
  - `_normalize_snapshot(exchange, symbol, bids, asks, market_type, last_update_id)`：调用 Normalizer 生成 EnhancedOrderBook（update_type=SNAPSHOT）；
  - `_publish_snapshot(eob)`：NATS Core 发布；
  - 错误重试、超时、指标与抽样日志（沿用 log_sampler/metrics）。
  - 节拍保障：若上次请求未完成，则跳过本 tick，防止请求堆积；固定 1s 不降频。


四个实现类的取数方式：
- BinanceSpotSnapManager：REST `/api/v3/depth`。
- BinanceDerivativesSnapManager：WS API `depth`；保持 1 条长连，共享请求，按 1s 发送 2 个符号请求，逐条读取响应。
- OKXSpotSnapManager：REST `/api/v5/market/books`。
- OKXDerivativesSnapManager：REST `/api/v5/market/books`（合约 instType 对应 Perp）。

---

## 4) 与现有架构的集成
- Normalizer：直接使用 `normalize_enhanced_orderbook_from_snapshot()`，或复用 `normalize_orderbook()` 产出 NATS 友好结构；无需修改现有 Normalizer；对永续合约符号自动移除 -SWAP/-PERPETUAL 后缀；Binance 符号 `BTCUSDT` → `BTC-USDT`，确保发布统一符号格式。
- NATSPublisher：继续使用 `publish_enhanced_orderbook()` 或 `publish_orderbook()`，高频类型走 Core NATS（已有策略）。主题：`orderbook.{exchange}.{market_type}.{symbol}`。
- ClickHouse Schema：`marketprism_hot.orderbooks` 已包含 `update_type`、`bids/asks`、`timestamp` 等字段，兼容快照（无需 Schema 变更）。
- Manager Factory：根据 YAML 中 `data_types.orderbook.method: snapshot` 选择 snap_managers；与旧 `websocket` 模式并存，实现无缝切换与回滚。

### 4.1 工厂接线与配置透传（示例代码）

```python
# main._create_orderbook_manager 透传
orderbook_config = exchange_raw_config.get('orderbook', {})
manager_config.update({
    'method': orderbook_config.get('method', 'websocket'),
    'snapshot_interval': orderbook_config.get('snapshot_interval', 1),
    'snapshot_depth': orderbook_config.get('snapshot_depth', 100),
    'ws_api_url': orderbook_config.get('ws_api_url'),
    'rest_base': orderbook_config.get('rest_base', api_base_url),
})
```

```python
# 按 method 分支到 snapshot 工厂
method = config.get('method', 'websocket')
if method == 'snapshot':
    from collector.orderbook_snap_managers import OrderBookSnapManagerFactory
    return OrderBookSnapManagerFactory().create_manager(
        exchange, market_type, symbols, normalizer, nats_publisher, config
    )
# 否则走原增量模式...
```

---

## 5) 配置文件示例（YAML）
```yaml
# services/data-collector/config/collector/unified_data_collection.yaml

data_types:
  orderbook:
    enabled: true
    method: snapshot           # snapshot | websocket(旧)
    snapshot_interval: 1       # 秒
    snapshot_depth: 100        # 档位

exchanges:
  binance_spot:
    orderbook:
      method: snapshot
      rest_base: "https://api.binance.com"
      symbols: ["BTCUSDT", "ETHUSDT"]

  binance_derivatives:
    orderbook:
      method: snapshot
      ws_api_url: "wss://ws-fapi.binance.com/ws-fapi/v1"  # WebSocket API（非Stream）
      symbols: ["BTCUSDT", "ETHUSDT"]

  okx_spot:
    orderbook:
      method: snapshot
      rest_base: "https://www.okx.com"
      symbols: ["BTC-USDT", "ETH-USDT"]

  okx_derivatives:
    orderbook:
      method: snapshot
      rest_base: "https://www.okx.com"
      symbols: ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
```

---

## 6) 关键流程与伪代码（精简）

基类调度（精确 1s 节拍，无相位错开）：
```python
next_ts = time.monotonic()
while running:
  next_ts += 1.0
  for sym in symbols:
    asyncio.create_task(self._fetch_one(sym))
  await asyncio.sleep(max(0, next_ts - time.monotonic()))
```

Binance 永续（WS API depth）请求示例：
```python
msg = {"id": uuid4().hex, "method": "depth", "params": {"symbol": sym, "limit": 100}}
await ws.send_json(msg)
resp = await ws.recv_json()

     
# resp.result = { lastUpdateId, E, T, bids:[[p,q]...], asks:[[p,q]...] }
```



标准化与发布：
```python
eob = normalizer.normalize_enhanced_orderbook_from_snapshot(ex, sym, bids, asks,
                       market_type=mt, last_update_id=lid)
await nats.publish_enhanced_orderbook(eob)
```






请求-响应匹配（简化示例）：
```python
req_id = f"{sym}_{int(time.time()*1000)}"
await ws.send_json({"id": req_id, "method":"depth", "params":{"symbol": sym, "limit":100}})
while True:
    resp = await ws.recv_json()
    if resp.get('id') == req_id:
        data = resp.get('result', {})
        break
```



---

## 7) 测试与验证计划（分阶段）
- Phase 0：单元测试
  - Normalizer：SNAPSHOT 路径（100 档）
  - Snap Managers：
    - REST：限流/超时/重试；空数组/异常字段
    - WS API：连接、握手、请求/响应匹配、断线重连
- Phase 1：最小 E2E（Binance Spot BTCUSDT）
  - Collector→NATS Core→Hot Storage 入库成功，字段正确；1s 间隔稳定
- Phase 2：加入 Binance Futures（WS API，BTCUSDT/ETHUSDT）
  - 单连接 1s 两请求，验证 `rateLimits` 与延迟（端到端 < 300ms 目标）
- Phase 3：加入 OKX（Spot/Perp）两符号
  - 观察 OKX 20 req/s 限额裕度；无 60014 报错
- Phase 4：全量稳定性/压测
  - 连续 4-6 小时运行；无显著丢包/超时，端到端稳定
- 验证项：
  - 速率合规：Binance `x-mbx-used-weight-1m`/`rateLimits`、OKX 错误码
  - 热表写入速率/延迟；冷表复制正常
  - 监控：成功/失败计数、平均/尾部延迟、重连计数

---

## 8) 风险评估与降级策略
- 速率限制抖动/峰值：
  - 策略：固定 1s，不自动降频；记录并告警。监控 Binance 响应头 `x-mbx-used-weight-1m` 与 OKX 错误码 `60014`。
- WS API 连接不稳定（Binance Futures）：
  - 策略：指数退避重连；重连前显式关闭旧连接；成功后恢复 1s 请求循环。
  - 降级：连续重连失败 ≥3 次，短时降级为 REST `/fapi/v1/depth`（仍固定 1s）；连接恢复后回切 WS API。
- 请求堆积风险：
  - 策略：若某符号上一次请求未完成，则跳过本 tick，防止请求堆积。
- 数据异常/空深度：
  - 策略：丢弃并计数报警；连续 N 次异常仅记录，不降频。
- 本地计算负载：
  - 策略：并发 create_task；保持 100 档；必要时在发布前可裁剪到 nats_publish_depth。
- 可观测性：
  - 指标：请求耗时、成功/失败、429/5xx、WS 重连次数、NATS 发布耗时；附加记录 Binance `x-mbx-used-weight-1m` 与 OKX `60014` 计数；日志抽样输出

---

## 9) 向后兼容与回滚
- YAML `data_types.orderbook.method` 支持 `websocket`（旧）与 `snapshot`（新）并存；
- 回滚：切回 `websocket` 即恢复旧增量模式；
- Schema 与 NATS 主题保持不变；
- 代码结构新增 snap_managers 目录，不修改/替代原 managers，避免回滚风险。

---

## 10) 实施步骤（建议迭代）
1) 新增目录与基类 `base_orderbook_snap_manager.py`；
2) 优先实现 BinanceDerivativesSnapManager（WS API depth），单连接覆盖 BTCUSDT/ETHUSDT；
3) 实现 BinanceSpot/OKXSpot/OKXDerivatives（REST）；
4) 扩展现有 `orderbook_managers/manager_factory.py` 或新增 `orderbook_snap_managers/manager_factory.py` 并在上层工厂注入选择逻辑；
5) 配置与日志/指标接入；
6) 分阶段 E2E 验证与压测；
7) 默认切换生产策略到 snapshot（保留回滚能力）。

---

## 11) 关键决策点（最终确定）
- 采用“单连接复用”在 Binance Futures WS API 上为多符号发起 depth 请求（已采纳）。
- 不启用 phase_stagger_ms（已采纳，统一 1s 无错开）。
- 永续合约标准化：Normalizer 去掉 -SWAP/-PERPETUAL 后缀，发布统一为 BTC-USDT（已采纳）。
- Collector 请求频率固定为 1s，不做自动降频（已采纳）。

---

## 12) 附：与现有代码的对齐点
- Normalizer：`normalize_enhanced_orderbook_from_snapshot()` 已具备；
- DataTypes：`OrderBookUpdateType.SNAPSHOT` 已定义；
- NATSPublisher：高频类型使用 Core NATS 已实现；主题模板 `orderbook.{exchange}.{market_type}.{symbol}` 可直接复用；
- ClickHouse（热/冷）：无需变更。

