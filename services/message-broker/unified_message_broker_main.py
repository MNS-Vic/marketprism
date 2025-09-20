#!/usr/bin/env python3
"""
MarketPrism统一消息代理服务 - 生产级消息中间件系统

🎯 设计理念：统一入口、模块化架构、生产级稳定性

🚀 核心功能：
-  JetStream流管理：创建、删除和管理持久化消息流
- 📊 消息路由和分发：高性能消息发布和订阅
- 💾 消息持久化存储：基于JetStream的可靠消息存储
- 🔍 LSR数据订阅：专门的LSR数据订阅和处理功能
- 📈 健康监控：实时监控客户端与流状态

🏗️ 架构设计：
- 📁 模块化组件：仅保留客户端流管理器；NATS 服务器由外部 Docker/集群提供
- 🔌 统一配置：单一YAML配置文件管理所有设置（支持环境变量覆盖 nats_url）
- 🔄 数据订阅：支持 LSR 等数据类型的订阅处理
- 📊 消息统计：完整的消息发布、消费、错误统计
- 🚨 错误处理：多层级错误管理，自动恢复机制

🎯 使用场景：
- 🏢 生产环境：高频消息路由和分发
- 📈 实时数据：LSR等市场数据的实时订阅处理
- 🔍 数据监控：消息流监控和分析
- 📊 系统集成：微服务间消息通信中枢
"""

import asyncio
import signal
import sys
import os
import argparse
import yaml
from pathlib import Path
from typing import Optional, Dict, Any
import structlog
import json
from datetime import datetime

# 添加项目路径
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

# 导入核心模块
try:
    from core.service_framework import BaseService
except ImportError:
    # 如果导入失败，创建一个简单的基类
    class BaseService:
        pass

try:
    from services.message_broker.main import MessageBrokerService
except ImportError:
    # 回退：直接从同目录导入（无需包化）
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from main import MessageBrokerService

# 设置日志
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


