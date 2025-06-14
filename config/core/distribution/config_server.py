"""
MarketPrism 配置服务器
实现集中配置管理的HTTP API和WebSocket推送服务
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict
from enum import Enum
import jwt
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor

try:
    from flask import Flask, request, jsonify, g
    from flask_cors import CORS
    import websockets
    from websockets.server import WebSocketServerProtocol
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    Flask = None
    request = None
    jsonify = None
    g = None
    CORS = None
    websockets = None
    WebSocketServerProtocol = None

from ..version_control.config_version_control import ConfigVersionControl
from ..repositories.config_repository import ConfigRepository


class ServerStatus(Enum):
    """服务器状态枚举"""
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class ClientConnection:
    """客户端连接信息"""
    client_id: str
    websocket: Optional[Any] = None
    subscriptions: Set[str] = None
    last_heartbeat: datetime = None
    connected_at: datetime = None
    
    def __post_init__(self):
        if self.subscriptions is None:
            self.subscriptions = set()
        if self.last_heartbeat is None:
            self.last_heartbeat = datetime.now()
        if self.connected_at is None:
            self.connected_at = datetime.now()


@dataclass
class ServerMetrics:
    """服务器指标"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    active_connections: int = 0
    total_connections: int = 0
    config_operations: int = 0
    push_notifications: int = 0
    average_response_time: float = 0.0
    uptime_seconds: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ConfigServer:
    """
    配置服务器
    提供HTTP API和WebSocket推送服务的集中配置管理
    """
    
    def __init__(
        self,
        config_repository: ConfigRepository,
        version_control: Optional[ConfigVersionControl] = None,
        host: str = "localhost",
        port: int = 8080,
        websocket_port: int = 8081,
        secret_key: str = "marketprism-config-server",
        enable_auth: bool = True,
        max_connections: int = 10000
    ):
        """
        初始化配置服务器
        
        Args:
            config_repository: 配置仓库
            version_control: 版本控制系统
            host: 服务器主机
            port: HTTP服务端口
            websocket_port: WebSocket服务端口
            secret_key: JWT密钥
            enable_auth: 是否启用认证
            max_connections: 最大连接数
        """
        self.config_repository = config_repository
        self.version_control = version_control
        self.host = host
        self.port = port
        self.websocket_port = websocket_port
        self.secret_key = secret_key
        self.enable_auth = enable_auth
        self.max_connections = max_connections
        
        # 服务器状态
        self.status = ServerStatus.STOPPED
        self.start_time = None
        self.metrics = ServerMetrics()
        
        # 客户端连接管理
        self.clients: Dict[str, ClientConnection] = {}
        self.client_lock = threading.RLock()
        
        # Flask应用
        self.app = None
        self.websocket_server = None
        
        # 线程池
        self.executor = ThreadPoolExecutor(max_workers=10)
        
        # 日志
        self.logger = logging.getLogger(__name__)
        
        # 初始化Flask应用
        if FLASK_AVAILABLE:
            self._init_flask_app()
    
    def _init_flask_app(self):
        """初始化Flask应用"""
        if not FLASK_AVAILABLE:
            raise ImportError("Flask is required for ConfigServer")
        
        self.app = Flask(__name__)
        self.app.config['SECRET_KEY'] = self.secret_key
        CORS(self.app)
        
        # 注册路由
        self._register_routes()
        
        # 请求前处理
        @self.app.before_request
        def before_request():
            g.start_time = time.time()
            self.metrics.total_requests += 1
        
        # 请求后处理
        @self.app.after_request
        def after_request(response):
            # 更新响应时间
            if hasattr(g, 'start_time'):
                response_time = time.time() - g.start_time
                self._update_response_time(response_time)
            
            # 更新成功/失败计数
            if response.status_code < 400:
                self.metrics.successful_requests += 1
            else:
                self.metrics.failed_requests += 1
            
            return response
    
    def _register_routes(self):
        """注册HTTP路由"""
        
        @self.app.route('/health', methods=['GET'])
        def health_check():
            """健康检查"""
            return jsonify({
                'status': self.status.value,
                'uptime': self._get_uptime(),
                'active_connections': len(self.clients),
                'version': '1.0.0'
            })
        
        @self.app.route('/metrics', methods=['GET'])
        def get_metrics():
            """获取服务器指标"""
            metrics = self.metrics.to_dict()
            metrics['uptime_seconds'] = self._get_uptime()
            metrics['active_connections'] = len(self.clients)
            return jsonify(metrics)
        
        @self.app.route('/status', methods=['GET'])
        def get_status():
            """获取详细状态"""
            return jsonify({
                'server': {
                    'status': self.status.value,
                    'host': self.host,
                    'port': self.port,
                    'websocket_port': self.websocket_port,
                    'uptime': self._get_uptime(),
                    'start_time': self.start_time.isoformat() if self.start_time else None
                },
                'connections': {
                    'active': len(self.clients),
                    'max': self.max_connections,
                    'total': self.metrics.total_connections
                },
                'metrics': self.metrics.to_dict()
            })
        
        @self.app.route('/api/v1/auth/token', methods=['POST'])
        def generate_token():
            """生成访问令牌"""
            data = request.get_json() or {}
            client_id = data.get('client_id', 'anonymous')
            
            # 生成JWT令牌
            payload = {
                'client_id': client_id,
                'exp': datetime.datetime.now(datetime.timezone.utc) + timedelta(hours=24),
                'iat': datetime.datetime.now(datetime.timezone.utc)
            }
            
            token = jwt.encode(payload, self.secret_key, algorithm='HS256')
            
            return jsonify({
                'token': token,
                'expires_in': 86400,  # 24小时
                'client_id': client_id
            })
        
        @self.app.route('/api/v1/config/<namespace>/<key>', methods=['GET'])
        def get_config(namespace: str, key: str):
            """获取配置"""
            if self.enable_auth and not self._verify_token():
                return jsonify({'error': 'Unauthorized'}), 401
            
            try:
                value = self.config_repository.get(f"{namespace}.{key}")
                version = None
                
                if self.version_control:
                    # 获取版本信息
                    history = self.version_control.get_file_history(f"{namespace}.{key}")
                    if history:
                        version = history[0].commit_id[:8]
                
                self.metrics.config_operations += 1
                
                return jsonify({
                    'namespace': namespace,
                    'key': key,
                    'value': value,
                    'version': version,
                    'timestamp': datetime.now().isoformat()
                })
                
            except Exception as e:
                self.logger.error(f"Error getting config {namespace}.{key}: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/v1/config/<namespace>/<key>', methods=['POST', 'PUT'])
        def set_config(namespace: str, key: str):
            """设置配置"""
            if self.enable_auth and not self._verify_token():
                return jsonify({'error': 'Unauthorized'}), 401
            
            try:
                data = request.get_json()
                if not data or 'value' not in data:
                    return jsonify({'error': 'Missing value'}), 400
                
                value = data['value']
                comment = data.get('comment', f'Update {namespace}.{key}')
                
                # 设置配置
                self.config_repository.set(f"{namespace}.{key}", value)
                
                # 版本控制提交
                if self.version_control:
                    self.version_control.stage_changes([f"{namespace}.{key}"])
                    commit_id = self.version_control.commit(comment)
                else:
                    commit_id = None
                
                self.metrics.config_operations += 1
                
                # 推送变更通知
                self._push_config_change(namespace, key, value, 'updated')
                
                return jsonify({
                    'namespace': namespace,
                    'key': key,
                    'value': value,
                    'commit_id': commit_id[:8] if commit_id else None,
                    'timestamp': datetime.now().isoformat()
                })
                
            except Exception as e:
                self.logger.error(f"Error setting config {namespace}.{key}: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/v1/config/<namespace>/<key>', methods=['DELETE'])
        def delete_config(namespace: str, key: str):
            """删除配置"""
            if self.enable_auth and not self._verify_token():
                return jsonify({'error': 'Unauthorized'}), 401
            
            try:
                # 删除配置
                self.config_repository.delete(f"{namespace}.{key}")
                
                # 版本控制提交
                if self.version_control:
                    self.version_control.stage_changes([f"{namespace}.{key}"])
                    commit_id = self.version_control.commit(f'Delete {namespace}.{key}')
                else:
                    commit_id = None
                
                self.metrics.config_operations += 1
                
                # 推送变更通知
                self._push_config_change(namespace, key, None, 'deleted')
                
                return jsonify({
                    'namespace': namespace,
                    'key': key,
                    'action': 'deleted',
                    'commit_id': commit_id[:8] if commit_id else None,
                    'timestamp': datetime.now().isoformat()
                })
                
            except Exception as e:
                self.logger.error(f"Error deleting config {namespace}.{key}: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/v1/config/<namespace>/list', methods=['GET'])
        def list_configs(namespace: str):
            """列出命名空间下的所有配置"""
            if self.enable_auth and not self._verify_token():
                return jsonify({'error': 'Unauthorized'}), 401
            
            try:
                pattern = request.args.get('pattern', '*')
                keys = self.config_repository.list_keys(f"{namespace}.*")
                
                # 过滤键名
                if pattern != '*':
                    import fnmatch
                    keys = [k for k in keys if fnmatch.fnmatch(k, f"{namespace}.{pattern}")]
                
                # 获取配置值
                configs = {}
                for key in keys:
                    try:
                        value = self.config_repository.get(key)
                        # 移除命名空间前缀
                        clean_key = key[len(namespace)+1:] if key.startswith(f"{namespace}.") else key
                        configs[clean_key] = value
                    except Exception as e:
                        self.logger.warning(f"Error getting config {key}: {e}")
                
                return jsonify({
                    'namespace': namespace,
                    'configs': configs,
                    'count': len(configs),
                    'timestamp': datetime.now().isoformat()
                })
                
            except Exception as e:
                self.logger.error(f"Error listing configs for namespace {namespace}: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/v1/config/<namespace>/version', methods=['GET'])
        def get_namespace_version(namespace: str):
            """获取命名空间版本信息"""
            if self.enable_auth and not self._verify_token():
                return jsonify({'error': 'Unauthorized'}), 401
            
            try:
                if not self.version_control:
                    return jsonify({'error': 'Version control not enabled'}), 404
                
                # 获取命名空间下所有文件的最新提交
                keys = self.config_repository.list_keys(f"{namespace}.*")
                latest_commit = None
                latest_timestamp = None
                
                for key in keys:
                    history = self.version_control.get_file_history(key, limit=1)
                    if history:
                        commit = history[0]
                        if latest_timestamp is None or commit.timestamp > latest_timestamp:
                            latest_commit = commit
                            latest_timestamp = commit.timestamp
                
                if latest_commit:
                    return jsonify({
                        'namespace': namespace,
                        'latest_commit': latest_commit.commit_id[:8],
                        'timestamp': latest_commit.timestamp.isoformat(),
                        'author': latest_commit.author,
                        'message': latest_commit.message
                    })
                else:
                    return jsonify({
                        'namespace': namespace,
                        'latest_commit': None,
                        'message': 'No commits found'
                    })
                
            except Exception as e:
                self.logger.error(f"Error getting version for namespace {namespace}: {e}")
                return jsonify({'error': str(e)}), 500
    
    def _verify_token(self) -> bool:
        """验证JWT令牌"""
        if not self.enable_auth:
            return True
        
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return False
        
        token = auth_header[7:]  # 移除 'Bearer ' 前缀
        
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
            g.client_id = payload.get('client_id', 'anonymous')
            return True
        except jwt.ExpiredSignatureError:
            return False
        except jwt.InvalidTokenError:
            return False
    
    def _update_response_time(self, response_time: float):
        """更新平均响应时间"""
        if self.metrics.successful_requests > 0:
            # 计算移动平均
            total_time = self.metrics.average_response_time * (self.metrics.successful_requests - 1)
            self.metrics.average_response_time = (total_time + response_time) / self.metrics.successful_requests
        else:
            self.metrics.average_response_time = response_time
    
    def _get_uptime(self) -> float:
        """获取运行时间（秒）"""
        if self.start_time:
            return (datetime.now() - self.start_time).total_seconds()
        return 0.0
    
    def _push_config_change(self, namespace: str, key: str, value: Any, action: str):
        """推送配置变更通知"""
        if not self.clients:
            return
        
        message = {
            'type': 'config_change',
            'namespace': namespace,
            'key': key,
            'value': value,
            'action': action,
            'timestamp': datetime.now().isoformat()
        }
        
        # 异步推送给所有订阅的客户端
        self.executor.submit(self._broadcast_message, message, namespace)
    
    def _broadcast_message(self, message: Dict[str, Any], namespace: str = None):
        """广播消息给客户端"""
        if not FLASK_AVAILABLE or not websockets:
            return
        
        message_json = json.dumps(message)
        disconnected_clients = []
        
        with self.client_lock:
            for client_id, client in self.clients.items():
                # 检查订阅
                if namespace and f"namespace:{namespace}" not in client.subscriptions:
                    continue
                
                if client.websocket:
                    try:
                        # 这里需要在实际的WebSocket服务器中实现
                        # 暂时记录推送
                        self.metrics.push_notifications += 1
                        self.logger.debug(f"Pushed message to client {client_id}")
                    except Exception as e:
                        self.logger.warning(f"Failed to push message to client {client_id}: {e}")
                        disconnected_clients.append(client_id)
            
            # 清理断开的客户端
            for client_id in disconnected_clients:
                self.clients.pop(client_id, None)
                self.metrics.active_connections = len(self.clients)
    
    async def _handle_websocket_client(self, websocket: WebSocketServerProtocol, path: str):
        """处理WebSocket客户端连接"""
        client_id = self._generate_client_id()
        
        try:
            # 注册客户端
            with self.client_lock:
                if len(self.clients) >= self.max_connections:
                    await websocket.close(code=1013, reason="Server overloaded")
                    return
                
                self.clients[client_id] = ClientConnection(
                    client_id=client_id,
                    websocket=websocket
                )
                self.metrics.active_connections = len(self.clients)
                self.metrics.total_connections += 1
            
            self.logger.info(f"Client {client_id} connected")
            
            # 发送欢迎消息
            welcome_message = {
                'type': 'welcome',
                'client_id': client_id,
                'server_time': datetime.now().isoformat()
            }
            await websocket.send(json.dumps(welcome_message))
            
            # 处理客户端消息
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self._handle_client_message(client_id, data)
                except json.JSONDecodeError:
                    error_message = {
                        'type': 'error',
                        'message': 'Invalid JSON format'
                    }
                    await websocket.send(json.dumps(error_message))
                except Exception as e:
                    self.logger.error(f"Error handling message from client {client_id}: {e}")
        
        except websockets.exceptions.ConnectionClosed:
            self.logger.info(f"Client {client_id} disconnected")
        except Exception as e:
            self.logger.error(f"Error handling WebSocket client {client_id}: {e}")
        finally:
            # 清理客户端
            with self.client_lock:
                self.clients.pop(client_id, None)
                self.metrics.active_connections = len(self.clients)
    
    async def _handle_client_message(self, client_id: str, data: Dict[str, Any]):
        """处理客户端消息"""
        message_type = data.get('type')
        
        if message_type == 'subscribe':
            # 订阅配置变更
            namespace = data.get('namespace')
            if namespace:
                with self.client_lock:
                    if client_id in self.clients:
                        self.clients[client_id].subscriptions.add(f"namespace:{namespace}")
                
                response = {
                    'type': 'subscription_confirmed',
                    'namespace': namespace,
                    'client_id': client_id
                }
                
                client = self.clients.get(client_id)
                if client and client.websocket:
                    await client.websocket.send(json.dumps(response))
        
        elif message_type == 'unsubscribe':
            # 取消订阅
            namespace = data.get('namespace')
            if namespace:
                with self.client_lock:
                    if client_id in self.clients:
                        self.clients[client_id].subscriptions.discard(f"namespace:{namespace}")
                
                response = {
                    'type': 'unsubscription_confirmed',
                    'namespace': namespace,
                    'client_id': client_id
                }
                
                client = self.clients.get(client_id)
                if client and client.websocket:
                    await client.websocket.send(json.dumps(response))
        
        elif message_type == 'heartbeat':
            # 心跳
            with self.client_lock:
                if client_id in self.clients:
                    self.clients[client_id].last_heartbeat = datetime.now()
            
            response = {
                'type': 'heartbeat_ack',
                'server_time': datetime.now().isoformat()
            }
            
            client = self.clients.get(client_id)
            if client and client.websocket:
                await client.websocket.send(json.dumps(response))
    
    def _generate_client_id(self) -> str:
        """生成客户端ID"""
        timestamp = str(int(time.time() * 1000))
        random_str = hashlib.md5(f"{timestamp}{len(self.clients)}".encode()).hexdigest()[:8]
        return f"client_{timestamp}_{random_str}"
    
    def start(self, debug: bool = False):
        """启动配置服务器"""
        if not FLASK_AVAILABLE:
            raise ImportError("Flask and websockets are required for ConfigServer")
        
        self.status = ServerStatus.STARTING
        self.start_time = datetime.now()
        
        try:
            self.logger.info(f"Starting ConfigServer on {self.host}:{self.port}")
            
            # 启动WebSocket服务器
            if websockets:
                self.logger.info(f"Starting WebSocket server on {self.host}:{self.websocket_port}")
                # 注意：这里需要在实际部署时使用异步事件循环
                # 当前只是示例实现
            
            self.status = ServerStatus.RUNNING
            
            # 启动Flask应用
            self.app.run(
                host=self.host,
                port=self.port,
                debug=debug,
                threaded=True
            )
            
        except Exception as e:
            self.status = ServerStatus.ERROR
            self.logger.error(f"Error starting ConfigServer: {e}")
            raise
    
    def stop(self):
        """停止配置服务器"""
        self.status = ServerStatus.STOPPING
        
        try:
            # 关闭所有WebSocket连接
            with self.client_lock:
                for client in self.clients.values():
                    if client.websocket:
                        try:
                            # 在实际实现中需要正确关闭WebSocket
                            pass
                        except Exception as e:
                            self.logger.warning(f"Error closing client connection: {e}")
                
                self.clients.clear()
                self.metrics.active_connections = 0
            
            # 关闭线程池
            self.executor.shutdown(wait=True)
            
            self.status = ServerStatus.STOPPED
            self.logger.info("ConfigServer stopped")
            
        except Exception as e:
            self.status = ServerStatus.ERROR
            self.logger.error(f"Error stopping ConfigServer: {e}")
            raise
    
    def get_server_info(self) -> Dict[str, Any]:
        """获取服务器信息"""
        return {
            'status': self.status.value,
            'host': self.host,
            'port': self.port,
            'websocket_port': self.websocket_port,
            'uptime': self._get_uptime(),
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'metrics': self.metrics.to_dict(),
            'active_connections': len(self.clients),
            'max_connections': self.max_connections,
            'auth_enabled': self.enable_auth
        }