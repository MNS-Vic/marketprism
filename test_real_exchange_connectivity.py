#!/usr/bin/env python3
"""
测试 python-collector 从各交易所获取数据的功能（使用正确的配置）

验证：
1. Binance 数据获取和真实连接
2. OKX 数据获取和真实连接
3. Deribit 数据获取和真实连接
4. 统一工厂功能
5. 使用项目配置文件
"""

import sys
import os
import asyncio
import json
import yaml
from pathlib import Path
from datetime import datetime
import traceback

# 添加项目路径
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root / "services/python-collector/src"))

# 导入必要的模块
try:
    from marketprism_collector.exchanges.factory import get_factory
    from marketprism_collector.exchanges import ExchangeAdapter
    from marketprism_collector.types import ExchangeConfig, Exchange, MarketType, DataType
    print("✅ 成功导入所有必要模块")
except ImportError as e:
    print(f"❌ 导入模块失败: {e}")
    print(f"PYTHONPATH: {os.environ.get('PYTHONPATH')}")
    print(f"sys.path: {sys.path}")
    sys.exit(1)


class ExchangeRealConnectivityTester:
    """交易所真实连接测试器"""
    
    def __init__(self):
        self.factory = get_factory()
        self.project_root = project_root
        self.config_dir = self.project_root / "config"
        
        # 加载主配置
        self.main_config = self.load_main_config()
        
        self.test_results = {
            'timestamp': datetime.now().isoformat(),
            'exchanges': {},
            'summary': {
                'total_exchanges': 0,
                'successful_connections': 0,
                'failed_connections': 0,
                'connection_success_rate': 0.0
            },
            'factory': {},
            'config_loaded': bool(self.main_config)
        }
    
    def load_main_config(self):
        """加载主配置文件"""
        try:
            config_file = self.config_dir / "collector_config.yaml"
            if not config_file.exists():
                # 尝试其他可能的配置文件名
                for alt_name in ["collector.yaml", "config.yaml", "main.yaml"]:
                    alt_file = self.config_dir / alt_name
                    if alt_file.exists():
                        config_file = alt_file
                        break
                else:
                    print(f"⚠️ 找不到主配置文件: {config_file}")
                    return None
            
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                print(f"✅ 成功加载主配置: {config_file}")
                return config
                
        except Exception as e:
            print(f"❌ 加载主配置失败: {e}")
            return None
    
    def load_exchange_config(self, exchange_name: str):
        """加载交易所配置文件"""
        try:
            exchange_config_dir = self.config_dir / "exchanges"
            
            # 根据交易所名称查找配置文件
            config_files = {
                'binance': ['binance_futures.yaml', 'binance.yaml'],
                'okx': ['okx.yaml'],
                'deribit': ['deribit.yaml']
            }
            
            for config_file_name in config_files.get(exchange_name, []):
                config_file = exchange_config_dir / config_file_name
                if config_file.exists():
                    with open(config_file, 'r', encoding='utf-8') as f:
                        config = yaml.safe_load(f)
                        print(f"✅ 成功加载{exchange_name}配置: {config_file}")
                        return config
            
            print(f"⚠️ 找不到{exchange_name}配置文件")
            return None
            
        except Exception as e:
            print(f"❌ 加载{exchange_name}配置失败: {e}")
            return None
    
    def create_exchange_config_from_file(self, exchange_name: str):
        """根据配置文件创建ExchangeConfig对象"""
        try:
            exchange_config = self.load_exchange_config(exchange_name)
            if not exchange_config:
                return None
            
            # 提取配置信息
            api_config = exchange_config.get('api', {})
            ws_url = api_config.get('ws_url')
            base_url = api_config.get('base_url')
            symbols = exchange_config.get('symbols', [])[:2]  # 只取前2个进行测试
            
            # 处理代理配置
            proxy_config = None
            if self.main_config and self.main_config.get('proxy', {}).get('enabled', False):
                proxy_config = self.main_config['proxy']
                print(f"🔄 {exchange_name}使用代理配置: {proxy_config}")
            elif exchange_config.get('proxy', {}).get('enabled', False):
                proxy_config = exchange_config['proxy']
                print(f"🔄 {exchange_name}使用交易所代理配置: {proxy_config}")
            
            # 根据交易所类型创建配置
            if exchange_name == 'binance':
                config = ExchangeConfig.for_binance(
                    market_type=MarketType.FUTURES,
                    symbols=symbols or ['BTCUSDT', 'ETHUSDT'],
                    data_types=[DataType.TRADE, DataType.ORDERBOOK],
                    ping_interval=30,
                    enable_ping=True,
                    reconnect_attempts=2,
                    reconnect_delay=5
                )
                # 覆盖WebSocket URL
                if ws_url:
                    config.ws_url = ws_url
                    
            elif exchange_name == 'okx':
                # OKX使用现货交易对进行测试
                okx_symbols = symbols[:2] if symbols else ['BTC-USDT', 'ETH-USDT']
                config = ExchangeConfig.for_okx(
                    market_type=MarketType.SPOT,
                    symbols=okx_symbols,
                    data_types=[DataType.TRADE, DataType.ORDERBOOK],
                    ping_interval=20,
                    enable_ping=True,
                    reconnect_attempts=2,
                    reconnect_delay=5
                )
                # 覆盖WebSocket URL
                if ws_url:
                    config.ws_url = ws_url
                    
            elif exchange_name == 'deribit':
                config = ExchangeConfig(
                    exchange=Exchange.DERIBIT,
                    market_type=MarketType.OPTIONS,
                    symbols=symbols or ['BTC-PERPETUAL', 'ETH-PERPETUAL'],
                    data_types=[DataType.TRADE, DataType.ORDERBOOK, DataType.TICKER],
                    base_url=base_url or 'https://www.deribit.com',
                    ws_url=ws_url or 'wss://www.deribit.com/ws/api/v2',
                    ping_interval=25,
                    enable_ping=True,
                    reconnect_attempts=2,
                    reconnect_delay=5
                )
            else:
                print(f"❌ 不支持的交易所: {exchange_name}")
                return None
            
            # 添加代理配置
            if proxy_config:
                config.proxy = proxy_config
                
            print(f"📋 {exchange_name}配置创建完成:")
            print(f"   WebSocket URL: {config.ws_url}")
            print(f"   交易对: {config.symbols}")
            print(f"   代理: {'启用' if proxy_config else '禁用'}")
            
            return config
            
        except Exception as e:
            print(f"❌ 创建{exchange_name}配置失败: {e}")
            traceback.print_exc()
            return None
    
    async def test_exchange_connectivity(self, exchange_name: str):
        """测试单个交易所连接"""
        print(f"\\n{'🟡' if exchange_name == 'binance' else '🟠' if exchange_name == 'okx' else '🟣'} 测试 {exchange_name.capitalize()} 真实连接...")
        print("=" * 50)
        
        adapter = None
        live_connected = False
        status = 'failed'
        error_info = None
        traceback_info = None
        
        try:
            # 创建配置
            config = self.create_exchange_config_from_file(exchange_name)
            if not config:
                raise Exception(f"无法创建{exchange_name}配置")
            
            # 创建适配器
            adapter = self.factory.create_adapter(exchange_name, config.to_dict() if hasattr(config, 'to_dict') else None)
            if adapter is None:
                raise Exception(f"无法创建 {exchange_name.capitalize()} 适配器")
            
            print(f"✅ {exchange_name.capitalize()} 适配器创建成功: {type(adapter).__name__}")
            
            # 获取初始状态
            initial_stats = adapter.get_stats() if hasattr(adapter, 'get_stats') else {}
            initial_connected = adapter.is_connected if hasattr(adapter, 'is_connected') else False
            
            print(f"📊 {exchange_name.capitalize()} 初始统计: 连接={initial_connected}, 消息={initial_stats.get('messages_received', 0)}")
            
            # 启动连接
            print(f"🚀 启动 {exchange_name.capitalize()} 适配器连接...")
            if hasattr(adapter, 'start'):
                start_success = await adapter.start()
                if start_success:
                    print(f"⏳ 等待 {exchange_name.capitalize()} 连接建立 (8 秒)...")
                    await asyncio.sleep(8)  # 给更多时间建立连接
                else:
                    print(f"⚠️ {exchange_name.capitalize()} 适配器 start() 返回 False")
            else:
                print(f"⚠️ {exchange_name.capitalize()} 适配器没有 start 方法")
            
            # 检查连接状态
            live_connected = adapter.is_connected if hasattr(adapter, 'is_connected') else False
            live_stats = adapter.get_stats() if hasattr(adapter, 'get_stats') else {}
            
            print(f"🔗 {exchange_name.capitalize()} 实时连接状态: {live_connected}")
            print(f"📈 {exchange_name.capitalize()} 实时统计: 消息={live_stats.get('messages_received', 0)}, 错误={live_stats.get('errors', 0)}")
            
            if live_connected:
                print(f"🎉 {exchange_name.capitalize()} 连接成功！")
                status = 'success'
            else:
                print(f"⚠️ {exchange_name.capitalize()} 未能建立连接")
                status = 'failed_to_connect'
            
        except Exception as e:
            print(f"❌ {exchange_name.capitalize()} 连接测试异常: {e}")
            error_info = str(e)
            traceback_info = traceback.format_exc()
            status = 'failed_exception'
            
        finally:
            # 停止适配器
            if adapter and hasattr(adapter, 'stop'):
                print(f"🛑 停止 {exchange_name.capitalize()} 适配器...")
                try:
                    await adapter.stop()
                    print(f"✅ {exchange_name.capitalize()} 适配器已停止")
                except Exception as e:
                    print(f"⚠️ 停止{exchange_name}适配器时出错: {e}")
            
            # 记录结果
            self.test_results['exchanges'][exchange_name] = {
                'status': status,
                'live_connected': live_connected,
                'config_loaded': config is not None,
                'initial_stats': initial_stats if 'initial_stats' in locals() else {},
                'live_stats': live_stats if 'live_stats' in locals() else {},
                'error': error_info,
                'traceback': traceback_info
            }
        
        return live_connected
    
    async def test_factory_features(self):
        """测试统一工厂功能"""
        print("\\n🏭 测试统一工厂功能...")
        print("=" * 50)
        
        try:
            arch_info = self.factory.get_architecture_info()
            print(f"🏗️ 架构类型: {arch_info['factory_type']}")
            print(f"📋 支持交易所: {arch_info['supported_exchanges']}")
            
            self.test_results['factory'] = {
                'status': 'success',
                'architecture': arch_info
            }
            print("✅ 统一工厂功能测试成功")
            return True
            
        except Exception as e:
            print(f"❌ 统一工厂功能测试失败: {e}")
            self.test_results['factory'] = {
                'status': 'failed',
                'error': str(e)
            }
            return False
    
    async def run_all_tests(self):
        """运行所有测试"""
        print("🚀 开始测试 python-collector 真实交易所连接")
        print("🔧 使用项目配置文件进行测试")
        print("=" * 80)
        
        if not self.main_config:
            print("⚠️ 主配置文件加载失败，可能影响代理设置")
        
        # 测试各交易所连接
        connection_results = []
        exchanges = ['binance', 'okx', 'deribit']
        
        for exchange in exchanges:
            result = await self.test_exchange_connectivity(exchange)
            connection_results.append(result)
            await asyncio.sleep(3)  # 交易所之间的间隔
        
        # 测试工厂
        factory_result = await self.test_factory_features()
        
        # 计算结果
        self.test_results['summary'].update({
            'total_exchanges': len(exchanges),
            'successful_connections': sum(connection_results),
            'failed_connections': len(exchanges) - sum(connection_results),
            'connection_success_rate': (sum(connection_results) / len(exchanges)) * 100 if exchanges else 0
        })
        
        # 显示总结
        print("\\n" + "=" * 80)
        print("📊 真实连接测试结果总结")
        print("=" * 80)
        print(f"💻 测试交易所数: {self.test_results['summary']['total_exchanges']}")
        print(f"✅ 成功连接: {self.test_results['summary']['successful_connections']}")
        print(f"❌ 连接失败: {self.test_results['summary']['failed_connections']}")
        print(f"📈 连接成功率: {self.test_results['summary']['connection_success_rate']:.1f}%")
        
        print("\\n📋 各交易所状态:")
        for exchange, result in self.test_results['exchanges'].items():
            status_icon = "✅" if result.get('live_connected') else "❌"
            config_icon = "📁" if result.get('config_loaded') else "📂"
            print(f"   {status_icon} {config_icon} {exchange.capitalize()}: {result['status']}")
            if result.get('error'):
                print(f"      错误: {result['error']}")
        
        factory_icon = "✅" if self.test_results['factory'].get('status') == 'success' else "❌"
        print(f"   {factory_icon} 🏭 统一工厂: {self.test_results['factory'].get('status')}")
        
        # 保存结果
        result_file = f"real_exchange_connectivity_test_{int(datetime.now().timestamp())}.json"
        try:
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(self.test_results, f, indent=2, ensure_ascii=False)
            print(f"\\n💾 详细结果已保存: {result_file}")
        except Exception as e:
            print(f"\\n⚠️ 保存结果失败: {e}")
        
        # 最终评估
        all_connected = self.test_results['summary']['successful_connections'] == self.test_results['summary']['total_exchanges']
        if all_connected and factory_result:
            print("\\n🎉 所有测试通过！所有交易所均已成功连接！")
        else:
            print("\\n⚠️ 部分测试失败，请查看上面的详细信息")
            if not all_connected:
                print(f"   - {self.test_results['summary']['failed_connections']} 个交易所连接失败")
            if not factory_result:
                print("   - 工厂功能测试失败")
        
        return self.test_results


async def main():
    """主函数"""
    try:
        print("🧪 MarketPrism 真实交易所连接测试")
        print("=" * 80)
        
        tester = ExchangeRealConnectivityTester()
        results = await tester.run_all_tests()
        return results
        
    except Exception as e:
        print(f"❌ 测试主函数失败: {e}")
        traceback.print_exc()
        return {
            'summary': {'successful_connections': 0, 'total_exchanges': 3},
            'factory': {'status': 'failed'},
            'exchanges': {}
        }


if __name__ == "__main__":
    # 设置事件循环策略
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    results = asyncio.run(main())
    
    # 基于连接成功率决定退出码
    all_connected = (
        results and 
        results.get('summary', {}).get('successful_connections', 0) == 
        results.get('summary', {}).get('total_exchanges', 3)
    )
    factory_ok = results and results.get('factory', {}).get('status') == 'success'
    
    exit_code = 0 if all_connected and factory_ok else 1
    sys.exit(exit_code)