"""
配置验证框架

提供配置验证的通用框架和常用验证器
"""

from abc import ABC, abstractmethod
from typing import Any, List, Dict, Optional, Union, Callable, Pattern
from dataclasses import dataclass
from enum import Enum
import re
import ipaddress
from urllib.parse import urlparse
from pathlib import Path


class ValidationSeverity(Enum):
    """验证严重级别"""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationResult:
    """验证结果"""
    field_name: str
    severity: ValidationSeverity
    message: str
    value: Any = None
    suggestion: Optional[str] = None


class ValidationError(Exception):
    """配置验证错误"""
    
    def __init__(self, message: str, results: List[ValidationResult] = None):
        super().__init__(message)
        self.results = results or []


class ValidatorInterface(ABC):
    """验证器接口"""
    
    @abstractmethod
    def validate(self, value: Any, field_name: str = "") -> List[ValidationResult]:
        """
        验证值
        
        Args:
            value: 要验证的值
            field_name: 字段名称
            
        Returns:
            List[ValidationResult]: 验证结果列表
        """
        pass


class RequiredValidator(ValidatorInterface):
    """必填验证器"""
    
    def __init__(self, message: str = "字段不能为空"):
        self.message = message
        
    def validate(self, value: Any, field_name: str = "") -> List[ValidationResult]:
        if value is None or (isinstance(value, str) and not value.strip()):
            return [ValidationResult(
                field_name=field_name,
                severity=ValidationSeverity.ERROR,
                message=self.message,
                value=value
            )]
        return []


class TypeValidator(ValidatorInterface):
    """类型验证器"""
    
    def __init__(self, expected_type: Union[type, tuple], message: str = None):
        self.expected_type = expected_type
        self.message = message or f"值必须是 {expected_type} 类型"
        
    def validate(self, value: Any, field_name: str = "") -> List[ValidationResult]:
        if value is not None and not isinstance(value, self.expected_type):
            return [ValidationResult(
                field_name=field_name,
                severity=ValidationSeverity.ERROR,
                message=self.message,
                value=value,
                suggestion=f"期望类型: {self.expected_type}, 实际类型: {type(value)}"
            )]
        return []


class RangeValidator(ValidatorInterface):
    """范围验证器"""
    
    def __init__(self, min_value: Optional[Union[int, float]] = None,
                 max_value: Optional[Union[int, float]] = None,
                 inclusive: bool = True):
        self.min_value = min_value
        self.max_value = max_value
        self.inclusive = inclusive
        
    def validate(self, value: Any, field_name: str = "") -> List[ValidationResult]:
        if value is None:
            return []
            
        if not isinstance(value, (int, float)):
            return [ValidationResult(
                field_name=field_name,
                severity=ValidationSeverity.ERROR,
                message="值必须是数字类型",
                value=value
            )]
            
        results = []
        
        if self.min_value is not None:
            if self.inclusive and value < self.min_value:
                results.append(ValidationResult(
                    field_name=field_name,
                    severity=ValidationSeverity.ERROR,
                    message=f"值不能小于 {self.min_value}",
                    value=value
                ))
            elif not self.inclusive and value <= self.min_value:
                results.append(ValidationResult(
                    field_name=field_name,
                    severity=ValidationSeverity.ERROR,
                    message=f"值必须大于 {self.min_value}",
                    value=value
                ))
                
        if self.max_value is not None:
            if self.inclusive and value > self.max_value:
                results.append(ValidationResult(
                    field_name=field_name,
                    severity=ValidationSeverity.ERROR,
                    message=f"值不能大于 {self.max_value}",
                    value=value
                ))
            elif not self.inclusive and value >= self.max_value:
                results.append(ValidationResult(
                    field_name=field_name,
                    severity=ValidationSeverity.ERROR,
                    message=f"值必须小于 {self.max_value}",
                    value=value
                ))
                
        return results


class LengthValidator(ValidatorInterface):
    """长度验证器"""
    
    def __init__(self, min_length: Optional[int] = None,
                 max_length: Optional[int] = None):
        self.min_length = min_length
        self.max_length = max_length
        
    def validate(self, value: Any, field_name: str = "") -> List[ValidationResult]:
        if value is None:
            return []
            
        if not hasattr(value, '__len__'):
            return [ValidationResult(
                field_name=field_name,
                severity=ValidationSeverity.ERROR,
                message="值必须有长度属性",
                value=value
            )]
            
        length = len(value)
        results = []
        
        if self.min_length is not None and length < self.min_length:
            results.append(ValidationResult(
                field_name=field_name,
                severity=ValidationSeverity.ERROR,
                message=f"长度不能小于 {self.min_length}",
                value=value,
                suggestion=f"当前长度: {length}"
            ))
            
        if self.max_length is not None and length > self.max_length:
            results.append(ValidationResult(
                field_name=field_name,
                severity=ValidationSeverity.ERROR,
                message=f"长度不能大于 {self.max_length}",
                value=value,
                suggestion=f"当前长度: {length}"
            ))
            
        return results


