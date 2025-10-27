# MarketPrism 命名规范统一（NATS 主题与 exchange/market_type）摸底与修改计划

本文档梳理当前实现、提出标准化改造方案，并给出风险评估、执行顺序与测试计划。范围覆盖：data-collector、message-broker、hot-storage-service、cold-storage-service、ClickHouse schema、监控看板。

---

## 目标规范
- 主题模板保持不变：`{data_type}.{exchange}.{market_type}.{symbol}`
- data_type：8 种，保持不变
  - orderbook, trade, funding_rate, open_interest, liquidation, lsr_top_position, lsr_all_account, volatility_index
- exchange：统一为 3 个基础名（去除 _spot/_derivatives）
  - binance, okx, deribit
- market_type：统一为 3 个值
  - spot, perpetual, options
- symbol：保持 BTC-USDT 标准

---

## 1. 摸底结果（现状清单）

### A) 采集层（services/data-collector）

1) Normalizer（collector/normalizer.py）
- 能力：提供 normalize_exchange_name、normalize_market_type、normalize_symbol_format 等标准化能力（含将 swap/futures/perp → perpetual）。
- 现状：大量 normalize_xxx_* 方法内仍写出 payload.exchange 为 binance_derivatives/okx_derivatives 等，未强制覆盖为基础名；payload.market_type 多为 spot/perpetual，Deribit 波指为 options。
- 结论：具备标准化能力，但未在“发布边界”强制使用，导致主题与 payload 混杂基础名与后缀名。

2) NATS Publisher（collector/nats_publisher.py）
- 主题模板：`{data_type}.{exchange}.{market_type}.{symbol}`。
- 现状：生成 subject 时直接使用传入 exchange 与 market_type（未统一为基础名/标准值）；payload.exchange/market_type 也可能保留后缀名；指标标签中 exchange 做了“去后缀”的基础名，market_type 将 perpetual/options 等归并为 derivatives（仅用于指标标签）。
- 结论：主题与 payload 未统一；指标已“半统一”（exchange=基础名，market_type=derivatives/spot）。

3) 数据类型枚举（collector/data_types.py）
- Exchange：包含 BINANCE_SPOT、BINANCE_DERIVATIVES、OKX_SPOT、OKX_DERIVATIVES、DERIBIT_DERIVATIVES 及兼容项。
- MarketType：含 SPOT、PERPETUAL、FUTURES、SWAP(=perpetual)、OPTIONS、DERIVATIVES。
- 结论：为采集端内部使用；不强制变更（避免大范围回归）。

4) 采集配置（config/collector/unified_data_collection.yaml）
- exchanges.* 使用带后缀名（binance_spot、okx_derivatives 等），用于内部区分连接参数。
- streams.subject_template 保持 `{exchange}.{market_type}` 占位符。
- 结论：配置层不强制变更；后续在 Publisher 层做最终标准化即可。

