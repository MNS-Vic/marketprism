"""
🌟 MarketPrism API网关生态系统

企业级API网关生态系统，整合所有核心组件：
- 🔗 API网关核心
- 🔍 服务发现
- ⚙️ 中间件系统  
- 🛡️ 安全系统
- 📊 监控系统
- ⚡ 性能优化
"""

from .ecosystem_manager import (
    APIGatewayEcosystem,
    EcosystemConfig,
    ComponentStatus,
    EcosystemHealth
)

from .control_plane import (
    ControlPlane,
    ManagementAPI,
    ConfigurationManager,
    PluginManager
)

from .data_plane import (
    DataPlane,
    RequestPipeline,
    ResponsePipeline,
    TrafficManager
)

from .plugin_system import (
    Plugin,
    PluginBase,
    PluginRegistry,
    PluginLoader
)

__all__ = [
    # 核心生态系统
    'APIGatewayEcosystem',
    'EcosystemConfig', 
    'ComponentStatus',
    'EcosystemHealth',
    
    # 控制平面
    'ControlPlane',
    'ManagementAPI',
    'ConfigurationManager', 
    'PluginManager',
    
    # 数据平面
    'DataPlane',
    'RequestPipeline',
    'ResponsePipeline',
    'TrafficManager',
    
    # 插件系统
    'Plugin',
    'PluginBase',
    'PluginRegistry',
    'PluginLoader'
]

__version__ = "1.0.0"
__author__ = "MarketPrism Team"
__description__ = "Enterprise API Gateway Ecosystem"