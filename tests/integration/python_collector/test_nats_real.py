"""
Python Collector NATS客户端真实集成测试

使用真实的NATS服务进行测试，不使用Mock对象
需要先启动NATS服务：docker-compose up nats
"""

import pytest
import asyncio
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
import nats
from nats.js.api import StreamConfig

# 导入被测试的模块
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../services/python-collector/src'))

from marketprism_collector.nats_client import MarketDataPublisher, NATSManager
from marketprism_collector.config import NATSConfig
from marketprism_collector.types import (
    NormalizedTrade, NormalizedOrderBook, NormalizedTicker,
    NormalizedKline, NormalizedFundingRate, NormalizedOpenInterest,
    NormalizedLiquidation, PriceLevel
)


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def nats_connection():
    """创建真实的NATS连接"""
    try:
        nc = await nats.connect("nats://localhost:4222")
        yield nc
        await nc.close()
    except Exception as e:
        pytest.skip(f"无法连接到NATS服务器: {e}")


@pytest.fixture
def nats_config():
    """NATS配置"""
    return NATSConfig(
        url="nats://localhost:4222",
        client_name="test-real-collector"
    )


class TestRealNATSConnection:
    """测试真实NATS连接"""
    
    @pytest.mark.asyncio
    async def test_nats_server_available(self):
        """测试NATS服务器是否可用"""
        try:
            nc = await nats.connect("nats://localhost:4222", connect_timeout=5)
            assert nc.is_connected
            await nc.close()
        except Exception as e:
            pytest.fail(f"NATS服务器不可用: {e}")
    
    @pytest.mark.asyncio
    async def test_jetstream_available(self, nats_connection):
        """测试JetStream是否可用"""
        js = nats_connection.jetstream()
        
        # 尝试获取流信息
        try:
            streams = await js.streams_info()
            assert isinstance(streams, list)
        except Exception as e:
            pytest.fail(f"JetStream不可用: {e}")


