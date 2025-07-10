"""
交易所配置加载器

从配置文件加载交易所默认配置，确保代码和配置文件同步
"""

import os
import yaml
from typing import Dict, Any, Optional
from pathlib import Path
import structlog

from .data_types import Exchange, MarketType


class ExchangeConfigLoader:
    """交易所配置加载器"""
    
    def __init__(self, config_dir: Optional[str] = None):
        self.logger = structlog.get_logger(__name__)
        
        # 确定配置目录
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            # 默认使用项目根目录的config/collector
            current_dir = Path(__file__).parent
            project_root = current_dir.parent.parent.parent  # 向上三级到项目根目录
            self.config_dir = project_root / "config" / "collector"
        
        self.config_file = self.config_dir / "exchange_defaults.yaml"
        self._config_cache: Optional[Dict[str, Any]] = None
        
        self.logger.info("交易所配置加载器初始化", config_file=str(self.config_file))
    
    def load_config(self, force_reload: bool = False) -> Dict[str, Any]:
        """
        加载配置文件
        
        Args:
            force_reload: 是否强制重新加载
            
        Returns:
            配置字典
        """
        if self._config_cache is None or force_reload:
            try:
                if not self.config_file.exists():
                    self.logger.warning("配置文件不存在，使用默认配置", 
                                      config_file=str(self.config_file))
                    return self._get_fallback_config()
                
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self._config_cache = yaml.safe_load(f)
                
                self.logger.info("配置文件加载成功", config_file=str(self.config_file))
                
            except Exception as e:
                self.logger.error("配置文件加载失败，使用默认配置", 
                                error=str(e), config_file=str(self.config_file))
                return self._get_fallback_config()
        
        return self._config_cache or {}
    
    def get_exchange_defaults(self, exchange: Exchange, market_type: MarketType) -> Dict[str, Any]:
        """
        获取交易所默认配置
        
        Args:
            exchange: 交易所
            market_type: 市场类型
            
        Returns:
            默认配置字典
        """
        config = self.load_config()
        
        # 获取全局默认配置
        global_defaults = config.get('global_defaults', {})
        
        # 获取交易所特定配置
        exchange_name = exchange.value.lower()
        exchange_config = config.get('exchanges', {}).get(exchange_name, {})
        
        # 获取市场类型特定配置
        market_type_str = market_type.value.lower()
        depth_config = exchange_config.get('depth_config', {}).get(market_type_str, {})
        performance_config = exchange_config.get('performance', {})
        limits_config = exchange_config.get('limits', {})
        
        # 合并配置（优先级：市场类型 > 交易所 > 全局）
        merged_config = {}
        merged_config.update(global_defaults)
        merged_config.update(performance_config)
        merged_config.update(limits_config)
        merged_config.update(depth_config)
        
        # 添加端点配置
        endpoints = exchange_config.get('endpoints', {}).get(market_type_str, {})
        if endpoints:
            merged_config.update({
                'base_url': endpoints.get('rest_url', ''),
                'ws_url': endpoints.get('websocket_url', '')
            })
        
        self.logger.debug("获取交易所默认配置",
                         exchange=exchange_name,
                         market_type=market_type_str,
                         config_keys=list(merged_config.keys()))
        
        return merged_config
    
    def get_depth_limits(self, exchange: Exchange, market_type: MarketType) -> Dict[str, Any]:
        """
        获取深度限制配置
        
        Args:
            exchange: 交易所
            market_type: 市场类型
            
        Returns:
            深度限制配置
        """
        config = self.load_config()
        exchange_name = exchange.value.lower()
        market_type_str = market_type.value.lower()
        
        depth_config = (config.get('exchanges', {})
                       .get(exchange_name, {})
                       .get('depth_config', {})
                       .get(market_type_str, {}))
        
        return {
            'max_snapshot_depth': depth_config.get('max_snapshot_depth', 5000),
            'supported_websocket_depths': depth_config.get('supported_websocket_depths', [20]),
            'api_weight_map': depth_config.get('api_weight_map', {20: 1})
        }
    
    def validate_config(self, config_dict: Dict[str, Any]) -> tuple[bool, str]:
        """
        验证配置有效性
        
        Args:
            config_dict: 配置字典
            
        Returns:
            (是否有效, 错误消息)
        """
        try:
            validation_rules = self.load_config().get('validation_rules', {})
            
            for field, rules in validation_rules.items():
                if field in config_dict:
                    value = config_dict[field]
                    
                    # 检查最小值
                    if 'min' in rules and value < rules['min']:
                        return False, f"{field}值{value}小于最小值{rules['min']}"
                    
                    # 检查最大值
                    if 'max' in rules and value > rules['max']:
                        return False, f"{field}值{value}大于最大值{rules['max']}"
            
            return True, "配置有效"
            
        except Exception as e:
            return False, f"配置验证失败: {str(e)}"
    
    def _get_fallback_config(self) -> Dict[str, Any]:
        """获取降级配置"""
        return {
            'global_defaults': {
                'ping_interval': 30,
                'reconnect_attempts': 5,
                'reconnect_delay': 5,
                'max_requests_per_minute': 1200,
                'snapshot_interval': 300,
                'snapshot_depth': 400,
                'websocket_depth': 20
            },
            'exchanges': {
                'binance': {
                    'endpoints': {
                        'spot': {
                            'rest_url': 'https://api.binance.com',
                            'websocket_url': 'wss://stream.binance.com:9443'
                        }
                    },
                    'depth_config': {
                        'spot': {
                            'snapshot_depth': 400,
                            'websocket_depth': 20,
                            'max_snapshot_depth': 5000,
                            'supported_websocket_depths': [5, 10, 20]
                        }
                    }
                },
                'okx': {
                    'endpoints': {
                        'spot': {
                            'rest_url': 'https://www.okx.com',
                            'websocket_url': 'wss://ws.okx.com:8443/ws/v5/public'
                        }
                    },
                    'depth_config': {
                        'spot': {
                            'snapshot_depth': 400,
                            'websocket_depth': 400,
                            'max_snapshot_depth': 400,
                            'supported_websocket_depths': [1, 5, 50, 400]
                        }
                    }
                }
            }
        }
    
    def get_environment_config(self, environment: str = "production") -> Dict[str, Any]:
        """
        获取环境特定配置
        
        Args:
            environment: 环境名称 (development, production, testing)
            
        Returns:
            环境配置
        """
        config = self.load_config()
        env_config = config.get('environments', {}).get(environment, {})
        
        # 合并环境特定的全局默认配置
        global_defaults = config.get('global_defaults', {})
        env_global_defaults = env_config.get('global_defaults', {})
        
        merged_defaults = {}
        merged_defaults.update(global_defaults)
        merged_defaults.update(env_global_defaults)
        
        return merged_defaults


# 全局实例
_exchange_config_loader = None

def get_exchange_config_loader() -> ExchangeConfigLoader:
    """获取交易所配置加载器实例"""
    global _exchange_config_loader
    if _exchange_config_loader is None:
        _exchange_config_loader = ExchangeConfigLoader()
    return _exchange_config_loader
