#!/usr/bin/env python3
"""
市场多空仓人数比收集器使用示例

演示如何使用MarketLongShortDataCollector收集币安和OKX的
整个市场多空仓人数比数据
"""

import asyncio
import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "services" / "python-collector" / "src"))

import structlog
from marketprism_collector.market_long_short_collector import MarketLongShortDataCollector
from marketprism_collector.rest_client import RestClientManager
from marketprism_collector.data_types import NormalizedMarketLongShortRatio


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


class MarketLongShortExample:
    """市场多空仓人数比收集器使用示例"""
    
    def __init__(self):
        self.rest_client_manager = RestClientManager()
        self.collector = MarketLongShortDataCollector(self.rest_client_manager)
        self.collected_data = []
        self._clients_setup = False
    
    async def _ensure_clients_setup(self):
        """确保客户端已设置（只设置一次）"""
        if not self._clients_setup:
            await self.collector._setup_exchange_clients()
            self._clients_setup = True
    
    async def example_1_basic_usage(self):
        """示例1: 基础使用方法"""
        print("\n" + "=" * 60)
        print("示例1: 基础使用方法")
        print("=" * 60)
        
        try:
            # 注册数据回调函数
            self.collector.register_callback(self._handle_data)
            
            # 启动收集器（监控指定交易对）
            symbols = ["BTC-USDT", "ETH-USDT"]
            await self.collector.start(symbols=symbols)
            
            print("收集器已启动，将每5分钟收集一次数据...")
            print("等待30秒以观察数据收集...")
            
            # 等待30秒观察数据收集
            await asyncio.sleep(30)
            
            # 停止收集器
            await self.collector.stop()
            
            print(f"收集完成，共收集到 {len(self.collected_data)} 条数据")
            
        except Exception as e:
            logger.error("示例1执行失败", error=str(e))
    
    async def example_2_manual_collection(self):
        """示例2: 手动触发数据收集"""
        print("\n" + "=" * 60)
        print("示例2: 手动触发数据收集")
        print("=" * 60)
        
        try:
            # 确保客户端已设置
            await self._ensure_clients_setup()
            
            # 手动收集一次数据
            results = await self.collector.collect_once()
            
            print(f"手动收集完成，获得 {len(results)} 条数据:")
            
            for i, data in enumerate(results, 1):
                print(f"\n数据 {i}:")
                print(f"  交易所: {data.exchange_name}")
                print(f"  交易对: {data.symbol_name}")
                print(f"  多空人数比值: {data.long_short_ratio}")
                print(f"  多仓账户比例: {data.long_account_ratio:.4f}")
                print(f"  空仓账户比例: {data.short_account_ratio:.4f}")
                print(f"  数据时间: {data.timestamp}")
            
        except Exception as e:
            logger.error("示例2执行失败", error=str(e))
    
    async def example_3_specific_exchange(self):
        """示例3: 收集特定交易所数据"""
        print("\n" + "=" * 60)
        print("示例3: 收集特定交易所数据")
        print("=" * 60)
        
        try:
            # 确保客户端已设置
            await self._ensure_clients_setup()
            
            # 收集Binance数据
            print("收集Binance BTC-USDT数据...")
            binance_data = await self.collector._collect_exchange_symbol_data("binance", "BTC-USDT")
            
            if binance_data:
                print("Binance数据:")
                print(f"  多空人数比值: {binance_data.long_short_ratio}")
                print(f"  多仓账户比例: {binance_data.long_account_ratio:.4f}")
                print(f"  空仓账户比例: {binance_data.short_account_ratio:.4f}")
                print(f"  数据类型: {binance_data.data_type}")
                print(f"  合约类型: {binance_data.instrument_type}")
            else:
                print("Binance数据收集失败")
            
            # 收集OKX数据
            print("\n收集OKX BTC-USDT数据...")
            okx_data = await self.collector._collect_exchange_symbol_data("okx", "BTC-USDT")
            
            if okx_data:
                print("OKX数据:")
                print(f"  多空人数比值: {okx_data.long_short_ratio}")
                print(f"  多仓账户比例: {okx_data.long_account_ratio:.4f}")
                print(f"  空仓账户比例: {okx_data.short_account_ratio:.4f}")
                print(f"  数据类型: {okx_data.data_type}")
                print(f"  合约类型: {okx_data.instrument_type}")
            else:
                print("OKX数据收集失败")
            
        except Exception as e:
            logger.error("示例3执行失败", error=str(e))
    
    async def example_4_data_analysis(self):
        """示例4: 数据分析示例"""
        print("\n" + "=" * 60)
        print("示例4: 数据分析示例")
        print("=" * 60)
        
        try:
            # 确保客户端已设置
            await self._ensure_clients_setup()
            
            # 收集多个交易对的数据
            symbols = ["BTC-USDT", "ETH-USDT"]  # 只收集BTC和ETH
            all_data = []
            
            for symbol in symbols:
                for exchange in ["binance", "okx"]:
                    data = await self.collector._collect_exchange_symbol_data(exchange, symbol)
                    if data:
                        all_data.append(data)
            
            if all_data:
                print(f"收集到 {len(all_data)} 条数据，进行分析:")
                
                # 按交易所分组分析
                binance_data = [d for d in all_data if d.exchange_name == "binance"]
                okx_data = [d for d in all_data if d.exchange_name == "okx"]
                
                print(f"\nBinance数据 ({len(binance_data)} 条):")
                if binance_data:
                    avg_ratio = sum(float(d.long_short_ratio) for d in binance_data) / len(binance_data)
                    avg_long = sum(float(d.long_account_ratio) for d in binance_data) / len(binance_data)
                    print(f"  平均多空人数比值: {avg_ratio:.4f}")
                    print(f"  平均多仓账户比例: {avg_long:.4f}")
                
                print(f"\nOKX数据 ({len(okx_data)} 条):")
                if okx_data:
                    avg_ratio = sum(float(d.long_short_ratio) for d in okx_data) / len(okx_data)
                    avg_long = sum(float(d.long_account_ratio) for d in okx_data) / len(okx_data)
                    print(f"  平均多空人数比值: {avg_ratio:.4f}")
                    print(f"  平均多仓账户比例: {avg_long:.4f}")
                
                # 按交易对分析
                print(f"\n按交易对分析:")
                for symbol in symbols:
                    symbol_data = [d for d in all_data if d.symbol_name == symbol]
                    if symbol_data:
                        avg_ratio = sum(float(d.long_short_ratio) for d in symbol_data) / len(symbol_data)
                        print(f"  {symbol}: 平均多空人数比值 {avg_ratio:.4f}")
            
        except Exception as e:
            logger.error("示例4执行失败", error=str(e))
    
    async def example_5_statistics(self):
        """示例5: 获取统计信息"""
        print("\n" + "=" * 60)
        print("示例5: 获取统计信息")
        print("=" * 60)
        
        try:
            # 确保客户端已设置
            await self._ensure_clients_setup()
            
            # 执行一次收集
            await self.collector.collect_once()
            
            # 获取统计信息
            stats = self.collector.get_stats()
            
            print("收集器统计信息:")
            print(f"  运行状态: {'运行中' if stats['is_running'] else '已停止'}")
            print(f"  监控交易对: {', '.join(stats['symbols'])}")
            print(f"  收集间隔: {stats['collection_interval']} 秒")
            print(f"  总收集次数: {stats['total_collections']}")
            print(f"  成功收集次数: {stats['successful_collections']}")
            print(f"  失败收集次数: {stats['failed_collections']}")
            print(f"  成功率: {stats['success_rate']:.1f}%")
            print(f"  数据点收集数: {stats['data_points_collected']}")
            
            # REST客户端统计
            rest_stats = stats['rest_clients']
            print(f"\nREST客户端统计:")
            for client_name, client_stats in rest_stats.items():
                print(f"  {client_name}:")
                print(f"    总请求数: {client_stats['total_requests']}")
                print(f"    成功率: {client_stats['success_rate']}%")
                print(f"    平均响应时间: {client_stats['average_response_time']}s")
            
        except Exception as e:
            logger.error("示例5执行失败", error=str(e))
    
    def _handle_data(self, data: NormalizedMarketLongShortRatio):
        """数据处理回调函数"""
        self.collected_data.append(data)
        print(f"收到数据: {data.exchange_name} {data.symbol_name} 多空比={data.long_short_ratio}")
    
    async def cleanup(self):
        """清理资源"""
        try:
            await self.collector.stop()
            await self.rest_client_manager.stop_all()
        except Exception as e:
            logger.error("清理资源失败", error=str(e))


async def main():
    """主函数"""
    print("市场多空仓人数比收集器使用示例")
    print("=" * 60)
    
    # 设置代理（如果需要）
    if not os.getenv('https_proxy'):
        os.environ['https_proxy'] = 'http://127.0.0.1:1087'
        os.environ['http_proxy'] = 'http://127.0.0.1:1087'
    
    example = MarketLongShortExample()
    
    try:
        # 运行所有示例
        await example.example_2_manual_collection()
        await example.example_3_specific_exchange()
        await example.example_4_data_analysis()
        await example.example_5_statistics()
        
        print("\n" + "=" * 60)
        print("所有示例执行完成！")
        print("=" * 60)
        
    except Exception as e:
        logger.error("示例执行失败", error=str(e))
    
    finally:
        await example.cleanup()


if __name__ == "__main__":
    asyncio.run(main())