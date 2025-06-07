"""
MarketPrism API代理使用示例

展示如何优雅地集成统一API代理到现有代码中
处理429/418等超限响应，实现智能IP管理
"""

import asyncio
import json
from datetime import datetime
from core.networking.exchange_api_proxy import ExchangeAPIProxy, proxy_request
from core.networking.proxy_adapter import use_api_proxy, get_proxy_session, enable_global_proxy


async def example_1_simple_usage():
    """示例1: 最简单的使用方式"""
    print("📡 示例1: 最简单的使用方式")
    print("-" * 30)
    
    try:
        # 一行代码发送请求，自动处理速率限制
        result = await proxy_request("binance", "GET", "/api/v3/ping")
        print(f"✅ Binance ping: {result}")
        
        # 获取行情数据
        ticker = await proxy_request("binance", "GET", "/api/v3/ticker/24hr", {"symbol": "BTCUSDT"})
        print(f"✅ BTC价格: {ticker.get('lastPrice', 'N/A')} USDT")
        
    except Exception as e:
        print(f"❌ 请求失败: {e}")


async def example_2_decorator_integration():
    """示例2: 装饰器集成到现有函数"""
    print("\n📡 示例2: 装饰器集成")
    print("-" * 30)
    
    @use_api_proxy("binance")
    async def get_account_info(session):
        """获取账户信息（现有代码无需修改）"""
        async with session.get("/api/v3/account") as response:
            return await response.json()
    
    @use_api_proxy("okx")
    async def get_okx_time(session):
        """获取OKX时间"""
        async with session.get("/api/v5/public/time") as response:
            return await response.json()
    
    try:
        # 直接调用，代理会自动处理
        # account = await get_account_info()
        # print(f"✅ 账户信息: {account}")
        
        okx_time = await get_okx_time()
        print(f"✅ OKX时间: {okx_time}")
        
    except Exception as e:
        print(f"❌ 装饰器测试失败: {e}")


async def example_3_advanced_proxy():
    """示例3: 高级代理配置"""
    print("\n📡 示例3: 高级代理配置")
    print("-" * 30)
    
    # 创建分布式代理（多IP环境）
    proxy = ExchangeAPIProxy.distributed_mode([
        "192.168.1.100",  # 服务器1
        "192.168.1.101",  # 服务器2  
        "192.168.1.102"   # 服务器3
    ])
    
    try:
        # 并发请求，自动分配到最佳IP
        tasks = [
            proxy.request("binance", "GET", "/api/v3/ticker/price", {"symbol": "BTCUSDT"}),
            proxy.request("binance", "GET", "/api/v3/ticker/price", {"symbol": "ETHUSDT"}),
            proxy.request("binance", "GET", "/api/v3/ticker/price", {"symbol": "BNBUSDT"}),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"❌ 请求{i+1}失败: {result}")
            else:
                symbol = result.get('symbol', 'Unknown')
                price = result.get('price', 'N/A')
                print(f"✅ {symbol}: {price} USDT")
        
        # 显示代理状态
        status = proxy.get_status()
        print(f"\n📊 代理状态:")
        print(f"  模式: {status['mode']}")
        print(f"  可用IP: {status['available_ips']}/{status['total_ips']}")
        print(f"  成功率: {status['recent_success_rate']}")
        print(f"  总权重消耗: {status['total_weight_consumed']}")
        
    except Exception as e:
        print(f"❌ 高级代理测试失败: {e}")


async def example_4_error_handling():
    """示例4: 超限错误处理演示"""
    print("\n📡 示例4: 超限错误处理")
    print("-" * 30)
    
    proxy = ExchangeAPIProxy.auto_configure()
    
    try:
        # 模拟高频请求触发限制
        print("🔥 发送高频请求测试速率限制...")
        
        for i in range(5):
            try:
                result = await proxy.request("binance", "GET", "/api/v3/ping")
                print(f"✅ 请求{i+1}成功")
                
            except Exception as e:
                if "429" in str(e):
                    print(f"⚠️ 请求{i+1}遇到速率限制: {e}")
                    print("⏳ 代理将自动等待并重试...")
                elif "418" in str(e):
                    print(f"🚫 请求{i+1}IP被封禁: {e}")
                    print("🔄 代理将尝试切换IP...")
                else:
                    print(f"❌ 请求{i+1}其他错误: {e}")
            
            await asyncio.sleep(0.1)  # 短间隔触发限制
        
        # 显示健康报告
        health = proxy.get_health_report()
        print(f"\n🏥 健康报告:")
        print(f"  整体健康: {health['overall_health']}")
        print(f"  平均响应时间: {health['performance']['average_response_time']}")
        print(f"  建议: {health['recommendations'][0] if health['recommendations'] else '无'}")
        
    except Exception as e:
        print(f"❌ 错误处理测试失败: {e}")


