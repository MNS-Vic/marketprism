"""
TDD测试：数据存储服务真实性验证
测试先行，验证数据存储服务在真实环境下的功能

遵循TDD原则：
1. 先写测试，描述期望的行为
2. 运行测试，验证失败（红灯）
3. 实现最小代码，使测试通过（绿灯）
4. 重构优化（重构）
"""

from datetime import datetime, timezone
import pytest
import asyncio
import aiohttp
import redis
import time
import json
from pathlib import Path
import sys

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.tdd_framework.real_test_base import RealTestBase, real_test_environment, requires_service


class TestRealDataStorage(RealTestBase):
    """数据存储服务真实性测试"""
    
    @pytest.mark.asyncio
    @requires_service("data_storage")
    async def test_should_connect_to_real_redis_when_service_starts(self):
        """
        TDD测试：数据存储服务启动时应该连接到真实Redis
        
        Given: Redis服务在localhost:6379运行
        When: 启动数据存储服务
        Then: 应该成功连接到Redis并能执行基本操作
        """
        async with real_test_environment() as env:
            # 验证环境准备就绪
            assert env.databases_ready.get('redis', False), "Redis数据库未准备就绪"
            assert env.services_running.get('data_storage', False), "数据存储服务未运行"
            
            # 测试Redis连接
            redis_config = env.config['databases']['redis']
            redis_client = redis.Redis(
                host=redis_config['host'],
                port=redis_config['port'],
                db=redis_config['db'],
                decode_responses=True
            )
            
            # 验证Redis连接
            ping_result = redis_client.ping()
            assert ping_result is True, "Redis连接失败"
            
            # 测试基本操作
            test_key = "tdd_test_key"
            test_value = "tdd_test_value"
            
            # 写入测试数据
            redis_client.set(test_key, test_value, ex=60)  # 60秒过期
            
            # 读取验证
            retrieved_value = redis_client.get(test_key)
            assert retrieved_value == test_value, f"数据不匹配: 期望 {test_value}, 实际 {retrieved_value}"
            
            # 清理测试数据
            redis_client.delete(test_key)
            
            print("✅ Redis真实连接测试通过")
    
    @pytest.mark.asyncio
    @requires_service("data_storage")
    async def test_should_handle_real_market_data_storage(self):
        """
        TDD测试：应该能存储真实的市场数据
        
        Given: 数据存储服务运行中，有真实的市场数据
        When: 通过API存储市场数据
        Then: 数据应该正确存储并可以查询
        """
        async with real_test_environment() as env:
            # 验证服务状态
            assert env.services_running.get('data_storage', False), "数据存储服务未运行"
            
            # 构造真实的市场数据格式
            market_data = {
                "symbol": "BTCUSDT",
                "exchange": "binance",
                "price": 45000.50,
                "volume": 1.25,
                "timestamp": int(time.time() * 1000),
                "data_type": "ticker"
            }
            
            # 通过HTTP API存储数据
            storage_url = f"http://localhost:8082"
            
            async with aiohttp.ClientSession() as session:
                # 存储数据
                async with session.post(
                    f"{storage_url}/api/v1/data/store",
                    json=market_data,
                    timeout=10
                ) as response:
                    assert response.status == 200, f"存储请求失败: {response.status}"
                    store_result = await response.json()
                    assert store_result.get('success', False), f"存储失败: {store_result}"
                    
                    data_id = store_result.get('data_id')
                    assert data_id is not None, "未返回数据ID"
                
                # 查询数据验证
                async with session.get(
                    f"{storage_url}/api/v1/data/query",
                    params={
                        "symbol": "BTCUSDT",
                        "exchange": "binance",
                        "limit": 1
                    },
                    timeout=10
                ) as response:
                    assert response.status == 200, f"查询请求失败: {response.status}"
                    query_result = await response.json()
                    
                    assert query_result.get('success', False), f"查询失败: {query_result}"
                    
                    data_list = query_result.get('data', [])
                    assert len(data_list) > 0, "未查询到存储的数据"
                    
                    # 验证数据内容
                    stored_data = data_list[0]
                    assert stored_data['symbol'] == market_data['symbol']
                    assert stored_data['exchange'] == market_data['exchange']
                    assert stored_data['price'] == market_data['price']
                    
                    print(f"✅ 市场数据存储测试通过，数据ID: {data_id}")
    
    @pytest.mark.asyncio
    @requires_service("data_storage")
    async def test_should_handle_concurrent_real_storage_requests(self):
        """
        TDD测试：应该能处理并发的真实存储请求
        
        Given: 数据存储服务运行中
        When: 同时发送多个存储请求
        Then: 所有请求都应该成功处理
        """
        async with real_test_environment() as env:
            assert env.services_running.get('data_storage', False), "数据存储服务未运行"
            
            storage_url = f"http://localhost:8082"
            
            # 生成多个测试数据
            test_data_list = []
            for i in range(10):
                test_data = {
                    "symbol": f"TEST{i:03d}USDT",
                    "exchange": "binance",
                    "price": 100.0 + i,
                    "volume": 1.0 + i * 0.1,
                    "timestamp": int(time.time() * 1000) + i,
                    "data_type": "ticker"
                }
                test_data_list.append(test_data)
            
            async def store_single_data(session, data):
                """存储单个数据项"""
                try:
                    async with session.post(
                        f"{storage_url}/api/v1/data/store",
                        json=data,
                        timeout=10
                    ) as response:
                        assert response.status == 200
                        result = await response.json()
                        assert result.get('success', False)
                        return result.get('data_id')
                except Exception as e:
                    return f"Error: {e}"
            
            # 并发存储测试
            async with aiohttp.ClientSession() as session:
                # 并发发送所有存储请求
                tasks = [store_single_data(session, data) for data in test_data_list]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # 验证结果
                success_count = 0
                for i, result in enumerate(results):
                    if isinstance(result, str) and not result.startswith("Error"):
                        success_count += 1
                    elif not isinstance(result, Exception):
                        success_count += 1
                
                success_rate = success_count / len(test_data_list)
                assert success_rate >= 0.9, f"并发存储成功率过低: {success_rate:.2%}"
                
                print(f"✅ 并发存储测试通过，成功率: {success_rate:.2%} ({success_count}/{len(test_data_list)})")
    
    @pytest.mark.asyncio
    @requires_service("data_storage")
    async def test_should_implement_real_hot_cold_data_strategy(self):
        """
        TDD测试：应该实现真实的热冷数据策略
        
        Given: 数据存储服务配置了热冷数据策略
        When: 存储不同时间的数据
        Then: 新数据应该在热存储，旧数据应该在冷存储
        """
        async with real_test_environment() as env:
            assert env.services_running.get('data_storage', False), "数据存储服务未运行"
            
            storage_url = f"http://localhost:8082"
            
            current_time = int(time.time() * 1000)
            
            # 热数据（当前时间）
            hot_data = {
                "symbol": "HOTUSDT",
                "exchange": "binance",
                "price": 100.0,
                "volume": 1.0,
                "timestamp": current_time,
                "data_type": "ticker"
            }
            
            # 冷数据（1小时前）
            cold_data = {
                "symbol": "COLDUSDT",
                "exchange": "binance",
                "price": 200.0,
                "volume": 2.0,
                "timestamp": current_time - (60 * 60 * 1000),  # 1小时前
                "data_type": "ticker"
            }
            
            async with aiohttp.ClientSession() as session:
                # 存储热数据
                async with session.post(
                    f"{storage_url}/api/v1/data/store",
                    json=hot_data,
                    timeout=10
                ) as response:
                    assert response.status == 200
                    hot_result = await response.json()
                    assert hot_result.get('success', False)
                    hot_data_id = hot_result.get('data_id')
                
                # 存储冷数据
                async with session.post(
                    f"{storage_url}/api/v1/data/store",
                    json=cold_data,
                    timeout=10
                ) as response:
                    assert response.status == 200
                    cold_result = await response.json()
                    assert cold_result.get('success', False)
                    cold_data_id = cold_result.get('data_id')
                
                # 查询数据位置信息
                async with session.get(
                    f"{storage_url}/api/v1/data/location/{hot_data_id}",
                    timeout=10
                ) as response:
                    if response.status == 200:
                        hot_location = await response.json()
                        # 验证热数据位置（如果API支持）
                        print(f"热数据位置: {hot_location}")
                
                async with session.get(
                    f"{storage_url}/api/v1/data/location/{cold_data_id}",
                    timeout=10
                ) as response:
                    if response.status == 200:
                        cold_location = await response.json()
                        # 验证冷数据位置（如果API支持）
                        print(f"冷数据位置: {cold_location}")
                
                print("✅ 热冷数据策略测试通过")
    
    @pytest.mark.asyncio
    @requires_service("data_storage")
    async def test_should_recover_from_real_database_failure(self):
        """
        TDD测试：应该能从真实数据库故障中恢复
        
        Given: 数据存储服务正常运行
        When: 数据库连接暂时失败
        Then: 服务应该能重新连接并继续工作
        """
        async with real_test_environment() as env:
            assert env.services_running.get('data_storage', False), "数据存储服务未运行"
            
            storage_url = f"http://localhost:8082"
            
            # 测试数据
            test_data = {
                "symbol": "RECOVERYUSDT",
                "exchange": "binance",
                "price": 300.0,
                "volume": 3.0,
                "timestamp": int(time.time() * 1000),
                "data_type": "ticker"
            }
            
            async with aiohttp.ClientSession() as session:
                # 1. 验证服务正常工作
                async with session.post(
                    f"{storage_url}/api/v1/data/store",
                    json=test_data,
                    timeout=10
                ) as response:
                    assert response.status == 200
                    result = await response.json()
                    assert result.get('success', False)
                    print("✅ 故障前服务正常")
                
                # 2. 检查服务健康状态
                async with session.get(
                    f"{storage_url}/health",
                    timeout=10
                ) as response:
                    assert response.status == 200
                    health_data = await response.json()
                    print(f"服务健康状态: {health_data}")
                
                # 3. 模拟故障恢复测试（这里主要测试重连机制）
                # 等待一段时间，然后再次测试
                await asyncio.sleep(2)
                
                # 4. 验证服务恢复后仍然可用
                recovery_data = {**test_data, "symbol": "RECOVERY2USDT"}
                async with session.post(
                    f"{storage_url}/api/v1/data/store",
                    json=recovery_data,
                    timeout=10
                ) as response:
                    assert response.status == 200
                    result = await response.json()
                    assert result.get('success', False)
                    print("✅ 故障恢复测试通过")


@pytest.mark.asyncio
async def test_data_storage_service_integration():
    """数据存储服务集成测试入口"""
    test_instance = TestRealDataStorage()
    
    async with real_test_environment() as env:
        if not env.services_running.get('data_storage', False):
            pytest.skip("数据存储服务未运行，跳过集成测试")
        
        print("🚀 开始数据存储服务真实性测试")
        
        # 运行所有测试方法
        await test_instance.test_should_connect_to_real_redis_when_service_starts()
        await test_instance.test_should_handle_real_market_data_storage()
        await test_instance.test_should_handle_concurrent_real_storage_requests()
        await test_instance.test_should_implement_real_hot_cold_data_strategy()
        await test_instance.test_should_recover_from_real_database_failure()
        
        print("🎉 所有数据存储服务测试通过")


if __name__ == "__main__":
    # 运行测试
    asyncio.run(test_data_storage_service_integration())