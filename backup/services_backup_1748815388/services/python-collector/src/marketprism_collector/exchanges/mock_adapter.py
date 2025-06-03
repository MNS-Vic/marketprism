"""
Mock Exchange Adapter - 测试和开发支持

基于TDD发现的设计问题，提供测试用的模拟交易所适配器
支持：数据模拟、行为控制、错误注入、性能测试
"""

from typing import Dict, List, Optional, Any, Callable
import asyncio
import random
import time
from decimal import Decimal
from datetime import datetime, timedelta
from dataclasses import dataclass
import logging

from ..types import (
    NormalizedTrade, NormalizedOrderBook, NormalizedTicker, 
    NormalizedKline, NormalizedFundingRate, NormalizedOpenInterest,
    PriceLevel, Exchange, DataType
)


@dataclass
class MockConfig:
    """模拟适配器配置"""
    simulate_latency: bool = True
    min_latency_ms: int = 10
    max_latency_ms: int = 100
    error_rate: float = 0.0  # 错误率 0.0-1.0
    enable_websocket: bool = True
    data_update_interval: float = 1.0  # 数据更新间隔（秒）


class MockExchangeAdapter:
    """
    模拟交易所适配器 - TDD驱动的测试支持
    
    功能特性：
    - 完整的适配器接口实现
    - 可配置的延迟和错误模拟
    - 实时数据流模拟
    - 测试场景支持
    - 性能测试辅助
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化MockExchangeAdapter，支持灵活的配置"""
        self.config = config or {}
        self.exchange_name = "mock"
        self.logger = logging.getLogger(__name__)
        
        # Mock配置
        mock_config = self.config.get('mock', {})
        self.mock_config = MockConfig(
            simulate_latency=mock_config.get('simulate_latency', True),
            min_latency_ms=mock_config.get('min_latency_ms', 10),
            max_latency_ms=mock_config.get('max_latency_ms', 100),
            error_rate=mock_config.get('error_rate', 0.0),
            enable_websocket=mock_config.get('enable_websocket', True),
            data_update_interval=mock_config.get('data_update_interval', 1.0)
        )
        
        # 基础属性
        self.last_error = None
        self.error_count = 0
        
        # 模拟数据
        self._symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'ADA/USDT']
        self._current_prices = {
            'BTC/USDT': 50000.0,
            'ETH/USDT': 3000.0,
            'BNB/USDT': 400.0,
            'ADA/USDT': 1.5
        }
        
        # WebSocket模拟
        self._websocket_subscriptions: Dict[str, List[Callable]] = {}
        self._websocket_running = False
        self._websocket_task: Optional[asyncio.Task] = None
        
        # 企业级特性
        self.rate_limiter = MockRateLimiter()
        self.retry_config = {'max_retries': 3, 'backoff_factor': 1.5}
        self.circuit_breaker = MockCircuitBreaker()
        
        # 监控
        self.metrics = MockMetrics()
        self.performance_metrics = MockPerformanceMetrics()
        self.health_status = "healthy"
        
        # WebSocket管理
        self.websocket_manager = MockWebSocketManager()
        
        # 测试控制
        self._forced_errors: Dict[str, Exception] = {}
        self._response_delays: Dict[str, float] = {}
        
        self.logger.info("模拟交易所适配器已初始化: %s", self.exchange_name)
    
    def get_config(self) -> Dict[str, Any]:
        """获取配置"""
        return self.config.copy()
    
    def update_config(self, new_config: Dict[str, Any]):
        """更新配置"""
        self.config.update(new_config)
    
    def get_effective_config(self) -> Dict[str, Any]:
        """获取有效配置"""
        return self.get_config()
    
    def is_sandbox_mode(self) -> bool:
        """检查是否为沙盒模式"""
        return self.config.get('sandbox', True)  # Mock默认为沙盒模式
    
    # 企业级特性方法
    def check_rate_limit(self) -> bool:
        """检查速率限制"""
        return self.rate_limiter.check()
    
    def wait_for_rate_limit(self):
        """等待速率限制"""
        return self.rate_limiter.wait()
    
    def execute_with_retry(self, func: Callable, *args, **kwargs):
        """带重试执行方法"""
        max_retries = self.retry_config.get('max_retries', 3)
        backoff_factor = self.retry_config.get('backoff_factor', 1.5)
        
        for attempt in range(max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt == max_retries:
                    raise
                
                wait_time = backoff_factor ** attempt
                time.sleep(wait_time)
                self.logger.warning(f"重试第{attempt + 1}次，等待{wait_time}秒: {str(e)}")
    
    def is_circuit_open(self) -> bool:
        """检查熔断器是否开启"""
        return self.circuit_breaker.is_open()
    
    def reset_circuit(self):
        """重置熔断器"""
        self.circuit_breaker.reset()
    
    # 监控和健康检查
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'error_count': self.error_count,
            'last_error': self.last_error,
            'health_status': self.health_status,
            'metrics': self.metrics.get_stats(),
            'performance': self.performance_metrics.get_stats()
        }
    
    def get_health(self) -> Dict[str, Any]:
        """获取健康状态"""
        return {
            'status': self.health_status,
            'is_healthy': self.health_status == 'healthy',
            'error_count': self.error_count,
            'last_error': self.last_error,
            'circuit_breaker_open': self.is_circuit_open(),
            'rate_limit_ok': self.check_rate_limit()
        }
    
    def handle_error(self, error: Exception, context: str = ""):
        """处理错误"""
        self.last_error = str(error)
        self.error_count += 1
        
        # 更新健康状态
        if self.error_count > 5:
            self.health_status = "degraded"
        if self.error_count > 10:
            self.health_status = "unhealthy"
        
        self.logger.error(f"处理错误 {context}: {str(error)}")
    
    def reset_error_state(self):
        """重置错误状态"""
        self.last_error = None
        self.error_count = 0
        self.health_status = "healthy"
        self.logger.info("错误状态已重置")
    
    def record_request_time(self, method: str, duration: float):
        """记录请求时间"""
        self.performance_metrics.record_request(method, duration)
    
    def get_latency_stats(self) -> Dict[str, float]:
        """获取延迟统计"""
        return self.performance_metrics.get_latency_stats()
    
    def get_throughput_stats(self) -> Dict[str, float]:
        """获取吞吐量统计"""
        return self.performance_metrics.get_throughput_stats()
    
    # WebSocket管理
    def start_websocket(self) -> bool:
        """启动WebSocket"""
        return self.websocket_manager.start()
    
    def stop_websocket(self):
        """停止WebSocket"""
        self.websocket_manager.stop()
    
    def restart_websocket(self):
        """重启WebSocket"""
        self.stop_websocket()
        return self.start_websocket()
    
    def subscribe(self, channel: str, callback: Callable):
        """订阅数据"""
        self.websocket_manager.subscribe(channel, callback)
    
    def unsubscribe(self, channel: str, callback: Callable):
        """取消订阅"""
        self.websocket_manager.unsubscribe(channel, callback)
    
    def get_subscriptions(self) -> List[str]:
        """获取订阅列表"""
        return self.websocket_manager.get_subscriptions()
    
    def clear_subscriptions(self):
        """清除所有订阅"""
        self.websocket_manager.clear_subscriptions()
    
    # 核心数据获取方法
    async def get_trades(self, symbol: str, limit: int = 100, **kwargs) -> List[NormalizedTrade]:
        """获取交易数据"""
        await self._simulate_request_delay('get_trades')
        self._check_forced_error('get_trades')
        
        trades = []
        base_price = self._current_prices.get(symbol, 1000.0)
        current_time = datetime.utcnow()
        
        for i in range(limit):
            price_variation = random.uniform(-0.01, 0.01)
            price = Decimal(str(base_price * (1 + price_variation)))
            quantity = Decimal(str(random.uniform(0.001, 1.0)))
            
            trade = NormalizedTrade(
                exchange_name="mock",
                symbol_name=symbol,
                trade_id=f"mock_trade_{int(current_time.timestamp() * 1000)}_{i}",
                price=price,
                quantity=quantity,
                quote_quantity=price * quantity,  # 计算报价数量
                timestamp=current_time,
                side="buy" if random.choice([True, False]) else "sell"
            )
            trades.append(trade)
        
        self.metrics.record_request('get_trades', True)
        return trades
    
    async def get_orderbook(self, symbol: str, limit: int = 100, **kwargs) -> NormalizedOrderBook:
        """获取订单簿数据"""
        await self._simulate_request_delay('get_orderbook')
        self._check_forced_error('get_orderbook')
        
        base_price = self._current_prices.get(symbol, 1000.0)
        
        # 生成买单
        bids = []
        for i in range(limit):
            price = Decimal(str(base_price * (1 - (i + 1) * 0.001)))
            quantity = Decimal(str(random.uniform(0.1, 10.0)))
            bids.append(PriceLevel(price=price, quantity=quantity))
        
        # 生成卖单
        asks = []
        for i in range(limit):
            price = Decimal(str(base_price * (1 + (i + 1) * 0.001)))
            quantity = Decimal(str(random.uniform(0.1, 10.0)))
            asks.append(PriceLevel(price=price, quantity=quantity))
        
        orderbook = NormalizedOrderBook(
            exchange_name="mock",
            symbol_name=symbol,
            bids=bids,
            asks=asks,
            timestamp=datetime.utcnow()
        )
        
        self.metrics.record_request('get_orderbook', True)
        return orderbook
    
    async def get_ticker(self, symbol: str, **kwargs) -> NormalizedTicker:
        """获取行情数据"""
        await self._simulate_request_delay('get_ticker')
        self._check_forced_error('get_ticker')
        
        base_price = self._current_prices.get(symbol, 1000.0)
        price_change = random.uniform(-0.05, 0.05)
        current_time = datetime.utcnow()
        
        ticker = NormalizedTicker(
            exchange_name="mock",
            symbol_name=symbol,
            last_price=Decimal(str(base_price)),
            open_price=Decimal(str(base_price * 0.98)),
            high_price=Decimal(str(base_price * 1.05)),
            low_price=Decimal(str(base_price * 0.95)),
            volume=Decimal(str(random.uniform(1000, 10000))),
            quote_volume=Decimal(str(random.uniform(1000000, 10000000))),
            price_change=Decimal(str(price_change)),
            price_change_percent=Decimal(str(price_change * 100)),
            weighted_avg_price=Decimal(str(base_price * 1.001)),
            last_quantity=Decimal(str(random.uniform(0.1, 1.0))),
            best_bid_price=Decimal(str(base_price * 0.999)),
            best_bid_quantity=Decimal(str(random.uniform(1.0, 10.0))),
            best_ask_price=Decimal(str(base_price * 1.001)),
            best_ask_quantity=Decimal(str(random.uniform(1.0, 10.0))),
            open_time=current_time,
            close_time=current_time,
            trade_count=random.randint(100, 1000),
            timestamp=current_time
        )
        
        self.metrics.record_request('get_ticker', True)
        return ticker
    
    async def get_klines(self, symbol: str, interval: str = '1m', limit: int = 100, **kwargs) -> List[NormalizedKline]:
        """获取K线数据"""
        await self._simulate_request_delay('get_klines')
        self._check_forced_error('get_klines')
        
        klines = []
        base_price = self._current_prices.get(symbol, 1000.0)
        current_time = datetime.utcnow()
        interval_minutes = 1  # 1分钟
        
        for i in range(limit):
            open_price = Decimal(str(base_price * (1 + random.uniform(-0.02, 0.02))))
            close_price = Decimal(str(float(open_price) * (1 + random.uniform(-0.01, 0.01))))
            high_price = max(open_price, close_price) * Decimal('1.01')
            low_price = min(open_price, close_price) * Decimal('0.99')
            
            kline_time = current_time - timedelta(minutes=i * interval_minutes)
            
            kline = NormalizedKline(
                exchange_name="mock",
                symbol_name=symbol,
                open_time=kline_time,
                close_time=kline_time + timedelta(minutes=interval_minutes),
                interval=interval,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
                volume=Decimal(str(random.uniform(10, 1000))),
                quote_volume=Decimal(str(random.uniform(10000, 1000000))),
                trade_count=random.randint(10, 100),
                taker_buy_volume=Decimal(str(random.uniform(5, 500))),
                taker_buy_quote_volume=Decimal(str(random.uniform(5000, 500000)))
            )
            klines.append(kline)
        
        self.metrics.record_request('get_klines', True)
        return klines
    
    async def get_funding_rate(self, symbol: str, **kwargs) -> NormalizedFundingRate:
        """获取资金费率数据"""
        await self._simulate_request_delay('get_funding_rate')
        self._check_forced_error('get_funding_rate')
        
        current_time = datetime.utcnow()
        base_price = self._current_prices.get(symbol, 1000.0)
        
        funding_rate = NormalizedFundingRate(
            exchange_name="mock",
            symbol_name=symbol,
            funding_rate=Decimal(str(random.uniform(-0.001, 0.001))),
            next_funding_time=current_time + timedelta(hours=8),
            mark_price=Decimal(str(base_price)),
            index_price=Decimal(str(base_price * 0.999)),
            premium_index=Decimal(str(base_price * 0.001)),
            timestamp=current_time
        )
        
        self.metrics.record_request('get_funding_rate', True)
        return funding_rate
    
    async def get_open_interest(self, symbol: str, **kwargs) -> NormalizedOpenInterest:
        """获取持仓量数据"""
        await self._simulate_request_delay('get_open_interest')
        self._check_forced_error('get_open_interest')
        
        open_interest = NormalizedOpenInterest(
            exchange_name="mock",
            symbol_name=symbol,
            open_interest=Decimal(str(random.uniform(1000, 100000))),
            open_interest_value=Decimal(str(random.uniform(1000000, 100000000))),
            timestamp=datetime.utcnow()
        )
        
        self.metrics.record_request('get_open_interest', True)
        return open_interest
    
    # WebSocket订阅方法
    def subscribe_trades(self, symbol: str, callback: Callable) -> bool:
        """订阅交易数据"""
        return self._subscribe('trades', symbol, callback)
    
    def subscribe_orderbook(self, symbol: str, callback: Callable) -> bool:
        """订阅订单簿数据"""
        return self._subscribe('orderbook', symbol, callback)
    
    def subscribe_ticker(self, symbol: str, callback: Callable) -> bool:
        """订阅行情数据"""
        return self._subscribe('ticker', symbol, callback)
    
    def _subscribe(self, data_type: str, symbol: str, callback: Callable) -> bool:
        """通用订阅方法"""
        if not self.mock_config.enable_websocket:
            return False
        
        key = f"{data_type}:{symbol}"
        if key not in self._websocket_subscriptions:
            self._websocket_subscriptions[key] = []
        
        self._websocket_subscriptions[key].append(callback)
        
        # 启动WebSocket模拟
        if not self._websocket_running:
            self._start_websocket_simulation()
        
        self.logger.info("已订阅 %s:%s", data_type, symbol)
        return True
    
    def _start_websocket_simulation(self):
        """启动WebSocket模拟"""
        if self._websocket_task is None or self._websocket_task.done():
            self._websocket_running = True
            self._websocket_task = asyncio.create_task(self._websocket_simulation_loop())
    
    async def _websocket_simulation_loop(self):
        """WebSocket模拟循环"""
        while self._websocket_running:
            try:
                # 为每个订阅发送模拟数据
                for key, callbacks in self._websocket_subscriptions.items():
                    data_type, symbol = key.split(':', 1)
                    
                    # 生成模拟数据
                    if data_type == 'trades':
                        data = await self.get_trades(symbol, limit=1)
                        data = data[0] if data else None
                    elif data_type == 'orderbook':
                        data = await self.get_orderbook(symbol, limit=10)
                    elif data_type == 'ticker':
                        data = await self.get_ticker(symbol)
                    else:
                        continue
                    
                    # 调用回调函数
                    for callback in callbacks:
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback(data)
                            else:
                                callback(data)
                        except Exception as e:
                            self.logger.error("WebSocket回调错误: %s", str(e))
                
                await asyncio.sleep(self.mock_config.data_update_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("WebSocket模拟循环错误: %s", str(e))
                await asyncio.sleep(1)
    
    # 数据标准化方法
    def normalize_trade_data(self, raw_data: Dict[str, Any]) -> NormalizedTrade:
        """标准化交易数据"""
        # Mock实现 - 已经是标准化格式
        return raw_data
    
    def normalize_orderbook_data(self, raw_data: Dict[str, Any]) -> NormalizedOrderBook:
        """标准化订单簿数据"""
        return raw_data
    
    def normalize_ticker_data(self, raw_data: Dict[str, Any]) -> NormalizedTicker:
        """标准化行情数据"""
        return raw_data
    
    # 测试控制方法
    def force_error(self, method_name: str, error: Exception):
        """强制指定方法抛出错误"""
        self._forced_errors[method_name] = error
    
    def clear_forced_errors(self):
        """清除强制错误"""
        self._forced_errors.clear()
    
    def set_response_delay(self, method_name: str, delay_seconds: float):
        """设置响应延迟"""
        self._response_delays[method_name] = delay_seconds
    
    def update_price(self, symbol: str, new_price: float):
        """更新模拟价格"""
        self._current_prices[symbol] = new_price
    
    # 测试支持
    def enable_test_mode(self):
        """启用测试模式"""
        self.config['test_mode'] = True
        self.logger.info("测试模式已启用")
    
    def generate_test_data(self, data_type: str, count: int = 10) -> List[Any]:
        """生成测试数据"""
        # 子类实现具体的测试数据生成
        return []
    
    def validate_test_data(self, data: Any) -> bool:
        """验证测试数据"""
        return True
    
    async def _simulate_request_delay(self, method_name: str):
        """模拟请求延迟"""
        delay = self._response_delays.get(method_name)
        if delay is None and self.mock_config.simulate_latency:
            delay = random.uniform(
                self.mock_config.min_latency_ms / 1000,
                self.mock_config.max_latency_ms / 1000
            )
        
        if delay and delay > 0:
            await asyncio.sleep(delay)
    
    def _check_forced_error(self, method_name: str):
        """检查强制错误"""
        if method_name in self._forced_errors:
            raise self._forced_errors[method_name]
        
        if random.random() < self.mock_config.error_rate:
            raise Exception(f"模拟错误: {method_name}")
    
    def stop(self):
        """停止适配器"""
        self._websocket_running = False
        if self._websocket_task and not self._websocket_task.done():
            self._websocket_task.cancel()


class MockRateLimiter:
    """模拟费率限制器"""
    
    def __init__(self):
        self.requests_per_minute = 60
        self.current_requests = 0
        self.last_reset = time.time()
    
    def check(self) -> bool:
        current_time = time.time()
        if current_time - self.last_reset >= 60:
            self.current_requests = 0
            self.last_reset = current_time
        
        return self.current_requests < self.requests_per_minute
    
    def wait(self):
        # Mock实现 - 不实际等待
        pass


class MockCircuitBreaker:
    """模拟熔断器"""
    
    def __init__(self):
        self.is_open_state = False
        self.failure_count = 0
        self.last_failure_time = None
    
    def is_open(self) -> bool:
        return self.is_open_state
    
    def reset(self):
        self.is_open_state = False
        self.failure_count = 0
        self.last_failure_time = None


class MockMetrics:
    """模拟监控指标"""
    
    def __init__(self):
        self.requests = {}
        self.start_time = time.time()
    
    def record_request(self, method: str, success: bool):
        if method not in self.requests:
            self.requests[method] = {'total': 0, 'success': 0, 'failed': 0}
        
        self.requests[method]['total'] += 1
        if success:
            self.requests[method]['success'] += 1
        else:
            self.requests[method]['failed'] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            'uptime': time.time() - self.start_time,
            'requests': self.requests.copy()
        }


