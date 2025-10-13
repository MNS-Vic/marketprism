#!/usr/bin/env python3
"""
MarketPrism Trades Manager性能和稳定性测试脚本
长时间运行测试，监控内存使用、CPU使用率、连接稳定性等
"""

import asyncio
import sys
import json
import time
import psutil
import os
import gc
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any
import yaml

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.append(str(Path(__file__).parent))

from main import UnifiedDataCollector
import structlog

# 配置日志
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.metrics_history = []
        self.start_time = None
        self.baseline_memory = None
        
    def start_monitoring(self):
        """开始监控"""
        self.start_time = time.time()
        self.baseline_memory = self.process.memory_info().rss
        
    def collect_metrics(self) -> Dict[str, Any]:
        """收集当前性能指标"""
        try:
            memory_info = self.process.memory_info()
            cpu_percent = self.process.cpu_percent()
            
            # 系统内存信息
            system_memory = psutil.virtual_memory()
            
            metrics = {
                'timestamp': time.time(),
                'elapsed_time': time.time() - self.start_time if self.start_time else 0,
                'memory': {
                    'rss': memory_info.rss / 1024 / 1024,  # MB
                    'vms': memory_info.vms / 1024 / 1024,  # MB
                    'percent': memory_info.rss / system_memory.total * 100,
                    'growth': (memory_info.rss - self.baseline_memory) / 1024 / 1024 if self.baseline_memory else 0
                },
                'cpu': {
                    'percent': cpu_percent,
                    'system_percent': psutil.cpu_percent()
                },
                'system': {
                    'memory_available': system_memory.available / 1024 / 1024 / 1024,  # GB
                    'memory_percent': system_memory.percent
                }
            }
            
            self.metrics_history.append(metrics)
            return metrics
            
        except Exception as e:
            logger.error("收集性能指标失败", error=str(e))
            return None
    
    def get_summary(self) -> Dict[str, Any]:
        """获取性能摘要"""
        if not self.metrics_history:
            return {'error': '没有性能数据'}
        
        memory_values = [m['memory']['rss'] for m in self.metrics_history]
        cpu_values = [m['cpu']['percent'] for m in self.metrics_history]
        memory_growth = [m['memory']['growth'] for m in self.metrics_history]
        
        return {
            'duration': self.metrics_history[-1]['elapsed_time'],
            'memory': {
                'initial': memory_values[0],
                'final': memory_values[-1],
                'peak': max(memory_values),
                'average': sum(memory_values) / len(memory_values),
                'growth': memory_growth[-1],
                'max_growth': max(memory_growth)
            },
            'cpu': {
                'average': sum(cpu_values) / len(cpu_values),
                'peak': max(cpu_values),
                'samples': len(cpu_values)
            },
            'stability': {
                'memory_stable': max(memory_growth) < 100,  # 内存增长小于100MB
                'cpu_reasonable': sum(cpu_values) / len(cpu_values) < 50  # 平均CPU使用率小于50%
            }
        }


