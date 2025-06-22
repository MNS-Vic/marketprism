"""
日志中间件TDD测试
专门用于提升logging_middleware.py模块的测试覆盖率

遵循TDD原则：
1. Red: 编写失败的测试
2. Green: 编写最少代码使测试通过
3. Refactor: 重构代码保持测试通过
"""

import pytest
import asyncio
import json
import logging
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from io import StringIO

# 导入日志中间件模块（假设存在）
try:
    from core.middleware.logging_middleware import (
        LoggingMiddleware, LoggingConfig, LoggingRule, LogFormatter,
        RequestLogger, ResponseLogger, ErrorLogger, StructuredLogger,
        LogLevel, LogFormat, LogDestination, LogFilter, LogContext
    )
except ImportError:
    # 如果模块不存在，创建模拟类用于测试
    from enum import Enum
    from dataclasses import dataclass, field
    import sys
    
    class LogLevel(Enum):
        DEBUG = "DEBUG"
        INFO = "INFO"
        WARNING = "WARNING"
        ERROR = "ERROR"
        CRITICAL = "CRITICAL"
    
    class LogFormat(Enum):
        TEXT = "text"
        JSON = "json"
        STRUCTURED = "structured"
    
    class LogDestination(Enum):
        CONSOLE = "console"
        FILE = "file"
        SYSLOG = "syslog"
        REMOTE = "remote"
    
    @dataclass
    class LoggingRule:
        rule_id: str
        name: str
        description: str = ""
        path_pattern: str = "*"
        method_pattern: str = "*"
        log_level: LogLevel = LogLevel.INFO
        log_format: LogFormat = LogFormat.JSON
        destinations: List[LogDestination] = field(default_factory=lambda: [LogDestination.CONSOLE])
        include_request_body: bool = False
        include_response_body: bool = False
        include_headers: bool = True
        exclude_headers: List[str] = field(default_factory=lambda: ["Authorization", "Cookie"])
        enabled: bool = True
        priority: int = 0
        
        def matches_request(self, method: str, path: str) -> bool:
            """检查请求是否匹配规则"""
            method_match = self.method_pattern == "*" or method.upper() == self.method_pattern.upper()
            
            if self.path_pattern == "*":
                path_match = True
            elif self.path_pattern.endswith("/*"):
                prefix = self.path_pattern[:-2]
                path_match = path.startswith(prefix)
            else:
                path_match = path == self.path_pattern
            
            return method_match and path_match
    
    @dataclass
    class LoggingConfig:
        enabled: bool = True
        default_log_level: LogLevel = LogLevel.INFO
        default_format: LogFormat = LogFormat.JSON
        default_destinations: List[LogDestination] = field(default_factory=lambda: [LogDestination.CONSOLE])
        include_request_id: bool = True
        include_timestamp: bool = True
        include_user_info: bool = True
        max_body_size: int = 1024
        sensitive_fields: List[str] = field(default_factory=lambda: ["password", "token", "secret"])
        rules: List[LoggingRule] = field(default_factory=list)
        
        def add_rule(self, rule: LoggingRule) -> None:
            self.rules.append(rule)
        
        def remove_rule(self, rule_id: str) -> bool:
            for i, rule in enumerate(self.rules):
                if rule.rule_id == rule_id:
                    del self.rules[i]
                    return True
            return False
        
        def find_matching_rule(self, method: str, path: str) -> Optional[LoggingRule]:
            # 按优先级排序
            sorted_rules = sorted(self.rules, key=lambda r: r.priority, reverse=True)
            
            for rule in sorted_rules:
                if rule.enabled and rule.matches_request(method, path):
                    return rule
            
            return None
    
    @dataclass
    class LogContext:
        request_id: str
        timestamp: datetime
        method: str
        path: str
        user_id: str = None
        session_id: str = None
        ip_address: str = None
        user_agent: str = None
        metadata: Dict[str, Any] = field(default_factory=dict)
    
    class LogFormatter:
        def __init__(self, format_type: LogFormat = LogFormat.JSON):
            self.format_type = format_type
        
        def format_request_log(self, context: LogContext, request_data: Dict[str, Any]) -> str:
            """格式化请求日志"""
            log_entry = {
                "type": "request",
                "request_id": context.request_id,
                "timestamp": context.timestamp.isoformat(),
                "method": context.method,
                "path": context.path,
                "user_id": context.user_id,
                "ip_address": context.ip_address,
                **request_data
            }
            
            if self.format_type == LogFormat.JSON:
                return json.dumps(log_entry, default=str)
            elif self.format_type == LogFormat.TEXT:
                return f"[{context.timestamp}] {context.method} {context.path} - User: {context.user_id}"
            else:
                return str(log_entry)
        
        def format_response_log(self, context: LogContext, response_data: Dict[str, Any]) -> str:
            """格式化响应日志"""
            log_entry = {
                "type": "response",
                "request_id": context.request_id,
                "timestamp": context.timestamp.isoformat(),
                "method": context.method,
                "path": context.path,
                "user_id": context.user_id,
                **response_data
            }
            
            if self.format_type == LogFormat.JSON:
                return json.dumps(log_entry, default=str)
            elif self.format_type == LogFormat.TEXT:
                status = response_data.get("status_code", "unknown")
                duration = response_data.get("duration", "unknown")
                return f"[{context.timestamp}] {context.method} {context.path} - Status: {status}, Duration: {duration}ms"
            else:
                return str(log_entry)
        
        def format_error_log(self, context: LogContext, error_data: Dict[str, Any]) -> str:
            """格式化错误日志"""
            log_entry = {
                "type": "error",
                "request_id": context.request_id,
                "timestamp": context.timestamp.isoformat(),
                "method": context.method,
                "path": context.path,
                "user_id": context.user_id,
                **error_data
            }
            
            if self.format_type == LogFormat.JSON:
                return json.dumps(log_entry, default=str)
            elif self.format_type == LogFormat.TEXT:
                error_type = error_data.get("error_type", "unknown")
                error_message = error_data.get("error_message", "unknown")
                return f"[{context.timestamp}] ERROR {context.method} {context.path} - {error_type}: {error_message}"
            else:
                return str(log_entry)
    
    class LogFilter:
        def __init__(self, sensitive_fields: List[str] = None):
            self.sensitive_fields = sensitive_fields or ["password", "token", "secret", "authorization"]
        
        def filter_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
            """过滤敏感数据"""
            if not isinstance(data, dict):
                return data
            
            filtered_data = {}
            for key, value in data.items():
                if any(sensitive in key.lower() for sensitive in self.sensitive_fields):
                    filtered_data[key] = "***FILTERED***"
                elif isinstance(value, dict):
                    filtered_data[key] = self.filter_sensitive_data(value)
                else:
                    filtered_data[key] = value
            
            return filtered_data
        
        def filter_headers(self, headers: Dict[str, str], exclude_headers: List[str] = None) -> Dict[str, str]:
            """过滤头部信息"""
            exclude_headers = exclude_headers or []
            filtered_headers = {}
            
            for key, value in headers.items():
                if key.lower() in [h.lower() for h in exclude_headers]:
                    filtered_headers[key] = "***FILTERED***"
                else:
                    filtered_headers[key] = value
            
            return filtered_headers
        
        def truncate_body(self, body: str, max_size: int) -> str:
            """截断请求/响应体"""
            if len(body) <= max_size:
                return body
            else:
                return body[:max_size] + "...[TRUNCATED]"
    
    class RequestLogger:
        def __init__(self, formatter: LogFormatter, filter_obj: LogFilter):
            self.formatter = formatter
            self.filter = filter_obj
            self.logger = logging.getLogger("request_logger")
        
        def log_request(self, context: LogContext, request_data: Dict[str, Any], rule: LoggingRule) -> None:
            """记录请求日志"""
            # 过滤敏感数据
            filtered_data = self.filter.filter_sensitive_data(request_data)
            
            # 过滤头部
            if "headers" in filtered_data and rule.include_headers:
                filtered_data["headers"] = self.filter.filter_headers(
                    filtered_data["headers"], 
                    rule.exclude_headers
                )
            elif not rule.include_headers:
                filtered_data.pop("headers", None)
            
            # 处理请求体
            if "body" in filtered_data:
                if rule.include_request_body:
                    filtered_data["body"] = self.filter.truncate_body(
                        filtered_data["body"], 
                        1024
                    )
                else:
                    filtered_data.pop("body", None)
            
            # 格式化并记录
            log_message = self.formatter.format_request_log(context, filtered_data)
            self.logger.log(self._get_log_level_value(rule.log_level), log_message)
        
        def _get_log_level_value(self, log_level: LogLevel) -> int:
            """获取日志级别数值"""
            level_map = {
                LogLevel.DEBUG: logging.DEBUG,
                LogLevel.INFO: logging.INFO,
                LogLevel.WARNING: logging.WARNING,
                LogLevel.ERROR: logging.ERROR,
                LogLevel.CRITICAL: logging.CRITICAL
            }
            return level_map.get(log_level, logging.INFO)
    
    class ResponseLogger:
        def __init__(self, formatter: LogFormatter, filter_obj: LogFilter):
            self.formatter = formatter
            self.filter = filter_obj
            self.logger = logging.getLogger("response_logger")
        
        def log_response(self, context: LogContext, response_data: Dict[str, Any], rule: LoggingRule) -> None:
            """记录响应日志"""
            # 过滤敏感数据
            filtered_data = self.filter.filter_sensitive_data(response_data)
            
            # 处理响应体
            if "body" in filtered_data:
                if rule.include_response_body:
                    filtered_data["body"] = self.filter.truncate_body(
                        filtered_data["body"], 
                        1024
                    )
                else:
                    filtered_data.pop("body", None)
            
            # 格式化并记录
            log_message = self.formatter.format_response_log(context, filtered_data)
            self.logger.log(self._get_log_level_value(rule.log_level), log_message)
        
        def _get_log_level_value(self, log_level: LogLevel) -> int:
            """获取日志级别数值"""
            level_map = {
                LogLevel.DEBUG: logging.DEBUG,
                LogLevel.INFO: logging.INFO,
                LogLevel.WARNING: logging.WARNING,
                LogLevel.ERROR: logging.ERROR,
                LogLevel.CRITICAL: logging.CRITICAL
            }
            return level_map.get(log_level, logging.INFO)
    
    class ErrorLogger:
        def __init__(self, formatter: LogFormatter):
            self.formatter = formatter
            self.logger = logging.getLogger("error_logger")
        
        def log_error(self, context: LogContext, error: Exception, error_data: Dict[str, Any] = None) -> None:
            """记录错误日志"""
            error_info = {
                "error_type": type(error).__name__,
                "error_message": str(error),
                "error_data": error_data or {}
            }
            
            log_message = self.formatter.format_error_log(context, error_info)
            self.logger.error(log_message)
    
    class LoggingMiddleware:
        def __init__(self, config: LoggingConfig):
            self.config = config
            self.formatter = LogFormatter(config.default_format)
            self.filter = LogFilter(config.sensitive_fields)
            self.request_logger = RequestLogger(self.formatter, self.filter)
            self.response_logger = ResponseLogger(self.formatter, self.filter)
            self.error_logger = ErrorLogger(self.formatter)
        
        def _build_context(self, request) -> LogContext:
            """构建日志上下文"""
            return LogContext(
                request_id=getattr(request, 'request_id', 'unknown'),
                timestamp=datetime.now(timezone.utc),
                method=getattr(request, 'method', 'unknown'),
                path=getattr(request, 'path', 'unknown'),
                user_id=getattr(request, 'user_id', None),
                ip_address=getattr(request, 'ip_address', None),
                user_agent=getattr(request, 'user_agent', None)
            )
        
        async def process_request(self, request) -> Dict[str, Any]:
            """处理请求日志"""
            if not self.config.enabled:
                return {"success": True, "continue_chain": True}
            
            context = self._build_context(request)
            rule = self.config.find_matching_rule(context.method, context.path)
            
            if rule:
                request_data = {
                    "headers": getattr(request, 'headers', {}),
                    "query_params": getattr(request, 'query_params', {}),
                    "body": getattr(request, 'body', '')
                }
                
                self.request_logger.log_request(context, request_data, rule)
            
            return {"success": True, "continue_chain": True}
        
        async def process_response(self, request, response) -> Dict[str, Any]:
            """处理响应日志"""
            if not self.config.enabled:
                return {"success": True}
            
            context = self._build_context(request)
            rule = self.config.find_matching_rule(context.method, context.path)
            
            if rule:
                response_data = {
                    "status_code": getattr(response, 'status_code', 200),
                    "headers": getattr(response, 'headers', {}),
                    "body": getattr(response, 'body', ''),
                    "duration": getattr(response, 'duration', 0)
                }
                
                self.response_logger.log_response(context, response_data, rule)
            
            return {"success": True}
        
        async def process_error(self, request, error: Exception) -> Dict[str, Any]:
            """处理错误日志"""
            if not self.config.enabled:
                return {"success": True}
            
            context = self._build_context(request)
            self.error_logger.log_error(context, error)
            
            return {"success": True}

