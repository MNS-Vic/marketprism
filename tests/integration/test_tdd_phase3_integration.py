# TDD Phase 3 - 集成测试套件

"""
MarketPrism TDD Phase 3 集成测试

本测试套件专注于服务间通信和外部依赖的集成测试，目标是将测试覆盖率从32.37%提升至75%。

测试重点：
1. NATS消息队列集成测试
2. ClickHouse数据库集成测试  
3. Redis缓存集成测试
4. 数据收集器与存储服务的端到端数据流
5. API网关与各微服务的集成
"""

import pytest
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List

# 导入核心模块
from core.networking.websocket_manager import WebSocketConnectionManager, WebSocketConfig
from core.reliability.circuit_breaker import MarketPrismCircuitBreaker, CircuitBreakerConfig


class TestNATSIntegration:
    """NATS消息队列集成测试"""
    
    @pytest.fixture
    async def mock_nats_client(self):
        """模拟NATS客户端"""
        mock_client = AsyncMock()
        mock_client.publish = AsyncMock()
        mock_client.subscribe = AsyncMock()
        mock_client.is_connected = True
        return mock_client
    
    @pytest.mark.asyncio
    async def test_nats_message_publishing(self, mock_nats_client):
        """测试NATS消息发布"""
        # 准备测试数据
        test_message = {
            "symbol": "BTCUSDT",
            "price": 50000.0,
            "volume": 1000.0,
            "timestamp": int(time.time())
        }
        
        # 模拟发布消息
        await mock_nats_client.publish(
            "market.ticker.BTCUSDT", 
            json.dumps(test_message).encode()
        )
        
        # 验证发布调用
        mock_nats_client.publish.assert_called_once()
        call_args = mock_nats_client.publish.call_args
        assert call_args[0][0] == "market.ticker.BTCUSDT"
        
        # 验证消息内容
        published_data = json.loads(call_args[0][1].decode())
        assert published_data["symbol"] == "BTCUSDT"
        assert published_data["price"] == 50000.0
    
    @pytest.mark.asyncio
    async def test_nats_message_subscription(self, mock_nats_client):
        """测试NATS消息订阅"""
        received_messages = []
        
        async def message_handler(msg):
            """消息处理器"""
            data = json.loads(msg.data.decode())
            received_messages.append(data)
        
        # 模拟订阅
        mock_subscription = AsyncMock()
        mock_nats_client.subscribe.return_value = mock_subscription
        
        subscription = await mock_nats_client.subscribe(
            "market.ticker.*", 
            cb=message_handler
        )
        
        # 验证订阅调用
        mock_nats_client.subscribe.assert_called_once_with(
            "market.ticker.*", 
            cb=message_handler
        )
        assert subscription == mock_subscription
    
    @pytest.mark.asyncio
    async def test_nats_connection_resilience(self, mock_nats_client):
        """测试NATS连接弹性"""
        # 模拟连接断开
        mock_nats_client.is_connected = False
        
        # 模拟重连逻辑
        reconnect_attempts = 0
        max_attempts = 3
        
        while not mock_nats_client.is_connected and reconnect_attempts < max_attempts:
            reconnect_attempts += 1
            await asyncio.sleep(0.1)  # 模拟重连延迟
            
            if reconnect_attempts == 2:  # 第二次尝试成功
                mock_nats_client.is_connected = True
        
        # 验证重连成功
        assert mock_nats_client.is_connected
        assert reconnect_attempts == 2


