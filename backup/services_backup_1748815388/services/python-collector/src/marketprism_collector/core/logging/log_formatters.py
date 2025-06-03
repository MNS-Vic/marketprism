"""
日志格式化器

提供多种日志格式化方式，包括JSON、结构化文本和彩色输出。
"""

import json
import re
from typing import Dict, Any
from datetime import datetime
from abc import ABC, abstractmethod


class LogFormatter(ABC):
    """日志格式化器抽象基类"""
    
    @abstractmethod
    def format(self, record: Dict[str, Any]) -> str:
        """格式化日志记录"""
        pass


class JSONFormatter(LogFormatter):
    """JSON格式化器"""
    
    def __init__(self, ensure_ascii: bool = False, indent: int = None):
        self.ensure_ascii = ensure_ascii
        self.indent = indent
    
    def format(self, record: Dict[str, Any]) -> str:
        """格式化为JSON"""
        try:
            return json.dumps(
                record,
                ensure_ascii=self.ensure_ascii,
                indent=self.indent,
                default=str,
                separators=(',', ':') if self.indent is None else (',', ': ')
            )
        except Exception as e:
            # 如果序列化失败，返回基本信息
            return json.dumps({
                'timestamp': record.get('timestamp', ''),
                'level': record.get('level', ''),
                'logger': record.get('logger', ''),
                'message': record.get('message', ''),
                'serialization_error': str(e)
            })


class StructuredFormatter(LogFormatter):
    """结构化文本格式化器"""
    
    def __init__(self):
        self.template = "{timestamp} [{level:>8}] {logger}: {message}"
    
    def format(self, record: Dict[str, Any]) -> str:
        """格式化为结构化文本"""
        # 基本格式
        timestamp = record.get('timestamp', '')
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                timestamp = dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            except:
                pass
        
        formatted = self.template.format(
            timestamp=timestamp,
            level=record.get('level', ''),
            logger=record.get('logger', ''),
            message=record.get('message', '')
        )
        
        # 添加上下文信息
        context_fields = []
        
        # 添加关键上下文字段
        for field in ['correlation_id', 'request_id', 'component', 'operation', 'exchange', 'symbol']:
            if field in record:
                context_fields.append(f"{field}={record[field]}")
        
        # 添加异常信息
        if 'exception' in record:
            exc = record['exception']
            context_fields.append(f"exception={exc.get('type', 'Unknown')}: {exc.get('message', '')}")
        
        # 添加性能信息
        if record.get('performance'):
            if 'duration' in record:
                context_fields.append(f"duration={record['duration']:.3f}s")
        
        # 添加安全信息
        if record.get('security'):
            if 'severity' in record:
                context_fields.append(f"security_severity={record['severity']}")
        
        if context_fields:
            formatted += f" [{', '.join(context_fields)}]"
        
        return formatted


class ColoredFormatter(LogFormatter):
    """彩色输出格式化器"""
    
    # ANSI颜色代码
    COLORS = {
        'TRACE': '\033[36m',      # 青色
        'DEBUG': '\033[37m',      # 白色
        'INFO': '\033[32m',       # 绿色
        'WARNING': '\033[33m',    # 黄色
        'ERROR': '\033[31m',      # 红色
        'CRITICAL': '\033[35m',   # 紫色
        'RESET': '\033[0m'        # 重置
    }
    
    def __init__(self, use_colors: bool = True):
        self.use_colors = use_colors
        self.structured_formatter = StructuredFormatter()
    
    def format(self, record: Dict[str, Any]) -> str:
        """格式化为彩色文本"""
        # 首先使用结构化格式化器
        formatted = self.structured_formatter.format(record)
        
        if not self.use_colors:
            return formatted
        
        # 添加颜色
        level = record.get('level', '')
        if level in self.COLORS:
            color = self.COLORS[level]
            reset = self.COLORS['RESET']
            
            # 只对级别部分添加颜色
            formatted = re.sub(
                r'(\[[\s]*' + re.escape(level) + r'[\s]*\])',
                f'{color}\\1{reset}',
                formatted
            )
        
        return formatted


class CompactFormatter(LogFormatter):
    """紧凑格式化器"""
    
    def format(self, record: Dict[str, Any]) -> str:
        """格式化为紧凑格式"""
        timestamp = record.get('timestamp', '')
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                timestamp = dt.strftime('%H:%M:%S')
            except:
                timestamp = timestamp[:8]
        
        level = record.get('level', '')[:4]  # 只取前4个字符
        logger = record.get('logger', '').split('.')[-1]  # 只取最后一部分
        message = record.get('message', '')
        
        formatted = f"{timestamp} {level:>4} {logger}: {message}"
        
        # 添加关键上下文
        if 'correlation_id' in record:
            formatted += f" [cid:{record['correlation_id'][:8]}]"
        
        if 'component' in record:
            formatted += f" [comp:{record['component']}]"
        
        if 'exception' in record:
            exc = record['exception']
            formatted += f" [exc:{exc.get('type', 'Unknown')}]"
        
        return formatted


class ElasticsearchFormatter(LogFormatter):
    """Elasticsearch格式化器"""
    
    def format(self, record: Dict[str, Any]) -> str:
        """格式化为Elasticsearch友好的JSON"""
        # 扁平化嵌套字段
        flattened = self._flatten_record(record)
        
        # 确保字段名符合Elasticsearch规范
        normalized = self._normalize_field_names(flattened)
        
        return json.dumps(normalized, default=str, separators=(',', ':'))
    
    def _flatten_record(self, record: Dict[str, Any], prefix: str = '') -> Dict[str, Any]:
        """扁平化嵌套字典"""
        flattened = {}
        
        for key, value in record.items():
            new_key = f"{prefix}.{key}" if prefix else key
            
            if isinstance(value, dict):
                flattened.update(self._flatten_record(value, new_key))
            elif isinstance(value, list):
                # 对于列表，创建数组字段
                flattened[new_key] = value
            else:
                flattened[new_key] = value
        
        return flattened
    
    def _normalize_field_names(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """规范化字段名"""
        normalized = {}
        
        for key, value in record.items():
            # 替换不允许的字符
            normalized_key = re.sub(r'[^\w\.]', '_', key.lower())
            normalized[normalized_key] = value
        
        return normalized


class MetricsFormatter(LogFormatter):
    """指标格式化器（用于Prometheus等监控系统）"""
    
    def format(self, record: Dict[str, Any]) -> str:
        """格式化为指标格式"""
        if not record.get('performance') and not record.get('metrics'):
            return ""
        
        lines = []
        timestamp = record.get('timestamp', '')
        labels = []
        
        # 添加标签
        for field in ['component', 'operation', 'exchange', 'symbol']:
            if field in record:
                labels.append(f'{field}="{record[field]}"')
        
        label_str = '{' + ','.join(labels) + '}' if labels else ''
        
        # 性能指标
        if record.get('performance') and 'duration' in record:
            metric_name = f"marketprism_operation_duration_seconds{label_str}"
            lines.append(f"{metric_name} {record['duration']}")
        
        # 错误指标
        if record.get('level') in ['ERROR', 'CRITICAL']:
            metric_name = f"marketprism_errors_total{label_str}"
            lines.append(f"{metric_name} 1")
        
        return '\n'.join(lines) if lines else ""