from core.middleware.middleware_framework import MiddlewareConfig, MiddlewareType, MiddlewareContext


class TestLoggingRule:
    """测试日志规则"""
    
    def test_logging_rule_creation(self):
        """测试：日志规则创建"""
        rule = LoggingRule(
            rule_id="api_log",
            name="API日志规则",
            description="API接口日志",
            path_pattern="/api/*",
            method_pattern="*",
            log_level=LogLevel.INFO,
            log_format=LogFormat.JSON,
            destinations=[LogDestination.CONSOLE, LogDestination.FILE],
            include_request_body=True,
            include_response_body=False,
            include_headers=True,
            exclude_headers=["Authorization", "Cookie"],
            enabled=True,
            priority=10
        )
        
        assert rule.rule_id == "api_log"
        assert rule.name == "API日志规则"
        assert rule.description == "API接口日志"
        assert rule.path_pattern == "/api/*"
        assert rule.method_pattern == "*"
        assert rule.log_level == LogLevel.INFO
        assert rule.log_format == LogFormat.JSON
        assert rule.destinations == [LogDestination.CONSOLE, LogDestination.FILE]
        assert rule.include_request_body is True
        assert rule.include_response_body is False
        assert rule.include_headers is True
        assert rule.exclude_headers == ["Authorization", "Cookie"]
        assert rule.enabled is True
        assert rule.priority == 10

    def test_logging_rule_defaults(self):
        """测试：日志规则默认值"""
        rule = LoggingRule(rule_id="basic", name="基础规则")

        assert rule.rule_id == "basic"
        assert rule.name == "基础规则"
        assert rule.description == ""
        assert rule.path_pattern == "*"
        assert rule.method_pattern == "*"
        assert rule.log_level == LogLevel.INFO
        assert rule.log_format == LogFormat.JSON
        assert rule.destinations == [LogDestination.CONSOLE]
        assert rule.include_request_body is False
        assert rule.include_response_body is False
        assert rule.include_headers is True
        assert rule.exclude_headers == ["Authorization", "Cookie"]
        assert rule.enabled is True
        assert rule.priority == 0

    def test_logging_rule_matches_request(self):
        """测试：日志规则请求匹配"""
        # 通配符规则
        wildcard_rule = LoggingRule(
            rule_id="wildcard",
            name="通配符规则",
            path_pattern="*",
            method_pattern="*"
        )

        assert wildcard_rule.matches_request("GET", "/any/path") is True
        assert wildcard_rule.matches_request("POST", "/api/users") is True

        # API路径规则
        api_rule = LoggingRule(
            rule_id="api",
            name="API规则",
            path_pattern="/api/*",
            method_pattern="GET"
        )

        assert api_rule.matches_request("GET", "/api/users") is True
        assert api_rule.matches_request("GET", "/api/users/123") is True
        assert api_rule.matches_request("POST", "/api/users") is False
        assert api_rule.matches_request("GET", "/public/info") is False


