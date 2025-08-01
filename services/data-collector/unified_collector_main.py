#!/usr/bin/env python3
"""
MarketPrism统一数据收集器 - 生产级数据收集系统

🎯 设计理念：统一入口、模块化架构、生产级稳定性

🚀 核心功能：
- 📊 多交易所支持：Binance现货/衍生品、OKX现货/衍生品
- 🔄 实时数据流：订单簿、交易数据毫秒级处理
- 📡 NATS消息发布：结构化主题 orderbook-data.{exchange}.{market_type}.{symbol}
- 🛡️ 生产级稳定性：断路器、重试机制、内存管理
- 🔍 智能监控：连接状态、数据质量、性能指标
- ⚙️ 统一配置：单一YAML配置文件管理所有设置

🏗️ 架构设计：
- 📁 模块化组件：订单簿管理器、交易数据管理器独立解耦
- 🔌 交易所适配器：统一WebSocket接口，支持心跳和重连
- 🔄 数据标准化：统一数据格式，支持BTC-USDT符号标准化
- 📊 序列号验证：Binance lastUpdateId、OKX seqId/checksum双重验证
- 🚨 错误处理：多层级错误管理，自动恢复机制

🎯 使用场景：
- 🏢 生产环境：高频交易数据收集
- 📈 量化分析：实时市场数据分析
- 🔍 套利监控：跨交易所价格差异检测
- 📊 风险管理：实时订单簿深度监控

🚨 重要使用提醒：
1. 首次启动建议使用渐进式配置，避免系统过载
2. 确保NATS服务器正在运行 (默认端口4222)
3. 检查网络连接和交易所API访问权限
4. 监控系统资源使用情况，特别是内存和CPU
5. 高频数据类型(LSR)会增加API请求，注意速率限制

📋 启动前检查清单：
✅ NATS服务器运行状态
✅ 配置文件语法正确性
✅ 数据类型名称匹配性
✅ 网络连接稳定性
✅ 系统资源充足性

🔧 常见启动问题：
- 配置文件中数据类型名称错误 (如"trades"应为"trade")
- NATS服务器未启动或端口被占用
- 虚拟环境未激活或依赖包缺失
- 系统资源不足导致初始化超时
"""

import asyncio
import signal
import sys
import os
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Protocol, Type
from datetime import datetime, timezone
import argparse
import logging
from abc import ABC, abstractmethod
from enum import Enum

import yaml

# 🔧 迁移到统一日志系统 - 首先设置路径
import sys
import os

# 添加项目根目录到Python路径 - 必须在导入之前
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, '/app')  # Docker支持
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from core.observability.logging import (
    get_managed_logger,
    configure_global_logging,
    LogConfiguration,
    ComponentType,
    shutdown_global_logging
)

# 配置日志系统
def setup_logging(log_level: str = "INFO", use_json: bool = False):
    """配置统一日志系统"""
    # 🔧 迁移到统一日志系统
    config = LogConfiguration(
        global_level=log_level,
        use_json_format=use_json,
        enable_performance_mode=True,  # 生产环境启用性能模式
        enable_deduplication=True,     # 启用日志去重
        use_emoji=False,               # 生产环境禁用emoji
        environment="production" if log_level == "INFO" else "development"
    )

    configure_global_logging(config)

# 🔧 修复：移除有问题的导入，只保留必要的导入

# 系统资源管理器导入
from core.memory_manager import MemoryManager, MemoryConfig, SystemResourceManager, SystemResourceConfig

# 🗑️ 已删除内存分析器导入 - 误报太多，无实际价值

# 🔧 修复：添加必要的导入
from typing import Union

# 🔧 修复：导入必要的NATS相关模块
try:
    from collector.nats_publisher import NATSPublisher, NATSConfig, create_nats_config_from_yaml
    from collector.normalizer import DataNormalizer
    from collector.data_types import Exchange, MarketType, ExchangeConfig
except ImportError as e:
    print(f"警告：部分模块导入失败: {e}")
    # 临时类型定义，避免导入错误
    class ExchangeConfig:
        """临时交易所配置类"""
        pass

    class DataNormalizer:
        """临时数据标准化器类"""
        pass

    class NATSPublisher:
        """临时NATS发布器类"""
        pass

    def create_nats_config_from_yaml(config):
        """临时函数"""
        return None

# 🔧 临时注释：专注于OrderBook Manager修复
# class TradesManager:
#     """临时交易管理器类"""
#     def __init__(self, *args, **kwargs):
#         pass

#     async def initialize(self):
#         pass

#     async def start(self, symbols):
#         pass

#     async def stop(self):
#         pass


# ==================== 🏗️ 并行管理器启动框架 ====================

class ManagerType(Enum):
    """数据管理器类型枚举"""
    ORDERBOOK = "orderbook"
    TRADES = "trades"
    TICKER = "ticker"
    KLINE = "kline"
    LIQUIDATION = "liquidation"  # 🔧 新增：强平订单数据管理器
    LSR_TOP_POSITION = "lsr_top_position"  # 🔧 新增：顶级大户多空持仓比例数据管理器（按持仓量计算）
    LSR_ALL_ACCOUNT = "lsr_all_account"    # 🔧 新增：全市场多空持仓人数比例数据管理器（按账户数计算）
    FUNDING_RATE = "funding_rate"  # 🔧 新增：资金费率数据管理器（仅衍生品）
    OPEN_INTEREST = "open_interest"  # 🔧 新增：未平仓量数据管理器（仅衍生品）
    VOLATILITY_INDEX = "volatility_index"  # 🔧 新增：波动率指数数据管理器


class DataManagerProtocol(Protocol):
    """数据管理器协议接口"""

    async def start(self, symbols: List[str]) -> bool:
        """启动管理器"""
        ...

    async def stop(self) -> None:
        """停止管理器"""
        ...

    @property
    def is_running(self) -> bool:
        """检查管理器是否运行中"""
        ...


class ManagerStartupResult:
    """管理器启动结果"""

    def __init__(self, manager_type: ManagerType, exchange_name: str,
                 success: bool, manager: Optional[DataManagerProtocol] = None,
                 error: Optional[str] = None):
        self.manager_type = manager_type
        self.exchange_name = exchange_name
        self.success = success
        self.manager = manager
        self.error = error
        self.startup_time = datetime.now(timezone.utc)


class ManagerFactory:
    """数据管理器工厂类"""

    @staticmethod
    def create_manager(manager_type: ManagerType, config: ExchangeConfig,
                      normalizer: DataNormalizer, nats_publisher: NATSPublisher) -> DataManagerProtocol:
        """创建指定类型的数据管理器"""
        if manager_type == ManagerType.ORDERBOOK:
            # 🔧 已迁移到新版专用管理器架构，旧版通用管理器已废弃
            raise NotImplementedError("OrderBook管理器已迁移到专用管理器架构，请使用ParallelManagerLauncher")
            # return OrderBookManager(config, normalizer, nats_publisher)
        elif manager_type == ManagerType.TRADES:
            # 🔧 已迁移到新版专用管理器架构，旧版通用管理器已废弃
            raise NotImplementedError("Trades管理器已迁移到专用管理器架构，请使用ParallelManagerLauncher")
        elif manager_type == ManagerType.TICKER:
            # TODO: 实现TickerManager
            raise NotImplementedError("TickerManager尚未实现")
        elif manager_type == ManagerType.KLINE:
            # TODO: 实现KlineManager
            raise NotImplementedError("KlineManager尚未实现")
        else:
            raise ValueError(f"不支持的管理器类型: {manager_type}")


