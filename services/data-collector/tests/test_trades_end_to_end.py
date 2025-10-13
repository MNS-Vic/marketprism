#!/usr/bin/env python3
"""
MarketPrism Trades Manager端到端测试脚本
同时运行数据收集器和NATS订阅验证
"""

import asyncio
import sys
import json
import time
import signal
import psutil
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any
import yaml

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.append(str(Path(__file__).parent))

import nats
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


class EndToEndTestRunner:
    """端到端测试运行器"""

    def __init__(self):
        self.collector = None
        self.nats_client = None
        self.received_data = []
        self.start_time = None
        self.test_duration = 120  # 2分钟测试
        self.running = False
        self.performance_data = []
        self.process = psutil.Process(os.getpid())
        
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
    
    async def setup_nats_subscriber(self):
        """设置NATS订阅器"""
        print("📡 设置NATS订阅器...")
        
        # 加载配置
        config_path = "../../config/collector/unified_data_collection.yaml"
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        nats_config = config.get('nats', {})
        servers = nats_config.get('servers', ['nats://localhost:4222'])
        
        # 连接NATS
        self.nats_client = await nats.connect(servers=servers)
        
        # 订阅Trades数据
        async def message_handler(msg):
            try:
                subject = msg.subject
                data = json.loads(msg.data.decode())
                
                self.received_data.append({
                    'subject': subject,
                    'data': data,
                    'received_at': time.time(),
                    'latency': time.time() - self.start_time if self.start_time else 0
                })
                
                # 每50条数据打印一次进度
                if len(self.received_data) % 50 == 0:
                    print(f"📊 NATS已接收 {len(self.received_data)} 条Trades数据")
                    
            except Exception as e:
                logger.error("处理NATS消息失败", error=str(e))
        
        await self.nats_client.subscribe("trade.>", cb=message_handler)
        print("✅ NATS订阅器设置完成")
    
    async def start_data_collection(self):
        """启动数据收集"""
        print("🚀 启动数据收集...")
        self.start_time = time.time()
        
        # 启动数据收集
        success = await self.collector._start_data_collection()
        if not success:
            raise Exception("数据收集启动失败")
        
        print("✅ 数据收集已启动")

    def collect_performance_metrics(self):
        """收集性能指标"""
        try:
            memory_info = self.process.memory_info()
            cpu_percent = self.process.cpu_percent()

            metrics = {
                'timestamp': time.time(),
                'memory_rss': memory_info.rss / 1024 / 1024,  # MB
                'memory_vms': memory_info.vms / 1024 / 1024,  # MB
                'cpu_percent': cpu_percent,
                'data_count': len(self.received_data)
            }

            self.performance_data.append(metrics)
            return metrics
        except Exception as e:
            logger.error("收集性能指标失败", error=str(e))
            return None

    async def run_test(self):
        """运行端到端测试"""
        print("🧪 开始端到端测试...")
        self.running = True
        
        # 等待系统稳定
        print("⏱️ 等待系统稳定 (10秒)...")
        await asyncio.sleep(10)
        
        # 运行测试
        print(f"🔄 运行测试 ({self.test_duration}秒)...")
        test_start = time.time()

        while self.running and (time.time() - test_start) < self.test_duration:
            await asyncio.sleep(5)

            # 收集性能指标
            metrics = self.collect_performance_metrics()

            # 打印中间统计
            elapsed = time.time() - test_start
            if len(self.received_data) > 0:
                rate = len(self.received_data) / elapsed
                if metrics:
                    print(f"📈 进度: {elapsed:.0f}s, 数据: {len(self.received_data)}条, "
                          f"速率: {rate:.1f}条/秒, 内存: {metrics['memory_rss']:.1f}MB, "
                          f"CPU: {metrics['cpu_percent']:.1f}%")
                else:
                    print(f"📈 进度: {elapsed:.0f}s, 数据: {len(self.received_data)}条, 速率: {rate:.1f}条/秒")
            else:
                print(f"⏳ 进度: {elapsed:.0f}s, 等待数据...")

        print("✅ 测试运行完成")
    
    def analyze_results(self) -> Dict[str, Any]:
        """分析测试结果"""
        if not self.received_data:
            return {'success': False, 'error': '没有接收到数据'}
        
        # 基本统计
        total_count = len(self.received_data)
        test_duration = self.test_duration
        data_rate = total_count / test_duration
        
        # 按交易所分组
        exchanges = {}
        subjects = set()
        
        for item in self.received_data:
            subject = item['subject']
            subjects.add(subject)
            
            # 解析主题
            parts = subject.split('.')
            if len(parts) >= 2:
                exchange = parts[1]
                if exchange not in exchanges:
                    exchanges[exchange] = {'count': 0, 'subjects': set()}
                exchanges[exchange]['count'] += 1
                exchanges[exchange]['subjects'].add(subject)
        
        # 数据完整性检查
        data_integrity = self._check_data_integrity()
        
        # 延迟分析
        latencies = [item['latency'] for item in self.received_data if item['latency'] > 0]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        max_latency = max(latencies) if latencies else 0
        
        return {
            'success': True,
            'total_count': total_count,
            'test_duration': test_duration,
            'data_rate': data_rate,
            'exchanges': {k: {'count': v['count'], 'subjects': list(v['subjects'])} 
                         for k, v in exchanges.items()},
            'unique_subjects': list(subjects),
            'data_integrity': data_integrity,
            'latency': {
                'average': avg_latency,
                'maximum': max_latency,
                'samples': len(latencies)
            }
        }
    
    def _check_data_integrity(self) -> Dict[str, Any]:
        """检查数据完整性"""
        integrity = {
            'valid_count': 0,
            'invalid_count': 0,
            'missing_fields': [],
            'format_errors': []
        }
        
        required_fields = ['symbol', 'price', 'quantity', 'timestamp', 'side']
        
        for item in self.received_data:
            data = item['data']
            is_valid = True
            
            # 检查必需字段
            for field in required_fields:
                if field not in data:
                    integrity['missing_fields'].append(field)
                    is_valid = False
            
            # 检查数据格式
            try:
                if 'price' in data:
                    float(data['price'])
                if 'quantity' in data:
                    float(data['quantity'])
            except (ValueError, TypeError) as e:
                integrity['format_errors'].append(str(e))
                is_valid = False
            
            if is_valid:
                integrity['valid_count'] += 1
            else:
                integrity['invalid_count'] += 1
        
        return integrity
    
    async def cleanup(self):
        """清理资源"""
        print("🧹 清理资源...")
        
        self.running = False
        
        if self.collector:
            try:
                await self.collector.stop()
            except Exception as e:
                print(f"⚠️ 停止数据收集器失败: {e}")
        
        if self.nats_client:
            try:
                await self.nats_client.close()
            except Exception as e:
                print(f"⚠️ 关闭NATS连接失败: {e}")
        
        print("✅ 资源清理完成")


