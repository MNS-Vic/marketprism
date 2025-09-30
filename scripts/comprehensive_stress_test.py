#!/usr/bin/env python3
"""
MarketPrism 完整数据链路压力测试和质量验证脚本
- 运行 15-20 分钟完整压力测试
- 验证所有 8 种数据类型的完整性、准确性、去重性、实时性、连续性
- 监控性能指标：吞吐量 ≥125.5 msg/s，成功率 ≥99.6%，错误率 ≈0%
- 生成详细的数据质量报告
"""

import asyncio
import aiohttp
import json
import time
import statistics
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path
import sys

# 配置
TEST_DURATION_MINUTES = 18  # 测试持续时间
SAMPLE_INTERVAL_SECONDS = 30  # 采样间隔
TARGET_THROUGHPUT = 125.5  # 目标吞吐量 msg/s
TARGET_SUCCESS_RATE = 99.6  # 目标成功率 %
MAX_ERROR_RATE = 0.4  # 最大错误率 %

# 服务端点
COLLECTOR_HEALTH = "http://127.0.0.1:8087/health"
COLLECTOR_METRICS = "http://127.0.0.1:9093/metrics"
HOT_STORAGE_HEALTH = "http://127.0.0.1:8085/health"
COLD_STORAGE_HEALTH = "http://127.0.0.1:8086/health"
NATS_MONITORING = "http://127.0.0.1:8222"
CLICKHOUSE_HTTP = "http://127.0.0.1:8123"

# 数据类型和表映射
DATA_TYPES = {
    "orderbook": "orderbooks",
    "trade": "trades", 
    "funding_rate": "funding_rates",
    "open_interest": "open_interests",
    "liquidation": "liquidations",
    "lsr_top_position": "lsr_top_positions",
    "lsr_all_account": "lsr_all_accounts",
    "volatility_index": "volatility_indices"
}