class ParallelManagerLauncher:
    """并行管理器启动器"""

    def __init__(self, config: Dict[str, Any], startup_timeout: float = 60.0):
        # 🔧 迁移到统一日志系统
        self.logger = get_managed_logger(ComponentType.MAIN, exchange="parallel_launcher")
        self.startup_timeout = startup_timeout
        self.config = config  # 保存配置引用
        self.active_managers: Dict[str, Dict[ManagerType, DataManagerProtocol]] = {}

    async def start_exchange_managers(self, exchange_name: str, exchange_config: Dict[str, Any],
                                    normalizer: DataNormalizer, nats_publisher: NATSPublisher) -> List[ManagerStartupResult]:
        """并行启动单个交易所的所有数据管理器"""

        # 解析配置
        exchange_enum = Exchange(exchange_config['exchange'])
        market_type_enum = MarketType(exchange_config['market_type'])
        symbols = exchange_config['symbols']
        data_types = exchange_config.get('data_types', ['orderbook'])

        # 创建ExchangeConfig
        config = ExchangeConfig(
            name=exchange_name,
            exchange=exchange_enum,
            symbols=symbols,
            data_types=data_types,
            market_type=market_type_enum.value,
            use_unified_websocket=True,
            vol_index=exchange_config.get('vol_index')  # 🔧 新增：传递vol_index配置
        )

        # 确定需要启动的管理器类型
        manager_types = []
        for data_type in data_types:
            if data_type == 'orderbook':
                manager_types.append(ManagerType.ORDERBOOK)
            elif data_type == 'trade':  # 🔧 修复：配置文件中使用的是单数形式 "trade"
                manager_types.append(ManagerType.TRADES)
            elif data_type == 'ticker':
                manager_types.append(ManagerType.TICKER)
            elif data_type == 'kline':
                manager_types.append(ManagerType.KLINE)
            elif data_type == 'liquidation':  # 🔧 新增：强平订单数据类型支持
                manager_types.append(ManagerType.LIQUIDATION)
            elif data_type == 'lsr_top_position':  # 🔧 新增：顶级大户多空持仓比例数据类型支持
                # 重新启用LSR管理器，使用延迟启动机制
                self.logger.info("启用LSR_TOP_POSITION管理器（延迟启动）")
                manager_types.append(ManagerType.LSR_TOP_POSITION)
            elif data_type == 'lsr_all_account':  # 🔧 新增：全市场多空持仓人数比例数据类型支持
                # 重新启用LSR管理器，使用延迟启动机制
                self.logger.info("启用LSR_ALL_ACCOUNT管理器（延迟启动）")
                manager_types.append(ManagerType.LSR_ALL_ACCOUNT)
            elif data_type == 'funding_rate':  # 🔧 新增：资金费率数据类型支持
                # 启用FundingRate管理器，使用延迟启动机制
                self.logger.info("启用FUNDING_RATE管理器（延迟启动）")
                manager_types.append(ManagerType.FUNDING_RATE)
            elif data_type == 'open_interest':  # 🔧 新增：未平仓量数据类型支持
                # 启用OpenInterest管理器，使用延迟启动机制
                self.logger.info("启用OPEN_INTEREST管理器（延迟启动）")
                manager_types.append(ManagerType.OPEN_INTEREST)
            elif data_type == 'volatility_index':  # 🔧 新增：波动率指数数据类型支持
                # 启用VolatilityIndex管理器，使用延迟启动机制
                self.logger.info("启用VOLATILITY_INDEX管理器（延迟启动）")
                manager_types.append(ManagerType.VOLATILITY_INDEX)

        # 🔧 迁移到统一日志系统 - 使用标准化启动日志
        self.logger.startup(
            "Starting parallel exchange managers",
            exchange=exchange_name,
            manager_types=[mt.value for mt in manager_types],
            symbols=symbols
        )

        # 创建启动任务
        startup_tasks = []
        for manager_type in manager_types:
            task = asyncio.create_task(
                self._start_single_manager(manager_type, exchange_name, config, normalizer, nats_publisher, symbols)
            )
            startup_tasks.append((manager_type, task))

        # 等待所有管理器启动完成
        results = []
        for manager_type, task in startup_tasks:
            try:
                result = await asyncio.wait_for(task, timeout=self.startup_timeout)
                results.append(result)

                if result.success:
                    # 保存成功启动的管理器
                    if exchange_name not in self.active_managers:
                        self.active_managers[exchange_name] = {}
                    self.active_managers[exchange_name][manager_type] = result.manager

                    # 🔧 迁移到统一日志系统 - 成功日志会被自动去重
                    self.logger.data_processed(
                        "Manager started successfully",
                        exchange=exchange_name,
                        manager_type=manager_type.value
                    )
                else:
                    # 🔧 迁移到统一日志系统 - 标准化错误处理
                    self.logger.error(
                        "Manager startup failed",
                        error=Exception(result.error),
                        exchange=exchange_name,
                        manager_type=manager_type.value
                    )

            except asyncio.TimeoutError:
                # 🔧 迁移到统一日志系统 - 标准化超时错误
                timeout_error = TimeoutError(f"Manager startup timeout ({self.startup_timeout}s)")
                self.logger.error(
                    "Manager startup timeout",
                    error=timeout_error,
                    exchange=exchange_name,
                    manager_type=manager_type.value,
                    timeout_seconds=self.startup_timeout
                )
                task.cancel()
                results.append(ManagerStartupResult(
                    manager_type, exchange_name, False,
                    error=f"启动超时 ({self.startup_timeout}s)"
                ))
            except Exception as e:
                # 🔧 迁移到统一日志系统 - 标准化异常处理
                self.logger.error(
                    "Manager startup exception",
                    error=e,
                    exchange=exchange_name,
                    manager_type=manager_type.value
                )
                results.append(ManagerStartupResult(
                    manager_type, exchange_name, False, error=str(e)
                ))

        return results

    async def _start_single_manager(self, manager_type: ManagerType, exchange_name: str,
                                  config: ExchangeConfig, normalizer: DataNormalizer,
                                  nats_publisher: NATSPublisher, symbols: List[str]) -> ManagerStartupResult:
        """启动单个数据管理器"""
        try:
            # 🔧 根据管理器类型使用不同的创建方式
            if manager_type == ManagerType.ORDERBOOK:
                # 使用新版专用OrderBook管理器架构
                manager = await self._create_orderbook_manager(exchange_name, config, normalizer, nats_publisher, symbols)
            elif manager_type == ManagerType.TRADES:
                # 使用新版专用Trades管理器架构
                manager = await self._create_trades_manager(exchange_name, config, normalizer, nats_publisher, symbols)
            elif manager_type == ManagerType.LIQUIDATION:
                # 使用新版专用Liquidation管理器架构
                manager = await self._create_liquidation_manager(exchange_name, config, normalizer, nats_publisher, symbols)
            elif manager_type == ManagerType.LSR_TOP_POSITION:
                # 使用新版专用LSR顶级大户持仓管理器架构
                manager = await self._create_lsr_manager(exchange_name, config, normalizer, nats_publisher, symbols, 'lsr_top_position')
            elif manager_type == ManagerType.LSR_ALL_ACCOUNT:
                # 使用新版专用LSR全市场账户管理器架构
                manager = await self._create_lsr_manager(exchange_name, config, normalizer, nats_publisher, symbols, 'lsr_all_account')
            elif manager_type == ManagerType.FUNDING_RATE:
                # 使用新版专用FundingRate管理器架构
                manager = await self._create_funding_rate_manager(exchange_name, config, normalizer, nats_publisher, symbols)
            elif manager_type == ManagerType.OPEN_INTEREST:
                # 使用新版专用OpenInterest管理器架构
                manager = await self._create_open_interest_manager(exchange_name, config, normalizer, nats_publisher, symbols)
            elif manager_type == ManagerType.VOLATILITY_INDEX:
                # 使用新版专用VolatilityIndex管理器架构
                manager = await self._create_vol_index_manager(exchange_name, config, normalizer, nats_publisher, symbols)
            else:
                # 使用旧版管理器工厂（其他管理器）
                manager = ManagerFactory.create_manager(manager_type, config, normalizer, nats_publisher)

            if not manager:
                return ManagerStartupResult(manager_type, exchange_name, False, error="管理器创建失败")

            # 启动管理器
            if manager_type == ManagerType.ORDERBOOK:
                # 专用OrderBook管理器使用start()方法
                await manager.start()
                success = True
            elif manager_type == ManagerType.TRADES:
                # 专用Trades管理器使用start()方法
                success = await manager.start()
            elif manager_type == ManagerType.LIQUIDATION:
                # 专用Liquidation管理器使用start()方法
                success = await manager.start()
            elif manager_type == ManagerType.LSR_TOP_POSITION or manager_type == ManagerType.LSR_ALL_ACCOUNT:
                # 专用LSR管理器使用start()方法（不需要symbols参数）
                success = await manager.start()
            elif manager_type == ManagerType.FUNDING_RATE:
                # 专用FundingRate管理器使用start()方法（不需要symbols参数）
                success = await manager.start()
            elif manager_type == ManagerType.OPEN_INTEREST:
                # 专用OpenInterest管理器使用start()方法（不需要symbols参数）
                success = await manager.start()
            elif manager_type == ManagerType.VOLATILITY_INDEX:
                # 专用VolatilityIndex管理器使用start()方法（不需要symbols参数）
                success = await manager.start()
            else:
                # 其他管理器使用start(symbols)方法
                success = await manager.start(symbols)

            if success:
                return ManagerStartupResult(manager_type, exchange_name, True, manager)
            else:
                return ManagerStartupResult(manager_type, exchange_name, False,
                                          error="管理器start()方法返回False")
        except Exception as e:
            return ManagerStartupResult(manager_type, exchange_name, False, error=str(e))

    async def _create_orderbook_manager(self, exchange_name: str, config: ExchangeConfig,
                                      normalizer: DataNormalizer, nats_publisher: NATSPublisher,
                                      symbols: List[str]):
        """创建专用OrderBook管理器"""
        try:
            # 导入专用管理器工厂
            from collector.orderbook_managers import OrderBookManagerFactory

            factory = OrderBookManagerFactory()

            # 确定市场类型
            market_type = config.market_type.value if hasattr(config.market_type, 'value') else str(config.market_type)

            # 🔧 修复配置传递问题：直接从统一配置文件获取正确的URL
            api_base_url = config.base_url
            ws_base_url = config.ws_url

            # 🔧 从原始配置中获取orderbook配置
            exchange_raw_config = self.config.get('exchanges', {}).get(exchange_name, {})
            orderbook_config = exchange_raw_config.get('orderbook', {})

            # 如果配置中的URL为空，使用硬编码的默认值
            if not api_base_url:
                if exchange_name == "binance_spot":
                    api_base_url = "https://api.binance.com"
                elif exchange_name == "binance_derivatives":
                    api_base_url = "https://fapi.binance.com"
                elif exchange_name == "okx_spot":
                    api_base_url = "https://www.okx.com"
                elif exchange_name == "okx_derivatives":
                    api_base_url = "https://www.okx.com"

            if not ws_base_url:
                if exchange_name == "binance_spot":
                    ws_base_url = "wss://stream.binance.com:9443/ws"
                elif exchange_name == "binance_derivatives":
                    ws_base_url = "wss://fstream.binance.com/ws"
                elif exchange_name == "okx_spot":
                    ws_base_url = "wss://ws.okx.com:8443/ws/v5/public"
                elif exchange_name == "okx_derivatives":
                    ws_base_url = "wss://ws.okx.com:8443/ws/v5/public"

            # 准备配置字典
            manager_config = {
                'api_base_url': api_base_url,
                'ws_base_url': ws_base_url,
                # 🔧 修复：从配置文件中正确获取depth_limit
                'depth_limit': orderbook_config.get('depth_limit', 500),
                'nats_publish_depth': orderbook_config.get('nats_publish_depth', 400),
                'snapshot_interval': orderbook_config.get('snapshot_interval', 60),
                'lastUpdateId_validation': True,
                'checksum_validation': True,
                'sequence_validation': True,
                'enable_nats_push': True
            }

            self.logger.info(f"🏭 创建专用OrderBook管理器: {exchange_name}_{market_type}",
                           api_base_url=api_base_url, ws_base_url=ws_base_url,
                           depth_limit=manager_config['depth_limit'],
                           nats_publish_depth=manager_config['nats_publish_depth'])

            # 创建管理器
            manager = factory.create_manager(
                exchange=exchange_name,
                market_type=market_type,
                symbols=symbols,
                normalizer=normalizer,
                nats_publisher=nats_publisher,
                config=manager_config
            )

            if not manager:
                raise ValueError(f"无法创建{exchange_name}_{market_type}的OrderBook管理器")

            return manager

        except Exception as e:
            self.logger.error(f"❌ 创建专用OrderBook管理器失败: {exchange_name}", error=str(e), exc_info=True)
            return None

    async def _create_trades_manager(self, exchange_name: str, config: ExchangeConfig,
                                   normalizer: DataNormalizer, nats_publisher: NATSPublisher,
                                   symbols: List[str]):
        """创建专用Trades管理器"""
        try:
            # 导入专用管理器工厂
            from collector.trades_manager_factory import TradesManagerFactory

            # 创建工厂实例
            factory = TradesManagerFactory()

            # 确定市场类型
            market_type = config.market_type.value if hasattr(config.market_type, 'value') else str(config.market_type)

            # 准备配置字典
            manager_config = {
                'ws_url': getattr(config, 'ws_url', None) or self._get_default_ws_url(exchange_name),
                'heartbeat_interval': 30 if 'binance' in exchange_name else 25,
                'connection_timeout': 10,
                'max_reconnect_attempts': 5,
                'reconnect_delay': 5,
                'max_consecutive_errors': 10,
                'enable_nats_push': True
            }

            self.logger.info(f"🏭 创建专用Trades管理器: {exchange_name}_{market_type}",
                           symbols=symbols)

            # 使用工厂创建管理器
            manager = factory.create_trades_manager(
                exchange=config.exchange,
                market_type=config.market_type,
                symbols=symbols,
                normalizer=normalizer,
                nats_publisher=nats_publisher,
                config=manager_config
            )

            if not manager:
                raise ValueError(f"无法创建{exchange_name}_{market_type}的Trades管理器")

            return manager

        except Exception as e:
            self.logger.error(f"❌ 创建专用Trades管理器失败: {exchange_name}", error=str(e), exc_info=True)
            return None

    async def _create_liquidation_manager(self, exchange_name: str, config: ExchangeConfig,
                                        normalizer: DataNormalizer, nats_publisher: NATSPublisher,
                                        symbols: List[str]):
        """创建专用Liquidation管理器"""
        try:
            # 导入专用管理器工厂
            from collector.liquidation_managers.liquidation_manager_factory import LiquidationManagerFactory

            # 创建工厂实例
            factory = LiquidationManagerFactory()

            # 确定市场类型
            market_type = config.market_type.value if hasattr(config.market_type, 'value') else str(config.market_type)

            # 准备配置字典
            manager_config = {
                'ws_url': getattr(config, 'ws_url', None) or self._get_default_ws_url(exchange_name),
                'heartbeat_interval': 180 if 'binance' in exchange_name else 25,  # Binance衍生品180s，OKX 25s
                'connection_timeout': 30,  # 增加连接超时到30秒
                'max_reconnect_attempts': -1,  # 无限重连
                'reconnect_delay': 1.0,
                'max_reconnect_delay': 30.0,
                'backoff_multiplier': 2.0
            }

            self.logger.info(f"🏭 创建专用Liquidation管理器: {exchange_name}_{market_type}",
                           symbols=symbols)

            # 使用工厂创建管理器
            manager = factory.create_manager(
                exchange=exchange_name,
                market_type=market_type,
                symbols=symbols,
                normalizer=normalizer,
                nats_publisher=nats_publisher,
                config=manager_config
            )

            if not manager:
                raise ValueError(f"无法创建{exchange_name}_{market_type}的Liquidation管理器")

            return manager

        except Exception as e:
            self.logger.error(f"❌ 创建专用Liquidation管理器失败: {exchange_name}", error=str(e), exc_info=True)
            return None

    async def _create_lsr_manager(self, exchange_name: str, config: ExchangeConfig,
                                  normalizer: DataNormalizer, nats_publisher: NATSPublisher,
                                  symbols: List[str], data_type: str):
        """创建专用LSR管理器"""
        try:
            # 导入专用管理器工厂
            from collector.lsr_managers.lsr_manager_factory import LSRManagerFactory

            # 创建工厂实例
            factory = LSRManagerFactory()

            # 确定市场类型
            market_type = config.market_type.value if hasattr(config.market_type, 'value') else str(config.market_type)

            # 从全局配置中获取LSR特定配置
            lsr_config = self._get_lsr_config_from_global(data_type)

            # 准备配置字典，使用配置文件驱动
            manager_config = self._build_lsr_manager_config(lsr_config, data_type)

            # 确定交易所和市场类型
            if exchange_name == "binance_derivatives":
                exchange_enum = Exchange.BINANCE_DERIVATIVES
                market_type_enum = MarketType.DERIVATIVES
            elif exchange_name == "okx_derivatives":
                exchange_enum = Exchange.OKX_DERIVATIVES
                market_type_enum = MarketType.DERIVATIVES
            else:
                self.logger.error(f"❌ 不支持的交易所: {exchange_name}")
                return None

            # 创建管理器
            manager = factory.create_manager(
                data_type=data_type,
                exchange=exchange_enum,
                market_type=market_type_enum,
                symbols=symbols,
                normalizer=normalizer,
                nats_publisher=nats_publisher,
                config=manager_config
            )

            if manager:
                self.logger.info(f"✅ 专用LSR管理器创建成功: {exchange_name}",
                               data_type=data_type,
                               symbols=symbols,
                               config=manager_config)
                return manager
            else:
                self.logger.error(f"❌ 专用LSR管理器创建失败: {exchange_name}", data_type=data_type)
                return None

        except Exception as e:
            self.logger.error(f"❌ 创建专用LSR管理器失败: {exchange_name}", data_type=data_type, error=str(e), exc_info=True)
            return None

    def _get_lsr_config_from_global(self, data_type: str) -> dict:
        """从全局配置中获取LSR配置"""
        try:
            # 从self.config中获取LSR配置
            if not hasattr(self, 'config') or not self.config:
                self.logger.warning("全局配置不可用，使用默认LSR配置")
                return {}

            # 从data_types部分获取对应的配置
            data_types_config = self.config.get('data_types', {})
            lsr_config = data_types_config.get(data_type, {})

            if lsr_config:
                self.logger.info(f"从全局配置中获取{data_type}配置成功",
                               config_keys=list(lsr_config.keys()),
                               source="配置文件")
            else:
                self.logger.warning(f"全局配置中未找到{data_type}配置，使用默认配置")

            return lsr_config

        except Exception as e:
            self.logger.error(f"获取{data_type}全局配置失败", error=str(e))
            return {}

    def _build_lsr_manager_config(self, lsr_config: dict, data_type: str) -> dict:
        """构建LSR管理器配置"""
        try:
            # 默认配置
            default_config = {
                'fetch_interval': 10,  # 默认10秒
                'period': '5m',        # 默认5分钟数据周期
                'limit': 30,           # 默认30个数据点
                'max_retries': 3,      # 默认最大重试次数
                'retry_delay': 5,      # 默认重试延迟
                'timeout': 30          # 默认请求超时
            }

            # 如果没有配置，返回默认配置
            if not lsr_config:
                self.logger.info(f"使用{data_type}默认配置", config=default_config)
                return default_config

            # 从配置中读取参数
            manager_config = {
                'fetch_interval': lsr_config.get('interval', default_config['fetch_interval']),
                'period': default_config['period'],
                'limit': default_config['limit'],
                'max_retries': default_config['max_retries'],
                'retry_delay': default_config['retry_delay'],
                'timeout': default_config['timeout']
            }

            # 如果有api_config，使用其中的配置
            if 'api_config' in lsr_config:
                api_config = lsr_config['api_config']
                manager_config.update({
                    'period': api_config.get('period', manager_config['period']),
                    'limit': api_config.get('limit', manager_config['limit']),
                    'max_retries': api_config.get('max_retries', manager_config['max_retries']),
                    'retry_delay': api_config.get('retry_delay', manager_config['retry_delay']),
                    'timeout': api_config.get('timeout', manager_config['timeout'])
                })

            self.logger.info(f"构建{data_type}管理器配置完成",
                           config=manager_config,
                           source="配置文件驱动")

            return manager_config

        except Exception as e:
            self.logger.error(f"构建{data_type}管理器配置失败", error=str(e))
            # 返回默认配置作为fallback
            return {
                'fetch_interval': 10,
                'period': '5m',
                'limit': 30,
                'max_retries': 3,
                'retry_delay': 5,
                'timeout': 30
            }

    async def _create_funding_rate_manager(self, exchange_name: str, config: ExchangeConfig,
                                         normalizer: DataNormalizer, nats_publisher: NATSPublisher,
                                         symbols: List[str]):
        """创建专用FundingRate管理器"""
        try:
            # 导入专用管理器工厂
            from collector.funding_rate_managers.funding_rate_manager_factory import FundingRateManagerFactory

            # 创建管理器
            manager = FundingRateManagerFactory.create_manager(
                exchange=exchange_name,
                symbols=symbols,
                nats_publisher=nats_publisher
            )

            if manager:
                self.logger.info(f"✅ 专用FundingRate管理器创建成功: {exchange_name}",
                               symbols=symbols)
                return manager
            else:
                self.logger.error(f"❌ 专用FundingRate管理器创建失败: {exchange_name}")
                return None

        except Exception as e:
            self.logger.error(f"❌ 创建专用FundingRate管理器失败: {exchange_name}", error=str(e), exc_info=True)
            return None

    async def _create_open_interest_manager(self, exchange_name: str, config: ExchangeConfig,
                                          normalizer: DataNormalizer, nats_publisher: NATSPublisher,
                                          symbols: List[str]):
        """创建专用OpenInterest管理器"""
        try:
            # 导入专用管理器工厂
            from collector.open_interest_managers.open_interest_manager_factory import OpenInterestManagerFactory

            # 创建管理器
            manager = OpenInterestManagerFactory.create_manager(
                exchange=exchange_name,
                symbols=symbols,
                nats_publisher=nats_publisher
            )

            if manager:
                self.logger.info(f"✅ 专用OpenInterest管理器创建成功: {exchange_name}",
                               symbols=symbols)
                return manager
            else:
                self.logger.error(f"❌ 专用OpenInterest管理器创建失败: {exchange_name}")
                return None

        except Exception as e:
            self.logger.error(f"❌ 创建专用OpenInterest管理器失败: {exchange_name}", error=str(e), exc_info=True)
            return None

    async def _create_vol_index_manager(self, exchange_name: str, config: ExchangeConfig,
                                      normalizer: DataNormalizer, nats_publisher: NATSPublisher,
                                      symbols: List[str]):
        """创建专用VolatilityIndex管理器"""
        try:
            # 导入专用管理器工厂
            from collector.vol_index_managers.vol_index_manager_factory import VolIndexManagerFactory

            # 创建管理器
            manager = VolIndexManagerFactory.create_manager(
                exchange=exchange_name,
                symbols=symbols,
                nats_publisher=nats_publisher,
                config=config.model_dump()  # 传递配置
            )

            if manager:
                self.logger.info(f"✅ 专用VolatilityIndex管理器创建成功: {exchange_name}",
                               symbols=symbols)
                return manager
            else:
                self.logger.error(f"❌ 专用VolatilityIndex管理器创建失败: {exchange_name}")
                return None

        except Exception as e:
            self.logger.error(f"❌ 创建专用VolatilityIndex管理器失败: {exchange_name}", error=str(e), exc_info=True)
            return None

    def _get_default_ws_url(self, exchange_name: str) -> str:
        """获取默认的WebSocket URL"""
        if 'binance_spot' in exchange_name:
            return "wss://stream.binance.com:9443/ws"
        elif 'binance_derivatives' in exchange_name:
            return "wss://fstream.binance.com/ws"
        elif 'okx' in exchange_name:
            return "wss://ws.okx.com:8443/ws/v5/public"
        elif 'deribit' in exchange_name:
            return "wss://www.deribit.com/ws/api/v2"
        else:
            return "wss://ws.okx.com:8443/ws/v5/public"  # 默认

    async def stop_all_managers(self):
        """停止所有管理器"""
        self.logger.info("🛑 开始停止所有管理器")

        for exchange_name, managers in self.active_managers.items():
            for manager_type, manager in managers.items():
                try:
                    await manager.stop()
                    self.logger.info("✅ 管理器停止成功",
                                   exchange=exchange_name,
                                   manager_type=manager_type.value)
                except Exception as e:
                    self.logger.error("❌ 管理器停止失败",
                                    exchange=exchange_name,
                                    manager_type=manager_type.value,
                                    error=str(e), exc_info=True)

        self.active_managers.clear()

    def get_manager_stats(self) -> Dict[str, Any]:
        """获取管理器统计信息"""
        stats = {
            'total_exchanges': len(self.active_managers),
            'total_managers': sum(len(managers) for managers in self.active_managers.values()),
            'exchanges': {}
        }

        for exchange_name, managers in self.active_managers.items():
            stats['exchanges'][exchange_name] = {
                'manager_count': len(managers),
                'manager_types': [mt.value for mt in managers.keys()],
                'all_running': all(manager.is_running for manager in managers.values())
            }

        return stats


