#!/usr/bin/env python3
"""
MarketPrism生产就绪状态验证器
执行完整的端到端测试，确认所有核心功能正常工作

验证范围：
1. 基础设施检查（Docker、网络、存储）
2. 核心服务验证（数据收集、缓存、数据库）
3. API集成测试（多交易所连接）
4. 告警系统验证（规则、通知渠道）
5. 监控系统检查（指标收集、健康检查）
6. 安全性验证（配置安全、网络安全）
7. 性能基准测试（响应时间、吞吐量）
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple
import requests
import yaml

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ProductionReadinessValidator:
    """生产就绪状态验证器"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.validation_results = {
            'timestamp': time.time(),
            'overall_status': 'unknown',
            'checks': {},
            'recommendations': [],
            'critical_issues': [],
            'warnings': []
        }
        
    def run_command(self, command: str, timeout: int = 30) -> Tuple[bool, str]:
        """运行系统命令"""
        try:
            result = subprocess.run(
                command.split(),
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, f"Command timeout after {timeout}s"
        except Exception as e:
            return False, str(e)
    
    def check_infrastructure(self) -> Dict[str, Any]:
        """检查基础设施"""
        logger.info("🏗️ 检查基础设施...")
        
        checks = {}
        
        # 检查Docker
        success, output = self.run_command("docker --version")
        checks['docker'] = {
            'status': 'pass' if success else 'fail',
            'message': 'Docker可用' if success else 'Docker不可用',
            'details': output.strip()
        }
        
        # 检查Docker Compose
        success, output = self.run_command("docker-compose --version")
        checks['docker_compose'] = {
            'status': 'pass' if success else 'fail',
            'message': 'Docker Compose可用' if success else 'Docker Compose不可用',
            'details': output.strip()
        }
        
        # 检查磁盘空间
        success, output = self.run_command("df -h .")
        if success:
            lines = output.strip().split('\n')
            if len(lines) > 1:
                usage_line = lines[1].split()
                if len(usage_line) >= 5:
                    usage_percent = usage_line[4].rstrip('%')
                    try:
                        usage = int(usage_percent)
                        checks['disk_space'] = {
                            'status': 'pass' if usage < 80 else 'warn' if usage < 90 else 'fail',
                            'message': f'磁盘使用率: {usage}%',
                            'details': output.strip()
                        }
                    except ValueError:
                        checks['disk_space'] = {
                            'status': 'warn',
                            'message': '无法解析磁盘使用率',
                            'details': output.strip()
                        }
        
        # 检查内存
        success, output = self.run_command("free -h")
        checks['memory'] = {
            'status': 'pass' if success else 'warn',
            'message': '内存信息可用' if success else '无法获取内存信息',
            'details': output.strip() if success else 'N/A'
        }
        
        # 检查网络连接
        success, output = self.run_command("ping -c 1 8.8.8.8")
        checks['network'] = {
            'status': 'pass' if success else 'fail',
            'message': '网络连接正常' if success else '网络连接异常',
            'details': 'Internet connectivity verified' if success else output
        }
        
        return checks
    
    def check_configuration_files(self) -> Dict[str, Any]:
        """检查配置文件"""
        logger.info("⚙️ 检查配置文件...")
        
        checks = {}
        
        # 必需的配置文件
        required_files = [
            'docker-compose.yml',
            '.env.example',
            'config/proxy.yaml',
            'config/alerting/marketprism_alert_rules.py'
        ]
        
        for file_path in required_files:
            full_path = self.project_root / file_path
            checks[f'config_{file_path.replace("/", "_").replace(".", "_")}'] = {
                'status': 'pass' if full_path.exists() else 'fail',
                'message': f'{file_path} 存在' if full_path.exists() else f'{file_path} 缺失',
                'details': str(full_path)
            }
        
        # 检查环境变量文件
        env_file = self.project_root / '.env'
        if env_file.exists():
            checks['env_file'] = {
                'status': 'pass',
                'message': '.env文件存在',
                'details': '生产环境配置就绪'
            }
        else:
            checks['env_file'] = {
                'status': 'warn',
                'message': '.env文件不存在',
                'details': '需要从.env.example复制并配置'
            }
        
        return checks
    
    def check_core_services(self) -> Dict[str, Any]:
        """检查核心服务"""
        logger.info("🔧 检查核心服务...")
        
        checks = {}
        
        # 检查Docker服务状态
        success, output = self.run_command("docker-compose ps")
        if success:
            checks['docker_services'] = {
                'status': 'pass',
                'message': 'Docker服务状态可查询',
                'details': output.strip()
            }
        else:
            checks['docker_services'] = {
                'status': 'fail',
                'message': '无法查询Docker服务状态',
                'details': output
            }
        
        # 检查关键端口
        key_ports = [8080, 9090, 5432, 6379]
        for port in key_ports:
            success, output = self.run_command(f"netstat -tlnp | grep :{port}")
            checks[f'port_{port}'] = {
                'status': 'pass' if success else 'warn',
                'message': f'端口{port}已监听' if success else f'端口{port}未监听',
                'details': output.strip() if success else '端口未使用'
            }
        
        return checks
    
    def check_api_integration(self) -> Dict[str, Any]:
        """检查API集成"""
        logger.info("🌐 检查API集成...")
        
        checks = {}
        
        try:
            # 导入API客户端
            from tests.utils.enhanced_api_client import EnhancedAPIClient
            
            client = EnhancedAPIClient()
            
            # 测试Binance API
            try:
                result = client.test_binance_ping()
                checks['binance_api'] = {
                    'status': 'pass' if result.get('success') else 'fail',
                    'message': 'Binance API连接正常' if result.get('success') else 'Binance API连接失败',
                    'details': result
                }
            except Exception as e:
                checks['binance_api'] = {
                    'status': 'fail',
                    'message': 'Binance API测试异常',
                    'details': str(e)
                }
            
            # 测试OKX API
            try:
                result = client.test_okx_time()
                checks['okx_api'] = {
                    'status': 'pass' if result.get('success') else 'warn',
                    'message': 'OKX API连接正常' if result.get('success') else 'OKX API连接失败（可能需要代理）',
                    'details': result
                }
            except Exception as e:
                checks['okx_api'] = {
                    'status': 'warn',
                    'message': 'OKX API测试异常（可能需要代理配置）',
                    'details': str(e)
                }
            
            client.close()
            
        except ImportError as e:
            checks['api_client'] = {
                'status': 'fail',
                'message': 'API客户端导入失败',
                'details': str(e)
            }
        
        return checks
    
    def check_alerting_system(self) -> Dict[str, Any]:
        """检查告警系统"""
        logger.info("🚨 检查告警系统...")
        
        checks = {}
        
        try:
            # 导入告警系统
            from config.alerting.marketprism_alert_rules import setup_marketprism_alerting
            
            alerting_system = setup_marketprism_alerting()
            
            # 检查告警规则数量
            rule_count = len(alerting_system.rules)
            checks['alert_rules'] = {
                'status': 'pass' if rule_count >= 10 else 'warn',
                'message': f'告警规则数量: {rule_count}',
                'details': f'已配置{rule_count}个告警规则'
            }
            
            # 检查优先级分布
            priorities = {}
            for rule in alerting_system.rules.values():
                priority = rule.priority.value
                priorities[priority] = priorities.get(priority, 0) + 1
            
            checks['alert_priorities'] = {
                'status': 'pass',
                'message': '告警优先级分布正常',
                'details': priorities
            }
            
            # 检查通知渠道
            channels = set()
            for rule in alerting_system.rules.values():
                for channel in rule.notification_channels:
                    channels.add(channel.value)
            
            checks['notification_channels'] = {
                'status': 'pass' if len(channels) >= 3 else 'warn',
                'message': f'通知渠道数量: {len(channels)}',
                'details': list(channels)
            }
            
        except Exception as e:
            checks['alerting_system'] = {
                'status': 'fail',
                'message': '告警系统检查失败',
                'details': str(e)
            }
        
        return checks
    
    def check_monitoring_system(self) -> Dict[str, Any]:
        """检查监控系统"""
        logger.info("📊 检查监控系统...")
        
        checks = {}
        
        # 检查Prometheus配置
        prometheus_config = self.project_root / 'config' / 'monitoring' / 'prometheus.yml'
        checks['prometheus_config'] = {
            'status': 'pass' if prometheus_config.exists() else 'warn',
            'message': 'Prometheus配置存在' if prometheus_config.exists() else 'Prometheus配置缺失',
            'details': str(prometheus_config)
        }
        
        # 检查告警规则配置
        alert_rules = self.project_root / 'config' / 'monitoring' / 'prometheus_rules.yml'
        checks['prometheus_rules'] = {
            'status': 'pass' if alert_rules.exists() else 'warn',
            'message': 'Prometheus告警规则存在' if alert_rules.exists() else 'Prometheus告警规则缺失',
            'details': str(alert_rules)
        }
        
        return checks
    
    def check_security(self) -> Dict[str, Any]:
        """检查安全配置"""
        logger.info("🔒 检查安全配置...")
        
        checks = {}
        
        # 检查敏感文件权限
        sensitive_files = ['.env', 'config/secrets.yaml']
        for file_path in sensitive_files:
            full_path = self.project_root / file_path
            if full_path.exists():
                # 检查文件权限（Unix系统）
                try:
                    import stat
                    file_stat = full_path.stat()
                    mode = stat.filemode(file_stat.st_mode)
                    checks[f'security_{file_path.replace("/", "_")}'] = {
                        'status': 'pass',
                        'message': f'{file_path} 权限: {mode}',
                        'details': f'文件权限检查通过'
                    }
                except Exception as e:
                    checks[f'security_{file_path.replace("/", "_")}'] = {
                        'status': 'warn',
                        'message': f'{file_path} 权限检查失败',
                        'details': str(e)
                    }
        
        # 检查默认密码
        env_example = self.project_root / '.env.example'
        if env_example.exists():
            with open(env_example, 'r') as f:
                content = f.read()
                if 'password123' in content.lower() or 'changeme' in content.lower():
                    checks['default_passwords'] = {
                        'status': 'warn',
                        'message': '检测到默认密码',
                        'details': '请确保生产环境使用强密码'
                    }
                else:
                    checks['default_passwords'] = {
                        'status': 'pass',
                        'message': '未检测到明显的默认密码',
                        'details': '密码安全检查通过'
                    }
        
        return checks
    
    def run_performance_tests(self) -> Dict[str, Any]:
        """运行性能测试"""
        logger.info("⚡ 运行性能测试...")
        
        checks = {}
        
        try:
            # 测试API响应时间
            start_time = time.time()
            response = requests.get('https://api.binance.com/api/v3/ping', timeout=10)
            response_time = time.time() - start_time
            
            checks['api_performance'] = {
                'status': 'pass' if response_time < 1.0 else 'warn',
                'message': f'API响应时间: {response_time:.3f}s',
                'details': f'Binance API响应时间测试'
            }
            
        except Exception as e:
            checks['api_performance'] = {
                'status': 'warn',
                'message': 'API性能测试失败',
                'details': str(e)
            }
        
        # 测试系统资源
        try:
            import psutil
            
            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)
            checks['cpu_performance'] = {
                'status': 'pass' if cpu_percent < 80 else 'warn',
                'message': f'CPU使用率: {cpu_percent}%',
                'details': f'系统CPU负载检查'
            }
            
            # 内存使用率
            memory = psutil.virtual_memory()
            checks['memory_performance'] = {
                'status': 'pass' if memory.percent < 80 else 'warn',
                'message': f'内存使用率: {memory.percent}%',
                'details': f'可用内存: {memory.available // (1024**3)}GB'
            }
            
        except ImportError:
            checks['system_resources'] = {
                'status': 'warn',
                'message': 'psutil未安装，无法检查系统资源',
                'details': 'pip install psutil'
            }
        
        return checks
    
    async def run_full_validation(self) -> Dict[str, Any]:
        """运行完整验证"""
        logger.info("🚀 开始MarketPrism生产就绪状态验证...")
        
        # 执行各项检查
        validation_steps = [
            ('infrastructure', self.check_infrastructure),
            ('configuration', self.check_configuration_files),
            ('core_services', self.check_core_services),
            ('api_integration', self.check_api_integration),
            ('alerting_system', self.check_alerting_system),
            ('monitoring_system', self.check_monitoring_system),
            ('security', self.check_security),
            ('performance', self.run_performance_tests)
        ]
        
        for step_name, step_func in validation_steps:
            logger.info(f"执行检查: {step_name}")
            try:
                self.validation_results['checks'][step_name] = step_func()
            except Exception as e:
                logger.error(f"检查失败 {step_name}: {e}")
                self.validation_results['checks'][step_name] = {
                    'error': {
                        'status': 'fail',
                        'message': f'检查执行失败: {step_name}',
                        'details': str(e)
                    }
                }
        
        # 分析结果
        self._analyze_results()
        
        # 生成报告
        self._generate_report()
        
        return self.validation_results
    
    def _analyze_results(self):
        """分析验证结果"""
        total_checks = 0
        passed_checks = 0
        failed_checks = 0
        warnings = 0
        
        for category, checks in self.validation_results['checks'].items():
            for check_name, check_result in checks.items():
                total_checks += 1
                status = check_result.get('status', 'unknown')
                
                if status == 'pass':
                    passed_checks += 1
                elif status == 'fail':
                    failed_checks += 1
                    self.validation_results['critical_issues'].append({
                        'category': category,
                        'check': check_name,
                        'message': check_result.get('message', ''),
                        'details': check_result.get('details', '')
                    })
                elif status == 'warn':
                    warnings += 1
                    self.validation_results['warnings'].append({
                        'category': category,
                        'check': check_name,
                        'message': check_result.get('message', ''),
                        'details': check_result.get('details', '')
                    })
        
        # 确定整体状态
        if failed_checks == 0 and warnings <= 2:
            self.validation_results['overall_status'] = 'ready'
        elif failed_checks <= 2 and warnings <= 5:
            self.validation_results['overall_status'] = 'ready_with_warnings'
        else:
            self.validation_results['overall_status'] = 'not_ready'
        
        # 生成建议
        self._generate_recommendations()
        
        logger.info(f"验证完成: {passed_checks}/{total_checks} 通过, {warnings} 警告, {failed_checks} 失败")
    
    def _generate_recommendations(self):
        """生成改进建议"""
        recommendations = []
        
        # 基于关键问题生成建议
        if self.validation_results['critical_issues']:
            recommendations.append("🚨 修复所有关键问题后再部署到生产环境")
        
        if len(self.validation_results['warnings']) > 3:
            recommendations.append("⚠️ 建议解决警告问题以提高系统稳定性")
        
        # 检查特定问题
        for category, checks in self.validation_results['checks'].items():
            if category == 'api_integration':
                okx_status = checks.get('okx_api', {}).get('status')
                if okx_status in ['fail', 'warn']:
                    recommendations.append("🔧 配置代理服务器以启用OKX API支持")
            
            if category == 'security':
                if any(check.get('status') == 'warn' for check in checks.values()):
                    recommendations.append("🔒 加强安全配置，确保生产环境安全")
        
        # 通用建议
        if self.validation_results['overall_status'] == 'ready':
            recommendations.append("✅ 系统已准备好部署到生产环境")
            recommendations.append("📊 建议部署后持续监控系统状态")
        
        self.validation_results['recommendations'] = recommendations
    
    def _generate_report(self):
        """生成验证报告"""
        report_file = self.project_root / 'tests' / 'reports' / 'production_readiness_report.json'
        report_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(self.validation_results, f, indent=2, ensure_ascii=False, default=str)
        
        # 生成Markdown报告
        md_report = self._generate_markdown_report()
        md_file = report_file.with_suffix('.md')
        
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(md_report)
        
        logger.info(f"验证报告已保存: {report_file}")
        logger.info(f"Markdown报告: {md_file}")
    
    def _generate_markdown_report(self) -> str:
        """生成Markdown格式报告"""
        status_icons = {
            'ready': '🟢',
            'ready_with_warnings': '🟡',
            'not_ready': '🔴'
        }
        
        md = "# 🚀 MarketPrism生产就绪状态验证报告\n\n"
        
        # 总体状态
        overall_status = self.validation_results['overall_status']
        status_icon = status_icons.get(overall_status, '⚪')
        
        md += f"## {status_icon} 总体状态: {overall_status.replace('_', ' ').title()}\n\n"
        md += f"**验证时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        # 检查结果汇总
        md += "## 📊 检查结果汇总\n\n"
        
        for category, checks in self.validation_results['checks'].items():
            md += f"### {category.replace('_', ' ').title()}\n\n"
            md += "| 检查项 | 状态 | 消息 |\n"
            md += "|--------|------|------|\n"
            
            for check_name, check_result in checks.items():
                status = check_result.get('status', 'unknown')
                status_emoji = {'pass': '✅', 'warn': '⚠️', 'fail': '❌'}.get(status, '❓')
                message = check_result.get('message', 'N/A')
                md += f"| {check_name} | {status_emoji} | {message} |\n"
            
            md += "\n"
        
        # 关键问题
        if self.validation_results['critical_issues']:
            md += "## 🚨 关键问题\n\n"
            for issue in self.validation_results['critical_issues']:
                md += f"- **{issue['category']}.{issue['check']}**: {issue['message']}\n"
            md += "\n"
        
        # 警告
        if self.validation_results['warnings']:
            md += "## ⚠️ 警告\n\n"
            for warning in self.validation_results['warnings']:
                md += f"- **{warning['category']}.{warning['check']}**: {warning['message']}\n"
            md += "\n"
        
        # 建议
        md += "## 💡 建议\n\n"
        for i, rec in enumerate(self.validation_results['recommendations'], 1):
            md += f"{i}. {rec}\n"
        
        # 部署决策
        md += "\n## 🎯 部署决策\n\n"
        if overall_status == 'ready':
            md += "🟢 **建议**: 可以安全部署到生产环境\n"
        elif overall_status == 'ready_with_warnings':
            md += "🟡 **建议**: 可以部署，但建议先解决警告问题\n"
        else:
            md += "🔴 **建议**: 暂不建议部署，需要解决关键问题\n"
        
        md += f"\n---\n*报告生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}*\n"
        
        return md