class StabilityTester:
    """稳定性测试器"""
    
    def __init__(self):
        self.collector = None
        self.monitor = PerformanceMonitor()
        self.test_duration = 600  # 10分钟测试
        self.running = False
        self.connection_events = []
        self.error_events = []
        
    async def setup_collector(self):
        """设置数据收集器"""
        print("🔧 设置统一数据收集器...")
        self.collector = UnifiedDataCollector()
        
        # 加载配置
        success = await self.collector._load_configuration()
        if not success:
            raise Exception("配置加载失败")
        
        # 初始化组件
        success = await self.collector._initialize_components()
        if not success:
            raise Exception("组件初始化失败")
        
        print("✅ 数据收集器设置完成")
    
    async def start_data_collection(self):
        """启动数据收集"""
        print("🚀 启动数据收集...")
        
        # 启动数据收集
        success = await self.collector._start_data_collection()
        if not success:
            raise Exception("数据收集启动失败")
        
        print("✅ 数据收集已启动")
    
    def check_trades_manager_health(self) -> Dict[str, Any]:
        """检查Trades Manager健康状态"""
        if not self.collector or not self.collector.trades_manager:
            return {'healthy': False, 'error': 'Trades Manager不存在'}
        
        try:
            stats = self.collector.trades_manager.get_stats()
            
            # 检查WebSocket连接状态
            websocket_status = stats.get('websocket_status', {})
            connected_count = sum(1 for status in websocket_status.values() 
                                if isinstance(status, dict) and status.get('connected', False))
            
            # 检查数据接收
            total_received = stats.get('total_trades_received', 0)
            
            health = {
                'healthy': True,
                'connected_websockets': connected_count,
                'total_websockets': len(websocket_status),
                'data_received': total_received,
                'is_running': stats.get('is_running', False),
                'errors': stats.get('errors', 0)
            }
            
            # 健康检查标准
            if connected_count < len(websocket_status) * 0.5:  # 至少50%连接
                health['healthy'] = False
                health['issue'] = 'WebSocket连接不足'
            
            return health
            
        except Exception as e:
            return {'healthy': False, 'error': str(e)}
    
    async def run_stability_test(self):
        """运行稳定性测试"""
        print(f"🧪 开始稳定性测试 ({self.test_duration}秒)...")
        self.running = True
        self.monitor.start_monitoring()
        
        test_start = time.time()
        last_health_check = 0
        last_gc = 0
        
        while self.running and (time.time() - test_start) < self.test_duration:
            current_time = time.time()
            elapsed = current_time - test_start
            
            # 每30秒收集一次性能指标
            if current_time - last_health_check >= 30:
                metrics = self.monitor.collect_metrics()
                health = self.check_trades_manager_health()
                
                if metrics and health:
                    print(f"📊 {elapsed:.0f}s - "
                          f"内存: {metrics['memory']['rss']:.1f}MB "
                          f"(+{metrics['memory']['growth']:.1f}MB), "
                          f"CPU: {metrics['cpu']['percent']:.1f}%, "
                          f"连接: {health['connected_websockets']}/{health['total_websockets']}, "
                          f"数据: {health['data_received']}")
                    
                    if not health['healthy']:
                        self.error_events.append({
                            'timestamp': current_time,
                            'type': 'health_check_failed',
                            'details': health
                        })
                        print(f"⚠️ 健康检查失败: {health.get('issue', health.get('error', '未知错误'))}")
                
                last_health_check = current_time
            
            # 每5分钟强制垃圾回收
            if current_time - last_gc >= 300:
                collected = gc.collect()
                print(f"🗑️ 垃圾回收: 清理了 {collected} 个对象")
                last_gc = current_time
            
            await asyncio.sleep(10)  # 每10秒检查一次
        
        print("✅ 稳定性测试完成")
    
    def analyze_stability(self) -> Dict[str, Any]:
        """分析稳定性结果"""
        performance_summary = self.monitor.get_summary()
        
        # 连接稳定性分析
        connection_issues = len([e for e in self.error_events if 'connection' in e.get('type', '')])
        health_issues = len([e for e in self.error_events if 'health' in e.get('type', '')])
        
        stability_score = 100
        issues = []
        
        # 内存稳定性检查
        if not performance_summary.get('stability', {}).get('memory_stable', True):
            stability_score -= 30
            issues.append("内存增长过多")
        
        # CPU使用率检查
        if not performance_summary.get('stability', {}).get('cpu_reasonable', True):
            stability_score -= 20
            issues.append("CPU使用率过高")
        
        # 连接稳定性检查
        if connection_issues > 0:
            stability_score -= 25
            issues.append(f"连接问题: {connection_issues}次")
        
        # 健康检查失败
        if health_issues > 0:
            stability_score -= 25
            issues.append(f"健康检查失败: {health_issues}次")
        
        return {
            'stability_score': max(0, stability_score),
            'performance': performance_summary,
            'issues': issues,
            'error_events': self.error_events,
            'recommendations': self._get_recommendations(performance_summary, issues)
        }
    
    def _get_recommendations(self, performance: Dict[str, Any], issues: List[str]) -> List[str]:
        """获取优化建议"""
        recommendations = []
        
        if "内存增长过多" in issues:
            recommendations.append("检查是否存在内存泄漏，考虑增加垃圾回收频率")
        
        if "CPU使用率过高" in issues:
            recommendations.append("优化数据处理逻辑，考虑异步处理或减少计算密集型操作")
        
        if any("连接" in issue for issue in issues):
            recommendations.append("检查网络连接稳定性，增强重连机制")
        
        if any("健康检查" in issue for issue in issues):
            recommendations.append("检查WebSocket管理器状态，确保错误处理机制正常")
        
        # 基于性能数据的建议
        if performance.get('memory', {}).get('peak', 0) > 500:  # 超过500MB
            recommendations.append("内存使用量较高，考虑优化数据结构或增加内存限制")
        
        return recommendations
    
    async def cleanup(self):
        """清理资源"""
        print("🧹 清理资源...")
        self.running = False
        
        if self.collector:
            try:
                await self.collector.stop()
            except Exception as e:
                print(f"⚠️ 停止数据收集器失败: {e}")
        
        print("✅ 资源清理完成")


