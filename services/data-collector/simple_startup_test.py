#!/usr/bin/env python3
"""
简单的MarketPrism启动测试
验证基础功能是否正常
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def test_basic_imports():
    """测试基础模块导入"""
    print("🔍 测试基础模块导入...")
    
    try:
        import asyncio
        print("✅ asyncio 导入成功")
        
        import yaml
        print("✅ yaml 导入成功")
        
        import structlog
        print("✅ structlog 导入成功")
        
        import websockets
        print("✅ websockets 导入成功")
        
        import nats
        print("✅ nats 导入成功")
        
        return True
    except ImportError as e:
        print(f"❌ 基础模块导入失败: {e}")
        return False

def test_config_file():
    """测试配置文件"""
    print("\n🔍 测试配置文件...")
    
    config_path = project_root / "config" / "collector" / "unified_data_collection.yaml"
    
    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        return False
    
    try:
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        print(f"✅ 配置文件解析成功")
        print(f"   - 包含 {len(config)} 个配置项")
        
        if 'exchanges' in config:
            exchanges = config['exchanges']
            print(f"   - 配置了 {len(exchanges)} 个交易所")
            for exchange_name in exchanges.keys():
                enabled = exchanges[exchange_name].get('enabled', True)
                status = "启用" if enabled else "禁用"
                print(f"     * {exchange_name}: {status}")
        
        return True
    except Exception as e:
        print(f"❌ 配置文件解析失败: {e}")
        return False

def test_nats_connection():
    """测试NATS连接"""
    print("\n🔍 测试NATS连接...")
    
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('localhost', 4222))
        sock.close()
        
        if result == 0:
            print("✅ NATS服务器可访问 (localhost:4222)")
            return True
        else:
            print("❌ NATS服务器不可访问")
            return False
    except Exception as e:
        print(f"❌ NATS连接测试失败: {e}")
        return False

def test_project_structure():
    """测试项目结构"""
    print("\n🔍 测试项目结构...")
    
    required_paths = [
        "core",
        "services/data-collector",
        "config/collector",
        "services/data-collector/exchanges",
        "services/data-collector/collector/orderbook_manager.py"
    ]
    
    all_exist = True
    for path_str in required_paths:
        path = project_root / path_str
        if path.exists():
            print(f"✅ {path_str}")
        else:
            print(f"❌ {path_str} 不存在")
            all_exist = False
    
    return all_exist

def main():
    """主测试函数"""
    print("🎯 MarketPrism基础功能测试")
    print("=" * 50)
    print(f"项目根目录: {project_root}")
    print("=" * 50)
    
    tests = [
        ("基础模块导入", test_basic_imports),
        ("配置文件", test_config_file),
        ("NATS连接", test_nats_connection),
        ("项目结构", test_project_structure)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 测试: {test_name}")
        print("-" * 30)
        
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name} 通过")
            else:
                print(f"❌ {test_name} 失败")
        except Exception as e:
            print(f"❌ {test_name} 异常: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过！系统准备就绪")
        print("💡 可以尝试启动完整的数据收集系统")
        return 0
    else:
        print("⚠️  部分测试失败，请检查系统配置")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
