"""
MarketPrism 动态权重配置加载器

负责从config/core/dynamic_weight_config.yaml加载权重配置
并提供配置访问接口
"""

import os
import yaml
from typing import Dict, Any, Optional, List
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class WeightConfigLoader:
    """权重配置加载器"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置加载器
        
        Args:
            config_path: 配置文件路径，默认使用项目标准路径
        """
        if config_path is None:
            # 使用项目标准配置路径
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config" / "core" / "dynamic_weight_config.yaml"
        
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = {}
        self._load_config()
    
    def _load_config(self):
        """加载配置文件"""
        try:
            if not self.config_path.exists():
                logger.error(f"权重配置文件不存在: {self.config_path}")
                self._load_default_config()
                return
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
            
            logger.info(f"权重配置加载成功: {self.config_path}")
            self._validate_config()
            
        except Exception as e:
            logger.error(f"加载权重配置失败: {e}")
            self._load_default_config()
    
    def _validate_config(self):
        """验证配置的有效性"""
        required_sections = ['global_settings', 'exchanges']
        for section in required_sections:
            if section not in self.config:
                logger.error(f"配置缺少必需的部分: {section}")
                raise ValueError(f"Invalid config: missing {section}")
        
        # 验证交易所配置
        exchanges = self.config.get('exchanges', {})
        for exchange_name, exchange_config in exchanges.items():
            if not exchange_config.get('enabled', False):
                continue
                
            if 'weight_rules' not in exchange_config:
                logger.warning(f"交易所 {exchange_name} 缺少权重规则配置")
    
    def _load_default_config(self):
        """加载默认配置"""
        logger.info("使用默认权重配置")
        self.config = {
            'global_settings': {
                'enable_dynamic_weight_calculation': True,
                'enable_weight_optimization_suggestions': True,
                'enable_weight_monitoring': True,
                'weight_cache_ttl': 300,
                'optimization_report_interval': 3600
            },
            'exchanges': {
                'binance': {
                    'enabled': True,
                    'rate_limits': {
                        'request_weight_per_minute': 6000,
                        'request_count_per_minute': 1200
                    },
                    'safety_margins': {
                        'weight_margin': 0.8,
                        'request_margin': 0.85
                    },
                    'weight_rules': {
                        'basic_apis': {
                            '/api/v3/ping': {'base_weight': 1},
                            '/api/v3/time': {'base_weight': 1},
                            '/api/v3/exchangeInfo': {'base_weight': 10}
                        }
                    }
                }
            }
        }
    
    def get_global_setting(self, key: str, default: Any = None) -> Any:
        """获取全局设置"""
        return self.config.get('global_settings', {}).get(key, default)
    
    def get_exchange_config(self, exchange: str) -> Dict[str, Any]:
        """获取交易所配置"""
        return self.config.get('exchanges', {}).get(exchange.lower(), {})
    
    def get_exchange_rate_limits(self, exchange: str) -> Dict[str, Any]:
        """获取交易所速率限制配置"""
        exchange_config = self.get_exchange_config(exchange)
        return exchange_config.get('rate_limits', {})
    
    def get_exchange_safety_margins(self, exchange: str) -> Dict[str, Any]:
        """获取交易所安全边际配置"""
        exchange_config = self.get_exchange_config(exchange)
        return exchange_config.get('safety_margins', {})
    
    def get_exchange_weight_rules(self, exchange: str) -> Dict[str, Any]:
        """获取交易所权重规则"""
        exchange_config = self.get_exchange_config(exchange)
        return exchange_config.get('weight_rules', {})
    
    def get_basic_api_weight(self, exchange: str, endpoint: str) -> Optional[int]:
        """获取基础API的权重"""
        weight_rules = self.get_exchange_weight_rules(exchange)
        basic_apis = weight_rules.get('basic_apis', {})
        
        endpoint_config = basic_apis.get(endpoint, {})
        return endpoint_config.get('base_weight')
    
    def get_parameter_based_api_config(self, exchange: str, endpoint: str) -> Optional[Dict[str, Any]]:
        """获取参数相关API的配置"""
        weight_rules = self.get_exchange_weight_rules(exchange)
        parameter_apis = weight_rules.get('parameter_based_apis', {})
        
        return parameter_apis.get(endpoint)
    
    def get_multi_symbol_api_config(self, exchange: str, endpoint: str) -> Optional[Dict[str, Any]]:
        """获取多交易对API的配置"""
        weight_rules = self.get_exchange_weight_rules(exchange)
        multi_symbol_apis = weight_rules.get('multi_symbol_apis', {})
        
        return multi_symbol_apis.get(endpoint)
    
    def get_batch_api_config(self, exchange: str, endpoint: str) -> Optional[Dict[str, Any]]:
        """获取批量API的配置"""
        weight_rules = self.get_exchange_weight_rules(exchange)
        batch_apis = weight_rules.get('batch_apis', {})
        
        return batch_apis.get(endpoint)
    
    def get_websocket_api_config(self, exchange: str, endpoint: str) -> Optional[Dict[str, Any]]:
        """获取WebSocket API的配置"""
        weight_rules = self.get_exchange_weight_rules(exchange)
        websocket_apis = weight_rules.get('websocket_apis', {})
        
        return websocket_apis.get(endpoint)
    
    def get_order_api_config(self, exchange: str, endpoint: str) -> Optional[Dict[str, Any]]:
        """获取订单API的配置"""
        weight_rules = self.get_exchange_weight_rules(exchange)
        order_apis = weight_rules.get('order_apis', {})
        
        return order_apis.get(endpoint)
    
    def get_optimization_config(self) -> Dict[str, Any]:
        """获取优化配置"""
        return self.config.get('optimization', {})
    
    def get_logging_config(self) -> Dict[str, Any]:
        """获取日志配置"""
        return self.config.get('logging', {})
    
    def get_integration_config(self) -> Dict[str, Any]:
        """获取集成配置"""
        return self.config.get('integration', {})
    
    def is_exchange_enabled(self, exchange: str) -> bool:
        """检查交易所是否启用"""
        exchange_config = self.get_exchange_config(exchange)
        return exchange_config.get('enabled', False)
    
    def is_dynamic_weight_enabled(self) -> bool:
        """检查是否启用动态权重计算"""
        return self.get_global_setting('enable_dynamic_weight_calculation', True)
    
    def is_optimization_enabled(self) -> bool:
        """检查是否启用优化建议"""
        return self.get_global_setting('enable_weight_optimization_suggestions', True)
    
    def is_monitoring_enabled(self) -> bool:
        """检查是否启用权重监控"""
        return self.get_global_setting('enable_weight_monitoring', True)
    
    def get_supported_exchanges(self) -> List[str]:
        """获取支持的交易所列表"""
        exchanges = []
        for exchange_name, config in self.config.get('exchanges', {}).items():
            if config.get('enabled', False):
                exchanges.append(exchange_name)
        return exchanges
    
    def get_test_scenarios(self) -> List[Dict[str, Any]]:
        """获取测试场景配置"""
        testing_config = self.config.get('testing', {})
        return testing_config.get('test_scenarios', [])
    
    def reload_config(self):
        """重新加载配置"""
        logger.info("重新加载权重配置")
        self._load_config()
    
    def get_config_summary(self) -> Dict[str, Any]:
        """获取配置摘要"""
        return {
            'config_path': str(self.config_path),
            'config_loaded': bool(self.config),
            'dynamic_weight_enabled': self.is_dynamic_weight_enabled(),
            'optimization_enabled': self.is_optimization_enabled(),
            'monitoring_enabled': self.is_monitoring_enabled(),
            'supported_exchanges': self.get_supported_exchanges(),
            'total_exchanges_configured': len(self.config.get('exchanges', {})),
            'global_settings': self.config.get('global_settings', {}),
            'optimization_config': self.get_optimization_config(),
            'integration_config': self.get_integration_config()
        }


