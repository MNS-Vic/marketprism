#!/usr/bin/env python3
"""
OKX API备选方案和集成验证器
解决OKX API连接问题，实现智能备选方案和完整的集成验证

功能：
1. OKX API连接问题的智能诊断
2. 备选交易所API集成（Coinbase Pro、Kraken等）
3. 智能路由和故障转移机制
4. 完整的集成验证和性能测试
5. 告警系统集成测试
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
import requests
import aiohttp

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tests.utils.enhanced_api_client import EnhancedAPIClient
from config.alerting.marketprism_alert_rules import setup_marketprism_alerting

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class ExchangeConfig:
    """交易所配置"""
    name: str
    base_url: str
    endpoints: Dict[str, str]
    rate_limit: int  # 每秒请求数
    priority: int    # 优先级（1最高）
    enabled: bool = True

class ExchangeAPIManager:
    """交易所API管理器"""
    
    def __init__(self):
        self.exchanges = self._initialize_exchanges()
        self.client = EnhancedAPIClient()
        self.performance_stats = {}
        
    def _initialize_exchanges(self) -> Dict[str, ExchangeConfig]:
        """初始化支持的交易所"""
        return {
            'binance': ExchangeConfig(
                name='Binance',
                base_url='https://api.binance.com',
                endpoints={
                    'ping': '/api/v3/ping',
                    'time': '/api/v3/time',
                    'orderbook': '/api/v3/depth',
                    'ticker': '/api/v3/ticker/24hr'
                },
                rate_limit=10,  # 10 requests/second
                priority=1
            ),
            'okx': ExchangeConfig(
                name='OKX',
                base_url='https://www.okx.com',
                endpoints={
                    'ping': '/api/v5/public/time',
                    'time': '/api/v5/public/time',
                    'orderbook': '/api/v5/market/books',
                    'ticker': '/api/v5/market/ticker'
                },
                rate_limit=5,   # 5 requests/second
                priority=2
            ),
            'coinbase': ExchangeConfig(
                name='Coinbase Pro',
                base_url='https://api.exchange.coinbase.com',
                endpoints={
                    'ping': '/time',
                    'time': '/time',
                    'orderbook': '/products/{symbol}/book',
                    'ticker': '/products/{symbol}/ticker'
                },
                rate_limit=8,   # 8 requests/second
                priority=3
            ),
            'kraken': ExchangeConfig(
                name='Kraken',
                base_url='https://api.kraken.com',
                endpoints={
                    'ping': '/0/public/SystemStatus',
                    'time': '/0/public/Time',
                    'orderbook': '/0/public/Depth',
                    'ticker': '/0/public/Ticker'
                },
                rate_limit=6,   # 6 requests/second
                priority=4
            )
        }
    
    async def test_exchange_connectivity(self, exchange_name: str) -> Dict[str, Any]:
        """测试交易所连接性"""
        if exchange_name not in self.exchanges:
            return {'success': False, 'error': 'Exchange not supported'}
        
        exchange = self.exchanges[exchange_name]
        results = {}
        
        # 测试不同的端点
        test_endpoints = ['ping', 'time']
        
        for endpoint_name in test_endpoints:
            if endpoint_name not in exchange.endpoints:
                continue
                
            try:
                start_time = time.time()
                
                if exchange_name == 'binance':
                    if endpoint_name == 'ping':
                        result = self.client.test_binance_ping()
                    elif endpoint_name == 'time':
                        # Binance时间API测试
                        url = f"{exchange.base_url}/api/v3/time"
                        response = self.client.session.get(url, timeout=10)
                        result = {
                            'success': response.status_code == 200,
                            'response_time': time.time() - start_time,
                            'status_code': response.status_code
                        }
                        if result['success']:
                            data = response.json()
                            result['server_time'] = data.get('serverTime')
                
                elif exchange_name == 'okx':
                    if endpoint_name in ['ping', 'time']:
                        result = self.client.test_okx_time()
                
                elif exchange_name == 'coinbase':
                    # Coinbase Pro API测试
                    url = f"{exchange.base_url}{exchange.endpoints[endpoint_name]}"
                    response = self.client.session.get(url, timeout=10)
                    result = {
                        'success': response.status_code == 200,
                        'response_time': time.time() - start_time,
                        'status_code': response.status_code
                    }
                    if result['success']:
                        data = response.json()
                        result['server_time'] = data.get('iso') if endpoint_name == 'time' else None
                
                elif exchange_name == 'kraken':
                    # Kraken API测试
                    url = f"{exchange.base_url}{exchange.endpoints[endpoint_name]}"
                    response = self.client.session.get(url, timeout=10)
                    result = {
                        'success': response.status_code == 200,
                        'response_time': time.time() - start_time,
                        'status_code': response.status_code
                    }
                    if result['success']:
                        data = response.json()
                        if endpoint_name == 'time':
                            result['server_time'] = data.get('result', {}).get('unixtime')
                        elif endpoint_name == 'ping':
                            result['system_status'] = data.get('result', {}).get('status')
                
                results[endpoint_name] = result
                
            except Exception as e:
                results[endpoint_name] = {
                    'success': False,
                    'error': str(e),
                    'response_time': 0
                }
            
            # 避免过于频繁的请求
            await asyncio.sleep(1)
        
        # 计算总体成功率
        successful_tests = sum(1 for r in results.values() if r.get('success', False))
        total_tests = len(results)
        success_rate = (successful_tests / total_tests * 100) if total_tests > 0 else 0
        
        # 计算平均响应时间
        response_times = [r.get('response_time', 0) for r in results.values() if r.get('success', False)]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        return {
            'exchange': exchange_name,
            'success_rate': success_rate,
            'avg_response_time': avg_response_time,
            'test_results': results,
            'priority': exchange.priority,
            'enabled': exchange.enabled
        }
    
    async def test_all_exchanges(self) -> Dict[str, Any]:
        """测试所有交易所"""
        logger.info("🔍 开始测试所有交易所连接性...")
        
        results = {}
        
        for exchange_name in self.exchanges.keys():
            logger.info(f"测试 {exchange_name}...")
            result = await self.test_exchange_connectivity(exchange_name)
            results[exchange_name] = result
            
            status = "✅" if result['success_rate'] >= 50 else "❌"
            logger.info(f"{status} {exchange_name}: {result['success_rate']:.1f}% 成功率, "
                       f"平均响应时间: {result['avg_response_time']:.3f}s")
        
        return results
    
    def get_available_exchanges(self, min_success_rate: float = 50.0) -> List[str]:
        """获取可用的交易所列表"""
        available = []
        
        for exchange_name, stats in self.performance_stats.items():
            if stats.get('success_rate', 0) >= min_success_rate:
                available.append(exchange_name)
        
        # 按优先级排序
        available.sort(key=lambda x: self.exchanges[x].priority)
        return available
    
    def get_primary_exchange(self) -> Optional[str]:
        """获取主要交易所"""
        available = self.get_available_exchanges()
        return available[0] if available else None
    
    def get_fallback_exchanges(self) -> List[str]:
        """获取备选交易所"""
        available = self.get_available_exchanges()
        return available[1:] if len(available) > 1 else []

class IntegrationValidator:
    """集成验证器"""
    
    def __init__(self):
        self.exchange_manager = ExchangeAPIManager()
        self.alerting_system = None
        
    async def setup_alerting_system(self):
        """设置告警系统"""
        try:
            self.alerting_system = setup_marketprism_alerting()
            await self.alerting_system.start()
            logger.info("✅ 告警系统已启动")
            return True
        except Exception as e:
            logger.error(f"告警系统启动失败: {e}")
            return False
    
    async def test_alerting_integration(self) -> Dict[str, Any]:
        """测试告警系统集成"""
        if not self.alerting_system:
            return {'success': False, 'error': 'Alerting system not initialized'}
        
        logger.info("🚨 测试告警系统集成...")
        
        # 模拟一些指标数据
        test_metrics = {
            'service_up': 1,
            'binance_connection_status': 1,
            'okx_connection_status': 0,  # 模拟OKX连接问题
            'api_response_time_ms': 500,
            'api_error_rate_percent': 5,
            'memory_usage_percent': 60,
            'cpu_usage_percent': 45
        }
        
        # 评估告警规则
        alerts = await self.alerting_system.evaluate_rules(test_metrics)
        
        # 处理告警
        await self.alerting_system.process_alerts(alerts)
        
        # 获取统计信息
        stats = self.alerting_system.get_stats()
        
        return {
            'success': True,
            'triggered_alerts': len(alerts),
            'alert_details': [
                {
                    'rule_name': alert.rule_name,
                    'priority': alert.priority.value,
                    'summary': alert.summary
                } for alert in alerts
            ],
            'system_stats': stats
        }
    
    async def run_comprehensive_validation(self) -> Dict[str, Any]:
        """运行综合验证"""
        logger.info("🚀 开始MarketPrism集成综合验证...")
        
        validation_results = {
            'timestamp': time.time(),
            'exchange_connectivity': {},
            'alerting_system': {},
            'fallback_strategy': {},
            'recommendations': []
        }
        
        # 1. 测试交易所连接性
        logger.info("1️⃣ 测试交易所连接性...")
        exchange_results = await self.exchange_manager.test_all_exchanges()
        validation_results['exchange_connectivity'] = exchange_results
        self.exchange_manager.performance_stats = exchange_results
        
        # 2. 设置和测试告警系统
        logger.info("2️⃣ 设置和测试告警系统...")
        alerting_setup = await self.setup_alerting_system()
        if alerting_setup:
            alerting_results = await self.test_alerting_integration()
            validation_results['alerting_system'] = alerting_results
        else:
            validation_results['alerting_system'] = {'success': False, 'error': 'Setup failed'}
        
        # 3. 分析备选策略
        logger.info("3️⃣ 分析备选策略...")
        available_exchanges = self.exchange_manager.get_available_exchanges()
        primary_exchange = self.exchange_manager.get_primary_exchange()
        fallback_exchanges = self.exchange_manager.get_fallback_exchanges()
        
        validation_results['fallback_strategy'] = {
            'available_exchanges': available_exchanges,
            'primary_exchange': primary_exchange,
            'fallback_exchanges': fallback_exchanges,
            'total_available': len(available_exchanges)
        }
        
        # 4. 生成建议
        recommendations = self._generate_recommendations(validation_results)
        validation_results['recommendations'] = recommendations
        
        # 5. 生成报告
        await self._generate_validation_report(validation_results)
        
        return validation_results
    
    def _generate_recommendations(self, results: Dict[str, Any]) -> List[str]:
        """生成改进建议"""
        recommendations = []
        
        # 分析交易所连接性
        exchange_results = results['exchange_connectivity']
        available_count = len([e for e in exchange_results.values() if e['success_rate'] >= 50])
        
        if available_count == 0:
            recommendations.append("🚨 严重：所有交易所连接失败，需要立即检查网络配置和代理设置")
        elif available_count == 1:
            recommendations.append("⚠️ 警告：只有一个交易所可用，建议修复其他交易所连接以提高可靠性")
        elif available_count >= 2:
            recommendations.append("✅ 良好：多个交易所可用，具备良好的故障转移能力")
        
        # OKX特定建议
        okx_result = exchange_results.get('okx', {})
        if okx_result.get('success_rate', 0) < 50:
            recommendations.append("🔧 OKX连接问题：建议配置代理或使用备选交易所")
            recommendations.append("💡 运行OKX优化器：python scripts/okx_api_integration_optimizer.py")
        
        # Binance状态检查
        binance_result = exchange_results.get('binance', {})
        if binance_result.get('success_rate', 0) >= 80:
            recommendations.append("✅ Binance连接稳定，建议作为主要数据源")
        
        # 告警系统建议
        alerting_result = results['alerting_system']
        if alerting_result.get('success'):
            recommendations.append("✅ 告警系统运行正常，已配置生产级告警规则")
        else:
            recommendations.append("❌ 告警系统存在问题，需要检查配置")
        
        # 备选策略建议
        fallback_strategy = results['fallback_strategy']
        if fallback_strategy['total_available'] >= 2:
            recommendations.append(f"✅ 备选策略完善：主要交易所 {fallback_strategy['primary_exchange']}，"
                                 f"备选交易所 {', '.join(fallback_strategy['fallback_exchanges'])}")
        else:
            recommendations.append("⚠️ 建议增加更多可用的交易所以提高系统可靠性")
        
        return recommendations
    
    async def _generate_validation_report(self, results: Dict[str, Any]):
        """生成验证报告"""
        report_file = project_root / "tests" / "reports" / "integration_validation_report.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"📊 验证报告已保存: {report_file}")
        
        # 生成Markdown报告
        md_report = self._generate_markdown_report(results)
        md_file = report_file.with_suffix('.md')
        
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(md_report)
        
        logger.info(f"📄 Markdown报告已保存: {md_file}")
    
    def _generate_markdown_report(self, results: Dict[str, Any]) -> str:
        """生成Markdown格式报告"""
        md = "# 🔍 MarketPrism集成验证报告\n\n"
        
        # 概览
        md += "## 📊 验证概览\n\n"
        md += f"**验证时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        # 交易所连接性
        md += "\n## 🌐 交易所连接性测试\n\n"
        md += "| 交易所 | 成功率 | 平均响应时间 | 优先级 | 状态 |\n"
        md += "|--------|--------|--------------|--------|------|\n"
        
        for exchange, result in results['exchange_connectivity'].items():
            status = "🟢" if result['success_rate'] >= 80 else "🟡" if result['success_rate'] >= 50 else "🔴"
            md += f"| {result.get('exchange', exchange)} | {result['success_rate']:.1f}% | {result['avg_response_time']:.3f}s | {result['priority']} | {status} |\n"
        
        # 告警系统
        md += "\n## 🚨 告警系统测试\n\n"
        alerting_result = results['alerting_system']
        if alerting_result.get('success'):
            md += f"✅ **告警系统状态**: 正常运行\n"
            md += f"📊 **触发告警数**: {alerting_result.get('triggered_alerts', 0)}\n"
            
            if alerting_result.get('alert_details'):
                md += "\n**触发的告警**:\n"
                for alert in alerting_result['alert_details']:
                    md += f"- {alert['rule_name']} ({alert['priority']}): {alert['summary']}\n"
        else:
            md += "❌ **告警系统状态**: 存在问题\n"
        
        # 备选策略
        md += "\n## 🔄 备选策略分析\n\n"
        fallback = results['fallback_strategy']
        md += f"**主要交易所**: {fallback.get('primary_exchange', 'None')}\n"
        md += f"**备选交易所**: {', '.join(fallback.get('fallback_exchanges', []))}\n"
        md += f"**可用交易所总数**: {fallback.get('total_available', 0)}\n"
        
        # 建议
        md += "\n## 💡 改进建议\n\n"
        for i, rec in enumerate(results['recommendations'], 1):
            md += f"{i}. {rec}\n"
        
        # 结论
        md += "\n## 🎯 验证结论\n\n"
        available_count = fallback.get('total_available', 0)
        alerting_ok = alerting_result.get('success', False)
        
        if available_count >= 2 and alerting_ok:
            md += "🟢 **系统状态**: 优秀，可以安全部署到生产环境\n"
        elif available_count >= 1 and alerting_ok:
            md += "🟡 **系统状态**: 良好，建议优化后部署\n"
        else:
            md += "🔴 **系统状态**: 需要改进，暂不建议部署\n"
        
        md += f"\n---\n*报告生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}*\n"
        
        return md

async def main():
    """主函数"""
    validator = IntegrationValidator()
    
    try:
        results = await validator.run_comprehensive_validation()
        
        # 输出总结
        logger.info("\n" + "="*60)
        logger.info("🎯 MarketPrism集成验证完成")
        logger.info("="*60)
        
        # 交易所状态
        exchange_results = results['exchange_connectivity']
        available_exchanges = [e for e, r in exchange_results.items() if r['success_rate'] >= 50]
        logger.info(f"可用交易所: {len(available_exchanges)}/{len(exchange_results)}")
        
        # 告警系统状态
        alerting_ok = results['alerting_system'].get('success', False)
        logger.info(f"告警系统: {'✅ 正常' if alerting_ok else '❌ 异常'}")
        
        # 主要建议
        recommendations = results['recommendations']
        logger.info(f"\n💡 主要建议 (共{len(recommendations)}条):")
        for i, rec in enumerate(recommendations[:3], 1):  # 显示前3条
            logger.info(f"  {i}. {rec}")
        
        logger.info("="*60)
        
        # 停止告警系统
        if validator.alerting_system:
            await validator.alerting_system.stop()
        
        return 0 if len(available_exchanges) >= 1 and alerting_ok else 1
        
    except Exception as e:
        logger.error(f"验证过程失败: {e}")
        return 2

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
