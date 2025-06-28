"""
优化后的交易所适配器基类

使用统一的网络连接管理器，提供：
- 统一的WebSocket连接管理
- 统一的HTTP会话管理
- 统一的代理配置管理
- 改进的错误处理和重连机制
- 更好的监控和统计
"""

import asyncio
import json
import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Any, Optional, List, Callable
import structlog

# 导入新的网络管理模块
from ....core.networking import (
    NetworkConnectionManager, network_manager,
    WebSocketConfig, SessionConfig, NetworkConfig
)

from ..data_types import (
    NormalizedTrade, NormalizedOrderBook, 
    NormalizedKline, NormalizedTicker,
    ExchangeConfig, DataType
)


class OptimizedExchangeAdapter(ABC):
    """优化后的交易所适配器基类"""
    
    def __init__(self, config: ExchangeConfig):
        self.config = config
        self.logger = structlog.get_logger(__name__).bind(
            exchange=config.exchange.value,
            market_type=config.market_type.value
        )
        
        # 网络连接管理器
        self.network_manager = network_manager
        
        # 连接状态
        self.ws_connection = None
        self.http_session = None
        self.is_connected = False
        self.reconnect_count = 0
        
        # 网络配置
        self.network_config = NetworkConfig(
            timeout=getattr(config, 'timeout', 30),
            enable_proxy=getattr(config, 'enable_proxy', True),
            enable_ssl=getattr(config, 'enable_ssl', True),
            ws_ping_interval=getattr(config, 'ping_interval', 180),
            ws_ping_timeout=getattr(config, 'ping_timeout', 10),
            http_retry_attempts=getattr(config, 'retry_attempts', 3),
            exchange_name=config.exchange.value,
            disable_ssl_for_exchanges=getattr(config, 'disable_ssl_for_exchanges', ['deribit'])
        )
        
        # 连接维护任务
        self.maintenance_tasks = []
        
        # 数据回调
        self.callbacks: Dict[DataType, List[Callable]] = {
            DataType.TRADE: [],
            DataType.ORDERBOOK: [],
            DataType.KLINE: [],
            DataType.TICKER: [],
            DataType.FUNDING_RATE: [],
            DataType.OPEN_INTEREST: [],
            DataType.LIQUIDATION: [],
            DataType.TOP_TRADER_LONG_SHORT_RATIO: [],
            DataType.MARKET_LONG_SHORT_RATIO: []
        }
        
        # 原始数据回调
        self.raw_callbacks: Dict[str, List[Callable]] = {
            'depth': [],
            'trade': [],
            'ticker': []
        }
        
        # 统计信息
        self.stats = {
            'messages_received': 0,
            'messages_processed': 0,
            'errors': 0,
            'last_message_time': None,
            'connected_at': None,
            'reconnect_count': 0,
            'connection_health_score': 100
        }
    
    async def start(self) -> bool:
        """启动交易所适配器"""
        try:
            self.logger.info("启动优化交易所适配器")
            
            # 建立连接
            success = await self.connect()
            if success:
                # 订阅数据流
                await self.subscribe_data_streams()
                
                # 启动连接维护
                await self._start_maintenance_tasks()
                
                # 启动消息处理循环
                asyncio.create_task(self._message_loop())
                
                # 启动网络监控
                await self.network_manager.start_monitoring()
                
                return True
            
            return False
            
        except Exception as e:
            self.logger.error("启动适配器失败", exc_info=True)
            return False
    
    async def stop(self):
        """停止交易所适配器"""
        try:
            self.logger.info("停止优化交易所适配器")
            
            # 停止维护任务
            await self._stop_maintenance_tasks()
            
            # 关闭连接
            if self.ws_connection:
                await self.ws_connection.close()
                self.ws_connection = None
            
            if self.http_session:
                await self.http_session.close()
                self.http_session = None
            
            self.is_connected = False
            
        except Exception as e:
            self.logger.error("停止适配器失败", exc_info=True)
    
    async def connect(self) -> bool:
        """建立网络连接"""
        try:
            self.logger.info("建立网络连接", 
                           ws_url=self.config.ws_url,
                           exchange=self.network_config.exchange_name)
            
            # 建立WebSocket连接
            self.ws_connection = await self.network_manager.create_websocket_connection(
                url=self.config.ws_url,
                exchange_name=self.network_config.exchange_name,
                network_config=self.network_config,
                exchange_config=self._get_exchange_config_dict()
            )
            
            if not self.ws_connection:
                self.logger.error("WebSocket连接建立失败")
                return False
            
            # 建立HTTP会话（用于REST API调用）
            session_name = f"{self.network_config.exchange_name}_rest"
            self.http_session = await self.network_manager.create_http_session(
                session_name=session_name,
                exchange_name=self.network_config.exchange_name,
                network_config=self.network_config,
                exchange_config=self._get_exchange_config_dict()
            )
            
            if not self.http_session:
                self.logger.warning("HTTP会话建立失败，仅WebSocket可用")
            
            # 更新连接状态
            self.is_connected = True
            self.stats['connected_at'] = datetime.now(timezone.utc)
            self.reconnect_count = 0
            
            self.logger.info("网络连接建立成功",
                           websocket=bool(self.ws_connection),
                           http_session=bool(self.http_session))
            
            return True
            
        except Exception as e:
            self.logger.error("建立网络连接失败", exc_info=True)
            return False
    
    def _get_exchange_config_dict(self) -> Dict[str, Any]:
        """获取交易所配置字典"""
        config_dict = {
            'exchange': self.config.exchange.value,
            'market_type': self.config.market_type.value,
            'ws_url': self.config.ws_url
        }
        
        # 添加代理配置（如果存在）
        if hasattr(self.config, 'proxy'):
            config_dict['proxy'] = self.config.proxy
        
        # 添加REST API配置（如果存在）
        if hasattr(self.config, 'rest_api'):
            config_dict['rest_api'] = self.config.rest_api
        
        return config_dict
    
    async def _message_loop(self):
        """消息处理循环"""
        try:
            async for message in self.ws_connection:
                await self._process_message(message)
                
        except StopAsyncIteration:
            self.logger.warning("WebSocket连接已关闭")
            self.is_connected = False
            await self._handle_reconnect("connection_closed")
            
        except Exception as e:
            self.logger.error("消息循环错误", exc_info=True)
            self.is_connected = False
            await self._handle_reconnect("message_loop_error")
    
    async def _process_message(self, message: str):
        """处理接收到的消息"""
        try:
            self.stats['messages_received'] += 1
            self.stats['last_message_time'] = datetime.now(timezone.utc)
            
            # 解析JSON消息
            data = json.loads(message)
            
            # 检查是否为ping/pong消息
            if await self._is_ping_pong_message(data):
                await self._handle_ping_pong_message(data)
                return
            
            # 处理业务消息
            await self.handle_message(data)
            
            self.stats['messages_processed'] += 1
            
        except Exception as e:
            self.logger.error("处理消息失败", exc_info=True, message=message[:200])
            self.stats['errors'] += 1
    
    async def _is_ping_pong_message(self, data: Dict[str, Any]) -> bool:
        """检查是否为ping/pong消息 - 子类可覆盖"""
        return ("ping" in data or "pong" in data or 
                data.get("method") in ["ping", "pong"])
    
    async def _handle_ping_pong_message(self, data: Dict[str, Any]):
        """处理ping/pong消息 - 子类可覆盖"""
        if "ping" in data:
            # 响应ping消息
            pong_message = {"pong": data["ping"]}
            await self.ws_connection.send(json.dumps(pong_message))
            self.logger.debug("响应ping消息", ping_id=data["ping"])
        elif "pong" in data or data.get("method") == "pong":
            # 收到pong响应
            self.logger.debug("收到pong响应", data=data)
    
    async def _handle_reconnect(self, reason: str):
        """处理重连"""
        if self.reconnect_count >= self.config.reconnect_attempts:
            self.logger.error("达到最大重连次数，停止重连",
                            attempts=self.reconnect_count,
                            reason=reason)
            return
        
        self.reconnect_count += 1
        self.stats['reconnect_count'] = self.reconnect_count
        
        self.logger.info("尝试重连",
                        reason=reason,
                        attempt=self.reconnect_count,
                        max_attempts=self.config.reconnect_attempts)
        
        try:
            # 停止维护任务
            await self._stop_maintenance_tasks()
            
            # 关闭当前连接
            if self.ws_connection:
                await self.ws_connection.close()
                self.ws_connection = None
            
            # 等待重连延迟
            await asyncio.sleep(self.config.reconnect_delay)
            
            # 重新连接
            success = await self.connect()
            if success:
                await self.subscribe_data_streams()
                await self._start_maintenance_tasks()
                asyncio.create_task(self._message_loop())
                
                self.logger.info("重连成功")
            
        except Exception as e:
            self.logger.error("重连失败", exc_info=True)
    
    async def _start_maintenance_tasks(self):
        """启动连接维护任务"""
        try:
            # 启动健康检查任务
            health_task = asyncio.create_task(self._health_check_loop())
            self.maintenance_tasks.append(health_task)
            
            # 启动交易所特定的ping任务（如果需要）
            if self.network_config.ws_ping_interval:
                ping_task = asyncio.create_task(self._ping_loop())
                self.maintenance_tasks.append(ping_task)
            
            # 子类可以覆盖此方法添加更多维护任务
            await self._start_exchange_specific_tasks()
            
            self.logger.info("连接维护任务已启动", task_count=len(self.maintenance_tasks))
            
        except Exception as e:
            self.logger.error("启动维护任务失败", exc_info=True)
    
    async def _stop_maintenance_tasks(self):
        """停止维护任务"""
        try:
            for task in self.maintenance_tasks:
                if task and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            
            self.maintenance_tasks.clear()
            self.logger.info("所有维护任务已停止")
            
        except Exception as e:
            self.logger.error("停止维护任务失败", exc_info=True)
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while self.is_connected:
            try:
                await asyncio.sleep(60)  # 每分钟检查一次
                
                # 计算健康分数
                health_score = self._calculate_health_score()
                self.stats['connection_health_score'] = health_score
                
                if health_score < 50:  # 健康分数低于50触发重连
                    self.logger.warning("连接健康分数过低，触发重连", health_score=health_score)
                    await self._handle_reconnect("poor_health")
                    break
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("健康检查失败", exc_info=True)
    
    def _calculate_health_score(self) -> int:
        """计算连接健康分数（0-100）"""
        score = 100
        
        # 检查最近是否有消息
        if self.stats['last_message_time']:
            time_since_last_message = (
                datetime.now(timezone.utc) - self.stats['last_message_time']
            ).total_seconds()
            if time_since_last_message > 300:  # 5分钟无消息
                score -= 30
        
        # 检查错误率
        if self.stats['messages_received'] > 0:
            error_rate = self.stats['errors'] / self.stats['messages_received']
            score -= int(error_rate * 50)
        
        # 检查重连次数
        if self.reconnect_count > 0:
            score -= min(30, self.reconnect_count * 10)
        
        return max(0, min(100, score))
    
    async def _ping_loop(self):
        """Ping循环"""
        while self.is_connected:
            try:
                await asyncio.sleep(self.network_config.ws_ping_interval)
                
                if self.is_connected and self.ws_connection:
                    await self._send_ping()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Ping循环错误", exc_info=True)
    
    async def _send_ping(self):
        """发送ping消息 - 子类应该覆盖此方法"""
        try:
            ping_message = {
                "method": "ping",
                "id": int(asyncio.get_event_loop().time() * 1000)
            }
            
            await self.ws_connection.send(json.dumps(ping_message))
            self.logger.debug("发送ping消息", ping_id=ping_message['id'])
            
        except Exception as e:
            self.logger.error("发送ping失败", exc_info=True)
    
    async def _start_exchange_specific_tasks(self):
        """启动交易所特定的维护任务 - 子类可覆盖"""
        pass
    
    # REST API 便捷方法
    
    async def http_get(self, url: str, **kwargs):
        """HTTP GET请求"""
        if not self.http_session:
            raise Exception("HTTP会话未建立")
        
        try:
            response = await self.http_session.get(url, **kwargs)
            return response
        except Exception as e:
            self.logger.error("HTTP GET请求失败", url=url, exc_info=True)
            raise
    
    async def http_post(self, url: str, **kwargs):
        """HTTP POST请求"""
        if not self.http_session:
            raise Exception("HTTP会话未建立")
        
        try:
            response = await self.http_session.post(url, **kwargs)
            return response
        except Exception as e:
            self.logger.error("HTTP POST请求失败", url=url, exc_info=True)
            raise
    
    # 数据回调管理
    
    def register_callback(self, data_type: DataType, callback: Callable):
        """注册数据回调函数"""
        self.callbacks[data_type].append(callback)
    
    def register_raw_callback(self, data_type: str, callback: Callable):
        """注册原始数据回调函数"""
        if data_type in self.raw_callbacks:
            self.raw_callbacks[data_type].append(callback)
    
    async def _emit_data(self, data_type: DataType, data: Any):
        """发送数据到回调函数"""
        for callback in self.callbacks[data_type]:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                self.logger.error("回调函数执行失败",
                                data_type=data_type.value,
                                exc_info=True)
    
    async def _emit_raw_data(self, data_type: str, exchange: str, symbol: str, raw_data: Dict[str, Any]):
        """发送原始数据到回调函数"""
        for callback in self.raw_callbacks.get(data_type, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(exchange, symbol, raw_data)
                else:
                    callback(exchange, symbol, raw_data)
            except Exception as e:
                self.logger.error("原始数据回调函数执行失败",
                                data_type=data_type,
                                exc_info=True)
    
    # 统计和监控
    
    def get_stats(self) -> Dict[str, Any]:
        """获取适配器统计信息"""
        network_stats = self.network_manager.get_network_stats()
        
        return {
            'adapter': self.stats.copy(),
            'network': network_stats,
            'is_connected': self.is_connected,
            'exchange': self.network_config.exchange_name,
            'connections': {
                'websocket': bool(self.ws_connection and not self.ws_connection.closed),
                'http_session': bool(self.http_session and not self.http_session.closed)
            }
        }
    
    async def test_connectivity(self) -> Dict[str, Any]:
        """测试连接性"""
        return await self.network_manager.test_connectivity(
            url=self.config.ws_url,
            connection_type="websocket",
            exchange_name=self.network_config.exchange_name
        )
    
    # 工具方法
    
    def _safe_decimal(self, value: Any) -> Decimal:
        """安全转换为Decimal"""
        try:
            if value is None or value == '':
                return Decimal('0')
            return Decimal(str(value))
        except:
            return Decimal('0')
    
    def _safe_int(self, value: Any) -> int:
        """安全转换为int"""
        try:
            if value is None or value == '':
                return 0
            return int(float(str(value)))
        except:
            return 0
    
    def _safe_timestamp(self, timestamp: Any) -> datetime:
        """安全转换时间戳"""
        try:
            if isinstance(timestamp, (int, float)):
                # 处理毫秒时间戳
                if timestamp > 1e10:
                    timestamp = timestamp / 1000
                return datetime.fromtimestamp(timestamp)
            else:
                return datetime.now(timezone.utc)
        except:
            return datetime.now(timezone.utc)
    
    # 抽象方法 - 子类必须实现
    
    @abstractmethod
    async def handle_message(self, data: Dict[str, Any]):
        """处理消息数据 - 子类实现具体的消息解析逻辑"""
        pass
    
    @abstractmethod
    async def subscribe_data_streams(self):
        """订阅数据流 - 子类实现具体的订阅逻辑"""
        pass
    
    @abstractmethod
    async def normalize_trade(self, raw_data: Dict[str, Any]) -> Optional[NormalizedTrade]:
        """标准化交易数据"""
        pass
    
    @abstractmethod
    async def normalize_orderbook(self, raw_data: Dict[str, Any]) -> Optional[NormalizedOrderBook]:
        """标准化订单簿数据"""
        pass
    
    @abstractmethod
    async def normalize_kline(self, raw_data: Dict[str, Any]) -> Optional[NormalizedKline]:
        """标准化K线数据"""
        pass
    
    @abstractmethod
    async def normalize_ticker(self, raw_data: Dict[str, Any]) -> Optional[NormalizedTicker]:
        """标准化行情数据"""
        pass