class TestRealMarketDataPublisher:
    """测试真实的市场数据发布器"""
    
    @pytest.mark.asyncio
    async def test_publisher_real_connection(self, nats_config):
        """测试发布器真实连接"""
        publisher = MarketDataPublisher(nats_config)
        
        # 连接到真实NATS服务器
        result = await publisher.connect()
        assert result is True
        assert publisher.is_connected is True
        assert publisher.client is not None
        assert publisher.js is not None
        
        # 清理
        await publisher.disconnect()
        assert publisher.is_connected is False
    
    @pytest.mark.asyncio
    async def test_stream_creation(self, nats_config):
        """测试流创建"""
        publisher = MarketDataPublisher(nats_config)
        
        # 连接并确保流存在
        await publisher.connect()
        
        # 验证流是否存在
        try:
            stream_info = await publisher.js.stream_info("MARKET_DATA")
            assert stream_info.config.name == "MARKET_DATA"
            assert "market.>" in stream_info.config.subjects
        except Exception as e:
            pytest.fail(f"流创建失败: {e}")
        
        await publisher.disconnect()
    
    @pytest.mark.asyncio
    async def test_publish_real_trade(self, nats_config):
        """测试发布真实交易数据"""
        publisher = MarketDataPublisher(nats_config)
        await publisher.connect()
        
        # 创建真实交易数据
        trade = NormalizedTrade(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            trade_id=f"test_{int(time.time())}",
            price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            quote_quantity=Decimal("5000.00"),
            timestamp=datetime.now(timezone.utc),
            is_buyer_maker=True
        )
        
        # 发布数据
        result = await publisher.publish_trade(trade)
        assert result is True
        
        # 验证数据是否真的发布到了NATS
        # 通过订阅相同主题来验证
        subject = "market.binance.btcusdt.trade"
        received_data = []
        
        async def message_handler(msg):
            data = json.loads(msg.data.decode())
            received_data.append(data)
        
        # 订阅消息
        sub = await publisher.client.subscribe(subject, cb=message_handler)
        
        # 再次发布数据
        await publisher.publish_trade(trade)
        
        # 等待消息接收
        await asyncio.sleep(0.5)
        
        # 验证接收到的数据
        assert len(received_data) > 0
        received_trade = received_data[-1]
        assert received_trade["exchange_name"] == "binance"
        assert received_trade["symbol_name"] == "BTCUSDT"
        assert received_trade["price"] == "50000.00"
        
        await sub.unsubscribe()
        await publisher.disconnect()
    
    @pytest.mark.asyncio
    async def test_publish_real_orderbook(self, nats_config):
        """测试发布真实订单簿数据"""
        publisher = MarketDataPublisher(nats_config)
        await publisher.connect()
        
        # 创建真实订单簿数据
        orderbook = NormalizedOrderBook(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            bids=[
                PriceLevel(price=Decimal("49999.00"), quantity=Decimal("0.5")),
                PriceLevel(price=Decimal("49998.00"), quantity=Decimal("1.0"))
            ],
            asks=[
                PriceLevel(price=Decimal("50001.00"), quantity=Decimal("0.3")),
                PriceLevel(price=Decimal("50002.00"), quantity=Decimal("0.8"))
            ],
            timestamp=datetime.now(timezone.utc),
            last_update_id=int(time.time())
        )
        
        # 发布数据
        result = await publisher.publish_orderbook(orderbook)
        assert result is True
        
        # 验证数据发布
        subject = "market.binance.btcusdt.orderbook"
        received_data = []
        
        async def message_handler(msg):
            data = json.loads(msg.data.decode())
            received_data.append(data)
        
        sub = await publisher.client.subscribe(subject, cb=message_handler)
        await publisher.publish_orderbook(orderbook)
        await asyncio.sleep(0.5)
        
        assert len(received_data) > 0
        received_orderbook = received_data[-1]
        assert received_orderbook["exchange_name"] == "binance"
        assert len(received_orderbook["bids"]) == 2
        assert len(received_orderbook["asks"]) == 2
        
        await sub.unsubscribe()
        await publisher.disconnect()
    
    @pytest.mark.asyncio
    async def test_publish_real_ticker(self, nats_config):
        """测试发布真实行情数据"""
        publisher = MarketDataPublisher(nats_config)
        await publisher.connect()
        
        # 创建真实行情数据
        ticker = NormalizedTicker(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            last_price=Decimal("50000.00"),
            open_price=Decimal("49000.00"),
            high_price=Decimal("51000.00"),
            low_price=Decimal("48000.00"),
            volume=Decimal("1000.0"),
            quote_volume=Decimal("50000000.0"),
            price_change=Decimal("1000.00"),
            price_change_percent=Decimal("2.04"),
            weighted_avg_price=Decimal("49500.00"),
            last_quantity=Decimal("0.1"),
            best_bid_price=Decimal("49999.00"),
            best_bid_quantity=Decimal("0.5"),
            best_ask_price=Decimal("50001.00"),
            best_ask_quantity=Decimal("0.3"),
            open_time=datetime.now(timezone.utc),
            close_time=datetime.now(timezone.utc),
            trade_count=1000,
            timestamp=datetime.now(timezone.utc)
        )
        
        # 发布数据
        result = await publisher.publish_ticker(ticker)
        assert result is True
        
        # 验证数据发布
        subject = "market.binance.btcusdt.ticker"
        received_data = []
        
        async def message_handler(msg):
            data = json.loads(msg.data.decode())
            received_data.append(data)
        
        sub = await publisher.client.subscribe(subject, cb=message_handler)
        await publisher.publish_ticker(ticker)
        await asyncio.sleep(0.5)
        
        assert len(received_data) > 0
        received_ticker = received_data[-1]
        assert received_ticker["exchange_name"] == "binance"
        assert received_ticker["last_price"] == "50000.00"
        assert received_ticker["volume"] == "1000.0"
        
        await sub.unsubscribe()
        await publisher.disconnect()
    
    @pytest.mark.asyncio
    async def test_publish_real_funding_rate(self, nats_config):
        """测试发布真实资金费率数据"""
        publisher = MarketDataPublisher(nats_config)
        await publisher.connect()
        
        # 创建真实资金费率数据
        funding_rate = NormalizedFundingRate(
            exchange_name="binance",
            symbol_name="BTC-USDT",
            funding_rate=Decimal("0.0001"),
            next_funding_time=datetime.now(timezone.utc),
            mark_price=Decimal("50000.00"),
            index_price=Decimal("49999.50"),
            premium_index=Decimal("0.50"),
            timestamp=datetime.now(timezone.utc)
        )
        
        # 发布数据
        result = await publisher.publish_funding_rate(funding_rate)
        assert result is True
        
        # 验证数据发布
        subject = "market.binance.btc_usdt.funding_rate"
        received_data = []
        
        async def message_handler(msg):
            data = json.loads(msg.data.decode())
            received_data.append(data)
        
        sub = await publisher.client.subscribe(subject, cb=message_handler)
        await publisher.publish_funding_rate(funding_rate)
        await asyncio.sleep(0.5)
        
        assert len(received_data) > 0
        received_funding = received_data[-1]
        assert received_funding["exchange_name"] == "binance"
        assert received_funding["funding_rate"] == "0.0001"
        
        await sub.unsubscribe()
        await publisher.disconnect()


