"""
统一网络连接管理器

整合WebSocket和HTTP连接管理，提供：
- 一站式网络连接服务
- 统一的配置管理
- 连接健康监控
- 自动故障恢复
- 性能统计和监控
"""

import asyncio
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import structlog

from .proxy_manager import ProxyConfig, proxy_manager
from .websocket_manager import WebSocketConfig, WebSocketConnectionManager, websocket_manager
from .unified_session_manager import UnifiedSessionConfig as SessionConfig, unified_session_manager as session_manager


@dataclass
class NetworkConfig:
    """网络配置"""
    # 基础配置
    timeout: int = 30
    enable_proxy: bool = True
    enable_ssl: bool = True
    
    # WebSocket配置
    ws_ping_interval: Optional[int] = None
    ws_ping_timeout: Optional[int] = None
    ws_max_size: Optional[int] = None
    
    # HTTP配置
    http_connector_limit: int = 100
    http_connector_limit_per_host: int = 30
    http_retry_attempts: int = 3
    
    # 监控配置
    health_check_interval: int = 60
    connection_timeout_threshold: int = 300
    
    # 交易所特定配置
    exchange_name: Optional[str] = None
    disable_ssl_for_exchanges: Optional[List[str]] = None


class NetworkConnectionManager:
    """统一网络连接管理器"""
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
        
        # 子管理器
        self.websocket_manager = websocket_manager
        self.session_manager = session_manager
        self.proxy_manager = proxy_manager
        
        # 连接跟踪
        self.connections: Dict[str, Dict[str, Any]] = {}
        self.connection_stats: Dict[str, Any] = {
            'total_connections': 0,
            'active_connections': 0,
            'failed_connections': 0,
            'websocket_connections': 0,
            'http_sessions': 0,
            'proxy_connections': 0,
            'direct_connections': 0
        }
        
        # 健康监控
        self.health_check_task: Optional[asyncio.Task] = None
        self.is_monitoring = False
    
    async def create_websocket_connection(self,
                                        url: str,
                                        exchange_name: Optional[str] = None,
                                        network_config: Optional[NetworkConfig] = None,
                                        exchange_config: Optional[Dict[str, Any]] = None,
                                        **kwargs):
        """
        创建WebSocket连接
        
        Args:
            url: WebSocket URL
            exchange_name: 交易所名称
            network_config: 网络配置
            exchange_config: 交易所配置
            **kwargs: 其他WebSocket配置参数
        """
        try:
            # 使用提供的配置或默认配置
            net_config = network_config or NetworkConfig(exchange_name=exchange_name)
            
            # 创建WebSocket配置，避免参数重复
            ws_config_params = {
                'url': url,
                'timeout': net_config.timeout,
                'ssl_verify': net_config.enable_ssl,
                'ping_interval': net_config.ws_ping_interval,
                'ping_timeout': net_config.ws_ping_timeout,
                'max_size': net_config.ws_max_size,
                'exchange_name': exchange_name,
                'disable_ssl_for_exchanges': net_config.disable_ssl_for_exchanges,
            }

            # 合并kwargs，kwargs中的值优先级更高
            ws_config_params.update(kwargs)

            ws_config = WebSocketConfig(**ws_config_params)
            
            # 获取代理配置
            proxy_config = None
            if net_config.enable_proxy:
                proxy_config = self.proxy_manager.get_proxy_config(exchange_config)
            
            # 建立连接
            connection = await self.websocket_manager.connect(
                ws_config, proxy_config, exchange_config
            )
            
            if connection:
                # 记录连接信息
                connection_id = f"ws_{exchange_name or 'unknown'}_{len(self.connections)}"
                self.connections[connection_id] = {
                    'type': 'websocket',
                    'url': url,
                    'exchange': exchange_name,
                    'created_at': datetime.now(timezone.utc),
                    'config': ws_config,
                    'proxy_config': proxy_config,
                    'connection': connection
                }
                
                # 更新统计
                self._update_connection_stats('websocket', 'created', proxy_config)
                
                self.logger.info("WebSocket连接已建立",
                               connection_id=connection_id,
                               url=url,
                               exchange=exchange_name)
                
                return connection
            else:
                self._update_connection_stats('websocket', 'failed', proxy_config)
                return None
                
        except Exception as e:
            self.logger.error("创建WebSocket连接失败", 
                            url=url, 
                            exchange=exchange_name,
                            error=str(e))
            self._update_connection_stats('websocket', 'failed', None)
            raise
    
    async def create_http_session(self,
                                 session_name: str = "default",
                                 exchange_name: Optional[str] = None,
                                 network_config: Optional[NetworkConfig] = None,
                                 exchange_config: Optional[Dict[str, Any]] = None,
                                 **kwargs):
        """
        创建HTTP会话
        
        Args:
            session_name: 会话名称
            exchange_name: 交易所名称
            network_config: 网络配置
            exchange_config: 交易所配置
            **kwargs: 其他会话配置参数
        """
        try:
            # 使用提供的配置或默认配置
            net_config = network_config or NetworkConfig(exchange_name=exchange_name)
            
            # 创建会话配置
            session_config = SessionConfig(
                total_timeout=net_config.timeout,
                connector_limit=net_config.http_connector_limit,
                connector_limit_per_host=net_config.http_connector_limit_per_host,
                enable_ssl=net_config.enable_ssl,
                max_retries=net_config.http_retry_attempts,
                **kwargs
            )
            
            # 获取代理配置
            proxy_config = None
            if net_config.enable_proxy:
                proxy_config = self.proxy_manager.get_proxy_config(exchange_config)
            
            # 创建会话
            session = await self.session_manager.get_session(
                session_name, session_config, proxy_config, exchange_config
            )
            
            if session:
                # 记录会话信息
                session_id = f"http_{session_name}_{exchange_name or 'unknown'}"
                self.connections[session_id] = {
                    'type': 'http_session',
                    'session_name': session_name,
                    'exchange': exchange_name,
                    'created_at': datetime.now(timezone.utc),
                    'config': session_config,
                    'proxy_config': proxy_config,
                    'session': session
                }
                
                # 更新统计
                self._update_connection_stats('http', 'created', proxy_config)
                
                self.logger.info("HTTP会话已建立",
                               session_id=session_id,
                               session_name=session_name,
                               exchange=exchange_name)
                
                return session
            else:
                self._update_connection_stats('http', 'failed', proxy_config)
                return None
                
        except Exception as e:
            self.logger.error("创建HTTP会话失败",
                            session_name=session_name,
                            exchange=exchange_name,
                            error=str(e))
            self._update_connection_stats('http', 'failed', None)
            raise
    
    async def close_connection(self, connection_id: str):
        """关闭指定连接"""
        if connection_id in self.connections:
            conn_info = self.connections[connection_id]
            
            try:
                if conn_info['type'] == 'websocket':
                    await conn_info['connection'].close()
                elif conn_info['type'] == 'http_session':
                    await self.session_manager.close_session(conn_info['session_name'])
                
                del self.connections[connection_id]
                self.logger.info("连接已关闭", connection_id=connection_id)
                
            except Exception as e:
                self.logger.error("关闭连接失败", 
                                connection_id=connection_id,
                                error=str(e))
    
    async def close_all_connections(self):
        """关闭所有连接"""
        try:
            # 关闭WebSocket连接
            await self.websocket_manager.close_all_connections()
            
            # 关闭HTTP会话
            await self.session_manager.close_all_sessions()
            
            # 清理连接记录
            self.connections.clear()
            
            # 重置统计
            for key in self.connection_stats:
                self.connection_stats[key] = 0
            
            self.logger.info("所有网络连接已关闭")
            
        except Exception as e:
            self.logger.error("关闭连接时出错", error=str(e))
    
    def _update_connection_stats(self, conn_type: str, action: str, proxy_config: Optional[ProxyConfig]):
        """更新连接统计"""
        if action == 'created':
            self.connection_stats['total_connections'] += 1
            self.connection_stats['active_connections'] += 1
            
            if conn_type == 'websocket':
                self.connection_stats['websocket_connections'] += 1
            elif conn_type == 'http':
                self.connection_stats['http_sessions'] += 1
            
            if proxy_config and proxy_config.has_proxy():
                self.connection_stats['proxy_connections'] += 1
            else:
                self.connection_stats['direct_connections'] += 1
                
        elif action == 'failed':
            self.connection_stats['failed_connections'] += 1
        
        elif action == 'closed':
            self.connection_stats['active_connections'] = max(0, 
                self.connection_stats['active_connections'] - 1)
    
    async def start_monitoring(self, interval: int = 60):
        """启动连接健康监控"""
        if self.is_monitoring:
            return
        
        self.is_monitoring = True
        self.health_check_task = asyncio.create_task(self._health_check_loop(interval))
        self.logger.info("网络连接健康监控已启动", interval=interval)
    
    async def stop_monitoring(self):
        """停止连接健康监控"""
        self.is_monitoring = False
        
        if self.health_check_task and not self.health_check_task.done():
            self.health_check_task.cancel()
            try:
                await self.health_check_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("网络连接健康监控已停止")
    
    async def _health_check_loop(self, interval: int):
        """健康检查循环"""
        while self.is_monitoring:
            try:
                await self._perform_health_check()
                await asyncio.sleep(interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("健康检查失败", error=str(e))
                await asyncio.sleep(30)  # 出错后等待30秒再试
    
    async def _perform_health_check(self):
        """执行健康检查"""
        current_time = datetime.now(timezone.utc)
        stale_connections = []
        
        # 检查连接是否超时
        for conn_id, conn_info in self.connections.items():
            created_at = conn_info['created_at']
            age = (current_time - created_at).total_seconds()
            
            # 检查WebSocket连接
            if conn_info['type'] == 'websocket':
                connection = conn_info['connection']
                if connection.closed:
                    stale_connections.append(conn_id)
                    self.logger.warning("发现已关闭的WebSocket连接", 
                                      connection_id=conn_id)
            
            # 检查HTTP会话
            elif conn_info['type'] == 'http_session':
                session = conn_info['session']
                if session.closed:
                    stale_connections.append(conn_id)
                    self.logger.warning("发现已关闭的HTTP会话",
                                      connection_id=conn_id)
        
        # 清理失效连接
        for conn_id in stale_connections:
            await self.close_connection(conn_id)
            self._update_connection_stats('', 'closed', None)
        
        # 记录健康状态
        if stale_connections:
            self.logger.info("健康检查完成，清理失效连接",
                           cleaned=len(stale_connections),
                           active=self.connection_stats['active_connections'])
    
    def get_network_stats(self) -> Dict[str, Any]:
        """获取网络统计信息"""
        # 获取子管理器统计
        ws_stats = self.websocket_manager.get_connection_stats()
        http_stats = self.session_manager.get_session_stats()
        
        return {
            'overview': self.connection_stats.copy(),
            'websocket': ws_stats,
            'http_sessions': http_stats,
            'monitoring': {
                'is_monitoring': self.is_monitoring,
                'health_check_running': (self.health_check_task and 
                                       not self.health_check_task.done())
            },
            'connections': {
                conn_id: {
                    'type': info['type'],
                    'exchange': info.get('exchange'),
                    'created_at': info['created_at'].isoformat(),
                    'age_seconds': (datetime.now(timezone.utc) - info['created_at']).total_seconds(),
                    'has_proxy': (info.get('proxy_config') and 
                                info['proxy_config'].has_proxy()) if info.get('proxy_config') else False
                }
                for conn_id, info in self.connections.items()
            }
        }
    
    async def test_connectivity(self, 
                               url: str, 
                               connection_type: str = "websocket",
                               exchange_name: Optional[str] = None,
                               timeout: int = 10) -> Dict[str, Any]:
        """
        测试网络连接性
        
        Args:
            url: 测试URL
            connection_type: 连接类型 ('websocket' 或 'http')
            exchange_name: 交易所名称
            timeout: 超时时间
        """
        test_result = {
            'url': url,
            'type': connection_type,
            'exchange': exchange_name,
            'success': False,
            'error': None,
            'proxy_used': False,
            'response_time': None,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        start_time = datetime.now(timezone.utc)
        
        try:
            if connection_type == "websocket":
                # 测试WebSocket连接
                ws_config = WebSocketConfig(
                    url=url,
                    timeout=timeout,
                    exchange_name=exchange_name
                )
                
                proxy_config = self.proxy_manager.get_proxy_config()
                connection = await self.websocket_manager.connect(ws_config, proxy_config)
                
                if connection:
                    test_result['success'] = True
                    test_result['proxy_used'] = proxy_config.has_proxy()
                    await connection.close()
                
            elif connection_type == "http":
                # 测试HTTP连接
                session = await self.create_http_session(
                    session_name=f"test_{exchange_name or 'unknown'}",
                    exchange_name=exchange_name
                )
                
                response = await session.get(url, timeout=aiohttp.ClientTimeout(total=timeout))
                test_result['success'] = response.status < 400
                test_result['status_code'] = response.status
                
                await self.session_manager.close_session(f"test_{exchange_name or 'unknown'}")
            
            # 计算响应时间
            end_time = datetime.now(timezone.utc)
            test_result['response_time'] = (end_time - start_time).total_seconds()
            
        except Exception as e:
            test_result['error'] = str(e)
            test_result['response_time'] = (datetime.now(timezone.utc) - start_time).total_seconds()
        
        return test_result


# 全局网络连接管理器实例
network_manager = NetworkConnectionManager()