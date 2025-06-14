"""
环境变量覆盖管理器

处理环境变量对配置的覆盖
"""

from datetime import datetime, timezone
import os
import re
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass
from enum import Enum
import structlog


class OverrideType(Enum):
    """覆盖类型"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST = "list"
    JSON = "json"


@dataclass
class OverrideRule:
    """覆盖规则"""
    config_name: str
    field_path: str
    env_var: str
    override_type: OverrideType = OverrideType.STRING
    default_value: Any = None
    required: bool = False
    description: str = ""


class EnvironmentOverrideManager:
    """
    环境变量覆盖管理器
    
    处理环境变量对配置的覆盖
    """
    
    def __init__(self, prefix: str = "MARKETPRISM_"):
        """
        初始化环境变量覆盖管理器
        
        Args:
            prefix: 环境变量前缀
        """
        self.prefix = prefix
        self.logger = structlog.get_logger(__name__)
        
        # 覆盖规则
        self.override_rules: Dict[str, List[OverrideRule]] = {}
        
        # 内置规则
        self._register_builtin_rules()
        
    def register_override_rule(self, rule: OverrideRule):
        """
        注册覆盖规则
        
        Args:
            rule: 覆盖规则
        """
        if rule.config_name not in self.override_rules:
            self.override_rules[rule.config_name] = []
            
        self.override_rules[rule.config_name].append(rule)
        
        self.logger.debug(
            "注册环境变量覆盖规则",
            config_name=rule.config_name,
            field_path=rule.field_path,
            env_var=rule.env_var
        )
        
    def get_overrides(self, config_name: str) -> Dict[str, Any]:
        """
        获取指定配置的环境变量覆盖
        
        Args:
            config_name: 配置名称
            
        Returns:
            Dict[str, Any]: 覆盖值字典
        """
        overrides = {}
        
        # 应用注册的规则
        rules = self.override_rules.get(config_name, [])
        for rule in rules:
            value = self._get_env_value(rule)
            if value is not None:
                self._set_nested_value(overrides, rule.field_path, value)
                
        # 自动发现环境变量
        auto_overrides = self._auto_discover_overrides(config_name)
        self._merge_overrides(overrides, auto_overrides)
        
        if overrides:
            self.logger.debug(
                "获取环境变量覆盖",
                config_name=config_name,
                overrides=list(overrides.keys())
            )
            
        return overrides
        
    def get_all_overrides(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有配置的环境变量覆盖
        
        Returns:
            Dict[str, Dict[str, Any]]: 配置名称到覆盖值的映射
        """
        all_overrides = {}
        
        # 获取注册的配置覆盖
        for config_name in self.override_rules:
            overrides = self.get_overrides(config_name)
            if overrides:
                all_overrides[config_name] = overrides
                
        return all_overrides
        
    def validate_required_overrides(self) -> Dict[str, List[str]]:
        """
        验证必需的环境变量覆盖
        
        Returns:
            Dict[str, List[str]]: 配置名称到缺失环境变量的映射
        """
        missing = {}
        
        for config_name, rules in self.override_rules.items():
            missing_vars = []
            
            for rule in rules:
                if rule.required and not os.getenv(rule.env_var):
                    missing_vars.append(rule.env_var)
                    
            if missing_vars:
                missing[config_name] = missing_vars
                
        return missing
        
    def list_env_vars(self, config_name: Optional[str] = None) -> List[str]:
        """
        列出相关的环境变量
        
        Args:
            config_name: 配置名称，如果不提供则返回所有
            
        Returns:
            List[str]: 环境变量列表
        """
        env_vars = []
        
        if config_name:
            rules = self.override_rules.get(config_name, [])
            env_vars.extend([rule.env_var for rule in rules])
        else:
            for rules in self.override_rules.values():
                env_vars.extend([rule.env_var for rule in rules])
                
        # 添加自动发现的环境变量
        for env_var in os.environ:
            if env_var.startswith(self.prefix):
                env_vars.append(env_var)
                
        return sorted(set(env_vars))
        
    def generate_env_template(self, config_name: Optional[str] = None) -> str:
        """
        生成环境变量模板
        
        Args:
            config_name: 配置名称，如果不提供则生成所有
            
        Returns:
            str: 环境变量模板
        """
        lines = [
            "# MarketPrism 环境变量配置",
            "# 复制此文件为 .env 并根据需要修改",
            ""
        ]
        
        if config_name:
            configs = {config_name: self.override_rules.get(config_name, [])}
        else:
            configs = self.override_rules
            
        for config_name, rules in configs.items():
            if rules:
                lines.append(f"# {config_name} 配置")
                
                for rule in rules:
                    # 添加描述
                    if rule.description:
                        lines.append(f"# {rule.description}")
                        
                    # 添加类型说明
                    type_hint = f"# 类型: {rule.override_type.value}"
                    if rule.default_value is not None:
                        type_hint += f", 默认值: {rule.default_value}"
                    if rule.required:
                        type_hint += " (必需)"
                    lines.append(type_hint)
                    
                    # 添加环境变量
                    value = rule.default_value if rule.default_value is not None else ""
                    if rule.required:
                        lines.append(f"{rule.env_var}={value}")
                    else:
                        lines.append(f"# {rule.env_var}={value}")
                        
                    lines.append("")
                    
        return "\n".join(lines)
        
    def _register_builtin_rules(self):
        """注册内置覆盖规则"""
        # 通用配置覆盖
        builtin_rules = [
            # 日志级别
            OverrideRule(
                config_name="logging",
                field_path="level",
                env_var=f"{self.prefix}LOG_LEVEL",
                override_type=OverrideType.STRING,
                default_value="INFO",
                description="日志级别"
            ),
            
            # 代理配置
            OverrideRule(
                config_name="proxy",
                field_path="enabled",
                env_var=f"{self.prefix}PROXY_ENABLED",
                override_type=OverrideType.BOOLEAN,
                default_value=False,
                description="是否启用代理"
            ),
            OverrideRule(
                config_name="proxy",
                field_path="host",
                env_var=f"{self.prefix}PROXY_HOST",
                override_type=OverrideType.STRING,
                description="代理主机"
            ),
            OverrideRule(
                config_name="proxy",
                field_path="port",
                env_var=f"{self.prefix}PROXY_PORT",
                override_type=OverrideType.INTEGER,
                description="代理端口"
            ),
            
            # NATS配置
            OverrideRule(
                config_name="nats",
                field_path="servers",
                env_var=f"{self.prefix}NATS_SERVERS",
                override_type=OverrideType.LIST,
                default_value=["nats://localhost:4222"],
                description="NATS服务器列表"
            ),
            
            # ClickHouse配置
            OverrideRule(
                config_name="storage",
                field_path="clickhouse.host",
                env_var=f"{self.prefix}CLICKHOUSE_HOST",
                override_type=OverrideType.STRING,
                default_value="localhost",
                description="ClickHouse主机"
            ),
            OverrideRule(
                config_name="storage",
                field_path="clickhouse.port",
                env_var=f"{self.prefix}CLICKHOUSE_PORT",
                override_type=OverrideType.INTEGER,
                default_value=9000,
                description="ClickHouse端口"
            ),
            
            # 交易所API密钥
            OverrideRule(
                config_name="exchange",
                field_path="binance.api_key",
                env_var=f"{self.prefix}BINANCE_API_KEY",
                override_type=OverrideType.STRING,
                description="Binance API密钥"
            ),
            OverrideRule(
                config_name="exchange",
                field_path="binance.api_secret",
                env_var=f"{self.prefix}BINANCE_API_SECRET",
                override_type=OverrideType.STRING,
                description="Binance API密钥"
            ),
            OverrideRule(
                config_name="exchange",
                field_path="okx.api_key",
                env_var=f"{self.prefix}OKX_API_KEY",
                override_type=OverrideType.STRING,
                description="OKX API密钥"
            ),
            OverrideRule(
                config_name="exchange",
                field_path="okx.api_secret",
                env_var=f"{self.prefix}OKX_API_SECRET",
                override_type=OverrideType.STRING,
                description="OKX API密钥"
            ),
            OverrideRule(
                config_name="exchange",
                field_path="okx.passphrase",
                env_var=f"{self.prefix}OKX_PASSPHRASE",
                override_type=OverrideType.STRING,
                description="OKX API密码"
            ),
        ]
        
        for rule in builtin_rules:
            self.register_override_rule(rule)
            
    def _get_env_value(self, rule: OverrideRule) -> Any:
        """获取环境变量值"""
        env_value = os.getenv(rule.env_var)
        
        if env_value is None:
            return rule.default_value if not rule.required else None
            
        # 类型转换
        try:
            if rule.override_type == OverrideType.STRING:
                return env_value
            elif rule.override_type == OverrideType.INTEGER:
                return int(env_value)
            elif rule.override_type == OverrideType.FLOAT:
                return float(env_value)
            elif rule.override_type == OverrideType.BOOLEAN:
                return env_value.lower() in ('true', '1', 'yes', 'on')
            elif rule.override_type == OverrideType.LIST:
                # 逗号分隔的列表
                return [item.strip() for item in env_value.split(',') if item.strip()]
            elif rule.override_type == OverrideType.JSON:
                import json
                return json.loads(env_value)
            else:
                return env_value
                
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            self.logger.warning(
                "环境变量类型转换失败",
                env_var=rule.env_var,
                value=env_value,
                expected_type=rule.override_type.value,
                error=str(e)
            )
            return None
            
    def _auto_discover_overrides(self, config_name: str) -> Dict[str, Any]:
        """自动发现环境变量覆盖"""
        overrides = {}
        
        # 查找匹配的环境变量
        config_prefix = f"{self.prefix}{config_name.upper()}_"
        
        for env_var, value in os.environ.items():
            if env_var.startswith(config_prefix):
                # 提取字段路径
                field_part = env_var[len(config_prefix):]
                field_path = field_part.lower().replace('_', '.')
                
                # 尝试类型推断
                converted_value = self._auto_convert_value(value)
                self._set_nested_value(overrides, field_path, converted_value)
                
        return overrides
        
    def _auto_convert_value(self, value: str) -> Any:
        """自动转换值类型"""
        # 布尔值
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'
            
        # 整数
        try:
            return int(value)
        except ValueError:
            pass
            
        # 浮点数
        try:
            return float(value)
        except ValueError:
            pass
            
        # 列表 (逗号分隔)
        if ',' in value:
            return [item.strip() for item in value.split(',') if item.strip()]
            
        # 字符串
        return value
        
    def _set_nested_value(self, target: Dict[str, Any], path: str, value: Any):
        """设置嵌套字典值"""
        parts = path.split('.')
        current = target
        
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
            
        current[parts[-1]] = value
        
    def _merge_overrides(self, target: Dict[str, Any], source: Dict[str, Any]):
        """合并覆盖值"""
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._merge_overrides(target[key], value)
            else:
                target[key] = value