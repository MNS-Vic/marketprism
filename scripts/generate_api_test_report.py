#!/usr/bin/env python3
"""
MarketPrism真实API测试报告生成器
生成完整的API测试分析报告，包含代理配置建议和故障排除指南
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, List

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tests.utils.enhanced_api_client import test_exchange_apis
from tests.utils.api_rate_limiter import get_api_stats

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class APITestReportGenerator:
    """API测试报告生成器"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.reports_dir = self.project_root / "tests" / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
    
    def run_comprehensive_api_test(self) -> Dict[str, Any]:
        """运行综合API测试"""
        logger.info("🚀 开始综合API测试...")
        
        # 测试不同环境
        environments = ['development', 'ci', 'testing']
        test_results = {}
        
        for env in environments:
            logger.info(f"测试环境: {env}")
            try:
                result = test_exchange_apis(env)
                test_results[env] = result
                logger.info(f"环境 {env} 测试完成: {result['success_rate']:.1f}% 成功率")
            except Exception as e:
                logger.error(f"环境 {env} 测试失败: {e}")
                test_results[env] = {
                    'environment': env,
                    'error': str(e),
                    'success_rate': 0
                }
        
        return test_results
    
    def analyze_test_results(self, test_results: Dict[str, Any]) -> Dict[str, Any]:
        """分析测试结果"""
        logger.info("📊 分析测试结果...")
        
        analysis = {
            'overall_status': 'unknown',
            'best_environment': None,
            'worst_environment': None,
            'proxy_effectiveness': {},
            'exchange_reliability': {},
            'common_issues': [],
            'recommendations': []
        }
        
        # 分析环境性能
        env_scores = {}
        for env, result in test_results.items():
            if 'success_rate' in result:
                env_scores[env] = result['success_rate']
        
        if env_scores:
            analysis['best_environment'] = max(env_scores, key=env_scores.get)
            analysis['worst_environment'] = min(env_scores, key=env_scores.get)
            
            avg_success_rate = sum(env_scores.values()) / len(env_scores)
            if avg_success_rate >= 80:
                analysis['overall_status'] = 'excellent'
            elif avg_success_rate >= 60:
                analysis['overall_status'] = 'good'
            elif avg_success_rate >= 40:
                analysis['overall_status'] = 'fair'
            else:
                analysis['overall_status'] = 'poor'
        
        # 分析代理效果
        for env, result in test_results.items():
            if 'proxy_enabled' in result:
                proxy_key = f"{env}_proxy_{result['proxy_enabled']}"
                analysis['proxy_effectiveness'][proxy_key] = result.get('success_rate', 0)
        
        # 分析交易所可靠性
        exchange_stats = {'binance': [], 'okx': []}
        
        for env, result in test_results.items():
            if 'results' in result:
                for test_name, test_result in result['results'].items():
                    if 'Binance' in test_name:
                        exchange_stats['binance'].append(test_result.get('success', False))
                    elif 'OKX' in test_name:
                        exchange_stats['okx'].append(test_result.get('success', False))
        
        for exchange, results in exchange_stats.items():
            if results:
                success_rate = (sum(results) / len(results)) * 100
                analysis['exchange_reliability'][exchange] = success_rate
        
        # 识别常见问题
        common_errors = {}
        for env, result in test_results.items():
            if 'results' in result:
                for test_name, test_result in result['results'].items():
                    if not test_result.get('success', False):
                        error = test_result.get('error', 'unknown')
                        if error not in common_errors:
                            common_errors[error] = []
                        common_errors[error].append(f"{env}:{test_name}")
        
        analysis['common_issues'] = [
            {'error': error, 'occurrences': len(occurrences), 'details': occurrences}
            for error, occurrences in common_errors.items()
        ]
        
        # 生成建议
        analysis['recommendations'] = self._generate_comprehensive_recommendations(test_results, analysis)
        
        return analysis
    
    def _generate_comprehensive_recommendations(self, test_results: Dict[str, Any], analysis: Dict[str, Any]) -> List[str]:
        """生成综合建议"""
        recommendations = []
        
        # 基于整体状态的建议
        overall_status = analysis['overall_status']
        if overall_status == 'excellent':
            recommendations.append("🎉 API集成状态优秀，可以部署到生产环境")
        elif overall_status == 'good':
            recommendations.append("✅ API集成状态良好，建议解决少数问题后部署")
        elif overall_status == 'fair':
            recommendations.append("⚠️ API集成状态一般，需要解决关键问题")
        else:
            recommendations.append("❌ API集成状态较差，需要全面优化")
        
        # 基于交易所可靠性的建议
        exchange_reliability = analysis['exchange_reliability']
        if 'binance' in exchange_reliability:
            binance_rate = exchange_reliability['binance']
            if binance_rate >= 90:
                recommendations.append("Binance API连接稳定，建议作为主要数据源")
            elif binance_rate >= 70:
                recommendations.append("Binance API基本稳定，可作为主要数据源")
            else:
                recommendations.append("Binance API连接不稳定，需要检查网络配置")
        
        if 'okx' in exchange_reliability:
            okx_rate = exchange_reliability['okx']
            if okx_rate >= 90:
                recommendations.append("OKX API连接稳定，可作为备用数据源")
            elif okx_rate >= 50:
                recommendations.append("OKX API部分可用，建议优化连接配置")
            else:
                recommendations.append("OKX API连接问题较多，建议配置代理或寻找替代方案")
        
        # 基于常见问题的建议
        common_issues = analysis['common_issues']
        for issue in common_issues:
            error = issue['error']
            count = issue['occurrences']
            
            if 'SSL_ERROR' in error and count >= 2:
                recommendations.append("多次SSL错误，建议检查代理配置或网络环境")
            elif 'TIMEOUT' in error and count >= 2:
                recommendations.append("多次超时错误，建议增加超时时间或优化网络连接")
            elif 'Connection' in error and count >= 2:
                recommendations.append("多次连接错误，建议检查防火墙设置或代理配置")
        
        # 基于环境的建议
        best_env = analysis['best_environment']
        worst_env = analysis['worst_environment']
        
        if best_env and worst_env and best_env != worst_env:
            recommendations.append(f"环境 {best_env} 表现最佳，环境 {worst_env} 需要优化")
        
        # 代理配置建议
        proxy_effectiveness = analysis['proxy_effectiveness']
        if proxy_effectiveness:
            proxy_enabled_rates = [rate for key, rate in proxy_effectiveness.items() if 'True' in key]
            proxy_disabled_rates = [rate for key, rate in proxy_effectiveness.items() if 'False' in key]
            
            if proxy_enabled_rates and proxy_disabled_rates:
                avg_with_proxy = sum(proxy_enabled_rates) / len(proxy_enabled_rates)
                avg_without_proxy = sum(proxy_disabled_rates) / len(proxy_disabled_rates)
                
                if avg_with_proxy > avg_without_proxy + 10:
                    recommendations.append("代理配置显著提升连接成功率，建议在开发环境启用")
                elif avg_without_proxy > avg_with_proxy + 10:
                    recommendations.append("代理配置可能影响性能，建议在CI环境禁用")
        
        return recommendations
    
    def generate_markdown_report(self, test_results: Dict[str, Any], analysis: Dict[str, Any]) -> str:
        """生成Markdown格式报告"""
        md = "# 📊 MarketPrism真实交易所API测试完整报告\n\n"
        
        # 报告概览
        md += "## 🎯 测试概览\n\n"
        md += f"**测试时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        md += f"**测试环境数量**: {len(test_results)}\n"
        md += f"**整体状态**: {analysis['overall_status'].upper()}\n"
        md += f"**最佳环境**: {analysis['best_environment']}\n"
        md += f"**问题最多环境**: {analysis['worst_environment']}\n\n"
        
        # 环境测试结果
        md += "## 📈 环境测试结果\n\n"
        md += "| 环境 | 成功率 | 代理状态 | 通过测试 | 总测试 | 状态 |\n"
        md += "|------|--------|----------|----------|--------|------|\n"
        
        for env, result in test_results.items():
            if 'success_rate' in result:
                status_icon = "🟢" if result['success_rate'] >= 80 else "🟡" if result['success_rate'] >= 60 else "🔴"
                proxy_status = "✅" if result.get('proxy_enabled', False) else "❌"
                passed = result.get('passed_tests', 0)
                total = result.get('total_tests', 0)
                
                md += f"| {env} | {result['success_rate']:.1f}% | {proxy_status} | {passed} | {total} | {status_icon} |\n"
            else:
                md += f"| {env} | 错误 | - | - | - | 🔴 |\n"
        
        # 交易所可靠性分析
        md += "\n## 🏢 交易所可靠性分析\n\n"
        exchange_reliability = analysis['exchange_reliability']
        
        if exchange_reliability:
            md += "| 交易所 | 可靠性 | 状态 | 建议 |\n"
            md += "|--------|--------|------|------|\n"
            
            for exchange, reliability in exchange_reliability.items():
                status_icon = "🟢" if reliability >= 90 else "🟡" if reliability >= 70 else "🔴"
                if reliability >= 90:
                    suggestion = "主要数据源"
                elif reliability >= 70:
                    suggestion = "备用数据源"
                else:
                    suggestion = "需要优化"
                
                md += f"| {exchange.upper()} | {reliability:.1f}% | {status_icon} | {suggestion} |\n"
        else:
            md += "无可靠性数据\n"
        
        # 详细测试结果
        md += "\n## 🔍 详细测试结果\n\n"
        
        for env, result in test_results.items():
            md += f"### {env.upper()} 环境\n\n"
            
            if 'results' in result:
                md += "| 测试项目 | 状态 | 响应时间 | 错误信息 |\n"
                md += "|----------|------|----------|----------|\n"
                
                for test_name, test_result in result['results'].items():
                    status = "✅" if test_result.get('success', False) else "❌"
                    response_time = test_result.get('response_time', 0)
                    error = test_result.get('error', test_result.get('error_detail', '-'))
                    
                    md += f"| {test_name} | {status} | {response_time:.3f}s | {error} |\n"
            else:
                md += f"环境测试失败: {result.get('error', '未知错误')}\n"
            
            md += "\n"
        
        # 常见问题分析
        md += "## ⚠️ 常见问题分析\n\n"
        common_issues = analysis['common_issues']
        
        if common_issues:
            for i, issue in enumerate(common_issues, 1):
                md += f"### {i}. {issue['error']}\n\n"
                md += f"**出现次数**: {issue['occurrences']}\n"
                md += f"**影响范围**: {', '.join(issue['details'])}\n\n"
                
                # 提供解决方案
                error = issue['error']
                if 'SSL_ERROR' in error:
                    md += "**解决方案**:\n"
                    md += "- 检查代理配置是否正确\n"
                    md += "- 验证SSL证书设置\n"
                    md += "- 尝试使用不同的代理服务器\n\n"
                elif 'TIMEOUT' in error:
                    md += "**解决方案**:\n"
                    md += "- 增加连接超时时间\n"
                    md += "- 检查网络连接稳定性\n"
                    md += "- 配置代理服务器\n\n"
                elif 'Connection' in error:
                    md += "**解决方案**:\n"
                    md += "- 检查防火墙设置\n"
                    md += "- 验证代理配置\n"
                    md += "- 确认目标服务器可访问性\n\n"
        else:
            md += "未发现常见问题模式\n\n"
        
        # 改进建议
        md += "## 💡 改进建议\n\n"
        recommendations = analysis['recommendations']
        
        for i, rec in enumerate(recommendations, 1):
            md += f"{i}. {rec}\n"
        
        # 代理配置指南
        md += "\n## 🔧 代理配置指南\n\n"
        md += "### 本地开发环境\n\n"
        md += "如果在本地开发环境中遇到连接问题，请按以下步骤配置代理：\n\n"
        md += "1. **检查代理配置文件**: `config/proxy.yaml`\n"
        md += "2. **更新代理地址**: 确保代理服务器地址和端口正确\n"
        md += "3. **验证代理连接**: 使用 `curl --proxy http://127.0.0.1:1087 https://httpbin.org/ip` 测试\n"
        md += "4. **重启服务**: 重新启动数据收集服务以应用新配置\n\n"
        
        md += "### CI/CD环境\n\n"
        md += "GitHub Actions环境通常不需要代理配置：\n\n"
        md += "- ✅ GitHub服务器可直接访问大多数交易所API\n"
        md += "- ✅ 自动检测CI环境并禁用代理\n"
        md += "- ⚠️ 如遇连接问题，可能是临时网络问题或地理限制\n\n"
        
        # API使用统计
        md += "## 📊 API使用统计\n\n"
        
        # 获取API统计
        api_stats = {}
        for exchange in ['binance', 'okx']:
            stats = get_api_stats(exchange)
            if stats['total_requests'] > 0:
                api_stats[exchange] = stats
        
        if api_stats:
            md += "| 交易所 | 总请求数 | 最近1分钟 | 最近1小时 | 平均间隔 |\n"
            md += "|--------|----------|-----------|-----------|----------|\n"
            
            for exchange, stats in api_stats.items():
                avg_interval = stats.get('time_since_last_request', 0)
                md += f"| {exchange.upper()} | {stats['total_requests']} | {stats['requests_last_minute']} | {stats['requests_last_hour']} | {avg_interval:.1f}s |\n"
        else:
            md += "无API使用统计数据\n"
        
        # 结论
        md += "\n## 🎯 结论\n\n"
        overall_status = analysis['overall_status']
        
        if overall_status == 'excellent':
            md += "🎉 **MarketPrism真实API集成测试结果优秀**\n\n"
            md += "- 所有主要功能正常工作\n"
            md += "- API频率限制器运行稳定\n"
            md += "- 交易所连接可靠\n"
            md += "- 可以安全部署到生产环境\n"
        elif overall_status == 'good':
            md += "✅ **MarketPrism真实API集成测试结果良好**\n\n"
            md += "- 核心功能正常工作\n"
            md += "- 少数问题需要解决\n"
            md += "- 建议优化后部署\n"
        elif overall_status == 'fair':
            md += "⚠️ **MarketPrism真实API集成测试结果一般**\n\n"
            md += "- 部分功能存在问题\n"
            md += "- 需要解决关键问题\n"
            md += "- 建议完善后再部署\n"
        else:
            md += "❌ **MarketPrism真实API集成测试需要改进**\n\n"
            md += "- 多个功能存在问题\n"
            md += "- 需要全面优化\n"
            md += "- 暂不建议部署\n"
        
        md += f"\n---\n*报告生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}*\n"
        md += "*测试环境: MarketPrism CI/CD Pipeline*\n"
        
        return md
    
    def save_reports(self, test_results: Dict[str, Any], analysis: Dict[str, Any]):
        """保存报告文件"""
        # 保存JSON报告
        json_report = {
            'timestamp': time.time(),
            'test_results': test_results,
            'analysis': analysis
        }
        
        json_file = self.reports_dir / "live_api_test_complete_report.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(json_report, f, indent=2, ensure_ascii=False)
        
        # 保存Markdown报告
        md_content = self.generate_markdown_report(test_results, analysis)
        md_file = self.reports_dir / "live_api_test_complete_report.md"
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        logger.info(f"报告已保存:")
        logger.info(f"  JSON: {json_file}")
        logger.info(f"  Markdown: {md_file}")
        
        return json_file, md_file
    
    def run_complete_analysis(self) -> Dict[str, Any]:
        """运行完整分析"""
        logger.info("🚀 开始MarketPrism真实API测试完整分析...")
        
        # 运行测试
        test_results = self.run_comprehensive_api_test()
        
        # 分析结果
        analysis = self.analyze_test_results(test_results)
        
        # 保存报告
        json_file, md_file = self.save_reports(test_results, analysis)
        
        # 打印摘要
        logger.info("\n" + "="*60)
        logger.info("📊 API测试分析完成")
        logger.info("="*60)
        logger.info(f"整体状态: {analysis['overall_status'].upper()}")
        logger.info(f"最佳环境: {analysis['best_environment']}")
        logger.info(f"交易所可靠性: {analysis['exchange_reliability']}")
        logger.info(f"主要建议数量: {len(analysis['recommendations'])}")
        logger.info("="*60)
        
        return {
            'test_results': test_results,
            'analysis': analysis,
            'reports': {
                'json': str(json_file),
                'markdown': str(md_file)
            }
        }

def main():
    """主函数"""
    generator = APITestReportGenerator()
    result = generator.run_complete_analysis()
    
    # 打印关键建议
    recommendations = result['analysis']['recommendations']
    if recommendations:
        logger.info("\n🎯 关键建议:")
        for i, rec in enumerate(recommendations[:5], 1):  # 显示前5个建议
            logger.info(f"  {i}. {rec}")
    
    return result

if __name__ == "__main__":
    main()
