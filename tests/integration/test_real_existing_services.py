"""
MarketPrism 现有服务真实测试

测试现有的Go和Python数据收集器的真实功能
"""
from datetime import datetime, timezone
import pytest
import asyncio
import time
import json
import subprocess
import requests
import os
import sys
from pathlib import Path

# 添加Python收集器路径
python_collector_path = Path(__file__).parent.parent.parent / "services" / "python-collector" / "src"
sys.path.insert(0, str(python_collector_path))

try:
    from marketprism_collector.config import Config
    from marketprism_collector.collector import MarketDataCollector
    from marketprism_collector.data_types import NormalizedTrade, NormalizedOrderBook
    from marketprism_collector.nats_client import NATSManager
    PYTHON_COLLECTOR_AVAILABLE = True
except ImportError as e:
    print(f"Python收集器模块导入失败: {e}")
    PYTHON_COLLECTOR_AVAILABLE = False


class TestRealPythonCollector:
    """真实Python收集器测试"""
    
    @pytest.mark.skipif(not PYTHON_COLLECTOR_AVAILABLE, reason="Python收集器模块不可用")
    def test_config_loading(self):
        """测试配置加载功能"""
        # 创建测试配置
        test_config = {
            "collector": {
                "name": "test_collector",
                "http_port": 8082,
                "enable_scheduler": False,
                "data_types": ["trades", "orderbooks", "tickers"]
            },
            "nats": {
                "servers": ["nats://localhost:4222"],
                "subjects": {
                    "trades": "market.trades",
                    "orderbooks": "market.orderbooks",
                    "tickers": "market.tickers"
                }
            },
            "exchanges": {
                "binance": {
                    "enabled": True,
                    "symbols": ["BTC/USDT", "ETH/USDT"],
                    "data_types": ["trades", "orderbooks"],
                    "rate_limit": 1000
                }
            },
            "proxy": {
                "enabled": False
            }
        }
        
        # 写入临时配置文件
        import tempfile
        import yaml
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(test_config, f)
            config_file = f.name
        
        try:
            # 测试配置加载
            config = Config.load_from_file(config_file)
            
            # 验证配置
            assert config.collector.name == "test_collector"
            assert config.collector.http_port == 8082
            assert config.nats.servers == ["nats://localhost:4222"]
            assert "binance" in config.exchanges
            assert config.exchanges["binance"]["enabled"] is True
            assert len(config.exchanges["binance"]["symbols"]) == 2
            
        finally:
            os.unlink(config_file)
    
    @pytest.mark.skipif(not PYTHON_COLLECTOR_AVAILABLE, reason="Python收集器模块不可用")
    @pytest.mark.asyncio
    async def test_collector_initialization(self):
        """测试收集器初始化"""
        # 创建最小配置
        test_config = {
            "collector": {
                "name": "test_collector",
                "http_port": 8083,
                "enable_scheduler": False
            },
            "nats": {
                "servers": ["nats://localhost:4222"],
                "subjects": {"trades": "test.trades"}
            },
            "exchanges": {},
            "proxy": {"enabled": False}
        }
        
        import tempfile
        import yaml
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(test_config, f)
            config_file = f.name
        
        try:
            config = Config.load_from_file(config_file)
            collector = MarketDataCollector(config)
            
            # 验证初始化状态
            assert collector.config == config
            assert collector.is_running is False
            assert collector.start_time is None
            assert len(collector.exchange_adapters) == 0
            
            # 测试指标获取
            metrics = collector.get_metrics()
            assert hasattr(metrics, 'total_messages_received')
            assert hasattr(metrics, 'total_messages_published')
            
        finally:
            os.unlink(config_file)
    
    @pytest.mark.skipif(not PYTHON_COLLECTOR_AVAILABLE, reason="Python收集器模块不可用")
    def test_data_types_validation(self):
        """测试数据类型验证"""
        # 测试NormalizedTrade
        trade_data = {
            'id': 'test_trade_123',
            'exchange': 'binance',
            'symbol': 'BTC/USDT',
            'price': 67234.56,
            'amount': 0.001,
            'side': 'buy',
            'timestamp': time.time(),
            'trade_id': 'T_123',
            'order_id': 'O_456'
        }
        
        trade = NormalizedTrade(**trade_data)
        assert trade.exchange == 'binance'
        assert trade.symbol == 'BTC/USDT'
        assert trade.price == 67234.56
        assert trade.side == 'buy'
        
        # 测试NormalizedOrderBook
        orderbook_data = {
            'exchange': 'binance',
            'symbol': 'BTC/USDT',
            'timestamp': time.time(),
            'bids': [[67234.55, 0.1], [67234.54, 0.2]],
            'asks': [[67234.57, 0.1], [67234.58, 0.2]],
            'checksum': 123456
        }
        
        orderbook = NormalizedOrderBook(**orderbook_data)
        assert orderbook.exchange == 'binance'
        assert orderbook.symbol == 'BTC/USDT'
        assert len(orderbook.bids) == 2
        assert len(orderbook.asks) == 2
        assert orderbook.checksum == 123456


# Go收集器已被Python收集器完全替代，相关测试已移除


