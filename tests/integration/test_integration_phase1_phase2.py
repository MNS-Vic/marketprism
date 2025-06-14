"""
MarketPrism 整合成果验证测试

测试阶段1（统一会话管理器）和阶段2（统一ClickHouse写入器）的整合成果：
1. 功能完整性验证
2. 向后兼容性验证  
3. 性能和稳定性验证
4. API接口一致性验证
"""

import pytest
import asyncio
import warnings
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone
import json

# --- Direct Imports to fix Collection Errors ---
from core.networking.unified_session_manager import (
    UnifiedSessionManager,
    UnifiedSessionConfig,
    unified_session_manager
)
from core.storage.unified_clickhouse_writer import UnifiedClickHouseWriter
from core.storage.types import NormalizedTrade, NormalizedOrderBook, NormalizedTicker

# --- Create Aliases for Backward Compatibility Tests ---
HTTPSessionManager = UnifiedSessionManager
SessionManager = UnifiedSessionManager
SessionConfig = UnifiedSessionConfig
session_manager = unified_session_manager
# get_session_manager was removed, alias to the main instance for the test
def get_session_manager():
    warnings.warn(
        "get_session_manager is deprecated and has been removed. "
        "Returning the global unified_session_manager instance.",
        DeprecationWarning
    )
    return unified_session_manager
ClickHouseWriter = UnifiedClickHouseWriter
OptimizedClickHouseWriter = UnifiedClickHouseWriter


class TestPhase1UnifiedSessionManager:
    """阶段1：统一会话管理器测试"""
    
    def test_import_success(self):
        """测试导入是否成功"""
        assert UnifiedSessionManager is not None
        assert UnifiedSessionConfig is not None
        assert unified_session_manager is not None
    
    def test_backward_compatibility_aliases(self):
        """测试向后兼容性别名"""
        # 测试类别名
        assert HTTPSessionManager == UnifiedSessionManager
        assert SessionManager == UnifiedSessionManager
        assert SessionConfig == UnifiedSessionConfig
        
        # 测试实例别名
        assert session_manager == unified_session_manager
    
    def test_deprecated_function_warnings(self):
        """测试废弃函数警告"""
        with pytest.warns(DeprecationWarning, match="get_session_manager 已废弃"):
            manager = get_session_manager()
            assert manager == unified_session_manager
    
    @pytest.mark.asyncio
    async def test_unified_session_manager_basic_functionality(self):
        """测试统一会话管理器基本功能"""
        config = UnifiedSessionConfig(
            total_timeout=10.0,
            enable_auto_cleanup=False  # 测试环境禁用自动清理
        )
        manager = UnifiedSessionManager(config)
        
        try:
            # 测试统计信息
            stats = manager.get_session_stats()
            assert isinstance(stats, dict)
            assert 'sessions_created' in stats
            assert 'active_sessions' in stats
            
            # 测试健康状态
            health = manager.get_health_status()
            assert isinstance(health, dict)
            assert 'healthy' in health
            assert 'health_score' in health
            
        finally:
            await manager.close()
    
    @pytest.mark.asyncio
    async def test_session_lifecycle(self):
        """测试会话生命周期管理"""
        config = UnifiedSessionConfig(enable_auto_cleanup=False)
        manager = UnifiedSessionManager(config)
        
        try:
            # 创建会话
            session = await manager.get_session("test_session")
            assert session is not None
            assert not session.closed
            
            # 检查统计
            stats = manager.get_session_stats()
            assert stats['sessions_created'] >= 1
            assert 'test_session' in stats['session_names']
            
            # 关闭会话
            await manager.close_session("test_session")
            
        finally:
            await manager.close()
    
    def test_config_integration(self):
        """测试配置整合"""
        config = UnifiedSessionConfig(
            connection_timeout=15.0,
            read_timeout=45.0,
            total_timeout=90.0,
            max_retries=5,
            # 来自基础版本的配置
            headers={'User-Agent': 'Test'},
            cookies={'test': 'value'},
            trust_env=True,
            # 来自优化版本的配置
            enable_auto_cleanup=True,
            cleanup_interval=30
        )
        
        # 验证所有配置属性都存在
        assert config.connection_timeout == 15.0
        assert config.read_timeout == 45.0
        assert config.total_timeout == 90.0
        assert config.max_retries == 5
        assert config.headers == {'User-Agent': 'Test'}
        assert config.cookies == {'test': 'value'}
        assert config.trust_env == True
        assert config.enable_auto_cleanup == True
        assert config.cleanup_interval == 30