class UnifiedMessageBroker:
    """
    MarketPrism统一消息代理服务主类

    🎯 核心功能：
    - 管理NATS服务器的启动和停止
    - 创建和管理JetStream消息流
    - 提供LSR数据订阅和处理功能
    - 支持多种运行模式（broker/subscriber/test）

    🏗️ 架构设计：
    - 基于配置文件的统一管理
    - 模块化组件设计，便于扩展
    - 支持优雅启动和停止
    - 完整的错误处理和恢复机制
    """

    def __init__(self, config_path: Optional[str] = None, mode: str = "broker"):
        """
        初始化统一消息代理服务

        Args:
            config_path (str, optional): 配置文件路径，默认使用标准配置文件
                                       默认路径：config/message-broker/unified_message_broker.yaml
            mode (str): 运行模式，支持以下选项：
                       - "broker": 完整消息代理模式（推荐生产环境）
                       - "subscriber": 仅订阅模式（用于数据消费）
                       - "test": 测试模式（启动代理并运行测试）

        Attributes:
            config_path (str): 实际使用的配置文件路径
            mode (str): 当前运行模式
            config (dict): 加载的配置数据
            message_broker (MessageBrokerService): 核心消息代理服务实例
            lsr_subscriber (LSRSubscriber): LSR数据订阅器实例
            is_running (bool): 服务运行状态标志
        """
        self.config_path = config_path or "services/message-broker/config/unified_message_broker.yaml"
        self.mode = mode
        self.config = None
        self.message_broker: Optional[MessageBrokerService] = None
        self.lsr_subscriber: Optional['LSRSubscriber'] = None
        self.is_running = False

    def load_config(self) -> Dict[str, Any]:
        """
        加载和验证配置文件

        🔧 功能说明：
        - 从指定路径加载YAML配置文件
        - 验证配置文件的存在性和格式正确性
        - 提供详细的错误信息用于调试

        Returns:
            Dict[str, Any]: 解析后的配置数据字典，包含所有服务配置项

        Raises:
            FileNotFoundError: 当配置文件不存在时抛出
            yaml.YAMLError: 当配置文件格式错误时抛出
            Exception: 其他配置加载相关错误

        📝 使用示例：
            config = self.load_config()
            nats_client = config.get('nats_client', {})
        """
        try:
            config_file = Path(self.config_path)
            if not config_file.exists():
                raise FileNotFoundError(f"配置文件不存在: {self.config_path}")

            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            logger.info("配置文件加载成功", config_path=self.config_path)
            return config

        except Exception as e:
            logger.error("配置文件加载失败", error=str(e), config_path=self.config_path)
            raise

    async def start(self) -> bool:
        """
        启动统一消息代理服务

        🚀 启动流程：
        1. 加载配置文件
        2. 根据运行模式选择启动策略
        3. 初始化相应的服务组件
        4. 设置运行状态标志

        Returns:
            bool: 启动成功返回True，失败返回False

        🎯 支持的运行模式：
        - broker: 启动完整的消息代理服务（包括NATS服务器管理）
        - subscriber: 仅启动LSR数据订阅功能
        - test: 启动代理服务并运行内置测试

        ⚠️ 注意事项：
        - 启动失败时会自动调用stop()方法清理资源
        - 所有异常都会被捕获并记录到日志
        """
        try:
            logger.info("🚀 启动MarketPrism统一消息代理服务", mode=self.mode)

            # 加载配置文件，获取所有服务配置参数
            self.config = self.load_config()

            # 根据运行模式选择相应的启动策略
            if self.mode == "broker":
                return await self._start_broker_mode()
            elif self.mode == "subscriber":
                return await self._start_subscriber_mode()
            elif self.mode == "test":
                return await self._start_test_mode()
            else:
                logger.error("未知的运行模式", mode=self.mode)
                return False

        except Exception as e:
            logger.error("统一消息代理服务启动失败", error=str(e))
            await self.stop()
            return False

    async def _start_broker_mode(self) -> bool:
        """
        启动消息代理模式（生产环境推荐模式）

        🎯 功能说明：
        - 启动完整的NATS服务器和JetStream功能
        - 创建和管理消息流
        - 可选择性启动LSR数据订阅器
        - 提供完整的消息代理服务

        🔧 启动步骤：
        1. 构建MessageBrokerService配置
        2. 启动NATS服务器和JetStream
        3. 创建必要的消息流
        4. 根据配置启动LSR订阅器
        5. 设置服务运行状态

        Returns:
            bool: 启动成功返回True，失败时抛出异常

        ⚠️ 注意事项：
        - 需要确保NATS服务器端口（4222, 8222）未被占用
        - 需要足够的磁盘空间用于JetStream数据存储
        """
        try:
            logger.info("📡 启动消息代理模式...")

            # 构建MessageBrokerService所需的配置参数
            # 将 service 段落扁平化到顶层，便于 BaseService.run 读取端口等配置
            # 统一注入：MessageBrokerService 需要在 nats_client 中同时看到 nats_url 与 streams
            service_cfg = self.config.get('service', {})

            nats_client_cfg = dict(self.config.get('nats_client', {}))
            # 环境变量覆盖：MARKETPRISM_NATS_URL 优先于 YAML
            env_nats_url = os.getenv('MARKETPRISM_NATS_URL')
            if env_nats_url:
                nats_client_cfg['nats_url'] = env_nats_url
                logger.info("使用环境变量覆盖NATS地址", env_var="MARKETPRISM_NATS_URL", nats_url=env_nats_url)
            nats_client_cfg['streams'] = self.config.get('streams', {})

            broker_config = {
                **service_cfg,                   # 端口、host、环境等（供 BaseService.run 使用）
                'nats_client': nats_client_cfg,  # 仅作为NATS客户端（含 streams）
            }

            # 创建并启动核心消息代理服务（run会负责on_startup和HTTP服务启动）
            self.message_broker = MessageBrokerService(broker_config)
            self._service_task = asyncio.create_task(self.message_broker.run())

            # 等待HTTP健康端点就绪（最多15秒）
            port = broker_config.get('port', 8086)
            ready = False
            for _ in range(30):
                try:
                    import aiohttp
                    async with aiohttp.ClientSession() as session:
                        async with session.get(f'http://127.0.0.1:{port}/health', timeout=1.5) as resp:
                            if resp.status == 200:
                                ready = True
                                break
                except Exception:
                    pass
                await asyncio.sleep(0.5)
            if not ready:
                logger.warning("HTTP健康端点未在预期时间内就绪", port=port)

            # 根据配置决定是否启动LSR数据订阅器
            # 这允许在同一个进程中同时提供消息代理和数据消费功能
            if self.config.get('lsr_subscription', {}).get('enabled', False):
                logger.info("🔍 启动LSR数据订阅器...")
                await self._start_lsr_subscriber()

            self.is_running = True
            logger.info("✅ 消息代理模式启动成功")
            return True

        except Exception as e:
            logger.error("❌ 消息代理模式启动失败", error=str(e))
            raise

    async def _start_subscriber_mode(self) -> bool:
        """启动订阅器模式"""
        try:
            logger.info("🔍 启动订阅器模式...")

            # 只启动LSR订阅器
            await self._start_lsr_subscriber()

            self.is_running = True
            logger.info("✅ 订阅器模式启动成功")
            return True

        except Exception as e:
            logger.error("❌ 订阅器模式启动失败", error=str(e))
            raise

    async def _start_test_mode(self) -> bool:
        """启动测试模式"""
        try:
            logger.info("🧪 启动测试模式...")

            # 启动消息代理
            await self._start_broker_mode()

            # 运行测试
            await self._run_tests()

            return True

        except Exception as e:
            logger.error("❌ 测试模式启动失败", error=str(e))
            raise

    async def _start_lsr_subscriber(self):
        """
        启动LSR（Long-Short Ratio）数据订阅器

        🎯 功能说明：
        - 订阅来自Data Collector的LSR数据
        - 处理顶级持仓多空比和全账户多空比数据
        - 提供实时数据显示和日志记录
        - 支持多交易所和多交易对订阅

        🔧 实现策略：
        1. 优先尝试加载专用的LSRSubscriber模块
        2. 如果模块不存在，则创建简单的内置订阅器
        3. 使用配置文件中的LSR订阅参数

        📊 订阅的数据类型：
        - lsr_top_position: 顶级持仓多空比数据
        - lsr_all_account: 全账户多空比数据

        ⚠️ 注意事项：
        - 需要确保NATS服务器已启动并且MARKET_DATA流已创建
        - LSR数据的主题格式必须与Data Collector发布的格式匹配
        """
        try:
            # 尝试导入专用的LSR订阅器模块
            from .lsr_subscriber import LSRSubscriber

            # 提取LSR订阅相关配置
            lsr_config = self.config.get('lsr_subscription', {})
            nats_config = self.config.get('nats_client', {})

            # 创建并启动LSR订阅器实例
            self.lsr_subscriber = LSRSubscriber(lsr_config, nats_config)
            await self.lsr_subscriber.start()

            logger.info("✅ LSR数据订阅器启动成功")

        except ImportError:
            # 如果专用模块不存在，使用内置的简单订阅器
            logger.warning("LSRSubscriber模块未找到，将创建简单订阅器")
            await self._create_simple_lsr_subscriber()
        except Exception as e:
            logger.error("❌ LSR数据订阅器启动失败", error=str(e))
            raise

    async def _create_simple_lsr_subscriber(self):
        """
        创建简单的内置LSR订阅器

        🎯 功能说明：
        - 当专用LSRSubscriber模块不可用时的备用方案
        - 提供基本的LSR数据订阅和显示功能
        - 支持实时数据解析和格式化输出
        - 自动消息确认和错误处理

        🔧 实现细节：
        1. 连接到NATS JetStream
        2. 创建LSR消息处理器
        3. 订阅LSR相关主题
        4. 实时显示接收到的数据

        📊 支持的LSR数据格式：
        - 顶级持仓多空比：long_position_ratio, short_position_ratio
        - 全账户多空比：long_account_ratio, short_account_ratio
        - 多空比计算：long_short_ratio

        ⚠️ 注意事项：
        - 这是一个简化版本，主要用于测试和调试
        - 生产环境建议使用专用的LSRSubscriber模块
        """
        import nats

        try:
            # 从配置中获取NATS连接URL
            nats_url = self.config.get('nats_client', {}).get('nats_url', 'nats://localhost:4222')

            # 建立NATS连接和JetStream上下文
            nc = await nats.connect(nats_url)
            js = nc.jetstream()

            logger.info("🔍 简单LSR订阅器已连接到NATS", nats_url=nats_url)

            async def lsr_message_handler(msg):
                """
                LSR消息处理器

                处理从NATS接收到的LSR数据消息，解析JSON格式的数据
                并根据消息主题类型进行相应的格式化显示

                Args:
                    msg: NATS消息对象，包含主题、数据和元数据
                """
                try:
                    # 解析JSON格式的消息数据
                    data = json.loads(msg.data.decode())
                    subject = msg.subject

                    # 提取通用字段信息
                    exchange = data.get('exchange', 'unknown')
                    symbol = data.get('symbol', 'unknown')
                    timestamp = data.get('timestamp', 'unknown')

                    # 根据消息主题类型进行不同的数据处理和显示
                    if 'lsr-top-position' in subject or 'lsr_top_position' in subject:
                        # 处理顶级持仓多空比数据
                        long_ratio = data.get('long_position_ratio', 'N/A')
                        short_ratio = data.get('short_position_ratio', 'N/A')
                        ls_ratio = data.get('long_short_ratio', 'N/A')

                        print(f"📊 [{datetime.now().strftime('%H:%M:%S')}] LSR顶级持仓 | {exchange} {symbol}")
                        print(f"    多头: {long_ratio} | 空头: {short_ratio} | 多空比: {ls_ratio}")

                    elif 'lsr-all-account' in subject or 'lsr_all_account' in subject:
                        # 处理全账户多空比数据
                        long_ratio = data.get('long_account_ratio', 'N/A')
                        short_ratio = data.get('short_account_ratio', 'N/A')
                        ls_ratio = data.get('long_short_ratio', 'N/A')

                        print(f"👥 [{datetime.now().strftime('%H:%M:%S')}] LSR全账户 | {exchange} {symbol}")
                        print(f"    多头账户: {long_ratio} | 空头账户: {short_ratio} | 多空比: {ls_ratio}")

                    # 向NATS确认消息已成功处理
                    await msg.ack()

                except Exception as e:
                    logger.error("处理LSR消息失败", error=str(e))

            # 订阅LSR数据主题（与collector发布主题对齐）
            # 需要分别订阅两个具体主题前缀：lsr-top-position 与 lsr-all-account
            await js.subscribe(
                "lsr_top_position.>",            # 订阅顶级持仓多空比
                cb=lsr_message_handler,          # 消息处理回调函数
                durable="lsr_top_position-test", # 持久化消费者名称（区分不同前缀）
                stream="MARKET_DATA"             # 目标消息流
            )
            await js.subscribe(
                "lsr_all_account.>",            # 订阅全账户多空比
                cb=lsr_message_handler,          # 消息处理回调函数
                durable="lsr-all-account-test",  # 持久化消费者名称
                stream="MARKET_DATA"             # 目标消息流
            )

            print("🎯 LSR数据订阅已激活（lsr-top-position 与 lsr-all-account），等待数据...")
            print("=" * 60)

            # 保存NATS连接引用，用于后续清理
            self._nc = nc

        except Exception as e:
            logger.error("创建简单LSR订阅器失败", error=str(e))
            raise

    async def _run_tests(self):
        """运行测试"""
        logger.info("🧪 运行消息代理测试...")

        # 这里可以添加各种测试逻辑
        await asyncio.sleep(5)

        logger.info("✅ 测试完成")

    async def stop(self):
        """
        优雅停止统一消息代理服务

        🛑 停止流程：
        1. 停止LSR数据订阅器（包括简单订阅器和专用订阅器）
        2. 关闭NATS客户端连接
        3. 停止MessageBrokerService（包括NATS服务器）
        4. 清理资源和重置状态标志

        🔧 实现细节：
        - 按照依赖关系的逆序进行停止操作
        - 每个组件的停止都有独立的异常处理
        - 确保即使某个组件停止失败，其他组件仍能正常停止
        - 提供详细的停止状态日志

        ⚠️ 注意事项：
        - 此方法是幂等的，可以安全地多次调用
        - 所有异常都会被捕获并记录，不会向上传播
        - 停止完成后会重置is_running标志
        """
        try:
            logger.info("🛑 停止统一消息代理服务...")

            # 停止简单LSR订阅器（如果存在）
            # 这是内置订阅器使用的NATS连接
            if hasattr(self, '_nc') and self._nc:
                await self._nc.close()
                logger.info("✅ 简单LSR订阅器已停止")

            # 停止专用LSR订阅器（如果存在）
            # 这是使用LSRSubscriber模块创建的订阅器
            if self.lsr_subscriber:
                await self.lsr_subscriber.stop()
                logger.info("✅ 专用LSR订阅器已停止")

            # 停止核心消息代理服务
            # 这会关闭NATS服务器和所有相关资源
            if self.message_broker:
                await self.message_broker.on_shutdown()
                logger.info("✅ 消息代理服务已停止")

            # 重置运行状态标志
            self.is_running = False
            logger.info("✅ 统一消息代理服务已完全停止")

        except Exception as e:
            logger.error("❌ 停止统一消息代理服务时出错", error=str(e))


