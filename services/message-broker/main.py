"""
Message Broker Service - Phase 3
消息代理服务，负责NATS集群管理和消息路由

这是MarketPrism微服务架构的消息中枢，提供：
1. NATS Server集群管理
2. JetStream持久化消息流
3. 消息路由和分发
4. 消息持久化存储
5. 消息订阅管理
6. 集群健康监控
7. 消息统计和分析
"""

import asyncio
import sys
import json
import subprocess
import signal
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
import structlog
from datetime import datetime, timedelta, timezone
import aiohttp
from aiohttp import web
import tempfile
import yaml
import logging
import nats
from nats.aio.client import Client as NATSClient
from nats.aio.errors import ErrConnectionClosed, ErrTimeout, ErrNoServers
import traceback

# 尝试导入NATS客户端
try:
    import nats
    from nats.js import JetStreamContext
    NATS_AVAILABLE = True
except ImportError:
    print("警告: NATS客户端库未安装，某些功能可能不可用")
    NATS_AVAILABLE = False

# 添加项目路径 - 在Docker容器中调整路径
try:
    # 在Docker容器中，当前目录就是/app
    project_root = Path(__file__).resolve().parent
    sys.path.insert(0, str(project_root))
    sys.path.insert(0, '/app')
except Exception as e:
    print(f"路径配置警告: {e}")
    sys.path.insert(0, '/app')

# 导入微服务框架
from core.service_framework import BaseService


class NATSServerManager:
    """NATS服务器管理器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = structlog.get_logger(__name__)
        self.server_process = None
        self.server_config_file = None
        
        # NATS配置
        self.nats_port = config.get('nats_port', 4222)
        self.cluster_port = config.get('cluster_port', 6222) 
        self.http_port = config.get('http_port', 8222)
        self.jetstream_enabled = config.get('jetstream_enabled', True)
        self.jetstream_max_memory = config.get('jetstream_max_memory', '1GB')
        self.jetstream_max_storage = config.get('jetstream_max_storage', '10GB')
        
        # 数据目录
        self.data_dir = Path(config.get('data_dir', 'data/nats'))
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def _create_nats_config(self) -> str:
        """创建NATS服务器配置文件"""
        config_content = f"""
# NATS Server Configuration for MarketPrism
server_name: "marketprism-nats"
port: {self.nats_port}
http_port: {self.http_port}

# 集群配置
cluster {{
  name: "marketprism-cluster"
  listen: "0.0.0.0:{self.cluster_port}"
  # routes = [
  #   "nats-route://localhost:6222"
  # ]
}}

# JetStream配置
jetstream {{
  store_dir: "{self.data_dir}/jetstream"
  max_memory_store: {self.jetstream_max_memory}
  max_file_store: {self.jetstream_max_storage}
}}

# 日志配置
log_file: "{self.data_dir}/nats-server.log"
logtime: true
debug: false
trace: false

# 监控配置
accounts {{
  $SYS {{
    users: [
      {{user: "admin", password: "marketprism_admin"}}
    ]
  }}
}}

# 默认账户配置
no_auth_user: "marketprism"
users: [
  {{
    user: "marketprism"
    password: "marketprism_pass"
    permissions: {{
      publish: ["market.>", "system.>", "service.>"]
      subscribe: ["market.>", "system.>", "service.>"]
    }}
  }}
]

# 连接限制
max_connections: 1000
max_subscriptions: 1000
max_payload: 1MB

