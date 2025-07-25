"""
错误分类系统测试
"""

import sys
import os
import pytest
from datetime import datetime, timezone
from pathlib import Path

# Add the project root to the path to allow absolute imports
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from core.errors.error_categories import (
    ErrorCategory, ErrorSeverity, ErrorType, RecoveryStrategy,
    ErrorDefinition, ErrorCategoryManager
)


class TestErrorCategories:
    """错误分类测试"""
    
    def test_error_category_values(self):
        """测试错误分类值"""
        assert ErrorCategory.BUSINESS.value == "business"
        assert ErrorCategory.NETWORK.value == "network"
        assert ErrorCategory.SYSTEM.value == "system"
    
    def test_error_severity_priority(self):
        """测试错误严重程度优先级"""
        assert ErrorSeverity.CRITICAL.priority > ErrorSeverity.HIGH.priority
        assert ErrorSeverity.HIGH.priority > ErrorSeverity.MEDIUM.priority
        assert ErrorSeverity.MEDIUM.priority > ErrorSeverity.LOW.priority
        assert ErrorSeverity.LOW.priority > ErrorSeverity.INFO.priority
    
    def test_error_type_enum(self):
        """测试错误类型枚举"""
        assert ErrorType.CONNECTION_TIMEOUT.name == "CONNECTION_TIMEOUT"
        assert ErrorType.API_RATE_LIMITED.name == "API_RATE_LIMITED"
        assert ErrorType.DATA_FORMAT_INVALID.name == "DATA_FORMAT_INVALID"
    
    def test_recovery_strategy_enum(self):
        """测试恢复策略枚举"""
        assert RecoveryStrategy.RETRY.value == "retry"
        assert RecoveryStrategy.CIRCUIT_BREAKER.value == "circuit_breaker"
        assert RecoveryStrategy.GRACEFUL_DEGRADATION.value == "graceful_degradation"


class TestErrorDefinition:
    """错误定义测试"""
    
    def test_error_definition_creation(self):
        """测试错误定义创建"""
        definition = ErrorDefinition(
            error_type=ErrorType.CONNECTION_TIMEOUT,
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.HIGH,
            description="连接超时错误",
            recovery_strategy=RecoveryStrategy.RETRY,
            retry_count=3,
            retry_delay=1.0
        )
        
        assert definition.error_type == ErrorType.CONNECTION_TIMEOUT
        assert definition.category == ErrorCategory.NETWORK
        assert definition.severity == ErrorSeverity.HIGH
        assert definition.retry_count == 3
        assert definition.retry_delay == 1.0
    
    def test_error_definition_to_dict(self):
        """测试错误定义序列化"""
        definition = ErrorDefinition(
            error_type=ErrorType.DATA_FORMAT_INVALID,
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.MEDIUM,
            description="数据验证失败"
        )
        
        data = definition.to_dict()
        
        assert data["error_type"] == "DATA_FORMAT_INVALID"
        assert data["category"] == "validation"
        assert data["severity"] == "medium"
        assert data["description"] == "数据验证失败"


