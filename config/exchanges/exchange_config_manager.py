"""
交易所配置管理器
基于官方文档的交易所特定配置加载和管理
"""

import os
import yaml
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class WebSocketConnectionConfig:
    """WebSocket连接配置"""
    base_urls: Dict[str, str]
    limits: Dict[str, int]
    parameters: Dict[str, Any]


@dataclass
class HeartbeatConfig:
    """心跳配置"""
    server_ping_interval_seconds: Optional[int] = None
    client_ping_interval_seconds: Optional[int] = None
    client_pong_timeout_seconds: Optional[int] = None
    server_pong_timeout_seconds: Optional[int] = None
    client_strategy: Dict[str, Any] = None
    monitoring: Dict[str, Any] = None


@dataclass
class OrderBookConfig:
    """订单簿配置"""
    maintenance_method: str
    official_method: Optional[Dict[str, Any]] = None
    standard_method: Optional[Dict[str, Any]] = None


@dataclass
class ExchangeWebSocketConfig:
    """交易所WebSocket配置"""
    exchange_name: str
    version: str
    connection: WebSocketConnectionConfig
    heartbeat: HeartbeatConfig
    orderbook: OrderBookConfig
    streams: Dict[str, Any]
    error_handling: Dict[str, Any]
    performance: Dict[str, Any]
    monitoring: Dict[str, Any]
    compatibility: Dict[str, Any]
    authentication: Optional[Dict[str, Any]] = None


