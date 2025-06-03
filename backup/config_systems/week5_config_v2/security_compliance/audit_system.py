"""
企业级审计系统

提供完整的安全审计日志记录、审计计划管理、审计报告生成和审计分析功能。
支持多种审计标准和要求，实现企业级审计管理能力。

Author: MarketPrism Team
Date: 2025-01-28
"""

import time
import json
import uuid
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set, Tuple, Union
from enum import Enum
from dataclasses import dataclass, asdict
import logging
from concurrent.futures import ThreadPoolExecutor
import threading
import os
import gzip
import pickle

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AuditEventType(Enum):
    """审计事件类型"""
    LOGIN = "login"                   # 登录事件
    LOGOUT = "logout"                 # 登出事件
    ACCESS = "access"                 # 访问事件
    MODIFICATION = "modification"     # 修改事件
    DELETION = "deletion"             # 删除事件
    CREATION = "creation"             # 创建事件
    CONFIGURATION = "configuration"  # 配置变更
    SECURITY = "security"             # 安全事件
    COMPLIANCE = "compliance"         # 合规事件
    SYSTEM = "system"                 # 系统事件
    ERROR = "error"                   # 错误事件
    WARNING = "warning"               # 警告事件

class AuditSeverity(Enum):
    """审计严重程度"""
    CRITICAL = "critical"             # 严重
    HIGH = "high"                     # 高
    MEDIUM = "medium"                 # 中等
    LOW = "low"                       # 低
    INFO = "info"                     # 信息

class AuditSource(Enum):
    """审计源"""
    APPLICATION = "application"       # 应用程序
    SYSTEM = "system"                 # 系统
    DATABASE = "database"             # 数据库
    NETWORK = "network"               # 网络
    SECURITY = "security"             # 安全设备
    USER = "user"                     # 用户操作
    API = "api"                       # API调用
    EXTERNAL = "external"             # 外部系统

class AuditPlanStatus(Enum):
    """审计计划状态"""
    PLANNED = "planned"               # 已计划
    IN_PROGRESS = "in_progress"       # 进行中
    COMPLETED = "completed"           # 已完成
    CANCELLED = "cancelled"           # 已取消
    POSTPONED = "postponed"           # 已推迟

@dataclass
class AuditEvent:
    """审计事件数据类"""
    id: str
    timestamp: datetime
    event_type: AuditEventType
    severity: AuditSeverity
    source: AuditSource
    user_id: Optional[str]
    session_id: Optional[str]
    ip_address: Optional[str]
    resource: str
    action: str
    description: str
    details: Dict[str, Any]
    outcome: str  # success, failure, error
    risk_score: float  # 0.0-1.0
    tags: Set[str]
    
    def __post_init__(self):
        if isinstance(self.tags, list):
            self.tags = set(self.tags)
        elif self.tags is None:
            self.tags = set()

