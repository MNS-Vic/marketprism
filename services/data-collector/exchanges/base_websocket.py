"""
WebSocket客户端基础接口
定义所有交易所WebSocket客户端的统一接口
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable, List
import asyncio


class BaseWebSocketClient(ABC):
    """
    WebSocket客户端基础接口
    
    所有交易所的WebSocket客户端都应该实现这个接口，
    确保统一的调用方式和行为。
    """
    
    def __init__(self,
                 symbols: List[str],
                 on_orderbook_update: Optional[Callable[[str, Dict[str, Any]], None]] = None,
                 market_type: str = 'spot',
                 websocket_depth: int = 400):
        """
        初始化WebSocket客户端
        
        Args:
            symbols: 交易对列表
            on_orderbook_update: 订单簿更新回调函数 (symbol, data)
            market_type: 市场类型 ('spot', 'perpetual')
            websocket_depth: WebSocket深度
        """
        self.symbols = symbols
        self.on_orderbook_update = on_orderbook_update
        self.market_type = market_type
        self.websocket_depth = websocket_depth
        
        # 连接状态
        self.is_connected = False
        self.is_running = False
        
        # 统计信息
        self.message_count = 0
        self.error_count = 0
        self.reconnect_count = 0
    
    @abstractmethod
    async def start(self) -> bool:
        """
        启动WebSocket客户端
        
        Returns:
            启动是否成功
        """
        pass
    
    @abstractmethod
    async def stop(self):
        """停止WebSocket客户端"""
        pass
    
    @abstractmethod
    async def connect(self) -> bool:
        """
        建立WebSocket连接
        
        Returns:
            连接是否成功
        """
        pass
    
    @abstractmethod
    async def disconnect(self):
        """断开WebSocket连接"""
        pass
    
    @abstractmethod
    async def subscribe_orderbook(self, symbols: List[str] = None) -> bool:
        """
        订阅订单簿数据
        
        Args:
            symbols: 要订阅的交易对列表，None表示使用初始化时的symbols
            
        Returns:
            订阅是否成功
        """
        pass
    
    @abstractmethod
    async def unsubscribe_orderbook(self, symbols: List[str] = None) -> bool:
        """
        取消订阅订单簿数据
        
        Args:
            symbols: 要取消订阅的交易对列表，None表示使用初始化时的symbols
            
        Returns:
            取消订阅是否成功
        """
        pass
    
    @abstractmethod
    def get_connection_status(self) -> Dict[str, Any]:
        """
        获取连接状态信息
        
        Returns:
            包含连接状态的字典
        """
        pass
    
    @abstractmethod
    async def send_message(self, message: Dict[str, Any]) -> bool:
        """
        发送消息到WebSocket
        
        Args:
            message: 要发送的消息
            
        Returns:
            发送是否成功
        """
        pass
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            包含统计信息的字典
        """
        return {
            'message_count': self.message_count,
            'error_count': self.error_count,
            'reconnect_count': self.reconnect_count,
            'is_connected': self.is_connected,
            'is_running': self.is_running,
            'symbols': self.symbols,
            'market_type': self.market_type,
            'websocket_depth': self.websocket_depth
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查
        
        Returns:
            健康状态信息
        """
        status = self.get_connection_status()
        stats = self.get_stats()
        
        return {
            'healthy': self.is_connected and self.is_running,
            'status': status,
            'stats': stats,
            'error_rate': self.error_count / max(self.message_count, 1)
        }


class WebSocketClientFactory:
    """WebSocket客户端工厂类"""
    
    @staticmethod
    def create_client(exchange: str, **kwargs) -> BaseWebSocketClient:
        """
        创建指定交易所的WebSocket客户端
        
        Args:
            exchange: 交易所名称 ('binance', 'okx')
            **kwargs: 传递给客户端构造函数的参数
            
        Returns:
            WebSocket客户端实例
        """
        if exchange.lower() == 'binance':
            from .binance_websocket import BinanceWebSocketClient
            return BinanceWebSocketClient(**kwargs)
        elif exchange.lower() == 'okx':
            from .okx_websocket import OKXWebSocketManager
            return OKXWebSocketManager(**kwargs)
        else:
            raise ValueError(f"不支持的交易所: {exchange}")
