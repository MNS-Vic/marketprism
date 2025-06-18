"""
MarketPrism 测试配置和全局Fixtures
提供统一的测试环境配置和通用测试工具
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, Any, AsyncGenerator, Generator
from unittest.mock import Mock, AsyncMock

import pytest
import yaml
from aiohttp import ClientSession
from aioresponses import aioresponses

# 添加项目路径到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "services" / "data-collector" / "src"))

# 设置测试环境变量
os.environ.setdefault("MARKETPRISM_ENV", "test")
os.environ.setdefault("MARKETPRISM_LOG_LEVEL", "DEBUG")
os.environ.setdefault("MARKETPRISM_TEST_MODE", "true")


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环用于整个测试会话"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir():
    """创建临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_config() -> Dict[str, Any]:
    """提供示例配置数据"""
    return {
        "app": {
            "name": "marketprism-test",
            "version": "1.0.0",
            "debug": True
        },
        "logging": {
            "level": "DEBUG",
            "format": "json"
        },
        "exchanges": {
            "binance": {
                "enabled": True,
                "api_key": "test_api_key",
                "api_secret": "test_api_secret",
                "testnet": True
            },
            "okx": {
                "enabled": True,
                "api_key": "test_okx_key",
                "api_secret": "test_okx_secret",
                "passphrase": "test_passphrase"
            }
        },
        "storage": {
            "clickhouse": {
                "host": "localhost",
                "port": 8123,
                "database": "test_marketprism"
            }
        },
        "nats": {
            "servers": ["nats://localhost:4222"],
            "cluster_id": "test-cluster"
        }
    }


@pytest.fixture
def config_file(temp_dir, sample_config):
    """创建临时配置文件"""
    config_path = temp_dir / "test_config.yaml"
    with open(config_path, 'w') as f:
        yaml.dump(sample_config, f)
    return config_path


@pytest.fixture
def mock_aiohttp():
    """Mock aiohttp请求"""
    with aioresponses() as m:
        yield m


@pytest.fixture
async def aiohttp_session():
    """提供aiohttp会话"""
    async with ClientSession() as session:
        yield session


@pytest.fixture
def mock_clickhouse_client():
    """Mock ClickHouse客户端"""
    mock_client = AsyncMock()
    mock_client.execute = AsyncMock(return_value=[])
    mock_client.fetch = AsyncMock(return_value=[])
    mock_client.fetchrow = AsyncMock(return_value=None)
    mock_client.close = AsyncMock()
    return mock_client


@pytest.fixture
def mock_nats_client():
    """Mock NATS客户端"""
    mock_client = AsyncMock()
    mock_client.connect = AsyncMock()
    mock_client.publish = AsyncMock()
    mock_client.subscribe = AsyncMock()
    mock_client.close = AsyncMock()
    return mock_client


@pytest.fixture
def mock_redis_client():
    """Mock Redis客户端"""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=None)
    mock_client.set = AsyncMock(return_value=True)
    mock_client.delete = AsyncMock(return_value=1)
    mock_client.exists = AsyncMock(return_value=False)
    mock_client.close = AsyncMock()
    return mock_client


@pytest.fixture
def sample_trade_data():
    """提供示例交易数据"""
    return {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "price": 50000.0,
        "quantity": 0.1,
        "side": "buy",
        "timestamp": 1640995200000,
        "trade_id": "12345"
    }


@pytest.fixture
def sample_orderbook_data():
    """提供示例订单簿数据"""
    return {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "timestamp": 1640995200000,
        "bids": [
            [49950.0, 0.5],
            [49940.0, 1.0],
            [49930.0, 2.0]
        ],
        "asks": [
            [50050.0, 0.3],
            [50060.0, 0.8],
            [50070.0, 1.5]
        ]
    }


