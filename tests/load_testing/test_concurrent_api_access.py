"""
MarketPrism API并发访问负载测试

测试API服务在高并发访问下的性能和稳定性
"""
from datetime import datetime, timezone
import sys
import os
import json
import time
import asyncio
import pytest
import statistics
import aiohttp
import random
from pathlib import Path
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor

# 添加项目根目录到系统路径
project_root = Path(__file__).parent.parent.parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 导入测试辅助工具
from tests.utils.data_factory import data_factory
from tests.utils.test_helpers import test_helpers

# API负载测试配置
API_LOAD_CONFIG = {
    "base_url": "http://localhost:8000",  # API服务地址
    "duration": 60,  # 测试持续时间(秒)
    "concurrent_users": [1, 5, 10, 20, 50, 100],  # 并发用户数
    "request_interval": 1.0,  # 用户请求间隔(秒)
    "endpoints": [
        "/api/v1/trades",
        "/api/v1/orderbooks",
        "/api/v1/klines",
        "/api/v1/funding_rates",
        "/api/v1/exchanges"
    ],
    "symbols": ["BTC/USDT", "ETH/USDT", "BNB/USDT"],
    "exchanges": ["binance", "deribit", "okex"]
}

# API负载测试基类
@pytest.mark.load
class ApiLoadTestBase:
    """API负载测试基类"""
    
    @staticmethod
    def calculate_api_metrics(requests_sent: int, 
                            requests_success: int,
                            requests_failed: int,
                            start_time: float,
                            end_time: float,
                            response_times: List[float] = None) -> Dict:
        """计算API性能指标"""
        duration = end_time - start_time
        
        metrics = {
            "duration_seconds": duration,
            "requests_sent": requests_sent,
            "requests_success": requests_success,
            "requests_failed": requests_failed,
            "success_rate": requests_success / requests_sent if requests_sent > 0 else 0,
            "requests_per_second": requests_sent / duration if duration > 0 else 0,
            "successful_requests_per_second": requests_success / duration if duration > 0 else 0
        }
        
        # 如果有响应时间数据，则计算响应时间指标
        if response_times and len(response_times) > 0:
            metrics.update({
                "avg_response_time_ms": statistics.mean(response_times) * 1000,
                "min_response_time_ms": min(response_times) * 1000,
                "max_response_time_ms": max(response_times) * 1000,
                "p50_response_time_ms": sorted(response_times)[len(response_times) // 2] * 1000,
                "p90_response_time_ms": sorted(response_times)[int(len(response_times) * 0.9)] * 1000,
                "p95_response_time_ms": sorted(response_times)[int(len(response_times) * 0.95)] * 1000,
                "p99_response_time_ms": sorted(response_times)[int(len(response_times) * 0.99)] * 1000
            })
        
        return metrics
    
    @staticmethod
    def print_api_load_report(test_name: str, metrics: Dict, config: Dict) -> None:
        """打印API负载测试报告"""
        print(f"\n=== {test_name} 负载测试报告 ===")
        print(f"配置: {json.dumps(config, indent=2)}")
        print(f"指标: {json.dumps(metrics, indent=2)}")
        print("=" * 50)


# API并发访问负载测试
@pytest.mark.load
class TestApiConcurrentAccess(ApiLoadTestBase):
    """测试API服务在并发访问下的性能"""
    
    @staticmethod
    async def _simulate_user_behavior(session, 
                                      base_url, 
                                      user_id, 
                                      duration, 
                                      request_interval,
                                      endpoints,
                                      symbols,
                                      exchanges,
                                      results):
        """模拟用户行为"""
        requests_sent = 0
        requests_success = 0
        requests_failed = 0
        response_times = []
        
        start_time = time.time()
        end_time = start_time + duration
        
        while time.time() < end_time:
            # 随机选择一个端点
            endpoint = random.choice(endpoints)
            
            # 构建请求参数
            params = {}
            
            if endpoint == "/api/v1/trades":
                # 交易查询
                params = {
                    "exchange": random.choice(exchanges),
                    "symbol": random.choice(symbols),
                    "limit": random.choice([10, 50, 100, 500])
                }
                # 随机添加时间范围
                if random.random() > 0.5:
                    end_ts = time.time()
                    start_ts = end_ts - random.choice([3600, 86400, 604800])  # 1小时、1天或1周
                    params["start_time"] = str(int(start_ts))
                    params["end_time"] = str(int(end_ts))
                    
            elif endpoint == "/api/v1/orderbooks":
                # 订单簿查询
                params = {
                    "exchange": random.choice(exchanges),
                    "symbol": random.choice(symbols)
                }
                # 随机添加时间戳
                if random.random() > 0.7:
                    params["timestamp"] = str(int(time.time() - random.randint(0, 3600)))
                    
            elif endpoint == "/api/v1/klines":
                # K线查询
                params = {
                    "exchange": random.choice(exchanges),
                    "symbol": random.choice(symbols),
                    "interval": random.choice(["1m", "5m", "15m", "1h", "4h", "1d"])
                }
                # 随机添加时间范围
                if random.random() > 0.3:
                    end_ts = time.time()
                    start_ts = end_ts - random.choice([3600, 86400, 604800])
                    params["start_time"] = str(int(start_ts))
                    params["end_time"] = str(int(end_ts))
                
                # 随机添加限制
                params["limit"] = random.choice([10, 50, 100, 200])
                    
            elif endpoint == "/api/v1/funding_rates":
                # 资金费率查询
                params = {
                    "exchange": random.choice(exchanges),
                    "symbol": random.choice([s for s in symbols if random.random() > 0.3])
                }
                
            # 发送请求
            url = base_url + endpoint
            req_start_time = time.time()
            
            try:
                requests_sent += 1
                async with session.get(url, params=params) as response:
                    req_end_time = time.time()
                    response_time = req_end_time - req_start_time
                    response_times.append(response_time)
                    
                    if response.status == 200:
                        requests_success += 1
                    else:
                        requests_failed += 1
            except Exception as e:
                req_end_time = time.time()
                requests_failed += 1
            
            # 等待间隔时间
            # 添加随机扰动，使请求更接近真实用户行为
            interval = request_interval * (0.5 + random.random())
            await asyncio.sleep(interval)
        
        # 记录结果
        results[user_id] = {
            "requests_sent": requests_sent,
            "requests_success": requests_success,
            "requests_failed": requests_failed,
            "response_times": response_times
        }
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("concurrent_users", API_LOAD_CONFIG["concurrent_users"])
    async def test_concurrent_access(self, concurrent_users):
        """测试并发访问性能"""
        if concurrent_users > 50:
            pytest.skip("并发用户数超过50，跳过测试")
            
        # 检查API服务是否可用
        base_url = API_LOAD_CONFIG["base_url"]
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{base_url}/api/v1/exchanges") as response:
                    if response.status != 200:
                        pytest.skip(f"API服务不可用: {response.status}")
        except:
            pytest.skip("API服务不可用")
        
        # 准备测试配置
        duration = API_LOAD_CONFIG["duration"]
        request_interval = API_LOAD_CONFIG["request_interval"]
        endpoints = API_LOAD_CONFIG["endpoints"]
        symbols = API_LOAD_CONFIG["symbols"]
        exchanges = API_LOAD_CONFIG["exchanges"]
        
        # 结果容器
        results = {}
        
        # 创建并发用户
        async with aiohttp.ClientSession() as session:
            # 创建用户任务
            tasks = []
            for user_id in range(concurrent_users):
                task = self._simulate_user_behavior(
                    session=session,
                    base_url=base_url,
                    user_id=user_id,
                    duration=duration,
                    request_interval=request_interval,
                    endpoints=endpoints,
                    symbols=symbols,
                    exchanges=exchanges,
                    results=results
                )
                tasks.append(task)
            
            # 启动所有用户任务
            start_time = time.time()
            await asyncio.gather(*tasks)
            end_time = time.time()
        
        # 汇总结果
        total_requests_sent = sum(r["requests_sent"] for r in results.values())
        total_requests_success = sum(r["requests_success"] for r in results.values())
        total_requests_failed = sum(r["requests_failed"] for r in results.values())
        all_response_times = []
        for r in results.values():
            all_response_times.extend(r["response_times"])
        
        # 计算性能指标
        metrics = self.calculate_api_metrics(
            requests_sent=total_requests_sent,
            requests_success=total_requests_success,
            requests_failed=total_requests_failed,
            start_time=start_time,
            end_time=end_time,
            response_times=all_response_times
        )
        
        config = {
            "concurrent_users": concurrent_users,
            "duration": duration,
            "request_interval": request_interval,
            "base_url": base_url
        }
        
        # 打印性能报告
        self.print_api_load_report("API并发访问", metrics, config)
        
        # 验证测试结果
        assert metrics["success_rate"] >= 0.95, f"请求成功率低于95%: {metrics['success_rate'] * 100}%"
        if all_response_times:
            assert metrics["p95_response_time_ms"] < 1000, f"95%响应时间超过1000ms: {metrics['p95_response_time_ms']}ms"


# API持续负载测试
@pytest.mark.load
class TestApiSustainedLoad(ApiLoadTestBase):
    """测试API服务在持续负载下的性能"""
    
    def test_sustained_load(self):
        """测试API服务在持续负载下的性能"""
        # 检查API服务是否可用
        base_url = API_LOAD_CONFIG["base_url"]
        try:
            import requests
            response = requests.get(f"{base_url}/api/v1/exchanges", timeout=5)
            if response.status_code != 200:
                pytest.skip(f"API服务不可用: {response.status_code}")
        except:
            pytest.skip("API服务不可用")
        
        # 测试配置
        test_duration = 300  # 5分钟
        concurrent_threads = 10
        ramp_up_time = 60  # 1分钟预热
        
        # 内部测试计数器
        class TestCounter:
            def __init__(self):
                self.requests_sent = 0
                self.requests_success = 0
                self.requests_failed = 0
                self.response_times = []
                self.lock = threading.Lock()
                
            def record_request(self, success, response_time=None):
                with self.lock:
                    self.requests_sent += 1
                    if success:
                        self.requests_success += 1
                    else:
                        self.requests_failed += 1
                    if response_time is not None:
                        self.response_times.append(response_time)
        
        counter = TestCounter()
        
        # 测试请求函数
        def make_requests(thread_id, end_time, ramp_up_end=None):
            session = requests.Session()
            
            # 计算请求间隔（根据线程ID调整以实现均匀分布）
            base_interval = 1.0
            interval = base_interval + (thread_id * 0.1)
            
            while time.time() < end_time:
                # 在预热阶段逐渐增加请求率
                if ramp_up_end and time.time() < ramp_up_end:
                    progress = (time.time() - (ramp_up_end - ramp_up_time)) / ramp_up_time
                    adjusted_interval = base_interval * (1.0 - (progress * 0.8))
                    current_interval = max(0.2, adjusted_interval)
                else:
                    current_interval = interval
                
                # 随机选择端点和参数
                endpoint = random.choice(API_LOAD_CONFIG["endpoints"])
                exchange = random.choice(API_LOAD_CONFIG["exchanges"])
                symbol = random.choice(API_LOAD_CONFIG["symbols"])
                
                params = {"exchange": exchange, "symbol": symbol}
                
                # 根据端点调整参数
                if endpoint == "/api/v1/klines":
                    params["interval"] = random.choice(["1m", "5m", "15m", "1h", "4h", "1d"])
                    params["limit"] = random.choice([10, 50, 100])
                
                url = base_url + endpoint
                
                # 发送请求
                try:
                    start_time = time.time()
                    response = session.get(url, params=params, timeout=10)
                    response_time = time.time() - start_time
                    
                    success = response.status_code == 200
                    counter.record_request(success, response_time)
                    
                except Exception as e:
                    counter.record_request(False)
                
                # 等待间隔时间
                interval_with_jitter = current_interval * (0.8 + random.random() * 0.4)
                time.sleep(interval_with_jitter)
        
        # 启动测试
        start_time = time.time()
        ramp_up_end = start_time + ramp_up_time
        end_time = start_time + test_duration
        
        with ThreadPoolExecutor(max_workers=concurrent_threads) as executor:
            futures = []
            for i in range(concurrent_threads):
                futures.append(executor.submit(make_requests, i, end_time, ramp_up_end))
            
            # 等待所有线程完成
            for future in futures:
                future.result()
        
        # 计算性能指标
        metrics = self.calculate_api_metrics(
            requests_sent=counter.requests_sent,
            requests_success=counter.requests_success,
            requests_failed=counter.requests_failed,
            start_time=start_time,
            end_time=time.time(),
            response_times=counter.response_times
        )
        
        config = {
            "concurrent_threads": concurrent_threads,
            "test_duration": test_duration,
            "ramp_up_time": ramp_up_time,
            "base_url": base_url
        }
        
        # 打印性能报告
        self.print_api_load_report("API持续负载", metrics, config)
        
        # 验证测试结果
        assert metrics["success_rate"] >= 0.95, f"请求成功率低于95%: {metrics['success_rate'] * 100}%"
        if counter.response_times:
            assert metrics["p95_response_time_ms"] < 1000, f"95%响应时间超过1000ms: {metrics['p95_response_time_ms']}ms"


if __name__ == "__main__":
    import threading  # 添加缺失的导入
    pytest.main(["-v", __file__])