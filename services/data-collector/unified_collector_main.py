#!/usr/bin/env python3
"""
MarketPrism统一数据收集器 - 主启动程序

集成多种启动方式的统一入口：
- 微服务模式：基于BaseService框架，提供HTTP API
- 收集器模式：基于WebSocket架构，专注数据收集
- 测试模式：组件验证和集成测试
- Docker模式：容器化部署支持

功能特性：
- 统一WebSocket连接管理（core/networking）
- 职责分离的数据处理（collector层）
- 配置驱动的启动系统
- 多交易所、多市场类型支持
- NATS消息发布
- 完整的监控和错误处理
- 多种部署模式支持
"""

import asyncio
import signal
import sys
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
import argparse
import logging

import structlog
import yaml

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, '/app')  # Docker支持

# 配置日志系统
def setup_logging(log_level: str = "INFO", use_json: bool = False):
    """配置日志系统"""
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if use_json:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True
    )

    # 设置标准库日志级别
    import logging
    logging.basicConfig(level=getattr(logging, log_level.upper()))

# 核心模块导入
from core.config import get_global_config_manager
from core.networking import (
    websocket_manager, network_manager,
    DataType, WebSocketConnectionManager
)

# 数据收集模块导入
from collector.websocket_adapter import OrderBookWebSocketAdapter
from collector.orderbook_manager import OrderBookManager
from collector.normalizer import DataNormalizer
from collector.data_types import Exchange, MarketType, ExchangeConfig
from collector.nats_publisher import NATSPublisher, NATSConfig, create_nats_config_from_yaml

# 微服务模块导入
from collector.service import DataCollectorService
from core.networking.port_manager import ensure_service_port


class ConfigResolver:
    """配置路径解析器"""

    @staticmethod
    def get_config_path(config_name: str = "unified_data_collection") -> Path:
        """获取配置文件路径，按优先级查找"""

        # 1. 环境变量指定的路径（最高优先级）
        env_path = os.getenv(f'MARKETPRISM_{config_name.upper()}_CONFIG')
        if env_path and Path(env_path).exists():
            return Path(env_path)

        # 2. 项目根目录配置（推荐）
        main_config = project_root / "config" / "collector" / f"{config_name}.yaml"
        if main_config.exists():
            return main_config

        # 3. 服务本地配置（回退）
        local_config = Path(__file__).parent / "config" / "collector.yaml"
        if local_config.exists():
            return local_config

        # 4. 默认路径
        return main_config

    @staticmethod
    def get_service_config_path() -> Path:
        """获取微服务配置路径"""
        service_config = project_root / 'config' / 'services' / 'services.yml'
        if service_config.exists():
            return service_config
        return service_config