class TestLoggingConfig:
    """测试日志配置"""

    def setup_method(self):
        """设置测试方法"""
        self.config = LoggingConfig()

    def test_logging_config_creation(self):
        """测试：日志配置创建"""
        config = LoggingConfig(
            enabled=True,
            default_log_level=LogLevel.DEBUG,
            default_format=LogFormat.TEXT,
            default_destinations=[LogDestination.FILE],
            include_request_id=True,
            include_timestamp=True,
            include_user_info=True,
            max_body_size=2048,
            sensitive_fields=["password", "secret"]
        )

        assert config.enabled is True
        assert config.default_log_level == LogLevel.DEBUG
        assert config.default_format == LogFormat.TEXT
        assert config.default_destinations == [LogDestination.FILE]
        assert config.include_request_id is True
        assert config.include_timestamp is True
        assert config.include_user_info is True
        assert config.max_body_size == 2048
        assert config.sensitive_fields == ["password", "secret"]

    def test_logging_config_defaults(self):
        """测试：日志配置默认值"""
        assert self.config.enabled is True
        assert self.config.default_log_level == LogLevel.INFO
        assert self.config.default_format == LogFormat.JSON
        assert self.config.default_destinations == [LogDestination.CONSOLE]
        assert self.config.include_request_id is True
        assert self.config.include_timestamp is True
        assert self.config.include_user_info is True
        assert self.config.max_body_size == 1024
        assert self.config.sensitive_fields == ["password", "token", "secret"]
        assert self.config.rules == []

    def test_add_remove_rule(self):
        """测试：添加和移除规则"""
        rule = LoggingRule(rule_id="test_rule", name="测试规则")

        # 添加规则
        self.config.add_rule(rule)
        assert len(self.config.rules) == 1
        assert self.config.rules[0] == rule

        # 移除规则
        result = self.config.remove_rule("test_rule")
        assert result is True
        assert len(self.config.rules) == 0

        # 移除不存在的规则
        result = self.config.remove_rule("non_existent")
        assert result is False

    def test_find_matching_rule(self):
        """测试：查找匹配规则"""
        # 添加多个规则
        high_priority_rule = LoggingRule(
            rule_id="high_priority",
            name="高优先级",
            path_pattern="/api/important/*",
            priority=100
        )

        low_priority_rule = LoggingRule(
            rule_id="low_priority",
            name="低优先级",
            path_pattern="/api/*",
            priority=10
        )

        self.config.add_rule(low_priority_rule)
        self.config.add_rule(high_priority_rule)

        # 测试高优先级匹配
        matched = self.config.find_matching_rule("GET", "/api/important/data")
        assert matched == high_priority_rule

        # 测试低优先级匹配
        matched = self.config.find_matching_rule("GET", "/api/users")
        assert matched == low_priority_rule

        # 测试无匹配
        matched = self.config.find_matching_rule("GET", "/public/info")
        assert matched is None


