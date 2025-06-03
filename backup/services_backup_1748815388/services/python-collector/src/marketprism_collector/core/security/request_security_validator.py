"""
Request Security Validator

Week 6 Day 4: API网关安全系统组件
"""

import asyncio
import logging
import re
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class RequestSecurityValidatorConfig:
    """请求安全验证器配置"""
    enabled: bool = True
    version: str = "1.0.0"
    # 请求大小限制
    max_request_size_mb: int = 10
    max_header_size_kb: int = 8
    max_url_length: int = 2048
    # 内容验证
    enable_content_validation: bool = True
    enable_header_validation: bool = True
    enable_url_validation: bool = True
    # 安全检查
    check_malicious_patterns: bool = True
    check_encoding_attacks: bool = True
    check_directory_traversal: bool = True

class RequestSecurityValidator:
    """
    Request Security Validator
    
    企业级请求安全验证器：
    - 请求大小和格式验证
    - 恶意模式检测
    - 编码攻击防护
    - 目录遍历检测
    - HTTP头部安全检查
    """
    
    def __init__(self, config: RequestSecurityValidatorConfig):
        self.config = config
        self.is_started = False
        
        # 恶意模式库
        self.malicious_patterns = [
            r"\.\.\/",  # 目录遍历
            r"\/etc\/passwd",  # 系统文件访问
            r"<script.*?>",  # XSS
            r"javascript:",  # XSS
            r"eval\s*\(",  # 代码注入
            r"exec\s*\(",  # 代码注入
            r"union.*select",  # SQL注入
            r"drop\s+table",  # SQL注入
        ]
        
        # 危险头部
        self.dangerous_headers = [
            "x-forwarded-host",
            "x-real-ip",
            "x-cluster-client-ip",
        ]
        
        # 统计信息
        self.validation_stats = {
            "total_requests": 0,
            "valid_requests": 0,
            "blocked_requests": 0,
            "malicious_patterns_detected": 0,
            "encoding_attacks_detected": 0,
            "size_violations": 0
        }
        
    async def start(self):
        """启动请求安全验证器"""
        logger.info(f"启动 Request Security Validator v{self.config.version}")
        self.is_started = True
        logger.info("✅ Request Security Validator 启动完成")
        
    async def stop(self):
        """停止请求安全验证器"""
        logger.info("停止 Request Security Validator")
        self.is_started = False
        
    async def validate_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """验证请求安全性"""
        if not self.is_started:
            return {"valid": True, "reason": "Validator not started"}
            
        self.validation_stats["total_requests"] += 1
        
        validation_result = {
            "valid": True,
            "violations": [],
            "warnings": [],
            "metadata": {}
        }
        
        try:
            # 1. 请求大小检查
            size_check = await self._check_request_size(request_data)
            if not size_check["valid"]:
                validation_result["valid"] = False
                validation_result["violations"].append(size_check["violation"])
                self.validation_stats["size_violations"] += 1
                
            # 2. URL验证
            if self.config.enable_url_validation:
                url_check = await self._validate_url(request_data.get("url", ""))
                if not url_check["valid"]:
                    validation_result["valid"] = False
                    validation_result["violations"].extend(url_check["violations"])
                    
            # 3. 头部验证
            if self.config.enable_header_validation:
                header_check = await self._validate_headers(request_data.get("headers", {}))
                if not header_check["valid"]:
                    validation_result["valid"] = False
                    validation_result["violations"].extend(header_check["violations"])
                    
            # 4. 内容验证
            if self.config.enable_content_validation:
                content_check = await self._validate_content(request_data.get("content", ""))
                if not content_check["valid"]:
                    validation_result["valid"] = False
                    validation_result["violations"].extend(content_check["violations"])
                    
            # 5. 恶意模式检测
            if self.config.check_malicious_patterns:
                pattern_check = await self._check_malicious_patterns(request_data)
                if not pattern_check["valid"]:
                    validation_result["valid"] = False
                    validation_result["violations"].extend(pattern_check["violations"])
                    self.validation_stats["malicious_patterns_detected"] += 1
                    
            # 6. 编码攻击检测
            if self.config.check_encoding_attacks:
                encoding_check = await self._check_encoding_attacks(request_data)
                if not encoding_check["valid"]:
                    validation_result["valid"] = False
                    validation_result["violations"].extend(encoding_check["violations"])
                    self.validation_stats["encoding_attacks_detected"] += 1
                    
            # 7. 目录遍历检测
            if self.config.check_directory_traversal:
                traversal_check = await self._check_directory_traversal(request_data)
                if not traversal_check["valid"]:
                    validation_result["valid"] = False
                    validation_result["violations"].extend(traversal_check["violations"])
                    
            # 更新统计
            if validation_result["valid"]:
                self.validation_stats["valid_requests"] += 1
            else:
                self.validation_stats["blocked_requests"] += 1
                
            return validation_result
            
        except Exception as e:
            logger.error(f"请求验证时出错: {e}")
            return {
                "valid": False,
                "violations": ["Validation error"],
                "error": str(e)
            }
            
    async def _check_request_size(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """检查请求大小"""
        try:
            # 检查请求内容大小
            content = request_data.get("content", "")
            content_size_mb = len(content.encode('utf-8')) / (1024 * 1024)
            
            if content_size_mb > self.config.max_request_size_mb:
                return {
                    "valid": False,
                    "violation": f"Request content too large: {content_size_mb:.2f}MB > {self.config.max_request_size_mb}MB"
                }
                
            # 检查URL长度
            url = request_data.get("url", "")
            if len(url) > self.config.max_url_length:
                return {
                    "valid": False,
                    "violation": f"URL too long: {len(url)} > {self.config.max_url_length}"
                }
                
            # 检查头部大小
            headers = request_data.get("headers", {})
            headers_size_kb = len(json.dumps(headers).encode('utf-8')) / 1024
            
            if headers_size_kb > self.config.max_header_size_kb:
                return {
                    "valid": False,
                    "violation": f"Headers too large: {headers_size_kb:.2f}KB > {self.config.max_header_size_kb}KB"
                }
                
            return {"valid": True}
            
        except Exception as e:
            logger.error(f"大小检查时出错: {e}")
            return {"valid": True}
            
    async def _validate_url(self, url: str) -> Dict[str, Any]:
        """验证URL"""
        violations = []
        
        try:
            # 检查URL编码攻击
            if "%00" in url:  # 空字节攻击
                violations.append("Null byte attack detected in URL")
                
            # 检查目录遍历
            if "../" in url or "..%2f" in url.lower():
                violations.append("Directory traversal attempt in URL")
                
            # 检查协议
            if url.startswith(("file://", "ftp://", "gopher://")):
                violations.append("Dangerous protocol in URL")
                
            # 检查特殊字符
            dangerous_chars = ["<", ">", "\"", "'", "`"]
            for char in dangerous_chars:
                if char in url:
                    violations.append(f"Dangerous character '{char}' in URL")
                    break
                    
            return {
                "valid": len(violations) == 0,
                "violations": violations
            }
            
        except Exception as e:
            logger.error(f"URL验证时出错: {e}")
            return {"valid": True, "violations": []}
            
    async def _validate_headers(self, headers: Dict[str, str]) -> Dict[str, Any]:
        """验证HTTP头部"""
        violations = []
        
        try:
            for header_name, header_value in headers.items():
                header_name_lower = header_name.lower()
                
                # 检查危险头部
                if header_name_lower in self.dangerous_headers:
                    violations.append(f"Dangerous header: {header_name}")
                    
                # 检查头部值中的恶意模式
                for pattern in self.malicious_patterns:
                    if re.search(pattern, header_value, re.IGNORECASE):
                        violations.append(f"Malicious pattern in header {header_name}: {pattern}")
                        
                # 检查头部注入
                if "\r" in header_value or "\n" in header_value:
                    violations.append(f"Header injection attempt in {header_name}")
                    
                # 检查超长头部值
                if len(header_value) > 4096:
                    violations.append(f"Header value too long: {header_name}")
                    
            return {
                "valid": len(violations) == 0,
                "violations": violations
            }
            
        except Exception as e:
            logger.error(f"头部验证时出错: {e}")
            return {"valid": True, "violations": []}
            
    async def _validate_content(self, content: str) -> Dict[str, Any]:
        """验证请求内容"""
        violations = []
        
        try:
            # 检查空字节攻击
            if "\x00" in content:
                violations.append("Null byte detected in content")
                
            # 检查控制字符
            control_chars = [chr(i) for i in range(32) if i not in [9, 10, 13]]  # 排除tab, LF, CR
            for char in control_chars:
                if char in content:
                    violations.append("Control character detected in content")
                    break
                    
            # 检查过度嵌套（JSON/XML炸弹）
            if content.count("{") > 100 or content.count("[") > 100:
                violations.append("Excessive nesting detected (potential bomb attack)")
                
            # 检查重复模式（Zip炸弹类似攻击）
            if len(content) > 1000:
                # 简单的重复检测
                sample = content[:100]
                if content.count(sample) > 50:
                    violations.append("Excessive repetition detected")
                    
            return {
                "valid": len(violations) == 0,
                "violations": violations
            }
            
        except Exception as e:
            logger.error(f"内容验证时出错: {e}")
            return {"valid": True, "violations": []}
            
    async def _check_malicious_patterns(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """检查恶意模式"""
        violations = []
        
        try:
            # 合并所有需要检查的内容
            all_content = " ".join([
                str(request_data.get("content", "")),
                str(request_data.get("url", "")),
                " ".join(str(v) for v in request_data.get("headers", {}).values())
            ])
            
            # 检查每个恶意模式
            for pattern in self.malicious_patterns:
                if re.search(pattern, all_content, re.IGNORECASE):
                    violations.append(f"Malicious pattern detected: {pattern}")
                    
            return {
                "valid": len(violations) == 0,
                "violations": violations
            }
            
        except Exception as e:
            logger.error(f"恶意模式检查时出错: {e}")
            return {"valid": True, "violations": []}
            
    async def _check_encoding_attacks(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """检查编码攻击"""
        violations = []
        
        try:
            all_content = " ".join([
                str(request_data.get("content", "")),
                str(request_data.get("url", ""))
            ])
            
            # 检查双重编码
            if "%25" in all_content:  # %25 是 % 的编码
                violations.append("Double encoding attack detected")
                
            # 检查Unicode编码攻击
            unicode_patterns = [
                r"\\u[0-9a-fA-F]{4}",  # Unicode转义
                r"\\x[0-9a-fA-F]{2}",  # 十六进制转义
                r"&#x[0-9a-fA-F]+;",   # HTML实体
                r"&#[0-9]+;"           # HTML实体
            ]
            
            for pattern in unicode_patterns:
                matches = re.findall(pattern, all_content)
                if len(matches) > 10:  # 过多的编码可能是攻击
                    violations.append(f"Excessive encoding detected: {pattern}")
                    
            return {
                "valid": len(violations) == 0,
                "violations": violations
            }
            
        except Exception as e:
            logger.error(f"编码攻击检查时出错: {e}")
            return {"valid": True, "violations": []}
            
    async def _check_directory_traversal(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """检查目录遍历攻击"""
        violations = []
        
        try:
            url = request_data.get("url", "")
            content = request_data.get("content", "")
            
            # 目录遍历模式
            traversal_patterns = [
                r"\.\.\/",
                r"\.\.\\",
                r"\.\.%2f",
                r"\.\.%5c",
                r"%2e%2e%2f",
                r"%2e%2e%5c"
            ]
            
            for pattern in traversal_patterns:
                if re.search(pattern, url + " " + content, re.IGNORECASE):
                    violations.append(f"Directory traversal pattern detected: {pattern}")
                    
            # 检查绝对路径
            dangerous_paths = [
                "/etc/passwd",
                "/etc/shadow",
                "/windows/system32",
                "c:\\windows\\system32"
            ]
            
            for path in dangerous_paths:
                if path.lower() in (url + " " + content).lower():
                    violations.append(f"Dangerous path access attempt: {path}")
                    
            return {
                "valid": len(violations) == 0,
                "violations": violations
            }
            
        except Exception as e:
            logger.error(f"目录遍历检查时出错: {e}")
            return {"valid": True, "violations": []}
            
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.validation_stats.copy()
        
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        return {
            "component": "Request Security Validator",
            "status": "running" if self.is_started else "stopped",
            "version": self.config.version,
            "statistics": self.get_statistics()
        }