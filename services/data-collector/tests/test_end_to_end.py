"""
Data-Collector端到端测试

验证整个Data-Collector系统的集成和数据流完整性
"""

import asyncio
import json
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from decimal import Decimal
import pytest
import aiohttp

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from collector.service import DataCollectorService
from collector.orderbook_manager import OrderBookManager
from collector.data_collection_config_manager import get_data_collection_config_manager
from collector.data_quality_validator import get_data_quality_validator
from collector.websocket_config_loader import get_websocket_config_loader
from collector.data_types import Exchange, ExchangeConfig
from collector.normalizer import DataNormalizer
from exchanges.binance import BinanceAdapter
from exchanges.okx import OKXAdapter
from exchanges.deribit import DeribitAdapter


class TestDataCollectorEndToEnd:
    """Data-Collector端到端测试套件"""
    
    @pytest.fixture
    def mock_config(self):
        """模拟配置"""
        return {
            'service_name': 'data-collector',
            'port': 8084,
            'exchanges': {
                'binance': {
                    'enabled': True,
                    'symbols': ['BTCUSDT', 'ETHUSDT']
                },
                'okx': {
                    'enabled': True,
                    'symbols': ['BTC-USDT', 'ETH-USDT']
                },
                'deribit': {
                    'enabled': True,
                    'symbols': ['btc_usd', 'eth_usd']
                }
            },
            'data_types': ['kline', 'orderbook', 'trade'],
            'enable_orderbook': True,
            'enable_websocket': True,
            'collection_interval': 30
        }
    
    @pytest.fixture
    def mock_nats_client(self):
        """模拟NATS客户端"""
        client = Mock()
        client.publish = AsyncMock()
        client.subscribe = AsyncMock()
        client.is_connected = True
        return client
    
    @pytest.fixture
    def mock_normalizer(self):
        """模拟数据标准化器"""
        normalizer = Mock(spec=DataNormalizer)
        
        # 模拟标准化方法
        normalizer.normalize_trade = Mock(return_value={
            'exchange': 'binance',
            'symbol': 'BTCUSDT',
            'price': '50000.00',
            'quantity': '1.0',
            'timestamp': datetime.now(timezone.utc)
        })
        
        normalizer.normalize_orderbook = Mock(return_value={
            'exchange_name': 'binance',
            'symbol_name': 'BTCUSDT',
            'bids': [],
            'asks': [],
            'timestamp': datetime.now(timezone.utc)
        })
        
        normalizer.normalize_kline = Mock(return_value={
            'exchange': 'binance',
            'symbol': 'BTCUSDT',
            'interval': '1m',
            'open': '50000.00',
            'high': '50100.00',
            'low': '49900.00',
            'close': '50050.00',
            'volume': '100.0',
            'timestamp': datetime.now(timezone.utc)
        })
        
        return normalizer
    
    @pytest.fixture
    async def data_collector_service(self, mock_config, mock_nats_client, mock_normalizer):
        """创建Data-Collector服务实例"""
        with patch('collector.service.DataNormalizer', return_value=mock_normalizer):
            service = DataCollectorService(mock_config)
            service.nats_client = mock_nats_client
            yield service
    
    @pytest.mark.asyncio
    async def test_service_initialization(self, data_collector_service):
        """测试服务初始化"""
        service = data_collector_service
        
        # 验证基本属性
        assert service.service_name == 'data-collector'
        assert service.port == 8084
        assert service.enable_orderbook is True
        assert service.enable_websocket is True
        
        # 验证组件初始化
        assert service.data_normalizer is not None
        assert service.nats_client is not None
    
    @pytest.mark.asyncio
    async def test_configuration_loading(self):
        """测试配置加载"""
        # 测试数据收集配置管理器
        config_manager = get_data_collection_config_manager()
        
        # 验证配置加载
        enabled_exchanges = config_manager.get_enabled_exchanges()
        assert isinstance(enabled_exchanges, list)
        
        enabled_data_types = config_manager.get_enabled_data_types()
        assert isinstance(enabled_data_types, list)
        
        # 测试WebSocket配置加载器
        ws_config_loader = get_websocket_config_loader()
        
        # 验证支持的交易所
        supported_exchanges = ws_config_loader.get_supported_exchanges()
        assert isinstance(supported_exchanges, list)
    
    @pytest.mark.asyncio
    async def test_exchange_adapters_initialization(self, mock_config):
        """测试交易所适配器初始化"""
        # 测试Binance适配器
        binance_config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            symbols=['BTCUSDT'],
            base_url='https://api.binance.com'
        )
        binance_adapter = BinanceAdapter(binance_config)
        
        assert binance_adapter.exchange == Exchange.BINANCE
        assert binance_adapter.ws_config_loader is not None
        
        # 测试OKX适配器
        okx_config = ExchangeConfig(
            exchange=Exchange.OKX,
            symbols=['BTC-USDT'],
            base_url='https://www.okx.com'
        )
        okx_adapter = OKXAdapter(okx_config)
        
        assert okx_adapter.exchange == Exchange.OKX
        assert okx_adapter.ws_config_loader is not None
        
        # 测试Deribit适配器
        deribit_config = ExchangeConfig(
            exchange=Exchange.DERIBIT,
            symbols=['btc_usd'],
            base_url='https://www.deribit.com'
        )
        deribit_adapter = DeribitAdapter(deribit_config)
        
        assert deribit_adapter.exchange == Exchange.DERIBIT
        assert deribit_adapter.ws_config_loader is not None
    
    @pytest.mark.asyncio
    async def test_orderbook_manager_integration(self, mock_normalizer, mock_nats_client):
        """测试OrderBook Manager集成"""
        config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            symbols=['BTCUSDT'],
            snapshot_interval=10
        )
        
        # 创建OrderBook Manager
        orderbook_manager = OrderBookManager(config, mock_normalizer, mock_nats_client)
        
        # 验证初始化
        assert orderbook_manager.config == config
        assert orderbook_manager.normalizer == mock_normalizer
        assert orderbook_manager.nats_client == mock_nats_client
        assert orderbook_manager.enable_nats_push is True
    
    @pytest.mark.asyncio
    async def test_data_quality_validation(self):
        """测试数据质量验证"""
        from collector.data_quality_validator import DataPoint, ValidationResult
        
        validator = get_data_quality_validator()
        
        # 创建测试数据点
        data_point = DataPoint(
            timestamp=int(time.time() * 1000),
            symbol='BTCUSDT',
            exchange='binance',
            data_type='trade',
            data={
                'price': '50000.00',
                'quantity': '1.0',
                'timestamp': int(time.time() * 1000)
            }
        )
        
        # 验证数据
        result = validator.validate_data_point(data_point)
        
        assert isinstance(result, ValidationResult)
        assert result.valid is True
        assert result.action == 'accept'
    
    @pytest.mark.asyncio
    async def test_rate_limiting_integration(self, mock_config):
        """测试Rate Limiting集成"""
        # 测试Binance Rate Limiting
        binance_config = ExchangeConfig(exchange=Exchange.BINANCE)
        binance_adapter = BinanceAdapter(binance_config)
        
        # 验证rate limiting配置
        assert binance_adapter.max_request_weight == 6000
        assert binance_adapter.order_rate_limit == 100
        assert hasattr(binance_adapter, '_rate_limit_lock')
        
        # 测试OKX Rate Limiting
        okx_config = ExchangeConfig(exchange=Exchange.OKX)
        okx_adapter = OKXAdapter(okx_config)
        
        # 验证rate limiting配置
        assert okx_adapter.max_requests_per_second == 20
        assert okx_adapter.max_requests_per_2s == 60
        assert hasattr(okx_adapter, '_rate_limit_lock')
        
        # 测试Deribit Rate Limiting
        deribit_config = ExchangeConfig(exchange=Exchange.DERIBIT)
        deribit_adapter = DeribitAdapter(deribit_config)
        
        # 验证rate limiting配置
        assert deribit_adapter.max_requests_per_minute == 300
        assert deribit_adapter.max_matching_engine_requests == 20
        assert hasattr(deribit_adapter, '_rate_limit_lock')
    
    @pytest.mark.asyncio
    async def test_websocket_configuration_integration(self):
        """测试WebSocket配置集成"""
        ws_config_loader = get_websocket_config_loader()
        
        # 测试Binance WebSocket配置
        binance_config = ws_config_loader.load_config('binance')
        assert binance_config.exchange == 'binance'
        assert binance_config.ping_pong['interval'] == 20
        assert binance_config.ping_pong['format'] == 'json'
        
        # 测试OKX WebSocket配置
        okx_config = ws_config_loader.load_config('okx')
        assert okx_config.exchange == 'okx'
        assert okx_config.ping_pong['interval'] == 25
        assert okx_config.ping_pong['format'] == 'string'
        
        # 测试Deribit WebSocket配置
        deribit_config = ws_config_loader.load_config('deribit')
        assert deribit_config.exchange == 'deribit'
        assert deribit_config.heartbeat['interval'] == 60
        assert deribit_config.heartbeat['auto_heartbeat'] is True
    
    @pytest.mark.asyncio
    async def test_data_flow_integration(self, mock_normalizer, mock_nats_client):
        """测试完整数据流集成"""
        # 1. 创建模拟数据
        trade_data = {
            'e': 'trade',
            's': 'BTCUSDT',
            'p': '50000.00',
            'q': '1.0',
            'T': int(time.time() * 1000)
        }
        
        # 2. 数据标准化
        normalized_trade = mock_normalizer.normalize_trade(trade_data)
        
        # 3. 数据质量验证
        validator = get_data_quality_validator()
        data_point = DataPoint(
            timestamp=trade_data['T'],
            symbol=trade_data['s'],
            exchange='binance',
            data_type='trade',
            data=normalized_trade
        )
        
        validation_result = validator.validate_data_point(data_point)
        assert validation_result.valid is True
        
        # 4. NATS发布
        subject = f"trade-data.binance.{trade_data['s']}"
        await mock_nats_client.publish(subject, json.dumps(normalized_trade).encode())
        
        # 验证发布调用
        mock_nats_client.publish.assert_called_with(
            subject, 
            json.dumps(normalized_trade).encode()
        )
    
    @pytest.mark.asyncio
    async def test_error_handling_integration(self, data_collector_service):
        """测试错误处理集成"""
        service = data_collector_service
        
        # 测试服务状态
        status = await service.get_status()
        assert 'service_name' in status
        assert 'start_time' in status
        assert 'is_initialized' in status
        
        # 测试健康检查
        health = await service.health_check()
        assert isinstance(health, dict)
    
    @pytest.mark.asyncio
    async def test_performance_integration(self, mock_normalizer, mock_nats_client):
        """测试性能集成"""
        # 创建OrderBook Manager
        config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            symbols=['BTCUSDT'],
            snapshot_interval=10
        )
        orderbook_manager = OrderBookManager(config, mock_normalizer, mock_nats_client)
        
        # 模拟高频数据处理
        num_operations = 100
        start_time = time.time()
        
        for i in range(num_operations):
            # 模拟数据验证
            validator = get_data_quality_validator()
            data_point = DataPoint(
                timestamp=int(time.time() * 1000),
                symbol='BTCUSDT',
                exchange='binance',
                data_type='trade',
                data={'price': f'{50000 + i}', 'quantity': '1.0'}
            )
            
            result = validator.validate_data_point(data_point)
            assert result.valid is True
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # 验证性能（100个操作应该在1秒内完成）
        assert total_time < 1.0, f"性能测试失败: {total_time:.4f}s"
        
        # 验证统计信息
        stats = validator.get_stats()
        assert stats['total_processed'] >= num_operations
        assert stats['valid_data'] >= num_operations


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