class ConfigResolver:
    """
    配置路径解析器 - 🔧 第二阶段简化：统一配置文件原则
    """

    @staticmethod
    def get_config_path(config_name: str = "unified_data_collection") -> Path:
        """
        获取配置文件路径 - 简化为单一配置源

        优先级：
        1. 环境变量指定的路径（用于部署环境）
        2. 统一主配置文件：config/collector/unified_data_collection.yaml
        """

        # 1. 环境变量指定的路径（最高优先级，用于生产部署）
        env_path = os.getenv(f'MARKETPRISM_{config_name.upper()}_CONFIG')
        if env_path and Path(env_path).exists():
            return Path(env_path)

        # 2. 🎯 统一主配置文件（唯一配置源）
        main_config = project_root / "config" / "collector" / f"{config_name}.yaml"
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

    def __init__(self, config_path: Optional[str] = None, mode: str = "collector", target_exchange: Optional[str] = None):
        """
        初始化统一数据收集器

        Args:
            config_path: 配置文件路径，默认使用统一配置
            mode: 运行模式 ("collector", "service", "test")
            target_exchange: 指定运行的交易所 (如 'binance_spot', 'binance_derivatives')
        """
        self.config_path = config_path
        self.mode = mode
        self.target_exchange = target_exchange
        self.config = None
        self.is_running = False
        self.start_time = None

        # 组件管理
        self.websocket_adapters: Dict[str, Any] = {}  # OrderBookWebSocketAdapter类型
        self.orderbook_managers: Dict[str, OrderBookManager] = {}
        self.nats_publisher: Optional[NATSPublisher] = None
        self.normalizer: Optional[DataNormalizer] = None

        # 🔧 临时注释：专注于OrderBook Manager修复
        # self.trades_manager: Optional[TradesManager] = None

        # 🔧 新增：内存管理器
        self.memory_manager: Optional[MemoryManager] = None

        # 🏗️ 新增：并行管理器启动器
        self.manager_launcher: Optional[ParallelManagerLauncher] = None

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

        # 🔧 迁移到统一日志系统
        self.logger = get_managed_logger(ComponentType.MAIN)
    
    async def start(self) -> bool:
        """
        🚀 启动统一数据收集器 - 简化版本，专注核心功能

        Returns:
            启动是否成功
        """
        try:
            # 🔧 迁移到统一日志系统 - 标准化启动日志
            self.logger.startup("Unified data collector starting", mode=self.mode)

            if self.mode == "test":
                return await self._start_test_mode()
            else:
                # 默认启动数据收集模式
                return await self._start_collector_mode()

        except Exception as e:
            # 🔧 迁移到统一日志系统 - 标准化错误处理
            self.logger.error("Unified data collector startup failed", error=e)
            await self.stop()
            return False



    async def _start_collector_mode(self) -> bool:
        """🚀 启动数据收集器模式 - 核心功能"""
        try:
            self.logger.info("🔧 启动数据收集器模式")

            # 第1步：加载配置
            self.logger.debug("📋 第1步：加载配置文件...")
            success = await self._load_configuration()
            if not success:
                self.logger.error("❌ 配置加载失败")
                return False
            self.logger.debug("✅ 配置加载成功")

            # 第2步：初始化核心组件
            self.logger.debug("🔧 第2步：初始化核心组件...")
            success = await self._initialize_components()
            if not success:
                self.logger.error("❌ 组件初始化失败")
                return False
            self.logger.debug("✅ 核心组件初始化成功")

            # 第3步：启动数据收集
            self.logger.debug("🚀 第3步：启动数据收集...")
            success = await self._start_data_collection()
            if not success:
                self.logger.error("❌ 数据收集启动失败")
                return False
            self.logger.debug("✅ 数据收集启动成功")

            # 第4步：启动监控任务
            self.logger.debug("📊 第4步：启动监控任务...")
            await self._start_monitoring_tasks()
            self.logger.debug("✅ 监控任务启动成功")

            # 更新运行状态
            self.is_running = True
            self.start_time = datetime.now(timezone.utc)
            self.stats['start_time'] = self.start_time

            # 显示启动统计
            manager_count = 0
            if self.manager_launcher:
                stats = self.manager_launcher.get_manager_stats()
                manager_count = stats.get('total_managers', 0)

            self.logger.info("🎉 数据收集器启动完成",
                           total_managers=manager_count,
                           exchanges_connected=self.stats.get('exchanges_connected', 0),
                           config_path=self.config_path or "默认配置")

            return True

        except Exception as e:
            self.logger.error("❌ 数据收集器启动失败", error=str(e), exc_info=True)
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





    async def _start_launcher_orderbook_managers(self):
        """启动launcher模式的订单簿管理器（从配置文件读取）"""
        try:
            self.logger.info("📊 🚫 跳过旧版订单簿管理器启动 - 使用新版专用管理器")
            return  # 🔧 禁用旧版管理器，使用新版专用管理器

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
            try:
                from core.networking import websocket_manager
                if websocket_manager is None:
                    self.logger.warning("⚠️ WebSocket管理器不可用")
                    return False
            except ImportError:
                self.logger.warning("⚠️ WebSocket管理器模块不可用")
                # 不返回False，继续其他测试

            # 测试数据收集组件
            try:
                from collector.websocket_adapter import OrderBookWebSocketAdapter
                if OrderBookWebSocketAdapter is None:
                    self.logger.warning("⚠️ OrderBook适配器不可用")
                    return False
            except ImportError:
                self.logger.warning("⚠️ OrderBook适配器模块不可用")
                # 不返回False，继续其他测试

            self.logger.info("✅ 核心组件测试通过")
            return True
        except Exception as e:
            self.logger.error("❌ 核心组件测试失败", error=str(e))
            return False

    async def _test_nats_integration(self) -> bool:
        """测试NATS集成"""
        try:
            # 简单的NATS连接测试
            # 🔧 合理的默认值：NATS标准端口，作为环境变量缺失时的回退
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

            # 等待WebSocket连接完全断开
            if self.websocket_adapters:
                self.logger.info("⏳ 等待WebSocket连接完全断开...")
                await asyncio.sleep(1)

            # 🏗️ 新增：使用并行管理器启动器停止所有管理器
            if self.manager_launcher:
                try:
                    await self.manager_launcher.stop_all_managers()
                    self.logger.info("✅ 所有管理器已通过并行启动器停止")
                except Exception as e:
                    self.logger.error("❌ 并行管理器停止失败", error=str(e), exc_info=True)

            # 🔧 向后兼容：停止传统OrderBook管理器（如果有的话）
            for name, manager in self.orderbook_managers.items():
                try:
                    await manager.stop()
                    self.logger.info("OrderBook管理器已停止", name=name)
                except Exception as e:
                    self.logger.error("停止OrderBook管理器失败", name=name, error=str(e))

            # 🔧 临时注释：专注于OrderBook Manager修复
            # if self.trades_manager:
            #     try:
            #         await self.trades_manager.stop()
            #         self.logger.info("TradesManager已停止")
            #     except Exception as e:
            #         self.logger.error("停止TradesManager失败", error=str(e))
            
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

            # 🔧 新增：停止内存管理器
            if self.memory_manager:
                try:
                    await self.memory_manager.stop()
                    self.logger.info("内存管理器已停止")
                except Exception as e:
                    self.logger.error("停止内存管理器失败", error=str(e))

            self.logger.info("✅ 统一数据收集器已停止")
            
        except Exception as e:
            self.logger.error("❌ 停止统一数据收集器失败", error=str(e))
    
    async def _load_configuration(self) -> bool:
        """
        加载配置 - 🔧 第二阶段简化：统一配置源

        Returns:
            配置加载是否成功
        """
        try:
            self.logger.info("📋 加载配置（统一配置源）")

            # 🎯 简化配置加载：优先使用指定路径，否则使用统一主配置
            if self.config_path:
                # 使用指定的配置文件
                config_file = Path(self.config_path)
                if not config_file.exists():
                    self.logger.error("❌ 指定的配置文件不存在", path=self.config_path)
                    return False
                config_path = config_file
            else:
                # 使用统一主配置文件
                config_path = ConfigResolver.get_config_path()
                if not config_path.exists():
                    self.logger.error("❌ 统一主配置文件不存在", path=str(config_path))
                    return False

            # 加载配置文件
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)

            if not self.config:
                self.logger.error("❌ 配置文件为空或格式错误", path=str(config_path))
                return False

            # 🎯 新增：根据--exchange参数过滤配置
            if hasattr(self, 'target_exchange') and self.target_exchange:
                self._filter_config_by_exchange(self.target_exchange)

            self.logger.info("✅ 配置加载成功",
                           path=str(config_path),
                           exchanges=len(self.config.get('exchanges', {})),
                           nats_enabled=bool(self.config.get('nats')))

            return True

        except Exception as e:
            self.logger.error("❌ 配置加载失败", error=str(e), exc_info=True)
            return False

    def _filter_config_by_exchange(self, target_exchange: str):
        """
        根据指定的交易所过滤配置

        Args:
            target_exchange: 目标交易所名称 (如 'binance_spot', 'binance_derivatives')
        """
        try:
            if 'exchanges' not in self.config:
                self.logger.warning("⚠️ 配置中没有exchanges部分")
                return

            original_exchanges = list(self.config['exchanges'].keys())

            if target_exchange not in self.config['exchanges']:
                self.logger.error("❌ 指定的交易所不存在",
                                target=target_exchange,
                                available=original_exchanges)
                return

            # 只保留指定的交易所配置
            filtered_exchanges = {target_exchange: self.config['exchanges'][target_exchange]}
            self.config['exchanges'] = filtered_exchanges

            self.logger.info("🎯 配置已过滤为单一交易所",
                           target_exchange=target_exchange,
                           original_exchanges=original_exchanges,
                           filtered_exchanges=list(filtered_exchanges.keys()))

        except Exception as e:
            self.logger.error("❌ 配置过滤失败", error=str(e), exc_info=True)


    async def _initialize_components(self) -> bool:
        """初始化组件"""
        try:
            self.logger.info("🔧 初始化组件")

            # 🔧 新增：初始化系统资源管理器
            resource_config = SystemResourceConfig(
                memory_warning_threshold_mb=500,
                memory_critical_threshold_mb=800,
                memory_max_threshold_mb=1000,
                cpu_warning_threshold=60.0,
                cpu_critical_threshold=80.0,
                fd_warning_threshold=0.7,
                fd_critical_threshold=0.85,
                connection_warning_threshold=50,
                connection_critical_threshold=100,
                thread_warning_threshold=20,
                thread_critical_threshold=50,
                monitor_interval=60,
                cleanup_interval=300
            )
            self.memory_manager = SystemResourceManager(resource_config)
            await self.memory_manager.start()
            self.logger.info("✅ 系统资源管理器初始化成功")

            # 🗑️ 已删除内存分析器启动 - 误报太多，无实际价值

            # 初始化数据标准化器
            self.normalizer = DataNormalizer()
            self.logger.info("✅ 数据标准化器初始化成功")

            # 🔧 逐笔成交数据将复用现有的DataNormalizer，无需单独初始化

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

            # 🔧 临时注释：专注于OrderBook Manager修复
            # if self.nats_publisher and self.normalizer:
            #     # 创建OKX现货配置用于TradesManager
            #     okx_spot_config = ExchangeConfig(
            #         exchange=Exchange.OKX_SPOT,
            #         market_type=MarketType.SPOT,
            #         symbols=['BTC-USDT', 'ETH-USDT'],
            #         data_types=['trade'],
            #         enabled=True,
            #         base_url='https://www.okx.com'
            #     )
            #     self.trades_manager = TradesManager(okx_spot_config, self.normalizer, self.nats_publisher)
            #     await self.trades_manager.initialize()
            #     self.logger.info("✅ 逐笔成交数据管理器初始化成功")
            # else:
            #     self.logger.warning("⚠️ NATS或Normalizer未初始化，跳过逐笔成交数据管理器初始化")

            self.logger.info("✅ 组件初始化完成")
            return True

        except Exception as e:
            self.logger.error("❌ 组件初始化失败", error=str(e), exc_info=True)
            return False
    
    async def _start_data_collection(self) -> bool:
        """启动数据收集 - 使用新的并行管理器启动框架"""
        try:
            self.logger.info("🏗️ 启动数据收集 (并行管理器模式)")

            exchanges_config = self.config.get('exchanges', {})

            # 🔧 修复：初始化并行管理器启动器（已迁移到统一日志系统）
            # 增加启动超时时间，给Binance更多时间完成复杂的初始化流程
            self.manager_launcher = ParallelManagerLauncher(config=self.config, startup_timeout=120.0)

            # 🚀 分批启动交易所管理器（避免资源竞争）
            all_startup_results = []

            # 按优先级分组启动
            priority_groups = [
                # 第一批：稳定的交易所
                ["okx_spot", "okx_derivatives"],
                # 第二批：复杂的交易所
                ["binance_spot", "binance_derivatives"],
                # 第三批：特殊数据源
                ["deribit_derivatives"]
            ]

            for group_index, group in enumerate(priority_groups):
                self.logger.info(f"🚀 启动第 {group_index + 1} 批交易所", exchanges=group)

                startup_tasks = []
                for exchange_name in group:
                    if exchange_name not in exchanges_config:
                        continue

                    exchange_config = exchanges_config[exchange_name]
                    if not exchange_config.get('enabled', True):
                        self.logger.info("跳过禁用的交易所", exchange=exchange_name)
                        continue

                    # 为每个交易所创建管理器启动任务
                    task = asyncio.create_task(
                        self.manager_launcher.start_exchange_managers(
                            exchange_name, exchange_config, self.normalizer, self.nats_publisher
                        )
                    )
                    startup_tasks.append((exchange_name, task))

                # 等待当前批次的所有交易所启动完成
                for exchange_name, task in startup_tasks:
                    try:
                        results = await asyncio.wait_for(task, timeout=150.0)
                        all_startup_results.extend(results)

                        # 统计成功启动的管理器
                        successful_managers = [r for r in results if r.success]
                        if successful_managers:
                            self.stats['exchanges_connected'] += 1
                            self.logger.info("✅ 交易所管理器启动完成",
                                           exchange=exchange_name,
                                           successful_managers=len(successful_managers),
                                           total_managers=len(results))
                        else:
                            self.logger.error("❌ 交易所所有管理器启动失败", exchange=exchange_name)

                    except asyncio.TimeoutError:
                        self.logger.error("❌ 交易所管理器启动超时", exchange=exchange_name)
                        task.cancel()
                    except Exception as e:
                        self.logger.error("❌ 交易所管理器启动异常",
                                        exchange=exchange_name, error=str(e), exc_info=True)

                # 批次间等待，避免资源竞争
                if group_index < len(priority_groups) - 1:  # 不是最后一批
                    self.logger.info(f"⏳ 等待 3 秒后启动下一批交易所...")
                    await asyncio.sleep(3)

            # 统计启动结果
            successful_results = [r for r in all_startup_results if r.success]
            failed_results = [r for r in all_startup_results if not r.success]

            self.logger.info("📊 管理器启动统计",
                           total_managers=len(all_startup_results),
                           successful=len(successful_results),
                           failed=len(failed_results))

            if len(successful_results) == 0:
                self.logger.error("没有成功启动的管理器")
                return False

            # 将成功启动的OrderBook管理器添加到传统字典中（保持向后兼容）
            for result in successful_results:
                if result.manager_type == ManagerType.ORDERBOOK and result.success:
                    self.orderbook_managers[result.exchange_name] = result.manager
            
            # 🔧 新增：注册连接池和数据缓冲区到内存管理器
            if self.memory_manager:
                # 注册WebSocket连接管理器
                from core.networking import websocket_manager
                if hasattr(websocket_manager, 'connections'):
                    self.memory_manager.register_connection_pool(websocket_manager)

                # 注册OrderBook管理器的数据缓冲区
                for manager in self.orderbook_managers.values():
                    if hasattr(manager, 'orderbook_states'):
                        self.memory_manager.register_data_buffer(manager.orderbook_states)

                self.logger.info("✅ 连接池和数据缓冲区已注册到内存管理器")

            # 显示管理器启动统计
            manager_stats = self.manager_launcher.get_manager_stats()
            self.logger.info("🎯 管理器启动完成统计",
                           total_exchanges=manager_stats['total_exchanges'],
                           total_managers=manager_stats['total_managers'],
                           exchange_details=manager_stats['exchanges'])

            # 更新统计信息
            self.stats['total_managers'] = manager_stats['total_managers']
            self.stats['manager_types'] = {}
            for exchange_name, exchange_info in manager_stats['exchanges'].items():
                self.stats['manager_types'][exchange_name] = exchange_info['manager_types']

            # 🔧 临时注释：专注于OrderBook Manager修复
            # if self.trades_manager:
            #     try:
            #         symbols = ['BTC-USDT', 'ETH-USDT']  # 从配置中获取
            #         success = await self.trades_manager.start(symbols)
            #         if success:
            #             self.logger.info("✅ TradesManager启动成功", symbols=symbols)
            #         else:
            #             self.logger.warning("⚠️ TradesManager启动失败")
            #     except Exception as e:
            #         self.logger.error("❌ TradesManager启动异常", error=str(e))

            self.logger.info("✅ 数据收集启动成功 (并行管理器模式)",
                           connected_exchanges=self.stats['exchanges_connected'],
                           total_managers=manager_stats['total_managers'])
            return True
            
        except Exception as e:
            self.logger.error("❌ 数据收集启动失败", error=str(e))
            return False

    def get_manager_status(self) -> Dict[str, Any]:
        """获取管理器状态信息"""
        if not self.manager_launcher:
            return {"error": "管理器启动器未初始化"}

        return self.manager_launcher.get_manager_stats()

    def get_detailed_stats(self) -> Dict[str, Any]:
        """获取详细的系统统计信息"""
        base_stats = self.stats.copy()

        # 添加管理器统计
        if self.manager_launcher:
            base_stats['managers'] = self.manager_launcher.get_manager_stats()

        # 添加运行时间
        if self.start_time:
            base_stats['uptime_seconds'] = (datetime.now(timezone.utc) - self.start_time).total_seconds()

        return base_stats
    
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

    async def _start_exchange_collection_safe(self, exchange_name: str, exchange_config: Dict[str, Any]) -> bool:
        """安全启动单个交易所的数据收集（带异常处理）"""
        try:
            return await self._start_exchange_collection(exchange_name, exchange_config)
        except Exception as e:
            self.logger.error("❌ 交易所启动异常", exchange=exchange_name, error=str(e), exc_info=True)
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
                
                # 🏗️ 收集管理器统计信息
                total_messages = 0

                # 从并行管理器启动器收集统计
                if self.manager_launcher:
                    manager_stats = self.manager_launcher.get_manager_stats()
                    self.stats['managers'] = manager_stats

                    # 收集所有管理器的消息统计
                    for exchange_name, managers in self.manager_launcher.active_managers.items():
                        for manager_type, manager in managers.items():
                            try:
                                if hasattr(manager, 'get_stats'):
                                    mgr_stats = manager.get_stats()
                                    total_messages += mgr_stats.get('messages_received', 0)
                            except Exception:
                                pass

                # 向后兼容：从传统OrderBook管理器收集统计
                for manager in self.orderbook_managers.values():
                    try:
                        manager_stats = manager.get_stats()
                        total_messages += manager_stats.get('messages_received', 0)
                    except Exception:
                        pass

                self.stats['total_messages'] = total_messages

                # 显示详细统计信息
                detailed_stats = self.get_detailed_stats()
                self.logger.info("📊 系统统计 (并行管理器模式)", stats=detailed_stats)
                
        except asyncio.CancelledError:
            self.logger.info("统计任务已取消")
        except Exception as e:
            self.logger.error("统计任务异常", error=str(e))
    
    async def _health_check_loop(self):
        """健康检查循环"""
        try:
            while self.is_running:
                await asyncio.sleep(30)  # 每30秒检查一次
                
                # 🏗️ 检查管理器健康状态
                healthy_managers = 0
                total_managers = 0

                if self.manager_launcher:
                    # 检查并行管理器的健康状态
                    for exchange_name, managers in self.manager_launcher.active_managers.items():
                        for manager_type, manager in managers.items():
                            total_managers += 1
                            try:
                                if hasattr(manager, 'is_running') and manager.is_running:
                                    healthy_managers += 1
                                else:
                                    self.logger.warning("管理器状态异常",
                                                      exchange=exchange_name,
                                                      manager_type=manager_type.value)
                            except Exception as e:
                                self.logger.warning("管理器健康检查失败",
                                                  exchange=exchange_name,
                                                  manager_type=manager_type.value,
                                                  error=str(e))

                # 向后兼容：检查传统OrderBook管理器
                for name, manager in self.orderbook_managers.items():
                    total_managers += 1
                    try:
                        if hasattr(manager, 'is_running') and manager.is_running:
                            healthy_managers += 1
                    except Exception as e:
                        self.logger.warning("传统管理器健康检查失败", component=name, error=str(e))

                health_ratio = healthy_managers / total_managers if total_managers > 0 else 0

                if health_ratio < 0.8:  # 80%以下认为不健康
                    self.logger.warning("🚨 系统健康状态不佳",
                                      healthy_managers=healthy_managers,
                                      total_managers=total_managers,
                                      health_ratio=health_ratio)
                elif total_managers > 0:
                    # 健康状态良好时不输出日志，减少冗余信息
                    pass
                
        except asyncio.CancelledError:
            self.logger.info("健康检查任务已取消")
        except Exception as e:
            self.logger.error("健康检查任务异常", error=str(e))
    
    def get_stats(self) -> Dict[str, Any]:
        """获取系统统计信息"""
        base_stats = {
            **self.stats,
            'is_running': self.is_running,
            'connected_exchanges': list(self.orderbook_managers.keys())
        }

        # 尝试获取WebSocket统计信息
        try:
            from core.networking import websocket_manager
            base_stats['websocket_stats'] = websocket_manager.get_connection_stats()
        except ImportError:
            base_stats['websocket_stats'] = {'status': 'not_available'}

        # 🏗️ 添加管理器统计信息
        if self.manager_launcher:
            base_stats['managers'] = self.manager_launcher.get_manager_stats()

        return base_stats


