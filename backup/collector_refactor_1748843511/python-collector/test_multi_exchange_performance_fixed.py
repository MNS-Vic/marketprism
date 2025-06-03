#!/usr/bin/env python3
"""
多交易所并发性能测试 - 修复版本

使用显式代理配置解决连接问题
"""

import asyncio
import time
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any
import psutil
import aiohttp

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from marketprism_collector.types import ExchangeConfig, Exchange, MarketType, DataType
from marketprism_collector.exchanges import ExchangeAdapterFactory


class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self):
        self.start_time = time.time()
        self.cpu_samples = []
        self.memory_samples = []
        self.message_count = 0
        self.error_count = 0
        self.connection_status = {}
        
    def record_cpu_memory(self):
        """记录CPU和内存使用"""
        process = psutil.Process()
        cpu_percent = process.cpu_percent()
        memory_mb = process.memory_info().rss / 1024 / 1024
        
        self.cpu_samples.append(cpu_percent)
        self.memory_samples.append(memory_mb)
        
    def record_message(self):
        """记录消息处理"""
        self.message_count += 1
        
    def record_error(self):
        """记录错误"""
        self.error_count += 1
        
    def set_connection_status(self, exchange: str, status: bool):
        """设置连接状态"""
        self.connection_status[exchange] = status
        
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        elapsed = time.time() - self.start_time
        
        return {
            'test_duration': elapsed,
            'messages_processed': self.message_count,
            'messages_per_second': self.message_count / elapsed if elapsed > 0 else 0,
            'error_count': self.error_count,
            'error_rate': self.error_count / max(self.message_count, 1),
            'cpu_usage': {
                'average': sum(self.cpu_samples) / len(self.cpu_samples) if self.cpu_samples else 0,
                'peak': max(self.cpu_samples) if self.cpu_samples else 0,
                'samples': len(self.cpu_samples)
            },
            'memory_usage': {
                'average': sum(self.memory_samples) / len(self.memory_samples) if self.memory_samples else 0,
                'peak': max(self.memory_samples) if self.memory_samples else 0,
                'samples': len(self.memory_samples)
            },
            'connection_status': self.connection_status,
            'connection_stability': sum(1 for status in self.connection_status.values() if status) / len(self.connection_status) * 100 if self.connection_status else 0
        }


async def test_exchange_rest_api_with_proxy(exchange_name: str, api_url: str) -> bool:
    """测试交易所REST API连接（使用显式代理）"""
    try:
        proxy = "http://127.0.0.1:1087"
        timeout = aiohttp.ClientTimeout(total=10)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(api_url, proxy=proxy) as response:
                if response.status == 200:
                    print(f"   ✅ {exchange_name} REST API连接成功 ({response.status})")
                    return True
                else:
                    print(f"   ❌ {exchange_name} REST API连接失败 ({response.status})")
                    return False
                    
    except Exception as e:
        print(f"   ❌ {exchange_name} REST API连接异常: {e}")
        return False


