#!/usr/bin/env python3
"""
测试 python-collector 从各交易所获取数据的功能

验证：
1. Binance 数据获取和真实连接
2. OKX 数据获取和真实连接
3. Deribit 数据获取和真实连接
4. 统一工厂功能
5. 数据标准化处理
"""

import sys
import os
import asyncio
import json
from pathlib import Path
from datetime import datetime
import traceback

# 添加项目路径
project_root = Path(__file__).resolve().parent.parent # Go up two levels to project root
sys.path.insert(0, str(project_root / "services/python-collector/src"))

# 导入必要的模块
try:
    from marketprism_collector.exchanges.factory import get_factory
    from marketprism_collector.exchanges import ExchangeAdapter # Base class for type hinting
    from marketprism_collector.types import ExchangeConfig, Exchange, MarketType, DataType
    print("✅ 成功导入所有必要模块")
except ImportError as e:
    print(f"❌ 导入模块失败: {e}")
    print(f"PYTHONPATH: {os.environ.get('PYTHONPATH')}")
    print(f"sys.path: {sys.path}")
    sys.exit(1)


class ExchangeDataTester:
    """交易所数据获取测试器"""
    
    def __init__(self):
        self.factory = get_factory()
        self.test_results = {
            'timestamp': datetime.now().isoformat(),
            'exchanges': {},
            'summary': {
                'total_exchanges': 0,
                'successful_connections': 0,
                'failed_connections': 0,
                'connection_success_rate': 0.0
            },
            'factory': {}
        }
    
    async def _test_exchange_connectivity(self, exchange_name: str, adapter_config: ExchangeConfig):
        """通用交易所连接测试逻辑"""
        adapter: ExchangeAdapter = None
        live_connected = False
        status = 'failed' # Default status
        error_info = None
        traceback_info = None

        try:
            adapter = self.factory.create_adapter(exchange_name, adapter_config.to_dict() if hasattr(adapter_config, 'to_dict') else None)
            if adapter is None:
                raise Exception(f"无法创建 {exchange_name.capitalize()} 适配器")
            
            print(f"✅ {exchange_name.capitalize()} 适配器创建成功: {type(adapter).__name__}")

            initial_stats = adapter.get_stats() if hasattr(adapter, 'get_stats') else {}
            print(f"📊 {exchange_name.capitalize()} 初始统计信息: {initial_stats}")
            initial_connected = adapter.is_connected if hasattr(adapter, 'is_connected') else False
            print(f"🔌 {exchange_name.capitalize()} 初始连接状态: {initial_connected}")

            print(f"🚀 尝试启动 {exchange_name.capitalize()} 适配器...")
            if hasattr(adapter, 'start'):
                start_success = await adapter.start()
                if start_success:
                    print(f"⏳ 等待 {exchange_name.capitalize()} 连接建立和订阅 (5 秒)...")
                    await asyncio.sleep(5) 
                else:
                    print(f"⚠️ {exchange_name.capitalize()} 适配器 start() 方法返回 False。")
            else:
                print(f"⚠️ {exchange_name.capitalize()} 适配器没有 start 方法")

            live_connected = adapter.is_connected if hasattr(adapter, 'is_connected') else False
            print(f"🔗 {exchange_name.capitalize()} 实时连接状态: {live_connected}")

            live_stats = adapter.get_stats() if hasattr(adapter, 'get_stats') else {}
            print(f"📈 {exchange_name.capitalize()} 实时统计信息: {live_stats}")
            
            status = 'success' if live_connected else 'failed_to_connect'
            if not live_connected:
                 print(f"⚠️ {exchange_name.capitalize()} 未能成功连接。检查日志以获取更多信息。")

        except Exception as e:
            print(f"❌ {exchange_name.capitalize()} 数据获取或连接测试失败: {e}")
            error_info = str(e)
            traceback_info = traceback.format_exc()
            status = 'failed_exception'
        
        finally:
            if adapter and hasattr(adapter, 'stop'):
                print(f"🛑 尝试停止 {exchange_name.capitalize()} 适配器...")
                await adapter.stop()
                print(f"✅ {exchange_name.capitalize()} 适配器已停止")

            self.test_results['exchanges'][exchange_name] = {
                'status': status,
                'adapter_type': type(adapter).__name__ if adapter else 'N/A',
                'initial_connected': initial_connected if 'initial_connected' in locals() else False,
                'live_connected': live_connected,
                'initial_stats': initial_stats if 'initial_stats' in locals() else {},
                'live_stats': live_stats if 'live_stats' in locals() else {},
                'features': { # Keep feature check based on adapter presence
                    'has_stats': hasattr(adapter, 'get_stats') if adapter else False,
                    'has_enhanced_stats': hasattr(adapter, 'get_enhanced_stats') if adapter else False,
                    'has_ping_pong': hasattr(adapter, '_send_exchange_ping') if adapter else False,
                    'has_connection_check': hasattr(adapter, 'is_connected') if adapter else False
                },
                'config': {
                    'symbols': adapter_config.symbols,
                    'data_types': [dt.value for dt in adapter_config.data_types],
                    'ping_interval': getattr(adapter_config, 'ping_interval', None)
                },
                'error': error_info,
                'traceback': traceback_info
            }
        return live_connected

    async def test_binance_data(self):
        """测试 Binance 数据获取和真实连接"""
        print("\\n🟡 测试 Binance 数据获取和真实连接...")
        print("=" * 50)
        config = ExchangeConfig.for_binance(
            market_type=MarketType.FUTURES,
            symbols=['BTCUSDT', 'ETHUSDT'], 
            data_types=[DataType.TRADE, DataType.ORDERBOOK],
            ping_interval=30, 
            enable_ping=True,
            reconnect_attempts=1, # For faster test failure if needed
            reconnect_delay=2
        )
        return await self._test_exchange_connectivity('binance', config)
    
    async def test_okx_data(self):
        """测试 OKX 数据获取和真实连接"""
        print("\\n🟠 测试 OKX 数据获取和真实连接...")
        print("=" * 50)
        config = ExchangeConfig.for_okx(
            market_type=MarketType.FUTURES, # or MarketType.SWAP for perpetuals
            symbols=['BTC-USDT-SWAP', 'ETH-USDT-SWAP'], 
            data_types=[DataType.TRADE, DataType.ORDERBOOK],
            ping_interval=20,
            enable_ping=True,
            reconnect_attempts=1,
            reconnect_delay=2
        )
        # Note: OKX might require API Key for certain (even public) channels or has stricter rate limits.
        return await self._test_exchange_connectivity('okx', config)
    
    async def test_deribit_data(self):
        """测试 Deribit 数据获取和真实连接"""
        print("\\n🟣 测试 Deribit 数据获取和真实连接...")
        print("=" * 50)
        config = ExchangeConfig(
            exchange=Exchange.DERIBIT,
            market_type=MarketType.OPTIONS, 
            symbols=['BTC-PERPETUAL', 'ETH-PERPETUAL'], 
            data_types=[DataType.TRADE, DataType.ORDERBOOK, DataType.TICKER],
            base_url='https://www.deribit.com', 
            ws_url='wss://www.deribit.com/ws/api/v2',
            ping_interval=25,
            enable_ping=True,
            reconnect_attempts=1,
            reconnect_delay=2
        )
        return await self._test_exchange_connectivity('deribit', config)
    
    async def test_factory_features(self):
        """测试统一工厂功能"""
        print("\\n🏭 测试统一工厂功能...")
        print("=" * 50)
        factory_ok = False
        try:
            arch_info = self.factory.get_architecture_info()
            print(f"🏗️ 架构类型: {arch_info['factory_type']}")
            print(f"📋 支持交易所: {arch_info['supported_exchanges']}")
            print(f"🔧 功能特性: {arch_info.get('management_features', {})}")
            
            if hasattr(self.factory, 'get_adapter_capabilities'):
                binance_caps = self.factory.get_adapter_capabilities('binance')
                print(f"⚡ Binance 能力: {len(binance_caps)} 项")
            
            self.test_results['factory'] = {
                'status': 'success',
                'architecture': arch_info,
            }
            factory_ok = True
            print("✅ 统一工厂功能测试成功")
            
        except Exception as e:
            print(f"❌ 统一工厂功能测试失败: {e}")
            self.test_results['factory'] = {
                'status': 'failed',
                'error': str(e),
                'traceback': traceback.format_exc()
            }
        return factory_ok
    
    async def run_all_tests(self):
        """运行所有测试"""
        print("🚀 开始测试 python-collector 真实交易所连接功能")
        print("=" * 80)
        
        connection_results = []
        
        connection_results.append(await self.test_binance_data())
        await asyncio.sleep(2) 
        connection_results.append(await self.test_okx_data())
        await asyncio.sleep(2)
        connection_results.append(await self.test_deribit_data())
        
        factory_result = await self.test_factory_features()
        
        self.test_results['summary']['total_exchanges'] = len(connection_results)
        self.test_results['summary']['successful_connections'] = sum(bool(r) for r in connection_results)
        self.test_results['summary']['failed_connections'] = len(connection_results) - sum(bool(r) for r in connection_results)
        if len(connection_results) > 0:
            self.test_results['summary']['connection_success_rate'] = \
                (self.test_results['summary']['successful_connections'] / len(connection_results)) * 100
        else:
            self.test_results['summary']['connection_success_rate'] = 0.0

        print("\\n" + "=" * 80)
        print("📊 测试结果总结")
        print("=" * 80)
        print(f"💻 总交易所数量: {self.test_results['summary']['total_exchanges']}")
        print(f"✅ 成功连接: {self.test_results['summary']['successful_connections']}")
        print(f"❌ 连接失败: {self.test_results['summary']['failed_connections']}")
        print(f"📈 连接成功率: {self.test_results['summary']['connection_success_rate']:.1f}%")
        
        print(f"\\n📋 各交易所状态:")
        for exchange, result in self.test_results['exchanges'].items():
            status_icon = "✅" if result.get('live_connected') else ("⚠️" if result['status'] == 'failed_to_connect' else "❌")
            connection_status_msg = f"实时连接: {'成功' if result.get('live_connected') else '失败'}"
            print(f"   {status_icon} {exchange.capitalize()}: {result['status']} ({connection_status_msg})")
            if result['status'] not in ['success', 'failed_to_connect'] or not result.get('live_connected'):
                 print(f"     详情: {result.get('error', 'N/A')}")

        factory_status_icon = "✅" if self.test_results.get('factory', {}).get('status') == 'success' else "❌"
        print(f"   {factory_status_icon} 统一工厂: {self.test_results.get('factory', {}).get('status', 'unknown')}")
        
        result_file = f"exchange_connectivity_test_results_{int(datetime.now().timestamp())}.json"
        try:
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(self.test_results, f, indent=2, ensure_ascii=False)
            print(f"\\n💾 详细测试结果已保存到: {result_file}")
        except Exception as e:
            print(f"\\n⚠️无法保存测试结果到文件 {result_file}: {e}")
        
        if self.test_results['summary']['connection_success_rate'] == 100.0 and factory_result:
            print(f"\\n🎉 所有交易所均已成功连接！工厂测试通过！")
        else:
            print(f"\\n⚠️ 部分测试失败。请检查日志和上面的输出。")
            if not factory_result:
                print("   - 工厂功能测试失败。")
            if self.test_results['summary']['successful_connections'] < self.test_results['summary']['total_exchanges']:
                 print(f"   - {self.test_results['summary']['failed_connections']} 个交易所未能成功连接。")
        
        return self.test_results


async def main():
    """主函数"""
    try:
        tester = ExchangeDataTester()
        results = await tester.run_all_tests()
        return results
    except Exception as e:
        print(f"❌ 测试脚本主函数运行失败: {e}")
        traceback.print_exc()
        # Create a minimal results dict for consistent exit code handling
        return {
            'summary': {'successful_connections': 0, 'total_exchanges': 3},
            'factory': {'status': 'failed_exception'},
            'exchanges': {} # Ensure exchanges key exists
        }


if __name__ == "__main__":
    # Ensure asyncio event loop is properly managed, especially on Windows
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    results = asyncio.run(main())
    
    if results:
        all_exchanges_connected = results['summary']['successful_connections'] == results['summary']['total_exchanges']
        factory_ok = results.get('factory', {}).get('status') == 'success'
        # Ensure total_exchanges is not zero to avoid division by zero if main fails early
        if results['summary']['total_exchanges'] == 0 and results['summary']['successful_connections'] == 0:
             all_exchanges_connected = False # If no exchanges were tested, count as failure

        exit_code = 0 if all_exchanges_connected and factory_ok else 1
        sys.exit(exit_code)
    else:
        # Should not happen if main returns a minimal dict on error, but as a fallback
        sys.exit(1)

