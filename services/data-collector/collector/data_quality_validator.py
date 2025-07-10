"""
数据质量验证器

实现数据去重、异常检测和完整性检查
"""

import time
from typing import Dict, Any, List, Optional, Set, Tuple
from decimal import Decimal
from dataclasses import dataclass
from collections import defaultdict, deque
import structlog

from .data_collection_config_manager import get_data_collection_config_manager


@dataclass
class DataPoint:
    """数据点"""
    timestamp: int
    symbol: str
    exchange: str
    data_type: str
    data: Dict[str, Any]
    
    def get_key(self) -> str:
        """获取去重键"""
        return f"{self.timestamp}_{self.symbol}_{self.exchange}_{self.data_type}"


@dataclass
class ValidationResult:
    """验证结果"""
    valid: bool
    action: str  # 'accept', 'drop', 'error'
    reason: Optional[str] = None
    original_data: Optional[Any] = None
    processed_data: Optional[Any] = None


class DataQualityValidator:
    """数据质量验证器"""
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
        self.config_manager = get_data_collection_config_manager()
        self.quality_config = self.config_manager.get_quality_config()
        
        # 去重缓存
        self._dedup_cache: Set[str] = set()
        self._cache_max_size = 10000
        self._cache_cleanup_threshold = 8000
        
        # 价格历史（用于异常检测）
        self._price_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        
        # 统计信息
        self.stats = {
            'total_processed': 0,
            'duplicates_dropped': 0,
            'anomalies_detected': 0,
            'errors_raised': 0,
            'valid_data': 0
        }
        
        self.logger.info("数据质量验证器初始化完成")
    
    def validate_data_point(self, data_point: DataPoint) -> ValidationResult:
        """验证单个数据点"""
        try:
            self.stats['total_processed'] += 1
            
            # 1. 去重检查
            if self.quality_config.deduplication_enabled:
                dedup_result = self._check_duplicate(data_point)
                if not dedup_result.valid:
                    self.stats['duplicates_dropped'] += 1
                    return dedup_result
            
            # 2. 异常检测
            if self.quality_config.anomaly_detection_enabled:
                anomaly_result = self._detect_anomaly(data_point)
                if not anomaly_result.valid:
                    self.stats['anomalies_detected'] += 1
                    if anomaly_result.action == 'error':
                        self.stats['errors_raised'] += 1
                    return anomaly_result
            
            # 3. 数据有效
            self.stats['valid_data'] += 1
            return ValidationResult(valid=True, action='accept', processed_data=data_point.data)
            
        except Exception as e:
            self.logger.error("数据验证异常", 
                            symbol=data_point.symbol,
                            exchange=data_point.exchange,
                            error=str(e),
                            exc_info=True)
            return ValidationResult(
                valid=False, 
                action='error', 
                reason=f"验证异常: {str(e)}"
            )
    
    def _check_duplicate(self, data_point: DataPoint) -> ValidationResult:
        """检查重复数据"""
        key = data_point.get_key()
        
        if key in self._dedup_cache:
            return ValidationResult(
                valid=False,
                action='drop',
                reason='重复数据',
                original_data=data_point.data
            )
        
        # 添加到缓存
        self._dedup_cache.add(key)
        
        # 缓存清理
        if len(self._dedup_cache) > self._cache_max_size:
            self._cleanup_cache()
        
        return ValidationResult(valid=True, action='accept')
    
    def _cleanup_cache(self):
        """清理去重缓存"""
        try:
            # 简单策略：清理一半缓存
            cache_list = list(self._dedup_cache)
            keep_size = self._cache_cleanup_threshold
            self._dedup_cache = set(cache_list[-keep_size:])
            
            self.logger.debug("去重缓存已清理", 
                            old_size=len(cache_list),
                            new_size=len(self._dedup_cache))
        except Exception as e:
            self.logger.error("缓存清理失败", error=str(e))
    
    def _detect_anomaly(self, data_point: DataPoint) -> ValidationResult:
        """检测异常数据"""
        try:
            data = data_point.data
            symbol_key = f"{data_point.exchange}_{data_point.symbol}"
            
            # 价格异常检测
            if 'price' in data:
                price_result = self._check_price_anomaly(data['price'], symbol_key)
                if not price_result.valid:
                    return price_result
            
            # 交易量异常检测
            if 'volume' in data or 'quantity' in data:
                volume = data.get('volume') or data.get('quantity')
                volume_result = self._check_volume_anomaly(volume)
                if not volume_result.valid:
                    return volume_result
            
            # 时间戳检查
            timestamp_result = self._check_timestamp_anomaly(data_point.timestamp)
            if not timestamp_result.valid:
                return timestamp_result
            
            return ValidationResult(valid=True, action='accept')
            
        except Exception as e:
            return ValidationResult(
                valid=False,
                action='error',
                reason=f"异常检测失败: {str(e)}"
            )
    
    def _check_price_anomaly(self, price: Any, symbol_key: str) -> ValidationResult:
        """检查价格异常"""
        try:
            price_decimal = Decimal(str(price))
            
            # 检查价格是否为正数
            if price_decimal <= 0:
                return ValidationResult(
                    valid=False,
                    action='error',
                    reason=f"价格必须为正数: {price}"
                )
            
            # 获取历史价格
            price_history = self._price_history[symbol_key]
            
            if len(price_history) > 0:
                # 计算价格偏差
                recent_price = price_history[-1]
                deviation = abs(price_decimal - recent_price) / recent_price
                
                if deviation > self.quality_config.price_deviation_threshold:
                    return ValidationResult(
                        valid=False,
                        action='error',
                        reason=f"价格偏差过大: {deviation:.2%} > {self.quality_config.price_deviation_threshold:.2%}"
                    )
            
            # 添加到历史记录
            price_history.append(price_decimal)
            
            return ValidationResult(valid=True, action='accept')
            
        except (ValueError, TypeError) as e:
            return ValidationResult(
                valid=False,
                action='error',
                reason=f"价格格式错误: {price}"
            )
    
    def _check_volume_anomaly(self, volume: Any) -> ValidationResult:
        """检查交易量异常"""
        try:
            volume_decimal = Decimal(str(volume))
            
            # 检查交易量是否为非负数
            if volume_decimal < 0:
                return ValidationResult(
                    valid=False,
                    action='error',
                    reason=f"交易量不能为负数: {volume}"
                )
            
            # 检查交易量是否过大
            if volume_decimal > self.quality_config.volume_threshold:
                return ValidationResult(
                    valid=False,
                    action='error',
                    reason=f"交易量异常过大: {volume} > {self.quality_config.volume_threshold}"
                )
            
            return ValidationResult(valid=True, action='accept')
            
        except (ValueError, TypeError) as e:
            return ValidationResult(
                valid=False,
                action='error',
                reason=f"交易量格式错误: {volume}"
            )
    
    def _check_timestamp_anomaly(self, timestamp: int) -> ValidationResult:
        """检查时间戳异常"""
        try:
            current_time = int(time.time() * 1000)  # 毫秒时间戳
            
            # 检查时间戳是否在合理范围内（过去1小时到未来5分钟）
            min_timestamp = current_time - 3600000  # 1小时前
            max_timestamp = current_time + 300000   # 5分钟后
            
            if timestamp < min_timestamp:
                return ValidationResult(
                    valid=False,
                    action='error',
                    reason=f"时间戳过旧: {timestamp}"
                )
            
            if timestamp > max_timestamp:
                return ValidationResult(
                    valid=False,
                    action='error',
                    reason=f"时间戳过新: {timestamp}"
                )
            
            return ValidationResult(valid=True, action='accept')
            
        except Exception as e:
            return ValidationResult(
                valid=False,
                action='error',
                reason=f"时间戳检查失败: {str(e)}"
            )
    
    def validate_batch(self, data_points: List[DataPoint]) -> List[ValidationResult]:
        """批量验证数据点"""
        results = []
        for data_point in data_points:
            result = self.validate_data_point(data_point)
            results.append(result)
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """获取验证统计信息"""
        total = self.stats['total_processed']
        if total > 0:
            return {
                **self.stats,
                'duplicate_rate': self.stats['duplicates_dropped'] / total,
                'anomaly_rate': self.stats['anomalies_detected'] / total,
                'error_rate': self.stats['errors_raised'] / total,
                'valid_rate': self.stats['valid_data'] / total
            }
        return self.stats
    
    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            'total_processed': 0,
            'duplicates_dropped': 0,
            'anomalies_detected': 0,
            'errors_raised': 0,
            'valid_data': 0
        }
        self.logger.info("数据质量验证统计已重置")
    
    def clear_cache(self):
        """清空缓存"""
        self._dedup_cache.clear()
        self._price_history.clear()
        self.logger.info("数据质量验证缓存已清空")


# 全局验证器实例
_validator = None

def get_data_quality_validator() -> DataQualityValidator:
    """获取全局数据质量验证器实例"""
    global _validator
    if _validator is None:
        _validator = DataQualityValidator()
    return _validator
