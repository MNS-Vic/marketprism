"""
统一可靠性管理器

整合了熔断器、限流器、重试处理、负载均衡等所有可靠性组件
提供统一的配置和管理接口
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

from .circuit_breaker import MarketPrismCircuitBreaker
from .rate_limiter import AdaptiveRateLimiter, RateLimitConfig
from .retry_handler import ExponentialBackoffRetry, RetryPolicy
from .redundancy_manager import ColdStorageMonitor, ColdStorageConfig

logger = logging.getLogger(__name__)


@dataclass
class UnifiedReliabilityConfig:
    """统一可靠性配置"""
    # 组件启用开关
    enable_circuit_breaker: bool = True
    enable_rate_limiter: bool = True
    enable_retry_handler: bool = True
    enable_cold_storage_monitor: bool = True
    
    # 监控配置
    health_check_interval: int = 30
    metrics_collection_interval: int = 60
    alert_cooldown: int = 300


class UnifiedReliabilityManager:
    """统一可靠性管理器"""
    
    def __init__(self, config: Optional[UnifiedReliabilityConfig] = None):
        self.config = config or UnifiedReliabilityConfig()
        self.components = {}
        self.is_running = False
        
        logger.info("统一可靠性管理器已初始化")
    
    async def start(self):
        """启动所有可靠性组件"""
        if self.is_running:
            return
        
        # 启动各个组件
        if self.config.enable_circuit_breaker:
            self.components['circuit_breaker'] = MarketPrismCircuitBreaker()
            await self.components['circuit_breaker'].start()
        
        if self.config.enable_rate_limiter:
            rate_config = RateLimitConfig()
            self.components['rate_limiter'] = AdaptiveRateLimiter("unified", rate_config)
            await self.components['rate_limiter'].start()
        
        if self.config.enable_retry_handler:
            retry_config = RetryPolicy()
            self.components['retry_handler'] = ExponentialBackoffRetry("unified", retry_config)
        
        if self.config.enable_cold_storage_monitor:
            cold_config = ColdStorageConfig()
            self.components['cold_storage_monitor'] = ColdStorageMonitor(cold_config)
            await self.components['cold_storage_monitor'].start()
        
        self.is_running = True
        logger.info("统一可靠性管理器已启动")
    
    async def stop(self):
        """停止所有可靠性组件"""
        self.is_running = False
        
        for name, component in self.components.items():
            try:
                if hasattr(component, 'stop'):
                    await component.stop()
                logger.info(f"已停止组件: {name}")
            except Exception as e:
                logger.error(f"停止组件失败: {name} - {e}")
        
        logger.info("统一可靠性管理器已停止")
    
    def get_comprehensive_status(self) -> Dict[str, Any]:
        """获取综合状态"""
        status = {
            "is_running": self.is_running,
            "components": {}
        }
        
        for name, component in self.components.items():
            try:
                if hasattr(component, 'get_status'):
                    status["components"][name] = component.get_status()
                else:
                    status["components"][name] = {"available": True}
            except Exception as e:
                status["components"][name] = {"error": str(e)}
        
        return status