class TestErrorCategoryManager:
    """错误分类管理器测试"""
    
    def setup_method(self):
        """设置测试方法"""
        self.manager = ErrorCategoryManager()
    
    def test_register_error_definition(self):
        """测试注册错误定义"""
        definition = ErrorDefinition(
            error_type=ErrorType.CONNECTION_TIMEOUT,
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.HIGH,
            description="连接超时",
            recovery_strategy=RecoveryStrategy.RETRY
        )
        
        self.manager.register_error_definition(definition)
        
        retrieved = self.manager.get_error_definition(ErrorType.CONNECTION_TIMEOUT)
        assert retrieved is not None
        assert retrieved.error_type == ErrorType.CONNECTION_TIMEOUT
        assert retrieved.severity == ErrorSeverity.HIGH
    
    def test_get_definitions_by_category(self):
        """测试按分类获取错误定义"""
        # 注册网络相关错误
        network_def = ErrorDefinition(
            error_type=ErrorType.CONNECTION_TIMEOUT,
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.HIGH,
            description="网络连接超时",
            recovery_strategy=RecoveryStrategy.RETRY
        )
        
        # 注册验证相关错误
        validation_def = ErrorDefinition(
            error_type=ErrorType.DATA_FORMAT_INVALID,
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.MEDIUM,
            description="数据验证失败",
            recovery_strategy=RecoveryStrategy.LOG_ONLY
        )
        
        self.manager.register_error_definition(network_def)
        self.manager.register_error_definition(validation_def)
        
        network_defs = self.manager.get_errors_by_category(ErrorCategory.NETWORK)
        validation_defs = self.manager.get_errors_by_category(ErrorCategory.VALIDATION)
        
        assert len(network_defs) > 0
        assert len(validation_defs) > 0
        assert network_defs[0].error_type == ErrorType.CONNECTION_TIMEOUT
        assert validation_defs[0].error_type == ErrorType.DATA_FORMAT_INVALID
    
    def test_get_definitions_by_severity(self):
        """测试按严重程度获取错误定义"""
        high_def = ErrorDefinition(
            error_type=ErrorType.CONNECTION_TIMEOUT,
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.HIGH,
            description="高严重程度错误",
            recovery_strategy=RecoveryStrategy.RETRY
        )
        
        medium_def = ErrorDefinition(
            error_type=ErrorType.DATA_FORMAT_INVALID,
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.MEDIUM,
            description="中等严重程度错误",
            recovery_strategy=RecoveryStrategy.LOG_ONLY
        )
        
        self.manager.register_error_definition(high_def)
        self.manager.register_error_definition(medium_def)
        
        high_defs = self.manager.get_errors_by_severity(ErrorSeverity.HIGH)
        medium_defs = self.manager.get_errors_by_severity(ErrorSeverity.MEDIUM)
        
        assert len(high_defs) > 0
        assert len(medium_defs) > 0
        assert high_defs[0].severity == ErrorSeverity.HIGH
        assert medium_defs[0].severity == ErrorSeverity.MEDIUM
    
    def test_get_statistics(self):
        """测试获取统计信息"""
        # 清除默认定义以进行精确测试
        self.manager.clear_definitions()

        definitions = [
            ErrorDefinition(
                error_type=ErrorType.CONNECTION_TIMEOUT,
                category=ErrorCategory.NETWORK,
                severity=ErrorSeverity.HIGH,
                description="网络错误1",
                recovery_strategy=RecoveryStrategy.RETRY
            ),
            ErrorDefinition(
                error_type=ErrorType.API_RATE_LIMITED,
                category=ErrorCategory.NETWORK,
                severity=ErrorSeverity.MEDIUM,
                description="网络错误2",
                recovery_strategy=RecoveryStrategy.EXPONENTIAL_BACKOFF
            ),
            ErrorDefinition(
                error_type=ErrorType.DATA_FORMAT_INVALID,
                category=ErrorCategory.VALIDATION,
                severity=ErrorSeverity.LOW,
                description="验证错误",
                recovery_strategy=RecoveryStrategy.LOG_ONLY
            )
        ]
        
        for definition in definitions:
            self.manager.register_error_definition(definition)
        
        stats = self.manager.get_error_statistics()
        
        assert stats["total_definitions"] == 3
        assert stats["by_category"]["network"] == 2
        assert stats["by_category"]["validation"] == 1
        assert stats["by_severity"]["high"] == 1
        assert stats["by_severity"]["medium"] == 1
        assert stats["by_severity"]["low"] == 1
    
    def test_register_duplicate_definition(self):
        """测试注册重复错误定义"""
        definition1 = ErrorDefinition(
            error_type=ErrorType.CONNECTION_TIMEOUT,
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.HIGH,
            description="第一个定义",
            recovery_strategy=RecoveryStrategy.RETRY
        )
        
        definition2 = ErrorDefinition(
            error_type=ErrorType.CONNECTION_TIMEOUT,
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.MEDIUM,
            description="第二个定义",
            recovery_strategy=RecoveryStrategy.LOG_ONLY
        )
        
        self.manager.register_error_definition(definition1)
        self.manager.register_error_definition(definition2)  # 应该覆盖第一个
        
        retrieved = self.manager.get_error_definition(ErrorType.CONNECTION_TIMEOUT)
        assert retrieved is not None
        assert retrieved.description == "第二个定义"
        assert retrieved.severity == ErrorSeverity.MEDIUM
    
    def test_get_nonexistent_definition(self):
        """测试获取不存在的错误定义"""
        # 使用一个不太可能被默认注册的类型
        result = self.manager.get_error_definition(ErrorType.WORKFLOW_INTERRUPTED)
        assert result is None
    
    def test_clear_definitions(self):
        """测试清除错误定义"""
        # 首先确保有定义
        definition = ErrorDefinition(
            error_type=ErrorType.WORKFLOW_INTERRUPTED,
            category=ErrorCategory.BUSINESS,
            severity=ErrorSeverity.HIGH,
            description="测试定义",
            recovery_strategy=RecoveryStrategy.RETRY
        )
        self.manager.register_error_definition(definition)
        assert self.manager.get_error_statistics()["total_definitions"] > 0
        
        self.manager.clear_definitions()
        assert self.manager.get_error_statistics()["total_definitions"] == 0