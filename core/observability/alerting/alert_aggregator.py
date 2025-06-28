"""
MarketPrism 告警聚合和去重机制

提供智能的告警聚合和去重功能，避免告警风暴
"""

import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict
import structlog

from .alert_types import Alert, AlertSeverity, AlertCategory, AlertStatus


logger = structlog.get_logger(__name__)


class AlertDeduplicator:
    """告警去重器"""
    
    def __init__(self, time_window: int = 300):  # 5分钟时间窗口
        self.time_window = time_window  # 去重时间窗口（秒）
        self.alert_fingerprints: Dict[str, datetime] = {}  # 告警指纹 -> 最后创建时间
        
    def should_create_alert(self, alert: Alert, existing_alerts: List[Alert]) -> bool:
        """判断是否应该创建告警（去重检查）"""
        fingerprint = self._generate_fingerprint(alert)
        current_time = datetime.now(timezone.utc)
        
        # 检查指纹缓存
        if fingerprint in self.alert_fingerprints:
            last_time = self.alert_fingerprints[fingerprint]
            if (current_time - last_time).total_seconds() < self.time_window:
                logger.debug("告警被去重", fingerprint=fingerprint)
                return False
        
        # 检查现有活跃告警
        for existing_alert in existing_alerts:
            if existing_alert.status == AlertStatus.ACTIVE:
                if self._are_similar_alerts(alert, existing_alert):
                    logger.debug("发现相似活跃告警", 
                               new_alert=alert.name, 
                               existing_alert=existing_alert.name)
                    return False
        
        # 更新指纹缓存
        self.alert_fingerprints[fingerprint] = current_time
        
        # 清理过期指纹
        self._cleanup_fingerprints()
        
        return True
    
    def _generate_fingerprint(self, alert: Alert) -> str:
        """生成告警指纹"""
        # 基于关键字段生成唯一指纹
        key_fields = [
            alert.name,
            alert.severity.value,
            alert.category.value,
            alert.metadata.get('source', ''),
            alert.metadata.get('component', ''),
            alert.labels.get('service', ''),
            alert.labels.get('instance', '')
        ]
        
        fingerprint_str = '|'.join(str(field) for field in key_fields)
        return hashlib.md5(fingerprint_str.encode()).hexdigest()
    
    def _are_similar_alerts(self, alert1: Alert, alert2: Alert) -> bool:
        """判断两个告警是否相似"""
        # 基本字段比较
        if (alert1.name == alert2.name and 
            alert1.severity == alert2.severity and
            alert1.category == alert2.category):
            
            # 检查关键标签
            key_labels = ['service', 'instance', 'component']
            for label in key_labels:
                if (alert1.labels.get(label) and alert2.labels.get(label) and
                    alert1.labels[label] == alert2.labels[label]):
                    return True
        
        return False
    
    def _cleanup_fingerprints(self) -> None:
        """清理过期的指纹"""
        current_time = datetime.now(timezone.utc)
        cutoff_time = current_time - timedelta(seconds=self.time_window * 2)
        
        expired_fingerprints = [
            fp for fp, timestamp in self.alert_fingerprints.items()
            if timestamp < cutoff_time
        ]
        
        for fp in expired_fingerprints:
            del self.alert_fingerprints[fp]


class AlertAggregator:
    """告警聚合器"""
    
    def __init__(self, aggregation_window: int = 600):  # 10分钟聚合窗口
        self.aggregation_window = aggregation_window
        self.aggregated_alerts: Dict[str, List[Alert]] = defaultdict(list)
        
    def aggregate_alerts(self, alerts: List[Alert]) -> List[Dict]:
        """聚合告警"""
        aggregated = []
        
        # 按聚合键分组
        groups = self._group_alerts_by_key(alerts)
        
        for group_key, group_alerts in groups.items():
            if len(group_alerts) > 1:
                # 创建聚合告警
                aggregated_alert = self._create_aggregated_alert(group_key, group_alerts)
                aggregated.append(aggregated_alert)
            else:
                # 单个告警不需要聚合
                aggregated.extend([alert.to_dict() for alert in group_alerts])
        
        return aggregated
    
    def _group_alerts_by_key(self, alerts: List[Alert]) -> Dict[str, List[Alert]]:
        """按聚合键分组告警"""
        groups = defaultdict(list)
        
        for alert in alerts:
            # 生成聚合键
            group_key = self._generate_aggregation_key(alert)
            groups[group_key].append(alert)
        
        return groups
    
    def _generate_aggregation_key(self, alert: Alert) -> str:
        """生成聚合键"""
        # 基于服务、组件、告警类型等进行聚合
        key_parts = [
            alert.category.value,
            alert.labels.get('service', 'unknown'),
            alert.labels.get('component', 'unknown'),
            alert.name.split(':')[0] if ':' in alert.name else alert.name  # 告警名称前缀
        ]
        
        return '|'.join(key_parts)
    
    def _create_aggregated_alert(self, group_key: str, alerts: List[Alert]) -> Dict:
        """创建聚合告警"""
        if not alerts:
            return {}
        
        # 选择最高严重程度
        max_severity = max(alerts, key=lambda a: self._severity_weight(a.severity))
        
        # 统计信息
        severity_counts = defaultdict(int)
        for alert in alerts:
            severity_counts[alert.severity.value] += 1
        
        # 创建聚合告警信息
        aggregated = {
            'type': 'aggregated',
            'group_key': group_key,
            'count': len(alerts),
            'severity': max_severity.severity.value,
            'category': alerts[0].category.value,
            'title': f"聚合告警: {group_key} ({len(alerts)}个告警)",
            'description': f"聚合了{len(alerts)}个相关告警",
            'severity_breakdown': dict(severity_counts),
            'first_alert_time': min(alert.created_at for alert in alerts).isoformat(),
            'last_alert_time': max(alert.created_at for alert in alerts).isoformat(),
            'alert_ids': [alert.id for alert in alerts],
            'sample_alerts': [
                {
                    'id': alert.id,
                    'name': alert.name,
                    'severity': alert.severity.value,
                    'created_at': alert.created_at.isoformat()
                }
                for alert in alerts[:5]  # 只显示前5个作为样本
            ]
        }
        
        return aggregated
    
    def _severity_weight(self, severity: AlertSeverity) -> int:
        """获取严重程度权重"""
        weights = {
            AlertSeverity.CRITICAL: 4,
            AlertSeverity.HIGH: 3,
            AlertSeverity.MEDIUM: 2,
            AlertSeverity.LOW: 1
        }
        return weights.get(severity, 0)


