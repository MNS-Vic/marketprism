#!/usr/bin/env python3
"""
MarketPrism 简化热端数据存储服务 - Docker部署优化版
直接处理NATS消息并写入ClickHouse

🔄 Docker部署简化改造 (2025-08-02):
- ✅ 支持8种数据类型: orderbook, trade, funding_rate, open_interest, liquidation, lsr_top_position, lsr_all_account, volatility_index
- ✅ 优化ClickHouse建表脚本: 分离LSR数据类型，优化分区和索引
- ✅ 简化NATS订阅: 统一主题订阅，自动数据类型识别
- ✅ Docker集成: 与统一NATS容器完美集成
- ✅ 批量写入优化: 提高写入性能，减少数据库负载

特性:
- 从NATS JetStream订阅市场数据
- 实时写入ClickHouse热端数据库
- 支持8种数据类型，自动表映射
- 批量写入优化，性能提升
- 错误处理和重试机制
- 健康检查和监控
- Docker容器化部署
"""

import asyncio
import json
import os
import signal
import sys
import time
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union
import yaml
import nats
from nats.js import JetStreamContext
import aiohttp
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

# 导入优化的ClickHouse客户端
try:
    from services.data_storage_service.storage import get_clickhouse_client, close_clickhouse_client
except ImportError:
    # 如果模块路径不对，尝试其他路径
    sys.path.append(str(Path(__file__).parent))
    from storage import get_clickhouse_client, close_clickhouse_client
from aiohttp import web
from pathlib import Path
from decimal import Decimal, InvalidOperation
import traceback

# 可选引入 clickhouse-driver（优先使用TCP驱动，失败回退HTTP）
try:
    from clickhouse_driver import Client as CHClient
except Exception:
    CHClient = None


class DataValidationError(Exception):
    """数据验证错误"""
    pass


class DataFormatValidator:
    """数据格式验证器"""

    @staticmethod
    def validate_json_data(data: Any, field_name: str) -> str:
        """验证并转换JSON数据"""
        try:
            if data is None:
                return '[]'

            if isinstance(data, str):
                # 验证是否为有效JSON
                try:
                    json.loads(data)
                    return data
                except json.JSONDecodeError:
                    logging.warning(f"Invalid JSON string in {field_name}: {data[:100]}...")
                    return '[]'

            elif isinstance(data, (list, dict)):
                # 转换为标准JSON格式
                return json.dumps(data, ensure_ascii=False, separators=(',', ':'))

            else:
                logging.warning(f"Unexpected data type for {field_name}: {type(data)}")
                return '[]'

        except Exception as e:
            logging.error(f"Error validating JSON data for {field_name}: {e}")
            return '[]'

    @staticmethod
    def validate_numeric(value: Any, field_name: str, default: Union[int, float] = 0) -> Union[int, float]:
        """验证数值类型"""
        try:
            if value is None:
                return default

            if isinstance(value, (int, float)):
                return value

            if isinstance(value, str):
                try:
                    # 尝试转换为数字
                    if '.' in value:
                        return float(value)
                    else:
                        return int(value)
                except ValueError:
                    logging.warning(f"Cannot convert {field_name} to number: {value}")
                    return default

            return default

        except Exception as e:
            logging.error(f"Error validating numeric value for {field_name}: {e}")
            return default

    @staticmethod
    def validate_timestamp(timestamp: Any, field_name: str) -> datetime:
        """验证时间戳格式，返回无时区的 UTC datetime 对象供 ClickHouse 使用"""
        try:
            # 兜底：当前UTC时间（无时区）
            def now_utc_naive() -> datetime:
                return datetime.now(timezone.utc).replace(tzinfo=None)

            if timestamp is None:
                return now_utc_naive()

            if isinstance(timestamp, str):
                t = timestamp.strip()
                # 归一：去掉Z，替换T为空格，去除时区后缀
                t = t.replace('Z', '').replace('T', ' ')
                if '+' in t:
                    t = t.split('+')[0]
                # 去掉毫秒部分，只保留到秒
                if '.' in t:
                    t = t.split('.')[0]

                # 尝试解析为 datetime（无时区）
                try:
                    dt = datetime.strptime(t, '%Y-%m-%d %H:%M:%S')
                    return dt  # 返回无时区的 datetime
                except ValueError:
                    logging.warning(f"Failed to parse timestamp string: {t}")
                    return now_utc_naive()

            if isinstance(timestamp, datetime):
                # 转换为 UTC 并移除时区信息
                if timestamp.tzinfo is None:
                    return timestamp  # 已经是无时区的
                else:
                    return timestamp.astimezone(timezone.utc).replace(tzinfo=None)

            logging.warning(f"Unexpected timestamp type for {field_name}: {type(timestamp)}")
            return now_utc_naive()

        except Exception as e:
            logging.error(f"Error validating timestamp for {field_name}: {e}")
            return datetime.now(timezone.utc).replace(tzinfo=None)


