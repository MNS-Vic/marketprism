"""
统一WebSocket连接管理器

基于成功连接的模式，提供：
- 统一的WebSocket连接逻辑
- 自动代理检测和配置
- SSL/TLS灵活配置
- 连接重试和恢复
- aiohttp和websockets库兼容性
"""

import asyncio
import os
from typing import Optional, Dict, Any, Union
from dataclasses import dataclass
import aiohttp
import websockets
import structlog

from .proxy_manager import ProxyConfig, proxy_manager


@dataclass
class WebSocketConfig:
    """WebSocket连接配置"""
    url: str
    timeout: int = 10
    ssl_verify: bool = True
    ssl_context: Optional[Any] = None
    ping_interval: Optional[int] = None
    ping_timeout: Optional[int] = None
    max_size: Optional[int] = None
    extra_headers: Optional[Dict[str, str]] = None
    subprotocols: Optional[list] = None
    
    # 交易所特定配置
    exchange_name: Optional[str] = None
    disable_ssl_for_exchanges: Optional[list] = None
    
    def should_disable_ssl(self) -> bool:
        """判断是否应该禁用SSL验证"""
        if not self.ssl_verify:
            return True
            
        # 某些交易所在代理环境下需要禁用SSL
        if (self.disable_ssl_for_exchanges and 
            self.exchange_name and 
            self.exchange_name.lower() in [ex.lower() for ex in self.disable_ssl_for_exchanges]):
            return True
            
        return False


class WebSocketWrapper:
    """统一的WebSocket包装器，兼容不同底层实现"""
    
    def __init__(self, 
                 ws: Union[aiohttp.ClientWebSocketResponse, websockets.WebSocketClientProtocol],
                 session: Optional[aiohttp.ClientSession] = None,
                 connection_type: str = "aiohttp"):
        self.ws = ws
        self.session = session
        self.connection_type = connection_type
        self.closed = False
        self.logger = structlog.get_logger(__name__)
    
    async def send(self, data: str):
        """发送消息"""
        if self.closed:
            raise ConnectionError("WebSocket连接已关闭")
        
        try:
            if self.connection_type == "aiohttp":
                await self.ws.send_str(data)
            else:  # websockets
                await self.ws.send(data)
        except Exception as e:
            self.logger.error("发送WebSocket消息失败", error=str(e))
            raise
    
    async def close(self):
        """关闭连接"""
        if self.closed:
            return
        
        try:
            if not self.ws.closed:
                await self.ws.close()
            
            if self.session:
                await self.session.close()
            
            self.closed = True
            
        except Exception as e:
            self.logger.warning("关闭WebSocket连接时出错", error=str(e))
    
    def __aiter__(self):
        """异步迭代器"""
        return self
    
    async def __anext__(self):
        """异步迭代下一个消息"""
        if self.closed:
            raise StopAsyncIteration
        
        try:
            if self.connection_type == "aiohttp":
                msg = await self.ws.receive()
                
                if msg.type == aiohttp.WSMsgType.TEXT:
                    return msg.data
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    return msg.data.decode('utf-8')
                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                    self.closed = True
                    raise StopAsyncIteration
                else:
                    # 跳过其他类型的消息，继续获取下一个
                    return await self.__anext__()
            else:  # websockets
                try:
                    message = await self.ws.recv()
                    return message
                except websockets.exceptions.ConnectionClosed:
                    self.closed = True
                    raise StopAsyncIteration
                    
        except Exception as e:
            self.closed = True
            self.logger.error("WebSocket消息接收失败", error=str(e))
            raise StopAsyncIteration


class WebSocketConnectionManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
        self.connections: Dict[str, WebSocketWrapper] = {}
    
    async def connect(self, 
                     config: WebSocketConfig,
                     proxy_config: Optional[ProxyConfig] = None,
                     exchange_config: Optional[Dict[str, Any]] = None) -> Optional[WebSocketWrapper]:
        """
        建立WebSocket连接
        
        基于成功的连接模式：
        1. 优先尝试aiohttp + 代理
        2. SSL配置灵活处理 
        3. 回退到websockets库
        """
        try:
            # 获取代理配置
            if proxy_config is None:
                proxy_config = proxy_manager.get_proxy_config(exchange_config)
            
            # 记录连接尝试
            self.logger.info("尝试建立WebSocket连接",
                           url=config.url,
                           exchange=config.exchange_name,
                           has_proxy=proxy_config.has_proxy(),
                           ssl_verify=not config.should_disable_ssl())
            
            # 如果有代理，优先使用aiohttp
            if proxy_config.has_proxy():
                connection = await self._connect_with_aiohttp_proxy(config, proxy_config)
                if connection:
                    return connection
                
                # aiohttp失败，尝试其他方式
                self.logger.warning("aiohttp代理连接失败，尝试其他方式")
            
            # 直接连接（使用websockets或aiohttp）
            return await self._connect_direct(config)
            
        except Exception as e:
            self.logger.error("WebSocket连接失败", error=str(e), url=config.url)
            return None
    
    async def _connect_with_aiohttp_proxy(self, 
                                        config: WebSocketConfig, 
                                        proxy_config: ProxyConfig) -> Optional[WebSocketWrapper]:
        """使用aiohttp通过代理连接"""
        try:
            proxy_url = proxy_config.to_aiohttp_proxy()
            if not proxy_url:
                return None
            
            # 超时配置
            timeout = aiohttp.ClientTimeout(total=config.timeout)
            
            # SSL配置
            ssl_context = None if config.should_disable_ssl() else config.ssl_context
            
            # 创建会话（兼容不同aiohttp版本）
            try:
                # 新版本aiohttp
                session = aiohttp.ClientSession(timeout=timeout, trust_env=True)
            except TypeError:
                # 旧版本aiohttp不支持trust_env
                session = aiohttp.ClientSession(timeout=timeout)
            
            # 连接参数
            connect_kwargs = {
                'proxy': proxy_url,
                'ssl': ssl_context,
                'timeout': timeout
            }
            
            # 添加可选参数
            if config.extra_headers:
                connect_kwargs['headers'] = config.extra_headers
            
            if config.subprotocols:
                connect_kwargs['protocols'] = config.subprotocols
                
            if config.max_size:
                connect_kwargs['max_msg_size'] = config.max_size
            
            # 建立连接
            ws = await session.ws_connect(config.url, **connect_kwargs)
            
            wrapper = WebSocketWrapper(ws, session, "aiohttp")
            
            # 缓存连接
            connection_key = f"{config.exchange_name or 'unknown'}_{config.url}"
            self.connections[connection_key] = wrapper
            
            self.logger.info("aiohttp代理WebSocket连接成功", 
                           proxy=proxy_url, 
                           ssl_disabled=config.should_disable_ssl())
            
            return wrapper
            
        except Exception as e:
            if 'session' in locals():
                await session.close()
            self.logger.error("aiohttp代理连接失败", error=str(e))
            return None
    
    async def _connect_direct(self, config: WebSocketConfig) -> Optional[WebSocketWrapper]:
        """直接WebSocket连接"""
        try:
            # 优先尝试websockets库（更稳定）
            if not proxy_manager.get_proxy_config().has_proxy():
                return await self._connect_with_websockets(config)
            
            # 有代理环境时使用aiohttp
            return await self._connect_with_aiohttp_direct(config)
            
        except Exception as e:
            self.logger.error("直接WebSocket连接失败", error=str(e))
            return None
    
    async def _connect_with_websockets(self, config: WebSocketConfig) -> Optional[WebSocketWrapper]:
        """使用websockets库连接"""
        try:
            # 连接参数
            connect_kwargs = {
                'ping_interval': config.ping_interval,
                'ping_timeout': config.ping_timeout
            }
            
            # SSL配置
            if config.should_disable_ssl():
                connect_kwargs['ssl'] = None
            elif config.ssl_context:
                connect_kwargs['ssl'] = config.ssl_context
            
            # 添加可选参数
            if config.extra_headers:
                connect_kwargs['extra_headers'] = config.extra_headers
            
            if config.subprotocols:
                connect_kwargs['subprotocols'] = config.subprotocols
                
            if config.max_size:
                connect_kwargs['max_size'] = config.max_size
            
            # 建立连接
            ws = await websockets.connect(config.url, **connect_kwargs)
            
            wrapper = WebSocketWrapper(ws, None, "websockets")
            
            # 缓存连接
            connection_key = f"{config.exchange_name or 'unknown'}_{config.url}"
            self.connections[connection_key] = wrapper
            
            self.logger.info("websockets直接连接成功")
            return wrapper
            
        except Exception as e:
            self.logger.error("websockets连接失败", error=str(e))
            return None
    
    async def _connect_with_aiohttp_direct(self, config: WebSocketConfig) -> Optional[WebSocketWrapper]:
        """使用aiohttp直接连接"""
        try:
            timeout = aiohttp.ClientTimeout(total=config.timeout)
            ssl_context = None if config.should_disable_ssl() else config.ssl_context
            
            # 创建会话
            session = aiohttp.ClientSession(timeout=timeout)
            
            # 连接参数
            connect_kwargs = {
                'ssl': ssl_context,
                'timeout': timeout
            }
            
            if config.extra_headers:
                connect_kwargs['headers'] = config.extra_headers
            
            if config.subprotocols:
                connect_kwargs['protocols'] = config.subprotocols
                
            if config.max_size:
                connect_kwargs['max_msg_size'] = config.max_size
            
            # 建立连接
            ws = await session.ws_connect(config.url, **connect_kwargs)
            
            wrapper = WebSocketWrapper(ws, session, "aiohttp")
            
            # 缓存连接
            connection_key = f"{config.exchange_name or 'unknown'}_{config.url}"
            self.connections[connection_key] = wrapper
            
            self.logger.info("aiohttp直接连接成功")
            return wrapper
            
        except Exception as e:
            if 'session' in locals():
                await session.close()
            self.logger.error("aiohttp直接连接失败", error=str(e))
            return None
    
    async def close_connection(self, connection_key: str):
        """关闭指定连接"""
        if connection_key in self.connections:
            await self.connections[connection_key].close()
            del self.connections[connection_key]
    
    async def close_all_connections(self):
        """关闭所有连接"""
        for connection in self.connections.values():
            await connection.close()
        self.connections.clear()
    
    def get_connection(self, connection_key: str) -> Optional[WebSocketWrapper]:
        """获取连接"""
        return self.connections.get(connection_key)
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接统计"""
        return {
            'total_connections': len(self.connections),
            'active_connections': len([c for c in self.connections.values() if not c.closed]),
            'connections': list(self.connections.keys())
        }


# 全局WebSocket连接管理器实例
websocket_manager = WebSocketConnectionManager()