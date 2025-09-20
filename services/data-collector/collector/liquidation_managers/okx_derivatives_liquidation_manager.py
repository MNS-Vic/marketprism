"""
OKXDerivativesLiquidationManager - OKX衍生品强平订单数据管理器

基于OKX官方文档实现：
https://www.okx.com/docs-v5/zh/#public-data-websocket-liquidation-orders-channel

WebSocket频道：liquidation-orders
数据格式：包含instId, side, sz, bkPx, bkLoss, cTime等字段
"""

import asyncio
import json
import time
import websockets
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any

from .base_liquidation_manager import BaseLiquidationManager
from collector.data_types import Exchange, MarketType, NormalizedLiquidation, LiquidationStatus

from exchanges.common.ws_message_utils import unwrap_combined_stream_message


class OKXDerivativesLiquidationManager(BaseLiquidationManager):
    """
    OKX衍生品强平订单数据管理器

    订阅OKX的liquidation-orders频道，处理永续合约强平数据
    """

    def __init__(self, symbols: List[str], normalizer, nats_publisher, config: dict):
        """
        初始化OKX衍生品强平管理器

        Args:
            symbols: 交易对列表（如 ['BTC-USDT-SWAP', 'ETH-USDT-SWAP']）
            normalizer: 数据标准化器
            nats_publisher: NATS发布器
            config: 配置信息
        """
        super().__init__(
            exchange=Exchange.OKX_DERIVATIVES,
            market_type=MarketType.PERPETUAL,
            symbols=symbols,
            normalizer=normalizer,
            nats_publisher=nats_publisher,
            config=config
        )

        # OKX WebSocket配置
        self.ws_url = config.get('ws_url', "wss://ws.okx.com:8443/ws/v5/public")

        # OKX特定配置
        self.heartbeat_interval = config.get('heartbeat_interval', 25)  # OKX推荐25秒
        self.connection_timeout = config.get('connection_timeout', 10)

        # 🔧 修复：心跳机制配置
        self.last_message_time = 0
        self.waiting_for_pong = False
        self.ping_sent_time = 0
        self.total_pings_sent = 0
        self.total_pongs_received = 0
        self.heartbeat_failures = 0
        self.consecutive_heartbeat_failures = 0
        self.max_consecutive_failures = 3
        self.pong_timeout = 15  # pong响应超时时间（放宽，避免网络抖动误报）

        # 出站心跳（OKX要求30s内客户端需“发送”消息）
        self.last_outbound_time = 0.0
        # 默认每20s发送一次ping；同时保证小于服务器30s阈值
        self.outbound_ping_interval = max(10, min(self.heartbeat_interval - 5, 20))


        # 消息处理配置
        self.message_queue = asyncio.Queue()
        self.message_processor_task = None

        self.logger.startup(
            "OKX衍生品强平管理器初始化完成",
            symbols=symbols,
            ws_url=self.ws_url,
            heartbeat_interval=self.heartbeat_interval
        )

    async def _connect_and_listen(self):
        """连接OKX WebSocket并监听强平数据"""
        try:
            self.logger.info(
                "连接OKX衍生品强平WebSocket",
                url=self.ws_url,
                symbols=self.symbols
            )

            # 🔧 修复：禁用内置ping，使用OKX自定义心跳机制
            async with websockets.connect(
                self.ws_url,
                ping_interval=None,  # 禁用内置ping
                ping_timeout=None,   # 禁用内置ping超时
                close_timeout=10
            ) as websocket:
                self.websocket = websocket
                self.last_successful_connection = datetime.now(timezone.utc)
                self.reconnect_attempts = 0  # 重置重连计数
                self.last_message_time = time.time()  # 初始化最后消息时间

                self.logger.info(
                    "OKX衍生品强平WebSocket连接成功",
                    url=self.ws_url,
                    heartbeat_interval=self.heartbeat_interval
                )

                # 订阅强平数据
                await self._subscribe_liquidation_data()

                # 🔧 修复：创建心跳任务
                heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                # 🔧 修复：简化为直接监听消息
                try:
                    await asyncio.gather(
                        self._listen_messages(),
                        heartbeat_task,
                        return_exceptions=True
                    )
                finally:
                    # 清理任务
                    heartbeat_task.cancel()
                    if self.message_processor_task:
                        self.message_processor_task.cancel()

        except websockets.exceptions.ConnectionClosed as e:
            self.logger.warning(
                "OKX WebSocket连接关闭",
                close_code=e.code,
                close_reason=e.reason
            )
            raise
        except Exception as e:
            self.logger.error(
                "OKX WebSocket连接失败",
                error=e,
                url=self.ws_url
            )
            raise
        finally:
            # 清理消息处理器
            if self.message_processor_task and not self.message_processor_task.done():
                self.message_processor_task.cancel()
                try:
                    await self.message_processor_task
                except asyncio.CancelledError:
                    pass

    async def _subscribe_liquidation_data(self):
        """订阅OKX强平数据（按 instId 精确订阅，仅 BTC/ETH 永续）"""
        try:
            # 规范化 symbol：将 BTCUSDT/ETHUSDT 转为 BTC-USDT-SWAP/ETH-USDT-SWAP
            def to_okx_swap_inst(symbol: str) -> str:
                s = symbol.strip().upper()
                if s.endswith('-SWAP'):
                    return s
                # 处理无连字符格式
                if s in ('BTCUSDT', 'ETHUSDT'):
                    base = s[:-4]
                    return f"{base}-USDT-SWAP"
                # 处理 BTC-USDT -> 补 SWAP
                if '-' in s:
                    if not s.endswith('-SWAP'):
                        return f"{s}-SWAP"
                # 兜底：直接返回原始（由上游配置保障）
                return s

            target_symbols = [to_okx_swap_inst(sym) for sym in (self.symbols or [])]
            # 只保留 BTC/ETH 两类（防御性过滤）
            target_symbols = [s for s in target_symbols if s in ("BTC-USDT-SWAP", "ETH-USDT-SWAP")]

            if not target_symbols:
                # 若未配置，则默认订阅 BTC/ETH 永续
                target_symbols = ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]

            # 逐一发送独立订阅，精确到 instId
            for inst in target_symbols:
                subscribe_message = {
                    "op": "subscribe",
                    "args": [
                        {
                            "channel": "liquidation-orders",
                            "instType": "SWAP",
                            "instId": inst
                        }
                    ]
                }
                await self.websocket.send(json.dumps(subscribe_message))
                self.logger.info(
                    "已订阅OKX强平数据频道(instId精确)",
                    channel="liquidation-orders",
                    inst_type="SWAP",
                    inst_id=inst
                )

            # 记录最终目标集合
            self.logger.info(
                "OKX强平订阅目标汇总",
                target_symbols=target_symbols
            )

        except Exception as e:
            self.logger.error(
                "订阅OKX强平数据失败",
                error=e
            )
            raise

    async def _listen_messages(self):
        """监听WebSocket消息 - 修复为简单直接处理模式"""
        try:
            async for message in self.websocket:
                if not self.is_running:
                    break

                try:
                    # 跳过心跳响应
                    if isinstance(message, str) and message.strip().lower() == 'pong':
                        continue

                    data = json.loads(message)

                    # 跳过心跳响应（JSON格式）
                    if isinstance(data, dict) and data.get('event') in ['pong', 'subscribe']:
                        continue

                    await self._process_liquidation_message(data)

                except json.JSONDecodeError as e:
                    self.logger.error(f"❌ JSON解析失败: {e}")
                except Exception as e:
                    self.logger.error(f"❌ 处理消息失败: {e}")

        except websockets.exceptions.ConnectionClosed:
            self.logger.warning("⚠️ OKX强平WebSocket连接关闭")
        except Exception as e:
            self.logger.error(f"❌ 监听消息失败: {e}")

    async def _process_liquidation_message(self, message: dict):
        """处理OKX强平消息 - 修复为简单直接处理"""
        # 统一预解包（OKX当前data为list，此处为前向兼容）
        message = unwrap_combined_stream_message(message)

        try:
            # 检查是否是强平数据
            if not isinstance(message, dict) or 'data' not in message:
                return

            data_list = message.get('data', [])
            if not data_list:
                return

            for liquidation_item in data_list:
                self.stats['liquidations_received'] = self.stats.get('liquidations_received', 0) + 1

                # 解析并标准化强平数据
                normalized_liquidation = await self._parse_liquidation_message(liquidation_item)
                if normalized_liquidation:
                    await self._process_liquidation_data(normalized_liquidation)
                    self.stats['liquidations_processed'] = self.stats.get('liquidations_processed', 0) + 1

                    self.logger.data_processed(
                        "OKX强平数据处理完成",
                        symbol=liquidation_item.get('instId'),
                        side=liquidation_item.get('side'),
                        size=liquidation_item.get('sz')
                    )

        except Exception as e:
            self.logger.error(
                "处理OKX强平消息失败",
                error=e,
                message_preview=str(message)[:200]
            )
            self.stats['errors'] = self.stats.get('errors', 0) + 1

    # 删除复杂的消息处理器，使用简单直接处理

    # 删除旧的复杂处理方法，已被 _process_liquidation_message 替代

    async def _parse_liquidation_message(self, liquidation_item: dict) -> Optional[NormalizedLiquidation]:
        """
        解析OKX强平消息并返回标准化数据

        实际OKX强平数据格式有两种可能：
        1. 嵌套格式：{"instId": "BTC-USDT-SWAP", "details": [{"side": "buy", ...}]}
        2. 扁平格式：{"instId": "BTC-USDT-SWAP", "side": "buy", "sz": "0.1", ...}

        Args:
            liquidation_item: OKX单个强平数据项

        Returns:
            标准化的强平数据对象
        """
        try:
            # 获取交易对ID
            inst_id = liquidation_item.get('instId', '')
            if not inst_id:
                self.logger.warning("OKX强平数据缺少instId字段", data=liquidation_item)
                return None

            # 检查数据格式：嵌套格式还是扁平格式
            if 'details' in liquidation_item:
                # 嵌套格式：从details数组中获取数据
                details = liquidation_item.get('details', [])
                if not details:
                    self.logger.warning("OKX强平数据details为空", inst_id=inst_id)
                    return None
                detail = details[0]  # 处理第一个详情
            else:
                # 扁平格式：直接使用liquidation_item作为detail
                detail = liquidation_item

            # 统一改为委托 normalizer（就地完成时间戳统一为UTC毫秒字符串）
            # 构造通用格式数据
            liquidation_raw = {
                'instId': inst_id,
                'side': detail.get("side", ""),
                'sz': detail.get("sz", "0"),
                'bkPx': detail.get("bkPx", "0"),
                'bkLoss': detail.get("bkLoss", "0"),
                'ts': detail.get("ts", "0"),
                'cTime': detail.get("cTime") or detail.get("ts", "0")  # 强平时间，优先使用cTime
            }

            # 使用通用的强平数据标准化方法
            norm = self.normalizer.normalize_liquidation(
                exchange="okx_derivatives",
                market_type="perpetual",
                symbol=inst_id,
                raw_data=liquidation_raw
            )

            # 封装为 NormalizedLiquidation 对象（保持与基类兼容）
            from collector.data_types import LiquidationSide
            from datetime import datetime, timezone
            from decimal import Decimal

            def dec_or_none(x):
                try:
                    return Decimal(str(x)) if x is not None else None
                except Exception:
                    return None

            # 解析交易方向
            side_str = norm.get('side', '').lower()
            trade_side = LiquidationSide.BUY if side_str == 'buy' else LiquidationSide.SELL

            # 计算必需字段
            price_val = dec_or_none(norm.get('price')) or Decimal('0')
            quantity_val = dec_or_none(norm.get('quantity')) or Decimal('0')
            notional_val = price_val * quantity_val

            # 解析事件时间戳（优先使用标准化后的毫秒时间戳）
            ts_candidate = norm.get('timestamp') or norm.get('liquidation_time') or norm.get('ts')
            ts_ms = None
            try:
                if ts_candidate is not None:
                    ts_str = str(ts_candidate)
                    if ts_str.isdigit():
                        # 纯毫秒数字
                        ts_ms = int(ts_str)
                    else:
                        # 尝试从ISO/格式化字符串解析到毫秒
                        t = ts_str.replace('T', ' ').replace('Z', '')
                        if '+' in t:
                            t = t.split('+')[0]
                        if '.' in t:
                            head, frac = t.split('.', 1)
                            frac = ''.join(ch for ch in frac if ch.isdigit())
                            frac = (frac + '000')[:3]
                            t = f"{head}.{frac}"
                        else:
                            t = f"{t}.000"
                        try:
                            dt = datetime.strptime(t, "%Y-%m-%d %H:%M:%S.%f")
                            ts_ms = int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
                        except Exception:
                            ts_ms = None
            except Exception:
                ts_ms = None

            # 回退：使用系统当前时间（毫秒）
            if ts_ms is None:
                ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

            # 生成强平ID（稳定去重：事件毫秒时间戳 + 合约ID + 方向）
            liquidation_id = f"okx_{ts_ms}_{inst_id}_{side_str}"

            # 解析强平时间（使用事件时间戳）
            liquidation_time = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)

            normalized_liquidation = NormalizedLiquidation(
                exchange_name="okx_derivatives",
                symbol_name=norm.get('symbol', inst_id),
                product_type="perpetual",
                instrument_id=norm.get('instrument_id', inst_id),
                liquidation_id=liquidation_id,
                side=trade_side,
                status=LiquidationStatus.FILLED,  # OKX 强平数据通常是已成交
                quantity=quantity_val,
                price=price_val,
                notional_value=notional_val,
                liquidation_time=liquidation_time,
                timestamp=datetime.now(timezone.utc),
                raw_data=liquidation_item
            )

            if normalized_liquidation:
                self.logger.debug(
                    "OKX强平数据解析成功(委托 normalizer)",
                    symbol=normalized_liquidation.symbol_name,
                    side=normalized_liquidation.side.value,
                    quantity=str(normalized_liquidation.quantity),
                    price=str(normalized_liquidation.price)
                )
            else:
                self.logger.warning(
                    "OKX强平数据标准化失败",
                    inst_id=inst_id,
                    detail_preview=str(detail)[:200]
                )

            return normalized_liquidation

        except Exception as e:
            self.logger.error(
                "解析OKX强平消息失败",
                error=e,
                liquidation_item_preview=str(liquidation_item)[:200]
            )
            return None

    async def _heartbeat_loop(self):
        """OKX心跳循环"""
        try:
            while self.is_running and self.websocket:
                await asyncio.sleep(self.heartbeat_interval)

                if not self.is_running or not self.websocket:
                    break

                # 发送ping消息
                ping_msg = "ping"
                await self.websocket.send(ping_msg)
                self.logger.debug("发送OKX心跳ping")

        except Exception as e:
            self.logger.error("OKX心跳循环异常", error=e)

    # 使用基类的简单停止方法

    # 使用基类的简单统计方法
