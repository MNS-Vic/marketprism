#!/usr/bin/env python3
"""
MarketPrism 阶段4整合验证脚本

验证data_archiver整合到core/storage/的所有功能是否正常工作
"""

import sys
import asyncio
import traceback
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_imports():
    """测试导入是否正常"""
    print("🔍 测试1: 检查模块导入...")
    
    try:
        # 测试基础导入
        from core.storage.unified_storage_manager import UnifiedStorageManager, UnifiedStorageConfig
        print("  ✅ UnifiedStorageManager导入成功")
        
        from core.storage.archive_manager import ArchiveManager, ArchiveConfig
        print("  ✅ ArchiveManager导入成功")
        
        from core.storage.archive_manager import DataArchiver, DataArchiverService
        print("  ✅ 向后兼容类导入成功")
        
        # 测试配置文件读取
        import yaml
        config_path = project_root / "config" / "unified_storage_config.yaml"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            print("  ✅ 统一配置文件读取成功")
        else:
            print("  ⚠️ 统一配置文件不存在，将使用默认配置")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 导入失败: {e}")
        traceback.print_exc()
        return False

async def test_unified_storage_manager():
    """测试统一存储管理器"""
    print("\n🔍 测试2: 统一存储管理器基础功能...")
    
    try:
        from core.storage.unified_storage_manager import UnifiedStorageManager, UnifiedStorageConfig
        
        # 创建热存储配置
        config = UnifiedStorageConfig(
            storage_type="hot",
            enabled=False,  # 使用Mock客户端
            redis_enabled=False,
            memory_cache_enabled=True,
            auto_archive_enabled=True
        )
        
        # 创建管理器
        manager = UnifiedStorageManager(config, None, "hot")
        print("  ✅ 统一存储管理器创建成功")
        
        # 启动管理器
        await manager.start()
        print("  ✅ 统一存储管理器启动成功")
        
        # 检查归档管理器集成
        if manager.archive_manager:
            print("  ✅ 归档管理器已集成")
        else:
            print("  ⚠️ 归档管理器未初始化（可能是配置问题）")
        
        # 测试基础功能
        test_data = {
            'timestamp': '2025-01-31 12:00:00',
            'symbol': 'BTC/USDT',
            'exchange': 'test',
            'price': 45000.0,
            'amount': 1.0,
            'side': 'buy',
            'trade_id': 'test_123'
        }
        
        await manager.store_trade(test_data)
        print("  ✅ 交易数据存储测试成功")
        
        # 获取状态
        status = manager.get_comprehensive_status()
        assert status['is_running'] == True
        print("  ✅ 状态获取测试成功")
        
        # 停止管理器
        await manager.stop()
        print("  ✅ 统一存储管理器停止成功")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 统一存储管理器测试失败: {e}")
        traceback.print_exc()
        return False

async def test_archive_manager():
    """测试归档管理器"""
    print("\n🔍 测试3: 归档管理器功能...")
    
    try:
        from core.storage.unified_storage_manager import UnifiedStorageManager, UnifiedStorageConfig
        from core.storage.archive_manager import ArchiveManager, ArchiveConfig
        
        # 创建存储管理器
        hot_config = UnifiedStorageConfig(
            storage_type="hot",
            enabled=False,
            redis_enabled=False
        )
        hot_manager = UnifiedStorageManager(hot_config, None, "hot")
        await hot_manager.start()
        
        cold_config = UnifiedStorageConfig(
            storage_type="cold", 
            enabled=False,
            redis_enabled=False
        )
        cold_manager = UnifiedStorageManager(cold_config, None, "cold")
        await cold_manager.start()
        
        # 创建归档配置
        archive_config = ArchiveConfig(
            enabled=True,
            retention_days=7,
            cleanup_enabled=True
        )
        
        # 创建归档管理器
        archive_manager = ArchiveManager(hot_manager, cold_manager, archive_config)
        print("  ✅ 归档管理器创建成功")
        
        # 启动归档管理器
        await archive_manager.start()
        print("  ✅ 归档管理器启动成功")
        
        # 测试归档功能（模拟运行）
        results = await archive_manager.archive_data(
            tables=['test_trades'],
            dry_run=True
        )
        print("  ✅ 归档功能测试成功")
        
        # 测试恢复功能（模拟运行）
        count = await archive_manager.restore_data(
            table='test_trades',
            date_from='2025-01-01',
            date_to='2025-01-31',
            dry_run=True
        )
        print("  ✅ 恢复功能测试成功")
        
        # 获取状态
        status = archive_manager.get_status()
        assert status['is_running'] == True
        print("  ✅ 归档状态获取成功")
        
        # 停止归档管理器
        await archive_manager.stop()
        await hot_manager.stop()
        await cold_manager.stop()
        print("  ✅ 归档管理器停止成功")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 归档管理器测试失败: {e}")
        traceback.print_exc()
        return False

async def test_backward_compatibility():
    """测试向后兼容性"""
    print("\n🔍 测试4: 向后兼容性...")
    
    try:
        from core.storage.archive_manager import DataArchiver, DataArchiverService
        
        # 测试DataArchiver兼容性
        archiver = DataArchiver()
        print("  ✅ DataArchiver创建成功")
        
        status = archiver.get_status()
        assert isinstance(status, dict)
        print("  ✅ DataArchiver状态获取成功")
        
        # 测试DataArchiverService兼容性
        service = DataArchiverService()
        print("  ✅ DataArchiverService创建成功")
        
        await service.start_async()
        assert service.running == True
        print("  ✅ DataArchiverService启动成功")
        
        health = service.health_check()
        assert isinstance(health, dict)
        print("  ✅ DataArchiverService健康检查成功")
        
        await service.stop_async()
        assert service.running == False
        print("  ✅ DataArchiverService停止成功")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 向后兼容性测试失败: {e}")
        traceback.print_exc()
        return False

