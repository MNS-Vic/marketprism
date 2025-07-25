#!/usr/bin/env python3
"""
测试夹具配置文件

定义可被所有测试模块共享的夹具(fixtures)。
"""
import os
import sys
import pytest
from datetime import datetime, timezone
import tempfile
from unittest.mock import MagicMock

# 调整系统路径，便于导入被测模块
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


# 模拟配置夹具
@pytest.fixture(scope="session")
def mock_config():
    """
    提供模拟配置对象
    """
    return {
        "app": {
            "name": "marketprism",
            "version": "1.0.0",
            "debug": False
        },
        "database": {
            "host": "localhost",
            "port": 8123,
            "user": "default",
            "password": "password",
            "database": "market_data"
        },
        "exchanges": {
            "binance": {
                "api_key": "test_api_key",
                "api_secret": "test_api_secret",
                "symbols": ["BTC/USDT", "ETH/USDT"],
                "endpoints": {
                    "rest": "https://api.binance.com",
                    "ws": "wss://stream.binance.com:9443/ws"
                }
            }
        },
        "nats": {
            "host": "localhost",
            "port": 4222,
            "streams": {
                "market_data": {
                    "subjects": ["market.*.>"],
                    "retention": "limits",
                    "max_msgs": 1000000
                }
            }
        },
        "logging": {
            "level": "INFO",
            "file": "logs/app.log"
        }
    }


# 模拟时间范围夹具
@pytest.fixture
def time_range():
    """
    提供测试时间范围
    """
    now = datetime.now()
    start = now - datetime.timedelta(days=1)
    return start, now


# 临时目录夹具
@pytest.fixture
def temp_dir():
    """
    提供临时目录
    """
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    
    # 清理临时目录
    try:
        import shutil
        shutil.rmtree(temp_dir)
    except Exception as e:
        print(f"清理失败: {e}")


# 模拟数据库客户端夹具
@pytest.fixture
def mock_db_client():
    """
    提供模拟数据库客户端
    """
    client = MagicMock()
    
    # 模拟查询方法
    client.query = MagicMock(return_value=[])
    
    # 模拟插入方法
    client.insert = MagicMock(return_value={"inserted": 1})
    
    # 模拟批量插入方法
    client.insert_batch = MagicMock(return_value={"inserted": 10, "errors": 0})
    
    return client


# 模拟消息客户端夹具
@pytest.fixture
def mock_message_client():
    """
    提供模拟消息客户端
    """
    client = MagicMock()
    
    # 模拟发布方法
    client.publish = MagicMock(return_value=True)
    
    # 模拟订阅方法
    client.subscribe = MagicMock()
    
    # 添加JetStream属性
    js_client = MagicMock()
    js_client.publish = MagicMock(return_value={"seq": 1})
    js_client.pull = MagicMock(return_value=[])
    
    client.jetstream = js_client
    
    return client


# 添加pytest标记
def pytest_configure(config):
    """
    配置自定义pytest标记
    """
    config.addinivalue_line("markers", "unit: 单元测试")
    config.addinivalue_line("markers", "integration: 集成测试")
    config.addinivalue_line("markers", "performance: 性能测试")
    config.addinivalue_line("markers", "load_testing: 负载测试")