class ExchangeConfigManager:
    """交易所配置管理器"""
    
    def __init__(self, config_dir: str = None):
        """
        初始化配置管理器
        
        Args:
            config_dir: 配置文件目录，默认为当前目录下的exchanges
        """
        if config_dir is None:
            config_dir = Path(__file__).parent
        
        self.config_dir = Path(config_dir)
        self._configs: Dict[str, ExchangeWebSocketConfig] = {}
        self._load_all_configs()
    
    def _load_all_configs(self):
        """加载所有交易所配置"""
        try:
            # 查找所有WebSocket配置文件
            websocket_config_files = list(self.config_dir.glob("*_websocket.yaml"))
            
            for config_file in websocket_config_files:
                try:
                    exchange_name = config_file.stem.replace("_websocket", "")
                    config = self._load_exchange_config(config_file)
                    self._configs[exchange_name] = config
                    logger.info(f"✅ 加载交易所配置成功: {exchange_name}")
                except Exception as e:
                    logger.error(f"❌ 加载交易所配置失败: {config_file}, 错误: {e}")
            
            logger.info(f"📋 总共加载了 {len(self._configs)} 个交易所配置")
            
        except Exception as e:
            logger.error(f"❌ 加载交易所配置目录失败: {e}")
    
    def _load_exchange_config(self, config_file: Path) -> ExchangeWebSocketConfig:
        """加载单个交易所配置"""
        with open(config_file, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        
        # 解析WebSocket连接配置
        websocket_config = config_data.get('websocket', {})
        connection_config = WebSocketConnectionConfig(
            base_urls=websocket_config.get('connection', {}).get('base_urls', {}),
            limits=websocket_config.get('connection', {}).get('limits', {}),
            parameters=websocket_config.get('connection', {}).get('parameters', {})
        )
        
        # 解析心跳配置
        heartbeat_data = websocket_config.get('heartbeat', {})
        heartbeat_config = HeartbeatConfig(
            server_ping_interval_seconds=heartbeat_data.get('server_ping_interval_seconds'),
            client_ping_interval_seconds=heartbeat_data.get('client_ping_interval_seconds'),
            client_pong_timeout_seconds=heartbeat_data.get('client_pong_timeout_seconds'),
            server_pong_timeout_seconds=heartbeat_data.get('server_pong_timeout_seconds'),
            client_strategy=heartbeat_data.get('client_strategy', {}),
            monitoring=heartbeat_data.get('monitoring', {})
        )
        
        # 解析订单簿配置
        orderbook_data = config_data.get('orderbook', {})
        orderbook_config = OrderBookConfig(
            maintenance_method=orderbook_data.get('maintenance_method', 'standard'),
            official_method=orderbook_data.get('official_method'),
            standard_method=orderbook_data.get('standard_method')
        )
        
        # 创建完整配置对象
        exchange_config = ExchangeWebSocketConfig(
            exchange_name=config_data.get('exchange_name'),
            version=config_data.get('version'),
            connection=connection_config,
            heartbeat=heartbeat_config,
            orderbook=orderbook_config,
            streams=config_data.get('streams', {}),
            error_handling=config_data.get('error_handling', {}),
            performance=config_data.get('performance', {}),
            monitoring=config_data.get('monitoring', {}),
            compatibility=config_data.get('compatibility', {}),
            authentication=config_data.get('authentication')
        )
        
        return exchange_config
    
    def get_config(self, exchange_name: str) -> Optional[ExchangeWebSocketConfig]:
        """
        获取指定交易所的配置
        
        Args:
            exchange_name: 交易所名称（如 'binance', 'okx'）
            
        Returns:
            交易所配置对象，如果不存在则返回None
        """
        return self._configs.get(exchange_name.lower())
    
    def get_all_exchanges(self) -> List[str]:
        """获取所有已配置的交易所名称"""
        return list(self._configs.keys())
    
    def is_exchange_supported(self, exchange_name: str) -> bool:
        """检查交易所是否已配置"""
        return exchange_name.lower() in self._configs
    
    def get_websocket_url(self, exchange_name: str, connection_type: str = "public") -> Optional[str]:
        """
        获取WebSocket连接URL
        
        Args:
            exchange_name: 交易所名称
            connection_type: 连接类型（如 'public', 'private', 'spot', 'futures'）
            
        Returns:
            WebSocket URL，如果不存在则返回None
        """
        config = self.get_config(exchange_name)
        if not config:
            return None
        
        return config.connection.base_urls.get(connection_type)
    
    def get_heartbeat_config(self, exchange_name: str) -> Optional[HeartbeatConfig]:
        """获取心跳配置"""
        config = self.get_config(exchange_name)
        return config.heartbeat if config else None
    
    def get_orderbook_config(self, exchange_name: str) -> Optional[OrderBookConfig]:
        """获取订单簿配置"""
        config = self.get_config(exchange_name)
        return config.orderbook if config else None
    
    def get_connection_limits(self, exchange_name: str) -> Dict[str, int]:
        """获取连接限制配置"""
        config = self.get_config(exchange_name)
        if not config:
            return {}
        
        return config.connection.limits
    
    def should_use_client_ping(self, exchange_name: str) -> bool:
        """检查是否需要客户端主动发送ping"""
        heartbeat_config = self.get_heartbeat_config(exchange_name)
        if not heartbeat_config or not heartbeat_config.client_strategy:
            return False
        
        return heartbeat_config.client_strategy.get('enable_proactive_ping', False)
    
    def get_ping_interval(self, exchange_name: str) -> Optional[int]:
        """获取ping间隔时间"""
        heartbeat_config = self.get_heartbeat_config(exchange_name)
        if not heartbeat_config:
            return None
        
        return heartbeat_config.client_ping_interval_seconds
    
    def get_orderbook_maintenance_method(self, exchange_name: str) -> str:
        """获取订单簿维护方法"""
        orderbook_config = self.get_orderbook_config(exchange_name)
        if not orderbook_config:
            return "standard"
        
        return orderbook_config.maintenance_method
    
    def reload_config(self, exchange_name: str = None):
        """
        重新加载配置
        
        Args:
            exchange_name: 指定交易所名称，如果为None则重新加载所有配置
        """
        if exchange_name:
            # 重新加载指定交易所配置
            config_file = self.config_dir / f"{exchange_name}_websocket.yaml"
            if config_file.exists():
                try:
                    config = self._load_exchange_config(config_file)
                    self._configs[exchange_name] = config
                    logger.info(f"✅ 重新加载交易所配置成功: {exchange_name}")
                except Exception as e:
                    logger.error(f"❌ 重新加载交易所配置失败: {exchange_name}, 错误: {e}")
            else:
                logger.warning(f"⚠️ 配置文件不存在: {config_file}")
        else:
            # 重新加载所有配置
            self._configs.clear()
            self._load_all_configs()
    
    def validate_config(self, exchange_name: str) -> Dict[str, Any]:
        """
        验证配置完整性
        
        Args:
            exchange_name: 交易所名称
            
        Returns:
            验证结果字典，包含is_valid和errors字段
        """
        config = self.get_config(exchange_name)
        if not config:
            return {
                "is_valid": False,
                "errors": [f"交易所配置不存在: {exchange_name}"]
            }
        
        errors = []
        
        # 验证必需字段
        if not config.exchange_name:
            errors.append("缺少exchange_name字段")
        
        if not config.connection.base_urls:
            errors.append("缺少WebSocket连接URL配置")
        
        if not config.orderbook.maintenance_method:
            errors.append("缺少订单簿维护方法配置")
        
        # 验证心跳配置
        if config.heartbeat.client_strategy and config.heartbeat.client_strategy.get('enable_proactive_ping'):
            if not config.heartbeat.client_ping_interval_seconds:
                errors.append("启用客户端ping但未配置ping间隔")
        
        return {
            "is_valid": len(errors) == 0,
            "errors": errors
        }


# 全局配置管理器实例
_global_config_manager = None


def get_exchange_config_manager() -> ExchangeConfigManager:
    """获取全局交易所配置管理器实例"""
    global _global_config_manager
    if _global_config_manager is None:
        _global_config_manager = ExchangeConfigManager()
    return _global_config_manager


def get_exchange_config(exchange_name: str) -> Optional[ExchangeWebSocketConfig]:
    """快捷方法：获取交易所配置"""
    manager = get_exchange_config_manager()
    return manager.get_config(exchange_name)


def get_websocket_url(exchange_name: str, connection_type: str = "public") -> Optional[str]:
    """快捷方法：获取WebSocket URL"""
    manager = get_exchange_config_manager()
    return manager.get_websocket_url(exchange_name, connection_type)


if __name__ == "__main__":
    # 测试配置管理器
    manager = ExchangeConfigManager()
    
    print("🔍 已配置的交易所:")
    for exchange in manager.get_all_exchanges():
        print(f"  - {exchange}")
        
        # 验证配置
        validation = manager.validate_config(exchange)
        if validation["is_valid"]:
            print(f"    ✅ 配置验证通过")
        else:
            print(f"    ❌ 配置验证失败: {validation['errors']}")
        
        # 显示关键配置
        config = manager.get_config(exchange)
        if config:
            print(f"    📡 WebSocket URLs: {list(config.connection.base_urls.keys())}")
            print(f"    💓 心跳方法: {'客户端主动ping' if manager.should_use_client_ping(exchange) else '服务器ping'}")
            print(f"    📚 订单簿维护: {config.orderbook.maintenance_method}")
        print()