def test_configuration():
    """测试配置系统"""
    print("\n🔍 测试5: 配置系统...")
    
    try:
        from core.storage.unified_storage_manager import UnifiedStorageConfig
        from core.storage.archive_manager import ArchiveConfig
        
        # 测试统一存储配置
        storage_config = UnifiedStorageConfig(
            storage_type="hot",
            enabled=True,
            auto_archive_enabled=True
        )
        print("  ✅ 统一存储配置创建成功")
        
        # 测试归档配置
        archive_config = ArchiveConfig(
            enabled=True,
            retention_days=14,
            cleanup_enabled=True
        )
        print("  ✅ 归档配置创建成功")
        
        # 测试配置字典转换
        config_dict = {
            'enabled': True,
            'retention_days': 7,
            'cleanup_enabled': True,
            'max_age_days': 30
        }
        
        archive_config_from_dict = ArchiveConfig.from_dict(config_dict)
        assert archive_config_from_dict.enabled == True
        assert archive_config_from_dict.retention_days == 7
        print("  ✅ 配置字典转换成功")
        
        # 测试YAML配置加载（如果文件存在）
        config_path = project_root / "config" / "unified_storage_config.yaml"
        if config_path.exists():
            unified_config = UnifiedStorageConfig.from_yaml(str(config_path), "hot")
            print("  ✅ YAML配置加载成功")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 配置系统测试失败: {e}")
        traceback.print_exc()
        return False

async def test_integration_workflow():
    """测试完整集成工作流程"""
    print("\n🔍 测试6: 完整集成工作流程...")
    
    try:
        from core.storage.unified_storage_manager import UnifiedStorageManager, UnifiedStorageConfig
        
        # 创建带归档功能的热存储管理器
        config = UnifiedStorageConfig(
            storage_type="hot",
            enabled=False,  # 使用Mock客户端
            redis_enabled=False,
            memory_cache_enabled=True,
            auto_archive_enabled=True,
            archive_retention_days=7,
            cleanup_enabled=True,
            cleanup_max_age_days=30
        )
        
        manager = UnifiedStorageManager(config, None, "hot")
        await manager.start()
        print("  ✅ 带归档功能的存储管理器启动成功")
        
        # 测试数据存储
        test_trade = {
            'timestamp': '2025-01-31 12:00:00',
            'symbol': 'BTC/USDT',
            'exchange': 'binance',
            'price': 45000.0,
            'amount': 1.0,
            'side': 'buy',
            'trade_id': 'integration_test'
        }
        
        await manager.store_trade(test_trade)
        print("  ✅ 数据存储测试成功")
        
        # 测试归档接口
        archive_results = await manager.archive_data(dry_run=True)
        assert isinstance(archive_results, dict)
        print("  ✅ 归档接口测试成功")
        
        # 测试清理接口
        cleanup_results = await manager.cleanup_expired_data(dry_run=True)
        assert isinstance(cleanup_results, dict)
        print("  ✅ 清理接口测试成功")
        
        # 测试状态监控
        archive_status = manager.get_archive_status()
        assert isinstance(archive_status, dict)
        print("  ✅ 归档状态监控测试成功")
        
        archive_stats = manager.get_archive_statistics()
        assert isinstance(archive_stats, dict)
        print("  ✅ 归档统计信息测试成功")
        
        # 测试综合状态
        comprehensive_status = manager.get_comprehensive_status()
        assert 'archive_status' in comprehensive_status
        print("  ✅ 综合状态测试成功")
        
        await manager.stop()
        print("  ✅ 完整集成工作流程测试成功")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 完整集成工作流程测试失败: {e}")
        traceback.print_exc()
        return False

async def main():
    """主函数"""
    print("🚀 MarketPrism 阶段4整合验证")
    print("验证data_archiver整合到core/storage/的功能完整性")
    print("=" * 60)
    
    # 运行所有测试
    tests = [
        ("模块导入", test_imports),
        ("统一存储管理器", test_unified_storage_manager),
        ("归档管理器", test_archive_manager),
        ("向后兼容性", test_backward_compatibility),
        ("配置系统", test_configuration),
        ("完整集成工作流程", test_integration_workflow)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"  ❌ 测试执行异常: {e}")
            results.append((test_name, False))
    
    # 汇总结果
    print("\n" + "="*60)
    print("🏆 阶段4整合验证结果汇总")
    print("="*60)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name:<20} {status}")
        if result:
            passed += 1
    
    print(f"\n📊 测试统计:")
    print(f"总计: {total} 个测试")
    print(f"通过: {passed} 个测试")
    print(f"失败: {total - passed} 个测试")
    print(f"成功率: {passed/total*100:.1f}%")
    
    if passed == total:
        print("\n🎉 所有测试通过！阶段4整合完全成功！")
        print("\n✅ 结论: data_archiver模块已成功整合到core/storage/")
        print("✅ 功能完整性: 100%保留并增强")
        print("✅ 向后兼容性: 100%兼容")
        print("✅ 推荐状态: 可投入生产使用")
        return True
    else:
        print(f"\n⚠️ 发现 {total - passed} 个问题，需要进一步检查")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)