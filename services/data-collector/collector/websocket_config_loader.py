"""
WebSocket配置加载器 - 为各交易所提供差异化WebSocket配置

基于2025年最新API文档，为每个交易所提供专门的WebSocket配置管理
"""

import yaml
import os
from pathlib import Path
from typing import Dict, Any, Optional
import structlog
from dataclasses import dataclass


@dataclass
class WebSocketConfig:
    """WebSocket配置数据类"""
    exchange: str
    connection: Dict[str, Any]
    ping_pong: Dict[str, Any]
    maintenance: Dict[str, Any]
    reconnect: Dict[str, Any]
    subscription: Dict[str, Any]
    streams: Dict[str, Any]
    error_handling: Dict[str, Any]
    performance: Dict[str, Any]
    monitoring: Dict[str, Any]
    
    # 交易所特定配置
    authentication: Optional[Dict[str, Any]] = None
    websocket_api: Optional[Dict[str, Any]] = None
    heartbeat: Optional[Dict[str, Any]] = None
    jsonrpc: Optional[Dict[str, Any]] = None
    aiohttp_config: Optional[Dict[str, Any]] = None
    proxy: Optional[Dict[str, Any]] = None


class WebSocketConfigLoader:
    """WebSocket配置加载器 - 使用统一配置文件"""

    def __init__(self, config_file: Optional[str] = None):
        self.logger = structlog.get_logger(__name__)

        # 🔧 配置统一：使用统一主配置文件
        if config_file:
            self.config_file = Path(config_file)
        else:
            project_root = Path(__file__).parent.parent.parent.parent
            # 🎯 关键修改：使用统一主配置文件
            self.config_file = project_root / "config" / "collector" / "unified_data_collection.yaml"

        self.logger.info("WebSocket配置加载器初始化（统一配置）", config_file=str(self.config_file))

        # 配置缓存
        self._config_cache: Dict[str, WebSocketConfig] = {}
        self._unified_config: Optional[Dict[str, Any]] = None
        
    def _load_unified_config(self):
        """加载统一配置文件"""
        if self._unified_config is None:
            if not self.config_file.exists():
                raise FileNotFoundError(f"统一配置文件不存在: {self.config_file}")

            with open(self.config_file, 'r', encoding='utf-8') as f:
                self._unified_config = yaml.safe_load(f)

    def load_config(self, exchange: str) -> WebSocketConfig:
        """从统一配置文件加载指定交易所的WebSocket配置"""
        try:
            # 检查缓存
            if exchange in self._config_cache:
                return self._config_cache[exchange]

            # 加载统一配置
            self._load_unified_config()

            # 从统一配置中提取WebSocket配置
            exchanges_config = self._unified_config.get('exchanges', {})

            # 查找匹配的交易所配置
            exchange_config = None
            for ex_name, ex_config in exchanges_config.items():
                if ex_name.startswith(exchange) or ex_config.get('name') == exchange:
                    exchange_config = ex_config
                    break

            if not exchange_config:
                raise ValueError(f"统一配置文件中未找到 {exchange} 的配置")
            
            # 创建WebSocketConfig对象
            config = WebSocketConfig(
                exchange=exchange,
                connection=exchange_config.get('connection', {}),
                ping_pong=exchange_config.get('ping_pong', {}),
                maintenance=exchange_config.get('maintenance', {}),
                reconnect=exchange_config.get('reconnect', {}),
                subscription=exchange_config.get('subscription', {}),
                streams=exchange_config.get('streams', {}),
                error_handling=exchange_config.get('error_handling', {}),
                performance=exchange_config.get('performance', {}),
                monitoring=exchange_config.get('monitoring', {}),
                authentication=exchange_config.get('authentication'),
                websocket_api=exchange_config.get('websocket_api'),
                heartbeat=exchange_config.get('heartbeat'),
                jsonrpc=exchange_config.get('jsonrpc'),
                aiohttp_config=exchange_config.get('aiohttp_config'),
                proxy=exchange_config.get('proxy')
            )
            
            # 缓存配置
            self._config_cache[exchange] = config
            
            self.logger.info("WebSocket配置从统一配置文件加载成功",
                           exchange=exchange,
                           config_file=str(self.config_file))
            
            return config
            
        except Exception as e:
            self.logger.error("WebSocket配置加载失败", 
                            exchange=exchange, 
                            error=str(e),
                            exc_info=True)
            raise
    
    def get_ping_config(self, exchange: str) -> Dict[str, Any]:
        """获取交易所特定的ping配置"""
        config = self.load_config(exchange)
        return config.ping_pong
    
    def get_reconnect_config(self, exchange: str) -> Dict[str, Any]:
        """获取交易所特定的重连配置"""
        config = self.load_config(exchange)
        return config.reconnect
    
    def get_subscription_config(self, exchange: str) -> Dict[str, Any]:
        """获取交易所特定的订阅配置"""
        config = self.load_config(exchange)
        return config.subscription
    
    def get_authentication_config(self, exchange: str) -> Optional[Dict[str, Any]]:
        """获取交易所特定的认证配置"""
        config = self.load_config(exchange)
        return config.authentication
    
    def get_performance_config(self, exchange: str) -> Dict[str, Any]:
        """获取交易所特定的性能配置"""
        config = self.load_config(exchange)
        return config.performance
    
    def is_ping_enabled(self, exchange: str) -> bool:
        """检查交易所是否启用ping/pong"""
        ping_config = self.get_ping_config(exchange)
        return ping_config.get('enabled', False)
    
    def get_ping_interval(self, exchange: str) -> int:
        """获取交易所的ping间隔"""
        ping_config = self.get_ping_config(exchange)
        return ping_config.get('interval', 30)
    
    def get_ping_format(self, exchange: str) -> str:
        """获取交易所的ping格式"""
        ping_config = self.get_ping_config(exchange)
        return ping_config.get('format', 'json')
    
    def get_ping_message(self, exchange: str) -> Any:
        """获取交易所的ping消息"""
        ping_config = self.get_ping_config(exchange)
        return ping_config.get('ping_message', 'ping')
    
    def get_max_reconnect_attempts(self, exchange: str) -> int:
        """获取最大重连尝试次数"""
        reconnect_config = self.get_reconnect_config(exchange)
        return reconnect_config.get('max_attempts', 5)
    
    def get_reconnect_delay(self, exchange: str) -> int:
        """获取初始重连延迟"""
        reconnect_config = self.get_reconnect_config(exchange)
        return reconnect_config.get('initial_delay', 1)
    
    def clear_cache(self):
        """清空配置缓存"""
        self._config_cache.clear()
        self.logger.info("WebSocket配置缓存已清空")
    
    def reload_config(self, exchange: str) -> WebSocketConfig:
        """重新加载指定交易所的配置"""
        if exchange in self._config_cache:
            del self._config_cache[exchange]
        return self.load_config(exchange)
    
    def get_supported_exchanges(self) -> list:
        """从统一配置文件获取支持的交易所列表"""
        try:
            self._load_unified_config()
            exchanges_config = self._unified_config.get('exchanges', {})

            # 从统一配置中提取交易所名称
            exchanges = []
            for exchange_key in exchanges_config.keys():
                # 提取基础交易所名称（去掉_spot, _derivatives等后缀）
                base_name = exchange_key.split('_')[0]
                if base_name not in exchanges:
                    exchanges.append(base_name)

            return exchanges
        except Exception as e:
            self.logger.error("从统一配置获取支持的交易所列表失败", error=str(e))
            return ['binance', 'okx']  # 默认支持的交易所


# 全局配置加载器实例
_config_loader = None

def get_websocket_config_loader() -> WebSocketConfigLoader:
    """获取全局WebSocket配置加载器实例"""
    global _config_loader
    if _config_loader is None:
        _config_loader = WebSocketConfigLoader()
    return _config_loader
