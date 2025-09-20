"""
资金费率管理器基类

提供永续合约资金费率数据收集的通用功能：
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

from ..data_types import NormalizedFundingRate, ProductType
from ..normalizer import DataNormalizer


class BaseFundingRateManager(ABC):
    """资金费率管理器基类"""
    
    def __init__(self, exchange: str, symbols: List[str], nats_publisher=None):
        """
        初始化资金费率管理器
        
        Args:
            exchange: 交易所名称 (binance_derivatives, okx_derivatives)
            symbols: 交易对列表 (如: ['BTC-USDT', 'ETH-USDT'])
            nats_publisher: NATS发布器实例
        """
        self.exchange = exchange
        self.symbols = symbols
        self.nats_publisher = nats_publisher
        self.data_type = "funding_rate"
        
        # 设置日志
        self.logger = structlog.get_logger(
            f"funding_rate_manager.{exchange}",
            exchange=exchange,
            data_type=self.data_type
        )
        
        # HTTP会话配置
        self.session = None
        self.request_timeout = 30.0
        self.max_retries = 3
        self.retry_delay = 1.0
        
        # 收集配置 - 修改为1分钟一次，用于测试和实时监控
        self.collection_interval = 60  # 1分钟 = 60秒

        # 运行状态
        self.is_running = False
        self.collection_task = None

        self.logger.info("资金费率管理器初始化完成",
                        symbols=symbols,
                        collection_interval_minutes=1)
    
    async def start(self):
        """启动资金费率数据收集"""
        if self.is_running:
            self.logger.warning("资金费率管理器已在运行")
            return True  # 已在运行，返回True

        self.logger.info("启动资金费率数据收集")

        try:
            # 创建HTTP会话
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            self.session = aiohttp.ClientSession(timeout=timeout)

            # 启动收集任务
            self.is_running = True
            self.collection_task = asyncio.create_task(self._collection_loop())

            self.logger.info("资金费率数据收集已启动")
            return True  # 启动成功，返回True

        except Exception as e:
            self.logger.error("启动资金费率数据收集失败", error=str(e))
            self.is_running = False
            if self.session:
                await self._close_http_session()
            return False  # 启动失败，返回False
    
    async def stop(self):
        """停止资金费率数据收集"""
        if not self.is_running:
            return

        self.logger.info("停止资金费率数据收集")

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

        self.logger.info("资金费率数据收集已停止")

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
        """收集所有交易对的资金费率数据"""
        self.logger.info("开始收集资金费率数据", symbols=self.symbols)
        
        for symbol in self.symbols:
            try:
                await self._collect_symbol_data(symbol)
            except Exception as e:
                self.logger.error("收集交易对数据失败",
                                symbol=symbol,
                                error=str(e))
        
        self.logger.info("资金费率数据收集完成")
    
    async def _collect_symbol_data(self, symbol: str):
        """收集单个交易对的资金费率数据"""
        try:
            # 🔍 调试：开始收集数据
            self.logger.debug("🔍 开始收集资金费率数据",
                            symbol=symbol,
                            exchange=self.exchange)
            
            # 获取原始数据
            raw_data = await self._fetch_funding_rate_data(symbol)
            if not raw_data:
                self.logger.warning("未获取到资金费率数据", symbol=symbol)
                return
            
            # 标准化数据
            normalized_data = self._normalize_funding_rate_data(raw_data, symbol)
            if not normalized_data:
                self.logger.warning("资金费率数据标准化失败", symbol=symbol)
                return
            
            # 🔍 调试：数据标准化完成
            self.logger.debug("🔍 资金费率数据标准化完成",
                            symbol=symbol,
                            current_funding_rate=str(normalized_data.current_funding_rate),
                            next_funding_time=normalized_data.next_funding_time.isoformat())
            
            # 发布到NATS
            await self._publish_to_nats(normalized_data)
            
            self.logger.info("资金费率数据处理完成",
                           symbol=symbol,
                           current_funding_rate=str(normalized_data.current_funding_rate),
                           next_funding_time=normalized_data.next_funding_time.isoformat())
            
        except Exception as e:
            self.logger.error("收集资金费率数据异常",
                            symbol=symbol,
                            error=str(e))
            raise

    @abstractmethod
    async def _fetch_funding_rate_data(self, symbol: str) -> Dict[str, Any]:
        """
        获取资金费率数据 - 子类实现

        Args:
            symbol: 交易对名称

        Returns:
            原始资金费率数据
        """
        pass

    @abstractmethod
    def _normalize_funding_rate_data(self, raw_data: Dict[str, Any], symbol: str) -> Optional[NormalizedFundingRate]:
        """
        标准化资金费率数据 - 子类实现

        Args:
            raw_data: 原始数据
            symbol: 交易对名称

        Returns:
            标准化的资金费率数据
        """
        pass

    async def _publish_to_nats(self, normalized_data: NormalizedFundingRate):
        """发布资金费率数据到NATS"""
        try:
            # 🔍 调试：开始发布到NATS
            self.logger.debug("🔍 资金费率数据开始发布到NATS",
                            exchange=normalized_data.exchange_name,
                            symbol=normalized_data.symbol_name,
                            data_type=self.data_type)

            # 构建发布数据（不在Manager层做时间/数值字符串格式化，交由 normalizer/publisher 统一处理）
            data_dict = {
                'exchange': normalized_data.exchange_name,
                'market_type': normalized_data.product_type,
                'symbol': normalized_data.symbol_name,
                'instrument_id': normalized_data.instrument_id,
                'current_funding_rate': normalized_data.current_funding_rate,
                'estimated_funding_rate': normalized_data.estimated_funding_rate,
                'next_funding_time': normalized_data.next_funding_time,
                'funding_interval': normalized_data.funding_interval,
                'mark_price': normalized_data.mark_price,
                'index_price': normalized_data.index_price,
                'premium_index': normalized_data.premium_index,
                'timestamp': normalized_data.timestamp,
                'collected_at': getattr(normalized_data, 'collected_at', None),
                'data_type': self.data_type
            }

            # 🔍 调试：准备调用NATS发布器
            self.logger.debug("🔍 准备调用NATS发布器",
                            data_type=self.data_type,
                            data_dict_keys=list(data_dict.keys()))

            # 发布到NATS（使用专用方法与模板）
            if not self.nats_publisher:
                self.logger.warning("NATS发布器未配置，跳过发布")
                return

            success = await self.nats_publisher.publish_funding_rate(
                exchange=normalized_data.exchange_name,
                market_type=normalized_data.product_type,
                symbol=normalized_data.symbol_name,
                funding_data=data_dict
            )

            # 🔍 调试：NATS发布结果
            if success:
                self.logger.debug("🔍 资金费率数据NATS发布成功",
                                symbol=normalized_data.symbol_name,
                                data_type=self.data_type)
            else:
                self.logger.warning("🔍 资金费率数据NATS发布失败",
                                  symbol=normalized_data.symbol_name,
                                  data_type=self.data_type)

        except Exception as e:
            self.logger.error("NATS发布异常",
                            symbol=normalized_data.symbol_name,
                            error=str(e))

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
