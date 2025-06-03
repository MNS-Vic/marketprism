"""
Security Policy Engine

Week 6 Day 4: API网关安全系统组件
"""

import asyncio
import logging
import re
import hashlib
import json
from typing import Dict, Any, Optional, List, Union, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from ipaddress import ip_address, ip_network

logger = logging.getLogger(__name__)

class SecurityAction(Enum):
    """安全动作枚举"""
    ALLOW = "allow"
    DENY = "deny"
    THROTTLE = "throttle"
    LOG = "log"
    CHALLENGE = "challenge"

class ThreatLevel(Enum):
    """威胁等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class SecurityRule:
    """安全规则"""
    rule_id: str
    name: str
    description: str
    pattern: str
    action: SecurityAction
    threat_level: ThreatLevel
    enabled: bool = True
    priority: int = 100
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class SecurityEvent:
    """安全事件"""
    event_id: str
    timestamp: datetime
    source_ip: str
    rule_id: str
    action: SecurityAction
    threat_level: ThreatLevel
    description: str
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class SecurityPolicyEngineConfig:
    """安全策略引擎配置"""
    enabled: bool = True
    version: str = "1.0.0"
    # IP限制配置
    enable_ip_whitelist: bool = True
    ip_whitelist: List[str] = field(default_factory=lambda: ["127.0.0.1", "192.168.0.0/16"])
    enable_ip_blacklist: bool = True
    ip_blacklist: List[str] = field(default_factory=list)
    # 频率限制配置
    enable_rate_limiting: bool = True
    requests_per_minute: int = 1000
    burst_limit: int = 100
    # 威胁检测配置
    enable_sql_injection_detection: bool = True
    enable_xss_detection: bool = True
    enable_csrf_protection: bool = True
    # 安全规则配置
    enable_custom_rules: bool = True
    rules_cache_ttl: int = 300
    max_violations_per_hour: int = 10
    auto_block_threshold: int = 5
    
class SecurityPolicyEngine:
    """
    Security Policy Engine
    
    企业级安全策略引擎：
    - IP白名单/黑名单管理
    - 威胁检测与防护
    - 安全规则引擎
    - 访问控制管理
    - 风险评估系统
    """
    
    def __init__(self, config: SecurityPolicyEngineConfig):
        self.config = config
        self.is_started = False
        
        # 安全规则存储
        self.security_rules: Dict[str, SecurityRule] = {}
        self.rule_statistics: Dict[str, Dict[str, Any]] = {}
        
        # IP管理
        self.ip_whitelist: Set[str] = set(config.ip_whitelist)
        self.ip_blacklist: Set[str] = set(config.ip_blacklist)
        self.blocked_ips: Dict[str, datetime] = {}
        
        # 频率限制
        self.request_counts: Dict[str, List[datetime]] = {}
        
        # 威胁检测模式
        self.sql_injection_patterns = [
            r"(\bUNION\b|\bSELECT\b|\bINSERT\b|\bDELETE\b|\bUPDATE\b|\bDROP\b)",
            r"'.*OR.*'",
            r";\s*(DROP|DELETE|UPDATE)",
        ]
        
        self.xss_patterns = [
            r"<script.*?>.*?</script>",
            r"javascript:",
            r"on\w+\s*=",
            r"<iframe.*?>",
        ]
        
        # 初始化默认规则
        self._initialize_default_rules()
        
    def _initialize_default_rules(self):
        """初始化默认安全规则"""
        default_rules = [
            SecurityRule(
                rule_id="sql_injection_basic",
                name="SQL注入基础检测",
                description="检测基础SQL注入攻击模式",
                pattern="|".join(self.sql_injection_patterns),
                action=SecurityAction.DENY,
                threat_level=ThreatLevel.HIGH
            ),
            SecurityRule(
                rule_id="xss_basic",
                name="XSS基础检测",
                description="检测基础跨站脚本攻击",
                pattern="|".join(self.xss_patterns),
                action=SecurityAction.DENY,
                threat_level=ThreatLevel.MEDIUM
            ),
            SecurityRule(
                rule_id="rate_limit_basic",
                name="基础频率限制",
                description="基础请求频率限制",
                pattern=".*",
                action=SecurityAction.THROTTLE,
                threat_level=ThreatLevel.LOW
            )
        ]
        
        for rule in default_rules:
            self.security_rules[rule.rule_id] = rule
            self.rule_statistics[rule.rule_id] = {
                "triggered_count": 0,
                "last_triggered": None,
                "false_positive_count": 0
            }
        
    async def start(self):
        """启动安全策略引擎"""
        logger.info(f"启动 Security Policy Engine v{self.config.version}")
        
        # 验证配置
        await self._validate_configuration()
        
        # 加载安全规则
        await self._load_security_rules()
        
        # 启动监控任务
        if self.config.enable_rate_limiting:
            asyncio.create_task(self._cleanup_request_counts())
            
        self.is_started = True
        logger.info("✅ Security Policy Engine 启动完成")
        
    async def stop(self):
        """停止安全策略引擎"""
        logger.info("停止 Security Policy Engine")
        self.is_started = False
        
    async def _validate_configuration(self):
        """验证配置"""
        # 验证IP地址格式
        for ip in self.config.ip_whitelist:
            try:
                if '/' in ip:
                    ip_network(ip)
                else:
                    ip_address(ip)
            except ValueError:
                logger.error(f"Invalid IP format in whitelist: {ip}")
                
        for ip in self.config.ip_blacklist:
            try:
                if '/' in ip:
                    ip_network(ip)
                else:
                    ip_address(ip)
            except ValueError:
                logger.error(f"Invalid IP format in blacklist: {ip}")
        
    async def _load_security_rules(self):
        """加载安全规则"""
        logger.info(f"加载了 {len(self.security_rules)} 条安全规则")
        
    async def _cleanup_request_counts(self):
        """清理过期的请求计数"""
        while self.is_started:
            try:
                current_time = datetime.now()
                cutoff_time = current_time - timedelta(minutes=1)
                
                for ip in list(self.request_counts.keys()):
                    self.request_counts[ip] = [
                        req_time for req_time in self.request_counts[ip]
                        if req_time > cutoff_time
                    ]
                    
                    if not self.request_counts[ip]:
                        del self.request_counts[ip]
                        
                await asyncio.sleep(30)  # 每30秒清理一次
                
            except Exception as e:
                logger.error(f"清理请求计数时出错: {e}")
                await asyncio.sleep(5)
        
    async def evaluate_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """评估请求安全性"""
        if not self.is_started:
            return {"allowed": True, "reason": "Engine not started"}
            
        source_ip = request_data.get("source_ip", "unknown")
        request_content = request_data.get("content", "")
        headers = request_data.get("headers", {})
        
        evaluation_result = {
            "allowed": True,
            "action": SecurityAction.ALLOW,
            "threat_level": ThreatLevel.LOW,
            "triggered_rules": [],
            "violations": [],
            "metadata": {}
        }
        
        try:
            # 1. IP检查
            ip_check = await self._check_ip_restrictions(source_ip)
            if not ip_check["allowed"]:
                evaluation_result.update(ip_check)
                return evaluation_result
                
            # 2. 频率限制检查
            if self.config.enable_rate_limiting:
                rate_check = await self._check_rate_limiting(source_ip)
                if not rate_check["allowed"]:
                    evaluation_result.update(rate_check)
                    return evaluation_result
                    
            # 3. 威胁检测
            threat_check = await self._detect_threats(request_content, headers)
            if not threat_check["allowed"]:
                evaluation_result.update(threat_check)
                return evaluation_result
                
            # 4. 自定义规则检查
            if self.config.enable_custom_rules:
                custom_check = await self._evaluate_custom_rules(request_data)
                if not custom_check["allowed"]:
                    evaluation_result.update(custom_check)
                    return evaluation_result
                    
        except Exception as e:
            logger.error(f"请求评估时出错: {e}")
            evaluation_result.update({
                "allowed": False,
                "action": SecurityAction.DENY,
                "reason": "Evaluation error",
                "error": str(e)
            })
            
        return evaluation_result
        
    async def _check_ip_restrictions(self, source_ip: str) -> Dict[str, Any]:
        """检查IP限制"""
        try:
            # 检查是否在黑名单
            if self.config.enable_ip_blacklist and source_ip in self.ip_blacklist:
                return {
                    "allowed": False,
                    "action": SecurityAction.DENY,
                    "threat_level": ThreatLevel.HIGH,
                    "reason": "IP in blacklist",
                    "violated_rule": "ip_blacklist"
                }
                
            # 检查白名单（如果启用）
            if self.config.enable_ip_whitelist:
                ip_allowed = False
                for allowed_ip in self.ip_whitelist:
                    try:
                        if '/' in allowed_ip:
                            if ip_address(source_ip) in ip_network(allowed_ip):
                                ip_allowed = True
                                break
                        else:
                            if source_ip == allowed_ip:
                                ip_allowed = True
                                break
                    except ValueError:
                        continue
                        
                if not ip_allowed:
                    return {
                        "allowed": False,
                        "action": SecurityAction.DENY,
                        "threat_level": ThreatLevel.MEDIUM,
                        "reason": "IP not in whitelist",
                        "violated_rule": "ip_whitelist"
                    }
                    
            return {"allowed": True}
            
        except Exception as e:
            logger.error(f"IP检查时出错: {e}")
            return {"allowed": True}
            
    async def _check_rate_limiting(self, source_ip: str) -> Dict[str, Any]:
        """检查频率限制"""
        try:
            current_time = datetime.now()
            
            # 初始化IP记录
            if source_ip not in self.request_counts:
                self.request_counts[source_ip] = []
                
            # 记录当前请求
            self.request_counts[source_ip].append(current_time)
            
            # 计算最近一分钟的请求数
            cutoff_time = current_time - timedelta(minutes=1)
            recent_requests = [
                req_time for req_time in self.request_counts[source_ip]
                if req_time > cutoff_time
            ]
            
            # 检查是否超过限制
            if len(recent_requests) > self.config.requests_per_minute:
                return {
                    "allowed": False,
                    "action": SecurityAction.THROTTLE,
                    "threat_level": ThreatLevel.MEDIUM,
                    "reason": f"Rate limit exceeded: {len(recent_requests)} requests/minute",
                    "violated_rule": "rate_limiting",
                    "retry_after": 60
                }
                
            return {"allowed": True}
            
        except Exception as e:
            logger.error(f"频率限制检查时出错: {e}")
            return {"allowed": True}
            
    async def _detect_threats(self, content: str, headers: Dict[str, str]) -> Dict[str, Any]:
        """威胁检测"""
        try:
            violations = []
            
            # SQL注入检测
            if self.config.enable_sql_injection_detection:
                for pattern in self.sql_injection_patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        violations.append({
                            "type": "sql_injection",
                            "pattern": pattern,
                            "threat_level": ThreatLevel.HIGH
                        })
                        
            # XSS检测
            if self.config.enable_xss_detection:
                for pattern in self.xss_patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        violations.append({
                            "type": "xss",
                            "pattern": pattern,
                            "threat_level": ThreatLevel.MEDIUM
                        })
                        
            # CSRF检测
            if self.config.enable_csrf_protection:
                if not headers.get("X-CSRF-Token") and not headers.get("X-Requested-With"):
                    violations.append({
                        "type": "csrf",
                        "threat_level": ThreatLevel.LOW,
                        "description": "Missing CSRF protection headers"
                    })
                    
            if violations:
                # 找到最高威胁等级
                threat_levels = [v["threat_level"] for v in violations]
                threat_level_order = {ThreatLevel.LOW: 1, ThreatLevel.MEDIUM: 2, ThreatLevel.HIGH: 3, ThreatLevel.CRITICAL: 4}
                max_threat = max(threat_levels, key=lambda x: threat_level_order[x])
                
                return {
                    "allowed": False,
                    "action": SecurityAction.DENY,
                    "threat_level": max_threat,
                    "reason": "Threat detected",
                    "violations": violations
                }
                
            return {"allowed": True}
            
        except Exception as e:
            logger.error(f"威胁检测时出错: {e}")
            return {"allowed": True}
            
    async def _evaluate_custom_rules(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """评估自定义规则"""
        try:
            triggered_rules = []
            
            for rule_id, rule in self.security_rules.items():
                if not rule.enabled:
                    continue
                    
                content = str(request_data.get("content", ""))
                if re.search(rule.pattern, content, re.IGNORECASE):
                    triggered_rules.append(rule)
                    
                    # 更新统计
                    self.rule_statistics[rule_id]["triggered_count"] += 1
                    self.rule_statistics[rule_id]["last_triggered"] = datetime.now()
                    
            if triggered_rules:
                # 按优先级排序
                triggered_rules.sort(key=lambda r: r.priority)
                primary_rule = triggered_rules[0]
                
                return {
                    "allowed": primary_rule.action == SecurityAction.ALLOW,
                    "action": primary_rule.action,
                    "threat_level": primary_rule.threat_level,
                    "reason": f"Triggered rule: {primary_rule.name}",
                    "triggered_rules": [r.rule_id for r in triggered_rules]
                }
                
            return {"allowed": True}
            
        except Exception as e:
            logger.error(f"自定义规则评估时出错: {e}")
            return {"allowed": True}
            
    async def add_security_rule(self, rule: SecurityRule):
        """添加安全规则"""
        self.security_rules[rule.rule_id] = rule
        self.rule_statistics[rule.rule_id] = {
            "triggered_count": 0,
            "last_triggered": None,
            "false_positive_count": 0
        }
        logger.info(f"添加安全规则: {rule.name}")
        
    async def remove_security_rule(self, rule_id: str):
        """删除安全规则"""
        if rule_id in self.security_rules:
            del self.security_rules[rule_id]
            del self.rule_statistics[rule_id]
            logger.info(f"删除安全规则: {rule_id}")
            
    async def update_ip_whitelist(self, ip_list: List[str]):
        """更新IP白名单"""
        self.ip_whitelist = set(ip_list)
        logger.info(f"更新IP白名单: {len(ip_list)} 个地址")
        
    async def update_ip_blacklist(self, ip_list: List[str]):
        """更新IP黑名单"""
        self.ip_blacklist = set(ip_list)
        logger.info(f"更新IP黑名单: {len(ip_list)} 个地址")
        
    async def block_ip(self, ip: str, duration_hours: int = 24):
        """临时封禁IP"""
        self.ip_blacklist.add(ip)
        self.blocked_ips[ip] = datetime.now() + timedelta(hours=duration_hours)
        logger.warning(f"封禁IP: {ip} ({duration_hours}小时)")
        
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_rules": len(self.security_rules),
            "active_rules": sum(1 for r in self.security_rules.values() if r.enabled),
            "ip_whitelist_size": len(self.ip_whitelist),
            "ip_blacklist_size": len(self.ip_blacklist),
            "blocked_ips": len(self.blocked_ips),
            "request_counts": len(self.request_counts),
            "rule_statistics": self.rule_statistics
        }
        
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        return {
            "component": "Security Policy Engine",
            "status": "running" if self.is_started else "stopped",
            "version": self.config.version,
            "statistics": self.get_statistics()
        }