async def run_end_to_end_test():
    """运行端到端测试"""
    print("🚀 MarketPrism Trades Manager端到端测试")
    print("="*80)
    
    runner = EndToEndTestRunner()
    
    try:
        # 设置信号处理
        def signal_handler(signum, frame):
            print("\n⚠️ 接收到中断信号，正在停止测试...")
            runner.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # 1. 设置组件
        await runner.setup_nats_subscriber()
        await runner.setup_collector()
        
        # 2. 启动数据收集
        await runner.start_data_collection()
        
        # 3. 运行测试
        await runner.run_test()
        
        # 4. 分析结果
        print("\n📊 分析测试结果...")
        results = runner.analyze_results()
        
        if not results['success']:
            print(f"❌ 测试失败: {results['error']}")
            return False
        
        # 打印结果
        print("="*60)
        print("📈 端到端测试结果:")
        print(f"⏱️ 测试时长: {results['test_duration']}秒")
        print(f"📊 总数据量: {results['total_count']}条")
        print(f"🚀 数据速率: {results['data_rate']:.1f}条/秒")
        print(f"🏢 交易所数量: {len(results['exchanges'])}")
        print(f"📋 主题数量: {len(results['unique_subjects'])}")
        
        # 交易所详情
        print(f"\n📋 各交易所数据:")
        for exchange, stats in results['exchanges'].items():
            print(f"  {exchange}: {stats['count']}条数据")
            for subject in stats['subjects']:
                print(f"    - {subject}")
        
        # 数据完整性
        integrity = results['data_integrity']
        print(f"\n🔍 数据完整性:")
        print(f"  有效数据: {integrity['valid_count']}条")
        print(f"  无效数据: {integrity['invalid_count']}条")
        if integrity['missing_fields']:
            print(f"  缺失字段: {set(integrity['missing_fields'])}")
        if integrity['format_errors']:
            print(f"  格式错误: {len(integrity['format_errors'])}个")
        
        # 延迟分析
        latency = results['latency']
        print(f"\n⚡ 延迟分析:")
        print(f"  平均延迟: {latency['average']:.3f}秒")
        print(f"  最大延迟: {latency['maximum']:.3f}秒")
        print(f"  样本数量: {latency['samples']}")
        
        # 判断测试是否成功
        success_criteria = {
            'min_data_count': 50,      # 至少50条数据
            'min_data_rate': 0.5,      # 至少0.5条/秒
            'min_exchanges': 1,        # 至少1个交易所
            'max_invalid_rate': 0.1,   # 最多10%无效数据
            'max_avg_latency': 5.0     # 最大平均延迟5秒
        }
        
        success = True
        issues = []
        
        if results['total_count'] < success_criteria['min_data_count']:
            success = False
            issues.append(f"数据量不足: {results['total_count']} < {success_criteria['min_data_count']}")
        
        if results['data_rate'] < success_criteria['min_data_rate']:
            success = False
            issues.append(f"数据速率过低: {results['data_rate']:.1f} < {success_criteria['min_data_rate']}")
        
        if len(results['exchanges']) < success_criteria['min_exchanges']:
            success = False
            issues.append(f"交易所数量不足: {len(results['exchanges'])} < {success_criteria['min_exchanges']}")
        
        invalid_rate = integrity['invalid_count'] / results['total_count'] if results['total_count'] > 0 else 0
        if invalid_rate > success_criteria['max_invalid_rate']:
            success = False
            issues.append(f"无效数据率过高: {invalid_rate:.1%} > {success_criteria['max_invalid_rate']:.1%}")
        
        if latency['average'] > success_criteria['max_avg_latency']:
            success = False
            issues.append(f"平均延迟过高: {latency['average']:.1f}s > {success_criteria['max_avg_latency']}s")
        
        print(f"\n🎯 最终结果:")
        if success:
            print("🎉 端到端测试通过！")
            print("✅ 数据流完整且稳定")
            print("✅ 延迟在可接受范围内")
            print("✅ 数据格式正确")
        else:
            print("⚠️ 端到端测试存在问题:")
            for issue in issues:
                print(f"  ❌ {issue}")
        
        return success
        
    except Exception as e:
        print(f"❌ 端到端测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        await runner.cleanup()


async def main():
    """主函数"""
    try:
        success = await run_end_to_end_test()
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
