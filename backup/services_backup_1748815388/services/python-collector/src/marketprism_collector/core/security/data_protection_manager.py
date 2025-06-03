"""
Data Protection Manager

Week 6 Day 4: API网关安全系统组件
"""

import asyncio
import logging
import re
import hashlib
import secrets
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class DataProtectionManagerConfig:
    """数据保护管理器配置"""
    enabled: bool = True
    version: str = "1.0.0"
    # 数据脱敏配置
    enable_data_masking: bool = True
    sensitive_fields: List[str] = field(default_factory=lambda: ["password", "ssn", "credit_card"])
    # 加密配置
    encryption_algorithm: str = "AES-256-GCM"
    enable_tls: bool = True
    min_tls_version: str = "1.2"

class DataProtectionManager:
    """
    Data Protection Manager
    
    企业级数据保护管理器：
    - 敏感数据识别与脱敏
    - 数据加密与解密
    - PII（个人身份信息）保护
    - 数据分类与标记
    - 合规性检查（GDPR、CCPA等）
    """
    
    def __init__(self, config: DataProtectionManagerConfig):
        self.config = config
        self.is_started = False
        
        # 敏感数据模式
        self.sensitive_patterns = {
            "ssn": r"\b\d{3}-\d{2}-\d{4}\b",  # 社会安全号码
            "credit_card": r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",  # 信用卡号
            "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # 邮箱
            "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",  # 电话号码
            "ip_address": r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",  # IP地址
            "password": r"(?i)(password|pwd|pass|secret|key)\s*[:=]\s*[^\s]+",  # 密码
            "api_key": r"(?i)(api[_-]?key|access[_-]?token|secret[_-]?key)\s*[:=]\s*[a-zA-Z0-9]{16,}"
        }
        
        # 脱敏配置
        self.masking_rules = {
            "partial": {"email": True, "phone": True},
            "full": {"ssn": True, "credit_card": True, "password": True, "api_key": True},
            "hash": {"password": True, "api_key": True}
        }
        
        # 统计信息
        self.protection_stats = {
            "data_masked": 0,
            "data_encrypted": 0,
            "sensitive_data_detected": 0,
            "compliance_checks": 0
        }
        
    async def start(self):
        """启动数据保护管理器"""
        logger.info(f"启动 Data Protection Manager v{self.config.version}")
        
        # 验证配置
        await self._validate_configuration()
        
        self.is_started = True
        logger.info("✅ Data Protection Manager 启动完成")
        
    async def stop(self):
        """停止数据保护管理器"""
        logger.info("停止 Data Protection Manager")
        self.is_started = False
        
    async def _validate_configuration(self):
        """验证配置"""
        if not self.config.sensitive_fields:
            logger.warning("未配置敏感字段列表")
            
        logger.info(f"数据保护配置验证通过 - 敏感字段: {len(self.config.sensitive_fields)} 个")
        
    async def scan_sensitive_data(self, data: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """扫描敏感数据"""
        try:
            scan_result = {
                "has_sensitive_data": False,
                "sensitive_fields": [],
                "detected_patterns": {},
                "risk_level": "low",
                "recommendations": []
            }
            
            # 将数据转换为字符串进行扫描
            if isinstance(data, dict):
                scan_text = str(data)
                # 同时检查字段名
                field_names = self._extract_field_names(data)
                scan_result["field_analysis"] = await self._analyze_field_names(field_names)
            else:
                scan_text = str(data)
                
            # 扫描敏感模式
            for pattern_name, pattern in self.sensitive_patterns.items():
                matches = re.findall(pattern, scan_text, re.IGNORECASE)
                if matches:
                    scan_result["has_sensitive_data"] = True
                    scan_result["sensitive_fields"].append(pattern_name)
                    scan_result["detected_patterns"][pattern_name] = len(matches)
                    
            # 评估风险等级
            scan_result["risk_level"] = self._assess_risk_level(scan_result["detected_patterns"])
            
            # 生成建议
            scan_result["recommendations"] = self._generate_recommendations(scan_result)
            
            if scan_result["has_sensitive_data"]:
                self.protection_stats["sensitive_data_detected"] += 1
                
            return scan_result
            
        except Exception as e:
            logger.error(f"扫描敏感数据时出错: {e}")
            return {"has_sensitive_data": False, "error": str(e)}
            
    async def mask_sensitive_data(self, data: Union[str, Dict[str, Any]], masking_level: str = "partial") -> Dict[str, Any]:
        """脱敏敏感数据"""
        try:
            if isinstance(data, dict):
                masked_data = await self._mask_dict_data(data, masking_level)
            else:
                masked_data = await self._mask_string_data(str(data), masking_level)
                
            self.protection_stats["data_masked"] += 1
            
            return {
                "success": True,
                "masked_data": masked_data,
                "masking_level": masking_level,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"数据脱敏时出错: {e}")
            return {"success": False, "error": str(e)}
            
    async def _mask_dict_data(self, data: Dict[str, Any], masking_level: str) -> Dict[str, Any]:
        """脱敏字典数据"""
        masked_data = {}
        
        for key, value in data.items():
            if isinstance(value, dict):
                masked_data[key] = await self._mask_dict_data(value, masking_level)
            elif isinstance(value, list):
                masked_data[key] = [
                    await self._mask_dict_data(item, masking_level) if isinstance(item, dict)
                    else await self._mask_string_data(str(item), masking_level)
                    for item in value
                ]
            else:
                # 检查字段名是否为敏感字段
                if key.lower() in [field.lower() for field in self.config.sensitive_fields]:
                    masked_data[key] = self._apply_masking(str(value), key.lower(), masking_level)
                else:
                    masked_data[key] = await self._mask_string_data(str(value), masking_level)
                    
        return masked_data
        
    async def _mask_string_data(self, data: str, masking_level: str) -> str:
        """脱敏字符串数据"""
        masked_data = data
        
        for pattern_name, pattern in self.sensitive_patterns.items():
            matches = re.finditer(pattern, masked_data, re.IGNORECASE)
            for match in reversed(list(matches)):  # 反向处理避免索引问题
                original_text = match.group()
                masked_text = self._apply_masking(original_text, pattern_name, masking_level)
                masked_data = masked_data[:match.start()] + masked_text + masked_data[match.end():]
                
        return masked_data
        
    def _apply_masking(self, text: str, data_type: str, masking_level: str) -> str:
        """应用脱敏规则"""
        if masking_level == "none":
            return text
            
        if masking_level == "full" or data_type in ["password", "api_key", "ssn"]:
            return "*" * len(text)
            
        if masking_level == "hash":
            return hashlib.sha256(text.encode()).hexdigest()[:16]
            
        # 部分脱敏
        if data_type == "email":
            parts = text.split("@")
            if len(parts) == 2:
                username = parts[0]
                domain = parts[1]
                masked_username = username[0] + "*" * (len(username) - 2) + username[-1] if len(username) > 2 else "*"
                return f"{masked_username}@{domain}"
                
        elif data_type == "credit_card":
            digits_only = re.sub(r"\D", "", text)
            if len(digits_only) >= 12:
                return "*" * (len(digits_only) - 4) + digits_only[-4:]
                
        elif data_type == "phone":
            digits_only = re.sub(r"\D", "", text)
            if len(digits_only) >= 7:
                return "*" * (len(digits_only) - 4) + digits_only[-4:]
                
        elif data_type == "ip_address":
            parts = text.split(".")
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.*.{parts[3]}"
                
        # 默认部分脱敏
        if len(text) > 4:
            return text[:2] + "*" * (len(text) - 4) + text[-2:]
        else:
            return "*" * len(text)
            
    def _extract_field_names(self, data: Dict[str, Any]) -> List[str]:
        """提取字段名"""
        field_names = []
        
        def extract_recursive(obj, prefix=""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    full_key = f"{prefix}.{key}" if prefix else key
                    field_names.append(full_key)
                    if isinstance(value, (dict, list)):
                        extract_recursive(value, full_key)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    if isinstance(item, (dict, list)):
                        extract_recursive(item, f"{prefix}[{i}]")
                        
        extract_recursive(data)
        return field_names
        
    async def _analyze_field_names(self, field_names: List[str]) -> Dict[str, Any]:
        """分析字段名"""
        suspicious_fields = []
        
        for field_name in field_names:
            field_lower = field_name.lower()
            for sensitive_field in self.config.sensitive_fields:
                if sensitive_field.lower() in field_lower:
                    suspicious_fields.append({
                        "field": field_name,
                        "reason": f"Contains sensitive keyword: {sensitive_field}"
                    })
                    
        return {
            "total_fields": len(field_names),
            "suspicious_fields": suspicious_fields,
            "risk_score": min(len(suspicious_fields) * 10, 100)
        }
        
    def _assess_risk_level(self, detected_patterns: Dict[str, int]) -> str:
        """评估风险等级"""
        if not detected_patterns:
            return "low"
            
        total_matches = sum(detected_patterns.values())
        high_risk_patterns = ["ssn", "credit_card", "password", "api_key"]
        
        high_risk_count = sum(detected_patterns.get(pattern, 0) for pattern in high_risk_patterns)
        
        if high_risk_count > 0 or total_matches > 10:
            return "high"
        elif total_matches > 3:
            return "medium"
        else:
            return "low"
            
    def _generate_recommendations(self, scan_result: Dict[str, Any]) -> List[str]:
        """生成保护建议"""
        recommendations = []
        
        if scan_result["has_sensitive_data"]:
            recommendations.append("发现敏感数据，建议进行数据脱敏处理")
            
            if "password" in scan_result["sensitive_fields"]:
                recommendations.append("检测到密码，建议使用哈希存储")
                
            if "credit_card" in scan_result["sensitive_fields"]:
                recommendations.append("检测到信用卡号，建议遵循PCI DSS标准")
                
            if "ssn" in scan_result["sensitive_fields"]:
                recommendations.append("检测到社会安全号码，建议加强访问控制")
                
            if scan_result["risk_level"] == "high":
                recommendations.append("高风险数据，建议立即采取保护措施")
                
        return recommendations
        
    async def encrypt_data(self, data: str, key: Optional[str] = None) -> Dict[str, Any]:
        """加密数据（简化实现）"""
        try:
            # 这里是简化的加密实现，实际应用中应使用标准加密库
            if not key:
                key = secrets.token_hex(32)
                
            # 简单的XOR加密作为示例
            encrypted_data = ""
            for i, char in enumerate(data):
                key_char = key[i % len(key)]
                encrypted_char = chr(ord(char) ^ ord(key_char))
                encrypted_data += encrypted_char
                
            self.protection_stats["data_encrypted"] += 1
            
            return {
                "success": True,
                "encrypted_data": encrypted_data.encode().hex(),
                "key": key,
                "algorithm": "XOR-Example",
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"数据加密时出错: {e}")
            return {"success": False, "error": str(e)}
            
    async def check_compliance(self, data: Union[str, Dict[str, Any]], regulations: List[str] = None) -> Dict[str, Any]:
        """检查合规性"""
        try:
            if regulations is None:
                regulations = ["GDPR", "CCPA"]
                
            compliance_result = {
                "compliant": True,
                "violations": [],
                "recommendations": [],
                "regulations_checked": regulations
            }
            
            # 扫描敏感数据
            scan_result = await self.scan_sensitive_data(data)
            
            # GDPR检查
            if "GDPR" in regulations:
                gdpr_check = self._check_gdpr_compliance(scan_result)
                if not gdpr_check["compliant"]:
                    compliance_result["compliant"] = False
                    compliance_result["violations"].extend(gdpr_check["violations"])
                    compliance_result["recommendations"].extend(gdpr_check["recommendations"])
                    
            # CCPA检查
            if "CCPA" in regulations:
                ccpa_check = self._check_ccpa_compliance(scan_result)
                if not ccpa_check["compliant"]:
                    compliance_result["compliant"] = False
                    compliance_result["violations"].extend(ccpa_check["violations"])
                    compliance_result["recommendations"].extend(ccpa_check["recommendations"])
                    
            self.protection_stats["compliance_checks"] += 1
            
            return compliance_result
            
        except Exception as e:
            logger.error(f"合规性检查时出错: {e}")
            return {"compliant": False, "error": str(e)}
            
    def _check_gdpr_compliance(self, scan_result: Dict[str, Any]) -> Dict[str, Any]:
        """检查GDPR合规性"""
        violations = []
        recommendations = []
        
        if scan_result["has_sensitive_data"]:
            if "email" in scan_result["sensitive_fields"]:
                violations.append("个人邮箱地址需要用户明确同意处理")
                recommendations.append("确保获得用户对邮箱处理的明确同意")
                
            if scan_result["risk_level"] == "high":
                violations.append("高风险个人数据需要额外保护措施")
                recommendations.append("对高风险数据实施加密和访问控制")
                
        return {
            "compliant": len(violations) == 0,
            "violations": violations,
            "recommendations": recommendations
        }
        
    def _check_ccpa_compliance(self, scan_result: Dict[str, Any]) -> Dict[str, Any]:
        """检查CCPA合规性"""
        violations = []
        recommendations = []
        
        if scan_result["has_sensitive_data"]:
            violations.append("个人信息的收集和使用需要透明化")
            recommendations.append("提供清晰的隐私政策说明数据用途")
            
            if scan_result["risk_level"] in ["medium", "high"]:
                recommendations.append("确保消费者有删除个人信息的权利")
                
        return {
            "compliant": len(violations) == 0,
            "violations": violations,
            "recommendations": recommendations
        }
        
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.protection_stats.copy()
        
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        return {
            "component": "Data Protection Manager",
            "status": "running" if self.is_started else "stopped",
            "version": self.config.version,
            "statistics": self.get_statistics()
        }