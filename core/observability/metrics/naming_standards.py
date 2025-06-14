"""
指标命名标准模块

定义统一的指标命名规范，确保所有指标名称符合Prometheus标准。
"""

from datetime import datetime, timezone
import re
from typing import Dict, List, Tuple, Optional, Set
from enum import Enum
from dataclasses import dataclass

from .metric_categories import MetricType, MetricCategory, MetricSubCategory


class NamingConvention(Enum):
    """命名约定枚举"""
    PROMETHEUS = "prometheus"
    INFLUXDB = "influxdb"
    CUSTOM = "custom"


@dataclass
class NamingRule:
    """命名规则"""
    pattern: str
    description: str
    required: bool = True
    examples: List[str] = None
    
    def __post_init__(self):
        if self.examples is None:
            self.examples = []


class PrometheusNamingStandards:
    """Prometheus命名标准"""
    
    # 基本规则
    VALID_NAME_PATTERN = re.compile(r'^[a-zA-Z_:][a-zA-Z0-9_:]*$')
    VALID_LABEL_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
    RESERVED_PREFIXES = {'__'}
    RESERVED_SUFFIXES = {'_total', '_created', '_count', '_sum', '_bucket'}
    
    # 长度限制
    MAX_NAME_LENGTH = 63
    MAX_LABEL_NAME_LENGTH = 63
    MAX_LABEL_VALUE_LENGTH = 256
    
    # 标准后缀
    COUNTER_SUFFIXES = ['_total', '_created']
    RATE_SUFFIXES = ['_per_second', '_rate']
    GAUGE_SUFFIXES = ['_current', '_active', '_usage', '_ratio']
    HISTOGRAM_SUFFIXES = ['_duration_seconds', '_size_bytes', '_latency_seconds']
    SUMMARY_SUFFIXES = ['_duration_seconds', '_size_bytes']
    
    # 标准单位
    STANDARD_UNITS = {
        'time': ['seconds', 'milliseconds', 'microseconds', 'nanoseconds'],
        'size': ['bytes', 'kilobytes', 'megabytes', 'gigabytes'],
        'ratio': ['ratio', 'percent'],
        'count': ['total', 'current', 'active'],
        'rate': ['per_second', 'per_minute', 'per_hour']
    }
    
    # 命名规则
    NAMING_RULES = [
        NamingRule(
            pattern="^[a-z][a-z0-9_]*[a-z0-9]$",
            description="指标名称必须以小写字母开头，包含小写字母、数字和下划线",
            examples=["http_requests_total", "memory_usage_bytes"]
        ),
        NamingRule(
            pattern="^marketprism_.*",
            description="所有指标必须以项目前缀开头",
            examples=["marketprism_api_requests_total", "marketprism_memory_usage"]
        ),
        NamingRule(
            pattern=".*_(total|seconds|bytes|ratio|percent)$",
            description="指标应该包含描述性的单位后缀",
            required=False,
            examples=["requests_total", "duration_seconds", "size_bytes"]
        )
    ]


