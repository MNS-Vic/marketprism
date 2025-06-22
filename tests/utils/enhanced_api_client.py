"""
增强的API客户端 - 支持代理配置和CI/CD环境适配
专为MarketPrism CI/CD流程设计，自动处理本地开发和CI环境的网络差异
"""

import os
import sys
import yaml
import requests
import aiohttp
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union, List
from dataclasses import dataclass
import time

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tests.utils.api_rate_limiter import rate_limited_request, get_rate_limiter

logger = logging.getLogger(__name__)

@dataclass
class ProxyConfig:
    """代理配置数据类"""
    enabled: bool = False
    http_proxy: Optional[str] = None
    https_proxy: Optional[str] = None
    socks_proxy: Optional[str] = None
    no_proxy: Optional[str] = None
    timeout: int = 30

class EnhancedAPIClient:
    """增强的API客户端"""
    
    def __init__(self, environment: Optional[str] = None):
        # 首先配置日志
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.logger.setLevel(logging.INFO)

        self.environment = environment or self._detect_environment()
        self.proxy_config = self._load_proxy_config()
        self.rate_limiter = get_rate_limiter()

        # 创建会话
        self.session = self._create_session()

        self.logger.info(f"初始化API客户端 - 环境: {self.environment}, 代理: {self.proxy_config.enabled}")
    
    def _detect_environment(self) -> str:
        """自动检测运行环境"""
        # CI/CD环境检测
        if os.getenv('CI') or os.getenv('GITHUB_ACTIONS'):
            return 'ci'
        elif os.getenv('PYTEST_CURRENT_TEST'):
            return 'testing'
        elif os.getenv('MARKETPRISM_ENV'):
            return os.getenv('MARKETPRISM_ENV')
        else:
            return 'development'
    
    def _load_proxy_config(self) -> ProxyConfig:
        """加载代理配置"""
        try:
            proxy_file = project_root / 'config' / 'proxy.yaml'
            
            if not proxy_file.exists():
                self.logger.warning(f"代理配置文件不存在: {proxy_file}")
                return ProxyConfig()
            
            with open(proxy_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # 根据环境获取配置
            env_config = config.get('environments', {}).get(self.environment, {})
            data_collector_config = env_config.get('data-collector', {})
            
            if not data_collector_config.get('enabled', False):
                self.logger.info(f"环境 {self.environment} 未启用代理")
                return ProxyConfig()
            
            # 构建代理配置
            rest_api = data_collector_config.get('rest_api', {})
            websocket = data_collector_config.get('websocket', {})
            
            proxy_config = ProxyConfig(
                enabled=True,
                http_proxy=rest_api.get('http_proxy'),
                https_proxy=rest_api.get('https_proxy'),
                socks_proxy=websocket.get('socks_proxy'),
                no_proxy=data_collector_config.get('no_proxy'),
                timeout=rest_api.get('timeout', 30)
            )
            
            self.logger.info(f"加载代理配置成功: {proxy_config}")
            return proxy_config
            
        except Exception as e:
            self.logger.error(f"加载代理配置失败: {e}")
            return ProxyConfig()
    
    def _create_session(self) -> requests.Session:
        """创建配置好的requests会话"""
        session = requests.Session()
        
        # 设置通用headers
        session.headers.update({
            'User-Agent': 'MarketPrism/1.0 (CI/CD Test Client)',
            'Accept': 'application/json',
            'Connection': 'keep-alive'
        })
        
        # 配置代理
        if self.proxy_config.enabled:
            proxies = {}
            if self.proxy_config.http_proxy:
                proxies['http'] = self.proxy_config.http_proxy
            if self.proxy_config.https_proxy:
                proxies['https'] = self.proxy_config.https_proxy
            
            session.proxies.update(proxies)
            self.logger.info(f"配置代理: {proxies}")
        
        # 配置重试策略
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    @rate_limited_request('binance', 'ping')
    def test_binance_ping(self) -> Dict[str, Any]:
        """测试Binance连接"""
        try:
            url = "https://api.binance.com/api/v3/ping"
            response = self.session.get(url, timeout=self.proxy_config.timeout)
            
            result = {
                'success': response.status_code == 200,
                'status_code': response.status_code,
                'response_time': response.elapsed.total_seconds(),
                'proxy_used': self.proxy_config.enabled
            }
            
            if result['success']:
                self.logger.info(f"Binance Ping成功: {result['response_time']:.3f}s")
            else:
                self.logger.warning(f"Binance Ping失败: {response.status_code}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Binance Ping异常: {e}")
            return {
                'success': False,
                'error': str(e),
                'proxy_used': self.proxy_config.enabled
            }
    
    @rate_limited_request('binance', 'orderbook')
    def test_binance_orderbook(self, symbol: str = 'BTCUSDT') -> Dict[str, Any]:
        """测试Binance订单簿"""
        try:
            url = "https://api.binance.com/api/v3/depth"
            params = {'symbol': symbol, 'limit': 5}
            
            response = self.session.get(url, params=params, timeout=self.proxy_config.timeout)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'bids' in data and 'asks' in data and len(data['bids']) > 0 and len(data['asks']) > 0:
                    best_bid = float(data['bids'][0][0])
                    best_ask = float(data['asks'][0][0])
                    
                    result = {
                        'success': True,
                        'symbol': symbol,
                        'best_bid': best_bid,
                        'best_ask': best_ask,
                        'spread': best_ask - best_bid,
                        'bids_count': len(data['bids']),
                        'asks_count': len(data['asks']),
                        'response_time': response.elapsed.total_seconds(),
                        'proxy_used': self.proxy_config.enabled
                    }
                    
                    self.logger.info(f"Binance订单簿成功: {symbol}, 买价={best_bid}, 卖价={best_ask}")
                    return result
                else:
                    return {'success': False, 'error': 'Invalid data format', 'proxy_used': self.proxy_config.enabled}
            else:
                return {'success': False, 'status_code': response.status_code, 'proxy_used': self.proxy_config.enabled}
                
        except Exception as e:
            self.logger.error(f"Binance订单簿异常: {e}")
            return {'success': False, 'error': str(e), 'proxy_used': self.proxy_config.enabled}
    
    @rate_limited_request('okx', 'time')
    def test_okx_time(self) -> Dict[str, Any]:
        """测试OKX时间API（带增强错误处理和代理优化）"""
        try:
            url = "https://www.okx.com/api/v5/public/time"

            # 增强的超时和SSL配置
            timeout_config = (15, 45) if self.proxy_config.enabled else (10, 30)

            # 添加更多的请求头以提高成功率
            headers = {
                'User-Agent': 'MarketPrism/1.0 (CI/CD Test Client)',
                'Accept': 'application/json',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Cache-Control': 'no-cache'
            }

            response = self.session.get(
                url,
                timeout=timeout_config,
                verify=True,
                headers=headers,
                allow_redirects=True
            )

            if response.status_code == 200:
                data = response.json()

                result = {
                    'success': data.get('code') == '0',
                    'status_code': response.status_code,
                    'response_time': response.elapsed.total_seconds(),
                    'proxy_used': self.proxy_config.enabled,
                    'data': data,
                    'server_time': data.get('data', [{}])[0].get('ts') if data.get('data') else None
                }

                if result['success']:
                    self.logger.info(f"OKX时间API成功: {result['response_time']:.3f}s, 代理: {self.proxy_config.enabled}")
                else:
                    self.logger.warning(f"OKX时间API错误: {data.get('code')}")

                return result
            else:
                return {
                    'success': False,
                    'status_code': response.status_code,
                    'proxy_used': self.proxy_config.enabled,
                    'error': f'HTTP {response.status_code}'
                }

        except requests.exceptions.SSLError as e:
            self.logger.warning(f"OKX SSL错误 (常见于网络限制): {e}")
            return {
                'success': False,
                'error': 'SSL_ERROR',
                'error_detail': str(e),
                'proxy_used': self.proxy_config.enabled,
                'suggestion': '建议配置代理或检查SSL设置' if not self.proxy_config.enabled else '代理SSL配置可能需要调整'
            }
        except requests.exceptions.Timeout as e:
            self.logger.warning(f"OKX连接超时: {e}")
            return {
                'success': False,
                'error': 'TIMEOUT',
                'error_detail': str(e),
                'proxy_used': self.proxy_config.enabled,
                'suggestion': '建议配置代理或增加超时时间' if not self.proxy_config.enabled else '代理连接较慢，建议检查代理服务器'
            }
        except requests.exceptions.ConnectionError as e:
            self.logger.warning(f"OKX连接错误: {e}")
            return {
                'success': False,
                'error': 'CONNECTION_ERROR',
                'error_detail': str(e),
                'proxy_used': self.proxy_config.enabled,
                'suggestion': '网络连接问题，建议检查网络或代理配置'
            }
        except Exception as e:
            self.logger.error(f"OKX时间API异常: {e}")
            return {'success': False, 'error': str(e), 'proxy_used': self.proxy_config.enabled}
    
    @rate_limited_request('okx', 'orderbook')
    def test_okx_orderbook(self, symbol: str = 'BTC-USDT') -> Dict[str, Any]:
        """测试OKX订单簿（带增强错误处理和代理优化）"""
        try:
            url = "https://www.okx.com/api/v5/market/books"
            params = {'instId': symbol, 'sz': 5}

            # 根据代理状态调整超时
            timeout_config = (15, 45) if self.proxy_config.enabled else (10, 30)

            # 增强的请求头
            headers = {
                'User-Agent': 'MarketPrism/1.0 (CI/CD Test Client)',
                'Accept': 'application/json',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Cache-Control': 'no-cache'
            }

            response = self.session.get(
                url,
                params=params,
                timeout=timeout_config,
                verify=True,
                headers=headers,
                allow_redirects=True
            )

            if response.status_code == 200:
                data = response.json()

                if data.get('code') == '0' and data.get('data'):
                    orderbook = data['data'][0]

                    if 'bids' in orderbook and 'asks' in orderbook and orderbook['bids'] and orderbook['asks']:
                        best_bid = float(orderbook['bids'][0][0])
                        best_ask = float(orderbook['asks'][0][0])

                        # 数据质量验证
                        spread = best_ask - best_bid
                        spread_percentage = (spread / best_bid) * 100 if best_bid > 0 else 0

                        result = {
                            'success': True,
                            'symbol': symbol,
                            'best_bid': best_bid,
                            'best_ask': best_ask,
                            'spread': spread,
                            'spread_percentage': spread_percentage,
                            'bids_count': len(orderbook['bids']),
                            'asks_count': len(orderbook['asks']),
                            'response_time': response.elapsed.total_seconds(),
                            'proxy_used': self.proxy_config.enabled,
                            'timestamp': orderbook.get('ts'),
                            'data_quality': 'excellent' if spread_percentage < 0.1 else 'good' if spread_percentage < 0.5 else 'fair'
                        }

                        self.logger.info(f"OKX订单簿成功: {symbol}, 买价={best_bid}, 卖价={best_ask}, 价差={spread:.4f} ({spread_percentage:.3f}%), 代理: {self.proxy_config.enabled}")
                        return result
                    else:
                        return {
                            'success': False,
                            'error': 'Invalid orderbook data format or empty data',
                            'proxy_used': self.proxy_config.enabled,
                            'data_received': bool(data.get('data'))
                        }
                else:
                    return {
                        'success': False,
                        'error': f"API error: {data.get('code', 'unknown')}",
                        'proxy_used': self.proxy_config.enabled,
                        'api_message': data.get('msg', 'No message')
                    }
            else:
                return {
                    'success': False,
                    'status_code': response.status_code,
                    'proxy_used': self.proxy_config.enabled,
                    'error': f'HTTP {response.status_code}'
                }

        except requests.exceptions.SSLError as e:
            self.logger.warning(f"OKX订单簿SSL错误: {e}")
            return {
                'success': False,
                'error': 'SSL_ERROR',
                'error_detail': str(e),
                'proxy_used': self.proxy_config.enabled,
                'suggestion': '建议配置代理或检查SSL设置' if not self.proxy_config.enabled else '代理SSL配置可能需要调整'
            }
        except requests.exceptions.Timeout as e:
            self.logger.warning(f"OKX订单簿超时: {e}")
            return {
                'success': False,
                'error': 'TIMEOUT',
                'error_detail': str(e),
                'proxy_used': self.proxy_config.enabled,
                'suggestion': '建议配置代理或增加超时时间' if not self.proxy_config.enabled else '代理连接较慢，建议检查代理服务器'
            }
        except requests.exceptions.ConnectionError as e:
            self.logger.warning(f"OKX订单簿连接错误: {e}")
            return {
                'success': False,
                'error': 'CONNECTION_ERROR',
                'error_detail': str(e),
                'proxy_used': self.proxy_config.enabled,
                'suggestion': '网络连接问题，建议检查网络或代理配置'
            }
        except Exception as e:
            self.logger.error(f"OKX订单簿异常: {e}")
            return {'success': False, 'error': str(e), 'proxy_used': self.proxy_config.enabled}
    
    def run_comprehensive_test(self) -> Dict[str, Any]:
        """运行综合API测试"""
        self.logger.info(f"开始综合API测试 - 环境: {self.environment}")
        
        tests = [
            ("Binance Ping", self.test_binance_ping),
            ("Binance订单簿", self.test_binance_orderbook),
            ("OKX时间", self.test_okx_time),
            ("OKX订单簿", self.test_okx_orderbook),
        ]
        
        results = {}
        passed = 0
        
        for test_name, test_func in tests:
            self.logger.info(f"运行测试: {test_name}")
            
            try:
                result = test_func()
                results[test_name] = result
                
                if result.get('success', False):
                    passed += 1
                    self.logger.info(f"✅ {test_name} 通过")
                else:
                    error_msg = result.get('error', result.get('error_detail', '未知错误'))
                    self.logger.warning(f"❌ {test_name} 失败: {error_msg}")
                    
                    # 提供解决建议
                    if 'suggestion' in result:
                        self.logger.info(f"💡 建议: {result['suggestion']}")
                        
            except Exception as e:
                self.logger.error(f"❌ {test_name} 异常: {e}")
                results[test_name] = {'success': False, 'error': str(e)}
        
        # 生成总结报告
        total_tests = len(tests)
        success_rate = (passed / total_tests) * 100
        
        summary = {
            'environment': self.environment,
            'proxy_enabled': self.proxy_config.enabled,
            'total_tests': total_tests,
            'passed_tests': passed,
            'success_rate': success_rate,
            'results': results,
            'recommendations': self._generate_recommendations(results)
        }
        
        self.logger.info(f"测试完成: {passed}/{total_tests} 通过 ({success_rate:.1f}%)")
        
        return summary
    
    def _generate_recommendations(self, results: Dict[str, Any]) -> List[str]:
        """生成改进建议"""
        recommendations = []
        
        # 检查OKX连接问题
        okx_tests = [k for k in results.keys() if 'OKX' in k]
        okx_failures = [k for k in okx_tests if not results[k].get('success', False)]
        
        if okx_failures:
            if self.environment == 'development' and not self.proxy_config.enabled:
                recommendations.append("本地开发环境建议配置代理以访问OKX API")
            elif any('SSL_ERROR' in results[k].get('error', '') for k in okx_failures):
                recommendations.append("OKX SSL连接问题，建议检查网络配置或使用代理")
            elif any('TIMEOUT' in results[k].get('error', '') for k in okx_failures):
                recommendations.append("OKX连接超时，建议增加超时时间或配置代理")
        
        # 检查Binance连接
        binance_tests = [k for k in results.keys() if 'Binance' in k]
        binance_success = all(results[k].get('success', False) for k in binance_tests)
        
        if binance_success:
            recommendations.append("Binance API连接稳定，可作为主要数据源")
        
        # 代理配置建议
        if self.environment == 'ci' and self.proxy_config.enabled:
            recommendations.append("CI环境不建议使用代理，可能影响性能")
        elif self.environment == 'development' and not self.proxy_config.enabled:
            recommendations.append("开发环境建议配置代理以确保API访问稳定性")
        
        return recommendations
    
    def close(self):
        """关闭客户端"""
        if hasattr(self, 'session'):
            self.session.close()

# 便捷函数
def create_api_client(environment: Optional[str] = None) -> EnhancedAPIClient:
    """创建API客户端"""
    return EnhancedAPIClient(environment)

def test_exchange_apis(environment: Optional[str] = None) -> Dict[str, Any]:
    """测试交易所API连接"""
    client = create_api_client(environment)
    try:
        return client.run_comprehensive_test()
    finally:
        client.close()
