#!/usr/bin/env python3
"""
MarketPrism 阶段4清理验证测试

验证第4阶段代码模块清理的结果：
1. 验证统一管理器功能完整性
2. 验证向后兼容性
3. 验证导入正常工作
4. 验证清理后的目录结构
"""

from datetime import datetime, timezone
import asyncio
import unittest
import sys
import os
from pathlib import Path
from typing import Dict, Any

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

class TestPhase4CleanupVerification(unittest.TestCase):
    """阶段4清理验证测试"""
    
    def setUp(self):
        """测试初始化"""
        self.storage_path = project_root / "core" / "storage"
        self.backup_path = project_root / "backup" / "storage_deprecated_phase4"
        
    def test_01_backup_directory_created(self):
        """测试1：验证备份目录已创建"""
        self.assertTrue(self.backup_path.exists(), "备份目录应该存在")
        self.assertTrue(self.backup_path.is_dir(), "备份路径应该是目录")
        
    def test_02_deprecated_files_moved(self):
        """测试2：验证已废弃文件已移动到备份目录"""
        expected_backup_files = [
            "hot_storage_manager.py",
            "simple_hot_storage_manager.py", 
            "cold_storage_manager.py",
            "clickhouse_writer.py",
            "optimized_clickhouse_writer.py",
            "archiver_storage_manager.py",
            "manager.py"
        ]
        
        for filename in expected_backup_files:
            backup_file = self.backup_path / filename
            self.assertTrue(backup_file.exists(), f"备份文件 {filename} 应该存在")
            
            # 验证原文件不存在
            original_file = self.storage_path / filename
            self.assertFalse(original_file.exists(), f"原文件 {filename} 应该已移动")
    
    def test_03_unified_files_remain(self):
        """测试3：验证统一管理器文件保留"""
        essential_files = [
            "__init__.py",
            "unified_storage_manager.py",
            "unified_clickhouse_writer.py",
            "types.py",
            "factory.py"
        ]
        
        for filename in essential_files:
            file_path = self.storage_path / filename
            self.assertTrue(file_path.exists(), f"核心文件 {filename} 应该保留")
    
    def test_04_backward_compatibility_imports(self):
        """测试4：验证向后兼容性导入"""
        try:
            # 测试旧的导入方式仍然有效
            from core.storage import HotStorageManager
            from core.storage import SimpleHotStorageManager
            from core.storage import ColdStorageManager
            from core.storage import StorageManager
            from core.storage import ClickHouseWriter
            from core.storage import OptimizedClickHouseWriter
            
            # 验证这些都指向统一管理器
            from core.storage import UnifiedStorageManager
            
            self.assertEqual(HotStorageManager, UnifiedStorageManager, "HotStorageManager应该指向UnifiedStorageManager")
            self.assertEqual(SimpleHotStorageManager, UnifiedStorageManager, "SimpleHotStorageManager应该指向UnifiedStorageManager")
            self.assertEqual(ColdStorageManager, UnifiedStorageManager, "ColdStorageManager应该指向UnifiedStorageManager")
            self.assertEqual(StorageManager, UnifiedStorageManager, "StorageManager应该指向UnifiedStorageManager")
            
        except ImportError as e:
            self.fail(f"向后兼容导入失败: {e}")
    
    def test_05_unified_storage_manager_functionality(self):
        """测试5：验证统一存储管理器功能"""
        try:
            from core.storage import UnifiedStorageManager, UnifiedStorageConfig
            
            # 测试配置创建
            config = UnifiedStorageConfig(
                storage_type="hot",
                enabled=False,  # 防止真实连接
                redis_enabled=False,
                memory_cache_enabled=True
            )
            
            # 测试管理器创建
            manager = UnifiedStorageManager(config)
            
            # 验证基本属性
            self.assertEqual(manager.config.storage_type, "hot")
            self.assertFalse(manager.config.enabled)
            self.assertFalse(manager.is_running)
            
            # 验证统计信息
            stats = manager.get_statistics()
            self.assertIsInstance(stats, dict)
            self.assertIn('storage_type', stats)
            self.assertEqual(stats['storage_type'], 'hot')
            
            # 验证健康状态
            health = manager.get_health_status()
            self.assertIsInstance(health, dict)
            self.assertIn('is_healthy', health)
            self.assertIn('storage_type', health)
            
        except Exception as e:
            self.fail(f"统一存储管理器功能测试失败: {e}")
    
    def test_06_factory_functions_work(self):
        """测试6：验证工厂函数正常工作"""
        try:
            from core.storage import (
                get_hot_storage_manager,
                get_simple_hot_storage_manager,
                get_cold_storage_manager,
                get_storage_manager
            )
            
            # 测试工厂函数返回统一管理器实例
            hot_manager = get_hot_storage_manager()
            simple_manager = get_simple_hot_storage_manager()
            cold_manager = get_cold_storage_manager()
            storage_manager = get_storage_manager()
            
            # 验证都是UnifiedStorageManager实例
            from core.storage import UnifiedStorageManager
            self.assertIsInstance(hot_manager, UnifiedStorageManager)
            self.assertIsInstance(simple_manager, UnifiedStorageManager)
            self.assertIsInstance(cold_manager, UnifiedStorageManager)
            self.assertIsInstance(storage_manager, UnifiedStorageManager)
            
            # 验证存储类型正确
            self.assertEqual(hot_manager.config.storage_type, "hot")
            self.assertEqual(simple_manager.config.storage_type, "simple")
            self.assertEqual(cold_manager.config.storage_type, "cold")
            self.assertEqual(storage_manager.config.storage_type, "hybrid")
            
        except Exception as e:
            self.fail(f"工厂函数测试失败: {e}")
    
    def test_07_clickhouse_writer_functionality(self):
        """测试7：验证ClickHouse写入器功能"""
        try:
            from core.storage import UnifiedClickHouseWriter
            from core.storage import ClickHouseWriter, OptimizedClickHouseWriter
            
            # 验证向后兼容别名
            self.assertEqual(ClickHouseWriter, UnifiedClickHouseWriter)
            self.assertEqual(OptimizedClickHouseWriter, UnifiedClickHouseWriter)
            
            # 测试配置创建
            config = {
                'host': 'localhost',
                'port': 8123,
                'database': 'test',
                'enabled': False  # 防止真实连接
            }
            
            # 测试写入器创建
            writer = UnifiedClickHouseWriter(config)
            self.assertIsInstance(writer, UnifiedClickHouseWriter)
            
        except Exception as e:
            self.fail(f"ClickHouse写入器功能测试失败: {e}")
    
    def test_08_networking_imports(self):
        """测试8：验证网络模块导入正常"""
        try:
            from core.networking import UnifiedSessionManager
            from core.networking import HTTPSessionManager, SessionManager
            
            # 验证向后兼容
            self.assertEqual(HTTPSessionManager, UnifiedSessionManager)
            self.assertEqual(SessionManager, UnifiedSessionManager)
            
        except ImportError as e:
            self.fail(f"网络模块导入失败: {e}")
    
    def test_09_directory_structure_clean(self):
        """测试9：验证目录结构清洁"""
        storage_files = list(self.storage_path.glob("*.py"))
        storage_filenames = [f.name for f in storage_files]
        
        # 不应该存在的文件
        deprecated_files = [
            "hot_storage_manager.py",
            "simple_hot_storage_manager.py",
            "cold_storage_manager.py", 
            "clickhouse_writer.py",
            "optimized_clickhouse_writer.py",
            "archiver_storage_manager.py",
            "manager.py"
        ]
        
        for deprecated_file in deprecated_files:
            self.assertNotIn(deprecated_file, storage_filenames, 
                           f"已废弃文件 {deprecated_file} 不应该在存储目录中")
        
        # 应该存在的文件
        essential_files = [
            "__init__.py",
            "unified_storage_manager.py",
            "unified_clickhouse_writer.py",
            "types.py",
            "factory.py"
        ]
        
        for essential_file in essential_files:
            self.assertIn(essential_file, storage_filenames,
                         f"核心文件 {essential_file} 应该在存储目录中")
    
    def test_10_integration_status(self):
        """测试10：验证整合状态报告"""
        try:
            from core.storage import get_integration_status
            
            status = get_integration_status()
            self.assertIsInstance(status, dict)
            self.assertEqual(status['phase'], 3)
            self.assertEqual(status['status'], 'completed')
            self.assertIn('unified_managers', status)
            self.assertIn('backward_compatibility', status)
            self.assertEqual(status['backward_compatibility'], '100%')
            
        except Exception as e:
            self.fail(f"整合状态测试失败: {e}")