async def run_performance_test():
    """运行性能测试"""
    print("🚀 MarketPrism Trades Manager性能和稳定性测试")
    print("="*80)
    
    tester = StabilityTester()
    
    try:
        # 设置和启动
        await tester.setup_collector()
        await tester.start_data_collection()
        
        # 等待系统稳定
        print("⏱️ 等待系统稳定 (30秒)...")
        await asyncio.sleep(30)
        
        # 运行稳定性测试
        await tester.run_stability_test()
        
        # 分析结果
        print("\n📊 分析稳定性结果...")
        results = tester.analyze_stability()
        
        # 打印结果
        print("="*60)
        print("📈 性能和稳定性测试结果:")
        print(f"🎯 稳定性评分: {results['stability_score']}/100")
        
        performance = results['performance']
        if 'error' not in performance:
            print(f"⏱️ 测试时长: {performance['duration']:.0f}秒")
            print(f"💾 内存使用:")
            print(f"  初始: {performance['memory']['initial']:.1f}MB")
            print(f"  最终: {performance['memory']['final']:.1f}MB")
            print(f"  峰值: {performance['memory']['peak']:.1f}MB")
            print(f"  增长: {performance['memory']['growth']:.1f}MB")
            print(f"🖥️ CPU使用:")
            print(f"  平均: {performance['cpu']['average']:.1f}%")
            print(f"  峰值: {performance['cpu']['peak']:.1f}%")
        
        if results['issues']:
            print(f"\n⚠️ 发现的问题:")
            for issue in results['issues']:
                print(f"  ❌ {issue}")
        
        if results['recommendations']:
            print(f"\n💡 优化建议:")
            for rec in results['recommendations']:
                print(f"  🔧 {rec}")
        
        # 判断测试结果
        success = results['stability_score'] >= 80
        
        print(f"\n🎯 最终结果:")
        if success:
            print("🎉 性能和稳定性测试通过！")
            print("✅ 系统运行稳定")
            print("✅ 资源使用合理")
        else:
            print("⚠️ 性能和稳定性测试需要改进")
            print("建议根据上述建议进行优化")
        
        return success
        
    except Exception as e:
        print(f"❌ 性能测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        await tester.cleanup()


async def main():
    """主函数"""
    try:
        success = await run_performance_test()
        return success
    except KeyboardInterrupt:
        print("\n⚠️ 测试被用户中断")
        return False
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
