"""
数据收集配置管理器

基于用户具体需求实现的数据收集参数配置和验证系统
"""

import yaml
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass
from enum import Enum
import structlog


class DataType(Enum):
    """数据类型枚举"""

    ORDERBOOK = "orderbook"
    TRADE = "trade"
    FUNDING_RATE = "funding_rate"
    OPEN_INTEREST = "open_interest"
    VOLATILITY_INDEX = "volatility_index"
    TOP_TRADER_RATIO = "top_trader_ratio"
    GLOBAL_LONG_SHORT_RATIO = "global_long_short_ratio"
    LIQUIDATION = "liquidation"


class CollectionMethod(Enum):
    """数据收集方法枚举"""
    WEBSOCKET = "websocket"
    REST_API = "rest_api"
    INCREMENTAL_WITH_SNAPSHOT = "incremental_with_snapshot"


@dataclass
class DataTypeConfig:
    """数据类型配置"""
    enabled: bool
    method: CollectionMethod
    interval: Optional[int] = None  # 秒
    real_time: bool = False
    historical: bool = False
    exchanges: Optional[List[str]] = None


@dataclass
class ExchangeConfig:
    """交易所配置"""
    enabled: bool
    symbols: Dict[str, List[str]]  # 产品类型 -> 交易对列表
    data_types: List[str]


@dataclass
class DataQualityConfig:
    """数据质量配置"""
    deduplication_enabled: bool
    anomaly_detection_enabled: bool
    price_deviation_threshold: float
    volume_threshold: int
    completeness_target: float
    latency_target: int


