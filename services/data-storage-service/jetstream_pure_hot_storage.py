#!/usr/bin/env python3
"""
MarketPrism 纯JetStream热端存储服务
完全移除Core NATS回退机制，使用Pull消费者模式
配置一致性：从环境变量读取LSR配置参数
"""
import asyncio
import json
import os
import sys
import time
import traceback
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Union

import nats
import nats.js
import nats.js.api
from clickhouse_driver import Client as ClickHouseClient

# 全局服务引用，供健康检查HTTP服务访问
SERVICE_REF = None


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global SERVICE_REF
        if self.path.startswith('/health'):
            status = 200
            resp = {
                "service": "jetstream_pure_hot_storage",
                "status": "healthy" if SERVICE_REF and SERVICE_REF.is_running else "starting",
                "nats_connected": bool(SERVICE_REF and SERVICE_REF.nats_client),
                "subscriptions": len(SERVICE_REF.subscriptions) if SERVICE_REF else 0,
            }
            body = json.dumps(resp).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith('/metrics'):
            processed = getattr(SERVICE_REF, 'messages_processed', 0) or 0
            failed = getattr(SERVICE_REF, 'messages_failed', 0) or 0
            total = processed + failed
            error_rate = (failed / total * 100.0) if total > 0 else 0.0

            # 计算摄入延迟指标
            avg_ingest_lag = 0.0
            if SERVICE_REF and SERVICE_REF.ingest_lag_count > 0:
                avg_ingest_lag = SERVICE_REF.ingest_lag_sum / SERVICE_REF.ingest_lag_count

            # 计算ClickHouse写入耗时指标
            avg_insert_time = 0.0
            if SERVICE_REF and SERVICE_REF.clickhouse_insert_times:
                avg_insert_time = sum(SERVICE_REF.clickhouse_insert_times) / len(SERVICE_REF.clickhouse_insert_times)
                # 保留最近100次记录
                if len(SERVICE_REF.clickhouse_insert_times) > 100:
                    SERVICE_REF.clickhouse_insert_times = SERVICE_REF.clickhouse_insert_times[-100:]

            text = (
                f"hot_storage_messages_processed_total {processed}\n"
                f"hot_storage_messages_failed_total {failed}\n"
                f"hot_storage_error_rate_percent {error_rate:.2f}\n"
                f"hot_storage_ingest_lag_seconds {avg_ingest_lag:.3f}\n"
                f"hot_storage_clickhouse_insert_seconds {avg_insert_time:.3f}\n"
            ).encode()

            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; version=0.0.4')
            self.send_header('Content-Length', str(len(text)))
            self.end_headers()
            self.wfile.write(text)
            return
        self.send_response(404)
        self.end_headers()