5) 波动率指数（collector/vol_index_managers/*）
- exchange 通常传 deribit_derivatives；market_type 固定传 options。

6) 采集指标（collector/metrics.py）
- 导出 marketprism_nats_messages_published_labeled_total{exchange, market_type, data_type}，其中 exchange 取基础名、market_type 将非 spot 归并至 derivatives。

### B) 消息代理（services/message-broker）
- config/unified_message_broker.yaml：strict_subjects: true；MARKET_DATA 流按 data_type.> 通配（funding_rate.> 等）。
- 结论：不关心 exchange/market_type 具体取值，后续变更不影响流匹配。

### C) 热存储（services/hot-storage-service）
- 订阅：按 data_type.>；高频 Core NATS，低频 JetStream（deliver_policy=LAST）。
- 入库：写入 payload 的 exchange 与 market_type。
- 现状：market_type 在入库与指标层将 perpetual/options/swap/futures/perp/derivatives 统一为 derivatives（spot 例外）。
- 结论：与目标“perpetual 与 options 分离”为不一致，需要调整归一策略。

### D) 冷存储（services/cold-storage-service）
- main.py：不依赖 NATS；只做 ClickHouse 热→冷复制（窗口化），含 /health /stats /metrics。
- replication.py：通过 HTTP/remote 从 marketprism_hot.<table> 复制到 marketprism_cold.<table>：`INSERT INTO ... SELECT * FROM ... WHERE timestamp BETWEEN ...`；复制“全字段”，不改写 exchange/market_type。
- 配置（config/cold_storage_config.yaml）：仅 ClickHouse 连接与复制窗口/延迟参数；不涉及 exchange/market_type。
- 结论：对主题命名变更完全无感；将“如实复制”热端入库的 exchange/market_type 值（新老混合会被原样复制）。

### E) ClickHouse 表（hot-storage-service/config/clickhouse_schema.sql）
- 各数据表均含 exchange、market_type 字符串列；无枚举约束；分区包含 exchange。
- 结论：变更取值不会引起 schema 变更；历史混合值可与新值共存。

### F) 监控看板（monitoring-alerting/config/grafana/*）
- $exchange 变量来源于指标标签（采集/存储端导出）；部分面板通过 subject 正则解析 exchange。
- 现状假设：exchange=基础名时，subject=~"^orderbook.($exchange)..*" 等筛选将继续工作；需要同步保证指标标签也输出基础名。

---

## 2. 修改计划（分模块/分文件）

总体思路：
- 在“发布边界（Publisher）”与“存储边界（热端）”统一 exchange 与 market_type；尽量不动采集内部与 YAML 结构，降低回归风险。
- 冷存储无须修改。

### A) 采集层 Publisher（services/data-collector/collector/nats_publisher.py）

1) 生成主题前统一 exchange/market_type
- 使用 Normalizer：exchange → 基础名（binance/okx/deribit），market_type → spot/perpetual/options。

修改前：
```python
subject = template.format(
    exchange=exchange,
    market_type=market_type.lower(),
    symbol=normalized_symbol
)
```
修改后（示意）：
```python
_base_ex = self.normalizer.normalize_exchange_name(exchange)
_base_mt = self.normalizer.normalize_market_type(market_type)
subject = template.format(exchange=_base_ex, market_type=_base_mt, symbol=normalized_symbol)
```

2) 统一 payload.exchange 与 payload.market_type
- 发布时覆盖 message_data['exchange'] 与 message_data['market_type'] 为上述标准值。

修改前：
```python
message_data = data.copy()
message_data['market_type'] = message_data.get('market_type', market_type)
```
修改后（示意）：
```python
message_data = data.copy()
_base_ex = self.normalizer.normalize_exchange_name(exchange)
_base_mt = self.normalizer.normalize_market_type(message_data.get('market_type', market_type))
message_data['exchange'] = _base_ex
message_data['market_type'] = _base_mt
```

3) 指标标签统一
- record_nats_publish_labeled(exchange, market_type, data_type)：使用基础名与标准 market_type（不再把 options 合并到 derivatives）。
- record_data_success(exchange=...)：送入基础名。

修改前（简化）：
```python
base_ex = _ex.split('_', 1)[0] if '_' in _ex else _ex
_mt = (market_type or '').lower()
if _mt in (..., 'options', 'derivatives'):
    _mt = 'derivatives'
```
修改后（示意）：
```python
base_ex = self.normalizer.normalize_exchange_name(exchange)
_mt = self.normalizer.normalize_market_type(market_type)
```

备注：publish_trade/publish_orderbook 等快捷方法最终走 publish_data，统一受控。

### B) 热存储（services/hot-storage-service/main.py）

1) 入库与指标的 market_type 归一策略
- 将 ('swap','futures','future','perp','derivatives') → 'perpetual'；'options' 保持；'spot' 保持。

修改前：
```python
_raw_mt = str(data.get('market_type','') or '').lower()
if _raw_mt in ('perpetual','swap','futures','future','perp','options','derivatives'):
    _canon_mt = 'derivatives'
elif _raw_mt == 'spot':
    _canon_mt = 'spot'
```
修改后（示意）：
```python
_raw_mt = str(data.get('market_type','') or '').lower()
if _raw_mt in ('swap','futures','future','perp','derivatives'):
    _canon_mt = 'perpetual'
elif _raw_mt in ('spot','perpetual','options'):
    _canon_mt = _raw_mt
else:
    _canon_mt = _raw_mt or ''
```

2) 指标标签 exchange/market_type
- exchange 直接使用 payload.exchange（采集端已统一基础名），不再 split('_')。
- market_type 直接使用上面的 _canon_mt，unknown 兜底。

### C) 冷存储（services/cold-storage-service/*）
- 无需修改：不订阅 NATS，不改写 exchange/market_type；复制“全字段”到冷库。
- 验证：确认新数据按标准值复制；历史混合值继续如实复制。

### D) 监控看板（monitoring-alerting/config/grafana/*）
- $exchange 变量：确保来源指标标签为 binance/okx/deribit 基础名（依赖 A3/B2 改造）。
- 文案：将“derivatives 聚合”调整为“perpetual 与 options 分离”。
- 若有 subject 解析的面板，`^orderbook.($exchange)\..*` 仍可匹配（主题中 exchange 已为基础名）。

### E) 采集 Normalizer（可选后续清理）
- 低优先：逐步去除 normalize_xxx_* 中对 exchange 后缀名的写出，改为调用 normalize_exchange_name 产出基础名。


### F) 映射规范（白名单与规则）
- Exchange 归一（输入 → 输出，大小写不敏感）：
  - binance、binance_spot、binance_derivatives、binance_perpetual、binance_futures → binance
  - okx、okx_spot、okx_derivatives、okx_perpetual、okx_swap、okx_futures → okx
  - deribit、deribit_derivatives → deribit
  - 规则：优先命中白名单；否则若形如 `<base>_<suffix>` 且 suffix∈{spot,derivatives,perpetual,futures,swap}，则取 `<base>`；最终统一为小写基础名。
- MarketType 归一：
  - spot → spot
  - options → options（仅期权，如 Deribit 波指）
  - {perpetual, swap, futures, future, perp, derivatives} → perpetual
  - 规则：未知保持原样的小写；指标缺失时使用 'unknown' 兜底。
- Symbol 归一：
  - 交易对统一为 `BASE-QUOTE`（如 BTCUSDT → BTC-USDT）；OKX `-SWAP` 后缀去除，仅保留币对（如 BTC-USDT-SWAP → BTC-USDT）。

### G) 配置开关（Publisher）与默认值（建议写入 unified_data_collection.yaml 下 publish/naming）
- publish.naming.normalize_subject_exchange: true  （主题 exchange 使用基础名）
- publish.naming.normalize_subject_market_type: true（主题 market_type 使用标准三值）
- publish.naming.normalize_payload_exchange: true  （payload.exchange 覆盖为基础名）
- publish.naming.normalize_payload_market_type: true（payload.market_type 覆盖为标准三值）
- publish.naming.metrics_market_type_mode: strict | legacy（默认 strict；legacy 表示将非 spot 归并为 derivatives，仅用于回退指标口径）
- publish.naming.compat_old_subjects: false（默认关闭双发，避免存储重复；如确需临时兼容外部消费者，可短期开启并确保下游去重）

说明：以上为“临时兼容”与“可控切换”所需配置。修复稳定后可收敛为固定行为并移除开关（遵循项目“唯一配置原则”）。

### H) 具体修改点清单（函数级粒度）
- services/data-collector/collector/nats_publisher.py：
  - _generate_subject：对 exchange/market_type 调用 normalizer 归一后再 format
  - publish_data：构造 message_data 时覆盖 exchange、market_type 为标准值；尊重配置开关
  - publish_orderbook/trade/funding_rate/open_interest/liquidation/lsr_top_position/lsr_all_account/volatility_index：确保内部走 publish_data（统一逻辑）
  - 指标：record_nats_publish_labeled、record_data_success 调用前对 exchange/market_type 做同样归一（或根据 metrics_market_type_mode 切换）
  -（若存在）_publish_core/_publish_jetstream：无需改动主题结构，复用上游 subject 字符串
- services/hot-storage-service/main.py：
  - 解包/校验阶段的 market_type 标准化段：按“swap/futures/future/perp/derivatives→perpetual；options/spot 保持”的规则设置 _canon_mt，并用于入库与指标
  - 指标标签生成：
    - exchange 直接取 payload.exchange（已为基础名），不再 split('_')
    - market_type 使用 _canon_mt，空值使用 'unknown'
- services/monitoring-alerting/config/grafana/marketprism-unified.json：
  - 变量 $exchange 来源标签为基础名；$market_type 展示 spot/perpetual/options
  - 面板文案与图例：取消“derivatives 聚合”，改为分别展示 perpetual 与 options
- 不改动清单：
  - services/data-collector/collector/normalizer.py（作为工具类使用，后续可做低优先清理）
  - services/data-collector/config/collector/unified_data_collection.yaml（结构与 exchange 键保留，用于内部区分）
  - services/message-broker/config/unified_message_broker.yaml（按 data_type.> 通配，不需变更）

### I) 外部消费者影响清单与迁移建议
- 影响对象：任何精确匹配旧主题（如 trade.binance_derivatives.perpetual.BTC-USDT）的外部订阅者
- 迁移方式：
  - 更新订阅到新主题（示例：trade.binance.perpetual.BTC-USDT；funding_rate.okx.perpetual.BTC-USDT；volatility_index.deribit.options.BTC）
  - 若临时无法迁移：不建议双发至旧主题（会导致热端重复消费与入库）；如必须，可在独立环境开启 compat_old_subjects 并确保下游专用、且与生产入库隔离
- 沟通清单：
  - 发布前 3 天下发变更公告（主题差异表 + 生效时间 + 回滚窗口）
  - 提供对照表（旧→新）与订阅示例

### J) 冷存储验证清单
- 复制行为：确认冷端按窗口复制新写入的标准化行，无字段丢失
- 延迟监控：marketprism_cold_replication_lag_minutes 按表观测在预期范围内
- 抽样校验：对热/冷同一时间窗内按 exchange/market_type 计数对比，误差应为 0

### K) 回滚方案细化（操作步骤）
- 回滚主题/payload：
  1) 将 publish.naming.normalize_subject_* 与 normalize_payload_* 开关置为 false
  2)（可选）metrics_market_type_mode 切回 legacy，便于看板继续聚合展示
  3) 保持热端原 market_type 归一逻辑的兜底分支在代码中可切回（临时）
- 观察项：
  - NATS 发布速率、发布错误率、JetStream ACK 超时
  - 热端处理速率、入库错误、ClickHouse 写入耗时
  - 看板关键面板是否恢复

### L) 验收标准（Definition of Done）
- 主题：随机抽样 100 条发布消息，subject 必满足 `{data_type}.{binance|okx|deribit}.{spot|perpetual|options}.<symbol>`
- payload：同样抽样，payload.exchange ∈ {binance, okx, deribit}；payload.market_type ∈ {spot, perpetual, options}
- 指标：
  - 采集与热端的 labeled 指标中 exchange 仅有 3 个取值；market_type 仅有 3 个取值（strict 模式）
  - 指标时序在变更窗口内无显著异常（发布/处理 QPS、错误率）
- ClickHouse：
  - 新数据 time window 内按 exchange、market_type group by 结果仅出现标准值
  - 冷端复制与热端计数一致
- 看板：
  - $exchange、$market_type 维度正常工作；perpetual 与 options 图表分离展示

### M) 可选：ClickHouse 视图用于历史查询兼容（不强制落地）
- 示例（仅文档示例，不自动执行）：
  - trades_v：在 SELECT 时将旧的 derivatives/swap/futures/perp 统一投影为 'perpetual'
  - 示例 SQL：
    ```sql
    CREATE OR REPLACE VIEW marketprism_hot.trades_v AS
    SELECT
      timestamp, exchange, symbol,
      multiIf(
        lower(market_type) IN ('spot'), 'spot',
        lower(market_type) IN ('options'), 'options',
        'perpetual'
      ) AS market_type,
      /* 其他字段 */ * EXCEPT(market_type)
    FROM marketprism_hot.trades;
    ```

---

## 3. 风险与兼容性

- NATS 主题变化：
  - 变更：{exchange} 从 binance_spot/binance_derivatives 等统一为 binance/okx/deribit。
  - 影响：使用 data_type.> 的订阅（热端、Broker）不受影响；如有外部消费者精确匹配旧主题，需要同步调整。

- ClickHouse 历史数据不一致：
  - 历史存在 exchange=binance_derivatives/okx_derivatives、market_type=derivatives 等记录。
  - 方案：不做表内 UPDATE 迁移，改为查询兼容（where market_type in ('perpetual','derivatives')）。必要时提供只读视图做统一映射。

- 冷存储影响：
  - 不受主题变更影响；复制“全字段”，热端写入什么就复制什么。
  - 历史/新数据混合值将共存于冷库，与热库一致。

- 停机与过渡：
  - 可平滑：先改发布，再改热端与看板；无停机要求。提供 Publisher 侧开关以便快速回滚旧主题值（如需）。

---

## 4. 执行顺序（建议）

阶段A（发布侧）
1) 修改 NATSPublisher：主题与 payload 统一基础名/标准 market_type；指标标签同步。
2) 单测与小流量验证：本地/测试 NATS 环境检查主题与指标标签输出。

阶段B（存储/可视化）
3) 修改热端 market_type 归一策略与指标标签；去掉 exchange split('_')。
4) 更新 Grafana 变量与文案；确认 subject 解析面板仍匹配。
5) 端到端验证：采集→NATS→热端→CH→冷端复制；检查指标与看板。

回滚策略
- Publisher 增加开关（use_base_exchange_for_subject=false）可瞬时回退旧主题值。
- 热端 market_type 归一可保留旧逻辑为兜底分支（临时）。

---

## 5. 测试方案（验证与回归）

- 单元测试（采集侧）
  - NATSPublisher._generate_subject：
    - ('binance_derivatives','perpetual','BTC-USDT') → '... binance.perpetual.BTC-USDT'
    - ('okx_spot','spot','BTC-USDT') → '... okx.spot.BTC-USDT'
    - ('deribit_derivatives','options','BTC') → '... deribit.options.BTC'
  - NATSPublisher.publish_data：payload.exchange/market_type 被覆盖为标准值；record_nats_publish_labeled 标签为基础名+spot/perpetual/options。

- 集成测试（采集→NATS）
  - 启动测试 NATS/JetStream；订阅 data_type.>；发布 funding_rate/open_interest/liquidation/volatility_index 样本，断言 subject 与 payload。

- 集成测试（热端）
  - 启动热端，注入多种 market_type 同义（swap/futures/perp/derivatives）消息，入库/指标应归一为 perpetual；options 与 spot 保持。
  - exchange 指标应为基础名（binance/okx/deribit），无需 split('_')。

- 端到端（含冷存）
  - 全链路跑样本（1-2 symbols）；检查：
    - Prom 指标 marketprism_nats_messages_published_labeled_total{exchange,market_type}
    - 热端 processed_total 标签一致
    - ClickHouse 热/冷两库新数据行的 exchange/market_type 值标准化
    - 冷端复制延迟在预期内（lag 指标）

- 回归检查
  - 高频 Core NATS 和低频 JetStream 的稳定性（重连、ACK 超时）
  - Broker 严格主题开关（strict_subjects）无副作用

---

## 6. 结论与待确认
- 建议采用“在 Publisher 与 热端边界统一”的最小改造路径；冷端无需改动；配置与管理器维持现状。
- market_type 标准三值：spot/perpetual/options；不再输出 derivatives（仅保留历史兼容查询）。
- 看板同步：变量来源与文案更新（可与第二阶段一起提交）。

请确认：
1) 是否按上述路径推进（先 Publisher，后热端与看板）？
2) 是否需要 Publisher 兼容开关以便快速回退旧主题值？
3) 看板更新是否一同纳入本次提交？