class DataCollectionConfigManager:
    """数据收集配置管理器"""
    
    def __init__(self, config_file: Optional[str] = None):
        self.logger = structlog.get_logger(__name__)

        # 🔧 第二阶段修复：使用本地配置文件
        # 确定配置文件路径
        if config_file:
            self.config_file = Path(config_file)
        else:
            # 优先使用服务本地配置
            current_file = Path(__file__)
            service_root = current_file.parent.parent  # services/data-collector/
            local_config = service_root / "config" / "collector" / "unified_data_collection.yaml"

            if local_config.exists():
                self.config_file = local_config
            else:
                # 回退到全局配置（向后兼容）
                project_root = current_file.parent.parent.parent.parent
                self.config_file = project_root / "config" / "collector" / "unified_data_collection.yaml"

        self.logger.info("数据收集配置管理器初始化（统一配置）", config_file=str(self.config_file))

        # 加载配置
        self._raw_config = None
        self._data_types_config = {}
        self._exchanges_config = {}
        self._quality_config = None

        self.load_config()
    
    def load_config(self):
        """加载配置文件"""
        try:
            if not self.config_file.exists():
                raise FileNotFoundError(f"配置文件不存在: {self.config_file}")
            
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self._raw_config = yaml.safe_load(f)
            
            # 解析配置
            self._parse_data_types_config()
            self._parse_exchanges_config()
            self._parse_quality_config()
            
            self.logger.info("数据收集配置加载成功")
            
        except Exception as e:
            self.logger.error("数据收集配置加载失败", error=str(e), exc_info=True)
            raise
    
    def _parse_data_types_config(self):
        """解析数据类型配置"""
        data_types = self._raw_config.get('data_collection', {}).get('data_types', {})
        
        for data_type, config in data_types.items():
            if isinstance(config, dict) and config.get('enabled', False):
                method_str = config.get('method', 'websocket')
                method = CollectionMethod(method_str)
                
                self._data_types_config[data_type] = DataTypeConfig(
                    enabled=True,
                    method=method,
                    interval=config.get('interval'),
                    real_time=config.get('real_time', False),
                    historical=config.get('historical', False),
                    exchanges=config.get('exchanges')
                )
    
    def _parse_exchanges_config(self):
        """解析交易所配置"""
        exchanges = self._raw_config.get('data_collection', {}).get('exchanges', {})
        
        for exchange, config in exchanges.items():
            if config.get('enabled', False):
                self._exchanges_config[exchange] = ExchangeConfig(
                    enabled=True,
                    symbols=config.get('symbols', {}),
                    data_types=config.get('data_types', [])
                )
    
    def _parse_quality_config(self):
        """解析数据质量配置"""
        quality = self._raw_config.get('data_collection', {}).get('data_quality', {})
        
        dedup = quality.get('deduplication', {})
        anomaly = quality.get('anomaly_detection', {})
        completeness = quality.get('completeness', {})
        latency = quality.get('latency', {})
        
        self._quality_config = DataQualityConfig(
            deduplication_enabled=dedup.get('enabled', True),
            anomaly_detection_enabled=anomaly.get('enabled', True),
            price_deviation_threshold=anomaly.get('price_deviation_threshold', 0.1),
            volume_threshold=anomaly.get('volume_threshold', 1000000),
            completeness_target=completeness.get('target', 0.95),
            latency_target=latency.get('target', 5)
        )
    
    def get_enabled_data_types(self) -> List[str]:
        """获取启用的数据类型列表"""
        return [dt for dt, config in self._data_types_config.items() if config.enabled]
    
    def get_data_type_config(self, data_type: str) -> Optional[DataTypeConfig]:
        """获取指定数据类型的配置"""
        return self._data_types_config.get(data_type)
    
    def get_enabled_exchanges(self) -> List[str]:
        """获取启用的交易所列表"""
        return [ex for ex, config in self._exchanges_config.items() if config.enabled]
    
    def get_exchange_config(self, exchange: str) -> Optional[ExchangeConfig]:
        """获取指定交易所的配置"""
        return self._exchanges_config.get(exchange)
    
    def get_exchange_symbols(self, exchange: str, product_type: str = None) -> List[str]:
        """获取交易所的交易对列表"""
        exchange_config = self.get_exchange_config(exchange)
        if not exchange_config:
            return []
        
        if product_type:
            return exchange_config.symbols.get(product_type, [])
        else:
            # 返回所有产品类型的交易对
            all_symbols = []
            for symbols in exchange_config.symbols.values():
                all_symbols.extend(symbols)
            return all_symbols
    
    def get_exchange_data_types(self, exchange: str) -> List[str]:
        """获取交易所支持的数据类型"""
        exchange_config = self.get_exchange_config(exchange)
        return exchange_config.data_types if exchange_config else []
    
    def is_data_type_enabled_for_exchange(self, data_type: str, exchange: str) -> bool:
        """检查数据类型是否在指定交易所启用"""
        # 检查数据类型是否全局启用
        dt_config = self.get_data_type_config(data_type)
        if not dt_config or not dt_config.enabled:
            return False
        
        # 检查数据类型是否限制了交易所
        if dt_config.exchanges and exchange not in dt_config.exchanges:
            return False
        
        # 检查交易所是否支持该数据类型
        exchange_data_types = self.get_exchange_data_types(exchange)
        return data_type in exchange_data_types
    
    def get_collection_method(self, data_type: str) -> Optional[CollectionMethod]:
        """获取数据类型的收集方法"""
        dt_config = self.get_data_type_config(data_type)
        return dt_config.method if dt_config else None
    
    def get_collection_interval(self, data_type: str) -> Optional[int]:
        """获取数据类型的收集间隔（秒）"""
        dt_config = self.get_data_type_config(data_type)
        return dt_config.interval if dt_config else None
    
    def is_real_time_data(self, data_type: str) -> bool:
        """检查是否为实时数据"""
        dt_config = self.get_data_type_config(data_type)
        return dt_config.real_time if dt_config else False
    
    def get_quality_config(self) -> DataQualityConfig:
        """获取数据质量配置"""
        return self._quality_config
    
    def should_deduplicate(self) -> bool:
        """是否启用去重"""
        return self._quality_config.deduplication_enabled
    
    def should_detect_anomalies(self) -> bool:
        """是否启用异常检测"""
        return self._quality_config.anomaly_detection_enabled
    
    def get_orderbook_config(self) -> Dict[str, Any]:
        """获取OrderBook Manager配置"""
        return self._raw_config.get('data_collection', {}).get('orderbook_manager', {})
    
    def get_nats_config(self) -> Dict[str, Any]:
        """获取NATS配置"""
        return self._raw_config.get('data_collection', {}).get('nats_streaming', {})
    
    def get_performance_config(self) -> Dict[str, Any]:
        """获取性能配置"""
        return self._raw_config.get('data_collection', {}).get('performance', {})

    def get_collection_schedule(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取数据收集调度计划"""
        schedule = {
            'websocket': [],      # WebSocket实时数据
            'rest_api': [],       # REST API定期数据
            'special': []         # 特殊处理数据
        }

        for data_type, config in self._data_types_config.items():
            if not config.enabled:
                continue

            for exchange in self.get_enabled_exchanges():
                if not self.is_data_type_enabled_for_exchange(data_type, exchange):
                    continue

                symbols = self.get_exchange_symbols(exchange)
                if not symbols:
                    continue

                task_info = {
                    'data_type': data_type,
                    'exchange': exchange,
                    'symbols': symbols,
                    'config': config
                }

                if config.method == CollectionMethod.WEBSOCKET:
                    schedule['websocket'].append(task_info)
                elif config.method == CollectionMethod.REST_API:
                    schedule['rest_api'].append(task_info)
                elif config.method == CollectionMethod.INCREMENTAL_WITH_SNAPSHOT:
                    schedule['special'].append(task_info)

        return schedule
    
    def validate_config(self) -> Dict[str, Any]:
        """验证配置的有效性"""
        validation_result = {
            'valid': True,
            'errors': [],
            'warnings': []
        }
        
        try:
            # 检查是否有启用的数据类型
            enabled_data_types = self.get_enabled_data_types()
            if not enabled_data_types:
                validation_result['errors'].append("没有启用的数据类型")
                validation_result['valid'] = False
            
            # 检查是否有启用的交易所
            enabled_exchanges = self.get_enabled_exchanges()
            if not enabled_exchanges:
                validation_result['errors'].append("没有启用的交易所")
                validation_result['valid'] = False
            
            # 检查交易所和数据类型的匹配
            for exchange in enabled_exchanges:
                exchange_data_types = self.get_exchange_data_types(exchange)
                if not exchange_data_types:
                    validation_result['warnings'].append(f"交易所 {exchange} 没有配置数据类型")
            
            # 检查特殊配置
            for data_type in enabled_data_types:
                dt_config = self.get_data_type_config(data_type)
                if dt_config.method == CollectionMethod.INCREMENTAL_WITH_SNAPSHOT:
                    if data_type != 'orderbook':
                        validation_result['warnings'].append(
                            f"数据类型 {data_type} 使用增量+快照方法，通常只用于orderbook"
                        )
            
            self.logger.info("配置验证完成", 
                           valid=validation_result['valid'],
                           errors=len(validation_result['errors']),
                           warnings=len(validation_result['warnings']))
            
        except Exception as e:
            validation_result['valid'] = False
            validation_result['errors'].append(f"配置验证异常: {str(e)}")
            self.logger.error("配置验证失败", error=str(e), exc_info=True)
        
        return validation_result


# 全局配置管理器实例
_config_manager = None

def get_data_collection_config_manager() -> DataCollectionConfigManager:
    """获取全局数据收集配置管理器实例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = DataCollectionConfigManager()
    return _config_manager