class RegexValidator(ValidatorInterface):
    """正则表达式验证器"""
    
    def __init__(self, pattern: Union[str, Pattern], message: str = "格式不正确"):
        self.pattern = re.compile(pattern) if isinstance(pattern, str) else pattern
        self.message = message
        
    def validate(self, value: Any, field_name: str = "") -> List[ValidationResult]:
        if value is None:
            return []
            
        if not isinstance(value, str):
            return [ValidationResult(
                field_name=field_name,
                severity=ValidationSeverity.ERROR,
                message="值必须是字符串类型",
                value=value
            )]
            
        if not self.pattern.match(value):
            return [ValidationResult(
                field_name=field_name,
                severity=ValidationSeverity.ERROR,
                message=self.message,
                value=value,
                suggestion=f"期望模式: {self.pattern.pattern}"
            )]
            
        return []


class ChoiceValidator(ValidatorInterface):
    """选择值验证器"""
    
    def __init__(self, choices: List[Any], case_sensitive: bool = True):
        self.choices = choices
        self.case_sensitive = case_sensitive
        
    def validate(self, value: Any, field_name: str = "") -> List[ValidationResult]:
        if value is None:
            return []
            
        choices = self.choices
        check_value = value
        
        if not self.case_sensitive and isinstance(value, str):
            choices = [str(c).lower() for c in self.choices]
            check_value = value.lower()
            
        if check_value not in choices:
            return [ValidationResult(
                field_name=field_name,
                severity=ValidationSeverity.ERROR,
                message=f"值必须是以下选项之一: {self.choices}",
                value=value
            )]
            
        return []


class URLValidator(ValidatorInterface):
    """URL验证器"""
    
    def __init__(self, allowed_schemes: List[str] = None):
        self.allowed_schemes = allowed_schemes or ['http', 'https']
        
    def validate(self, value: Any, field_name: str = "") -> List[ValidationResult]:
        if value is None:
            return []
            
        if not isinstance(value, str):
            return [ValidationResult(
                field_name=field_name,
                severity=ValidationSeverity.ERROR,
                message="URL必须是字符串类型",
                value=value
            )]
            
        try:
            parsed = urlparse(value)
            if not parsed.scheme:
                return [ValidationResult(
                    field_name=field_name,
                    severity=ValidationSeverity.ERROR,
                    message="URL缺少协议",
                    value=value
                )]
                
            if parsed.scheme not in self.allowed_schemes:
                return [ValidationResult(
                    field_name=field_name,
                    severity=ValidationSeverity.ERROR,
                    message=f"不支持的协议: {parsed.scheme}",
                    value=value,
                    suggestion=f"支持的协议: {self.allowed_schemes}"
                )]
                
            if not parsed.netloc:
                return [ValidationResult(
                    field_name=field_name,
                    severity=ValidationSeverity.ERROR,
                    message="URL缺少主机名",
                    value=value
                )]
                
        except Exception as e:
            return [ValidationResult(
                field_name=field_name,
                severity=ValidationSeverity.ERROR,
                message=f"无效的URL格式: {e}",
                value=value
            )]
            
        return []


class IPAddressValidator(ValidatorInterface):
    """IP地址验证器"""
    
    def __init__(self, version: Optional[int] = None):
        self.version = version  # 4, 6, or None for both
        
    def validate(self, value: Any, field_name: str = "") -> List[ValidationResult]:
        if value is None:
            return []
            
        if not isinstance(value, str):
            return [ValidationResult(
                field_name=field_name,
                severity=ValidationSeverity.ERROR,
                message="IP地址必须是字符串类型",
                value=value
            )]
            
        try:
            ip = ipaddress.ip_address(value)
            if self.version == 4 and not isinstance(ip, ipaddress.IPv4Address):
                return [ValidationResult(
                    field_name=field_name,
                    severity=ValidationSeverity.ERROR,
                    message="必须是IPv4地址",
                    value=value
                )]
            elif self.version == 6 and not isinstance(ip, ipaddress.IPv6Address):
                return [ValidationResult(
                    field_name=field_name,
                    severity=ValidationSeverity.ERROR,
                    message="必须是IPv6地址",
                    value=value
                )]
        except ValueError as e:
            return [ValidationResult(
                field_name=field_name,
                severity=ValidationSeverity.ERROR,
                message=f"无效的IP地址: {e}",
                value=value
            )]
            
        return []