class TestRealNATSManager:
    """测试真实的NATS管理器"""
    
    @pytest.mark.asyncio
    async def test_manager_real_workflow(self, nats_config):
        """测试管理器真实工作流程"""
        manager = NATSManager(nats_config)
        
        # 启动管理器
        result = await manager.start()
        assert result is True
        
        # 获取发布器
        publisher = manager.get_publisher()
        assert publisher is not None
        assert publisher.is_connected is True
        
        # 健康检查
        health = await manager.health_check()
        assert health["connected"] is True
        assert health["client_name"] == "test-real-collector"
        
        # 停止管理器
        await manager.stop()
        assert publisher.is_connected is False


class TestRealDataFlow:
    """测试真实数据流"""
    
    @pytest.mark.asyncio
    async def test_complete_real_data_flow(self, nats_config):
        """测试完整的真实数据流"""
        # 创建发布器和订阅器
        publisher = MarketDataPublisher(nats_config)
        subscriber_nc = await nats.connect("nats://localhost:4222")
        
        await publisher.connect()
        
        # 收集所有接收到的消息
        received_messages = []
        
        async def collect_messages(msg):
            data = json.loads(msg.data.decode())
            received_messages.append({
                "subject": msg.subject,
                "data": data
            })
        
        # 订阅所有市场数据主题
        await subscriber_nc.subscribe("market.>", cb=collect_messages)
        
        # 发布各种类型的数据
        timestamp = datetime.now(timezone.utc)
        
        # 1. 交易数据
        trade = NormalizedTrade(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            trade_id=f"test_trade_{int(time.time())}",
            price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            quote_quantity=Decimal("5000.00"),
            timestamp=timestamp,
            is_buyer_maker=True
        )
        await publisher.publish_trade(trade)
        
        # 2. 订单簿数据
        orderbook = NormalizedOrderBook(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            bids=[PriceLevel(price=Decimal("49999.00"), quantity=Decimal("0.5"))],
            asks=[PriceLevel(price=Decimal("50001.00"), quantity=Decimal("0.3"))],
            timestamp=timestamp
        )
        await publisher.publish_orderbook(orderbook)
        
        # 3. 行情数据
        ticker = NormalizedTicker(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            last_price=Decimal("50000.00"),
            open_price=Decimal("49000.00"),
            high_price=Decimal("51000.00"),
            low_price=Decimal("48000.00"),
            volume=Decimal("1000.0"),
            quote_volume=Decimal("50000000.0"),
            price_change=Decimal("1000.00"),
            price_change_percent=Decimal("2.04"),
            weighted_avg_price=Decimal("49500.00"),
            last_quantity=Decimal("0.1"),
            best_bid_price=Decimal("49999.00"),
            best_bid_quantity=Decimal("0.5"),
            best_ask_price=Decimal("50001.00"),
            best_ask_quantity=Decimal("0.3"),
            open_time=timestamp,
            close_time=timestamp,
            trade_count=1000,
            timestamp=timestamp
        )
        await publisher.publish_ticker(ticker)
        
        # 等待消息传递
        await asyncio.sleep(1.0)
        
        # 验证接收到的消息
        assert len(received_messages) >= 3
        
        # 验证消息类型
        subjects = [msg["subject"] for msg in received_messages]
        assert any("trade" in subject for subject in subjects)
        assert any("orderbook" in subject for subject in subjects)
        assert any("ticker" in subject for subject in subjects)
        
        # 验证消息内容
        for msg in received_messages:
            data = msg["data"]
            assert "exchange_name" in data
            assert "symbol_name" in data
            assert "timestamp" in data
            assert data["exchange_name"] == "binance"
            assert data["symbol_name"] == "BTCUSDT"
        
        # 清理
        await publisher.disconnect()
        await subscriber_nc.close()


