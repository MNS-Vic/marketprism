"""
CI/CD流水线管理器

提供完整的CI/CD流水线管理功能，包括流水线创建、执行、
状态管理、并行处理和智能重试机制。
"""

import asyncio
import logging
import uuid
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)

class PipelineStatus(Enum):
    """流水线状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"

class StageStatus(Enum):
    """流水线阶段状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRY = "retry"

class StageType(Enum):
    """流水线阶段类型枚举"""
    SOURCE = "source"
    BUILD = "build"
    TEST = "test"
    SECURITY = "security"
    PACKAGE = "package"
    DEPLOY = "deploy"
    VALIDATION = "validation"
    NOTIFICATION = "notification"

@dataclass
class StageConfig:
    """流水线阶段配置"""
    name: str
    stage_type: StageType
    enabled: bool = True
    timeout: int = 300  # 5分钟默认超时
    retry_count: int = 3
    retry_delay: int = 10  # 秒
    depends_on: List[str] = field(default_factory=list)
    parallel: bool = False
    environment: Dict[str, str] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)

@dataclass
class PipelineConfig:
    """流水线配置"""
    name: str
    version: str = "1.0.0"
    description: str = ""
    timeout: int = 1800  # 30分钟默认超时
    
    # 阶段配置
    stages: List[StageConfig] = field(default_factory=list)
    
    # 全局配置
    global_environment: Dict[str, str] = field(default_factory=dict)
    notification_config: Dict[str, Any] = field(default_factory=dict)
    
    # 触发器配置
    triggers: List[Dict[str, Any]] = field(default_factory=list)
    
    # 并发配置
    max_parallel_stages: int = 5
    allow_failure: bool = False

@dataclass
class StageResult:
    """阶段执行结果"""
    stage_name: str
    status: StageStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    duration: float = 0.0
    output: Optional[str] = None
    error_message: Optional[str] = None
    artifacts: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

@dataclass
class PipelineResult:
    """流水线执行结果"""
    pipeline_id: str
    status: PipelineStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    duration: float = 0.0
    
    # 阶段结果
    stage_results: Dict[str, StageResult] = field(default_factory=dict)
    
    # 总体指标
    total_stages: int = 0
    successful_stages: int = 0
    failed_stages: int = 0
    skipped_stages: int = 0
    
    # 错误信息
    error_message: Optional[str] = None
    
    # 产出物
    artifacts: List[str] = field(default_factory=list)