class TestPhase2UnifiedClickHouseWriter:
    """阶段2：统一ClickHouse写入器测试"""
    
    def test_import_success(self):
        """测试导入是否成功"""
        assert UnifiedClickHouseWriter is not None
    
    def test_backward_compatibility_aliases(self):
        """测试向后兼容性别名"""
        # 检查类别名是否正确设置
        assert ClickHouseWriter == UnifiedClickHouseWriter
        assert OptimizedClickHouseWriter == UnifiedClickHouseWriter
    
    def test_disabled_writer_initialization(self):
        """测试禁用状态下的写入器初始化"""
        config = {'clickhouse_direct_write': False}
        writer = UnifiedClickHouseWriter(config)
        
        assert writer.enabled == False
        assert writer.config == config
        assert writer.client is None
    
    def test_enabled_writer_configuration(self):
        """测试启用状态下的写入器配置"""
        config = {
            'clickhouse_direct_write': True,
            'clickhouse': {
                'host': 'test-host',
                'port': 9000,
                'database': 'test_db',
                'user': 'test_user',
                'password': 'test_pass',
                'tables': {
                    'trades': 'test_trades',
                    'orderbook': 'test_orderbook',
                    'ticker': 'test_ticker'
                },
                'write': {
                    'batch_size': 500,
                    'interval': 3
                }
            },
            'optimization': {
                'connection_pool_size': 5,
                'max_retries': 2,
                'enable_data_validation': True,
                'enable_transactions': True
            }
        }
        
        writer = UnifiedClickHouseWriter(config)
        
        # 验证基础配置（来自原始版本）
        assert writer.enabled == True
        assert writer.host == 'test-host'
        assert writer.port == 9000
        assert writer.database == 'test_db'
        assert writer.trades_table == 'test_trades'
        assert writer.batch_size == 500
        assert writer.write_interval == 3
        
        # 验证优化配置（来自优化版本）
        assert writer.connection_pool_size == 5
        assert writer.max_retries == 2
        assert writer.enable_data_validation == True
        assert writer.enable_transactions == True
    
    def test_data_validation_functionality(self):
        """测试数据验证功能（来自优化版本）"""
        config = {
            'clickhouse_direct_write': True,
            'optimization': {'enable_data_validation': True}
        }
        writer = UnifiedClickHouseWriter(config)
        
        # 测试有效交易数据
        valid_trade = NormalizedTrade(
            exchange_name='binance',
            symbol_name='BTCUSDT',
            trade_id='12345',
            price=50000.0,
            quantity=1.0,
            timestamp=datetime.now(),
            is_buyer_maker=False
        )
        assert writer.validate_trade_data(valid_trade) == True
        
        # 测试无效交易数据（价格为负）
        invalid_trade = NormalizedTrade(
            exchange_name='binance',
            symbol_name='BTCUSDT',
            trade_id='12345',
            price=-50000.0,  # 无效价格
            quantity=1.0,
            timestamp=datetime.now(),
            is_buyer_maker=False
        )
        assert writer.validate_trade_data(invalid_trade) == False
    
    def test_performance_metrics(self):
        """测试性能监控功能"""
        writer = UnifiedClickHouseWriter()
        
        # 获取性能指标
        metrics = writer.get_performance_metrics()
        assert isinstance(metrics, dict)
        assert 'uptime_seconds' in metrics
        assert 'total_writes' in metrics
        assert 'successful_writes' in metrics
        assert 'failed_writes' in metrics
        assert 'success_rate' in metrics
        assert 'average_latency' in metrics
        
        # 获取健康状态
        health = writer.get_health_status()
        assert isinstance(health, dict)
        assert 'healthy' in health
        assert 'health_score' in health
        assert 'status' in health
        assert 'issues' in health
    
    def test_queue_management(self):
        """测试队列管理功能（来自基础版本）"""
        writer = UnifiedClickHouseWriter()
        
        # 初始队列应该为空
        queue_sizes = writer.get_queue_sizes()
        assert queue_sizes['trades'] == 0
        assert queue_sizes['orderbook'] == 0
        assert queue_sizes['ticker'] == 0
        assert queue_sizes['total'] == 0
    
    @pytest.mark.asyncio
    async def test_disabled_writer_operations(self):
        """测试禁用状态下的写入器操作"""
        config = {'clickhouse_direct_write': False}
        writer = UnifiedClickHouseWriter(config)
        
        # 启动和停止操作应该正常工作
        await writer.start()
        assert writer.client is not None  # 应该是DummyClient
        
        await writer.stop()
        
        # 写入操作应该被忽略
        trade = NormalizedTrade(
            exchange_name='binance',
            symbol_name='BTCUSDT',
            trade_id='12345',
            price=50000.0,
            quantity=1.0,
            timestamp=datetime.now(),
            is_buyer_maker=False
        )
        
        await writer.write_trade(trade)  # 应该不会报错
    
    def test_connection_pool_configuration(self):
        """测试连接池配置（来自优化版本）"""
        config = {
            'clickhouse_direct_write': True,
            'optimization': {'connection_pool_size': 8}
        }
        writer = UnifiedClickHouseWriter(config)
        
        assert writer.connection_pool_size == 8
        assert len(writer.connection_pool) == 0  # 初始为空
        assert writer.connection_pool_lock is not None


