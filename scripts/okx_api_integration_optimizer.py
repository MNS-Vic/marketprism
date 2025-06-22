#!/usr/bin/env python3
"""
OKX API集成优化器
专门解决OKX API连接问题，实现稳定的API集成

功能：
1. 自动检测网络环境和代理需求
2. 优化代理配置以提高OKX API连接成功率
3. 实施多重连接策略和故障转移
4. 验证OKX API在不同环境下的稳定性
"""

import os
import sys
import json
import yaml
import time
import asyncio
import logging
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
import aiohttp
import ssl

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tests.utils.enhanced_api_client import EnhancedAPIClient
from tests.utils.api_rate_limiter import get_rate_limiter

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class ProxyTestResult:
    """代理测试结果"""
    proxy_config: str
    success: bool
    response_time: float
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

class OKXAPIOptimizer:
    """OKX API集成优化器"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.config_dir = self.project_root / "config"
        self.proxy_config_file = self.config_dir / "proxy.yaml"
        
        # OKX API端点
        self.okx_endpoints = {
            'time': 'https://www.okx.com/api/v5/public/time',
            'orderbook': 'https://www.okx.com/api/v5/market/books',
            'ticker': 'https://www.okx.com/api/v5/market/ticker',
            'instruments': 'https://www.okx.com/api/v5/public/instruments'
        }
        
        # 代理配置候选
        self.proxy_candidates = [
            {'http': 'http://127.0.0.1:1087', 'https': 'http://127.0.0.1:1087'},
            {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'},
            {'http': 'http://127.0.0.1:8080', 'https': 'http://127.0.0.1:8080'},
            {'http': 'http://127.0.0.1:3128', 'https': 'http://127.0.0.1:3128'},
            None  # 直连
        ]
        
        self.rate_limiter = get_rate_limiter()
    
    def detect_environment(self) -> str:
        """检测运行环境"""
        if os.getenv('CI') or os.getenv('GITHUB_ACTIONS'):
            return 'ci'
        elif os.getenv('PYTEST_CURRENT_TEST'):
            return 'testing'
        elif os.getenv('MARKETPRISM_ENV'):
            return os.getenv('MARKETPRISM_ENV')
        else:
            return 'development'
    
    def test_proxy_configuration(self, proxy_config: Optional[Dict[str, str]]) -> ProxyTestResult:
        """测试代理配置"""
        logger.info(f"测试代理配置: {proxy_config}")
        
        session = requests.Session()
        if proxy_config:
            session.proxies.update(proxy_config)
        
        # 增强的请求头
        session.headers.update({
            'User-Agent': 'MarketPrism/1.0 (OKX Integration Optimizer)',
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache'
        })
        
        try:
            start_time = time.time()
            
            # 测试OKX时间API
            response = session.get(
                self.okx_endpoints['time'],
                timeout=(15, 30),
                verify=True,
                allow_redirects=True
            )
            
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                if data.get('code') == '0':
                    return ProxyTestResult(
                        proxy_config=str(proxy_config),
                        success=True,
                        response_time=response_time,
                        details={
                            'status_code': response.status_code,
                            'server_time': data.get('data', [{}])[0].get('ts'),
                            'api_response': data
                        }
                    )
                else:
                    return ProxyTestResult(
                        proxy_config=str(proxy_config),
                        success=False,
                        response_time=response_time,
                        error=f"API error: {data.get('code')}",
                        details={'api_response': data}
                    )
            else:
                return ProxyTestResult(
                    proxy_config=str(proxy_config),
                    success=False,
                    response_time=response_time,
                    error=f"HTTP {response.status_code}"
                )
                
        except requests.exceptions.SSLError as e:
            return ProxyTestResult(
                proxy_config=str(proxy_config),
                success=False,
                response_time=0,
                error=f"SSL_ERROR: {str(e)}"
            )
        except requests.exceptions.Timeout as e:
            return ProxyTestResult(
                proxy_config=str(proxy_config),
                success=False,
                response_time=0,
                error=f"TIMEOUT: {str(e)}"
            )
        except requests.exceptions.ConnectionError as e:
            return ProxyTestResult(
                proxy_config=str(proxy_config),
                success=False,
                response_time=0,
                error=f"CONNECTION_ERROR: {str(e)}"
            )
        except Exception as e:
            return ProxyTestResult(
                proxy_config=str(proxy_config),
                success=False,
                response_time=0,
                error=f"UNKNOWN_ERROR: {str(e)}"
            )
        finally:
            session.close()
    
    def find_optimal_proxy(self) -> Optional[Dict[str, str]]:
        """寻找最优代理配置"""
        logger.info("开始寻找最优代理配置...")
        
        results = []
        
        for proxy_config in self.proxy_candidates:
            result = self.test_proxy_configuration(proxy_config)
            results.append(result)
            
            logger.info(f"代理测试结果: {result.proxy_config} - 成功: {result.success}, 响应时间: {result.response_time:.3f}s")
            
            if result.error:
                logger.warning(f"错误详情: {result.error}")
            
            # 避免过于频繁的请求
            time.sleep(2)
        
        # 选择最优配置
        successful_results = [r for r in results if r.success]
        
        if successful_results:
            # 按响应时间排序，选择最快的
            best_result = min(successful_results, key=lambda x: x.response_time)
            logger.info(f"找到最优代理配置: {best_result.proxy_config}, 响应时间: {best_result.response_time:.3f}s")
            
            # 解析代理配置
            if best_result.proxy_config == 'None':
                return None
            else:
                # 从字符串解析代理配置
                import ast
                try:
                    return ast.literal_eval(best_result.proxy_config)
                except:
                    return None
        else:
            logger.warning("未找到可用的代理配置")
            return None
    
    def update_proxy_config(self, optimal_proxy: Optional[Dict[str, str]]):
        """更新代理配置文件"""
        try:
            # 读取现有配置
            with open(self.proxy_config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            environment = self.detect_environment()
            
            # 更新配置
            if optimal_proxy:
                logger.info(f"更新{environment}环境代理配置: {optimal_proxy}")
                
                # 更新环境特定配置
                if 'environments' not in config:
                    config['environments'] = {}
                
                if environment not in config['environments']:
                    config['environments'][environment] = {}
                
                if 'data-collector' not in config['environments'][environment]:
                    config['environments'][environment]['data-collector'] = {}
                
                config['environments'][environment]['data-collector'].update({
                    'enabled': True,
                    'rest_api': {
                        'http_proxy': optimal_proxy['http'],
                        'https_proxy': optimal_proxy['https'],
                        'timeout': 30
                    },
                    'websocket': {
                        'socks_proxy': optimal_proxy['http'].replace('http://', 'socks5://'),
                        'timeout': 30
                    }
                })
            else:
                logger.info(f"直连可用，禁用{environment}环境代理")
                
                if 'environments' in config and environment in config['environments']:
                    if 'data-collector' in config['environments'][environment]:
                        config['environments'][environment]['data-collector']['enabled'] = False
            
            # 保存配置
            with open(self.proxy_config_file, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
            
            logger.info(f"代理配置已更新: {self.proxy_config_file}")
            
        except Exception as e:
            logger.error(f"更新代理配置失败: {e}")
    
    def comprehensive_okx_test(self) -> Dict[str, Any]:
        """全面的OKX API测试"""
        logger.info("开始全面OKX API测试...")
        
        # 使用增强的API客户端
        client = EnhancedAPIClient(self.detect_environment())
        
        tests = [
            ("OKX时间API", lambda: client.test_okx_time()),
            ("OKX订单簿", lambda: client.test_okx_orderbook('BTC-USDT')),
            ("OKX订单簿(ETH)", lambda: client.test_okx_orderbook('ETH-USDT')),
        ]
        
        results = {}
        passed = 0
        
        for test_name, test_func in tests:
            logger.info(f"执行测试: {test_name}")
            
            try:
                result = test_func()
                results[test_name] = result
                
                if result.get('success', False):
                    passed += 1
                    logger.info(f"✅ {test_name} 通过 - 响应时间: {result.get('response_time', 0):.3f}s")
                else:
                    error_msg = result.get('error', result.get('error_detail', '未知错误'))
                    logger.warning(f"❌ {test_name} 失败: {error_msg}")
                    
                    if 'suggestion' in result:
                        logger.info(f"💡 建议: {result['suggestion']}")
                        
            except Exception as e:
                logger.error(f"❌ {test_name} 异常: {e}")
                results[test_name] = {'success': False, 'error': str(e)}
            
            # 避免过于频繁的请求
            time.sleep(3)
        
        client.close()
        
        total_tests = len(tests)
        success_rate = (passed / total_tests) * 100
        
        summary = {
            'environment': self.detect_environment(),
            'total_tests': total_tests,
            'passed_tests': passed,
            'success_rate': success_rate,
            'results': results,
            'timestamp': time.time()
        }
        
        logger.info(f"OKX API测试完成: {passed}/{total_tests} 通过 ({success_rate:.1f}%)")
        
        return summary
    
    def generate_optimization_report(self, test_results: Dict[str, Any], optimal_proxy: Optional[Dict[str, str]]):
        """生成优化报告"""
        report = {
            'optimization_timestamp': time.time(),
            'environment': self.detect_environment(),
            'optimal_proxy_config': optimal_proxy,
            'test_results': test_results,
            'recommendations': []
        }
        
        # 生成建议
        if test_results['success_rate'] >= 80:
            report['recommendations'].append("OKX API集成状态良好，可以投入生产使用")
        elif test_results['success_rate'] >= 50:
            report['recommendations'].append("OKX API集成部分可用，建议进一步优化网络配置")
        else:
            report['recommendations'].append("OKX API集成存在问题，需要检查网络环境和代理配置")
        
        if optimal_proxy:
            report['recommendations'].append(f"建议使用代理配置: {optimal_proxy}")
        else:
            report['recommendations'].append("直连可用，无需配置代理")
        
        # 保存报告
        report_file = self.project_root / "tests" / "reports" / "okx_api_optimization_report.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"优化报告已保存: {report_file}")
        
        return report
    
    def run_optimization(self) -> Dict[str, Any]:
        """运行完整的OKX API优化流程"""
        logger.info("🚀 开始OKX API集成优化...")
        
        # 1. 寻找最优代理配置
        optimal_proxy = self.find_optimal_proxy()
        
        # 2. 更新代理配置
        self.update_proxy_config(optimal_proxy)
        
        # 3. 等待配置生效
        time.sleep(5)
        
        # 4. 全面测试
        test_results = self.comprehensive_okx_test()
        
        # 5. 生成报告
        report = self.generate_optimization_report(test_results, optimal_proxy)
        
        # 6. 输出总结
        logger.info("="*60)
        logger.info("🎯 OKX API优化完成")
        logger.info("="*60)
        logger.info(f"环境: {report['environment']}")
        logger.info(f"最优代理: {optimal_proxy or '直连'}")
        logger.info(f"测试成功率: {test_results['success_rate']:.1f}%")
        logger.info(f"通过测试: {test_results['passed_tests']}/{test_results['total_tests']}")
        
        for rec in report['recommendations']:
            logger.info(f"💡 建议: {rec}")
        
        logger.info("="*60)
        
        return report

def main():
    """主函数"""
    optimizer = OKXAPIOptimizer()
    result = optimizer.run_optimization()
    
    # 返回退出码
    if result['test_results']['success_rate'] >= 80:
        sys.exit(0)  # 成功
    elif result['test_results']['success_rate'] >= 50:
        sys.exit(1)  # 部分成功
    else:
        sys.exit(2)  # 失败

if __name__ == "__main__":
    main()
