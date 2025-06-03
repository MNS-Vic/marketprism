"""
MarketPrism Collector Core Module

统一架构核心模块，提供：
- 配置管理 (Week 1 ✅)
- 监控指标 (Week 2 🚀)
- 生命周期管理
- 服务总线
- 数据流管理
- 错误处理
"""

# 导入各个子模块
from . import config
from . import monitoring

__version__ = "1.1.0"  # Week 2 版本
__author__ = "MarketPrism Team"

__all__ = [
    'config',
    'monitoring'
]