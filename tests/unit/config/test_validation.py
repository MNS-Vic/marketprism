"""
配置验证测试
"""

import pytest
import sys
from pathlib import Path
from typing import Dict, Any

# 添加项目路径到sys.path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "services" / "python-collector" / "src"))

from core.config.validators import (
    ConfigValidator,
    RequiredValidator,
    TypeValidator,
    RangeValidator,
    LengthValidator,
    RegexValidator,
    ChoiceValidator,
    URLValidator,
    IPAddressValidator,
    FilePathValidator,
    CustomValidator,
    ValidationResult,
    ValidationSeverity
)


class TestValidators:
    """验证器测试"""
    
    def test_required_validator(self):
        """测试必填验证器"""
        validator = RequiredValidator()
        
        # 测试有效值
        assert len(validator.validate("valid_value")) == 0
        assert len(validator.validate(123)) == 0
        
        # 测试无效值
        results = validator.validate(None)
        assert len(results) == 1
        assert results[0].severity == ValidationSeverity.ERROR
        
        results = validator.validate("")
        assert len(results) == 1
        assert results[0].severity == ValidationSeverity.ERROR
        
        results = validator.validate("   ")
        assert len(results) == 1
        assert results[0].severity == ValidationSeverity.ERROR
        
    def test_type_validator(self):
        """测试类型验证器"""
        # 字符串类型验证
        validator = TypeValidator(str)
        assert len(validator.validate("test")) == 0
        assert len(validator.validate(123)) == 1
        
        # 数字类型验证
        validator = TypeValidator((int, float))
        assert len(validator.validate(123)) == 0
        assert len(validator.validate(12.3)) == 0
        assert len(validator.validate("123")) == 1
        
        # None值测试
        assert len(validator.validate(None)) == 0
        
    def test_range_validator(self):
        """测试范围验证器"""
        validator = RangeValidator(min_value=0, max_value=100)
        
        # 有效值
        assert len(validator.validate(50)) == 0
        assert len(validator.validate(0)) == 0
        assert len(validator.validate(100)) == 0
        
        # 无效值
        assert len(validator.validate(-1)) == 1
        assert len(validator.validate(101)) == 1
        
        # 非数字类型
        assert len(validator.validate("50")) == 1
        
        # None值
        assert len(validator.validate(None)) == 0
        
    def test_length_validator(self):
        """测试长度验证器"""
        validator = LengthValidator(min_length=2, max_length=10)
        
        # 有效值
        assert len(validator.validate("test")) == 0
        assert len(validator.validate([1, 2, 3])) == 0
        
        # 无效值
        assert len(validator.validate("a")) == 1  # 太短
        assert len(validator.validate("12345678901")) == 1  # 太长
        
        # 无长度属性的对象
        assert len(validator.validate(123)) == 1
        
    def test_regex_validator(self):
        """测试正则表达式验证器"""
        validator = RegexValidator(r"^[a-zA-Z0-9]+$", "只能包含字母和数字")
        
        # 有效值
        assert len(validator.validate("test123")) == 0
        assert len(validator.validate("ABC")) == 0
        
        # 无效值
        assert len(validator.validate("test-123")) == 1
        assert len(validator.validate("test@123")) == 1
        
        # 非字符串类型
        assert len(validator.validate(123)) == 1
        
    def test_choice_validator(self):
        """测试选择值验证器"""
        validator = ChoiceValidator(["option1", "option2", "option3"])
        
        # 有效值
        assert len(validator.validate("option1")) == 0
        assert len(validator.validate("option2")) == 0
        
        # 无效值
        assert len(validator.validate("option4")) == 1
        assert len(validator.validate("OPTION1")) == 1  # 区分大小写
        
        # 不区分大小写
        validator = ChoiceValidator(["Option1", "Option2"], case_sensitive=False)
        assert len(validator.validate("option1")) == 0
        assert len(validator.validate("OPTION1")) == 0
        
    def test_url_validator(self):
        """测试URL验证器"""
        validator = URLValidator()
        
        # 有效URL
        assert len(validator.validate("https://example.com")) == 0
        assert len(validator.validate("http://localhost:8080/path")) == 0
        
        # 无效URL
        assert len(validator.validate("not-a-url")) == 1
        assert len(validator.validate("ftp://example.com")) == 1  # 不支持的协议
        assert len(validator.validate("https://")) == 1  # 缺少主机名
        
        # 自定义允许的协议
        validator = URLValidator(allowed_schemes=["ftp"])
        assert len(validator.validate("ftp://example.com")) == 0
        assert len(validator.validate("https://example.com")) == 1
        
    def test_ip_address_validator(self):
        """测试IP地址验证器"""
        validator = IPAddressValidator()
        
        # 有效IP地址
        assert len(validator.validate("192.168.1.1")) == 0
        assert len(validator.validate("::1")) == 0
        
        # 无效IP地址
        assert len(validator.validate("999.999.999.999")) == 1
        assert len(validator.validate("not-an-ip")) == 1
        
        # IPv4专用验证器
        validator = IPAddressValidator(version=4)
        assert len(validator.validate("192.168.1.1")) == 0
        assert len(validator.validate("::1")) == 1
        
        # IPv6专用验证器
        validator = IPAddressValidator(version=6)
        assert len(validator.validate("::1")) == 0
        assert len(validator.validate("192.168.1.1")) == 1
        
    def test_custom_validator(self):
        """测试自定义验证器"""
        def is_even(value):
            return isinstance(value, int) and value % 2 == 0
            
        validator = CustomValidator(is_even, "值必须是偶数")
        
        # 有效值
        assert len(validator.validate(2)) == 0
        assert len(validator.validate(100)) == 0
        
        # 无效值
        assert len(validator.validate(3)) == 1
        assert len(validator.validate("2")) == 1
        
        # 异常处理
        def raise_error(value):
            raise ValueError("测试异常")
            
        validator = CustomValidator(raise_error)
        results = validator.validate("test")
        assert len(results) == 1
        assert "验证器执行错误" in results[0].message