class AlertStormDetector:
    """告警风暴检测器"""
    
    def __init__(self, threshold: int = 50, time_window: int = 300):
        self.threshold = threshold  # 告警数量阈值
        self.time_window = time_window  # 时间窗口（秒）
        self.alert_timestamps: List[datetime] = []
    
    def is_alert_storm(self, new_alert_time: datetime = None) -> bool:
        """检测是否发生告警风暴"""
        if new_alert_time is None:
            new_alert_time = datetime.now(timezone.utc)
        
        # 添加新告警时间
        self.alert_timestamps.append(new_alert_time)
        
        # 清理过期时间戳
        cutoff_time = new_alert_time - timedelta(seconds=self.time_window)
        self.alert_timestamps = [
            ts for ts in self.alert_timestamps if ts > cutoff_time
        ]
        
        # 检查是否超过阈值
        is_storm = len(self.alert_timestamps) > self.threshold
        
        if is_storm:
            logger.warning(
                "检测到告警风暴",
                alert_count=len(self.alert_timestamps),
                threshold=self.threshold,
                time_window=self.time_window
            )
        
        return is_storm
    
    def get_current_rate(self) -> float:
        """获取当前告警速率（每分钟）"""
        if not self.alert_timestamps:
            return 0.0
        
        current_time = datetime.now(timezone.utc)
        cutoff_time = current_time - timedelta(seconds=self.time_window)
        
        recent_alerts = [
            ts for ts in self.alert_timestamps if ts > cutoff_time
        ]
        
        # 计算每分钟告警数
        return len(recent_alerts) * 60 / self.time_window


class AlertSuppressor:
    """告警抑制器"""
    
    def __init__(self):
        self.suppression_rules: List[Dict] = []
        self.suppressed_alerts: Set[str] = set()
    
    def add_suppression_rule(self, rule: Dict) -> None:
        """添加抑制规则"""
        self.suppression_rules.append(rule)
        logger.info("添加告警抑制规则", rule=rule)
    
    def should_suppress_alert(self, alert: Alert, active_alerts: List[Alert]) -> bool:
        """判断是否应该抑制告警"""
        for rule in self.suppression_rules:
            if self._matches_suppression_rule(alert, rule, active_alerts):
                logger.debug("告警被抑制规则匹配", alert_id=alert.id, rule=rule)
                return True
        
        return False
    
    def _matches_suppression_rule(self, alert: Alert, rule: Dict, active_alerts: List[Alert]) -> bool:
        """检查告警是否匹配抑制规则"""
        # 检查源告警条件
        source_conditions = rule.get('source', {})
        if not self._matches_conditions(alert, source_conditions):
            return False
        
        # 检查目标告警条件
        target_conditions = rule.get('target', {})
        for active_alert in active_alerts:
            if (active_alert.id != alert.id and 
                self._matches_conditions(active_alert, target_conditions)):
                return True
        
        return False
    
    def _matches_conditions(self, alert: Alert, conditions: Dict) -> bool:
        """检查告警是否匹配条件"""
        for key, value in conditions.items():
            if key == 'severity':
                if alert.severity.value != value:
                    return False
            elif key == 'category':
                if alert.category.value != value:
                    return False
            elif key == 'name':
                if alert.name != value:
                    return False
            elif key == 'labels':
                for label_key, label_value in value.items():
                    if alert.labels.get(label_key) != label_value:
                        return False
        
        return True