async def test_multi_exchange_performance():
    """多交易所并发性能测试"""
    print("🚀 多交易所并发性能测试 - 修复版本")
    print("=" * 80)
    
    # 显示代理设置
    print(f"🔧 代理配置:")
    print(f"   http_proxy: {os.getenv('http_proxy', '未设置')}")
    print(f"   https_proxy: {os.getenv('https_proxy', '未设置')}")
    print(f"   ALL_PROXY: {os.getenv('ALL_PROXY', '未设置')}")
    print()
    
    # 测试REST API连接
    print("📡 测试REST API连接...")
    api_tests = [
        ("Binance", "https://api.binance.com/api/v3/ping"),
        ("OKX", "https://www.okx.com/api/v5/public/time"),
        ("Deribit", "https://www.deribit.com/api/v2/public/get_time")
    ]
    
    rest_results = {}
    for exchange_name, api_url in api_tests:
        rest_results[exchange_name] = await test_exchange_rest_api_with_proxy(exchange_name, api_url)
    
    print()
    
    # 创建交易所配置
    configs = []
    
    # Binance配置
    if rest_results.get("Binance", False):
        binance_config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            market_type=MarketType.SPOT,
            enabled=True,
            symbols=["BTC-USDT", "ETH-USDT"],
            data_types=[DataType.TRADE, DataType.TICKER],
            ws_url="wss://stream.binance.com:9443/ws",
            base_url="https://api.binance.com",
            ping_interval=20,
            reconnect_attempts=3,
            reconnect_delay=5,
            depth_limit=20
        )
        configs.append(binance_config)
    
    # OKX配置
    if rest_results.get("OKX", False):
        okx_config = ExchangeConfig(
            exchange=Exchange.OKX,
            market_type=MarketType.SPOT,
            enabled=True,
            symbols=["BTC-USDT", "ETH-USDT"],
            data_types=[DataType.TRADE, DataType.TICKER],
            ws_url="wss://ws.okx.com:8443/ws/v5/public",
            base_url="https://www.okx.com",
            ping_interval=20,
            reconnect_attempts=3,
            reconnect_delay=5,
            depth_limit=20
        )
        configs.append(okx_config)
    
    # Deribit配置
    if rest_results.get("Deribit", False):
        deribit_config = ExchangeConfig(
            exchange=Exchange.DERIBIT,
            market_type=MarketType.DERIVATIVES,
            enabled=True,
            symbols=["BTC-PERPETUAL", "ETH-PERPETUAL"],
            data_types=[DataType.TRADE, DataType.TICKER],
            ws_url="wss://www.deribit.com/ws/api/v2",
            base_url="https://www.deribit.com",
            ping_interval=20,
            reconnect_attempts=3,
            reconnect_delay=5,
            depth_limit=20
        )
        configs.append(deribit_config)
    
    if not configs:
        print("❌ 没有可用的交易所配置，测试终止")
        return
    
    print(f"📊 开始测试 {len(configs)} 个交易所...")
    
    # 创建性能监控器
    monitor = PerformanceMonitor()
    
    # 创建交易所适配器
    adapters = []
    factory = ExchangeAdapterFactory()
    
    for config in configs:
        try:
            adapter = factory.create_adapter(config)
            
            # 注册数据回调
            def create_callback(exchange_name):
                def callback(data):
                    monitor.record_message()
                    if len(monitor.cpu_samples) % 100 == 0:  # 每100条消息记录一次性能
                        monitor.record_cpu_memory()
                return callback
            
            adapter.register_callback(DataType.TRADE, create_callback(config.exchange.value))
            adapter.register_callback(DataType.TICKER, create_callback(config.exchange.value))
            
            adapters.append((config.exchange.value, adapter))
            
        except Exception as e:
            print(f"❌ 创建 {config.exchange.value} 适配器失败: {e}")
            monitor.record_error()
    
    if not adapters:
        print("❌ 没有成功创建的适配器，测试终止")
        return
    
    # 启动适配器
    print(f"\n🔌 启动 {len(adapters)} 个交易所适配器...")
    
    start_tasks = []
    for exchange_name, adapter in adapters:
        task = asyncio.create_task(adapter.start())
        start_tasks.append((exchange_name, task))
    
    # 等待启动完成
    for exchange_name, task in start_tasks:
        try:
            success = await asyncio.wait_for(task, timeout=30)
            monitor.set_connection_status(exchange_name, success)
            if success:
                print(f"   ✅ {exchange_name} 启动成功")
            else:
                print(f"   ❌ {exchange_name} 启动失败")
        except asyncio.TimeoutError:
            print(f"   ⏰ {exchange_name} 启动超时")
            monitor.set_connection_status(exchange_name, False)
        except Exception as e:
            print(f"   ❌ {exchange_name} 启动异常: {e}")
            monitor.set_connection_status(exchange_name, False)
            monitor.record_error()
    
    # 运行测试
    test_duration = 120  # 2分钟测试
    print(f"\n⏱️ 运行性能测试 {test_duration} 秒...")
    
    # 定期记录性能数据
    async def performance_recorder():
        while True:
            monitor.record_cpu_memory()
            await asyncio.sleep(5)  # 每5秒记录一次
    
    recorder_task = asyncio.create_task(performance_recorder())
    
    # 等待测试完成
    await asyncio.sleep(test_duration)
    
    # 停止性能记录
    recorder_task.cancel()
    
    # 停止适配器
    print("\n⏹️ 停止交易所适配器...")
    for exchange_name, adapter in adapters:
        try:
            await adapter.stop()
            print(f"   ✅ {exchange_name} 已停止")
        except Exception as e:
            print(f"   ❌ {exchange_name} 停止异常: {e}")
    
    # 生成测试报告
    stats = monitor.get_stats()
    
    print("\n📊 多交易所并发性能测试报告")
    print("=" * 80)
    
    print(f"⏱️ 测试时长: {stats['test_duration']:.1f}秒")
    print(f"📨 处理消息: {stats['messages_processed']:,}条")
    print(f"🚀 处理速度: {stats['messages_per_second']:.1f} msg/s")
    print(f"❌ 错误数量: {stats['error_count']}个")
    print(f"📉 错误率: {stats['error_rate']:.3%}")
    
    print(f"\n💻 CPU性能:")
    print(f"   平均使用率: {stats['cpu_usage']['average']:.1f}%")
    print(f"   峰值使用率: {stats['cpu_usage']['peak']:.1f}%")
    print(f"   采样次数: {stats['cpu_usage']['samples']}次")
    
    print(f"\n🧠 内存性能:")
    print(f"   平均使用: {stats['memory_usage']['average']:.1f}MB")
    print(f"   峰值使用: {stats['memory_usage']['peak']:.1f}MB")
    print(f"   采样次数: {stats['memory_usage']['samples']}次")
    
    print(f"\n🔗 连接状态:")
    for exchange, status in stats['connection_status'].items():
        status_icon = "✅" if status else "❌"
        print(f"   {status_icon} {exchange}: {'连接成功' if status else '连接失败'}")
    
    print(f"\n📈 连接稳定性: {stats['connection_stability']:.1f}%")
    
    # 性能评估
    print(f"\n🎯 性能评估:")
    
    # CPU评估
    cpu_avg = stats['cpu_usage']['average']
    if cpu_avg < 30:
        cpu_grade = "优秀"
    elif cpu_avg < 50:
        cpu_grade = "良好"
    elif cpu_avg < 70:
        cpu_grade = "一般"
    else:
        cpu_grade = "需优化"
    print(f"   CPU性能: {cpu_grade} (平均{cpu_avg:.1f}%)")
    
    # 内存评估
    memory_avg = stats['memory_usage']['average']
    if memory_avg < 200:
        memory_grade = "优秀"
    elif memory_avg < 500:
        memory_grade = "良好"
    elif memory_avg < 1000:
        memory_grade = "一般"
    else:
        memory_grade = "需优化"
    print(f"   内存性能: {memory_grade} (平均{memory_avg:.1f}MB)")
    
    # 处理速度评估
    msg_per_sec = stats['messages_per_second']
    if msg_per_sec > 100:
        speed_grade = "优秀"
    elif msg_per_sec > 50:
        speed_grade = "良好"
    elif msg_per_sec > 20:
        speed_grade = "一般"
    else:
        speed_grade = "需优化"
    print(f"   处理速度: {speed_grade} ({msg_per_sec:.1f} msg/s)")
    
    # 连接稳定性评估
    stability = stats['connection_stability']
    if stability >= 100:
        stability_grade = "完美"
    elif stability >= 80:
        stability_grade = "优秀"
    elif stability >= 60:
        stability_grade = "良好"
    else:
        stability_grade = "需改进"
    print(f"   连接稳定性: {stability_grade} ({stability:.1f}%)")
    
    # 综合评分
    cpu_score = max(0, 100 - cpu_avg)
    memory_score = max(0, 100 - memory_avg / 10)
    speed_score = min(100, msg_per_sec)
    stability_score = stability
    
    overall_score = (cpu_score + memory_score + speed_score + stability_score) / 4
    
    if overall_score >= 90:
        overall_grade = "⭐⭐⭐⭐⭐ 优秀"
    elif overall_score >= 80:
        overall_grade = "⭐⭐⭐⭐ 良好"
    elif overall_score >= 70:
        overall_grade = "⭐⭐⭐ 一般"
    elif overall_score >= 60:
        overall_grade = "⭐⭐ 需改进"
    else:
        overall_grade = "⭐ 需优化"
    
    print(f"\n🏆 综合评分: {overall_score:.1f}/100 {overall_grade}")
    
    print("=" * 80)
    
    # 保存详细结果
    result_file = f"multi_exchange_performance_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"📄 详细结果已保存到: {result_file}")


async def main():
    """主函数"""
    try:
        await test_multi_exchange_performance()
    except KeyboardInterrupt:
        print("\n⏹️ 测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())