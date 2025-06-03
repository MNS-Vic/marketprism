"""
Security Audit System

Week 6 Day 4: API网关安全系统组件
"""

import asyncio
import logging
import secrets
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class SecurityAuditSystemConfig:
    """安全审计系统配置"""
    enabled: bool = True
    version: str = "1.0.0"
    # 审计配置
    log_level: str = "INFO"
    max_log_entries: int = 10000
    retention_days: int = 90
    # 告警配置
    enable_real_time_alerts: bool = True
    alert_threshold: int = 10
    
class SecurityAuditSystem:
    """
    Security Audit System
    
    企业级安全审计系统：
    - 安全事件记录
    - 审计日志管理
    - 威胁情报收集
    - 合规性报告
    - 实时监控告警
    """
    
    def __init__(self, config: SecurityAuditSystemConfig):
        self.config = config
        self.is_started = False
        
        # 审计日志存储
        self.audit_logs: List[Dict[str, Any]] = []
        self.security_events: List[Dict[str, Any]] = []
        
        # 统计信息
        self.audit_stats = {
            "total_events": 0,
            "security_violations": 0,
            "authentication_events": 0,
            "authorization_events": 0,
            "system_events": 0
        }
        
    async def start(self):
        """启动安全审计系统"""
        logger.info(f"启动 Security Audit System v{self.config.version}")
        
        # 启动日志清理任务
        asyncio.create_task(self._log_cleanup_worker())
        
        self.is_started = True
        logger.info("✅ Security Audit System 启动完成")
        
    async def stop(self):
        """停止安全审计系统"""
        logger.info("停止 Security Audit System")
        self.is_started = False
        
    async def log_security_event(self, event_data: Dict[str, Any]):
        """记录安全事件"""
        try:
            event = {
                "timestamp": datetime.now().isoformat(),
                "event_id": f"evt_{secrets.token_hex(8)}",
                "event_type": event_data.get("event_type", "unknown"),
                "severity": event_data.get("severity", "info"),
                "source_ip": event_data.get("source_ip"),
                "user_id": event_data.get("user_id"),
                "details": event_data,
                "processed": False
            }
            
            self.security_events.append(event)
            self.audit_stats["total_events"] += 1
            
            # 根据事件类型更新统计
            event_type = event_data.get("event_type", "")
            if "violation" in event_type or "attack" in event_type:
                self.audit_stats["security_violations"] += 1
            elif "auth" in event_type:
                self.audit_stats["authentication_events"] += 1
            elif "access" in event_type:
                self.audit_stats["authorization_events"] += 1
            else:
                self.audit_stats["system_events"] += 1
                
            logger.debug(f"记录安全事件: {event['event_type']} - {event['event_id']}")
            
        except Exception as e:
            logger.error(f"记录安全事件失败: {e}")
            
    async def log_audit_event(self, audit_data: Dict[str, Any]):
        """记录审计事件"""
        try:
            audit_entry = {
                "timestamp": datetime.now().isoformat(),
                "audit_id": f"aud_{secrets.token_hex(8)}",
                "action": audit_data.get("action", "unknown"),
                "resource": audit_data.get("resource"),
                "user_id": audit_data.get("user_id"),
                "result": audit_data.get("result", "success"),
                "details": audit_data
            }
            
            self.audit_logs.append(audit_entry)
            logger.debug(f"记录审计事件: {audit_entry['action']} - {audit_entry['audit_id']}")
            
        except Exception as e:
            logger.error(f"记录审计事件失败: {e}")
            
    async def _log_cleanup_worker(self):
        """日志清理工作任务"""
        while self.is_started:
            try:
                current_time = datetime.now()
                cutoff_time = current_time - timedelta(days=30)  # 保留30天
                
                # 清理过期的安全事件
                original_count = len(self.security_events)
                self.security_events = [
                    event for event in self.security_events
                    if datetime.fromisoformat(event["timestamp"]) > cutoff_time
                ]
                
                # 清理过期的审计日志
                original_audit_count = len(self.audit_logs)
                self.audit_logs = [
                    log for log in self.audit_logs
                    if datetime.fromisoformat(log["timestamp"]) > cutoff_time
                ]
                
                cleaned_events = original_count - len(self.security_events)
                cleaned_audits = original_audit_count - len(self.audit_logs)
                
                if cleaned_events > 0 or cleaned_audits > 0:
                    logger.info(f"清理过期日志: 安全事件={cleaned_events}, 审计日志={cleaned_audits}")
                    
                await asyncio.sleep(86400)  # 每天清理一次
                
            except Exception as e:
                logger.error(f"日志清理任务出错: {e}")
                await asyncio.sleep(3600)
                
    def get_recent_events(self, hours: int = 24) -> List[Dict[str, Any]]:
        """获取最近的安全事件"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        return [
            event for event in self.security_events
            if datetime.fromisoformat(event["timestamp"]) > cutoff_time
        ]
        
    def get_security_summary(self) -> Dict[str, Any]:
        """获取安全摘要"""
        recent_events = self.get_recent_events(24)
        
        return {
            "total_events_24h": len(recent_events),
            "security_violations_24h": sum(1 for e in recent_events if "violation" in e.get("event_type", "")),
            "unique_source_ips": len(set(e.get("source_ip") for e in recent_events if e.get("source_ip"))),
            "top_event_types": self._get_top_event_types(recent_events),
            "severity_distribution": self._get_severity_distribution(recent_events)
        }
        
    def _get_top_event_types(self, events: List[Dict[str, Any]]) -> Dict[str, int]:
        """获取主要事件类型"""
        event_types = {}
        for event in events:
            event_type = event.get("event_type", "unknown")
            event_types[event_type] = event_types.get(event_type, 0) + 1
            
        return dict(sorted(event_types.items(), key=lambda x: x[1], reverse=True)[:5])
        
    def _get_severity_distribution(self, events: List[Dict[str, Any]]) -> Dict[str, int]:
        """获取严重程度分布"""
        severity_dist = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        
        for event in events:
            severity = event.get("severity", "info")
            if severity in severity_dist:
                severity_dist[severity] += 1
                
        return severity_dist
        
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.audit_stats,
            "total_security_events": len(self.security_events),
            "total_audit_logs": len(self.audit_logs),
            "recent_events_24h": len(self.get_recent_events(24))
        }
        
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        return {
            "component": "Security Audit System",
            "status": "running" if self.is_started else "stopped",
            "version": self.config.version,
            "statistics": self.get_statistics()
        }