class CIPipelineManager:
    """
    CI/CD流水线管理器
    
    提供完整的CI/CD流水线管理功能，包括流水线创建、执行、
    状态管理、并行处理和智能重试机制。
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化CI/CD流水线管理器"""
        self.config = config or {}
        self.pipelines: Dict[str, PipelineResult] = {}
        self.running_pipelines: Dict[str, asyncio.Task] = {}
        
        # 阶段执行器映射
        self.stage_executors: Dict[StageType, Callable] = {}
        self._register_stage_executors()
        
        # 通知回调
        self.notification_callbacks: List[Callable] = []
        
        logger.info("CI/CD流水线管理器已初始化")
    
    def _register_stage_executors(self):
        """注册阶段执行器"""
        from .build_stage import BuildStage
        from .test_stage import TestStage
        from .deploy_stage import DeployStage
        from .validation_stage import ValidationStage
        
        self.stage_executors[StageType.SOURCE] = self._execute_source_stage
        self.stage_executors[StageType.BUILD] = BuildStage().execute
        self.stage_executors[StageType.TEST] = TestStage().execute
        self.stage_executors[StageType.SECURITY] = self._execute_security_stage
        self.stage_executors[StageType.PACKAGE] = self._execute_package_stage
        self.stage_executors[StageType.DEPLOY] = DeployStage().execute
        self.stage_executors[StageType.VALIDATION] = ValidationStage().execute
        self.stage_executors[StageType.NOTIFICATION] = self._execute_notification_stage
    
    async def create_pipeline(self, config: PipelineConfig) -> str:
        """创建流水线"""
        pipeline_id = str(uuid.uuid4())
        
        # 初始化流水线结果
        pipeline_result = PipelineResult(
            pipeline_id=pipeline_id,
            status=PipelineStatus.PENDING,
            start_time=datetime.now(),
            total_stages=len(config.stages)
        )
        
        self.pipelines[pipeline_id] = pipeline_result
        
        logger.info(f"流水线已创建: {pipeline_id}")
        return pipeline_id
    
    async def execute_pipeline(self, config: PipelineConfig) -> PipelineResult:
        """执行流水线"""
        pipeline_id = await self.create_pipeline(config)
        
        try:
            # 创建执行任务
            execution_task = asyncio.create_task(
                self._execute_pipeline_internal(pipeline_id, config)
            )
            self.running_pipelines[pipeline_id] = execution_task
            
            # 等待执行完成
            result = await execution_task
            
            return result
            
        except Exception as e:
            logger.error(f"流水线执行失败: {e}")
            pipeline_result = self.pipelines[pipeline_id]
            pipeline_result.status = PipelineStatus.FAILED
            pipeline_result.error_message = str(e)
            pipeline_result.end_time = datetime.now()
            pipeline_result.duration = (
                pipeline_result.end_time - pipeline_result.start_time
            ).total_seconds()
            
            return pipeline_result
        
        finally:
            # 清理运行中的流水线
            if pipeline_id in self.running_pipelines:
                del self.running_pipelines[pipeline_id]
    
    async def _execute_pipeline_internal(
        self, 
        pipeline_id: str, 
        config: PipelineConfig
    ) -> PipelineResult:
        """内部流水线执行逻辑"""
        pipeline_result = self.pipelines[pipeline_id]
        pipeline_result.status = PipelineStatus.RUNNING
        
        try:
            # 构建阶段依赖图
            stage_graph = self._build_stage_dependency_graph(config.stages)
            
            # 按依赖关系执行阶段
            await self._execute_stages_by_dependency(
                pipeline_id, config, stage_graph
            )
            
            # 计算最终状态
            self._calculate_final_status(pipeline_result)
            
        except asyncio.TimeoutError:
            pipeline_result.status = PipelineStatus.TIMEOUT
            pipeline_result.error_message = "流水线执行超时"
        except Exception as e:
            pipeline_result.status = PipelineStatus.FAILED
            pipeline_result.error_message = str(e)
        
        # 更新结束时间和持续时间
        pipeline_result.end_time = datetime.now()
        pipeline_result.duration = (
            pipeline_result.end_time - pipeline_result.start_time
        ).total_seconds()
        
        # 发送通知
        await self._send_pipeline_notification(pipeline_result, config)
        
        return pipeline_result
    
    def _build_stage_dependency_graph(
        self, 
        stages: List[StageConfig]
    ) -> Dict[str, List[str]]:
        """构建阶段依赖图"""
        graph = {}
        for stage in stages:
            graph[stage.name] = stage.depends_on.copy()
        return graph
    
    async def _execute_stages_by_dependency(
        self,
        pipeline_id: str,
        config: PipelineConfig,
        stage_graph: Dict[str, List[str]]
    ):
        """按依赖关系执行阶段"""
        executed_stages = set()
        stage_configs = {stage.name: stage for stage in config.stages}
        
        while len(executed_stages) < len(config.stages):
            # 找到可以执行的阶段（依赖已满足）
            ready_stages = []
            for stage_name, dependencies in stage_graph.items():
                if (stage_name not in executed_stages and 
                    all(dep in executed_stages for dep in dependencies)):
                    ready_stages.append(stage_name)
            
            if not ready_stages:
                # 检查是否有循环依赖
                remaining_stages = set(stage_graph.keys()) - executed_stages
                if remaining_stages:
                    raise ValueError(f"检测到循环依赖: {remaining_stages}")
                break
            
            # 分批执行阶段（考虑并行限制）
            parallel_stages = []
            sequential_stages = []
            
            for stage_name in ready_stages:
                stage_config = stage_configs[stage_name]
                if stage_config.parallel and len(parallel_stages) < config.max_parallel_stages:
                    parallel_stages.append(stage_name)
                else:
                    sequential_stages.append(stage_name)
            
            # 执行并行阶段
            if parallel_stages:
                tasks = []
                for stage_name in parallel_stages:
                    task = asyncio.create_task(
                        self._execute_stage(pipeline_id, stage_configs[stage_name], config)
                    )
                    tasks.append(task)
                
                # 等待所有并行阶段完成
                await asyncio.gather(*tasks, return_exceptions=True)
                executed_stages.update(parallel_stages)
            
            # 执行顺序阶段
            for stage_name in sequential_stages:
                await self._execute_stage(pipeline_id, stage_configs[stage_name], config)
                executed_stages.add(stage_name)
    
    async def _execute_stage(
        self, 
        pipeline_id: str, 
        stage_config: StageConfig,
        pipeline_config: PipelineConfig
    ) -> StageResult:
        """执行单个阶段"""
        stage_result = StageResult(
            stage_name=stage_config.name,
            status=StageStatus.PENDING,
            start_time=datetime.now()
        )
        
        # 添加到流水线结果
        pipeline_result = self.pipelines[pipeline_id]
        pipeline_result.stage_results[stage_config.name] = stage_result
        
        if not stage_config.enabled:
            stage_result.status = StageStatus.SKIPPED
            stage_result.end_time = datetime.now()
            return stage_result
        
        stage_result.status = StageStatus.RUNNING
        
        retry_count = 0
        while retry_count <= stage_config.retry_count:
            try:
                # 执行阶段
                if stage_config.stage_type in self.stage_executors:
                    executor = self.stage_executors[stage_config.stage_type]
                    
                    # 执行超时控制
                    result = await asyncio.wait_for(
                        executor(stage_config, pipeline_config),
                        timeout=stage_config.timeout
                    )
                    
                    # 更新阶段结果
                    if isinstance(result, dict):
                        stage_result.output = result.get('output')
                        stage_result.artifacts.extend(result.get('artifacts', []))
                        stage_result.metrics.update(result.get('metrics', {}))
                        
                        if result.get('success', True):
                            stage_result.status = StageStatus.SUCCESS
                        else:
                            raise Exception(result.get('error', '阶段执行失败'))
                    else:
                        stage_result.status = StageStatus.SUCCESS
                
                break  # 成功执行，退出重试循环
                
            except asyncio.TimeoutError:
                stage_result.error_message = f"阶段执行超时（{stage_config.timeout}秒）"
                if retry_count < stage_config.retry_count:
                    retry_count += 1
                    stage_result.status = StageStatus.RETRY
                    await asyncio.sleep(stage_config.retry_delay)
                else:
                    stage_result.status = StageStatus.FAILED
                    break
                    
            except Exception as e:
                stage_result.error_message = str(e)
                if retry_count < stage_config.retry_count:
                    retry_count += 1
                    stage_result.status = StageStatus.RETRY
                    await asyncio.sleep(stage_config.retry_delay)
                else:
                    stage_result.status = StageStatus.FAILED
                    break
        
        # 更新结束时间和持续时间
        stage_result.end_time = datetime.now()
        stage_result.duration = (
            stage_result.end_time - stage_result.start_time
        ).total_seconds()
        
        logger.info(
            f"阶段 {stage_config.name} 执行完成: {stage_result.status.value}"
        )
        
        return stage_result
    
    def _calculate_final_status(self, pipeline_result: PipelineResult):
        """计算流水线最终状态"""
        successful_count = 0
        failed_count = 0
        skipped_count = 0
        
        for stage_result in pipeline_result.stage_results.values():
            if stage_result.status == StageStatus.SUCCESS:
                successful_count += 1
            elif stage_result.status == StageStatus.FAILED:
                failed_count += 1
            elif stage_result.status == StageStatus.SKIPPED:
                skipped_count += 1
        
        pipeline_result.successful_stages = successful_count
        pipeline_result.failed_stages = failed_count
        pipeline_result.skipped_stages = skipped_count
        
        # 确定最终状态
        if failed_count > 0:
            pipeline_result.status = PipelineStatus.FAILED
        elif successful_count > 0 or skipped_count == pipeline_result.total_stages:
            pipeline_result.status = PipelineStatus.SUCCESS
        else:
            pipeline_result.status = PipelineStatus.FAILED
    
    async def _send_pipeline_notification(
        self, 
        pipeline_result: PipelineResult,
        config: PipelineConfig
    ):
        """发送流水线通知"""
        try:
            notification_data = {
                'pipeline_id': pipeline_result.pipeline_id,
                'pipeline_name': config.name,
                'status': pipeline_result.status.value,
                'duration': pipeline_result.duration,
                'successful_stages': pipeline_result.successful_stages,
                'failed_stages': pipeline_result.failed_stages
            }
            
            # 调用通知回调
            for callback in self.notification_callbacks:
                try:
                    await callback(notification_data)
                except Exception as e:
                    logger.error(f"通知回调失败: {e}")
                    
        except Exception as e:
            logger.error(f"发送流水线通知失败: {e}")
    
    # 默认阶段执行器实现
    async def _execute_source_stage(
        self, 
        stage_config: StageConfig,
        pipeline_config: PipelineConfig
    ) -> Dict[str, Any]:
        """执行源码阶段"""
        # 模拟源码拉取
        await asyncio.sleep(1)
        return {
            'success': True,
            'output': 'Source code checked out successfully',
            'artifacts': ['source.tar.gz']
        }
    
    async def _execute_security_stage(
        self, 
        stage_config: StageConfig,
        pipeline_config: PipelineConfig
    ) -> Dict[str, Any]:
        """执行安全扫描阶段"""
        # 模拟安全扫描
        await asyncio.sleep(2)
        return {
            'success': True,
            'output': 'Security scan completed with no issues',
            'metrics': {'vulnerabilities': 0, 'scan_duration': 2.0}
        }
    
    async def _execute_package_stage(
        self, 
        stage_config: StageConfig,
        pipeline_config: PipelineConfig
    ) -> Dict[str, Any]:
        """执行打包阶段"""
        # 模拟应用打包
        await asyncio.sleep(1)
        return {
            'success': True,
            'output': 'Application packaged successfully',
            'artifacts': ['app-v1.0.0.tar.gz', 'docker-image:v1.0.0']
        }
    
    async def _execute_notification_stage(
        self, 
        stage_config: StageConfig,
        pipeline_config: PipelineConfig
    ) -> Dict[str, Any]:
        """执行通知阶段"""
        # 模拟发送通知
        await asyncio.sleep(0.5)
        return {
            'success': True,
            'output': 'Notifications sent successfully'
        }
    
    # 流水线管理方法
    def get_pipeline_status(self, pipeline_id: str) -> Optional[PipelineStatus]:
        """获取流水线状态"""
        if pipeline_id in self.pipelines:
            return self.pipelines[pipeline_id].status
        return None
    
    def get_pipeline_result(self, pipeline_id: str) -> Optional[PipelineResult]:
        """获取流水线结果"""
        return self.pipelines.get(pipeline_id)
    
    async def abort_pipeline(self, pipeline_id: str) -> bool:
        """中止流水线"""
        if pipeline_id in self.running_pipelines:
            task = self.running_pipelines[pipeline_id]
            task.cancel()
            
            if pipeline_id in self.pipelines:
                self.pipelines[pipeline_id].status = PipelineStatus.CANCELLED
                self.pipelines[pipeline_id].end_time = datetime.now()
            
            return True
        return False
    
    def add_notification_callback(self, callback: Callable):
        """添加通知回调"""
        self.notification_callbacks.append(callback)
    
    async def get_metrics(self) -> Dict[str, Any]:
        """获取流水线指标"""
        total_pipelines = len(self.pipelines)
        successful_pipelines = sum(
            1 for p in self.pipelines.values() 
            if p.status == PipelineStatus.SUCCESS
        )
        failed_pipelines = sum(
            1 for p in self.pipelines.values() 
            if p.status == PipelineStatus.FAILED
        )
        running_pipelines = len(self.running_pipelines)
        
        avg_duration = 0.0
        if total_pipelines > 0:
            completed_pipelines = [
                p for p in self.pipelines.values() 
                if p.status in [PipelineStatus.SUCCESS, PipelineStatus.FAILED]
            ]
            if completed_pipelines:
                avg_duration = sum(p.duration for p in completed_pipelines) / len(completed_pipelines)
        
        return {
            'total_executions': total_pipelines,
            'successful_executions': successful_pipelines,
            'failed_executions': failed_pipelines,
            'running_executions': running_pipelines,
            'success_rate': successful_pipelines / max(total_pipelines, 1),
            'average_duration': avg_duration
        }
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # 检查是否有太多失败的流水线
            recent_pipelines = [
                p for p in self.pipelines.values()
                if p.start_time > datetime.now() - timedelta(hours=1)
            ]
            
            if recent_pipelines:
                failure_rate = sum(
                    1 for p in recent_pipelines 
                    if p.status == PipelineStatus.FAILED
                ) / len(recent_pipelines)
                
                return failure_rate < 0.5  # 失败率小于50%认为健康
            
            return True
            
        except Exception as e:
            logger.error(f"CI/CD流水线健康检查失败: {e}")
            return False
    
    async def shutdown(self):
        """关闭流水线管理器"""
        try:
            # 取消所有运行中的流水线
            for pipeline_id, task in self.running_pipelines.items():
                task.cancel()
                if pipeline_id in self.pipelines:
                    self.pipelines[pipeline_id].status = PipelineStatus.CANCELLED
            
            # 等待所有任务完成
            if self.running_pipelines:
                await asyncio.gather(
                    *self.running_pipelines.values(), 
                    return_exceptions=True
                )
            
            self.running_pipelines.clear()
            logger.info("CI/CD流水线管理器已关闭")
            
        except Exception as e:
            logger.error(f"CI/CD流水线管理器关闭失败: {e}")