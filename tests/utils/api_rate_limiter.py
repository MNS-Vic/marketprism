"""
API频率限制工具 - 专为CI/CD环境设计
确保在测试中安全使用真实交易所API，避免触发限流或封禁
"""

import time
import asyncio
import threading
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass
from collections import defaultdict, deque
import logging
import os

logger = logging.getLogger(__name__)

@dataclass
class RateLimitConfig:
    """频率限制配置"""
    requests_per_second: float = 1.0  # 每秒请求数
    requests_per_minute: int = 30      # 每分钟请求数
    requests_per_hour: int = 1000      # 每小时请求数
    burst_size: int = 5                # 突发请求数量
    cooldown_seconds: float = 1.0      # 冷却时间

class APIRateLimiter:
    """API频率限制器"""
    
    def __init__(self):
        self._locks = defaultdict(threading.Lock)
        self._request_history = defaultdict(lambda: deque())
        self._last_request_time = defaultdict(float)
        
        # 预定义的交易所限制配置
        self._exchange_configs = {
            'binance': RateLimitConfig(
                requests_per_second=0.5,  # 保守设置
                requests_per_minute=20,
                requests_per_hour=800,
                burst_size=3,
                cooldown_seconds=2.0
            ),
            'okx': RateLimitConfig(
                requests_per_second=0.4,
                requests_per_minute=15,
                requests_per_hour=600,
                burst_size=2,
                cooldown_seconds=2.5
            ),
            'deribit': RateLimitConfig(
                requests_per_second=0.3,
                requests_per_minute=10,
                requests_per_hour=400,
                burst_size=2,
                cooldown_seconds=3.0
            ),
            'default': RateLimitConfig(
                requests_per_second=0.2,
                requests_per_minute=8,
                requests_per_hour=200,
                burst_size=1,
                cooldown_seconds=5.0
            )
        }
        
        # CI环境下更严格的限制
        if os.getenv('CI') or os.getenv('GITHUB_ACTIONS'):
            self._apply_ci_restrictions()
    
    def _apply_ci_restrictions(self):
        """在CI环境中应用更严格的限制"""
        logger.info("检测到CI环境，应用严格的API频率限制")
        
        for exchange, config in self._exchange_configs.items():
            # CI环境下减少50%的请求频率
            config.requests_per_second *= 0.5
            config.requests_per_minute = int(config.requests_per_minute * 0.5)
            config.requests_per_hour = int(config.requests_per_hour * 0.5)
            config.burst_size = max(1, config.burst_size - 1)
            config.cooldown_seconds *= 1.5
    
    def get_config(self, exchange: str) -> RateLimitConfig:
        """获取交易所的频率限制配置"""
        return self._exchange_configs.get(exchange.lower(), self._exchange_configs['default'])
    
    def can_make_request(self, exchange: str, endpoint: str = 'default') -> bool:
        """检查是否可以发起请求"""
        key = f"{exchange}:{endpoint}"
        config = self.get_config(exchange)
        
        with self._locks[key]:
            now = time.time()
            history = self._request_history[key]
            
            # 清理过期的请求记录
            self._cleanup_history(history, now)
            
            # 检查各种限制
            if not self._check_per_second_limit(key, config, now):
                return False
            
            if not self._check_per_minute_limit(history, config, now):
                return False
            
            if not self._check_per_hour_limit(history, config, now):
                return False
            
            if not self._check_burst_limit(history, config, now):
                return False
            
            return True
    
    def record_request(self, exchange: str, endpoint: str = 'default'):
        """记录请求"""
        key = f"{exchange}:{endpoint}"
        
        with self._locks[key]:
            now = time.time()
            self._request_history[key].append(now)
            self._last_request_time[key] = now
    
    def wait_if_needed(self, exchange: str, endpoint: str = 'default') -> float:
        """如果需要，等待直到可以发起请求，返回等待时间"""
        if self.can_make_request(exchange, endpoint):
            return 0.0
        
        config = self.get_config(exchange)
        wait_time = config.cooldown_seconds
        
        logger.info(f"API频率限制触发，等待 {wait_time:.2f} 秒 - {exchange}:{endpoint}")
        time.sleep(wait_time)
        
        return wait_time
    
    async def async_wait_if_needed(self, exchange: str, endpoint: str = 'default') -> float:
        """异步版本的等待方法"""
        if self.can_make_request(exchange, endpoint):
            return 0.0
        
        config = self.get_config(exchange)
        wait_time = config.cooldown_seconds
        
        logger.info(f"API频率限制触发，异步等待 {wait_time:.2f} 秒 - {exchange}:{endpoint}")
        await asyncio.sleep(wait_time)
        
        return wait_time
    
    def _cleanup_history(self, history: deque, now: float):
        """清理过期的请求历史"""
        # 保留最近1小时的记录
        cutoff = now - 3600
        while history and history[0] < cutoff:
            history.popleft()
    
    def _check_per_second_limit(self, key: str, config: RateLimitConfig, now: float) -> bool:
        """检查每秒限制"""
        last_time = self._last_request_time.get(key, 0)
        min_interval = 1.0 / config.requests_per_second
        
        return (now - last_time) >= min_interval
    
    def _check_per_minute_limit(self, history: deque, config: RateLimitConfig, now: float) -> bool:
        """检查每分钟限制"""
        minute_ago = now - 60
        recent_requests = sum(1 for t in history if t > minute_ago)
        
        return recent_requests < config.requests_per_minute
    
    def _check_per_hour_limit(self, history: deque, config: RateLimitConfig, now: float) -> bool:
        """检查每小时限制"""
        hour_ago = now - 3600
        recent_requests = sum(1 for t in history if t > hour_ago)
        
        return recent_requests < config.requests_per_hour
    
    def _check_burst_limit(self, history: deque, config: RateLimitConfig, now: float) -> bool:
        """检查突发限制"""
        burst_window = 10.0  # 10秒窗口
        window_start = now - burst_window
        burst_requests = sum(1 for t in history if t > window_start)
        
        return burst_requests < config.burst_size
    
    def get_stats(self, exchange: str, endpoint: str = 'default') -> Dict[str, Any]:
        """获取统计信息"""
        key = f"{exchange}:{endpoint}"
        config = self.get_config(exchange)
        
        with self._locks[key]:
            now = time.time()
            history = self._request_history[key]
            
            # 计算各时间窗口的请求数
            minute_ago = now - 60
            hour_ago = now - 3600
            
            requests_last_minute = sum(1 for t in history if t > minute_ago)
            requests_last_hour = sum(1 for t in history if t > hour_ago)
            
            last_request = self._last_request_time.get(key, 0)
            time_since_last = now - last_request if last_request > 0 else float('inf')
            
            return {
                'exchange': exchange,
                'endpoint': endpoint,
                'config': config,
                'requests_last_minute': requests_last_minute,
                'requests_last_hour': requests_last_hour,
                'time_since_last_request': time_since_last,
                'can_make_request': self.can_make_request(exchange, endpoint),
                'total_requests': len(history)
            }