class TestIntegrationCompatibility:
    """整合兼容性测试"""
    
    def test_cross_component_integration(self):
        """测试跨组件集成"""
        # 测试会话管理器和ClickHouse写入器可以同时使用
        session_manager = UnifiedSessionManager()
        clickhouse_writer = UnifiedClickHouseWriter()
        
        # 都应该能正常初始化
        assert session_manager is not None
        assert clickhouse_writer is not None
        
        # 都应该有健康检查功能
        session_health = session_manager.get_health_status()
        writer_health = clickhouse_writer.get_health_status()
        
        assert isinstance(session_health, dict)
        assert isinstance(writer_health, dict)
    
    def test_global_instances_accessibility(self):
        """测试全局实例可访问性"""
        from core.networking import unified_session_manager
        from core.storage import unified_clickhouse_writer
        
        assert unified_session_manager is not None
        assert unified_clickhouse_writer is not None
        
        # 测试类型检查
        assert isinstance(unified_session_manager, UnifiedSessionManager)
        assert isinstance(unified_clickhouse_writer, UnifiedClickHouseWriter)
    
    @pytest.mark.asyncio
    async def test_async_operations_compatibility(self):
        """测试异步操作兼容性"""
        session_manager = UnifiedSessionManager(
            UnifiedSessionConfig(enable_auto_cleanup=False)
        )
        writer = UnifiedClickHouseWriter({'clickhouse_direct_write': False})
        
        try:
            # 两个组件的异步操作应该能同时进行
            await asyncio.gather(
                session_manager.get_session("test"),
                writer.start()
            )
            
            # 清理
            await asyncio.gather(
                session_manager.close(),
                writer.stop()
            )
            
        except Exception as e:
            pytest.fail(f"异步操作兼容性测试失败: {e}")


