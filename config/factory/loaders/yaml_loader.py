"""
YAML配置文件加载器
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import re


class YamlLoader:
    """YAML配置文件加载器"""
    
    def __init__(self, config_root: Path):
        self.config_root = Path(config_root)
        self.logger = logging.getLogger(__name__)
        
        # 确保配置目录存在
        if not self.config_root.exists():
            raise FileNotFoundError(f"配置根目录不存在: {self.config_root}")
    
    def load_base_config(self) -> Dict[str, Any]:
        """加载基础配置"""
        base_config_path = self.config_root / "core" / "base.yaml"
        return self._load_yaml_file(base_config_path, required=False)
    
    def load_environment_config(self, environment: str) -> Dict[str, Any]:
        """加载环境配置"""
        env_config_path = self.config_root / "environments" / f"{environment}.yaml"
        return self._load_yaml_file(env_config_path, required=False)
    
    def load_service_config(self, service_name: str, config_type: str = "service") -> Dict[str, Any]:
        """加载服务配置"""
        service_dir = self.config_root / "services" / service_name
        
        if not service_dir.exists():
            self.logger.warning(f"服务配置目录不存在: {service_dir}")
            return {}
        
        # 加载主配置文件
        main_config_path = service_dir / f"{config_type}.yaml"
        main_config = self._load_yaml_file(main_config_path, required=False)
        
        # 加载其他配置文件并合并
        all_configs = [main_config]
        
        for config_file in service_dir.glob("*.yaml"):
            if config_file.name != f"{config_type}.yaml":
                config = self._load_yaml_file(config_file, required=False)
                if config:
                    all_configs.append(config)
        
        return self._merge_configs(all_configs)
    
    def load_infrastructure_config(self, component: str, config_type: str) -> Dict[str, Any]:
        """加载基础设施配置"""
        infra_config_path = self.config_root / "infrastructure" / component / f"{config_type}.yaml"
        return self._load_yaml_file(infra_config_path, required=False)
    
    def load_schema(self, schema_name: str) -> Dict[str, Any]:
        """加载配置模式"""
        schema_path = self.config_root / "schemas" / f"{schema_name}.yaml"
        return self._load_yaml_file(schema_path, required=False)
    
    def load_template(self, template_name: str) -> Dict[str, Any]:
        """加载配置模板"""
        template_path = self.config_root / "templates" / f"{template_name}.yaml.template"
        return self._load_yaml_file(template_path, required=False)
    
    def _load_yaml_file(self, file_path: Path, required: bool = True) -> Dict[str, Any]:
        """加载单个YAML文件"""
        try:
            if not file_path.exists():
                if required:
                    raise FileNotFoundError(f"配置文件不存在: {file_path}")
                else:
                    self.logger.debug(f"可选配置文件不存在: {file_path}")
                    return {}
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # 处理环境变量替换
                content = self._substitute_variables(content)
                
                # 解析YAML
                config = yaml.safe_load(content) or {}
                
                self.logger.debug(f"成功加载配置文件: {file_path}")
                return config
                
        except yaml.YAMLError as e:
            self.logger.error(f"YAML解析错误 {file_path}: {e}")
            raise
        except Exception as e:
            self.logger.error(f"加载配置文件失败 {file_path}: {e}")
            raise
    
    def _substitute_variables(self, content: str) -> str:
        """替换配置中的变量"""
        # 替换环境变量 ${VAR_NAME} 或 ${VAR_NAME:default_value}
        def replace_env_var(match):
            var_expr = match.group(1)
            if ':' in var_expr:
                var_name, default_value = var_expr.split(':', 1)
                return os.getenv(var_name.strip(), default_value.strip())
            else:
                var_name = var_expr.strip()
                value = os.getenv(var_name)
                if value is None:
                    self.logger.warning(f"环境变量未设置: {var_name}")
                    return match.group(0)  # 保持原样
                return value
        
        # 匹配 ${...} 模式
        content = re.sub(r'\$\{([^}]+)\}', replace_env_var, content)
        
        return content
    
    def _merge_configs(self, configs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """合并多个配置"""
        result = {}
        for config in configs:
            if config:
                result = self._deep_merge(result, config)
        return result
    
    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """深度合并字典"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    def list_available_configs(self) -> Dict[str, List[str]]:
        """列出所有可用的配置"""
        available = {
            "environments": [],
            "services": [],
            "infrastructure": {},
            "schemas": [],
            "templates": []
        }
        
        # 环境配置
        env_dir = self.config_root / "environments"
        if env_dir.exists():
            available["environments"] = [
                f.stem for f in env_dir.glob("*.yaml")
            ]
        
        # 服务配置
        services_dir = self.config_root / "services"
        if services_dir.exists():
            available["services"] = [
                d.name for d in services_dir.iterdir() if d.is_dir()
            ]
        
        # 基础设施配置
        infra_dir = self.config_root / "infrastructure"
        if infra_dir.exists():
            for component_dir in infra_dir.iterdir():
                if component_dir.is_dir():
                    available["infrastructure"][component_dir.name] = [
                        f.stem for f in component_dir.glob("*.yaml")
                    ]
        
        # 模式配置
        schemas_dir = self.config_root / "schemas"
        if schemas_dir.exists():
            available["schemas"] = [
                f.stem for f in schemas_dir.glob("*.yaml")
            ]
        
        # 模板配置
        templates_dir = self.config_root / "templates"
        if templates_dir.exists():
            available["templates"] = [
                f.stem.replace('.yaml', '') for f in templates_dir.glob("*.yaml.template")
            ]
        
        return available
    
    def validate_yaml_syntax(self, file_path: Path) -> bool:
        """验证YAML文件语法"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                yaml.safe_load(f)
            return True
        except yaml.YAMLError as e:
            self.logger.error(f"YAML语法错误 {file_path}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"文件读取错误 {file_path}: {e}")
            return False
    
    def get_file_info(self, file_path: Path) -> Dict[str, Any]:
        """获取配置文件信息"""
        if not file_path.exists():
            return {}
        
        stat = file_path.stat()
        return {
            "path": str(file_path),
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "is_valid": self.validate_yaml_syntax(file_path)
        }