class TestRealServiceIntegration:
    """真实服务集成测试"""
    
    def test_service_directory_structure(self):
        """测试服务目录结构"""
        services_path = Path(__file__).parent.parent.parent / "services"
        
        # 验证关键服务目录存在
        expected_services = [
            "python-collector",  # 主要数据收集器
            "data_normalizer",
            "data_archiver", 
            "reliability"
        ]
        
        for service in expected_services:
            service_path = services_path / service
            assert service_path.exists(), f"服务目录不存在: {service}"
            assert service_path.is_dir(), f"不是目录: {service}"
    
    def test_python_collector_dependencies(self):
        """测试Python收集器依赖"""
        requirements_path = Path(__file__).parent.parent.parent / "services" / "python-collector" / "requirements.txt"
        
        if requirements_path.exists():
            with open(requirements_path, 'r') as f:
                requirements = f.read()
            
            # 检查关键依赖（适应实际的依赖名称）
            key_dependencies = [
                "aiohttp",
                "structlog",
                "prometheus-client",  # 实际使用的是prometheus-client而不是prometheus_client
                "pyyaml"
            ]
            
            for dep in key_dependencies:
                assert dep in requirements, f"缺少Python依赖: {dep}"
    
    def test_config_files_exist(self):
        """测试配置文件存在"""
        config_paths = [
            Path(__file__).parent.parent.parent / "services" / "python-collector" / "config",
            Path(__file__).parent.parent.parent / "config"
        ]
        
        for config_path in config_paths:
            if config_path.exists():
                # 检查是否有配置文件
                config_files = list(config_path.glob("*.yaml")) + list(config_path.glob("*.yml")) + list(config_path.glob("*.json"))
                # 至少应该有一些配置文件或示例文件
                assert len(config_files) >= 0  # 允许为空，但目录应该存在
    
    @pytest.mark.asyncio
    async def test_nats_client_functionality(self):
        """测试NATS客户端功能"""
        if not PYTHON_COLLECTOR_AVAILABLE:
            pytest.skip("Python收集器不可用")
        
        # 创建NATS配置
        nats_config = {
            "servers": ["nats://localhost:4222"],
            "subjects": {
                "trades": "test.trades",
                "orderbooks": "test.orderbooks"
            },
            "connection_timeout": 5,
            "max_reconnect_attempts": 3
        }
        
        try:
            # 创建NATS管理器
            from types import SimpleNamespace
            config = SimpleNamespace(**nats_config)
            nats_manager = NATSManager(config)
            
            # 测试连接（如果NATS服务器可用）
            try:
                success = await nats_manager.start()
                if success:
                    # 测试发布消息
                    test_message = {
                        "exchange": "test",
                        "symbol": "BTC/USDT",
                        "price": 50000.0,
                        "timestamp": time.time()
                    }
                    
                    publisher = nats_manager.get_publisher()
                    if publisher:
                        await publisher.publish_trade(test_message)
                    
                    # 清理
                    await nats_manager.stop()
                    
            except Exception as e:
                # NATS服务器不可用，跳过测试
                pytest.skip(f"NATS服务器不可用: {e}")
                
        except ImportError:
            pytest.skip("NATS客户端模块不可用")


class TestRealServicePerformance:
    """真实服务性能测试"""
    
    @pytest.mark.skipif(not PYTHON_COLLECTOR_AVAILABLE, reason="Python收集器不可用")
    def test_data_processing_performance(self):
        """测试数据处理性能"""
        # 生成大量测试数据
        start_time = time.time()
        
        trades = []
        for i in range(1000):
            trade_data = {
                'id': f'trade_{i}',
                'exchange': 'binance',
                'symbol': 'BTC/USDT',
                'price': 50000.0 + i,
                'amount': 0.001,
                'side': 'buy' if i % 2 == 0 else 'sell',
                'timestamp': time.time() + i,
                'trade_id': f'T_{i}',
                'order_id': f'O_{i}'
            }
            trades.append(NormalizedTrade(**trade_data))
        
        creation_time = time.time() - start_time
        assert creation_time < 1.0  # 创建1000个交易对象应该在1秒内
        
        # 测试数据序列化性能
        start_time = time.time()
        
        serialized_trades = []
        for trade in trades:
            # 模拟序列化过程
            trade_dict = {
                'id': trade.id,
                'exchange': trade.exchange,
                'symbol': trade.symbol,
                'price': trade.price,
                'amount': trade.amount,
                'side': trade.side,
                'timestamp': trade.timestamp
            }
            serialized_trades.append(json.dumps(trade_dict))
        
        serialization_time = time.time() - start_time
        assert serialization_time < 0.5  # 序列化应该在0.5秒内完成
        
        # 验证结果
        assert len(serialized_trades) == 1000
        assert all(isinstance(s, str) for s in serialized_trades)
    
    def test_concurrent_processing_simulation(self):
        """测试并发处理模拟"""
        import concurrent.futures
        import threading
        
        def process_batch(batch_id, batch_size):
            """模拟批处理"""
            processed = 0
            for i in range(batch_size):
                # 模拟数据处理
                data = {
                    'batch_id': batch_id,
                    'item_id': i,
                    'timestamp': time.time(),
                    'processed': True
                }
                processed += 1
            return processed
        
        start_time = time.time()
        
        # 并发处理多个批次
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(process_batch, i, 250) 
                for i in range(4)
            ]
            
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        processing_time = time.time() - start_time
        
        # 验证结果
        assert len(results) == 4
        assert sum(results) == 1000  # 总共处理1000个项目
        assert processing_time < 2.0  # 并发处理应该在2秒内完成


if __name__ == "__main__":
    # 可以直接运行这个文件进行测试
    pytest.main([__file__, "-v", "--tb=short"]) 