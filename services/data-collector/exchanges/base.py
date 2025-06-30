"""
交易所适配器基类 - 统一增强版

整合了基础功能和增强功能：
- WebSocket连接管理
- 代理支持
- ping/pong维护机制  
- 连接健康监控
- 自动重连机制
- 数据标准化
"""

import asyncio
import json
import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Any, Optional, List, Callable
import structlog
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException
import aiohttp

from ..data_types import (
    NormalizedTrade, NormalizedOrderBook,
    NormalizedKline,
    ExchangeConfig, DataType
)


class WebSocketWrapper:
    """aiohttp WebSocket包装器，兼容websockets接口"""
    
    def __init__(self, ws: aiohttp.ClientWebSocketResponse, session: aiohttp.ClientSession):
        self.ws = ws
        self.session = session
        self.closed = False
    
    async def send(self, data: str):
        """发送消息"""
        if not self.closed:
            await self.ws.send_str(data)
    
    async def close(self):
        """关闭连接"""
        if not self.closed:
            await self.ws.close()
            await self.session.close()
            self.closed = True
    
    def __aiter__(self):
        """异步迭代器"""
        return self
    
    async def __anext__(self):
        """异步迭代下一个消息"""
        if self.closed:
            raise StopAsyncIteration
        
        try:
            msg = await self.ws.receive()
            
            if msg.type == aiohttp.WSMsgType.TEXT:
                return msg.data
            elif msg.type == aiohttp.WSMsgType.BINARY:
                return msg.data.decode('utf-8')
            elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                self.closed = True
                raise StopAsyncIteration
            else:
                # 跳过其他类型的消息
                return await self.__anext__()
                
        except Exception as e:
            self.closed = True
            raise StopAsyncIteration


