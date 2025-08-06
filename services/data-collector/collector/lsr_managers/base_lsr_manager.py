"""
多空持仓比例数据管理器基类

提供统一的架构模式和接口定义，支持按持仓量和按账户数两种计算方式
"""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union
import aiohttp

import structlog
from collector.data_types import Exchange, MarketType, NormalizedLSRTopPosition, NormalizedLSRAllAccount
from collector.normalizer import DataNormalizer


class BaseLSRManager(ABC):
    """
    多空持仓比例数据管理器基类

    架构特点：
    1. 定期REST API调用获取数据
    2. 数据标准化和NATS发布
    3. 错误处理和重试机制
    4. 统一的日志管理
    5. 支持按持仓量和按账户数两种计算方式
    """
    
    def __init__(self,
                 exchange: Exchange,
                 market_type: MarketType,
                 data_type: str,  # 'lsr_position' 或 'lsr_account'
                 symbols: List[str],
                 normalizer: DataNormalizer,
                 nats_publisher: Any,  # 使用Any类型避免导入问题
                 config: dict):
        """
        初始化多空持仓比例数据管理器

        Args:
            exchange: 交易所枚举
            market_type: 市场类型枚举
            data_type: 数据类型 ('lsr_position' 或 'lsr_account')
            symbols: 交易对列表
            normalizer: 数据标准化器
            nats_publisher: NATS发布器
            config: 配置信息
        """
        self.exchange = exchange
        self.market_type = market_type
        self.data_type = data_type  # 'lsr_position' 或 'lsr_account'
        self.symbols = symbols
        self.normalizer = normalizer
        self.nats_publisher = nats_publisher
        self.config = config

        # 日志系统
        self.logger = structlog.get_logger(
            f"lsr_{data_type}_{exchange.value.lower()}_{market_type.value.lower()}"
        )

        # 统计信息
        self.stats = {
            'requests_sent': 0,
            'requests_successful': 0,
            'requests_failed': 0,
            'data_points_received': 0,
            'data_points_processed': 0,
            'data_points_published': 0,
            'last_request_time': None,
            'last_data_time': None,
            'errors': 0
        }

        # 运行状态
        self.is_running = False
        self.fetch_task: Optional[asyncio.Task] = None

        # 配置参数
        self.fetch_interval = config.get('fetch_interval', 10)  # 默认10秒
        self.period = config.get('period', '1h')  # 默认1小时周期
        self.limit = config.get('limit', 30)  # 默认获取30个数据点
        self.max_retries = config.get('max_retries', 3)
        self.retry_delay = config.get('retry_delay', 5)

        # HTTP会话
        self.session: Optional[aiohttp.ClientSession] = None

        self.logger.info(f"🏭 {self.__class__.__name__}初始化完成",
                        exchange=exchange.value,
                        market_type=market_type.value,
                        data_type=data_type,
                        symbols=symbols,
                        fetch_interval=self.fetch_interval,
                        period=self.period)

    async def start(self) -> bool:
        """
        启动顶级交易者多空持仓比例数据管理器
        
        Returns:
            bool: 启动是否成功
        """
        try:
            self.logger.info(
                f"启动{self.data_type}数据管理器",
                exchange=self.exchange.value,
                market_type=self.market_type.value,
                data_type=self.data_type
            )
            
            if self.is_running:
                self.logger.warning("顶级交易者多空持仓比例数据管理器已在运行中")
                return True
            
            # 创建HTTP会话（增加更短的超时时间）
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10, connect=5),
                headers={'User-Agent': 'MarketPrism/1.0'}
            )
            
            self.is_running = True

            # 启动定期获取任务（延迟启动，避免启动时阻塞）
            # 使用更长的延迟，确保系统完全启动后再开始数据获取
            self.fetch_task = asyncio.create_task(self._delayed_fetch_start())
            
            self.logger.info(
                f"{self.data_type}数据管理器启动成功",
                exchange=self.exchange.value,
                market_type=self.market_type.value,
                data_type=self.data_type
            )
            return True
            
        except Exception as e:
            self.logger.error(
                "顶级交易者多空持仓比例数据管理器启动失败",
                error=e,
                exchange=self.exchange.value,
                market_type=self.market_type.value
            )
            self.stats['errors'] += 1
            return False

    async def stop(self):
        """停止顶级交易者多空持仓比例数据管理器"""
        try:
            self.logger.info(f"停止{self.data_type}数据管理器")
            
            self.is_running = False
            
            # 取消获取任务
            if self.fetch_task and not self.fetch_task.done():
                self.fetch_task.cancel()
                try:
                    await self.fetch_task
                except asyncio.CancelledError:
                    pass
            
            # 关闭HTTP会话
            await self._close_http_session()
            
            self.logger.info(f"{self.data_type}数据管理器已停止")
            
        except Exception as e:
            self.logger.error(f"停止{self.data_type}数据管理器失败", error=e)

    async def _close_http_session(self):
        """安全关闭HTTP会话"""
        if self.session and not self.session.closed:
            try:
                await self.session.close()
                self.logger.debug("HTTP会话已关闭")
            except Exception as e:
                self.logger.warning("关闭HTTP会话时出错", error=str(e))
            finally:
                self.session = None

    async def _delayed_fetch_start(self):
        """延迟启动数据获取，避免启动时阻塞"""
        try:
            # 等待10秒后开始数据获取，让系统完全启动并稳定运行
            self.logger.info(f"{self.data_type}数据管理器将在10秒后开始数据获取")
            await asyncio.sleep(10)

            if self.is_running:
                self.logger.info(f"开始{self.data_type}数据获取循环")
                await self._fetch_data_loop()
            else:
                self.logger.info(f"{self.data_type}数据管理器已停止，取消数据获取")
        except Exception as e:
            self.logger.error(f"延迟启动{self.data_type}数据获取失败", error=e)

    async def _fetch_data_loop(self):
        """定期获取数据的主循环"""
        while self.is_running:
            try:
                # 为每个交易对获取数据
                for symbol in self.symbols:
                    if not self.is_running:
                        break
                    
                    await self._fetch_symbol_data(symbol)
                    
                    # 避免请求过于频繁
                    await asyncio.sleep(1)
                
                # 等待下次获取
                await asyncio.sleep(self.fetch_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("数据获取循环异常", error=e)
                self.stats['errors'] += 1
                await asyncio.sleep(self.retry_delay)

    async def _fetch_symbol_data(self, symbol: str):
        """获取单个交易对的数据"""
        for attempt in range(self.max_retries):
            try:
                self.stats['requests_sent'] += 1
                self.stats['last_request_time'] = datetime.now(timezone.utc)
                
                # 调用具体交易所的实现
                raw_data = await self._fetch_data_from_api(symbol)
                
                if raw_data:
                    self.stats['requests_successful'] += 1
                    await self._process_raw_data(symbol, raw_data)
                    return
                else:
                    self.stats['requests_failed'] += 1
                    
            except Exception as e:
                self.logger.error(
                    f"获取{symbol}数据失败 (尝试 {attempt + 1}/{self.max_retries})",
                    error=e,
                    symbol=symbol
                )
                self.stats['requests_failed'] += 1
                
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)

    async def _process_raw_data(self, symbol: str, raw_data: Dict[str, Any]):
        """处理原始数据"""
        try:
            # 添加请求参数到原始数据中，供标准化使用
            raw_data['instId'] = symbol
            raw_data['period'] = self.period
            
            # 标准化数据
            normalized_data = await self._normalize_data(raw_data)
            
            if normalized_data:
                self.stats['data_points_processed'] += 1
                self.stats['last_data_time'] = normalized_data.timestamp
                
                # 发布到NATS
                await self._publish_to_nats(normalized_data)
                self.stats['data_points_published'] += 1
                
                # 构建日志信息
                log_data = {
                    'exchange': normalized_data.exchange_name,
                    'symbol': normalized_data.symbol_name,
                    'long_short_ratio': str(normalized_data.long_short_ratio),
                    'data_type': self.data_type
                }

                # 根据数据类型添加特定字段到日志
                if self.data_type == 'lsr_top_position':
                    log_data.update({
                        'long_position_ratio': str(normalized_data.long_position_ratio),
                        'short_position_ratio': str(normalized_data.short_position_ratio)
                    })
                elif self.data_type == 'lsr_all_account':
                    log_data.update({
                        'long_account_ratio': str(normalized_data.long_account_ratio),
                        'short_account_ratio': str(normalized_data.short_account_ratio)
                    })

                self.logger.info(f"{self.data_type}数据处理完成", **log_data)
            
        except Exception as e:
            self.logger.error("处理原始数据失败", error=e, symbol=symbol)
            self.stats['errors'] += 1

    async def _publish_to_nats(self, normalized_data):
        """发布数据到NATS - 修复版：使用统一的主题格式"""
        try:
            # 修复：使用统一的LSR主题格式以匹配存储服务订阅
            # 将 lsr_top_position -> top-position, lsr_all_account -> all-account
            lsr_subtype = self.data_type.replace('lsr_', '').replace('_', '-')
            topic = f"lsr-data.{normalized_data.exchange_name}.{normalized_data.product_type.value}.{lsr_subtype}.{normalized_data.symbol_name}"

            # 🔍 调试：LSR数据发布开始
            self.logger.debug("🔍 LSR数据开始发布到NATS",
                            data_type=self.data_type,
                            exchange=normalized_data.exchange_name,
                            symbol=normalized_data.symbol_name,
                            topic=topic)

            # 构建发布数据
            data_dict = {
                'exchange': normalized_data.exchange_name,
                'symbol': normalized_data.symbol_name,
                'product_type': normalized_data.product_type.value,
                'instrument_id': normalized_data.instrument_id,
                'timestamp': normalized_data.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'long_short_ratio': str(normalized_data.long_short_ratio),
                'period': normalized_data.period,
                'data_source': 'marketprism'
            }

            # 根据数据类型添加特定字段
            if self.data_type == 'lsr_top_position':
                data_dict.update({
                    'long_position_ratio': str(normalized_data.long_position_ratio),
                    'short_position_ratio': str(normalized_data.short_position_ratio)
                })
            elif self.data_type == 'lsr_all_account':
                data_dict.update({
                    'long_account_ratio': str(normalized_data.long_account_ratio),
                    'short_account_ratio': str(normalized_data.short_account_ratio)
                })
            
            # 🔍 调试：准备调用NATS发布器
            self.logger.debug("🔍 准备调用NATS发布器",
                            data_type=self.data_type,
                            data_dict_keys=list(data_dict.keys()))

            # 发布到NATS
            success = await self.nats_publisher.publish_data(
                data_type=self.data_type,
                exchange=normalized_data.exchange_name,
                market_type=normalized_data.product_type.value,
                symbol=normalized_data.symbol_name,
                data=data_dict
            )

            # 🔍 调试：NATS发布结果
            if success:
                self.logger.debug("🔍 LSR数据NATS发布成功",
                                symbol=normalized_data.symbol_name,
                                topic=topic,
                                data_type=self.data_type)
            else:
                self.logger.warning("🔍 LSR数据NATS发布失败",
                                  symbol=normalized_data.symbol_name,
                                  topic=topic,
                                  data_type=self.data_type)
                
        except Exception as e:
            self.logger.error("发布到NATS失败", error=e, symbol=normalized_data.symbol_name)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.stats.copy()

    @abstractmethod
    async def _fetch_data_from_api(self, symbol: str) -> Optional[Dict[str, Any]]:
        """从API获取数据 - 子类实现"""
        pass

    @abstractmethod
    async def _normalize_data(self, raw_data: Dict[str, Any]) -> Optional[Union[NormalizedLSRTopPosition, NormalizedLSRAllAccount]]:
        """标准化数据 - 子类实现"""
        pass