class TestPhase4CleanupAsync(unittest.IsolatedAsyncioTestCase):
    """阶段4清理异步功能验证测试"""
    
    async def test_async_storage_manager_operations(self):
        """测试异步存储管理器操作"""
        try:
            from core.storage import UnifiedStorageManager, UnifiedStorageConfig
            
            # 创建测试配置（不连接真实服务）
            config = UnifiedStorageConfig(
                storage_type="hot",
                enabled=False,
                redis_enabled=False,
                memory_cache_enabled=True
            )
            
            manager = UnifiedStorageManager(config)
            
            # 测试异步启动（模拟模式）
            await manager.start()
            self.assertTrue(manager.is_running)
            
            # 测试数据存储操作（模拟数据）
            test_trade = {
                'symbol': 'BTCUSDT',
                'exchange': 'binance',
                'price': 50000.0,
                'amount': 0.1,
                'side': 'buy',
                'trade_id': 'test123',
                'timestamp': '2025-01-31T12:00:00Z'
            }
            
            # 这些操作在Mock模式下应该不会失败
            await manager.store_trade(test_trade)
            
            # 测试读取操作
            latest_trade = await manager.get_latest_trade('binance', 'BTCUSDT')
            # 在Mock模式下可能返回None，这是正常的
            
            # 测试统计信息
            stats = manager.get_statistics()
            self.assertIsInstance(stats, dict)
            self.assertGreaterEqual(stats['total_writes'], 1)
            
            # 测试停止
            await manager.stop()
            self.assertFalse(manager.is_running)
            
        except Exception as e:
            self.fail(f"异步存储管理器操作测试失败: {e}")

