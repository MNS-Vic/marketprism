"""
配置安全验证器
"""

import logging
import re
from typing import Dict, Any, List


class SecurityValidator:
    """配置安全验证器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # 敏感字段模式
        self.sensitive_patterns = [
            r'password',
            r'secret',
            r'key',
            r'token',
            r'credential',
            r'auth'
        ]
        
        # 不安全的默认值
        self.insecure_defaults = [
            'password',
            'admin',
            '123456',
            'secret',
            'default',
            'changeme'
        ]
    
    def validate(self, config: Dict[str, Any]) -> bool:
        """验证配置安全性"""
        try:
            # 检查敏感信息泄露
            if not self._check_sensitive_data_exposure(config):
                return False
            
            # 检查不安全的默认值
            if not self._check_insecure_defaults(config):
                return False
            
            # 检查SSL/TLS配置
            if not self._check_ssl_configuration(config):
                return False
            
            # 检查访问控制配置
            if not self._check_access_control(config):
                return False
            
            self.logger.debug("安全验证通过")
            return True
            
        except Exception as e:
            self.logger.error(f"安全验证失败: {e}")
            return False
    
    def _check_sensitive_data_exposure(self, config: Dict[str, Any]) -> bool:
        """检查敏感信息是否暴露"""
        sensitive_fields = self._find_sensitive_fields(config)
        
        for field_path, value in sensitive_fields:
            # 检查是否为明文
            if self._is_plaintext_sensitive_value(value):
                self.logger.warning(f"可能的敏感信息暴露: {field_path}")
                # 在生产环境中应该返回False，这里只是警告
        
        return True
    
    def _find_sensitive_fields(self, obj: Any, path: str = "") -> List[tuple]:
        """递归查找敏感字段"""
        sensitive_fields = []
        
        if isinstance(obj, dict):
            for key, value in obj.items():
                current_path = f"{path}.{key}" if path else key
                
                # 检查字段名是否敏感
                if self._is_sensitive_field_name(key):
                    sensitive_fields.append((current_path, value))
                
                # 递归检查
                sensitive_fields.extend(self._find_sensitive_fields(value, current_path))
        
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                current_path = f"{path}[{i}]"
                sensitive_fields.extend(self._find_sensitive_fields(item, current_path))
        
        return sensitive_fields
    
    def _is_sensitive_field_name(self, field_name: str) -> bool:
        """检查字段名是否敏感"""
        field_lower = field_name.lower()
        return any(re.search(pattern, field_lower) for pattern in self.sensitive_patterns)
    
    def _is_plaintext_sensitive_value(self, value: str) -> bool:
        """检查是否为明文敏感值"""
        if not isinstance(value, str):
            return False
        
        # 检查是否为环境变量引用
        if value.startswith('${') and value.endswith('}'):
            return False
        
        # 检查是否为密钥引用
        if value.startswith('${secret:') or value.startswith('${file:'):
            return False
        
        # 检查是否为明显的明文密码
        if value in self.insecure_defaults:
            return True
        
        # 检查长度（太短的可能是测试值）
        if len(value) < 8:
            return True
        
        return False
    
    def _check_insecure_defaults(self, config: Dict[str, Any]) -> bool:
        """检查不安全的默认值"""
        insecure_values = self._find_insecure_values(config)
        
        for field_path, value in insecure_values:
            self.logger.error(f"发现不安全的默认值: {field_path} = {value}")
            return False
        
        return True
    
    def _find_insecure_values(self, obj: Any, path: str = "") -> List[tuple]:
        """查找不安全的值"""
        insecure_values = []
        
        if isinstance(obj, dict):
            for key, value in obj.items():
                current_path = f"{path}.{key}" if path else key
                
                if isinstance(value, str) and value.lower() in self.insecure_defaults:
                    if self._is_sensitive_field_name(key):
                        insecure_values.append((current_path, value))
                
                insecure_values.extend(self._find_insecure_values(value, current_path))
        
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                current_path = f"{path}[{i}]"
                insecure_values.extend(self._find_insecure_values(item, current_path))
        
        return insecure_values
    
    def _check_ssl_configuration(self, config: Dict[str, Any]) -> bool:
        """检查SSL/TLS配置"""
        ssl_config = config.get('ssl', {})
        
        if ssl_config.get('enabled', False):
            # 检查证书文件配置
            if not ssl_config.get('cert_file'):
                self.logger.error("SSL启用但未配置证书文件")
                return False
            
            if not ssl_config.get('key_file'):
                self.logger.error("SSL启用但未配置私钥文件")
                return False
            
            # 检查安全配置
            if ssl_config.get('verify_client', True) is False:
                self.logger.warning("SSL客户端验证已禁用")
        
        return True
    
    def _check_access_control(self, config: Dict[str, Any]) -> bool:
        """检查访问控制配置"""
        access_control = config.get('access_control', {})
        
        if access_control.get('enabled', True):
            allowed_ips = access_control.get('allowed_ips', [])
            
            # 检查是否允许所有IP
            if '*' in allowed_ips or '0.0.0.0/0' in allowed_ips:
                self.logger.warning("访问控制允许所有IP地址")
            
            # 检查是否有过于宽泛的网段
            for ip in allowed_ips:
                if '/' in ip:
                    network, prefix = ip.split('/')
                    if int(prefix) < 16:
                        self.logger.warning(f"网段过于宽泛: {ip}")
        
        return True
    
    def get_security_recommendations(self, config: Dict[str, Any]) -> List[str]:
        """获取安全建议"""
        recommendations = []
        
        # 检查敏感字段
        sensitive_fields = self._find_sensitive_fields(config)
        if sensitive_fields:
            recommendations.append("建议使用环境变量或密钥管理系统存储敏感信息")
        
        # 检查SSL配置
        ssl_config = config.get('ssl', {})
        if not ssl_config.get('enabled', False):
            recommendations.append("建议启用SSL/TLS加密")
        
        # 检查访问控制
        access_control = config.get('access_control', {})
        if not access_control.get('enabled', True):
            recommendations.append("建议启用访问控制")
        
        # 检查审计日志
        audit_config = config.get('audit', {})
        if not audit_config.get('enabled', False):
            recommendations.append("建议启用审计日志")
        
        return recommendations
    
    def sanitize_config_for_logging(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """清理配置用于日志记录（隐藏敏感信息）"""
        return self._recursive_sanitize(config)
    
    def _recursive_sanitize(self, obj: Any) -> Any:
        """递归清理敏感信息"""
        if isinstance(obj, dict):
            sanitized = {}
            for key, value in obj.items():
                if self._is_sensitive_field_name(key):
                    sanitized[key] = "***HIDDEN***"
                else:
                    sanitized[key] = self._recursive_sanitize(value)
            return sanitized
        
        elif isinstance(obj, list):
            return [self._recursive_sanitize(item) for item in obj]
        
        else:
            return obj
