"""
MarketPrism 数据收集器主类

负责协调所有组件，包括交易所适配器、NATS发布器等
"""

import asyncio
import signal
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import structlog
from aiohttp import web
import json
import uvloop
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
import time

from .config import Config
from .types import (
    DataType, CollectorMetrics, HealthStatus,
    NormalizedTrade, NormalizedOrderBook, 
    NormalizedKline, NormalizedTicker,
    NormalizedFundingRate, NormalizedOpenInterest, NormalizedLiquidation,
    NormalizedTopTraderLongShortRatio,
    EnhancedOrderBook, OrderBookDelta, ExchangeConfig
)
from .nats_client import NATSManager, EnhancedMarketDataPublisher
from .exchanges import ExchangeAdapterFactory, ExchangeAdapter
from .monitoring import (
    CollectorMetrics as PrometheusMetrics,
    HealthChecker,
    get_metrics,
    check_nats_connection,
    check_exchange_connections,
    check_memory_usage,
    monitor_queue_sizes,
    update_system_metrics
)
from .normalizer import DataNormalizer
from .storage import ClickHouseWriter
from .orderbook_integration import OrderBookCollectorIntegration
from .rest_api import OrderBookRestAPI
from .rest_client import rest_client_manager
from .top_trader_collector import TopTraderDataCollector

# 导入任务调度器
try:
    import sys
    sys.path.append('..')  # 添加父目录到路径
    from scheduler import CollectorScheduler
    SCHEDULER_AVAILABLE = True
except ImportError:
    SCHEDULER_AVAILABLE = False
    CollectorScheduler = None