class ExchangeAdapter(ABC):
    """统一的交易所适配器基类 - 整合基础功能和增强功能"""
    
    def __init__(self, config: ExchangeConfig):
        self.config = config
        self.logger = structlog.get_logger(__name__).bind(
            exchange=config.exchange.value,
            market_type=config.market_type.value if hasattr(config, 'market_type') and config.market_type else 'spot'
        )
        
        # WebSocket连接
        self.ws_connection = None
        self.is_connected = False
        self.reconnect_count = 0
        
        # ping/pong维护配置（整合自base_enhanced）
        self.ping_interval = getattr(config, 'ping_interval', 180)  # 默认3分钟
        self.ping_timeout = getattr(config, 'ping_timeout', 10)     # 默认10秒超时
        self.enable_ping = getattr(config, 'enable_ping', True)     # 是否启用ping
        
        # ping/pong状态
        self.last_ping_time = None
        self.last_pong_time = None
        self.ping_task = None
        self.ping_count = 0
        self.pong_count = 0
        
        # 连接维护任务
        self.maintenance_tasks = []
        
        # 数据回调
        self.callbacks: Dict[DataType, List[Callable]] = {
            DataType.TRADE: [],
            DataType.ORDERBOOK: [],
            DataType.KLINE: [],

            DataType.FUNDING_RATE: [],
            DataType.OPEN_INTEREST: [],
            DataType.LIQUIDATION: [],
            DataType.TOP_TRADER_LONG_SHORT_RATIO: [],
            DataType.MARKET_LONG_SHORT_RATIO: []
        }
        
        # 原始数据回调（用于OrderBook Manager）
        self.raw_callbacks: Dict[str, List[Callable]] = {
            'depth': [],  # 深度数据原始回调
            'trade': [],  # 交易数据原始回调

        }
        
        # 统计信息（整合基础和增强统计）
        self.stats = {
            'messages_received': 0,
            'messages_processed': 0,
            'errors': 0,
            'last_message_time': None,
            'connected_at': None
        }
        
        # 增强统计
        self.enhanced_stats = {
            'ping_count': 0,
            'pong_count': 0,
            'ping_timeouts': 0,
            'reconnect_triggers': 0,
            'connection_health_score': 100  # 0-100分
        }
    
    async def start(self) -> bool:
        """启动统一的交易所连接"""
        try:
            self.logger.info("启动统一交易所适配器")
            
            # 建立WebSocket连接（不使用自动ping）
            success = await self.connect()
            if success:
                # 订阅数据流
                await self.subscribe_data_streams()
                
                # 启动连接维护任务
                await self._start_maintenance_tasks()
                
                # 启动消息处理循环
                asyncio.create_task(self._enhanced_message_loop())
                
                return True
            
            return False
            
        except Exception as e:
            self.logger.error("启动适配器失败", exc_info=True)
            return False
    
    async def stop(self):
        """停止统一的交易所连接"""
        try:
            self.logger.info("停止统一交易所适配器")
            
            # 停止维护任务
            await self._stop_maintenance_tasks()
            
            if self.ws_connection:
                await self.ws_connection.close()
                self.ws_connection = None
            
            self.is_connected = False
            
        except Exception as e:
            self.logger.error("停止适配器失败", exc_info=True)
    
    async def connect(self) -> bool:
        """建立WebSocket连接（禁用自动ping）"""
        try:
            self.logger.info("连接WebSocket", url=self.config.ws_url)
            
            # 获取代理设置 - TDD优化：优先使用配置中的代理，然后是环境变量
            proxy_config = self._get_effective_proxy_config()
            
            if proxy_config and proxy_config.get('enabled', True):
                return await self._connect_with_proxy(proxy_config)
            else:
                return await self._connect_direct()
                
        except Exception as e:
            self.logger.error("WebSocket连接失败", exc_info=True)
            return False
    
    def _get_effective_proxy_config(self) -> Optional[Dict[str, Any]]:
        """获取有效的代理配置 - TDD优化：配置优先，环境变量备选"""
        # 1. 优先使用ExchangeConfig中的代理配置
        if hasattr(self.config, 'proxy') and self.config.proxy:
            if self.config.proxy.get('enabled', True):
                self.logger.info("使用配置文件中的代理设置")
                return self.config.proxy
            else:
                self.logger.info("代理在配置中被明确禁用")
                return None
        
        # 2. 回退到环境变量（向后兼容）
        env_proxy = self._get_env_proxy_config()
        if env_proxy:
            self.logger.info("使用环境变量中的代理设置")
            return env_proxy
        
        # 3. 检查是否有REST API的代理配置（来自collector配置）
        rest_proxy = self._get_rest_proxy_config()
        if rest_proxy:
            self.logger.info("使用REST API代理配置用于WebSocket")
            return rest_proxy
            
        return None
    
    def _get_env_proxy_config(self) -> Optional[Dict[str, Any]]:
        """从环境变量获取代理配置 - 向后兼容"""
        http_proxy = os.getenv('http_proxy') or os.getenv('HTTP_PROXY')
        https_proxy = os.getenv('https_proxy') or os.getenv('HTTPS_PROXY')
        all_proxy = os.getenv('ALL_PROXY') or os.getenv('all_proxy')
        
        if all_proxy:
            if 'socks' in all_proxy.lower():
                return {'enabled': True, 'socks5': all_proxy}
            else:
                return {'enabled': True, 'http': all_proxy}
        elif https_proxy or http_proxy:
            return {
                'enabled': True,
                'http': http_proxy,
                'https': https_proxy or http_proxy
            }
        
        return None
    
    def _get_rest_proxy_config(self) -> Optional[Dict[str, Any]]:
        """从REST API代理配置获取WebSocket代理设置"""
        if hasattr(self.config, 'rest_api') and self.config.rest_api:
            rest_api = self.config.rest_api
            http_proxy = rest_api.get('http_proxy')
            https_proxy = rest_api.get('https_proxy')
            
            if https_proxy or http_proxy:
                return {
                    'enabled': True,
                    'http': http_proxy,
                    'https': https_proxy or http_proxy
                }
        
        return None
    
    async def _connect_with_proxy(self, proxy_config: Dict[str, Any]) -> bool:
        """通过代理建立连接 - TDD优化：支持多种代理类型"""
        # SOCKS代理优先
        if 'socks5' in proxy_config or 'socks4' in proxy_config:
            socks_url = proxy_config.get('socks5') or proxy_config.get('socks4')
            return await self._connect_socks_proxy(socks_url)
        
        # HTTP/HTTPS代理
        elif 'http' in proxy_config or 'https' in proxy_config:
            proxy_url = proxy_config.get('https') or proxy_config.get('http')
            return await self._connect_http_proxy(proxy_url)
        
        # 未知代理类型，回退到直连
        else:
            self.logger.warning("未知的代理配置，回退到直连", config=proxy_config)
            return await self._connect_direct()
    
    async def _connect_socks_proxy(self, socks_url: str) -> bool:
        """通过SOCKS代理连接"""
        self.logger.info("使用SOCKS代理连接WebSocket", proxy=socks_url)
        
        try:
            import aiohttp_socks
            
            # 创建SOCKS代理连接器
            connector = aiohttp_socks.ProxyConnector.from_url(socks_url)
            session = aiohttp.ClientSession(connector=connector)
            
            # 通过SOCKS代理建立WebSocket连接
            ws = await session.ws_connect(
                self.config.ws_url,
                timeout=aiohttp.ClientTimeout(total=20)
            )
            
            # 包装aiohttp WebSocket为兼容接口
            self.ws_connection = WebSocketWrapper(ws, session)
            return True
            
        except ImportError:
            self.logger.warning("aiohttp_socks库未安装，无法使用SOCKS代理")
            return False
        except Exception as e:
            if 'session' in locals():
                await session.close()
            raise e
    
    async def _connect_http_proxy(self, proxy_url: str) -> bool:
        """通过HTTP代理连接"""
        self.logger.info("使用HTTP代理连接WebSocket", proxy=proxy_url)
        
        try:
            import aiohttp
            
            # 创建代理连接器（兼容旧版本aiohttp）
            try:
                # 新版本aiohttp支持trust_env
                connector = aiohttp.TCPConnector(trust_env=True)
                session = aiohttp.ClientSession(connector=connector, trust_env=True)
            except TypeError:
                # 旧版本aiohttp不支持trust_env，使用默认设置
                connector = aiohttp.TCPConnector()
                session = aiohttp.ClientSession(connector=connector)
            
            # 通过HTTP代理建立WebSocket连接
            ws = await session.ws_connect(
                self.config.ws_url,
                proxy=proxy_url,
                timeout=aiohttp.ClientTimeout(total=20)
            )
            
            self.ws_connection = WebSocketWrapper(ws, session)
            self.is_connected = True
            self.stats['connected_at'] = datetime.now(timezone.utc)
            self.reconnect_count = 0
            self.logger.info("WebSocket代理连接成功")
            return True
            
        except Exception as e:
            if 'session' in locals():
                await session.close()
            raise e
    
    async def _connect_direct(self) -> bool:
        """直接WebSocket连接（禁用自动ping）"""
        try:
            import websockets
            
            # 禁用自动ping，手动实现交易所特定的ping
            self.ws_connection = await websockets.connect(
                self.config.ws_url,
                ping_interval=None,  # 禁用自动ping
                ping_timeout=None    # 禁用ping超时
            )
            
            self.is_connected = True
            self.stats['connected_at'] = datetime.now(timezone.utc)
            self.reconnect_count = 0  # 重置重连计数
            
            self.logger.info("WebSocket连接成功")
            return True
            
        except Exception as e:
            self.logger.error("直接WebSocket连接失败", exc_info=True)
            return False
    
    async def _message_loop(self):
        """消息处理循环"""
        try:
            async for message in self.ws_connection:
                await self._process_message(message)
                
        except (ConnectionClosed, StopAsyncIteration):
            self.logger.warning("WebSocket连接已关闭")
            self.is_connected = False
            await self._handle_reconnect()
            
        except (WebSocketException, aiohttp.ClientError) as e:
            self.logger.error("WebSocket错误", exc_info=True)
            self.is_connected = False
            await self._handle_reconnect()
            
        except Exception as e:
            self.logger.error("消息循环错误", exc_info=True)
            self.stats['errors'] += 1
    
    async def _process_message(self, message: str):
        """处理接收到的消息"""
        try:
            self.stats['messages_received'] += 1
            self.stats['last_message_time'] = datetime.now(timezone.utc)
            
            # 添加调试日志
            if self.stats['messages_received'] % 100 == 1:  # 每100条消息记录一次
                self.logger.debug("WebSocket消息接收", 
                                count=self.stats['messages_received'],
                                message_preview=message[:100])
            
            # 解析JSON消息
            data = json.loads(message)
            
            # 处理不同类型的数据
            await self.handle_message(data)
            
            self.stats['messages_processed'] += 1
            
        except Exception as e:
            self.logger.error("处理消息失败", exc_info=True, message=message[:200])
            self.stats['errors'] += 1
    
    async def _handle_reconnect(self):
        """处理重连"""
        if self.reconnect_count >= self.config.reconnect_attempts:
            self.logger.error("达到最大重连次数，停止重连")
            return
        
        self.reconnect_count += 1
        self.logger.info(
            "尝试重连", 
            attempt=self.reconnect_count,
            max_attempts=self.config.reconnect_attempts
        )
        
        # 等待重连延迟
        await asyncio.sleep(self.config.reconnect_delay)
        
        # 尝试重连
        success = await self.connect()
        if success:
            await self.subscribe_data_streams()
    
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
                self.logger.error(
                    "回调函数执行失败",
                    data_type=data_type.value,
                    exc_info=True
                )
    
    async def _emit_raw_data(self, data_type: str, exchange: str, symbol: str, raw_data: Dict[str, Any]):
        """发送原始数据到回调函数"""
        for callback in self.raw_callbacks.get(data_type, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(exchange, symbol, raw_data)
                else:
                    callback(exchange, symbol, raw_data)
            except Exception as e:
                self.logger.error(
                    "原始数据回调函数执行失败",
                    data_type=data_type,
                    exc_info=True
                )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取基础统计信息"""
        return {
            **self.stats,
            'is_connected': self.is_connected,
            'reconnect_count': self.reconnect_count,
            'ping_interval': self.ping_interval,
            'enable_ping': self.enable_ping
        }
    
    def get_enhanced_stats(self) -> Dict[str, Any]:
        """获取增强统计信息"""
        base_stats = self.get_stats()
        
        return {
            **base_stats,
            'enhanced': {
                **self.enhanced_stats,
                'ping_interval': self.ping_interval,
                'ping_timeout': self.ping_timeout,
                'last_ping_time': self.last_ping_time.isoformat() if self.last_ping_time else None,
                'last_pong_time': self.last_pong_time.isoformat() if self.last_pong_time else None,
                'maintenance_tasks_count': len(self.maintenance_tasks)
            }
        }
    
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
    
    async def _start_maintenance_tasks(self):
        """启动连接维护任务"""
        try:
            # 启动ping任务
            if self.enable_ping:
                self.ping_task = asyncio.create_task(self._ping_maintenance_loop())
                self.maintenance_tasks.append(self.ping_task)
                self.logger.info("Ping维护任务已启动", interval=self.ping_interval)
            
            # 启动健康检查任务
            health_task = asyncio.create_task(self._health_check_loop())
            self.maintenance_tasks.append(health_task)
            
            # 子类可以覆盖此方法添加更多维护任务
            await self._start_exchange_specific_tasks()
            
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
    
    async def _ping_maintenance_loop(self):
        """Ping维护循环 - 子类可覆盖实现交易所特定逻辑"""
        while self.is_connected:
            try:
                await asyncio.sleep(self.ping_interval)
                
                if self.is_connected and self.ws_connection:
                    await self._send_exchange_ping()
                
            except asyncio.CancelledError:
                self.logger.info("Ping维护循环被取消")
                break
            except Exception as e:
                self.logger.error("Ping维护循环错误", exc_info=True)
                await asyncio.sleep(30)  # 错误后等待30秒再重试
    
    async def _send_exchange_ping(self):
        """发送交易所特定的ping - 子类应该覆盖此方法"""
        try:
            # 默认实现：发送通用ping消息
            ping_message = {"method": "ping", "id": int(asyncio.get_event_loop().time() * 1000)}
            
            await self.ws_connection.send(json.dumps(ping_message))
            self.last_ping_time = datetime.now(timezone.utc)
            self.ping_count += 1
            self.enhanced_stats['ping_count'] += 1
            
            self.logger.debug("发送ping消息", ping_id=ping_message['id'])
            
            # 启动pong超时检查
            asyncio.create_task(self._check_pong_timeout())
            
        except Exception as e:
            self.logger.error("发送ping失败", exc_info=True)
            self.enhanced_stats['ping_timeouts'] += 1
            await self._trigger_reconnect("ping_send_failed")
    
    async def _check_pong_timeout(self):
        """检查pong超时"""
        try:
            await asyncio.sleep(self.ping_timeout)
            
            # 检查是否收到pong响应
            if (self.last_ping_time and self.last_pong_time and 
                self.last_ping_time > self.last_pong_time):
                
                self.logger.warning("Ping响应超时", 
                                  timeout=self.ping_timeout,
                                  last_ping=self.last_ping_time,
                                  last_pong=self.last_pong_time)
                
                self.enhanced_stats['ping_timeouts'] += 1
                await self._trigger_reconnect("pong_timeout")
                
        except Exception as e:
            self.logger.error("Pong超时检查失败", exc_info=True)
    
    async def _health_check_loop(self):
        """连接健康检查循环"""
        while self.is_connected:
            try:
                await asyncio.sleep(60)  # 每分钟检查一次
                
                # 计算健康分数
                health_score = self._calculate_health_score()
                self.enhanced_stats['connection_health_score'] = health_score
                
                if health_score < 50:  # 健康分数低于50触发重连
                    self.logger.warning("连接健康分数过低，触发重连", health_score=health_score)
                    await self._trigger_reconnect("poor_health")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("健康检查失败", exc_info=True)
    
    def _calculate_health_score(self) -> int:
        """计算连接健康分数（0-100）"""
        score = 100
        
        # ping/pong成功率
        if self.ping_count > 0:
            pong_success_rate = self.pong_count / self.ping_count
            score = int(score * pong_success_rate)
        
        # 最近是否有消息
        if self.stats['last_message_time']:
            time_since_last_message = (datetime.now(timezone.utc) - self.stats['last_message_time']).total_seconds()
            if time_since_last_message > 300:  # 5分钟无消息
                score -= 30
        
        # 错误率
        if self.stats['messages_received'] > 0:
            error_rate = self.stats['errors'] / self.stats['messages_received']
            score -= int(error_rate * 50)
        
        return max(0, min(100, score))
    
    async def _enhanced_message_loop(self):
        """增强版消息处理循环"""
        try:
            async for message in self.ws_connection:
                await self._process_enhanced_message(message)
                
        except (ConnectionClosed, StopAsyncIteration):
            self.logger.warning("WebSocket连接已关闭")
            self.is_connected = False
            await self._trigger_reconnect("connection_closed")
            
        except (WebSocketException, aiohttp.ClientError) as e:
            self.logger.error("WebSocket错误", exc_info=True)
            self.is_connected = False
            await self._trigger_reconnect("websocket_error")
            
        except Exception as e:
            self.logger.error("消息循环错误", exc_info=True)
            self.stats['errors'] += 1
    
    async def _process_enhanced_message(self, message: str):
        """处理增强消息"""
        try:
            # 更新统计
            self.stats['messages_received'] += 1
            self.stats['last_message_time'] = datetime.now(timezone.utc)
            
            # 解析消息
            data = json.loads(message)
            
            # 检查是否为pong响应
            if await self._is_pong_message(data):
                await self._handle_pong_response(data)
                return
            
            # 处理其他消息类型
            await self.handle_message(data)
            self.stats['messages_processed'] += 1
            
        except Exception as e:
            self.logger.error("处理消息失败", exc_info=True, message=message[:200])
            self.stats['errors'] += 1
    
    async def _is_pong_message(self, data: Dict[str, Any]) -> bool:
        """检查是否为pong消息 - 子类可覆盖"""
        # 默认检查：包含pong字段
        return "pong" in data or data.get("method") == "pong"
    
    async def _handle_pong_response(self, data: Dict[str, Any]):
        """处理pong响应 - 子类可覆盖"""
        self.last_pong_time = datetime.now(timezone.utc)
        self.pong_count += 1
        self.enhanced_stats['pong_count'] += 1
        
        self.logger.debug("收到pong响应", data=data)
    
    async def _trigger_reconnect(self, reason: str):
        """触发重连"""
        self.enhanced_stats['reconnect_triggers'] += 1
        
        if self.reconnect_count >= self.config.reconnect_attempts:
            self.logger.error("达到最大重连次数，停止重连", 
                            attempts=self.reconnect_count,
                            reason=reason)
            return
        
        self.logger.info("触发重连", reason=reason, attempt=self.reconnect_count + 1)
        
        try:
            # 停止维护任务
            await self._stop_maintenance_tasks()
            
            # 关闭当前连接
            if self.ws_connection:
                await self.ws_connection.close()
                self.ws_connection = None
            
            self.is_connected = False
            
            # 等待重连延迟
            await asyncio.sleep(self.config.reconnect_delay)
            
            # 重新连接
            success = await self.connect()
            if success:
                await self.subscribe_data_streams()
                await self._start_maintenance_tasks()
                asyncio.create_task(self._enhanced_message_loop())
                
                self.logger.info("重连成功")
            else:
                self.reconnect_count += 1
                
        except Exception as e:
            self.logger.error("重连失败", exc_info=True)
            self.reconnect_count += 1
    
    async def _start_exchange_specific_tasks(self):
        """启动交易所特定的维护任务 - 子类可覆盖"""
        pass


# MockExchangeAdapter已移除 - 使用真实的交易所适配器进行测试
# 如需测试数据，请使用真实的交易所API或测试环境