class SimpleHotStorageService:
    """简化的热端数据存储服务"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化服务

        Args:
            config: 服务配置
        """
        self.config = self._validate_config(config)
        self.nats_config = self.config.get('nats', {})
        self.hot_storage_config = self.config.get('hot_storage', {})

        # 设置日志
        self._setup_logging()

        # 数据验证器
        self.validator = DataFormatValidator()

        # NATS连接
        self.nats_client: Optional[nats.NATS] = None
        self.jetstream: Optional[JetStreamContext] = None

        # 订阅管理
        self.subscriptions: Dict[str, Any] = {}

        # 运行状态
        self.is_running = False
        self.shutdown_event = asyncio.Event()

        # HTTP服务器
        self.app = None
        self.http_server = None
        self.http_port = self.config.get('http_port', 8080)

        # 统计信息
        self.stats = {
            "messages_received": 0,
            "messages_processed": 0,
            "messages_failed": 0,
            "validation_errors": 0,
            "retry_attempts": 0,
            "last_message_time": None,
            "last_error_time": None,
            "batch_inserts": 0,
            "batch_size_total": 0,
            "tcp_driver_hits": 0,
            "http_fallback_hits": 0
        }

        # 🔧 批量写入缓冲区
        self.batch_buffers = {}  # {data_type: [validated_data, ...]}
        self.batch_locks = {}    # {data_type: asyncio.Lock()}
        self.batch_tasks = {}    # {data_type: asyncio.Task}
        # NOTE(Phase2-Fix 2025-09-19):
        #   - 修复 deliver_policy=LAST 生效后，发现高频数据（trade/orderbook）吞吐瓶颈与偶发“批量处理停滞”
        #   - 将批量参数上调，并为 trade 引入更大批次阈值；适度延长 flush_interval 以提升 ClickHouse 写入效率
        #   - 这些参数在 E2E 验证中带来稳定的批量插入与较低错误率（详见 logs/e2e_report.txt）
        self.batch_config = {
            "max_batch_size": 100,      # 提升批量大小以提高吞吐量
            "flush_interval": 1.0,      # 适度延长间隔以积累更多数据
            "high_freq_types": {"orderbook", "trade"},  # 高频数据类型
            "low_freq_batch_size": 20,  # 提升低频数据批量大小
            "orderbook_flush_interval": 0.8,  # 订单簿稍微延长以积累更多数据
            "trade_batch_size": 150,    # trade 专用更大批量
        }

        # ClickHouse 驱动客户端（懒初始化）
        self._ch_client = None

        # 重试配置
        self.retry_config = {
            "max_retries": self.config.get('retry', {}).get('max_retries', 3),
            "retry_delay": self.config.get('retry', {}).get('delay_seconds', 1),
            "backoff_multiplier": self.config.get('retry', {}).get('backoff_multiplier', 2)
        }

    def _validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """验证配置文件"""
        try:
            # 验证必需的配置项
            required_sections = ['nats', 'hot_storage']
            for section in required_sections:
                if section not in config:
                    raise DataValidationError(f"Missing required config section: {section}")

            # 验证NATS配置（统一使用 servers 列表，兼容历史 url 与环境变量）
            nats_config = config['nats']
            servers = nats_config.get('servers')
            if not servers:
                env_url = os.getenv('MARKETPRISM_NATS_URL') or os.getenv('NATS_URL') or nats_config.get('url', 'nats://localhost:4222')
                nats_config['servers'] = [env_url]

            # 验证ClickHouse配置
            ch_config = config['hot_storage']
            defaults = {
                'clickhouse_host': 'localhost',
                'clickhouse_http_port': 8123,
                'clickhouse_tcp_port': 9000,
                'clickhouse_database': 'marketprism_hot',
                'clickhouse_user': 'default',
                'clickhouse_password': '',
                'use_clickhouse_driver': True
            }

            for key, default_value in defaults.items():
                if key not in ch_config:
                    ch_config[key] = default_value

            # 设置默认重试配置
            if 'retry' not in config:
                config['retry'] = {
                    'max_retries': 3,
                    'delay_seconds': 1,
                    'backoff_multiplier': 2
                }

            return config

        except Exception as e:
            print(f"❌ 配置验证失败: {e}")
            raise

    def _setup_logging(self):
        """设置日志"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('/tmp/hot_storage_service.log')
            ]
        )
        self.logger = logging.getLogger('HotStorageService')

    async def start(self):
        """启动服务"""
        try:
            print("🚀 启动简化热端数据存储服务")

            # 连接NATS
            await self._connect_nats()

            # 设置订阅
            await self._setup_subscriptions()

            # 启动HTTP服务器
            await self.setup_http_server()

            # 设置信号处理
            self._setup_signal_handlers()

            self.is_running = True
            self.start_time = time.time()
            print("✅ 简化热端数据存储服务已启动")

            # 等待关闭信号
            await self.shutdown_event.wait()

        except Exception as e:
            print(f"❌ 服务启动失败: {e}")
            raise

    async def _connect_nats(self):
        """连接NATS服务器"""
        try:
            # 统一读取 servers，兼容历史 url 与环境变量
            env_url = os.getenv('MARKETPRISM_NATS_URL') or os.getenv('NATS_URL')
            servers = self.nats_config.get('servers') or ([env_url] if env_url else [self.nats_config.get('url', 'nats://localhost:4222')])

            # Define callback functions
            async def error_cb(e):
                print(f"NATS error: {e}")

            async def disconnected_cb():
                print("NATS disconnected")

            async def reconnected_cb():
                print("NATS reconnected")

            async def closed_cb():
                print("NATS closed")

            self.nats_client = await nats.connect(
                servers=servers,
                max_reconnect_attempts=10,
                reconnect_time_wait=2,
                error_cb=error_cb,
                disconnected_cb=disconnected_cb,
                reconnected_cb=reconnected_cb,
                closed_cb=closed_cb
            )

            # 获取JetStream上下文
            self.jetstream = self.nats_client.jetstream()

            print(f"✅ NATS connection established: {', '.join(servers)}")

        except Exception as e:
            print(f"❌ NATS连接失败: {e}")
            raise

    async def _setup_subscriptions(self):
        """设置NATS订阅"""
        try:
            # 订阅各种数据类型 - 8种数据类型
            data_types = ["orderbook", "trade", "funding_rate", "open_interest",
                         "liquidation", "lsr_top_position", "lsr_all_account", "volatility_index"]

            for data_type in data_types:
                await self._subscribe_to_data_type(data_type)

            print(f"✅ NATS订阅设置完成，成功订阅数量: {len(self.subscriptions)}")

            # 只要有至少一个订阅成功就继续
            if len(self.subscriptions) == 0:
                raise Exception("没有成功创建任何订阅")

        except Exception as e:
            print(f"❌ NATS订阅设置失败: {e}")
            print(traceback.format_exc())
            raise

    async def _subscribe_to_data_type(self, data_type: str):
        """订阅特定数据类型 - 纯JetStream Pull消费者模式"""
        try:
            # 构建主题模式 - 与发布端统一
            subject_mapping = {
                "funding_rate": "funding_rate.>",
                "open_interest": "open_interest.>",
                "lsr_top_position": "lsr_top_position.>",  # 顶级大户多空持仓比例
                "lsr_all_account": "lsr_all_account.>",  # 全市场多空持仓人数比例
                "orderbook": "orderbook.>",  # 订单簿
                "trade": "trade.>",  # 成交数据
                "liquidation": "liquidation.>",  # 强平数据
                "volatility_index": "volatility_index.>",  # 波动率指数
            }

            if data_type in subject_mapping:
                subject_pattern = subject_mapping[data_type]
            else:
                # 其他类型直接使用下划线命名
                subject_pattern = f"{data_type}.>"

            # 确定流名称 - 订单簿使用独立ORDERBOOK_SNAP流，其他使用MARKET_DATA流
            if data_type == "orderbook":
                stream_name = "ORDERBOOK_SNAP"
            else:
                stream_name = "MARKET_DATA"

            print(f"设置JetStream订阅: {data_type} -> {subject_pattern} (流: {stream_name})")

            # 等待 JetStream Stream 可用
            js_ready = False
            for attempt in range(10):  # 最长重试 ~20s
                try:
                    await self.jetstream._jsm.stream_info(stream_name)
                    js_ready = True
                    print(f"✅ 流 {stream_name} 可用")
                    break
                except Exception as e:
                    print(f"⏳ 等待流 {stream_name} 可用... (尝试 {attempt+1}/10)")
                    await asyncio.sleep(2)

            if not js_ready:
                raise Exception(f"流 {stream_name} 在20秒内未就绪")

            # JetStream订阅（纯JetStream模式）
            try:
                # 定义协程回调，绑定当前数据类型
                async def _cb(msg, _dt=data_type):
                    await self._handle_message(msg, _dt)

                # 使用新的 durable 名称以避免复用历史消费位置，确保本次启动从“新消息”开始
                new_durable = f"simple_hot_storage_realtime_{data_type}"

                # 🔧 检查并删除不符合要求的历史consumer，确保使用LAST策略（按实际流检查）
                try:
                    existing_consumer = await self.jetstream._jsm.consumer_info(stream_name, new_durable)
                    existing_policy = existing_consumer.config.deliver_policy
                    existing_max_ack = existing_consumer.config.max_ack_pending

                    # 如果现有consumer不是LAST策略或max_ack_pending不符合预期，则删除重建
                    expected_max_ack = 5000 if data_type == "orderbook" else 2000
                    if (existing_policy != nats.js.api.DeliverPolicy.LAST or
                        existing_max_ack != expected_max_ack):
                        print(f"🧹 删除不符合要求的consumer: {new_durable} (policy={existing_policy}, max_ack={existing_max_ack})")
                        await self.jetstream._jsm.delete_consumer(stream_name, new_durable)
                except nats.js.errors.NotFoundError:
                    # Consumer不存在，正常情况
                    pass
                except Exception as e:
                    print(f"⚠️ 检查consumer状态时出错: {e}")

                # 🔧 明确绑定到指定Stream并显式创建Consumer，确保使用LAST策略
                # 不覆盖前面根据数据类型确定的 stream_name

                # 先删除历史不符合要求的consumer（若仍存在）
                try:
                    await self.jetstream._jsm.delete_consumer(stream_name, new_durable)
                except Exception:
                    pass

                # 使用 push consumer（指定 deliver_subject）以支持回调式消费
                deliver_subject = f"_deliver.{new_durable}.{int(time.time())}"
                desired_config = nats.js.api.ConsumerConfig(
                    durable_name=new_durable,
                    deliver_policy=nats.js.api.DeliverPolicy.LAST,  # 从最新消息开始，避免历史回放
                    ack_policy=nats.js.api.AckPolicy.EXPLICIT,
                    max_deliver=3,
                    ack_wait=60,    # 放宽ACK等待，便于批处理与并发
                    max_ack_pending=(5000 if data_type == "orderbook" else 2000),
                    filter_subject=subject_pattern,  # 关键：限定到对应数据类型的主题
                    deliver_subject=deliver_subject,
                )

                # 显式创建/确保存在
                try:
                    await self.jetstream._jsm.add_consumer(stream_name, desired_config)
                except Exception:
                    # 若已存在则忽略
                    pass

                # 绑定到已创建的consumer，显式指定stream避免自动绑定造成的默认策略
                subscription = await self.jetstream.subscribe(
                    subject=subject_pattern,
                    cb=_cb,
                    durable=new_durable,
                    stream=stream_name
                )
                print(f"✅ 订阅成功(JS): {data_type} -> {subject_pattern} (durable={new_durable}, enforced_policy=LAST, max_ack_pending={(5000 if data_type == 'orderbook' else 2000)})")
                self.subscriptions[data_type] = subscription
                return
            except Exception as js_err:
                print(f"❌ 订阅失败 {data_type} (JetStream): {js_err} — 尝试回退到 Core NATS")
                print(traceback.format_exc())

            # 回退到 Core NATS（使用协程回调）
            try:
                subscription = await self.nats_client.subscribe(
                    subject_pattern,
                    cb=_cb
                )
                self.subscriptions[data_type] = subscription
                print(f"✅ 订阅成功(Core): {data_type} -> {subject_pattern}")
            except Exception as core_err:
                print(f"❌ Core subscription failed {data_type}: {core_err}")
                print(traceback.format_exc())
                # Don't raise exception, continue with other subscriptions
                pass

        except Exception as e:
            print(f"❌ 订阅 {data_type} 失败: {e}")
            print(traceback.format_exc())

    async def _handle_message(self, msg, data_type: str):
        """处理NATS消息，包含重试机制"""
        try:
            # 更新统计
            self.stats["messages_received"] += 1
            # 统一为 epoch 秒，便于 Prometheus 指标直接输出
            self.stats["last_message_time"] = time.time()

            # 解析消息
            try:
                data = json.loads(msg.data.decode())
            except json.JSONDecodeError as e:
                self.logger.error(f"消息JSON解析失败 {data_type}: {e}")
                try:
                    await msg.nak()
                except Exception:
                    pass
                self.stats["messages_failed"] += 1
                self.stats["validation_errors"] += 1
                return

            # 验证数据格式
            try:
                validated_data = self._validate_message_data(data, data_type)
            except DataValidationError as e:
                self.logger.error(f"数据验证失败 {data_type}: {e}")
                try:
                    await msg.nak()
                except Exception:
                    pass
                self.stats["validation_errors"] += 1
                return

            #   :       
            #    orderbook  trade  
            success = False
            if data_type in self.batch_config.get("high_freq_types", {"orderbook", "trade"}):
                enq = await self._store_to_batch_buffer(data_type, validated_data)
                if enq:
                    #  ->  
                    try:
                        await msg.ack()
                    except Exception:
                        pass
                    self.stats["messages_processed"] += 1
                    print(f"✅ 已入队等待批量: {data_type} -> {msg.subject}")
                    success = True
                else:
                    # 批量入队失败则回退为单条入库
                    success = await self._store_to_clickhouse_with_retry(data_type, validated_data)
                    if success:
                        try:
                            await msg.ack()
                        except Exception:
                            pass
                        self.stats["messages_processed"] += 1
                        print(f"✅ 消息处理成功: {data_type} -> {msg.subject}")
            else:
                # 低频类型：单条入库并成功后ACK
                success = await self._store_to_clickhouse_with_retry(data_type, validated_data)
                if success:
                    try:
                        await msg.ack()
                    except Exception:
                        pass
                    self.stats["messages_processed"] += 1
                    print(f"✅ 消息处理成功: {data_type} -> {msg.subject}")

            if success:
                pass
            else:
                #  
                try:
                    await msg.nak()
                except Exception:
                    pass
                self.stats["messages_failed"] += 1
                # 统一为 epoch 秒，便于 Prometheus 指标输出
                self.stats["last_error_time"] = time.time()
                print(f"❌ : {data_type} -> {msg.subject}")

        except Exception as e:
            # 处理异常，拒绝消息（仅 JetStream 消息支持 NAK）
            try:
                await msg.nak()
            except Exception:
                pass

            self.stats["messages_failed"] += 1
            self.stats["last_error_time"] = datetime.now(timezone.utc)
            self.logger.error(f"消息处理异常 {data_type}: {e}")
            print(f"❌ 消息处理异常 {data_type}: {e}")

    def _validate_message_data(self, data: Dict[str, Any], data_type: str) -> Dict[str, Any]:
        """验证消息数据格式"""
        try:
            validated_data = {}

            # 验证基础字段
            validated_data['timestamp'] = self.validator.validate_timestamp(
                data.get('timestamp'), 'timestamp'
            )
            validated_data['exchange'] = str(data.get('exchange', ''))
            validated_data['market_type'] = str(data.get('market_type', ''))
            validated_data['symbol'] = str(data.get('symbol', ''))
            validated_data['data_source'] = str(data.get('data_source', 'simple_hot_storage'))

            # 根据数据类型验证特定字段
            if data_type in ['orderbook']:
                validated_data['last_update_id'] = self.validator.validate_numeric(
                    data.get('last_update_id'), 'last_update_id', 0
                )

                # 处理订单簿数据并提取最优价格
                bids_data = data.get('bids', '[]')
                asks_data = data.get('asks', '[]')

                validated_data['bids'] = self.validator.validate_json_data(bids_data, 'bids')
                validated_data['asks'] = self.validator.validate_json_data(asks_data, 'asks')

                # 提取最优买卖价
                try:
                    import json
                    bids_list = json.loads(bids_data) if isinstance(bids_data, str) else bids_data
                    asks_list = json.loads(asks_data) if isinstance(asks_data, str) else asks_data

                    # 提取最优买价（bids第一个）
                    if bids_list and len(bids_list) > 0:
                        best_bid = bids_list[0]
                        if isinstance(best_bid, dict):
                            validated_data['best_bid_price'] = float(best_bid.get('price', 0))
                            validated_data['best_bid_quantity'] = float(best_bid.get('quantity', 0))
                        elif isinstance(best_bid, list) and len(best_bid) >= 2:
                            validated_data['best_bid_price'] = float(best_bid[0])
                            validated_data['best_bid_quantity'] = float(best_bid[1])
                        else:
                            validated_data['best_bid_price'] = 0
                            validated_data['best_bid_quantity'] = 0
                    else:
                        validated_data['best_bid_price'] = 0
                        validated_data['best_bid_quantity'] = 0

                    # 提取最优卖价（asks第一个）
                    if asks_list and len(asks_list) > 0:
                        best_ask = asks_list[0]
                        if isinstance(best_ask, dict):
                            validated_data['best_ask_price'] = float(best_ask.get('price', 0))
                            validated_data['best_ask_quantity'] = float(best_ask.get('quantity', 0))
                        elif isinstance(best_ask, list) and len(best_ask) >= 2:
                            validated_data['best_ask_price'] = float(best_ask[0])
                            validated_data['best_ask_quantity'] = float(best_ask[1])
                        else:
                            validated_data['best_ask_price'] = 0
                            validated_data['best_ask_quantity'] = 0
                    else:
                        validated_data['best_ask_price'] = 0
                        validated_data['best_ask_quantity'] = 0

                    # 计算bids和asks数量
                    validated_data['bids_count'] = len(bids_list) if bids_list else 0
                    validated_data['asks_count'] = len(asks_list) if asks_list else 0

                except Exception as e:
                    print(f"⚠️ 订单簿价格提取失败: {e}")
                    validated_data['best_bid_price'] = 0
                    validated_data['best_ask_price'] = 0
                    validated_data['best_bid_quantity'] = 0
                    validated_data['best_ask_quantity'] = 0
                    validated_data['bids_count'] = 0
                    validated_data['asks_count'] = 0

            elif data_type in ['trade']:
                validated_data['trade_id'] = str(data.get('trade_id', ''))
                validated_data['price'] = self.validator.validate_numeric(
                    data.get('price'), 'price', 0.0
                )
                validated_data['quantity'] = self.validator.validate_numeric(
                    data.get('quantity'), 'quantity', 0.0
                )
                validated_data['side'] = str(data.get('side', ''))
                validated_data['is_maker'] = bool(data.get('is_maker', False))
                # 兼容表结构：若未提供 trade_time 则使用消息 timestamp
                validated_data['trade_time'] = self.validator.validate_timestamp(
                    data.get('trade_time') or data.get('timestamp'), 'trade_time'
                )

            elif data_type in ['funding_rate']:
                # 🔧 修复：从 current_funding_rate 字段读取数据（与 Collector 发布的字段名一致）
                validated_data['funding_rate'] = self.validator.validate_numeric(
                    data.get('current_funding_rate'), 'current_funding_rate', 0.0
                )
                validated_data['funding_time'] = self.validator.validate_timestamp(
                    data.get('funding_time'), 'funding_time'
                )
                validated_data['next_funding_time'] = self.validator.validate_timestamp(
                    data.get('next_funding_time'), 'next_funding_time'
                )

            elif data_type in ['liquidation']:
                # 🔧 修复：添加 liquidation 数据验证逻辑
                validated_data['side'] = str(data.get('side', ''))
                validated_data['price'] = self.validator.validate_numeric(
                    data.get('price'), 'price', 0.0
                )
                validated_data['quantity'] = self.validator.validate_numeric(
                    data.get('quantity'), 'quantity', 0.0
                )
                validated_data['liquidation_time'] = self.validator.validate_timestamp(
                    data.get('liquidation_time') or data.get('timestamp'), 'liquidation_time'
                )


            elif data_type in ['volatility_index']:
                # 🔧 新增：添加 volatility_index 数据验证逻辑
                validated_data['volatility_index'] = self.validator.validate_numeric(
                    data.get('volatility_index'), 'volatility_index', 0.0
                )
                validated_data['index_value'] = self.validator.validate_numeric(
                    data.get('volatility_index'), 'volatility_index', 0.0  # 兼容字段名
                )
                validated_data['underlying_asset'] = str(data.get('underlying_asset', ''))
                validated_data['maturity_date'] = self.validator.validate_timestamp(
                    data.get('maturity_date'), 'maturity_date'
                )

            elif data_type in ['open_interest']:
                # 添加 open_interest 数据验证逻辑
                validated_data['open_interest'] = self.validator.validate_numeric(
                    data.get('open_interest'), 'open_interest', 0.0
                )
                validated_data['open_interest_value'] = self.validator.validate_numeric(
                    data.get('open_interest_value'), 'open_interest_value', 0.0
                )

            elif data_type in ['lsr_top_position']:
                # 添加 lsr_top_position 数据验证逻辑
                validated_data['long_position_ratio'] = self.validator.validate_numeric(
                    data.get('long_position_ratio'), 'long_position_ratio', 0.0
                )
                validated_data['short_position_ratio'] = self.validator.validate_numeric(
                    data.get('short_position_ratio'), 'short_position_ratio', 0.0
                )
                validated_data['period'] = str(data.get('period', ''))

            elif data_type in ['lsr_all_account']:
                # 添加 lsr_all_account 数据验证逻辑
                validated_data['long_account_ratio'] = self.validator.validate_numeric(
                    data.get('long_account_ratio'), 'long_account_ratio', 0.0
                )
                validated_data['short_account_ratio'] = self.validator.validate_numeric(
                    data.get('short_account_ratio'), 'short_account_ratio', 0.0
                )
                validated_data['period'] = str(data.get('period', ''))

            # 添加其他数据类型的验证...

            return validated_data

        except Exception as e:
            raise DataValidationError(f"数据验证失败: {e}")

    async def _store_to_clickhouse_with_retry(self, data_type: str, data: Dict[str, Any]) -> bool:
        """带重试机制的ClickHouse存储"""
        max_retries = self.retry_config['max_retries']
        delay = self.retry_config['retry_delay']
        backoff = self.retry_config['backoff_multiplier']

        for attempt in range(max_retries + 1):
            try:
                success = await self._store_to_clickhouse(data_type, data)
                if success:
                    if attempt > 0:
                        self.logger.info(f"重试成功 {data_type}，尝试次数: {attempt + 1}")
                    return True

                if attempt < max_retries:
                    self.stats["retry_attempts"] += 1
                    await asyncio.sleep(delay)
                    delay *= backoff


            except Exception as e:
                self.logger.error(f"存储尝试 {attempt + 1} 失败 {data_type}: {e}")
                if attempt < max_retries:
                    self.stats["retry_attempts"] += 1
                    await asyncio.sleep(delay)
                    delay *= backoff
                else:
                    self.logger.error(f"所有重试尝试失败 {data_type}")

        return False

    def _get_ch_client(self):
        """获取或初始化 ClickHouse TCP 客户端"""
        if getattr(self, "_ch_client", None) is not None:
            return self._ch_client
        if not CHClient or not self.hot_storage_config.get('use_clickhouse_driver', True):
            return None
        try:
            host = self.hot_storage_config.get('clickhouse_host', 'localhost')
            port = int(self.hot_storage_config.get('clickhouse_tcp_port', 9000))
            user = self.hot_storage_config.get('clickhouse_user', 'default')
            password = self.hot_storage_config.get('clickhouse_password', '')
            database = self.hot_storage_config.get('clickhouse_database', 'marketprism_hot')
            self._ch_client = CHClient(host=host, port=port, user=user, password=password, database=database)
            return self._ch_client
        except Exception as e:
            print(f"⚠️ 初始化 ClickHouse 驱动失败，将回退HTTP: {e}")
            self._ch_client = None
            return None

    async def _store_to_batch_buffer(self, data_type: str, data: Dict[str, Any]) -> bool:
        """将数据添加到批量缓冲区"""
        try:
            # 初始化数据类型的缓冲区和锁
            if data_type not in self.batch_buffers:
                self.batch_buffers[data_type] = []
                self.batch_locks[data_type] = asyncio.Lock()

            async with self.batch_locks[data_type]:
                self.batch_buffers[data_type].append(data)

                # 确定批量大小阈值（动态调整）
                if data_type == "trade":
                    batch_threshold = self.batch_config.get("trade_batch_size", 150)
                elif data_type in self.batch_config["high_freq_types"]:
                    batch_threshold = self.batch_config["max_batch_size"]
                else:
                    batch_threshold = self.batch_config["low_freq_batch_size"]

                # 检查是否需要立即刷新
                if len(self.batch_buffers[data_type]) >= batch_threshold:
                    await self._flush_batch_buffer(data_type)

                # 启动定时刷新任务（如果尚未启动）
                if data_type not in self.batch_tasks or self.batch_tasks[data_type].done():
                    self.batch_tasks[data_type] = asyncio.create_task(
                        self._batch_flush_timer(data_type)
                    )

            return True

        except Exception as e:
            self.logger.error(f"批量缓冲失败 {data_type}: {e}")
            # 回退到单条存储
            return await self._store_to_clickhouse_with_retry(data_type, data)

    async def _batch_flush_timer(self, data_type: str):
        """批量刷新定时器"""
        try:
            while self.is_running:
                # 订单簿使用更快的刷新间隔
                if data_type == "orderbook":
                    flush_interval = self.batch_config.get("orderbook_flush_interval", 0.5)
                else:
                    flush_interval = self.batch_config["flush_interval"]

                await asyncio.sleep(flush_interval)

                async with self.batch_locks[data_type]:
                    if self.batch_buffers[data_type]:
                        await self._flush_batch_buffer(data_type)

        except asyncio.CancelledError:
            # 服务停止时刷新剩余数据
            async with self.batch_locks[data_type]:
                if self.batch_buffers[data_type]:
                    await self._flush_batch_buffer(data_type)
        except Exception as e:
            self.logger.error(f"批量刷新定时器异常 {data_type}: {e}")

    async def _flush_batch_buffer(self, data_type: str):
        """刷新批量缓冲区到ClickHouse"""
        if not self.batch_buffers[data_type]:
            return

        batch_data = self.batch_buffers[data_type].copy()
        self.batch_buffers[data_type].clear()

        try:
            success = await self._batch_insert_to_clickhouse(data_type, batch_data)
            if success:
                self.stats["batch_inserts"] += 1
                self.stats["batch_size_total"] += len(batch_data)
                print(f"✅ 批量插入成功: {data_type} -> {len(batch_data)} 条记录")
            else:
                # 批量插入失败，回退到单条插入
                print(f"⚠️ 批量插入失败，回退到单条插入: {data_type}")
                for data in batch_data:
                    await self._store_to_clickhouse_with_retry(data_type, data)

        except Exception as e:
            self.logger.error(f"批量刷新失败 {data_type}: {e}")
            # 回退到单条插入
            for data in batch_data:
                await self._store_to_clickhouse_with_retry(data_type, data)

    async def _store_to_clickhouse(self, data_type: str, data: Dict[str, Any]) -> bool:
        """存储数据到ClickHouse（优先TCP驱动，失败回退HTTP）"""
        try:
            host = self.hot_storage_config.get('clickhouse_host', 'localhost')
            http_port = self.hot_storage_config.get('clickhouse_http_port', 8123)
            database = self.hot_storage_config.get('clickhouse_database', 'marketprism_hot')

            # 获取表名 - 更新为8种数据类型的分离表
            table_mapping = {
                "orderbook": "orderbooks",
                "trade": "trades",
                "funding_rate": "funding_rates",
                "open_interest": "open_interests",
                "liquidation": "liquidations",
                "lsr_top_position": "lsr_top_positions",    # 分离的LSR顶级持仓表
                "lsr_all_account": "lsr_all_accounts",      # 分离的LSR全账户表
                "volatility_index": "volatility_indices"
            }
            table_name = table_mapping.get(data_type, data_type)

            # 构建插入SQL
            insert_sql = self._build_insert_sql(table_name, data)

            # 1) 尝试使用 TCP 驱动
            ch = self._get_ch_client()
            if ch:
                try:
                    ch.execute(insert_sql)
                    return True
                except Exception as e:
                    print(f"⚠️ ClickHouse驱动执行失败，回退HTTP: {e}")

            # 2) 回退到 HTTP
            url = f"http://{host}:{http_port}/?database={database}"
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=insert_sql) as response:
                    if response.status == 200:
                        return True
                    else:
                        error_text = await response.text()
                        print(f"❌ ClickHouse插入失败: {error_text}")
                        return False

        except Exception as e:
            print(f"❌ 存储到ClickHouse异常: {e}")
            return False

    async def _batch_insert_to_clickhouse(self, data_type: str, batch_data: List[Dict[str, Any]]) -> bool:
        """批量插入数据到ClickHouse（优先TCP驱动，失败回退HTTP）"""
        if not batch_data:
            return True

        try:
            host = self.hot_storage_config.get('clickhouse_host', 'localhost')
            http_port = self.hot_storage_config.get('clickhouse_http_port', 8123)
            database = self.hot_storage_config.get('clickhouse_database', 'marketprism_hot')

            # 获取表名
            table_mapping = {
                "orderbook": "orderbooks",
                "trade": "trades",
                "funding_rate": "funding_rates",
                "open_interest": "open_interests",
                "liquidation": "liquidations",
                "lsr_top_position": "lsr_top_positions",
                "lsr_all_account": "lsr_all_accounts",
                "volatility_index": "volatility_indices"
            }
            table_name = table_mapping.get(data_type, data_type)

            # 构建批量插入SQL
            batch_sql = self._build_batch_insert_sql(table_name, batch_data)
            if not batch_sql:
                return False

            # 1) 先尝试 TCP 驱动
            ch = self._get_ch_client()
            if ch:
                try:
                    ch.execute(batch_sql)
                    self.stats["tcp_driver_hits"] += 1
                    if self.stats["tcp_driver_hits"] % 50 == 0:  # 每50次打印一次统计
                        tcp_total = self.stats["tcp_driver_hits"]
                        http_total = self.stats["http_fallback_hits"]
                        tcp_rate = tcp_total / (tcp_total + http_total) * 100 if (tcp_total + http_total) > 0 else 0
                        print(f"📊 ClickHouse驱动统计: TCP={tcp_total}, HTTP={http_total}, TCP命中率={tcp_rate:.1f}%")
                    return True
                except Exception as e:
                    print(f"⚠️ ClickHouse驱动批量执行失败，回退HTTP: {e}")

            # 2) 回退到 HTTP
            self.stats["http_fallback_hits"] += 1
            url = f"http://{host}:{http_port}/?database={database}"

            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=batch_sql) as response:
                    if response.status == 200:
                        return True
                    else:
                        error_text = await response.text()
                        print(f"❌ ClickHouse批量插入失败: {error_text}")
                        return False

        except Exception as e:
            print(f"❌ 批量插入到ClickHouse异常: {e}")
            return False

    def _build_batch_insert_sql(self, table_name: str, batch_data: List[Dict[str, Any]]) -> str:
        """构建批量插入SQL"""
        if not batch_data:
            return ""

        try:
            # 使用第一条记录确定字段结构
            first_record = batch_data[0]

            # 基础字段
            fields = ['timestamp', 'exchange', 'market_type', 'symbol', 'data_source']

            # 根据数据类型添加特定字段
            if table_name == 'orderbooks':
                fields.extend([
                    'last_update_id', 'bids_count', 'asks_count',
                    'best_bid_price', 'best_ask_price', 'best_bid_quantity', 'best_ask_quantity',
                    'bids', 'asks'
                ])
            elif table_name == 'trades':
                fields.extend(['trade_id', 'price', 'quantity', 'side', 'is_maker', 'trade_time'])
            elif table_name == 'funding_rates':
                fields.extend(['funding_rate', 'funding_time', 'next_funding_time'])
            elif table_name == 'liquidations':
                fields.extend(['side', 'price', 'quantity', 'liquidation_time'])
            elif table_name == 'lsr_top_positions':
                fields.extend(['long_position_ratio', 'short_position_ratio', 'period'])
            elif table_name == 'lsr_all_accounts':
                fields.extend(['long_account_ratio', 'short_account_ratio', 'period'])

            # 构建VALUES子句
            values_list = []
            for data in batch_data:
                values = self._build_values_for_record(table_name, data, fields)
                if values:
                    values_list.append(f"({', '.join(values)})")

            if not values_list:
                return ""

            # 构建完整SQL
            fields_str = ', '.join(fields)
            values_str = ',\n    '.join(values_list)

            sql = f"INSERT INTO {table_name} ({fields_str}) VALUES\n    {values_str}"
            return sql

        except Exception as e:
            print(f"❌ 构建批量SQL失败: {e}")
            return ""

    def _build_insert_sql(self, table_name: str, data: Dict[str, Any]) -> str:
        """构建插入SQL（使用已验证的数据）"""
        try:
            # 基础字段（数据已经过验证）
            fields = ['timestamp', 'exchange', 'market_type', 'symbol', 'data_source']
            values = [
                f"'{data['timestamp']}'",
                f"'{data['exchange']}'",
                f"'{data['market_type']}'",
                f"'{data['symbol']}'",
                f"'{data['data_source']}'"
            ]

            # 根据数据类型添加特定字段（数据已经过验证和格式化）
            if table_name == 'orderbooks':
                # 写入完整的订单簿数据，包括最优价格
                fields.extend([
                    'last_update_id', 'bids_count', 'asks_count',
                    'best_bid_price', 'best_ask_price', 'best_bid_quantity', 'best_ask_quantity',
                    'bids', 'asks'
                ])
                values.extend([
                    str(data['last_update_id']),
                    str(data['bids_count']),
                    str(data['asks_count']),
                    str(data['best_bid_price']),
                    str(data['best_ask_price']),
                    str(data['best_bid_quantity']),
                    str(data['best_ask_quantity']),
                    f"'{data['bids']}'",  # 已经是标准JSON格式
                    f"'{data['asks']}'"   # 已经是标准JSON格式
                ])

            elif table_name == 'trades':
                fields.extend(['trade_id', 'price', 'quantity', 'side', 'is_maker', 'trade_time'])
                values.extend([
                    f"'{data['trade_id']}'",
                    str(data['price']),
                    str(data['quantity']),
                    f"'{data['side']}'",
                    str(data['is_maker']).lower(),
                    f"'{data.get('trade_time', data['timestamp'])}'"
                ])

            elif table_name == 'funding_rates':
                fields.extend(['funding_rate', 'funding_time', 'next_funding_time'])
                values.extend([
                    str(data['funding_rate']),
                    f"'{data['funding_time']}'",  # 已经格式化
                    f"'{data['next_funding_time']}'"  # 已经格式化
                ])

            elif table_name == 'liquidations':
                fields.extend(['side', 'price', 'quantity', 'liquidation_time'])
                values.extend([
                    f"'{data.get('side', '')}'",
                    str(data['price']),
                    str(data['quantity']),
                    f"'{data.get('liquidation_time', data['timestamp'])}'"
                ])

            elif table_name == 'lsr_top_positions':
                # 处理LSR顶级持仓比例数据
                fields.extend(['long_position_ratio', 'short_position_ratio', 'period'])
                values.extend([
                    str(data.get('long_position_ratio', 0)),
                    str(data.get('short_position_ratio', 0)),
                    f"'{data.get('period', '5m')}'"
                ])

            elif table_name == 'lsr_all_accounts':
                # 处理LSR全账户比例数据
                fields.extend(['long_account_ratio', 'short_account_ratio', 'period'])
                values.extend([
                    str(data.get('long_account_ratio', 0)),
                    str(data.get('short_account_ratio', 0)),
                    f"'{data.get('period', '5m')}'"
                ])

            # 构建SQL
            fields_str = ', '.join(fields)
            values_str = ', '.join(values)

            sql = f"INSERT INTO {table_name} ({fields_str}) VALUES ({values_str})"
            return sql

        except Exception as e:
            print(f"❌ 构建SQL失败: {e}")
            return ""

    def _build_values_for_record(self, table_name: str, data: Dict[str, Any], fields: List[str]) -> List[str]:
        """为单条记录构建VALUES"""
        try:
            values = []

            for field in fields:
                if field == 'timestamp':
                    values.append(f"'{data['timestamp']}'")
                elif field == 'exchange':
                    values.append(f"'{data['exchange']}'")
                elif field == 'market_type':
                    values.append(f"'{data['market_type']}'")
                elif field == 'symbol':
                    values.append(f"'{data['symbol']}'")
                elif field == 'data_source':
                    values.append(f"'{data['data_source']}'")
                elif field in ['last_update_id', 'bids_count', 'asks_count']:
                    values.append(str(data.get(field, 0)))
                elif field in ['best_bid_price', 'best_ask_price', 'best_bid_quantity', 'best_ask_quantity']:
                    values.append(str(data.get(field, 0)))
                elif field in ['bids', 'asks']:
                    values.append(f"'{data.get(field, '[]')}'")
                elif field == 'trade_id':
                    values.append(f"'{data.get(field, '')}'")
                elif field in ['price', 'quantity']:
                    values.append(str(data.get(field, 0)))
                elif field == 'side':
                    values.append(f"'{data.get(field, '')}'")
                elif field == 'is_maker':
                    values.append(str(data.get(field, False)).lower())
                elif field == 'trade_time':
                    values.append(f"'{data.get(field, data.get('timestamp', ''))}'")
                elif field == 'funding_rate':
                    values.append(str(data.get(field, 0)))
                elif field in ['funding_time', 'next_funding_time']:
                    values.append(f"'{data.get(field, data.get('timestamp', ''))}'")
                elif field == 'liquidation_time':
                    values.append(f"'{data.get(field, data.get('timestamp', ''))}'")
                elif field in ['long_position_ratio', 'short_position_ratio', 'long_account_ratio', 'short_account_ratio']:
                    values.append(str(data.get(field, 0)))
                elif field == 'period':
                    values.append(f"'{data.get(field, '5m')}'")
                else:
                    values.append("''")  # 默认空字符串

            return values

        except Exception as e:
            print(f"❌ 构建记录VALUES失败: {e}")
            return []

    async def stop(self):
        """停止服务"""
        try:
            print("🛑 停止简化热端数据存储服务")

            self.is_running = False

            # 🔧 刷新所有批量缓冲区
            print("🔄 刷新批量缓冲区...")
            for data_type in list(self.batch_buffers.keys()):
                try:
                    if data_type in self.batch_locks:
                        async with self.batch_locks[data_type]:
                            if self.batch_buffers[data_type]:
                                await self._flush_batch_buffer(data_type)
                                print(f"✅ 已刷新 {data_type} 缓冲区")
                except Exception as e:
                    print(f"❌ 刷新缓冲区失败 {data_type}: {e}")

            # 🔧 取消批量刷新任务
            for data_type, task in self.batch_tasks.items():
                try:
                    if not task.done():
                        task.cancel()
                        await task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    print(f"❌ 取消批量任务失败 {data_type}: {e}")

            # 关闭订阅
            for data_type, subscription in self.subscriptions.items():
                try:
                    await subscription.unsubscribe()
                    print(f"✅ 订阅已关闭: {data_type}")
                except Exception as e:
                    print(f"❌ 关闭订阅失败 {data_type}: {e}")

            # 关闭NATS连接
            if self.nats_client:
                await self.nats_client.close()
                print("✅ NATS连接已关闭")

            # 设置关闭事件
            self.shutdown_event.set()

            print("✅ 简化热端数据存储服务已停止")

        except Exception as e:
            print(f"❌ 停止服务失败: {e}")

    def _setup_signal_handlers(self):
        """设置信号处理器"""
        def signal_handler(signum, frame):
            print(f"📡 收到停止信号: {signum}")
            asyncio.create_task(self.stop())

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def get_stats(self) -> Dict[str, Any]:
        """获取服务统计信息"""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service_status": {
                "is_running": self.is_running,
                "subscriptions_count": len(self.subscriptions),
                "nats_connected": self.nats_client is not None and not self.nats_client.is_closed
            },
            "message_stats": self.stats,
            "health_check": {
                "status": "healthy" if self.is_running else "unhealthy",
                "nats_connected": self.nats_client is not None and not self.nats_client.is_closed,
                "subscriptions_active": len(self.subscriptions)
            }
        }

    def _get_health_status(self) -> Dict[str, Any]:
        """获取健康状态"""
        now = datetime.now(timezone.utc)

        # 检查最近是否有消息处理
        last_message_time = self.stats.get("last_message_time")
        message_lag = None
        if last_message_time:
            if isinstance(last_message_time, str):
                last_message_time = datetime.fromisoformat(last_message_time.replace('Z', '+00:00'))
            message_lag = (now - last_message_time).total_seconds()

        # 计算错误率
        total_messages = self.stats["messages_received"]
        failed_messages = self.stats["messages_failed"]
        error_rate = (failed_messages / total_messages * 100) if total_messages > 0 else 0

        # 健康状态评估
        health_status = "healthy"
        issues = []

        if not self.is_running:
            health_status = "unhealthy"
            issues.append("Service not running")

        if message_lag and message_lag > 300:  # 5分钟没有消息
            health_status = "degraded"
            issues.append(f"No messages for {message_lag:.0f} seconds")

        if error_rate > 10:  # 错误率超过10%
            health_status = "degraded"
            issues.append(f"High error rate: {error_rate:.1f}%")

        if len(self.subscriptions) == 0:
            health_status = "unhealthy"
            issues.append("No active subscriptions")

        return {
            "status": health_status,
            "issues": issues,
            "metrics": {
                "message_lag_seconds": message_lag,
                "error_rate_percent": round(error_rate, 2),
                "active_subscriptions": len(self.subscriptions),
                "total_retries": self.stats["retry_attempts"]
            }
        }

    async def health_check(self) -> bool:
        """执行健康检查"""
        try:
            # 检查NATS连接
            if not self.nats_client or self.nats_client.is_closed:
                return False

            # 检查ClickHouse连接
            host = self.hot_storage_config.get('clickhouse_host', 'localhost')
            port = self.hot_storage_config.get('clickhouse_http_port', 8123)

            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://{host}:{port}/ping", timeout=5) as response:
                    if response.status != 200:
                        return False

            return True

        except Exception as e:
            self.logger.error(f"健康检查失败: {e}")
            return False

    async def setup_http_server(self):
        """设置HTTP服务器"""
        self.app = web.Application()

        # 添加路由
        self.app.router.add_get('/health', self.handle_health)
        self.app.router.add_get('/stats', self.handle_stats)
        self.app.router.add_get('/metrics', self.handle_metrics)

        # 启动HTTP服务器
        runner = web.AppRunner(self.app)
        await runner.setup()

        site = web.TCPSite(runner, '0.0.0.0', self.http_port)
        await site.start()

        self.http_server = runner
        self.logger.info(f"✅ HTTP服务器启动成功，端口: {self.http_port}")

    async def handle_health(self, request):
        """健康检查端点"""
        is_healthy = await self.health_check()

        health_data = {
            "status": "healthy" if is_healthy else "unhealthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": "hot_storage",
            "version": "2.0.0-simplified",
            "uptime": time.time() - self.start_time if hasattr(self, 'start_time') else 0,
            "nats_connected": self.nats_client is not None and not self.nats_client.is_closed,
            "subscriptions": len(self.subscriptions),
            "is_running": self.is_running
        }

        status_code = 200 if is_healthy else 503
        return web.json_response(health_data, status=status_code)

    async def handle_stats(self, request):
        """统计信息端点"""
        stats_data = self.get_stats()
        return web.json_response(stats_data)

    async def handle_metrics(self, request):
        """Prometheus格式指标端点"""
        metrics = []

        # 基础指标
        metrics.append(f"hot_storage_messages_received_total {self.stats['messages_received']}")
        metrics.append(f"hot_storage_messages_processed_total {self.stats['messages_processed']}")
        metrics.append(f"hot_storage_messages_failed_total {self.stats['messages_failed']}")
        metrics.append(f"hot_storage_validation_errors_total {self.stats['validation_errors']}")
        metrics.append(f"hot_storage_subscriptions_active {len(self.subscriptions)}")
        metrics.append(f"hot_storage_is_running {1 if self.is_running else 0}")

        # ClickHouse 写入相关指标
        metrics.append(f"hot_storage_batch_inserts_total {self.stats['batch_inserts']}")
        metrics.append(f"hot_storage_batch_size_total {self.stats['batch_size_total']}")
        avg_batch = (self.stats['batch_size_total'] / self.stats['batch_inserts']) if self.stats['batch_inserts'] > 0 else 0
        metrics.append(f"hot_storage_batch_size_avg {avg_batch:.2f}")
        metrics.append(f"hot_storage_clickhouse_tcp_hits_total {self.stats.get('tcp_driver_hits', 0)}")
        metrics.append(f"hot_storage_clickhouse_http_fallback_total {self.stats.get('http_fallback_hits', 0)}")

        # 计算错误率
        total_messages = self.stats["messages_received"]
        if total_messages > 0:
            error_rate = (self.stats["messages_failed"] / total_messages) * 100
            metrics.append(f"hot_storage_error_rate_percent {error_rate:.2f}")

        # 时间类指标（秒级 epoch）
        if self.stats.get('last_message_time'):
            try:
                ts = self.stats['last_message_time']
                if isinstance(ts, (int, float)):
                    metrics.append(f"hot_storage_last_message_time_seconds {float(ts):.3f}")
            except Exception:
                pass
        if self.stats.get('last_error_time'):
            try:
                ts = self.stats['last_error_time']
                if isinstance(ts, (int, float)):
                    metrics.append(f"hot_storage_last_error_time_seconds {float(ts):.3f}")
            except Exception:
                pass

        metrics_text = "\n".join(metrics) + "\n"
        return web.Response(text=metrics_text, content_type="text/plain")


async def main():
    """主函数"""
    try:
        # 加载配置
        config_path = Path(__file__).parent / "config" / "tiered_storage_config.yaml"

        # 如果配置文件不存在，使用默认配置
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
        else:
            print(f"⚠️ 配置文件不存在，使用默认配置: {config_path}")
            config = {}

        # 环境变量覆盖配置文件设置
        if 'nats' not in config:
            config['nats'] = {}
        if 'hot_storage' not in config:
            config['hot_storage'] = {}

        # 优先使用环境变量（MARKETPRISM_NATS_URL > NATS_URL），统一 servers 列表
        env_url = os.getenv('MARKETPRISM_NATS_URL') or os.getenv('NATS_URL')
        if env_url:
            config['nats']['servers'] = [env_url]
        else:
            config['nats']['servers'] = config['nats'].get('servers') or [config['nats'].get('url', 'nats://localhost:4222')]
        # 覆盖 ClickHouse 连接（env 优先）
        config['hot_storage']['clickhouse_host'] = os.getenv('CLICKHOUSE_HOST', config['hot_storage'].get('clickhouse_host', 'localhost'))
        config['hot_storage']['clickhouse_http_port'] = int(os.getenv('CLICKHOUSE_HTTP_PORT', str(config['hot_storage'].get('clickhouse_http_port', 8123))))
        config['hot_storage']['clickhouse_tcp_port'] = int(os.getenv('CLICKHOUSE_TCP_PORT', str(config['hot_storage'].get('clickhouse_tcp_port', 9000))))
        config['hot_storage']['clickhouse_database'] = os.getenv('CLICKHOUSE_DATABASE', config['hot_storage'].get('clickhouse_database', 'marketprism_hot'))
        use_driver_env = os.getenv('USE_CLICKHOUSE_DRIVER')
        if use_driver_env is not None:
            config['hot_storage']['use_clickhouse_driver'] = use_driver_env.lower() in ('1', 'true', 'yes')

        # 覆盖 HTTP 端口（env 优先）：HOT_STORAGE_HTTP_PORT 或 MARKETPRISM_STORAGE_SERVICE_PORT
        try:
            config['http_port'] = int(os.getenv('HOT_STORAGE_HTTP_PORT', os.getenv('MARKETPRISM_STORAGE_SERVICE_PORT', str(config.get('http_port', 8080)))))
        except Exception:
            config['http_port'] = config.get('http_port', 8080)

        print(f"🔧 使用NATS Servers: {', '.join(config['nats']['servers'])}")
        print(f"🔧 使用ClickHouse: {config['hot_storage']['clickhouse_host']} (HTTP:{config['hot_storage']['clickhouse_http_port']}, TCP:{config['hot_storage']['clickhouse_tcp_port']})")
        print(f"🔧 HTTP端口: {config['http_port']}")



        # 创建并启动服务
        service = SimpleHotStorageService(config)
        await service.start()

    except KeyboardInterrupt:
        print("📡 收到中断信号，正在关闭服务...")
    except Exception as e:
        print(f"❌ 服务启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    from pathlib import Path as _Path

    parser = argparse.ArgumentParser(description="MarketPrism Storage Service (hot/cold)")
    parser.add_argument("--mode", "-m", choices=["hot", "cold"], default=os.getenv("STORAGE_MODE", "hot"), help="Run mode: hot (subscribe+ingest) or cold (archive)")
    parser.add_argument("--config", "-c", type=str, default=str(_Path(__file__).resolve().parent / "config" / "tiered_storage_config.yaml"), help="Config file path (YAML), default: config/tiered_storage_config.yaml")
    args = parser.parse_args()

    def _load_yaml(path_str: str) -> Dict[str, Any]:
        p = _Path(path_str)
        with open(p, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}

    cfg = _load_yaml(args.config)

    if args.mode == "hot":
        mapped = {
            'nats': cfg.get('nats', {}) or {},
            # 从配置文件读取HTTP端口，默认8081（与项目约定一致）
            'http_port': cfg.get('http_port', 8081),
            'hot_storage': {
                'clickhouse_host': (cfg.get('hot_storage', {}) or {}).get('clickhouse_host', 'localhost'),
                'clickhouse_http_port': (cfg.get('hot_storage', {}) or {}).get('clickhouse_http_port', 8123),
                # 修复键名：从 clickhouse_port -> clickhouse_tcp_port
                'clickhouse_tcp_port': (cfg.get('hot_storage', {}) or {}).get('clickhouse_tcp_port', 9000),
                'clickhouse_user': (cfg.get('hot_storage', {}) or {}).get('clickhouse_user', 'default'),
                'clickhouse_password': (cfg.get('hot_storage', {}) or {}).get('clickhouse_password', ''),
                'clickhouse_database': (cfg.get('hot_storage', {}) or {}).get('clickhouse_database', 'marketprism_hot'),
                'use_clickhouse_driver': True
            },
            'retry': cfg.get('retry', {'max_retries': 3, 'delay_seconds': 1, 'backoff_multiplier': 2})
        }
        _svc = SimpleHotStorageService(mapped)
        try:
            asyncio.run(_svc.start())
        except KeyboardInterrupt:
            try:
                asyncio.run(_svc.stop())
            except Exception:
                pass
        import sys as _sys
        _sys.exit(0)
    else:
        try:
            from cold_storage_service import ColdStorageService as _Cold
        except Exception:
            from .cold_storage_service import ColdStorageService as _Cold
        cold_cfg = {
            'hot_storage': cfg.get('hot_storage', {}) or {},
            'cold_storage': cfg.get('cold_storage', {}) or {},
            'sync': cfg.get('sync', {}) or {}
        }
        _svc = _Cold(cold_cfg)
        async def _cold_main():
            await _svc.initialize()
            await _svc.start()
        try:
            asyncio.run(_cold_main())
        except KeyboardInterrupt:
            try:
                asyncio.run(_svc.stop())
            except Exception:
                pass
        import sys as _sys
        _sys.exit(0)


