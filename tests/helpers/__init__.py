# MarketPrism 测试辅助工具包
"""
测试辅助工具包，提供网络管理、服务管理、异步管理和类型处理功能
"""

from datetime import datetime, timezone
from .network_manager import NetworkManager, requires_network, requires_binance, requires_okx, requires_any_exchange
from .service_manager import ServiceManager, requires_monitoring, requires_nats, requires_clickhouse, requires_core_services
from .test_environment import Environment, test_env
from .async_manager import (
    AsyncTestManager, AsyncResourceTracker, 
    async_test, async_test_with_cleanup,
    safe_create_task, safe_create_session
)
from .type_utils import (
    FinancialTypeConverter, TestDataNormalizer, TestAssertionHelper,
    FinancialTestDataFactory, serialize_for_test, deserialize_from_test,
    compare_financial_values, normalize_numeric
)

__all__ = [
    # Core managers
    'NetworkManager',
    'ServiceManager', 
    'Environment',
    'test_env',
    
    # Network decorators
    'requires_network',
    'requires_binance',
    'requires_okx',
    'requires_any_exchange',
    
    # Service decorators
    'requires_monitoring',
    'requires_nats', 
    'requires_clickhouse',
    'requires_core_services',
    
    # Async management
    'AsyncTestManager',
    'AsyncResourceTracker',
    'async_test',
    'async_test_with_cleanup',
    'safe_create_task',
    'safe_create_session',
    
    # Type utilities
    'FinancialTypeConverter',
    'TestDataNormalizer',
    'TestAssertionHelper',
    'FinancialTestDataFactory',
    'serialize_for_test',
    'deserialize_from_test',
    'compare_financial_values',
    'normalize_numeric'
] 