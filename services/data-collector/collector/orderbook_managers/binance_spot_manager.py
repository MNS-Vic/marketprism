"""
Binance现货订单簿管理器 - 简化架构版本
采用定期快照获取策略，避免复杂的状态同步逻辑
参考Binance衍生品管理器的实现架构
"""

import asyncio
import json
import time
from typing import Dict, List, Optional
from datetime import datetime, timezone
from decimal import Decimal
import websockets

from .base_orderbook_manager import BaseOrderBookManager
from ..data_types import OrderBookSnapshot, NormalizedOrderBook
from ..error_management.error_handler import ErrorHandler, BinanceAPIError, RetryHandler
import structlog


class BinanceSpotOrderBookManager(BaseOrderBookManager):
    """Binance现货订单簿管理器 - 简化架构版本（定期快照）"""
    
    def __init__(self, symbols: List[str], normalizer, nats_publisher, config: dict):
        """
        初始化简化的Binance现货订单簿管理器

        Args:
            symbols: 交易对列表
            normalizer: 数据标准化器
            nats_publisher: NATS发布器
            config: 配置字典
        """
        # 先设置必要的属性，因为基类__init__会调用_get_snapshot_depth()等方法
        self.api_base_url = config.get('api_base_url', 'https://api.binance.com')
        self.depth_limit = config.get('depth_limit', 500)
        self.snapshot_interval = config.get('snapshot_interval', 1)  # 默认1秒间隔

        super().__init__(
            exchange="binance_spot",
            market_type="spot",
            symbols=symbols,
            normalizer=normalizer,
            nats_publisher=nats_publisher,
            config=config
        )
        
        # WebSocket API配置
        self.ws_api_url = "wss://ws-api.binance.com:443/ws-api/v3"
        self.ws_api_client = None
        self.ws_api_lock = asyncio.Lock()
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self.ws_api_connected = False
        self.ws_api_last_pong = time.time()
        
        # 快照获取任务
        self.snapshot_tasks: Dict[str, asyncio.Task] = {}
        self.running = False
        
        self.logger = structlog.get_logger("collector.orderbook_managers.binance_spot")

        self.logger.info("🏭 Binance现货订单簿管理器初始化完成（简化架构）",
                        symbols=symbols,
                        api_base_url=self.api_base_url,
                        depth_limit=self.depth_limit,
                        snapshot_interval=self.snapshot_interval)
        
    async def start(self):
        """启动简化的订单簿管理器"""
        self.logger.info("🚀 启动简化Binance现货订单簿管理器",
                        symbols=self.symbols,
                        snapshot_interval=self.snapshot_interval)

        # 设置运行状态（同时设置基类和本类的状态）
        self.running = True
        self._is_running = True  # 设置基类的运行状态，供健康检查使用
        
        # 建立持久WebSocket API连接
        if not await self._ensure_ws_api_connection():
            raise Exception("无法建立WebSocket API连接")
        
        # 为每个symbol启动定期快照任务
        for symbol in self.symbols:
            task = asyncio.create_task(self._periodic_snapshot_task(symbol))
            self.snapshot_tasks[symbol] = task
            self.logger.info(f"✅ {symbol}定期快照任务已启动")
        
        self.logger.info("✅ 简化订单簿管理器启动完成")

    async def _exchange_specific_initialization(self):
        """交易所特定的初始化逻辑"""
        # 简化架构不需要复杂的初始化，直接启动快照任务
        pass

    async def _exchange_specific_cleanup(self):
        """交易所特定的清理逻辑"""
        # 关闭持久WebSocket API连接
        await self._close_ws_api_connection()
        self.logger.info("🧹 WebSocket API连接已清理")

    # 实现基类要求的抽象方法
    def _get_snapshot_depth(self) -> int:
        """获取快照深度"""
        return self.depth_limit

    def _get_websocket_depth(self) -> int:
        """获取WebSocket深度"""
        return self.depth_limit

    async def initialize_orderbook_states(self):
        """初始化订单簿状态 - 简化版本不需要复杂状态"""
        self.logger.info("🚀 简化架构：跳过复杂状态初始化")
        pass

    async def process_websocket_message(self, symbol: str, message: dict):
        """处理WebSocket消息 - 简化版本不处理Stream消息"""
        self.logger.debug(f"🔄 简化架构：忽略WebSocket Stream消息: {symbol}")
        pass

    async def _apply_snapshot(self, symbol: str, snapshot_data: dict, state):
        """应用快照 - 简化版本不维护本地状态"""
        self.logger.debug(f"🔄 简化架构：不维护本地快照状态: {symbol}")
        pass

    async def _apply_update(self, symbol: str, update: dict, state):
        """应用更新 - 简化版本不处理增量更新"""
        self.logger.debug(f"🔄 简化架构：不处理增量更新: {symbol}")
        pass

    async def _fetch_initial_snapshot(self, symbol: str):
        """获取初始快照 - 简化版本使用WebSocket API"""
        return await self._fetch_websocket_api_snapshot(symbol)

    async def _validate_message_sequence(self, symbol: str, message: dict, state) -> bool:
        """验证消息序列 - 简化版本不需要序列验证"""
        return True

    async def _perform_reconnection(self, symbol: str):
        """执行重连 - 简化版本不需要重连逻辑"""
        self.logger.info(f"🔄 简化架构：不需要重连逻辑: {symbol}")
        pass
    
    async def stop(self):
        """停止简化的订单簿管理器"""
        self.logger.info("🛑 停止简化Binance现货订单簿管理器")

        # 设置停止状态（同时设置基类和本类的状态）
        self.running = False
        self._is_running = False  # 设置基类的运行状态
        
        # 停止所有快照任务
        for symbol, task in self.snapshot_tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            self.logger.info(f"🛑 {symbol}快照任务已停止")
        
        # 关闭WebSocket API连接
        await self._close_ws_api_connection()
        
        self.logger.info("✅ 简化订单簿管理器已停止")
    
    async def _periodic_snapshot_task(self, symbol: str):
        """定期获取快照的任务"""
        self.logger.info(f"🔄 {symbol}开始定期快照任务", interval=self.snapshot_interval)
        
        while self.running:
            try:
                # 获取最新快照
                snapshot = await self._fetch_websocket_api_snapshot(symbol)
                
                if snapshot:
                    # 标准化数据
                    normalized_data = self._normalize_snapshot(symbol, snapshot)
                    
                    # 推送到NATS
                    if self.nats_publisher and normalized_data:
                        await self._publish_to_nats(symbol, normalized_data)
                        self.logger.debug(f"✅ {symbol}快照已推送到NATS")

                    # 降级为DEBUG级别，减少频繁的INFO日志
                    self.logger.debug(f"✅ {symbol}快照处理完成",
                                    last_update_id=snapshot.last_update_id,
                                    bids_count=len(snapshot.bids),
                                    asks_count=len(snapshot.asks))
                else:
                    self.logger.warning(f"⚠️ {symbol}快照获取失败")
                
                # 等待下次获取
                await asyncio.sleep(self.snapshot_interval)
                
            except asyncio.CancelledError:
                self.logger.info(f"🛑 {symbol}快照任务被取消")
                break
            except Exception as e:
                self.logger.error(f"❌ {symbol}快照任务异常", error=str(e))
                # 错误时等待更长时间再重试
                await asyncio.sleep(min(self.snapshot_interval * 2, 10))
    
    def _normalize_snapshot(self, symbol: str, snapshot: OrderBookSnapshot) -> Optional[dict]:
        """标准化快照数据"""
        try:
            if not self.normalizer:
                return None

            # 先创建EnhancedOrderBook对象
            from ..data_types import PriceLevel, EnhancedOrderBook, OrderBookUpdateType

            # 转换为PriceLevel对象
            bids = [PriceLevel(price=price, quantity=qty) for price, qty in snapshot.bids]
            asks = [PriceLevel(price=price, quantity=qty) for price, qty in snapshot.asks]

            # 创建EnhancedOrderBook对象
            enhanced_orderbook = EnhancedOrderBook(
                exchange_name="binance_spot",
                symbol_name=symbol,
                market_type="spot",
                last_update_id=snapshot.last_update_id,
                bids=bids,
                asks=asks,
                timestamp=snapshot.timestamp or datetime.now(timezone.utc),
                update_type=OrderBookUpdateType.SNAPSHOT,
                depth_levels=len(bids) + len(asks),
                is_valid=True
            )

            # 使用正确的参数调用标准化器
            normalized = self.normalizer.normalize_orderbook(
                exchange="binance_spot",
                market_type="spot",
                symbol=symbol,
                orderbook=enhanced_orderbook
            )

            return normalized

        except Exception as e:
            self.logger.error(f"❌ {symbol}数据标准化失败", error=str(e))
            return None
    
    async def _publish_to_nats(self, symbol: str, normalized_data: dict):
        """推送数据到NATS"""
        try:
            # 使用正确的参数调用publish_orderbook
            # 参数顺序：exchange, market_type, symbol, orderbook_data
            success = await self.nats_publisher.publish_orderbook(
                exchange="binance_spot",
                market_type="spot",
                symbol=symbol,
                orderbook_data=normalized_data
            )

            if success:
                self.logger.debug(f"✅ {symbol}NATS推送成功")
            else:
                self.logger.warning(f"⚠️ {symbol}NATS推送返回失败")

        except Exception as e:
            self.logger.error(f"❌ {symbol}NATS推送失败", error=str(e))
    
    def _get_unique_key(self, symbol: str) -> str:
        """生成唯一键"""
        return f"binance_spot_spot_{symbol}"

    async def _ensure_ws_api_connection(self) -> bool:
        """确保WebSocket API连接建立"""
        async with self.ws_api_lock:
            if self.ws_api_connected and self.ws_api_client:
                return True

            try:
                self.logger.info("🔗 建立WebSocket API连接", url=self.ws_api_url)

                self.ws_api_client = await asyncio.wait_for(
                    websockets.connect(
                        self.ws_api_url,
                        ping_interval=None,  # 禁用自动ping，使用服务器的ping
                        ping_timeout=None,
                        close_timeout=10
                    ),
                    timeout=30.0  # 30秒连接超时
                )

                self.ws_api_connected = True
                self.ws_api_last_pong = time.time()

                # 启动消息处理任务
                asyncio.create_task(self._handle_ws_api_messages())

                self.logger.info("✅ WebSocket API连接建立成功")
                return True

            except Exception as e:
                self.logger.error("❌ WebSocket API连接失败", error=str(e))
                self.ws_api_connected = False
                self.ws_api_client = None
                return False

    async def _close_ws_api_connection(self):
        """关闭WebSocket API连接"""
        async with self.ws_api_lock:
            if self.ws_api_client:
                try:
                    await self.ws_api_client.close()
                    self.logger.info("🔌 WebSocket API连接已关闭")
                except Exception as e:
                    self.logger.error("❌ 关闭WebSocket API连接异常", error=str(e))
                finally:
                    self.ws_api_client = None
                    self.ws_api_connected = False

    async def _handle_ws_api_messages(self):
        """处理WebSocket API消息"""
        try:
            async for message in self.ws_api_client:
                try:
                    data = json.loads(message)

                    # 处理响应消息
                    if 'id' in data:
                        request_id = data['id']
                        if request_id in self.pending_requests:
                            future = self.pending_requests[request_id]
                            if not future.done():
                                future.set_result(data)

                    # 处理ping/pong
                    elif data.get('method') == 'ping':
                        # 响应ping
                        pong_response = {
                            "id": data.get('id'),
                            "result": {}
                        }
                        await self.ws_api_client.send(json.dumps(pong_response))
                        self.ws_api_last_pong = time.time()
                        self.logger.debug("🏓 WebSocket API pong已发送")

                except json.JSONDecodeError:
                    self.logger.error("❌ WebSocket API消息JSON解析失败", message=message)
                except Exception as e:
                    self.logger.error("❌ WebSocket API消息处理异常", error=str(e))

        except websockets.exceptions.ConnectionClosed:
            self.logger.warning("⚠️ WebSocket API连接已关闭")
            self.ws_api_connected = False
        except Exception as e:
            self.logger.error("❌ WebSocket API消息处理循环异常", error=str(e))
            self.ws_api_connected = False

    async def _fetch_websocket_api_snapshot(self, symbol: str, limit: int = None) -> Optional[OrderBookSnapshot]:
        """通过WebSocket API获取订单簿快照"""
        if limit is None:
            limit = self.depth_limit

        # 确保连接可用
        if not await self._ensure_ws_api_connection():
            self.logger.error(f"❌ WebSocket API连接不可用: {symbol}")
            return None

        try:
            # 生成请求ID
            request_id = f"depth_{symbol}_{int(time.time() * 1000)}"

            # 构建深度请求
            depth_request = {
                "id": request_id,
                "method": "depth",
                "params": {
                    "symbol": symbol,
                    "limit": limit
                }
            }

            # 创建Future等待响应
            future = asyncio.Future()
            self.pending_requests[request_id] = future

            try:
                # 发送请求
                await self.ws_api_client.send(json.dumps(depth_request))
                self.logger.debug(f"📤 WebSocket API请求已发送: {symbol}")

                # 等待响应
                response_data = await asyncio.wait_for(future, timeout=10.0)

                # 检查响应状态
                if response_data.get('status') != 200:
                    error_info = response_data.get('error', {})
                    self.logger.error(f"❌ WebSocket API请求失败: {symbol}, status={response_data.get('status')}, error={error_info}")
                    return None

                # 解析响应数据
                result = response_data.get('result', {})
                if not result:
                    self.logger.error(f"❌ WebSocket API响应无数据: {symbol}")
                    return None

                # 创建OrderBookSnapshot对象
                snapshot = OrderBookSnapshot(
                    symbol=symbol,
                    exchange="binance_spot",
                    last_update_id=result.get('lastUpdateId'),
                    bids=[(Decimal(bid[0]), Decimal(bid[1])) for bid in result.get('bids', [])],
                    asks=[(Decimal(ask[0]), Decimal(ask[1])) for ask in result.get('asks', [])],
                    timestamp=datetime.now(timezone.utc)
                )

                self.logger.debug(f"✅ {symbol}快照获取成功, lastUpdateId={snapshot.last_update_id}")
                return snapshot

            finally:
                # 清理待处理的请求
                self.pending_requests.pop(request_id, None)

        except asyncio.TimeoutError:
            self.logger.error(f"❌ WebSocket API请求超时: {symbol}")
            return None
        except Exception as e:
            self.logger.error(f"❌ WebSocket API请求异常: {symbol}, error={e}")
            return None
