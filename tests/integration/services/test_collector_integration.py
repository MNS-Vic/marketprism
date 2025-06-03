#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据采集服务集成测试
测试数据采集服务与NATS的集成
"""

import os
import sys
import pytest
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Any

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

# 标记为集成测试，只有加上--run-integration参数才会运行
pytestmark = pytest.mark.integration

class TestCollectorIntegration:
    """
    测试数据采集服务与NATS的集成
    """
    
    @pytest.fixture
    async def nats_client(self, test_config):
        """提供NATS客户端连接"""
        import nats
        
        # 从配置获取NATS连接信息
        nats_url = test_config["nats"]["url"]
        
        # 连接NATS
        client = await nats.connect(nats_url)
        yield client
        
        # 测试完成后关闭连接
        await client.close()
    
    @pytest.mark.asyncio
    async def test_collector_message_format(self, nats_client):
        """
        测试采集的消息格式是否符合预期
        """
        # 测试主题
        test_subject = "MARKET.TRADES.TEST"
        
        # 接收消息的容器
        received_messages = []
        done_receiving = asyncio.Event()
        
        # 消息处理函数
        async def message_handler(msg):
            try:
                data = json.loads(msg.data.decode())
                received_messages.append(data)
                
                # 当收到足够的消息后，触发完成事件
                if len(received_messages) >= 1:
                    done_receiving.set()
            except Exception as e:
                logging.error(f"处理消息时出错: {e}")
        
        # 订阅测试主题
        sub = await nats_client.subscribe(test_subject, cb=message_handler)
        
        # 模拟发布采集数据
        test_data = {
            "symbol": "BTC-USDT", 
            "price": "45000.50", 
            "volume": "1.234",
            "timestamp": int(datetime.now().timestamp()),
            "exchange": "binance",
            "trade_id": "test_collector_1",
            "side": "buy"
        }
        
        await nats_client.publish(test_subject, json.dumps(test_data).encode())
        
        # 等待消息处理完成或超时
        try:
            await asyncio.wait_for(done_receiving.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            assert False, "等待消息接收超时"
        
        # 取消订阅
        await sub.unsubscribe()
        
        # 验证收到的消息
        assert len(received_messages) > 0
        
        received_data = received_messages[0]
        assert received_data["symbol"] == test_data["symbol"]
        assert received_data["price"] == test_data["price"]
        assert received_data["volume"] == test_data["volume"]
        assert received_data["exchange"] == test_data["exchange"]
        assert received_data["trade_id"] == test_data["trade_id"]
        assert received_data["side"] == test_data["side"]
    
    @pytest.mark.asyncio
    async def test_collector_to_normalizer_flow(self, nats_client):
        """
        测试从采集器到标准化器的数据流
        """
        # 采集数据的主题和标准化数据的主题
        collector_subject = "MARKET.RAW.TEST"
        normalizer_subject = "MARKET.NORMALIZED.TEST"
        
        # 接收标准化数据的容器
        normalized_messages = []
        done_normalizing = asyncio.Event()
        
        # 标准化函数（模拟DataNormalizer）
        async def normalize_and_forward(msg):
            try:
                # 解析原始数据
                raw_data = json.loads(msg.data.decode())
                
                # 执行简单的标准化（转换价格和数量为浮点数）
                normalized_data = raw_data.copy()
                normalized_data["price"] = float(raw_data["price"])
                normalized_data["volume"] = float(raw_data["volume"])
                normalized_data["normalized_at"] = int(datetime.now().timestamp())
                
                # 发布到标准化数据主题
                await nats_client.publish(
                    normalizer_subject, 
                    json.dumps(normalized_data).encode()
                )
            except Exception as e:
                logging.error(f"标准化处理时出错: {e}")
        
        # 接收标准化数据的处理函数
        async def normalized_handler(msg):
            try:
                data = json.loads(msg.data.decode())
                normalized_messages.append(data)
                
                # 当收到消息后，触发完成事件
                done_normalizing.set()
            except Exception as e:
                logging.error(f"处理标准化消息时出错: {e}")
        
        # 订阅主题
        collector_sub = await nats_client.subscribe(collector_subject, cb=normalize_and_forward)
        normalized_sub = await nats_client.subscribe(normalizer_subject, cb=normalized_handler)
        
        # 发布测试数据（模拟采集服务）
        test_data = {
            "symbol": "ETH-USDT", 
            "price": "3200.75", 
            "volume": "2.5",
            "timestamp": int(datetime.now().timestamp()),
            "exchange": "binance",
            "trade_id": f"flow_test_{int(datetime.now().timestamp())}",
            "side": "sell"
        }
        
        await nats_client.publish(collector_subject, json.dumps(test_data).encode())
        
        # 等待标准化处理完成
        try:
            await asyncio.wait_for(done_normalizing.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            assert False, "等待消息标准化超时"
        
        # 取消订阅
        await collector_sub.unsubscribe()
        await normalized_sub.unsubscribe()
        
        # 验证标准化数据
        assert len(normalized_messages) > 0
        
        normalized = normalized_messages[0]
        assert normalized["symbol"] == test_data["symbol"]
        assert isinstance(normalized["price"], float)
        assert normalized["price"] == float(test_data["price"])
        assert isinstance(normalized["volume"], float)
        assert normalized["volume"] == float(test_data["volume"])
        assert "normalized_at" in normalized
        assert isinstance(normalized["normalized_at"], int)
    
    @pytest.mark.asyncio
    async def test_multi_exchange_collection(self, nats_client):
        """
        测试多交易所数据采集
        """
        # 测试交易所
        exchanges = ["binance", "okex", "deribit"]
        
        # 接收消息的容器
        received_by_exchange = {ex: [] for ex in exchanges}
        done_receiving = {ex: asyncio.Event() for ex in exchanges}
        
        # 为每个交易所创建处理函数
        async def create_handler(exchange):
            async def handler(msg):
                data = json.loads(msg.data.decode())
                received_by_exchange[exchange].append(data)
                
                # 当收到消息后，触发完成事件
                if len(received_by_exchange[exchange]) >= 1:
                    done_receiving[exchange].set()
            
            return handler
        
        # 订阅每个交易所的主题
        subscriptions = []
        for exchange in exchanges:
            handler = await create_handler(exchange)
            sub = await nats_client.subscribe(f"MARKET.TRADES.{exchange.upper()}.TEST", cb=handler)
            subscriptions.append(sub)
        
        # 为每个交易所发布模拟数据
        for exchange in exchanges:
            test_data = {
                "symbol": "BTC-USDT", 
                "price": "45000.50" if exchange == "binance" else ("45010.25" if exchange == "okex" else "44990.75"), 
                "volume": "1.0",
                "timestamp": int(datetime.now().timestamp()),
                "exchange": exchange,
                "trade_id": f"{exchange}_test_{int(datetime.now().timestamp())}",
                "side": "buy"
            }
            
            await nats_client.publish(
                f"MARKET.TRADES.{exchange.upper()}.TEST", 
                json.dumps(test_data).encode()
            )
        
        # 等待所有交易所的消息处理完成
        try:
            await asyncio.wait_for(
                asyncio.gather(*[done_receiving[ex].wait() for ex in exchanges]), 
                timeout=5.0
            )
        except asyncio.TimeoutError:
            # 检查哪些交易所没有收到消息
            missing = [ex for ex in exchanges if not done_receiving[ex].is_set()]
            assert False, f"等待消息接收超时，未收到以下交易所的消息: {missing}"
        
        # 取消所有订阅
        for sub in subscriptions:
            await sub.unsubscribe()
        
        # 验证每个交易所都收到了消息
        for exchange in exchanges:
            assert len(received_by_exchange[exchange]) > 0
            assert received_by_exchange[exchange][0]["exchange"] == exchange 