class FilePathValidator(ValidatorInterface):
    """文件路径验证器"""
    
    def __init__(self, must_exist: bool = False, must_be_file: bool = True):
        self.must_exist = must_exist
        self.must_be_file = must_be_file
        
    def validate(self, value: Any, field_name: str = "") -> List[ValidationResult]:
        if value is None:
            return []
            
        if not isinstance(value, (str, Path)):
            return [ValidationResult(
                field_name=field_name,
                severity=ValidationSeverity.ERROR,
                message="路径必须是字符串或Path对象",
                value=value
            )]
            
        path = Path(value)
        results = []
        
        if self.must_exist and not path.exists():
            results.append(ValidationResult(
                field_name=field_name,
                severity=ValidationSeverity.ERROR,
                message="路径不存在",
                value=value
            ))
        elif path.exists():
            if self.must_be_file and not path.is_file():
                results.append(ValidationResult(
                    field_name=field_name,
                    severity=ValidationSeverity.ERROR,
                    message="路径必须是文件",
                    value=value
                ))
                
        return results


class CustomValidator(ValidatorInterface):
    """自定义验证器"""
    
    def __init__(self, validator_func: Callable[[Any], bool], 
                 message: str = "验证失败"):
        self.validator_func = validator_func
        self.message = message
        
    def validate(self, value: Any, field_name: str = "") -> List[ValidationResult]:
        try:
            if not self.validator_func(value):
                return [ValidationResult(
                    field_name=field_name,
                    severity=ValidationSeverity.ERROR,
                    message=self.message,
                    value=value
                )]
        except Exception as e:
            return [ValidationResult(
                field_name=field_name,
                severity=ValidationSeverity.ERROR,
                message=f"验证器执行错误: {e}",
                value=value
            )]
            
        return []


class ConfigValidator:
    """配置验证器"""
    
    def __init__(self):
        self.field_validators: Dict[str, List[ValidatorInterface]] = {}
        
    def add_validator(self, field_name: str, validator: ValidatorInterface):
        """
        添加字段验证器
        
        Args:
            field_name: 字段名称
            validator: 验证器
        """
        if field_name not in self.field_validators:
            self.field_validators[field_name] = []
        self.field_validators[field_name].append(validator)
        
    def validate_field(self, field_name: str, value: Any) -> List[ValidationResult]:
        """
        验证单个字段
        
        Args:
            field_name: 字段名称
            value: 字段值
            
        Returns:
            List[ValidationResult]: 验证结果列表
        """
        results = []
        validators = self.field_validators.get(field_name, [])
        
        for validator in validators:
            try:
                field_results = validator.validate(value, field_name)
                results.extend(field_results)
            except Exception as e:
                results.append(ValidationResult(
                    field_name=field_name,
                    severity=ValidationSeverity.ERROR,
                    message=f"验证器执行错误: {e}",
                    value=value
                ))
                
        return results
        
    def validate_config(self, config_dict: Dict[str, Any]) -> List[ValidationResult]:
        """
        验证整个配置
        
        Args:
            config_dict: 配置字典
            
        Returns:
            List[ValidationResult]: 验证结果列表
        """
        all_results = []
        
        # 验证已定义的字段
        for field_name in self.field_validators:
            value = config_dict.get(field_name)
            results = self.validate_field(field_name, value)
            all_results.extend(results)
            
        return all_results
        
    def is_valid(self, config_dict: Dict[str, Any]) -> bool:
        """
        检查配置是否有效
        
        Args:
            config_dict: 配置字典
            
        Returns:
            bool: 是否有效
        """
        results = self.validate_config(config_dict)
        return not any(r.severity == ValidationSeverity.ERROR for r in results)
        
    def get_errors(self, config_dict: Dict[str, Any]) -> List[ValidationResult]:
        """
        获取配置错误
        
        Args:
            config_dict: 配置字典
            
        Returns:
            List[ValidationResult]: 错误列表
        """
        results = self.validate_config(config_dict)
        return [r for r in results if r.severity == ValidationSeverity.ERROR]
        
    def get_warnings(self, config_dict: Dict[str, Any]) -> List[ValidationResult]:
        """
        获取配置警告
        
        Args:
            config_dict: 配置字典
            
        Returns:
            List[ValidationResult]: 警告列表
        """
        results = self.validate_config(config_dict)
        return [r for r in results if r.severity == ValidationSeverity.WARNING]