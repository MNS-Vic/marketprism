#!/usr/bin/env python3
"""
多交易所并发性能测试

测试Binance + OKX + Deribit同时运行的性能表现
监控CPU、内存使用，网络连接稳定性，数据处理速度
"""

import asyncio
import signal
import sys
import time
import psutil
import os
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from dataclasses import dataclass
from typing import Dict, List, Optional
import json

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from marketprism_collector.config import Config
from marketprism_collector.collector import MarketDataCollector


@dataclass
class PerformanceMetrics:
    """性能指标数据类"""
    timestamp: datetime
    cpu_percent: float
    memory_mb: float
    memory_percent: float
    messages_received: int
    messages_processed: int
    messages_published: int
    errors_count: int
    connections_active: int
    data_rate_per_second: float


class MultiExchangePerformanceTest:
    """多交易所性能测试器"""
    
    def __init__(self):
        self.start_time = None
        self.running = True
        self.metrics_history: List[PerformanceMetrics] = []
        self.exchange_stats = defaultdict(lambda: defaultdict(int))
        self.process = psutil.Process(os.getpid())
        
        # 性能阈值
        self.thresholds = {
            'max_cpu_percent': 50.0,
            'max_memory_mb': 500.0,
            'min_data_rate': 100.0,  # msg/s
            'min_connection_stability': 99.0,  # %
            'max_error_rate': 0.1  # %
        }
        
    async def run_comprehensive_test(self, duration_minutes: int = 10):
        """运行综合性能测试"""
        print("🚀 多交易所并发性能测试")
        print("=" * 80)
        print(f"⏱️  测试时长: {duration_minutes}分钟")
        print(f"🏢 测试交易所: Binance + OKX + Deribit")
        print(f"📊 监控指标: CPU、内存、网络、数据处理速度")
        print()
        
        try:
            # 1. 环境检查
            await self._check_environment()
            
            # 2. 配置验证
            config = await self._setup_config()
            
            # 3. 启动收集器
            collector = await self._start_collector(config)
            
            # 4. 性能监控
            await self._run_performance_monitoring(collector, duration_minutes)
            
            # 5. 生成报告
            await self._generate_performance_report(collector)
            
            # 6. 停止收集器
            await self._stop_collector(collector)
            
            return True
            
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def _check_environment(self):
        """检查测试环境"""
        print("🔍 环境检查...")
        
        # 检查系统资源
        cpu_count = psutil.cpu_count()
        memory_total = psutil.virtual_memory().total / (1024**3)  # GB
        
        print(f"   💻 CPU核心数: {cpu_count}")
        print(f"   🧠 总内存: {memory_total:.1f}GB")
        
        # 检查网络连接
        try:
            import requests
            response = requests.get("https://api.binance.com/api/v3/ping", timeout=5)
            binance_ok = response.status_code == 200
        except:
            binance_ok = False
            
        try:
            response = requests.get("https://www.okx.com/api/v5/public/time", timeout=5)
            okx_ok = response.status_code == 200
        except:
            okx_ok = False
            
        try:
            response = requests.get("https://www.deribit.com/api/v2/public/get_time", timeout=5)
            deribit_ok = response.status_code == 200
        except:
            deribit_ok = False
        
        print(f"   🌐 Binance连接: {'✅' if binance_ok else '❌'}")
        print(f"   🌐 OKX连接: {'✅' if okx_ok else '❌'}")
        print(f"   🌐 Deribit连接: {'✅' if deribit_ok else '❌'}")
        
        if not all([binance_ok, okx_ok, deribit_ok]):
            print("⚠️  部分交易所连接失败，测试可能受影响")
        
        print("✅ 环境检查完成\n")
    
    async def _setup_config(self) -> Config:
        """设置测试配置"""
        print("⚙️  配置多交易所测试...")
        
        # 直接创建ExchangeConfig对象
        from marketprism_collector.types import ExchangeConfig, Exchange, MarketType, DataType
        
        exchanges = []
        
        # Binance配置
        binance_config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            enabled=True,
            market_type=MarketType.SPOT,
            base_url='https://api.binance.com',
            ws_url='wss://stream.binance.com:9443/ws',
            symbols=['BTCUSDT', 'ETHUSDT'],
            data_types=[DataType.TRADE, DataType.ORDERBOOK, DataType.TICKER],
            ping_interval=30,
            reconnect_attempts=5,
            reconnect_delay=5
        )
        exchanges.append(binance_config)
        
        # OKX配置
        okx_config = ExchangeConfig(
            exchange=Exchange.OKX,
            enabled=True,
            market_type=MarketType.SPOT,
            base_url='https://www.okx.com',
            ws_url='wss://ws.okx.com:8443/ws/v5/public',
            symbols=['BTC-USDT', 'ETH-USDT'],
            data_types=[DataType.TRADE, DataType.ORDERBOOK, DataType.TICKER],
            ping_interval=30,
            reconnect_attempts=5,
            reconnect_delay=5
        )
        exchanges.append(okx_config)
        
        # Deribit配置
        deribit_config = ExchangeConfig(
            exchange=Exchange.DERIBIT,
            enabled=True,
            market_type=MarketType.FUTURES,
            base_url='https://www.deribit.com',
            ws_url='wss://www.deribit.com/ws/api/v2',
            symbols=['BTC-PERPETUAL', 'ETH-PERPETUAL'],
            data_types=[DataType.TRADE, DataType.ORDERBOOK, DataType.TICKER],
            ping_interval=30,
            reconnect_attempts=5,
            reconnect_delay=5
        )
        exchanges.append(deribit_config)
        
        # 创建Config对象
        from marketprism_collector.config import NATSConfig, CollectorConfig
        
        config = Config(
            exchanges=exchanges,
            nats=NATSConfig(url='nats://localhost:4222'),
            collector=CollectorConfig(
                http_port=8080,
                metrics_port=9090,
                use_real_exchanges=True
            )
        )
        
        enabled_exchanges = config.get_enabled_exchanges()
        print(f"   ✅ 配置了 {len(enabled_exchanges)} 个交易所")
        for exchange_config in enabled_exchanges:
            print(f"      - {exchange_config.exchange.value}: {len(exchange_config.symbols)} 交易对")
        
        print("✅ 配置完成\n")
        return config
    
    async def _start_collector(self, config: Config) -> MarketDataCollector:
        """启动数据收集器"""
        print("🚀 启动多交易所数据收集器...")
        
        collector = MarketDataCollector(config)
        
        # 启动收集器
        success = await collector.start()
        
        if not success:
            raise Exception("收集器启动失败")
        
        # 等待连接建立
        print("   ⏳ 等待连接建立...")
        await asyncio.sleep(10)
        
        # 检查连接状态
        connected_exchanges = 0
        for key, adapter in collector.exchange_adapters.items():
            if adapter.is_connected:
                connected_exchanges += 1
                print(f"   ✅ {key}: 已连接")
            else:
                print(f"   ❌ {key}: 未连接")
        
        print(f"✅ 收集器启动完成，{connected_exchanges} 个交易所已连接\n")
        self.start_time = time.time()
        
        return collector
    
    async def _run_performance_monitoring(self, collector: MarketDataCollector, duration_minutes: int):
        """运行性能监控"""
        print(f"📊 开始性能监控 ({duration_minutes}分钟)...")
        print()
        
        duration_seconds = duration_minutes * 60
        reporting_interval = 30  # 每30秒报告一次
        
        # 设置停止信号处理
        def signal_handler(signum, frame):
            print("\n⚠️  收到停止信号...")
            self.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        
        last_metrics = None
        
        for i in range(0, duration_seconds, 5):  # 每5秒采集一次指标
            if not self.running:
                break
            
            # 采集性能指标
            metrics = await self._collect_metrics(collector)
            self.metrics_history.append(metrics)
            
            # 每30秒报告一次
            if i > 0 and (i % reporting_interval == 0 or i >= duration_seconds - 5):
                await self._report_current_status(metrics, last_metrics, i + 5)
                last_metrics = metrics
            
            await asyncio.sleep(5)
        
        print("\n✅ 性能监控完成\n")
    
    async def _collect_metrics(self, collector: MarketDataCollector) -> PerformanceMetrics:
        """采集性能指标"""
        # 系统资源指标
        cpu_percent = self.process.cpu_percent()
        memory_info = self.process.memory_info()
        memory_mb = memory_info.rss / (1024 * 1024)
        memory_percent = self.process.memory_percent()
        
        # 收集器指标
        collector_metrics = collector.get_metrics()
        
        # 连接状态
        connections_active = sum(1 for adapter in collector.exchange_adapters.values() 
                               if adapter.is_connected)
        
        # 数据处理速度
        elapsed_time = time.time() - self.start_time
        data_rate = collector_metrics.messages_processed / max(elapsed_time, 1)
        
        return PerformanceMetrics(
            timestamp=datetime.now(),
            cpu_percent=cpu_percent,
            memory_mb=memory_mb,
            memory_percent=memory_percent,
            messages_received=collector_metrics.messages_received,
            messages_processed=collector_metrics.messages_processed,
            messages_published=collector_metrics.messages_published,
            errors_count=collector_metrics.errors_count,
            connections_active=connections_active,
            data_rate_per_second=data_rate
        )
    
    async def _report_current_status(self, current: PerformanceMetrics, 
                                   previous: Optional[PerformanceMetrics], 
                                   elapsed_seconds: int):
        """报告当前状态"""
        print(f"⏱️  {elapsed_seconds}秒状态报告:")
        
        # 系统资源
        cpu_status = "✅" if current.cpu_percent <= self.thresholds['max_cpu_percent'] else "⚠️"
        memory_status = "✅" if current.memory_mb <= self.thresholds['max_memory_mb'] else "⚠️"
        
        print(f"   💻 CPU使用: {current.cpu_percent:.1f}% {cpu_status}")
        print(f"   🧠 内存使用: {current.memory_mb:.1f}MB ({current.memory_percent:.1f}%) {memory_status}")
        
        # 数据处理
        rate_status = "✅" if current.data_rate_per_second >= self.thresholds['min_data_rate'] else "⚠️"
        print(f"   📨 消息处理: {current.messages_processed} 条")
        print(f"   📈 处理速度: {current.data_rate_per_second:.1f} msg/s {rate_status}")
        print(f"   ❌ 错误数量: {current.errors_count}")
        
        # 连接状态
        connection_status = "✅" if current.connections_active >= 3 else "⚠️"
        print(f"   🔗 活跃连接: {current.connections_active}/3 {connection_status}")
        
        # 增量统计
        if previous:
            msg_delta = current.messages_processed - previous.messages_processed
            time_delta = (current.timestamp - previous.timestamp).total_seconds()
            instant_rate = msg_delta / max(time_delta, 1)
            print(f"   ⚡ 瞬时速度: {instant_rate:.1f} msg/s")
        
        print()
    
    async def _generate_performance_report(self, collector: MarketDataCollector):
        """生成性能报告"""
        print("📋 生成性能测试报告...")
        
        if not self.metrics_history:
            print("❌ 没有性能数据")
            return
        
        # 计算统计指标
        total_duration = (self.metrics_history[-1].timestamp - self.metrics_history[0].timestamp).total_seconds()
        final_metrics = self.metrics_history[-1]
        
        # CPU和内存统计
        cpu_values = [m.cpu_percent for m in self.metrics_history]
        memory_values = [m.memory_mb for m in self.metrics_history]
        
        avg_cpu = sum(cpu_values) / len(cpu_values)
        max_cpu = max(cpu_values)
        avg_memory = sum(memory_values) / len(memory_values)
        max_memory = max(memory_values)
        
        # 数据处理统计
        avg_rate = final_metrics.messages_processed / max(total_duration, 1)
        error_rate = (final_metrics.errors_count / max(final_metrics.messages_received, 1)) * 100
        
        # 连接稳定性
        connection_samples = [m.connections_active for m in self.metrics_history]
        stable_connections = sum(1 for c in connection_samples if c >= 3)
        connection_stability = (stable_connections / len(connection_samples)) * 100
        
        print("\n" + "="*80)
        print("📊 多交易所并发性能测试报告")
        print("="*80)
        
        print(f"\n⏱️  测试时长: {total_duration:.1f}秒")
        print(f"🏢 测试交易所: 3个 (Binance + OKX + Deribit)")
        
        print(f"\n💻 CPU性能:")
        print(f"   平均使用率: {avg_cpu:.1f}%")
        print(f"   峰值使用率: {max_cpu:.1f}%")
        print(f"   性能评估: {'✅ 优秀' if max_cpu <= 50 else '⚠️ 需优化' if max_cpu <= 80 else '❌ 超负荷'}")
        
        print(f"\n🧠 内存性能:")
        print(f"   平均使用: {avg_memory:.1f}MB")
        print(f"   峰值使用: {max_memory:.1f}MB")
        print(f"   性能评估: {'✅ 优秀' if max_memory <= 500 else '⚠️ 需优化' if max_memory <= 800 else '❌ 超负荷'}")
        
        print(f"\n📈 数据处理性能:")
        print(f"   总处理消息: {final_metrics.messages_processed:,}")
        print(f"   平均速度: {avg_rate:.1f} msg/s")
        print(f"   错误率: {error_rate:.3f}%")
        print(f"   性能评估: {'✅ 优秀' if avg_rate >= 1000 else '⚠️ 良好' if avg_rate >= 500 else '❌ 需优化'}")
        
        print(f"\n🔗 连接稳定性:")
        print(f"   稳定性: {connection_stability:.1f}%")
        print(f"   性能评估: {'✅ 优秀' if connection_stability >= 99 else '⚠️ 良好' if connection_stability >= 95 else '❌ 需优化'}")
        
        # 综合评分
        scores = []
        scores.append(100 if max_cpu <= 50 else max(0, 100 - (max_cpu - 50) * 2))
        scores.append(100 if max_memory <= 500 else max(0, 100 - (max_memory - 500) / 5))
        scores.append(100 if avg_rate >= 1000 else max(0, avg_rate / 10))
        scores.append(connection_stability)
        scores.append(100 if error_rate <= 0.1 else max(0, 100 - error_rate * 10))
        
        overall_score = sum(scores) / len(scores)
        
        print(f"\n🎯 综合评分: {overall_score:.1f}/100")
        if overall_score >= 90:
            print("   评级: ⭐⭐⭐⭐⭐ 优秀")
        elif overall_score >= 80:
            print("   评级: ⭐⭐⭐⭐ 良好")
        elif overall_score >= 70:
            print("   评级: ⭐⭐⭐ 一般")
        else:
            print("   评级: ⭐⭐ 需要优化")
        
        # 保存详细报告
        report_data = {
            'test_info': {
                'duration_seconds': total_duration,
                'exchanges_tested': 3,
                'timestamp': datetime.now().isoformat()
            },
            'performance_metrics': {
                'cpu': {
                    'average_percent': avg_cpu,
                    'peak_percent': max_cpu,
                    'threshold_met': max_cpu <= self.thresholds['max_cpu_percent']
                },
                'memory': {
                    'average_mb': avg_memory,
                    'peak_mb': max_memory,
                    'threshold_met': max_memory <= self.thresholds['max_memory_mb']
                },
                'data_processing': {
                    'total_messages': final_metrics.messages_processed,
                    'average_rate_per_second': avg_rate,
                    'error_rate_percent': error_rate,
                    'threshold_met': avg_rate >= self.thresholds['min_data_rate']
                },
                'connection_stability': {
                    'stability_percent': connection_stability,
                    'threshold_met': connection_stability >= self.thresholds['min_connection_stability']
                }
            },
            'overall_score': overall_score,
            'detailed_metrics': [
                {
                    'timestamp': m.timestamp.isoformat(),
                    'cpu_percent': m.cpu_percent,
                    'memory_mb': m.memory_mb,
                    'messages_processed': m.messages_processed,
                    'data_rate': m.data_rate_per_second,
                    'connections_active': m.connections_active
                }
                for m in self.metrics_history
            ]
        }
        
        # 保存报告文件
        report_file = f'multi_exchange_performance_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(report_file, 'w') as f:
            json.dump(report_data, f, indent=2, default=str)
        
        print(f"\n📄 详细报告已保存: {report_file}")
        print("="*80)
    
    async def _stop_collector(self, collector: MarketDataCollector):
        """停止数据收集器"""
        print("\n🛑 停止数据收集器...")
        await collector.stop()
        print("✅ 收集器已停止")


async def main():
    """主函数"""
    if len(sys.argv) > 1:
        duration = int(sys.argv[1])
    else:
        duration = 5  # 默认5分钟测试
    
    tester = MultiExchangePerformanceTest()
    success = await tester.run_comprehensive_test(duration)
    
    if success:
        print("\n🎉 多交易所并发性能测试完成！")
        sys.exit(0)
    else:
        print("\n❌ 测试失败")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main()) 