def parse_arguments():
    """
    解析命令行参数

    🎯 功能说明：
    - 定义和解析Message Broker的命令行参数
    - 提供灵活的启动选项配置
    - 支持不同的运行模式和日志级别

    📋 支持的参数：
    - --mode/-m: 运行模式选择
    - --config/-c: 自定义配置文件路径
    - --log-level/-l: 日志输出级别

    Returns:
        argparse.Namespace: 解析后的命令行参数对象

    📝 使用示例：
        python unified_message_broker_main.py --mode broker --log-level INFO
        python unified_message_broker_main.py -m subscriber -c custom_config.yaml
        python unified_message_broker_main.py --mode test --log-level DEBUG
    """
    parser = argparse.ArgumentParser(
        description='MarketPrism统一消息代理服务',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
运行模式说明：
  broker     - 消息代理模式（推荐生产环境）
               连接外部 NATS（Docker/集群），管理 JetStream 与可选 LSR 订阅器

  subscriber - 仅订阅模式（用于数据消费）
               仅启动LSR数据订阅功能，不启动NATS服务器

  test       - 测试模式（开发调试用）
               启动完整代理服务并运行内置测试

使用示例：
  python unified_message_broker_main.py --mode broker
  python unified_message_broker_main.py -m subscriber -l DEBUG
  python unified_message_broker_main.py --mode test --config custom.yaml
        """
    )

    parser.add_argument(
        '--mode', '-m',
        choices=['broker', 'subscriber', 'test'],
        default='broker',
        help='运行模式：broker（消息代理）、subscriber（订阅器）、test（测试）'
    )

    parser.add_argument(
        '--config', '-c',
        type=str,
        help='配置文件路径（默认：config/message-broker/unified_message_broker.yaml）'
    )

    parser.add_argument(
        '--log-level', '-l',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='日志级别（默认：INFO）'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='仅解析配置并打印最终 NATS URL 后退出（不连接 NATS）'
    )

    return parser.parse_args()


async def main():
    """
    主函数 - 程序入口点

    🚀 执行流程：
    1. 解析命令行参数
    2. 显示启动信息和配置
    3. 创建UnifiedMessageBroker实例
    4. 设置信号处理（优雅停止）
    5. 启动服务并保持运行
    6. 处理异常和清理资源

    🔧 信号处理：
    - SIGINT (Ctrl+C): 优雅停止服务
    - SIGTERM: 系统终止信号处理

    Returns:
        int: 程序退出码
             0 - 正常退出
             1 - 启动失败或异常退出

    ⚠️ 注意事项：
    - 使用异步事件循环运行
    - 所有异常都会被捕获并记录
    - 确保资源在任何情况下都能被正确清理
    """
    # 解析和验证命令行参数
    args = parse_arguments()
    #  Dry Run:  NATS URL 
    if getattr(args, 'dry_run', False):
        cfg_path = args.config or "services/message-broker/config/unified_message_broker.yaml"
        try:
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f) or {}
            nats_client_cfg = dict(cfg.get('nats_client', {}))
            env_nats_url = os.getenv('MARKETPRISM_NATS_URL')
            final_url = env_nats_url or nats_client_cfg.get('nats_url', 'nats://localhost:4222')
            print(f"DryRun OK - Resolved NATS URL: {final_url}")
            return 0
        except Exception as e:
            print(f"DryRun Failed - error: {e}")
            return 1


    # 显示服务启动信息和配置摘要
    print("\n" + "="*80)
    print("🚀 MarketPrism统一消息代理服务")
    print("="*80)
    print(f"📋 运行模式: {args.mode}")
    print(f"📊 日志级别: {args.log_level}")
    print(f"📁 配置文件: {args.config or '默认配置'}")
    print(f"🕒 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80 + "\n")

    # 创建统一消息代理服务实例
    broker = UnifiedMessageBroker(config_path=args.config, mode=args.mode)

    # 设置系统信号处理器，支持优雅停止
    def signal_handler(signum, frame):
        """
        信号处理器 - 处理系统停止信号

        Args:
            signum: 信号编号
            frame: 当前执行帧
        """
        print(f"\n📡 收到停止信号 {signum}，正在优雅停止...")
        # 创建异步任务来停止服务，避免阻塞信号处理器
        asyncio.create_task(broker.stop())

    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # 系统终止信号

    try:
        # 启动消息代理服务
        success = await broker.start()
        if not success:
            logger.error("服务启动失败")
            return 1

        # 主事件循环 - 保持服务运行
        # 使用短暂的睡眠避免CPU占用过高
        while broker.is_running:
            await asyncio.sleep(1)

        logger.info("服务正常退出")
        return 0

    except KeyboardInterrupt:
        # 处理键盘中断（Ctrl+C）
        print("\n📡 收到中断信号，正在停止...")
        await broker.stop()
        return 0
    except Exception as e:
        # 处理所有其他异常
        logger.error("❌ 系统异常", error=str(e))
        await broker.stop()
        return 1


if __name__ == "__main__":
    """
    程序执行入口

    🚀 启动方式：
    - 直接执行：python unified_message_broker_main.py
    - 指定模式：python unified_message_broker_main.py --mode subscriber
    - 调试模式：python unified_message_broker_main.py --log-level DEBUG

    📋 退出码说明：
    - 0: 正常退出
    - 1: 启动失败或运行异常

    ⚠️ 运行要求：
    - Python 3.8+
    - 已安装所需依赖包（nats-py, structlog, pyyaml等）
    - 外部 NATS（Docker/集群）已就绪
    - 正确的配置文件（如果使用自定义配置）
    """
    exit(asyncio.run(main()))
