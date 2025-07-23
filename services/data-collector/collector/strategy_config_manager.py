"""
策略配置管理器

管理交易策略的订单簿深度配置，支持策略驱动的档位定制
"""

import os
import yaml
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
import structlog

from .data_types import Exchange, MarketType


class StrategyPriority(Enum):
    """策略优先级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class StrategyDepthConfig:
    """策略深度配置"""
    strategy_name: str
    exchange: Exchange
    market_type: MarketType
    snapshot_depth: int
    websocket_depth: int
    api_weight: int
    update_frequency: str = "100ms"
    priority: StrategyPriority = StrategyPriority.MEDIUM
    
    def __post_init__(self):
        """后处理验证"""
        if self.snapshot_depth <= 0 or self.websocket_depth <= 0:
            raise ValueError("深度档位必须大于0")


@dataclass
class StrategyPerformanceConfig:
    """策略性能配置"""
    snapshot_interval: int
    max_latency_ms: int
    error_tolerance: str
    
    def __post_init__(self):
        """验证性能配置"""
        if self.snapshot_interval <= 0:
            raise ValueError("快照间隔必须大于0")
        if self.max_latency_ms <= 0:
            raise ValueError("最大延迟必须大于0")


class StrategyConfigManager:
    """策略配置管理器 - 使用统一配置文件"""

    def __init__(self, config_file: Optional[str] = None):
        self.logger = structlog.get_logger(__name__)

        # 🔧 配置统一：使用统一主配置文件
        if config_file:
            self.config_file = Path(config_file)
        else:
            current_dir = Path(__file__).parent
            project_root = current_dir.parent.parent.parent
            # 🎯 关键修改：使用统一主配置文件
            self.config_file = project_root / "config" / "collector" / "unified_data_collection.yaml"

        self._config_cache: Optional[Dict[str, Any]] = None

        self.logger.info("策略配置管理器初始化（统一配置）", config_file=str(self.config_file))
    
    def load_config(self, force_reload: bool = False) -> Dict[str, Any]:
        """从统一配置文件加载策略配置"""
        if self._config_cache is None or force_reload:
            try:
                if not self.config_file.exists():
                    self.logger.warning("统一配置文件不存在，使用默认配置")
                    return self._get_default_config()

                with open(self.config_file, 'r', encoding='utf-8') as f:
                    unified_config = yaml.safe_load(f)

                # 🔧 从统一配置中提取策略配置
                self._config_cache = unified_config.get('trading_strategies', {})

                self.logger.info("策略配置从统一配置文件加载成功")

            except Exception as e:
                self.logger.error("统一配置文件加载失败，使用默认配置", error=str(e))
                return self._get_default_config()

        return self._config_cache or {}
    
    def get_strategy_depth_config(self, strategy_name: str, exchange: Exchange, 
                                 market_type: MarketType) -> StrategyDepthConfig:
        """
        获取策略深度配置
        
        Args:
            strategy_name: 策略名称
            exchange: 交易所
            market_type: 市场类型
            
        Returns:
            策略深度配置
        """
        config = self.load_config()
        strategies = config.get('strategies', {})
        
        # 获取策略配置
        strategy_config = strategies.get(strategy_name)
        if not strategy_config:
            self.logger.warning("策略不存在，使用默认策略", strategy=strategy_name)
            strategy_config = strategies.get('default', {})
        
        # 获取深度配置
        depth_config = strategy_config.get('depth_config', {})
        
        # 获取交易所特定配置
        exchange_name = exchange.value.lower()
        market_type_str = market_type.value.lower()
        
        exchange_config = (depth_config.get('exchanges', {})
                          .get(exchange_name, {})
                          .get(market_type_str, {}))
        
        # 获取默认配置
        default_config = depth_config.get('default', {})
        
        # 合并配置（优先级：交易所特定 > 默认）
        merged_config = {}
        merged_config.update(default_config)
        merged_config.update(exchange_config)
        
        # 应用交易所限制
        validated_config = self._apply_exchange_limits(merged_config, exchange, market_type)
        
        # 创建配置对象
        return StrategyDepthConfig(
            strategy_name=strategy_name,
            exchange=exchange,
            market_type=market_type,
            snapshot_depth=validated_config.get('snapshot_depth', 400),
            websocket_depth=validated_config.get('websocket_depth', 20),
            api_weight=validated_config.get('api_weight', 1),
            update_frequency=validated_config.get('update_frequency', '100ms'),
            priority=StrategyPriority(strategy_config.get('priority', 'medium'))
        )
    
    def get_strategy_performance_config(self, strategy_name: str) -> StrategyPerformanceConfig:
        """获取策略性能配置"""
        config = self.load_config()
        strategies = config.get('strategies', {})
        
        strategy_config = strategies.get(strategy_name, strategies.get('default', {}))
        performance_config = strategy_config.get('performance', {})
        
        return StrategyPerformanceConfig(
            snapshot_interval=performance_config.get('snapshot_interval', 300),
            max_latency_ms=performance_config.get('max_latency_ms', 200),
            error_tolerance=performance_config.get('error_tolerance', 'medium')
        )
    
    def _apply_exchange_limits(self, config: Dict[str, Any], exchange: Exchange, 
                              market_type: MarketType) -> Dict[str, Any]:
        """应用交易所限制"""
        validation_rules = self.load_config().get('validation_rules', {})
        
        # 获取深度一致性规则
        consistency_rules = validation_rules.get('depth_consistency', {})
        exchange_rules = consistency_rules.get(exchange.value.lower(), {})
        
        # 应用WebSocket深度限制
        max_websocket_depth = exchange_rules.get('max_websocket_depth')
        if max_websocket_depth and config.get('websocket_depth', 0) > max_websocket_depth:
            original_depth = config.get('websocket_depth')
            config['websocket_depth'] = max_websocket_depth
            
            self.logger.info("应用WebSocket深度限制",
                           exchange=exchange.value,
                           original_depth=original_depth,
                           limited_depth=max_websocket_depth)
        
        return config
    
    def validate_strategy_config(self, strategy_name: str, exchange: Exchange, 
                                market_type: MarketType) -> Tuple[bool, str]:
        """验证策略配置"""
        try:
            depth_config = self.get_strategy_depth_config(strategy_name, exchange, market_type)
            performance_config = self.get_strategy_performance_config(strategy_name)
            
            # 验证深度配置
            if depth_config.snapshot_depth <= 0 or depth_config.websocket_depth <= 0:
                return False, "深度档位必须大于0"
            
            # 验证API权重
            validation_rules = self.load_config().get('validation_rules', {})
            weight_limits = validation_rules.get('api_weight_limits', {})
            exchange_limits = weight_limits.get(exchange.value.lower(), {})
            
            max_weight = exchange_limits.get('max_weight_per_minute', 1200)
            safety_margin = exchange_limits.get('weight_safety_margin', 0.8)
            
            if depth_config.api_weight > max_weight * safety_margin:
                return False, f"API权重{depth_config.api_weight}超过安全限制{max_weight * safety_margin}"
            
            # 验证性能约束
            constraints = validation_rules.get('performance_constraints', {})
            min_interval = constraints.get('min_snapshot_interval', 10)
            max_interval = constraints.get('max_snapshot_interval', 3600)
            
            if not (min_interval <= performance_config.snapshot_interval <= max_interval):
                return False, f"快照间隔{performance_config.snapshot_interval}超出范围[{min_interval}, {max_interval}]"
            
            return True, "策略配置有效"
            
        except Exception as e:
            return False, f"策略配置验证失败: {str(e)}"
    
    def get_available_strategies(self) -> List[str]:
        """获取可用策略列表"""
        config = self.load_config()
        return list(config.get('strategies', {}).keys())
    
    def get_strategy_combination_config(self, combination_name: str, exchange: Exchange, 
                                      market_type: MarketType) -> StrategyDepthConfig:
        """获取策略组合配置"""
        config = self.load_config()
        combinations = config.get('strategy_combinations', {})
        
        combination = combinations.get(combination_name)
        if not combination:
            raise ValueError(f"策略组合不存在: {combination_name}")
        
        strategies = combination.get('strategies', [])
        merge_policy = combination.get('depth_config', {}).get('merge_policy', 'max_depth')
        
        if merge_policy == 'max_depth':
            # 取所有策略的最大深度
            max_snapshot_depth = 0
            max_websocket_depth = 0
            max_api_weight = 0
            
            for strategy_name in strategies:
                strategy_config = self.get_strategy_depth_config(strategy_name, exchange, market_type)
                max_snapshot_depth = max(max_snapshot_depth, strategy_config.snapshot_depth)
                max_websocket_depth = max(max_websocket_depth, strategy_config.websocket_depth)
                max_api_weight = max(max_api_weight, strategy_config.api_weight)
            
            return StrategyDepthConfig(
                strategy_name=combination_name,
                exchange=exchange,
                market_type=market_type,
                snapshot_depth=max_snapshot_depth,
                websocket_depth=max_websocket_depth,
                api_weight=max_api_weight,
                priority=StrategyPriority.HIGH  # 组合策略优先级高
            )
        
        else:
            raise ValueError(f"不支持的合并策略: {merge_policy}")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            'strategies': {
                'default': {
                    'name': '默认策略',
                    'priority': 'medium',
                    'depth_config': {
                        'default': {
                            'snapshot_depth': 400,
                            'websocket_depth': 20,
                            'update_frequency': '100ms'
                        }
                    },
                    'performance': {
                        'snapshot_interval': 300,
                        'max_latency_ms': 200,
                        'error_tolerance': 'medium'
                    }
                }
            }
        }


# 全局实例
_strategy_config_manager = None

def get_strategy_config_manager() -> StrategyConfigManager:
    """获取策略配置管理器实例"""
    global _strategy_config_manager
    if _strategy_config_manager is None:
        _strategy_config_manager = StrategyConfigManager()
    return _strategy_config_manager