class MockPerformanceMetrics:
    """模拟性能指标"""
    
    def __init__(self):
        self.request_times = {}
    
    def record_request(self, method: str, duration: float):
        if method not in self.request_times:
            self.request_times[method] = []
        self.request_times[method].append(duration)
    
    def get_latency_stats(self) -> Dict[str, float]:
        return {'avg_latency': 0.1}
    
    def get_throughput_stats(self) -> Dict[str, float]:
        return {'requests_per_second': 10.0}
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            'latency': self.get_latency_stats(),
            'throughput': self.get_throughput_stats()
        }


class MockWebSocketManager:
    """模拟WebSocket管理器"""
    
    def __init__(self):
        self.subscriptions = {}
        self.running = False
    
    def start(self) -> bool:
        self.running = True
        return True
    
    def stop(self):
        self.running = False
    
    def subscribe(self, channel: str, callback: Callable):
        if channel not in self.subscriptions:
            self.subscriptions[channel] = []
        self.subscriptions[channel].append(callback)
    
    def unsubscribe(self, channel: str, callback: Callable):
        if channel in self.subscriptions:
            self.subscriptions[channel].remove(callback)
    
    def get_subscriptions(self) -> List[str]:
        return list(self.subscriptions.keys())
    
    def clear_subscriptions(self):
        self.subscriptions.clear()
    
    def is_healthy(self) -> bool:
        return self.running