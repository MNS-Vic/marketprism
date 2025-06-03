"""
监控模块单元测试

包含统一监控指标系统的全面测试：
- 统一指标管理器测试
- 指标导出器测试  
- 指标聚合测试
- 性能测试
- 集成测试
"""

# 导入测试模块使其可被pytest发现
from . import test_unified_metrics_manager
from . import test_exporters
from . import test_metric_aggregation

__all__ = [
    'test_unified_metrics_manager',
    'test_exporters', 
    'test_metric_aggregation'
]