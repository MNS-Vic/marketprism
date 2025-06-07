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
from datetime import datetime, timedelta
import aiohttp
from aiohttp import web
import tempfile
import yaml

# 尝试导入NATS客户端
try:
    import nats
    from nats.js import JetStreamContext
    NATS_AVAILABLE = True
except ImportError:
    print("警告: NATS客户端库未安装，某些功能可能不可用")
    NATS_AVAILABLE = False

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

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
        super().__init__(
            service_name="message-broker-service",
            service_version="1.0.0",
            service_port=config.get('port', 8085),
            config=config
        )
        
        self.logger = structlog.get_logger(__name__)
        
        # 核心组件
        self.nats_manager = NATSServerManager(config.get('nats', {}))
        self.stream_manager = NATSStreamManager(config.get('nats', {}))
        
        # 配置
        self.auto_start_nats = config.get('auto_start_nats', True)
        self.auto_create_streams = config.get('auto_create_streams', True)
        
        # 统计
        self.message_stats = {
            'published': 0,
            'consumed': 0,
            'errors': 0,
            'start_time': datetime.utcnow()
        }
        
        self.logger.info("Message Broker Service 初始化完成")
    
    async def initialize_service(self) -> bool:
        """初始化消息代理服务"""
        try:
            # 启动NATS服务器
            if self.auto_start_nats:
                success = await self.nats_manager.start_nats_server()
                if not success:
                    self.logger.error("NATS服务器启动失败")
                    return False
                
                # 等待服务器完全启动
                await asyncio.sleep(3)
            
            # 连接到NATS并创建流
            if NATS_AVAILABLE:
                connected = await self.stream_manager.connect()
                if connected and self.auto_create_streams:
                    await self.stream_manager.create_streams()
            
            self.logger.info("Message Broker Service 初始化成功")
            return True
            
        except Exception as e:
            self.logger.error(f"Message Broker Service 初始化失败: {e}")
            return False
    
    async def start_service(self) -> bool:
        """启动消息代理服务"""
        try:
            self.logger.info("Message Broker Service 启动成功")
            return True
            
        except Exception as e:
            self.logger.error(f"启动Message Broker Service失败: {e}")
            return False
    
    async def stop_service(self) -> bool:
        """停止消息代理服务"""
        try:
            # 断开NATS连接
            await self.stream_manager.disconnect()
            
            # 停止NATS服务器
            await self.nats_manager.stop_nats_server()
            
            self.logger.info("Message Broker Service 已停止")
            return True
            
        except Exception as e:
            self.logger.error(f"停止Message Broker Service失败: {e}")
            return False
    
    async def get_broker_status(self) -> Dict[str, Any]:
        """获取消息代理状态"""
        try:
            # NATS服务器状态
            server_info = await self.nats_manager.get_server_info()
            
            # 流信息
            streams_info = await self.stream_manager.get_streams_info()
            
            # 统计信息
            uptime = (datetime.utcnow() - self.message_stats['start_time']).total_seconds()
            
            status = {
                'service': 'message-broker-service',
                'timestamp': datetime.utcnow().isoformat(),
                'uptime_seconds': uptime,
                'nats_server': server_info,
                'jetstream_streams': streams_info,
                'message_stats': self.message_stats,
                'nats_available': NATS_AVAILABLE
            }
            
            return status
            
        except Exception as e:
            return {'error': str(e)}


async def main():
    """主函数"""
    try:
        # 加载配置
        import yaml
        config_path = project_root / "config" / "services.yaml"
        
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                services_config = yaml.safe_load(f)
            config = services_config.get('message-broker-service', {})
        else:
            # 默认配置
            config = {
                'port': 8085,
                'auto_start_nats': True,
                'auto_create_streams': True,
                'nats': {
                    'nats_port': 4222,
                    'cluster_port': 6222,
                    'http_port': 8222,
                    'jetstream_enabled': True,
                    'jetstream_max_memory': '1GB',
                    'jetstream_max_storage': '10GB',
                    'nats_url': 'nats://localhost:4222'
                }
            }
        
        # 创建并启动服务
        service = MessageBrokerService(config)
        
        # 注册API路由
        @service.app.get("/api/v1/status")
        async def get_status(request):
            from aiohttp import web
            status = await service.get_broker_status()
            return web.json_response(status)
        
        @service.app.get("/api/v1/streams")
        async def get_streams(request):
            from aiohttp import web
            streams = await service.stream_manager.get_streams_info()
            return web.json_response({'streams': streams})
        
        @service.app.post("/api/v1/publish")
        async def publish_message(request):
            from aiohttp import web
            try:
                data = await request.json()
                subject = data.get('subject')
                message = data.get('message')
                
                if not subject or not message:
                    return web.json_response(
                        {'error': 'subject and message are required'}, 
                        status=400
                    )
                
                success = await service.stream_manager.publish_message(subject, message)
                if success:
                    service.message_stats['published'] += 1
                    return web.json_response({'success': True})
                else:
                    service.message_stats['errors'] += 1
                    return web.json_response(
                        {'error': 'Failed to publish message'}, 
                        status=500
                    )
                    
            except Exception as e:
                service.message_stats['errors'] += 1
                return web.json_response(
                    {'error': str(e)}, 
                    status=500
                )
        
        @service.app.get("/api/v1/nats/info")
        async def get_nats_info(request):
            from aiohttp import web
            info = await service.nats_manager.get_server_info()
            return web.json_response(info)
        
        # 启动服务
        await service.run()
        
    except KeyboardInterrupt:
        print("服务被用户中断")
    except Exception as e:
        print(f"服务启动失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())