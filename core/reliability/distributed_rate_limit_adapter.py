"""
MarketPrism 分布式速率限制适配器

将分布式速率限制协调器集成到现有的MarketPrism系统中，
提供向后兼容性和平滑的迁移路径。

主要功能：
1. 适配现有的速率限制接口
2. 提供配置管理
3. 监控集成
4. 故障降级机制
5. 性能优化
"""

import asyncio
import os
import yaml
import logging
from typing import Dict, Any, Optional, Union, List
from dataclasses import dataclass
from pathlib import Path
import time

from .distributed_rate_limit_coordinator import (
    DistributedRateLimitCoordinator, 
    ExchangeType, 
    RequestType,
    RateLimitRequest,
    ExchangeRateLimit,
    create_redis_coordinator,
    create_memory_coordinator
)
from .rate_limit_manager import ExchangeRateLimitManager, GlobalRateLimitManager, RequestPriority
from ..monitoring.monitoring_system import MonitoringSystem

logger = logging.getLogger(__name__)


@dataclass
class DistributedRateLimitConfig:
    """分布式速率限制配置"""
    enabled: bool = True
    storage_type: str = "redis"
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 2
    redis_password: str = ""
    fallback_to_memory: bool = True
    service_name: str = "marketprism_service"
    priority: int = 1
    heartbeat_interval: float = 30.0
    config_file: Optional[str] = None
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'DistributedRateLimitConfig':
        """从字典创建配置"""
        storage_config = config_dict.get('storage', {})
        redis_config = storage_config.get('redis', {})
        clients_config = config_dict.get('clients', {})
        
        return cls(
            enabled=config_dict.get('enabled', True),
            storage_type=storage_config.get('type', 'redis'),
            redis_host=redis_config.get('host', 'localhost'),
            redis_port=redis_config.get('port', 6379),
            redis_db=redis_config.get('db', 2),
            redis_password=redis_config.get('password', ''),
            fallback_to_memory=redis_config.get('fallback_to_memory', True),
            service_name=config_dict.get('service_name', 'marketprism_service'),
            priority=clients_config.get('default_priority', 1),
            heartbeat_interval=clients_config.get('heartbeat', {}).get('interval_seconds', 30.0)
        )
    
    @classmethod
    def from_yaml_file(cls, file_path: str) -> 'DistributedRateLimitConfig':
        """从YAML文件加载配置"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                config_dict = yaml.safe_load(f)
            return cls.from_dict(config_dict)
        except Exception as e:
            logger.error(f"加载配置文件失败: {file_path}, 错误: {e}")
            return cls()  # 返回默认配置


class DistributedRateLimitAdapter:
    """分布式速率限制适配器"""
    
    def __init__(self, config: Optional[DistributedRateLimitConfig] = None, monitoring: Optional[MonitoringSystem] = None):
        """
        初始化适配器
        
        Args:
            config: 配置对象
            monitoring: 监控系统
        """
        self.config = config or self._load_default_config()
        self.monitoring = monitoring
        self.coordinator: Optional[DistributedRateLimitCoordinator] = None
        self.fallback_manager: Optional[GlobalRateLimitManager] = None
        self.is_initialized = False
        self.use_distributed = False
        
        # 统计数据
        self.stats = {
            'total_requests': 0,
            'distributed_requests': 0,
            'fallback_requests': 0,
            'granted_requests': 0,
            'denied_requests': 0,
            'initialization_time': 0,
            'last_heartbeat': 0
        }
        
        logger.info(f"分布式速率限制适配器已创建，配置: {self.config}")
    
    def _load_default_config(self) -> DistributedRateLimitConfig:
        """加载默认配置"""
        # 尝试从环境变量或配置文件加载
        config_file = os.getenv('MARKETPRISM_RATE_LIMIT_CONFIG')
        if not config_file:
            # 默认配置文件路径
            config_file = os.path.join(
                os.path.dirname(__file__), 
                '../../config/core/distributed_rate_limit_config.yaml'
            )
        
        if os.path.exists(config_file):
            return DistributedRateLimitConfig.from_yaml_file(config_file)
        else:
            logger.warning(f"配置文件不存在: {config_file}, 使用默认配置")
            return DistributedRateLimitConfig()
    
    async def initialize(self) -> bool:
        """初始化适配器"""
        if self.is_initialized:
            return True
        
        start_time = time.time()
        
        try:
            if self.config.enabled:
                # 尝试初始化分布式协调器
                success = await self._initialize_distributed_coordinator()
                if success:
                    self.use_distributed = True
                    logger.info("分布式速率限制协调器初始化成功")
                else:
                    logger.warning("分布式速率限制协调器初始化失败，使用本地降级")
            
            # 初始化降级管理器
            await self._initialize_fallback_manager()
            
            self.is_initialized = True
            self.stats['initialization_time'] = time.time() - start_time
            
            # 启动心跳任务
            if self.use_distributed and self.coordinator:
                asyncio.create_task(self._heartbeat_task())
            
            logger.info(f"速率限制适配器初始化完成，模式: {'分布式' if self.use_distributed else '本地'}")
            return True
            
        except Exception as e:
            logger.error(f"速率限制适配器初始化失败: {e}")
            return False
    
    async def _initialize_distributed_coordinator(self) -> bool:
        """初始化分布式协调器"""
        try:
            if self.config.storage_type == "redis":
                self.coordinator = await create_redis_coordinator(
                    redis_host=self.config.redis_host,
                    redis_port=self.config.redis_port,
                    redis_db=self.config.redis_db
                )
            else:
                self.coordinator = await create_memory_coordinator()
            
            # 注册客户端
            await self.coordinator.register_client(
                service_name=self.config.service_name,
                priority=self.config.priority,
                metadata={
                    'adapter_version': '1.0.0',
                    'process_id': os.getpid(),
                    'start_time': time.time()
                }
            )
            
            return True
            
        except Exception as e:
            logger.error(f"分布式协调器初始化失败: {e}")
            if self.config.fallback_to_memory:
                try:
                    self.coordinator = await create_memory_coordinator()
                    await self.coordinator.register_client(
                        service_name=self.config.service_name,
                        priority=self.config.priority
                    )
                    logger.info("已降级到内存协调器")
                    return True
                except Exception as e2:
                    logger.error(f"内存协调器初始化也失败: {e2}")
            return False
    
    async def _initialize_fallback_manager(self) -> bool:
        """初始化降级管理器"""
        try:
            self.fallback_manager = GlobalRateLimitManager()
            return True
        except Exception as e:
            logger.error(f"降级管理器初始化失败: {e}")
            return False
    
    async def _heartbeat_task(self):
        """心跳任务"""
        while self.is_initialized and self.coordinator:
            try:
                await asyncio.sleep(self.config.heartbeat_interval)
                success = await self.coordinator.heartbeat()
                if success:
                    self.stats['last_heartbeat'] = time.time()
                else:
                    logger.warning("心跳发送失败")
            except Exception as e:
                logger.error(f"心跳任务错误: {e}")
                break
    
    async def acquire_permit(
        self, 
        exchange: Union[str, ExchangeType],
        request_type: Union[str, RequestType] = RequestType.REST_PUBLIC,
        endpoint: Optional[str] = None,
        weight: int = 1,
        priority: RequestPriority = RequestPriority.MEDIUM
    ) -> Dict[str, Any]:
        """
        获取API请求许可
        
        这是主要的API接口，兼容现有的速率限制管理器接口
        """
        if not self.is_initialized:
            await self.initialize()
        
        self.stats['total_requests'] += 1
        
        # 标准化参数
        if isinstance(exchange, str):
            try:
                exchange = ExchangeType(exchange.lower())
            except ValueError:
                return self._create_error_response(f"不支持的交易所: {exchange}")
        
        if isinstance(request_type, str):
            try:
                request_type = RequestType(request_type.lower())
            except ValueError:
                request_type = RequestType.REST_PUBLIC
        
        # 尝试使用分布式协调器
        if self.use_distributed and self.coordinator:
            try:
                request = RateLimitRequest(
                    client_id=self.coordinator.client_id,
                    exchange=exchange,
                    request_type=request_type,
                    endpoint=endpoint,
                    weight=weight,
                    priority=self._convert_priority(priority)
                )
                
                response = await self.coordinator.acquire_permit(request)
                self.stats['distributed_requests'] += 1
                
                if response.granted:
                    self.stats['granted_requests'] += 1
                else:
                    self.stats['denied_requests'] += 1
                
                # 记录监控指标
                if self.monitoring:
                    self.monitoring.collect_metric(
                        "rate_limit_requests_total",
                        1,
                        labels={
                            "exchange": exchange.value,
                            "request_type": request_type.value,
                            "granted": str(response.granted),
                            "mode": "distributed"
                        }
                    )
                
                return {
                    'granted': response.granted,
                    'exchange': exchange.value,
                    'request_type': request_type.value,
                    'weight': weight,
                    'endpoint': endpoint,
                    'wait_time': response.wait_time,
                    'remaining_quota': response.remaining_quota,
                    'total_quota': response.total_quota,
                    'reason': response.reason,
                    'timestamp': response.timestamp,
                    'mode': 'distributed',
                    'client_id': response.client_id,
                    'request_id': response.request_id
                }
                
            except Exception as e:
                logger.error(f"分布式速率限制请求失败: {e}")
                # 降级到本地管理器
                return await self._fallback_acquire_permit(exchange, request_type, endpoint, weight, priority)
        
        # 使用本地降级管理器
        return await self._fallback_acquire_permit(exchange, request_type, endpoint, weight, priority)
    
    async def _fallback_acquire_permit(
        self, 
        exchange: ExchangeType,
        request_type: RequestType,
        endpoint: Optional[str],
        weight: int,
        priority: RequestPriority
    ) -> Dict[str, Any]:
        """使用降级管理器获取许可"""
        if not self.fallback_manager:
            return self._create_error_response("降级管理器未初始化")
        
        try:
            self.stats['fallback_requests'] += 1
            
            result = await self.fallback_manager.acquire_permit(
                exchange=exchange,
                request_type=request_type,
                endpoint=endpoint,
                priority=priority
            )
            
            if result.get('granted', False):
                self.stats['granted_requests'] += 1
            else:
                self.stats['denied_requests'] += 1
            
            # 记录监控指标
            if self.monitoring:
                self.monitoring.collect_metric(
                    "rate_limit_requests_total",
                    1,
                    labels={
                        "exchange": exchange.value,
                        "request_type": request_type.value,
                        "granted": str(result.get('granted', False)),
                        "mode": "fallback"
                    }
                )
            
            result['mode'] = 'fallback'
            return result
            
        except Exception as e:
            logger.error(f"降级管理器请求失败: {e}")
            return self._create_error_response(f"速率限制请求失败: {e}")
    
    def _convert_priority(self, priority: RequestPriority) -> int:
        """转换优先级格式"""
        priority_map = {
            RequestPriority.LOW: 1,
            RequestPriority.MEDIUM: 3,
            RequestPriority.HIGH: 5,
            RequestPriority.CRITICAL: 10
        }
        return priority_map.get(priority, 3)
    
    def _create_error_response(self, reason: str) -> Dict[str, Any]:
        """创建错误响应"""
        return {
            'granted': False,
            'reason': reason,
            'timestamp': time.time(),
            'mode': 'error'
        }
    
    async def get_status(self) -> Dict[str, Any]:
        """获取适配器状态"""
        status = {
            'adapter_status': {
                'initialized': self.is_initialized,
                'mode': 'distributed' if self.use_distributed else 'fallback',
                'config': {
                    'enabled': self.config.enabled,
                    'storage_type': self.config.storage_type,
                    'service_name': self.config.service_name,
                    'priority': self.config.priority
                },
                'statistics': self.stats.copy()
            }
        }
        
        # 添加协调器状态
        if self.use_distributed and self.coordinator:
            try:
                coordinator_status = await self.coordinator.get_system_status()
                status['coordinator_status'] = coordinator_status
            except Exception as e:
                status['coordinator_error'] = str(e)
        
        # 添加降级管理器状态
        if self.fallback_manager:
            try:
                # 这里可以添加降级管理器的状态信息
                status['fallback_status'] = {
                    'available': True,
                    'type': 'GlobalRateLimitManager'
                }
            except Exception as e:
                status['fallback_error'] = str(e)
        
        return status
    
    async def close(self):
        """关闭适配器"""
        self.is_initialized = False
        
        # 关闭协调器
        if self.coordinator:
            try:
                # 这里可以添加协调器的清理逻辑
                pass
            except Exception as e:
                logger.error(f"关闭协调器时出错: {e}")
        
        logger.info("速率限制适配器已关闭")


# 全局适配器实例
_global_adapter: Optional[DistributedRateLimitAdapter] = None


async def get_global_adapter() -> DistributedRateLimitAdapter:
    """获取全局适配器实例"""
    global _global_adapter
    if _global_adapter is None:
        _global_adapter = DistributedRateLimitAdapter()
        await _global_adapter.initialize()
    return _global_adapter


async def set_global_adapter(adapter: DistributedRateLimitAdapter):
    """设置全局适配器实例"""
    global _global_adapter
    _global_adapter = adapter


# 便利API函数（兼容现有接口）
async def acquire_api_permit(
    exchange: str, 
    request_type: str = "rest_public",
    endpoint: Optional[str] = None,
    weight: int = 1,
    priority: str = "medium"
) -> bool:
    """
    便利函数：获取API请求许可
    
    兼容现有的API接口
    """
    adapter = await get_global_adapter()
    
    # 转换优先级
    priority_map = {
        "low": RequestPriority.LOW,
        "medium": RequestPriority.MEDIUM,
        "high": RequestPriority.HIGH,
        "critical": RequestPriority.CRITICAL
    }
    request_priority = priority_map.get(priority.lower(), RequestPriority.MEDIUM)
    
    result = await adapter.acquire_permit(
        exchange=exchange,
        request_type=request_type,
        endpoint=endpoint,
        weight=weight,
        priority=request_priority
    )
    
    return result.get('granted', False)


async def get_rate_limit_status() -> Dict[str, Any]:
    """便利函数：获取速率限制状态"""
    adapter = await get_global_adapter()
    return await adapter.get_status()


# 配置管理函数
def configure_distributed_rate_limit(
    enabled: bool = True,
    redis_host: str = "localhost",
    redis_port: int = 6379,
    redis_db: int = 2,
    service_name: str = "marketprism_service",
    priority: int = 1,
    config_file: Optional[str] = None
) -> DistributedRateLimitConfig:
    """配置分布式速率限制"""
    if config_file:
        return DistributedRateLimitConfig.from_yaml_file(config_file)
    else:
        return DistributedRateLimitConfig(
            enabled=enabled,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            service_name=service_name,
            priority=priority
        )


# 装饰器：为函数添加速率限制
def rate_limited(exchange: str, request_type: str = "rest_public", weight: int = 1):
    """装饰器：为函数添加速率限制"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # 获取许可
            permitted = await acquire_api_permit(exchange, request_type, weight=weight)
            if not permitted:
                raise Exception(f"Rate limit exceeded for {exchange} {request_type}")
            
            # 执行原函数
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


if __name__ == "__main__":
    # 示例用法
    async def example_usage():
        # 创建适配器
        config = DistributedRateLimitConfig(
            enabled=True,
            storage_type="redis",
            service_name="example_service",
            priority=5
        )
        
        adapter = DistributedRateLimitAdapter(config)
        await adapter.initialize()
        
        # 获取许可
        result = await adapter.acquire_permit("binance", "rest_public", weight=1)
        print(f"Request permitted: {result['granted']}")
        
        # 获取状态
        status = await adapter.get_status()
        print(f"System status: {status}")
        
        # 关闭适配器
        await adapter.close()
    
    # 运行示例
    asyncio.run(example_usage())