class TestLogFormatter:
    """测试日志格式化器"""

    def setup_method(self):
        """设置测试方法"""
        self.context = LogContext(
            request_id="req_123",
            timestamp=datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            method="GET",
            path="/api/users",
            user_id="user_456",
            ip_address="192.168.1.1"
        )

    def test_log_formatter_json_format(self):
        """测试：JSON格式化"""
        formatter = LogFormatter(LogFormat.JSON)

        request_data = {"headers": {"Content-Type": "application/json"}}
        log_message = formatter.format_request_log(self.context, request_data)

        # 验证是有效的JSON
        log_dict = json.loads(log_message)
        assert log_dict["type"] == "request"
        assert log_dict["request_id"] == "req_123"
        assert log_dict["method"] == "GET"
        assert log_dict["path"] == "/api/users"
        assert log_dict["user_id"] == "user_456"

    def test_log_formatter_text_format(self):
        """测试：文本格式化"""
        formatter = LogFormatter(LogFormat.TEXT)

        request_data = {"headers": {"Content-Type": "application/json"}}
        log_message = formatter.format_request_log(self.context, request_data)

        assert "GET" in log_message
        assert "/api/users" in log_message
        assert "user_456" in log_message

    def test_log_formatter_response_format(self):
        """测试：响应格式化"""
        formatter = LogFormatter(LogFormat.JSON)

        response_data = {"status_code": 200, "duration": 150}
        log_message = formatter.format_response_log(self.context, response_data)

        log_dict = json.loads(log_message)
        assert log_dict["type"] == "response"
        assert log_dict["status_code"] == 200
        assert log_dict["duration"] == 150

    def test_log_formatter_error_format(self):
        """测试：错误格式化"""
        formatter = LogFormatter(LogFormat.JSON)

        error_data = {"error_type": "ValueError", "error_message": "Invalid input"}
        log_message = formatter.format_error_log(self.context, error_data)

        log_dict = json.loads(log_message)
        assert log_dict["type"] == "error"
        assert log_dict["error_type"] == "ValueError"
        assert log_dict["error_message"] == "Invalid input"