class MarketDataCollector:
    """MarketPrism 市场数据收集器"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = structlog.get_logger(__name__)
        
        # 核心组件
        self.nats_manager: Optional[NATSManager] = None
        self.normalizer = DataNormalizer()  # 初始化数据标准化器
        self.clickhouse_writer: Optional[ClickHouseWriter] = None  # ClickHouse直接写入器
        self.exchange_adapters: Dict[str, ExchangeAdapter] = {}
        
        # OrderBook Manager集成
        self.orderbook_integration: Optional[OrderBookCollectorIntegration] = None
        self.enhanced_publisher: Optional[EnhancedMarketDataPublisher] = None
        self.orderbook_rest_api: Optional[OrderBookRestAPI] = None
        
        # 大户持仓比数据收集器
        self.top_trader_collector: Optional[TopTraderDataCollector] = None
        
        # 状态管理
        self.is_running = False
        self.start_time: Optional[datetime] = None
        self.shutdown_event = asyncio.Event()
        self.http_app: Optional[web.Application] = None
        self.http_runner: Optional[web.AppRunner] = None
        
        # 监控系统
        self.metrics = CollectorMetrics()
        self.prometheus_metrics = PrometheusMetrics()
        self.health_checker: Optional[HealthChecker] = None
        
        # 任务调度器
        self.scheduler: Optional[CollectorScheduler] = None
        self.scheduler_enabled = SCHEDULER_AVAILABLE and getattr(config.collector, 'enable_scheduler', True)
        
        # 后台任务
        self.background_tasks: List[asyncio.Task] = []
        
        # 设置事件循环优化
        if sys.platform != 'win32':
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    
    async def start(self) -> bool:
        """启动收集器"""
        try:
            self.logger.info("启动MarketPrism数据收集器")
            self.start_time = datetime.utcnow()
            
            # 初始化监控系统
            await self._init_monitoring_system()
            
            # 设置代理环境
            self.config.setup_proxy_env()
            
            # 启动NATS管理器
            self.nats_manager = NATSManager(self.config.nats)
            nats_success = await self.nats_manager.start()
            if not nats_success:
                self.logger.error("NATS启动失败")
                return False
            
            # 创建增强发布器
            self.enhanced_publisher = EnhancedMarketDataPublisher(
                self.nats_manager.get_publisher()
            )
            
            # 启动OrderBook Manager集成
            await self._start_orderbook_integration()
            
            # 启动ClickHouse写入器（如果启用）
            self.clickhouse_writer = ClickHouseWriter(self.config.__dict__)
            await self.clickhouse_writer.start()
            
            # 启动交易所适配器
            await self._start_exchange_adapters()
            
            # 启动大户持仓比数据收集器
            await self._start_top_trader_collector()
            
            # 启动任务调度器（如果启用）
            if self.scheduler_enabled:
                await self._start_scheduler()
            
            # 启动HTTP服务
            await self._start_http_server()
            
            # 启动后台监控任务
            await self._start_background_tasks()
            
            # 注册信号处理器
            self._setup_signal_handlers()
            
            self.is_running = True
            self.logger.info("MarketPrism数据收集器启动成功")
            
            return True
            
        except Exception as e:
            self.logger.error("启动收集器失败", error=str(e))
            await self.stop()
            return False
    
    async def stop(self):
        """停止收集器"""
        try:
            self.logger.info("停止MarketPrism数据收集器")
            self.is_running = False
            
            # 停止任务调度器
            if self.scheduler:
                await self._stop_scheduler()
            
            # 停止后台监控任务
            await self._stop_background_tasks()
            
            # 停止交易所适配器
            await self._stop_exchange_adapters()
            
            # 停止大户持仓比数据收集器
            await self._stop_top_trader_collector()
            
            # 停止OrderBook Manager集成
            await self._stop_orderbook_integration()
            
            # 停止ClickHouse写入器
            if self.clickhouse_writer:
                await self.clickhouse_writer.stop()
            
            # 停止NATS管理器
            if self.nats_manager:
                await self.nats_manager.stop()
            
            # 停止HTTP服务
            if self.http_app:
                await self.http_app.cleanup()
            
            self.logger.info("MarketPrism数据收集器已停止")
            
        except Exception as e:
            self.logger.error("停止收集器失败", error=str(e))
    
    async def run(self):
        """运行收集器直到收到停止信号"""
        if not await self.start():
            return
        
        try:
            # 等待停止信号
            await self.shutdown_event.wait()
            
        except KeyboardInterrupt:
            self.logger.info("收到键盘中断信号")
            
        finally:
            await self.stop()
    
    async def _init_monitoring_system(self):
        """初始化监控系统"""
        try:
            # 注册健康检查项
            self.health_checker = HealthChecker()
            self.health_checker.register_check(
                'nats_connection',
                lambda: check_nats_connection(self.nats_manager.get_publisher() if self.nats_manager else None),
                timeout=5.0
            )
            
            self.health_checker.register_check(
                'exchange_connections',
                lambda: check_exchange_connections(self.exchange_adapters),
                timeout=5.0
            )
            
            self.health_checker.register_check(
                'memory_usage',
                check_memory_usage,
                timeout=3.0
            )
            
            # 初始化系统信息
            import platform
            import sys
            
            system_info = {
                'python_version': sys.version.split()[0],
                'platform': platform.platform(),
                'hostname': platform.node(),
                'collector_version': '1.0.0-enterprise'
            }
            self.prometheus_metrics.update_system_info(system_info)
            
            self.logger.info("监控系统初始化完成")
            
        except Exception as e:
            self.logger.error("初始化监控系统失败", error=str(e))
            raise
    
    async def _start_background_tasks(self):
        """启动后台监控任务"""
        try:
            # 队列大小监控任务
            queue_monitor_task = asyncio.create_task(
                monitor_queue_sizes(self.exchange_adapters, interval=30.0)
            )
            self.background_tasks.append(queue_monitor_task)
            
            # 系统指标更新任务
            metrics_update_task = asyncio.create_task(
                update_system_metrics(interval=60.0)
            )
            self.background_tasks.append(metrics_update_task)
            
            self.logger.info("后台监控任务启动完成")
            
        except Exception as e:
            self.logger.error("启动后台监控任务失败", error=str(e))
            raise
    
    async def _stop_background_tasks(self):
        """停止后台监控任务"""
        for task in self.background_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        self.background_tasks.clear()
        self.logger.info("后台监控任务已停止")
    
    async def _start_exchange_adapters(self):
        """启动交易所适配器"""
        enabled_exchanges = self.config.get_enabled_exchanges()
        
        if not enabled_exchanges:
            self.logger.warning("没有启用的交易所")
            return
        
        for exchange_config in enabled_exchanges:
            try:
                # 使用工厂创建适配器
                adapter = ExchangeAdapterFactory.create_adapter(exchange_config)
                
                # 注册数据回调
                self._register_adapter_callbacks(adapter)
                
                # 启动适配器
                success = await adapter.start()
                if success:
                    adapter_key = f"{exchange_config.exchange.value}_{exchange_config.market_type.value}"
                    self.exchange_adapters[adapter_key] = adapter
                    
                    self.logger.info(
                        "交易所适配器启动成功",
                        exchange=exchange_config.exchange.value,
                        market_type=exchange_config.market_type.value,
                        use_real=self.config.collector.use_real_exchanges
                    )
                else:
                    self.logger.error(
                        "交易所适配器启动失败",
                        exchange=exchange_config.exchange.value,
                        market_type=exchange_config.market_type.value
                    )
                    
            except Exception as e:
                self.logger.error(
                    "启动交易所适配器异常",
                    exchange=exchange_config.exchange.value,
                    error=str(e)
                )
    
    async def _stop_exchange_adapters(self):
        """停止交易所适配器"""
        for adapter_key, adapter in self.exchange_adapters.items():
            try:
                await adapter.stop()
                self.logger.info("交易所适配器已停止", adapter=adapter_key)
            except Exception as e:
                self.logger.error("停止交易所适配器失败", adapter=adapter_key, error=str(e))
        
        self.exchange_adapters.clear()
    
    async def _start_orderbook_integration(self):
        """启动OrderBook Manager集成"""
        try:
            # 检查是否启用OrderBook Manager
            if not getattr(self.config.collector, 'enable_orderbook_manager', False):
                self.logger.info("OrderBook Manager未启用，跳过启动")
                return
            
            # 创建OrderBook集成
            self.orderbook_integration = OrderBookCollectorIntegration()
            
            # 为每个启用的交易所添加集成
            enabled_exchanges = self.config.get_enabled_exchanges()
            for exchange_config in enabled_exchanges:
                # 只为支持的交易所启用OrderBook Manager
                if exchange_config.exchange.value.lower() in ['binance', 'okx']:
                    # 创建专门的OrderBook配置
                    orderbook_config = ExchangeConfig(
                        exchange=exchange_config.exchange,
                        market_type=exchange_config.market_type,
                        symbols=exchange_config.symbols,
                        base_url=exchange_config.base_url,
                        ws_url=exchange_config.ws_url,  # 添加WebSocket URL
                        data_types=exchange_config.data_types,  # 添加数据类型
                        depth_limit=5000,  # 全量深度
                        snapshot_interval=600  # 10分钟刷新快照，减少API调用
                    )
                    
                    success = await self.orderbook_integration.add_exchange_integration(
                        orderbook_config,
                        self.normalizer,
                        self.enhanced_publisher
                    )
                    
                    if success:
                        self.logger.info(
                            "OrderBook Manager集成启动成功",
                            exchange=exchange_config.exchange.value,
                            symbols=exchange_config.symbols
                        )
                    else:
                        self.logger.error(
                            "OrderBook Manager集成启动失败",
                            exchange=exchange_config.exchange.value
                        )
            
            # 创建REST API
            if self.orderbook_integration:
                self.orderbook_rest_api = OrderBookRestAPI(self.orderbook_integration)
                self.logger.info("OrderBook REST API已创建")
            
        except Exception as e:
            self.logger.error("启动OrderBook Manager集成失败", error=str(e))
            self.orderbook_integration = None
            self.orderbook_rest_api = None
    
    async def _stop_orderbook_integration(self):
        """停止OrderBook Manager集成"""
        try:
            if self.orderbook_integration:
                await self.orderbook_integration.stop_all()
                self.logger.info("OrderBook Manager集成已停止")
            
            self.orderbook_integration = None
            self.orderbook_rest_api = None
            
        except Exception as e:
            self.logger.error("停止OrderBook Manager集成失败", error=str(e))
    
    def _register_adapter_callbacks(self, adapter: ExchangeAdapter):
        """注册适配器数据回调"""
        adapter.register_callback(DataType.TRADE, self._handle_trade_data)
        adapter.register_callback(DataType.ORDERBOOK, self._handle_orderbook_data)
        adapter.register_callback(DataType.KLINE, self._handle_kline_data)
        adapter.register_callback(DataType.TICKER, self._handle_ticker_data)
        adapter.register_callback(DataType.FUNDING_RATE, self._handle_funding_rate_data)
        adapter.register_callback(DataType.OPEN_INTEREST, self._handle_open_interest_data)
        adapter.register_callback(DataType.LIQUIDATION, self._handle_liquidation_data)
        
        # 注册WebSocket原始数据回调用于OrderBook Manager
        if hasattr(adapter, 'register_raw_callback'):
            self.logger.info("注册原始深度数据回调", exchange=adapter.config.exchange.value)
            adapter.register_raw_callback('depth', self._handle_raw_depth_data)
    
    async def _handle_raw_depth_data(self, exchange: str, symbol: str, raw_data: Dict[str, Any]):
        """原始深度数据双路处理"""
        try:
            self.logger.info("处理原始深度数据", exchange=exchange, symbol=symbol, update_id=raw_data.get("u"))
            # 路径1: 标准化 → NATS发布
            if self.enhanced_publisher:
                normalized_update = await self.normalizer.normalize_depth_update(
                    raw_data, exchange, symbol
                )
                if normalized_update:
                    success = await self.enhanced_publisher.publish_depth_update(normalized_update)
                    if success:
                        self.logger.debug(
                            "增量深度数据发布成功",
                            exchange=exchange,
                            symbol=symbol,
                            update_id=normalized_update.last_update_id
                        )
                        
                        # 更新指标
                        self.metrics.messages_processed += 1
                        self.metrics.messages_published += 1
                        self.metrics.last_message_time = datetime.utcnow()
                        
                        # 更新交易所统计
                        exchange_key = exchange
                        if exchange_key not in self.metrics.exchange_stats:
                            self.metrics.exchange_stats[exchange_key] = {}
                        
                        stats = self.metrics.exchange_stats[exchange_key]
                        stats['depth_updates'] = stats.get('depth_updates', 0) + 1
            
            # 路径2: 原始数据 → OrderBook Manager
            if self.orderbook_integration:
                self.logger.info("发送数据到OrderBook Manager", exchange=exchange, symbol=symbol)
                success = await self.orderbook_integration.process_websocket_message(
                    exchange, symbol, raw_data
                )
                
                if success:
                    self.logger.info(
                        "OrderBook Manager处理成功",
                        exchange=exchange,
                        symbol=symbol
                    )
                else:
                    self.logger.warning(
                        "OrderBook Manager处理失败",
                        exchange=exchange,
                        symbol=symbol
                    )
                    
        except Exception as e:
            self.logger.error(
                "原始深度数据双路处理异常",
                exchange=exchange,
                symbol=symbol,
                error=str(e)
            )
            self._record_error(exchange, type(e).__name__)
    
    async def _handle_trade_data(self, trade: NormalizedTrade):
        """处理交易数据 - 数据已经由normalizer处理过"""
        start_time = time.time()
        
        try:
            if self.nats_manager:
                publisher = self.nats_manager.get_publisher()
                success = await publisher.publish_trade(trade)
                
                if success:
                    # 更新指标
                    self.metrics.messages_processed += 1
                    self.metrics.messages_published += 1
                    self.metrics.last_message_time = datetime.utcnow()
                    
                    # 更新Prometheus指标
                    self.prometheus_metrics.record_message_processed(
                        trade.exchange_name, 'trade', 'success'
                    )
                    self.prometheus_metrics.record_nats_publish(
                        trade.exchange_name, 'trade', 'success'
                    )
                    
                    # 更新交易所统计
                    exchange_key = trade.exchange_name
                    if exchange_key not in self.metrics.exchange_stats:
                        self.metrics.exchange_stats[exchange_key] = {}
                    
                    stats = self.metrics.exchange_stats[exchange_key]
                    stats['trades'] = stats.get('trades', 0) + 1
                    
                    self.logger.debug(
                        "交易数据发布成功",
                        exchange=trade.exchange_name,
                        symbol=trade.symbol_name,
                        price=str(trade.price),
                        quantity=str(trade.quantity)
                    )
                else:
                    self._record_error(trade.exchange_name, 'publish_failed')
            
            # 写入ClickHouse（如果启用）
            if self.clickhouse_writer:
                await self.clickhouse_writer.write_trade(trade)
                    
        except Exception as e:
            self.logger.error("处理交易数据失败", error=str(e))
            self._record_error(trade.exchange_name, type(e).__name__)
        finally:
            # 记录处理时间
            duration = time.time() - start_time
            self.prometheus_metrics.record_processing_time(
                trade.exchange_name, 'trade', duration
            )
    
    async def _handle_orderbook_data(self, orderbook: NormalizedOrderBook):
        """处理订单簿数据 - 数据已经由normalizer处理过"""
        start_time = time.time()
        
        try:
            if self.nats_manager:
                publisher = self.nats_manager.get_publisher()
                success = await publisher.publish_orderbook(orderbook)
                
                if success:
                    # 更新指标
                    self.metrics.messages_processed += 1
                    self.metrics.messages_published += 1
                    self.metrics.last_message_time = datetime.utcnow()
                    
                    # 更新Prometheus指标
                    self.prometheus_metrics.record_message_processed(
                        orderbook.exchange_name, 'orderbook', 'success'
                    )
                    self.prometheus_metrics.record_nats_publish(
                        orderbook.exchange_name, 'orderbook', 'success'
                    )
                    
                    # 更新交易所统计
                    exchange_key = orderbook.exchange_name
                    if exchange_key not in self.metrics.exchange_stats:
                        self.metrics.exchange_stats[exchange_key] = {}
                    
                    stats = self.metrics.exchange_stats[exchange_key]
                    stats['orderbooks'] = stats.get('orderbooks', 0) + 1
                    
                    self.logger.debug(
                        "订单簿数据发布成功",
                        exchange=orderbook.exchange_name,
                        symbol=orderbook.symbol_name,
                        bids_count=len(orderbook.bids),
                        asks_count=len(orderbook.asks)
                    )
                else:
                    self._record_error(orderbook.exchange_name, 'publish_failed')
            
            # 写入ClickHouse（如果启用）
            if self.clickhouse_writer:
                await self.clickhouse_writer.write_orderbook(orderbook)
                    
        except Exception as e:
            self.logger.error("处理订单簿数据失败", error=str(e))
            self._record_error(orderbook.exchange_name, type(e).__name__)
        finally:
            # 记录处理时间
            duration = time.time() - start_time
            self.prometheus_metrics.record_processing_time(
                orderbook.exchange_name, 'orderbook', duration
            )
    
    async def _handle_kline_data(self, kline: NormalizedKline):
        """处理K线数据"""
        start_time = time.time()
        
        try:
            if self.nats_manager:
                publisher = self.nats_manager.get_publisher()
                success = await publisher.publish_kline(kline)
                
                if success:
                    # 更新旧的指标（保持兼容性）
                    self.metrics.messages_processed += 1
                    self.metrics.messages_published += 1
                    self.metrics.last_message_time = datetime.utcnow()
                    
                    # 更新新的Prometheus指标
                    self.prometheus_metrics.record_message_processed(
                        kline.exchange_name, 'kline', 'success'
                    )
                    self.prometheus_metrics.record_nats_publish(
                        kline.exchange_name, 'kline', 'success'
                    )
                    
                    # 更新交易所统计
                    exchange_key = kline.exchange_name
                    if exchange_key not in self.metrics.exchange_stats:
                        self.metrics.exchange_stats[exchange_key] = {}
                    
                    stats = self.metrics.exchange_stats[exchange_key]
                    stats['klines'] = stats.get('klines', 0) + 1
                    
                    self.logger.debug(
                        "K线数据发布成功",
                        exchange=kline.exchange_name,
                        symbol=kline.symbol_name,
                        interval=kline.interval,
                        close_price=str(kline.close_price),
                        volume=str(kline.volume)
                    )
                else:
                    self.metrics.errors_count += 1
                    self.prometheus_metrics.record_nats_publish(
                        kline.exchange_name, 'kline', 'error'
                    )
                    
        except Exception as e:
            self.logger.error("处理K线数据失败", error=str(e))
            self.metrics.errors_count += 1
            
            # 记录错误到新指标
            error_type = type(e).__name__
            self.prometheus_metrics.record_error(kline.exchange_name, error_type)
            self.prometheus_metrics.record_message_processed(
                kline.exchange_name, 'kline', 'error'
            )
        finally:
            # 记录处理时间
            duration = time.time() - start_time
            self.prometheus_metrics.record_processing_time(
                kline.exchange_name, 'kline', duration
            )
    
    async def _handle_ticker_data(self, ticker: NormalizedTicker):
        """处理行情数据 - 数据已经由normalizer处理过"""
        start_time = time.time()
        
        try:
            if self.nats_manager:
                publisher = self.nats_manager.get_publisher()
                success = await publisher.publish_ticker(ticker)
                
                if success:
                    # 更新指标
                    self.metrics.messages_processed += 1
                    self.metrics.messages_published += 1
                    self.metrics.last_message_time = datetime.utcnow()
                    
                    # 更新Prometheus指标
                    self.prometheus_metrics.record_message_processed(
                        ticker.exchange_name, 'ticker', 'success'
                    )
                    self.prometheus_metrics.record_nats_publish(
                        ticker.exchange_name, 'ticker', 'success'
                    )
                    
                    # 更新交易所统计
                    exchange_key = ticker.exchange_name
                    if exchange_key not in self.metrics.exchange_stats:
                        self.metrics.exchange_stats[exchange_key] = {}
                    
                    stats = self.metrics.exchange_stats[exchange_key]
                    stats['tickers'] = stats.get('tickers', 0) + 1
                    
                    self.logger.debug(
                        "行情数据发布成功",
                        exchange=ticker.exchange_name,
                        symbol=ticker.symbol_name,
                        price=str(ticker.last_price),
                        volume=str(ticker.volume),
                        change=str(ticker.price_change)
                    )
                else:
                    self._record_error(ticker.exchange_name, 'publish_failed')
            
            # 写入ClickHouse（如果启用）
            if self.clickhouse_writer:
                await self.clickhouse_writer.write_ticker(ticker)
                    
        except Exception as e:
            self.logger.error("处理行情数据失败", error=str(e))
            self._record_error(ticker.exchange_name, type(e).__name__)
        finally:
            # 记录处理时间
            duration = time.time() - start_time
            self.prometheus_metrics.record_processing_time(
                ticker.exchange_name, 'ticker', duration
            )
    
    async def _handle_funding_rate_data(self, funding_rate: NormalizedFundingRate):
        """处理资金费率数据"""
        start_time = time.time()
        
        try:
            if self.nats_manager:
                publisher = self.nats_manager.get_publisher()
                success = await publisher.publish_funding_rate(funding_rate)
                
                if success:
                    # 更新指标
                    self.metrics.messages_processed += 1
                    self.metrics.messages_published += 1
                    self.metrics.last_message_time = datetime.utcnow()
                    
                    # 更新Prometheus指标
                    self.prometheus_metrics.record_message_processed(
                        funding_rate.exchange_name, 'funding_rate', 'success'
                    )
                    self.prometheus_metrics.record_nats_publish(
                        funding_rate.exchange_name, 'funding_rate', 'success'
                    )
                    
                    # 更新交易所统计
                    exchange_key = funding_rate.exchange_name
                    if exchange_key not in self.metrics.exchange_stats:
                        self.metrics.exchange_stats[exchange_key] = {}
                    
                    stats = self.metrics.exchange_stats[exchange_key]
                    stats['funding_rates'] = stats.get('funding_rates', 0) + 1
                    
                    self.logger.debug(
                        "资金费率数据发布成功",
                        exchange=funding_rate.exchange_name,
                        symbol=funding_rate.symbol_name,
                        rate=str(funding_rate.funding_rate),
                        next_funding=funding_rate.next_funding_time.isoformat()
                    )
                else:
                    self._record_error(funding_rate.exchange_name, 'publish_failed')
                    
        except Exception as e:
            self.logger.error("处理资金费率数据失败", error=str(e))
            self._record_error(funding_rate.exchange_name, type(e).__name__)
        finally:
            # 记录处理时间
            duration = time.time() - start_time
            self.prometheus_metrics.record_processing_time(
                funding_rate.exchange_name, 'funding_rate', duration
            )
    
    async def _handle_open_interest_data(self, open_interest: NormalizedOpenInterest):
        """处理持仓量数据"""
        start_time = time.time()
        
        try:
            if self.nats_manager:
                publisher = self.nats_manager.get_publisher()
                success = await publisher.publish_open_interest(open_interest)
                
                if success:
                    # 更新指标
                    self.metrics.messages_processed += 1
                    self.metrics.messages_published += 1
                    self.metrics.last_message_time = datetime.utcnow()
                    
                    # 更新Prometheus指标
                    self.prometheus_metrics.record_message_processed(
                        open_interest.exchange_name, 'open_interest', 'success'
                    )
                    self.prometheus_metrics.record_nats_publish(
                        open_interest.exchange_name, 'open_interest', 'success'
                    )
                    
                    # 更新交易所统计
                    exchange_key = open_interest.exchange_name
                    if exchange_key not in self.metrics.exchange_stats:
                        self.metrics.exchange_stats[exchange_key] = {}
                    
                    stats = self.metrics.exchange_stats[exchange_key]
                    stats['open_interests'] = stats.get('open_interests', 0) + 1
                    
                    self.logger.debug(
                        "持仓量数据发布成功",
                        exchange=open_interest.exchange_name,
                        symbol=open_interest.symbol_name,
                        value=str(open_interest.open_interest_value),
                        type=open_interest.instrument_type
                    )
                else:
                    self._record_error(open_interest.exchange_name, 'publish_failed')
                    
        except Exception as e:
            self.logger.error("处理持仓量数据失败", error=str(e))
            self._record_error(open_interest.exchange_name, type(e).__name__)
        finally:
            # 记录处理时间
            duration = time.time() - start_time
            self.prometheus_metrics.record_processing_time(
                open_interest.exchange_name, 'open_interest', duration
            )
    
    async def _handle_liquidation_data(self, liquidation: NormalizedLiquidation):
        """处理强平数据"""
        try:
                    # 更新指标
            self.metrics.liquidations_processed += 1
            self.prometheus_metrics.increment_data_processed('liquidation')
            
            # 发布到NATS
            if self.enhanced_publisher:
                await self.enhanced_publisher.publish_liquidation(liquidation)
                    
            # 写入ClickHouse（如果启用）
            if self.clickhouse_writer:
                await self.clickhouse_writer.write_liquidation(liquidation)
            
            self.logger.debug(
                "强平数据处理完成",
                        exchange=liquidation.exchange_name,
                        symbol=liquidation.symbol_name,
                        side=liquidation.side,
                        quantity=str(liquidation.quantity),
                price=str(liquidation.price)
                    )
                    
        except Exception as e:
            self.logger.error("处理强平数据失败", error=str(e))
            self._record_error(liquidation.exchange_name, "liquidation_processing")
    
    async def _handle_top_trader_data(self, top_trader_data: NormalizedTopTraderLongShortRatio):
        """处理大户持仓比数据"""
        try:
            # 更新指标
            self.metrics.data_points_processed += 1
            self.prometheus_metrics.increment_data_processed('top_trader_long_short_ratio')
            
            # 发布到NATS
            if self.enhanced_publisher:
                await self.enhanced_publisher.publish_data(
                    DataType.TOP_TRADER_LONG_SHORT_RATIO,
                    top_trader_data.dict()
                )
            
            # 写入ClickHouse（如果启用）
            if self.clickhouse_writer:
                # 这里可以添加ClickHouse写入逻辑
                pass
            
            self.logger.debug(
                "大户持仓比数据处理完成",
                exchange=top_trader_data.exchange_name,
                symbol=top_trader_data.symbol_name,
                long_short_ratio=str(top_trader_data.long_short_ratio),
                long_position_ratio=str(top_trader_data.long_position_ratio),
                short_position_ratio=str(top_trader_data.short_position_ratio)
            )
            
        except Exception as e:
            self.logger.error("处理大户持仓比数据失败", error=str(e))
            self._record_error(top_trader_data.exchange_name, "top_trader_processing")
    
    async def _start_http_server(self):
        """启动HTTP服务器"""
        try:
            self.http_app = web.Application()
            
            # 现有路由
            self.http_app.router.add_get('/health', self._health_handler)
            self.http_app.router.add_get('/metrics', self._metrics_handler)
            self.http_app.router.add_get('/status', self._status_handler)
            self.http_app.router.add_get('/scheduler', self._scheduler_handler)  # 新增调度器状态端点
            
            # 新增：数据中心快照代理端点
            self.http_app.router.add_get('/api/v1/snapshot/{exchange}/{symbol}', self._snapshot_handler)
            self.http_app.router.add_get('/api/v1/snapshot/{exchange}/{symbol}/cached', self._cached_snapshot_handler)
            self.http_app.router.add_get('/api/v1/data-center/info', self._data_center_info_handler)
            
            # 任务调度器接口（如果启用）
            if self.scheduler_enabled and self.scheduler:
                self.http_app.router.add_get('/api/v1/scheduler/status', self._scheduler_handler)
            
            # 大户持仓比数据收集器接口
            if self.top_trader_collector:
                self.http_app.router.add_get('/api/v1/top-trader/status', self._top_trader_status_handler)
                self.http_app.router.add_get('/api/v1/top-trader/stats', self._top_trader_stats_handler)
                self.http_app.router.add_post('/api/v1/top-trader/refresh', self._top_trader_refresh_handler)
            
            # OrderBook Manager接口（如果启用）
            if self.orderbook_rest_api:
                # 添加OrderBook Manager的所有路由
                self.http_app.router.add_get('/api/v1/orderbook/{exchange}/{symbol}', self.orderbook_rest_api.get_orderbook)
                self.http_app.router.add_get('/api/v1/orderbook/{exchange}/{symbol}/snapshot', self.orderbook_rest_api.get_orderbook_snapshot)
                self.http_app.router.add_post('/api/v1/orderbook/{exchange}/{symbol}/refresh', self.orderbook_rest_api.refresh_orderbook)
                self.http_app.router.add_get('/api/v1/orderbook/stats', self.orderbook_rest_api.get_all_stats)
                self.http_app.router.add_get('/api/v1/orderbook/stats/{exchange}', self.orderbook_rest_api.get_exchange_stats)
                self.http_app.router.add_get('/api/v1/orderbook/health', self.orderbook_rest_api.health_check)
                self.http_app.router.add_get('/api/v1/orderbook/status/{exchange}/{symbol}', self.orderbook_rest_api.get_symbol_status)
                self.http_app.router.add_get('/api/v1/orderbook/exchanges', self.orderbook_rest_api.list_exchanges)
                self.http_app.router.add_get('/api/v1/orderbook/symbols/{exchange}', self.orderbook_rest_api.list_symbols)
                self.http_app.router.add_get('/api/v1/orderbook/api/stats', self.orderbook_rest_api.get_api_stats)
            
            # 启动服务器
            self.http_runner = web.AppRunner(self.http_app)
            await self.http_runner.setup()
            
            site = web.TCPSite(self.http_runner, '0.0.0.0', self.config.collector.http_port)
            await site.start()
            
            self.logger.info(
                "HTTP服务器启动成功",
                port=self.config.collector.http_port
            )
            
        except Exception as e:
            self.logger.error("HTTP服务器启动失败", error=str(e))
            raise

    async def _snapshot_handler(self, request):
        """快照代理处理器 - 为客户端提供标准化快照"""
        exchange = request.match_info['exchange']
        symbol = request.match_info['symbol']
        
        try:
            # 通过现有的交易所适配器获取快照
            adapter = self.exchange_adapters.get(exchange.lower())
            if not adapter:
                return web.json_response(
                    {"error": f"不支持的交易所: {exchange}"}, 
                    status=400
                )
            
            # 获取原始快照
            if exchange.lower() == 'binance':
                raw_snapshot = await adapter.get_orderbook_snapshot(symbol, limit=5000)
            elif exchange.lower() == 'okx':
                raw_snapshot = await adapter.get_orderbook_snapshot(symbol, sz=5000)
            else:
                return web.json_response(
                    {"error": f"未实现的交易所: {exchange}"}, 
                    status=501
                )
            
            # 使用现有的标准化器处理
            normalized_snapshot = await self.normalizer.normalize_orderbook_snapshot(
                raw_snapshot, exchange, symbol
            )
            
            # 返回标准化快照
            return web.json_response(normalized_snapshot.dict())
            
        except Exception as e:
            self.logger.error("获取快照失败", exchange=exchange, symbol=symbol, error=str(e))
            return web.json_response({"error": str(e)}, status=500)

    async def _cached_snapshot_handler(self, request):
        """缓存快照处理器 - 优先返回缓存的快照"""
        exchange = request.match_info['exchange']
        symbol = request.match_info['symbol']
        
        try:
            # 如果有OrderBook Manager，优先从其获取
            if self.orderbook_integration:
                try:
                    orderbook = await self.orderbook_integration.get_current_orderbook(exchange, symbol)
                    if orderbook:
                        return web.json_response(orderbook.dict())
                except Exception as e:
                    self.logger.warning("从OrderBook Manager获取失败，降级到实时快照", error=str(e))
            
            # 降级到实时快照
            return await self._snapshot_handler(request)
            
        except Exception as e:
            self.logger.error("获取缓存快照失败", exchange=exchange, symbol=symbol, error=str(e))
            return web.json_response({"error": str(e)}, status=500)

    async def _data_center_info_handler(self, request):
        """数据中心信息处理器"""
        try:
            info = {
                "service": "MarketPrism Data Center",
                "version": "1.0.0",
                "status": "running" if self.is_running else "stopped",
                "start_time": self.start_time.isoformat() + 'Z' if self.start_time else None,
                "uptime_seconds": self.metrics.uptime_seconds,
                
                # 支持的交易所和交易对
                "supported_exchanges": list(self.exchange_adapters.keys()),
                "supported_symbols": self._get_supported_symbols(),
                
                # 服务能力
                "capabilities": {
                    "real_time_snapshots": True,
                    "cached_snapshots": bool(self.orderbook_integration),
                    "orderbook_manager": bool(self.orderbook_integration),
                    "nats_streaming": bool(self.nats_manager),
                    "rest_api": True
                },
                
                # 端点信息
                "endpoints": {
                    "snapshot": "/api/v1/snapshot/{exchange}/{symbol}",
                    "cached_snapshot": "/api/v1/snapshot/{exchange}/{symbol}/cached",
                    "orderbook": "/api/v1/orderbook/{exchange}/{symbol}",
                    "health": "/health",
                    "status": "/status",
                    "metrics": "/metrics"
                },
                
                # NATS信息
                "nats": {
                    "connected": self.nats_manager.get_publisher().is_connected if self.nats_manager else False,
                    "streams": list(self.config.nats.streams.keys()) if self.nats_manager else []
                }
            }
            
            return web.json_response(info)
            
        except Exception as e:
            self.logger.error("获取数据中心信息失败", error=str(e))
            return web.json_response({"error": str(e)}, status=500)

    def _get_supported_symbols(self) -> Dict[str, List[str]]:
        """获取支持的交易对列表"""
        symbols = {}
        for exchange_name, adapter in self.exchange_adapters.items():
            if hasattr(adapter, 'get_supported_symbols'):
                symbols[exchange_name] = adapter.get_supported_symbols()
            else:
                # 从配置中获取
                exchange_config = getattr(self.config, exchange_name, None)
                if exchange_config and hasattr(exchange_config, 'symbols'):
                    symbols[exchange_name] = exchange_config.symbols
                else:
                    symbols[exchange_name] = ["BTC-USDT", "ETH-USDT"]  # 默认
        return symbols

    async def _health_handler(self, request):
        """健康检查处理器（使用新的健康检查系统）"""
        try:
            # 使用新的健康检查系统
            health_status = await self.health_checker.check_health()
            
            # 确定HTTP状态码
            if health_status.status == "healthy":
                http_status = 200
            elif health_status.status == "degraded":
                http_status = 200  # degraded状态仍然返回200
            else:
                http_status = 503  # unhealthy返回503
            
            # 序列化健康检查结果
            health_data = {
                "status": health_status.status,
                "timestamp": health_status.timestamp.isoformat() + 'Z' if hasattr(health_status.timestamp, 'isoformat') else str(health_status.timestamp),
                "uptime_seconds": health_status.uptime_seconds,
                "checks": self._serialize_health_checks(getattr(health_status, 'checks', {})),
                "details": self._serialize_datetime(getattr(health_status, 'details', {})),
                "version": "1.0.0-enterprise",
                "service": "marketprism-collector"
            }
            
            return web.json_response(health_data, status=http_status)
            
        except Exception as e:
            self.logger.error("健康检查失败", error=str(e))
            return web.json_response(
                {
                    "status": "error",
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat() + 'Z',
                    "service": "marketprism-collector"
                },
                status=500
            )
    
    async def _metrics_handler(self, request):
        """Prometheus指标处理器（使用新的Prometheus系统）"""
        try:
            # 使用新的Prometheus指标系统
            metrics_data = generate_latest()
            return web.Response(
                body=metrics_data,
                content_type='text/plain'
            )
            
        except Exception as e:
            self.logger.error("获取Prometheus指标失败", error=str(e))
            return web.json_response(
                {"error": str(e)},
                status=500
            )
    
    def _serialize_datetime(self, obj):
        """递归序列化datetime对象为字符串"""
        if isinstance(obj, datetime):
            return obj.isoformat() + 'Z'
        elif isinstance(obj, dict):
            return {key: self._serialize_datetime(value) for key, value in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._serialize_datetime(item) for item in obj]
        else:
            return obj
    
    def _serialize_health_checks(self, checks):
        """序列化健康检查结果"""
        if not checks:
            return {}
        
        serialized = {}
        for key, value in checks.items():
            if hasattr(value, '__dict__'):
                # 如果是对象，转换为字典
                serialized[key] = {
                    'status': getattr(value, 'status', 'unknown'),
                    'message': getattr(value, 'message', ''),
                    'timestamp': getattr(value, 'timestamp', datetime.utcnow()).isoformat() + 'Z'
                }
            else:
                serialized[key] = str(value)
        return serialized

    async def _status_handler(self, request):
        """状态处理器"""
        try:
            status_info = {
                "collector": {
                    "running": self.is_running,
                    "start_time": self.start_time.isoformat() + 'Z' if self.start_time else None,
                    "uptime_seconds": self.metrics.uptime_seconds
                },
                "exchanges": {},
                "nats": {},
                "orderbook_manager": {}
            }
            
            # 交易所状态
            for adapter_key, adapter in self.exchange_adapters.items():
                adapter_stats = adapter.get_stats()
                status_info["exchanges"][adapter_key] = self._serialize_datetime(adapter_stats)
            
            # NATS状态
            if self.nats_manager:
                nats_health = await self.nats_manager.health_check()
                status_info["nats"] = self._serialize_datetime(nats_health)
            
            # OrderBook Manager状态
            if self.orderbook_integration:
                orderbook_stats = self.orderbook_integration.get_all_stats()
                status_info["orderbook_manager"] = self._serialize_datetime(orderbook_stats)
            else:
                status_info["orderbook_manager"] = {
                    "enabled": False,
                    "message": "OrderBook Manager未启用"
                }
            
            return web.json_response(status_info)
            
        except Exception as e:
            self.logger.error("获取状态失败", error=str(e))
            return web.json_response(
                {"error": str(e)},
                status=500
            )
    
    def _setup_signal_handlers(self):
        """设置信号处理器"""
        def signal_handler(signum, frame):
            self.logger.info(f"收到信号 {signum}")
            self.shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def get_metrics(self) -> CollectorMetrics:
        """获取收集器指标"""
        if self.start_time:
            self.metrics.uptime_seconds = (datetime.utcnow() - self.start_time).total_seconds()
        return self.metrics

    def _record_error(self, exchange: str, error_type: str):
        """记录错误"""
        self.metrics.errors_count += 1
        self.prometheus_metrics.record_error(exchange, error_type)

    async def _start_scheduler(self):
        """启动任务调度器"""
        if not SCHEDULER_AVAILABLE:
            self.logger.warning("任务调度器不可用，跳过启动")
            return
        
        try:
            self.scheduler = CollectorScheduler(self)
            await self.scheduler.start()
            self.logger.info("任务调度器启动成功")
            
        except Exception as e:
            self.logger.error("启动任务调度器失败", error=str(e))
            self.scheduler = None
    
    async def _stop_scheduler(self):
        """停止任务调度器"""
        if self.scheduler:
            try:
                await self.scheduler.stop()
                self.logger.info("任务调度器已停止")
            except Exception as e:
                self.logger.error("停止任务调度器失败", error=str(e))
            finally:
                self.scheduler = None

    async def _scheduler_handler(self, request):
        """任务调度器状态处理器"""
        try:
            if not self.scheduler_enabled:
                return web.json_response(
                    {
                        "scheduler_enabled": False,
                        "message": "任务调度器未启用",
                        "available": SCHEDULER_AVAILABLE
                    },
                    status=200
                )
            
            if not self.scheduler:
                return web.json_response(
                    {
                        "scheduler_enabled": True,
                        "scheduler_running": False,
                        "message": "任务调度器未运行",
                        "available": SCHEDULER_AVAILABLE
                    },
                    status=503
                )
            
            # 获取调度器状态
            scheduler_status = self.scheduler.get_jobs_status()
            
            return web.json_response(
                {
                    "scheduler_enabled": True,
                    "scheduler_available": SCHEDULER_AVAILABLE,
                    "timestamp": datetime.utcnow().isoformat() + 'Z',
                    **scheduler_status
                },
                status=200
            )
            
        except Exception as e:
            self.logger.error("获取调度器状态失败", error=str(e))
            return web.json_response(
                {
                    "error": str(e),
                    "scheduler_enabled": self.scheduler_enabled,
                    "scheduler_available": SCHEDULER_AVAILABLE
                },
                status=500
            )

    async def _start_top_trader_collector(self):
        """启动大户持仓比数据收集器"""
        try:
            # 检查是否启用大户持仓比数据收集器
            if not getattr(self.config.collector, 'enable_top_trader_collector', True):
                self.logger.info("大户持仓比数据收集器未启用，跳过启动")
                return
            
            # 创建大户持仓比数据收集器
            self.top_trader_collector = TopTraderDataCollector(rest_client_manager)
            
            # 注册数据回调函数
            self.top_trader_collector.register_callback(self._handle_top_trader_data)
            
            # 获取监控的交易对（从配置或使用默认值）
            symbols = getattr(self.config.collector, 'top_trader_symbols', ["BTC-USDT", "ETH-USDT", "BNB-USDT"])
            
            # 启动大户持仓比数据收集器
            await self.top_trader_collector.start(symbols)
            
            self.logger.info("大户持仓比数据收集器启动成功", symbols=symbols)
            
        except Exception as e:
            self.logger.error("启动大户持仓比数据收集器失败", error=str(e))
            self.top_trader_collector = None

    async def _stop_top_trader_collector(self):
        """停止大户持仓比数据收集器"""
        if self.top_trader_collector:
            try:
                await self.top_trader_collector.stop()
                self.logger.info("大户持仓比数据收集器已停止")
            except Exception as e:
                self.logger.error("停止大户持仓比数据收集器失败", error=str(e))
            finally:
                self.top_trader_collector = None

    async def _top_trader_status_handler(self, request):
        """大户持仓比数据收集器状态处理器"""
        try:
            if not self.top_trader_collector:
                return web.json_response(
                    {"status": "disabled", "message": "大户持仓比数据收集器未启用"},
                    status=404
                )
            
            status = await self.top_trader_collector.get_status()
            return web.json_response(status)
            
        except Exception as e:
            self.logger.error("获取大户持仓比数据收集器状态失败", error=str(e))
            return web.json_response({"error": str(e)}, status=500)
    
    async def _top_trader_stats_handler(self, request):
        """大户持仓比数据收集器统计处理器"""
        try:
            if not self.top_trader_collector:
                return web.json_response(
                    {"status": "disabled", "message": "大户持仓比数据收集器未启用"},
                    status=404
                )
            
            stats = await self.top_trader_collector.get_stats()
            return web.json_response(stats)
            
        except Exception as e:
            self.logger.error("获取大户持仓比数据收集器统计失败", error=str(e))
            return web.json_response({"error": str(e)}, status=500)
    
    async def _top_trader_refresh_handler(self, request):
        """大户持仓比数据收集器手动刷新处理器"""
        try:
            if not self.top_trader_collector:
                return web.json_response(
                    {"status": "disabled", "message": "大户持仓比数据收集器未启用"},
                    status=404
                )
            
            # 获取请求参数
            data = await request.json() if request.content_type == 'application/json' else {}
            symbols = data.get('symbols', None)
            exchanges = data.get('exchanges', None)
            
            # 执行手动刷新
            result = await self.top_trader_collector.manual_refresh(symbols=symbols, exchanges=exchanges)
            
            return web.json_response({
                "status": "success",
                "message": "手动刷新完成",
                "result": result
            })
            
        except Exception as e:
            self.logger.error("大户持仓比数据收集器手动刷新失败", error=str(e))
            return web.json_response({"error": str(e)}, status=500)


async def main():
    """主函数"""
    import argparse
    
    try:
        # 解析命令行参数
        parser = argparse.ArgumentParser(description='MarketPrism数据收集器')
        parser.add_argument('--config', '-c', 
                          default="../config/collector.yaml",
                          help='配置文件路径 (默认: ../config/collector.yaml)')
        
        args = parser.parse_args()
        
        # 加载配置
        config = Config.load_from_file(args.config)
        
        # 创建收集器
        collector = MarketDataCollector(config)
        
        # 运行收集器
        await collector.run()
        
    except Exception as e:
        print(f"启动收集器失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main()) 