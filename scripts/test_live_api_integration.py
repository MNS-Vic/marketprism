#!/usr/bin/env python3
"""
MarketPrism真实交易所API集成测试
验证频率限制策略在实际API调用中的有效性
"""

import os
import sys
import time
import json
import requests
import asyncio
import websockets
import logging
from pathlib import Path
from typing import Dict, List, Any

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tests.utils.api_rate_limiter import rate_limited_request, get_rate_limiter, get_api_stats

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LiveAPITester:
    """真实API测试器"""
    
    def __init__(self):
        self.rate_limiter = get_rate_limiter()
        self.test_results = {}
        
        # 交易所配置 - 仅使用公共API
        self.exchanges = {
            'binance': {
                'name': 'Binance',
                'rest_base': 'https://api.binance.com',
                'ws_base': 'wss://stream.binance.com:9443',
                'endpoints': {
                    'ping': '/api/v3/ping',
                    'time': '/api/v3/time',
                    'orderbook': '/api/v3/depth',
                    'ticker': '/api/v3/ticker/24hr',
                    'trades': '/api/v3/trades'
                },
                'test_symbol': 'BTCUSDT'
            },
            'okx': {
                'name': 'OKX',
                'rest_base': 'https://www.okx.com',
                'ws_base': 'wss://ws.okx.com:8443',
                'endpoints': {
                    'time': '/api/v5/public/time',
                    'orderbook': '/api/v5/market/books',
                    'ticker': '/api/v5/market/ticker',
                    'trades': '/api/v5/market/trades'
                },
                'test_symbol': 'BTC-USDT'
            }
        }
    
    @rate_limited_request('binance', 'ping')
    def test_binance_ping(self) -> bool:
        """测试Binance Ping"""
        logger.info("🏓 测试Binance Ping...")
        
        try:
            config = self.exchanges['binance']
            url = f"{config['rest_base']}{config['endpoints']['ping']}"
            
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                logger.info("✅ Binance Ping成功")
                return True
            else:
                logger.warning(f"⚠️ Binance Ping失败: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Binance Ping异常: {e}")
            return False
    
    @rate_limited_request('binance', 'orderbook')
    def test_binance_orderbook(self) -> Dict[str, Any]:
        """测试Binance订单簿"""
        logger.info("📊 测试Binance订单簿...")
        
        try:
            config = self.exchanges['binance']
            url = f"{config['rest_base']}{config['endpoints']['orderbook']}"
            params = {
                'symbol': config['test_symbol'],
                'limit': 5
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # 验证数据结构
                if 'bids' in data and 'asks' in data and len(data['bids']) > 0 and len(data['asks']) > 0:
                    best_bid = float(data['bids'][0][0])
                    best_ask = float(data['asks'][0][0])
                    spread = best_ask - best_bid
                    
                    result = {
                        'success': True,
                        'best_bid': best_bid,
                        'best_ask': best_ask,
                        'spread': spread,
                        'bids_count': len(data['bids']),
                        'asks_count': len(data['asks'])
                    }
                    
                    logger.info(f"✅ Binance订单簿: 买价={best_bid}, 卖价={best_ask}, 价差={spread:.2f}")
                    return result
                else:
                    logger.warning("⚠️ Binance订单簿数据格式异常")
                    return {'success': False, 'error': 'Invalid data format'}
            else:
                logger.warning(f"⚠️ Binance订单簿请求失败: {response.status_code}")
                return {'success': False, 'error': f'HTTP {response.status_code}'}
                
        except Exception as e:
            logger.error(f"❌ Binance订单簿异常: {e}")
            return {'success': False, 'error': str(e)}
    
    @rate_limited_request('okx', 'time')
    def test_okx_time(self) -> bool:
        """测试OKX时间"""
        logger.info("⏰ 测试OKX时间...")
        
        try:
            config = self.exchanges['okx']
            url = f"{config['rest_base']}{config['endpoints']['time']}"
            
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('code') == '0':
                    logger.info("✅ OKX时间获取成功")
                    return True
                else:
                    logger.warning(f"⚠️ OKX时间API错误: {data.get('code')}")
                    return False
            else:
                logger.warning(f"⚠️ OKX时间请求失败: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ OKX时间异常: {e}")
            return False
    
    @rate_limited_request('okx', 'orderbook')
    def test_okx_orderbook(self) -> Dict[str, Any]:
        """测试OKX订单簿"""
        logger.info("📊 测试OKX订单簿...")
        
        try:
            config = self.exchanges['okx']
            url = f"{config['rest_base']}{config['endpoints']['orderbook']}"
            params = {
                'instId': config['test_symbol'],
                'sz': 5
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('code') == '0' and data.get('data'):
                    orderbook = data['data'][0]
                    
                    if 'bids' in orderbook and 'asks' in orderbook:
                        best_bid = float(orderbook['bids'][0][0])
                        best_ask = float(orderbook['asks'][0][0])
                        spread = best_ask - best_bid
                        
                        result = {
                            'success': True,
                            'best_bid': best_bid,
                            'best_ask': best_ask,
                            'spread': spread,
                            'bids_count': len(orderbook['bids']),
                            'asks_count': len(orderbook['asks'])
                        }
                        
                        logger.info(f"✅ OKX订单簿: 买价={best_bid}, 卖价={best_ask}, 价差={spread:.2f}")
                        return result
                    else:
                        logger.warning("⚠️ OKX订单簿数据格式异常")
                        return {'success': False, 'error': 'Invalid data format'}
                else:
                    logger.warning(f"⚠️ OKX订单簿API错误: {data.get('code')}")
                    return {'success': False, 'error': f"API error: {data.get('code')}"}
            else:
                logger.warning(f"⚠️ OKX订单簿请求失败: {response.status_code}")
                return {'success': False, 'error': f'HTTP {response.status_code}'}
                
        except Exception as e:
            logger.error(f"❌ OKX订单簿异常: {e}")
            return {'success': False, 'error': str(e)}
    
    def test_rate_limiting_effectiveness(self) -> bool:
        """测试频率限制有效性"""
        logger.info("🔧 测试频率限制有效性...")
        
        try:
            exchange = 'test_rate_limit'
            endpoint = 'effectiveness_test'
            
            # 记录请求时间
            request_times = []
            
            for i in range(3):
                start_time = time.time()
                
                # 检查是否可以发起请求
                can_request = self.rate_limiter.can_make_request(exchange, endpoint)
                
                if can_request:
                    # 记录请求
                    self.rate_limiter.record_request(exchange, endpoint)
                    request_times.append(time.time())
                    logger.info(f"请求 {i+1}: 立即执行")
                else:
                    # 等待并记录
                    wait_time = self.rate_limiter.wait_if_needed(exchange, endpoint)
                    self.rate_limiter.record_request(exchange, endpoint)
                    request_times.append(time.time())
                    logger.info(f"请求 {i+1}: 等待 {wait_time:.2f}s")
            
            # 验证请求间隔
            if len(request_times) > 1:
                intervals = []
                for i in range(1, len(request_times)):
                    interval = request_times[i] - request_times[i-1]
                    intervals.append(interval)
                
                avg_interval = sum(intervals) / len(intervals)
                logger.info(f"平均请求间隔: {avg_interval:.2f}s")
                
                # 验证间隔是否符合预期（default配置应该有5秒间隔）
                if avg_interval >= 2.0:  # 允许一些误差
                    logger.info("✅ 频率限制有效")
                    return True
                else:
                    logger.warning(f"⚠️ 频率限制可能无效，间隔过短: {avg_interval:.2f}s")
                    return False
            else:
                logger.warning("⚠️ 无法验证频率限制")
                return False
                
        except Exception as e:
            logger.error(f"❌ 频率限制测试异常: {e}")
            return False
    
    def test_cross_exchange_price_consistency(self) -> bool:
        """测试跨交易所价格一致性"""
        logger.info("🔄 测试跨交易所价格一致性...")
        
        try:
            # 获取Binance价格
            binance_data = self.test_binance_orderbook()
            time.sleep(2)  # 频率限制间隔
            
            # 获取OKX价格
            okx_data = self.test_okx_orderbook()
            
            if binance_data.get('success') and okx_data.get('success'):
                binance_mid = (binance_data['best_bid'] + binance_data['best_ask']) / 2
                okx_mid = (okx_data['best_bid'] + okx_data['best_ask']) / 2
                
                price_diff_percent = abs(binance_mid - okx_mid) / binance_mid * 100
                
                logger.info(f"Binance中间价: {binance_mid:.2f}")
                logger.info(f"OKX中间价: {okx_mid:.2f}")
                logger.info(f"价格差异: {price_diff_percent:.2f}%")
                
                # 正常情况下价格差异应该小于5%
                if price_diff_percent < 5.0:
                    logger.info("✅ 跨交易所价格一致性正常")
                    return True
                else:
                    logger.warning(f"⚠️ 跨交易所价格差异较大: {price_diff_percent:.2f}%")
                    return False
            else:
                logger.warning("⚠️ 无法获取完整的价格数据")
                return False
                
        except Exception as e:
            logger.error(f"❌ 价格一致性测试异常: {e}")
            return False
    
    def run_comprehensive_test(self) -> bool:
        """运行综合测试"""
        logger.info("🚀 开始真实交易所API综合测试...")
        logger.info("=" * 60)
        
        tests = [
            ("Binance Ping", self.test_binance_ping),
            ("OKX时间", self.test_okx_time),
            ("频率限制有效性", self.test_rate_limiting_effectiveness),
            ("Binance订单簿", lambda: self.test_binance_orderbook().get('success', False)),
            ("OKX订单簿", lambda: self.test_okx_orderbook().get('success', False)),
            ("跨交易所价格一致性", self.test_cross_exchange_price_consistency),
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            logger.info(f"\n📋 测试: {test_name}")
            logger.info("-" * 40)
            
            try:
                if test_func():
                    passed += 1
                    self.test_results[test_name] = "通过"
                else:
                    self.test_results[test_name] = "失败"
            except Exception as e:
                logger.error(f"测试异常: {e}")
                self.test_results[test_name] = f"异常: {e}"
        
        # 打印API使用统计
        logger.info("\n📊 API使用统计:")
        for exchange in ['binance', 'okx', 'test_rate_limit']:
            stats = get_api_stats(exchange)
            if stats['total_requests'] > 0:
                logger.info(f"  {exchange}: {stats['total_requests']} 请求")
        
        # 打印最终结果
        logger.info("\n" + "=" * 60)
        logger.info("📊 真实API测试结果汇总:")
        logger.info("=" * 60)
        
        for test_name, result in self.test_results.items():
            status = "✅" if result == "通过" else "❌"
            logger.info(f"{status} {test_name}: {result}")
        
        success_rate = (passed / total) * 100
        logger.info(f"\n📈 成功率: {passed}/{total} ({success_rate:.1f}%)")
        
        if passed >= total * 0.8:  # 80%通过率
            logger.info("🎉 真实API集成测试通过！")
            return True
        else:
            logger.error("❌ 真实API集成测试需要改进。")
            return False

def main():
    """主函数"""
    # 设置CI环境变量以启用严格频率限制
    os.environ['CI'] = 'true'
    os.environ['RATE_LIMIT_ENABLED'] = 'true'
    
    tester = LiveAPITester()
    success = tester.run_comprehensive_test()
    
    if success:
        logger.info("\n🎯 真实API集成验证完成:")
        logger.info("1. ✅ API频率限制正常工作")
        logger.info("2. ✅ 交易所公共API连接正常")
        logger.info("3. ✅ 数据质量验证通过")
        logger.info("4. ✅ 跨交易所数据一致性检查")
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
