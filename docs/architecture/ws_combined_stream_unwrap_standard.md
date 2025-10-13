# WebSocket 合流/聚合流消息“预解包”标准化规范

本文档定义在各交易所管理器中引入统一“预解包（unwrap）”逻辑的规范，确保对 Binance 合流结构向后兼容，同时对 OKX / Deribit 等非合流结构保持严格 no‑op 行为（不改变现有语义），并在未来出现外层包裹时自动适配。

## 背景与目标

- Binance 合流（Combined Streams）消息外层格式：`{"stream": "...", "data": { ... }}`。
- 历史代码在多个管理器中分别手写了解包逻辑，导致重复与不一致。
- 本规范将“预解包”抽取为公共工具，在各 WS 消息入口统一调用，提升一致性与可维护性。

目标：
- 统一入口、最小侵入、严格向后兼容。
- 若顶层存在 `data` 且其值为 `dict`（即 Binance 合流样式），则自动下钻到内层；否则保持原样返回。

## 公共工具

- 路径：`services/data-collector/exchanges/common/ws_message_utils.py`
- 核心函数：

```python
def unwrap_combined_stream_message(message: Any, inner_key: str = "data") -> Any:
    """若顶层存在 data 且为 dict，则返回内部 data；否则原样返回。"""
```

> 实现仅在“顶层 data 且为字典”时生效。对 OKX（`{"arg":..., "data": [...]}`）或 Deribit（JSON‑RPC：`{"jsonrpc":"2.0", ...}`）均为严格 no‑op。

## 接入原则

- 统一在各交易所 WS 消息处理入口“尽早”调用：
  - 成交：各 `*_trades_manager.py` 的 `_process_trade_message` 开头（try 之前）。
  - 订单簿：各 `*_orderbook_manager.py`/`*_manager.py` 的 `process_websocket_message` 开头（状态校验通过后）。
  - 强平：各 `*_liquidation_manager.py` 的 `_process_liquidation_message` 开头（try 之前）。
- 不改变后续解析逻辑；只保证当出现 Binance 合流样式时能正确下钻。

## 兼容性矩阵

| 交易所 | 典型 WS 结构 | 预解包效果 |
|---|---|---|
| Binance | `{ "stream": "...", "data": { ... } }` | 生效：下钻到 `data` |
| OKX | `{ "arg": { ... }, "data": [ ... ] }` | no‑op：`data` 为 list，不解包 |
| Deribit | `{ "jsonrpc":"2.0", "method":"subscription", "params": { "data": { ... }}}` | no‑op：顶层无 `data`，不解包 |

## 已接入的管理器范围（示例）

- Binance：现货/衍生品的成交、订单簿、强平
- OKX：现货/衍生品的成交、订单簿、强平（前向兼容接入；当前为 no‑op）
- Deribit：目前仅 HTTP 轮询（波动率），WS 频道上线时按本规范接入

## 单元与集成测试

- 位置：`services/data-collector/tests/`
- 关键用例：
  - `test_ws_message_utils.py`：工具函数基础行为
  - `test_binance_spot_unwrap_integration.py`：Binance 合流解包回归
  - `test_binance_derivatives_liquidation_unwrap_integration.py`：Binance 强平解包回归
  - `test_ws_unwrap_okx_compat.py`：OKX 兼容（no‑op 与假设性包裹）
  - `test_ws_unwrap_deribit_compat.py`：Deribit JSON‑RPC 兼容（no‑op）

运行示例：

```bash
source venv/bin/activate
pytest -q services/data-collector/tests/test_ws_message_utils.py \
       services/data-collector/tests/test_binance_spot_unwrap_integration.py \
       services/data-collector/tests/test_binance_derivatives_liquidation_unwrap_integration.py \
       services/data-collector/tests/test_ws_unwrap_okx_compat.py \
       services/data-collector/tests/test_ws_unwrap_deribit_compat.py
```

## 在线快速验证建议

在本地已运行 NATS 的前提下，启动统一采集器并订阅关键主题做 2–3 分钟抽样：

```bash
source venv/bin/activate
python services/data-collector/main.py --mode launcher --log-level INFO
# 另开终端/会话，执行仅核心 NATS 订阅（避免 Durable Consumer 达上限）
VERIFY_DURATION=150 python services/message-broker/scripts/ephemeral_subscribe_validate_temp.py \
  'trade.binance_spot.spot.>' 'trade.binance_derivatives.perpetual.>' \
  'orderbook.binance_spot.spot.>' 'orderbook.binance_derivatives.perpetual.>' \
  'liquidation.binance_derivatives.perpetual.>' \
  'trade.okx_spot.spot.>' 'trade.okx_derivatives.perpetual.>' \
  'orderbook.okx_spot.spot.>' 'orderbook.okx_derivatives.perpetual.>' \
  'liquidation.okx_derivatives.perpetual.>'
```

成功标准：
- 所有目标主题收到非零消息量（强平如偶发为 0 属正常）。
- JSON 可解析、关键字段存在（symbol、timestamp、exchange）。
- 接收频率与预期一致，无明显丢包；订单簿偶发重建属正常自愈。

## 代码评审要点

- 仅在消息入口添加一行 `unwrap_combined_stream_message`，不改变后续解析流程。
- 注意缩进与异常边界：应在 try 之前调用，避免因早期返回导致未解包。
- 避免在内部二次判断/重复解包，保持唯一入口。

## 维护与扩展

- 如未来新增交易所/频道：按“接入原则”在 WS 入口统一调用，无需在各处手写解包。
- 若某交易所引入新的顶层键（非 `data`），可在调用处通过 `inner_key` 参数覆盖。
- 如需扩展到列表型外层（例如 `{"data": [...]}` 的下钻策略），应先评估现有解析对 list 的依赖关系，再谨慎演进工具函数（避免破坏 OKX 现状）。