def run_phase4_verification():
    """运行阶段4清理验证测试"""
    print("🧹 开始MarketPrism阶段4清理验证测试...")
    
    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加同步测试
    sync_tests = loader.loadTestsFromTestCase(TestPhase4CleanupVerification)
    suite.addTests(sync_tests)
    
    # 添加异步测试
    async_tests = loader.loadTestsFromTestCase(TestPhase4CleanupAsync)
    suite.addTests(async_tests)
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 生成报告
    total_tests = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    successes = total_tests - failures - errors
    
    print(f"\n{'='*60}")
    print(f"📊 阶段4清理验证测试结果:")
    print(f"{'='*60}")
    print(f"✅ 成功: {successes}/{total_tests}")
    print(f"❌ 失败: {failures}/{total_tests}")
    print(f"💥 错误: {errors}/{total_tests}")
    print(f"🎯 成功率: {(successes/total_tests)*100:.1f}%")
    
    if result.failures:
        print(f"\n❌ 失败的测试:")
        for test, traceback in result.failures:
            print(f"  - {test}: {traceback.split('AssertionError: ')[-1].split('\\n')[0]}")
    
    if result.errors:
        print(f"\n💥 错误的测试:")
        for test, traceback in result.errors:
            print(f"  - {test}: {traceback.split('\\n')[-2]}")
    
    print(f"\n{'='*60}")
    
    return result.wasSuccessful()

if __name__ == "__main__":
    success = run_phase4_verification()
    sys.exit(0 if success else 1)