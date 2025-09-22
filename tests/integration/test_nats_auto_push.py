chong'fen"""
MarketPrism NATS自动推送功能集成测试

验证Data Collector的NATS自动推送功能是否正常工作
"""

import asyncio
import pytest
import aiohttp
import nats
import json
import time
from datetime import datetime, timezone


class TestNATSAutoPush:
    """NATS自动推送功能测试"""
    
    @pytest.fixture
    async def nats_client(self):
        """NATS客户端fixture"""
        nc = await nats.connect(servers=["nats://localhost:4222"])
        yield nc
        await nc.close()
    
    @pytest.fixture
    async def http_session(self):
        """HTTP会话fixture"""
        async with aiohttp.ClientSession() as session:
            yield session
    
    @pytest.mark.asyncio
    async def test_data_collector_status(self, http_session):
        """测试Data Collector服务状态"""
        async with http_session.get('http://localhost:8084/api/v1/status') as response:
            assert response.status == 200
            data = await response.json()
            
            service_data = data.get('data', {})
            assert service_data.get('status') == 'running'
            assert 'collection_stats' in service_data
            assert service_data.get('supported_exchanges')
    
    @pytest.mark.asyncio
    async def test_nats_server_connection(self, nats_client):
        """测试NATS服务器连接"""
        # 如果能创建客户端，说明连接正常
        assert nats_client is not None
        
        # 测试简单的发布/订阅
        received_messages = []
        
        async def message_handler(msg):
            received_messages.append(msg.data.decode())
        
        await nats_client.subscribe("test.subject", cb=message_handler)
        await nats_client.publish("test.subject", b"test message")
        
        # 等待消息传播
        await asyncio.sleep(0.1)
        
        assert len(received_messages) == 1
        assert received_messages[0] == "test message"
    
    @pytest.mark.asyncio
    async def test_nats_auto_push_functionality(self, nats_client):
        """测试NATS自动推送功能"""
        received_messages = []
        
        async def message_handler(msg):
            try:
                data = json.loads(msg.data.decode())
                received_messages.append({
                    'subject': msg.subject,
                    'data': data,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })
            except json.JSONDecodeError:
                pass
        
        # 订阅所有数据主题
        await nats_client.subscribe("orderbook.>", cb=message_handler)
        await nats_client.subscribe("trade.>", cb=message_handler)
        await nats_client.subscribe("volatility_index.>", cb=message_handler)

        # 监听30秒
        await asyncio.sleep(30)
        
        # 验证收到消息
        assert len(received_messages) > 0, "应该收到至少一条NATS消息"
        
        # 验证消息格式
        for msg in received_messages:
            assert 'subject' in msg
            assert 'data' in msg
            assert 'timestamp' in msg
            
            # 验证主题格式
            subject_parts = msg['subject'].split('.')
            assert len(subject_parts) >= 3
            assert subject_parts[0] in ['orderbook', 'trade', 'volatility_index']
            assert subject_parts[1] in ['binance', 'okx', 'deribit']
            
            # 验证数据内容
            data = msg['data']
            assert isinstance(data, dict)
            assert 'exchange' in data
            assert 'timestamp' in data
    
    @pytest.mark.asyncio
    async def test_data_collection_and_push_integration(self, http_session, nats_client):
        """测试数据收集和推送的集成"""
        # 获取初始统计
        async with http_session.get('http://localhost:8084/api/v1/status') as response:
            initial_data = await response.json()
            initial_stats = initial_data.get('data', {}).get('collection_stats', {})
            initial_collections = initial_stats.get('total_collections', 0)
        
        # 设置NATS消息监听
        received_messages = []
        
        async def message_handler(msg):
            try:
                data = json.loads(msg.data.decode())
                received_messages.append(msg.subject)
            except:
                pass
        
        await nats_client.subscribe("*.>", cb=message_handler)
        
        # 等待30秒收集数据
        await asyncio.sleep(30)
        
        # 获取新的统计
        async with http_session.get('http://localhost:8084/api/v1/status') as response:
            new_data = await response.json()
            new_stats = new_data.get('data', {}).get('collection_stats', {})
            new_collections = new_stats.get('total_collections', 0)
        
        # 验证数据收集有增长
        assert new_collections > initial_collections, "数据收集应该有增长"
        
        # 验证NATS消息有接收
        assert len(received_messages) > 0, "应该接收到NATS推送消息"
        
        # 验证消息主题格式
        valid_subjects = [subject for subject in received_messages 
                         if any(subject.startswith(prefix) for prefix in 
                               ['orderbook-data', 'trade-data', 'volatility-index'])]
        assert len(valid_subjects) > 0, "应该有有效格式的消息主题"
    
    @pytest.mark.asyncio
    async def test_multiple_exchange_data(self, nats_client):
        """测试多交易所数据推送"""
        exchange_messages = {}
        
        async def message_handler(msg):
            try:
                subject_parts = msg.subject.split('.')
                if len(subject_parts) >= 2:
                    exchange = subject_parts[1]
                    if exchange not in exchange_messages:
                        exchange_messages[exchange] = 0
                    exchange_messages[exchange] += 1
            except:
                pass
        
        await nats_client.subscribe("*.>", cb=message_handler)
        
        # 监听30秒
        await asyncio.sleep(30)
        
        # 验证至少有一个交易所的数据
        assert len(exchange_messages) > 0, "应该收到至少一个交易所的数据"
        
        # 验证交易所名称正确
        valid_exchanges = {'binance', 'okx', 'deribit'}
        for exchange in exchange_messages.keys():
            assert exchange in valid_exchanges, f"无效的交易所名称: {exchange}"
    
    def test_nats_py_version(self):
        """测试nats-py版本是否正确"""
        import nats
        
        # 检查版本是否为2.2.0
        # 注意：不同版本的nats-py可能有不同的版本属性
        try:
            version = nats.__version__
            assert version.startswith('2.2'), f"nats-py版本应该是2.2.x，当前版本: {version}"
        except AttributeError:
            # 如果没有__version__属性，至少确保能正常导入
            assert nats is not None


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])