@dataclass
class AuditPlan:
    """审计计划数据类"""
    id: str
    name: str
    description: str
    audit_type: str  # compliance, security, operational, financial
    scope: List[str]  # 审计范围
    start_date: datetime
    end_date: datetime
    auditor: str
    status: AuditPlanStatus
    objectives: List[str]
    criteria: List[str]
    methodology: str
    findings: List[Dict[str, Any]]
    recommendations: List[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    progress: float  # 0.0-1.0

@dataclass
class AuditReport:
    """审计报告数据类"""
    id: str
    plan_id: str
    title: str
    report_type: str
    period_start: datetime
    period_end: datetime
    generated_at: datetime
    generated_by: str
    summary: Dict[str, Any]
    findings: List[Dict[str, Any]]
    recommendations: List[Dict[str, Any]]
    risk_assessment: Dict[str, Any]
    compliance_status: Dict[str, Any]
    appendices: List[Dict[str, Any]]

class AuditStorage:
    """审计存储管理器"""
    
    def __init__(self, storage_path: str = "./audit_data"):
        """初始化审计存储"""
        self.storage_path = storage_path
        self.events_path = os.path.join(storage_path, "events")
        self.plans_path = os.path.join(storage_path, "plans")
        self.reports_path = os.path.join(storage_path, "reports")
        
        # 创建存储目录
        for path in [self.events_path, self.plans_path, self.reports_path]:
            os.makedirs(path, exist_ok=True)
        
        self._lock = threading.Lock()
    
    def store_event(self, event: AuditEvent) -> bool:
        """存储审计事件"""
        try:
            # 按日期分组存储
            date_str = event.timestamp.strftime("%Y-%m-%d")
            file_path = os.path.join(self.events_path, f"events_{date_str}.json")
            
            event_data = asdict(event)
            # 处理特殊类型
            event_data['timestamp'] = event.timestamp.isoformat()
            event_data['event_type'] = event.event_type.value
            event_data['severity'] = event.severity.value
            event_data['source'] = event.source.value
            event_data['tags'] = list(event.tags)
            
            with self._lock:
                # 追加模式写入
                if os.path.exists(file_path):
                    with open(file_path, 'r') as f:
                        events = json.load(f)
                else:
                    events = []
                
                events.append(event_data)
                
                with open(file_path, 'w') as f:
                    json.dump(events, f, indent=2, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            logger.error(f"存储审计事件失败: {e}")
            return False
    
    def load_events(self, start_date: Optional[datetime] = None,
                   end_date: Optional[datetime] = None) -> List[AuditEvent]:
        """加载审计事件"""
        try:
            events = []
            
            # 确定日期范围
            if start_date is None:
                start_date = datetime.now() - timedelta(days=30)
            if end_date is None:
                end_date = datetime.now()
            
            # 遍历日期范围内的文件
            current_date = start_date.date()
            while current_date <= end_date.date():
                file_path = os.path.join(self.events_path, f"events_{current_date}.json")
                
                if os.path.exists(file_path):
                    with open(file_path, 'r') as f:
                        daily_events = json.load(f)
                    
                    for event_data in daily_events:
                        # 重构事件对象
                        event_data['timestamp'] = datetime.fromisoformat(event_data['timestamp'])
                        event_data['event_type'] = AuditEventType(event_data['event_type'])
                        event_data['severity'] = AuditSeverity(event_data['severity'])
                        event_data['source'] = AuditSource(event_data['source'])
                        event_data['tags'] = set(event_data['tags'])
                        
                        event = AuditEvent(**event_data)
                        
                        # 检查时间范围
                        if start_date <= event.timestamp <= end_date:
                            events.append(event)
                
                current_date += timedelta(days=1)
            
            return events
            
        except Exception as e:
            logger.error(f"加载审计事件失败: {e}")
            return []
    
    def store_plan(self, plan: AuditPlan) -> bool:
        """存储审计计划"""
        try:
            file_path = os.path.join(self.plans_path, f"plan_{plan.id}.json")
            
            plan_data = asdict(plan)
            # 处理特殊类型
            plan_data['start_date'] = plan.start_date.isoformat()
            plan_data['end_date'] = plan.end_date.isoformat()
            plan_data['created_at'] = plan.created_at.isoformat()
            plan_data['updated_at'] = plan.updated_at.isoformat()
            plan_data['status'] = plan.status.value
            
            with open(file_path, 'w') as f:
                json.dump(plan_data, f, indent=2, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            logger.error(f"存储审计计划失败: {e}")
            return False
    
    def load_plan(self, plan_id: str) -> Optional[AuditPlan]:
        """加载审计计划"""
        try:
            file_path = os.path.join(self.plans_path, f"plan_{plan_id}.json")
            
            if not os.path.exists(file_path):
                return None
            
            with open(file_path, 'r') as f:
                plan_data = json.load(f)
            
            # 重构计划对象
            plan_data['start_date'] = datetime.fromisoformat(plan_data['start_date'])
            plan_data['end_date'] = datetime.fromisoformat(plan_data['end_date'])
            plan_data['created_at'] = datetime.fromisoformat(plan_data['created_at'])
            plan_data['updated_at'] = datetime.fromisoformat(plan_data['updated_at'])
            plan_data['status'] = AuditPlanStatus(plan_data['status'])
            
            return AuditPlan(**plan_data)
            
        except Exception as e:
            logger.error(f"加载审计计划失败: {e}")
            return None
    
    def list_plans(self) -> List[str]:
        """列出所有审计计划ID"""
        try:
            plan_ids = []
            for filename in os.listdir(self.plans_path):
                if filename.startswith("plan_") and filename.endswith(".json"):
                    plan_id = filename[5:-5]  # 移除 "plan_" 前缀和 ".json" 后缀
                    plan_ids.append(plan_id)
            return plan_ids
        except Exception as e:
            logger.error(f"列出审计计划失败: {e}")
            return []

class AuditSystem:
    """企业级审计系统"""
    
    def __init__(self, storage_path: str = "./audit_data"):
        """初始化审计系统"""
        self.storage = AuditStorage(storage_path)
        self.event_buffer: List[AuditEvent] = []
        self.buffer_size = 100
        self.auto_flush_enabled = True
        self.flush_interval = 60  # 秒
        self.executor = ThreadPoolExecutor(max_workers=3)
        self._lock = threading.Lock()
        
        # 启动自动刷新
        if self.auto_flush_enabled:
            self._start_auto_flush()
        
        logger.info("AuditSystem 初始化完成")
    
    def _start_auto_flush(self):
        """启动自动刷新线程"""
        def flush_loop():
            while self.auto_flush_enabled:
                try:
                    time.sleep(self.flush_interval)
                    self.flush_events()
                except Exception as e:
                    logger.error(f"自动刷新错误: {e}")
        
        flush_thread = threading.Thread(target=flush_loop, daemon=True)
        flush_thread.start()
    
    def log_event(self, event_type: AuditEventType, action: str, resource: str,
                 description: str, severity: AuditSeverity = AuditSeverity.INFO,
                 source: AuditSource = AuditSource.APPLICATION,
                 user_id: Optional[str] = None, session_id: Optional[str] = None,
                 ip_address: Optional[str] = None, details: Optional[Dict] = None,
                 outcome: str = "success", tags: Optional[Set[str]] = None) -> str:
        """记录审计事件"""
        try:
            # 生成事件ID
            event_id = str(uuid.uuid4())
            
            # 计算风险分数
            risk_score = self._calculate_risk_score(event_type, severity, outcome)
            
            # 创建事件
            event = AuditEvent(
                id=event_id,
                timestamp=datetime.now(),
                event_type=event_type,
                severity=severity,
                source=source,
                user_id=user_id,
                session_id=session_id,
                ip_address=ip_address,
                resource=resource,
                action=action,
                description=description,
                details=details or {},
                outcome=outcome,
                risk_score=risk_score,
                tags=tags or set()
            )
            
            # 添加到缓冲区
            with self._lock:
                self.event_buffer.append(event)
                
                # 如果缓冲区满了，立即刷新
                if len(self.event_buffer) >= self.buffer_size:
                    self._flush_buffer()
            
            logger.debug(f"记录审计事件: {event_id}")
            return event_id
            
        except Exception as e:
            logger.error(f"记录审计事件失败: {e}")
            return ""
    
    def _calculate_risk_score(self, event_type: AuditEventType, severity: AuditSeverity,
                            outcome: str) -> float:
        """计算风险分数"""
        # 基础分数
        base_score = {
            AuditEventType.LOGIN: 0.1,
            AuditEventType.LOGOUT: 0.05,
            AuditEventType.ACCESS: 0.2,
            AuditEventType.MODIFICATION: 0.5,
            AuditEventType.DELETION: 0.7,
            AuditEventType.CREATION: 0.3,
            AuditEventType.CONFIGURATION: 0.6,
            AuditEventType.SECURITY: 0.8,
            AuditEventType.COMPLIANCE: 0.4,
            AuditEventType.SYSTEM: 0.3,
            AuditEventType.ERROR: 0.4,
            AuditEventType.WARNING: 0.2
        }.get(event_type, 0.3)
        
        # 严重程度乘数
        severity_multiplier = {
            AuditSeverity.CRITICAL: 2.0,
            AuditSeverity.HIGH: 1.5,
            AuditSeverity.MEDIUM: 1.0,
            AuditSeverity.LOW: 0.7,
            AuditSeverity.INFO: 0.5
        }.get(severity, 1.0)
        
        # 结果乘数
        outcome_multiplier = {
            "success": 1.0,
            "failure": 1.5,
            "error": 1.8
        }.get(outcome, 1.0)
        
        # 计算最终分数
        risk_score = base_score * severity_multiplier * outcome_multiplier
        return min(risk_score, 1.0)  # 限制在0-1范围内
    
    def flush_events(self):
        """刷新事件缓冲区"""
        with self._lock:
            self._flush_buffer()
    
    def _flush_buffer(self):
        """内部刷新缓冲区方法"""
        if not self.event_buffer:
            return
        
        try:
            # 复制缓冲区并清空
            events_to_flush = self.event_buffer.copy()
            self.event_buffer.clear()
            
            # 异步存储事件
            for event in events_to_flush:
                self.executor.submit(self.storage.store_event, event)
            
            logger.debug(f"刷新了 {len(events_to_flush)} 个审计事件")
            
        except Exception as e:
            logger.error(f"刷新事件缓冲区失败: {e}")
            # 将事件重新加入缓冲区
            self.event_buffer.extend(events_to_flush)
    
    def create_audit_plan(self, name: str, description: str, audit_type: str,
                         scope: List[str], start_date: datetime, end_date: datetime,
                         auditor: str, objectives: List[str],
                         criteria: List[str], methodology: str) -> str:
        """创建审计计划"""
        try:
            plan_id = str(uuid.uuid4())
            
            plan = AuditPlan(
                id=plan_id,
                name=name,
                description=description,
                audit_type=audit_type,
                scope=scope,
                start_date=start_date,
                end_date=end_date,
                auditor=auditor,
                status=AuditPlanStatus.PLANNED,
                objectives=objectives,
                criteria=criteria,
                methodology=methodology,
                findings=[],
                recommendations=[],
                created_at=datetime.now(),
                updated_at=datetime.now(),
                progress=0.0
            )
            
            # 存储计划
            if self.storage.store_plan(plan):
                # 记录审计事件
                self.log_event(
                    event_type=AuditEventType.CREATION,
                    action="create_audit_plan",
                    resource=f"audit_plan:{plan_id}",
                    description=f"创建审计计划: {name}",
                    severity=AuditSeverity.INFO,
                    details={"plan_type": audit_type, "auditor": auditor}
                )
                
                logger.info(f"创建审计计划: {name} ({plan_id})")
                return plan_id
            else:
                logger.error(f"存储审计计划失败: {plan_id}")
                return ""
                
        except Exception as e:
            logger.error(f"创建审计计划失败: {e}")
            return ""
    
    def update_audit_plan(self, plan_id: str, updates: Dict[str, Any]) -> bool:
        """更新审计计划"""
        try:
            plan = self.storage.load_plan(plan_id)
            if not plan:
                logger.error(f"审计计划不存在: {plan_id}")
                return False
            
            # 更新字段
            for key, value in updates.items():
                if hasattr(plan, key):
                    setattr(plan, key, value)
            
            plan.updated_at = datetime.now()
            
            # 存储更新后的计划
            if self.storage.store_plan(plan):
                # 记录审计事件
                self.log_event(
                    event_type=AuditEventType.MODIFICATION,
                    action="update_audit_plan",
                    resource=f"audit_plan:{plan_id}",
                    description=f"更新审计计划: {plan.name}",
                    severity=AuditSeverity.INFO,
                    details={"updated_fields": list(updates.keys())}
                )
                
                logger.info(f"更新审计计划: {plan_id}")
                return True
            else:
                logger.error(f"存储更新的审计计划失败: {plan_id}")
                return False
                
        except Exception as e:
            logger.error(f"更新审计计划失败: {e}")
            return False
    
    def add_finding(self, plan_id: str, finding: Dict[str, Any]) -> bool:
        """添加审计发现"""
        try:
            plan = self.storage.load_plan(plan_id)
            if not plan:
                logger.error(f"审计计划不存在: {plan_id}")
                return False
            
            # 添加发现ID和时间戳
            finding["id"] = str(uuid.uuid4())
            finding["timestamp"] = datetime.now().isoformat()
            
            plan.findings.append(finding)
            plan.updated_at = datetime.now()
            
            # 存储更新后的计划
            if self.storage.store_plan(plan):
                # 记录审计事件
                self.log_event(
                    event_type=AuditEventType.CREATION,
                    action="add_audit_finding",
                    resource=f"audit_plan:{plan_id}",
                    description=f"添加审计发现: {finding.get('title', 'Untitled')}",
                    severity=AuditSeverity.MEDIUM,
                    details={"finding_type": finding.get("type"), "risk_level": finding.get("risk_level")}
                )
                
                logger.info(f"添加审计发现到计划: {plan_id}")
                return True
            else:
                logger.error(f"存储审计发现失败: {plan_id}")
                return False
                
        except Exception as e:
            logger.error(f"添加审计发现失败: {e}")
            return False
    
    def add_recommendation(self, plan_id: str, recommendation: Dict[str, Any]) -> bool:
        """添加审计建议"""
        try:
            plan = self.storage.load_plan(plan_id)
            if not plan:
                logger.error(f"审计计划不存在: {plan_id}")
                return False
            
            # 添加建议ID和时间戳
            recommendation["id"] = str(uuid.uuid4())
            recommendation["timestamp"] = datetime.now().isoformat()
            
            plan.recommendations.append(recommendation)
            plan.updated_at = datetime.now()
            
            # 存储更新后的计划
            if self.storage.store_plan(plan):
                # 记录审计事件
                self.log_event(
                    event_type=AuditEventType.CREATION,
                    action="add_audit_recommendation",
                    resource=f"audit_plan:{plan_id}",
                    description=f"添加审计建议: {recommendation.get('title', 'Untitled')}",
                    severity=AuditSeverity.INFO,
                    details={"priority": recommendation.get("priority"), "category": recommendation.get("category")}
                )
                
                logger.info(f"添加审计建议到计划: {plan_id}")
                return True
            else:
                logger.error(f"存储审计建议失败: {plan_id}")
                return False
                
        except Exception as e:
            logger.error(f"添加审计建议失败: {e}")
            return False
    
    def search_events(self, start_date: Optional[datetime] = None,
                     end_date: Optional[datetime] = None,
                     event_types: Optional[List[AuditEventType]] = None,
                     severities: Optional[List[AuditSeverity]] = None,
                     sources: Optional[List[AuditSource]] = None,
                     user_id: Optional[str] = None,
                     resource: Optional[str] = None,
                     tags: Optional[Set[str]] = None,
                     limit: int = 1000) -> List[AuditEvent]:
        """搜索审计事件"""
        try:
            # 加载事件
            events = self.storage.load_events(start_date, end_date)
            
            # 应用过滤器
            filtered_events = []
            for event in events:
                # 检查事件类型
                if event_types and event.event_type not in event_types:
                    continue
                
                # 检查严重程度
                if severities and event.severity not in severities:
                    continue
                
                # 检查事件源
                if sources and event.source not in sources:
                    continue
                
                # 检查用户ID
                if user_id and event.user_id != user_id:
                    continue
                
                # 检查资源
                if resource and resource not in event.resource:
                    continue
                
                # 检查标签
                if tags and not tags.intersection(event.tags):
                    continue
                
                filtered_events.append(event)
                
                # 限制结果数量
                if len(filtered_events) >= limit:
                    break
            
            logger.info(f"搜索到 {len(filtered_events)} 个审计事件")
            return filtered_events
            
        except Exception as e:
            logger.error(f"搜索审计事件失败: {e}")
            return []
    
    def generate_audit_report(self, plan_id: str, title: str,
                            report_type: str = "standard") -> Optional[AuditReport]:
        """生成审计报告"""
        try:
            plan = self.storage.load_plan(plan_id)
            if not plan:
                logger.error(f"审计计划不存在: {plan_id}")
                return None
            
            report_id = str(uuid.uuid4())
            
            # 生成报告摘要
            summary = self._generate_report_summary(plan)
            
            # 生成风险评估
            risk_assessment = self._generate_risk_assessment(plan)
            
            # 生成合规状态
            compliance_status = self._generate_compliance_status(plan)
            
            report = AuditReport(
                id=report_id,
                plan_id=plan_id,
                title=title,
                report_type=report_type,
                period_start=plan.start_date,
                period_end=plan.end_date,
                generated_at=datetime.now(),
                generated_by="audit_system",
                summary=summary,
                findings=plan.findings,
                recommendations=plan.recommendations,
                risk_assessment=risk_assessment,
                compliance_status=compliance_status,
                appendices=[]
            )
            
            # 记录审计事件
            self.log_event(
                event_type=AuditEventType.CREATION,
                action="generate_audit_report",
                resource=f"audit_report:{report_id}",
                description=f"生成审计报告: {title}",
                severity=AuditSeverity.INFO,
                details={"plan_id": plan_id, "report_type": report_type}
            )
            
            logger.info(f"生成审计报告: {title} ({report_id})")
            return report
            
        except Exception as e:
            logger.error(f"生成审计报告失败: {e}")
            return None
    
    def _generate_report_summary(self, plan: AuditPlan) -> Dict[str, Any]:
        """生成报告摘要"""
        return {
            "audit_scope": plan.scope,
            "audit_objectives": plan.objectives,
            "audit_period": f"{plan.start_date.strftime('%Y-%m-%d')} to {plan.end_date.strftime('%Y-%m-%d')}",
            "findings_count": len(plan.findings),
            "recommendations_count": len(plan.recommendations),
            "overall_status": plan.status.value,
            "progress": plan.progress
        }
    
    def _generate_risk_assessment(self, plan: AuditPlan) -> Dict[str, Any]:
        """生成风险评估"""
        risk_levels = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        
        for finding in plan.findings:
            risk_level = finding.get("risk_level", "medium")
            if risk_level in risk_levels:
                risk_levels[risk_level] += 1
        
        total_findings = len(plan.findings)
        if total_findings > 0:
            # 计算风险分数
            risk_score = (
                risk_levels["critical"] * 4 + 
                risk_levels["high"] * 3 + 
                risk_levels["medium"] * 2 + 
                risk_levels["low"] * 1
            ) / (total_findings * 4)
        else:
            risk_score = 0.0
        
        return {
            "overall_risk_score": round(risk_score, 2),
            "risk_distribution": risk_levels,
            "key_risks": [
                finding for finding in plan.findings 
                if finding.get("risk_level") in ["critical", "high"]
            ][:5]
        }
    
    def _generate_compliance_status(self, plan: AuditPlan) -> Dict[str, Any]:
        """生成合规状态"""
        compliance_items = {}
        
        for finding in plan.findings:
            compliance_framework = finding.get("compliance_framework")
            if compliance_framework:
                if compliance_framework not in compliance_items:
                    compliance_items[compliance_framework] = {"total": 0, "issues": 0}
                
                compliance_items[compliance_framework]["total"] += 1
                if finding.get("compliance_status") == "non_compliant":
                    compliance_items[compliance_framework]["issues"] += 1
        
        # 计算合规率
        for framework in compliance_items:
            total = compliance_items[framework]["total"]
            issues = compliance_items[framework]["issues"]
            compliance_rate = (total - issues) / total if total > 0 else 1.0
            compliance_items[framework]["compliance_rate"] = round(compliance_rate * 100, 1)
        
        return {
            "frameworks": compliance_items,
            "overall_compliance_rate": round(
                sum(item["compliance_rate"] for item in compliance_items.values()) / 
                len(compliance_items) if compliance_items else 100, 1
            )
        }
    
    def get_audit_statistics(self, start_date: Optional[datetime] = None,
                           end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """获取审计统计信息"""
        try:
            # 加载事件
            events = self.storage.load_events(start_date, end_date)
            
            if not events:
                return {"message": "无审计数据"}
            
            # 统计事件类型
            event_type_counts = {}
            for event in events:
                event_type = event.event_type.value
                event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1
            
            # 统计严重程度
            severity_counts = {}
            for event in events:
                severity = event.severity.value
                severity_counts[severity] = severity_counts.get(severity, 0) + 1
            
            # 统计事件源
            source_counts = {}
            for event in events:
                source = event.source.value
                source_counts[source] = source_counts.get(source, 0) + 1
            
            # 统计结果
            outcome_counts = {}
            for event in events:
                outcome = event.outcome
                outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
            
            # 计算风险统计
            risk_scores = [event.risk_score for event in events]
            avg_risk_score = sum(risk_scores) / len(risk_scores) if risk_scores else 0
            
            # 统计用户活动
            user_activity = {}
            for event in events:
                if event.user_id:
                    user_activity[event.user_id] = user_activity.get(event.user_id, 0) + 1
            
            return {
                "period": {
                    "start": start_date.isoformat() if start_date else "N/A",
                    "end": end_date.isoformat() if end_date else "N/A"
                },
                "total_events": len(events),
                "event_types": event_type_counts,
                "severity_distribution": severity_counts,
                "source_distribution": source_counts,
                "outcome_distribution": outcome_counts,
                "risk_statistics": {
                    "average_risk_score": round(avg_risk_score, 3),
                    "max_risk_score": max(risk_scores) if risk_scores else 0,
                    "high_risk_events": len([s for s in risk_scores if s >= 0.7])
                },
                "user_activity": dict(list(user_activity.items())[:10])  # 前10个活跃用户
            }
            
        except Exception as e:
            logger.error(f"获取审计统计失败: {e}")
            return {"error": str(e)}
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取审计系统状态"""
        try:
            # 计划统计
            plan_ids = self.storage.list_plans()
            plan_status_counts = {}
            
            for plan_id in plan_ids:
                plan = self.storage.load_plan(plan_id)
                if plan:
                    status = plan.status.value
                    plan_status_counts[status] = plan_status_counts.get(status, 0) + 1
            
            return {
                "buffer_status": {
                    "current_size": len(self.event_buffer),
                    "max_size": self.buffer_size,
                    "auto_flush_enabled": self.auto_flush_enabled
                },
                "plans": {
                    "total": len(plan_ids),
                    "status_distribution": plan_status_counts
                },
                "storage": {
                    "path": self.storage.storage_path,
                    "events_stored": "varies_by_date",
                    "plans_stored": len(plan_ids)
                },
                "system": {
                    "executor_active": not self.executor._shutdown,
                    "last_updated": datetime.now().isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"获取系统状态失败: {e}")
            return {"error": str(e)}
    
    def cleanup(self):
        """清理资源"""
        try:
            # 刷新缓冲区
            self.flush_events()
            
            # 停止自动刷新
            self.auto_flush_enabled = False
            
            # 关闭线程池
            self.executor.shutdown(wait=True)
            
            logger.info("AuditSystem 清理完成")
            
        except Exception as e:
            logger.error(f"清理资源失败: {e}")

if __name__ == "__main__":
    # 演示用法
    audit = AuditSystem()
    
    try:
        # 记录一些示例事件
        print("记录审计事件...")
        
        # 用户登录事件
        audit.log_event(
            event_type=AuditEventType.LOGIN,
            action="user_login",
            resource="application",
            description="用户成功登录系统",
            user_id="user123",
            ip_address="192.168.1.100",
            outcome="success"
        )
        
        # 配置修改事件
        audit.log_event(
            event_type=AuditEventType.CONFIGURATION,
            action="modify_security_policy",
            resource="security_policy",
            description="修改密码策略配置",
            severity=AuditSeverity.MEDIUM,
            user_id="admin456",
            details={"changed_fields": ["min_length", "complexity"]},
            outcome="success"
        )
        
        # 安全事件
        audit.log_event(
            event_type=AuditEventType.SECURITY,
            action="failed_authentication",
            resource="login_system",
            description="多次登录失败，可能的暴力攻击",
            severity=AuditSeverity.HIGH,
            ip_address="10.0.0.5",
            details={"attempts": 5, "timeframe": "5_minutes"},
            outcome="failure"
        )
        
        # 创建审计计划
        print("\n创建审计计划...")
        plan_id = audit.create_audit_plan(
            name="年度安全审计",
            description="对整个系统进行年度安全审计",
            audit_type="security",
            scope=["authentication", "authorization", "encryption", "logging"],
            start_date=datetime.now(),
            end_date=datetime.now() + timedelta(days=30),
            auditor="external_auditor",
            objectives=[
                "评估安全控制有效性",
                "识别安全漏洞",
                "验证合规性"
            ],
            criteria=[
                "ISO 27001标准",
                "NIST安全框架",
                "公司安全政策"
            ],
            methodology="基于风险的审计方法"
        )
        
        print(f"创建审计计划: {plan_id}")
        
        # 添加审计发现
        audit.add_finding(plan_id, {
            "title": "密码策略不符合最佳实践",
            "description": "当前密码策略允许过于简单的密码",
            "type": "security_control",
            "risk_level": "medium",
            "compliance_framework": "NIST",
            "compliance_status": "non_compliant"
        })
        
        # 添加审计建议
        audit.add_recommendation(plan_id, {
            "title": "加强密码策略",
            "description": "实施更严格的密码复杂性要求",
            "priority": "medium",
            "category": "security",
            "estimated_effort": "low",
            "timeline": "2 weeks"
        })
        
        # 生成审计报告
        print("\n生成审计报告...")
        report = audit.generate_audit_report(plan_id, "年度安全审计报告")
        if report:
            print(f"生成审计报告: {report.id}")
            print(f"风险评分: {report.risk_assessment['overall_risk_score']}")
        
        # 获取审计统计
        print("\n审计统计:")
        stats = audit.get_audit_statistics()
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        
        # 获取系统状态
        print("\n系统状态:")
        status = audit.get_system_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))
        
    finally:
        audit.cleanup()