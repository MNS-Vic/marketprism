#!/usr/bin/env python3
"""
WebSocket API集成测试

测试WebSocket API与后端服务的集成功能。
"""
import os
import sys
import time
import pytest
import json
import datetime
import asyncio
import websockets
import signal
from unittest.mock import MagicMock, patch

# 调整系统路径，便于导入被测模块
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 尝试导入项目模块
try:
    # 这里导入待测试的WebSocket模块
    pass
except ImportError:
    print("无法导入WebSocket模块，使用模拟实现")


@pytest.mark.asyncio
class TestWebSocketAPIIntegration:
    """测试WebSocket API与其他系统组件的集成"""
    
    @pytest.fixture
    async def ws_client(self):
        """WebSocket客户端夹具"""
        ws_url = os.environ.get("WS_API_URL", "ws://localhost:8081")
        
        # 如果设置了模拟标志，返回模拟客户端
        if not os.environ.get("USE_REAL_API", "").lower() in ("true", "1", "yes"):
            class MockWebSocketClient:
                """模拟WebSocket客户端"""
                def __init__(self, url):
                    self.url = url
                    self.connected = False
                    self.messages = []
                    self.subscriptions = set()
                
                async def connect(self):
                    """模拟连接"""
                    self.connected = True
                    return self
                
                async def close(self):
                    """模拟关闭连接"""
                    self.connected = False
                
                async def send(self, message):
                    """模拟发送消息"""
                    if not self.connected:
                        raise Exception("WebSocket未连接")
                    
                    try:
                        data = json.loads(message)
                        if data.get("method") == "subscribe":
                            self.subscriptions.add(data.get("params", {}).get("channel", ""))
                        elif data.get("method") == "unsubscribe":
                            self.subscriptions.discard(data.get("params", {}).get("channel", ""))
                    except:
                        pass
                
                async def recv(self):
                    """模拟接收消息"""
                    if not self.connected:
                        raise Exception("WebSocket未连接")
                    
                    # 返回订阅确认或模拟数据
                    if not self.messages:
                        if self.subscriptions:
                            channel = next(iter(self.subscriptions))
                            if "trade" in channel:
                                return json.dumps({
                                    "channel": channel,
                                    "data": {
                                        "exchange": "binance",
                                        "symbol": "BTC/USDT",
                                        "price": 50000.0,
                                        "amount": 1.0,
                                        "timestamp": datetime.datetime.now().timestamp(),
                                        "trade_id": "binance_12345678",
                                        "side": "buy"
                                    }
                                })
                            elif "orderbook" in channel:
                                return json.dumps({
                                    "channel": channel,
                                    "data": {
                                        "exchange": "binance",
                                        "symbol": "BTC/USDT",
                                        "timestamp": datetime.datetime.now().timestamp(),
                                        "bids": [[50000.0, 1.0], [49990.0, 2.0]],
                                        "asks": [[50010.0, 1.0], [50020.0, 2.0]]
                                    }
                                })
                        
                        # 默认订阅确认
                        return json.dumps({
                            "type": "subscribed",
                            "channel": "system",
                            "data": {"status": "connected"}
                        })
                    else:
                        return self.messages.pop(0)
                
                def add_message(self, message):
                    """添加模拟消息到队列"""
                    self.messages.append(json.dumps(message) if isinstance(message, dict) else message)
            
            mock_client = MockWebSocketClient(ws_url)
            await mock_client.connect()
            return mock_client
        
        # 使用真实客户端
        try:
            real_ws = await websockets.connect(ws_url)
            return real_ws
        except Exception as e:
            pytest.skip(f"无法连接到WebSocket服务器: {str(e)}")
            # 返回一个占位符，不会实际使用
            mock_client = MagicMock()
            mock_client.connected = False
            return mock_client
    
    @pytest.mark.integration
    async def test_trade_subscription_flow(self, ws_client):
        """测试交易数据订阅流程"""
        # 准备订阅请求
        exchange = "binance"
        symbol = "BTC/USDT"
        
        subscription_message = {
            "method": "subscribe",
            "params": {
                "channel": f"trades.{exchange}.{symbol}"
            },
            "id": 1
        }
        
        # 发送订阅请求
        await ws_client.send(json.dumps(subscription_message))
        
        # 接收订阅确认消息
        confirmation = await ws_client.recv()
        confirmation_data = json.loads(confirmation)
        
        # 验证订阅确认
        assert "type" in confirmation_data or "method" in confirmation_data
        assert "subscribed" in confirmation_data.get("type", "") or "subscribe" in confirmation_data.get("method", "")
        
        # 接收数据消息
        received_messages = []
        
        # 设置超时时间
        timeout = 5
        start_time = time.time()
        
        # 接收多条消息或直到超时
        while time.time() - start_time < timeout and len(received_messages) < 3:
            try:
                message = await asyncio.wait_for(ws_client.recv(), timeout=1)
                received_messages.append(json.loads(message))
            except asyncio.TimeoutError:
                # 模拟客户端可能需要添加消息
                if hasattr(ws_client, 'add_message'):
                    ws_client.add_message({
                        "channel": f"trades.{exchange}.{symbol}",
                        "data": {
                            "exchange": exchange,
                            "symbol": symbol,
                            "price": 50000.0 + len(received_messages),
                            "amount": 1.0,
                            "timestamp": datetime.datetime.now().timestamp(),
                            "trade_id": f"{exchange}_{len(received_messages)}",
                            "side": "buy"
                        }
                    })
                continue
            except Exception as e:
                print(f"接收消息出错: {str(e)}")
                break
        
        # 验证接收到的数据
        assert len(received_messages) > 0, "未接收到任何消息"
        
        # 至少有一条消息应包含交易数据
        has_trade_data = False
        for msg in received_messages:
            if "data" in msg and isinstance(msg["data"], dict):
                data = msg["data"]
                if "exchange" in data and "price" in data:
                    has_trade_data = True
                    break
        
        assert has_trade_data, "未接收到包含交易数据的消息"
        
        # 发送取消订阅请求
        unsubscribe_message = {
            "method": "unsubscribe",
            "params": {
                "channel": f"trades.{exchange}.{symbol}"
            },
            "id": 2
        }
        
        await ws_client.send(json.dumps(unsubscribe_message))
        
        # 清理：关闭连接
        if hasattr(ws_client, 'close'):
            await ws_client.close()
    
    @pytest.mark.integration
    async def test_orderbook_update_flow(self, ws_client):
        """测试订单簿更新流程"""
        # 准备订阅请求
        exchange = "binance"
        symbol = "BTC/USDT"
        
        subscription_message = {
            "method": "subscribe",
            "params": {
                "channel": f"orderbook.{exchange}.{symbol}"
            },
            "id": 1
        }
        
        # 发送订阅请求
        await ws_client.send(json.dumps(subscription_message))
        
        # 接收订阅确认消息
        confirmation = await ws_client.recv()
        confirmation_data = json.loads(confirmation)
        
        # 验证订阅确认
        assert "type" in confirmation_data or "method" in confirmation_data
        
        # 接收订单簿快照和更新
        received_messages = []
        
        # 设置超时时间
        timeout = 5
        start_time = time.time()
        
        # 接收多条消息或直到超时
        while time.time() - start_time < timeout and len(received_messages) < 3:
            try:
                message = await asyncio.wait_for(ws_client.recv(), timeout=1)
                received_messages.append(json.loads(message))
            except asyncio.TimeoutError:
                # 模拟客户端可能需要添加消息
                if hasattr(ws_client, 'add_message'):
                    ws_client.add_message({
                        "channel": f"orderbook.{exchange}.{symbol}",
                        "data": {
                            "exchange": exchange,
                            "symbol": symbol,
                            "timestamp": datetime.datetime.now().timestamp(),
                            "bids": [[50000.0 - len(received_messages), 1.0], [49990.0, 2.0]],
                            "asks": [[50010.0 + len(received_messages), 1.0], [50020.0, 2.0]]
                        }
                    })
                continue
            except Exception as e:
                print(f"接收消息出错: {str(e)}")
                break
        
        # 验证接收到的数据
        assert len(received_messages) > 0, "未接收到任何消息"
        
        # 至少有一条消息应包含订单簿数据
        has_orderbook_data = False
        for msg in received_messages:
            if "data" in msg and isinstance(msg["data"], dict):
                data = msg["data"]
                if "bids" in data and "asks" in data:
                    has_orderbook_data = True
                    break
        
        assert has_orderbook_data, "未接收到包含订单簿数据的消息"
        
        # 发送取消订阅请求
        unsubscribe_message = {
            "method": "unsubscribe",
            "params": {
                "channel": f"orderbook.{exchange}.{symbol}"
            },
            "id": 2
        }
        
        await ws_client.send(json.dumps(unsubscribe_message))
        
        # 清理：关闭连接
        if hasattr(ws_client, 'close'):
            await ws_client.close()
    
    @pytest.mark.integration
    async def test_authentication_and_private_channel(self, ws_client):
        """测试WebSocket认证和私有频道流程"""
        # 跳过测试如果不是真实API测试
        if not os.environ.get("USE_REAL_API", "").lower() in ("true", "1", "yes"):
            if not hasattr(ws_client, 'add_message'):
                pytest.skip("此测试需要真实API环境或更复杂的模拟客户端")
        
        # 准备认证消息
        auth_message = {
            "method": "authenticate",
            "params": {
                "api_key": os.environ.get("API_TEST_KEY", "test_key"),
                "sign": os.environ.get("API_TEST_SIGN", "test_sign"),
                "timestamp": int(time.time() * 1000)
            },
            "id": 1
        }
        
        # 发送认证请求
        await ws_client.send(json.dumps(auth_message))
        
        # 接收认证响应
        auth_response = await ws_client.recv()
        auth_data = json.loads(auth_response)
        
        # 验证认证响应
        assert "success" in auth_data or "method" in auth_data
        
        # 如果是模拟客户端，添加认证确认消息
        if hasattr(ws_client, 'add_message'):
            ws_client.add_message({
                "method": "authenticate",
                "success": True,
                "id": 1
            })
            
            # 再次接收认证响应
            auth_response = await ws_client.recv()
            auth_data = json.loads(auth_response)
        
        # 验证认证成功
        assert auth_data.get("success", False) is True or "authenticated" in auth_data.get("type", "")
        
        # 订阅私有频道
        private_subscription = {
            "method": "subscribe",
            "params": {
                "channel": "user.orders"
            },
            "id": 2
        }
        
        await ws_client.send(json.dumps(private_subscription))
        
        # 接收订阅确认
        private_confirmation = await ws_client.recv()
        private_conf_data = json.loads(private_confirmation)
        
        # 验证私有频道订阅确认
        assert "channel" in private_conf_data or "method" in private_conf_data
        
        # 如果是模拟客户端，添加私有数据消息
        if hasattr(ws_client, 'add_message'):
            ws_client.add_message({
                "channel": "user.orders",
                "data": {
                    "order_id": "12345",
                    "status": "filled",
                    "symbol": "BTC/USDT",
                    "price": 50000.0,
                    "amount": 1.0,
                    "timestamp": datetime.datetime.now().timestamp()
                }
            })
        
        # 接收私有数据
        try:
            private_data = await asyncio.wait_for(ws_client.recv(), timeout=2)
            private_message = json.loads(private_data)
            
            # 验证私有数据
            assert "channel" in private_message
            assert private_message["channel"] == "user.orders" or "user" in private_message["channel"]
            
            if "data" in private_message:
                assert "order_id" in private_message["data"] or "status" in private_message["data"]
        
        except asyncio.TimeoutError:
            # 在真实环境中，可能不会立即收到私有数据
            pass
        
        # 清理：关闭连接
        if hasattr(ws_client, 'close'):
            await ws_client.close()


# 直接运行测试文件
if __name__ == "__main__":
    pytest.main(["-v", __file__])