"""
自动化部署引擎 - Week 5 Day 8
提供CI/CD流水线管理、多环境部署自动化、蓝绿部署等功能
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Callable, Any, Union
from concurrent.futures import ThreadPoolExecutor
import json
import random
import uuid

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DeploymentStrategy(Enum):
    """部署策略"""
    ROLLING_UPDATE = "rolling_update"
    BLUE_GREEN = "blue_green"
    CANARY = "canary"
    RECREATE = "recreate"
    A_B_TESTING = "ab_testing"
    FEATURE_FLAG = "feature_flag"


class DeploymentEnvironment(Enum):
    """部署环境"""
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"
    CANARY = "canary"


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLBACK = "rollback"


class PipelineStage(Enum):
    """流水线阶段"""
    SOURCE = "source"
    BUILD = "build"
    TEST = "test"
    SECURITY_SCAN = "security_scan"
    PACKAGE = "package"
    DEPLOY = "deploy"
    POST_DEPLOY_TEST = "post_deploy_test"
    SMOKE_TEST = "smoke_test"


@dataclass
class DeploymentTask:
    """部署任务"""
    task_id: str
    application: str
    version: str
    environment: DeploymentEnvironment
    strategy: DeploymentStrategy
    status: TaskStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_by: str = ""
    config: Dict[str, Any] = field(default_factory=dict)
    logs: List[str] = field(default_factory=list)
    rollback_version: Optional[str] = None
    approval_required: bool = False
    approved_by: str = ""
    approved_at: Optional[datetime] = None


@dataclass
class PipelineStep:
    """流水线步骤"""
    step_id: str
    stage: PipelineStage
    name: str
    command: str
    status: TaskStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration: float = 0.0
    logs: List[str] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)


@dataclass
class Pipeline:
    """CI/CD流水线"""
    pipeline_id: str
    name: str
    application: str
    trigger: str  # manual, webhook, schedule, git_push
    steps: List[PipelineStep]
    status: TaskStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    environment_config: Dict[str, Any] = field(default_factory=dict)
    variables: Dict[str, str] = field(default_factory=dict)


@dataclass
class DeploymentHistory:
    """部署历史"""
    deployment_id: str
    application: str
    version: str
    environment: DeploymentEnvironment
    strategy: DeploymentStrategy
    status: TaskStatus
    deployed_at: datetime
    rolled_back_at: Optional[datetime] = None
    deployed_by: str = ""
    rollback_reason: str = ""
    health_checks: Dict[str, bool] = field(default_factory=dict)
    performance_metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class RollbackPlan:
    """回滚计划"""
    plan_id: str
    application: str
    current_version: str
    target_version: str
    environment: DeploymentEnvironment
    rollback_strategy: str
    estimated_duration: int  # 分钟
    impact_assessment: str
    approval_required: bool = True
    pre_rollback_checks: List[str] = field(default_factory=list)
    post_rollback_checks: List[str] = field(default_factory=list)


@dataclass
class DeploymentRisk:
    """部署风险评估"""
    risk_id: str
    deployment_task: str
    risk_level: str  # low, medium, high, critical
    risk_category: str
    description: str
    likelihood: float  # 0.0-1.0
    impact: float  # 0.0-1.0
    mitigation_actions: List[str] = field(default_factory=list)
    automated_checks: List[str] = field(default_factory=list)


class AutomationDeployment:
    """自动化部署引擎"""
    
    def __init__(self):
        self.deployment_tasks: Dict[str, DeploymentTask] = {}
        self.pipelines: Dict[str, Pipeline] = {}
        self.deployment_history: List[DeploymentHistory] = []
        self.rollback_plans: Dict[str, RollbackPlan] = {}
        self.deployment_risks: List[DeploymentRisk] = []
        self.active_deployments: Dict[str, str] = {}  # environment -> task_id
        self.executor = ThreadPoolExecutor(max_workers=6)
        
        # 初始化默认配置
        self._initialize_default_configs()
        logger.info("自动化部署引擎初始化完成")
    
    def _initialize_default_configs(self):
        """初始化默认配置"""
        
        # 创建示例流水线
        self._create_sample_pipeline("marketprism-collector", "主要数据收集服务")
        self._create_sample_pipeline("marketprism-api", "API服务")
        self._create_sample_pipeline("marketprism-frontend", "前端应用")
        
        # 创建示例风险评估
        self._create_sample_risk_assessments()
        
        logger.info("默认配置初始化完成")
    
    def _create_sample_pipeline(self, application: str, description: str):
        """创建示例流水线"""
        pipeline_id = f"pipeline_{application}_{uuid.uuid4().hex[:8]}"
        
        steps = [
            PipelineStep(
                step_id=f"step_source_{uuid.uuid4().hex[:8]}",
                stage=PipelineStage.SOURCE,
                name="源码检出",
                command="git clone && git checkout",
                status=TaskStatus.PENDING
            ),
            PipelineStep(
                step_id=f"step_build_{uuid.uuid4().hex[:8]}",
                stage=PipelineStage.BUILD,
                name="构建应用",
                command="docker build -t $APP_NAME:$VERSION .",
                status=TaskStatus.PENDING,
                dependencies=["step_source"]
            ),
            PipelineStep(
                step_id=f"step_test_{uuid.uuid4().hex[:8]}",
                stage=PipelineStage.TEST,
                name="运行测试",
                command="pytest tests/",
                status=TaskStatus.PENDING,
                dependencies=["step_build"]
            ),
            PipelineStep(
                step_id=f"step_security_{uuid.uuid4().hex[:8]}",
                stage=PipelineStage.SECURITY_SCAN,
                name="安全扫描",
                command="trivy image $APP_NAME:$VERSION",
                status=TaskStatus.PENDING,
                dependencies=["step_build"]
            ),
            PipelineStep(
                step_id=f"step_package_{uuid.uuid4().hex[:8]}",
                stage=PipelineStage.PACKAGE,
                name="打包制品",
                command="docker push $REGISTRY/$APP_NAME:$VERSION",
                status=TaskStatus.PENDING,
                dependencies=["step_test", "step_security"]
            ),
            PipelineStep(
                step_id=f"step_deploy_{uuid.uuid4().hex[:8]}",
                stage=PipelineStage.DEPLOY,
                name="部署应用",
                command="kubectl apply -f k8s/",
                status=TaskStatus.PENDING,
                dependencies=["step_package"]
            ),
            PipelineStep(
                step_id=f"step_smoke_{uuid.uuid4().hex[:8]}",
                stage=PipelineStage.SMOKE_TEST,
                name="冒烟测试",
                command="curl -f $APP_URL/health",
                status=TaskStatus.PENDING,
                dependencies=["step_deploy"]
            )
        ]
        
        pipeline = Pipeline(
            pipeline_id=pipeline_id,
            name=f"{application} CI/CD Pipeline",
            application=application,
            trigger="git_push",
            steps=steps,
            status=TaskStatus.PENDING,
            created_at=datetime.now(),
            environment_config={
                "REGISTRY": "registry.marketprism.io",
                "K8S_NAMESPACE": "marketprism",
                "APP_URL": f"https://{application}.marketprism.io"
            },
            variables={
                "APP_NAME": application,
                "VERSION": "latest"
            }
        )
        
        self.pipelines[pipeline_id] = pipeline
    
    def _create_sample_risk_assessments(self):
        """创建示例风险评估"""
        risks = [
            DeploymentRisk(
                risk_id="risk_production_deploy",
                deployment_task="production_deployment",
                risk_level="high",
                risk_category="环境风险",
                description="生产环境部署可能影响用户体验",
                likelihood=0.3,
                impact=0.9,
                mitigation_actions=[
                    "使用蓝绿部署策略",
                    "提前进行健康检查",
                    "准备快速回滚方案"
                ],
                automated_checks=[
                    "健康检查端点验证",
                    "数据库连接检查",
                    "关键API响应时间检查"
                ]
            ),
            DeploymentRisk(
                risk_id="risk_database_migration",
                deployment_task="database_migration",
                risk_level="critical",
                risk_category="数据风险",
                description="数据库迁移可能导致数据丢失或服务中断",
                likelihood=0.2,
                impact=1.0,
                mitigation_actions=[
                    "执行数据库备份",
                    "在测试环境验证迁移脚本",
                    "准备回滚脚本"
                ],
                automated_checks=[
                    "数据库备份完整性检查",
                    "迁移脚本语法检查",
                    "数据一致性验证"
                ]
            ),
            DeploymentRisk(
                risk_id="risk_dependency_conflict",
                deployment_task="dependency_update",
                risk_level="medium",
                risk_category="依赖风险",
                description="依赖库更新可能引入不兼容问题",
                likelihood=0.4,
                impact=0.6,
                mitigation_actions=[
                    "运行完整测试套件",
                    "执行兼容性测试",
                    "逐步灰度发布"
                ],
                automated_checks=[
                    "单元测试执行",
                    "集成测试验证",
                    "性能回归测试"
                ]
            )
        ]
        
        self.deployment_risks.extend(risks)
    
    def create_deployment_task(
        self,
        application: str,
        version: str,
        environment: DeploymentEnvironment,
        strategy: DeploymentStrategy,
        created_by: str = "",
        config: Optional[Dict[str, Any]] = None
    ) -> str:
        """创建部署任务"""
        try:
            task_id = f"deploy_{application}_{environment.value}_{uuid.uuid4().hex[:8]}"
            
            task = DeploymentTask(
                task_id=task_id,
                application=application,
                version=version,
                environment=environment,
                strategy=strategy,
                status=TaskStatus.PENDING,
                created_at=datetime.now(),
                created_by=created_by,
                config=config or {},
                approval_required=environment == DeploymentEnvironment.PRODUCTION
            )
            
            self.deployment_tasks[task_id] = task
            
            # 执行风险评估
            self._assess_deployment_risk(task)
            
            logger.info(f"创建部署任务: {task_id} ({application} {version} -> {environment.value})")
            return task_id
            
        except Exception as e:
            logger.error(f"创建部署任务失败: {e}")
            return ""
    
    def _assess_deployment_risk(self, task: DeploymentTask):
        """评估部署风险"""
        try:
            risk_score = 0.0
            risk_factors = []
            
            # 环境风险评估
            if task.environment == DeploymentEnvironment.PRODUCTION:
                risk_score += 0.3
                risk_factors.append("生产环境部署")
            
            # 策略风险评估
            if task.strategy == DeploymentStrategy.RECREATE:
                risk_score += 0.2
                risk_factors.append("重新创建部署策略")
            elif task.strategy == DeploymentStrategy.BLUE_GREEN:
                risk_score -= 0.1
                risk_factors.append("蓝绿部署策略(低风险)")
            
            # 时间风险评估
            current_hour = datetime.now().hour
            if 9 <= current_hour <= 17:  # 工作时间
                risk_score += 0.1
                risk_factors.append("工作时间部署")
            
            # 版本风险评估
            if "beta" in task.version or "alpha" in task.version:
                risk_score += 0.2
                risk_factors.append("预发布版本")
            
            # 更新任务配置
            task.config["risk_score"] = min(risk_score, 1.0)
            task.config["risk_factors"] = risk_factors
            task.config["risk_assessment_completed"] = True
            
            logger.debug(f"部署风险评估完成: {task.task_id}, 风险分数: {risk_score:.2f}")
            
        except Exception as e:
            logger.error(f"部署风险评估失败: {e}")
    
    def execute_deployment(self, task_id: str) -> bool:
        """执行部署"""
        try:
            task = self.deployment_tasks.get(task_id)
            if not task:
                logger.error(f"部署任务不存在: {task_id}")
                return False
            
            if task.status != TaskStatus.PENDING:
                logger.error(f"部署任务状态不正确: {task.status}")
                return False
            
            # 检查审批
            if task.approval_required and not task.approved_by:
                logger.warning(f"部署任务需要审批: {task_id}")
                return False
            
            # 检查环境冲突
            current_deployment = self.active_deployments.get(task.environment.value)
            if current_deployment and current_deployment != task_id:
                logger.error(f"环境 {task.environment.value} 正在进行其他部署: {current_deployment}")
                return False
            
            # 开始部署
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now()
            self.active_deployments[task.environment.value] = task_id
            
            # 异步执行部署
            self.executor.submit(self._execute_deployment_async, task)
            
            logger.info(f"开始执行部署: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"执行部署失败: {e}")
            return False
    
    def _execute_deployment_async(self, task: DeploymentTask):
        """异步执行部署"""
        try:
            deployment_steps = self._get_deployment_steps(task)
            
            for step_name, step_func in deployment_steps:
                task.logs.append(f"执行步骤: {step_name}")
                logger.info(f"执行部署步骤: {step_name} (任务: {task.task_id})")
                
                success = step_func(task)
                if not success:
                    task.status = TaskStatus.FAILED
                    task.logs.append(f"步骤失败: {step_name}")
                    logger.error(f"部署步骤失败: {step_name}")
                    break
                
                task.logs.append(f"步骤完成: {step_name}")
            
            if task.status == TaskStatus.RUNNING:
                task.status = TaskStatus.SUCCESS
                task.logs.append("部署成功完成")
                
                # 记录部署历史
                self._record_deployment_history(task)
                
                logger.info(f"部署成功完成: {task.task_id}")
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.logs.append(f"部署异常: {str(e)}")
            logger.error(f"部署执行异常: {e}")
        
        finally:
            task.completed_at = datetime.now()
            # 清理活跃部署记录
            if self.active_deployments.get(task.environment.value) == task.task_id:
                del self.active_deployments[task.environment.value]
    
    def _get_deployment_steps(self, task: DeploymentTask) -> List[tuple]:
        """获取部署步骤"""
        if task.strategy == DeploymentStrategy.BLUE_GREEN:
            return [
                ("准备蓝绿环境", self._prepare_blue_green),
                ("部署到绿色环境", self._deploy_to_green),
                ("健康检查", self._health_check),
                ("切换流量", self._switch_traffic),
                ("清理蓝色环境", self._cleanup_blue)
            ]
        elif task.strategy == DeploymentStrategy.ROLLING_UPDATE:
            return [
                ("滚动更新开始", self._start_rolling_update),
                ("逐步替换实例", self._rolling_replace_instances),
                ("验证部署", self._verify_deployment),
                ("完成滚动更新", self._complete_rolling_update)
            ]
        elif task.strategy == DeploymentStrategy.CANARY:
            return [
                ("创建金丝雀版本", self._create_canary),
                ("分配少量流量", self._route_canary_traffic),
                ("监控金丝雀指标", self._monitor_canary),
                ("扩展到全量", self._expand_canary)
            ]
        else:
            return [
                ("停止旧版本", self._stop_old_version),
                ("部署新版本", self._deploy_new_version),
                ("启动新版本", self._start_new_version),
                ("验证部署", self._verify_deployment)
            ]
    
    def _prepare_blue_green(self, task: DeploymentTask) -> bool:
        """准备蓝绿环境"""
        try:
            # 模拟蓝绿环境准备
            task.logs.append("检查蓝色环境状态")
            task.logs.append("准备绿色环境资源")
            return True
        except Exception as e:
            task.logs.append(f"蓝绿环境准备失败: {e}")
            return False
    
    def _deploy_to_green(self, task: DeploymentTask) -> bool:
        """部署到绿色环境"""
        try:
            # 模拟绿色环境部署
            task.logs.append(f"部署 {task.application} {task.version} 到绿色环境")
            task.logs.append("启动绿色环境服务")
            return True
        except Exception as e:
            task.logs.append(f"绿色环境部署失败: {e}")
            return False
    
    def _health_check(self, task: DeploymentTask) -> bool:
        """健康检查"""
        try:
            # 模拟健康检查
            task.logs.append("执行健康检查")
            task.logs.append("检查应用响应")
            task.logs.append("验证数据库连接")
            task.logs.append("健康检查通过")
            return True
        except Exception as e:
            task.logs.append(f"健康检查失败: {e}")
            return False
    
    def _switch_traffic(self, task: DeploymentTask) -> bool:
        """切换流量"""
        try:
            # 模拟流量切换
            task.logs.append("切换负载均衡器流量")
            task.logs.append("流量已切换到绿色环境")
            return True
        except Exception as e:
            task.logs.append(f"流量切换失败: {e}")
            return False
    
    def _cleanup_blue(self, task: DeploymentTask) -> bool:
        """清理蓝色环境"""
        try:
            # 模拟蓝色环境清理
            task.logs.append("停止蓝色环境服务")
            task.logs.append("释放蓝色环境资源")
            return True
        except Exception as e:
            task.logs.append(f"蓝色环境清理失败: {e}")
            return False
    
    def _start_rolling_update(self, task: DeploymentTask) -> bool:
        """开始滚动更新"""
        try:
            task.logs.append("开始滚动更新")
            task.logs.append("设置滚动更新策略")
            return True
        except Exception as e:
            task.logs.append(f"滚动更新开始失败: {e}")
            return False
    
    def _rolling_replace_instances(self, task: DeploymentTask) -> bool:
        """滚动替换实例"""
        try:
            task.logs.append("逐步替换应用实例")
            task.logs.append("等待新实例就绪")
            return True
        except Exception as e:
            task.logs.append(f"实例替换失败: {e}")
            return False
    
    def _verify_deployment(self, task: DeploymentTask) -> bool:
        """验证部署"""
        try:
            task.logs.append("验证应用部署状态")
            task.logs.append("检查服务可用性")
            return True
        except Exception as e:
            task.logs.append(f"部署验证失败: {e}")
            return False
    
    def _complete_rolling_update(self, task: DeploymentTask) -> bool:
        """完成滚动更新"""
        try:
            task.logs.append("滚动更新完成")
            return True
        except Exception as e:
            task.logs.append(f"滚动更新完成失败: {e}")
            return False
    
    def _create_canary(self, task: DeploymentTask) -> bool:
        """创建金丝雀版本"""
        try:
            task.logs.append("创建金丝雀部署")
            return True
        except Exception as e:
            task.logs.append(f"金丝雀创建失败: {e}")
            return False
    
    def _route_canary_traffic(self, task: DeploymentTask) -> bool:
        """分配金丝雀流量"""
        try:
            task.logs.append("分配5%流量到金丝雀版本")
            return True
        except Exception as e:
            task.logs.append(f"金丝雀流量分配失败: {e}")
            return False
    
    def _monitor_canary(self, task: DeploymentTask) -> bool:
        """监控金丝雀指标"""
        try:
            task.logs.append("监控金丝雀版本指标")
            return True
        except Exception as e:
            task.logs.append(f"金丝雀监控失败: {e}")
            return False
    
    def _expand_canary(self, task: DeploymentTask) -> bool:
        """扩展金丝雀到全量"""
        try:
            task.logs.append("扩展金丝雀到100%流量")
            return True
        except Exception as e:
            task.logs.append(f"金丝雀扩展失败: {e}")
            return False
    
    def _stop_old_version(self, task: DeploymentTask) -> bool:
        """停止旧版本"""
        try:
            task.logs.append("停止旧版本服务")
            return True
        except Exception as e:
            task.logs.append(f"停止旧版本失败: {e}")
            return False
    
    def _deploy_new_version(self, task: DeploymentTask) -> bool:
        """部署新版本"""
        try:
            task.logs.append(f"部署新版本 {task.version}")
            return True
        except Exception as e:
            task.logs.append(f"新版本部署失败: {e}")
            return False
    
    def _start_new_version(self, task: DeploymentTask) -> bool:
        """启动新版本"""
        try:
            task.logs.append("启动新版本服务")
            return True
        except Exception as e:
            task.logs.append(f"新版本启动失败: {e}")
            return False
    
    def _record_deployment_history(self, task: DeploymentTask):
        """记录部署历史"""
        try:
            history = DeploymentHistory(
                deployment_id=task.task_id,
                application=task.application,
                version=task.version,
                environment=task.environment,
                strategy=task.strategy,
                status=task.status,
                deployed_at=task.completed_at or datetime.now(),
                deployed_by=task.created_by,
                health_checks={
                    "api_health": True,
                    "database_connection": True,
                    "external_services": True
                },
                performance_metrics={
                    "response_time": random.uniform(100, 500),
                    "error_rate": random.uniform(0, 2),
                    "throughput": random.uniform(1000, 5000)
                }
            )
            
            self.deployment_history.append(history)
            
        except Exception as e:
            logger.error(f"记录部署历史失败: {e}")
    
    def approve_deployment(self, task_id: str, approved_by: str) -> bool:
        """审批部署"""
        try:
            task = self.deployment_tasks.get(task_id)
            if not task:
                return False
            
            task.approved_by = approved_by
            task.approved_at = datetime.now()
            
            logger.info(f"部署任务已审批: {task_id} by {approved_by}")
            return True
            
        except Exception as e:
            logger.error(f"审批部署失败: {e}")
            return False
    
    def create_rollback_plan(self, application: str, environment: DeploymentEnvironment, target_version: str) -> str:
        """创建回滚计划"""
        try:
            # 找到当前版本
            current_deployment = None
            for history in reversed(self.deployment_history):
                if (history.application == application and 
                    history.environment == environment and 
                    history.status == TaskStatus.SUCCESS):
                    current_deployment = history
                    break
            
            if not current_deployment:
                logger.error(f"未找到当前部署版本: {application} {environment.value}")
                return ""
            
            plan_id = f"rollback_{application}_{environment.value}_{uuid.uuid4().hex[:8]}"
            
            plan = RollbackPlan(
                plan_id=plan_id,
                application=application,
                current_version=current_deployment.version,
                target_version=target_version,
                environment=environment,
                rollback_strategy="blue_green",
                estimated_duration=15,
                impact_assessment="服务短暂中断(预计<5分钟)",
                pre_rollback_checks=[
                    "验证目标版本可用性",
                    "检查数据库兼容性",
                    "确认配置文件兼容"
                ],
                post_rollback_checks=[
                    "健康检查",
                    "功能验证",
                    "性能监控"
                ]
            )
            
            self.rollback_plans[plan_id] = plan
            
            logger.info(f"创建回滚计划: {plan_id}")
            return plan_id
            
        except Exception as e:
            logger.error(f"创建回滚计划失败: {e}")
            return ""
    
    def execute_rollback(self, plan_id: str) -> bool:
        """执行回滚"""
        try:
            plan = self.rollback_plans.get(plan_id)
            if not plan:
                return False
            
            # 创建回滚部署任务
            rollback_task_id = self.create_deployment_task(
                application=plan.application,
                version=plan.target_version,
                environment=plan.environment,
                strategy=DeploymentStrategy.BLUE_GREEN,
                created_by="system_rollback",
                config={"is_rollback": True, "rollback_plan": plan_id}
            )
            
            if rollback_task_id:
                # 自动审批回滚任务
                self.approve_deployment(rollback_task_id, "auto_approved_rollback")
                # 执行回滚
                return self.execute_deployment(rollback_task_id)
            
            return False
            
        except Exception as e:
            logger.error(f"执行回滚失败: {e}")
            return False
    
    def get_deployment_stats(self) -> Dict[str, Any]:
        """获取部署统计信息"""
        try:
            stats = {
                "total_tasks": len(self.deployment_tasks),
                "active_deployments": len(self.active_deployments),
                "pipelines": len(self.pipelines),
                "deployment_history": len(self.deployment_history),
                "rollback_plans": len(self.rollback_plans),
                "deployment_risks": len(self.deployment_risks)
            }
            
            # 统计任务状态
            status_counts = {}
            for task in self.deployment_tasks.values():
                status = task.status.value
                status_counts[status] = status_counts.get(status, 0) + 1
            
            stats["task_status_counts"] = status_counts
            
            # 统计环境分布
            env_counts = {}
            for task in self.deployment_tasks.values():
                env = task.environment.value
                env_counts[env] = env_counts.get(env, 0) + 1
            
            stats["environment_counts"] = env_counts
            
            # 统计部署策略
            strategy_counts = {}
            for task in self.deployment_tasks.values():
                strategy = task.strategy.value
                strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
            
            stats["strategy_counts"] = strategy_counts
            
            return stats
            
        except Exception as e:
            logger.error(f"获取部署统计失败: {e}")
            return {}


# 生成示例部署任务的辅助函数
def generate_sample_deployments(deployment_engine: AutomationDeployment, count: int = 10):
    """生成示例部署任务"""
    applications = ["marketprism-collector", "marketprism-api", "marketprism-frontend", "marketprism-processor"]
    environments = list(DeploymentEnvironment)
    strategies = list(DeploymentStrategy)
    
    for i in range(count):
        app = random.choice(applications)
        env = random.choice(environments)
        strategy = random.choice(strategies)
        version = f"v1.{random.randint(0, 10)}.{random.randint(0, 20)}"
        
        task_id = deployment_engine.create_deployment_task(
            application=app,
            version=version,
            environment=env,
            strategy=strategy,
            created_by=f"user_{random.randint(1, 5)}"
        )
        
        # 随机审批一些任务
        if task_id and random.random() > 0.5:
            deployment_engine.approve_deployment(task_id, "admin")
            
            # 随机执行一些任务
            if random.random() > 0.3:
                deployment_engine.execute_deployment(task_id)