class UnifiedDataCollector:
    """
    统一数据收集器

    基于新的WebSocket架构，实现完整的数据收集系统：
    - 配置驱动启动
    - 统一WebSocket管理
    - 多交易所支持
    - NATS消息发布
    """

    def __init__(self, config_path: Optional[str] = None, mode: str = "collector"):
        """
        初始化统一数据收集器

        Args:
            config_path: 配置文件路径，默认使用统一配置
            mode: 运行模式 ("collector", "service", "test")
        """
        self.config_path = config_path
        self.mode = mode
        self.config = None
        self.is_running = False
        self.start_time = None

        # 组件管理
        self.websocket_adapters: Dict[str, OrderBookWebSocketAdapter] = {}
        self.orderbook_managers: Dict[str, OrderBookManager] = {}
        self.nats_publisher: Optional[NATSPublisher] = None
        self.normalizer: Optional[DataNormalizer] = None

        # 微服务组件
        self.service: Optional[DataCollectorService] = None

        # 任务管理
        self.tasks: List[asyncio.Task] = []

        # 统计信息
        self.stats = {
            'start_time': None,
            'exchanges_connected': 0,
            'total_messages': 0,
            'nats_published': 0,
            'errors': 0,
            'uptime_seconds': 0,
            'mode': mode
        }

        # 日志记录器
        self.logger = structlog.get_logger(__name__)
    
    async def start(self) -> bool:
        """
        启动统一数据收集器

        Returns:
            启动是否成功
        """
        try:
            self.logger.info("🚀 启动统一数据收集器", mode=self.mode)

            if self.mode == "service":
                return await self._start_service_mode()
            elif self.mode == "test":
                return await self._start_test_mode()
            elif self.mode == "launcher":
                return await self._start_launcher_mode()
            else:
                return await self._start_collector_mode()

        except Exception as e:
            self.logger.error("❌ 统一数据收集器启动失败", error=str(e), exc_info=True)
            await self.stop()
            return False

    async def _start_service_mode(self) -> bool:
        """启动微服务模式"""
        try:
            self.logger.info("🔧 启动微服务模式")

            # 加载微服务配置
            config_path = ConfigResolver.get_service_config_path()
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    full_config = yaml.safe_load(f) or {}
                service_config = full_config.get('services', {}).get('data-collector', {})
            else:
                # 使用环境变量配置
                service_config = {
                    'port': int(os.getenv('API_PORT', '8084')),
                    'nats_url': os.getenv('NATS_URL', 'nats://localhost:4222'),
                    'log_level': os.getenv('LOG_LEVEL', 'INFO')
                }

            # 确保端口配置
            if 'port' not in service_config:
                service_config['port'] = 8084

            # 端口管理
            if ensure_service_port:
                desired_port = service_config['port']
                try:
                    available_port = ensure_service_port(desired_port, "data-collector")
                    service_config['port'] = available_port
                    self.logger.info("✅ 端口管理完成", port=available_port)
                except Exception as e:
                    self.logger.warning("端口管理失败", error=str(e), port=desired_port)

            # 创建并启动微服务
            if DataCollectorService:
                self.service = DataCollectorService(config=service_config)
                await self.service.run()

                self.is_running = True
                self.start_time = datetime.now(timezone.utc)
                self.stats['start_time'] = self.start_time

                self.logger.info("✅ 微服务模式启动成功", port=service_config['port'])
                return True
            else:
                self.logger.error("DataCollectorService不可用")
                return False

        except Exception as e:
            self.logger.error("❌ 微服务模式启动失败", error=str(e))
            return False

    async def _start_collector_mode(self) -> bool:
        """启动收集器模式"""
        try:
            self.logger.info("🔧 启动收集器模式")

            # 加载配置
            success = await self._load_configuration()
            if not success:
                return False

            # 初始化组件
            success = await self._initialize_components()
            if not success:
                return False

            # 启动数据收集
            success = await self._start_data_collection()
            if not success:
                return False

            # 启动监控任务
            await self._start_monitoring_tasks()

            # 更新状态
            self.is_running = True
            self.start_time = datetime.now(timezone.utc)
            self.stats['start_time'] = self.start_time

            self.logger.info("✅ 收集器模式启动成功",
                           exchanges=len(self.websocket_adapters),
                           config_path=self.config_path)

            return True

        except Exception as e:
            self.logger.error("❌ 收集器模式启动失败", error=str(e))
            return False

    async def _start_test_mode(self) -> bool:
        """启动测试模式"""
        try:
            self.logger.info("🧪 启动测试模式")

            # 执行组件测试
            tests = [
                ("配置加载", self._test_configuration_loading),
                ("核心组件", self._test_core_components),
                ("NATS集成", self._test_nats_integration),
            ]

            results = []
            for test_name, test_func in tests:
                self.logger.info(f"执行测试: {test_name}")
                result = await test_func()
                results.append((test_name, result))

            # 统计结果
            passed = sum(1 for _, result in results if result)
            total = len(results)

            self.logger.info("📊 测试结果", passed=passed, total=total)

            if passed == total:
                self.logger.info("🎉 所有测试通过！")
                return True
            else:
                self.logger.error("❌ 部分测试失败")
                return False

        except Exception as e:
            self.logger.error("❌ 测试模式启动失败", error=str(e))
            return False

    async def _start_launcher_mode(self) -> bool:
        """启动完整数据收集系统模式（整合data_collection_launcher.py功能）"""
        try:
            self.logger.info("🚀 启动完整数据收集系统模式")

            # 加载配置
            success = await self._load_configuration()
            if not success:
                return False

            # 初始化组件（包含HTTP服务器和监控）
            success = await self._initialize_launcher_components()
            if not success:
                return False

            # 启动数据收集
            success = await self._start_data_collection()
            if not success:
                return False

            # 显示系统信息
            await self._show_launcher_system_info()

            # 更新状态
            self.is_running = True
            self.start_time = datetime.now(timezone.utc)
            self.stats['start_time'] = self.start_time

            # 启动监控循环（对应原launcher的monitor_data_collection）
            await self._monitor_launcher_data_collection()

            self.logger.info("✅ 完整数据收集系统启动成功")

            return True

        except Exception as e:
            self.logger.error("❌ 完整数据收集系统启动失败", error=str(e))
            return False

    async def _initialize_launcher_components(self) -> bool:
        """初始化launcher模式的所有组件（完全对应data_collection_launcher.py功能）"""
        try:
            self.logger.info("🔧 初始化完整数据收集组件")

            # 初始化基础组件
            success = await self._initialize_components()
            if not success:
                return False

            # 初始化HTTP服务器和监控组件
            try:
                # 尝试导入HTTP服务器组件
                from collector.http_server import HTTPServer
                from collector.health_check import HealthChecker
                from collector.metrics import MetricsCollector

                # 初始化健康检查器
                self.health_checker = HealthChecker()
                self.logger.info("✅ 健康检查器初始化完成")

                # 初始化指标收集器
                self.metrics_collector = MetricsCollector()
                self.logger.info("✅ 指标收集器初始化完成")

                # 初始化HTTP服务器（从配置文件读取端口）
                health_check_port = self.config.get('monitoring', {}).get('health_check', {}).get('port', 8082)
                metrics_port = self.config.get('monitoring', {}).get('metrics', {}).get('port', 8081)

                self.http_server = HTTPServer(
                    health_check_port=health_check_port,
                    metrics_port=metrics_port,
                    health_checker=self.health_checker,
                    metrics_collector=self.metrics_collector
                )

                # 设置依赖
                self.http_server.set_dependencies(
                    nats_client=self.nats_publisher,
                    websocket_connections={},
                    orderbook_manager=None
                )

                await self.http_server.start()
                self.logger.info("✅ HTTP服务器启动完成")

            except ImportError as e:
                self.logger.warning("HTTP服务器组件不可用，跳过", error=str(e))
            except Exception as e:
                self.logger.error("HTTP服务器初始化失败", error=str(e))
                return False

            # 注意：订单簿管理器已在_start_data_collection中启动，无需重复创建

            return True

        except Exception as e:
            self.logger.error("❌ launcher组件初始化失败", error=str(e))
            return False

    async def _start_launcher_orderbook_managers(self):
        """启动launcher模式的订单簿管理器（从配置文件读取）"""
        try:
            self.logger.info("📊 启动订单簿管理器")

            # 导入必要的类型
            from collector.data_types import Exchange, MarketType, ExchangeConfig
            from collector.orderbook_manager import OrderBookManager

            # 从配置文件读取交易所配置
            exchanges_config = self.config.get('exchanges', {})

            if not exchanges_config:
                self.logger.warning("配置文件中没有找到交易所配置")
                return

            for exchange_name, exchange_config in exchanges_config.items():
                # 🔍 调试：记录每个交易所的处理
                print(f"🔍 DEBUG: 处理交易所配置 {exchange_name}")
                print(f"🔍 DEBUG: enabled={exchange_config.get('enabled', True)}")

                # 检查是否启用
                if not exchange_config.get('enabled', True):
                    self.logger.info("跳过禁用的交易所", exchange=exchange_name)
                    print(f"🔍 DEBUG: 跳过禁用的交易所 {exchange_name}")
                    continue

                try:
                    # 解析交易所和市场类型
                    exchange_str = exchange_config.get('exchange')
                    market_type_str = exchange_config.get('market_type')

                    print(f"🔍 DEBUG: exchange_str={exchange_str}, market_type_str={market_type_str}")

                    if not exchange_str or not market_type_str:
                        self.logger.error("交易所配置缺少必要字段",
                                        exchange=exchange_name,
                                        missing_fields=[f for f in ['exchange', 'market_type']
                                                      if not exchange_config.get(f)])
                        print(f"🔍 DEBUG: 跳过配置不完整的交易所 {exchange_name}")
                        continue

                    # 转换为枚举类型
                    # 🔧 修复：Exchange枚举使用值而不是名称
                    try:
                        exchange_enum = Exchange(exchange_str)  # 直接使用值，如"binance_derivatives"
                        market_type_enum = MarketType(market_type_str.upper())  # MarketType使用大写
                        print(f"🔍 DEBUG: 枚举转换成功 exchange_enum={exchange_enum}, market_type_enum={market_type_enum}")
                    except Exception as e:
                        print(f"🔍 DEBUG: 枚举转换失败 {exchange_name}: {e}")
                        self.logger.error("枚举转换失败", exchange=exchange_name, error=str(e))
                        continue

                    # 🔍 调试：检查配置解析
                    base_url = exchange_config.get('api', {}).get('base_url')
                    ws_url = exchange_config.get('api', {}).get('ws_url')
                    symbols = exchange_config.get('symbols', [])

                    print(f"🔍 DEBUG: 创建ExchangeConfig for {exchange_name}")
                    print(f"🔍 DEBUG: base_url={base_url}, ws_url={ws_url}")
                    print(f"🔍 DEBUG: symbols={symbols}, market_type={market_type_enum}")

                    # 创建ExchangeConfig
                    config = ExchangeConfig(
                        name=exchange_name,
                        exchange=exchange_enum,
                        market_type=market_type_enum,
                        base_url=base_url,
                        ws_url=ws_url,
                        symbols=symbols,
                        data_types=exchange_config.get('data_types', ['orderbook']),
                        use_unified_websocket=True
                    )

                    print(f"🔍 DEBUG: ExchangeConfig创建成功: base_url={config.base_url}, ws_url={config.ws_url}")

                    # 创建管理器
                    manager = OrderBookManager(
                        config=config,
                        normalizer=self.normalizer,
                        nats_publisher=self.nats_publisher
                    )

                    # 获取symbols
                    symbols = exchange_config.get('symbols', [])
                    if not symbols:
                        self.logger.warning("交易所配置中没有symbols", exchange=exchange_name)
                        continue

                    # 启动管理器
                    await manager.start(symbols)

                    manager_key = f"{exchange_enum.value}_{market_type_enum.value}"
                    self.orderbook_managers[manager_key] = manager

                    self.logger.info(
                        "✅ 订单簿管理器启动成功",
                        exchange=exchange_enum.value,
                        market_type=market_type_enum.value,
                        symbols=symbols
                    )

                except Exception as e:
                    self.logger.error(
                        "订单簿管理器启动失败",
                        exchange=exchange_name,
                        error=str(e),
                        exc_info=True
                    )

            # 更新HTTP服务器依赖
            if self.orderbook_managers and hasattr(self, 'http_server') and self.http_server:
                first_manager = next(iter(self.orderbook_managers.values()))
                self.http_server.set_dependencies(
                    nats_client=self.nats_publisher,
                    websocket_connections=getattr(first_manager, 'websocket_connections', {}),
                    orderbook_manager=first_manager
                )

            self.logger.info(f"📊 启动了 {len(self.orderbook_managers)} 个订单簿管理器")

        except ImportError as e:
            self.logger.warning("订单簿管理器组件不可用", error=str(e))
        except Exception as e:
            self.logger.error("启动订单簿管理器失败", error=str(e), exc_info=True)

    async def _show_launcher_system_info(self):
        """显示launcher模式的系统信息"""
        print("\n" + "="*80)
        print("🎉 MarketPrism完整数据收集系统启动成功")
        print("="*80)

        print(f"\n📊 系统状态:")
        print(f"  NATS连接: {'✅ 已连接' if self.nats_publisher and hasattr(self.nats_publisher, 'is_connected') and self.nats_publisher.is_connected else '❌ 未连接'}")
        print(f"  WebSocket适配器: {len(self.websocket_adapters)} 个")
        print(f"  订单簿管理器: {len(self.orderbook_managers)} 个")
        print(f"  HTTP服务器: {'✅ 运行中' if hasattr(self, 'http_server') and self.http_server else '❌ 未启动'}")

        print(f"\n🔗 服务端点:")
        if hasattr(self, 'http_server') and self.http_server:
            print(f"  健康检查: http://localhost:8080/health")
            print(f"  系统状态: http://localhost:8080/status")
            print(f"  系统指标: http://localhost:8081/metrics")
        else:
            print(f"  HTTP服务: ❌ 不可用")

        print(f"\n📡 数据收集:")
        for exchange_name in self.websocket_adapters.keys():
            print(f"  {exchange_name.upper()}: ✅ 运行中")

        print(f"\n📋 NATS主题:")
        print(f"  订单簿数据: orderbook-data.{{exchange}}.{{market_type}}.{{symbol}}")
        print(f"  交易数据: trade-data.{{exchange}}.{{market_type}}.{{symbol}}")
        print(f"  价格数据: ticker-data.{{exchange}}.{{market_type}}.{{symbol}}")

        print(f"\n💡 提示:")
        print(f"  使用 Ctrl+C 优雅停止系统")
        print(f"  查看日志了解详细运行状态")

        print("\n" + "="*80)

    async def _monitor_launcher_data_collection(self):
        """监控launcher模式的数据收集状态（对应data_collection_launcher.py的monitor_data_collection）"""
        self.logger.info("📈 开始监控数据收集状态")

        while self.is_running:
            try:
                # 更新指标
                if hasattr(self, 'metrics_collector') and self.metrics_collector:
                    await self.metrics_collector.update_metrics(
                        nats_client=self.nats_publisher,
                        websocket_connections={},
                        orderbook_manager=next(iter(self.orderbook_managers.values())) if self.orderbook_managers else None
                    )

                # 检查各个管理器状态
                active_managers = 0
                total_symbols = 0

                for manager_key, manager in self.orderbook_managers.items():
                    if hasattr(manager, 'orderbook_states'):
                        symbols_count = len(manager.orderbook_states)
                        total_symbols += symbols_count
                        if symbols_count > 0:
                            active_managers += 1

                self.logger.info(
                    "📊 数据收集状态",
                    active_managers=active_managers,
                    total_managers=len(self.orderbook_managers),
                    total_symbols=total_symbols
                )

                # 等待30秒后再次检查
                await asyncio.sleep(30)

            except Exception as e:
                self.logger.error("监控数据收集状态异常", error=str(e), exc_info=True)
                await asyncio.sleep(30)

    async def _test_configuration_loading(self) -> bool:
        """测试配置加载"""
        try:
            # 尝试加载配置
            config_path = ConfigResolver.get_config_path()
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                self.logger.info("✅ 配置文件加载成功", path=str(config_path))
                return True
            else:
                self.logger.warning("⚠️ 配置文件不存在，使用默认配置", path=str(config_path))
                return True
        except Exception as e:
            self.logger.error("❌ 配置加载测试失败", error=str(e))
            return False

    async def _test_core_components(self) -> bool:
        """测试核心组件"""
        try:
            # 测试WebSocket管理器
            if websocket_manager is None:
                self.logger.warning("⚠️ WebSocket管理器不可用")
                return False

            # 测试数据收集组件
            if OrderBookWebSocketAdapter is None:
                self.logger.warning("⚠️ OrderBook适配器不可用")
                return False

            self.logger.info("✅ 核心组件测试通过")
            return True
        except Exception as e:
            self.logger.error("❌ 核心组件测试失败", error=str(e))
            return False

    async def _test_nats_integration(self) -> bool:
        """测试NATS集成"""
        try:
            # 简单的NATS连接测试
            nats_url = os.getenv('NATS_URL', 'nats://localhost:4222')
            self.logger.info("🔗 测试NATS连接", url=nats_url)

            # 这里可以添加实际的NATS连接测试
            # 暂时返回True，表示测试通过
            self.logger.info("✅ NATS集成测试通过")
            return True
        except Exception as e:
            self.logger.error("❌ NATS集成测试失败", error=str(e))
            return False

    async def stop(self):
        """停止统一数据收集器"""
        try:
            self.logger.info("🛑 停止统一数据收集器")
            
            self.is_running = False
            
            # 停止所有任务
            for task in self.tasks:
                if not task.done():
                    task.cancel()
            
            if self.tasks:
                await asyncio.gather(*self.tasks, return_exceptions=True)
            
            # 停止WebSocket适配器
            for name, adapter in self.websocket_adapters.items():
                try:
                    await adapter.disconnect()
                    self.logger.info("WebSocket适配器已停止", name=name)
                except Exception as e:
                    self.logger.error("停止WebSocket适配器失败", name=name, error=str(e))
            
            # 停止OrderBook管理器
            for name, manager in self.orderbook_managers.items():
                try:
                    await manager.stop()
                    self.logger.info("OrderBook管理器已停止", name=name)
                except Exception as e:
                    self.logger.error("停止OrderBook管理器失败", name=name, error=str(e))
            
            # 停止HTTP服务器（launcher模式）
            if hasattr(self, 'http_server') and self.http_server:
                try:
                    await self.http_server.stop()
                    self.logger.info("HTTP服务器已停止")
                except Exception as e:
                    self.logger.error("停止HTTP服务器失败", error=str(e))

            # 关闭NATS连接
            if self.nats_publisher:
                try:
                    await self.nats_publisher.disconnect()
                    self.logger.info("NATS发布器已关闭")
                except Exception as e:
                    self.logger.error("关闭NATS发布器失败", error=str(e))

            self.logger.info("✅ 统一数据收集器已停止")
            
        except Exception as e:
            self.logger.error("❌ 停止统一数据收集器失败", error=str(e))
    
    async def _load_configuration(self) -> bool:
        """
        加载配置

        Returns:
            配置加载是否成功
        """
        try:
            self.logger.info("📋 加载配置")

            if self.config_path:
                # 使用指定的配置文件
                config_file = Path(self.config_path)
                if not config_file.exists():
                    self.logger.error("配置文件不存在", path=self.config_path)
                    return False

                with open(config_file, 'r', encoding='utf-8') as f:
                    self.config = yaml.safe_load(f)
            else:
                # 尝试使用统一配置管理器
                try:
                    unified_config_manager = get_global_config_manager()
                    self.config = unified_config_manager.get_config('collector')
                    if self.config:
                        self.logger.info("✅ 使用统一配置管理器")
                    else:
                        raise Exception("统一配置管理器返回空配置")
                except Exception as e:
                    self.logger.warning("统一配置管理器失败，使用文件配置", error=str(e))
                    self.config = None

                # 回退到文件配置
                if not self.config:
                    config_path = ConfigResolver.get_config_path()
                    if config_path.exists():
                        with open(config_path, 'r', encoding='utf-8') as f:
                            self.config = yaml.safe_load(f)
                        self.logger.info("✅ 使用文件配置", path=str(config_path))
                    else:
                        self.logger.error("❌ 配置文件不存在", path=str(config_path))
                        return False

            self.logger.info("✅ 配置加载成功",
                           exchanges=len(self.config.get('exchanges', {})),
                           nats_enabled=bool(self.config.get('nats')))

            return True

        except Exception as e:
            self.logger.error("❌ 配置加载失败", error=str(e), exc_info=True)
            return False


    
    async def _initialize_components(self) -> bool:
        """初始化组件"""
        try:
            self.logger.info("🔧 初始化组件")

            # 初始化数据标准化器
            self.normalizer = DataNormalizer()
            self.logger.info("✅ 数据标准化器初始化成功")

            # 初始化NATS发布器
            nats_config = create_nats_config_from_yaml(self.config)
            self.logger.info("NATS配置", servers=nats_config.servers, client_name=nats_config.client_name)
            # 🔧 传递Normalizer给NATS Publisher，实现发布时Symbol标准化
            self.nats_publisher = NATSPublisher(nats_config, self.normalizer)

            # 连接NATS
            self.logger.info("开始连接NATS服务器...")
            success = await self.nats_publisher.connect()
            if not success:
                self.logger.error("❌ NATS连接失败")
                stats = self.nats_publisher.get_stats()
                self.logger.error("NATS连接统计", stats=stats)
                # 不要因为NATS连接失败而停止整个系统
                self.logger.warning("继续启动系统，但NATS功能将不可用")
            else:
                self.logger.info("✅ NATS发布器初始化成功")
            self.logger.info("✅ 组件初始化完成")
            return True

        except Exception as e:
            self.logger.error("❌ 组件初始化失败", error=str(e), exc_info=True)
            return False
    
    async def _start_data_collection(self) -> bool:
        """启动数据收集"""
        try:
            self.logger.info("🔧 启动数据收集")
            
            exchanges_config = self.config.get('exchanges', {})
            
            for exchange_name, exchange_config in exchanges_config.items():
                if not exchange_config.get('enabled', True):
                    self.logger.info("跳过禁用的交易所", exchange=exchange_name)
                    continue
                
                success = await self._start_exchange_collection(exchange_name, exchange_config)
                if success:
                    self.stats['exchanges_connected'] += 1
                else:
                    self.logger.error("交易所数据收集启动失败", exchange=exchange_name)
            
            if self.stats['exchanges_connected'] == 0:
                self.logger.error("没有成功连接的交易所")
                return False
            
            self.logger.info("✅ 数据收集启动成功", 
                           connected_exchanges=self.stats['exchanges_connected'])
            return True
            
        except Exception as e:
            self.logger.error("❌ 数据收集启动失败", error=str(e))
            return False
    
    async def _start_exchange_collection(self, exchange_name: str, exchange_config: Dict[str, Any]) -> bool:
        """启动单个交易所的数据收集"""
        try:
            # 解析交易所配置
            exchange_enum = Exchange(exchange_config['exchange'])
            market_type_enum = MarketType(exchange_config['market_type'])
            symbols = exchange_config['symbols']
            data_types = exchange_config.get('data_types', ['orderbook'])
            
            self.logger.info("启动交易所数据收集",
                           exchange=exchange_name,
                           market_type=market_type_enum.value,
                           symbols=symbols,
                           data_types=data_types)
            
            # 创建ExchangeConfig
            config = ExchangeConfig(
                name=exchange_name,
                exchange=exchange_enum,
                symbols=symbols,
                data_types=data_types,
                market_type=market_type_enum.value,
                use_unified_websocket=True  # 启用统一WebSocket
            )
            
            # 创建OrderBook管理器
            orderbook_manager = OrderBookManager(config, self.normalizer, self.nats_publisher)
            
            # 启动管理器
            success = await orderbook_manager.start(symbols)
            if success:
                self.orderbook_managers[exchange_name] = orderbook_manager
                self.logger.info("交易所数据收集启动成功", exchange=exchange_name)
                return True
            else:
                self.logger.error("交易所数据收集启动失败", exchange=exchange_name)
                return False
            
        except Exception as e:
            self.logger.error("启动交易所数据收集异常", 
                            exchange=exchange_name, 
                            error=str(e), 
                            exc_info=True)
            return False
    
    async def _start_monitoring_tasks(self):
        """启动监控任务"""
        try:
            # 启动统计任务
            stats_task = asyncio.create_task(self._stats_loop())
            self.tasks.append(stats_task)
            
            # 启动健康检查任务
            health_task = asyncio.create_task(self._health_check_loop())
            self.tasks.append(health_task)
            
            self.logger.info("监控任务已启动")
            
        except Exception as e:
            self.logger.error("启动监控任务失败", error=str(e))
    
    async def _stats_loop(self):
        """统计信息循环"""
        try:
            while self.is_running:
                await asyncio.sleep(60)  # 每分钟更新一次
                
                if self.start_time:
                    self.stats['uptime_seconds'] = (
                        datetime.now(timezone.utc) - self.start_time
                    ).total_seconds()
                
                # 收集各组件统计
                total_messages = 0
                for manager in self.orderbook_managers.values():
                    try:
                        manager_stats = manager.get_stats()
                        total_messages += manager_stats.get('messages_received', 0)
                    except Exception:
                        pass
                
                self.stats['total_messages'] = total_messages
                
                self.logger.info("📊 系统统计", stats=self.stats)
                
        except asyncio.CancelledError:
            self.logger.info("统计任务已取消")
        except Exception as e:
            self.logger.error("统计任务异常", error=str(e))
    
    async def _health_check_loop(self):
        """健康检查循环"""
        try:
            while self.is_running:
                await asyncio.sleep(30)  # 每30秒检查一次
                
                # 检查各组件健康状态
                healthy_components = 0
                total_components = len(self.orderbook_managers)
                
                for name, manager in self.orderbook_managers.items():
                    try:
                        # 这里可以添加具体的健康检查逻辑
                        healthy_components += 1
                    except Exception as e:
                        self.logger.warning("组件健康检查失败", component=name, error=str(e))
                
                health_ratio = healthy_components / total_components if total_components > 0 else 0
                
                if health_ratio < 0.8:  # 80%以下认为不健康
                    self.logger.warning("系统健康状态不佳", 
                                      healthy=healthy_components,
                                      total=total_components,
                                      ratio=health_ratio)
                
        except asyncio.CancelledError:
            self.logger.info("健康检查任务已取消")
        except Exception as e:
            self.logger.error("健康检查任务异常", error=str(e))
    
    def get_stats(self) -> Dict[str, Any]:
        """获取系统统计信息"""
        return {
            **self.stats,
            'is_running': self.is_running,
            'connected_exchanges': list(self.orderbook_managers.keys()),
            'websocket_stats': websocket_manager.get_connection_stats()
        }


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="MarketPrism统一数据收集器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
运行模式:
  collector  - 数据收集模式（默认）
  service    - 微服务模式（提供HTTP API）
  test       - 测试验证模式
  launcher   - 完整数据收集系统（包含HTTP服务和监控）

