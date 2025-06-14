"""
统一交易所适配器工厂 - 整合智能选择和管理功能

基于用户反馈简化架构，统一工厂设计：
- 整合基础工厂和智能工厂功能到一个文件
- 整合多交易所管理器功能到一个文件
- 所有适配器都继承ExchangeAdapter，支持完整的ping/pong机制  
- 移除enhanced/standard分离，简化为单一适配器模式
- 保持智能适配器选择和配置管理功能
- 添加企业级多交易所管理和监控功能
"""

from typing import Dict, Optional, Type, Any, List, Tuple, Union, Set, Callable
import logging
import structlog
import asyncio
import threading
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from .base import ExchangeAdapter
from .binance import BinanceAdapter
from .okx import OKXAdapter 
from .deribit import DeribitAdapter
from ..data_types import ExchangeConfig, Exchange, MarketType, DataType


class AdapterCapability(Enum):
    """适配器能力枚举"""
    BASIC_CONNECTION = "basic_connection"
    PING_PONG_MAINTENANCE = "ping_pong_maintenance"
    SESSION_MANAGEMENT = "session_management"
    RATE_LIMIT_HANDLING = "rate_limit_handling"
    DYNAMIC_SUBSCRIPTION = "dynamic_subscription"
    AUTHENTICATION = "authentication"
    USER_DATA_STREAM = "user_data_stream"
    ADVANCED_RECONNECT = "advanced_reconnect"
    ERROR_RECOVERY = "error_recovery"
    PERFORMANCE_MONITORING = "performance_monitoring"


@dataclass
class ExchangeHealth:
    """交易所健康状况"""
    exchange_name: str
    is_healthy: bool = True
    last_check: datetime = field(default_factory=datetime.now)
    error_count: int = 0
    last_error: Optional[str] = None
    uptime_percent: float = 100.0
    avg_response_time: float = 0.0


class ExchangeRequirements:
    """交易所特殊要求定义"""
    
    # Binance特殊要求
    BINANCE_REQUIREMENTS = {
        AdapterCapability.PING_PONG_MAINTENANCE: {
            'required': True,
            'interval': 300,  # 5分钟
            'format': 'json',
            'description': 'Binance需要定期ping维持连接'
        },
        AdapterCapability.SESSION_MANAGEMENT: {
            'required': False,
            'websocket_api': True,
            'user_data_stream': True,
            'description': 'Binance支持WebSocket API和用户数据流'
        },
        AdapterCapability.RATE_LIMIT_HANDLING: {
            'required': True,
            'weight_limit': 1200,
            'time_window': 60,
            'description': 'Binance有严格的请求权重限制'
        },
        AdapterCapability.DYNAMIC_SUBSCRIPTION: {
            'required': True,
            'method': 'SUBSCRIBE/UNSUBSCRIBE',
            'description': 'Binance支持动态订阅/取消订阅'
        }
    }
    
    # OKX特殊要求
    OKX_REQUIREMENTS = {
        AdapterCapability.PING_PONG_MAINTENANCE: {
            'required': True,
            'interval': 30,  # 30秒
            'format': 'string',
            'description': 'OKX需要30秒发送字符串ping'
        },
        AdapterCapability.AUTHENTICATION: {
            'required': False,
            'method': 'hmac_sha256',
            'fields': ['api_key', 'secret_key', 'passphrase'],
            'description': 'OKX私有频道需要API密钥认证'
        },
        AdapterCapability.SESSION_MANAGEMENT: {
            'required': True,
            'login_required': True,
            'description': 'OKX需要登录流程管理会话'
        },
        AdapterCapability.DYNAMIC_SUBSCRIPTION: {
            'required': True,
            'method': 'op:subscribe/unsubscribe',
            'description': 'OKX支持op操作动态订阅'
        }
    }
    
    # 其他交易所要求（可扩展）
    DERIBIT_REQUIREMENTS = {
        AdapterCapability.AUTHENTICATION: {
            'required': False,
            'method': 'client_credentials',
            'description': 'Deribit公开数据不需要认证，私有数据需要OAuth2'
        },
        AdapterCapability.PING_PONG_MAINTENANCE: {
            'required': True,
            'interval': 30,  # 30秒心跳
            'format': 'aiohttp_heartbeat',
            'description': 'Deribit使用aiohttp心跳维持连接'
        },
        AdapterCapability.ADVANCED_RECONNECT: {
            'required': True,
            'method': 'aiohttp_auto_reconnect',
            'max_attempts': 5,
            'description': 'Deribit支持智能重连和连接恢复'
        },
        AdapterCapability.RATE_LIMIT_HANDLING: {
            'required': True,
            'method': 'request_throttling',
            'description': 'Deribit需要请求限流处理'
        },
        AdapterCapability.PERFORMANCE_MONITORING: {
            'required': True,
            'metrics': ['messages_received', 'messages_processed', 'subscription_errors'],
            'description': 'Deribit提供增强统计监控'
        }
    }