# 全局配置实例
_global_weight_config: Optional[WeightConfigLoader] = None


def get_weight_config() -> WeightConfigLoader:
    """获取全局权重配置实例"""
    global _global_weight_config
    if _global_weight_config is None:
        _global_weight_config = WeightConfigLoader()
    return _global_weight_config


def reload_weight_config():
    """重新加载全局权重配置"""
    global _global_weight_config
    if _global_weight_config is not None:
        _global_weight_config.reload_config()
    else:
        _global_weight_config = WeightConfigLoader()


# 便利函数
def get_exchange_weight_limit(exchange: str) -> int:
    """获取交易所权重限制"""
    config = get_weight_config()
    rate_limits = config.get_exchange_rate_limits(exchange)
    return rate_limits.get('request_weight_per_minute', 6000)


def get_exchange_weight_margin(exchange: str) -> float:
    """获取交易所权重安全边际"""
    config = get_weight_config()
    safety_margins = config.get_exchange_safety_margins(exchange)
    return safety_margins.get('weight_margin', 0.8)


def is_high_weight_request(weight: int) -> bool:
    """判断是否为高权重请求"""
    config = get_weight_config()
    optimization_config = config.get_optimization_config()
    suggestions_config = optimization_config.get('suggestions', {})
    threshold = suggestions_config.get('high_weight_threshold', 10)
    return weight > threshold