class MetricNameGenerator:
    """指标名称生成器"""
    
    def __init__(self, convention: NamingConvention = NamingConvention.PROMETHEUS):
        self.convention = convention
        self.reserved_names: Set[str] = set()
        self.name_mapping: Dict[str, str] = {}
        
    def generate_metric_name(
        self,
        base_name: str,
        metric_type: MetricType,
        category: MetricCategory,
        subcategory: Optional[MetricSubCategory] = None,
        unit: Optional[str] = None,
        custom_prefix: Optional[str] = None
    ) -> str:
        """生成标准化指标名称"""
        
        # 构建名称组件
        components = []
        
        # 添加前缀
        if custom_prefix:
            components.append(custom_prefix.lower())
        else:
            components.append("marketprism")
        
        # 添加分类
        if category:
            components.append(category.value.lower())
        
        # 添加子分类
        if subcategory:
            components.append(subcategory.value.lower())
        
        # 添加基础名称
        base_name_clean = self._clean_name_component(base_name)
        components.append(base_name_clean)
        
        # 添加单位后缀
        if unit:
            unit_suffix = self._get_unit_suffix(unit, metric_type)
            if unit_suffix:
                components.append(unit_suffix)
        else:
            # 根据指标类型添加默认后缀
            default_suffix = self._get_default_suffix(metric_type)
            if default_suffix:
                components.append(default_suffix)
        
        # 组合名称
        metric_name = "_".join(components)
        
        # 验证和清理
        return self._validate_and_clean(metric_name)
    
    def _clean_name_component(self, component: str) -> str:
        """清理名称组件"""
        # 转换为小写
        component = component.lower()
        
        # 替换非法字符
        component = re.sub(r'[^a-z0-9_]', '_', component)
        
        # 移除连续下划线
        component = re.sub(r'_+', '_', component)
        
        # 移除首尾下划线
        component = component.strip('_')
        
        return component
    
    def _get_unit_suffix(self, unit: str, metric_type: MetricType) -> Optional[str]:
        """获取单位后缀"""
        unit_mappings = {
            # 时间单位
            'second': 'seconds',
            'seconds': 'seconds',
            'ms': 'milliseconds',
            'millisecond': 'milliseconds',
            'milliseconds': 'milliseconds',
            
            # 大小单位
            'byte': 'bytes',
            'bytes': 'bytes',
            'kb': 'kilobytes',
            'mb': 'megabytes',
            'gb': 'gigabytes',
            
            # 比率单位
            'percent': 'percent',
            'percentage': 'percent',
            'ratio': 'ratio',
            
            # 计数单位
            'count': 'total' if metric_type == MetricType.COUNTER else 'current',
            'number': 'total' if metric_type == MetricType.COUNTER else 'current'
        }
        
        return unit_mappings.get(unit.lower())
    
    def _get_default_suffix(self, metric_type: MetricType) -> Optional[str]:
        """获取默认后缀"""
        if metric_type == MetricType.COUNTER:
            return "total"
        elif metric_type == MetricType.HISTOGRAM:
            return None  # 直方图通常有特定的单位
        elif metric_type == MetricType.SUMMARY:
            return None  # 摘要通常有特定的单位
        else:
            return None
    
    def _validate_and_clean(self, metric_name: str) -> str:
        """验证和清理最终名称"""
        if self.convention == NamingConvention.PROMETHEUS:
            return self._validate_prometheus_name(metric_name)
        else:
            return metric_name
    
    def _validate_prometheus_name(self, metric_name: str) -> str:
        """验证Prometheus名称"""
        # 检查基本格式
        if not PrometheusNamingStandards.VALID_NAME_PATTERN.match(metric_name):
            # 尝试修复
            metric_name = re.sub(r'[^a-zA-Z0-9_:]', '_', metric_name)
            metric_name = re.sub(r'_+', '_', metric_name)
            metric_name = metric_name.strip('_')
        
        # 检查长度
        if len(metric_name) > PrometheusNamingStandards.MAX_NAME_LENGTH:
            metric_name = metric_name[:PrometheusNamingStandards.MAX_NAME_LENGTH]
        
        # 检查保留前缀
        for prefix in PrometheusNamingStandards.RESERVED_PREFIXES:
            if metric_name.startswith(prefix):
                metric_name = f"custom_{metric_name}"
        
        return metric_name
    
    def generate_label_name(self, label_name: str) -> str:
        """生成标准化标签名称"""
        # 清理标签名称
        clean_name = self._clean_name_component(label_name)
        
        # 验证长度
        if len(clean_name) > PrometheusNamingStandards.MAX_LABEL_NAME_LENGTH:
            clean_name = clean_name[:PrometheusNamingStandards.MAX_LABEL_NAME_LENGTH]
        
        return clean_name
    
    def register_reserved_name(self, name: str) -> None:
        """注册保留名称"""
        self.reserved_names.add(name)
    
    def is_name_available(self, name: str) -> bool:
        """检查名称是否可用"""
        return name not in self.reserved_names
    
    def suggest_alternative_name(self, base_name: str) -> str:
        """建议替代名称"""
        if self.is_name_available(base_name):
            return base_name
        
        # 尝试添加数字后缀
        for i in range(1, 100):
            candidate = f"{base_name}_{i}"
            if self.is_name_available(candidate):
                return candidate
        
        # 添加时间戳
        import time
        timestamp = str(int(time.time()))[-6:]
        return f"{base_name}_{timestamp}"