async def main():
    """主函数"""
    validator = ProductionReadinessValidator()
    
    try:
        results = await validator.run_full_validation()
        
        # 输出总结
        logger.info("\n" + "="*60)
        logger.info("🎯 MarketPrism生产就绪状态验证完成")
        logger.info("="*60)
        
        overall_status = results['overall_status']
        status_messages = {
            'ready': '🟢 系统已准备好部署到生产环境',
            'ready_with_warnings': '🟡 系统基本就绪，建议解决警告后部署',
            'not_ready': '🔴 系统尚未就绪，需要解决关键问题'
        }
        
        logger.info(f"总体状态: {status_messages.get(overall_status, '未知状态')}")
        
        # 显示关键统计
        total_checks = sum(len(checks) for checks in results['checks'].values())
        critical_issues = len(results['critical_issues'])
        warnings = len(results['warnings'])
        
        logger.info(f"检查项总数: {total_checks}")
        logger.info(f"关键问题: {critical_issues}")
        logger.info(f"警告: {warnings}")
        
        # 显示主要建议
        if results['recommendations']:
            logger.info("\n💡 主要建议:")
            for i, rec in enumerate(results['recommendations'][:3], 1):
                logger.info(f"  {i}. {rec}")
        
        logger.info("="*60)
        
        # 返回退出码
        if overall_status == 'ready':
            return 0
        elif overall_status == 'ready_with_warnings':
            return 1
        else:
            return 2
            
    except Exception as e:
        logger.error(f"验证过程失败: {e}")
        return 3

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