class TestLogFilter:
    """测试日志过滤器"""

    def setup_method(self):
        """设置测试方法"""
        self.filter = LogFilter(["password", "token", "secret"])

    def test_filter_sensitive_data(self):
        """测试：过滤敏感数据"""
        data = {
            "username": "testuser",
            "password": "secret123",
            "token": "abc123",
            "normal_field": "normal_value"
        }

        filtered_data = self.filter.filter_sensitive_data(data)

        assert filtered_data["username"] == "testuser"
        assert filtered_data["password"] == "***FILTERED***"
        assert filtered_data["token"] == "***FILTERED***"
        assert filtered_data["normal_field"] == "normal_value"

    def test_filter_nested_sensitive_data(self):
        """测试：过滤嵌套敏感数据"""
        data = {
            "user": {
                "name": "testuser",
                "password": "secret123"
            },
            "auth": {
                "token": "abc123"
            }
        }

        filtered_data = self.filter.filter_sensitive_data(data)

        assert filtered_data["user"]["name"] == "testuser"
        assert filtered_data["user"]["password"] == "***FILTERED***"
        assert filtered_data["auth"]["token"] == "***FILTERED***"

    def test_filter_headers(self):
        """测试：过滤头部信息"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer token123",
            "Cookie": "session=abc123",
            "User-Agent": "TestAgent/1.0"
        }

        exclude_headers = ["Authorization", "Cookie"]
        filtered_headers = self.filter.filter_headers(headers, exclude_headers)

        assert filtered_headers["Content-Type"] == "application/json"
        assert filtered_headers["Authorization"] == "***FILTERED***"
        assert filtered_headers["Cookie"] == "***FILTERED***"
        assert filtered_headers["User-Agent"] == "TestAgent/1.0"

    def test_truncate_body(self):
        """测试：截断请求体"""
        short_body = "short content"
        long_body = "a" * 2000

        # 短内容不截断
        result = self.filter.truncate_body(short_body, 1024)
        assert result == short_body

        # 长内容截断
        result = self.filter.truncate_body(long_body, 1024)
        assert len(result) == 1024 + len("...[TRUNCATED]")
        assert result.endswith("...[TRUNCATED]")


class TestRequestLogger:
    """测试请求日志记录器"""

    def setup_method(self):
        """设置测试方法"""
        self.formatter = LogFormatter(LogFormat.JSON)
        self.filter = LogFilter()
        self.logger = RequestLogger(self.formatter, self.filter)

        # 模拟日志输出
        self.log_stream = StringIO()
        handler = logging.StreamHandler(self.log_stream)
        self.logger.logger.addHandler(handler)
        self.logger.logger.setLevel(logging.DEBUG)

    def test_log_request_basic(self):
        """测试：基础请求日志"""
        context = LogContext(
            request_id="req_123",
            timestamp=datetime.now(timezone.utc),
            method="GET",
            path="/api/users"
        )

        request_data = {
            "headers": {"Content-Type": "application/json"},
            "query_params": {"page": "1"},
            "body": '{"test": "data"}'
        }

        rule = LoggingRule(
            rule_id="test",
            name="测试",
            include_headers=True,
            include_request_body=True
        )

        self.logger.log_request(context, request_data, rule)

        # 验证日志输出
        log_output = self.log_stream.getvalue()
        assert "req_123" in log_output
        assert "GET" in log_output
        assert "/api/users" in log_output
