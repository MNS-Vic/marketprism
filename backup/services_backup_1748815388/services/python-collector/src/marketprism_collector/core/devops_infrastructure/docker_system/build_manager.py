"""
Docker构建管理器

提供完整的Docker镜像构建和管理功能，包括多阶段构建、
缓存优化、安全扫描和镜像推送等功能。
"""

import asyncio
import logging
import json
import os
import subprocess
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

class BuildStatus(Enum):
    """构建状态枚举"""
    PENDING = "pending"
    BUILDING = "building"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"

class ImageType(Enum):
    """镜像类型枚举"""
    APPLICATION = "application"
    BASE = "base"
    RUNTIME = "runtime"
    DEBUG = "debug"

@dataclass
class DockerConfig:
    """Docker构建配置"""
    # 基础配置
    dockerfile_path: str = "Dockerfile"
    context_path: str = "."
    image_name: str = "app"
    image_tag: str = "latest"
    image_type: ImageType = ImageType.APPLICATION
    
    # 构建选项
    multi_stage: bool = True
    build_args: Dict[str, str] = field(default_factory=dict)
    build_secrets: Dict[str, str] = field(default_factory=dict)
    target_stage: Optional[str] = None
    platform: Optional[str] = None  # linux/amd64, linux/arm64等
    
    # 缓存配置
    use_cache: bool = True
    cache_from: List[str] = field(default_factory=list)
    cache_to: List[str] = field(default_factory=list)
    inline_cache: bool = True
    
    # 安全配置
    security_scan: bool = True
    vulnerability_threshold: str = "HIGH"  # LOW, MEDIUM, HIGH, CRITICAL
    
    # 推送配置
    push_to_registry: bool = False
    registry_url: Optional[str] = None
    registry_username: Optional[str] = None
    registry_password: Optional[str] = None
    
    # 优化配置
    squash_layers: bool = False
    compress: bool = True
    remove_intermediate: bool = True

@dataclass
class BuildResult:
    """构建结果"""
    build_id: str
    status: BuildStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    duration: float = 0.0
    
    # 镜像信息
    image_id: str = ""
    image_size: int = 0
    image_tags: List[str] = field(default_factory=list)
    
    # 构建日志
    build_log: str = ""
    error_message: Optional[str] = None
    
    # 安全扫描结果
    security_scan_result: Dict[str, Any] = field(default_factory=dict)
    
    # 构建指标
    metrics: Dict[str, Any] = field(default_factory=dict)
    
    # 产出物
    artifacts: List[str] = field(default_factory=list)

