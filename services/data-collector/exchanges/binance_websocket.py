"""
Binance WebSocket客户端
基于统一WebSocket管理器的Binance特定实现
符合orderbook_manager期望的接口
参考OKX成功经验进行优化，实现统一的WebSocket接口
"""

import asyncio
import json
import ssl
import time
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime, timezone
# 🔧 迁移到统一日志系统
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from core.observability.logging import (
    get_managed_logger,
    ComponentType
)

# 使用简化的WebSocket实现，避免复杂的依赖问题
import websockets

# 🔧 标准化导入路径 - 支持动态导入
import sys
from pathlib import Path

# 添加exchanges目录到Python路径以支持动态导入
exchanges_dir = Path(__file__).parent
if str(exchanges_dir) not in sys.path:
    sys.path.insert(0, str(exchanges_dir))

from base_websocket import BaseWebSocketClient


class BinanceWebSocketClient(BaseWebSocketClient):
    """
    Binance WebSocket客户端
    基于统一WebSocket管理器，符合orderbook_manager期望的接口
    """
    
    def __init__(self,
                 symbols: List[str],
                 on_orderbook_update: Callable[[str, Dict[str, Any]], None] = None,
                 ws_base_url: str = None,
                 market_type: str = 'spot',
                 websocket_depth: int = 1000,
                 config: Optional[Dict[str, Any]] = None):
        """
        初始化Binance WebSocket客户端

        Args:
            symbols: 交易对列表
            on_orderbook_update: 订单簿更新回调函数 (symbol, data)
            ws_base_url: WebSocket基础URL（已弃用，使用config）
            market_type: 市场类型 ('spot', 'perpetual')
            websocket_depth: WebSocket深度（Binance支持更高深度）
            config: 统一配置字典
        """
        # 调用父类构造函数
        super().__init__(symbols, on_orderbook_update, market_type, websocket_depth)

        # 🔧 配置统一：从统一配置获取WebSocket URL
        self.config = config or {}
        exchanges_config = self.config.get('exchanges', {})

        # 根据市场类型选择正确的配置
        if market_type == 'perpetual':
            binance_config = exchanges_config.get('binance_derivatives', {})
            # 🔧 合理的默认值：作为配置缺失时的回退机制
            default_url = "wss://fstream.binance.com/ws"  # Binance官方衍生品WebSocket URL
        else:
            binance_config = exchanges_config.get('binance_spot', {})
            # 🔧 合理的默认值：作为配置缺失时的回退机制
            default_url = "wss://stream.binance.com:9443/ws"  # Binance官方现货WebSocket URL

        # 优先使用统一配置，然后是传入参数，最后是默认值
        if ws_base_url:
            self.ws_base_url = ws_base_url
        else:
            self.ws_base_url = binance_config.get('api', {}).get('ws_url', default_url)
        # 🔧 迁移到统一日志系统
        self.logger = get_managed_logger(
            ComponentType.WEBSOCKET,
            exchange="binance",
            market_type=market_type
        )

        # WebSocket连接状态
        self.websocket = None
        self.listen_task = None

        # 统计信息（参考OKX的统计管理）
        self.last_message_time = None
        self.connection_start_time = None

        # 🔧 Binance特定的心跳机制 - 符合官方文档要求
        self.heartbeat_task = None
        self.heartbeat_interval = 20 if market_type == 'spot' else 180  # 现货20秒，期货3分钟
        self.ping_timeout = 10  # ping超时时间
        self.heartbeat_check_interval = 5  # 每5秒检查一次心跳状态
        self.last_ping_time = None
        self.last_pong_time = None
        self.waiting_for_pong = False
        self.total_pings_sent = 0
        self.total_pongs_received = 0
        self.heartbeat_failures = 0
        self.consecutive_ping_failures = 0
        self.max_consecutive_failures = 3  # 连续失败3次触发重连

        # 重连配置 - 与OKX保持一致
        self.max_reconnect_attempts = -1  # 无限重连
        self.reconnect_delay = 1.0  # 初始重连延迟1秒
        self.max_reconnect_delay = 30.0  # 最大重连延迟30秒
        self.backoff_multiplier = 2.0  # 指数退避倍数
        self.current_reconnect_attempts = 0
        self.connection_timeout = 30.0  # 连接超时增加到30秒
        self.reconnect_count = 0

        # 🔧 配置统一：使用统一配置的WebSocket URL
        self.ws_url = self.ws_base_url
    
    # 移除复杂的配置创建方法
    
    async def start(self):
        """启动WebSocket连接管理器"""
        self.logger.info("🚀 启动Binance WebSocket客户端")
        self.is_running = True
        await self._connection_manager()

    async def _connection_manager(self):
        """
        连接管理器 - 处理连接和重连

        根据Binance官方文档：
        - 实现指数退避重连策略
        - 连接失败时自动重连
        - 维护连接健康状态
        """
        while self.is_running:
            try:
                success = await self.connect()
                if not success:
                    await self._handle_reconnection("连接失败")
                    continue

            except websockets.exceptions.ConnectionClosed as e:
                self.logger.warning(f"🔗 Binance WebSocket连接关闭: {e}")
                await self._handle_reconnection("连接关闭")

            except websockets.exceptions.InvalidURI as e:
                self.logger.error(f"❌ Binance WebSocket URI无效: {e}")
                break  # URI错误不重连

            except asyncio.TimeoutError:
                self.logger.warning("⏰ Binance WebSocket连接超时")
                await self._handle_reconnection("连接超时")

            except Exception as e:
                self.logger.error(f"❌ Binance WebSocket连接异常: {e}", exc_info=True)
                await self._handle_reconnection(f"连接异常: {str(e)}")

                if not self.is_running:
                    break

    async def _handle_reconnection(self, reason: str):
        """
        处理重连逻辑

        Args:
            reason: 重连原因
        """
        if not self.is_running:
            return

        # 计算重连延迟（指数退避）
        delay = min(
            self.reconnect_delay * (self.backoff_multiplier ** self.current_reconnect_attempts),
            self.max_reconnect_delay
        )

        self.current_reconnect_attempts += 1
        self.reconnect_count += 1

        self.logger.warning(f"🔄 Binance WebSocket将在{delay:.1f}秒后重连",
                          reason=reason,
                          attempt=self.current_reconnect_attempts,
                          total_reconnects=self.reconnect_count)

        await asyncio.sleep(delay)

    async def stop(self):
        """停止WebSocket客户端"""
        self.logger.info("🛑 停止Binance WebSocket客户端")
        self.is_running = False

        # 🔧 停止心跳任务
        if self.heartbeat_task and not self.heartbeat_task.done():
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass

        if self.listen_task and not self.listen_task.done():
            self.listen_task.cancel()
            try:
                await self.listen_task
            except asyncio.CancelledError:
                pass

        await self.disconnect()
    
    async def connect(self):
        """
        连接到Binance WebSocket - 优化版本

        根据Binance官方文档：
        - 使用连接超时防止长时间等待
        - 连接成功后立即订阅数据
        - 启动心跳和消息监听
        """
        try:
            # 🔧 迁移到统一日志系统 - 标准化连接日志
            self.logger.connection_success(
                "Connecting to Binance WebSocket",
                market_type=self.market_type,
                symbols=self.symbols,
                url=self.ws_url
            )

            # 创建SSL上下文
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            # 建立WebSocket连接（带超时）
            self.websocket = await asyncio.wait_for(
                websockets.connect(
                    self.ws_url,
                    ssl=ssl_context,
                    ping_interval=None,    # 禁用客户端PING，让服务器控制
                    ping_timeout=None,     # 禁用客户端PING超时
                    close_timeout=10,
                    max_size=2**20,       # 1MB缓冲区
                    compression=None      # Binance不支持压缩
                ),
                timeout=self.connection_timeout
            )
            self.is_connected = True
            self.is_running = True
            self.connection_start_time = datetime.now(timezone.utc)
            self.last_message_time = time.time()
            # 🔧 迁移到统一日志系统 - 连接成功日志会被自动去重
            self.logger.connection_success("Binance WebSocket connection established")

            # 重置重连计数
            if self.current_reconnect_attempts > 0:
                # 🔧 迁移到统一日志系统 - 重连成功日志
                self.logger.connection_success(
                    "Binance WebSocket reconnection successful, resetting retry count",
                    reconnect_attempts=self.current_reconnect_attempts
                )
                self.current_reconnect_attempts = 0

            # 订阅订单簿数据
            await self.subscribe_orderbook()

            # 启动心跳监控任务（被动响应模式）
            self.heartbeat_task = asyncio.create_task(self._heartbeat_monitor())

            # 启动消息监听
            self.listen_task = asyncio.create_task(self._listen_messages())

            # 等待任务完成（通常是连接断开）
            done, pending = await asyncio.wait(
                [self.heartbeat_task, self.listen_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            # 取消未完成的任务
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            return True

        except asyncio.TimeoutError:
            self.logger.error(f"❌ Binance WebSocket连接超时 ({self.connection_timeout}s)",
                            url=self.ws_url,
                            market_type=self.market_type,
                            symbols=self.symbols)
            return False

        except Exception as e:
            self.logger.error(f"❌ Binance WebSocket连接失败: {e}",
                            url=self.ws_url,
                            market_type=self.market_type,
                            symbols=self.symbols,
                            error_type=type(e).__name__)
            return False

        finally:
            # 清理连接
            self.is_connected = False
            if hasattr(self, 'websocket') and self.websocket and not self.websocket.closed:
                try:
                    await self.websocket.close()
                except Exception as e:
                    self.logger.debug(f"关闭WebSocket连接时出错: {e}")

            # 清理任务
            for task_name in ['heartbeat_task', 'listen_task']:
                if hasattr(self, task_name):
                    task = getattr(self, task_name)
                    if task and not task.done():
                        task.cancel()

    async def _heartbeat_monitor(self):
        """
        心跳监控 - Binance被动响应模式

        根据Binance官方文档：
        - 服务器主动发送PING，客户端被动响应PONG
        - 现货：服务器每20秒发送PING
        - 衍生品：服务器每3分钟发送PING
        - 客户端只需要监控是否收到服务器的PING
        """
        self.logger.info("💓 启动Binance心跳监控（被动响应模式）",
                       server_ping_interval=f"{self.heartbeat_interval}秒",
                       market_type=self.market_type)

        try:
            while self.is_connected and self.is_running:
                try:
                    current_time = time.time()

                    # 检查是否长时间没有收到消息（包括PING）
                    if self.last_message_time:
                        time_since_last_message = current_time - self.last_message_time

                        # 如果超过心跳间隔的2倍时间没有收到任何消息，可能连接有问题
                        timeout_threshold = self.heartbeat_interval * 2

                        if time_since_last_message > timeout_threshold:
                            self.heartbeat_failures += 1
                            self.consecutive_ping_failures += 1

                            self.logger.warning("💔 Binance心跳超时",
                                              time_since_last_message=f"{time_since_last_message:.1f}s",
                                              timeout_threshold=f"{timeout_threshold}s",
                                              consecutive_failures=self.consecutive_ping_failures,
                                              total_failures=self.heartbeat_failures)

                            # 连续失败超过阈值时触发重连
                            if self.consecutive_ping_failures >= self.max_consecutive_failures:
                                self.logger.error(f"💔 连续{self.consecutive_ping_failures}次心跳失败，触发重连")
                                raise Exception(f"连续{self.consecutive_ping_failures}次心跳失败")

                    # 使用配置的检查间隔
                    await asyncio.sleep(self.heartbeat_check_interval)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self.logger.error(f"❌ Binance心跳监控异常: {e}")
                    break

        except asyncio.CancelledError:
            self.logger.info("💓 Binance心跳监控被取消")
        except Exception as e:
            self.logger.error(f"❌ Binance心跳监控失败: {e}")
        finally:
            self.logger.info("💓 Binance心跳监控已停止")

    async def _trigger_reconnect(self, reason: str):
        """触发重连"""
        self.logger.warning("🔄 触发Binance WebSocket重连", reason=reason)
        self.is_connected = False

        # 这里可以添加重连逻辑，或者让上层管理器处理重连
        # 目前先记录日志，让连接自然断开，由上层重连机制处理

    def get_heartbeat_stats(self) -> dict:
        """获取心跳统计信息"""
        return {
            'market_type': self.market_type,
            'heartbeat_interval': self.heartbeat_interval,
            'ping_timeout': self.ping_timeout,
            'total_pings_sent': self.total_pings_sent,
            'total_pongs_received': self.total_pongs_received,
            'heartbeat_failures': self.heartbeat_failures,
            'consecutive_ping_failures': self.consecutive_ping_failures,
            'max_consecutive_failures': self.max_consecutive_failures,
            'waiting_for_pong': self.waiting_for_pong,
            'last_ping_time': self.last_ping_time,
            'last_pong_time': self.last_pong_time,
            'ping_success_rate': (self.total_pongs_received / self.total_pings_sent * 100) if self.total_pings_sent > 0 else 0
        }
    
    async def _listen_messages(self):
        """监听WebSocket消息（增强调试版本）"""
        self.logger.info("🎧 开始监听Binance WebSocket消息...")

        try:
            # 连接状态检查
            if not self.websocket:
                self.logger.error("❌ WebSocket对象为空，无法监听消息")
                return

            self.logger.debug("🔄 进入WebSocket消息循环...")
            self.logger.debug("🔍 WebSocket状态检查",
                            websocket_closed=self.websocket.closed if self.websocket else "None",
                            is_connected=self.is_connected,
                            is_running=self.is_running)

            # 🔧 添加超时保护，避免无限等待
            message_timeout = 30  # 30秒超时

            try:
                async for message in self.websocket:
                    try:
                        self.message_count += 1
                        current_time = asyncio.get_event_loop().time()

                        # 🔍 详细记录每条消息
                        self.logger.debug("📨 收到WebSocket消息",
                                       message_count=self.message_count,
                                       message_size=len(str(message)),
                                       connection_status="active")

                        # 更新最后消息时间
                        self.last_message_time = time.time()

                        # 处理心跳消息 - Binance服务器发送的PING
                        if message == 'ping':
                            self.logger.debug("💓 收到Binance服务器PING，自动响应PONG")
                            await self.websocket.send('pong')
                            self.total_pongs_received += 1
                            self.consecutive_ping_failures = 0  # 重置连续失败计数
                            continue

                        # 处理PONG响应（如果有的话）
                        if message == 'pong':
                            self.logger.debug("💓 收到Binance服务器PONG响应")
                            continue

                        # 解析和处理数据消息
                        try:
                            data = json.loads(message)
                            await self._handle_message(data)
                        except json.JSONDecodeError:
                            # 可能是非JSON消息，记录但不处理
                            self.logger.debug(f"收到非JSON消息: {message[:100]}")
                            continue

                        # 定期报告状态（降级为DEBUG，减少频繁输出）
                        if self.message_count % 100 == 0:  # 每100条消息报告一次
                            self.logger.debug("📊 消息处理状态",
                                            processed=self.message_count,
                                            connection_alive=True,
                                            error_count=self.error_count,
                                            error_rate=f"{self.error_count/max(self.message_count,1)*100:.2f}%")

                    except json.JSONDecodeError as e:
                        self.error_count += 1
                        # 🔧 修复：避免参数冲突，使用不同的参数名
                        self.logger.error("JSON parsing failed", error=e, raw_message=str(message)[:200])
                    except Exception as e:
                        self.error_count += 1
                        self.logger.error("❌ 处理消息失败", error=str(e), message_count=self.message_count, exc_info=True)

                # 如果循环正常结束，说明连接断开
                self.logger.warning("🔌 WebSocket消息循环正常结束，连接已断开")

            except asyncio.TimeoutError:
                self.logger.error("⏰ WebSocket消息接收超时", timeout=message_timeout)
                self.is_connected = False
            except Exception as loop_e:
                self.logger.error("❌ WebSocket消息循环异常", error=str(loop_e), exc_info=True)
                self.is_connected = False

        except Exception as e:
            self.error_count += 1
            self.logger.error("❌ 消息监听失败", error=str(e), message_count=self.message_count, exc_info=True)
            self.is_connected = False

        finally:
            self.logger.info("🏁 WebSocket消息监听结束",
                           total_messages=self.message_count,
                           total_errors=self.error_count,
                           final_connection_status=self.is_connected)

    async def disconnect(self):
        """断开WebSocket连接（参考OKX的清理逻辑）"""
        try:
            # 取消监听任务
            if self.listen_task and not self.listen_task.done():
                self.listen_task.cancel()
                try:
                    await self.listen_task
                except asyncio.CancelledError:
                    pass

            # 关闭WebSocket连接
            if self.websocket and self.is_connected:
                await self.websocket.close()
                self.is_connected = False

            # 记录连接统计信息（参考OKX的统计记录）
            uptime = None
            if self.connection_start_time:
                uptime = (datetime.now(timezone.utc) - self.connection_start_time).total_seconds()

            self.logger.info("🔌 Binance WebSocket已断开",
                           total_messages=self.message_count,
                           total_errors=self.error_count,
                           error_rate=f"{self.error_count/max(self.message_count,1)*100:.2f}%",
                           uptime_seconds=uptime)

        except Exception as e:
            self.logger.error("❌ 断开Binance WebSocket失败", error=str(e))
    
    async def _handle_message(self, message: Dict[str, Any]):
        """处理WebSocket消息（参考OKX的消息处理结构和数据验证）"""
        try:
            # 🔍 调试：记录所有接收到的消息
            self.logger.debug("🔍 Binance WebSocket收到消息",
                           message_keys=list(message.keys()) if isinstance(message, dict) else "非字典",
                           market_type=self.market_type,
                           message_preview=str(message)[:200])

            if not self.on_orderbook_update:
                self.logger.warning("❌ 回调函数未设置")
                return

            # 处理WebSocket API响应（包括订阅确认和depth请求响应）
            if 'id' in message:
                request_id = message.get('id')

                # 检查是否是快照请求的响应
                if isinstance(request_id, str) and request_id.startswith('snapshot_'):
                    self.logger.info(f"📋 收到WebSocket API快照响应: request_id={request_id}")
                    # 将响应传递给管理器处理
                    await self._handle_websocket_api_response(message)
                    return
                elif 'result' in message:
                    if message['result'] is None:
                        # 🔧 修复：避免参数冲突，使用不同的参数名
                        self.logger.info("Binance subscription confirmed", subscription_message=message)
                    else:
                        # 🔧 修复：避免参数冲突，使用不同的参数名
                        self.logger.warning("Subscription may have failed", subscription_message=message)
                    return

            # 处理多流格式消息
            if 'stream' in message and 'data' in message:
                stream = message['stream']
                data = message['data']
                symbol = stream.split('@')[0].upper()

                self.logger.debug("处理Binance多流消息", symbol=symbol, stream=stream)

                # 验证数据完整性（参考OKX的数据验证）
                if self._validate_orderbook_data(data):
                    await self._call_update_callback(symbol, data)
                else:
                    self.logger.warning("❌ 多流消息数据验证失败", symbol=symbol)

            # 🔧 新增：处理逐笔成交数据
            elif 'e' in message and message.get('e') in ['trade', 'aggTrade']:
                symbol = message.get('s', '').upper()

                if not symbol:
                    # 🔧 修复：避免参数冲突，使用不同的参数名
                    self.logger.warning("Trade message missing symbol", raw_message=str(message)[:200])
                    return

                # 记录逐笔成交信息
                trade_data = {
                    'symbol': symbol,
                    'event_type': message.get('e'),
                    'trade_id': message.get('t', 'N/A'),
                    'price': message.get('p', 'N/A'),
                    'quantity': message.get('q', 'N/A'),
                    'trade_time': message.get('T', 'N/A')
                }

                self.logger.debug("💹 处理Binance逐笔成交数据", **trade_data)
                await self._call_update_callback(symbol, message)

            # 🔧 根据官方文档：处理深度更新消息
            elif 'e' in message and message.get('e') == 'depthUpdate':
                await self._handle_depth_update(message)

            # 处理完整订单簿快照格式
            elif 'lastUpdateId' in message and 'bids' in message and 'asks' in message:
                symbol = self.symbols[0].upper() if self.symbols else "UNKNOWN"

                # 转换为增量更新格式
                converted_data = {
                    'U': message['lastUpdateId'],
                    'u': message['lastUpdateId'],
                    'b': message['bids'],
                    'a': message['asks']
                }

                self.logger.debug("转换快照为增量格式", symbol=symbol, lastUpdateId=message['lastUpdateId'])
                await self._call_update_callback(symbol, converted_data)

            else:
                # 其他格式的消息
                self.logger.debug("收到其他格式的Binance消息",
                                message_keys=list(message.keys()),
                                message_preview=str(message)[:200])

        except Exception as e:
            self.error_count += 1
            self.logger.error("❌ 处理Binance WebSocket消息失败",
                            error=str(e),
                            message=str(message)[:200],
                            exc_info=True)

    async def _handle_depth_update(self, data: Dict[str, Any]):
        """
        根据官方文档处理深度更新消息
        现货和衍生品有不同的处理逻辑
        """
        try:
            symbol = data.get('s', '').upper()
            if not symbol:
                self.logger.warning("❌ 深度更新消息缺少symbol", data=str(data)[:200])
                return

            if symbol not in self.symbols:
                self.logger.warning("⚠️ 收到未订阅交易对的数据", symbol=symbol, subscribed_symbols=self.symbols)
                return

            # 🔧 根据官方文档：验证必要字段
            required_fields = ['U', 'u', 'b', 'a']  # 现货必需字段
            if self.market_type == 'perpetual':
                required_fields.append('pu')  # 衍生品还需要pu字段

            missing_fields = [field for field in required_fields if field not in data]
            if missing_fields:
                self.logger.warning("❌ 深度更新消息缺少必要字段",
                                  symbol=symbol,
                                  missing_fields=missing_fields,
                                  available_fields=list(data.keys()))
                return

            # 记录深度更新信息
            log_data = {
                'symbol': symbol,
                'first_update_id': data.get('U'),
                'final_update_id': data.get('u'),
                'bids_count': len(data.get('b', [])),
                'asks_count': len(data.get('a', [])),
                'market_type': self.market_type
            }

            # 衍生品特有的pu字段验证
            if self.market_type == 'perpetual':
                log_data['prev_update_id'] = data.get('pu')

            self.logger.debug("📊 处理Binance深度更新", **log_data)

            # 调用回调函数
            await self._call_update_callback(symbol, data)

        except Exception as e:
            self.error_count += 1
            self.logger.error("❌ 处理深度更新失败", error=str(e), data=str(data)[:200], exc_info=True)

    def _validate_orderbook_data(self, data: Dict[str, Any]) -> bool:
        """验证订单簿数据完整性（根据官方文档更新验证逻辑）"""
        try:
            # 检查必需字段
            if 'e' in data and data.get('e') == 'depthUpdate':
                # 深度更新格式验证（根据官方文档）
                required_fields = ['s', 'U', 'u', 'b', 'a']
                for field in required_fields:
                    if field not in data:
                        self.logger.warning(f"❌ 深度更新缺少必需字段: {field}")
                        return False

                # 永续合约特有字段验证
                if self.market_type == 'perpetual':
                    # 永续合约应该有 'pu' 字段（上一个流的最终更新ID）
                    if 'pu' not in data:
                        self.logger.debug("⚠️ 永续合约深度更新缺少pu字段", symbol=data.get('s'))
                        # 不作为错误，因为可能是第一条消息

            else:
                # 其他格式的基本验证
                if not isinstance(data.get('bids'), list) or not isinstance(data.get('asks'), list):
                    if not isinstance(data.get('b'), list) or not isinstance(data.get('a'), list):
                        self.logger.warning("❌ bids/asks或b/a不是列表类型")
                        return False

            # 检查更新ID的合理性（如果存在）
            if 'U' in data and 'u' in data:
                first_update_id = data.get('U', 0)
                last_update_id = data.get('u', 0)
                if last_update_id < first_update_id:
                    self.logger.warning("❌ 更新ID不合理",
                                      first_id=first_update_id,
                                      last_id=last_update_id)
                    return False

            return True

        except Exception as e:
            self.logger.error("❌ 数据验证异常", error=str(e))
            return False

    async def _call_update_callback(self, symbol: str, data: Dict[str, Any]):
        """调用更新回调函数（恢复简单错误处理）"""
        try:
            # 🔍 调试：记录回调调用
            self.logger.debug(f"🔧 调用Binance WebSocket回调: {symbol}")

            if asyncio.iscoroutinefunction(self.on_orderbook_update):
                await self.on_orderbook_update(symbol, data)
            else:
                self.on_orderbook_update(symbol, data)

            self.logger.debug(f"✅ Binance WebSocket回调完成: {symbol}")

        except Exception as e:
            self.error_count += 1
            self.logger.error("❌ 回调函数执行失败", error=str(e), symbol=symbol)

    async def send_message(self, message: Dict[str, Any]):
        """发送WebSocket消息（添加缺失的方法）"""
        try:
            if self.websocket and self.is_connected:
                message_str = json.dumps(message)
                await self.websocket.send(message_str)
                # 🔧 修复：避免参数冲突，使用不同的参数名
                self.logger.debug("Sending WebSocket message", sent_message=message)
            else:
                self.logger.error("❌ WebSocket未连接，无法发送消息")
        except Exception as e:
            self.error_count += 1
            # 🔧 修复：避免参数冲突，使用不同的参数名
            self.logger.error("Failed to send WebSocket message", error=e, failed_message=message)

    async def _handle_error(self, error: Exception):
        """处理WebSocket错误"""
        self.error_count += 1
        self.logger.error("❌ Binance WebSocket错误", error=str(error))
        self.is_connected = False

    async def _handle_close(self, code: int, reason: str):
        """处理WebSocket关闭"""
        self.logger.warning("🔌 Binance WebSocket连接关闭",
                          code=code, reason=reason)
        self.is_connected = False
    
    def get_connection_status(self) -> Dict[str, Any]:
        """获取连接状态（参考OKX的状态报告格式）"""
        uptime = None
        if self.connection_start_time:
            uptime = (datetime.now(timezone.utc) - self.connection_start_time).total_seconds()

        return {
            'connected': self.is_connected,
            'ws_url': self.ws_url,
            'market_type': self.market_type,
            'symbols': self.symbols,
            'websocket_depth': self.websocket_depth,
            'message_count': self.message_count,
            'error_count': self.error_count,
            'error_rate': self.error_count / max(self.message_count, 1),
            'uptime_seconds': uptime,
            'last_message_time': self.last_message_time,
            'connection_start_time': self.connection_start_time.isoformat() if self.connection_start_time else None
        }
    
    async def send_message(self, message: Dict[str, Any]):
        """发送消息到WebSocket"""
        try:
            if self.websocket and self.is_connected:
                await self.websocket.send(json.dumps(message))
            else:
                self.logger.warning("⚠️ WebSocket未连接，无法发送消息")
        except Exception as e:
            self.logger.error("❌ 发送WebSocket消息失败", error=str(e))
    
    async def subscribe_orderbook(self, symbols: List[str] = None):
        """订阅订单簿数据（根据官方文档修复）"""
        if symbols is None:
            symbols = self.symbols

        try:
            # 构建订阅参数列表
            params = []
            for symbol in symbols:
                # 使用@depth@100ms获得更频繁的更新，减少与WebSocket API的差距
                # 现货: <symbol>@depth@100ms (100ms推送一次depthUpdate事件)
                # 永续合约: <symbol>@depth@100ms (100ms推送一次depthUpdate事件，包含pu字段)
                params.append(f"{symbol.lower()}@depth@100ms")

            # 发送单个订阅消息包含所有交易对
            subscribe_msg = {
                "method": "SUBSCRIBE",
                "params": params,
                "id": 1
            }
            await self.send_message(subscribe_msg)

            self.logger.info("📊 已订阅Binance订单簿深度更新",
                           symbols=symbols,
                           params=params,
                           market_type=self.market_type)

        except Exception as e:
            self.error_count += 1
            self.logger.error("❌ 订阅Binance订单簿失败", error=str(e))
    
    async def unsubscribe_orderbook(self, symbols: List[str] = None):
        """取消订阅订单簿数据"""
        if symbols is None:
            symbols = self.symbols
        
        try:
            for symbol in symbols:
                unsubscribe_msg = {
                    "method": "UNSUBSCRIBE",
                    # 🔧 修复：使用与订阅一致的流格式
                    "params": [f"{symbol.lower()}@depth"],
                    "id": 2
                }
                await self.send_message(unsubscribe_msg)
                
            self.logger.info("📊 已取消订阅Binance订单簿数据", symbols=symbols)
            
        except Exception as e:
            self.logger.error("❌ 取消订阅Binance订单簿失败", error=str(e))

    # 🔧 新增：逐笔成交数据订阅功能
    async def subscribe_trades(self, symbols: List[str] = None):
        """
        订阅逐笔成交数据
        现货使用 @trade stream，期货使用 @aggTrade stream
        """
        if symbols is None:
            symbols = self.symbols

        try:
            for symbol in symbols:
                if self.market_type == 'spot':
                    stream = f"{symbol.lower()}@trade"
                else:  # derivatives
                    stream = f"{symbol.lower()}@aggTrade"

                subscribe_msg = {
                    "method": "SUBSCRIBE",
                    "params": [stream],
                    "id": int(time.time() * 1000)
                }
                await self.send_message(subscribe_msg)

            self.logger.info("✅ 订阅Binance逐笔成交数据成功",
                           symbols=symbols,
                           market_type=self.market_type)

        except Exception as e:
            self.logger.error("❌ 订阅Binance逐笔成交数据失败", error=str(e))

    async def unsubscribe_trades(self, symbols: List[str] = None):
        """取消订阅逐笔成交数据"""
        if symbols is None:
            symbols = self.symbols

        try:
            for symbol in symbols:
                if self.market_type == 'spot':
                    stream = f"{symbol.lower()}@trade"
                else:  # derivatives
                    stream = f"{symbol.lower()}@aggTrade"

                unsubscribe_msg = {
                    "method": "UNSUBSCRIBE",
                    "params": [stream],
                    "id": int(time.time() * 1000)
                }
                await self.send_message(unsubscribe_msg)

            self.logger.info("✅ 取消订阅Binance逐笔成交数据成功", symbols=symbols)

        except Exception as e:
            self.logger.error("❌ 取消订阅Binance逐笔成交数据失败", error=str(e))

    async def subscribe_stream(self, stream: str):
        """
        订阅单个stream（通用方法）
        支持订单簿、逐笔成交等各种数据流
        """
        try:
            subscribe_msg = {
                "method": "SUBSCRIBE",
                "params": [stream],
                "id": int(time.time() * 1000)
            }

            await self.send_message(subscribe_msg)
            self.logger.debug("✅ 订阅Binance数据流成功", stream=stream)

        except Exception as e:
            self.logger.error("❌ 订阅Binance数据流失败", stream=stream, error=str(e))

    async def _handle_websocket_api_response(self, message: Dict[str, Any]):
        """处理WebSocket API响应"""
        try:
            request_id = message.get('id')
            if not request_id:
                return

            self.logger.debug(f"🔍 处理WebSocket API响应: request_id={request_id}")

            # 将响应传递给回调函数，让管理器处理
            if self.on_orderbook_update:
                # 使用特殊的symbol标识这是API响应
                await self._call_update_callback('__websocket_api_response__', message)

        except Exception as e:
            self.logger.error(f"❌ 处理WebSocket API响应失败: {e}", exc_info=True)


class BinanceWebSocketManager:
    """
    Binance WebSocket管理器 - 专门用于Trades Manager
    支持通用数据回调，不限于订单簿数据
    """

    def __init__(self, market_type: str = 'spot', symbols: List[str] = None, data_callback: Callable = None):
        self.market_type = market_type
        self.symbols = symbols or []
        self.data_callback = data_callback
        # 🔧 迁移到统一日志系统
        self.logger = get_managed_logger(
            ComponentType.WEBSOCKET,
            exchange="binance",
            market_type=market_type
        )

        # 使用现有的WebSocket客户端
        self.client = BinanceWebSocketClient(
            symbols=self.symbols,
            on_orderbook_update=self._handle_data,
            market_type=market_type
        )

        self.is_connected = False

    async def start(self):
        """启动WebSocket连接"""
        try:
            success = await self.client.connect()
            # 🔧 修复：同步连接状态
            self.is_connected = success and self.client.is_connected

            if self.is_connected:
                self.logger.info("✅ BinanceWebSocketManager启动成功", market_type=self.market_type)
            else:
                self.logger.error("❌ BinanceWebSocketManager连接失败", market_type=self.market_type)

        except Exception as e:
            self.is_connected = False
            self.logger.error("❌ BinanceWebSocketManager启动失败", error=str(e), exc_info=True)
            raise

    async def stop(self):
        """停止WebSocket连接"""
        try:
            await self.client.disconnect()
            self.is_connected = False
            self.logger.info("✅ BinanceWebSocketManager停止成功")
        except Exception as e:
            self.logger.error("❌ BinanceWebSocketManager停止失败", error=str(e), exc_info=True)

    async def subscribe_stream(self, stream: str):
        """订阅数据流"""
        await self.client.subscribe_stream(stream)

    async def subscribe_trades(self, symbols: List[str] = None):
        """订阅逐笔成交数据"""
        await self.client.subscribe_trades(symbols)

    async def subscribe_orderbook(self, symbols: List[str] = None):
        """订阅订单簿数据"""
        await self.client.subscribe_orderbook(symbols)

    async def _handle_data(self, symbol: str, data: Dict[str, Any]):
        """处理接收到的数据"""
        if self.data_callback:
            try:
                if asyncio.iscoroutinefunction(self.data_callback):
                    await self.data_callback(data)
                else:
                    self.data_callback(data)
            except Exception as e:
                self.logger.error("数据回调处理失败", error=str(e), exc_info=True)


# 向后兼容的别名
BinanceWebSocket = BinanceWebSocketClient
