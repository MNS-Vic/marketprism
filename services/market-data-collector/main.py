"""
Market Data Collector Service - Phase 2
基于成熟的python-collector代码，重构为微服务架构

这是MarketPrism微服务架构的核心数据采集服务，负责：
1. 多交易所实时数据采集（Binance、OKX、Deribit等）  
2. 数据标准化和验证
3. 通过NATS发布到消息队列
4. 性能监控和健康检查
5. 动态订阅管理

复用components:
- services/python-collector/src/marketprism_collector/ (完整功能)
- core/service_framework.py (微服务框架)
- config/services.yaml (统一配置)
"""

import asyncio
import sys
import os
from pathlib import Path
from typing import Dict, Any, Optional
import structlog
from datetime import datetime

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "services" / "python-collector" / "src"))

# 导入微服务框架
from core.service_framework import BaseService

# 导入成熟的python-collector组件
try:
    from marketprism_collector import MarketDataCollector, Config
    from marketprism_collector.config import Config as CollectorConfig
    from marketprism_collector.types import DataType, CollectorMetrics
    COLLECTOR_AVAILABLE = True
except ImportError as e:
    print(f"警告: 无法导入python-collector组件: {e}")
    COLLECTOR_AVAILABLE = False
    MarketDataCollector = None
    CollectorConfig = None