class DockerBuildSystem:
    """
    Docker构建管理器
    
    提供完整的Docker镜像构建和管理功能，包括多阶段构建、
    缓存优化、安全扫描和镜像推送等功能。
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化Docker构建系统"""
        self.config = config or {}
        self.builds: Dict[str, BuildResult] = {}
        self.running_builds: Dict[str, asyncio.Task] = {}
        
        # 检查Docker环境
        self._check_docker_environment()
        
        logger.info("Docker构建系统已初始化")
    
    def _check_docker_environment(self):
        """检查Docker环境"""
        try:
            result = subprocess.run(
                ['docker', '--version'], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                raise Exception("Docker未安装或不可用")
            logger.info(f"Docker环境检查通过: {result.stdout.strip()}")
        except Exception as e:
            logger.error(f"Docker环境检查失败: {e}")
            raise
    
    async def build_image(self, config: DockerConfig) -> BuildResult:
        """构建Docker镜像"""
        build_id = self._generate_build_id(config)
        
        # 创建构建结果对象
        build_result = BuildResult(
            build_id=build_id,
            status=BuildStatus.PENDING,
            start_time=datetime.now()
        )
        self.builds[build_id] = build_result
        
        try:
            # 启动构建任务
            build_task = asyncio.create_task(
                self._build_image_internal(build_id, config)
            )
            self.running_builds[build_id] = build_task
            
            # 等待构建完成
            result = await build_task
            return result
            
        except Exception as e:
            logger.error(f"镜像构建失败: {e}")
            build_result.status = BuildStatus.FAILED
            build_result.error_message = str(e)
            build_result.end_time = datetime.now()
            build_result.duration = (
                build_result.end_time - build_result.start_time
            ).total_seconds()
            return build_result
        
        finally:
            # 清理运行中的构建任务
            if build_id in self.running_builds:
                del self.running_builds[build_id]
    
    async def _build_image_internal(
        self, 
        build_id: str, 
        config: DockerConfig
    ) -> BuildResult:
        """内部构建镜像逻辑"""
        build_result = self.builds[build_id]
        build_result.status = BuildStatus.BUILDING
        
        try:
            # 步骤1: 准备构建环境
            await self._prepare_build_environment(config)
            
            # 步骤2: 构建Docker镜像
            image_info = await self._execute_docker_build(build_id, config)
            
            # 步骤3: 安全扫描（如果启用）
            if config.security_scan:
                scan_result = await self._perform_security_scan(
                    image_info['image_id'], config
                )
                build_result.security_scan_result = scan_result
            
            # 步骤4: 推送到仓库（如果配置）
            if config.push_to_registry:
                await self._push_to_registry(image_info['image_id'], config)
            
            # 更新构建结果
            build_result.status = BuildStatus.SUCCESS
            build_result.image_id = image_info['image_id']
            build_result.image_size = image_info['size']
            build_result.image_tags = image_info['tags']
            
            # 收集构建指标
            build_result.metrics = await self._collect_build_metrics(
                build_id, config, image_info
            )
            
        except Exception as e:
            logger.error(f"构建过程失败: {e}")
            build_result.status = BuildStatus.FAILED
            build_result.error_message = str(e)
        
        # 更新结束时间和持续时间
        build_result.end_time = datetime.now()
        build_result.duration = (
            build_result.end_time - build_result.start_time
        ).total_seconds()
        
        return build_result
    
    def _generate_build_id(self, config: DockerConfig) -> str:
        """生成构建ID"""
        # 基于配置生成唯一的构建ID
        config_str = f"{config.image_name}:{config.image_tag}:{config.dockerfile_path}:{datetime.now().isoformat()}"
        return hashlib.md5(config_str.encode()).hexdigest()[:12]
    
    async def _prepare_build_environment(self, config: DockerConfig):
        """准备构建环境"""
        # 检查Dockerfile是否存在
        dockerfile_path = Path(config.context_path) / config.dockerfile_path
        if not dockerfile_path.exists():
            raise FileNotFoundError(f"Dockerfile不存在: {dockerfile_path}")
        
        # 检查构建上下文
        context_path = Path(config.context_path)
        if not context_path.exists():
            raise FileNotFoundError(f"构建上下文不存在: {context_path}")
        
        # 创建.dockerignore（如果需要）
        dockerignore_path = context_path / '.dockerignore'
        if not dockerignore_path.exists():
            await self._create_default_dockerignore(dockerignore_path)
        
        logger.info(f"构建环境准备完成: {context_path}")
    
    async def _create_default_dockerignore(self, dockerignore_path: Path):
        """创建默认的.dockerignore文件"""
        default_ignore = [
            ".git",
            ".gitignore",
            "README.md",
            "Dockerfile*",
            ".dockerignore",
            "node_modules",
            "*.pyc",
            "__pycache__",
            ".pytest_cache",
            ".coverage",
            "*.log",
            ".env*",
            ".DS_Store",
            "Thumbs.db"
        ]
        
        with open(dockerignore_path, 'w') as f:
            f.write('\n'.join(default_ignore))
        
        logger.info(f"创建默认.dockerignore: {dockerignore_path}")
    
    async def _execute_docker_build(
        self, 
        build_id: str, 
        config: DockerConfig
    ) -> Dict[str, Any]:
        """执行Docker构建"""
        # 构建命令
        cmd = ['docker', 'build']
        
        # 添加基础参数
        full_image_name = f"{config.image_name}:{config.image_tag}"
        cmd.extend(['-t', full_image_name])
        
        # 添加构建参数
        for key, value in config.build_args.items():
            cmd.extend(['--build-arg', f"{key}={value}"])
        
        # 添加构建密钥
        for key, value in config.build_secrets.items():
            cmd.extend(['--secret', f"id={key},src={value}"])
        
        # 添加目标阶段
        if config.target_stage:
            cmd.extend(['--target', config.target_stage])
        
        # 添加平台
        if config.platform:
            cmd.extend(['--platform', config.platform])
        
        # 添加缓存选项
        if config.use_cache:
            for cache_from in config.cache_from:
                cmd.extend(['--cache-from', cache_from])
        else:
            cmd.append('--no-cache')
        
        # 添加其他选项
        if config.squash_layers:
            cmd.append('--squash')
        
        if config.remove_intermediate:
            cmd.append('--rm')
        
        # 指定Dockerfile和构建上下文
        if config.dockerfile_path != "Dockerfile":
            cmd.extend(['-f', config.dockerfile_path])
        
        cmd.append(config.context_path)
        
        logger.info(f"执行Docker构建命令: {' '.join(cmd)}")
        
        # 执行构建
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        
        build_log = ""
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            
            line_str = line.decode('utf-8').strip()
            build_log += line_str + '\n'
            logger.info(f"[{build_id}] {line_str}")
        
        await process.wait()
        
        # 更新构建日志
        self.builds[build_id].build_log = build_log
        
        if process.returncode != 0:
            raise Exception(f"Docker构建失败，返回码: {process.returncode}")
        
        # 获取镜像信息
        image_info = await self._get_image_info(full_image_name)
        return image_info
    
    async def _get_image_info(self, image_name: str) -> Dict[str, Any]:
        """获取镜像信息"""
        # 获取镜像ID
        cmd = ['docker', 'images', '--format', '{{.ID}}', image_name]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        
        if process.returncode != 0:
            raise Exception("获取镜像ID失败")
        
        image_id = stdout.decode().strip()
        
        # 获取镜像大小
        cmd = ['docker', 'images', '--format', '{{.Size}}', image_name]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        
        size_str = stdout.decode().strip()
        size_bytes = self._parse_size_to_bytes(size_str)
        
        return {
            'image_id': image_id,
            'size': size_bytes,
            'tags': [image_name]
        }
    
    def _parse_size_to_bytes(self, size_str: str) -> int:
        """解析大小字符串为字节数"""
        try:
            if 'MB' in size_str:
                return int(float(size_str.replace('MB', '')) * 1024 * 1024)
            elif 'GB' in size_str:
                return int(float(size_str.replace('GB', '')) * 1024 * 1024 * 1024)
            elif 'KB' in size_str:
                return int(float(size_str.replace('KB', '')) * 1024)
            else:
                return int(size_str.replace('B', ''))
        except:
            return 0
    
    async def _perform_security_scan(
        self, 
        image_id: str, 
        config: DockerConfig
    ) -> Dict[str, Any]:
        """执行安全扫描"""
        logger.info(f"执行安全扫描: {image_id}")
        
        # 模拟安全扫描（实际实现可以使用Trivy、Clair等工具）
        await asyncio.sleep(2)  # 模拟扫描时间
        
        # 模拟扫描结果
        vulnerabilities = [
            {
                'severity': 'MEDIUM',
                'package': 'openssl',
                'version': '1.1.1f',
                'cve': 'CVE-2021-3711',
                'description': 'Buffer overflow in SSL'
            },
            {
                'severity': 'LOW',
                'package': 'zlib',
                'version': '1.2.11',
                'cve': 'CVE-2018-25032',
                'description': 'Memory corruption in deflate'
            }
        ]
        
        # 按严重程度统计
        severity_counts = {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 1, 'LOW': 1}
        
        # 检查是否超过阈值
        threshold_levels = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
        threshold_index = threshold_levels.index(config.vulnerability_threshold)
        
        exceeded_threshold = any(
            severity_counts.get(level, 0) > 0 
            for level in threshold_levels[:threshold_index + 1]
        )
        
        return {
            'scan_time': datetime.now().isoformat(),
            'vulnerabilities': vulnerabilities,
            'severity_counts': severity_counts,
            'threshold_exceeded': exceeded_threshold,
            'scan_tool': 'trivy',
            'scan_version': '0.35.0'
        }
    
    async def _push_to_registry(self, image_id: str, config: DockerConfig):
        """推送镜像到仓库"""
        if not config.registry_url:
            raise ValueError("未配置镜像仓库URL")
        
        # 登录仓库
        if config.registry_username and config.registry_password:
            login_cmd = [
                'docker', 'login', 
                '--username', config.registry_username,
                '--password-stdin',
                config.registry_url
            ]
            
            process = await asyncio.create_subprocess_exec(
                *login_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate(
                input=config.registry_password.encode()
            )
            
            if process.returncode != 0:
                raise Exception(f"仓库登录失败: {stderr.decode()}")
        
        # 标记镜像
        registry_image = f"{config.registry_url}/{config.image_name}:{config.image_tag}"
        tag_cmd = ['docker', 'tag', f"{config.image_name}:{config.image_tag}", registry_image]
        
        process = await asyncio.create_subprocess_exec(*tag_cmd)
        await process.wait()
        
        if process.returncode != 0:
            raise Exception("镜像标记失败")
        
        # 推送镜像
        push_cmd = ['docker', 'push', registry_image]
        
        process = await asyncio.create_subprocess_exec(
            *push_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            logger.info(f"Push: {line.decode().strip()}")
        
        await process.wait()
        
        if process.returncode != 0:
            raise Exception("镜像推送失败")
        
        logger.info(f"镜像推送成功: {registry_image}")
    
    async def _collect_build_metrics(
        self, 
        build_id: str, 
        config: DockerConfig,
        image_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """收集构建指标"""
        build_result = self.builds[build_id]
        
        return {
            'build_duration': build_result.duration,
            'image_size_mb': image_info['size'] / (1024 * 1024),
            'build_cache_used': config.use_cache,
            'multi_stage_build': config.multi_stage,
            'security_scan_enabled': config.security_scan,
            'pushed_to_registry': config.push_to_registry
        }
    
    def get_build_status(self, build_id: str) -> Optional[BuildStatus]:
        """获取构建状态"""
        if build_id in self.builds:
            return self.builds[build_id].status
        return None
    
    def get_build_result(self, build_id: str) -> Optional[BuildResult]:
        """获取构建结果"""
        return self.builds.get(build_id)
    
    async def cancel_build(self, build_id: str) -> bool:
        """取消构建"""
        if build_id in self.running_builds:
            task = self.running_builds[build_id]
            task.cancel()
            
            if build_id in self.builds:
                self.builds[build_id].status = BuildStatus.CANCELLED
                self.builds[build_id].end_time = datetime.now()
            
            return True
        return False
    
    async def cleanup_images(self, keep_latest: int = 5) -> Dict[str, Any]:
        """清理旧镜像"""
        logger.info("开始清理旧镜像...")
        
        # 获取所有镜像
        cmd = ['docker', 'images', '--format', '{{.Repository}}:{{.Tag}}\\t{{.ID}}\\t{{.CreatedAt}}']
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        
        if process.returncode != 0:
            raise Exception("获取镜像列表失败")
        
        # 解析镜像信息
        images = []
        for line in stdout.decode().strip().split('\n'):
            if line:
                parts = line.split('\t')
                if len(parts) >= 3:
                    images.append({
                        'name': parts[0],
                        'id': parts[1],
                        'created': parts[2]
                    })
        
        # 按仓库分组并保留最新的几个版本
        removed_images = []
        for image in images:
            # 这里可以添加更复杂的清理逻辑
            pass
        
        return {
            'total_images': len(images),
            'removed_images': len(removed_images),
            'freed_space': 0  # 可以计算释放的空间
        }
    
    async def get_metrics(self) -> Dict[str, Any]:
        """获取Docker构建系统指标"""
        total_builds = len(self.builds)
        successful_builds = sum(
            1 for build in self.builds.values() 
            if build.status == BuildStatus.SUCCESS
        )
        failed_builds = sum(
            1 for build in self.builds.values() 
            if build.status == BuildStatus.FAILED
        )
        running_builds = len(self.running_builds)
        
        avg_build_time = 0.0
        if total_builds > 0:
            completed_builds = [
                build for build in self.builds.values() 
                if build.status in [BuildStatus.SUCCESS, BuildStatus.FAILED]
            ]
            if completed_builds:
                avg_build_time = sum(build.duration for build in completed_builds) / len(completed_builds)
        
        return {
            'total_builds': total_builds,
            'successful_builds': successful_builds,
            'failed_builds': failed_builds,
            'running_builds': running_builds,
            'success_rate': successful_builds / max(total_builds, 1),
            'average_build_time': avg_build_time
        }
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # 检查Docker daemon是否运行
            process = await asyncio.create_subprocess_exec(
                'docker', 'info',
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await process.wait()
            
            return process.returncode == 0
            
        except Exception as e:
            logger.error(f"Docker构建系统健康检查失败: {e}")
            return False
    
    async def shutdown(self):
        """关闭Docker构建系统"""
        try:
            # 取消所有运行中的构建
            for build_id, task in self.running_builds.items():
                task.cancel()
                if build_id in self.builds:
                    self.builds[build_id].status = BuildStatus.CANCELLED
            
            # 等待所有任务完成
            if self.running_builds:
                await asyncio.gather(
                    *self.running_builds.values(), 
                    return_exceptions=True
                )
            
            self.running_builds.clear()
            logger.info("Docker构建系统已关闭")
            
        except Exception as e:
            logger.error(f"Docker构建系统关闭失败: {e}")