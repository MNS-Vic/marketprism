#!/usr/bin/env python3
"""
大户持仓比数据收集器使用示例

展示如何使用统一的REST API模块收集币安和OKX的大户持仓比数据
"""

import asyncio
import sys
import os
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../services/python-collector/src'))

from marketprism_collector.rest_client import RestClientManager
from marketprism_collector.top_trader_collector import TopTraderDataCollector


async def main():
    """主函数"""
    print("=== MarketPrism 大户持仓比数据收集器示例 ===")
    print()
    
    # 创建REST客户端管理器
    rest_manager = RestClientManager()
    
    try:
        # 创建大户持仓比数据收集器
        print("1. 创建大户持仓比数据收集器...")
        collector = TopTraderDataCollector(rest_manager)
        
        # 注册数据回调函数
        collected_data = []
        
        def data_callback(data):
            """数据回调函数"""
            collected_data.append(data)
            print(f"📊 收到数据: {data.exchange_name} {data.symbol_name}")
            print(f"   多空比: {data.long_short_ratio}")
            print(f"   多头比例: {data.long_position_ratio:.2%}")
            print(f"   空头比例: {data.short_position_ratio:.2%}")
            print(f"   时间: {data.timestamp}")
            print()
        
        collector.register_callback(data_callback)
        print("✅ 数据回调函数已注册")
        print()
        
        # 设置要监控的交易对
        symbols = ["BTC-USDT", "ETH-USDT"]
        print(f"2. 设置监控交易对: {symbols}")
        print()
        
        # 手动收集一次数据
        print("3. 开始手动收集数据...")
        print("   正在从币安和OKX获取大户持仓比数据...")
        
        results = await collector.collect_once()
        
        print(f"✅ 数据收集完成，共收集到 {len(results)} 条数据")
        print()
        
        # 显示收集到的数据
        if results:
            print("4. 收集到的数据详情:")
            print("-" * 60)
            
            for i, result in enumerate(results, 1):
                print(f"数据 {i}:")
                print(f"  交易所: {result.exchange_name}")
                print(f"  交易对: {result.symbol_name}")
                print(f"  多空比: {result.long_short_ratio}")
                print(f"  多头比例: {result.long_position_ratio:.2%}")
                print(f"  空头比例: {result.short_position_ratio:.2%}")
                print(f"  数据类型: {result.data_type}")
                print(f"  统计周期: {result.period}")
                print(f"  合约类型: {result.instrument_type}")
                print(f"  时间戳: {result.timestamp}")
                print(f"  原始数据: {result.raw_data}")
                print()
        else:
            print("⚠️  没有收集到数据，可能是网络问题或API限制")
            print()
        
        # 显示统计信息
        print("5. 收集器统计信息:")
        print("-" * 60)
        stats = collector.get_stats()
        
        print(f"运行状态: {'运行中' if stats['is_running'] else '已停止'}")
        print(f"监控交易对: {stats['symbols']}")
        print(f"收集间隔: {stats['collection_interval']} 秒")
        print(f"总收集次数: {stats['total_collections']}")
        print(f"成功收集次数: {stats['successful_collections']}")
        print(f"失败收集次数: {stats['failed_collections']}")
        print(f"成功率: {stats['success_rate']:.1f}%")
        print(f"数据点总数: {stats['data_points_collected']}")
        print(f"最后收集时间: {stats['last_collection_time']}")
        print()
        
        # 显示REST客户端统计
        print("6. REST客户端统计信息:")
        print("-" * 60)
        rest_stats = rest_manager.get_all_stats()
        
        for client_name, client_stats in rest_stats.items():
            print(f"客户端: {client_name}")
            print(f"  基础URL: {client_stats['base_url']}")
            print(f"  运行状态: {'运行中' if client_stats['is_started'] else '已停止'}")
            print(f"  总请求数: {client_stats['total_requests']}")
            print(f"  成功请求数: {client_stats['successful_requests']}")
            print(f"  失败请求数: {client_stats['failed_requests']}")
            print(f"  成功率: {client_stats['success_rate']}%")
            print(f"  平均响应时间: {client_stats['average_response_time']} 秒")
            print(f"  限流命中次数: {client_stats['rate_limit_hits']}")
            print(f"  最后请求时间: {client_stats['last_request_time']}")
            print()
        
        # 演示定时收集（可选）
        print("7. 演示定时收集功能（按 Ctrl+C 停止）:")
        print("-" * 60)
        
        try:
            # 启动定时收集
            await collector.start(symbols)
            
            # 等待一段时间观察定时收集
            print("⏰ 定时收集已启动，每5分钟收集一次数据...")
            print("   等待30秒观察定时收集效果...")
            
            await asyncio.sleep(30)
            
        except KeyboardInterrupt:
            print("\n⏹️  收到停止信号")
        
        finally:
            # 停止收集器
            await collector.stop()
            print("✅ 收集器已停止")
    
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 清理资源
        await rest_manager.stop_all()
        print("✅ 资源清理完成")
    
    print()
    print("=== 示例程序结束 ===")


if __name__ == "__main__":
    print("启动大户持仓比数据收集器示例...")
    print("注意：需要网络连接才能获取实时数据")
    print()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程序被用户中断")
    except Exception as e:
        print(f"程序异常退出: {e}")
        import traceback
        traceback.print_exc() 