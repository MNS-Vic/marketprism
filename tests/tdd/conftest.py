"""
pytest配置文件
定义TDD测试的fixtures和配置
"""

import pytest
import asyncio
import sys
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 异步测试支持
@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

# 测试标记
pytest_plugins = ["pytest_asyncio"]

# 自定义标记
def pytest_configure(config):
    """配置pytest标记"""
    config.addinivalue_line(
        "markers", "requires_service(name): 标记需要特定服务的测试"
    )
    config.addinivalue_line(
        "markers", "requires_real_network: 标记需要真实网络连接的测试"
    )
    config.addinivalue_line(
        "markers", "slow: 标记运行较慢的测试"
    )
    config.addinivalue_line(
        "markers", "integration: 标记集成测试"
    )

# 收集测试时的过滤
def pytest_collection_modifyitems(config, items):
    """修改测试收集"""
    for item in items:
        # 为异步测试添加标记
        if asyncio.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.asyncio)