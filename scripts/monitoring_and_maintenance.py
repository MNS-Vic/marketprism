#!/usr/bin/env python3
"""
MarketPrism监控和维护自动化脚本
提供持续的系统监控、自动维护和性能优化

功能：
1. 实时系统监控和健康检查
2. 自动化日常维护任务
3. 性能分析和优化建议
4. 告警状态监控和管理
5. 自动备份和清理
"""

import asyncio
import json
import logging
import os
import sys
import time
import schedule
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
import requests
import psutil

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MarketPrismMonitor:
    """MarketPrism监控器"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.monitoring_data = {
            'start_time': time.time(),
            'checks': [],
            'alerts': [],
            'performance_metrics': [],
            'maintenance_tasks': []
        }
        
    def check_system_health(self) -> Dict[str, Any]:
        """检查系统健康状态"""
        health_status = {
            'timestamp': time.time(),
            'overall_status': 'healthy',
            'services': {},
            'resources': {},
            'apis': {}
        }
        
        # 检查Docker服务
        try:
            import subprocess
            result = subprocess.run(['docker-compose', 'ps'], 
                                  capture_output=True, text=True, cwd=self.project_root)
            if result.returncode == 0:
                health_status['services']['docker'] = 'running'
            else:
                health_status['services']['docker'] = 'error'
                health_status['overall_status'] = 'degraded'
        except Exception as e:
            health_status['services']['docker'] = f'error: {e}'
            health_status['overall_status'] = 'degraded'
        
        # 检查系统资源
        try:
            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)
            health_status['resources']['cpu'] = {
                'usage_percent': cpu_percent,
                'status': 'normal' if cpu_percent < 80 else 'high'
            }
            
            # 内存使用率
            memory = psutil.virtual_memory()
            health_status['resources']['memory'] = {
                'usage_percent': memory.percent,
                'available_gb': memory.available / (1024**3),
                'status': 'normal' if memory.percent < 80 else 'high'
            }
            
            # 磁盘使用率
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            health_status['resources']['disk'] = {
                'usage_percent': disk_percent,
                'free_gb': disk.free / (1024**3),
                'status': 'normal' if disk_percent < 80 else 'high'
            }
            
            # 检查资源状态
            if (cpu_percent > 80 or memory.percent > 80 or disk_percent > 80):
                health_status['overall_status'] = 'warning'
                
        except Exception as e:
            health_status['resources']['error'] = str(e)
            health_status['overall_status'] = 'degraded'
        
        # 检查API端点
        api_endpoints = [
            ('health', 'http://localhost:8080/health'),
            ('metrics', 'http://localhost:9090/metrics'),
            ('binance_api', 'http://localhost:8080/api/v1/exchanges/binance/ping')
        ]
        
        for name, url in api_endpoints:
            try:
                response = requests.get(url, timeout=10)
                health_status['apis'][name] = {
                    'status_code': response.status_code,
                    'response_time': response.elapsed.total_seconds(),
                    'status': 'ok' if response.status_code == 200 else 'error'
                }
                
                if response.status_code != 200:
                    health_status['overall_status'] = 'degraded'
                    
            except Exception as e:
                health_status['apis'][name] = {
                    'error': str(e),
                    'status': 'error'
                }
                health_status['overall_status'] = 'degraded'
        
        return health_status
    
    def check_alert_system_status(self) -> Dict[str, Any]:
        """检查告警系统状态"""
        try:
            from config.alerting.marketprism_alert_rules import setup_marketprism_alerting
            
            alerting_system = setup_marketprism_alerting()
            
            status = {
                'timestamp': time.time(),
                'total_rules': len(alerting_system.rules),
                'active_alerts': len(alerting_system.active_alerts),
                'rule_distribution': {},
                'status': 'operational'
            }
            
            # 分析规则分布
            for rule in alerting_system.rules.values():
                priority = rule.priority.value
                status['rule_distribution'][priority] = status['rule_distribution'].get(priority, 0) + 1
            
            # 检查活跃告警
            if alerting_system.active_alerts:
                status['active_alert_details'] = []
                for alert in alerting_system.active_alerts.values():
                    status['active_alert_details'].append({
                        'rule_name': alert.rule_name,
                        'priority': alert.priority.value,
                        'summary': alert.summary,
                        'duration': (datetime.now() - alert.first_triggered).total_seconds()
                    })
            
            return status
            
        except Exception as e:
            return {
                'timestamp': time.time(),
                'error': str(e),
                'status': 'error'
            }
    
    def collect_performance_metrics(self) -> Dict[str, Any]:
        """收集性能指标"""
        metrics = {
            'timestamp': time.time(),
            'api_performance': {},
            'system_performance': {},
            'database_performance': {}
        }
        
        # API性能测试
        api_tests = [
            ('binance_ping', 'http://localhost:8080/api/v1/exchanges/binance/ping'),
            ('health_check', 'http://localhost:8080/health')
        ]
        
        for test_name, url in api_tests:
            try:
                start_time = time.time()
                response = requests.get(url, timeout=15)
                response_time = time.time() - start_time
                
                metrics['api_performance'][test_name] = {
                    'response_time': response_time,
                    'status_code': response.status_code,
                    'success': response.status_code == 200
                }
            except Exception as e:
                metrics['api_performance'][test_name] = {
                    'error': str(e),
                    'success': False
                }
        
        # 系统性能指标
        try:
            metrics['system_performance'] = {
                'cpu_percent': psutil.cpu_percent(),
                'memory_percent': psutil.virtual_memory().percent,
                'disk_io': psutil.disk_io_counters()._asdict() if psutil.disk_io_counters() else {},
                'network_io': psutil.net_io_counters()._asdict() if psutil.net_io_counters() else {}
            }
        except Exception as e:
            metrics['system_performance']['error'] = str(e)
        
        return metrics
    
    def run_maintenance_tasks(self) -> Dict[str, Any]:
        """运行维护任务"""
        maintenance_results = {
            'timestamp': time.time(),
            'tasks': {}
        }
        
        # 清理日志文件
        try:
            log_dir = Path('/var/log/marketprism')
            if log_dir.exists():
                # 删除7天前的日志
                cutoff_time = time.time() - (7 * 24 * 3600)
                cleaned_files = 0
                
                for log_file in log_dir.glob('*.log.*'):
                    if log_file.stat().st_mtime < cutoff_time:
                        log_file.unlink()
                        cleaned_files += 1
                
                maintenance_results['tasks']['log_cleanup'] = {
                    'status': 'completed',
                    'cleaned_files': cleaned_files
                }
            else:
                maintenance_results['tasks']['log_cleanup'] = {
                    'status': 'skipped',
                    'reason': 'log directory not found'
                }
        except Exception as e:
            maintenance_results['tasks']['log_cleanup'] = {
                'status': 'error',
                'error': str(e)
            }
        
        # Docker系统清理
        try:
            import subprocess
            
            # 清理未使用的Docker镜像
            result = subprocess.run(['docker', 'system', 'prune', '-f'], 
                                  capture_output=True, text=True)
            
            maintenance_results['tasks']['docker_cleanup'] = {
                'status': 'completed' if result.returncode == 0 else 'error',
                'output': result.stdout + result.stderr
            }
        except Exception as e:
            maintenance_results['tasks']['docker_cleanup'] = {
                'status': 'error',
                'error': str(e)
            }
        
        # 数据库维护
        try:
            # 这里可以添加数据库清理、索引优化等任务
            maintenance_results['tasks']['database_maintenance'] = {
                'status': 'skipped',
                'reason': 'no maintenance tasks configured'
            }
        except Exception as e:
            maintenance_results['tasks']['database_maintenance'] = {
                'status': 'error',
                'error': str(e)
            }
        
        return maintenance_results
    
    def generate_monitoring_report(self) -> str:
        """生成监控报告"""
        report_data = {
            'report_time': time.time(),
            'monitoring_period': time.time() - self.monitoring_data['start_time'],
            'system_health': self.check_system_health(),
            'alert_system': self.check_alert_system_status(),
            'performance_metrics': self.collect_performance_metrics(),
            'recent_checks': self.monitoring_data['checks'][-10:],  # 最近10次检查
            'recommendations': []
        }
        
        # 生成建议
        health = report_data['system_health']
        
        # 资源使用建议
        if health['resources'].get('cpu', {}).get('usage_percent', 0) > 80:
            report_data['recommendations'].append("CPU使用率过高，建议检查高CPU进程或增加计算资源")
        
        if health['resources'].get('memory', {}).get('usage_percent', 0) > 80:
            report_data['recommendations'].append("内存使用率过高，建议检查内存泄漏或增加内存")
        
        if health['resources'].get('disk', {}).get('usage_percent', 0) > 80:
            report_data['recommendations'].append("磁盘空间不足，建议清理日志文件或扩展存储")
        
        # API性能建议
        for api_name, api_data in health['apis'].items():
            if api_data.get('response_time', 0) > 5:
                report_data['recommendations'].append(f"{api_name} API响应时间过长，建议检查网络或服务性能")
        
        # 告警系统建议
        alert_status = report_data['alert_system']
        if alert_status.get('active_alerts', 0) > 5:
            report_data['recommendations'].append("活跃告警数量较多，建议检查系统状态")
        
        # 保存报告
        report_file = self.project_root / 'tests' / 'reports' / 'monitoring_report.json'
        report_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False, default=str)
        
        # 生成Markdown报告
        md_report = self._generate_markdown_monitoring_report(report_data)
        md_file = report_file.with_suffix('.md')
        
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(md_report)
        
        logger.info(f"监控报告已生成: {report_file}")
        return str(md_file)
    
    def _generate_markdown_monitoring_report(self, report_data: Dict[str, Any]) -> str:
        """生成Markdown格式监控报告"""
        md = "# 📊 MarketPrism系统监控报告\n\n"
        
        # 报告概览
        md += "## 📋 监控概览\n\n"
        md += f"**报告时间**: {datetime.fromtimestamp(report_data['report_time']).strftime('%Y-%m-%d %H:%M:%S')}\n"
        md += f"**监控时长**: {report_data['monitoring_period']/3600:.1f} 小时\n"
        
        # 系统健康状态
        health = report_data['system_health']
        status_icon = {'healthy': '🟢', 'warning': '🟡', 'degraded': '🔴'}.get(health['overall_status'], '⚪')
        md += f"**系统状态**: {status_icon} {health['overall_status']}\n\n"
        
        # 资源使用情况
        md += "## 💻 系统资源\n\n"
        if 'resources' in health:
            resources = health['resources']
            md += "| 资源 | 使用率 | 状态 | 详情 |\n"
            md += "|------|--------|------|------|\n"
            
            if 'cpu' in resources:
                cpu = resources['cpu']
                status_icon = '🟢' if cpu['status'] == 'normal' else '🔴'
                md += f"| CPU | {cpu['usage_percent']:.1f}% | {status_icon} | {cpu['status']} |\n"
            
            if 'memory' in resources:
                memory = resources['memory']
                status_icon = '🟢' if memory['status'] == 'normal' else '🔴'
                md += f"| 内存 | {memory['usage_percent']:.1f}% | {status_icon} | 可用: {memory['available_gb']:.1f}GB |\n"
            
            if 'disk' in resources:
                disk = resources['disk']
                status_icon = '🟢' if disk['status'] == 'normal' else '🔴'
                md += f"| 磁盘 | {disk['usage_percent']:.1f}% | {status_icon} | 可用: {disk['free_gb']:.1f}GB |\n"
        
        md += "\n"
        
        # API状态
        md += "## 🌐 API服务状态\n\n"
        if 'apis' in health:
            md += "| API | 状态码 | 响应时间 | 状态 |\n"
            md += "|-----|--------|----------|------|\n"
            
            for api_name, api_data in health['apis'].items():
                if 'status_code' in api_data:
                    status_icon = '🟢' if api_data['status'] == 'ok' else '🔴'
                    md += f"| {api_name} | {api_data['status_code']} | {api_data['response_time']:.3f}s | {status_icon} |\n"
                else:
                    md += f"| {api_name} | - | - | 🔴 错误 |\n"
        
        md += "\n"
        
        # 告警系统状态
        alert_status = report_data['alert_system']
        md += "## 🚨 告警系统状态\n\n"
        md += f"**告警规则总数**: {alert_status.get('total_rules', 0)}\n"
        md += f"**活跃告警数**: {alert_status.get('active_alerts', 0)}\n"
        
        if 'rule_distribution' in alert_status:
            md += "\n**规则分布**:\n"
            for priority, count in alert_status['rule_distribution'].items():
                md += f"- {priority}: {count}个\n"
        
        if alert_status.get('active_alert_details'):
            md += "\n**活跃告警**:\n"
            for alert in alert_status['active_alert_details']:
                duration_hours = alert['duration'] / 3600
                md += f"- **{alert['rule_name']}** ({alert['priority']}): {alert['summary']} (持续 {duration_hours:.1f}h)\n"
        
        md += "\n"
        
        # 性能指标
        performance = report_data['performance_metrics']
        md += "## ⚡ 性能指标\n\n"
        
        if 'api_performance' in performance:
            md += "**API性能**:\n"
            for api_name, api_data in performance['api_performance'].items():
                if api_data.get('success'):
                    md += f"- {api_name}: {api_data['response_time']:.3f}s ✅\n"
                else:
                    md += f"- {api_name}: 失败 ❌\n"
        
        md += "\n"
        
        # 建议
        if report_data['recommendations']:
            md += "## 💡 优化建议\n\n"
            for i, rec in enumerate(report_data['recommendations'], 1):
                md += f"{i}. {rec}\n"
        else:
            md += "## 💡 优化建议\n\n"
            md += "✅ 系统运行良好，暂无优化建议\n"
        
        md += "\n---\n"
        md += f"*报告生成时间: {datetime.fromtimestamp(report_data['report_time']).strftime('%Y-%m-%d %H:%M:%S')}*\n"
        
        return md
    
    def run_continuous_monitoring(self, interval: int = 300):
        """运行持续监控"""
        logger.info(f"🔄 开始持续监控，检查间隔: {interval}秒")
        
        def monitoring_job():
            try:
                # 执行健康检查
                health_status = self.check_system_health()
                self.monitoring_data['checks'].append(health_status)
                
                # 记录性能指标
                performance_metrics = self.collect_performance_metrics()
                self.monitoring_data['performance_metrics'].append(performance_metrics)
                
                # 检查是否需要告警
                if health_status['overall_status'] in ['warning', 'degraded']:
                    logger.warning(f"⚠️ 系统状态异常: {health_status['overall_status']}")
                
                # 保持最近100次检查记录
                if len(self.monitoring_data['checks']) > 100:
                    self.monitoring_data['checks'] = self.monitoring_data['checks'][-100:]
                
                if len(self.monitoring_data['performance_metrics']) > 100:
                    self.monitoring_data['performance_metrics'] = self.monitoring_data['performance_metrics'][-100:]
                
                logger.info(f"✅ 监控检查完成 - 状态: {health_status['overall_status']}")
                
            except Exception as e:
                logger.error(f"❌ 监控检查失败: {e}")
        
        # 设置定时任务
        schedule.every(interval).seconds.do(monitoring_job)
        
        # 每小时生成监控报告
        schedule.every().hour.do(self.generate_monitoring_report)
        
        # 每天凌晨2点运行维护任务
        schedule.every().day.at("02:00").do(self.run_maintenance_tasks)
        
        # 立即执行一次检查
        monitoring_job()
        
        # 持续运行
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # 每分钟检查一次定时任务
        except KeyboardInterrupt:
            logger.info("🛑 监控已停止")

def main():
    """主函数"""
    monitor = MarketPrismMonitor()
    
    print("📊 MarketPrism监控和维护系统")
    print("=" * 40)
    print("1. 运行单次健康检查")
    print("2. 生成监控报告")
    print("3. 运行维护任务")
    print("4. 启动持续监控")
    print("5. 退出")
    
    while True:
        choice = input("\n请选择操作 (1-5): ").strip()
        
        if choice == '1':
            print("🔍 执行健康检查...")
            health = monitor.check_system_health()
            print(f"系统状态: {health['overall_status']}")
            print(json.dumps(health, indent=2, default=str))
            
        elif choice == '2':
            print("📊 生成监控报告...")
            report_file = monitor.generate_monitoring_report()
            print(f"报告已生成: {report_file}")
            
        elif choice == '3':
            print("🔧 运行维护任务...")
            maintenance = monitor.run_maintenance_tasks()
            print(json.dumps(maintenance, indent=2, default=str))
            
        elif choice == '4':
            interval = input("请输入监控间隔（秒，默认300）: ").strip()
            interval = int(interval) if interval.isdigit() else 300
            monitor.run_continuous_monitoring(interval)
            break
            
        elif choice == '5':
            print("👋 再见！")
            break
            
        else:
            print("❌ 无效选择，请重试")

if __name__ == "__main__":
    main()
