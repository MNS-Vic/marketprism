"""
端到端测试：完整数据流程测试

测试场景：
1. 模拟完整的配置加载→网络连接→数据传输流程
2. 测试多交易所连接的并发场景
3. 验证错误恢复和重连机制
4. 测试系统在真实场景下的表现

遵循TDD原则：Red-Green-Refactor
"""

import pytest
import asyncio
import tempfile
import yaml
import json
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone

from core.config.unified_config_manager import UnifiedConfigManager
from core.networking.unified_session_manager import UnifiedSessionManager, UnifiedSessionConfig
from core.networking.proxy_manager import ProxyConfig


class TestCompleteDataFlow:
    """完整数据流程端到端测试"""
    
    def setup_method(self):
        """设置测试方法"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_manager = UnifiedConfigManager(config_dir=self.temp_dir)
        self.session_manager = UnifiedSessionManager()
        
    def teardown_method(self):
        """清理测试方法"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.session_manager.close())
            else:
                loop.run_until_complete(self.session_manager.close())
        except RuntimeError:
            pass
            
        # 清理临时目录
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        
    @pytest.mark.asyncio
    async def test_complete_config_to_network_flow(self):
        """测试：完整的配置→网络流程"""
        # 1. 创建配置文件
        config_file = Path(self.temp_dir) / "exchanges.yaml"
        config_data = {
            "exchanges": {
                "binance": {
                    "enabled": True,
                    "session_config": {
                        "total_timeout": 30.0,
                        "connector_limit": 50,
                        "max_retries": 3
                    }
                },
                "okx": {
                    "enabled": True,
                    "session_config": {
                        "total_timeout": 45.0,
                        "connector_limit": 75,
                        "max_retries": 5
                    }
                }
            }
        }
        
        with open(config_file, 'w') as f:
            yaml.dump(config_data, f)
            
        # 2. 加载配置
        with open(config_file, 'r') as f:
            loaded_config = yaml.safe_load(f)
            
        # 3. 为每个交易所创建会话
        sessions = {}
        for exchange_name, exchange_config in loaded_config["exchanges"].items():
            if exchange_config["enabled"]:
                session_config = UnifiedSessionConfig(**exchange_config["session_config"])
                session = await self.session_manager.get_session(
                    f"{exchange_name}_session", 
                    session_config
                )
                sessions[exchange_name] = session
                
        # 4. 验证所有会话创建成功
        assert len(sessions) == 2
        assert "binance" in sessions
        assert "okx" in sessions
        
        for exchange, session in sessions.items():
            assert session is not None
            assert not session.closed
            
        # 5. 验证配置正确应用
        binance_config = self.session_manager._session_configs["binance_session"]
        okx_config = self.session_manager._session_configs["okx_session"]
        
        assert binance_config.total_timeout == 30.0
        assert binance_config.connector_limit == 50
        assert okx_config.total_timeout == 45.0
        assert okx_config.connector_limit == 75
        
    @pytest.mark.asyncio
    async def test_multi_exchange_concurrent_connections(self):
        """测试：多交易所并发连接"""
        exchanges = ["binance", "okx", "deribit", "bybit", "huobi"]
        
        async def create_exchange_session(exchange_name):
            """创建交易所会话的异步函数"""
            config = UnifiedSessionConfig(
                total_timeout=30.0 + len(exchange_name),  # 基于名称长度的差异化配置
                connector_limit=50 + len(exchange_name) * 5,
                max_retries=3 + len(exchange_name) % 3
            )
            
            session = await self.session_manager.get_session(
                f"{exchange_name}_concurrent", 
                config
            )
            
            return exchange_name, session
            
        # 并发创建所有交易所会话
        tasks = [create_exchange_session(exchange) for exchange in exchanges]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 验证所有会话都成功创建
        successful_sessions = {}
        for result in results:
            if isinstance(result, tuple):
                exchange_name, session = result
                successful_sessions[exchange_name] = session
                
        assert len(successful_sessions) == len(exchanges)
        
        for exchange, session in successful_sessions.items():
            assert session is not None
            assert not session.closed
            assert f"{exchange}_concurrent" in self.session_manager._sessions
            
    @pytest.mark.asyncio
    async def test_error_recovery_and_reconnection(self):
        """测试：错误恢复和重连机制"""
        # 1. 创建初始会话
        config = UnifiedSessionConfig(total_timeout=30.0)
        session = await self.session_manager.get_session("recovery_test", config)
        
        assert session is not None
        assert not session.closed
        
        # 2. 模拟会话关闭（错误场景）
        await self.session_manager.close_session("recovery_test")
        assert session.closed
        assert "recovery_test" not in self.session_manager._sessions
        
        # 3. 重新创建会话（恢复机制）
        new_config = UnifiedSessionConfig(
            total_timeout=60.0,  # 使用不同的配置
            max_retries=5
        )
        
        new_session = await self.session_manager.get_session("recovery_test", new_config)
        
        # 4. 验证恢复成功
        assert new_session is not None
        assert not new_session.closed
        assert new_session is not session  # 应该是新的会话实例
        assert self.session_manager._session_configs["recovery_test"].total_timeout == 60.0
        
    @pytest.mark.asyncio
    async def test_session_lifecycle_management(self):
        """测试：会话生命周期管理"""
        # 1. 创建多个会话
        sessions = {}
        for i in range(3):
            config = UnifiedSessionConfig(total_timeout=30.0 + i * 10)
            session = await self.session_manager.get_session(f"lifecycle_{i}", config)
            sessions[f"lifecycle_{i}"] = session
            
        # 2. 验证所有会话都活跃
        assert len(self.session_manager._sessions) == 3
        for session in sessions.values():
            assert not session.closed
            
        # 3. 关闭部分会话
        await self.session_manager.close_session("lifecycle_1")
        assert sessions["lifecycle_1"].closed
        assert len(self.session_manager._sessions) == 2
        
        # 4. 验证其他会话仍然活跃
        assert not sessions["lifecycle_0"].closed
        assert not sessions["lifecycle_2"].closed
        
        # 5. 关闭所有会话
        await self.session_manager.close()
        
        for session in sessions.values():
            assert session.closed
            
        assert len(self.session_manager._sessions) == 0
        assert self.session_manager._closed is True
        
    def test_configuration_validation_e2e(self):
        """测试：端到端配置验证"""
        # 1. 测试有效配置组合
        valid_configs = [
            {"total_timeout": 30.0, "connector_limit": 100},
            {"total_timeout": 60.0, "max_retries": 5, "enable_ssl": True},
            {"connector_limit": 50, "enable_ssl": False}
        ]
        
        for config_data in valid_configs:
            config = UnifiedSessionConfig(**config_data)
            assert config is not None
            
        # 2. 测试边界值配置
        edge_cases = [
            {"total_timeout": 0.1},  # 最小超时
            {"connector_limit": 1},   # 最小连接数
            {"max_retries": 0}        # 无重试
        ]
        
        for config_data in edge_cases:
            config = UnifiedSessionConfig(**config_data)
            assert config is not None
            
    @pytest.mark.asyncio
    async def test_proxy_configuration_e2e(self):
        """测试：代理配置端到端流程"""
        # 1. 创建代理配置
        proxy_config = ProxyConfig(
            http_proxy="http://proxy.example.com:8080",
            https_proxy="https://proxy.example.com:8080",
            enabled=True
        )
        
        # 2. 使用代理配置创建会话
        session_config = UnifiedSessionConfig(total_timeout=30.0)
        session = await self.session_manager.get_session(
            "proxy_e2e_test", 
            session_config, 
            proxy_config=proxy_config
        )
        
        # 3. 验证会话创建成功
        assert session is not None
        assert not session.closed
        assert "proxy_e2e_test" in self.session_manager._sessions
        
    @pytest.mark.asyncio
    async def test_performance_under_load(self):
        """测试：负载下的性能表现"""
        # 1. 创建大量并发会话
        num_sessions = 20
        
        async def create_load_session(session_id):
            config = UnifiedSessionConfig(
                total_timeout=30.0,
                connector_limit=10,  # 较小的连接限制以测试资源管理
                max_retries=2
            )
            return await self.session_manager.get_session(f"load_{session_id}", config)
            
        # 2. 并发创建会话
        start_time = asyncio.get_event_loop().time()
        tasks = [create_load_session(i) for i in range(num_sessions)]
        sessions = await asyncio.gather(*tasks)
        end_time = asyncio.get_event_loop().time()
        
        # 3. 验证性能指标
        creation_time = end_time - start_time
        assert creation_time < 5.0  # 应该在5秒内完成
        
        # 4. 验证所有会话都成功创建
        assert len(sessions) == num_sessions
        for session in sessions:
            assert session is not None
            assert not session.closed
            
        # 5. 验证统计信息
        stats = self.session_manager.stats
        assert stats['sessions_created'] >= num_sessions
        
    def test_configuration_serialization_e2e(self):
        """测试：配置序列化端到端"""
        # 1. 创建复杂配置
        config = UnifiedSessionConfig(
            total_timeout=45.0,
            connector_limit=100,
            connector_limit_per_host=20,
            enable_ssl=True,
            max_retries=3,
            retry_delay=1.5
        )
        
        # 2. 序列化配置
        config_dict = {
            "total_timeout": config.total_timeout,
            "connector_limit": config.connector_limit,
            "connector_limit_per_host": config.connector_limit_per_host,
            "enable_ssl": config.enable_ssl,
            "max_retries": config.max_retries,
            "retry_delay": config.retry_delay
        }
        
        # 3. 转换为JSON（模拟网络传输）
        config_json = json.dumps(config_dict)
        assert config_json is not None
        
        # 4. 反序列化并重建配置
        restored_dict = json.loads(config_json)
        restored_config = UnifiedSessionConfig(**restored_dict)
        
        # 5. 验证配置一致性
        assert restored_config.total_timeout == config.total_timeout
        assert restored_config.connector_limit == config.connector_limit
        assert restored_config.enable_ssl == config.enable_ssl
        assert restored_config.max_retries == config.max_retries
        
    @pytest.mark.asyncio
    async def test_system_health_monitoring(self):
        """测试：系统健康监控"""
        # 1. 创建多个会话
        sessions = []
        for i in range(5):
            config = UnifiedSessionConfig(total_timeout=30.0)
            session = await self.session_manager.get_session(f"health_{i}", config)
            sessions.append(session)
            
        # 2. 检查系统健康状态
        stats = self.session_manager.stats
        assert stats['sessions_created'] >= 5
        assert stats['sessions_closed'] == 0
        
        # 3. 模拟部分会话关闭
        await self.session_manager.close_session("health_0")
        await self.session_manager.close_session("health_1")
        
        # 4. 验证统计信息更新
        # 注意：统计信息可能不会立即更新，这取决于实现
        assert len(self.session_manager._sessions) == 3
        
        # 5. 验证剩余会话仍然健康
        for i in range(2, 5):
            session_name = f"health_{i}"
            assert session_name in self.session_manager._sessions
            session = self.session_manager._sessions[session_name]
            assert not session.closed
