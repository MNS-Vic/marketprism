"""
未平仓量管理器基类

提供永续合约未平仓量数据收集的通用功能：
- 统一的数据获取接口
- 标准化数据处理
- NATS发布功能
- 错误处理和重试机制
"""

import asyncio
import aiohttp
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Dict, Any, Optional
import structlog

from ..data_types import NormalizedOpenInterest, ProductType, DataType
from ..normalizer import DataNormalizer


class BaseOpenInterestManager(ABC):
    """未平仓量管理器基类"""
    
    def __init__(self, exchange: str, symbols: List[str], nats_publisher=None):
        """
        初始化未平仓量管理器
        
        Args:
            exchange: 交易所名称 (binance_derivatives, okx_derivatives)
            symbols: 交易对列表 (如: ['BTC-USDT', 'ETH-USDT'])
            nats_publisher: NATS发布器实例
        """
        self.exchange = exchange
        self.symbols = symbols
        self.nats_publisher = nats_publisher
        self.data_type = DataType.OPEN_INTEREST
        
        # 设置日志
        self.logger = structlog.get_logger(
            f"open_interest_manager.{exchange}",
            exchange=exchange,
            data_type=self.data_type
        )
        
        # HTTP会话配置
        self.session = None
        self.request_timeout = 30.0
        self.max_retries = 3
        self.retry_delay = 1.0
        
        # 收集配置 - 5分钟间隔
        self.collection_interval = 5 * 60  # 5分钟 = 300秒
        
        # 运行状态
        self.is_running = False
        self.collection_task = None
        
        self.logger.info("未平仓量管理器初始化完成",
                        symbols=symbols,
                        collection_interval_minutes=5)
    
    async def start(self):
        """启动未平仓量数据收集"""
        if self.is_running:
            self.logger.warning("未平仓量管理器已在运行")
            return True  # 已在运行，返回True

        self.logger.info("启动未平仓量数据收集")

        try:
            # 创建HTTP会话
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            self.session = aiohttp.ClientSession(timeout=timeout)

            # 启动收集任务
            self.is_running = True
            self.collection_task = asyncio.create_task(self._collection_loop())

            self.logger.info("未平仓量数据收集已启动")
            return True  # 启动成功，返回True

        except Exception as e:
            self.logger.error("启动未平仓量数据收集失败", error=str(e))
            self.is_running = False
            if self.session:
                await self._close_http_session()
            return False  # 启动失败，返回False
    
    async def stop(self):
        """停止未平仓量数据收集"""
        if not self.is_running:
            return

        self.logger.info("停止未平仓量数据收集")

        # 停止收集任务
        self.is_running = False
        if self.collection_task:
            self.collection_task.cancel()
            try:
                await self.collection_task
            except asyncio.CancelledError:
                pass

        # 关闭HTTP会话
        await self._close_http_session()

        self.logger.info("未平仓量数据收集已停止")

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
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.stop()
    
    async def _collection_loop(self):
        """数据收集循环"""
        # 立即执行一次收集
        await self._collect_all_symbols()
        
        # 然后按间隔执行
        while self.is_running:
            try:
                await asyncio.sleep(self.collection_interval)
                if self.is_running:
                    await self._collect_all_symbols()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("收集循环异常", error=str(e))
                await asyncio.sleep(60)  # 出错后等待1分钟再重试
    
    async def _collect_all_symbols(self):
        """收集所有交易对的未平仓量数据"""
        self.logger.info("开始收集未平仓量数据", symbols=self.symbols)
        
        for symbol in self.symbols:
            try:
                await self._collect_symbol_data(symbol)
            except Exception as e:
                self.logger.error("收集交易对数据失败",
                                symbol=symbol,
                                error=str(e))
        
        self.logger.info("未平仓量数据收集完成")
    
    async def _collect_symbol_data(self, symbol: str):
        """收集单个交易对的未平仓量数据"""
        try:
            # 🔍 调试：开始收集数据
            self.logger.debug("🔍 开始收集未平仓量数据",
                            symbol=symbol,
                            exchange=self.exchange)
            
            # 获取原始数据
            raw_data = await self._fetch_open_interest_data(symbol)
            if not raw_data:
                self.logger.warning("未获取到未平仓量数据", symbol=symbol)
                return
            
            # 标准化数据
            normalized_data = self._normalize_open_interest_data(raw_data, symbol)
            if not normalized_data:
                self.logger.warning("未平仓量数据标准化失败", symbol=symbol)
                return
            
            # 🔍 调试：数据标准化完成
            self.logger.debug("🔍 未平仓量数据标准化完成",
                            symbol=symbol,
                            open_interest_value=str(normalized_data.open_interest_value),
                            open_interest_usd=str(normalized_data.open_interest_usd) if normalized_data.open_interest_usd else None)
            
            # 发布到NATS
            await self._publish_to_nats(normalized_data)
            
            self.logger.info("未平仓量数据处理完成",
                           symbol=symbol,
                           open_interest_value=str(normalized_data.open_interest_value),
                           open_interest_usd=str(normalized_data.open_interest_usd) if normalized_data.open_interest_usd else None)
            
        except Exception as e:
            self.logger.error("收集未平仓量数据异常",
                            symbol=symbol,
                            error=str(e))
            raise

    @abstractmethod
    async def _fetch_open_interest_data(self, symbol: str) -> Dict[str, Any]:
        """
        获取未平仓量数据 - 子类实现

        Args:
            symbol: 交易对名称

        Returns:
            原始未平仓量数据
        """
        pass

    @abstractmethod
    def _normalize_open_interest_data(self, raw_data: Dict[str, Any], symbol: str) -> Optional[NormalizedOpenInterest]:
        """
        标准化未平仓量数据 - 子类实现

        Args:
            raw_data: 原始数据
            symbol: 交易对名称

        Returns:
            标准化的未平仓量数据
        """
        pass

    async def _publish_to_nats(self, normalized_data: NormalizedOpenInterest):
        """发布未平仓量数据到NATS"""
        try:
            # 🔧 修复：使用INFO级别日志确保能看到发布过程
            self.logger.info("🚀 开始发布未平仓量数据到NATS",
                            exchange=normalized_data.exchange_name,
                            symbol=normalized_data.symbol_name,
                            data_type=self.data_type,
                            open_interest_usd=str(normalized_data.open_interest_usd) if normalized_data.open_interest_usd else None)

            # 检查NATS发布器
            if not self.nats_publisher:
                self.logger.error("❌ NATS发布器未配置，无法发布数据",
                                symbol=normalized_data.symbol_name,
                                exchange=normalized_data.exchange_name)
                return False

            # 构建发布数据
            data_dict = {
                'exchange': normalized_data.exchange_name,
                'symbol': normalized_data.symbol_name,
                'product_type': normalized_data.product_type,
                'instrument_id': normalized_data.instrument_id,
                'open_interest_value': str(normalized_data.open_interest_value),
                'open_interest_usd': str(normalized_data.open_interest_usd) if normalized_data.open_interest_usd else None,
                'open_interest_unit': normalized_data.open_interest_unit,
                'mark_price': str(normalized_data.mark_price) if normalized_data.mark_price else None,
                'index_price': str(normalized_data.index_price) if normalized_data.index_price else None,
                'change_24h': str(normalized_data.change_24h) if normalized_data.change_24h else None,
                'change_24h_percent': str(normalized_data.change_24h_percent) if normalized_data.change_24h_percent else None,
                'timestamp': normalized_data.timestamp.isoformat(),
                'collected_at': normalized_data.collected_at.isoformat(),
                'data_type': self.data_type
            }

            # 🔧 修复：记录即将发布的详细信息
            self.logger.info("📡 准备发布到NATS",
                            data_type=self.data_type,
                            exchange=normalized_data.exchange_name,
                            market_type=normalized_data.product_type,
                            symbol=normalized_data.symbol_name,
                            data_size=len(str(data_dict)))

            # 发布到NATS
            success = await self.nats_publisher.publish_data(
                data_type=self.data_type,
                exchange=normalized_data.exchange_name,
                market_type=normalized_data.product_type,
                symbol=normalized_data.symbol_name,
                data=data_dict
            )

            # 🔧 修复：明确记录发布结果
            if success:
                self.logger.info("✅ 未平仓量数据NATS发布成功",
                                symbol=normalized_data.symbol_name,
                                exchange=normalized_data.exchange_name,
                                data_type=self.data_type,
                                open_interest_usd=str(normalized_data.open_interest_usd) if normalized_data.open_interest_usd else None)
                return True
            else:
                self.logger.error("❌ 未平仓量数据NATS发布失败",
                                symbol=normalized_data.symbol_name,
                                exchange=normalized_data.exchange_name,
                                data_type=self.data_type)
                return False

        except Exception as e:
            self.logger.error("❌ NATS发布异常",
                            symbol=normalized_data.symbol_name,
                            exchange=normalized_data.exchange_name,
                            error=str(e),
                            exc_info=True)
            return False

    async def _make_http_request(self, url: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        发送HTTP请求，带重试机制

        Args:
            url: 请求URL
            params: 请求参数

        Returns:
            响应数据
        """
        # 确保HTTP会话已创建
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            self.session = aiohttp.ClientSession(timeout=timeout)

        for attempt in range(self.max_retries):
            try:
                self.logger.debug("发送HTTP请求",
                                url=url,
                                params=params,
                                attempt=attempt + 1)

                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.logger.debug("HTTP请求成功", status=response.status)
                        return data
                    else:
                        self.logger.warning("HTTP请求失败",
                                          status=response.status,
                                          url=url)

            except Exception as e:
                self.logger.warning("HTTP请求异常",
                                  error=str(e),
                                  attempt=attempt + 1,
                                  max_retries=self.max_retries)

                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                else:
                    raise

        raise Exception(f"HTTP请求失败，已重试{self.max_retries}次")