class MarketDataCollectorService(BaseService):
    """
    市场数据采集微服务
    
    基于成熟的python-collector代码，提供：
    - 多交易所数据采集（Binance、OKX、Deribit）
    - 实时WebSocket数据流
    - 数据标准化和验证
    - NATS消息发布
    - REST API接口
    - 性能监控和健康检查
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(
            service_name="market-data-collector",
            service_version="1.0.0",
            service_port=config.get('port', 8081),
            config=config
        )
        
        self.logger = structlog.get_logger(__name__)
        
        # Python Collector 实例
        self.python_collector: Optional[MarketDataCollector] = None
        self.collector_config: Optional[CollectorConfig] = None
        
        # 服务状态
        self.exchanges_status: Dict[str, Dict[str, Any]] = {}
        self.data_stats: Dict[str, int] = {
            'trades_processed': 0,
            'orderbooks_processed': 0, 
            'tickers_processed': 0,
            'klines_processed': 0,
            'total_messages': 0,
            'errors': 0
        }
        
        # 支持的交易所和数据类型
        self.supported_exchanges = ['binance', 'okx', 'deribit']
        self.supported_data_types = [
            DataType.TRADE, DataType.ORDERBOOK, 
            DataType.TICKER, DataType.KLINE,
            DataType.FUNDING_RATE, DataType.OPEN_INTEREST
        ]
        
        self.logger.info(
            "Market Data Collector Service 初始化完成",
            supported_exchanges=self.supported_exchanges,
            collector_available=COLLECTOR_AVAILABLE
        )
    
    async def initialize_service(self) -> bool:
        """初始化数据采集服务"""
        try:
            if not COLLECTOR_AVAILABLE:
                self.logger.error("Python Collector组件不可用，服务无法启动")
                return False
            
            # 创建Python Collector配置
            collector_config_path = self.config.get(
                'collector_config_path', 
                str(project_root / "services" / "python-collector" / "config" / "collector.yaml")
            )
            
            # 检查配置文件是否存在
            if not Path(collector_config_path).exists():
                self.logger.warning(f"配置文件不存在: {collector_config_path}，使用默认配置")
                self.collector_config = self._create_default_collector_config()
            else:
                self.collector_config = CollectorConfig.load_from_file(collector_config_path)
            
            # 应用微服务特定配置覆盖
            self._apply_microservice_config_overrides()
            
            # 创建Python Collector实例
            self.python_collector = MarketDataCollector(self.collector_config)
            
            # 初始化交易所状态
            self._initialize_exchanges_status()
            
            self.logger.info("数据采集服务初始化成功")
            return True
            
        except Exception as e:
            self.logger.error(f"数据采集服务初始化失败: {e}")
            return False
    
    async def start_service(self) -> bool:
        """启动数据采集服务"""
        try:
            if not self.python_collector:
                self.logger.error("Python Collector未初始化")
                return False
            
            # 启动Python Collector
            success = await self.python_collector.start()
            if not success:
                self.logger.error("Python Collector启动失败")
                return False
            
            # 启动性能监控
            asyncio.create_task(self._monitor_performance())
            
            # 启动状态更新
            asyncio.create_task(self._update_exchanges_status())
            
            self.logger.info("Market Data Collector Service 启动成功")
            return True
            
        except Exception as e:
            self.logger.error(f"启动数据采集服务失败: {e}")
            return False
    
    async def stop_service(self) -> bool:
        """停止数据采集服务"""
        try:
            if self.python_collector:
                await self.python_collector.stop()
                self.logger.info("Python Collector已停止")
            
            self.logger.info("Market Data Collector Service 已停止")
            return True
            
        except Exception as e:
            self.logger.error(f"停止数据采集服务失败: {e}")
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        health_status = await super().health_check()
        
        # 添加Python Collector健康状态
        if self.python_collector:
            try:
                collector_metrics = self.python_collector.get_metrics()
                collector_health = {
                    'running': self.python_collector.is_running,
                    'start_time': self.python_collector.start_time.isoformat() if self.python_collector.start_time else None,
                    'uptime_seconds': collector_metrics.uptime_seconds,
                    'messages_processed': collector_metrics.messages_processed,
                    'errors_count': collector_metrics.errors_count,
                    'exchanges': len(self.python_collector.exchange_adapters),
                    'active_exchanges': [
                        name for name, adapter in self.python_collector.exchange_adapters.items()
                        if hasattr(adapter, 'is_connected') and adapter.is_connected
                    ]
                }
                health_status['collector'] = collector_health
                
            except Exception as e:
                health_status['collector'] = {'error': str(e)}
        else:
            health_status['collector'] = {'status': 'not_initialized'}
        
        # 添加交易所状态
        health_status['exchanges'] = self.exchanges_status
        
        # 添加数据统计
        health_status['data_stats'] = self.data_stats
        
        return health_status
    
    def _create_default_collector_config(self) -> CollectorConfig:
        """创建默认的Collector配置"""
        try:
            # 创建最小化的配置
            config_dict = {
                'collector': {
                    'use_real_exchanges': True,
                    'log_level': 'INFO',
                    'http_port': 8082,  # 避免与微服务端口冲突
                    'max_reconnect_attempts': 5,
                    'enable_orderbook_manager': True,
                    'enable_top_trader_collector': True,
                    'enable_scheduler': False  # 微服务模式下禁用调度器
                },
                'nats': {
                    'url': self.config.get('nats_url', 'nats://localhost:4222'),
                    'client_name': 'marketprism-collector-service',
                    'streams': {
                        'MARKET_DATA': {
                            'subjects': ['market.>'],
                            'retention': 'limits',
                            'max_age': 3600,
                            'max_msgs': 1000000
                        }
                    }
                },
                'exchanges': {
                    'configs': []  # 动态配置
                },
                'proxy': {
                    'enabled': False
                }
            }
            
            # 添加交易所配置
            self._add_exchange_configs(config_dict)
            
            return CollectorConfig.from_dict(config_dict)
            
        except Exception as e:
            self.logger.error(f"创建默认配置失败: {e}")
            raise
    
    def _add_exchange_configs(self, config_dict: Dict[str, Any]):
        """添加交易所配置"""
        # Binance配置
        binance_config = {
            'exchange': 'binance',
            'market_type': 'futures',
            'enabled': True,
            'base_url': 'https://fapi.binance.com',
            'ws_url': 'wss://fstream.binance.com/ws',
            'data_types': ['trade', 'orderbook', 'ticker'],
            'symbols': ['BTCUSDT', 'ETHUSDT', 'BNBUSDT'],
            'ping_interval': 180,
            'enable_ping': True
        }
        config_dict['exchanges']['configs'].append(binance_config)
        
        # OKX配置  
        okx_config = {
            'exchange': 'okx',
            'market_type': 'futures',
            'enabled': True,
            'base_url': 'https://www.okx.com',
            'ws_url': 'wss://ws.okx.com:8443/ws/v5/public',
            'data_types': ['trade', 'orderbook', 'ticker'],
            'symbols': ['BTC-USDT', 'ETH-USDT', 'BNB-USDT'],
            'ping_interval': 25,
            'enable_ping': True
        }
        config_dict['exchanges']['configs'].append(okx_config)
        
        # Deribit配置
        deribit_config = {
            'exchange': 'deribit',
            'market_type': 'futures',
            'enabled': self.config.get('enable_deribit', False),  # 默认禁用
            'base_url': 'https://www.deribit.com',
            'ws_url': 'wss://www.deribit.com/ws/api/v2',
            'data_types': ['trade', 'orderbook'],
            'symbols': ['BTC-PERPETUAL', 'ETH-PERPETUAL'],
            'ping_interval': 60,
            'enable_ping': True
        }
        config_dict['exchanges']['configs'].append(deribit_config)
    
    def _apply_microservice_config_overrides(self):
        """应用微服务特定的配置覆盖"""
        if not self.collector_config:
            return
        
        # 覆盖NATS配置
        nats_url = self.config.get('nats_url')
        if nats_url and hasattr(self.collector_config, 'nats'):
            self.collector_config.nats.url = nats_url
        
        # 覆盖HTTP端口（避免冲突）
        if hasattr(self.collector_config, 'collector'):
            self.collector_config.collector.http_port = 8082
        
        # 覆盖日志级别
        log_level = self.config.get('log_level')
        if log_level and hasattr(self.collector_config, 'collector'):
            self.collector_config.collector.log_level = log_level
    
    def _initialize_exchanges_status(self):
        """初始化交易所状态"""
        for exchange in self.supported_exchanges:
            self.exchanges_status[exchange] = {
                'enabled': True,
                'connected': False,
                'last_message_time': None,
                'messages_count': 0,
                'errors_count': 0,
                'supported_symbols': [],
                'active_subscriptions': []
            }
    
    async def _monitor_performance(self):
        """性能监控循环"""
        while True:
            try:
                if self.python_collector:
                    metrics = self.python_collector.get_metrics()
                    
                    # 更新数据统计
                    self.data_stats['total_messages'] = metrics.messages_processed
                    self.data_stats['errors'] = metrics.errors_count
                    
                    # 记录到service metrics
                    self.record_metric('messages_processed_total', metrics.messages_processed)
                    self.record_metric('messages_published_total', metrics.messages_published)
                    self.record_metric('errors_total', metrics.errors_count)
                    self.record_metric('uptime_seconds', metrics.uptime_seconds)
                
                await asyncio.sleep(30)  # 30秒更新一次
                
            except Exception as e:
                self.logger.error(f"性能监控错误: {e}")
                await asyncio.sleep(5)
    
    async def _update_exchanges_status(self):
        """更新交易所状态循环"""
        while True:
            try:
                if self.python_collector and self.python_collector.exchange_adapters:
                    for adapter_key, adapter in self.python_collector.exchange_adapters.items():
                        try:
                            # 解析交易所名称
                            exchange_name = adapter_key.split('_')[0] if '_' in adapter_key else adapter_key
                            
                            if exchange_name in self.exchanges_status:
                                # 更新连接状态
                                self.exchanges_status[exchange_name]['connected'] = getattr(adapter, 'is_connected', False)
                                
                                # 获取统计信息
                                if hasattr(adapter, 'get_stats'):
                                    stats = adapter.get_stats()
                                    self.exchanges_status[exchange_name]['messages_count'] = stats.get('messages_received', 0)
                                    self.exchanges_status[exchange_name]['last_message_time'] = stats.get('last_message_time')
                                    self.exchanges_status[exchange_name]['errors_count'] = stats.get('error_count', 0)
                        
                        except Exception as e:
                            self.logger.warning(f"更新交易所状态失败 {adapter_key}: {e}")
                
                await asyncio.sleep(15)  # 15秒更新一次
                
            except Exception as e:
                self.logger.error(f"交易所状态更新错误: {e}")
                await asyncio.sleep(5)
    
    async def get_collector_status(self) -> Dict[str, Any]:
        """获取采集器状态"""
        try:
            if not self.python_collector:
                return {'status': 'not_initialized'}
            
            metrics = self.python_collector.get_metrics()
            
            status = {
                'service': 'market-data-collector',
                'running': self.python_collector.is_running,
                'start_time': self.python_collector.start_time.isoformat() if self.python_collector.start_time else None,
                'uptime_seconds': metrics.uptime_seconds,
                'collector_metrics': {
                    'messages_processed': metrics.messages_processed,
                    'messages_published': metrics.messages_published,
                    'errors_count': metrics.errors_count,
                    'last_message_time': metrics.last_message_time.isoformat() if metrics.last_message_time else None
                },
                'exchanges': self.exchanges_status,
                'data_stats': self.data_stats,
                'supported_exchanges': self.supported_exchanges,
                'supported_data_types': [dt.value for dt in self.supported_data_types]
            }
            
            return status
            
        except Exception as e:
            return {'status': 'error', 'error': str(e)}
    
    async def get_exchange_stats(self, exchange_name: str) -> Dict[str, Any]:
        """获取指定交易所统计信息"""
        try:
            if exchange_name not in self.supported_exchanges:
                return {'error': f'Unsupported exchange: {exchange_name}'}
            
            if not self.python_collector or not self.python_collector.exchange_adapters:
                return {'error': 'Collector not initialized'}
            
            # 查找对应的adapter
            adapter = None
            for adapter_key, adapter_instance in self.python_collector.exchange_adapters.items():
                if adapter_key.startswith(exchange_name):
                    adapter = adapter_instance
                    break
            
            if not adapter:
                return {'error': f'Exchange {exchange_name} adapter not found'}
            
            # 获取adapter统计
            stats = {}
            if hasattr(adapter, 'get_stats'):
                stats = adapter.get_stats()
            elif hasattr(adapter, 'get_enhanced_stats'):
                stats = adapter.get_enhanced_stats()
            
            # 合并状态信息
            exchange_status = self.exchanges_status.get(exchange_name, {})
            
            return {
                'exchange': exchange_name,
                'status': exchange_status,
                'adapter_stats': stats,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {'error': str(e)}
    
    async def control_exchange_subscription(self, exchange_name: str, action: str, 
                                          symbols: list = None, data_types: list = None) -> Dict[str, Any]:
        """控制交易所订阅"""
        try:
            if exchange_name not in self.supported_exchanges:
                return {'success': False, 'error': f'Unsupported exchange: {exchange_name}'}
            
            if not self.python_collector:
                return {'success': False, 'error': 'Collector not initialized'}
            
            # 准备订阅命令
            command = {
                'action': action,  # subscribe/unsubscribe
                'exchange': exchange_name,
                'symbols': symbols or ['BTC-USDT'],
                'data_types': data_types or ['trade', 'ticker']
            }
            
            # 使用Python Collector的动态订阅功能
            if hasattr(self.python_collector, 'handle_dynamic_subscription_command'):
                result = await self.python_collector.handle_dynamic_subscription_command(command)
                return result
            else:
                return {
                    'success': False, 
                    'error': 'Dynamic subscription not supported by current collector version'
                }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}


async def main():
    """主函数"""
    try:
        # 加载配置
        import yaml
        config_path = project_root / "config" / "services.yaml"
        
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                services_config = yaml.safe_load(f)
            config = services_config.get('market-data-collector', {})
        else:
            # 默认配置
            config = {
                'port': 8081,
                'nats_url': 'nats://localhost:4222',
                'log_level': 'INFO',
                'enable_deribit': False
            }
        
        # 创建并启动服务
        service = MarketDataCollectorService(config)
        
        # 注册API路由
        @service.app.get("/api/v1/status")
        async def get_status(request):
            from aiohttp import web
            status = await service.get_collector_status()
            return web.json_response(status)
        
        @service.app.get("/api/v1/exchanges/{exchange_name}/stats")
        async def get_exchange_stats(request):
            from aiohttp import web
            exchange_name = request.match_info['exchange_name']
            stats = await service.get_exchange_stats(exchange_name)
            return web.json_response(stats)
        
        @service.app.post("/api/v1/exchanges/{exchange_name}/subscribe")
        async def control_subscription(request):
            from aiohttp import web
            exchange_name = request.match_info['exchange_name']
            
            try:
                data = await request.json()
                action = data.get('action', 'subscribe')
                symbols = data.get('symbols', ['BTC-USDT'])
                data_types = data.get('data_types', ['trade', 'ticker'])
                
                result = await service.control_exchange_subscription(
                    exchange_name, action, symbols, data_types
                )
                return web.json_response(result)
                
            except Exception as e:
                return web.json_response(
                    {'success': False, 'error': str(e)}, 
                    status=400
                )
        
        # 启动服务
        await service.run()
        
    except KeyboardInterrupt:
        print("服务被用户中断")
    except Exception as e:
        print(f"服务启动失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())