if __name__ == "__main__":
    # 测试配置加载器
    def test_weight_config_loader():
        print("🔧 MarketPrism 权重配置加载器测试")
        print("=" * 50)
        
        # 加载配置
        config = WeightConfigLoader()
        
        # 显示配置摘要
        summary = config.get_config_summary()
        print(f"\n📄 配置摘要:")
        print(f"  配置文件: {summary['config_path']}")
        print(f"  配置已加载: {summary['config_loaded']}")
        print(f"  动态权重: {summary['dynamic_weight_enabled']}")
        print(f"  优化建议: {summary['optimization_enabled']}")
        print(f"  权重监控: {summary['monitoring_enabled']}")
        print(f"  支持交易所: {summary['supported_exchanges']}")
        
        # 测试Binance配置
        print(f"\n🏢 Binance配置测试:")
        print(f"  是否启用: {config.is_exchange_enabled('binance')}")
        
        rate_limits = config.get_exchange_rate_limits('binance')
        print(f"  权重限制: {rate_limits.get('request_weight_per_minute', 'N/A')}/分钟")
        
        safety_margins = config.get_exchange_safety_margins('binance')
        print(f"  安全边际: {safety_margins.get('weight_margin', 'N/A')}")
        
        # 测试权重规则
        ping_weight = config.get_basic_api_weight('binance', '/api/v3/ping')
        print(f"  ping权重: {ping_weight}")
        
        # 测试多交易对API配置
        ticker_config = config.get_multi_symbol_api_config('binance', '/api/v3/ticker/24hr')
        if ticker_config:
            special_rules = ticker_config.get('special_rules', {})
            print(f"  24hr ticker无symbol权重: {special_rules.get('no_symbol_weight', 'N/A')}")
        
        # 测试优化配置
        optimization = config.get_optimization_config()
        suggestions = optimization.get('suggestions', {})
        print(f"\n⚡ 优化配置:")
        print(f"  高权重阈值: {suggestions.get('high_weight_threshold', 'N/A')}")
        
        # 测试便利函数
        print(f"\n🛠 便利函数测试:")
        print(f"  Binance权重限制: {get_exchange_weight_limit('binance')}")
        print(f"  Binance安全边际: {get_exchange_weight_margin('binance')}")
        print(f"  权重15是否为高权重: {is_high_weight_request(15)}")
        print(f"  权重5是否为高权重: {is_high_weight_request(5)}")
        
        print("\n✅ 配置加载器测试完成")
    
    test_weight_config_loader()