# 全局实例
_rate_limiter = APIRateLimiter()

def rate_limited_request(exchange: str, endpoint: str = 'default'):
    """装饰器：为函数添加频率限制"""
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            wait_time = _rate_limiter.wait_if_needed(exchange, endpoint)
            try:
                result = func(*args, **kwargs)
                _rate_limiter.record_request(exchange, endpoint)
                return result
            except Exception as e:
                # 即使请求失败也记录，避免重试风暴
                _rate_limiter.record_request(exchange, endpoint)
                raise e
        
        async def async_wrapper(*args, **kwargs):
            wait_time = await _rate_limiter.async_wait_if_needed(exchange, endpoint)
            try:
                result = await func(*args, **kwargs)
                _rate_limiter.record_request(exchange, endpoint)
                return result
            except Exception as e:
                _rate_limiter.record_request(exchange, endpoint)
                raise e
        
        # 根据函数类型返回相应的包装器
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return wrapper
    
    return decorator

def get_rate_limiter() -> APIRateLimiter:
    """获取全局频率限制器实例"""
    return _rate_limiter

def reset_rate_limiter():
    """重置频率限制器（主要用于测试）"""
    global _rate_limiter
    _rate_limiter = APIRateLimiter()

# 便捷函数
def wait_for_api(exchange: str, endpoint: str = 'default') -> float:
    """等待API可用"""
    return _rate_limiter.wait_if_needed(exchange, endpoint)

async def async_wait_for_api(exchange: str, endpoint: str = 'default') -> float:
    """异步等待API可用"""
    return await _rate_limiter.async_wait_if_needed(exchange, endpoint)

def can_call_api(exchange: str, endpoint: str = 'default') -> bool:
    """检查是否可以调用API"""
    return _rate_limiter.can_make_request(exchange, endpoint)

def record_api_call(exchange: str, endpoint: str = 'default'):
    """记录API调用"""
    _rate_limiter.record_request(exchange, endpoint)

def get_api_stats(exchange: str, endpoint: str = 'default') -> Dict[str, Any]:
    """获取API统计信息"""
    return _rate_limiter.get_stats(exchange, endpoint)