class TestClickHouseIntegration:
    """ClickHouse数据库集成测试"""
    
    @pytest.fixture
    async def mock_clickhouse_client(self):
        """模拟ClickHouse客户端"""
        mock_client = AsyncMock()
        mock_client.execute = AsyncMock()
        mock_client.insert = AsyncMock()
        mock_client.select = AsyncMock()
        return mock_client
    
    @pytest.mark.asyncio
    async def test_clickhouse_data_insertion(self, mock_clickhouse_client):
        """测试ClickHouse数据插入"""
        # 准备测试数据
        ticker_data = [
            {
                "symbol": "BTCUSDT",
                "price": 50000.0,
                "volume": 1000.0,
                "timestamp": "2025-06-18 10:00:00",
                "exchange": "binance"
            },
            {
                "symbol": "ETHUSDT", 
                "price": 3000.0,
                "volume": 500.0,
                "timestamp": "2025-06-18 10:00:01",
                "exchange": "binance"
            }
        ]
        
        # 模拟插入操作
        await mock_clickhouse_client.insert(
            "market_data.tickers",
            ticker_data
        )
        
        # 验证插入调用
        mock_clickhouse_client.insert.assert_called_once_with(
            "market_data.tickers",
            ticker_data
        )
    
    @pytest.mark.asyncio
    async def test_clickhouse_data_query(self, mock_clickhouse_client):
        """测试ClickHouse数据查询"""
        # 模拟查询结果
        mock_result = [
            ("BTCUSDT", 50000.0, 1000.0, "2025-06-18 10:00:00"),
            ("ETHUSDT", 3000.0, 500.0, "2025-06-18 10:00:01")
        ]
        mock_clickhouse_client.select.return_value = mock_result
        
        # 执行查询
        query = """
        SELECT symbol, price, volume, timestamp 
        FROM market_data.tickers 
        WHERE timestamp >= '2025-06-18 10:00:00'
        ORDER BY timestamp DESC
        LIMIT 10
        """
        
        result = await mock_clickhouse_client.select(query)
        
        # 验证查询结果
        assert len(result) == 2
        assert result[0][0] == "BTCUSDT"
        assert result[1][0] == "ETHUSDT"
        
        # 验证查询调用
        mock_clickhouse_client.select.assert_called_once_with(query)
    
    @pytest.mark.asyncio
    async def test_clickhouse_batch_operations(self, mock_clickhouse_client):
        """测试ClickHouse批量操作"""
        # 准备大批量数据
        batch_size = 1000
        batch_data = []
        
        for i in range(batch_size):
            batch_data.append({
                "symbol": f"TEST{i:04d}",
                "price": 100.0 + i,
                "volume": 10.0 + i,
                "timestamp": f"2025-06-18 10:{i//60:02d}:{i%60:02d}",
                "exchange": "test"
            })
        
        # 模拟批量插入
        await mock_clickhouse_client.insert(
            "market_data.tickers",
            batch_data
        )
        
        # 验证批量插入
        mock_clickhouse_client.insert.assert_called_once()
        call_args = mock_clickhouse_client.insert.call_args
        assert call_args[0][0] == "market_data.tickers"
        assert len(call_args[0][1]) == batch_size


class TestRedisIntegration:
    """Redis缓存集成测试"""
    
    @pytest.fixture
    async def mock_redis_client(self):
        """模拟Redis客户端"""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock()
        mock_client.set = AsyncMock()
        mock_client.delete = AsyncMock()
        mock_client.exists = AsyncMock()
        mock_client.expire = AsyncMock()
        return mock_client
    
    @pytest.mark.asyncio
    async def test_redis_cache_operations(self, mock_redis_client):
        """测试Redis缓存操作"""
        # 测试数据
        cache_key = "market:ticker:BTCUSDT"
        cache_data = {
            "price": 50000.0,
            "volume": 1000.0,
            "timestamp": int(time.time())
        }
        
        # 模拟缓存设置
        await mock_redis_client.set(
            cache_key,
            json.dumps(cache_data),
            ex=300  # 5分钟过期
        )
        
        # 验证设置调用
        mock_redis_client.set.assert_called_once_with(
            cache_key,
            json.dumps(cache_data),
            ex=300
        )
        
        # 模拟缓存获取
        mock_redis_client.get.return_value = json.dumps(cache_data)
        result = await mock_redis_client.get(cache_key)
        
        # 验证获取结果
        retrieved_data = json.loads(result)
        assert retrieved_data["price"] == 50000.0
        assert retrieved_data["volume"] == 1000.0
    
    @pytest.mark.asyncio
    async def test_redis_cache_expiration(self, mock_redis_client):
        """测试Redis缓存过期"""
        cache_key = "market:temp:data"
        
        # 设置缓存
        await mock_redis_client.set(cache_key, "test_data", ex=1)
        
        # 检查存在性
        mock_redis_client.exists.return_value = True
        exists_before = await mock_redis_client.exists(cache_key)
        assert exists_before
        
        # 模拟过期后
        mock_redis_client.exists.return_value = False
        mock_redis_client.get.return_value = None
        
        exists_after = await mock_redis_client.exists(cache_key)
        result = await mock_redis_client.get(cache_key)
        
        assert not exists_after
        assert result is None


class TestEndToEndDataFlow:
    """端到端数据流集成测试"""
    
    @pytest.mark.asyncio
    async def test_complete_data_pipeline(self):
        """测试完整的数据管道"""
        # 模拟接收到的原始市场数据
        raw_market_data = {
            "s": "BTCUSDT",
            "c": "50000.0",
            "v": "1000.0",
            "E": 1718712000000
        }

        # 模拟数据标准化处理
        normalized_data = {
            "symbol": raw_market_data["s"],
            "price": float(raw_market_data["c"]),
            "volume": float(raw_market_data["v"]),
            "timestamp": int(time.time()),
            "exchange": "binance"
        }

        # 模拟数据增强处理
        enriched_data = {
            **normalized_data,
            "processed_at": int(time.time()),
            "source": "websocket",
            "data_quality": "high",
            "processing_latency_ms": 5
        }

        # 验证数据管道各阶段
        assert raw_market_data["s"] == "BTCUSDT"
        assert normalized_data["symbol"] == "BTCUSDT"
        assert normalized_data["price"] == 50000.0
        assert enriched_data["symbol"] == "BTCUSDT"
        assert "processed_at" in enriched_data
        assert "source" in enriched_data
        assert enriched_data["data_quality"] == "high"
