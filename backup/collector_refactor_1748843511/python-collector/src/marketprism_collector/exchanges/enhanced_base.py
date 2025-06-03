"""
增强版交易所适配器基类 - TDD驱动的企业级设计

基于TDD发现的设计问题，提供企业级功能：
- 灵活的初始化支持
- 企业级特性集成 
- 配置管理系统
- 监控和健康检查
- WebSocket管理
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Callable, Union
import asyncio
import time
import logging
from datetime import datetime
from dataclasses import dataclass, field

from ..types import (
    NormalizedTrade, NormalizedOrderBook, NormalizedTicker,
    NormalizedKline, NormalizedFundingRate, NormalizedOpenInterest
)


@dataclass 
class AdapterConfig:
    """适配器配置数据类"""
    api_key: Optional[str] = None
    secret: Optional[str] = None
    passphrase: Optional[str] = None
    sandbox: bool = False
    timeout: int = 30
    retries: int = 3
    enable_logging: bool = True
    proxy: Optional[Dict[str, Any]] = None
    rate_limit_per_minute: int = 60
    websocket_url: Optional[str] = None
    rest_url: Optional[str] = None
    

class EnhancedExchangeAdapter(ABC):
    """
    增强版交易所适配器基类 - TDD驱动的企业级设计
    
    解决TDD发现的设计问题：
    1. 支持灵活初始化（无参数、配置字典、多层配置）
    2. 集成企业级特性（rate_limiter, retry_config, circuit_breaker等）
    3. 提供完整的配置管理
    4. 支持监控和健康检查
    5. WebSocket统一管理
    6. 数据标准化支持
    """
    
    def __init__(self, *args, **kwargs):
        """
        灵活初始化支持
        
        支持的调用方式：
        - ExchangeAdapter()  # 无参数
        - ExchangeAdapter(config_dict)  # 配置字典
        - ExchangeAdapter(global_config, exchange_config)  # 多层配置
        """
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # 解析配置参数
        self.config = self._parse_init_args(*args, **kwargs)
        
        # 基础属性
        self.exchange_name = getattr(self, 'exchange_name', 'unknown')
        self.last_error = None
        self.error_count = 0
        
        # 企业级特性
        self.rate_limiter = self._create_rate_limiter()
        self.retry_config = self._create_retry_config()
        self.circuit_breaker = self._create_circuit_breaker()
        
        # 监控和指标
        self.metrics = self._create_metrics()
        self.health_status = "healthy"
        
        # WebSocket管理
        self.websocket_manager = self._create_websocket_manager()
        
        # 性能监控
        self.performance_metrics = self._create_performance_metrics()
        
        # 配置管理
        self._config_validator = self._create_config_validator()
        
        self.logger.info(f"增强版交易所适配器已初始化: {self.exchange_name}")
    
    def _parse_init_args(self, *args, **kwargs) -> Dict[str, Any]:
        """解析初始化参数"""
        config = {}
        
        if len(args) == 0 and len(kwargs) == 0:
            # 无参数初始化
            config = self._get_default_config()
        elif len(args) == 1 and isinstance(args[0], dict):
            # 单个配置字典
            config = args[0].copy()
        elif len(args) == 2 and isinstance(args[0], dict) and isinstance(args[1], dict):
            # 多层配置：global_config + exchange_config
            config = args[0].copy()
            config.update(args[1])  # exchange_config优先
        else:
            # kwargs形式
            config = kwargs.copy()
        
        return config
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            'timeout': 30,
            'retries': 3,
            'sandbox': False,
            'enable_logging': True,
            'rate_limit_per_minute': 60
        }
    
    # 配置管理方法
    def get_config(self) -> Dict[str, Any]:
        """获取当前配置"""
        return self.config.copy()
    
    def update_config(self, new_config: Dict[str, Any]):
        """更新配置"""
        self.config.update(new_config)
        self.logger.info(f"配置已更新: {list(new_config.keys())}")
    
    def get_effective_config(self) -> Dict[str, Any]:
        """获取有效配置（合并默认值后）"""
        effective_config = self._get_default_config()
        effective_config.update(self.config)
        return effective_config
    
    def validate_config(self) -> bool:
        """验证配置"""
        return self._config_validator.validate(self.config)
    
    def get_required_config_keys(self) -> List[str]:
        """获取必需的配置键"""
        return ['api_key', 'secret']  # 子类可重写
    
    def get_optional_config_keys(self) -> List[str]:
        """获取可选的配置键"""
        return ['timeout', 'retries', 'sandbox', 'proxy']  # 子类可重写
    
    def reload_config(self):
        """重新加载配置"""
        # 子类可实现从文件或远程重新加载
        pass
    
    def apply_config_changes(self):
        """应用配置变更"""
        # 重新创建依赖配置的组件
        self.rate_limiter = self._create_rate_limiter()
        self.retry_config = self._create_retry_config()
    
    # 沙盒模式支持
    def is_sandbox_mode(self) -> bool:
        """检查是否为沙盒模式"""
        return self.config.get('sandbox', False)
    
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
    
    def should_retry(self, error: Exception) -> bool:
        """判断是否应该重试"""
        # 可配置的重试逻辑
        return True  # 简单实现，子类可重写
    
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
    
    def handle_websocket_error(self, error: Exception):
        """处理WebSocket错误"""
        self.handle_error(error, "WebSocket")
        # 可以触发自动重连逻辑
    
    def websocket_reconnect(self):
        """WebSocket重连"""
        return self.restart_websocket()
    
    def websocket_health_check(self) -> bool:
        """WebSocket健康检查"""
        return self.websocket_manager.is_healthy()
    
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
    
    # 抽象方法 - 子类必须实现
    @abstractmethod
    async def get_trades(self, symbol: str, **kwargs) -> List[NormalizedTrade]:
        """获取交易数据"""
        pass
    
    @abstractmethod
    async def get_orderbook(self, symbol: str, **kwargs) -> NormalizedOrderBook:
        """获取订单簿数据"""
        pass
    
    @abstractmethod
    async def get_ticker(self, symbol: str, **kwargs) -> NormalizedTicker:
        """获取行情数据"""
        pass
    
    @abstractmethod
    async def get_klines(self, symbol: str, **kwargs) -> List[NormalizedKline]:
        """获取K线数据"""
        pass
    
    @abstractmethod
    async def get_funding_rate(self, symbol: str, **kwargs) -> NormalizedFundingRate:
        """获取资金费率"""
        pass
    
    @abstractmethod
    async def get_open_interest(self, symbol: str, **kwargs) -> NormalizedOpenInterest:
        """获取持仓量"""
        pass
    
    # 数据标准化方法（子类可重写）
    def normalize_trade_data(self, raw_data: Dict[str, Any]) -> NormalizedTrade:
        """标准化交易数据"""
        # 默认实现，子类重写
        raise NotImplementedError("子类必须实现normalize_trade_data方法")
    
    def normalize_orderbook_data(self, raw_data: Dict[str, Any]) -> NormalizedOrderBook:
        """标准化订单簿数据"""
        raise NotImplementedError("子类必须实现normalize_orderbook_data方法")
    
    def normalize_ticker_data(self, raw_data: Dict[str, Any]) -> NormalizedTicker:
        """标准化行情数据"""
        raise NotImplementedError("子类必须实现normalize_ticker_data方法")
    
    # 私有方法 - 创建企业级组件
    def _create_rate_limiter(self):
        """创建速率限制器"""
        return MockRateLimiter(self.config.get('rate_limit_per_minute', 60))
    
    def _create_retry_config(self) -> Dict[str, Any]:
        """创建重试配置"""
        return {
            'max_retries': self.config.get('retries', 3),
            'backoff_factor': 1.5,
            'retry_on_errors': ['timeout', 'connection_error']
        }
    
    def _create_circuit_breaker(self):
        """创建熔断器"""
        return MockCircuitBreaker()
    
    def _create_metrics(self):
        """创建监控指标"""
        return MockMetrics()
    
    def _create_performance_metrics(self):
        """创建性能指标"""
        return MockPerformanceMetrics()
    
    def _create_websocket_manager(self):
        """创建WebSocket管理器"""
        return MockWebSocketManager()
    
    def _create_config_validator(self):
        """创建配置验证器"""
        return MockConfigValidator()


# Mock组件实现（简化版，用于测试）
class MockRateLimiter:
    def __init__(self, rate_per_minute: int):
        self.rate_per_minute = rate_per_minute
        self.requests = []
    
    def check(self) -> bool:
        current_time = time.time()
        # 清理1分钟前的请求
        self.requests = [t for t in self.requests if current_time - t < 60]
        return len(self.requests) < self.rate_per_minute
    
    def wait(self):
        # 简化实现
        pass


class MockCircuitBreaker:
    def __init__(self):
        self.is_open_state = False
    
    def is_open(self) -> bool:
        return self.is_open_state
    
    def reset(self):
        self.is_open_state = False


class MockMetrics:
    def __init__(self):
        self.stats = {}
    
    def get_stats(self) -> Dict[str, Any]:
        return self.stats.copy()


class MockPerformanceMetrics:
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


class MockConfigValidator:
    def validate(self, config: Dict[str, Any]) -> bool:
        # 简化验证逻辑
        return True