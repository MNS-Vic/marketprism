"""
通用NATS消息发布器

支持MarketPrism数据收集器的所有数据类型发布需求
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field
import structlog

try:
    import nats
    from nats.aio.client import Client as NATSClient
    from nats.js.api import StreamConfig, RetentionPolicy, StorageType, DiscardPolicy
    NATS_AVAILABLE = True
except ImportError:
    NATS_AVAILABLE = False
    NATSClient = None

from .data_types import Exchange, MarketType, DataType
from .normalizer import DataNormalizer



@dataclass
class NATSConfig:
    """NATS配置"""
    # 🔧 合理的默认值：NATS标准端口，作为配置缺失时的回退机制
    servers: List[str] = field(default_factory=lambda: ["nats://localhost:4222"])
    client_name: str = "unified-collector"
    max_reconnect_attempts: int = 10
    reconnect_time_wait: int = 2
    timeout: int = 5
    max_retries: int = 3
    batch_size: int = 100

    # JetStream流配置 - 🔧 修复：启用JetStream确保金融数据不丢失
    enable_jetstream: bool = True
    streams: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {
        "MARKET_DATA": {
            "name": "MARKET_DATA",
            "subjects": ["orderbook-data.>", "trade-data.>", "funding-rate.>",
                        "open-interest.>", "liquidation-orders.>", "kline-data.>"],
            "retention": "limits",
            # 🔧 优化：金融数据配置 - 确保数据不丢失
            "max_msgs": 5000000,      # 增加到500万条消息
            "max_bytes": 2147483648,  # 增加到2GB
            "max_age": 172800,        # 增加到48小时
            "max_consumers": 50,      # 支持更多消费者
            "replicas": 1,
            # 🔧 新增：金融数据特定配置
            "storage": "file",        # 使用文件存储确保持久化
            "discard": "old",         # 达到限制时丢弃旧消息
            "duplicate_window": 120   # 2分钟重复消息检测窗口
        }
    })


def create_nats_config_from_yaml(config_dict: Dict[str, Any]) -> NATSConfig:
    """
    从YAML配置创建NATS配置

    Args:
        config_dict: 从unified_data_collection.yaml加载的配置字典

    Returns:
        NATSConfig实例
    """
    nats_config = config_dict.get('nats', {})

    # 🔧 修复：支持JetStream配置
    jetstream_config = nats_config.get('jetstream', {})

    return NATSConfig(
        # 基础连接配置
        servers=nats_config.get('servers', ["nats://localhost:4222"]),
        client_name=nats_config.get('client_name', 'unified-collector'),
        max_reconnect_attempts=nats_config.get('max_reconnect_attempts', 10),
        reconnect_time_wait=nats_config.get('reconnect_time_wait', 2),
        timeout=nats_config.get('publish', {}).get('timeout', 5),
        max_retries=nats_config.get('publish', {}).get('max_retries', 3),
        batch_size=nats_config.get('publish', {}).get('batch_size', 100),

        # 🔧 JetStream配置
        enable_jetstream=jetstream_config.get('enabled', True),
        streams=jetstream_config.get('streams', {})
    )


@dataclass
class PublishStats:
    """发布统计"""
    total_published: int = 0
    successful_published: int = 0
    failed_published: int = 0
    last_publish_time: Optional[float] = None
    connection_errors: int = 0
    publish_errors: int = 0


class NATSPublisher:
    """
    通用NATS消息发布器
    
    支持所有数据类型的统一发布接口
    """
    
    def __init__(self, config: Optional[NATSConfig] = None, normalizer: Optional[DataNormalizer] = None):
        self.config = config or NATSConfig()
        self.normalizer = normalizer or DataNormalizer()  # 🔧 添加Normalizer用于Symbol标准化
        self.logger = structlog.get_logger(__name__)
        
        # 连接管理
        self.client: Optional[NATSClient] = None
        self.js = None  # JetStream context
        self._is_connected = False
        self.connection_lock = asyncio.Lock()
        
        # 统计信息
        self.stats = PublishStats()
        
        # 主题模板 - 符合unified_data_collection.yaml配置
        self.subject_templates = {
            DataType.ORDERBOOK: "orderbook-data.{exchange}.{market_type}.{symbol}",
            DataType.TRADE: "trade-data.{exchange}.{market_type}.{symbol}",
            DataType.FUNDING_RATE: "funding-rate.{exchange}.{market_type}.{symbol}",
            DataType.OPEN_INTEREST: "open-interest.{exchange}.{market_type}.{symbol}",
        }
        
        # 批量发布缓冲区
        self.publish_buffer: List[Dict[str, Any]] = []
        self.buffer_lock = asyncio.Lock()
        self.last_flush_time = time.time()
        
        # 检查NATS可用性
        if not NATS_AVAILABLE:
            self.logger.warning("NATS客户端不可用，请安装: pip install nats-py")
    
    async def connect(self) -> bool:
        """连接到NATS服务器"""
        if not NATS_AVAILABLE:
            self.logger.error("NATS客户端不可用")
            return False
        
        async with self.connection_lock:
            if self.is_connected:
                return True
            
            try:
                self.logger.info("连接到NATS服务器", servers=self.config.servers)
                
                # 创建NATS客户端
                self.client = await nats.connect(
                    servers=self.config.servers,
                    name=self.config.client_name,
                    error_cb=self._error_handler,
                    closed_cb=self._closed_handler,
                    reconnected_cb=self._reconnected_handler,
                    max_reconnect_attempts=self.config.max_reconnect_attempts,
                    reconnect_time_wait=self.config.reconnect_time_wait,
                )
                
                # 获取JetStream上下文（可选）
                if self.config.enable_jetstream:
                    try:
                        self.js = self.client.jetstream()
                        self.logger.info("✅ JetStream上下文已创建")

                        # 确保流存在
                        await self._ensure_streams()
                        self.logger.info("✅ JetStream流配置完成 - 金融数据将持久化存储")

                    except Exception as e:
                        self.logger.warning("⚠️ JetStream不可用，降级到核心NATS",
                                          error=str(e),
                                          fallback="数据仍会发布但不会持久化")
                        self.js = None
                        # 🔧 重要：即使JetStream失败，也要继续使用核心NATS
                        # 这确保了数据流的连续性
                else:
                    self.js = None
                    self.logger.info("📡 使用核心NATS模式 - 实时传输优先")
                
                self._is_connected = True
                self.logger.info("NATS连接成功")
                return True
                
            except Exception as e:
                self.logger.error("NATS连接失败", error=str(e))
                self.stats.connection_errors += 1
                self._is_connected = False
                return False
    
    async def disconnect(self):
        """断开NATS连接"""
        async with self.connection_lock:
            try:
                # 刷新缓冲区
                await self._flush_buffer()
                
                self._is_connected = False

                if self.client and not self.client.is_closed:
                    await asyncio.wait_for(self.client.close(), timeout=5.0)
                    self.logger.info("NATS连接已断开")

            except asyncio.TimeoutError:
                self.logger.warning("NATS断开连接超时")
            except Exception as e:
                self.logger.error("断开NATS连接时出错", error=str(e))
            finally:
                self.client = None
                self.js = None
                self._is_connected = False

    @property
    def is_connected(self) -> bool:
        """
        检查NATS连接状态 - 🔧 修复：添加缺失的方法

        Returns:
            bool: 连接状态
        """
        return hasattr(self, '_is_connected') and self._is_connected and self.client is not None and not self.client.is_closed

    async def _ensure_streams(self):
        """确保所需的JetStream流存在"""
        if not self.js:
            return

        for stream_name, stream_config in self.config.streams.items():
            try:
                # 尝试获取流信息
                try:
                    await self.js.stream_info(stream_name)
                    self.logger.debug("JetStream流已存在", stream=stream_name)
                except:
                    # 流不存在，创建流
                    # 🔧 修复：支持新的金融数据配置参数
                    config = StreamConfig(
                        name=stream_config["name"],
                        subjects=stream_config["subjects"],
                        retention=RetentionPolicy.LIMITS,
                        max_msgs=stream_config["max_msgs"],
                        max_bytes=stream_config["max_bytes"],
                        max_age=stream_config["max_age"],
                        max_consumers=stream_config["max_consumers"],
                        num_replicas=stream_config["replicas"],
                        # 🔧 新增：金融数据特定配置
                        storage=StorageType.FILE if stream_config.get("storage") == "file" else StorageType.MEMORY,
                        discard=DiscardPolicy.OLD if stream_config.get("discard") == "old" else DiscardPolicy.NEW,
                        duplicate_window=stream_config.get("duplicate_window", 120)
                    )

                    await self.js.add_stream(config)
                    self.logger.info("创建JetStream流", stream=stream_name)

            except Exception as e:
                self.logger.error("创建JetStream流失败", stream=stream_name, error=str(e))
                # 不抛出异常，允许使用核心NATS

    # 🔧 移除重复的Symbol标准化逻辑 - 现在使用Normalizer的标准化结果
    # NATS Publisher不再进行Symbol格式转换，直接使用已标准化的数据

    def _generate_subject(self, data_type: str, exchange: str, market_type: str, symbol: str) -> str:
        """
        生成NATS主题
        
        Args:
            data_type: 数据类型 (orderbook, trade, funding_rate, open_interest)
            exchange: 交易所名称
            market_type: 市场类型 (spot, perpetual)
            symbol: 交易对符号
            
        Returns:
            NATS主题字符串
        """
        # 转换数据类型
        if isinstance(data_type, DataType):
            data_type_str = data_type.value
        else:
            data_type_str = str(data_type).lower()

        # 🔧 直接使用已标准化的symbol（从Normalizer获得）
        normalized_symbol = symbol

        # 获取主题模板
        template = self.subject_templates.get(
            DataType(data_type_str) if data_type_str in [dt.value for dt in DataType] else None,
            f"{data_type_str}-data.{{exchange}}.{{market_type}}.{{symbol}}"
        )

        # 🎯 格式化主题 - 新的市场分类架构
        # exchange名称保持原样（如binance_spot, binance_derivatives）
        # market_type转为小写（如spot, perpetual）
        subject = template.format(
            exchange=exchange,  # 🔧 保持原样，不转换为小写
            market_type=market_type.lower(),
            symbol=normalized_symbol
        )
        
        return subject

    # 🔧 移除市场类型推断逻辑 - 现在从配置获取market_type，不进行推断
    # 市场类型应该从OrderBook Manager传入，而不是根据Symbol推断

    async def publish_data(self, data_type: Union[str, DataType], exchange: str,
                          market_type: str, symbol: str, data: Dict[str, Any],
                          use_jetstream: bool = False) -> bool:
        """
        发布数据到NATS
        
        Args:
            data_type: 数据类型
            exchange: 交易所名称
            market_type: 市场类型
            symbol: 交易对符号
            data: 要发布的数据
            use_jetstream: 是否使用JetStream
            
        Returns:
            发布是否成功
        """
        if not self.is_connected:
            # 尝试重连
            if not await self.connect():
                return False
        
        try:
            # 🔧 直接使用已标准化的symbol（从Normalizer获得）
            normalized_symbol = symbol

            # 生成主题
            subject = self._generate_subject(data_type, exchange, market_type, normalized_symbol)

            # 🔍 调试：输出最终NATS主题生成
            self.logger.debug("🔍 最终NATS主题生成调试",
                           data_type=str(data_type),
                           exchange=exchange,
                           market_type=market_type,
                           normalized_symbol=normalized_symbol,
                           final_subject=subject)

            # 准备消息数据 - 直接发布数据内容，不包装
            # 如果data已经是完整的消息格式，直接使用
            if isinstance(data, dict) and 'exchange' in data and 'symbol' in data:
                message_data = data
            else:
                # 否则构建完整的消息格式
                message_data = {
                    'exchange': exchange,
                    'market_type': market_type,
                    'symbol': normalized_symbol,
                    'data_type': str(data_type),
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'publisher': 'unified-collector'
                }

                # 安全地添加数据内容
                if isinstance(data, dict):
                    message_data.update(data)
                else:
                    message_data['data'] = data
            
            # 序列化消息
            message_bytes = json.dumps(message_data, ensure_ascii=False, default=str).encode('utf-8')
            
            # 发布消息
            if use_jetstream and self.js:
                # 使用JetStream发布
                ack = await self.js.publish(subject, message_bytes)
                self.logger.debug("JetStream消息发布成功", 
                                subject=subject, sequence=ack.seq)
            else:
                # 使用核心NATS发布
                await self.client.publish(subject, message_bytes)
                self.logger.debug("NATS消息发布成功", subject=subject)
            
            # 更新统计
            self.stats.total_published += 1
            self.stats.successful_published += 1
            self.stats.last_publish_time = time.time()
            
            return True
            
        except Exception as e:
            # 改进的错误处理
            from collector.exceptions import handle_error

            wrapped_error = handle_error(
                e, "nats_publisher", "publish",
                additional_data={"subject": subject if 'subject' in locals() else 'unknown'}
            )

            self.logger.error("发布消息失败",
                            subject=subject if 'subject' in locals() else 'unknown',
                            error=str(wrapped_error))
            self.stats.total_published += 1
            self.stats.failed_published += 1
            self.stats.publish_errors += 1
            return False

    async def _publish_with_retry(self, subject: str, message_data: str):
        """带重试机制的发布方法"""
        from collector.retry_mechanism import nats_retry

        @nats_retry("nats_publish")
        async def _do_publish():
            message_bytes = message_data.encode('utf-8')

            if self.config.enable_jetstream and self.js:
                # 使用JetStream发布
                ack = await self.js.publish(subject, message_bytes)
                self.logger.debug("JetStream消息发布成功",
                                subject=subject, sequence=ack.seq)
            else:
                # 使用核心NATS发布
                await self.client.publish(subject, message_bytes)
                self.logger.debug("NATS消息发布成功", subject=subject)

        await _do_publish()
    
    async def publish_orderbook(self, exchange: str, market_type: str, symbol: str,
                               orderbook_data: Dict[str, Any]) -> bool:
        """
        发布订单簿数据 - 优化：集中化数据标准化

        🔧 架构优化：统一标准化入口，确保所有数据格式一致
        """
        try:
            # 🔧 集中化标准化：在此处统一进行所有数据标准化
            if orderbook_data.get('raw_data', False):
                # 处理原始数据，进行完整标准化
                standardized_data = await self._standardize_orderbook_data(
                    orderbook_data, exchange, market_type, symbol
                )
            else:
                # 处理已部分标准化的数据（向后兼容）
                standardized_data = orderbook_data

            # 🔧 Symbol标准化：统一格式 BTCUSDT -> BTC-USDT, BTC-USDT-SWAP -> BTC-USDT
            normalized_symbol = self.normalizer.normalize_symbol_format(symbol, exchange)

            # 确保标准化数据包含统一字段
            standardized_data.update({
                'normalized_symbol': normalized_symbol,
                'standardized_at': datetime.now(timezone.utc).isoformat(),
                'standardization_version': '2.0'
            })

            return await self.publish_data(
                DataType.ORDERBOOK, exchange, market_type, normalized_symbol, standardized_data
            )

        except Exception as e:
            self.logger.error(f"❌ 订单簿数据标准化失败: {e}")
            return False
    
    async def publish_trade(self, exchange: str, market_type: str, symbol: str, 
                           trade_data: Dict[str, Any]) -> bool:
        """发布交易数据"""
        return await self.publish_data(
            DataType.TRADE, exchange, market_type, symbol, trade_data
        )

    # 别名方法，用于兼容演示脚本
    async def publish_orderbook_data(self, exchange: str, market_type: str, symbol: str,
                                   data: Dict[str, Any]) -> bool:
        """发布订单簿数据（别名方法）"""
        return await self.publish_orderbook(exchange, market_type, symbol, data)

    async def publish_trade_data(self, trade_data: Dict[str, Any],
                               exchange: Exchange, market_type, symbol: str) -> bool:
        """
        🔧 优化：统一成交数据发布方法
        支持原始数据和标准化数据的处理
        """
        try:
            # 🔧 集中化标准化：检查是否为原始数据
            if trade_data.get('raw_data', False):
                # 处理原始数据，进行完整标准化
                standardized_data = await self._standardize_trade_data(
                    trade_data, exchange, market_type, symbol
                )
            else:
                # 处理已标准化的数据（向后兼容）
                standardized_data = trade_data

            # Symbol标准化
            normalized_symbol = self.normalizer.normalize_symbol_format(symbol, exchange.value)

            # 确保标准化数据包含统一字段
            standardized_data.update({
                'normalized_symbol': normalized_symbol,
                'standardized_at': datetime.now(timezone.utc).isoformat(),
                'standardization_version': '2.0'
            })

            # 构建NATS主题
            subject = f"trades-data.{exchange.value}.{market_type.value}.{normalized_symbol}"

            # 调试日志
            self.logger.debug("🔍 成交数据NATS主题生成",
                           data_type=DataType.TRADE,
                           exchange=exchange.value,
                           market_type=market_type.value,
                           normalized_symbol=normalized_symbol,
                           final_subject=subject)

            # 发布数据
            return await self.publish_data(
                DataType.TRADE, exchange.value, market_type.value, normalized_symbol, standardized_data
            )

        except Exception as e:
            self.logger.error(f"❌ 成交数据发布失败: {e}")
            return False

    async def publish_trade_data_raw(self, raw_trade_data: Dict[str, Any],
                                   exchange: Exchange, market_type, symbol: str) -> bool:
        """
        🔧 新增：处理原始成交数据的发布方法
        集中化标准化逻辑，确保输出格式统一
        """
        try:
            # 🔧 集中化标准化：统一成交数据格式
            standardized_data = await self._standardize_trade_data(
                raw_trade_data, exchange, market_type, symbol
            )

            # Symbol标准化
            normalized_symbol = self.normalizer.normalize_symbol_format(symbol, exchange.value)

            # 确保标准化数据包含统一字段
            standardized_data.update({
                'normalized_symbol': normalized_symbol,
                'standardized_at': datetime.now(timezone.utc).isoformat(),
                'standardization_version': '2.0'
            })

            return await self.publish_data(
                DataType.TRADE, exchange.value, market_type.value, normalized_symbol, standardized_data
            )

        except Exception as e:
            self.logger.error(f"❌ 原始成交数据发布失败: {e}")
            return False

    async def publish_trade_data_legacy(self, exchange: str, market_type: str, symbol: str,
                               data: Dict[str, Any]) -> bool:
        """发布交易数据（旧版别名方法）"""
        return await self.publish_trade(exchange, market_type, symbol, data)

    async def publish_ticker_data(self, exchange: str, market_type: str, symbol: str,
                                data: Dict[str, Any]) -> bool:
        """发布价格数据（别名方法）"""
        return await self.publish_data(DataType.TICKER, exchange, market_type, symbol, data)
    
    async def publish_funding_rate(self, exchange: str, market_type: str, symbol: str, 
                                  funding_data: Dict[str, Any]) -> bool:
        """发布资金费率数据"""
        return await self.publish_data(
            DataType.FUNDING_RATE, exchange, market_type, symbol, funding_data
        )
    
    async def publish_open_interest(self, exchange: str, market_type: str, symbol: str,
                                   oi_data: Dict[str, Any]) -> bool:
        """发布持仓量数据"""
        return await self.publish_data(
            DataType.OPEN_INTEREST, exchange, market_type, symbol, oi_data
        )

    async def publish_kline(self, exchange: str, market_type: str, symbol: str,
                           kline_data: Dict[str, Any]) -> bool:
        """发布K线数据"""
        return await self.publish_data(
            DataType.KLINE, exchange, market_type, symbol, kline_data
        )

    async def publish_liquidation(self, exchange: str, market_type: str, symbol: str,
                                 liquidation_data: Dict[str, Any]) -> bool:
        """发布强平数据"""
        return await self.publish_data(
            DataType.LIQUIDATION, exchange, market_type, symbol, liquidation_data
        )

    async def publish_top_trader_ratio(self, exchange: str, market_type: str, symbol: str,
                                      ratio_data: Dict[str, Any]) -> bool:
        """发布大户持仓比数据"""
        return await self.publish_data(
            DataType.TOP_TRADER_LONG_SHORT_RATIO, exchange, market_type, symbol, ratio_data
        )

    async def publish_market_ratio(self, exchange: str, market_type: str, symbol: str,
                                  ratio_data: Dict[str, Any]) -> bool:
        """发布市场多空比数据"""
        return await self.publish_data(
            DataType.MARKET_LONG_SHORT_RATIO, exchange, market_type, symbol, ratio_data
        )

    async def publish_volatility_index(self, exchange: str, market_type: str, symbol: str,
                                      volatility_data: Dict[str, Any]) -> bool:
        """发布波动率指数数据"""
        return await self.publish_data(
            DataType.VOLATILITY_INDEX, exchange, market_type, symbol, volatility_data
        )

    # 🔧 重构优化：统一的增强订单簿发布方法
    async def publish_enhanced_orderbook(self, orderbook) -> bool:
        """
        统一的增强订单簿发布方法

        🔧 架构分离：在此处进行Symbol标准化，保持业务逻辑使用原始格式
        🔧 重构优化：消除重复逻辑，提供统一的发布接口
        """
        if not (hasattr(orderbook, 'exchange_name') and hasattr(orderbook, 'symbol_name')):
            self.logger.error("订单簿对象缺少必要属性",
                            has_exchange=hasattr(orderbook, 'exchange_name'),
                            has_symbol=hasattr(orderbook, 'symbol_name'))
            return False

        # 🔧 在发布时进行Symbol标准化：BTCUSDT -> BTC-USDT, BTC-USDT-SWAP -> BTC-USDT
        normalized_symbol = self.normalizer.normalize_symbol_format(
            orderbook.symbol_name, orderbook.exchange_name
        )

        # 🔍 调试：输出Symbol标准化过程
        self.logger.debug("🔍 Symbol标准化调试",
                       original_symbol=orderbook.symbol_name,
                       exchange_name=orderbook.exchange_name,
                       normalized_symbol=normalized_symbol)

        # 转换为字典格式
        # 🔧 修复：确保timestamp为Unix时间戳格式，便于验证脚本解析
        timestamp_unix = None
        if hasattr(orderbook, 'timestamp') and orderbook.timestamp:
            timestamp_unix = orderbook.timestamp.timestamp()

        orderbook_data = {
            'exchange': orderbook.exchange_name,
            'symbol': normalized_symbol,  # 使用标准化后的symbol
            'bids': [[str(bid.price), str(bid.quantity)] for bid in orderbook.bids] if hasattr(orderbook, 'bids') else [],
            'asks': [[str(ask.price), str(ask.quantity)] for ask in orderbook.asks] if hasattr(orderbook, 'asks') else [],
            'timestamp': timestamp_unix,  # 使用Unix时间戳
            'timestamp_iso': orderbook.timestamp.isoformat() if hasattr(orderbook, 'timestamp') and orderbook.timestamp else None,
            'last_update_id': getattr(orderbook, 'last_update_id', None),
            'collected_at': datetime.now(timezone.utc).isoformat()
        }

        # 🔧 从订单簿对象获取市场类型，不进行推断
        # 🚨 修复：orderbook对象可能没有market_type属性，需要从exchange_name推断
        if hasattr(orderbook, 'market_type') and orderbook.market_type:
            market_type = orderbook.market_type
        else:
            # 从exchange_name推断市场类型
            exchange_name = orderbook.exchange_name.lower()
            if 'derivatives' in exchange_name or 'perpetual' in exchange_name or 'swap' in exchange_name:
                market_type = 'perpetual'
            else:
                market_type = 'spot'

        # 确保market_type是字符串
        if hasattr(market_type, 'value'):
            market_type = market_type.value
        market_type = str(market_type).lower()

        # 🔍 调试：输出market_type获取过程
        self.logger.debug("🔍 NATSPublisher market_type获取调试",
                       exchange_name=orderbook.exchange_name,
                       has_market_type_attr=hasattr(orderbook, 'market_type'),
                       original_market_type=getattr(orderbook, 'market_type', 'none'),
                       inferred_market_type=market_type)

        return await self.publish_orderbook(
            orderbook.exchange_name, market_type, normalized_symbol, orderbook_data
        )

    async def _standardize_orderbook_data(self, raw_data: Dict[str, Any],
                                         exchange: str, market_type: str, symbol: str) -> Dict[str, Any]:
        """
        🔧 集中化订单簿数据标准化
        统一所有交易所的订单簿数据格式
        """
        try:
            # 基础标准化字段
            standardized = {
                'exchange': exchange,
                'market_type': market_type,
                'symbol': symbol,
                'data_type': 'orderbook',
                'timestamp': raw_data.get('timestamp', datetime.now(timezone.utc).isoformat()),
                'last_update_id': raw_data.get('last_update_id') or raw_data.get('lastUpdateId'),
                'bids': raw_data.get('bids', []),
                'asks': raw_data.get('asks', []),
                'depth_levels': len(raw_data.get('bids', [])) + len(raw_data.get('asks', [])),
                'update_type': raw_data.get('update_type', 'update')
            }

            # 保留交易所特定信息
            if 'exchange_specific' in raw_data:
                standardized['exchange_specific'] = raw_data['exchange_specific']

            return standardized

        except Exception as e:
            self.logger.error(f"❌ 订单簿数据标准化失败: {e}")
            return raw_data

    async def _standardize_trade_data(self, raw_data: Dict[str, Any],
                                    exchange: Exchange, market_type, symbol: str) -> Dict[str, Any]:
        """
        🔧 集中化成交数据标准化
        统一所有交易所的成交数据格式
        """
        try:
            # 基础标准化字段
            standardized = {
                'exchange': exchange.value,
                'market_type': market_type.value,
                'symbol': symbol,
                'data_type': 'trade',
                'price': raw_data.get('price'),
                'quantity': raw_data.get('quantity'),
                'timestamp': raw_data.get('timestamp'),
                'side': raw_data.get('side'),
                'trade_id': raw_data.get('trade_id')
            }

            # 保留交易所特定信息
            if 'exchange_specific' in raw_data:
                standardized['exchange_specific'] = raw_data['exchange_specific']

            return standardized

        except Exception as e:
            self.logger.error(f"❌ 成交数据标准化失败: {e}")
            return raw_data

    # 🔧 重构完成：删除重复的legacy方法，统一使用publish_enhanced_orderbook

    async def publish_trade_legacy(self, trade) -> bool:
        """兼容旧版交易发布方法"""
        if hasattr(trade, 'exchange_name') and hasattr(trade, 'symbol_name'):
            trade_data = {
                'exchange': trade.exchange_name,
                'symbol': trade.symbol_name,
                'price': str(getattr(trade, 'price', 0)),
                'quantity': str(getattr(trade, 'quantity', 0)),
                'side': getattr(trade, 'side', 'unknown'),
                'timestamp': trade.timestamp.isoformat() if hasattr(trade, 'timestamp') and trade.timestamp else None,
                'trade_id': getattr(trade, 'trade_id', None),
                'collected_at': datetime.now(timezone.utc).isoformat()
            }

            market_type = 'spot'  # 默认现货

            return await self.publish_trade(
                trade.exchange_name, market_type, trade.symbol_name, trade_data
            )
        return False

    def _serialize_orderbook(self, orderbook) -> str:
        """
        序列化订单簿数据 - 🔧 修复：添加缺失的序列化方法

        Args:
            orderbook: EnhancedOrderBook对象

        Returns:
            JSON字符串
        """
        try:
            orderbook_data = {
                'exchange_name': orderbook.exchange_name,
                'symbol_name': orderbook.symbol_name,
                'last_update_id': orderbook.last_update_id,
                'bids': [[str(bid.price), str(bid.quantity)] for bid in orderbook.bids] if hasattr(orderbook, 'bids') else [],
                'asks': [[str(ask.price), str(ask.quantity)] for ask in orderbook.asks] if hasattr(orderbook, 'asks') else [],
                'timestamp': orderbook.timestamp.isoformat() if hasattr(orderbook, 'timestamp') and orderbook.timestamp else None,
                'update_type': orderbook.update_type.value if hasattr(orderbook, 'update_type') else 'UPDATE',
                'depth_levels': getattr(orderbook, 'depth_levels', len(orderbook.bids) + len(orderbook.asks)),
                'collected_at': orderbook.collected_at.isoformat() if hasattr(orderbook, 'collected_at') and orderbook.collected_at else datetime.now(timezone.utc).isoformat()
            }

            # 添加可选字段
            if hasattr(orderbook, 'checksum') and orderbook.checksum is not None:
                orderbook_data['checksum'] = orderbook.checksum

            return json.dumps(orderbook_data, ensure_ascii=False)

        except Exception as e:
            self.logger.error(f"订单簿序列化失败: {e}", exc_info=True)
            return ""

    async def batch_publish(self, messages: List[Dict[str, Any]]) -> int:
        """
        批量发布消息
        
        Args:
            messages: 消息列表，每个消息包含data_type, exchange, market_type, symbol, data
            
        Returns:
            成功发布的消息数量
        """
        if not messages:
            return 0
        
        success_count = 0
        
        for message in messages:
            try:
                success = await self.publish_data(
                    message['data_type'],
                    message['exchange'],
                    message['market_type'],
                    message['symbol'],
                    message['data']
                )
                if success:
                    success_count += 1
            except Exception as e:
                self.logger.error("批量发布消息失败", error=str(e))
        
        return success_count
    
    async def _flush_buffer(self):
        """刷新发布缓冲区"""
        async with self.buffer_lock:
            if not self.publish_buffer:
                return
            
            messages_to_publish = self.publish_buffer.copy()
            self.publish_buffer.clear()
            
            success_count = await self.batch_publish(messages_to_publish)
            self.logger.debug("缓冲区刷新完成", 
                            total=len(messages_to_publish),
                            success=success_count)
    
    async def _error_handler(self, error):
        """NATS错误处理器"""
        self.logger.error("NATS错误", error=str(error))
        self.stats.connection_errors += 1
    
    async def _closed_handler(self):
        """NATS连接关闭处理器"""
        self._is_connected = False
        self.logger.warning("NATS连接已关闭")

    async def _reconnected_handler(self):
        """NATS重连处理器"""
        self._is_connected = True
        self.logger.info("NATS重连成功")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取发布统计信息"""
        return {
            'total_published': self.stats.total_published,
            'successful_published': self.stats.successful_published,
            'failed_published': self.stats.failed_published,
            'success_rate': (
                self.stats.successful_published / max(self.stats.total_published, 1) * 100
            ),
            'last_publish_time': self.stats.last_publish_time,
            'connection_errors': self.stats.connection_errors,
            'publish_errors': self.stats.publish_errors,
            'is_connected': self.is_connected,
            'buffer_size': len(self.publish_buffer)
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取健康状态"""
        return {
            'connected': self.is_connected,
            'servers': self.config.servers,
            'client_name': self.config.client_name,
            'jetstream_available': self.js is not None,
            'stats': self.get_stats(),
            'last_check': datetime.now(timezone.utc).isoformat()
        }
