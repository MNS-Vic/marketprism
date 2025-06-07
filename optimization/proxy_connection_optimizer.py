#!/usr/bin/env python3
"""
MarketPrism 代理连接优化器

基于Binance API文档优化：
1. 多端点支持（api.binance.com, api1-4.binance.com, api-gcp.binance.com）
2. 智能代理切换
3. 连接健康检查
4. 自动故障转移
"""

import asyncio
import aiohttp
import time
import yaml
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class ProxyConfig:
    """代理配置"""
    enabled: bool = True
    http_proxy: Optional[str] = None
    https_proxy: Optional[str] = None
    socks_proxy: Optional[str] = None
    no_proxy: str = "localhost,127.0.0.1"
    timeout: float = 10.0
    max_retries: int = 3


@dataclass
class EndpointConfig:
    """端点配置"""
    url: str
    priority: int  # 优先级，数字越小优先级越高
    description: str
    expected_performance: str  # "high", "medium", "low"
    stability: str  # "high", "medium", "low"


class ProxyConnectionOptimizer:
    """代理连接优化器
    
    特性：
    1. 多个Binance API端点支持
    2. 智能代理配置
    3. 连接健康检查
    4. 自动故障转移
    5. 性能监控
    """
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or Path(__file__).parent.parent / "config" / "collector_config.yaml"
        self.proxy_config = None
        self.endpoints = self._initialize_endpoints()
        self.connection_stats = {}
        self.healthy_endpoints = set()
        self.current_proxy = None
        
    def _initialize_endpoints(self) -> List[EndpointConfig]:
        """初始化Binance API端点（基于官方文档）"""
        return [
            # 主要端点
            EndpointConfig(
                url="https://api.binance.com",
                priority=1,
                description="主要API端点",
                expected_performance="high",
                stability="high"
            ),
            # 性能优化端点 (2023-05-26 文档)
            EndpointConfig(
                url="https://api1.binance.com",
                priority=2,
                description="性能优化端点1",
                expected_performance="high",
                stability="medium"
            ),
            EndpointConfig(
                url="https://api2.binance.com",
                priority=3,
                description="性能优化端点2",
                expected_performance="high",
                stability="medium"
            ),
            EndpointConfig(
                url="https://api3.binance.com",
                priority=4,
                description="性能优化端点3",
                expected_performance="high",
                stability="medium"
            ),
            EndpointConfig(
                url="https://api4.binance.com",
                priority=5,
                description="性能优化端点4",
                expected_performance="high",
                stability="medium"
            ),
            # GCP CDN端点 (2023-06-06 文档)
            EndpointConfig(
                url="https://api-gcp.binance.com",
                priority=6,
                description="GCP CDN端点",
                expected_performance="medium",
                stability="high"
            )
        ]
    
    def load_proxy_config(self) -> ProxyConfig:
        """加载代理配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            proxy_data = config_data.get('proxy', {})
            
            if not proxy_data.get('enabled', False):
                logger.warning("代理配置未启用")
                return ProxyConfig(enabled=False)
            
            # 优先使用rest_api配置
            rest_api_config = proxy_data.get('rest_api', {})
            http_proxy = rest_api_config.get('http_proxy') or proxy_data.get('http_proxy')
            https_proxy = rest_api_config.get('https_proxy') or proxy_data.get('https_proxy')
            
            # WebSocket SOCKS代理
            ws_config = proxy_data.get('websocket', {})
            socks_proxy = ws_config.get('socks_proxy')
            
            proxy_config = ProxyConfig(
                enabled=True,
                http_proxy=http_proxy,
                https_proxy=https_proxy,
                socks_proxy=socks_proxy,
                no_proxy=proxy_data.get('no_proxy', 'localhost,127.0.0.1'),
                timeout=proxy_data.get('timeout', 10.0),
                max_retries=proxy_data.get('max_retries', 3)
            )
            
            logger.info(f"代理配置已加载: HTTP={http_proxy}, HTTPS={https_proxy}, SOCKS={socks_proxy}")
            return proxy_config
            
        except Exception as e:
            logger.error(f"加载代理配置失败: {e}")
            return ProxyConfig(enabled=False)
    
    async def test_endpoint_connectivity(self, endpoint: EndpointConfig, 
                                       proxy_config: ProxyConfig) -> Dict[str, Any]:
        """测试端点连接性"""
        test_url = f"{endpoint.url}/api/v3/ping"
        
        # 构建代理配置
        proxy_url = None
        if proxy_config.enabled:
            proxy_url = proxy_config.https_proxy or proxy_config.http_proxy
        
        connector = aiohttp.TCPConnector(
            limit=10,
            limit_per_host=5,
            keepalive_timeout=30,
            enable_cleanup_closed=True
        )
        
        timeout = aiohttp.ClientTimeout(total=proxy_config.timeout)
        
        start_time = time.time()
        success = False
        error_msg = None
        status_code = None
        response_time = 0
        
        try:
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            ) as session:
                
                async with session.get(
                    test_url,
                    proxy=proxy_url
                ) as response:
                    response_time = (time.time() - start_time) * 1000
                    status_code = response.status
                    
                    if response.status == 200:
                        success = True
                        logger.info(f"✅ {endpoint.description}: {response_time:.1f}ms")
                    else:
                        error_msg = f"HTTP {response.status}"
                        logger.warning(f"⚠️ {endpoint.description}: {error_msg}")
                        
        except asyncio.TimeoutError:
            response_time = (time.time() - start_time) * 1000
            error_msg = "连接超时"
            logger.warning(f"⏰ {endpoint.description}: {error_msg}")
            
        except aiohttp.ClientError as e:
            response_time = (time.time() - start_time) * 1000
            error_msg = str(e)
            logger.warning(f"❌ {endpoint.description}: {error_msg}")
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            error_msg = f"未知错误: {str(e)}"
            logger.error(f"💥 {endpoint.description}: {error_msg}")
            
        finally:
            await connector.close()
        
        result = {
            'endpoint': endpoint,
            'success': success,
            'response_time_ms': response_time,
            'status_code': status_code,
            'error': error_msg,
            'proxy_used': proxy_url,
            'timestamp': time.time()
        }
        
        # 更新连接统计
        self.connection_stats[endpoint.url] = result
        
        if success:
            self.healthy_endpoints.add(endpoint.url)
        else:
            self.healthy_endpoints.discard(endpoint.url)
        
        return result
    
    async def test_proxy_configurations(self) -> Dict[str, Any]:
        """测试多种代理配置"""
        print("🔧 测试代理配置")
        print("-" * 50)
        
        base_config = self.load_proxy_config()
        
        # 准备测试配置
        test_configs = [
            ("配置文件代理", base_config),
            ("直连(无代理)", ProxyConfig(enabled=False))
        ]
        
        # 如果有多个代理配置，可以添加更多测试
        if base_config.http_proxy and base_config.http_proxy != base_config.https_proxy:
            alt_config = ProxyConfig(
                enabled=True,
                http_proxy=base_config.http_proxy,
                https_proxy=base_config.http_proxy,  # 使用HTTP代理作为HTTPS代理
                timeout=base_config.timeout
            )
            test_configs.append(("HTTP代理作为HTTPS", alt_config))
        
        test_results = {}
        
        for config_name, proxy_config in test_configs:
            print(f"\n📊 测试配置: {config_name}")
            if proxy_config.enabled:
                print(f"  HTTP代理: {proxy_config.http_proxy}")
                print(f"  HTTPS代理: {proxy_config.https_proxy}")
            else:
                print(f"  直连模式")
            
            config_results = []
            
            # 测试前3个端点（主要 + api1 + api2）
            for endpoint in self.endpoints[:3]:
                result = await self.test_endpoint_connectivity(endpoint, proxy_config)
                config_results.append(result)
                
                # 避免过于频繁的请求
                await asyncio.sleep(0.5)
            
            # 统计结果
            successful_tests = sum(1 for r in config_results if r['success'])
            avg_response_time = sum(r['response_time_ms'] for r in config_results if r['success'])
            avg_response_time = avg_response_time / successful_tests if successful_tests > 0 else 0
            
            test_results[config_name] = {
                'proxy_config': proxy_config,
                'results': config_results,
                'success_count': successful_tests,
                'total_tests': len(config_results),
                'success_rate': successful_tests / len(config_results),
                'avg_response_time_ms': avg_response_time
            }
            
            print(f"  ✅ 成功: {successful_tests}/{len(config_results)}")
            print(f"  ⚡ 平均响应: {avg_response_time:.1f}ms")
        
        return test_results
    
    async def find_optimal_configuration(self) -> Dict[str, Any]:
        """找到最优配置"""
        print("\n🎯 寻找最优配置")
        print("-" * 50)
        
        test_results = await self.test_proxy_configurations()
        
        # 评分算法
        best_config = None
        best_score = -1
        best_config_name = None
        
        for config_name, result in test_results.items():
            # 计算综合评分
            success_rate = result['success_rate']
            avg_response_time = result['avg_response_time_ms']
            
            # 评分公式：成功率权重70%，响应时间权重30%
            if success_rate > 0:
                # 响应时间分数：越快分数越高（最大1000ms，超过则为0分）
                time_score = max(0, (1000 - avg_response_time) / 1000)
                total_score = success_rate * 0.7 + time_score * 0.3
            else:
                total_score = 0
            
            print(f"📊 {config_name}:")
            print(f"  成功率: {success_rate:.1%}")
            print(f"  平均响应: {avg_response_time:.1f}ms")
            print(f"  综合评分: {total_score:.3f}")
            
            if total_score > best_score:
                best_score = total_score
                best_config = result['proxy_config']
                best_config_name = config_name
        
        print(f"\n🏆 最优配置: {best_config_name} (评分: {best_score:.3f})")
        
        return {
            'best_config_name': best_config_name,
            'best_config': best_config,
            'best_score': best_score,
            'all_results': test_results,
            'healthy_endpoints': list(self.healthy_endpoints)
        }
    
    async def create_optimized_session(self, optimal_config: ProxyConfig) -> aiohttp.ClientSession:
        """创建优化的会话"""
        connector = aiohttp.TCPConnector(
            limit=50,
            limit_per_host=10,
            keepalive_timeout=60,
            enable_cleanup_closed=True,
            use_dns_cache=True,
            family=0,  # 允许IPv4和IPv6
            ssl=False  # 对于代理连接，通常不需要验证SSL
        )
        
        timeout = aiohttp.ClientTimeout(
            total=optimal_config.timeout,
            connect=optimal_config.timeout / 2,
            sock_read=optimal_config.timeout
        )
        
        session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                'User-Agent': 'MarketPrism/1.0 (Optimized Proxy Client)'
            }
        )
        
        return session
    
    async def test_exchange_apis_with_optimal_config(self, optimal_config: ProxyConfig) -> Dict[str, Any]:
        """使用最优配置测试交易所API"""
        print("\n🌐 使用最优配置测试交易所API")
        print("-" * 50)
        
        # 测试端点配置
        test_apis = [
            {
                'name': 'Binance 24hr Ticker',
                'url': f"{self.endpoints[0].url}/api/v3/ticker/24hr?symbol=BTCUSDT",
                'timeout': 15.0
            },
            {
                'name': 'Binance Server Time',
                'url': f"{self.endpoints[0].url}/api/v3/time",
                'timeout': 10.0
            },
            {
                'name': 'Binance Exchange Info',
                'url': f"{self.endpoints[0].url}/api/v3/exchangeInfo?symbol=BTCUSDT",
                'timeout': 20.0
            },
            {
                'name': 'OKX Ticker',
                'url': "https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT",
                'timeout': 15.0
            }
        ]
        
        # 创建优化会话
        session = await self.create_optimized_session(optimal_config)
        
        results = []
        
        try:
            for api_config in test_apis:
                print(f"📡 测试 {api_config['name']}...")
                
                proxy_url = None
                if optimal_config.enabled:
                    proxy_url = optimal_config.https_proxy or optimal_config.http_proxy
                
                start_time = time.time()
                success = False
                error_msg = None
                data_size = 0
                
                try:
                    async with session.get(
                        api_config['url'],
                        proxy=proxy_url,
                        timeout=aiohttp.ClientTimeout(total=api_config['timeout'])
                    ) as response:
                        
                        response_time = (time.time() - start_time) * 1000
                        
                        if response.status == 200:
                            data = await response.json()
                            data_size = len(str(data))
                            success = True
                            print(f"  ✅ 成功: {response_time:.1f}ms, 数据: {data_size} bytes")
                        else:
                            error_msg = f"HTTP {response.status}"
                            print(f"  ❌ 失败: {error_msg}")
                            
                except asyncio.TimeoutError:
                    response_time = (time.time() - start_time) * 1000
                    error_msg = "超时"
                    print(f"  ⏰ 超时: {response_time:.1f}ms")
                    
                except Exception as e:
                    response_time = (time.time() - start_time) * 1000
                    error_msg = str(e)
                    print(f"  💥 错误: {error_msg}")
                
                results.append({
                    'api_name': api_config['name'],
                    'success': success,
                    'response_time_ms': response_time,
                    'data_size_bytes': data_size,
                    'error': error_msg,
                    'proxy_used': proxy_url
                })
                
                # 避免频率限制
                await asyncio.sleep(1.0)
                
        finally:
            await session.close()
        
        # 统计结果
        successful_apis = sum(1 for r in results if r['success'])
        total_apis = len(results)
        avg_response_time = sum(r['response_time_ms'] for r in results if r['success'])
        avg_response_time = avg_response_time / successful_apis if successful_apis > 0 else 0
        
        print(f"\n📊 测试总结:")
        print(f"  成功API: {successful_apis}/{total_apis}")
        print(f"  成功率: {successful_apis/total_apis:.1%}")
        print(f"  平均响应: {avg_response_time:.1f}ms")
        
        return {
            'successful_apis': successful_apis,
            'total_apis': total_apis,
            'success_rate': successful_apis / total_apis,
            'avg_response_time_ms': avg_response_time,
            'results': results,
            'proxy_config': optimal_config
        }
    
    def generate_optimized_config(self, optimal_result: Dict[str, Any]) -> str:
        """生成优化后的配置文件内容"""
        best_config = optimal_result['best_config']
        
        optimized_config = {
            'proxy': {
                'enabled': best_config.enabled,
                'rest_api': {
                    'http_proxy': best_config.http_proxy,
                    'https_proxy': best_config.https_proxy
                },
                'websocket': {
                    'socks_proxy': best_config.socks_proxy
                },
                'no_proxy': best_config.no_proxy,
                'timeout': best_config.timeout,
                'max_retries': best_config.max_retries
            },
            'exchanges': {
                'binance': {
                    'endpoints': [
                        {
                            'url': endpoint.url,
                            'priority': endpoint.priority,
                            'description': endpoint.description,
                            'healthy': endpoint.url in optimal_result['healthy_endpoints']
                        }
                        for endpoint in self.endpoints
                    ]
                }
            }
        }
        
        return yaml.dump(optimized_config, default_flow_style=False, allow_unicode=True)


async def main():
    """主函数"""
    print("🚀 MarketPrism 代理连接优化器")
    print("=" * 60)
    print("基于Binance API文档优化网络连接")
    print("=" * 60)
    
    optimizer = ProxyConnectionOptimizer()
    
    try:
        # 1. 寻找最优配置
        optimal_result = await optimizer.find_optimal_configuration()
        
        if optimal_result['best_score'] <= 0:
            print("\n❌ 未找到可用的配置，所有连接都失败了")
            return 1
        
        # 2. 使用最优配置测试实际API
        api_test_result = await optimizer.test_exchange_apis_with_optimal_config(
            optimal_result['best_config']
        )
        
        # 3. 生成优化建议
        print("\n💡 优化建议")
        print("-" * 50)
        
        if api_test_result['success_rate'] >= 0.75:
            print("✅ 当前配置表现良好")
            print(f"  建议使用: {optimal_result['best_config_name']}")
            
            if optimal_result['best_config'].enabled:
                print(f"  HTTP代理: {optimal_result['best_config'].http_proxy}")
                print(f"  HTTPS代理: {optimal_result['best_config'].https_proxy}")
            else:
                print("  使用直连模式")
        else:
            print("⚠️ 网络连接仍有问题，建议:")
            print("  1. 检查代理服务器是否正常运行")
            print("  2. 验证代理端口配置")
            print("  3. 检查防火墙设置")
            print("  4. 考虑使用不同的代理服务")
        
        # 4. 生成优化配置
        optimized_config_content = optimizer.generate_optimized_config(optimal_result)
        
        config_file = "optimized_proxy_config.yaml"
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write(optimized_config_content)
        
        print(f"\n📄 优化配置已保存到: {config_file}")
        
        # 5. 输出最终结果
        print("\n" + "=" * 60)
        print("📊 优化总结")
        print("=" * 60)
        print(f"最优配置: {optimal_result['best_config_name']}")
        print(f"连接成功率: {api_test_result['success_rate']:.1%}")
        print(f"平均响应时间: {api_test_result['avg_response_time_ms']:.1f}ms")
        print(f"可用端点: {len(optimal_result['healthy_endpoints'])}")
        
        if api_test_result['success_rate'] >= 0.5:
            print("🎉 代理优化成功!")
            return 0
        else:
            print("⚠️ 代理优化部分成功，仍需手动调整")
            return 1
            
    except Exception as e:
        print(f"\n💥 优化过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    print(f"\n🏁 代理优化完成，退出代码: {exit_code}")
    exit(exit_code)