class TestRealPerformance:
    """测试真实性能"""
    
    @pytest.mark.asyncio
    async def test_high_frequency_publishing(self, nats_config):
        """测试高频发布性能"""
        publisher = MarketDataPublisher(nats_config)
        await publisher.connect()
        
        # 发布大量消息
        message_count = 100
        start_time = time.time()
        
        for i in range(message_count):
            trade = NormalizedTrade(
                exchange_name="binance",
                symbol_name="BTCUSDT",
                trade_id=f"perf_test_{i}",
                price=Decimal(f"{50000 + i}"),
                quantity=Decimal("0.1"),
                quote_quantity=Decimal(f"{5000 + i}"),
                timestamp=datetime.now(timezone.utc),
                is_buyer_maker=True
            )
            result = await publisher.publish_trade(trade)
            assert result is True
        
        end_time = time.time()
        duration = end_time - start_time
        
        # 验证性能指标
        messages_per_second = message_count / duration
        print(f"发布性能: {messages_per_second:.2f} 消息/秒")
        
        # 性能应该大于10消息/秒
        assert messages_per_second > 10
        
        await publisher.disconnect()
    
    @pytest.mark.asyncio
    async def test_concurrent_publishing(self, nats_config):
        """测试并发发布"""
        publisher = MarketDataPublisher(nats_config)
        await publisher.connect()
        
        async def publish_batch(batch_id, count):
            results = []
            for i in range(count):
                trade = NormalizedTrade(
                    exchange_name="binance",
                    symbol_name="BTCUSDT",
                    trade_id=f"concurrent_{batch_id}_{i}",
                    price=Decimal(f"{50000 + batch_id * 1000 + i}"),
                    quantity=Decimal("0.1"),
                    quote_quantity=Decimal(f"{5000 + i}"),
                    timestamp=datetime.now(timezone.utc),
                    is_buyer_maker=True
                )
                result = await publisher.publish_trade(trade)
                results.append(result)
            return results
        
        # 并发发布
        batch_size = 20
        batch_count = 5
        
        start_time = time.time()
        tasks = [publish_batch(i, batch_size) for i in range(batch_count)]
        results = await asyncio.gather(*tasks)
        end_time = time.time()
        
        # 验证所有消息都成功发布
        total_messages = 0
        for batch_results in results:
            assert all(batch_results)
            total_messages += len(batch_results)
        
        assert total_messages == batch_size * batch_count
        
        duration = end_time - start_time
        messages_per_second = total_messages / duration
        print(f"并发发布性能: {messages_per_second:.2f} 消息/秒")
        
        await publisher.disconnect()


if __name__ == "__main__":
    # 运行测试前的说明
    print("=" * 60)
    print("真实NATS集成测试")
    print("=" * 60)
    print("运行此测试需要先启动NATS服务:")
    print("docker-compose up nats")
    print("=" * 60)
    
    pytest.main([__file__, "-v", "-s"]) 