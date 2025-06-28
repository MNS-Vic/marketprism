"""
密钥和敏感信息加载器
"""

import os
import logging
import base64
import json
from pathlib import Path
from typing import Dict, Any, Optional, Union
import re


class SecretLoader:
    """密钥和敏感信息加载器"""
    
    def __init__(self, secrets_dir: str = None):
        self.secrets_dir = Path(secrets_dir or "/etc/secrets")
        self.logger = logging.getLogger(__name__)
        
        # 密钥模式匹配
        self.secret_patterns = [
            r'\$\{secret:([^}]+)\}',  # ${secret:key_name}
            r'\$\{file:([^}]+)\}',    # ${file:file_path}
            r'\$\{base64:([^}]+)\}',  # ${base64:encoded_value}
        ]
    
    def resolve_secrets(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """解析配置中的密钥引用"""
        return self._recursive_resolve(config)
    
    def _recursive_resolve(self, obj: Any) -> Any:
        """递归解析对象中的密钥"""
        if isinstance(obj, dict):
            return {key: self._recursive_resolve(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._recursive_resolve(item) for item in obj]
        elif isinstance(obj, str):
            return self._resolve_string_secrets(obj)
        else:
            return obj
    
    def _resolve_string_secrets(self, value: str) -> str:
        """解析字符串中的密钥引用"""
        result = value
        
        # 处理 ${secret:key_name} 模式
        result = re.sub(
            r'\$\{secret:([^}]+)\}',
            lambda m: self._load_secret_from_file(m.group(1)),
            result
        )
        
        # 处理 ${file:file_path} 模式
        result = re.sub(
            r'\$\{file:([^}]+)\}',
            lambda m: self._load_file_content(m.group(1)),
            result
        )
        
        # 处理 ${base64:encoded_value} 模式
        result = re.sub(
            r'\$\{base64:([^}]+)\}',
            lambda m: self._decode_base64(m.group(1)),
            result
        )
        
        return result
    
    def _load_secret_from_file(self, secret_name: str) -> str:
        """从文件加载密钥"""
        secret_file = self.secrets_dir / secret_name
        
        try:
            if secret_file.exists():
                with open(secret_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                self.logger.debug(f"成功加载密钥: {secret_name}")
                return content
            else:
                # 尝试从环境变量获取
                env_value = os.getenv(secret_name.upper())
                if env_value:
                    self.logger.debug(f"从环境变量加载密钥: {secret_name}")
                    return env_value
                else:
                    self.logger.warning(f"密钥文件不存在且环境变量未设置: {secret_name}")
                    return f"${{{secret_name}}}"  # 保持原样
        except Exception as e:
            self.logger.error(f"加载密钥失败 {secret_name}: {e}")
            return f"${{{secret_name}}}"
    
    def _load_file_content(self, file_path: str) -> str:
        """加载文件内容"""
        try:
            # 支持相对路径和绝对路径
            if not file_path.startswith('/'):
                full_path = self.secrets_dir / file_path
            else:
                full_path = Path(file_path)
            
            if full_path.exists():
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                self.logger.debug(f"成功加载文件: {file_path}")
                return content
            else:
                self.logger.warning(f"文件不存在: {file_path}")
                return f"${{file:{file_path}}}"
        except Exception as e:
            self.logger.error(f"加载文件失败 {file_path}: {e}")
            return f"${{file:{file_path}}}"
    
    def _decode_base64(self, encoded_value: str) -> str:
        """解码Base64值"""
        try:
            decoded = base64.b64decode(encoded_value).decode('utf-8')
            self.logger.debug("成功解码Base64值")
            return decoded
        except Exception as e:
            self.logger.error(f"Base64解码失败: {e}")
            return f"${{base64:{encoded_value}}}"
    
    def load_kubernetes_secrets(self, namespace: str = "default") -> Dict[str, str]:
        """加载Kubernetes密钥（如果在K8s环境中）"""
        secrets = {}
        
        # 检查是否在Kubernetes环境中
        if not self._is_kubernetes_environment():
            return secrets
        
        try:
            # Kubernetes会将密钥挂载到 /var/run/secrets/kubernetes.io/serviceaccount/
            k8s_secrets_dir = Path("/var/run/secrets")
            
            if k8s_secrets_dir.exists():
                for secret_file in k8s_secrets_dir.rglob("*"):
                    if secret_file.is_file():
                        try:
                            with open(secret_file, 'r', encoding='utf-8') as f:
                                secrets[secret_file.name] = f.read().strip()
                        except Exception as e:
                            self.logger.warning(f"读取K8s密钥失败 {secret_file}: {e}")
            
            self.logger.info(f"加载了 {len(secrets)} 个Kubernetes密钥")
            
        except Exception as e:
            self.logger.error(f"加载Kubernetes密钥失败: {e}")
        
        return secrets
    
    def _is_kubernetes_environment(self) -> bool:
        """检查是否在Kubernetes环境中"""
        return (
            os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount/token") or
            os.getenv("KUBERNETES_SERVICE_HOST") is not None
        )
    
    def load_docker_secrets(self) -> Dict[str, str]:
        """加载Docker密钥"""
        secrets = {}
        docker_secrets_dir = Path("/run/secrets")
        
        if not docker_secrets_dir.exists():
            return secrets
        
        try:
            for secret_file in docker_secrets_dir.iterdir():
                if secret_file.is_file():
                    try:
                        with open(secret_file, 'r', encoding='utf-8') as f:
                            secrets[secret_file.name] = f.read().strip()
                    except Exception as e:
                        self.logger.warning(f"读取Docker密钥失败 {secret_file}: {e}")
            
            self.logger.info(f"加载了 {len(secrets)} 个Docker密钥")
            
        except Exception as e:
            self.logger.error(f"加载Docker密钥失败: {e}")
        
        return secrets
    
    def create_secret_file(self, secret_name: str, secret_value: str, 
                          permissions: int = 0o600) -> bool:
        """创建密钥文件"""
        try:
            # 确保密钥目录存在
            self.secrets_dir.mkdir(parents=True, exist_ok=True)
            
            secret_file = self.secrets_dir / secret_name
            
            # 写入密钥
            with open(secret_file, 'w', encoding='utf-8') as f:
                f.write(secret_value)
            
            # 设置权限
            secret_file.chmod(permissions)
            
            self.logger.info(f"成功创建密钥文件: {secret_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"创建密钥文件失败 {secret_name}: {e}")
            return False
    
    def validate_secrets(self, config: Dict[str, Any]) -> Dict[str, bool]:
        """验证配置中的密钥是否可用"""
        validation_result = {}
        secret_refs = self._find_secret_references(config)
        
        for secret_ref in secret_refs:
            if secret_ref.startswith("secret:"):
                secret_name = secret_ref[7:]  # 移除 "secret:" 前缀
                secret_file = self.secrets_dir / secret_name
                validation_result[secret_ref] = (
                    secret_file.exists() or 
                    os.getenv(secret_name.upper()) is not None
                )
            elif secret_ref.startswith("file:"):
                file_path = secret_ref[5:]  # 移除 "file:" 前缀
                if not file_path.startswith('/'):
                    full_path = self.secrets_dir / file_path
                else:
                    full_path = Path(file_path)
                validation_result[secret_ref] = full_path.exists()
            elif secret_ref.startswith("base64:"):
                # Base64编码的值总是有效的（除非解码失败）
                validation_result[secret_ref] = True
        
        return validation_result
    
    def _find_secret_references(self, obj: Any, refs: set = None) -> set:
        """查找配置中的所有密钥引用"""
        if refs is None:
            refs = set()
        
        if isinstance(obj, dict):
            for value in obj.values():
                self._find_secret_references(value, refs)
        elif isinstance(obj, list):
            for item in obj:
                self._find_secret_references(item, refs)
        elif isinstance(obj, str):
            for pattern in self.secret_patterns:
                matches = re.findall(pattern, obj)
                for match in matches:
                    refs.add(f"{pattern.split(':')[0][3:]}:{match}")
        
        return refs
    
    def get_secrets_summary(self) -> Dict[str, Any]:
        """获取密钥摘要信息"""
        summary = {
            "secrets_dir": str(self.secrets_dir),
            "secrets_dir_exists": self.secrets_dir.exists(),
            "available_secrets": [],
            "kubernetes_environment": self._is_kubernetes_environment(),
            "docker_secrets_available": Path("/run/secrets").exists(),
        }
        
        if self.secrets_dir.exists():
            summary["available_secrets"] = [
                f.name for f in self.secrets_dir.iterdir() if f.is_file()
            ]
        
        return summary
