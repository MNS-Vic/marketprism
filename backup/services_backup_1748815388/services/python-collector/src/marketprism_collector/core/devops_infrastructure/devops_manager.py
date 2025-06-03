"""
DevOps基础设施管理器

提供统一的DevOps基础设施管理能力，包括CI/CD流水线、
Docker构建、环境管理、部署自动化、测试自动化和质量门禁的统一管理。
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json
import yaml
from pathlib import Path

# 配置日志
logger = logging.getLogger(__name__)

class DevOpsStatus(Enum):
    """DevOps系统状态枚举"""
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    DEGRADED = "degraded"
    ERROR = "error"
    MAINTENANCE = "maintenance"

class ComponentType(Enum):
    """DevOps组件类型枚举"""
    CI_PIPELINE = "ci_pipeline"
    DOCKER_SYSTEM = "docker_system"
    ENVIRONMENT = "environment"
    DEPLOYMENT = "deployment"
    TESTING = "testing"
    QUALITY_GATE = "quality_gate"

@dataclass
class DevOpsConfig:
    """DevOps基础设施配置"""
    # 基础配置
    enabled: bool = True
    max_concurrent_jobs: int = 10
    default_timeout: int = 1800  # 30分钟
    
    # CI/CD配置
    ci_pipeline_config: Dict[str, Any] = field(default_factory=dict)
    docker_build_config: Dict[str, Any] = field(default_factory=dict)
    environment_config: Dict[str, Any] = field(default_factory=dict)
    deployment_config: Dict[str, Any] = field(default_factory=dict)
    testing_config: Dict[str, Any] = field(default_factory=dict)
    quality_gate_config: Dict[str, Any] = field(default_factory=dict)
    
    # 监控配置
    metrics_enabled: bool = True
    health_check_interval: int = 60
    alert_thresholds: Dict[str, float] = field(default_factory=lambda: {
        'pipeline_failure_rate': 0.1,
        'deployment_failure_rate': 0.05,
        'test_failure_rate': 0.1,
        'build_time_threshold': 600  # 10分钟
    })

@dataclass
class ComponentStatus:
    """组件状态信息"""
    component_type: ComponentType
    status: DevOpsStatus
    last_update: datetime
    health_score: float = 100.0
    error_message: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)

@dataclass
class DevOpsMetrics:
    """DevOps指标数据"""
    # 基础指标
    total_pipelines: int = 0
    successful_pipelines: int = 0
    failed_pipelines: int = 0
    
    total_deployments: int = 0
    successful_deployments: int = 0
    failed_deployments: int = 0
    
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    
    # 性能指标
    avg_pipeline_duration: float = 0.0
    avg_deployment_duration: float = 0.0
    avg_test_duration: float = 0.0
    
    # 质量指标
    code_coverage: float = 0.0
    security_score: float = 0.0
    quality_score: float = 0.0
    
    # 时间戳
    last_updated: datetime = field(default_factory=datetime.now)

class DevOpsInfrastructureManager:
    """
    DevOps基础设施管理器
    
    统一管理CI/CD流水线、Docker构建、环境管理、部署自动化、
    测试自动化和质量门禁等DevOps基础设施组件。
    """
    
    def __init__(self, config: Optional[DevOpsConfig] = None):
        """初始化DevOps基础设施管理器"""
        self.config = config or DevOpsConfig()
        self.status = DevOpsStatus.INITIALIZING
        self.components: Dict[ComponentType, Any] = {}
        self.component_status: Dict[ComponentType, ComponentStatus] = {}
        self.metrics = DevOpsMetrics()
        
        # 内部状态
        self._running_jobs: Dict[str, Any] = {}
        self._health_check_task: Optional[asyncio.Task] = None
        self._metrics_collection_task: Optional[asyncio.Task] = None
        
        logger.info("DevOps基础设施管理器已初始化")
    
    async def initialize(self) -> bool:
        """初始化DevOps基础设施"""
        try:
            logger.info("开始初始化DevOps基础设施...")
            
            # 初始化各个组件
            await self._initialize_components()
            
            # 启动后台任务
            await self._start_background_tasks()
            
            # 更新状态
            self.status = DevOpsStatus.READY
            
            logger.info("DevOps基础设施初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"DevOps基础设施初始化失败: {e}")
            self.status = DevOpsStatus.ERROR
            return False
    
    async def _initialize_components(self):
        """初始化DevOps组件"""
        from .ci_pipeline.pipeline_manager import CIPipelineManager
        from .docker_system.build_manager import DockerBuildSystem
        from .environment.environment_manager import EnvironmentManager
        from .deployment.deployment_manager import DeploymentAutomation
        from .testing.test_orchestrator import TestAutomation
        from .quality_gate.quality_manager import QualityGate
        
        # 初始化CI/CD流水线管理器
        if self.config.ci_pipeline_config.get('enabled', True):
            self.components[ComponentType.CI_PIPELINE] = CIPipelineManager(
                self.config.ci_pipeline_config
            )
            await self._update_component_status(ComponentType.CI_PIPELINE, DevOpsStatus.READY)
        
        # 初始化Docker构建系统
        if self.config.docker_build_config.get('enabled', True):
            self.components[ComponentType.DOCKER_SYSTEM] = DockerBuildSystem(
                self.config.docker_build_config
            )
            await self._update_component_status(ComponentType.DOCKER_SYSTEM, DevOpsStatus.READY)
        
        # 初始化环境管理器
        if self.config.environment_config.get('enabled', True):
            self.components[ComponentType.ENVIRONMENT] = EnvironmentManager(
                self.config.environment_config
            )
            await self._update_component_status(ComponentType.ENVIRONMENT, DevOpsStatus.READY)
        
        # 初始化部署自动化
        if self.config.deployment_config.get('enabled', True):
            self.components[ComponentType.DEPLOYMENT] = DeploymentAutomation(
                self.config.deployment_config
            )
            await self._update_component_status(ComponentType.DEPLOYMENT, DevOpsStatus.READY)
        
        # 初始化测试自动化
        if self.config.testing_config.get('enabled', True):
            self.components[ComponentType.TESTING] = TestAutomation(
                self.config.testing_config
            )
            await self._update_component_status(ComponentType.TESTING, DevOpsStatus.READY)
        
        # 初始化质量门禁
        if self.config.quality_gate_config.get('enabled', True):
            self.components[ComponentType.QUALITY_GATE] = QualityGate(
                self.config.quality_gate_config
            )
            await self._update_component_status(ComponentType.QUALITY_GATE, DevOpsStatus.READY)
    
    async def _start_background_tasks(self):
        """启动后台任务"""
        # 启动健康检查任务
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        
        # 启动指标收集任务
        if self.config.metrics_enabled:
            self._metrics_collection_task = asyncio.create_task(self._metrics_collection_loop())
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while True:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(self.config.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查错误: {e}")
                await asyncio.sleep(self.config.health_check_interval)
    
    async def _metrics_collection_loop(self):
        """指标收集循环"""
        while True:
            try:
                await self._collect_metrics()
                await asyncio.sleep(60)  # 每分钟收集一次指标
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"指标收集错误: {e}")
                await asyncio.sleep(60)
    
    async def _perform_health_checks(self):
        """执行健康检查"""
        for component_type, component in self.components.items():
            try:
                # 检查组件健康状态
                if hasattr(component, 'health_check'):
                    health_result = await component.health_check()
                    if health_result:
                        await self._update_component_status(component_type, DevOpsStatus.READY)
                    else:
                        await self._update_component_status(component_type, DevOpsStatus.DEGRADED)
                else:
                    # 默认健康检查
                    await self._update_component_status(component_type, DevOpsStatus.READY)
                    
            except Exception as e:
                logger.error(f"组件 {component_type.value} 健康检查失败: {e}")
                await self._update_component_status(
                    component_type, 
                    DevOpsStatus.ERROR, 
                    error_message=str(e)
                )
    
    async def _collect_metrics(self):
        """收集系统指标"""
        try:
            # 收集各组件指标
            for component_type, component in self.components.items():
                if hasattr(component, 'get_metrics'):
                    component_metrics = await component.get_metrics()
                    if component_type in self.component_status:
                        self.component_status[component_type].metrics = component_metrics
            
            # 更新聚合指标
            self._update_aggregate_metrics()
            
        except Exception as e:
            logger.error(f"指标收集失败: {e}")
    
    def _update_aggregate_metrics(self):
        """更新聚合指标"""
        # 从各组件收集指标并聚合
        total_pipelines = 0
        successful_pipelines = 0
        total_deployments = 0
        successful_deployments = 0
        
        for status in self.component_status.values():
            metrics = status.metrics
            
            # 聚合流水线指标
            total_pipelines += metrics.get('total_executions', 0)
            successful_pipelines += metrics.get('successful_executions', 0)
            
            # 聚合部署指标
            total_deployments += metrics.get('total_deployments', 0)
            successful_deployments += metrics.get('successful_deployments', 0)
        
        # 更新聚合指标
        self.metrics.total_pipelines = total_pipelines
        self.metrics.successful_pipelines = successful_pipelines
        self.metrics.failed_pipelines = total_pipelines - successful_pipelines
        
        self.metrics.total_deployments = total_deployments
        self.metrics.successful_deployments = successful_deployments
        self.metrics.failed_deployments = total_deployments - successful_deployments
        
        self.metrics.last_updated = datetime.now()
    
    async def _update_component_status(
        self, 
        component_type: ComponentType, 
        status: DevOpsStatus,
        error_message: Optional[str] = None
    ):
        """更新组件状态"""
        if component_type not in self.component_status:
            self.component_status[component_type] = ComponentStatus(
                component_type=component_type,
                status=status,
                last_update=datetime.now(),
                error_message=error_message
            )
        else:
            self.component_status[component_type].status = status
            self.component_status[component_type].last_update = datetime.now()
            self.component_status[component_type].error_message = error_message
    
    async def execute_pipeline(self, pipeline_config: Dict[str, Any]) -> Dict[str, Any]:
        """执行CI/CD流水线"""
        try:
            if ComponentType.CI_PIPELINE not in self.components:
                raise ValueError("CI/CD流水线组件未初始化")
            
            pipeline_manager = self.components[ComponentType.CI_PIPELINE]
            result = await pipeline_manager.execute_pipeline(pipeline_config)
            
            # 更新指标
            self.metrics.total_pipelines += 1
            if result.get('success', False):
                self.metrics.successful_pipelines += 1
            else:
                self.metrics.failed_pipelines += 1
            
            return result
            
        except Exception as e:
            logger.error(f"流水线执行失败: {e}")
            self.metrics.total_pipelines += 1
            self.metrics.failed_pipelines += 1
            return {'success': False, 'error': str(e)}
    
    async def build_docker_image(self, build_config: Dict[str, Any]) -> Dict[str, Any]:
        """构建Docker镜像"""
        try:
            if ComponentType.DOCKER_SYSTEM not in self.components:
                raise ValueError("Docker构建系统组件未初始化")
            
            docker_system = self.components[ComponentType.DOCKER_SYSTEM]
            result = await docker_system.build_image(build_config)
            
            return result
            
        except Exception as e:
            logger.error(f"Docker镜像构建失败: {e}")
            return {'success': False, 'error': str(e)}
    
    async def deploy_application(self, deployment_config: Dict[str, Any]) -> Dict[str, Any]:
        """部署应用"""
        try:
            if ComponentType.DEPLOYMENT not in self.components:
                raise ValueError("部署自动化组件未初始化")
            
            deployment_manager = self.components[ComponentType.DEPLOYMENT]
            result = await deployment_manager.deploy(deployment_config)
            
            # 更新指标
            self.metrics.total_deployments += 1
            if result.get('success', False):
                self.metrics.successful_deployments += 1
            else:
                self.metrics.failed_deployments += 1
            
            return result
            
        except Exception as e:
            logger.error(f"应用部署失败: {e}")
            self.metrics.total_deployments += 1
            self.metrics.failed_deployments += 1
            return {'success': False, 'error': str(e)}
    
    async def run_tests(self, test_config: Dict[str, Any]) -> Dict[str, Any]:
        """运行测试"""
        try:
            if ComponentType.TESTING not in self.components:
                raise ValueError("测试自动化组件未初始化")
            
            test_automation = self.components[ComponentType.TESTING]
            result = await test_automation.run_tests(test_config)
            
            # 更新指标
            test_results = result.get('test_results', {})
            total_tests = test_results.get('total', 0)
            passed_tests = test_results.get('passed', 0)
            
            self.metrics.total_tests += total_tests
            self.metrics.passed_tests += passed_tests
            self.metrics.failed_tests += (total_tests - passed_tests)
            
            return result
            
        except Exception as e:
            logger.error(f"测试运行失败: {e}")
            return {'success': False, 'error': str(e)}
    
    async def check_quality_gate(self, quality_config: Dict[str, Any]) -> Dict[str, Any]:
        """检查质量门禁"""
        try:
            if ComponentType.QUALITY_GATE not in self.components:
                raise ValueError("质量门禁组件未初始化")
            
            quality_gate = self.components[ComponentType.QUALITY_GATE]
            result = await quality_gate.check_quality(quality_config)
            
            return result
            
        except Exception as e:
            logger.error(f"质量门禁检查失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        return {
            'overall_status': self.status.value,
            'components': {
                component_type.value: {
                    'status': status.status.value,
                    'last_update': status.last_update.isoformat(),
                    'health_score': status.health_score,
                    'error_message': status.error_message
                }
                for component_type, status in self.component_status.items()
            },
            'metrics': {
                'total_pipelines': self.metrics.total_pipelines,
                'successful_pipelines': self.metrics.successful_pipelines,
                'failed_pipelines': self.metrics.failed_pipelines,
                'pipeline_success_rate': (
                    self.metrics.successful_pipelines / max(self.metrics.total_pipelines, 1)
                ),
                'total_deployments': self.metrics.total_deployments,
                'successful_deployments': self.metrics.successful_deployments,
                'failed_deployments': self.metrics.failed_deployments,
                'deployment_success_rate': (
                    self.metrics.successful_deployments / max(self.metrics.total_deployments, 1)
                ),
                'total_tests': self.metrics.total_tests,
                'passed_tests': self.metrics.passed_tests,
                'failed_tests': self.metrics.failed_tests,
                'test_pass_rate': (
                    self.metrics.passed_tests / max(self.metrics.total_tests, 1)
                ),
                'last_updated': self.metrics.last_updated.isoformat()
            }
        }
    
    def get_component_metrics(self, component_type: ComponentType) -> Dict[str, Any]:
        """获取组件指标"""
        if component_type in self.component_status:
            status = self.component_status[component_type]
            return {
                'status': status.status.value,
                'health_score': status.health_score,
                'last_update': status.last_update.isoformat(),
                'metrics': status.metrics
            }
        return {}
    
    async def shutdown(self):
        """关闭DevOps基础设施管理器"""
        try:
            logger.info("开始关闭DevOps基础设施管理器...")
            
            # 取消后台任务
            if self._health_check_task:
                self._health_check_task.cancel()
                try:
                    await self._health_check_task
                except asyncio.CancelledError:
                    pass
            
            if self._metrics_collection_task:
                self._metrics_collection_task.cancel()
                try:
                    await self._metrics_collection_task
                except asyncio.CancelledError:
                    pass
            
            # 关闭各组件
            for component in self.components.values():
                if hasattr(component, 'shutdown'):
                    await component.shutdown()
            
            self.status = DevOpsStatus.MAINTENANCE
            logger.info("DevOps基础设施管理器已关闭")
            
        except Exception as e:
            logger.error(f"DevOps基础设施管理器关闭失败: {e}")
            self.status = DevOpsStatus.ERROR