async def example_5_global_proxy():
    """示例5: 全局代理模式（零侵入）"""
    print("\n📡 示例5: 全局代理模式")
    print("-" * 30)
    
    # 启用全局代理
    enable_global_proxy()
    
    try:
        # 现有代码完全不用修改！
        import aiohttp
        
        async with aiohttp.ClientSession(base_url="https://api.binance.com") as session:
            # 这些请求会自动通过代理处理
            async with session.get("/api/v3/ping") as response:
                ping_result = await response.json()
                print(f"✅ 全局代理ping: {ping_result}")
            
            async with session.get("/api/v3/time") as response:
                time_result = await response.json()
                server_time = datetime.fromtimestamp(time_result['serverTime'] / 1000)
                print(f"✅ 服务器时间: {server_time}")
        
    except Exception as e:
        print(f"❌ 全局代理测试失败: {e}")
    
    finally:
        # 禁用全局代理
        from core.networking.proxy_adapter import disable_global_proxy
        disable_global_proxy()


async def example_6_integration_with_existing_collector():
    """示例6: 与现有收集器集成"""
    print("\n📡 示例6: 与现有收集器集成")
    print("-" * 30)
    
    # 模拟现有的数据收集器代码
    class MockDataCollector:
        def __init__(self):
            self.proxy_session = get_proxy_session("binance")
        
        async def collect_ticker_data(self, symbols):
            """收集行情数据"""
            results = []
            
            for symbol in symbols:
                try:
                    async with self.proxy_session.get(f"/api/v3/ticker/24hr?symbol={symbol}") as response:
                        data = await response.json()
                        results.append({
                            'symbol': data.get('symbol'),
                            'price': data.get('lastPrice'),
                            'change': data.get('priceChangePercent'),
                            'volume': data.get('volume')
                        })
                        
                except Exception as e:
                    print(f"❌ 收集{symbol}数据失败: {e}")
                    results.append({'symbol': symbol, 'error': str(e)})
            
            return results
        
        async def cleanup(self):
            await self.proxy_session.close()
    
    # 使用收集器
    collector = MockDataCollector()
    
    try:
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        ticker_data = await collector.collect_ticker_data(symbols)
        
        print(f"📊 收集到{len(ticker_data)}个交易对数据:")
        for data in ticker_data:
            if 'error' not in data:
                print(f"  {data['symbol']}: {data['price']} USDT ({data['change']}%)")
            else:
                print(f"  {data['symbol']}: 错误 - {data['error']}")
        
    finally:
        await collector.cleanup()


async def main():
    """主函数：运行所有示例"""
    print("🚀 MarketPrism API代理使用示例")
    print("=" * 50)
    print("演示如何优雅地处理交易所API速率限制和IP管理")
    print()
    
    # 运行所有示例
    await example_1_simple_usage()
    await example_2_decorator_integration()
    await example_3_advanced_proxy()
    await example_4_error_handling()
    await example_5_global_proxy()
    await example_6_integration_with_existing_collector()
    
    print("\n🎉 所有示例演示完成！")
    print("\n💡 关键特性总结:")
    print("  ✅ 统一收口所有API请求")
    print("  ✅ 自动处理429/418超限响应") 
    print("  ✅ 智能IP资源管理和切换")
    print("  ✅ 动态权重计算和限制")
    print("  ✅ 零侵入集成到现有代码")
    print("  ✅ 实时监控和健康报告")


if __name__ == "__main__":
    # 运行示例
    asyncio.run(main())