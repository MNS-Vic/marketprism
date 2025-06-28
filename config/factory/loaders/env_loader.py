"""
环境变量配置加载器
"""

import os
import logging
from typing import Dict, Any, Optional, List, Union
import re


class EnvLoader:
    """环境变量配置加载器"""
    
    def __init__(self, prefix: str = "MARKETPRISM_"):
        self.prefix = prefix
        self.logger = logging.getLogger(__name__)
    
    def apply_env_overrides(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """应用环境变量覆盖"""
        result = config.copy()
        
        # 获取所有相关的环境变量
        env_vars = self._get_relevant_env_vars()
        
        for env_key, env_value in env_vars.items():
            # 转换环境变量名为配置路径
            config_path = self._env_key_to_config_path(env_key)
            
            if config_path:
                # 应用覆盖
                self._set_nested_value(result, config_path, self._parse_env_value(env_value))
                self.logger.debug(f"环境变量覆盖: {env_key} -> {config_path}")
        
        return result
    
    def _get_relevant_env_vars(self) -> Dict[str, str]:
        """获取相关的环境变量"""
        relevant_vars = {}
        
        for key, value in os.environ.items():
            if key.startswith(self.prefix):
                relevant_vars[key] = value
        
        return relevant_vars
    
    def _env_key_to_config_path(self, env_key: str) -> Optional[List[str]]:
        """将环境变量名转换为配置路径"""
        if not env_key.startswith(self.prefix):
            return None
        
        # 移除前缀
        config_key = env_key[len(self.prefix):]
        
        # 转换为小写并分割
        path_parts = config_key.lower().split('_')
        
        return path_parts
    
    def _set_nested_value(self, config: Dict[str, Any], path: List[str], value: Any):
        """设置嵌套配置值"""
        current = config
        
        # 导航到目标位置
        for key in path[:-1]:
            if key not in current:
                current[key] = {}
            elif not isinstance(current[key], dict):
                # 如果不是字典，创建新的字典
                current[key] = {}
            current = current[key]
        
        # 设置最终值
        current[path[-1]] = value
    
    def _parse_env_value(self, value: str) -> Union[str, int, float, bool, List, Dict]:
        """解析环境变量值"""
        # 去除首尾空格
        value = value.strip()
        
        # 布尔值
        if value.lower() in ('true', 'yes', '1', 'on'):
            return True
        elif value.lower() in ('false', 'no', '0', 'off'):
            return False
        
        # 数字
        try:
            # 尝试整数
            if '.' not in value:
                return int(value)
            else:
                return float(value)
        except ValueError:
            pass
        
        # JSON格式
        if value.startswith('{') or value.startswith('['):
            try:
                import json
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        
        # 逗号分隔的列表
        if ',' in value:
            return [item.strip() for item in value.split(',')]
        
        # 默认返回字符串
        return value
    
    def load_env_file(self, env_file_path: str) -> Dict[str, str]:
        """加载.env文件"""
        env_vars = {}
        
        try:
            with open(env_file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    
                    # 跳过空行和注释
                    if not line or line.startswith('#'):
                        continue
                    
                    # 解析键值对
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # 移除引号
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]
                        
                        env_vars[key] = value
                    else:
                        self.logger.warning(f"无效的环境变量格式 {env_file_path}:{line_num}: {line}")
            
            self.logger.info(f"成功加载环境文件: {env_file_path}")
            
        except FileNotFoundError:
            self.logger.warning(f"环境文件不存在: {env_file_path}")
        except Exception as e:
            self.logger.error(f"加载环境文件失败 {env_file_path}: {e}")
        
        return env_vars
    
    def apply_env_file(self, env_file_path: str, override_existing: bool = False):
        """应用.env文件到当前环境"""
        env_vars = self.load_env_file(env_file_path)
        
        for key, value in env_vars.items():
            if override_existing or key not in os.environ:
                os.environ[key] = value
    
    def get_env_config_mapping(self) -> Dict[str, str]:
        """获取环境变量到配置的映射"""
        return {
            # 数据库配置
            f"{self.prefix}REDIS_HOST": "infrastructure.redis.host",
            f"{self.prefix}REDIS_PORT": "infrastructure.redis.port",
            f"{self.prefix}REDIS_PASSWORD": "infrastructure.redis.password",
            f"{self.prefix}CLICKHOUSE_HOST": "infrastructure.clickhouse.host",
            f"{self.prefix}CLICKHOUSE_PORT": "infrastructure.clickhouse.port",
            f"{self.prefix}CLICKHOUSE_USER": "infrastructure.clickhouse.user",
            f"{self.prefix}CLICKHOUSE_PASSWORD": "infrastructure.clickhouse.password",
            f"{self.prefix}CLICKHOUSE_DATABASE": "infrastructure.clickhouse.database",
            
            # 服务配置
            f"{self.prefix}MONITORING_PORT": "services.monitoring-alerting.port",
            f"{self.prefix}DASHBOARD_PORT": "services.frontend-dashboard.port",
            f"{self.prefix}API_GATEWAY_PORT": "services.api-gateway.port",
            
            # 安全配置
            f"{self.prefix}JWT_SECRET": "core.security.jwt_secret",
            f"{self.prefix}API_KEY": "core.security.api_key",
            
            # 通知配置
            f"{self.prefix}SMTP_USERNAME": "services.monitoring-alerting.notifications.email.username",
            f"{self.prefix}SMTP_PASSWORD": "services.monitoring-alerting.notifications.email.password",
            f"{self.prefix}SMTP_SERVER": "services.monitoring-alerting.notifications.email.server",
            f"{self.prefix}SLACK_WEBHOOK_URL": "services.monitoring-alerting.notifications.slack.webhook_url",
            
            # 日志配置
            f"{self.prefix}LOG_LEVEL": "core.logging.level",
            f"{self.prefix}LOG_FORMAT": "core.logging.format",
            
            # 环境配置
            f"{self.prefix}ENVIRONMENT": "core.environment",
            f"{self.prefix}DEBUG": "core.debug",
        }
    
    def validate_required_env_vars(self, required_vars: List[str]) -> Dict[str, bool]:
        """验证必需的环境变量"""
        validation_result = {}
        
        for var in required_vars:
            validation_result[var] = var in os.environ and bool(os.environ[var])
            
            if not validation_result[var]:
                self.logger.warning(f"必需的环境变量未设置: {var}")
        
        return validation_result
    
    def get_env_summary(self) -> Dict[str, Any]:
        """获取环境变量摘要"""
        relevant_vars = self._get_relevant_env_vars()
        
        return {
            "prefix": self.prefix,
            "total_env_vars": len(os.environ),
            "relevant_vars": len(relevant_vars),
            "relevant_var_names": list(relevant_vars.keys()),
            "common_vars": {
                "ENVIRONMENT": os.getenv("ENVIRONMENT", "未设置"),
                "LOG_LEVEL": os.getenv("LOG_LEVEL", "未设置"),
                "DEBUG": os.getenv("DEBUG", "未设置"),
            }
        }
