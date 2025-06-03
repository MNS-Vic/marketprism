"""
威胁检测系统

提供实时威胁检测和防护功能：
- 威胁模式识别
- 异常行为检测
- 攻击向量分析
- 威胁情报集成
- 实时威胁响应

Week 5 Day 6 实现
"""

import time
import uuid
import threading
import hashlib
import re
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from collections import defaultdict, deque
from datetime import datetime, timedelta


class ThreatType(Enum):
    """威胁类型"""
    MALWARE = "malware"
    INTRUSION = "intrusion"
    DATA_BREACH = "data_breach"
    DENIAL_OF_SERVICE = "denial_of_service"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    CONFIGURATION_TAMPERING = "configuration_tampering"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"


class ThreatLevel(Enum):
    """威胁级别"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AttackVector(Enum):
    """攻击向量"""
    NETWORK = "network"
    APPLICATION = "application"
    SYSTEM = "system"
    PHYSICAL = "physical"
    SOCIAL_ENGINEERING = "social_engineering"
    CONFIGURATION = "configuration"


@dataclass
class ThreatIndicator:
    """威胁指标"""
    indicator_id: str
    indicator_type: str  # ip, domain, hash, pattern, behavior
    value: str
    threat_type: ThreatType
    threat_level: ThreatLevel
    confidence: float  # 0.0 - 1.0
    description: str = ""
    source: str = "internal"
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    
    def is_expired(self) -> bool:
        """检查指标是否过期"""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at


@dataclass
class ThreatPattern:
    """威胁模式"""
    pattern_id: str
    name: str
    description: str
    pattern_type: str  # regex, behavioral, statistical
    pattern_data: Any  # 模式数据（正则表达式、行为规则等）
    threat_type: ThreatType
    threat_level: ThreatLevel
    confidence_threshold: float = 0.7
    enabled: bool = True
    
    def match(self, data: Any) -> Optional[float]:
        """匹配模式"""
        if not self.enabled:
            return None
        
        try:
            if self.pattern_type == "regex":
                if isinstance(data, str) and isinstance(self.pattern_data, str):
                    match = re.search(self.pattern_data, data, re.IGNORECASE)
                    return 1.0 if match else None
            
            elif self.pattern_type == "behavioral":
                return self._match_behavioral_pattern(data)
            
            elif self.pattern_type == "statistical":
                return self._match_statistical_pattern(data)
            
            return None
            
        except Exception:
            return None
    
    def _match_behavioral_pattern(self, data: Any) -> Optional[float]:
        """匹配行为模式"""
        if not isinstance(self.pattern_data, dict):
            return None
        
        # 简单的行为模式匹配
        rules = self.pattern_data.get('rules', [])
        matches = 0
        
        for rule in rules:
            field = rule.get('field')
            operator = rule.get('operator')
            value = rule.get('value')
            
            if self._evaluate_rule(data, field, operator, value):
                matches += 1
        
        if len(rules) > 0:
            confidence = matches / len(rules)
            return confidence if confidence >= self.confidence_threshold else None
        
        return None
    
    def _match_statistical_pattern(self, data: Any) -> Optional[float]:
        """匹配统计模式"""
        # 简化的统计模式匹配
        if isinstance(data, (int, float)):
            threshold = self.pattern_data.get('threshold', 0)
            return 1.0 if data > threshold else None
        
        return None
    
    def _evaluate_rule(self, data: Any, field: str, operator: str, value: Any) -> bool:
        """评估规则"""
        try:
            if isinstance(data, dict):
                field_value = data.get(field)
            else:
                field_value = getattr(data, field, None)
            
            if operator == "eq":
                return field_value == value
            elif operator == "ne":
                return field_value != value
            elif operator == "gt":
                return field_value > value
            elif operator == "lt":
                return field_value < value
            elif operator == "contains":
                return value in str(field_value)
            elif operator == "regex":
                return bool(re.search(str(value), str(field_value)))
            
            return False
            
        except Exception:
            return False


@dataclass
class ThreatEvent:
    """威胁事件"""
    event_id: str
    threat_type: ThreatType
    threat_level: ThreatLevel
    attack_vector: AttackVector
    source_ip: Optional[str] = None
    target: Optional[str] = None
    description: str = ""
    indicators: List[str] = field(default_factory=list)
    patterns: List[str] = field(default_factory=list)
    confidence: float = 0.0
    timestamp: float = field(default_factory=time.time)
    resolved: bool = False
    response_actions: List[str] = field(default_factory=list)


@dataclass
class ThreatResponse:
    """威胁响应"""
    response_id: str
    threat_event_id: str
    action_type: str  # block, alert, log, quarantine, investigate
    action_data: Dict[str, Any]
    executed: bool = False
    executed_at: Optional[float] = None
    result: Optional[str] = None


@dataclass
class DetectionRule:
    """检测规则"""
    rule_id: str
    name: str
    description: str
    conditions: List[Dict[str, Any]]
    actions: List[str]
    severity: ThreatLevel
    enabled: bool = True
    
    def evaluate(self, event_data: Dict[str, Any]) -> bool:
        """评估规则"""
        if not self.enabled:
            return False
        
        for condition in self.conditions:
            if not self._evaluate_condition(event_data, condition):
                return False
        
        return True
    
    def _evaluate_condition(self, data: Dict[str, Any], condition: Dict[str, Any]) -> bool:
        """评估单个条件"""
        field = condition.get('field')
        operator = condition.get('operator')
        value = condition.get('value')
        
        if field not in data:
            return False
        
        field_value = data[field]
        
        try:
            if operator == "eq":
                return field_value == value
            elif operator == "ne":
                return field_value != value
            elif operator == "gt":
                return field_value > value
            elif operator == "lt":
                return field_value < value
            elif operator == "contains":
                return value in str(field_value)
            elif operator == "regex":
                return bool(re.search(str(value), str(field_value)))
            
            return False
            
        except Exception:
            return False


class ThreatIntelligence:
    """威胁情报"""
    
    def __init__(self):
        self.indicators: Dict[str, ThreatIndicator] = {}
        self.patterns: Dict[str, ThreatPattern] = {}
        self.reputation_cache: Dict[str, Dict] = {}
        self._lock = threading.RLock()
    
    def add_indicator(self, indicator: ThreatIndicator):
        """添加威胁指标"""
        with self._lock:
            self.indicators[indicator.indicator_id] = indicator
    
    def add_pattern(self, pattern: ThreatPattern):
        """添加威胁模式"""
        with self._lock:
            self.patterns[pattern.pattern_id] = pattern
    
    def check_indicators(self, data: str) -> List[ThreatIndicator]:
        """检查威胁指标"""
        with self._lock:
            matches = []
            
            for indicator in self.indicators.values():
                if indicator.is_expired():
                    continue
                
                if self._matches_indicator(data, indicator):
                    matches.append(indicator)
            
            return matches
    
    def check_patterns(self, data: Any) -> List[tuple]:
        """检查威胁模式"""
        with self._lock:
            matches = []
            
            for pattern in self.patterns.values():
                confidence = pattern.match(data)
                if confidence is not None:
                    matches.append((pattern, confidence))
            
            return matches
    
    def _matches_indicator(self, data: str, indicator: ThreatIndicator) -> bool:
        """检查数据是否匹配指标"""
        if indicator.indicator_type == "ip":
            return indicator.value in data
        elif indicator.indicator_type == "domain":
            return indicator.value in data
        elif indicator.indicator_type == "hash":
            data_hash = hashlib.md5(data.encode()).hexdigest()
            return data_hash == indicator.value
        elif indicator.indicator_type == "pattern":
            return bool(re.search(indicator.value, data, re.IGNORECASE))
        
        return False


class ThreatDetectionSystem:
    """威胁检测系统"""
    
    def __init__(self, config_path: str = "/tmp/threat_detection"):
        self.config_path = config_path
        self.threat_intelligence = ThreatIntelligence()
        self.detection_rules: Dict[str, DetectionRule] = {}
        self.threat_events: List[ThreatEvent] = []
        self.pending_responses: List[ThreatResponse] = []
        
        # 统计信息
        self.statistics = {
            'total_events': 0,
            'threats_detected': 0,
            'false_positives': 0,
            'responses_executed': 0,
            'last_detection': None
        }
        
        # 实时监控
        self.is_monitoring = False
        self.monitoring_thread = None
        self.event_queue = deque(maxlen=1000)
        self.rate_limiter = defaultdict(lambda: deque(maxlen=100))
        
        # 线程安全
        self._lock = threading.RLock()
        
        # 初始化默认规则和模式
        self._initialize_default_intelligence()
    
    def _initialize_default_intelligence(self):
        """初始化默认威胁情报"""
        # 默认威胁指标
        default_indicators = [
            ThreatIndicator(
                indicator_id="malicious_ip_001",
                indicator_type="ip",
                value="192.168.1.100",  # 示例恶意IP
                threat_type=ThreatType.INTRUSION,
                threat_level=ThreatLevel.HIGH,
                confidence=0.9,
                description="已知恶意IP地址"
            ),
            ThreatIndicator(
                indicator_id="malware_hash_001",
                indicator_type="hash",
                value="d41d8cd98f00b204e9800998ecf8427e",  # 示例恶意文件哈希
                threat_type=ThreatType.MALWARE,
                threat_level=ThreatLevel.CRITICAL,
                confidence=0.95,
                description="已知恶意文件哈希"
            )
        ]
        
        # 默认威胁模式
        default_patterns = [
            ThreatPattern(
                pattern_id="brute_force_001",
                name="暴力破解检测",
                description="检测暴力破解攻击",
                pattern_type="behavioral",
                pattern_data={
                    'rules': [
                        {'field': 'failed_attempts', 'operator': 'gt', 'value': 5},
                        {'field': 'time_window', 'operator': 'lt', 'value': 300}
                    ]
                },
                threat_type=ThreatType.UNAUTHORIZED_ACCESS,
                threat_level=ThreatLevel.HIGH
            ),
            ThreatPattern(
                pattern_id="config_tampering_001",
                name="配置篡改检测",
                description="检测异常的配置修改",
                pattern_type="regex",
                pattern_data=r"(delete|remove|drop|truncate|destroy)",
                threat_type=ThreatType.CONFIGURATION_TAMPERING,
                threat_level=ThreatLevel.MEDIUM
            ),
            ThreatPattern(
                pattern_id="suspicious_activity_001",
                name="可疑活动检测",
                description="检测异常访问频率",
                pattern_type="statistical",
                pattern_data={'threshold': 100},  # 每分钟超过100次请求
                threat_type=ThreatType.SUSPICIOUS_ACTIVITY,
                threat_level=ThreatLevel.MEDIUM
            )
        ]
        
        # 默认检测规则
        default_rules = [
            DetectionRule(
                rule_id="high_frequency_access",
                name="高频访问检测",
                description="检测异常高频的配置访问",
                conditions=[
                    {'field': 'request_count', 'operator': 'gt', 'value': 50},
                    {'field': 'time_window', 'operator': 'lt', 'value': 60}
                ],
                actions=['alert', 'rate_limit'],
                severity=ThreatLevel.MEDIUM
            ),
            DetectionRule(
                rule_id="unauthorized_modification",
                name="未授权修改检测",
                description="检测未授权的配置修改",
                conditions=[
                    {'field': 'operation', 'operator': 'eq', 'value': 'modify'},
                    {'field': 'authorized', 'operator': 'eq', 'value': False}
                ],
                actions=['block', 'alert'],
                severity=ThreatLevel.HIGH
            )
        ]
        
        # 添加到系统
        for indicator in default_indicators:
            self.threat_intelligence.add_indicator(indicator)
        
        for pattern in default_patterns:
            self.threat_intelligence.add_pattern(pattern)
        
        for rule in default_rules:
            self.detection_rules[rule.rule_id] = rule
    
    def start_detection(self):
        """启动威胁检测"""
        with self._lock:
            if not self.is_monitoring:
                self.is_monitoring = True
                self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
                self.monitoring_thread.start()
    
    def stop_detection(self):
        """停止威胁检测"""
        with self._lock:
            self.is_monitoring = False
            if self.monitoring_thread:
                self.monitoring_thread.join(timeout=5)
    
    def _monitoring_loop(self):
        """监控循环"""
        while self.is_monitoring:
            try:
                # 处理事件队列
                while self.event_queue and self.is_monitoring:
                    event_data = self.event_queue.popleft()
                    self._process_event(event_data)
                
                # 执行挂起的响应
                self._execute_pending_responses()
                
                # 清理过期数据
                self._cleanup_expired_data()
                
                time.sleep(1)  # 1秒检查一次
                
            except Exception:
                time.sleep(5)  # 错误时等待5秒
    
    def analyze_event(self, event_data: Dict[str, Any]) -> Optional[ThreatEvent]:
        """分析事件"""
        with self._lock:
            self.event_queue.append(event_data)
            return self._process_event(event_data)
    
    def _process_event(self, event_data: Dict[str, Any]) -> Optional[ThreatEvent]:
        """处理事件"""
        try:
            self.statistics['total_events'] += 1
            
            # 检查威胁指标
            data_str = str(event_data)
            indicators = self.threat_intelligence.check_indicators(data_str)
            
            # 检查威胁模式
            patterns = self.threat_intelligence.check_patterns(event_data)
            
            # 检查检测规则
            triggered_rules = []
            for rule in self.detection_rules.values():
                if rule.evaluate(event_data):
                    triggered_rules.append(rule)
            
            # 如果发现威胁
            if indicators or patterns or triggered_rules:
                threat_event = self._create_threat_event(
                    event_data, indicators, patterns, triggered_rules
                )
                
                self.threat_events.append(threat_event)
                self.statistics['threats_detected'] += 1
                self.statistics['last_detection'] = time.time()
                
                # 生成响应
                responses = self._generate_responses(threat_event)
                self.pending_responses.extend(responses)
                
                return threat_event
            
            return None
            
        except Exception:
            return None
    
    def _create_threat_event(
        self,
        event_data: Dict[str, Any],
        indicators: List[ThreatIndicator],
        patterns: List[tuple],
        rules: List[DetectionRule]
    ) -> ThreatEvent:
        """创建威胁事件"""
        # 确定威胁类型和级别
        threat_type = ThreatType.SUSPICIOUS_ACTIVITY
        threat_level = ThreatLevel.LOW
        
        if indicators:
            highest_indicator = max(indicators, key=lambda x: x.threat_level.value)
            threat_type = highest_indicator.threat_type
            threat_level = highest_indicator.threat_level
        
        if patterns:
            highest_pattern = max(patterns, key=lambda x: x[0].threat_level.value)
            if highest_pattern[0].threat_level.value > threat_level.value:
                threat_type = highest_pattern[0].threat_type
                threat_level = highest_pattern[0].threat_level
        
        if rules:
            highest_rule = max(rules, key=lambda x: x.severity.value)
            if highest_rule.severity.value > threat_level.value:
                threat_level = highest_rule.severity
        
        # 计算置信度
        confidence_scores = []
        if indicators:
            confidence_scores.extend([i.confidence for i in indicators])
        if patterns:
            confidence_scores.extend([p[1] for p in patterns])
        
        confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.5
        
        return ThreatEvent(
            event_id=str(uuid.uuid4()),
            threat_type=threat_type,
            threat_level=threat_level,
            attack_vector=AttackVector.CONFIGURATION,
            source_ip=event_data.get('source_ip'),
            target=event_data.get('target'),
            description=f"检测到{threat_type.value}威胁",
            indicators=[i.indicator_id for i in indicators],
            patterns=[p[0].pattern_id for p in patterns],
            confidence=confidence
        )
    
    def _generate_responses(self, threat_event: ThreatEvent) -> List[ThreatResponse]:
        """生成威胁响应"""
        responses = []
        
        # 基于威胁级别生成响应
        if threat_event.threat_level == ThreatLevel.CRITICAL:
            responses.append(ThreatResponse(
                response_id=str(uuid.uuid4()),
                threat_event_id=threat_event.event_id,
                action_type="block",
                action_data={"reason": "Critical threat detected"}
            ))
            responses.append(ThreatResponse(
                response_id=str(uuid.uuid4()),
                threat_event_id=threat_event.event_id,
                action_type="alert",
                action_data={"severity": "critical", "immediate": True}
            ))
        
        elif threat_event.threat_level == ThreatLevel.HIGH:
            responses.append(ThreatResponse(
                response_id=str(uuid.uuid4()),
                threat_event_id=threat_event.event_id,
                action_type="alert",
                action_data={"severity": "high"}
            ))
            responses.append(ThreatResponse(
                response_id=str(uuid.uuid4()),
                threat_event_id=threat_event.event_id,
                action_type="investigate",
                action_data={"priority": "high"}
            ))
        
        else:
            responses.append(ThreatResponse(
                response_id=str(uuid.uuid4()),
                threat_event_id=threat_event.event_id,
                action_type="log",
                action_data={"level": "warning"}
            ))
        
        return responses
    
    def _execute_pending_responses(self):
        """执行挂起的响应"""
        for response in self.pending_responses[:]:
            if not response.executed:
                try:
                    self._execute_response(response)
                    response.executed = True
                    response.executed_at = time.time()
                    response.result = "success"
                    self.statistics['responses_executed'] += 1
                except Exception as e:
                    response.result = f"failed: {e}"
    
    def _execute_response(self, response: ThreatResponse):
        """执行单个响应"""
        if response.action_type == "block":
            # 实现阻止逻辑
            pass
        elif response.action_type == "alert":
            # 实现告警逻辑
            pass
        elif response.action_type == "log":
            # 实现日志记录逻辑
            pass
        elif response.action_type == "investigate":
            # 实现调查逻辑
            pass
    
    def _cleanup_expired_data(self):
        """清理过期数据"""
        current_time = time.time()
        
        # 清理过期的威胁事件（保留24小时）
        self.threat_events = [
            event for event in self.threat_events
            if (current_time - event.timestamp) < 86400
        ]
        
        # 清理过期的响应（保留24小时）
        self.pending_responses = [
            response for response in self.pending_responses
            if response.executed_at is None or (current_time - response.executed_at) < 86400
        ]
    
    def get_threat_status(self) -> dict:
        """获取威胁状态"""
        with self._lock:
            # 计算当前威胁级别
            recent_events = [
                event for event in self.threat_events
                if (time.time() - event.timestamp) < 3600 and not event.resolved
            ]
            
            if not recent_events:
                current_threat_level = "LOW"
            else:
                levels = [event.threat_level.value for event in recent_events]
                if "critical" in levels:
                    current_threat_level = "CRITICAL"
                elif "high" in levels:
                    current_threat_level = "HIGH"
                elif "medium" in levels:
                    current_threat_level = "MEDIUM"
                else:
                    current_threat_level = "LOW"
            
            return {
                'current_threat_level': current_threat_level,
                'active_threats': len(recent_events),
                'total_events': len(self.threat_events),
                'is_monitoring': self.is_monitoring,
                'statistics': self.statistics.copy()
            }
    
    def get_detection_status(self) -> dict:
        """获取检测状态"""
        with self._lock:
            return {
                'is_active': self.is_monitoring,
                'indicators_count': len(self.threat_intelligence.indicators),
                'patterns_count': len(self.threat_intelligence.patterns),
                'rules_count': len(self.detection_rules),
                'events_in_queue': len(self.event_queue),
                'pending_responses': len([r for r in self.pending_responses if not r.executed]),
                'statistics': self.statistics.copy()
            }
    
    def generate_threat_report(self) -> dict:
        """生成威胁报告"""
        with self._lock:
            status = self.get_threat_status()
            detection_status = self.get_detection_status()
            
            # 威胁分布统计
            threat_types = defaultdict(int)
            threat_levels = defaultdict(int)
            
            for event in self.threat_events:
                threat_types[event.threat_type.value] += 1
                threat_levels[event.threat_level.value] += 1
            
            return {
                'report_timestamp': time.time(),
                'threat_status': status,
                'detection_status': detection_status,
                'threat_distribution': {
                    'by_type': dict(threat_types),
                    'by_level': dict(threat_levels)
                },
                'recent_events': [
                    {
                        'event_id': event.event_id,
                        'threat_type': event.threat_type.value,
                        'threat_level': event.threat_level.value,
                        'timestamp': event.timestamp,
                        'resolved': event.resolved
                    }
                    for event in self.threat_events[-20:]  # 最近20个事件
                ]
            }


class ThreatDetectionError(Exception):
    """威胁检测错误"""
    pass


def create_threat_detection_system(config_path: str = None) -> ThreatDetectionSystem:
    """
    创建威胁检测系统
    
    Args:
        config_path: 配置路径
        
    Returns:
        ThreatDetectionSystem: 威胁检测系统实例
    """
    return ThreatDetectionSystem(config_path or "/tmp/threat_detection")