class JetStreamPureHotStorage:
    """纯JetStream热端存储服务"""

    def __init__(self):
        self.nats_client = None
        self.jetstream = None
        self.clickhouse_client = None
        self.subscriptions = {}
        self.is_running = False
        self.start_time = time.time()

        # 从环境变量读取配置
        self.nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
        self.clickhouse_host = os.getenv("CLICKHOUSE_HOST", "localhost")
        self.clickhouse_port = int(os.getenv("CLICKHOUSE_PORT", "9000"))
        self.clickhouse_database = os.getenv("CLICKHOUSE_DATABASE", "marketprism_hot")

        # LSR配置参数（确保配置一致性）
        self.lsr_deliver_policy = os.getenv("LSR_DELIVER_POLICY", "last").lower()
        self.lsr_ack_policy = os.getenv("LSR_ACK_POLICY", "explicit").lower()
        self.lsr_ack_wait = int(os.getenv("LSR_ACK_WAIT", "60"))
        self.lsr_max_ack_pending = int(os.getenv("LSR_MAX_ACK_PENDING", "2000"))
        self.lsr_max_deliver = int(os.getenv("LSR_MAX_DELIVER", "3"))

        # Pull模式调优参数（可配置）
        self.pull_batch_size = int(os.getenv("JS_PULL_BATCH_SIZE", "50"))       # 默认50
        self.pull_concurrency = int(os.getenv("JS_PULL_CONCURRENCY", "2"))      # 默认2

        # 数据类型配置
        # 恢复完整数据类型支持
        self.data_types = [
            "funding_rate", "open_interest", "lsr_top_position", "lsr_all_account",
            "orderbook", "trade", "liquidation", "volatility_index"
        ]


        # 运行时指标与HTTP健康服务
        self.messages_processed = 0
        self.messages_failed = 0
        self.ingest_lag_sum = 0.0
        self.ingest_lag_count = 0
        self.clickhouse_insert_times = []
        self.httpd = None
        self.http_port = int(os.getenv("MARKETPRISM_STORAGE_SERVICE_PORT", "8080"))

        print(f"🚀 JetStream纯热端存储服务初始化")
        print(f"NATS URL: {self.nats_url}")
        print(f"ClickHouse: {self.clickhouse_host}:{self.clickhouse_port}/{self.clickhouse_database}")
        print(f"LSR配置: policy={self.lsr_deliver_policy}, ack={self.lsr_ack_policy}, wait={self.lsr_ack_wait}s, pending={self.lsr_max_ack_pending}")

    def _start_http_server(self):
        """启动内置HTTP健康检查与指标服务"""
        global SERVICE_REF
        try:
            SERVICE_REF = self
            self.httpd = HTTPServer(('0.0.0.0', self.http_port), _HealthHandler)
            th = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            th.start()
            print(f"✅ 健康检查HTTP服务启动于 0.0.0.0:{self.http_port}")
        except Exception as e:
            print(f"⚠️ 健康检查HTTP服务启动失败: {e}")


    async def connect(self):
        """连接NATS和ClickHouse"""
        try:
            # 连接NATS
            self.nats_client = await nats.connect(self.nats_url)
            self.jetstream = self.nats_client.jetstream()
            print("✅ NATS连接成功")

            # 连接ClickHouse
            self.clickhouse_client = ClickHouseClient(
                host=self.clickhouse_host,
                port=self.clickhouse_port,
                database=self.clickhouse_database
            )
            # 测试连接
            self.clickhouse_client.execute("SELECT 1")
            print("✅ ClickHouse连接成功")

        except Exception as e:
            print(f"❌ 连接失败: {e}")
            raise

    async def subscribe_all_data_types(self):
        """订阅所有数据类型"""
        print("🔄 开始订阅所有数据类型...")

        for data_type in self.data_types:
            try:
                await self._subscribe_to_data_type(data_type)
                await asyncio.sleep(0.1)  # 避免过快创建消费者
            except Exception as e:
                print(f"❌ 订阅 {data_type} 失败: {e}")
                traceback.print_exc()

        print(f"✅ 完成订阅，共 {len(self.subscriptions)} 个数据类型")

    async def _subscribe_to_data_type(self, data_type: str):
        """订阅特定数据类型 - 纯JetStream Pull消费者模式"""
        # 构建主题模式
        subject_mapping = {
            "funding_rate": "funding_rate.>",
            "open_interest": "open_interest.>",
            "lsr_top_position": "lsr_top_position.>",
            "lsr_all_account": "lsr_all_account.>",
            "orderbook": "orderbook.>",
            "trade": "trade.>",
            "liquidation": "liquidation.>",
            "volatility_index": "volatility_index.>"
        }

        subject_pattern = subject_mapping.get(data_type, f"{data_type}.>")

        # 确定流名称 - 订单簿使用独立ORDERBOOK_SNAP流，其他使用MARKET_DATA流
        stream_name = "ORDERBOOK_SNAP" if data_type == "orderbook" else "MARKET_DATA"

        print(f"设置JetStream订阅: {data_type} -> {subject_pattern} (流: {stream_name})")

        # 等待流可用
        for attempt in range(10):
            try:
                await self.jetstream._jsm.stream_info(stream_name)
                print(f"✅ 流 {stream_name} 可用")
                break
            except Exception:
                print(f"⏳ 等待流 {stream_name} 可用... (尝试 {attempt+1}/10)")
                await asyncio.sleep(2)
        else:
            raise Exception(f"❌ 流 {stream_name} 在20秒内未就绪")

        # 创建消费者
        durable_name = f"simple_hot_storage_realtime_{data_type}"

        # 删除旧消费者（如果存在）
        try:
            await self.jetstream._jsm.delete_consumer(stream_name, durable_name)
            print(f"🧹 删除旧消费者: {durable_name}")
        except Exception:
            pass

        # 创建消费者配置
        consumer_config = nats.js.api.ConsumerConfig(
            durable_name=durable_name,
            deliver_policy=nats.js.api.DeliverPolicy.LAST if self.lsr_deliver_policy == "last" else nats.js.api.DeliverPolicy.NEW,
            ack_policy=nats.js.api.AckPolicy.EXPLICIT if self.lsr_ack_policy == "explicit" else nats.js.api.AckPolicy.NONE,
            max_deliver=self.lsr_max_deliver,
            ack_wait=self.lsr_ack_wait,
            max_ack_pending=self.lsr_max_ack_pending,
            filter_subject=subject_pattern
        )

        # 创建消费者
        await self.jetstream._jsm.add_consumer(stream_name, consumer_config)
        print(f"✅ 消费者创建成功: {durable_name}")

        # 创建pull订阅
        consumer = await self.jetstream.pull_subscribe(
            subject=subject_pattern,
            durable=durable_name,
            stream=stream_name
        )

        # 启动消息处理任务（并发）
        tasks = []
        for i in range(max(1, self.pull_concurrency)):
            task = asyncio.create_task(self._pull_message_handler(consumer, data_type))
            tasks.append(task)
        self.subscriptions[data_type] = {"consumer": consumer, "tasks": tasks}

        print(f"✅ JetStream Pull订阅成功: {data_type} -> {subject_pattern}，并发={self.pull_concurrency}，batch={self.pull_batch_size}")

    async def _pull_message_handler(self, consumer, data_type: str):
        """Pull消费者消息处理器"""
        print(f"🔄 启动 {data_type} 消息处理器")

        while self.is_running:
            try:
                # 批量拉取消息（可配置批量大小）
                msgs = await consumer.fetch(batch=self.pull_batch_size, timeout=5.0)

                for msg in msgs:
                    try:
                        # 计算摄入延迟
                        data = json.loads(msg.data.decode())
                        msg_timestamp = self._parse_ts(data.get('timestamp'))
                        now = datetime.now(timezone.utc)
                        ingest_lag = (now - msg_timestamp).total_seconds()
                        self.ingest_lag_sum += ingest_lag
                        self.ingest_lag_count += 1

                        # 记录ClickHouse写入时间
                        start_time = time.time()
                        await self._handle_message(msg, data_type)
                        insert_time = time.time() - start_time
                        self.clickhouse_insert_times.append(insert_time)

                        await msg.ack()
                        self.messages_processed += 1
                    except Exception as e:
                        print(f"❌ 处理消息失败 {data_type}: {e}")
                        self.messages_failed += 1
                        await msg.nak()

            except asyncio.TimeoutError:
                # 正常超时，继续拉取
                continue
            except Exception as e:
                print(f"❌ Pull消息失败 {data_type}: {e}")
                await asyncio.sleep(1)

    async def _handle_message(self, msg, data_type: str):
        """处理单条消息"""
        try:
            # 解析消息
            data = json.loads(msg.data.decode())

            # 根据数据类型写入对应表
            if data_type == "trade":
                await self._insert_trade(data)
            elif data_type == "orderbook":
                await self._insert_orderbook(data)
            elif data_type == "liquidation":
                await self._insert_liquidation(data)
            elif data_type == "funding_rate":
                await self._insert_funding_rate(data)
            elif data_type == "open_interest":
                await self._insert_open_interest(data)
            elif data_type in ["lsr_top_position", "lsr_all_account"]:
                await self._insert_lsr(data, data_type)
            elif data_type == "volatility_index":
                await self._insert_volatility_index(data)
            else:
                print(f"⚠️ 未知数据类型: {data_type}")

        except Exception as e:
            print(f"❌ 处理消息失败: {e}")
            raise

    def _parse_ts(self, ts: Union[str, int, float, datetime, None]) -> datetime:
        """将各种时间戳格式转换为带UTC时区的datetime供clickhouse-driver使用"""
        if ts is None:
            return datetime.now(timezone.utc)
        if isinstance(ts, datetime):
            return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        try:
            # 毫秒或秒
            if isinstance(ts, (int, float)):
                # 认为>= 10^11 为毫秒
                if ts > 1e11:
                    return datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
                else:
                    return datetime.fromtimestamp(ts, tz=timezone.utc)
            if isinstance(ts, str):
                t = ts.strip()
                # 处理Z结尾与T分隔
                t = t.replace('T', ' ')
                if t.endswith('Z'):
                    t = t[:-1]
                # 截断到毫秒
                if '.' in t:
                    left, right = t.split('.', 1)
                    ms = ''.join(ch for ch in right if ch.isdigit())[:3]
                    t = f"{left}.{ms}" if ms else left
                # 尝试不同格式
                for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S'):
                    try:
                        dt = datetime.strptime(t, fmt)
                        return dt.replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue
        except Exception:
            pass
        # 兜底：当前时间
        return datetime.now(timezone.utc)

    async def _insert_trade(self, data: Dict[str, Any]):
        """插入交易数据"""
        query = """
        INSERT INTO trades (
            timestamp, trade_time, exchange, market_type, symbol,
            trade_id, price, quantity, side, is_maker, data_source, created_at
        ) VALUES
        """

        values = [(
            self._parse_ts(data.get('timestamp')),
            self._parse_ts(data.get('trade_time', data.get('timestamp'))),
            data.get('exchange'),
            data.get('market_type'),
            data.get('symbol'),
            data.get('trade_id'),
            float(data.get('price', 0)),
            float(data.get('quantity', 0)),
            data.get('side'),
            data.get('is_maker', False),
            data.get('data_source', 'collector'),
            datetime.now(timezone.utc)
        )]

        self.clickhouse_client.execute(query, values)

    async def _insert_orderbook(self, data: Dict[str, Any]):
        """插入订单簿数据"""
        query = """
        INSERT INTO orderbooks (
            timestamp, exchange, market_type, symbol, last_update_id,
            bids, asks, bids_count, asks_count,
            best_bid_price, best_bid_quantity, best_ask_price, best_ask_quantity,
            data_source, created_at
        ) VALUES
        """

        bids = data.get('bids', [])
        asks = data.get('asks', [])

        values = [(
            self._parse_ts(data.get('timestamp')),
            data.get('exchange'),
            data.get('market_type'),
            data.get('symbol'),
            data.get('last_update_id', 0),
            json.dumps(bids),
            json.dumps(asks),
            len(bids),
            len(asks),
            float(bids[0][0]) if bids else 0,
            float(bids[0][1]) if bids else 0,
            float(asks[0][0]) if asks else 0,
            float(asks[0][1]) if asks else 0,
            data.get('data_source', 'collector'),
            datetime.now(timezone.utc)
        )]

        self.clickhouse_client.execute(query, values)

    async def _insert_liquidation(self, data: Dict[str, Any]):
        """插入强平数据"""
        query = """
        INSERT INTO liquidations (
            timestamp, liquidation_time, exchange, market_type, symbol,
            price, quantity, side, data_source, created_at
        ) VALUES
        """

        values = [(
            self._parse_ts(data.get('timestamp')),
            self._parse_ts(data.get('liquidation_time', data.get('timestamp'))),
            data.get('exchange'),
            data.get('market_type'),
            data.get('symbol'),
            float(data.get('price', 0)),
            float(data.get('quantity', 0)),
            data.get('side'),
            data.get('data_source', 'collector'),
            datetime.now(timezone.utc)
        )]

        self.clickhouse_client.execute(query, values)

    async def _insert_funding_rate(self, data: Dict[str, Any]):
        """插入资金费率数据"""
        query = """
        INSERT INTO funding_rates (
            timestamp, exchange, market_type, symbol,
            funding_rate, funding_time, next_funding_time,
            mark_price, index_price, data_source, created_at
        ) VALUES
        """

        values = [(
            self._parse_ts(data.get('timestamp')),
            data.get('exchange'),
            data.get('market_type'),
            data.get('symbol'),
            float(data.get('funding_rate', 0)),
            self._parse_ts(data.get('funding_time', data.get('timestamp'))),
            self._parse_ts(data.get('next_funding_time')),
            float(data.get('mark_price', 0)),
            float(data.get('index_price', 0)),
            data.get('data_source', 'collector'),
            datetime.now(timezone.utc)
        )]

        self.clickhouse_client.execute(query, values)

    async def _insert_open_interest(self, data: Dict[str, Any]):
        """插入持仓量数据"""
        query = """
        INSERT INTO open_interests (
            timestamp, exchange, market_type, symbol,
            open_interest, open_interest_value, count,
            data_source, created_at
        ) VALUES
        """

        values = [(
            self._parse_ts(data.get('timestamp')),
            data.get('exchange'),
            data.get('market_type'),
            data.get('symbol'),
            float(data.get('open_interest', 0)),
            float(data.get('open_interest_value', 0)),
            int(data.get('count', 0)),
            data.get('data_source', 'collector'),
            datetime.now(timezone.utc)
        )]

        self.clickhouse_client.execute(query, values)

    async def _insert_lsr(self, data: Dict[str, Any], data_type: str):
        """插入LSR数据"""
        if data_type == "lsr_top_position":
            query = """
            INSERT INTO lsr_top_positions (
                timestamp, exchange, market_type, symbol,
                long_position_ratio, short_position_ratio, period,
                data_source, created_at
            ) VALUES
            """

            values = [(
                self._parse_ts(data.get('timestamp')),
                data.get('exchange'),
                data.get('market_type'),
                data.get('symbol'),
                float(data.get('long_position_ratio', 0)),
                float(data.get('short_position_ratio', 0)),
                data.get('period', '5m'),
                data.get('data_source', 'collector'),
                datetime.now(timezone.utc)
            )]

        elif data_type == "lsr_all_account":
            query = """
            INSERT INTO lsr_all_accounts (
                timestamp, exchange, market_type, symbol,
                long_account_ratio, short_account_ratio, period,
                data_source, created_at
            ) VALUES
            """

            values = [(
                self._parse_ts(data.get('timestamp')),
                data.get('exchange'),
                data.get('market_type'),
                data.get('symbol'),
                float(data.get('long_account_ratio', 0)),
                float(data.get('short_account_ratio', 0)),
                data.get('period', '5m'),
                data.get('data_source', 'collector'),
                datetime.now(timezone.utc)
            )]
        else:
            print(f"⚠️ 未知LSR数据类型: {data_type}")
            return

        self.clickhouse_client.execute(query, values)

    async def _insert_volatility_index(self, data: Dict[str, Any]):
        """插入波动率指数数据"""
        query = """
        INSERT INTO volatility_indices (
            timestamp, exchange, market_type, symbol,
            index_value, underlying_asset, data_source, created_at
        ) VALUES
        """

        values = [(
            self._parse_ts(data.get('timestamp')),
            data.get('exchange'),
            data.get('market_type'),
            data.get('symbol'),
            float(data.get('volatility_index', data.get('index_value', 0))),
            data.get('underlying_asset', data.get('symbol', '')),
            data.get('data_source', 'collector'),
            datetime.now(timezone.utc)
        )]

        self.clickhouse_client.execute(query, values)

    async def start(self):
        """启动服务"""
        self.is_running = True
        print("🚀 启动JetStream纯热端存储服务...")

        # 启动健康检查HTTP服务
        self._start_http_server()

        await self.connect()
        await self.subscribe_all_data_types()

        print("✅ 服务启动完成，开始处理消息...")

        # 保持运行
        try:
            while self.is_running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("⏹️ 收到停止信号")
        finally:
            await self.stop()

    async def stop(self):
        """停止服务"""
        print("⏹️ 停止服务...")
        self.is_running = False

        # 停止所有任务
        for data_type, sub_info in self.subscriptions.items():
            tasks = sub_info.get("tasks")
            if tasks:
                for t in tasks:
                    t.cancel()

        # 停止HTTP健康服务
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception as e:
                print(f"⚠️ 停止HTTP服务时出现问题: {e}")
            finally:
                self.httpd = None

        # 关闭连接
        if self.nats_client:
            await self.nats_client.close()

        print("✅ 服务已停止")


async def main():
    """主函数"""
    service = JetStreamPureHotStorage()
    await service.start()


if __name__ == "__main__":
    asyncio.run(main())