@pytest.fixture
def sample_ticker_data():
    """提供示例行情数据"""
    return {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "timestamp": 1640995200000,
        "open": 49000.0,
        "high": 51000.0,
        "low": 48500.0,
        "close": 50000.0,
        "volume": 1000.0,
        "quote_volume": 50000000.0
    }


@pytest.fixture
def mock_websocket():
    """Mock WebSocket连接"""
    mock_ws = AsyncMock()
    mock_ws.send_str = AsyncMock()
    mock_ws.receive_str = AsyncMock()
    mock_ws.close = AsyncMock()
    mock_ws.closed = False
    return mock_ws


@pytest.fixture
def mock_exchange_adapter():
    """Mock交易所适配器"""
    mock_adapter = AsyncMock()
    mock_adapter.connect = AsyncMock()
    mock_adapter.disconnect = AsyncMock()
    mock_adapter.subscribe_trades = AsyncMock()
    mock_adapter.subscribe_orderbook = AsyncMock()
    mock_adapter.subscribe_ticker = AsyncMock()
    mock_adapter.is_connected = True
    return mock_adapter


@pytest.fixture
def mock_metrics_collector():
    """Mock指标收集器"""
    mock_collector = Mock()
    mock_collector.increment = Mock()
    mock_collector.gauge = Mock()
    mock_collector.histogram = Mock()
    mock_collector.timer = Mock()
    return mock_collector


@pytest.fixture
def mock_logger():
    """Mock日志记录器"""
    mock_logger = Mock()
    mock_logger.debug = Mock()
    mock_logger.info = Mock()
    mock_logger.warning = Mock()
    mock_logger.error = Mock()
    mock_logger.critical = Mock()
    return mock_logger


@pytest.fixture
def mock_health_checker():
    """Mock健康检查器"""
    mock_checker = AsyncMock()
    mock_checker.check_health = AsyncMock(return_value={"status": "healthy"})
    mock_checker.get_status = AsyncMock(return_value="healthy")
    return mock_checker


@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch):
    """自动设置测试环境"""
    # 设置测试环境变量
    monkeypatch.setenv("MARKETPRISM_ENV", "test")
    monkeypatch.setenv("MARKETPRISM_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("MARKETPRISM_TEST_MODE", "true")
    
    # 禁用真实的外部连接
    monkeypatch.setenv("MARKETPRISM_DISABLE_EXTERNAL_CONNECTIONS", "true")


@pytest.fixture
def isolated_config():
    """提供隔离的配置环境"""
    original_config = {}
    
    def _set_config(key: str, value: Any):
        original_config[key] = value
    
    def _get_config(key: str, default: Any = None):
        return original_config.get(key, default)
    
    def _clear_config():
        original_config.clear()
    
    return {
        "set": _set_config,
        "get": _get_config,
        "clear": _clear_config
    }


# 测试标记定义
pytest_plugins = []

def pytest_configure(config):
    """配置pytest标记"""
    config.addinivalue_line(
        "markers", "unit: 单元测试标记"
    )
    config.addinivalue_line(
        "markers", "integration: 集成测试标记"
    )
    config.addinivalue_line(
        "markers", "e2e: 端到端测试标记"
    )
    config.addinivalue_line(
        "markers", "performance: 性能测试标记"
    )
    config.addinivalue_line(
        "markers", "slow: 慢速测试标记"
    )
    config.addinivalue_line(
        "markers", "real_api: 真实API测试标记"
    )


def pytest_collection_modifyitems(config, items):
    """修改测试收集项"""
    for item in items:
        # 为所有测试添加asyncio标记
        if "async" in item.name or "test_async" in item.name:
            item.add_marker(pytest.mark.asyncio)
        
        # 根据路径添加标记
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
        elif "performance" in str(item.fspath):
            item.add_marker(pytest.mark.performance)


@pytest.fixture(scope="session", autouse=True)
def setup_test_session():
    """设置测试会话"""
    print("\n🚀 开始MarketPrism TDD测试会话")
    yield
    print("\n✅ MarketPrism TDD测试会话完成")
