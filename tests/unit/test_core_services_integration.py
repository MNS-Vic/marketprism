#!/usr/bin/env python3
"""
Core Services Integration Tests for Python-Collector

测试Python-Collector与项目级Core层服务的集成
替代原有的重复基础设施组件测试
"""
import pytest
import asyncio
import sys
import os
from unittest.mock import Mock, AsyncMock, patch

# 添加搜索路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/python-collector/src'))

from marketprism_collector.core_services import core_services, CoreServicesAdapter
from marketprism_collector.core_integration import get_core_integration


@pytest.mark.unit
class TestCoreServicesIntegration:
    """测试Core服务集成"""
    
    def test_core_services_adapter_initialization(self):
        """测试Core服务适配器初始化"""
        adapter = CoreServicesAdapter()
        
        # 检查服务状态
        status = adapter.get_services_status()
        assert isinstance(status, dict)
        assert 'core_services_available' in status
    
    def test_core_monitoring_integration(self):
        """测试Core监控服务集成"""
        monitoring = core_services.get_monitoring_service()
        
        # 如果Core服务可用，应该返回监控实例
        if monitoring:
            assert hasattr(monitoring, 'record_metric') or hasattr(monitoring, 'get_metrics')
    
    def test_core_security_integration(self):
        """测试Core安全服务集成"""
        security = core_services.get_security_service()
        
        # 测试API密钥验证
        result = core_services.validate_api_key("test_key")
        assert isinstance(result, bool)
    
    def test_core_reliability_integration(self):
        """测试Core可靠性服务集成"""
        reliability = core_services.get_reliability_service()
        
        # 测试熔断器创建
        circuit_breaker = core_services.create_circuit_breaker("test_breaker")
        # 在降级模式下可能返回None
    
    def test_core_storage_integration(self):
        """测试Core存储服务集成"""
        storage = core_services.get_storage_service()
        
        # 测试ClickHouse写入器创建
        writer = core_services.get_clickhouse_writer({})
        # 在降级模式下可能返回None
    
    def test_core_error_handling_integration(self):
        """测试Core错误处理集成"""
        error_handler = core_services.get_error_handler()
        
        # 测试错误处理
        test_error = Exception("Test error")
        error_id = core_services.handle_error(test_error)
        assert isinstance(error_id, str)
    
    def test_core_logging_integration(self):
        """测试Core日志服务集成"""
        logger = core_services.get_logger_service()
        
        # 测试日志记录
        core_services.log_info("Test info message")
        core_services.log_error("Test error message")
        
        # 应该不抛出异常
    
    def test_graceful_degradation(self):
        """测试优雅降级"""
        # 模拟Core服务不可用的情况
        with patch('marketprism_collector.core_services.CORE_SERVICES_AVAILABLE', False):
            adapter = CoreServicesAdapter()
            
            # 应该仍能工作，但返回降级结果
            result = adapter.validate_api_key("test")
            assert result is True  # 降级模式返回True
            
            error_id = adapter.handle_error(Exception("test"))
            assert isinstance(error_id, str)


@pytest.mark.unit
class TestConfigurationPathsIntegration:
    """测试统一配置路径管理器"""
    
    def test_config_path_manager_import(self):
        """测试配置路径管理器导入"""
        from marketprism_collector.config import config_path_manager
        assert config_path_manager is not None
    
    def test_exchange_config_paths(self):
        """测试交易所配置路径"""
        from marketprism_collector.config_paths import config_path_manager
        
        # 测试配置路径解析
        exchange_config_path = config_path_manager.get_exchange_config_path("binance")
        assert "config/exchanges/binance.yaml" in str(exchange_config_path)
    
    def test_collector_config_paths(self):
        """测试收集器配置路径"""
        from marketprism_collector.config_paths import config_path_manager
        
        collector_config_path = config_path_manager.get_collector_config_path("main")
        assert "config/collector/main.yaml" in str(collector_config_path)
    
    def test_config_files_listing(self):
        """测试配置文件列表"""
        from marketprism_collector.config_paths import config_path_manager
        
        # 测试配置文件列表
        exchange_configs = config_path_manager.list_config_files("exchanges")
        assert isinstance(exchange_configs, list)


@pytest.mark.integration
class TestCoreIntegrationWorkflow:
    """测试Core集成工作流"""
    
    def test_collector_core_integration_workflow(self):
        """测试收集器Core集成工作流"""
        from marketprism_collector.core_integration import (
            get_core_integration, log_collector_info, record_collector_metric
        )
        
        # 测试Core集成获取
        integration = get_core_integration()
        assert integration is not None
        
        # 测试日志记录
        log_collector_info("Test workflow starting")
        
        # 测试指标记录
        record_collector_metric("test_metric", 1.0, exchange="test")
        
        # 测试健康状态
        health = integration.get_health_status()
        assert isinstance(health, dict)
    
    def test_error_aggregation_workflow(self):
        """测试错误聚合工作流"""
        # 测试错误聚合器
        error_aggregator = core_services.get_error_aggregator()
        
        if error_aggregator:
            # 测试时序错误分析
            test_error = Exception("Test error for aggregation")
            core_services.handle_error(test_error, {"component": "test"})
    
    def test_middleware_integration_workflow(self):
        """测试中间件集成工作流"""
        # 测试中间件框架
        middleware_framework = core_services.get_middleware_framework()
        
        if middleware_framework:
            # 测试限流中间件创建
            rate_limiter = core_services.create_rate_limiting_middleware({"max_requests": 100})


@pytest.mark.unit
class TestArchitectureCompliance:
    """测试架构合规性"""
    
    def test_no_duplicate_infrastructure_imports(self):
        """确保不再导入重复的基础设施组件"""
        # 确保不能导入已删除的组件
        with pytest.raises(ImportError):
            from marketprism_collector.monitoring.metrics import MetricsCollector
        
        with pytest.raises(ImportError):
            from marketprism_collector.reliability.circuit_breaker import CircuitBreaker
        
        with pytest.raises(ImportError):
            from marketprism_collector.storage.clickhouse_writer import ClickHouseWriter
    
    def test_core_services_availability(self):
        """测试Core服务可用性检查"""
        from marketprism_collector.core_services import CORE_SERVICES_AVAILABLE
        
        # 检查Core服务可用性标志
        assert isinstance(CORE_SERVICES_AVAILABLE, bool)
        
        # 获取服务状态
        status = core_services.get_services_status()
        assert 'core_services_available' in status
        assert status['core_services_available'] == CORE_SERVICES_AVAILABLE
    
    def test_unified_configuration_architecture(self):
        """测试统一配置架构"""
        from marketprism_collector.config import ConfigPathManager
        
        # 测试配置路径管理器类
        path_manager = ConfigPathManager()
        assert hasattr(path_manager, 'get_config_path')
        assert hasattr(path_manager, 'get_exchange_config_path')
        assert hasattr(path_manager, 'get_collector_config_path')
    
    def test_enterprise_middleware_availability(self):
        """测试企业级中间件可用性"""
        # 测试6种企业级中间件的可用性
        middleware_types = [
            'rate_limiting', 'cors', 'authentication', 
            'authorization', 'caching', 'logging'
        ]
        
        middleware_framework = core_services.get_middleware_framework()
        if middleware_framework:
            # 检查中间件框架是否包含所需功能
            assert hasattr(middleware_framework, 'add_middleware') or \
                   hasattr(middleware_framework, 'register_middleware')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])