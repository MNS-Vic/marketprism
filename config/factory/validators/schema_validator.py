"""
配置模式验证器
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import yaml


class SchemaValidator:
    """配置模式验证器"""
    
    def __init__(self, schemas_dir: Path):
        self.schemas_dir = Path(schemas_dir)
        self.logger = logging.getLogger(__name__)
        self.schemas_cache = {}
        
        # 尝试导入jsonschema
        try:
            import jsonschema
            self.jsonschema = jsonschema
            self.has_jsonschema = True
        except ImportError:
            self.logger.warning("jsonschema库未安装，将使用基础验证")
            self.has_jsonschema = False
    
    def validate(self, config: Dict[str, Any], schema_name: str = None) -> bool:
        """验证配置"""
        try:
            if not schema_name:
                # 尝试从配置中推断模式名称
                schema_name = self._infer_schema_name(config)
            
            if not schema_name:
                self.logger.warning("无法确定配置模式，跳过验证")
                return True
            
            # 加载模式
            schema = self._load_schema(schema_name)
            if not schema:
                self.logger.warning(f"模式不存在: {schema_name}")
                return True
            
            # 执行验证
            if self.has_jsonschema:
                return self._validate_with_jsonschema(config, schema)
            else:
                return self._validate_basic(config, schema)
                
        except Exception as e:
            self.logger.error(f"配置验证失败: {e}")
            return False
    
    def _infer_schema_name(self, config: Dict[str, Any]) -> Optional[str]:
        """从配置推断模式名称"""
        # 检查配置中是否有明确的模式指定
        if 'schema' in config:
            return config['schema']
        
        # 根据配置结构推断
        if 'service' in config:
            return 'service-schema'
        elif 'database' in config or any(db in config for db in ['redis', 'clickhouse', 'postgresql']):
            return 'database-schema'
        elif 'monitoring' in config or 'prometheus' in config or 'grafana' in config:
            return 'monitoring-schema'
        elif 'security' in config or 'auth' in config:
            return 'security-schema'
        
        return None
    
    def _load_schema(self, schema_name: str) -> Optional[Dict[str, Any]]:
        """加载配置模式"""
        # 检查缓存
        if schema_name in self.schemas_cache:
            return self.schemas_cache[schema_name]
        
        schema_file = self.schemas_dir / f"{schema_name}.yaml"
        
        try:
            if not schema_file.exists():
                return None
            
            with open(schema_file, 'r', encoding='utf-8') as f:
                schema = yaml.safe_load(f)
            
            # 缓存模式
            self.schemas_cache[schema_name] = schema
            self.logger.debug(f"成功加载模式: {schema_name}")
            
            return schema
            
        except Exception as e:
            self.logger.error(f"加载模式失败 {schema_name}: {e}")
            return None
    
    def _validate_with_jsonschema(self, config: Dict[str, Any], schema: Dict[str, Any]) -> bool:
        """使用jsonschema进行验证"""
        try:
            self.jsonschema.validate(config, schema)
            self.logger.debug("JSON Schema验证通过")
            return True
        except self.jsonschema.ValidationError as e:
            self.logger.error(f"JSON Schema验证失败: {e.message}")
            return False
        except Exception as e:
            self.logger.error(f"JSON Schema验证异常: {e}")
            return False
    
    def _validate_basic(self, config: Dict[str, Any], schema: Dict[str, Any]) -> bool:
        """基础配置验证"""
        try:
            # 检查必需字段
            required_fields = schema.get('required', [])
            for field in required_fields:
                if not self._check_field_exists(config, field):
                    self.logger.error(f"必需字段缺失: {field}")
                    return False
            
            # 检查字段类型
            properties = schema.get('properties', {})
            for field_name, field_schema in properties.items():
                if field_name in config:
                    if not self._validate_field_type(config[field_name], field_schema):
                        self.logger.error(f"字段类型错误: {field_name}")
                        return False
            
            self.logger.debug("基础验证通过")
            return True
            
        except Exception as e:
            self.logger.error(f"基础验证失败: {e}")
            return False
    
    def _check_field_exists(self, config: Dict[str, Any], field_path: str) -> bool:
        """检查字段是否存在（支持嵌套路径）"""
        keys = field_path.split('.')
        current = config
        
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                return False
            current = current[key]
        
        return True
    
    def _validate_field_type(self, value: Any, field_schema: Dict[str, Any]) -> bool:
        """验证字段类型"""
        expected_type = field_schema.get('type')
        
        if not expected_type:
            return True
        
        type_mapping = {
            'string': str,
            'integer': int,
            'number': (int, float),
            'boolean': bool,
            'array': list,
            'object': dict
        }
        
        expected_python_type = type_mapping.get(expected_type)
        if expected_python_type:
            return isinstance(value, expected_python_type)
        
        return True
    
    def create_schema_template(self, schema_name: str, config_sample: Dict[str, Any]) -> Dict[str, Any]:
        """从配置样本创建模式模板"""
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": f"{schema_name} Configuration Schema",
            "type": "object",
            "properties": {},
            "required": []
        }
        
        # 递归生成属性模式
        schema["properties"] = self._generate_properties_schema(config_sample)
        
        return schema
    
    def _generate_properties_schema(self, obj: Any) -> Dict[str, Any]:
        """递归生成属性模式"""
        if isinstance(obj, dict):
            properties = {}
            for key, value in obj.items():
                properties[key] = self._generate_value_schema(value)
            return properties
        else:
            return self._generate_value_schema(obj)
    
    def _generate_value_schema(self, value: Any) -> Dict[str, Any]:
        """生成值的模式"""
        if isinstance(value, str):
            return {"type": "string"}
        elif isinstance(value, bool):
            return {"type": "boolean"}
        elif isinstance(value, int):
            return {"type": "integer"}
        elif isinstance(value, float):
            return {"type": "number"}
        elif isinstance(value, list):
            if value:
                # 使用第一个元素的类型作为数组项类型
                item_schema = self._generate_value_schema(value[0])
                return {"type": "array", "items": item_schema}
            else:
                return {"type": "array"}
        elif isinstance(value, dict):
            return {
                "type": "object",
                "properties": self._generate_properties_schema(value)
            }
        else:
            return {"type": "string"}  # 默认类型
    
    def list_available_schemas(self) -> List[str]:
        """列出可用的模式"""
        if not self.schemas_dir.exists():
            return []
        
        return [f.stem for f in self.schemas_dir.glob("*.yaml")]
    
    def validate_schema_syntax(self, schema_name: str) -> bool:
        """验证模式文件语法"""
        schema = self._load_schema(schema_name)
        return schema is not None
    
    def get_validation_errors(self, config: Dict[str, Any], schema_name: str) -> List[str]:
        """获取详细的验证错误"""
        errors = []
        
        try:
            schema = self._load_schema(schema_name)
            if not schema:
                errors.append(f"模式不存在: {schema_name}")
                return errors
            
            if self.has_jsonschema:
                try:
                    self.jsonschema.validate(config, schema)
                except self.jsonschema.ValidationError as e:
                    errors.append(f"验证错误: {e.message}")
                    if e.path:
                        errors.append(f"错误路径: {'.'.join(str(p) for p in e.path)}")
            else:
                # 基础验证错误收集
                required_fields = schema.get('required', [])
                for field in required_fields:
                    if not self._check_field_exists(config, field):
                        errors.append(f"必需字段缺失: {field}")
                
                properties = schema.get('properties', {})
                for field_name, field_schema in properties.items():
                    if field_name in config:
                        if not self._validate_field_type(config[field_name], field_schema):
                            expected_type = field_schema.get('type', 'unknown')
                            actual_type = type(config[field_name]).__name__
                            errors.append(f"字段 {field_name} 类型错误: 期望 {expected_type}, 实际 {actual_type}")
            
        except Exception as e:
            errors.append(f"验证异常: {str(e)}")
        
        return errors