class ExchangeFactory:
    """
    统一交易所适配器工厂类 - 整合智能选择和管理功能
    
    架构简化V2.0：
    - 统一适配器：所有适配器都继承ExchangeAdapter，支持完整ping/pong
    - 智能选择：根据配置自动选择最适合的实现
    - 简化配置：移除enhanced/standard分离
    - 整合功能：将基础工厂、智能工厂、管理器合并为一个
    - 企业级管理：多交易所生命周期管理、健康监控、性能统计
    
    功能特性：
    - 统一适配器创建接口
    - 智能适配器能力分析和选择
    - 配置验证和管理
    - 实例缓存和复用
    - 错误处理和日志记录
    - 支持插件式扩展
    - 多交易所统一管理
    - 健康监控和故障检测
    - 并发数据聚合
    - 性能监控和统计
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.struct_logger = structlog.get_logger(__name__)
        
        # 统一适配器映射（都支持完整功能）
        self._adapter_classes: Dict[str, Type[ExchangeAdapter]] = {
            'binance': BinanceAdapter,        # 完整功能：ping/pong + 会话管理 + 动态订阅
            'okx': OKXAdapter,               # 完整功能：ping/pong + 认证 + 动态订阅
            'deribit': DeribitAdapter        # 统一增强功能：aiohttp + 代理 + 重连
        }
        
        # Exchange枚举映射
        self._exchange_mapping: Dict[Exchange, Type[ExchangeAdapter]] = {
            Exchange.BINANCE: BinanceAdapter,
            Exchange.OKX: OKXAdapter,
            Exchange.DERIBIT: DeribitAdapter,  # 启用Deribit支持
        }
        
        # 交易所要求映射
        self._exchange_requirements = {
            Exchange.BINANCE: ExchangeRequirements.BINANCE_REQUIREMENTS,
            Exchange.OKX: ExchangeRequirements.OKX_REQUIREMENTS,
            Exchange.DERIBIT: ExchangeRequirements.DERIBIT_REQUIREMENTS,  # 启用Deribit要求
        }
        
        self._adapter_cache: Dict[str, ExchangeAdapter] = {}
        self._default_configs: Dict[str, Dict[str, Any]] = {
            'binance': {
                'base_url': 'https://api.binance.com',
                'ws_url': 'wss://stream.binance.com:9443',
                'timeout': 30,
                'retries': 3,
                'ping_interval': 180,  # 3分钟
                'enable_ping': True
            },
            'okx': {
                'base_url': 'https://www.okx.com',
                'ws_url': 'wss://ws.okx.com:8443',
                'timeout': 30,
                'retries': 3,
                'ping_interval': 25,   # 25秒
                'enable_ping': True
            },
            'deribit': {
                'base_url': 'https://www.deribit.com',
                'ws_url': 'wss://www.deribit.com/ws/api/v2',
                'timeout': 30,
                'retries': 3,
                'ping_interval': 60,   # 1分钟
                'enable_ping': True
            }
        }
        
        # ===== 多交易所管理功能（整合自manager.py）=====
        
        # 管理的适配器实例
        self._managed_adapters: Dict[str, ExchangeAdapter] = {}
        self._adapter_configs: Dict[str, Dict[str, Any]] = {}
        
        # 健康监控
        self._health_status: Dict[str, ExchangeHealth] = {}
        self._health_check_interval = 60  # 秒
        self._health_check_task: Optional[asyncio.Task] = None
        
        # 性能统计
        self._stats: Dict[str, Dict[str, Any]] = {}
        
        # 事件回调
        self._event_callbacks: Dict[str, List[Callable]] = {
            'adapter_added': [],
            'adapter_removed': [],
            'adapter_failed': [],
            'adapter_recovered': []
        }
        
        # 线程池
        self._thread_pool = ThreadPoolExecutor(max_workers=10, thread_name_prefix="ExchangeFactory")
        self._lock = threading.RLock()
        
        self.logger.info(
            "统一交易所工厂已初始化（整合智能选择和管理功能），支持交易所: %s，架构: %s",
            list(self._adapter_classes.keys()),
            "unified_intelligent_factory_with_management"
        )
    
    def create_adapter(self, exchange_name: str, config: Optional[Dict[str, Any]] = None, 
                      use_cache: bool = True, use_intelligent_selection: bool = True) -> Optional[ExchangeAdapter]:
        """
        创建交易所适配器（智能选择版本）
        
        Args:
            exchange_name: 交易所名称
            config: 配置字典
            use_cache: 是否使用缓存
            use_intelligent_selection: 是否使用智能适配器选择
            
        Returns:
            交易所适配器实例
        """
        try:
            if exchange_name not in self._adapter_classes:
                self.logger.error("不支持的交易所: %s", exchange_name)
                return None
            
            # 处理配置
            final_config = self._prepare_config(exchange_name, config)
            
            # 智能适配器选择
            if use_intelligent_selection:
                try:
                    adapter = self._create_intelligent_adapter(final_config)
                    self.logger.info("使用智能工厂创建适配器: %s", exchange_name)
                    return adapter
                except Exception as e:
                    self.logger.warning("智能工厂失败，回退到标准工厂: %s", str(e))
            
            # 标准适配器创建
            return self._create_adapter_direct(exchange_name, final_config, use_cache)
            
        except Exception as e:
            self.logger.error("创建 %s 适配器失败: %s", exchange_name, str(e))
            return None
    
    def _create_intelligent_adapter(self, config: ExchangeConfig) -> ExchangeAdapter:
        """
        智能创建适配器
        
        根据配置需求自动选择最佳适配器实现
        """
        try:
            exchange = config.exchange
            self.struct_logger.info("分析交易所适配器需求", exchange=exchange.value)
            
            # 分析配置需求
            required_capabilities = self._analyze_config_requirements(config)
            
            # 获取适配器类
            adapter_class = self._exchange_mapping.get(exchange)
            if not adapter_class:
                raise ValueError(f"不支持的交易所: {exchange.value}")
            
            # 创建适配器实例
            adapter = adapter_class(config)
            
            self.struct_logger.info(
                "智能适配器选择完成",
                exchange=exchange.value,
                adapter_class=adapter_class.__name__,
                required_capabilities=[cap.value for cap in required_capabilities]
            )
            
            return adapter
            
        except Exception as e:
            self.struct_logger.error("创建智能适配器失败", exchange=exchange.value, exc_info=True)
            raise
    
    def _analyze_config_requirements(self, config: ExchangeConfig) -> Set[AdapterCapability]:
        """分析配置的能力需求"""
        required_capabilities = set()
        
        # 基本连接是必需的
        required_capabilities.add(AdapterCapability.BASIC_CONNECTION)
        
        # 检查是否需要认证
        if hasattr(config, 'api_key') and config.api_key:
            required_capabilities.add(AdapterCapability.AUTHENTICATION)
            required_capabilities.add(AdapterCapability.USER_DATA_STREAM)
        
        # 检查是否需要动态订阅
        if getattr(config, 'enable_dynamic_subscription', False):
            required_capabilities.add(AdapterCapability.DYNAMIC_SUBSCRIPTION)
        
        # 检查是否需要高级重连
        if getattr(config, 'enable_advanced_reconnect', False):
            required_capabilities.add(AdapterCapability.ADVANCED_RECONNECT)
        
        # 检查是否需要性能监控
        if getattr(config, 'enable_performance_monitoring', False):
            required_capabilities.add(AdapterCapability.PERFORMANCE_MONITORING)
        
        # 检查是否配置了严格的错误处理
        if getattr(config, 'strict_error_handling', False):
            required_capabilities.add(AdapterCapability.ERROR_RECOVERY)
        
        return required_capabilities
    
    def _create_adapter_direct(self, exchange_name: str, config: ExchangeConfig, use_cache: bool = True) -> Optional[ExchangeAdapter]:
        """直接创建适配器"""
        try:
            # 生成缓存键
            cache_key = f"unified_{exchange_name}_{hash(str(config))}"
            
            # 检查缓存
            if use_cache and cache_key in self._adapter_cache:
                self.logger.debug("从缓存获取适配器: %s", exchange_name)
                return self._adapter_cache[cache_key]
            
            # 获取适配器类
            adapter_class = self._adapter_classes[exchange_name]
            
            # 创建实例
            adapter = adapter_class(config)
            
            # 缓存实例
            if use_cache:
                self._adapter_cache[cache_key] = adapter
            
            self.logger.info("成功创建统一适配器: %s", exchange_name)
            return adapter
            
        except Exception as e:
            self.logger.error("创建适配器失败: %s", str(e))
            return None
    
    def create_adapter_from_config(self, exchange_name: str, 
                                  exchange_config: ExchangeConfig, 
                                  use_intelligent_selection: bool = True) -> Optional[ExchangeAdapter]:
        """
        从ExchangeConfig对象创建适配器
        """
        try:
            if exchange_name not in self._adapter_classes:
                self.logger.error("不支持的交易所: %s", exchange_name)
                return None
            
            # 智能适配器选择
            if use_intelligent_selection:
                try:
                    adapter = self._create_intelligent_adapter(exchange_config)
                    self.logger.info("使用智能工厂从ExchangeConfig创建适配器: %s", exchange_name)
                    return adapter
                except Exception as e:
                    self.logger.warning("智能工厂失败，回退到标准工厂: %s", str(e))
            
            # 标准适配器创建
            return self._create_adapter_direct(exchange_name, exchange_config, use_cache=False)
            
        except Exception as e:
            self.logger.error("从ExchangeConfig创建 %s 适配器失败: %s", exchange_name, str(e))
            return None
    
    def create_exchange_config(self, exchange_name: str, 
                              config_dict: Dict[str, Any]) -> Optional[ExchangeConfig]:
        """
        将字典配置转换为ExchangeConfig对象
        """
        try:
            # 获取默认配置
            default_config = self._default_configs.get(exchange_name, {})
            
            # 合并配置
            merged_config = {**default_config, **config_dict}
            
            # 设置必需字段的默认值
            if exchange_name == 'binance':
                return ExchangeConfig.for_binance(
                    market_type=MarketType.FUTURES,
                    api_key=merged_config.get('api_key'),
                    api_secret=merged_config.get('secret'),
                    symbols=merged_config.get('symbols', ['BTCUSDT']),
                    data_types=merged_config.get('data_types', [DataType.TRADE]),
                    ping_interval=merged_config.get('ping_interval', 180),
                    enable_ping=merged_config.get('enable_ping', True)
                )
            elif exchange_name == 'okx':
                return ExchangeConfig.for_okx(
                    market_type=MarketType.FUTURES,
                    api_key=merged_config.get('api_key'),
                    api_secret=merged_config.get('secret'),
                    passphrase=merged_config.get('passphrase'),
                    symbols=merged_config.get('symbols', ['BTC-USDT']),
                    data_types=merged_config.get('data_types', [DataType.TRADE]),
                    ping_interval=merged_config.get('ping_interval', 25),
                    enable_ping=merged_config.get('enable_ping', True)
                )
            else:
                return self._create_default_config(exchange_name)
                
        except Exception as e:
            self.logger.error("创建ExchangeConfig失败: %s", str(e))
            return None
    
    def _prepare_config(self, exchange_name: str, config: Optional[Dict[str, Any]]) -> ExchangeConfig:
        """准备最终配置"""
        if config is None:
            return self._create_default_config(exchange_name)
        
        return self.create_exchange_config(exchange_name, config)
    
    def _create_default_config(self, exchange_name: str) -> ExchangeConfig:
        """创建默认配置"""
        default_config = self._default_configs.get(exchange_name, {})
        
        if exchange_name == 'binance':
            return ExchangeConfig.for_binance(
                market_type=MarketType.FUTURES,
                symbols=['BTC-USDT'],
                data_types=[DataType.TRADE, DataType.ORDERBOOK]
            )
        elif exchange_name == 'okx':
            return ExchangeConfig.for_okx(
                market_type=MarketType.FUTURES,
                symbols=['BTC-USDT'],
                data_types=[DataType.TRADE, DataType.ORDERBOOK]
            )
        else:
            # 通用默认配置
            return ExchangeConfig(
                exchange=Exchange(exchange_name),
                market_type=MarketType.FUTURES,
                symbols=['BTC-USDT'],
                data_types=[DataType.TRADE, DataType.ORDERBOOK],
                **default_config
            )
    
    # ===== 多交易所管理功能（整合自manager.py）=====
    
    def add_managed_adapter(self, exchange_name: str, config: Optional[Dict[str, Any]] = None, 
                           adapter: Optional[ExchangeAdapter] = None) -> bool:
        """添加托管的交易所适配器"""
        try:
            with self._lock:
                if exchange_name in self._managed_adapters:
                    self.logger.warning("交易所 %s 适配器已存在，将替换", exchange_name)
                
                # 创建或使用提供的适配器
                if adapter is None:
                    adapter = self.create_adapter(exchange_name, config)
                    if adapter is None:
                        return False
                
                self._managed_adapters[exchange_name] = adapter
                self._adapter_configs[exchange_name] = config or {}
                
                # 初始化健康状态
                self._health_status[exchange_name] = ExchangeHealth(
                    exchange_name=exchange_name,
                    is_healthy=True,
                    last_check=datetime.now()
                )
                
                # 初始化统计
                self._stats[exchange_name] = {
                    'requests_total': 0,
                    'requests_successful': 0,
                    'requests_failed': 0,
                    'avg_response_time': 0.0,
                    'last_activity': None
                }
                
                self._trigger_event('adapter_added', exchange_name, adapter)
                self.logger.info("已添加托管交易所适配器: %s", exchange_name)
                return True
                
        except Exception as e:
            self.logger.error("添加托管交易所适配器失败 %s: %s", exchange_name, str(e))
            return False
    
    def remove_managed_adapter(self, exchange_name: str) -> bool:
        """移除托管的交易所适配器"""
        try:
            with self._lock:
                if exchange_name not in self._managed_adapters:
                    self.logger.warning("托管交易所 %s 适配器不存在", exchange_name)
                    return False
                
                adapter = self._managed_adapters.pop(exchange_name)
                self._adapter_configs.pop(exchange_name, None)
                self._health_status.pop(exchange_name, None)
                self._stats.pop(exchange_name, None)
                
                # 停止适配器（如果有停止方法）
                if hasattr(adapter, 'stop'):
                    try:
                        if asyncio.iscoroutinefunction(adapter.stop):
                            # 异步停止方法需要在事件循环中执行
                            try:
                                loop = asyncio.get_event_loop()
                                if loop.is_running():
                                    asyncio.create_task(adapter.stop())
                                else:
                                    loop.run_until_complete(adapter.stop())
                            except RuntimeError:
                                # 没有事件循环，跳过异步停止
                                pass
                        else:
                            adapter.stop()
                    except Exception as e:
                        self.logger.warning("停止适配器时出错: %s", str(e))
                
                self._trigger_event('adapter_removed', exchange_name, adapter)
                self.logger.info("已移除托管交易所适配器: %s", exchange_name)
                return True
                
        except Exception as e:
            self.logger.error("移除托管交易所适配器失败 %s: %s", exchange_name, str(e))
            return False
    
    def get_managed_adapter(self, exchange_name: str) -> Optional[ExchangeAdapter]:
        """获取指定的托管交易所适配器"""
        with self._lock:
            return self._managed_adapters.get(exchange_name)
    
    def get_all_managed_adapters(self) -> Dict[str, ExchangeAdapter]:
        """获取所有托管的适配器"""
        with self._lock:
            return self._managed_adapters.copy()
    
    def get_active_exchanges(self) -> List[str]:
        """获取活跃的交易所列表"""
        with self._lock:
            return [name for name, health in self._health_status.items() if health.is_healthy]
    
    def start_all_managed(self) -> Dict[str, bool]:
        """启动所有托管的适配器"""
        results = {}
        with self._lock:
            for exchange_name, adapter in self._managed_adapters.items():
                try:
                    if hasattr(adapter, 'start'):
                        if asyncio.iscoroutinefunction(adapter.start):
                            # 处理异步启动
                            try:
                                loop = asyncio.get_event_loop()
                                if loop.is_running():
                                    asyncio.create_task(adapter.start())
                                else:
                                    loop.run_until_complete(adapter.start())
                            except RuntimeError:
                                # 没有事件循环，创建新的
                                asyncio.run(adapter.start())
                        else:
                            adapter.start()
                    results[exchange_name] = True
                    self.logger.info("已启动托管交易所适配器: %s", exchange_name)
                except Exception as e:
                    results[exchange_name] = False
                    self.logger.error("启动托管交易所适配器失败 %s: %s", exchange_name, str(e))
        
        # 启动健康检查
        self._start_health_monitoring()
        return results
    
    def stop_all_managed(self) -> Dict[str, bool]:
        """停止所有托管的适配器"""
        results = {}
        
        # 停止健康检查
        self._stop_health_monitoring()
        
        with self._lock:
            for exchange_name, adapter in self._managed_adapters.items():
                try:
                    if hasattr(adapter, 'stop'):
                        if asyncio.iscoroutinefunction(adapter.stop):
                            # 处理异步停止
                            try:
                                loop = asyncio.get_event_loop()
                                if loop.is_running():
                                    asyncio.create_task(adapter.stop())
                                else:
                                    loop.run_until_complete(adapter.stop())
                            except RuntimeError:
                                # 没有事件循环，创建新的
                                asyncio.run(adapter.stop())
                        else:
                            adapter.stop()
                    results[exchange_name] = True
                    self.logger.info("已停止托管交易所适配器: %s", exchange_name)
                except Exception as e:
                    results[exchange_name] = False
                    self.logger.error("停止托管交易所适配器失败 %s: %s", exchange_name, str(e))
        
        return results
    
    def restart_managed_adapter(self, exchange_name: str) -> bool:
        """重启指定的托管适配器"""
        adapter = self.get_managed_adapter(exchange_name)
        if adapter is None:
            return False
        
        try:
            # 停止
            if hasattr(adapter, 'stop'):
                if asyncio.iscoroutinefunction(adapter.stop):
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.create_task(adapter.stop())
                        else:
                            loop.run_until_complete(adapter.stop())
                    except RuntimeError:
                        asyncio.run(adapter.stop())
                else:
                    adapter.stop()
            
            # 重新创建
            config = self._adapter_configs.get(exchange_name, {})
            new_adapter = self.create_adapter(exchange_name, config, use_cache=False)
            if new_adapter is None:
                return False
            
            # 替换
            with self._lock:
                self._managed_adapters[exchange_name] = new_adapter
            
            # 启动
            if hasattr(new_adapter, 'start'):
                if asyncio.iscoroutinefunction(new_adapter.start):
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.create_task(new_adapter.start())
                        else:
                            loop.run_until_complete(new_adapter.start())
                    except RuntimeError:
                        asyncio.run(new_adapter.start())
                else:
                    new_adapter.start()
            
            self.logger.info("已重启托管交易所适配器: %s", exchange_name)
            return True
            
        except Exception as e:
            self.logger.error("重启托管交易所适配器失败 %s: %s", exchange_name, str(e))
            return False
    
    def get_health_status(self) -> Dict[str, ExchangeHealth]:
        """获取所有托管交易所健康状态"""
        with self._lock:
            return self._health_status.copy()
    
    def get_performance_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有托管交易所性能统计"""
        with self._lock:
            return self._stats.copy()
    
    def check_adapter_health(self, exchange_name: str) -> bool:
        """检查指定适配器健康状态"""
        adapter = self.get_managed_adapter(exchange_name)
        if adapter is None:
            return False
        
        try:
            # 简单健康检查 - 尝试获取基本统计信息
            if hasattr(adapter, 'get_stats'):
                adapter.get_stats()
            elif hasattr(adapter, 'get_enhanced_stats'):
                adapter.get_enhanced_stats()
            else:
                # 默认认为健康（适配器存在且可访问）
                pass
            
            # 更新健康状态
            with self._lock:
                if exchange_name in self._health_status:
                    health = self._health_status[exchange_name]
                    health.is_healthy = True
                    health.last_check = datetime.now()
                    health.error_count = 0
                    health.last_error = None
            
            return True
            
        except Exception as e:
            # 更新健康状态
            with self._lock:
                if exchange_name in self._health_status:
                    health = self._health_status[exchange_name]
                    health.is_healthy = False
                    health.last_check = datetime.now()
                    health.error_count += 1
                    health.last_error = str(e)
            
            self.logger.warning("托管交易所 %s 健康检查失败: %s", exchange_name, str(e))
            return False
    
    def add_event_callback(self, event_type: str, callback: Callable):
        """添加事件回调"""
        if event_type in self._event_callbacks:
            self._event_callbacks[event_type].append(callback)
    
    def _start_health_monitoring(self):
        """启动健康监控"""
        if self._health_check_task is None or self._health_check_task.done():
            try:
                self._health_check_task = asyncio.create_task(self._health_check_loop())
            except RuntimeError:
                # 没有事件循环，跳过健康监控
                self.logger.warning("没有事件循环，跳过健康监控启动")
    
    def _stop_health_monitoring(self):
        """停止健康监控"""
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while True:
            try:
                exchanges = list(self._managed_adapters.keys())
                for exchange_name in exchanges:
                    self.check_adapter_health(exchange_name)
                
                await asyncio.sleep(self._health_check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("健康检查循环错误: %s", str(e))
                await asyncio.sleep(5)
    
    def _trigger_event(self, event_type: str, *args, **kwargs):
        """触发事件回调"""
        if event_type in self._event_callbacks:
            for callback in self._event_callbacks[event_type]:
                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    self.logger.error("事件回调执行失败 %s: %s", event_type, str(e))
    
    def _update_stats(self, exchange_name: str, success: bool, response_time: float):
        """更新统计信息"""
        with self._lock:
            if exchange_name in self._stats:
                stats = self._stats[exchange_name]
                stats['requests_total'] += 1
                if success:
                    stats['requests_successful'] += 1
                else:
                    stats['requests_failed'] += 1
                
                # 更新平均响应时间
                current_avg = stats['avg_response_time']
                total_requests = stats['requests_total']
                stats['avg_response_time'] = ((current_avg * (total_requests - 1)) + response_time) / total_requests
                stats['last_activity'] = datetime.now()

    # ===== 智能工厂功能方法 =====
    
    def get_adapter_capabilities(self, exchange: Union[Exchange, str], enhanced: bool = False) -> Dict[AdapterCapability, bool]:
        """获取适配器支持的能力"""
        if isinstance(exchange, str):
            if exchange not in self._adapter_classes:
                return {}
            adapter_class = self._adapter_classes[exchange]
        else:
            adapter_class = self._exchange_mapping.get(exchange)
        
        if not adapter_class:
            return {}
        
        # 检查适配器支持的能力
        capabilities = {}
        
        # 基础能力检查
        capabilities[AdapterCapability.BASIC_CONNECTION] = True
        
        # 检查是否有ping/pong方法
        if hasattr(adapter_class, '_send_exchange_ping') or hasattr(adapter_class, '_ping_maintenance_loop'):
            capabilities[AdapterCapability.PING_PONG_MAINTENANCE] = True
        
        # 检查是否有认证方法
        if hasattr(adapter_class, '_perform_login') or hasattr(adapter_class, 'authenticate'):
            capabilities[AdapterCapability.AUTHENTICATION] = True
        
        # 检查是否有动态订阅方法
        if hasattr(adapter_class, 'add_symbol_subscription'):
            capabilities[AdapterCapability.DYNAMIC_SUBSCRIPTION] = True
        
        # 检查是否有会话管理
        if hasattr(adapter_class, 'session_active') or hasattr(adapter_class, 'is_authenticated'):
            capabilities[AdapterCapability.SESSION_MANAGEMENT] = True
        
        # 检查是否有增强统计
        if hasattr(adapter_class, 'get_enhanced_stats'):
            capabilities[AdapterCapability.PERFORMANCE_MONITORING] = True
        
        return capabilities
    
    def validate_adapter_requirements(self, exchange: Union[Exchange, str], config: ExchangeConfig) -> Dict[str, Any]:
        """验证适配器是否满足配置要求"""
        validation_result = {
            'valid': True,
            'missing_capabilities': [],
            'warnings': [],
            'recommendations': []
        }
        
        try:
            # 分析配置需求
            required_capabilities = self._analyze_config_requirements(config)
            
            # 获取适配器能力
            adapter_capabilities = self.get_adapter_capabilities(exchange, enhanced=True)
            
            # 验证能力匹配
            for capability in required_capabilities:
                if not adapter_capabilities.get(capability, False):
                    validation_result['missing_capabilities'].append(capability.value)
                    validation_result['valid'] = False
            
            # 检查交易所特殊要求
            if isinstance(exchange, str):
                exchange_enum = Exchange(exchange)
            else:
                exchange_enum = exchange
                
            exchange_requirements = self._exchange_requirements.get(exchange_enum, {})
            for capability, requirement in exchange_requirements.items():
                if requirement.get('required', False):
                    if not adapter_capabilities.get(capability, False):
                        validation_result['warnings'].append(
                            f"交易所 {exchange_enum.value} 建议支持 {capability.value}: {requirement.get('description', '')}"
                        )
            
            self.struct_logger.info(
                "适配器需求验证完成",
                exchange=exchange,
                valid=validation_result['valid'],
                missing_count=len(validation_result['missing_capabilities'])
            )
            
        except Exception as e:
            validation_result['valid'] = False
            validation_result['error'] = str(e)
            self.struct_logger.error("适配器需求验证失败", exchange=exchange, exc_info=True)
        
        return validation_result
    
    def get_exchange_recommendations(self, exchange: Union[Exchange, str]) -> Dict[str, Any]:
        """获取交易所特定的配置建议"""
        if isinstance(exchange, str):
            exchange_enum = Exchange(exchange)
        else:
            exchange_enum = exchange
            
        requirements = self._exchange_requirements.get(exchange_enum, {})
        
        recommendations = {
            'exchange': exchange_enum.value,
            'suggested_config': {},
            'performance_tips': [],
            'best_practices': []
        }
        
        if exchange_enum == Exchange.BINANCE:
            recommendations['suggested_config'] = {
                'ping_interval': 180,
                'enable_dynamic_subscription': True,
                'enable_rate_limit_handling': True,
                'max_request_weight': 1200
            }
            recommendations['performance_tips'] = [
                "使用增量深度流 (@depth@100ms) 获得最佳性能",
                "启用请求权重监控避免限流",
                "考虑使用WebSocket API进行高级功能"
            ]
            recommendations['best_practices'] = [
                "定期发送ping维持连接",
                "监控请求权重避免超限",
                "实现优雅的重连策略"
            ]
        
        elif exchange_enum == Exchange.OKX:
            recommendations['suggested_config'] = {
                'ping_interval': 25,
                'enable_authentication': True,
                'enable_private_channels': False,
                'reconnect_delay': 1
            }
            recommendations['performance_tips'] = [
                "使用25秒ping间隔保持连接",
                "私有频道需要API密钥认证",
                "实现快速重连策略(1秒延迟)"
            ]
            recommendations['best_practices'] = [
                "处理登录响应和错误消息",
                "实现私有频道数据处理",
                "使用op操作进行订阅管理"
            ]
        
        return recommendations
    
    # ===== 基础工厂功能方法 =====
    
    def create_binance_adapter(self, config: Optional[Dict[str, Any]] = None) -> Optional[BinanceAdapter]:
        """创建Binance适配器"""
        return self.create_adapter('binance', config)
    
    def create_okx_adapter(self, config: Optional[Dict[str, Any]] = None) -> Optional[OKXAdapter]:
        """创建OKX适配器"""
        return self.create_adapter('okx', config)
    
    def create_deribit_adapter(self, config: Optional[Dict[str, Any]] = None) -> Optional[DeribitAdapter]:
        """创建Deribit适配器"""
        return self.create_adapter('deribit', config)
    
    def register_adapter(self, exchange_name: str, adapter_class: Type[ExchangeAdapter]):
        """注册新的适配器类"""
        self._adapter_classes[exchange_name] = adapter_class
        self.logger.info("注册新适配器: %s -> %s", exchange_name, adapter_class.__name__)
    
    def get_supported_exchanges(self) -> List[str]:
        """获取支持的交易所列表"""
        return list(self._adapter_classes.keys())
    
    def clear_cache(self):
        """清空适配器缓存"""
        self._adapter_cache.clear()
        self.logger.info("适配器缓存已清空")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return {
            'cache_size': len(self._adapter_cache),
            'cached_adapters': list(self._adapter_cache.keys()),
            'supported_exchanges': self.get_supported_exchanges()
        }
    
    def get_architecture_info(self) -> Dict[str, Any]:
        """获取架构信息"""
        return {
            'factory_type': 'unified_intelligent_factory_with_management',
            'supported_exchanges': self.get_supported_exchanges(),
            'adapter_classes': {
                name: cls.__name__ for name, cls in self._adapter_classes.items()
            },
            'cache_enabled': True,
            'intelligent_selection': True,
            'capabilities_supported': [cap.value for cap in AdapterCapability],
            'unified_architecture': True,
            'ping_pong_support': True,
            'management_features': {
                'health_monitoring': True,
                'performance_stats': True,
                'event_callbacks': True,
                'managed_adapters': len(self._managed_adapters)
            }
        }
    
    def __del__(self):
        """清理资源"""
        try:
            self._stop_health_monitoring()
            self._thread_pool.shutdown(wait=False)
        except:
            pass


# ===== 全局工厂实例和便利函数 =====

# 全局工厂实例
_factory_instance = None

def get_factory() -> ExchangeFactory:
    """获取全局工厂实例（单例模式）"""
    global _factory_instance
    if _factory_instance is None:
        _factory_instance = ExchangeFactory()
    return _factory_instance


def create_adapter(exchange_name: str, config: Optional[Dict[str, Any]] = None) -> Optional[ExchangeAdapter]:
    """便捷函数：创建适配器"""
    factory = get_factory()
    return factory.create_adapter(exchange_name, config)


def get_supported_exchanges() -> List[str]:
    """便捷函数：获取支持的交易所"""
    factory = get_factory()
    return factory.get_supported_exchanges()


def get_architecture_info() -> Dict[str, Any]:
    """便捷函数：获取架构信息"""
    factory = get_factory()
    return factory.get_architecture_info()


# ===== 多交易所管理便利函数 =====

def create_exchange_manager() -> ExchangeFactory:
    """创建交易所管理器（返回工厂实例，兼容性函数）"""
    return get_factory()


def add_managed_adapter(exchange_name: str, config: Optional[Dict[str, Any]] = None) -> bool:
    """便捷函数：添加托管适配器"""
    factory = get_factory()
    return factory.add_managed_adapter(exchange_name, config)


def get_health_status() -> Dict[str, ExchangeHealth]:
    """便捷函数：获取健康状态"""
    factory = get_factory()
    return factory.get_health_status()


def get_performance_stats() -> Dict[str, Dict[str, Any]]:
    """便捷函数：获取性能统计"""
    factory = get_factory()
    return factory.get_performance_stats()


# ===== 向后兼容性 =====

# 向后兼容的智能工厂别名
intelligent_factory = get_factory()

# 向后兼容的管理器别名（ExchangeManager现在就是ExchangeFactory）
ExchangeManager = ExchangeFactory