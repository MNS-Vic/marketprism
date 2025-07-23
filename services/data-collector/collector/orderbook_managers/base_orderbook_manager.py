"""
订单簿管理器基础抽象类

定义所有交易所订单簿管理器的通用接口和基础功能
保持与原有架构的完全兼容性
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
import asyncio
import time
from datetime import datetime, timezone, timedelta
from structlog import get_logger

from ..data_types import EnhancedOrderBook, OrderBookState


class BaseOrderBookManager(ABC):
    """订单簿管理器基础抽象类"""

    def __init__(self, exchange: str, market_type: str, symbols: List[str],
                 normalizer, nats_publisher, config: dict):
        """
        初始化订单簿管理器

        Args:
            exchange: 交易所名称 (如 'binance_spot', 'okx_derivatives')
            market_type: 市场类型 ('spot'/'perpetual')
            symbols: 交易对列表
            normalizer: 数据标准化器
            nats_publisher: NATS发布器
            config: 配置信息
        """
        self.exchange = exchange
        self.market_type = market_type
        self.symbols = symbols
        self.normalizer = normalizer
        self.nats_publisher = nats_publisher
        self.config = config
        self.logger = get_logger(f"{exchange}_{market_type}_orderbook")

        # 订单簿状态存储 - 保持与原有架构一致
        self.orderbook_states: Dict[str, OrderBookState] = {}

        # 消息处理队列 - 保持串行处理机制
        self.message_queues: Dict[str, asyncio.Queue] = {}
        self.processing_locks: Dict[str, asyncio.Lock] = {}
        self.processing_tasks: Dict[str, asyncio.Task] = {}

        # 运行状态
        self._is_running = False
        self.message_processors_running = False
        self.memory_management_task = None

        # 统计信息
        self.stats = {
            'messages_processed': 0,
            'snapshots_applied': 0,
            'updates_applied': 0,
            'errors': 0,
            'last_update_time': None,
            'resync_count': 0,
            'reconnection_count': 0,
            'reconnection_failures': 0,
            'last_reconnection_time': None,
            'connection_health_checks': 0
        }

        # 统一的重连配置 - 基于官方文档最佳实践
        self.reconnect_config = {
            'enabled': True,
            'max_attempts': -1,  # -1表示无限重连
            'initial_delay': 1.0,  # 初始延迟1秒
            'max_delay': 30.0,  # 最大延迟30秒
            'backoff_multiplier': 2.0,  # 指数退避倍数
            'connection_timeout': 10.0,  # 连接超时10秒
            'health_check_interval': 30.0,  # 健康检查间隔30秒
            'heartbeat_timeout': 60.0  # 心跳超时60秒
        }

        # 重连状态管理
        self.reconnect_attempts = 0
        self.is_reconnecting = False
        self.last_successful_connection = None
        self.connection_start_time = datetime.now(timezone.utc)

        # 内存管理配置
        self.memory_config = {
            'enabled': True,
            'max_orderbook_states': 1000,  # 最大订单簿状态数量
            'cleanup_interval': 300.0,  # 清理间隔5分钟
            'inactive_threshold': 3600.0,  # 非活跃阈值1小时
            'memory_check_interval': 60.0,  # 内存检查间隔1分钟
            'max_memory_mb': 512,  # 最大内存使用512MB
            'memory_warning_threshold': 0.8  # 内存警告阈值80%
        }

        # 内存管理状态
        self.last_memory_cleanup = datetime.now(timezone.utc)
        self.last_memory_check = datetime.now(timezone.utc)
        self.memory_cleanup_count = 0
        self.memory_warnings = 0

        # 错误恢复配置
        self.error_recovery_config = {
            'enabled': True,
            'max_consecutive_errors': 5,  # 最大连续错误次数
            'error_reset_interval': 300.0,  # 错误重置间隔5分钟
            'checksum_failure_threshold': 3,  # checksum失败阈值
            'sequence_error_threshold': 3,  # 序列错误阈值
            'auto_resync_enabled': True,  # 自动重新同步
            'resync_delay': 5.0,  # 重新同步延迟5秒
            'max_resync_attempts': 3  # 最大重新同步尝试次数
        }

        # 错误恢复状态
        self.consecutive_errors = 0
        self.last_error_time = None
        self.checksum_failures = 0
        self.sequence_errors = 0
        self.resync_attempts = 0
        self.last_resync_time = None

        # 性能监控配置（基于API测试优化）
        self.performance_config = {
            'enabled': True,
            'monitoring_interval': 60.0,  # 监控间隔1分钟
            'latency_warning_threshold': 200.0,  # 延迟警告阈值200ms（基于API测试优化）
            'throughput_warning_threshold': 10.0,  # 吞吐量警告阈值10msg/s
            'cpu_warning_threshold': 80.0,  # CPU警告阈值80%
            'detailed_stats_interval': 300.0,  # 详细统计间隔5分钟
            'performance_history_size': 100  # 性能历史记录大小
        }

        # 性能监控状态
        self.last_performance_check = datetime.now(timezone.utc)
        self.last_detailed_stats = datetime.now(timezone.utc)
        self.performance_warnings = 0
        self.message_timestamps = []  # 消息时间戳队列
        self.processing_times = []  # 处理时间队列
        self.performance_history = []  # 性能历史记录

        # 日志记录配置
        self.logging_config = {
            'enabled': True,
            'log_level': 'INFO',  # DEBUG, INFO, WARNING, ERROR
            'structured_logging': True,  # 结构化日志
            'log_performance': True,  # 记录性能日志
            'log_errors': True,  # 记录错误日志
            'log_connections': True,  # 记录连接日志
            'log_data_flow': False,  # 记录数据流日志（调试用）
            'context_fields': ['exchange', 'market_type', 'symbol'],  # 上下文字段
            'sensitive_fields': ['api_key', 'api_secret', 'passphrase']  # 敏感字段
        }

        # 日志记录状态
        self.log_context = {
            'exchange': self.exchange,
            'market_type': self.market_type,
            'manager_id': f"{self.exchange}_{self.market_type}_{id(self)}"
        }

        # 深度配置
        self.snapshot_depth = self._get_snapshot_depth()
        self.websocket_depth = self._get_websocket_depth()
        self.nats_publish_depth = 400  # 统一发布400档

        self.logger.info(f"🏗️ {self.__class__.__name__}初始化完成",
                        exchange=exchange, market_type=market_type, symbols=symbols,
                        snapshot_depth=self.snapshot_depth, websocket_depth=self.websocket_depth)

    @abstractmethod
    def _get_snapshot_depth(self) -> int:
        """获取快照深度配置"""
        pass

    @abstractmethod
    def _get_websocket_depth(self) -> int:
        """获取WebSocket深度配置"""
        pass

    @abstractmethod
    async def initialize_orderbook_states(self):
        """初始化订单簿状态"""
        pass

    @abstractmethod
    async def process_websocket_message(self, symbol: str, message: dict):
        """处理WebSocket消息 - 交易所特定实现"""
        pass

    @abstractmethod
    async def _apply_snapshot(self, symbol: str, snapshot_data: dict, state: OrderBookState):
        """应用快照数据 - 交易所特定实现"""
        pass

    @abstractmethod
    async def _apply_update(self, symbol: str, update_data: dict, state: OrderBookState):
        """应用增量更新 - 交易所特定实现"""
        pass

    @abstractmethod
    def _validate_message_sequence(self, symbol: str, message: dict, state: OrderBookState) -> tuple[bool, str]:
        """验证消息序列 - 交易所特定实现"""
        pass

    @abstractmethod
    async def _fetch_initial_snapshot(self, symbol: str) -> Optional[EnhancedOrderBook]:
        """获取初始快照 - 交易所特定实现"""
        pass

    def _get_unique_key(self, symbol: str) -> str:
        """生成唯一键 - 保持与原有架构一致"""
        return f"{self.exchange}_{self.market_type}_{symbol}"

    async def start(self):
        """启动订单簿管理器"""
        self.logger.info(f"🔍 DEBUG: start()方法被调用 - {self.__class__.__name__}")

        if self._is_running:
            self.logger.warning("管理器已在运行中")
            return

        self.log_info(f"🚀 启动{self.__class__.__name__}",
                     symbols=self.symbols,
                     snapshot_depth=self.snapshot_depth,
                     websocket_depth=self.websocket_depth)

        try:
            # 1. 初始化订单簿状态
            self.logger.info("📋 步骤1：初始化订单簿状态")
            await self.initialize_orderbook_states()
            self.logger.info("✅ 订单簿状态初始化完成")

            # 2. 启动串行消息处理器
            self.logger.info("📋 步骤2：启动串行消息处理器")
            await self._start_message_processors(self.symbols)
            self.logger.info("✅ 串行消息处理器启动完成")

            # 3. 启动内存管理任务
            self.logger.info("📋 步骤3：启动内存管理任务")
            if self.memory_config['enabled']:
                self.memory_management_task = asyncio.create_task(self._memory_management_loop())
                self.logger.info("🧹 内存管理任务已启动")
            else:
                self.logger.info("⏭️ 内存管理任务已禁用，跳过")

            # 4. 交易所特定的初始化
            self.logger.info("📋 步骤4：开始交易所特定初始化")
            await self._exchange_specific_initialization()
            self.logger.info("✅ 交易所特定初始化完成")

            self._is_running = True
            self.log_info(f"✅ {self.__class__.__name__}启动完成",
                         startup_time=f"{(datetime.now(timezone.utc) - self.connection_start_time).total_seconds():.2f}s")

        except Exception as e:
            self.log_error(f"❌ 启动失败", exception=e)
            await self.stop()
            raise

    async def stop(self):
        """停止订单簿管理器"""
        if not self._is_running:
            return

        self.logger.info(f"🛑 停止{self.__class__.__name__}")

        # 停止消息处理器
        await self._stop_message_processors()

        # 停止内存管理任务
        if hasattr(self, 'memory_management_task') and self.memory_management_task:
            self.memory_management_task.cancel()
            try:
                await self.memory_management_task
            except asyncio.CancelledError:
                pass
            self.logger.info("🧹 内存管理任务已停止")

        # 交易所特定的清理
        await self._exchange_specific_cleanup()

        self._is_running = False
        self.log_info(f"✅ {self.__class__.__name__}已停止",
                     uptime_seconds=int((datetime.now(timezone.utc) - self.connection_start_time).total_seconds()),
                     total_messages=self.stats.get('messages_processed', 0),
                     total_errors=self.stats.get('errors', 0))

    async def _start_message_processors(self, symbols: List[str] = None):
        """启动串行消息处理器 - 保持原有机制"""
        if self.message_processors_running:
            return

        self.message_processors_running = True

        # 使用传入的symbols或默认使用self.symbols
        symbols_to_use = symbols if symbols is not None else self.symbols

        for symbol in symbols_to_use:
            # 创建消息队列和锁
            self.message_queues[symbol] = asyncio.Queue()
            self.processing_locks[symbol] = asyncio.Lock()

            # 启动串行处理任务
            task = asyncio.create_task(self._process_messages_serially(symbol))
            self.processing_tasks[symbol] = task

        self.logger.info(f"🔧 已启动{len(self.symbols)}个串行消息处理器")

    async def _stop_message_processors(self):
        """停止消息处理器"""
        self.message_processors_running = False

        # 发送停止信号
        for symbol in self.symbols:
            if symbol in self.message_queues:
                await self.message_queues[symbol].put(None)

        # 等待任务完成
        for symbol, task in self.processing_tasks.items():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self.processing_tasks.clear()
        self.message_queues.clear()
        self.processing_locks.clear()

    async def _process_messages_serially(self, symbol: str):
        """串行处理单个交易对的消息 - 保持原有机制"""
        queue = self.message_queues[symbol]
        lock = self.processing_locks[symbol]

        self.logger.debug(f"🔧 启动{symbol}的串行消息处理器")

        try:
            while True:
                # 从队列中获取消息
                message_data = await queue.get()

                # 检查停止信号
                if message_data is None:
                    break

                # 串行处理消息（使用锁确保原子性）
                async with lock:
                    start_time = time.time()
                    try:
                        await self._process_single_message(symbol, message_data)

                        # 记录处理性能
                        if self.performance_config['enabled']:
                            processing_time = time.time() - start_time
                            message_size = len(str(message_data)) if message_data else 0
                            await self._record_message_processing(symbol, processing_time, message_size)

                    except Exception as e:
                        self.logger.error(f"❌ 处理{symbol}消息失败: {e}")
                        self.stats['errors'] += 1
                    finally:
                        queue.task_done()

        except asyncio.CancelledError:
            self.logger.info(f"🔧 {symbol}串行处理器已取消")
        except Exception as e:
            self.logger.error(f"❌ {symbol}串行处理器异常: {e}")

    async def _process_single_message(self, symbol: str, message_data: dict):
        """处理单条消息 - 调用交易所特定实现"""
        update = message_data['update']
        await self.process_websocket_message(symbol, update)

        # 更新统计
        self.stats['messages_processed'] += 1
        self.stats['last_update_time'] = time.time()

    async def handle_websocket_message(self, symbol: str, message: dict):
        """处理WebSocket消息的入口点 - 保持原有接口"""
        try:
            # 将消息放入对应的处理队列
            if symbol in self.message_queues:
                await self.message_queues[symbol].put({
                    'timestamp': time.time(),
                    'symbol': symbol,
                    'update': message
                })
            else:
                self.logger.warning(f"⚠️ 未知交易对: {symbol}")
        except Exception as e:
            self.logger.error(f"❌ 处理WebSocket消息失败: {symbol}, error={e}")
            self.stats['errors'] += 1

    async def publish_orderbook(self, symbol: str, orderbook: EnhancedOrderBook):
        """
        发布订单簿数据到NATS - 优化：延迟标准化到NATS层

        🔧 架构优化：移除中间标准化，保持原始数据到最后发布时刻
        这样确保所有验证和计算都使用原始交易所格式
        """
        try:
            # 🔧 优化：直接构建原始格式数据，不进行标准化
            # 标准化将在NATS Publisher层统一进行
            raw_orderbook_data = {
                'exchange': self.exchange,
                'market_type': self.market_type,
                'symbol': symbol,  # 保持原始symbol格式
                'last_update_id': orderbook.last_update_id,
                'bids': [[str(level.price), str(level.quantity)] for level in orderbook.bids[:400]],
                'asks': [[str(level.price), str(level.quantity)] for level in orderbook.asks[:400]],
                'timestamp': orderbook.timestamp.isoformat(),
                'update_type': orderbook.update_type.value if hasattr(orderbook.update_type, 'value') else str(orderbook.update_type),
                'depth_levels': min(len(orderbook.bids) + len(orderbook.asks), 800),
                'raw_data': True  # 标记为原始数据
            }

            # 🔧 优化：发布原始数据，标准化在NATS Publisher中进行
            await self.nats_publisher.publish_orderbook(
                self.exchange,
                self.market_type,
                symbol,  # 使用原始symbol
                raw_orderbook_data
            )

        except Exception as e:
            self.logger.error(f"❌ 发布订单簿失败: {symbol}, error={e}")

    @abstractmethod
    async def _exchange_specific_initialization(self):
        """交易所特定的初始化逻辑"""
        pass

    @abstractmethod
    async def _exchange_specific_cleanup(self):
        """交易所特定的清理逻辑"""
        pass

    def _calculate_okx_checksum(self, orderbook: dict) -> str:
        """
        统一的OKX checksum计算方法

        根据OKX官方文档规范：
        1. 取前25档买卖单
        2. 按bid:ask交替排列：bid[价格:数量]:ask[价格:数量]:bid[价格:数量]:ask[价格:数量]...
        3. bid或ask不足25档时，直接忽略缺失的深度
        4. 使用CRC32计算校验和（32位有符号整型）

        Args:
            orderbook: 订单簿数据 {'bids': {price: quantity}, 'asks': {price: quantity}}

        Returns:
            str: CRC32校验和字符串
        """
        try:
            # 获取前25档买卖单并排序
            bids = sorted(orderbook.get('bids', {}).items(), key=lambda x: x[0], reverse=True)[:25]
            asks = sorted(orderbook.get('asks', {}).items(), key=lambda x: x[0])[:25]

            # 构建校验字符串 - 严格按照OKX官方文档的交替排列
            checksum_parts = []
            min_len = min(len(bids), len(asks))

            # 先处理相同长度的部分（交替排列）
            for i in range(min_len):
                bid_price, bid_quantity = bids[i]
                ask_price, ask_quantity = asks[i]

                # 🎯 关键：使用正确的数据格式化（移除尾随零）
                bid_price_str = self._format_price_for_checksum(bid_price)
                bid_quantity_str = self._format_quantity_for_checksum(bid_quantity)
                ask_price_str = self._format_price_for_checksum(ask_price)
                ask_quantity_str = self._format_quantity_for_checksum(ask_quantity)

                checksum_parts.extend([bid_price_str, bid_quantity_str, ask_price_str, ask_quantity_str])

            # 处理剩余的部分（如果bid或ask有剩余）
            if len(bids) > min_len:
                # 剩余的bids
                for i in range(min_len, len(bids)):
                    bid_price, bid_quantity = bids[i]
                    bid_price_str = self._format_price_for_checksum(bid_price)
                    bid_quantity_str = self._format_quantity_for_checksum(bid_quantity)
                    checksum_parts.extend([bid_price_str, bid_quantity_str])
            elif len(asks) > min_len:
                # 剩余的asks
                for i in range(min_len, len(asks)):
                    ask_price, ask_quantity = asks[i]
                    ask_price_str = self._format_price_for_checksum(ask_price)
                    ask_quantity_str = self._format_quantity_for_checksum(ask_quantity)
                    checksum_parts.extend([ask_price_str, ask_quantity_str])

            # 拼接为完整字符串
            checksum_str = ':'.join(checksum_parts)

            # 计算CRC32校验和（32位有符号整型）
            import zlib
            crc32_value = zlib.crc32(checksum_str.encode('utf-8'))
            # 转换为32位有符号整型
            if crc32_value >= 2**31:
                crc32_value -= 2**32

            return str(crc32_value)

        except Exception as e:
            self.logger.error(f"❌ 计算OKX checksum失败: {e}")
            return ""

    def _format_price_for_checksum(self, price) -> str:
        """
        格式化价格用于checksum计算
        🔧 修复：保持原始字符串格式，避免科学计数法
        """
        try:
            # 直接使用原始字符串，避免Decimal的normalize()导致科学计数法
            if isinstance(price, str):
                return price
            else:
                return str(price)

        except Exception:
            return str(price)

    def _format_quantity_for_checksum(self, quantity) -> str:
        """
        格式化数量用于checksum计算
        🔧 修复：保持原始字符串格式，避免科学计数法
        """
        try:
            # 直接使用原始字符串，避免Decimal的normalize()导致科学计数法
            if isinstance(quantity, str):
                return quantity
            else:
                return str(quantity)

        except Exception:
            return str(quantity)

    async def _calculate_reconnect_delay(self) -> float:
        """
        计算重连延迟时间（指数退避算法）

        Returns:
            float: 延迟时间（秒）
        """
        if not self.reconnect_config['enabled']:
            return 0

        delay = min(
            self.reconnect_config['initial_delay'] * (
                self.reconnect_config['backoff_multiplier'] ** self.reconnect_attempts
            ),
            self.reconnect_config['max_delay']
        )

        return delay

    async def _should_attempt_reconnect(self) -> bool:
        """
        判断是否应该尝试重连

        Returns:
            bool: 是否应该重连
        """
        if not self.reconnect_config['enabled']:
            return False

        max_attempts = self.reconnect_config['max_attempts']
        if max_attempts > 0 and self.reconnect_attempts >= max_attempts:
            self.logger.error(f"❌ 已达到最大重连次数限制: {max_attempts}")
            return False

        return True

    async def _on_connection_lost(self, reason: str = "Unknown"):
        """
        连接丢失处理

        Args:
            reason: 连接丢失原因
        """
        self.log_connection(f"🔗 连接丢失: {reason}",
                           reconnection_failures=self.stats['reconnection_failures'] + 1)
        self.stats['reconnection_failures'] += 1

        if await self._should_attempt_reconnect():
            await self._attempt_reconnection(reason)

    async def _attempt_reconnection(self, reason: str):
        """
        尝试重连

        Args:
            reason: 重连原因
        """
        if self.is_reconnecting:
            self.logger.debug("🔄 重连已在进行中，跳过")
            return

        self.is_reconnecting = True
        self.reconnect_attempts += 1

        try:
            delay = await self._calculate_reconnect_delay()

            self.logger.info(f"🔄 准备重连 (第{self.reconnect_attempts}次)",
                           reason=reason, delay=f"{delay:.1f}s")

            if delay > 0:
                await asyncio.sleep(delay)

            # 调用子类实现的重连逻辑
            success = await self._perform_reconnection()

            if success:
                self.log_connection(f"✅ 重连成功 (第{self.reconnect_attempts}次)",
                                  reconnection_count=self.stats['reconnection_count'] + 1,
                                  total_attempts=self.reconnect_attempts)
                self.stats['reconnection_count'] += 1
                self.stats['last_reconnection_time'] = datetime.now(timezone.utc)
                self.reconnect_attempts = 0  # 重置重连计数
                self.last_successful_connection = datetime.now(timezone.utc)

                # 重连成功后恢复订单簿状态
                await self._restore_orderbook_states()
            else:
                self.log_error(f"❌ 重连失败 (第{self.reconnect_attempts}次)",
                             attempt=self.reconnect_attempts)

        except Exception as e:
            self.logger.error(f"❌ 重连过程异常: {e}")
        finally:
            self.is_reconnecting = False

    @abstractmethod
    async def _perform_reconnection(self) -> bool:
        """
        执行重连操作 - 子类实现

        Returns:
            bool: 重连是否成功
        """
        pass

    async def _restore_orderbook_states(self):
        """
        重连后恢复订单簿状态
        """
        try:
            self.logger.info("🔄 重连后恢复订单簿状态")

            # 清理所有订单簿状态，强制重新同步
            for symbol, state in self.orderbook_states.items():
                state.is_synced = False
                state.local_orderbook = None
                self.logger.debug(f"🔄 重置{symbol}订单簿状态")

            # 重新初始化订单簿状态
            await self.initialize_orderbook_states()

            self.logger.info("✅ 订单簿状态恢复完成")

        except Exception as e:
            self.logger.error(f"❌ 恢复订单簿状态失败: {e}")

    async def _check_connection_health(self) -> bool:
        """
        检查连接健康状态 - 子类可重写

        Returns:
            bool: 连接是否健康
        """
        self.stats['connection_health_checks'] += 1

        # 基础健康检查：检查最后更新时间
        if self.stats['last_update_time']:
            time_since_last_update = datetime.now(timezone.utc) - self.stats['last_update_time']
            if time_since_last_update.total_seconds() > self.reconnect_config['heartbeat_timeout']:
                self.logger.warning(f"⚠️ 连接可能不健康: {time_since_last_update.total_seconds():.1f}s无数据更新")
                return False

        return True

    async def _get_memory_usage(self) -> dict:
        """
        获取内存使用情况

        Returns:
            dict: 内存使用统计
        """
        try:
            import psutil
            import sys

            # 获取进程内存信息
            process = psutil.Process()
            memory_info = process.memory_info()

            # 计算内存使用
            memory_mb = memory_info.rss / 1024 / 1024
            memory_percent = process.memory_percent()

            # 统计订单簿状态数量
            orderbook_count = len(self.orderbook_states)

            # 估算订单簿内存使用
            orderbook_memory_estimate = 0
            for state in self.orderbook_states.values():
                if state.local_orderbook:
                    # 粗略估算：每个价位约100字节
                    if hasattr(state.local_orderbook, 'bids') and hasattr(state.local_orderbook, 'asks'):
                        orderbook_memory_estimate += (len(state.local_orderbook.bids) + len(state.local_orderbook.asks)) * 100

            orderbook_memory_mb = orderbook_memory_estimate / 1024 / 1024

            return {
                'total_memory_mb': memory_mb,
                'memory_percent': memory_percent,
                'orderbook_count': orderbook_count,
                'orderbook_memory_mb': orderbook_memory_mb,
                'max_memory_mb': self.memory_config['max_memory_mb'],
                'memory_usage_ratio': memory_mb / self.memory_config['max_memory_mb']
            }

        except ImportError:
            self.logger.warning("⚠️ psutil未安装，无法获取内存使用情况")
            return {
                'total_memory_mb': 0,
                'memory_percent': 0,
                'orderbook_count': len(self.orderbook_states),
                'orderbook_memory_mb': 0,
                'max_memory_mb': self.memory_config['max_memory_mb'],
                'memory_usage_ratio': 0
            }
        except Exception as e:
            self.logger.error(f"❌ 获取内存使用情况失败: {e}")
            return {}

    async def _check_memory_usage(self):
        """
        检查内存使用情况并发出警告
        """
        try:
            current_time = datetime.now(timezone.utc)

            # 检查是否需要进行内存检查
            if (current_time - self.last_memory_check).total_seconds() < self.memory_config['memory_check_interval']:
                return

            self.last_memory_check = current_time

            # 获取内存使用情况
            memory_stats = await self._get_memory_usage()
            if not memory_stats:
                return

            # 检查内存使用是否超过警告阈值
            usage_ratio = memory_stats.get('memory_usage_ratio', 0)
            warning_threshold = self.memory_config['memory_warning_threshold']

            if usage_ratio > warning_threshold:
                self.memory_warnings += 1
                self.logger.warning(f"⚠️ 内存使用过高",
                                  memory_mb=f"{memory_stats['total_memory_mb']:.1f}MB",
                                  usage_ratio=f"{usage_ratio:.1%}",
                                  orderbook_count=memory_stats['orderbook_count'],
                                  warning_count=self.memory_warnings)

                # 如果内存使用过高，触发清理
                if usage_ratio > 0.9:  # 90%以上强制清理
                    self.logger.warning("🧹 内存使用过高，强制执行清理")
                    await self._cleanup_memory()

            # 定期记录内存使用情况
            if self.memory_warnings == 0 and memory_stats['orderbook_count'] > 0:
                self.logger.debug(f"📊 内存使用情况",
                                memory_mb=f"{memory_stats['total_memory_mb']:.1f}MB",
                                orderbook_count=memory_stats['orderbook_count'],
                                orderbook_memory_mb=f"{memory_stats['orderbook_memory_mb']:.1f}MB")

        except Exception as e:
            self.logger.error(f"❌ 检查内存使用失败: {e}")

    async def _cleanup_memory(self):
        """
        执行内存清理
        """
        try:
            if not self.memory_config['enabled']:
                return

            current_time = datetime.now(timezone.utc)

            # 检查是否需要清理
            if (current_time - self.last_memory_cleanup).total_seconds() < self.memory_config['cleanup_interval']:
                return

            self.logger.info("🧹 开始内存清理")

            # 清理非活跃的订单簿状态
            inactive_threshold = self.memory_config['inactive_threshold']
            max_states = self.memory_config['max_orderbook_states']

            # 找出非活跃的状态
            inactive_keys = []
            for key, state in self.orderbook_states.items():
                if state.last_update_time:
                    time_since_update = (current_time - state.last_update_time).total_seconds()
                    if time_since_update > inactive_threshold:
                        inactive_keys.append(key)

            # 清理非活跃状态
            cleaned_count = 0
            for key in inactive_keys:
                if len(self.orderbook_states) <= max_states // 2:  # 保留至少一半的状态
                    break
                del self.orderbook_states[key]
                cleaned_count += 1

            # 如果状态数量仍然过多，清理最旧的状态
            if len(self.orderbook_states) > max_states:
                # 按最后更新时间排序，清理最旧的
                sorted_states = sorted(
                    self.orderbook_states.items(),
                    key=lambda x: x[1].last_update_time or datetime.min.replace(tzinfo=timezone.utc)
                )

                excess_count = len(self.orderbook_states) - max_states
                for i in range(excess_count):
                    key = sorted_states[i][0]
                    del self.orderbook_states[key]
                    cleaned_count += 1

            self.last_memory_cleanup = current_time
            self.memory_cleanup_count += 1

            if cleaned_count > 0:
                self.logger.info(f"🧹 内存清理完成",
                               cleaned_states=cleaned_count,
                               remaining_states=len(self.orderbook_states),
                               cleanup_count=self.memory_cleanup_count)
            else:
                self.logger.debug("🧹 内存清理完成，无需清理状态")

            # 强制垃圾回收
            import gc
            gc.collect()

        except Exception as e:
            self.logger.error(f"❌ 内存清理失败: {e}")

    async def _periodic_memory_management(self):
        """
        定期内存管理任务
        """
        try:
            # 检查内存使用
            await self._check_memory_usage()

            # 执行清理
            await self._cleanup_memory()

            # 执行错误恢复检查
            await self._periodic_error_recovery_check()

            # 执行性能监控
            if self.performance_config['enabled']:
                await self._periodic_performance_monitoring()

        except Exception as e:
            self.logger.error(f"❌ 定期内存管理失败: {e}")

    async def _memory_management_loop(self):
        """
        内存管理循环任务
        """
        self.logger.info("🧹 内存管理循环已启动")

        try:
            while self._is_running:
                try:
                    # 执行定期内存管理
                    await self._periodic_memory_management()

                    # 等待下次检查
                    await asyncio.sleep(self.memory_config['memory_check_interval'])

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self.logger.error(f"❌ 内存管理循环异常: {e}")
                    await asyncio.sleep(30)  # 出错时等待30秒再重试

        except asyncio.CancelledError:
            self.logger.info("🧹 内存管理循环被取消")
        except Exception as e:
            self.logger.error(f"❌ 内存管理循环失败: {e}")
        finally:
            self.logger.info("🧹 内存管理循环已停止")

    async def _handle_error(self, symbol: str, error_type: str, error_msg: str, exception: Exception = None):
        """
        统一的错误处理机制

        Args:
            symbol: 交易对
            error_type: 错误类型 ('checksum', 'sequence', 'processing', 'connection')
            error_msg: 错误消息
            exception: 异常对象
        """
        try:
            current_time = datetime.now(timezone.utc)

            # 记录错误
            self.consecutive_errors += 1
            self.last_error_time = current_time
            self.stats['errors'] += 1

            # 根据错误类型更新计数
            if error_type == 'checksum':
                self.checksum_failures += 1
            elif error_type == 'sequence':
                self.sequence_errors += 1

            self.logger.error(f"❌ {error_type}错误: {symbol}",
                            error_msg=error_msg,
                            consecutive_errors=self.consecutive_errors,
                            checksum_failures=self.checksum_failures,
                            sequence_errors=self.sequence_errors,
                            exception=str(exception) if exception else None)

            # 检查是否需要错误恢复
            await self._check_error_recovery(symbol, error_type)

        except Exception as e:
            self.logger.error(f"❌ 错误处理失败: {e}")

    async def _check_error_recovery(self, symbol: str, error_type: str):
        """
        检查是否需要执行错误恢复

        Args:
            symbol: 交易对
            error_type: 错误类型
        """
        try:
            if not self.error_recovery_config['enabled']:
                return

            # 检查连续错误次数
            if self.consecutive_errors >= self.error_recovery_config['max_consecutive_errors']:
                self.logger.warning(f"⚠️ 连续错误次数过多({self.consecutive_errors})，触发错误恢复")
                await self._trigger_error_recovery(symbol, f"连续{self.consecutive_errors}次错误")
                return

            # 检查特定错误类型的阈值
            if error_type == 'checksum' and self.checksum_failures >= self.error_recovery_config['checksum_failure_threshold']:
                self.logger.warning(f"⚠️ checksum失败次数过多({self.checksum_failures})，触发重新同步")
                await self._trigger_resync(symbol, f"checksum失败{self.checksum_failures}次")

            elif error_type == 'sequence' and self.sequence_errors >= self.error_recovery_config['sequence_error_threshold']:
                self.logger.warning(f"⚠️ 序列错误次数过多({self.sequence_errors})，触发重新同步")
                await self._trigger_resync(symbol, f"序列错误{self.sequence_errors}次")

        except Exception as e:
            self.logger.error(f"❌ 检查错误恢复失败: {e}")

    async def _trigger_error_recovery(self, symbol: str, reason: str):
        """
        触发错误恢复

        Args:
            symbol: 交易对
            reason: 恢复原因
        """
        try:
            self.logger.info(f"🔄 开始错误恢复: {symbol}, 原因: {reason}")

            # 重置错误计数
            self._reset_error_counters()

            # 触发重新同步
            await self._trigger_resync(symbol, reason)

            # 如果重新同步失败次数过多，触发重连
            if self.resync_attempts >= self.error_recovery_config['max_resync_attempts']:
                self.logger.warning(f"⚠️ 重新同步失败次数过多({self.resync_attempts})，触发重连")
                await self._on_connection_lost(f"重新同步失败{self.resync_attempts}次")

        except Exception as e:
            self.logger.error(f"❌ 错误恢复失败: {e}")

    async def _trigger_resync(self, symbol: str, reason: str):
        """
        触发重新同步

        Args:
            symbol: 交易对
            reason: 重新同步原因
        """
        try:
            if not self.error_recovery_config['auto_resync_enabled']:
                self.logger.info(f"⚠️ 自动重新同步已禁用: {symbol}")
                return

            current_time = datetime.now(timezone.utc)

            # 检查重新同步间隔
            if (self.last_resync_time and
                (current_time - self.last_resync_time).total_seconds() < self.error_recovery_config['resync_delay']):
                self.logger.debug(f"⏰ 重新同步间隔未到，跳过: {symbol}")
                return

            self.resync_attempts += 1
            self.last_resync_time = current_time
            self.stats['resync_count'] += 1

            self.logger.info(f"🔄 触发重新同步: {symbol}",
                           reason=reason,
                           attempt=self.resync_attempts,
                           total_resyncs=self.stats['resync_count'])

            # 重置订单簿状态
            unique_key = self._get_unique_key(symbol)
            state = self.orderbook_states.get(unique_key)
            if state:
                state.is_synced = False
                state.local_orderbook = None

                # 重置特定于交易所的状态
                if hasattr(state, 'last_update_id'):
                    state.last_update_id = 0
                if hasattr(state, 'last_seq_id'):
                    state.last_seq_id = None

                self.logger.debug(f"🔄 重置订单簿状态: {symbol}")

            # 等待重新同步延迟
            if self.error_recovery_config['resync_delay'] > 0:
                await asyncio.sleep(self.error_recovery_config['resync_delay'])

            # 调用交易所特定的重新同步逻辑
            await self._exchange_specific_resync(symbol, reason)

        except Exception as e:
            self.logger.error(f"❌ 触发重新同步失败: {symbol}, error={e}")

    async def _exchange_specific_resync(self, symbol: str, reason: str):
        """
        交易所特定的重新同步逻辑 - 子类可重写

        Args:
            symbol: 交易对
            reason: 重新同步原因
        """
        # 默认实现：等待WebSocket重新推送数据
        self.logger.info(f"📡 等待WebSocket重新推送数据: {symbol}")

    def _reset_error_counters(self):
        """重置错误计数器"""
        self.consecutive_errors = 0
        self.checksum_failures = 0
        self.sequence_errors = 0
        self.resync_attempts = 0
        self.logger.debug("🔄 错误计数器已重置")

    async def _periodic_error_recovery_check(self):
        """
        定期错误恢复检查
        """
        try:
            current_time = datetime.now(timezone.utc)

            # 检查是否需要重置错误计数器
            if (self.last_error_time and
                (current_time - self.last_error_time).total_seconds() > self.error_recovery_config['error_reset_interval']):

                if self.consecutive_errors > 0 or self.checksum_failures > 0 or self.sequence_errors > 0:
                    self.logger.info(f"🔄 错误重置间隔已到，重置错误计数器")
                    self._reset_error_counters()

        except Exception as e:
            self.logger.error(f"❌ 定期错误恢复检查失败: {e}")

    async def _on_successful_operation(self, symbol: str, operation_type: str):
        """
        成功操作回调 - 用于重置错误状态

        Args:
            symbol: 交易对
            operation_type: 操作类型 ('snapshot', 'update', 'checksum', 'sequence')
        """
        try:
            # 成功操作时，可以考虑部分重置错误计数
            if operation_type in ['snapshot', 'update']:
                # 成功处理数据，重置连续错误计数
                if self.consecutive_errors > 0:
                    self.consecutive_errors = max(0, self.consecutive_errors - 1)

            elif operation_type == 'checksum':
                # checksum验证成功，重置checksum失败计数
                if self.checksum_failures > 0:
                    self.checksum_failures = max(0, self.checksum_failures - 1)

            elif operation_type == 'sequence':
                # 序列验证成功，重置序列错误计数
                if self.sequence_errors > 0:
                    self.sequence_errors = max(0, self.sequence_errors - 1)

        except Exception as e:
            self.logger.error(f"❌ 成功操作回调失败: {e}")

    async def _record_message_processing(self, symbol: str, processing_time: float, message_size: int = 0):
        """
        记录消息处理性能

        Args:
            symbol: 交易对
            processing_time: 处理时间（秒）
            message_size: 消息大小（字节）
        """
        try:
            current_time = datetime.now(timezone.utc)

            # 记录处理时间
            self.processing_times.append({
                'timestamp': current_time,
                'symbol': symbol,
                'processing_time': processing_time,
                'message_size': message_size
            })

            # 保持队列大小
            max_size = self.performance_config['performance_history_size']
            if len(self.processing_times) > max_size:
                self.processing_times = self.processing_times[-max_size:]

            # 记录消息时间戳（用于计算吞吐量）
            self.message_timestamps.append(current_time)
            if len(self.message_timestamps) > max_size:
                self.message_timestamps = self.message_timestamps[-max_size:]

            # 检查延迟警告
            latency_ms = processing_time * 1000
            if latency_ms > self.performance_config['latency_warning_threshold']:
                self.performance_warnings += 1
                self.logger.warning(f"⚠️ 消息处理延迟过高: {symbol}",
                                  latency_ms=f"{latency_ms:.1f}ms",
                                  threshold=f"{self.performance_config['latency_warning_threshold']:.1f}ms",
                                  warning_count=self.performance_warnings)

        except Exception as e:
            self.logger.error(f"❌ 记录消息处理性能失败: {e}")

    async def _get_performance_stats(self) -> dict:
        """
        获取性能统计信息

        Returns:
            dict: 性能统计数据
        """
        try:
            current_time = datetime.now(timezone.utc)

            # 计算吞吐量（最近1分钟）
            one_minute_ago = current_time - timedelta(minutes=1)
            recent_messages = [ts for ts in self.message_timestamps if ts > one_minute_ago]
            throughput = len(recent_messages) / 60.0  # 消息/秒

            # 计算平均延迟（最近1分钟）
            recent_processing_times = [
                pt['processing_time'] for pt in self.processing_times
                if pt['timestamp'] > one_minute_ago
            ]

            avg_latency_ms = 0
            max_latency_ms = 0
            min_latency_ms = 0

            if recent_processing_times:
                avg_latency_ms = sum(recent_processing_times) / len(recent_processing_times) * 1000
                max_latency_ms = max(recent_processing_times) * 1000
                min_latency_ms = min(recent_processing_times) * 1000

            # 获取CPU使用率
            cpu_percent = 0
            try:
                import psutil
                cpu_percent = psutil.cpu_percent(interval=0.1)
            except ImportError:
                pass

            # 计算订单簿更新频率
            update_frequency = self.stats.get('updates_applied', 0) / max(
                (current_time - self.connection_start_time).total_seconds(), 1
            )

            return {
                'throughput_msg_per_sec': throughput,
                'avg_latency_ms': avg_latency_ms,
                'max_latency_ms': max_latency_ms,
                'min_latency_ms': min_latency_ms,
                'cpu_percent': cpu_percent,
                'update_frequency': update_frequency,
                'total_messages': len(self.message_timestamps),
                'performance_warnings': self.performance_warnings,
                'orderbook_count': len(self.orderbook_states),
                'synced_orderbooks': sum(1 for state in self.orderbook_states.values() if state.is_synced)
            }

        except Exception as e:
            self.logger.error(f"❌ 获取性能统计失败: {e}")
            return {}

    async def _check_performance_metrics(self):
        """
        检查性能指标并发出警告
        """
        try:
            current_time = datetime.now(timezone.utc)

            # 检查是否需要进行性能检查
            if (current_time - self.last_performance_check).total_seconds() < self.performance_config['monitoring_interval']:
                return

            self.last_performance_check = current_time

            # 获取性能统计
            stats = await self._get_performance_stats()
            if not stats:
                return

            # 检查吞吐量警告
            throughput = stats.get('throughput_msg_per_sec', 0)
            if throughput < self.performance_config['throughput_warning_threshold']:
                self.performance_warnings += 1
                self.logger.warning(f"⚠️ 消息吞吐量过低",
                                  throughput=f"{throughput:.1f}msg/s",
                                  threshold=f"{self.performance_config['throughput_warning_threshold']:.1f}msg/s",
                                  warning_count=self.performance_warnings)

            # 检查CPU使用率警告
            cpu_percent = stats.get('cpu_percent', 0)
            if cpu_percent > self.performance_config['cpu_warning_threshold']:
                self.performance_warnings += 1
                self.logger.warning(f"⚠️ CPU使用率过高",
                                  cpu_percent=f"{cpu_percent:.1f}%",
                                  threshold=f"{self.performance_config['cpu_warning_threshold']:.1f}%",
                                  warning_count=self.performance_warnings)

            # 记录性能历史
            self.performance_history.append({
                'timestamp': current_time,
                'stats': stats
            })

            # 保持历史记录大小
            max_size = self.performance_config['performance_history_size']
            if len(self.performance_history) > max_size:
                self.performance_history = self.performance_history[-max_size:]

            # 定期输出详细统计
            if (current_time - self.last_detailed_stats).total_seconds() >= self.performance_config['detailed_stats_interval']:
                self.last_detailed_stats = current_time
                await self._log_detailed_performance_stats(stats)
                await self._log_system_status()

        except Exception as e:
            self.logger.error(f"❌ 检查性能指标失败: {e}")

    async def _log_detailed_performance_stats(self, stats: dict):
        """
        记录详细的性能统计信息

        Args:
            stats: 性能统计数据
        """
        try:
            self.logger.info("📊 详细性能统计",
                           throughput=f"{stats.get('throughput_msg_per_sec', 0):.1f}msg/s",
                           avg_latency=f"{stats.get('avg_latency_ms', 0):.1f}ms",
                           max_latency=f"{stats.get('max_latency_ms', 0):.1f}ms",
                           cpu_usage=f"{stats.get('cpu_percent', 0):.1f}%",
                           update_frequency=f"{stats.get('update_frequency', 0):.2f}updates/s",
                           orderbook_count=stats.get('orderbook_count', 0),
                           synced_count=stats.get('synced_orderbooks', 0),
                           total_messages=stats.get('total_messages', 0),
                           performance_warnings=stats.get('performance_warnings', 0),
                           memory_warnings=self.memory_warnings,
                           reconnection_count=self.stats.get('reconnection_count', 0),
                           resync_count=self.stats.get('resync_count', 0))

        except Exception as e:
            self.logger.error(f"❌ 记录详细性能统计失败: {e}")

    async def _periodic_performance_monitoring(self):
        """
        定期性能监控任务
        """
        try:
            # 检查性能指标
            await self._check_performance_metrics()

        except Exception as e:
            self.logger.error(f"❌ 定期性能监控失败: {e}")

    def _create_log_context(self, symbol: str = None, **kwargs) -> dict:
        """
        创建日志上下文

        Args:
            symbol: 交易对
            **kwargs: 额外的上下文字段

        Returns:
            dict: 日志上下文
        """
        context = self.log_context.copy()

        if symbol:
            context['symbol'] = symbol
            context['unique_key'] = self._get_unique_key(symbol)

        # 添加额外字段
        for key, value in kwargs.items():
            if key not in self.logging_config['sensitive_fields']:
                context[key] = value

        return context

    def _sanitize_log_data(self, data: Any) -> Any:
        """
        清理日志数据，移除敏感信息

        Args:
            data: 原始数据

        Returns:
            Any: 清理后的数据
        """
        if isinstance(data, dict):
            sanitized = {}
            for key, value in data.items():
                if key.lower() in self.logging_config['sensitive_fields']:
                    sanitized[key] = "***REDACTED***"
                elif isinstance(value, (dict, list)):
                    sanitized[key] = self._sanitize_log_data(value)
                else:
                    sanitized[key] = value
            return sanitized
        elif isinstance(data, list):
            return [self._sanitize_log_data(item) for item in data]
        else:
            return data

    def log_info(self, message: str, symbol: str = None, **kwargs):
        """
        记录信息日志

        Args:
            message: 日志消息
            symbol: 交易对
            **kwargs: 额外的日志字段
        """
        if not self.logging_config['enabled']:
            return

        try:
            context = self._create_log_context(symbol, **kwargs)
            sanitized_context = self._sanitize_log_data(context)

            if self.logging_config['structured_logging']:
                self.logger.info(message, **sanitized_context)
            else:
                self.logger.info(f"{message} | {sanitized_context}")

        except Exception as e:
            # 避免日志记录本身出错影响主流程
            print(f"日志记录失败: {e}")

    def log_warning(self, message: str, symbol: str = None, **kwargs):
        """
        记录警告日志

        Args:
            message: 日志消息
            symbol: 交易对
            **kwargs: 额外的日志字段
        """
        if not self.logging_config['enabled']:
            return

        try:
            context = self._create_log_context(symbol, **kwargs)
            sanitized_context = self._sanitize_log_data(context)

            if self.logging_config['structured_logging']:
                self.logger.warning(message, **sanitized_context)
            else:
                self.logger.warning(f"{message} | {sanitized_context}")

        except Exception as e:
            print(f"日志记录失败: {e}")

    def log_error(self, message: str, symbol: str = None, exception: Exception = None, **kwargs):
        """
        记录错误日志

        Args:
            message: 日志消息
            symbol: 交易对
            exception: 异常对象
            **kwargs: 额外的日志字段
        """
        if not self.logging_config['enabled'] or not self.logging_config['log_errors']:
            return

        try:
            context = self._create_log_context(symbol, **kwargs)

            if exception:
                context['exception_type'] = type(exception).__name__
                context['exception_message'] = str(exception)
                context['traceback'] = True

            sanitized_context = self._sanitize_log_data(context)

            if self.logging_config['structured_logging']:
                if exception:
                    self.logger.error(message, exc_info=True, **sanitized_context)
                else:
                    self.logger.error(message, **sanitized_context)
            else:
                self.logger.error(f"{message} | {sanitized_context}")

        except Exception as e:
            print(f"日志记录失败: {e}")

    def log_debug(self, message: str, symbol: str = None, **kwargs):
        """
        记录调试日志

        Args:
            message: 日志消息
            symbol: 交易对
            **kwargs: 额外的日志字段
        """
        if (not self.logging_config['enabled'] or
            self.logging_config['log_level'] not in ['DEBUG']):
            return

        try:
            context = self._create_log_context(symbol, **kwargs)
            sanitized_context = self._sanitize_log_data(context)

            if self.logging_config['structured_logging']:
                self.logger.debug(message, **sanitized_context)
            else:
                self.logger.debug(f"{message} | {sanitized_context}")

        except Exception as e:
            print(f"日志记录失败: {e}")

    def log_performance(self, message: str, symbol: str = None, **kwargs):
        """
        记录性能日志

        Args:
            message: 日志消息
            symbol: 交易对
            **kwargs: 额外的日志字段
        """
        if (not self.logging_config['enabled'] or
            not self.logging_config['log_performance']):
            return

        try:
            context = self._create_log_context(symbol, **kwargs)
            context['log_type'] = 'performance'
            sanitized_context = self._sanitize_log_data(context)

            if self.logging_config['structured_logging']:
                self.logger.info(message, **sanitized_context)
            else:
                self.logger.info(f"[PERF] {message} | {sanitized_context}")

        except Exception as e:
            print(f"日志记录失败: {e}")

    def log_connection(self, message: str, **kwargs):
        """
        记录连接日志

        Args:
            message: 日志消息
            **kwargs: 额外的日志字段
        """
        if (not self.logging_config['enabled'] or
            not self.logging_config['log_connections']):
            return

        try:
            context = self._create_log_context(**kwargs)
            context['log_type'] = 'connection'
            sanitized_context = self._sanitize_log_data(context)

            if self.logging_config['structured_logging']:
                self.logger.info(message, **sanitized_context)
            else:
                self.logger.info(f"[CONN] {message} | {sanitized_context}")

        except Exception as e:
            print(f"日志记录失败: {e}")

    def log_data_flow(self, message: str, symbol: str = None, data_size: int = 0, **kwargs):
        """
        记录数据流日志（调试用）

        Args:
            message: 日志消息
            symbol: 交易对
            data_size: 数据大小
            **kwargs: 额外的日志字段
        """
        if (not self.logging_config['enabled'] or
            not self.logging_config['log_data_flow']):
            return

        try:
            context = self._create_log_context(symbol, **kwargs)
            context['log_type'] = 'data_flow'
            context['data_size'] = data_size
            sanitized_context = self._sanitize_log_data(context)

            if self.logging_config['structured_logging']:
                self.logger.debug(message, **sanitized_context)
            else:
                self.logger.debug(f"[DATA] {message} | {sanitized_context}")

        except Exception as e:
            print(f"日志记录失败: {e}")

    async def _log_system_status(self):
        """
        记录系统状态日志
        """
        try:
            if not self.logging_config['enabled']:
                return

            # 获取系统状态
            memory_stats = await self._get_memory_usage()
            performance_stats = await self._get_performance_stats()

            # 统计订单簿状态
            total_orderbooks = len(self.orderbook_states)
            synced_orderbooks = sum(1 for state in self.orderbook_states.values() if state.is_synced)

            # 记录系统状态
            self.log_info("📊 系统状态报告",
                        total_orderbooks=total_orderbooks,
                        synced_orderbooks=synced_orderbooks,
                        sync_ratio=f"{synced_orderbooks/max(total_orderbooks,1)*100:.1f}%",
                        memory_mb=f"{memory_stats.get('total_memory_mb', 0):.1f}MB",
                        cpu_percent=f"{performance_stats.get('cpu_percent', 0):.1f}%",
                        throughput=f"{performance_stats.get('throughput_msg_per_sec', 0):.1f}msg/s",
                        avg_latency=f"{performance_stats.get('avg_latency_ms', 0):.1f}ms",
                        total_messages=self.stats.get('messages_processed', 0),
                        total_errors=self.stats.get('errors', 0),
                        reconnection_count=self.stats.get('reconnection_count', 0),
                        resync_count=self.stats.get('resync_count', 0),
                        uptime_seconds=int((datetime.now(timezone.utc) - self.connection_start_time).total_seconds()))

        except Exception as e:
            self.log_error("❌ 记录系统状态失败", exception=e)

    def get_stats(self) -> dict:
        """获取统计信息"""
        return self.stats.copy()

    def get_orderbook_state(self, symbol: str) -> Optional[OrderBookState]:
        """获取订单簿状态"""
        unique_key = self._get_unique_key(symbol)
        return self.orderbook_states.get(unique_key)

    @property
    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self._is_running