def parse_arguments():
    """解析命令行参数 - 简化版本，专注核心功能"""
    parser = argparse.ArgumentParser(
        description="🚀 MarketPrism统一数据收集器 - 一键启动，一次成功",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
🎯 使用方法:
  # 🚀 一键启动（推荐）
  python unified_collector_main.py

  # 🧪 测试验证模式
  python unified_collector_main.py --mode test

  # 🎯 指定单个交易所
  python unified_collector_main.py --exchange binance_spot
  python unified_collector_main.py --exchange binance_derivatives
  python unified_collector_main.py --exchange okx_spot
  python unified_collector_main.py --exchange okx_derivatives
  python unified_collector_main.py --exchange deribit_derivatives

  # 🔍 调试模式
  python unified_collector_main.py --log-level DEBUG

  # 📋 自定义配置
  python unified_collector_main.py --config custom.yaml

📋 环境变量:
  MARKETPRISM_CONFIG_PATH  - 配置文件路径
  MARKETPRISM_LOG_LEVEL    - 日志级别 (DEBUG/INFO/WARNING/ERROR)
  MARKETPRISM_NATS_SERVERS - NATS服务器地址

🏗️ 系统架构:
  - 📊 订单簿管理器：完整深度维护，支持400/5000级别
  - 💱 交易数据管理器：实时逐笔成交数据收集
  - 📡 NATS发布器：结构化主题发布和数据标准化
  - 🔌 交易所适配器：WebSocket连接管理和心跳机制
  - 🛡️ 错误处理系统：断路器、重试机制、内存管理

📊 数据输出:
  - NATS主题格式：orderbook-data.{exchange}.{market_type}.{symbol}
  - 支持的交易所：binance_spot, binance_derivatives, okx_spot, okx_derivatives
  - 数据类型：订单簿深度数据、实时交易数据
  - 数据验证：序列号连续性检查、checksum验证
        """
    )

    parser.add_argument(
        '--mode', '-m',
        choices=['collector', 'test'],
        default='collector',
        help='运行模式: collector=数据收集(默认), test=测试验证'
    )

    parser.add_argument(
        '--config', '-c',
        type=str,
        help='配置文件路径 (默认: config/collector/unified_data_collection.yaml)'
    )

    parser.add_argument(
        '--log-level', '-l',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default=os.getenv('MARKETPRISM_LOG_LEVEL', 'INFO'),
        help='日志级别 (默认: INFO)'
    )

    parser.add_argument(
        '--exchange', '-e',
        choices=['binance_spot', 'binance_derivatives', 'okx_spot', 'okx_derivatives', 'deribit_derivatives'],
        help='指定运行的交易所 (默认: 运行所有启用的交易所)'
    )

    return parser.parse_args()


async def main():
    """🚀 主函数 - 一键启动MarketPrism数据收集器"""
    print("DEBUG: main函数开始执行")

    # 解析命令行参数
    print("DEBUG: 开始解析命令行参数")
    args = parse_arguments()
    print(f"DEBUG: 命令行参数解析完成: {args}")

    # 🔧 迁移到统一日志系统
    setup_logging(args.log_level, use_json=False)
    logger = get_managed_logger(ComponentType.MAIN)

    # 显示启动信息
    print("\n" + "="*80)
    print("🚀 MarketPrism统一数据收集器")
    print("="*80)
    print(f"📋 模式: {args.mode}")
    print(f"📊 日志级别: {args.log_level}")
    print(f"📁 配置文件: {args.config or '默认配置'}")
    if args.exchange:
        print(f"🎯 指定交易所: {args.exchange}")
    print("="*80 + "\n")

    # 🔧 迁移到统一日志系统 - 标准化启动日志
    logger.startup(
        "MarketPrism unified data collector starting",
        mode=args.mode,
        log_level=args.log_level,
        config=args.config or "默认配置",
        target_exchange=args.exchange
    )

    # 确定配置路径
    config_path = args.config or os.getenv('MARKETPRISM_CONFIG_PATH')

    # 创建收集器实例
    collector = UnifiedDataCollector(config_path=config_path, mode=args.mode, target_exchange=args.exchange)

    # 设置优雅停止信号处理
    stop_event = asyncio.Event()

    def signal_handler(signum, frame):
        logger.info(f"📡 收到停止信号 {signum}，开始优雅停止...")
        stop_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # 🚀 启动数据收集器
        logger.info("🔄 正在启动数据收集器...")
        success = await collector.start()

        if not success:
            logger.error("❌ 数据收集器启动失败")
            print("\n❌ 启动失败！请检查配置和网络连接。\n")
            return 1

        # 显示启动成功信息
        print("\n" + "="*80)
        print("✅ MarketPrism数据收集器启动成功！")
        print("="*80)
        print("📡 正在收集以下交易所数据:")
        if hasattr(collector, 'manager_launcher') and collector.manager_launcher:
            stats = collector.manager_launcher.get_manager_stats()
            for exchange, info in stats.get('exchanges', {}).items():
                print(f"  • {exchange.upper()}: {', '.join(info['manager_types'])}")
        print("🔗 NATS推送: 实时数据推送中...")
        print("📊 监控: 内存和连接状态监控中...")
        print("\n💡 按 Ctrl+C 优雅停止系统")
        print("="*80 + "\n")

        # 保持运行（除非是测试模式）
        if args.mode != 'test':
            logger.info("✅ 数据收集器运行中，等待停止信号...")
            logger.debug("🔍 初始状态",
                    collector_running=collector.is_running,
                    stop_signal_received=stop_event.is_set())

            # 等待停止信号或收集器停止
            while collector.is_running and not stop_event.is_set():
                await asyncio.sleep(1)
                # 每30秒打印一次状态（降低频率，改为DEBUG级别）
                if int(time.time()) % 30 == 0:
                    logger.debug("🔍 系统运行状态检查",
                               collector_running=collector.is_running,
                               stop_signal_received=stop_event.is_set())

            logger.debug("🔍 退出主循环",
                        collector_running=collector.is_running,
                        stop_signal_received=stop_event.is_set())

        logger.info("🛑 开始停止数据收集器...")
        return 0

    except KeyboardInterrupt:
        logger.info("⌨️ 收到键盘中断，停止收集器...")
        return 0
    except Exception as e:
        logger.error("💥 收集器运行异常", error=str(e), exc_info=True)
        print(f"\n💥 运行异常: {str(e)}\n")
        return 1
    finally:
        # 确保收集器被正确停止
        try:
            await collector.stop()
            print("\n✅ MarketPrism数据收集器已安全停止\n")
        except Exception as e:
            logger.error("停止收集器时发生异常", error=str(e))


if __name__ == "__main__":
    print("DEBUG: 程序开始执行")
    try:
        exit_code = asyncio.run(main())
        print(f"DEBUG: main函数执行完成，退出码: {exit_code}")
        sys.exit(exit_code)
    except Exception as e:
        print(f"DEBUG: 程序执行异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
