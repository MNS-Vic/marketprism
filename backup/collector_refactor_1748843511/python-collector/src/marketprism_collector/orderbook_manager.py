"""
OrderBook Manager - 订单簿管理器

实现交易所订单簿的本地维护，支持快照+增量更新模式
参考Binance和OKX官方文档的最佳实践
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple, Set
from collections import deque, defaultdict
import structlog
from dataclasses import dataclass, field

from .types import (
    Exchange, PriceLevel, EnhancedOrderBook, OrderBookDelta, 
    OrderBookUpdateType, ExchangeConfig
)
from .normalizer import DataNormalizer


@dataclass
class OrderBookSnapshot:
    """订单簿快照"""
    symbol: str
    exchange: str
    last_update_id: int
    bids: List[PriceLevel]
    asks: List[PriceLevel]
    timestamp: datetime
    checksum: Optional[int] = None


@dataclass
class OrderBookUpdate:
    """订单簿增量更新"""
    symbol: str
    exchange: str
    first_update_id: int
    last_update_id: int
    bids: List[PriceLevel]
    asks: List[PriceLevel]
    timestamp: datetime
    prev_update_id: Optional[int] = None


@dataclass
class OrderBookState:
    """订单簿状态管理"""
    symbol: str
    exchange: str
    local_orderbook: Optional[OrderBookSnapshot] = None
    update_buffer: deque = field(default_factory=deque)
    last_update_id: int = 0
    last_snapshot_time: datetime = field(default_factory=datetime.utcnow)
    is_synced: bool = False
    error_count: int = 0
    total_updates: int = 0
    
    # 新增：Binance官方同步算法需要的字段
    first_update_id: Optional[int] = None  # 第一个收到的更新的U值
    snapshot_last_update_id: Optional[int] = None  # 快照的lastUpdateId
    sync_in_progress: bool = False  # 是否正在同步中
    
    def __post_init__(self):
        if not self.update_buffer:
            self.update_buffer = deque(maxlen=1000)  # 限制缓冲区大小


class OrderBookManager:
    """订单簿管理器 - 支持多交易所的订单簿维护"""
    
    def __init__(self, config: ExchangeConfig, normalizer: DataNormalizer):
        self.config = config
        self.normalizer = normalizer
        self.logger = structlog.get_logger(__name__)
        
        # 订单簿状态管理
        self.orderbook_states: Dict[str, OrderBookState] = {}
        self.snapshot_tasks: Dict[str, asyncio.Task] = {}
        self.update_tasks: Dict[str, asyncio.Task] = {}
        
        # 配置参数
        self.snapshot_interval = config.snapshot_interval  # 快照刷新间隔
        # 统一使用400档深度，提高性能和一致性
        self.depth_limit = 400  # 统一400档深度
        if config.exchange == Exchange.OKX:
            self.okx_snapshot_sync_interval = 300  # OKX定时快照同步间隔（5分钟）
        self.max_error_count = 5  # 最大错误次数
        self.sync_timeout = 30  # 同步超时时间
        
        # OKX WebSocket客户端
        self.okx_ws_client = None
        self.okx_snapshot_sync_tasks = {}  # OKX定时快照同步任务
        
        # API频率限制控制
        self.last_snapshot_request = {}  # 每个交易对的最后请求时间
        self.min_snapshot_interval = 30.0  # 最小快照请求间隔（30秒，更保守）
        self.api_weight_used = 0  # 当前使用的API权重
        self.api_weight_limit = 1200  # 每分钟权重限制（保守值，实际是6000）
        self.weight_reset_time = datetime.utcnow()  # 权重重置时间
        self.consecutive_errors = 0  # 连续错误计数
        self.backoff_multiplier = 1.0  # 退避倍数
        
        # HTTP客户端
        self.session: Optional[aiohttp.ClientSession] = None
        
        # 统计信息
        self.stats = {
            'snapshots_fetched': 0,
            'updates_processed': 0,
            'sync_errors': 0,
            'resync_count': 0
        }
    
    async def start(self, symbols: List[str]) -> bool:
        """启动订单簿管理器"""
        try:
            # 创建HTTP客户端（支持代理）
            import os
            
            # 获取代理设置
            proxy = None
            http_proxy = os.getenv('http_proxy') or os.getenv('HTTP_PROXY')
            https_proxy = os.getenv('https_proxy') or os.getenv('HTTPS_PROXY')
            
            if https_proxy or http_proxy:
                proxy = https_proxy or http_proxy
                self.logger.info("使用代理连接REST API", proxy=proxy)
            
            # 创建连接器
            connector = aiohttp.TCPConnector(limit=100)
            
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
                connector=connector
            )
            
            # 如果有代理，设置代理
            if proxy:
                self.proxy = proxy
            else:
                self.proxy = None
            
            # 根据交易所类型启动不同的管理模式
            if self.config.exchange == Exchange.OKX:
                # OKX使用WebSocket + 定时快照同步模式
                await self._start_okx_management(symbols)
            else:
                # 其他交易所使用传统的快照+缓冲模式
                for symbol in symbols:
                    await self.start_symbol_management(symbol)
            
            self.logger.info(
                "订单簿管理器启动成功",
                exchange=self.config.exchange.value,
                symbols=symbols,
                depth_limit=self.depth_limit,
                mode="WebSocket+定时同步" if self.config.exchange == Exchange.OKX else "快照+缓冲"
            )
            return True
            
        except Exception as e:
            self.logger.error(
                "订单簿管理器启动失败",
                error=str(e),
                exchange=self.config.exchange.value
            )
            return False
    
    async def stop(self):
        """停止订单簿管理器"""
        # 停止OKX WebSocket客户端
        if self.okx_ws_client:
            await self.okx_ws_client.stop()
        
        # 取消所有任务
        all_tasks = (list(self.snapshot_tasks.values()) + 
                    list(self.update_tasks.values()) + 
                    list(self.okx_snapshot_sync_tasks.values()))
        for task in all_tasks:
            if not task.done():
                task.cancel()
        
        # 等待任务完成
        if all_tasks:
            await asyncio.gather(*all_tasks, return_exceptions=True)
        
        # 关闭HTTP客户端
        if self.session:
            await self.session.close()
        
        self.logger.info(
            "订单簿管理器已停止",
            exchange=self.config.exchange.value,
            stats=self.stats
        )
    
    async def start_symbol_management(self, symbol: str):
        """启动单个交易对的订单簿管理"""
        # 初始化状态
        self.orderbook_states[symbol] = OrderBookState(
            symbol=symbol,
            exchange=self.config.exchange.value
        )
        
        # 启动管理任务
        task = asyncio.create_task(self.maintain_orderbook(symbol))
        self.snapshot_tasks[symbol] = task
        
        self.logger.info(
            "启动交易对订单簿管理",
            symbol=symbol,
            exchange=self.config.exchange.value
        )
    
    async def _start_okx_management(self, symbols: List[str]):
        """启动OKX订单簿管理（WebSocket + 定时快照同步）"""
        # 初始化所有交易对的状态
        for symbol in symbols:
            self.orderbook_states[symbol] = OrderBookState(
                symbol=symbol,
                exchange=self.config.exchange.value
            )
        
        # 首先获取初始快照
        for symbol in symbols:
            await self._initialize_okx_orderbook(symbol)
        
        # 创建OKX WebSocket客户端
        from .okx_websocket import OKXWebSocketClient
        self.okx_ws_client = OKXWebSocketClient(
            symbols=symbols,
            on_orderbook_update=self._handle_okx_websocket_update
        )
        
        # 启动WebSocket客户端
        ws_task = asyncio.create_task(self.okx_ws_client.start())
        self.snapshot_tasks['okx_websocket'] = ws_task
        
        # 为每个交易对启动定时快照同步任务
        for symbol in symbols:
            sync_task = asyncio.create_task(self._okx_snapshot_sync_loop(symbol))
            self.okx_snapshot_sync_tasks[symbol] = sync_task
        
        self.logger.info(
            "OKX订单簿管理启动",
            symbols=symbols,
            websocket_url=self.okx_ws_client.ws_url,
            sync_interval=self.okx_snapshot_sync_interval
        )
    
    async def _handle_okx_websocket_update(self, symbol: str, update):
        """处理OKX WebSocket订单簿更新"""
        try:
            state = self.orderbook_states.get(symbol)
            if not state:
                self.logger.warning("收到未管理交易对的OKX更新", symbol=symbol)
                return
            
            # 如果已经初始化，直接应用更新
            if state.is_synced and state.local_orderbook:
                # 直接应用WebSocket更新到本地订单簿
                enhanced_orderbook = await self._apply_okx_update(symbol, update)
                if enhanced_orderbook:
                    state.total_updates += 1
                    state.last_update_id = update.last_update_id
                    self.stats['updates_processed'] += 1
                    
                    # 每100次更新记录一次
                    if state.total_updates % 100 == 0:
                        self.logger.info(
                            "OKX订单簿更新统计",
                            symbol=symbol,
                            total_updates=state.total_updates,
                            last_update_id=state.last_update_id,
                            seq_id=update.last_update_id
                        )
                
        except Exception as e:
            self.logger.error(
                "处理OKX WebSocket更新失败",
                symbol=symbol,
                error=str(e)
            )
    
    async def _apply_okx_update(self, symbol: str, update) -> Optional[EnhancedOrderBook]:
        """应用OKX WebSocket更新到本地订单簿"""
        try:
            state = self.orderbook_states[symbol]
            local_book = state.local_orderbook
            
            if not local_book:
                self.logger.warning("本地订单簿未初始化", symbol=symbol)
                return None
            
            # 复制当前订单簿
            new_bids = {level.price: level.quantity for level in local_book.bids}
            new_asks = {level.price: level.quantity for level in local_book.asks}
            
            # 记录变化
            bid_changes = []
            ask_changes = []
            removed_bids = []
            removed_asks = []
            
            # 应用买单更新
            for level in update.bids:
                if level.quantity == 0:
                    # 删除价位
                    if level.price in new_bids:
                        del new_bids[level.price]
                        removed_bids.append(level.price)
                else:
                    # 更新或添加价位
                    old_qty = new_bids.get(level.price, Decimal('0'))
                    if old_qty != level.quantity:
                        new_bids[level.price] = level.quantity
                        bid_changes.append(level)
            
            # 应用卖单更新
            for level in update.asks:
                if level.quantity == 0:
                    # 删除价位
                    if level.price in new_asks:
                        del new_asks[level.price]
                        removed_asks.append(level.price)
                else:
                    # 更新或添加价位
                    old_qty = new_asks.get(level.price, Decimal('0'))
                    if old_qty != level.quantity:
                        new_asks[level.price] = level.quantity
                        ask_changes.append(level)
            
            # 排序并转换为列表
            sorted_bids = [
                PriceLevel(price=price, quantity=qty)
                for price, qty in sorted(new_bids.items(), key=lambda x: x[0], reverse=True)
            ]
            sorted_asks = [
                PriceLevel(price=price, quantity=qty)
                for price, qty in sorted(new_asks.items(), key=lambda x: x[0])
            ]
            
            # 更新本地订单簿
            state.local_orderbook.bids = sorted_bids
            state.local_orderbook.asks = sorted_asks
            state.local_orderbook.last_update_id = update.last_update_id
            state.local_orderbook.timestamp = update.timestamp
            
            # 创建增强订单簿
            from .types import EnhancedOrderBook, OrderBookUpdateType
            enhanced_orderbook = EnhancedOrderBook(
                exchange_name=self.config.exchange.value,
                symbol_name=symbol,
                last_update_id=update.last_update_id,
                bids=sorted_bids,
                asks=sorted_asks,
                timestamp=update.timestamp,
                update_type=OrderBookUpdateType.UPDATE,
                first_update_id=update.first_update_id,
                prev_update_id=update.prev_update_id,
                depth_levels=len(sorted_bids) + len(sorted_asks),
                bid_changes=bid_changes if bid_changes else None,
                ask_changes=ask_changes if ask_changes else None,
                removed_bids=removed_bids if removed_bids else None,
                removed_asks=removed_asks if removed_asks else None
            )
            
            return enhanced_orderbook
            
        except Exception as e:
            self.logger.error(
                "应用OKX更新失败",
                symbol=symbol,
                error=str(e)
            )
            return None
    
    async def _okx_snapshot_sync_loop(self, symbol: str):
        """OKX定时快照同步循环"""
        while True:
            try:
                # 等待同步间隔
                await asyncio.sleep(self.okx_snapshot_sync_interval)
                
                # 获取快照并同步
                await self._sync_okx_snapshot(symbol)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(
                    "OKX快照同步失败",
                    symbol=symbol,
                    error=str(e)
                )
                # 错误后等待较短时间再重试
                await asyncio.sleep(30)
    
    async def _sync_okx_snapshot(self, symbol: str):
        """同步OKX快照，防止累积误差"""
        try:
            # 获取最新快照
            snapshot = await self._fetch_okx_snapshot(symbol)
            if not snapshot:
                return
            
            state = self.orderbook_states[symbol]
            
            # 比较WebSocket状态和快照状态
            ws_state = self.okx_ws_client.orderbook_states.get(symbol, {}) if self.okx_ws_client else {}
            ws_seq_id = ws_state.get('last_seq_id', 0)
            snapshot_timestamp = int(snapshot.timestamp.timestamp() * 1000)
            
            # 如果快照比WebSocket状态新，更新本地订单簿
            if snapshot_timestamp > ws_state.get('last_timestamp', 0):
                state.local_orderbook = snapshot
                state.last_update_id = snapshot.last_update_id
                state.last_snapshot_time = snapshot.timestamp
                
                self.logger.info(
                    "OKX快照同步完成",
                    symbol=symbol,
                    snapshot_timestamp=snapshot_timestamp,
                    ws_seq_id=ws_seq_id,
                    bids_count=len(snapshot.bids),
                    asks_count=len(snapshot.asks)
                )
            else:
                self.logger.debug(
                    "OKX快照无需同步",
                    symbol=symbol,
                    snapshot_timestamp=snapshot_timestamp,
                    ws_timestamp=ws_state.get('last_timestamp', 0)
                )
                
        except Exception as e:
            self.logger.error(
                "OKX快照同步异常",
                symbol=symbol,
                error=str(e)
            )
    
    async def _initialize_okx_orderbook(self, symbol: str):
        """初始化OKX订单簿"""
        try:
            # 获取初始快照
            snapshot = await self._fetch_okx_snapshot(symbol)
            if snapshot:
                state = self.orderbook_states[symbol]
                state.local_orderbook = snapshot
                state.last_update_id = snapshot.last_update_id
                state.last_snapshot_time = snapshot.timestamp
                state.is_synced = True
                
                self.logger.info(
                    "OKX订单簿初始化完成",
                    symbol=symbol,
                    bids_count=len(snapshot.bids),
                    asks_count=len(snapshot.asks),
                    last_update_id=snapshot.last_update_id
                )
            else:
                self.logger.error("获取OKX初始快照失败", symbol=symbol)
                
        except Exception as e:
            self.logger.error(
                "OKX订单簿初始化异常",
                symbol=symbol,
                error=str(e)
            )
    
    async def maintain_orderbook(self, symbol: str):
        """维护单个交易对的订单簿"""
        state = self.orderbook_states[symbol]
        
        # 初始启动延迟，避免所有交易对同时请求
        initial_delay = hash(symbol) % 10  # 0-9秒的随机延迟
        await asyncio.sleep(initial_delay)
        self.logger.info(
            "订单簿维护启动",
            symbol=symbol,
            initial_delay=initial_delay
        )
        
        while True:
            try:
                # 1. 获取初始快照（控制频率）
                if not state.is_synced or self._need_resync(state):
                    if not state.sync_in_progress:
                        # 检查是否需要延迟重试
                        if hasattr(state, 'last_resync_time'):
                            time_since_resync = (datetime.utcnow() - state.last_resync_time).total_seconds()
                            # 指数退避：10秒、20秒、40秒...最多120秒
                            retry_count = getattr(state, 'retry_count', 0)
                            wait_time = min(10 * (2 ** retry_count), 120)
                            if time_since_resync < wait_time:
                                self.logger.info(
                                    "等待重试",
                                    symbol=symbol,
                                    wait_time=wait_time - time_since_resync,
                                    retry_count=retry_count
                                )
                                await asyncio.sleep(wait_time - time_since_resync)
                        
                        await self._sync_orderbook(symbol)
                
                # 2. 处理缓冲的增量更新
                await self._process_buffered_updates(symbol)
                
                # 3. 定期刷新快照（控制频率）
                if self._need_snapshot_refresh(state) and not state.sync_in_progress:
                    await self._refresh_snapshot(symbol)
                
                # 4. 适当休眠，减少CPU使用
                await asyncio.sleep(1.0)  # 增加到1秒
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                state.error_count += 1
                self.stats['sync_errors'] += 1
                
                self.logger.error(
                    "维护订单簿失败",
                    symbol=symbol,
                    error=str(e),
                    error_count=state.error_count
                )
                
                # 错误过多时重置状态
                if state.error_count >= self.max_error_count:
                    await self._reset_orderbook_state(symbol)
                
                await asyncio.sleep(5)  # 错误后等待重试
    
    async def _sync_orderbook(self, symbol: str):
        """同步订单簿 - 严格按照Binance官方文档实现"""
        state = self.orderbook_states[symbol]
        state.sync_in_progress = True
        
        try:
            self.logger.info(
                "开始订单簿同步",
                symbol=symbol,
                first_update_id=state.first_update_id,
                buffer_size=len(state.update_buffer)
            )
            
            # 步骤1: 如果没有缓存的更新，等待第一个更新
            if not state.first_update_id and len(state.update_buffer) == 0:
                self.logger.info("等待第一个WebSocket更新", symbol=symbol)
                state.sync_in_progress = False
                return
            
            # 步骤2: 获取深度快照
            snapshot = await self._fetch_snapshot(symbol)
            if not snapshot:
                state.sync_in_progress = False
                return
            
            state.snapshot_last_update_id = snapshot.last_update_id
            
            # 步骤3: 验证同步条件
            # 如果快照的lastUpdateId < 第一个事件的U值，重新获取快照
            if state.first_update_id and snapshot.last_update_id < state.first_update_id:
                self.logger.warning(
                    "快照过旧，需要重新获取",
                    symbol=symbol,
                    snapshot_last_update_id=snapshot.last_update_id,
                    first_update_id=state.first_update_id
                )
                state.sync_in_progress = False
                # 等待更长时间再重试，避免频繁请求
                await asyncio.sleep(5.0)
                return await self._sync_orderbook(symbol)
            
            # 步骤4: 设置本地订单簿为快照
            state.local_orderbook = snapshot
            state.last_update_id = snapshot.last_update_id
            state.last_snapshot_time = datetime.utcnow()
            
            # 步骤5: 丢弃过期的更新（u <= lastUpdateId）
            self._clean_expired_updates_binance_style(state, snapshot.last_update_id)
            
            # 步骤6: 应用有效的缓冲更新
            # 从第一个 U <= lastUpdateId 且 u >= lastUpdateId 的事件开始
            applied_count = await self._apply_buffered_updates_binance_style(symbol)
            
            # 步骤7: 标记为已同步
            state.is_synced = True
            state.error_count = 0
            state.sync_in_progress = False
            state.retry_count = 0  # 重置重试计数
            self.stats['snapshots_fetched'] += 1
            
            self.logger.info(
                "订单簿同步成功",
                symbol=symbol,
                snapshot_last_update_id=snapshot.last_update_id,
                applied_updates=applied_count,
                buffer_size=len(state.update_buffer),
                final_update_id=state.last_update_id
            )
            
        except Exception as e:
            state.sync_in_progress = False
            self.logger.error(
                "订单簿同步失败",
                symbol=symbol,
                error=str(e)
            )
            raise
    
    async def _fetch_snapshot(self, symbol: str) -> Optional[OrderBookSnapshot]:
        """获取订单簿快照（带频率限制）"""
        # 检查API权重限制
        now = datetime.utcnow()
        if (now - self.weight_reset_time).total_seconds() >= 60:
            # 重置权重计数
            self.api_weight_used = 0
            self.weight_reset_time = now
            self.consecutive_errors = 0  # 重置连续错误计数
            self.backoff_multiplier = 1.0  # 重置退避倍数
        
        # 根据深度限制计算权重
        # 400档深度权重约为25，比5000档的250要低很多
        weight = 25
        
        # 检查是否会超过权重限制
        if self.api_weight_used + weight > self.api_weight_limit:
            wait_time = 60 - (now - self.weight_reset_time).total_seconds()
            self.logger.warning(
                "API权重限制，等待重置",
                symbol=symbol,
                weight_used=self.api_weight_used,
                weight_limit=self.api_weight_limit,
                wait_time=f"{wait_time:.1f}s"
            )
            await asyncio.sleep(wait_time)
            # 重置权重
            self.api_weight_used = 0
            self.weight_reset_time = datetime.utcnow()
        
        # 检查频率限制（带动态退避）
        current_time = time.time()
        last_request = self.last_snapshot_request.get(symbol, 0)
        time_since_last = current_time - last_request
        
        # 动态调整最小间隔
        min_interval = self.min_snapshot_interval * self.backoff_multiplier
        
        if time_since_last < min_interval:
            wait_time = min_interval - time_since_last
            self.logger.info(
                "API频率限制，等待中",
                symbol=symbol,
                wait_time=f"{wait_time:.1f}s",
                min_interval=min_interval,
                backoff_multiplier=self.backoff_multiplier
            )
            await asyncio.sleep(wait_time)
        
        # 记录请求时间
        self.last_snapshot_request[symbol] = time.time()
        
        if self.config.exchange == Exchange.BINANCE:
            return await self._fetch_binance_snapshot(symbol)
        elif self.config.exchange == Exchange.OKX:
            return await self._fetch_okx_snapshot(symbol)
        else:
            self.logger.warning(
                "不支持的交易所",
                exchange=self.config.exchange.value
            )
            return None
    
    async def _fetch_binance_snapshot(self, symbol: str) -> Optional[OrderBookSnapshot]:
        """获取Binance订单簿快照"""
        try:
            # 构建API URL
            if self.config.market_type.value == "spot":
                url = f"{self.config.base_url}/api/v3/depth"
            else:  # futures
                url = f"{self.config.base_url}/fapi/v1/depth"
            
            params = {
                "symbol": symbol.replace("-", ""),
                "limit": self.depth_limit
            }
            
            # 使用代理（如果配置了）
            kwargs = {'params': params}
            if hasattr(self, 'proxy') and self.proxy:
                kwargs['proxy'] = self.proxy
            
            async with self.session.get(url, **kwargs) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(
                        "获取Binance快照失败",
                        symbol=symbol,
                        status=response.status,
                        text=error_text
                    )
                    
                    # 特殊处理418错误（IP封禁）
                    if response.status == 418:
                        self.consecutive_errors += 1
                        self.backoff_multiplier = min(self.backoff_multiplier * 2, 8.0)  # 最多8倍退避
                        
                        try:
                            error_data = json.loads(error_text)
                            if 'banned until' in error_data.get('msg', ''):
                                # 提取封禁时间
                                import re
                                match = re.search(r'banned until (\d+)', error_data['msg'])
                                if match:
                                    ban_until = int(match.group(1)) / 1000
                                    wait_time = ban_until - time.time()
                                    self.logger.error(
                                        "IP被封禁，需要等待",
                                        symbol=symbol,
                                        wait_seconds=wait_time,
                                        ban_until=datetime.fromtimestamp(ban_until).isoformat(),
                                        consecutive_errors=self.consecutive_errors
                                    )
                                    # 等待解封时间加上额外30秒
                                    await asyncio.sleep(wait_time + 30)
                        except:
                            # 默认等待5分钟
                            await asyncio.sleep(300)
                    elif response.status == 429:
                        # 频率限制错误
                        self.consecutive_errors += 1
                        self.backoff_multiplier = min(self.backoff_multiplier * 1.5, 4.0)
                        self.logger.warning(
                            "API频率限制(429)",
                            symbol=symbol,
                            consecutive_errors=self.consecutive_errors,
                            backoff_multiplier=self.backoff_multiplier
                        )
                        await asyncio.sleep(60)  # 等待1分钟
                    
                    return None
                
                data = await response.json()
                
                # 计算并更新权重使用量
                weight = 25  # 400档深度权重
                self.api_weight_used += weight
                
                # 成功请求，重置错误计数和退避
                if self.consecutive_errors > 0:
                    self.consecutive_errors = 0
                    self.backoff_multiplier = max(1.0, self.backoff_multiplier * 0.8)  # 逐渐恢复
                
                return self._parse_binance_snapshot(symbol, data)
                
        except Exception as e:
            import traceback
            self.logger.error(
                "获取Binance快照异常",
                symbol=symbol,
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc()
            )
            return None
    
    async def _fetch_okx_snapshot(self, symbol: str) -> Optional[OrderBookSnapshot]:
        """获取OKX订单簿快照 - 使用全量深度API"""
        try:
            # 使用OKX全量深度API，支持最大5000档（买卖各5000，共10000条）
            url = f"https://www.okx.com/api/v5/market/books-full"
            params = {
                'instId': symbol,  # OKX使用instId参数
                'sz': '400'  # 400档深度（买卖各400档）
            }
            
            self.logger.debug("获取OKX订单簿快照", symbol=symbol, url=url, params=params)
            
            # 使用代理（如果配置了）
            kwargs = {'params': params}
            if hasattr(self, 'proxy') and self.proxy:
                kwargs['proxy'] = self.proxy
                self.logger.debug("使用代理访问OKX API", proxy=self.proxy)
            
            async with self.session.get(url, **kwargs) as response:
                if response.status != 200:
                    self.logger.error("OKX快照请求失败", status=response.status, symbol=symbol)
                    return None
                
                data = await response.json()
                
                # 检查OKX API响应格式
                if data.get('code') != '0':
                    self.logger.error("OKX API返回错误", code=data.get('code'), msg=data.get('msg'), symbol=symbol)
                    return None
                
                if not data.get('data') or not data['data']:
                    self.logger.error("OKX快照数据为空", symbol=symbol)
                    return None
                
                snapshot_data = data['data'][0]  # OKX返回数组，取第一个元素
                
                return await self._parse_okx_snapshot(snapshot_data, symbol)
                
        except Exception as e:
            self.logger.error("获取OKX快照失败", error=str(e), symbol=symbol)
            return None

    async def _parse_okx_snapshot(self, data: Dict[str, Any], symbol: str) -> Optional[OrderBookSnapshot]:
        """解析OKX订单簿快照"""
        try:
            # OKX快照格式
            bids_data = data.get('bids', [])
            asks_data = data.get('asks', [])
            timestamp_ms = int(data.get('ts', 0))
            
            # OKX没有lastUpdateId，使用时间戳作为标识
            last_update_id = timestamp_ms
            
            # 解析买盘
            bids = []
            for bid in bids_data:
                price = Decimal(bid[0])
                quantity = Decimal(bid[1])
                if quantity > 0:  # 只保留有效的价格层级
                    bids.append(PriceLevel(price=price, quantity=quantity))
            
            # 解析卖盘
            asks = []
            for ask in asks_data:
                price = Decimal(ask[0])
                quantity = Decimal(ask[1])
                if quantity > 0:  # 只保留有效的价格层级
                    asks.append(PriceLevel(price=price, quantity=quantity))
            
            # 按价格排序
            bids.sort(key=lambda x: x.price, reverse=True)  # 买盘从高到低
            asks.sort(key=lambda x: x.price)  # 卖盘从低到高
            
            snapshot = OrderBookSnapshot(
                symbol=symbol,
                exchange=self.config.exchange.value,
                last_update_id=last_update_id,
                bids=bids,
                asks=asks,
                timestamp=datetime.fromtimestamp(timestamp_ms / 1000.0)
            )
            
            self.logger.debug("解析OKX快照成功", 
                            symbol=symbol, 
                            bids_count=len(bids), 
                            asks_count=len(asks),
                            last_update_id=last_update_id)
            
            return snapshot
            
        except Exception as e:
            self.logger.error("解析OKX快照失败", error=str(e), symbol=symbol, data=str(data)[:200])
            return None

    async def _parse_okx_update(self, data: Dict[str, Any], symbol: str) -> Optional[OrderBookDelta]:
        """解析OKX订单簿增量更新"""
        try:
            # OKX增量更新格式
            bids_data = data.get('bids', [])
            asks_data = data.get('asks', [])
            timestamp_ms = int(data.get('ts', 0))
            
            # OKX使用时间戳作为更新ID
            update_id = timestamp_ms
            
            # 解析买盘更新
            bid_updates = []
            for bid in bids_data:
                price = Decimal(bid[0])
                quantity = Decimal(bid[1])
                bid_updates.append(PriceLevel(price=price, quantity=quantity))
            
            # 解析卖盘更新
            ask_updates = []
            for ask in asks_data:
                price = Decimal(ask[0])
                quantity = Decimal(ask[1])
                ask_updates.append(PriceLevel(price=price, quantity=quantity))
            
            delta = OrderBookDelta(
                symbol=symbol,
                first_update_id=update_id,
                final_update_id=update_id,
                bid_updates=bid_updates,
                ask_updates=ask_updates,
                timestamp=datetime.fromtimestamp(timestamp_ms / 1000.0)
            )
            
            self.logger.debug("解析OKX增量更新成功", 
                            symbol=symbol, 
                            update_id=update_id,
                            bid_updates=len(bid_updates),
                            ask_updates=len(ask_updates))
            
            return delta
            
        except Exception as e:
            self.logger.error("解析OKX增量更新失败", error=str(e), symbol=symbol, data=str(data)[:200])
            return None

    async def _validate_okx_sequence(self, delta: OrderBookDelta, symbol: str) -> bool:
        """验证OKX订单簿序列
        
        注意：OKX使用时间戳作为更新ID，序列验证策略与Binance不同
        """
        try:
            current_state = self.orderbooks.get(symbol)
            if not current_state:
                self.logger.warning("OKX序列验证：订单簿状态不存在", symbol=symbol)
                return False
            
            # OKX的时间戳序列验证
            # 新的更新时间戳应该大于等于当前状态的时间戳
            if delta.final_update_id >= current_state.last_update_id:
                self.logger.debug("OKX序列验证成功", 
                                symbol=symbol,
                                current_id=current_state.last_update_id,
                                update_id=delta.final_update_id)
                return True
            else:
                self.logger.warning("OKX序列验证失败：时间戳倒退", 
                                  symbol=symbol,
                                  current_id=current_state.last_update_id,
                                  update_id=delta.final_update_id)
                return False
                
        except Exception as e:
            self.logger.error("OKX序列验证异常", error=str(e), symbol=symbol)
            return False
    
    def _parse_binance_snapshot(self, symbol: str, data: Dict) -> OrderBookSnapshot:
        """解析Binance快照数据"""
        bids = [
            PriceLevel(price=Decimal(price), quantity=Decimal(qty))
            for price, qty in data["bids"]
        ]
        asks = [
            PriceLevel(price=Decimal(price), quantity=Decimal(qty))
            for price, qty in data["asks"]
        ]
        
        return OrderBookSnapshot(
            symbol=symbol,
            exchange=self.config.exchange.value,
            last_update_id=data["lastUpdateId"],
            bids=bids,
            asks=asks,
            timestamp=datetime.utcnow()
        )
    

    
    async def process_update(self, symbol: str, update_data: Dict) -> Optional[EnhancedOrderBook]:
        """处理订单簿增量更新"""
        if symbol not in self.orderbook_states:
            self.logger.warning(
                "收到未管理交易对的更新",
                symbol=symbol
            )
            return None
        
        state = self.orderbook_states[symbol]
        
        try:
            # 解析更新数据
            update = self._parse_update(symbol, update_data)
            if not update:
                return None
            
            # 记录第一个更新的U值（按照Binance官方文档）
            if state.first_update_id is None:
                state.first_update_id = update.first_update_id
                self.logger.info(
                    "记录第一个更新ID",
                    symbol=symbol,
                    first_update_id=state.first_update_id
                )
            
            # 如果未同步或正在同步中，缓冲更新
            if not state.is_synced or state.sync_in_progress:
                state.update_buffer.append(update)
                self.logger.debug(
                    "缓冲更新（未同步）",
                    symbol=symbol,
                    update_id=update.last_update_id,
                    buffer_size=len(state.update_buffer),
                    is_synced=state.is_synced,
                    sync_in_progress=state.sync_in_progress
                )
                return None
            
            # 验证更新序列
            if not self._validate_update_sequence(state, update):
                # 序列错误，需要重新同步
                self.logger.warning(
                    "更新序列验证失败",
                    symbol=symbol,
                    current_update_id=state.last_update_id,
                    update_first_id=update.first_update_id,
                    update_last_id=update.last_update_id,
                    update_prev_id=update.prev_update_id,
                    gap=update.first_update_id - state.last_update_id - 1
                )
                
                # 缓冲更新，然后触发重新同步
                state.update_buffer.append(update)
                await self._trigger_resync(symbol, "更新序列错误")
                return None
            
            # 应用更新到本地订单簿
            enhanced_orderbook = await self._apply_update(symbol, update)
            
            # 更新状态
            state.last_update_id = update.last_update_id
            state.total_updates += 1
            self.stats['updates_processed'] += 1
            
            # 每100次更新记录一次
            if state.total_updates % 100 == 0:
                self.logger.info(
                    "订单簿更新统计",
                    symbol=symbol,
                    total_updates=state.total_updates,
                    last_update_id=state.last_update_id,
                    buffer_size=len(state.update_buffer)
                )
            else:
                self.logger.debug(
                    "应用更新成功",
                    symbol=symbol,
                    first_update_id=update.first_update_id,
                    last_update_id=update.last_update_id,
                    total_updates=state.total_updates
                )
            
            return enhanced_orderbook
            
        except Exception as e:
            self.logger.error(
                "处理订单簿更新失败",
                symbol=symbol,
                error=str(e),
                error_type=type(e).__name__
            )
            import traceback
            self.logger.error("详细错误信息", traceback=traceback.format_exc())
            return None
    
    def _parse_update(self, symbol: str, data: Dict) -> Optional[OrderBookUpdate]:
        """解析增量更新数据"""
        if self.config.exchange == Exchange.BINANCE:
            return self._parse_binance_update(symbol, data)
        elif self.config.exchange == Exchange.OKX:
            return self._parse_okx_update(symbol, data)
        return None
    
    def _parse_binance_update(self, symbol: str, data: Dict) -> Optional[OrderBookUpdate]:
        """解析Binance增量更新"""
        try:
            bids = [
                PriceLevel(price=Decimal(price), quantity=Decimal(qty))
                for price, qty in data.get("b", [])
            ]
            asks = [
                PriceLevel(price=Decimal(price), quantity=Decimal(qty))
                for price, qty in data.get("a", [])
            ]
            
            return OrderBookUpdate(
                symbol=symbol,
                exchange=self.config.exchange.value,
                first_update_id=data["U"],
                last_update_id=data["u"],
                bids=bids,
                asks=asks,
                timestamp=datetime.utcnow(),
                prev_update_id=data.get("pu")
            )
        except Exception as e:
            self.logger.error(
                "解析Binance更新失败",
                symbol=symbol,
                error=str(e)
            )
            return None
    
    def _parse_okx_update(self, symbol: str, data: Dict) -> Optional[OrderBookUpdate]:
        """解析OKX增量更新"""
        try:
            # OKX订单簿更新格式：[price, quantity, liquidated_orders, order_count]
            bids = [
                PriceLevel(price=Decimal(bid[0]), quantity=Decimal(bid[1]))
                for bid in data.get("bids", [])
            ]
            asks = [
                PriceLevel(price=Decimal(ask[0]), quantity=Decimal(ask[1]))
                for ask in data.get("asks", [])
            ]
            
            # OKX使用时间戳作为更新ID
            timestamp_ms = int(data.get("ts", 0))
            
            return OrderBookUpdate(
                symbol=symbol,
                exchange=self.config.exchange.value,
                first_update_id=timestamp_ms,
                last_update_id=timestamp_ms,
                bids=bids,
                asks=asks,
                timestamp=datetime.fromtimestamp(timestamp_ms / 1000.0)
            )
        except Exception as e:
            self.logger.error(
                "解析OKX更新失败",
                symbol=symbol,
                error=str(e),
                data=str(data)[:200]
            )
            return None
    
    def _validate_update_sequence(self, state: OrderBookState, update: OrderBookUpdate) -> bool:
        """验证更新序列的连续性"""
        if self.config.exchange == Exchange.BINANCE:
            # Binance: 根据官方文档，验证更新是否可以应用
            # 如果有 pu 字段，使用它来验证连续性
            if update.prev_update_id is not None:
                is_valid = update.prev_update_id == state.last_update_id
                if not is_valid:
                    self.logger.debug(
                        "序列验证失败（pu不匹配）",
                        symbol=state.symbol,
                        expected_pu=state.last_update_id,
                        actual_pu=update.prev_update_id
                    )
                return is_valid
            
            # 如果没有 pu 字段，检查更新是否可以接续当前状态
            # 更新的 U (first_update_id) 应该等于 last_update_id + 1
            # 或者更新覆盖了当前状态（U <= last_update_id < u）
            if update.first_update_id == state.last_update_id + 1:
                # 完美接续
                self.logger.debug(
                    "序列验证成功（完美接续）",
                    symbol=state.symbol,
                    state_update_id=state.last_update_id,
                    update_U=update.first_update_id
                )
                return True
            elif (update.first_update_id <= state.last_update_id and 
                  update.last_update_id > state.last_update_id):
                # 更新覆盖了当前状态，也是有效的
                self.logger.debug(
                    "序列验证成功（覆盖更新）",
                    symbol=state.symbol,
                    state_update_id=state.last_update_id,
                    update_U=update.first_update_id,
                    update_u=update.last_update_id
                )
                return True
            else:
                # 有间隙或更新太旧
                if update.last_update_id <= state.last_update_id:
                    self.logger.debug(
                        "序列验证失败（更新太旧）",
                        symbol=state.symbol,
                        state_update_id=state.last_update_id,
                        update_u=update.last_update_id
                    )
                else:
                    self.logger.debug(
                        "序列验证失败（有间隙）",
                        symbol=state.symbol,
                        state_update_id=state.last_update_id,
                        update_U=update.first_update_id,
                        gap=update.first_update_id - state.last_update_id - 1
                    )
                return False
        
        elif self.config.exchange == Exchange.OKX:
            # OKX: 使用时间戳序列验证
            # 新的更新时间戳应该大于等于当前状态的时间戳
            if update.last_update_id >= state.last_update_id:
                self.logger.debug(
                    "OKX序列验证成功",
                    symbol=state.symbol,
                    current_id=state.last_update_id,
                    update_id=update.last_update_id
                )
                return True
            else:
                self.logger.warning(
                    "OKX序列验证失败：时间戳倒退",
                    symbol=state.symbol,
                    current_id=state.last_update_id,
                    update_id=update.last_update_id
                )
                return False
        
        return True
    
    async def _apply_update(self, symbol: str, update: OrderBookUpdate) -> EnhancedOrderBook:
        """应用增量更新到本地订单簿"""
        state = self.orderbook_states[symbol]
        local_book = state.local_orderbook
        
        # 复制当前订单簿
        new_bids = {level.price: level.quantity for level in local_book.bids}
        new_asks = {level.price: level.quantity for level in local_book.asks}
        
        # 记录变化
        bid_changes = []
        ask_changes = []
        removed_bids = []
        removed_asks = []
        
        # 应用买单更新
        for level in update.bids:
            if level.quantity == 0:
                # 删除价位
                if level.price in new_bids:
                    del new_bids[level.price]
                    removed_bids.append(level.price)
            else:
                # 更新或添加价位
                old_qty = new_bids.get(level.price, Decimal('0'))
                if old_qty != level.quantity:
                    new_bids[level.price] = level.quantity
                    bid_changes.append(level)
        
        # 应用卖单更新
        for level in update.asks:
            if level.quantity == 0:
                # 删除价位
                if level.price in new_asks:
                    del new_asks[level.price]
                    removed_asks.append(level.price)
            else:
                # 更新或添加价位
                old_qty = new_asks.get(level.price, Decimal('0'))
                if old_qty != level.quantity:
                    new_asks[level.price] = level.quantity
                    ask_changes.append(level)
        
        # 排序并转换为列表
        sorted_bids = [
            PriceLevel(price=price, quantity=qty)
            for price, qty in sorted(new_bids.items(), key=lambda x: x[0], reverse=True)
        ]
        sorted_asks = [
            PriceLevel(price=price, quantity=qty)
            for price, qty in sorted(new_asks.items(), key=lambda x: x[0])
        ]
        
        # 更新本地订单簿
        state.local_orderbook.bids = sorted_bids
        state.local_orderbook.asks = sorted_asks
        state.local_orderbook.last_update_id = update.last_update_id
        state.local_orderbook.timestamp = update.timestamp
        
        # 创建增强订单簿
        enhanced_orderbook = EnhancedOrderBook(
            exchange_name=self.config.exchange.value,
            symbol_name=symbol,
            last_update_id=update.last_update_id,
            bids=sorted_bids,
            asks=sorted_asks,
            timestamp=update.timestamp,
            update_type=OrderBookUpdateType.UPDATE,
            first_update_id=update.first_update_id,
            prev_update_id=update.prev_update_id,
            depth_levels=len(sorted_bids) + len(sorted_asks),
            bid_changes=bid_changes if bid_changes else None,
            ask_changes=ask_changes if ask_changes else None,
            removed_bids=removed_bids if removed_bids else None,
            removed_asks=removed_asks if removed_asks else None
        )
        
        return enhanced_orderbook
    
    def _clean_expired_updates(self, state: OrderBookState, snapshot_update_id: int):
        """清理过期的缓冲更新"""
        # 移除所有 last_update_id <= snapshot_update_id 的更新
        while state.update_buffer:
            update = state.update_buffer[0]
            if update.last_update_id <= snapshot_update_id:
                state.update_buffer.popleft()
            else:
                break
    
    def _clean_expired_updates_binance_style(self, state: OrderBookState, snapshot_last_update_id: int):
        """按照Binance官方文档清理过期更新"""
        original_size = len(state.update_buffer)
        
        # 丢弃所有 u <= lastUpdateId 的事件
        state.update_buffer = deque([
            update for update in state.update_buffer
            if update.last_update_id > snapshot_last_update_id
        ], maxlen=1000)
        
        cleaned_count = original_size - len(state.update_buffer)
        
        self.logger.info(
            "清理过期更新（Binance算法）",
            symbol=state.symbol,
            snapshot_last_update_id=snapshot_last_update_id,
            cleaned_count=cleaned_count,
            remaining_count=len(state.update_buffer)
        )
    
    async def _apply_buffered_updates(self, symbol: str):
        """应用缓冲的增量更新"""
        state = self.orderbook_states[symbol]
        applied_count = 0
        
        while state.update_buffer:
            update = state.update_buffer[0]
            
            # 检查更新是否有效
            if self._validate_update_sequence(state, update):
                await self._apply_update(symbol, update)
                state.last_update_id = update.last_update_id
                state.update_buffer.popleft()
                applied_count += 1
            else:
                # 序列不连续，停止应用
                break
        
        return applied_count
    
    async def _apply_buffered_updates_binance_style(self, symbol: str) -> int:
        """按照Binance官方文档应用缓冲更新"""
        state = self.orderbook_states[symbol]
        applied_count = 0
        snapshot_last_update_id = state.snapshot_last_update_id
        
        if not snapshot_last_update_id:
            return 0
        
        self.logger.debug(
            "开始应用缓冲更新",
            symbol=symbol,
            snapshot_last_update_id=snapshot_last_update_id,
            buffer_size=len(state.update_buffer),
            current_update_id=state.last_update_id
        )
        
        # 找到第一个有效的更新：U <= lastUpdateId 且 u >= lastUpdateId
        valid_updates = []
        start_index = -1
        
        for i, update in enumerate(state.update_buffer):
            if (update.first_update_id <= snapshot_last_update_id and 
                update.last_update_id >= snapshot_last_update_id):
                valid_updates.append(update)
                start_index = i
                self.logger.debug(
                    "找到起始更新",
                    symbol=symbol,
                    index=i,
                    update_U=update.first_update_id,
                    update_u=update.last_update_id,
                    snapshot_id=snapshot_last_update_id
                )
                break
        
        # 如果找到了起始更新，继续收集后续的连续更新
        if valid_updates and start_index >= 0:
            expected_prev_update_id = valid_updates[0].last_update_id
            
            # 从缓冲区中找到所有连续的更新
            for i in range(start_index + 1, len(state.update_buffer)):
                update = state.update_buffer[i]
                    
                # 检查连续性：每个新事件的 U 应该等于上一个事件的 u + 1
                if update.first_update_id == expected_prev_update_id + 1:
                    valid_updates.append(update)
                    expected_prev_update_id = update.last_update_id
                elif update.first_update_id > expected_prev_update_id + 1:
                    # 发现间隙，停止
                    self.logger.warning(
                        "发现更新间隙，停止应用",
                        symbol=symbol,
                        expected=expected_prev_update_id + 1,
                        actual=update.first_update_id,
                        gap=update.first_update_id - expected_prev_update_id - 1
                    )
                    break
                # 如果是覆盖更新（U <= prev_id < u），也可以接受
                elif (update.first_update_id <= expected_prev_update_id and 
                      update.last_update_id > expected_prev_update_id):
                    valid_updates.append(update)
                    expected_prev_update_id = update.last_update_id
        
        # 应用有效的更新
        for update in valid_updates:
            try:
                await self._apply_update(symbol, update)
                state.last_update_id = update.last_update_id
                state.total_updates += 1
                applied_count += 1
                
                # 从缓冲区移除已应用的更新
                if update in state.update_buffer:
                    state.update_buffer.remove(update)
                    
                self.logger.debug(
                    "应用更新成功",
                    symbol=symbol,
                    first_update_id=update.first_update_id,
                    last_update_id=update.last_update_id
                )
                
            except Exception as e:
                self.logger.error(
                    "应用更新失败",
                    symbol=symbol,
                    update_id=update.last_update_id,
                    error=str(e)
                )
                break
        
        if applied_count > 0:
            self.logger.info(
                "缓冲更新应用完成",
                symbol=symbol,
                applied_count=applied_count,
                remaining_buffer=len(state.update_buffer),
                final_update_id=state.last_update_id
            )
        
        return applied_count
    
    async def _process_buffered_updates(self, symbol: str):
        """处理缓冲区中的更新"""
        state = self.orderbook_states[symbol]
        
        if not state.is_synced or not state.update_buffer:
            return
        
        # 应用有效的缓冲更新
        applied_count = await self._apply_buffered_updates(symbol)
        
        if applied_count > 0:
            self.logger.debug(
                "应用缓冲更新",
                symbol=symbol,
                applied_count=applied_count,
                remaining_buffer=len(state.update_buffer)
            )
    
    def _need_resync(self, state: OrderBookState) -> bool:
        """判断是否需要重新同步"""
        return (
            state.error_count >= self.max_error_count or
            not state.local_orderbook or
            len(state.update_buffer) > 500  # 缓冲区过大
        )
    
    def _need_snapshot_refresh(self, state: OrderBookState) -> bool:
        """判断是否需要刷新快照"""
        if not state.local_orderbook:
            return True
        
        time_since_snapshot = datetime.utcnow() - state.last_snapshot_time
        
        # 确保至少间隔配置的时间，且不少于最小API间隔（考虑退避）
        min_refresh_interval = max(
            self.snapshot_interval, 
            self.min_snapshot_interval * self.backoff_multiplier
        )
        return time_since_snapshot.total_seconds() > min_refresh_interval
    
    async def _refresh_snapshot(self, symbol: str):
        """刷新快照"""
        try:
            snapshot = await self._fetch_snapshot(symbol)
            if snapshot:
                state = self.orderbook_states[symbol]
                state.local_orderbook = snapshot
                state.last_snapshot_time = datetime.utcnow()
                state.last_update_id = snapshot.last_update_id
                
                self.logger.debug(
                    "快照刷新成功",
                    symbol=symbol,
                    last_update_id=snapshot.last_update_id
                )
        except Exception as e:
            self.logger.error(
                "快照刷新失败",
                symbol=symbol,
                error=str(e)
            )
    
    async def _trigger_resync(self, symbol: str, reason: str):
        """触发重新同步"""
        state = self.orderbook_states[symbol]
        state.is_synced = False
        # 不清理缓冲区，保留更新以便后续使用
        # state.update_buffer.clear()
        self.stats['resync_count'] += 1
        
        # 记录重试时间和计数，避免频繁重试
        state.last_resync_time = datetime.utcnow()
        if not hasattr(state, 'retry_count'):
            state.retry_count = 0
        state.retry_count += 1
        
        self.logger.warning(
            "触发订单簿重新同步",
            symbol=symbol,
            reason=reason,
            resync_count=self.stats['resync_count']
        )
    
    async def _reset_orderbook_state(self, symbol: str):
        """重置订单簿状态"""
        state = self.orderbook_states[symbol]
        state.is_synced = False
        state.local_orderbook = None
        state.update_buffer.clear()
        state.error_count = 0
        state.last_update_id = 0
        
        self.logger.info(
            "重置订单簿状态",
            symbol=symbol
        )
    
    def get_current_orderbook(self, symbol: str) -> Optional[EnhancedOrderBook]:
        """获取当前订单簿"""
        if symbol not in self.orderbook_states:
            return None
        
        state = self.orderbook_states[symbol]
        if not state.is_synced or not state.local_orderbook:
            return None
        
        snapshot = state.local_orderbook
        return EnhancedOrderBook(
            exchange_name=self.config.exchange.value,
            symbol_name=symbol,
            last_update_id=snapshot.last_update_id,
            bids=snapshot.bids,
            asks=snapshot.asks,
            timestamp=snapshot.timestamp,
            update_type=OrderBookUpdateType.SNAPSHOT,
            depth_levels=len(snapshot.bids) + len(snapshot.asks),
            checksum=snapshot.checksum
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        symbol_stats = {}
        for symbol, state in self.orderbook_states.items():
            symbol_stats[symbol] = {
                'is_synced': state.is_synced,
                'last_update_id': state.last_update_id,
                'buffer_size': len(state.update_buffer),
                'error_count': state.error_count,
                'total_updates': state.total_updates,
                'last_snapshot_time': state.last_snapshot_time.isoformat()
            }
        
        return {
            'global_stats': self.stats,
            'symbol_stats': symbol_stats,
            'config': {
                'exchange': self.config.exchange.value,
                'depth_limit': self.depth_limit,
                'snapshot_interval': self.snapshot_interval
            }
        }
    
    # TDD发现的缺失方法 - 必要的核心方法
    def _can_request_snapshot(self, symbol: str) -> bool:
        """检查是否可以请求快照（頻率限制）"""
        current_time = datetime.utcnow()
        
        # 检查最后请求时间
        if symbol in self.last_snapshot_request:
            time_since_last = (current_time - self.last_snapshot_request[symbol]).total_seconds()
            return time_since_last >= self.min_snapshot_interval * self.backoff_multiplier
        
        return True
    
    def _can_request_within_weight_limit(self, weight: int) -> bool:
        """检查是否在API权重限制内"""
        # 检查并重置权重
        self._check_and_reset_weight()
        
        # 检查是否超出限制
        return (self.api_weight_used + weight) <= self.api_weight_limit
    
    def _check_and_reset_weight(self):
        """检查并重置API权重（每分钟重置）"""
        current_time = datetime.utcnow()
        time_since_reset = (current_time - self.weight_reset_time).total_seconds()
        
        # 每分钟重置一次
        if time_since_reset >= 60:
            self.api_weight_used = 0
            self.weight_reset_time = current_time
    
    def _build_snapshot_url(self, symbol: str) -> str:
        """构建快照请求URL"""
        if self.config.exchange == Exchange.BINANCE:
            return f"https://api.binance.com/api/v3/depth?symbol={symbol}&limit=1000"
        elif self.config.exchange == Exchange.OKX:
            return f"https://www.okx.com/api/v5/market/books?instId={symbol}&sz={self.depth_limit}"
        else:
            return self.config.base_url + f"/depth?symbol={symbol}"
    
    def _validate_update_sequence(self, update: OrderBookUpdate, state: OrderBookState) -> bool:
        """验证更新序列号的连续性"""
        # 如果是第一个更新
        if state.last_update_id == 0:
            return True
        
        # 检查更新ID的连续性
        # Binance: 新更新的U应该等于或小于上一个更新的u+1
        if update.first_update_id <= state.last_update_id + 1:
            return True
        
        # 在限定的间隙内也可以接受
        gap = update.first_update_id - state.last_update_id - 1
        return gap <= 10  # 允许10个以内的间隙
    
    def _apply_update_to_orderbook(self, orderbook: OrderBookSnapshot, bids: List[PriceLevel], asks: List[PriceLevel]):
        """将更新应用到订单簿快照"""
        # 将现有价格档位转换为字典
        bid_dict = {level.price: level.quantity for level in orderbook.bids}
        ask_dict = {level.price: level.quantity for level in orderbook.asks}
        
        # 应用买单更新
        for bid_level in bids:
            if bid_level.quantity == 0:
                # 删除价格档位
                bid_dict.pop(bid_level.price, None)
            else:
                # 更新或添加价格档位
                bid_dict[bid_level.price] = bid_level.quantity
        
        # 应用卖单更新
        for ask_level in asks:
            if ask_level.quantity == 0:
                # 删除价格档位
                ask_dict.pop(ask_level.price, None)
            else:
                # 更新或添加价格档位
                ask_dict[ask_level.price] = ask_level.quantity
        
        # 排序并更新订单簿
        # 买单按价格从高到低排序
        orderbook.bids = [
            PriceLevel(price=price, quantity=qty)
            for price, qty in sorted(bid_dict.items(), key=lambda x: x[0], reverse=True)
        ]
        
        # 卖单按价格从低到高排序
        orderbook.asks = [
            PriceLevel(price=price, quantity=qty)
            for price, qty in sorted(ask_dict.items(), key=lambda x: x[0])
        ]
    
    async def _sync_orderbook_binance(self, symbol: str) -> bool:
        """同步Binance订单簿（官方算法）"""
        try:
            state = self.orderbook_states[symbol]
            
            # 1. 获取快照
            snapshot = await self._fetch_binance_snapshot(symbol)
            if not snapshot:
                return False
            
            # 2. 检查缓冲区中的更新
            valid_updates = []
            for update in list(state.update_buffer):
                # 如果更新的最后ID大于快照的lastUpdateId，则保留
                if update.last_update_id > snapshot.last_update_id:
                    valid_updates.append(update)
            
            # 3. 设置快照
            state.local_orderbook = snapshot
            state.snapshot_last_update_id = snapshot.last_update_id
            state.last_update_id = snapshot.last_update_id
            
            # 4. 应用有效更新
            for update in sorted(valid_updates, key=lambda x: x.first_update_id):
                self._apply_update_to_orderbook(state.local_orderbook, update.bids, update.asks)
                state.last_update_id = update.last_update_id
            
            # 5. 清理缓冲区并标记为已同步
            state.update_buffer.clear()
            state.is_synced = True
            state.error_count = 0
            
            self.logger.info(
                "Binance订单簿同步成功",
                symbol=symbol,
                snapshot_update_id=snapshot.last_update_id,
                applied_updates=len(valid_updates),
                final_update_id=state.last_update_id
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Binance订单簿同步失败",
                symbol=symbol,
                error=str(e)
            )
            return False
    
    async def _fetch_binance_snapshot(self, symbol: str) -> Optional[OrderBookSnapshot]:
        """获取Binance快照"""
        if not self.session:
            return None
        
        try:
            url = self._build_snapshot_url(symbol)
            
            # 设置代理（如果有）
            kwargs = {}
            if hasattr(self, 'proxy') and self.proxy:
                kwargs['proxy'] = self.proxy
            
            async with self.session.get(url, **kwargs) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # 转换为快照对象
                    bids = [
                        PriceLevel(price=Decimal(bid[0]), quantity=Decimal(bid[1]))
                        for bid in data.get('bids', [])
                    ]
                    asks = [
                        PriceLevel(price=Decimal(ask[0]), quantity=Decimal(ask[1]))
                        for ask in data.get('asks', [])
                    ]
                    
                    snapshot = OrderBookSnapshot(
                        symbol=symbol,
                        exchange=self.config.exchange.value,
                        last_update_id=data.get('lastUpdateId', 0),
                        bids=bids,
                        asks=asks,
                        timestamp=datetime.utcnow()
                    )
                    
                    # 更新API统计
                    self.api_weight_used += 25  # Binance 1000档深度需褁25权重
                    self.last_snapshot_request[symbol] = datetime.utcnow()
                    self.stats['snapshots_fetched'] += 1
                    
                    return snapshot
                else:
                    self.logger.error(
                        "Binance快照请求失败",
                        symbol=symbol,
                        status=response.status
                    )
                    return None
                    
        except Exception as e:
            self.logger.error(
                "Binance快照获取异常",
                symbol=symbol,
                error=str(e)
            )
            return None
    
    # TDD发现的缺失方法 - 错误恢复机制
    def _handle_sync_error(self, symbol: str, error: Exception):
        """处理同步错误"""
        state = self.orderbook_states.get(symbol)
        if not state:
            return
        
        state.error_count += 1
        self.consecutive_errors += 1
        self.stats['sync_errors'] += 1
        
        # 计算退避延迟
        self.backoff_multiplier = min(self.backoff_multiplier * 1.5, 8.0)
        
        self.logger.warning(
            "同步错误处理",
            symbol=symbol,
            error=str(error),
            error_count=state.error_count,
            consecutive_errors=self.consecutive_errors,
            backoff_multiplier=self.backoff_multiplier
        )
        
        # 如果错误次数过多，重置状态
        if state.error_count >= self.max_error_count:
            asyncio.create_task(self._reset_orderbook_state(symbol))
    
    def _calculate_backoff_delay(self, error_count: int) -> float:
        """计算退避延迟时间"""
        # 指数退避：2^error_count * base_delay
        base_delay = 1.0
        max_delay = 300.0  # 最大5分钟
        
        delay = min(base_delay * (2 ** min(error_count, 8)), max_delay)
        return delay * self.backoff_multiplier
    
    def _should_retry_sync(self, symbol: str) -> bool:
        """判断是否应该重试同步"""
        state = self.orderbook_states.get(symbol)
        if not state:
            return False
        
        # 检查错误次数
        if state.error_count >= self.max_error_count:
            return False
        
        # 检查最后重试时间
        if hasattr(state, 'last_resync_time'):
            time_since_last = (datetime.utcnow() - state.last_resync_time).total_seconds()
            min_retry_interval = self._calculate_backoff_delay(state.error_count)
            return time_since_last >= min_retry_interval
        
        return True 