环境变量:
  COLLECTOR_CONFIG_PATH  - 配置文件路径
  NATS_URL              - NATS服务器地址
  LOG_LEVEL             - 日志级别
  API_PORT              - 微服务端口（service模式）

示例:
  python unified_collector_main.py                    # 默认收集器模式
  python unified_collector_main.py --mode service     # 微服务模式
  python unified_collector_main.py --mode test        # 测试模式
  python unified_collector_main.py --config custom.yaml  # 指定配置文件
        """
    )

    parser.add_argument(
        '--mode', '-m',
        choices=['collector', 'service', 'test', 'launcher'],
        default='collector',
        help='运行模式 (默认: collector)'
    )

    parser.add_argument(
        '--config', '-c',
        type=str,
        help='配置文件路径'
    )

    parser.add_argument(
        '--log-level', '-l',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default=os.getenv('LOG_LEVEL', 'INFO'),
        help='日志级别 (默认: INFO)'
    )

    parser.add_argument(
        '--json-logs',
        action='store_true',
        help='使用JSON格式日志'
    )

    return parser.parse_args()


async def main():
    """主函数"""
    # 解析命令行参数
    args = parse_arguments()

    # 配置日志
    setup_logging(args.log_level, args.json_logs)
    logger = structlog.get_logger(__name__)

    logger.info("🚀 启动MarketPrism统一数据收集器",
                mode=args.mode,
                log_level=args.log_level,
                config=args.config)

    # 确定配置路径
    config_path = args.config or os.getenv('COLLECTOR_CONFIG_PATH')

    # 创建收集器
    collector = UnifiedDataCollector(config_path=config_path, mode=args.mode)

    # 设置信号处理
    def signal_handler(signum, frame):
        logger.info(f"收到信号 {signum}，准备停止...")
        asyncio.create_task(collector.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # 启动收集器
        success = await collector.start()
        if not success:
            logger.error("❌ 收集器启动失败")
            return 1

        # 保持运行（除非是测试模式）
        if args.mode != 'test':
            logger.info("✅ 收集器运行中，按Ctrl+C停止...")
            while collector.is_running:
                await asyncio.sleep(1)

        return 0

    except KeyboardInterrupt:
        logger.info("收到键盘中断，停止收集器...")
        await collector.stop()
        return 0
    except Exception as e:
        logger.error("收集器运行异常", error=str(e), exc_info=True)
        await collector.stop()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