# 性能优化
write_deadline: "2s"
"""
        
        # 创建临时配置文件
        fd, config_file_path = tempfile.mkstemp(suffix='.conf', text=True)
        with os.fdopen(fd, 'w') as f:
            f.write(config_content)
        
        self.server_config_file = config_file_path
        return config_file_path
    
    async def start_nats_server(self) -> bool:
        """启动NATS服务器"""
        try:
            if self.server_process and self.server_process.poll() is None:
                self.logger.info("NATS服务器已在运行")
                return True
            
            # 检查nats-server是否可用
            try:
                result = subprocess.run(['nats-server', '--version'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode != 0:
                    self.logger.error("nats-server命令不可用，请安装NATS Server")
                    return False
            except (subprocess.TimeoutExpired, FileNotFoundError):
                self.logger.error("nats-server未安装或不在PATH中")
                return False
            
            # 创建配置文件
            config_file = self._create_nats_config()
            
            # 启动NATS服务器
            self.logger.info(f"启动NATS服务器，端口: {self.nats_port}")
            self.server_process = subprocess.Popen([
                'nats-server',
                '--config', config_file,
                '--jetstream'
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # 等待服务器启动
            await asyncio.sleep(2)
            
            # 检查进程是否仍在运行
            if self.server_process.poll() is None:
                self.logger.info("NATS服务器启动成功")
                return True
            else:
                stdout, stderr = self.server_process.communicate()
                self.logger.error(f"NATS服务器启动失败: {stderr.decode()}")
                return False
                
        except Exception as e:
            self.logger.error(f"启动NATS服务器失败: {e}")
            return False
    
    async def stop_nats_server(self):
        """停止NATS服务器"""
        try:
            if self.server_process and self.server_process.poll() is None:
                self.logger.info("停止NATS服务器")
                self.server_process.terminate()
                
                # 等待进程结束
                try:
                    self.server_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.logger.warning("NATS服务器未响应SIGTERM，强制终止")
                    self.server_process.kill()
                    self.server_process.wait()
                
                self.server_process = None
            
            # 清理配置文件
            if self.server_config_file and os.path.exists(self.server_config_file):
                os.unlink(self.server_config_file)
                self.server_config_file = None
                
        except Exception as e:
            self.logger.error(f"停止NATS服务器失败: {e}")
    
    def is_running(self) -> bool:
        """检查NATS服务器是否运行"""
        return self.server_process and self.server_process.poll() is None
    
    async def get_server_info(self) -> Dict[str, Any]:
        """获取NATS服务器信息"""
        try:
            if not self.is_running():
                return {'status': 'stopped'}
            
            # 通过HTTP监控端点获取信息
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(f'http://localhost:{self.http_port}/varz', timeout=5) as response:
                        if response.status == 200:
                            server_info = await response.json()
                            return {
                                'status': 'running',
                                'server_info': server_info
                            }
                except:
                    pass
                
                # 如果HTTP端点不可用，返回基本信息
                return {
                    'status': 'running',
                    'pid': self.server_process.pid,
                    'ports': {
                        'nats': self.nats_port,
                        'cluster': self.cluster_port,
                        'http': self.http_port
                    }
                }
                
        except Exception as e:
            return {'status': 'error', 'error': str(e)}


class NATSStreamManager:
    """NATS Stream管理器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = structlog.get_logger(__name__)
        self.nc = None
        self.js = None
        
        # 流配置
        self.streams_config = config.get('streams', {})
        self.nats_url = config.get('nats_url', 'nats://localhost:4222')
        
        # 默认流配置
        self.default_streams = {
            'MARKET_DATA': {
                'subjects': ['market.>'],
                'retention': 'limits',
                'max_age': 3600,  # 1小时
                'max_msgs': 1000000,
                'storage': 'file'
            },
            'SYSTEM_EVENTS': {
                'subjects': ['system.>'],
                'retention': 'limits', 
                'max_age': 86400,  # 24小时
                'max_msgs': 100000,
                'storage': 'file'
            },
            'SERVICE_LOGS': {
                'subjects': ['service.>'],
                'retention': 'limits',
                'max_age': 604800,  # 7天
                'max_msgs': 500000,
                'storage': 'file'
            }
        }
    
    async def connect(self) -> bool:
        """连接到NATS服务器"""
        if not NATS_AVAILABLE:
            self.logger.error("NATS客户端库不可用")
            return False
            
        try:
            self.nc = await nats.connect(self.nats_url)
            self.js = self.nc.jetstream()
            
            self.logger.info("已连接到NATS服务器")
            return True
            
        except Exception as e:
            self.logger.error(f"连接NATS服务器失败: {e}")
            return False
    
    async def disconnect(self):
        """断开NATS连接"""
        try:
            if self.nc:
                await self.nc.close()
                self.nc = None
                self.js = None
                self.logger.info("已断开NATS连接")
        except Exception as e:
            self.logger.error(f"断开NATS连接失败: {e}")
    
    async def create_streams(self) -> bool:
        """创建JetStream流"""
        if not self.js:
            self.logger.error("JetStream未初始化")
            return False
        
        try:
            # 合并默认流和配置的流
            all_streams = {**self.default_streams, **self.streams_config}
            
            for stream_name, stream_config in all_streams.items():
                try:
                    # 检查流是否已存在
                    try:
                        await self.js.stream_info(stream_name)
                        self.logger.info(f"流 {stream_name} 已存在")
                        continue
                    except:
                        pass
                    
                    # 创建流
                    from nats.js.api import StreamConfig, RetentionPolicy, StorageType
                    
                    # 转换配置
                    retention = RetentionPolicy.LIMITS
                    if stream_config.get('retention') == 'interest':
                        retention = RetentionPolicy.INTEREST
                    elif stream_config.get('retention') == 'workqueue':
                        retention = RetentionPolicy.WORK_QUEUE
                    
                    storage = StorageType.FILE
                    if stream_config.get('storage') == 'memory':
                        storage = StorageType.MEMORY
                    
                    config = StreamConfig(
                        name=stream_name,
                        subjects=stream_config['subjects'],
                        retention=retention,
                        max_age=stream_config.get('max_age', 3600),
                        max_msgs=stream_config.get('max_msgs', 1000000),
                        storage=storage
                    )
                    
                    await self.js.add_stream(config)
                    self.logger.info(f"创建流 {stream_name} 成功")
                    
                except Exception as e:
                    self.logger.error(f"创建流 {stream_name} 失败: {e}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"创建流失败: {e}")
            return False
    
    async def get_streams_info(self) -> List[Dict[str, Any]]:
        """获取流信息"""
        if not self.js:
            return []
        
        try:
            streams = []
            async for stream_info in self.js.streams_info():
                streams.append({
                    'name': stream_info.config.name,
                    'subjects': stream_info.config.subjects,
                    'messages': stream_info.state.messages,
                    'bytes': stream_info.state.bytes,
                    'first_seq': stream_info.state.first_seq,
                    'last_seq': stream_info.state.last_seq,
                    'consumer_count': stream_info.state.consumer_count
                })
            return streams
            
        except Exception as e:
            self.logger.error(f"获取流信息失败: {e}")
            return []
    
    async def publish_message(self, subject: str, message: Any) -> bool:
        """发布消息"""
        if not self.js:
            return False
        
        try:
            if isinstance(message, dict):
                message = json.dumps(message).encode()
            elif isinstance(message, str):
                message = message.encode()
            
            await self.js.publish(subject, message)
            return True
            
        except Exception as e:
            self.logger.error(f"发布消息失败: {e}")
            return False
    
    def get_client_status(self) -> Dict[str, Any]:
        """获取客户端状态"""
        return {
            'connected': self.nc is not None and self.nc.is_connected if self.nc else False,
            'jetstream_enabled': self.js is not None,
            'server_url': getattr(self, 'server_url', 'nats://localhost:4222'),
            'connection_time': datetime.datetime.now(datetime.timezone.utc).isoformat() if self.nc and self.nc.is_connected else None
        }


class MessageBrokerService(BaseService):
    """
    消息代理服务
    
    提供NATS消息代理功能：
    - NATS Server集群管理
    - JetStream流创建和管理
    - 消息发布和订阅
    - 消息持久化存储
    - 消息统计和监控
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__("message-broker", config)
        
        self.nats_manager = NATSServerManager(config.get('nats_server', {}))
        self.stream_manager = NATSStreamManager(config.get('nats_client', {}))
        self.is_running = False
        self.nc: Optional[NATSClient] = None

    async def on_startup(self):
        """服务启动时的钩子"""
        await self.initialize_service()
        await self.start_service()

    async def on_shutdown(self):
        """服务关闭时的钩子"""
        await self.stop_service()

    def setup_routes(self):
        """设置API路由"""
        # 标准化API端点
        self.app.router.add_get("/api/v1/status", self._get_service_status)

        # Message Broker特有的API端点
        self.app.router.add_get("/api/v1/broker/status", self._get_broker_status)
        self.app.router.add_post("/api/v1/broker/streams", self._create_stream)
        self.app.router.add_get("/api/v1/broker/streams", self._list_streams)
        self.app.router.add_delete("/api/v1/broker/streams/{stream_name}", self._delete_stream)
        self.app.router.add_post("/api/v1/broker/publish", self._publish_message)
        self.app.router.add_get("/api/v1/broker/health", self._get_broker_health)

        # 兼容性路由（保持向后兼容）
        self.app.router.add_get("/api/v1/streams", self._list_streams)
        self.app.router.add_post("/api/v1/publish", self._publish_message)

    def _create_success_response(self, data: Any, message: str = "Success") -> web.Response:
        """
        创建标准化成功响应

        Args:
            data: 响应数据
            message: 成功消息

        Returns:
            标准化的成功响应
        """
        return web.json_response({
            "status": "success",
            "message": message,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    def _create_error_response(self, message: str, error_code: str = "INTERNAL_ERROR",
                              status_code: int = 500) -> web.Response:
        """
        创建标准化错误响应

        Args:
            message: 错误描述信息
            error_code: 标准化错误代码
            status_code: HTTP状态码

        Returns:
            标准化的错误响应
        """
        return web.json_response({
            "status": "error",
            "error_code": error_code,
            "message": message,
            "data": None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, status=status_code)

    # 标准化错误代码常量
    ERROR_CODES = {
        'NATS_CONNECTION_ERROR': 'NATS_CONNECTION_ERROR',
        'NATS_SERVER_ERROR': 'NATS_SERVER_ERROR',
        'STREAM_NOT_FOUND': 'STREAM_NOT_FOUND',
        'STREAM_CREATION_ERROR': 'STREAM_CREATION_ERROR',
        'MESSAGE_PUBLISH_ERROR': 'MESSAGE_PUBLISH_ERROR',
        'INVALID_STREAM_DATA': 'INVALID_STREAM_DATA',
        'INVALID_MESSAGE_DATA': 'INVALID_MESSAGE_DATA',
        'JETSTREAM_ERROR': 'JETSTREAM_ERROR',
        'INVALID_PARAMETERS': 'INVALID_PARAMETERS',
        'SERVICE_UNAVAILABLE': 'SERVICE_UNAVAILABLE',
        'INTERNAL_ERROR': 'INTERNAL_ERROR'
    }

    async def initialize_service(self) -> bool:
        """初始化消息代理服务"""
        try:
            self.logger.info("初始化NATS服务器...")
            success = await self.nats_manager.start_nats_server()
            if not success:
                self.logger.error("NATS服务器未能启动，服务初始化失败")
                # 不返回 False，而是继续启动基本服务
                self.logger.warning("将以降级模式运行，不支持NATS功能")
            else:
                self.logger.info("连接NATS客户端...")
                success = await self.stream_manager.connect()
                if not success:
                    self.logger.error("NATS客户端未能连接")
                    await self.nats_manager.stop_nats_server()
                    self.logger.warning("将以降级模式运行，不支持NATS功能")
                else:
                    self.logger.info("创建JetStream流...")
                    await self.stream_manager.create_streams()
                    self.logger.info("NATS功能初始化完成")
            
            self.logger.info("Message Broker Service 初始化完成")
            return True
        except Exception as e:
            self.logger.error(f"Message Broker Service 初始化异常: {e}")
            # 即使出现异常，也尝试启动基本服务
            self.logger.warning("初始化异常，将以基本模式运行")
            return True

    async def start_service(self) -> bool:
        """启动服务"""
        self.logger.info("Message Broker Service 已启动")
        self.is_running = True
        return True

    async def stop_service(self) -> bool:
        """停止服务"""
        self.logger.info("停止消息代理服务...")
        await self.stream_manager.disconnect()
        await self.nats_manager.stop_nats_server()
        self.logger.info("消息代理服务关闭")
        self.is_running = False
        return True

    async def get_broker_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        nats_status = await self.nats_manager.get_server_info()
        client_status = self.stream_manager.get_client_status()
        
        # 获取JetStream流信息
        streams_info = await self.stream_manager.get_streams_info()
        
        status = {
            'service': self.service_name,
            'service_name': self.service_name,  # 保持向后兼容
            'is_running': self.is_running,
            'nats_server': nats_status,
            'nats_client': client_status,
            'jetstream_streams': streams_info,
            'message_stats': {
                'published': 0,  # 这里可以添加实际的统计
                'consumed': 0,
                'errors': 0
            }
        }
        return status

    async def _get_service_status(self, request: web.Request) -> web.Response:
        """获取服务状态 - 标准化API端点"""
        try:
            # 获取基础服务信息
            uptime_seconds = (datetime.now(timezone.utc) - self.start_time).total_seconds()

            # 获取NATS相关状态
            nats_status = await self.nats_manager.get_server_info()
            client_status = self.stream_manager.get_client_status()
            streams_info = await self.stream_manager.get_streams_info()

            status_data = {
                "service": "message-broker",
                "status": "running" if self.is_running else "stopped",
                "uptime_seconds": round(uptime_seconds, 2),
                "version": "1.0.0",
                "environment": self.config.get('environment', 'production'),
                "port": self.config.get('port', 8086),
                "features": {
                    "nats_server": True,
                    "jetstream": True,
                    "message_routing": True,
                    "stream_management": True,
                    "message_persistence": True
                },
                "nats_info": {
                    "server_status": nats_status.get('status', 'unknown') if nats_status else 'unavailable',
                    "client_connected": client_status.get('connected', False) if client_status else False,
                    "streams_count": len(streams_info) if streams_info else 0,
                    "server_version": nats_status.get('version', 'unknown') if nats_status else 'unknown'
                },
                "statistics": {
                    "messages_published": 0,  # 可以添加实际统计
                    "messages_consumed": 0,
                    "active_streams": len(streams_info) if streams_info else 0,
                    "connection_errors": 0
                }
            }

            return self._create_success_response(status_data, "Service status retrieved successfully")

        except Exception as e:
            self.logger.error(f"获取服务状态失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to retrieve service status: {str(e)}",
                self.ERROR_CODES['INTERNAL_ERROR']
            )

    async def _get_broker_status(self, request: web.Request) -> web.Response:
        """获取详细的broker状态信息"""
        try:
            # 获取详细的broker状态
            nats_status = await self.nats_manager.get_server_info()
            client_status = self.stream_manager.get_client_status()
            streams_info = await self.stream_manager.get_streams_info()

            broker_data = {
                "service_name": "message-broker",
                "is_running": self.is_running,
                "nats_server": nats_status,
                "nats_client": client_status,
                "jetstream_streams": streams_info,
                "message_stats": {
                    "published": 0,
                    "consumed": 0,
                    "errors": 0
                },
                "uptime_seconds": (datetime.now(timezone.utc) - self.start_time).total_seconds()
            }

            return self._create_success_response(broker_data, "Broker status retrieved successfully")

        except Exception as e:
            self.logger.error(f"获取broker状态失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to retrieve broker status: {str(e)}",
                self.ERROR_CODES['NATS_SERVER_ERROR']
            )

    async def _get_broker_health(self, request: web.Request) -> web.Response:
        """获取broker健康状态"""
        try:
            nats_status = await self.nats_manager.get_server_info()
            client_status = self.stream_manager.get_client_status()

            # 判断健康状态
            nats_healthy = nats_status and nats_status.get('status') == 'running'
            client_healthy = client_status and client_status.get('connected', False)
            overall_healthy = nats_healthy and client_healthy

            health_data = {
                "healthy": overall_healthy,
                "components": {
                    "nats_server": {
                        "healthy": nats_healthy,
                        "status": nats_status.get('status', 'unknown') if nats_status else 'unavailable'
                    },
                    "nats_client": {
                        "healthy": client_healthy,
                        "connected": client_status.get('connected', False) if client_status else False
                    }
                },
                "last_check": datetime.now(timezone.utc).isoformat()
            }

            return self._create_success_response(health_data, "Broker health retrieved successfully")

        except Exception as e:
            self.logger.error(f"获取broker健康状态失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to retrieve broker health: {str(e)}",
                self.ERROR_CODES['NATS_SERVER_ERROR']
            )

    async def _create_stream(self, request: web.Request) -> web.Response:
        """创建JetStream流"""
        try:
            # 解析请求数据
            data = await request.json()

            # 验证必需字段
            stream_name = data.get("name")
            subjects = data.get("subjects")

            if not stream_name:
                return self._create_error_response(
                    "Stream name is required",
                    self.ERROR_CODES['INVALID_STREAM_DATA'],
                    400
                )

            if not subjects or not isinstance(subjects, list):
                return self._create_error_response(
                    "Subjects must be a non-empty list",
                    self.ERROR_CODES['INVALID_STREAM_DATA'],
                    400
                )

            # 检查NATS连接
            if not self.stream_manager.nc or not self.stream_manager.js:
                return self._create_error_response(
                    "NATS JetStream not available",
                    self.ERROR_CODES['JETSTREAM_ERROR'],
                    503
                )

            # 创建流
            try:
                await self.stream_manager.js.add_stream(
                    name=stream_name,
                    subjects=subjects,
                    retention=data.get("retention", "limits"),
                    max_msgs=data.get("max_msgs", 1000000),
                    max_bytes=data.get("max_bytes", 1024*1024*1024),  # 1GB
                    max_age=data.get("max_age", 24*60*60)  # 24 hours
                )

                stream_data = {
                    "name": stream_name,
                    "subjects": subjects,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "config": {
                        "retention": data.get("retention", "limits"),
                        "max_msgs": data.get("max_msgs", 1000000),
                        "max_bytes": data.get("max_bytes", 1024*1024*1024),
                        "max_age": data.get("max_age", 24*60*60)
                    }
                }

                return self._create_success_response(stream_data, f"Stream '{stream_name}' created successfully")

            except Exception as e:
                if "stream name already in use" in str(e).lower():
                    return self._create_error_response(
                        f"Stream '{stream_name}' already exists",
                        self.ERROR_CODES['STREAM_CREATION_ERROR'],
                        409
                    )
                else:
                    raise e

        except json.JSONDecodeError:
            return self._create_error_response(
                "Invalid JSON data",
                self.ERROR_CODES['INVALID_STREAM_DATA'],
                400
            )
        except Exception as e:
            self.logger.error(f"创建流失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to create stream: {str(e)}",
                self.ERROR_CODES['STREAM_CREATION_ERROR']
            )

    async def _list_streams(self, request: web.Request) -> web.Response:
        """获取JetStream流列表"""
        try:
            # 检查NATS连接
            if not self.stream_manager.nc or not self.stream_manager.js:
                return self._create_error_response(
                    "NATS JetStream not available",
                    self.ERROR_CODES['JETSTREAM_ERROR'],
                    503
                )

            # 获取流信息
            streams_info = await self.stream_manager.get_streams_info()

            # 格式化流信息
            streams = []
            for stream_info in streams_info:
                stream_data = {
                    "name": stream_info.get("name", "unknown"),
                    "subjects": stream_info.get("subjects", []),
                    "messages": stream_info.get("messages", 0),
                    "bytes": stream_info.get("bytes", 0),
                    "consumers": stream_info.get("consumers", 0),
                    "created": stream_info.get("created", None),
                    "config": {
                        "retention": stream_info.get("retention", "limits"),
                        "max_msgs": stream_info.get("max_msgs", 0),
                        "max_bytes": stream_info.get("max_bytes", 0),
                        "max_age": stream_info.get("max_age", 0)
                    }
                }
                streams.append(stream_data)

            list_data = {
                "streams": streams,
                "total_count": len(streams),
                "total_messages": sum(s["messages"] for s in streams),
                "total_bytes": sum(s["bytes"] for s in streams)
            }

            return self._create_success_response(list_data, "Streams retrieved successfully")

        except Exception as e:
            self.logger.error(f"获取流列表失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to retrieve streams: {str(e)}",
                self.ERROR_CODES['JETSTREAM_ERROR']
            )

    async def _delete_stream(self, request: web.Request) -> web.Response:
        """删除JetStream流"""
        try:
            stream_name = request.match_info.get('stream_name')

            if not stream_name:
                return self._create_error_response(
                    "Stream name is required",
                    self.ERROR_CODES['INVALID_PARAMETERS'],
                    400
                )

            # 检查NATS连接
            if not self.stream_manager.nc or not self.stream_manager.js:
                return self._create_error_response(
                    "NATS JetStream not available",
                    self.ERROR_CODES['JETSTREAM_ERROR'],
                    503
                )

            # 检查流是否存在
            try:
                await self.stream_manager.js.stream_info(stream_name)
            except Exception:
                return self._create_error_response(
                    f"Stream '{stream_name}' not found",
                    self.ERROR_CODES['STREAM_NOT_FOUND'],
                    404
                )

            # 删除流
            await self.stream_manager.js.delete_stream(stream_name)

            delete_data = {
                "stream_name": stream_name,
                "deleted_at": datetime.now(timezone.utc).isoformat()
            }

            return self._create_success_response(delete_data, f"Stream '{stream_name}' deleted successfully")

        except Exception as e:
            self.logger.error(f"删除流失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to delete stream: {str(e)}",
                self.ERROR_CODES['STREAM_CREATION_ERROR']
            )

    async def _publish_message(self, request: web.Request) -> web.Response:
        """发布消息到JetStream"""
        try:
            # 解析请求数据
            data = await request.json()

            # 验证必需字段
            subject = data.get("subject")
            message = data.get("message")

            if not subject:
                return self._create_error_response(
                    "Subject is required",
                    self.ERROR_CODES['INVALID_MESSAGE_DATA'],
                    400
                )

            if message is None:
                return self._create_error_response(
                    "Message is required",
                    self.ERROR_CODES['INVALID_MESSAGE_DATA'],
                    400
                )

            # 检查NATS连接
            if not self.stream_manager.nc or not self.stream_manager.js:
                return self._create_error_response(
                    "NATS JetStream not available",
                    self.ERROR_CODES['JETSTREAM_ERROR'],
                    503
                )

            # 准备消息数据
            if isinstance(message, dict):
                message_bytes = json.dumps(message).encode()
            elif isinstance(message, str):
                message_bytes = message.encode()
            else:
                message_bytes = str(message).encode()

            # 发布消息
            ack = await self.stream_manager.js.publish(subject, message_bytes)

            publish_data = {
                "subject": subject,
                "message_id": ack.seq if ack else None,
                "stream": ack.stream if ack else None,
                "published_at": datetime.now(timezone.utc).isoformat(),
                "message_size": len(message_bytes)
            }

            return self._create_success_response(publish_data, "Message published successfully")

        except json.JSONDecodeError:
            return self._create_error_response(
                "Invalid JSON data",
                self.ERROR_CODES['INVALID_MESSAGE_DATA'],
                400
            )
        except Exception as e:
            self.logger.error(f"发布消息失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to publish message: {str(e)}",
                self.ERROR_CODES['MESSAGE_PUBLISH_ERROR']
            )



async def main():
    """服务主入口点"""
    try:
        # 在Docker容器中调整配置路径
        try:
            project_root = Path(__file__).resolve().parents[2]
            config_path = project_root / 'config' / 'services.yaml'
        except IndexError:
            # Docker容器中的路径
            config_path = Path('/app/config/services.yaml')
            if not config_path.exists():
                # 使用默认配置
                config_path = None

        if config_path and config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                full_config = yaml.safe_load(f) or {}
            service_config = full_config.get('services', {}).get('message-broker', {})
        else:
            # 使用环境变量配置
            service_config = {
                'port': int(os.getenv('API_PORT', '8086')),
                'nats_url': os.getenv('NATS_URL', 'nats://nats:4222'),
                'log_level': os.getenv('LOG_LEVEL', 'INFO')
            }
        
        service = MessageBrokerService(config=service_config)
        await service.start(
            host=service_config.get('host', '0.0.0.0'),
            port=service_config.get('port', 8086)
        )

    except Exception:
        logging.basicConfig()
        logging.critical("Message Broker Service failed to start", exc_info=True)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    # 配置日志记录
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    
    asyncio.run(main())