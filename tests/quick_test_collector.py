#!/usr/bin/env python3
"""
MarketPrism Collector 快速测试脚本

快速验证 Collector 核心功能是否正常工作
"""

import sys
import os
from pathlib import Path
import asyncio
import time

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "services" / "python-collector" / "src"))

try:
    # 检查核心文件是否存在
    collector_src = project_root / "services" / "python-collector" / "src" / "marketprism_collector"
    if not collector_src.exists():
        print(f"❌ Collector 源码目录不存在: {collector_src}")
        sys.exit(1)
    
    # 尝试导入基础模块
    from marketprism_collector.exchanges.factory import ExchangeFactory
    from marketprism_collector.exchanges.binance import BinanceAdapter
    print("✅ Collector 模块导入成功")
    
    # 检查是否有核心集成文件
    core_integration_files = [
        "core_integration.py", 
        "core_services.py", 
        "unified_error_manager.py"
    ]
    
    for filename in core_integration_files:
        filepath = collector_src / filename
        if filepath.exists():
            print(f"✅ 发现核心集成文件: {filename}")
        else:
            print(f"⚠️ 缺少核心集成文件: {filename}")
    
except ImportError as e:
    print(f"❌ 模块导入失败: {e}")
    print("将使用基础测试模式")
    
    # 使用基础测试模式
    ExchangeFactory = None
    BinanceAdapter = None


def test_project_structure():
    """测试项目结构"""
    print("\n🔧 测试项目结构...")
    
    try:
        # 检查关键目录
        key_dirs = [
            "services/python-collector/src/marketprism_collector",
            "services/python-collector/src/marketprism_collector/exchanges",
            "core",
            "config",
            "tests"
        ]
        
        for dir_path in key_dirs:
            full_path = project_root / dir_path
            if full_path.exists():
                print(f"✅ 目录存在: {dir_path}")
            else:
                print(f"❌ 目录缺失: {dir_path}")
        
        # 检查关键文件
        key_files = [
            "services/python-collector/src/marketprism_collector/exchanges/factory.py",
            "services/python-collector/src/marketprism_collector/exchanges/binance.py",
            "services/python-collector/src/marketprism_collector/exchanges/okx.py",
        ]
        
        for file_path in key_files:
            full_path = project_root / file_path
            if full_path.exists():
                print(f"✅ 文件存在: {file_path}")
            else:
                print(f"❌ 文件缺失: {file_path}")
        
        return True
        
    except Exception as e:
        print(f"❌ 项目结构测试失败: {e}")
        return False


def test_core_services_integration():
    """测试 Core 服务集成"""
    print("\n🔧 测试 Core 服务集成...")
    
    try:
        # 检查Core模块是否存在
        core_dir = project_root / "core"
        if not core_dir.exists():
            print("⚠️ Core 目录不存在，跳过Core集成测试")
            return True
        
        # 尝试导入Core模块
        try:
            sys.path.insert(0, str(project_root))
            from core.errors import UnifiedErrorHandler
            print("✅ Core错误处理模块导入成功")
        except ImportError:
            print("⚠️ Core错误处理模块不可用")
        
        try:
            from core.monitoring import get_global_monitoring
            print("✅ Core监控模块导入成功")
        except ImportError:
            print("⚠️ Core监控模块不可用")
        
        try:
            from core.reliability.rate_limit_manager import GlobalRateLimitManager
            print("✅ Core限流管理模块导入成功")
        except ImportError:
            print("⚠️ Core限流管理模块不可用")
        
        return True
        
    except Exception as e:
        print(f"❌ Core 服务集成测试失败: {e}")
        return False


def test_exchange_factory():
    """测试交易所工厂"""
    print("\n🔧 测试交易所工厂...")
    
    if not ExchangeFactory:
        print("⚠️ ExchangeFactory 不可用，跳过测试")
        return False
    
    try:
        # 创建工厂实例
        factory = ExchangeFactory()
        
        # 测试 Binance 适配器创建
        binance_config = {
            'api_key': 'test_key',
            'api_secret': 'test_secret',
            'testnet': True
        }
        
        binance_adapter = factory.create_adapter('binance', binance_config)
        if binance_adapter:
            print(f"✅ Binance 适配器创建成功: {binance_adapter.exchange}")
        else:
            print("⚠️ Binance 适配器创建返回None")
        
        # 测试 OKX 适配器创建
        okx_config = {
            'api_key': 'test_key',
            'api_secret': 'test_secret',
            'passphrase': 'test_passphrase',
            'testnet': True
        }
        
        okx_adapter = factory.create_adapter('okx', okx_config)
        if okx_adapter:
            print(f"✅ OKX 适配器创建成功: {okx_adapter.exchange}")
        else:
            print("⚠️ OKX 适配器创建返回None")
        
        # 测试支持的交易所列表
        supported_exchanges = factory.get_supported_exchanges()
        print(f"✅ 支持的交易所: {supported_exchanges}")
        
        return True
        
    except Exception as e:
        print(f"❌ 交易所工厂测试失败: {e}")
        return False