class MetricNameValidator:
    """指标名称验证器"""
    
    def __init__(self, convention: NamingConvention = NamingConvention.PROMETHEUS):
        self.convention = convention
        
    def validate_metric_name(self, name: str) -> Dict[str, any]:
        """验证指标名称"""
        result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "suggestions": []
        }
        
        if self.convention == NamingConvention.PROMETHEUS:
            return self._validate_prometheus_metric_name(name, result)
        
        return result
    
    def _validate_prometheus_metric_name(self, name: str, result: Dict) -> Dict:
        """验证Prometheus指标名称"""
        # 检查基本格式
        if not PrometheusNamingStandards.VALID_NAME_PATTERN.match(name):
            result["valid"] = False
            result["errors"].append("名称包含非法字符")
            result["suggestions"].append("名称只能包含字母、数字、下划线和冒号")
        
        # 检查长度
        if len(name) > PrometheusNamingStandards.MAX_NAME_LENGTH:
            result["valid"] = False
            result["errors"].append(f"名称过长: {len(name)} > {PrometheusNamingStandards.MAX_NAME_LENGTH}")
        
        # 检查保留前缀
        for prefix in PrometheusNamingStandards.RESERVED_PREFIXES:
            if name.startswith(prefix):
                result["valid"] = False
                result["errors"].append(f"使用了保留前缀: {prefix}")
        
        # 检查项目前缀
        if not name.startswith("marketprism_"):
            result["warnings"].append("建议使用 'marketprism_' 前缀")
            result["suggestions"].append(f"建议名称: marketprism_{name}")
        
        # 检查命名约定
        if not re.match(r'^[a-z][a-z0-9_]*[a-z0-9]$', name):
            result["warnings"].append("名称应该全小写，以字母开头和结尾")
        
        # 检查单位后缀
        has_unit_suffix = any(name.endswith(suffix) for suffix_list in 
                             PrometheusNamingStandards.STANDARD_UNITS.values() 
                             for suffix in suffix_list)
        
        if not has_unit_suffix:
            result["warnings"].append("建议添加描述性的单位后缀")
            result["suggestions"].append("如: _total, _seconds, _bytes, _ratio")
        
        return result
    
    def validate_label_name(self, name: str) -> Dict[str, any]:
        """验证标签名称"""
        result = {
            "valid": True,
            "errors": [],
            "warnings": []
        }
        
        if self.convention == NamingConvention.PROMETHEUS:
            # 检查基本格式
            if not PrometheusNamingStandards.VALID_LABEL_PATTERN.match(name):
                result["valid"] = False
                result["errors"].append("标签名称包含非法字符")
            
            # 检查长度
            if len(name) > PrometheusNamingStandards.MAX_LABEL_NAME_LENGTH:
                result["valid"] = False
                result["errors"].append(f"标签名称过长: {len(name)} > {PrometheusNamingStandards.MAX_LABEL_NAME_LENGTH}")
            
            # 检查保留前缀
            if name.startswith("__"):
                result["valid"] = False
                result["errors"].append("标签名称不能以__开头")
        
        return result
    
    def validate_label_value(self, value: str) -> Dict[str, any]:
        """验证标签值"""
        result = {
            "valid": True,
            "errors": [],
            "warnings": []
        }
        
        # 检查长度
        if len(value) > PrometheusNamingStandards.MAX_LABEL_VALUE_LENGTH:
            result["valid"] = False
            result["errors"].append(f"标签值过长: {len(value)} > {PrometheusNamingStandards.MAX_LABEL_VALUE_LENGTH}")
        
        # 检查空值
        if not value:
            result["warnings"].append("标签值为空可能导致指标混淆")
        
        return result


# 全局名称生成器和验证器实例
_global_name_generator = MetricNameGenerator()
_global_name_validator = MetricNameValidator()


def generate_metric_name(
    base_name: str,
    metric_type: MetricType,
    category: MetricCategory,
    subcategory: Optional[MetricSubCategory] = None,
    unit: Optional[str] = None
) -> str:
    """生成标准化指标名称（全局函数）"""
    return _global_name_generator.generate_metric_name(
        base_name, metric_type, category, subcategory, unit
    )


def validate_metric_name(name: str) -> Dict[str, any]:
    """验证指标名称（全局函数）"""
    return _global_name_validator.validate_metric_name(name)


def validate_label_name(name: str) -> Dict[str, any]:
    """验证标签名称（全局函数）"""
    return _global_name_validator.validate_label_name(name)


# 常用指标名称模板
COMMON_METRIC_TEMPLATES = {
    # 业务指标
    "message_processing": {
        "total": "marketprism_business_messages_processed_total",
        "rate": "marketprism_business_messages_per_second",
        "errors": "marketprism_business_message_errors_total",
        "duration": "marketprism_business_message_processing_duration_seconds"
    },
    
    # 系统指标
    "system_resources": {
        "cpu": "marketprism_system_cpu_usage_percent",
        "memory": "marketprism_system_memory_usage_bytes",
        "disk": "marketprism_system_disk_usage_bytes",
        "network": "marketprism_system_network_bytes_total"
    },
    
    # API指标
    "api_performance": {
        "requests": "marketprism_api_requests_total",
        "duration": "marketprism_api_request_duration_seconds",
        "errors": "marketprism_api_errors_total",
        "rate_limit": "marketprism_api_rate_limit_exceeded_total"
    },
    
    # 数据库指标
    "database_operations": {
        "queries": "marketprism_database_queries_total",
        "duration": "marketprism_database_query_duration_seconds",
        "connections": "marketprism_database_connections_active",
        "errors": "marketprism_database_errors_total"
    }
}