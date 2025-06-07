#!/usr/bin/env python3
"""
最小化TDD测试运行器
在缺少某些基础设施的情况下仍能运行部分TDD测试
"""

import asyncio
import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

def run_pytest_command(test_files, extra_args=None):
    """运行pytest命令"""
    cmd = [sys.executable, '-m', 'pytest'] + test_files + ['-v', '--tb=short']
    
    if extra_args:
        cmd.extend(extra_args)
    
    print(f"运行命令: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=300
        )
        
        print("STDOUT:")
        print(result.stdout)
        
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        
        return result.returncode == 0
    
    except subprocess.TimeoutExpired:
        print("❌ 测试运行超时")
        return False
    except Exception as e:
        print(f"❌ 运行测试时出错: {e}")
        return False

def test_basic_imports():
    """测试基础导入功能"""
    print("🧪 测试基础导入功能...")
    
    try:
        # 测试核心模块导入
        sys.path.insert(0, str(PROJECT_ROOT))
        
        from tests.tdd_framework.real_test_base import RealTestBase
        from core.storage.unified_storage_manager import UnifiedStorageManager
        from core.networking.unified_session_manager import UnifiedSessionManager
        
        print("✅ 核心模块导入成功")
        return True
        
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False

def test_configuration_loading():
    """测试配置文件加载"""
    print("🧪 测试配置文件加载...")
    
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from tests.tdd_framework.real_test_base import RealTestBase
        
        test_base = RealTestBase()
        config = test_base.config
        
        # 验证关键配置项
        assert 'services' in config, "配置缺少services部分"
        assert 'databases' in config, "配置缺少databases部分"
        assert 'exchanges' in config, "配置缺少exchanges部分"
        
        print("✅ 配置文件加载成功")
        print(f"   发现服务: {list(config['services'].keys())}")
        print(f"   配置的交易所: {list(config['exchanges'].keys())}")
        
        return True
        
    except Exception as e:
        print(f"❌ 配置加载失败: {e}")
        return False

def test_network_connectivity():
    """测试网络连接性"""
    print("🧪 测试网络连接性...")
    
    try:
        import asyncio
        import aiohttp
        
        async def check_connectivity():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get('https://httpbin.org/ip', timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            print(f"✅ 网络连接正常，IP: {data.get('origin')}")
                            return True
                        else:
                            print(f"❌ 网络请求失败: {response.status}")
                            return False
            except Exception as e:
                print(f"❌ 网络连接失败: {e}")
                return False
        
        return asyncio.run(check_connectivity())
        
    except Exception as e:
        print(f"❌ 网络测试失败: {e}")
        return False

def test_exchange_api_basic():
    """测试交易所API基础连接"""
    print("🧪 测试交易所API基础连接...")
    
    try:
        import asyncio
        import aiohttp
        
        async def test_binance_connectivity():
            try:
                async with aiohttp.ClientSession() as session:
                    # 测试Binance Testnet
                    async with session.get(
                        'https://testnet.binance.vision/api/v3/time', 
                        timeout=10
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            print(f"✅ Binance Testnet连接成功，服务器时间: {data.get('serverTime')}")
                            return True
                        else:
                            print(f"❌ Binance API请求失败: {response.status}")
                            return False
            except Exception as e:
                print(f"❌ Binance连接失败: {e}")
                return False
        
        return asyncio.run(test_binance_connectivity())
        
    except Exception as e:
        print(f"❌ 交易所API测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🎯 开始最小化TDD测试")
    print("="*50)
    
    tests = [
        ("基础导入测试", test_basic_imports),
        ("配置加载测试", test_configuration_loading),
        ("网络连接测试", test_network_connectivity),
        ("交易所API测试", test_exchange_api_basic)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}")
        print("-" * 30)
        success = test_func()
        results[test_name] = success
        print()
    
    # 汇总结果
    print("\n📊 测试结果汇总")
    print("="*50)
    
    total_tests = len(results)
    passed_tests = sum(results.values())
    
    for test_name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"   {status} {test_name}")
    
    print(f"\n总计: {passed_tests}/{total_tests} 测试通过")
    
    if passed_tests == total_tests:
        print("🎉 所有基础测试通过！")
        
        # 如果基础测试通过，尝试运行单元测试
        print("\n🧪 运行单元测试...")
        unit_test_files = [
            "tests/unit/core/test_unified_storage_manager.py",
            "tests/unit/core/test_unified_session_manager.py"
        ]
        
        # 过滤存在的测试文件
        existing_files = []
        for test_file in unit_test_files:
            if (PROJECT_ROOT / test_file).exists():
                existing_files.append(test_file)
        
        if existing_files:
            print(f"发现单元测试文件: {existing_files}")
            success = run_pytest_command(existing_files)
            if success:
                print("✅ 单元测试通过")
            else:
                print("❌ 单元测试失败")
        else:
            print("⚠️ 未找到单元测试文件")
        
        return True
    else:
        print("❌ 部分基础测试失败")
        return False

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️ 测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试运行出错: {e}")
        sys.exit(1)