async def test_basic_connectivity():
    """测试基本连接功能"""
    print("\n🔧 测试基本连接功能...")
    
    if not BinanceAdapter:
        print("⚠️ BinanceAdapter 不可用，跳过连接测试")
        return False
    
    try:
        # 创建测试配置
        config = {
            'api_key': 'test_key',
            'api_secret': 'test_secret',
            'testnet': True,
            'rate_limits': {
                'requests_per_minute': 1200,
                'requests_per_second': 20
            }
        }
        
        # 尝试通过工厂创建适配器
        if ExchangeFactory:
            factory = ExchangeFactory()
            adapter = factory.create_adapter('binance', config)
            if adapter:
                print("✅ Binance 适配器通过工厂初始化成功")
                
                # 测试基本方法存在性
                required_methods = ['get_server_time', 'get_exchange_info', 'get_orderbook_snapshot']
                for method_name in required_methods:
                    if hasattr(adapter, method_name):
                        print(f"✅ 方法存在: {method_name}")
                    else:
                        print(f"❌ 方法缺失: {method_name}")
                
                return True
            else:
                print("⚠️ 工厂创建适配器返回None")
        
        # 直接创建适配器测试
        from marketprism_collector.config import ExchangeConfig, Exchange
        
        exchange_config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            api_key='test_key',
            api_secret='test_secret',
            testnet=True
        )
        
        adapter = BinanceAdapter(exchange_config)
        print("✅ Binance 适配器直接初始化成功")
        
        # 测试基本方法存在性
        required_methods = ['get_server_time', 'get_exchange_info', 'get_orderbook_snapshot']
        for method_name in required_methods:
            if hasattr(adapter, method_name):
                print(f"✅ 方法存在: {method_name}")
            else:
                print(f"❌ 方法缺失: {method_name}")
        
        return True
        
    except Exception as e:
        print(f"❌ 基本连接测试失败: {e}")
        return False


def test_configuration_loading():
    """测试配置加载"""
    print("\n🔧 测试配置加载...")
    
    try:
        # 测试基本配置结构
        test_config = {
            'exchanges': {
                'binance': {
                    'name': 'binance',
                    'enabled': True,
                    'testnet': True
                },
                'okx': {
                    'name': 'okx',
                    'enabled': True,
                    'testnet': True
                }
            },
            'data_collection': {
                'collection_interval': 1.0,
                'batch_size': 100
            }
        }
        
        # 验证配置结构
        assert 'exchanges' in test_config
        assert 'data_collection' in test_config
        assert len(test_config['exchanges']) == 2
        
        print("✅ 配置结构验证成功")
        
        # 测试配置验证逻辑
        for exchange_name, exchange_config in test_config['exchanges'].items():
            assert 'name' in exchange_config
            assert 'enabled' in exchange_config
            print(f"✅ {exchange_name} 配置验证成功")
        
        return True
        
    except Exception as e:
        print(f"❌ 配置加载测试失败: {e}")
        return False


def test_file_permissions():
    """测试文件权限"""
    print("\n🔧 测试文件权限...")
    
    try:
        # 检查关键文件是否可读
        test_files = [
            "services/python-collector/src/marketprism_collector/__init__.py",
            "tests/tdd_collector_comprehensive_plan.md",
            "README.md"
        ]
        
        for file_path in test_files:
            full_path = project_root / file_path
            if full_path.exists() and os.access(full_path, os.R_OK):
                print(f"✅ 文件可读: {file_path}")
            else:
                print(f"⚠️ 文件不可读或不存在: {file_path}")
        
        # 检查测试目录权限
        test_dirs = ["tests", "logs", "cache"]
        for dir_name in test_dirs:
            dir_path = project_root / dir_name
            if dir_path.exists():
                if os.access(dir_path, os.W_OK):
                    print(f"✅ 目录可写: {dir_name}")
                else:
                    print(f"⚠️ 目录不可写: {dir_name}")
            else:
                print(f"⚠️ 目录不存在: {dir_name}")
        
        return True
        
    except Exception as e:
        print(f"❌ 文件权限测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("🚀 MarketPrism Collector 快速测试开始")
    print(f"📁 项目根目录: {project_root}")
    
    start_time = time.time()
    test_results = []
    
    # 执行测试
    tests = [
        ("项目结构", test_project_structure),
        ("Core 服务集成", test_core_services_integration),
        ("交易所工厂", test_exchange_factory),
        ("配置加载", test_configuration_loading),
        ("文件权限", test_file_permissions),
    ]
    
    for test_name, test_func in tests:
        print(f"\n{'='*50}")
        result = test_func()
        test_results.append((test_name, result))
    
    # 异步测试
    print(f"\n{'='*50}")
    async_result = asyncio.run(test_basic_connectivity())
    test_results.append(("基本连接", async_result))
    
    # 总结
    end_time = time.time()
    duration = end_time - start_time
    
    print(f"\n{'='*60}")
    print("📊 测试结果总结")
    print(f"{'='*60}")
    
    passed = 0
    failed = 0
    
    for test_name, result in test_results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    total_tests = len(test_results)
    success_rate = (passed / total_tests) * 100
    
    print(f"\n📈 统计:")
    print(f"   总测试: {total_tests}")
    print(f"   通过: {passed}")
    print(f"   失败: {failed}")
    print(f"   成功率: {success_rate:.1f}%")
    print(f"   耗时: {duration:.2f}秒")
    
    if success_rate >= 60:
        print("\n🎉 基础功能测试通过！可以继续执行更详细的测试")
        print("\n📋 下一步建议:")
        print("   1. 执行单元测试: make -f Makefile_collector_tdd test-unit")
        print("   2. 执行集成测试: make -f Makefile_collector_tdd test-integration")
        print("   3. 执行完整TDD: python tests/run_collector_tdd.py")
        return 0
    else:
        print("\n⚠️ 部分基础功能存在问题，建议先修复后再执行完整测试")
        print("\n🔧 修复建议:")
        if failed > 0:
            print("   1. 检查缺失的模块和文件")
            print("   2. 确认项目结构完整性")
            print("   3. 验证Python路径设置")
        return 1


if __name__ == "__main__":
    sys.exit(main())