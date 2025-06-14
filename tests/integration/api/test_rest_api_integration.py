#!/usr/bin/env python3
"""
REST API集成测试

测试REST API与后端服务的集成功能。
"""
import os
import sys
import time
import pytest
import json
from datetime import datetime, timezone
import asyncio
import requests
from unittest.mock import MagicMock, patch

# 调整系统路径，便于导入被测模块
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 尝试导入项目模块
try:
    # 这里导入待测试的API模块
    pass
except ImportError:
    print("无法导入API模块，使用模拟实现")


class TestRESTAPIIntegration:
    """测试REST API与其他系统组件的集成"""
    
    @pytest.fixture
    def api_client(self):
        """API客户端夹具"""
        base_url = os.environ.get("API_BASE_URL", "http://localhost:8080")
        
        # 如果设置了模拟标志，返回模拟客户端
        if not os.environ.get("USE_REAL_API", "").lower() in ("true", "1", "yes"):
            class MockAPIClient:
                def __init__(self, base_url):
                    self.base_url = base_url
                    self.responses = {
                        "/api/v1/trades/latest": {"success": True, "data": []},
                        "/api/v1/orderbook/latest": {"success": True, "data": {}},
                        "/api/v1/exchanges": {"success": True, "data": ["binance", "okex"]}
                    }
                
                def get(self, endpoint, params=None, timeout=5):
                    # 模拟GET请求
                    response = MagicMock()
                    response.json = lambda: self.responses.get(endpoint, {"success": False, "error": "未知端点"})
                    response.status_code = 200
                    return response
                
                def post(self, endpoint, json=None, timeout=5):
                    # 模拟POST请求
                    response = MagicMock()
                    response.json = lambda: {"success": True, "data": {}}
                    response.status_code = 200
                    return response
            
            return MockAPIClient(base_url)
        
        # 使用真实客户端
        return requests.Session()
    
    @pytest.mark.integration
    def test_get_trades_with_storage(self, api_client):
        """测试获取交易数据时与存储系统的集成"""
        # 准备测试参数
        exchange = "binance"
        symbol = "BTC/USDT"
        limit = 10
        
        # 构建请求URL
        url = f"{api_client.base_url}/api/v1/trades/latest"
        params = {"exchange": exchange, "symbol": symbol, "limit": limit}
        
        # 发送请求
        try:
            response = api_client.get(url, params=params)
            
            # 解析响应
            if hasattr(response, 'json'):
                data = response.json()
            else:
                data = response
            
            # 验证结果
            assert data["success"] is True
            assert "data" in data
            
            # 如果有真实数据，执行额外检查
            if len(data["data"]) > 0:
                trade = data["data"][0]
                assert "exchange" in trade
                assert "symbol" in trade
                assert "price" in trade
                assert "timestamp" in trade
        
        except requests.RequestException as e:
            pytest.skip(f"API请求失败: {str(e)}")
    
    @pytest.mark.integration
    def test_get_orderbook_with_storage(self, api_client):
        """测试获取订单簿数据时与存储系统的集成"""
        # 准备测试参数
        exchange = "binance"
        symbol = "BTC/USDT"
        
        # 构建请求URL
        url = f"{api_client.base_url}/api/v1/orderbook/latest"
        params = {"exchange": exchange, "symbol": symbol}
        
        # 发送请求
        try:
            response = api_client.get(url, params=params)
            
            # 解析响应
            if hasattr(response, 'json'):
                data = response.json()
            else:
                data = response
            
            # 验证结果
            assert data["success"] is True
            assert "data" in data
            
            # 如果有真实数据，执行额外检查
            if data["data"] and not isinstance(data["data"], list):
                orderbook = data["data"]
                assert "exchange" in orderbook
                assert "symbol" in orderbook
                assert "bids" in orderbook
                assert "asks" in orderbook
                assert "timestamp" in orderbook
        
        except requests.RequestException as e:
            pytest.skip(f"API请求失败: {str(e)}")
    
    @pytest.mark.integration
    def test_historical_data_query_flow(self, api_client):
        """测试历史数据查询流程，包括数据库交互"""
        # 准备测试参数
        exchange = "binance"
        symbol = "BTC/USDT"
        end_time = int(datetime.now().timestamp())
        start_time = end_time - 3600  # 过去一小时
        
        # 构建请求URL
        url = f"{api_client.base_url}/api/v1/trades/history"
        params = {
            "exchange": exchange,
            "symbol": symbol,
            "start_time": start_time,
            "end_time": end_time,
            "page": 1,
            "page_size": 50
        }
        
        # 发送请求
        try:
            response = api_client.get(url, params=params)
            
            # 解析响应
            if hasattr(response, 'json'):
                data = response.json()
            else:
                data = response
            
            # 验证结果
            assert data["success"] is True
            assert "data" in data
            
            # 验证分页信息
            if "pagination" in data:
                assert "page" in data["pagination"]
                assert "page_size" in data["pagination"]
                assert "total" in data["pagination"]
        
        except requests.RequestException as e:
            pytest.skip(f"API请求失败: {str(e)}")
    
    @pytest.mark.integration
    def test_exchange_list_from_config(self, api_client):
        """测试从配置系统获取交易所列表"""
        # 构建请求URL
        url = f"{api_client.base_url}/api/v1/exchanges"
        
        # 发送请求
        try:
            response = api_client.get(url)
            
            # 解析响应
            if hasattr(response, 'json'):
                data = response.json()
            else:
                data = response
            
            # 验证结果
            assert data["success"] is True
            assert "data" in data
            assert isinstance(data["data"], list)
            assert len(data["data"]) > 0
            
            # 验证是否包含主要交易所
            exchanges = data["data"]
            expected_exchanges = ["binance", "okex", "deribit"]
            found_exchanges = [ex for ex in expected_exchanges if ex in exchanges]
            assert len(found_exchanges) > 0, "未找到任何预期的交易所"
        
        except requests.RequestException as e:
            pytest.skip(f"API请求失败: {str(e)}")
    
    @pytest.mark.integration
    def test_api_authentication_flow(self, api_client):
        """测试API认证流程，包括身份验证系统集成"""
        # 跳过测试如果不是真实API测试
        if not os.environ.get("USE_REAL_API", "").lower() in ("true", "1", "yes"):
            pytest.skip("此测试需要真实API环境")
        
        # 准备认证信息
        auth_url = f"{api_client.base_url}/api/v1/auth/token"
        auth_data = {
            "username": os.environ.get("API_TEST_USER", "test_user"),
            "password": os.environ.get("API_TEST_PASSWORD", "test_password")
        }
        
        # 发送认证请求
        try:
            response = api_client.post(auth_url, json=auth_data)
            
            # 解析响应
            data = response.json()
            
            # 验证结果
            assert data["success"] is True
            assert "data" in data
            assert "token" in data["data"]
            
            # 使用获得的令牌访问受保护资源
            token = data["data"]["token"]
            protected_url = f"{api_client.base_url}/api/v1/user/profile"
            headers = {"Authorization": f"Bearer {token}"}
            
            profile_response = api_client.get(protected_url, headers=headers)
            profile_data = profile_response.json()
            
            # 验证认证后的响应
            assert profile_data["success"] is True
            assert "data" in profile_data
            assert "username" in profile_data["data"]
            assert profile_data["data"]["username"] == auth_data["username"]
        
        except requests.RequestException as e:
            pytest.skip(f"API请求失败: {str(e)}")
        except (KeyError, AssertionError) as e:
            pytest.fail(f"认证流程测试失败: {str(e)}")


# 直接运行测试文件
if __name__ == "__main__":
    pytest.main(["-v", __file__])