class TestConfigValidator:
    """配置验证器测试"""
    
    def test_add_validator(self):
        """测试添加验证器"""
        config_validator = ConfigValidator()
        
        # 添加验证器
        config_validator.add_validator("name", RequiredValidator())
        config_validator.add_validator("name", LengthValidator(min_length=2))
        config_validator.add_validator("age", TypeValidator(int))
        config_validator.add_validator("age", RangeValidator(min_value=0, max_value=150))
        
        assert len(config_validator.field_validators["name"]) == 2
        assert len(config_validator.field_validators["age"]) == 2
        
    def test_validate_field(self):
        """测试验证单个字段"""
        config_validator = ConfigValidator()
        config_validator.add_validator("name", RequiredValidator())
        config_validator.add_validator("name", LengthValidator(min_length=2))
        
        # 有效值
        results = config_validator.validate_field("name", "John")
        assert len(results) == 0
        
        # 无效值 - 空值
        results = config_validator.validate_field("name", "")
        assert len(results) >= 1
        assert any(r.severity == ValidationSeverity.ERROR for r in results)
        
        # 无效值 - 太短
        results = config_validator.validate_field("name", "J")
        assert len(results) >= 1
        assert any(r.severity == ValidationSeverity.ERROR for r in results)
        
    def test_validate_config(self):
        """测试验证整个配置"""
        config_validator = ConfigValidator()
        config_validator.add_validator("name", RequiredValidator())
        config_validator.add_validator("age", TypeValidator(int))
        config_validator.add_validator("age", RangeValidator(min_value=0, max_value=150))
        config_validator.add_validator("email", RegexValidator(r".+@.+\..+", "无效的邮箱格式"))
        
        # 有效配置
        config_dict = {
            "name": "John Doe",
            "age": 30,
            "email": "john@example.com"
        }
        results = config_validator.validate_config(config_dict)
        errors = [r for r in results if r.severity == ValidationSeverity.ERROR]
        assert len(errors) == 0
        
        # 无效配置
        config_dict = {
            "name": "",  # 空名称
            "age": "thirty",  # 错误类型
            "email": "invalid-email"  # 无效邮箱
        }
        results = config_validator.validate_config(config_dict)
        errors = [r for r in results if r.severity == ValidationSeverity.ERROR]
        assert len(errors) >= 3
        
    def test_is_valid(self):
        """测试配置有效性检查"""
        config_validator = ConfigValidator()
        config_validator.add_validator("name", RequiredValidator())
        config_validator.add_validator("age", TypeValidator(int))
        
        # 有效配置
        assert config_validator.is_valid({"name": "John", "age": 30})
        
        # 无效配置
        assert not config_validator.is_valid({"name": "", "age": "thirty"})
        
    def test_get_errors_and_warnings(self):
        """测试获取错误和警告"""
        config_validator = ConfigValidator()
        config_validator.add_validator("name", RequiredValidator())
        
        # 创建一个会产生警告的验证器
        class WarningValidator:
            def validate(self, value, field_name=""):
                if value and len(value) > 20:
                    return [ValidationResult(
                        field_name=field_name,
                        severity=ValidationSeverity.WARNING,
                        message="名称可能过长",
                        value=value
                    )]
                return []
                
        config_validator.add_validator("name", WarningValidator())
        
        config_dict = {"name": "This is a very long name that might be too long"}
        
        errors = config_validator.get_errors(config_dict)
        warnings = config_validator.get_warnings(config_dict)
        
        assert len(errors) == 0  # 没有错误
        assert len(warnings) == 1  # 有一个警告
        assert warnings[0].severity == ValidationSeverity.WARNING