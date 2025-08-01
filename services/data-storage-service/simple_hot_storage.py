#!/usr/bin/env python3
"""
MarketPrism 简化热端数据存储服务
直接处理NATS消息并写入ClickHouse
"""

import asyncio
import json
import os
import signal
import sys
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union
import yaml
import nats
from nats.js import JetStreamContext
import aiohttp
from pathlib import Path
from decimal import Decimal, InvalidOperation


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
    def validate_timestamp(timestamp: Any, field_name: str) -> str:
        """验证时间戳格式"""
        try:
            if timestamp is None:
                return datetime.now(timezone.utc).isoformat()

            if isinstance(timestamp, str):
                # 转换ISO格式到ClickHouse格式
                if '+' in timestamp:
                    timestamp = timestamp.split('+')[0]
                if 'T' in timestamp:
                    timestamp = timestamp.replace('T', ' ')
                return timestamp

            elif isinstance(timestamp, datetime):
                return timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

            else:
                logging.warning(f"Unexpected timestamp type for {field_name}: {type(timestamp)}")
                return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        except Exception as e:
            logging.error(f"Error validating timestamp for {field_name}: {e}")
            return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]


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

        # 统计信息
        self.stats = {
            "messages_received": 0,
            "messages_processed": 0,
            "messages_failed": 0,
            "validation_errors": 0,
            "retry_attempts": 0,
            "last_message_time": None,
            "last_error_time": None
        }

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

            # 验证NATS配置
            nats_config = config['nats']
            if 'url' not in nats_config:
                nats_config['url'] = os.getenv('NATS_URL', 'nats://localhost:4222')

            # 验证ClickHouse配置
            ch_config = config['hot_storage']
            defaults = {
                'clickhouse_host': 'localhost',
                'clickhouse_http_port': 8123,
                'clickhouse_database': 'marketprism_hot',
                'clickhouse_user': 'default',
                'clickhouse_password': ''
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
            
            # 设置信号处理
            self._setup_signal_handlers()
            
            self.is_running = True
            print("✅ 简化热端数据存储服务已启动")
            
            # 等待关闭信号
            await self.shutdown_event.wait()
            
        except Exception as e:
            print(f"❌ 服务启动失败: {e}")
            raise
    
    async def _connect_nats(self):
        """连接NATS服务器"""
        try:
            nats_url = self.nats_config.get('url', os.getenv('NATS_URL', 'nats://localhost:4222'))
            
            self.nats_client = await nats.connect(
                servers=[nats_url],
                max_reconnect_attempts=10,
                reconnect_time_wait=2
            )
            
            # 获取JetStream上下文
            self.jetstream = self.nats_client.jetstream()
            
            print(f"✅ NATS连接建立成功: {nats_url}")
            
        except Exception as e:
            print(f"❌ NATS连接失败: {e}")
            raise
    
    async def _setup_subscriptions(self):
        """设置NATS订阅"""
        try:
            # 订阅各种数据类型
            data_types = ["orderbook", "trade", "funding_rate", "open_interest",
                         "liquidation", "lsr", "lsr_top_position", "lsr_all_account", "volatility_index"]

            for data_type in data_types:
                await self._subscribe_to_data_type(data_type)

            print(f"✅ NATS订阅设置完成，成功订阅数量: {len(self.subscriptions)}")

            # 只要有至少一个订阅成功就继续
            if len(self.subscriptions) == 0:
                raise Exception("没有成功创建任何订阅")

        except Exception as e:
            print(f"❌ NATS订阅设置失败: {e}")
            raise
    
    async def _subscribe_to_data_type(self, data_type: str):
        """订阅特定数据类型"""
        try:
            # 构建主题模式 - 根据stream配置调整
            subject_mapping = {
                "funding_rate": "funding-rate.>",
                "open_interest": "open-interest.>",
                "lsr": "lsr-data.>",  # 通用LSR格式
                "lsr_top_position": "lsr-top-position-data.>",  # 顶级大户多空持仓比例
                "lsr_all_account": "lsr-all-account-data.>",  # 全市场多空持仓人数比例
            }

            if data_type in subject_mapping:
                subject_pattern = subject_mapping[data_type]
            else:
                subject_pattern = f"{data_type}-data.>"

            # 创建订阅
            subscription = await self.jetstream.subscribe(
                subject=subject_pattern,
                cb=lambda msg, dt=data_type: asyncio.create_task(
                    self._handle_message(msg, dt)
                ),
                durable=f"simple_hot_storage_{data_type}",
                config=nats.js.api.ConsumerConfig(
                    deliver_policy=nats.js.api.DeliverPolicy.NEW,
                    ack_policy=nats.js.api.AckPolicy.EXPLICIT,
                    max_deliver=3,
                    ack_wait=30
                )
            )

            self.subscriptions[data_type] = subscription
            print(f"✅ 订阅成功: {data_type} -> {subject_pattern}")

        except Exception as e:
            print(f"❌ 订阅失败 {data_type}: {e}")
            # 不要抛出异常，继续处理其他订阅
            pass
    
    async def _handle_message(self, msg, data_type: str):
        """处理NATS消息，包含重试机制"""
        try:
            # 更新统计
            self.stats["messages_received"] += 1
            self.stats["last_message_time"] = datetime.now(timezone.utc)

            # 解析消息
            try:
                data = json.loads(msg.data.decode())
            except json.JSONDecodeError as e:
                self.logger.error(f"消息JSON解析失败 {data_type}: {e}")
                await msg.nak()
                self.stats["messages_failed"] += 1
                self.stats["validation_errors"] += 1
                return

            # 验证数据格式
            try:
                validated_data = self._validate_message_data(data, data_type)
            except DataValidationError as e:
                self.logger.error(f"数据验证失败 {data_type}: {e}")
                await msg.nak()
                self.stats["validation_errors"] += 1
                return

            # 存储到ClickHouse（带重试）
            success = await self._store_to_clickhouse_with_retry(data_type, validated_data)

            if success:
                # 确认消息
                await msg.ack()
                self.stats["messages_processed"] += 1
                print(f"✅ 消息处理成功: {data_type} -> {msg.subject}")
            else:
                # 拒绝消息，触发重试
                await msg.nak()
                self.stats["messages_failed"] += 1
                self.stats["last_error_time"] = datetime.now(timezone.utc)
                print(f"❌ 消息存储失败: {data_type} -> {msg.subject}")

        except Exception as e:
            # 处理异常，拒绝消息
            try:
                await msg.nak()
            except:
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
                validated_data['best_bid_price'] = self.validator.validate_numeric(
                    data.get('best_bid_price'), 'best_bid_price', 0.0
                )
                validated_data['best_ask_price'] = self.validator.validate_numeric(
                    data.get('best_ask_price'), 'best_ask_price', 0.0
                )
                validated_data['bids'] = self.validator.validate_json_data(
                    data.get('bids'), 'bids'
                )
                validated_data['asks'] = self.validator.validate_json_data(
                    data.get('asks'), 'asks'
                )

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

            elif data_type in ['funding_rate']:
                validated_data['funding_rate'] = self.validator.validate_numeric(
                    data.get('funding_rate'), 'funding_rate', 0.0
                )
                validated_data['funding_time'] = self.validator.validate_timestamp(
                    data.get('funding_time'), 'funding_time'
                )
                validated_data['next_funding_time'] = self.validator.validate_timestamp(
                    data.get('next_funding_time'), 'next_funding_time'
                )

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
    
    async def _store_to_clickhouse(self, data_type: str, data: Dict[str, Any]) -> bool:
        """存储数据到ClickHouse"""
        try:
            host = self.hot_storage_config.get('clickhouse_host', 'localhost')
            port = self.hot_storage_config.get('clickhouse_http_port', 8123)
            database = self.hot_storage_config.get('clickhouse_database', 'marketprism_hot')
            
            # 获取表名
            table_mapping = {
                "orderbook": "orderbooks",
                "trade": "trades",
                "funding_rate": "funding_rates",
                "open_interest": "open_interests",
                "liquidation": "liquidations",
                "lsr": "lsrs",
                "lsr_top_position": "lsrs",  # 使用同一个表
                "lsr_all_account": "lsrs",   # 使用同一个表
                "volatility_index": "volatility_indices"
            }
            table_name = table_mapping.get(data_type, data_type)
            
            # 构建插入SQL
            insert_sql = self._build_insert_sql(table_name, data)
            
            # 执行插入
            url = f"http://{host}:{port}/?database={database}"
            
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
                fields.extend(['last_update_id', 'best_bid_price', 'best_ask_price', 'bids', 'asks'])
                values.extend([
                    str(data['last_update_id']),
                    str(data['best_bid_price']),
                    str(data['best_ask_price']),
                    f"'{data['bids']}'",  # 已经是标准JSON格式
                    f"'{data['asks']}'"   # 已经是标准JSON格式
                ])
            
            elif table_name == 'trades':
                fields.extend(['trade_id', 'price', 'quantity', 'side', 'is_maker'])
                values.extend([
                    f"'{data['trade_id']}'",
                    str(data['price']),
                    str(data['quantity']),
                    f"'{data['side']}'",
                    str(data['is_maker']).lower()
                ])

            elif table_name == 'funding_rates':
                fields.extend(['funding_rate', 'funding_time', 'next_funding_time'])
                values.extend([
                    str(data['funding_rate']),
                    f"'{data['funding_time']}'",  # 已经格式化
                    f"'{data['next_funding_time']}'"  # 已经格式化
                ])

            elif table_name == 'lsrs':
                # 处理LSR数据（多空持仓比例）
                fields.extend(['lsr_type', 'long_ratio', 'short_ratio', 'long_account_ratio', 'short_account_ratio'])
                values.extend([
                    f"'{data.get('lsr_type', 'unknown')}'",  # top_position 或 all_account
                    str(data.get('long_ratio', 0)),
                    str(data.get('short_ratio', 0)),
                    str(data.get('long_account_ratio', 0)),
                    str(data.get('short_account_ratio', 0))
                ])
            
            # 构建SQL
            fields_str = ', '.join(fields)
            values_str = ', '.join(values)
            
            sql = f"INSERT INTO {table_name} ({fields_str}) VALUES ({values_str})"
            return sql
            
        except Exception as e:
            print(f"❌ 构建SQL失败: {e}")
            return ""
    
    async def stop(self):
        """停止服务"""
        try:
            print("🛑 停止简化热端数据存储服务")
            
            self.is_running = False
            
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
            "health_check": self._get_health_status()
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

        # 优先使用环境变量
        config['nats']['url'] = os.getenv('NATS_URL', config['nats'].get('url', 'nats://localhost:4222'))
        config['hot_storage']['clickhouse_host'] = os.getenv('CLICKHOUSE_HOST', config['hot_storage'].get('clickhouse_host', 'localhost'))
        config['hot_storage']['clickhouse_http_port'] = int(os.getenv('CLICKHOUSE_HTTP_PORT', str(config['hot_storage'].get('clickhouse_http_port', 8123))))
        config['hot_storage']['clickhouse_database'] = os.getenv('CLICKHOUSE_DATABASE', config['hot_storage'].get('clickhouse_database', 'marketprism_hot'))

        print(f"🔧 使用NATS URL: {config['nats']['url']}")
        print(f"🔧 使用ClickHouse: {config['hot_storage']['clickhouse_host']}:{config['hot_storage']['clickhouse_http_port']}")

        # 创建并启动服务
        service = SimpleHotStorageService(config)
        await service.start()
        
    except KeyboardInterrupt:
        print("📡 收到中断信号，正在关闭服务...")
    except Exception as e:
        print(f"❌ 服务启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