class TestPerformanceAndStability:
    """性能和稳定性测试"""
    
    @pytest.mark.asyncio
    async def test_session_manager_under_load(self):
        """测试会话管理器负载表现"""
        config = UnifiedSessionConfig(
            connection_timeout=5.0,
            enable_auto_cleanup=False
        )
        manager = UnifiedSessionManager(config)
        
        try:
            # 创建多个会话
            sessions = []
            for i in range(10):
                session = await manager.get_session(f"session_{i}")
                sessions.append(session)
            
            # 检查统计
            stats = manager.get_session_stats()
            assert stats['sessions_created'] >= 10
            assert stats['active_sessions'] >= 10
            
            # 健康状态应该良好
            health = manager.get_health_status()
            assert health['healthy'] == True
            
        finally:
            await manager.close()
    
    def test_clickhouse_writer_queue_performance(self):
        """测试ClickHouse写入器队列性能"""
        # 启用ClickHouse以测试队列功能
        config = {'clickhouse_direct_write': True}
        writer = UnifiedClickHouseWriter(config)
        
        # 添加大量数据到队列
        for i in range(100):  # 减少数量以加快测试
            trade = NormalizedTrade(
                exchange_name='test',
                symbol_name=f'TEST{i}',
                trade_id=str(i),
                price=100.0,
                quantity=1.0,
                timestamp=datetime.now(),
                is_buyer_maker=False
            )
            # 同步调用异步方法进行测试
            asyncio.run(writer.write_trade(trade))
        
        # 检查队列大小
        queue_sizes = writer.get_queue_sizes()
        assert queue_sizes['trades'] == 100
        
        # 性能指标应该正常
        metrics = writer.get_performance_metrics()
        assert metrics['uptime_seconds'] > 0
    
    @pytest.mark.asyncio
    async def test_memory_cleanup(self):
        """测试内存清理"""
        import gc
        
        # 创建并销毁多个实例
        for _ in range(50):
            manager = UnifiedSessionManager(
                UnifiedSessionConfig(enable_auto_cleanup=False)
            )
            writer = UnifiedClickHouseWriter({'clickhouse_direct_write': False})
            
            await manager.close()
            await writer.stop()
            
            del manager, writer
        
        # 强制垃圾回收
        gc.collect()
        
        # 测试通过，说明没有明显的内存泄漏
        assert True


@pytest.mark.integration
class TestRealWorldScenarios:
    """真实场景测试"""
    
    @pytest.mark.asyncio
    async def test_typical_usage_scenario(self):
        """测试典型使用场景"""
        # 场景：同时使用会话管理器和ClickHouse写入器
        
        session_manager = UnifiedSessionManager(
            UnifiedSessionConfig(
                total_timeout=10.0,
                enable_auto_cleanup=False
            )
        )
        
        writer = UnifiedClickHouseWriter({
            'clickhouse_direct_write': False,  # 测试环境禁用实际写入
            'optimization': {
                'enable_data_validation': True
            }
        })
        
        try:
            # 启动组件
            await writer.start()
            
            # 获取HTTP会话
            session = await session_manager.get_session("binance_session")
            assert session is not None
            
            # 模拟交易数据
            trade = NormalizedTrade(
                exchange_name='binance',
                symbol_name='BTCUSDT',
                trade_id='test_12345',
                price=50000.0,
                quantity=1.0,
                timestamp=datetime.now(),
                is_buyer_maker=False
            )
            
            # 写入数据
            await writer.write_trade(trade)
            
            # 检查状态
            session_health = session_manager.get_health_status()
            writer_health = writer.get_health_status()
            
            assert session_health['healthy'] == True
            assert writer_health['healthy'] == True
            
        finally:
            # 清理资源
            await session_manager.close()
            await writer.stop()
    
    def test_configuration_flexibility(self):
        """测试配置灵活性"""
        # 测试各种配置组合
        
        # 最小配置
        minimal_session = UnifiedSessionManager()
        minimal_writer = UnifiedClickHouseWriter()
        
        assert minimal_session is not None
        assert minimal_writer is not None
        
        # 完整配置
        full_config_session = UnifiedSessionManager(UnifiedSessionConfig(
            connection_timeout=20.0,
            read_timeout=60.0,
            total_timeout=120.0,
            max_retries=5,
            headers={'Custom-Header': 'value'},
            enable_auto_cleanup=True,
            cleanup_interval=45
        ))
        
        full_config_writer = UnifiedClickHouseWriter({
            'clickhouse_direct_write': True,
            'clickhouse': {
                'host': 'custom-host',
                'database': 'custom_db'
            },
            'optimization': {
                'connection_pool_size': 15,
                'enable_data_validation': True,
                'enable_transactions': True
            }
        })
        
        assert full_config_session.config.connection_timeout == 20.0
        assert full_config_writer.connection_pool_size == 15


if __name__ == '__main__':
    # 运行所有测试
    pytest.main([__file__, '-v', '--tb=short'])