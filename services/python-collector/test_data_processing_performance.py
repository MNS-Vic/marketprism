#!/usr/bin/env python3
"""
数据处理性能测试

专注测试数据标准化、处理速度、内存使用等核心性能指标
不依赖WebSocket连接，使用模拟数据进行测试
"""

import asyncio
import time
import json
import psutil
import os
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any
from dataclasses import dataclass
import sys

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from marketprism_collector.types import (
    NormalizedTrade, NormalizedOrderBook, NormalizedTicker,
    PriceLevel, DataType
)


@dataclass
class ProcessingMetrics:
    """处理性能指标"""
    timestamp: datetime
    cpu_percent: float
    memory_mb: float
    processed_count: int
    processing_rate: float
    avg_processing_time_ms: float


class DataProcessingPerformanceTest:
    """数据处理性能测试器"""
    
    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.metrics_history: List[ProcessingMetrics] = []
        
        # 性能目标
        self.targets = {
            'processing_rate': 1000,  # msg/s
            'max_cpu_percent': 30.0,
            'max_memory_mb': 200.0,
            'max_processing_time_ms': 5.0
        }
    
    async def run_performance_test(self, duration_minutes: int = 5):
        """运行数据处理性能测试"""
        print("⚡ 数据处理性能测试")
        print("=" * 80)
        print(f"⏱️  测试时长: {duration_minutes}分钟")
        print(f"🎯 测试目标: 数据标准化、处理速度、内存使用")
        print()
        
        try:
            # 1. 生成测试数据
            test_data = await self._generate_test_data()
            print(f"📊 生成测试数据: {len(test_data)}条")
            
            # 2. 数据标准化性能测试
            await self._test_data_normalization(test_data)
            
            # 3. 批量处理性能测试
            await self._test_batch_processing(test_data, duration_minutes)
            
            # 4. 内存使用测试
            await self._test_memory_usage(test_data)
            
            # 5. 并发处理测试
            await self._test_concurrent_processing(test_data)
            
            # 6. 生成性能报告
            await self._generate_performance_report()
            
            return True
            
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def _generate_test_data(self) -> List[Dict[str, Any]]:
        """生成测试数据"""
        print("🔧 生成测试数据...")
        
        test_data = []
        
        # 生成交易数据
        for i in range(1000):
            trade_data = {
                'type': 'trade',
                'exchange': 'okx',
                'symbol': 'BTC-USDT',
                'trade_id': str(i),
                'price': f"{100000 + i * 0.1}",
                'quantity': f"{0.001 + i * 0.0001}",
                'timestamp': int(time.time() * 1000),
                'side': 'buy' if i % 2 == 0 else 'sell'
            }
            test_data.append(trade_data)
        
        # 生成订单簿数据
        for i in range(500):
            orderbook_data = {
                'type': 'orderbook',
                'exchange': 'okx',
                'symbol': 'BTC-USDT',
                'bids': [
                    [f"{100000 - j}", f"{0.1 + j * 0.01}"] 
                    for j in range(20)
                ],
                'asks': [
                    [f"{100000 + j}", f"{0.1 + j * 0.01}"] 
                    for j in range(20)
                ],
                'timestamp': int(time.time() * 1000)
            }
            test_data.append(orderbook_data)
        
        # 生成行情数据
        for i in range(300):
            ticker_data = {
                'type': 'ticker',
                'exchange': 'okx',
                'symbol': 'BTC-USDT',
                'last_price': f"{100000 + i}",
                'open_price': f"{99000 + i}",
                'high_price': f"{101000 + i}",
                'low_price': f"{98000 + i}",
                'volume': f"{1000 + i}",
                'timestamp': int(time.time() * 1000)
            }
            test_data.append(ticker_data)
        
        print(f"✅ 生成完成: 交易数据1000条, 订单簿500条, 行情300条")
        return test_data
    
    async def _test_data_normalization(self, test_data: List[Dict[str, Any]]):
        """测试数据标准化性能"""
        print("\n🔄 测试数据标准化性能...")
        
        start_time = time.time()
        normalized_count = 0
        processing_times = []
        
        for data in test_data:
            process_start = time.time()
            
            try:
                if data['type'] == 'trade':
                    normalized = await self._normalize_trade(data)
                elif data['type'] == 'orderbook':
                    normalized = await self._normalize_orderbook(data)
                elif data['type'] == 'ticker':
                    normalized = await self._normalize_ticker(data)
                else:
                    continue
                
                if normalized:
                    normalized_count += 1
                
                process_time = (time.time() - process_start) * 1000
                processing_times.append(process_time)
                
            except Exception as e:
                print(f"   ❌ 标准化失败: {e}")
        
        total_time = time.time() - start_time
        avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0
        processing_rate = normalized_count / total_time
        
        print(f"   📊 标准化结果:")
        print(f"      成功处理: {normalized_count}/{len(test_data)} 条")
        print(f"      处理速度: {processing_rate:.1f} msg/s")
        print(f"      平均处理时间: {avg_processing_time:.2f}ms")
        print(f"      总耗时: {total_time:.2f}s")
        
        # 评估性能
        if processing_rate >= self.targets['processing_rate']:
            print(f"      ✅ 处理速度达标 (目标: {self.targets['processing_rate']} msg/s)")
        else:
            print(f"      ⚠️ 处理速度需优化 (目标: {self.targets['processing_rate']} msg/s)")
        
        if avg_processing_time <= self.targets['max_processing_time_ms']:
            print(f"      ✅ 处理延迟达标 (目标: <{self.targets['max_processing_time_ms']}ms)")
        else:
            print(f"      ⚠️ 处理延迟需优化 (目标: <{self.targets['max_processing_time_ms']}ms)")
    
    async def _test_batch_processing(self, test_data: List[Dict[str, Any]], duration_minutes: int):
        """测试批量处理性能"""
        print(f"\n⚡ 测试批量处理性能 ({duration_minutes}分钟)...")
        
        duration_seconds = duration_minutes * 60
        batch_size = 100
        total_processed = 0
        
        start_time = time.time()
        
        while time.time() - start_time < duration_seconds:
            batch_start = time.time()
            
            # 处理一批数据
            batch = test_data[:batch_size]
            processed_count = 0
            
            for data in batch:
                try:
                    if data['type'] == 'trade':
                        normalized = await self._normalize_trade(data)
                    elif data['type'] == 'orderbook':
                        normalized = await self._normalize_orderbook(data)
                    elif data['type'] == 'ticker':
                        normalized = await self._normalize_ticker(data)
                    else:
                        continue
                    
                    if normalized:
                        processed_count += 1
                        total_processed += 1
                
                except Exception:
                    pass
            
            # 收集性能指标
            cpu_percent = self.process.cpu_percent()
            memory_mb = self.process.memory_info().rss / (1024 * 1024)
            batch_time = time.time() - batch_start
            processing_rate = processed_count / batch_time if batch_time > 0 else 0
            avg_processing_time = (batch_time / processed_count * 1000) if processed_count > 0 else 0
            
            metrics = ProcessingMetrics(
                timestamp=datetime.now(),
                cpu_percent=cpu_percent,
                memory_mb=memory_mb,
                processed_count=total_processed,
                processing_rate=processing_rate,
                avg_processing_time_ms=avg_processing_time
            )
            
            self.metrics_history.append(metrics)
            
            # 每30秒报告一次
            elapsed = time.time() - start_time
            if len(self.metrics_history) % 10 == 0:  # 大约每30秒
                print(f"   ⏱️  {elapsed:.0f}s: 处理 {total_processed} 条, "
                      f"速度 {processing_rate:.1f} msg/s, "
                      f"CPU {cpu_percent:.1f}%, 内存 {memory_mb:.1f}MB")
            
            # 短暂休息避免过度占用CPU
            await asyncio.sleep(0.1)
        
        total_time = time.time() - start_time
        avg_rate = total_processed / total_time
        
        print(f"   📊 批量处理结果:")
        print(f"      总处理量: {total_processed:,} 条")
        print(f"      平均速度: {avg_rate:.1f} msg/s")
        print(f"      测试时长: {total_time:.1f}s")
    
    async def _test_memory_usage(self, test_data: List[Dict[str, Any]]):
        """测试内存使用"""
        print("\n🧠 测试内存使用...")
        
        initial_memory = self.process.memory_info().rss / (1024 * 1024)
        print(f"   初始内存: {initial_memory:.1f}MB")
        
        # 创建大量标准化对象
        normalized_objects = []
        
        for i in range(0, len(test_data), 10):  # 每10个处理一次
            batch = test_data[i:i+10]
            
            for data in batch:
                try:
                    if data['type'] == 'trade':
                        normalized = await self._normalize_trade(data)
                    elif data['type'] == 'orderbook':
                        normalized = await self._normalize_orderbook(data)
                    elif data['type'] == 'ticker':
                        normalized = await self._normalize_ticker(data)
                    else:
                        continue
                    
                    if normalized:
                        normalized_objects.append(normalized)
                
                except Exception:
                    pass
            
            # 检查内存使用
            if len(normalized_objects) % 100 == 0:
                current_memory = self.process.memory_info().rss / (1024 * 1024)
                memory_increase = current_memory - initial_memory
                print(f"   对象数: {len(normalized_objects)}, "
                      f"内存: {current_memory:.1f}MB (+{memory_increase:.1f}MB)")
        
        final_memory = self.process.memory_info().rss / (1024 * 1024)
        total_increase = final_memory - initial_memory
        avg_memory_per_object = total_increase / len(normalized_objects) if normalized_objects else 0
        
        print(f"   📊 内存使用结果:")
        print(f"      最终内存: {final_memory:.1f}MB")
        print(f"      内存增长: {total_increase:.1f}MB")
        print(f"      平均每对象: {avg_memory_per_object*1024:.2f}KB")
        print(f"      对象总数: {len(normalized_objects):,}")
        
        # 清理内存
        del normalized_objects
        
        if total_increase <= self.targets['max_memory_mb']:
            print(f"      ✅ 内存使用达标 (目标: <{self.targets['max_memory_mb']}MB)")
        else:
            print(f"      ⚠️ 内存使用需优化 (目标: <{self.targets['max_memory_mb']}MB)")
    
    async def _test_concurrent_processing(self, test_data: List[Dict[str, Any]]):
        """测试并发处理性能"""
        print("\n🔀 测试并发处理性能...")
        
        async def process_batch(batch_data: List[Dict[str, Any]], batch_id: int):
            """处理一批数据"""
            processed = 0
            start_time = time.time()
            
            for data in batch_data:
                try:
                    if data['type'] == 'trade':
                        normalized = await self._normalize_trade(data)
                    elif data['type'] == 'orderbook':
                        normalized = await self._normalize_orderbook(data)
                    elif data['type'] == 'ticker':
                        normalized = await self._normalize_ticker(data)
                    else:
                        continue
                    
                    if normalized:
                        processed += 1
                
                except Exception:
                    pass
            
            processing_time = time.time() - start_time
            rate = processed / processing_time if processing_time > 0 else 0
            
            return {
                'batch_id': batch_id,
                'processed': processed,
                'time': processing_time,
                'rate': rate
            }
        
        # 分成多个批次并发处理
        batch_size = 200
        batches = [test_data[i:i+batch_size] for i in range(0, len(test_data), batch_size)]
        
        start_time = time.time()
        
        # 并发处理所有批次
        tasks = [process_batch(batch, i) for i, batch in enumerate(batches)]
        results = await asyncio.gather(*tasks)
        
        total_time = time.time() - start_time
        total_processed = sum(r['processed'] for r in results)
        avg_rate = total_processed / total_time
        
        print(f"   📊 并发处理结果:")
        print(f"      批次数量: {len(batches)}")
        print(f"      总处理量: {total_processed:,} 条")
        print(f"      总耗时: {total_time:.2f}s")
        print(f"      并发速度: {avg_rate:.1f} msg/s")
        
        # 显示各批次性能
        for result in results[:5]:  # 只显示前5个批次
            print(f"      批次{result['batch_id']}: {result['processed']}条, "
                  f"{result['rate']:.1f} msg/s")
        
        if len(results) > 5:
            print(f"      ... 还有{len(results)-5}个批次")
    
    async def _normalize_trade(self, data: Dict[str, Any]) -> NormalizedTrade:
        """标准化交易数据"""
        return NormalizedTrade(
            exchange_name=data['exchange'],
            symbol_name=data['symbol'],
            trade_id=data['trade_id'],
            price=Decimal(data['price']),
            quantity=Decimal(data['quantity']),
            quote_quantity=Decimal(data['price']) * Decimal(data['quantity']),
            timestamp=datetime.fromtimestamp(data['timestamp'] / 1000),
            is_buyer_maker=data['side'] == 'sell'
        )
    
    async def _normalize_orderbook(self, data: Dict[str, Any]) -> NormalizedOrderBook:
        """标准化订单簿数据"""
        bids = [PriceLevel(price=Decimal(bid[0]), quantity=Decimal(bid[1])) 
                for bid in data['bids']]
        asks = [PriceLevel(price=Decimal(ask[0]), quantity=Decimal(ask[1])) 
                for ask in data['asks']]
        
        return NormalizedOrderBook(
            exchange_name=data['exchange'],
            symbol_name=data['symbol'],
            bids=bids,
            asks=asks,
            timestamp=datetime.fromtimestamp(data['timestamp'] / 1000)
        )
    
    async def _normalize_ticker(self, data: Dict[str, Any]) -> NormalizedTicker:
        """标准化行情数据"""
        return NormalizedTicker(
            exchange_name=data['exchange'],
            symbol_name=data['symbol'],
            last_price=Decimal(data['last_price']),
            open_price=Decimal(data['open_price']),
            high_price=Decimal(data['high_price']),
            low_price=Decimal(data['low_price']),
            volume=Decimal(data['volume']),
            quote_volume=Decimal(data['volume']) * Decimal(data['last_price']),
            price_change=Decimal(data['last_price']) - Decimal(data['open_price']),
            price_change_percent=((Decimal(data['last_price']) - Decimal(data['open_price'])) / Decimal(data['open_price'])) * 100,
            weighted_avg_price=(Decimal(data['high_price']) + Decimal(data['low_price'])) / 2,
            last_quantity=Decimal('1.0'),
            best_bid_price=Decimal(data['last_price']) - Decimal('0.1'),
            best_bid_quantity=Decimal('1.0'),
            best_ask_price=Decimal(data['last_price']) + Decimal('0.1'),
            best_ask_quantity=Decimal('1.0'),
            open_time=datetime.fromtimestamp(data['timestamp'] / 1000),
            close_time=datetime.fromtimestamp(data['timestamp'] / 1000),
            trade_count=100,
            timestamp=datetime.fromtimestamp(data['timestamp'] / 1000)
        )
    
    async def _generate_performance_report(self):
        """生成性能报告"""
        print("\n📋 生成数据处理性能报告...")
        
        if not self.metrics_history:
            print("❌ 没有性能数据")
            return
        
        # 计算统计指标
        cpu_values = [m.cpu_percent for m in self.metrics_history]
        memory_values = [m.memory_mb for m in self.metrics_history]
        rate_values = [m.processing_rate for m in self.metrics_history]
        time_values = [m.avg_processing_time_ms for m in self.metrics_history]
        
        avg_cpu = sum(cpu_values) / len(cpu_values)
        max_cpu = max(cpu_values)
        avg_memory = sum(memory_values) / len(memory_values)
        max_memory = max(memory_values)
        avg_rate = sum(rate_values) / len(rate_values)
        max_rate = max(rate_values)
        avg_time = sum(time_values) / len(time_values)
        
        print("\n" + "="*80)
        print("📊 数据处理性能测试报告")
        print("="*80)
        
        print(f"\n💻 CPU性能:")
        print(f"   平均使用率: {avg_cpu:.1f}%")
        print(f"   峰值使用率: {max_cpu:.1f}%")
        print(f"   性能评估: {'✅ 达标' if max_cpu <= self.targets['max_cpu_percent'] else '⚠️ 需优化'}")
        
        print(f"\n🧠 内存性能:")
        print(f"   平均使用: {avg_memory:.1f}MB")
        print(f"   峰值使用: {max_memory:.1f}MB")
        print(f"   性能评估: {'✅ 达标' if max_memory <= self.targets['max_memory_mb'] else '⚠️ 需优化'}")
        
        print(f"\n⚡ 处理性能:")
        print(f"   平均速度: {avg_rate:.1f} msg/s")
        print(f"   峰值速度: {max_rate:.1f} msg/s")
        print(f"   平均延迟: {avg_time:.2f}ms")
        print(f"   性能评估: {'✅ 达标' if avg_rate >= self.targets['processing_rate'] else '⚠️ 需优化'}")
        
        # 综合评分
        scores = []
        scores.append(100 if max_cpu <= self.targets['max_cpu_percent'] else max(0, 100 - (max_cpu - self.targets['max_cpu_percent']) * 2))
        scores.append(100 if max_memory <= self.targets['max_memory_mb'] else max(0, 100 - (max_memory - self.targets['max_memory_mb']) / 2))
        scores.append(100 if avg_rate >= self.targets['processing_rate'] else min(100, avg_rate / self.targets['processing_rate'] * 100))
        scores.append(100 if avg_time <= self.targets['max_processing_time_ms'] else max(0, 100 - (avg_time - self.targets['max_processing_time_ms']) * 10))
        
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
        
        print("="*80)


async def main():
    """主函数"""
    if len(sys.argv) > 1:
        duration = int(sys.argv[1])
    else:
        duration = 3  # 默认3分钟测试
    
    tester = DataProcessingPerformanceTest()
    success = await tester.run_performance_test(duration)
    
    if success:
        print("\n🎉 数据处理性能测试完成！")
        sys.exit(0)
    else:
        print("\n❌ 测试失败")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main()) 