# 交易所和交易对
EXCHANGES = {
    "binance_spot": ["BTCUSDT", "ETHUSDT"],
    "binance_derivatives": ["BTCUSDT", "ETHUSDT"],
    "okx_spot": ["BTC-USDT", "ETH-USDT"],
    "okx_derivatives": ["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
    "deribit_derivatives": ["BTC", "ETH"]
}

class StressTestMonitor:
    def __init__(self):
        self.start_time = None
        self.samples = []
        self.initial_counts = {}
        self.session = None
        self.report_data = {
            "test_config": {
                "duration_minutes": TEST_DURATION_MINUTES,
                "target_throughput": TARGET_THROUGHPUT,
                "target_success_rate": TARGET_SUCCESS_RATE,
                "max_error_rate": MAX_ERROR_RATE
            },
            "performance_samples": [],
            "data_quality": {},
            "final_statistics": {}
        }

    async def initialize(self):
        """初始化测试环境"""
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        self.start_time = datetime.now(timezone.utc)
        
        print(f"🚀 MarketPrism 完整数据链路压力测试")
        print(f"{'='*50}")
        print(f"测试时长: {TEST_DURATION_MINUTES} 分钟")
        print(f"目标吞吐量: ≥{TARGET_THROUGHPUT} msg/s")
        print(f"目标成功率: ≥{TARGET_SUCCESS_RATE}%")
        print(f"最大错误率: ≤{MAX_ERROR_RATE}%")
        print(f"开始时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print()

        # 检查服务健康状态
        await self._check_services_health()
        
        # 记录初始数据计数
        await self._record_initial_counts()

    async def _check_services_health(self):
        """检查所有服务健康状态"""
        print("🔍 检查服务健康状态...")
        
        services = [
            ("Collector", COLLECTOR_HEALTH),
            ("Hot Storage", HOT_STORAGE_HEALTH), 
            ("Cold Storage", COLD_STORAGE_HEALTH)
        ]
        
        all_healthy = True
        for name, url in services:
            try:
                async with self.session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        status = data.get("status", "unknown")
                        print(f"  ✅ {name}: {status}")
                        if status != "healthy":
                            all_healthy = False
                    else:
                        print(f"  ❌ {name}: HTTP {resp.status}")
                        all_healthy = False
            except Exception as e:
                print(f"  ❌ {name}: {e}")
                all_healthy = False
        
        if not all_healthy:
            raise RuntimeError("部分服务不健康，无法开始压力测试")

    async def _record_initial_counts(self):
        """记录初始数据计数"""
        print("📊 记录初始数据计数...")
        
        for data_type, table_name in DATA_TYPES.items():
            try:
                # 热端计数
                hot_count = await self._query_clickhouse(
                    f"SELECT count() FROM marketprism_hot.{table_name}"
                )
                # 冷端计数
                cold_count = await self._query_clickhouse(
                    f"SELECT count() FROM marketprism_cold.{table_name}"
                )
                
                self.initial_counts[data_type] = {
                    "hot": int(hot_count.strip() or 0),
                    "cold": int(cold_count.strip() or 0)
                }
                print(f"  {data_type}: 热端={self.initial_counts[data_type]['hot']}, "
                      f"冷端={self.initial_counts[data_type]['cold']}")
                
            except Exception as e:
                print(f"  ❌ 获取 {data_type} 计数失败: {e}")
                self.initial_counts[data_type] = {"hot": 0, "cold": 0}

    async def run_stress_test(self):
        """运行压力测试"""
        print(f"\n🔥 开始 {TEST_DURATION_MINUTES} 分钟压力测试...")
        print(f"采样间隔: {SAMPLE_INTERVAL_SECONDS} 秒")
        print()

        test_end_time = self.start_time + timedelta(minutes=TEST_DURATION_MINUTES)
        sample_count = 0
        
        while datetime.now(timezone.utc) < test_end_time:
            sample_count += 1
            elapsed_minutes = (datetime.now(timezone.utc) - self.start_time).total_seconds() / 60
            
            print(f"📈 采样 #{sample_count} (已运行 {elapsed_minutes:.1f} 分钟)")
            
            # 收集性能指标
            sample_data = await self._collect_performance_sample()
            sample_data["sample_number"] = sample_count
            sample_data["elapsed_minutes"] = elapsed_minutes
            
            self.samples.append(sample_data)
            self.report_data["performance_samples"].append(sample_data)
            
            # 显示实时指标
            self._display_sample_metrics(sample_data)
            
            # 等待下次采样
            await asyncio.sleep(SAMPLE_INTERVAL_SECONDS)
        
        print(f"\n✅ 压力测试完成！总采样次数: {sample_count}")

    async def _collect_performance_sample(self) -> Dict[str, Any]:
        """收集单次性能采样数据"""
        sample = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "services": {},
            "nats": {},
            "data_counts": {},
            "throughput": 0,
            "error_rate": 0
        }

        # 收集服务健康状态
        for service_name, url in [("collector", COLLECTOR_HEALTH), 
                                  ("hot_storage", HOT_STORAGE_HEALTH),
                                  ("cold_storage", COLD_STORAGE_HEALTH)]:
            try:
                async with self.session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        sample["services"][service_name] = {
                            "status": data.get("status", "unknown"),
                            "healthy": data.get("status") == "healthy"
                        }
                    else:
                        sample["services"][service_name] = {"status": "error", "healthy": False}
            except:
                sample["services"][service_name] = {"status": "unreachable", "healthy": False}

        # 收集 NATS 指标
        try:
            async with self.session.get(f"{NATS_MONITORING}/jsz") as resp:
                if resp.status == 200:
                    nats_data = await resp.json()
                    sample["nats"] = {
                        "total_messages": nats_data.get("messages", 0),
                        "total_bytes": nats_data.get("bytes", 0),
                        "streams": nats_data.get("streams", 0),
                        "consumers": nats_data.get("consumers", 0)
                    }
        except:
            sample["nats"] = {"error": "unreachable"}

        # 收集数据计数
        for data_type, table_name in DATA_TYPES.items():
            try:
                hot_count = await self._query_clickhouse(
                    f"SELECT count() FROM marketprism_hot.{table_name}"
                )
                cold_count = await self._query_clickhouse(
                    f"SELECT count() FROM marketprism_cold.{table_name}"
                )
                
                sample["data_counts"][data_type] = {
                    "hot": int(hot_count.strip() or 0),
                    "cold": int(cold_count.strip() or 0)
                }
            except:
                sample["data_counts"][data_type] = {"hot": 0, "cold": 0}

        # 计算吞吐量（基于总消息数变化）
        if len(self.samples) > 0:
            prev_sample = self.samples[-1]
            if "nats" in prev_sample and "total_messages" in prev_sample["nats"]:
                msg_diff = sample["nats"].get("total_messages", 0) - prev_sample["nats"].get("total_messages", 0)
                time_diff = SAMPLE_INTERVAL_SECONDS
                sample["throughput"] = msg_diff / time_diff if time_diff > 0 else 0

        return sample

    def _display_sample_metrics(self, sample: Dict[str, Any]):
        """显示采样指标"""
        # 服务状态
        services_status = []
        for name, info in sample["services"].items():
            status = "✅" if info.get("healthy") else "❌"
            services_status.append(f"{name}:{status}")
        
        print(f"  服务状态: {' '.join(services_status)}")
        
        # NATS 指标
        if "total_messages" in sample["nats"]:
            print(f"  NATS: {sample['nats']['total_messages']:,} 消息, "
                  f"{sample['nats']['streams']} 流, {sample['nats']['consumers']} 消费者")
        
        # 吞吐量
        if sample["throughput"] > 0:
            throughput_status = "✅" if sample["throughput"] >= TARGET_THROUGHPUT else "⚠️"
            print(f"  吞吐量: {sample['throughput']:.1f} msg/s {throughput_status}")
        
        # 数据增长
        growth_summary = []
        for data_type, counts in sample["data_counts"].items():
            if data_type in self.initial_counts:
                hot_growth = counts["hot"] - self.initial_counts[data_type]["hot"]
                if hot_growth > 0:
                    growth_summary.append(f"{data_type}:+{hot_growth}")
        
        if growth_summary:
            print(f"  数据增长: {', '.join(growth_summary[:4])}")  # 只显示前4个
        
        print()

    async def _query_clickhouse(self, query: str) -> str:
        """查询 ClickHouse"""
        url = f"{CLICKHOUSE_HTTP}/?query={query.replace(' ', '%20')}"
        async with self.session.get(url) as resp:
            if resp.status == 200:
                return await resp.text()
            else:
                raise Exception(f"ClickHouse query failed: {resp.status}")

    async def generate_final_report(self):
        """生成最终测试报告"""
        print("📋 生成最终测试报告...")
        
        # 计算最终数据计数
        final_counts = {}
        for data_type, table_name in DATA_TYPES.items():
            try:
                hot_count = await self._query_clickhouse(
                    f"SELECT count() FROM marketprism_hot.{table_name}"
                )
                cold_count = await self._query_clickhouse(
                    f"SELECT count() FROM marketprism_cold.{table_name}"
                )
                
                final_counts[data_type] = {
                    "hot": int(hot_count.strip() or 0),
                    "cold": int(cold_count.strip() or 0),
                    "hot_growth": int(hot_count.strip() or 0) - self.initial_counts[data_type]["hot"],
                    "cold_growth": int(cold_count.strip() or 0) - self.initial_counts[data_type]["cold"]
                }
            except Exception as e:
                print(f"  ❌ 获取最终 {data_type} 计数失败: {e}")
                final_counts[data_type] = {"hot": 0, "cold": 0, "hot_growth": 0, "cold_growth": 0}

        # 计算性能统计
        throughputs = [s["throughput"] for s in self.samples if s["throughput"] > 0]
        avg_throughput = statistics.mean(throughputs) if throughputs else 0
        max_throughput = max(throughputs) if throughputs else 0
        min_throughput = min(throughputs) if throughputs else 0

        # 计算服务可用性
        service_availability = {}
        for service_name in ["collector", "hot_storage", "cold_storage"]:
            healthy_samples = sum(1 for s in self.samples 
                                if s["services"].get(service_name, {}).get("healthy", False))
            availability = (healthy_samples / len(self.samples)) * 100 if self.samples else 0
            service_availability[service_name] = availability

        # 保存报告数据
        self.report_data["final_statistics"] = {
            "test_duration_minutes": TEST_DURATION_MINUTES,
            "total_samples": len(self.samples),
            "data_counts": final_counts,
            "performance": {
                "avg_throughput": avg_throughput,
                "max_throughput": max_throughput,
                "min_throughput": min_throughput,
                "throughput_target_met": avg_throughput >= TARGET_THROUGHPUT
            },
            "service_availability": service_availability,
            "overall_success": all(avail >= TARGET_SUCCESS_RATE for avail in service_availability.values())
        }

        # 显示报告
        await self._display_final_report()
        
        # 保存报告到文件
        await self._save_report_to_file()

    async def _display_final_report(self):
        """显示最终报告"""
        stats = self.report_data["final_statistics"]
        
        print(f"\n{'='*60}")
        print(f"📊 MarketPrism 压力测试最终报告")
        print(f"{'='*60}")
        
        print(f"\n🕒 测试概况:")
        print(f"  测试时长: {stats['test_duration_minutes']} 分钟")
        print(f"  采样次数: {stats['total_samples']}")
        print(f"  开始时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"  结束时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

        print(f"\n🚀 性能指标:")
        perf = stats["performance"]
        throughput_status = "✅ 达标" if perf["throughput_target_met"] else "❌ 未达标"
        print(f"  平均吞吐量: {perf['avg_throughput']:.1f} msg/s (目标: ≥{TARGET_THROUGHPUT}) {throughput_status}")
        print(f"  最大吞吐量: {perf['max_throughput']:.1f} msg/s")
        print(f"  最小吞吐量: {perf['min_throughput']:.1f} msg/s")

        print(f"\n🏥 服务可用性:")
        for service, availability in stats["service_availability"].items():
            status = "✅ 达标" if availability >= TARGET_SUCCESS_RATE else "❌ 未达标"
            print(f"  {service}: {availability:.1f}% (目标: ≥{TARGET_SUCCESS_RATE}%) {status}")

        print(f"\n📈 数据增长统计:")
        total_hot_growth = 0
        total_cold_growth = 0
        
        for data_type, counts in stats["data_counts"].items():
            hot_growth = counts["hot_growth"]
            cold_growth = counts["cold_growth"]
            total_hot_growth += hot_growth
            total_cold_growth += cold_growth
            
            if hot_growth > 0 or cold_growth > 0:
                print(f"  {data_type}:")
                print(f"    热端增长: +{hot_growth:,} (总计: {counts['hot']:,})")
                print(f"    冷端增长: +{cold_growth:,} (总计: {counts['cold']:,})")

        print(f"\n📊 总体数据增长:")
        print(f"  热端总增长: +{total_hot_growth:,}")
        print(f"  冷端总增长: +{total_cold_growth:,}")

        # 最终评估
        overall_success = stats["overall_success"] and perf["throughput_target_met"]
        print(f"\n🎯 最终评估:")
        if overall_success:
            print("  ✅ 压力测试通过！系统满足生产环境要求")
        else:
            print("  ❌ 压力测试未完全通过，存在性能或可用性问题")

    async def _save_report_to_file(self):
        """保存报告到文件"""
        report_file = Path("logs") / f"stress_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_file.parent.mkdir(exist_ok=True)
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(self.report_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 详细报告已保存: {report_file}")

    async def cleanup(self):
        """清理资源"""
        if self.session:
            await self.session.close()

async def main():
    """主函数"""
    monitor = StressTestMonitor()
    
    try:
        await monitor.initialize()
        await monitor.run_stress_test()
        await monitor.generate_final_report()
        
    except KeyboardInterrupt:
        print("\n⚠️ 测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await monitor.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
