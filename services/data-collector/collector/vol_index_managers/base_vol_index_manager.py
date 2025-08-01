"""
波动率指数管理器基类

提供波动率指数数据收集的通用功能：
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

from ..data_types import DataType, ProductType
from ..normalizer import DataNormalizer


class BaseVolIndexManager(ABC):
    """波动率指数管理器基类"""
    
    def __init__(self, exchange: str, symbols: List[str], nats_publisher=None, config: dict = None):
        """
        初始化波动率指数管理器

        Args:
            exchange: 交易所名称 (deribit_derivatives)
            symbols: 交易对列表 (如: ['BTC', 'ETH'])
            nats_publisher: NATS发布器实例
            config: 配置字典
        """
        self.exchange = exchange
        self.symbols = symbols
        self.nats_publisher = nats_publisher
        self.data_type = "vol_index"
        
        # 设置日志
        self.logger = structlog.get_logger(
            f"vol_index_manager.{exchange}",
            exchange=exchange,
            data_type=self.data_type
        )
        
        # HTTP会话配置
        self.session = None
        self.request_timeout = 30.0
        self.max_retries = 3
        self.retry_delay = 1.0
        
        # 数据标准化器
        self.normalizer = DataNormalizer()
        
        # 运行状态
        self.is_running = False
        self.collection_task = None
        
        # 收集间隔配置 (从配置文件读取，默认5分钟)
        self.collection_interval_minutes = 5

        # 从传递的配置字典中查找vol_index配置
        vol_config_found = False
        vol_config = None

        if config:
            # 直接查找vol_index键
            if 'vol_index' in config and config['vol_index'] is not None:
                vol_config = config['vol_index']
                vol_config_found = True


        if vol_config_found and vol_config:
            self.collection_interval_minutes = vol_config.get('collection_interval_minutes', 5)
            self.request_timeout = vol_config.get('timeout', 30.0)
            self.max_retries = vol_config.get('max_retries', 3)
            self.retry_delay = vol_config.get('retry_delay', 1.0)
            self.logger.info("从配置文件读取vol_index配置成功",
                           collection_interval_minutes=self.collection_interval_minutes,
                           timeout=self.request_timeout,
                           max_retries=self.max_retries)
        else:
            self.logger.warning("未找到有效的vol_index配置，使用默认值",
                              config_available=config is not None)
        
        self.logger.info("波动率指数管理器初始化完成",
                        symbols=symbols,
                        collection_interval_minutes=self.collection_interval_minutes)
    
    async def start(self):
        """启动波动率指数数据收集"""
        if self.is_running:
            self.logger.warning("波动率指数管理器已在运行")
            return True  # 已在运行，返回True
            
        self.logger.info("启动波动率指数数据收集")
        
        try:
            # 创建HTTP会话
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            self.session = aiohttp.ClientSession(timeout=timeout)
            
            # 启动收集任务
            self.is_running = True
            self.collection_task = asyncio.create_task(self._collection_loop())
            
            self.logger.info("波动率指数数据收集已启动")
            return True  # 启动成功，返回True
            
        except Exception as e:
            self.logger.error("启动波动率指数数据收集失败", error=str(e))
            self.is_running = False
            if self.session:
                await self._close_http_session()
            return False  # 启动失败，返回False
    
    async def stop(self):
        """停止波动率指数数据收集"""
        if not self.is_running:
            return
            
        self.logger.info("停止波动率指数数据收集")
        
        self.is_running = False
        
        # 取消收集任务
        if self.collection_task and not self.collection_task.done():
            self.collection_task.cancel()
            try:
                await self.collection_task
            except asyncio.CancelledError:
                pass
        
        # 关闭HTTP会话
        await self._close_http_session()
        
        self.logger.info("波动率指数数据收集已停止")
    
    async def _close_http_session(self):
        """关闭HTTP会话"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
            self.logger.debug("HTTP会话已关闭")
    
    async def _collection_loop(self):
        """数据收集循环"""
        self.logger.info("开始收集波动率指数数据", 
                        symbols=self.symbols)
        
        while self.is_running:
            try:
                # 收集所有交易对的数据
                for symbol in self.symbols:
                    if not self.is_running:
                        break
                    
                    await self._collect_symbol_data(symbol)
                
                self.logger.info("波动率指数数据收集完成")
                
                # 等待下次收集
                if self.is_running:
                    await asyncio.sleep(self.collection_interval_minutes * 60)
                    
            except asyncio.CancelledError:
                self.logger.info("波动率指数数据收集任务被取消")
                break
            except Exception as e:
                self.logger.error("波动率指数数据收集循环异常", error=str(e))
                if self.is_running:
                    await asyncio.sleep(30)  # 异常后等待30秒再重试
    
    async def _collect_symbol_data(self, symbol: str):
        """收集单个交易对的波动率指数数据"""
        self.logger.debug("🔍 开始收集波动率指数数据", symbol=symbol)
        
        try:
            # 获取原始数据
            raw_data = await self._fetch_vol_index_data(symbol)
            if not raw_data:
                self.logger.warning("未获取到波动率指数数据", symbol=symbol)
                return
            
            # 标准化数据
            normalized_data = await self._normalize_data(symbol, raw_data)
            if not normalized_data:
                self.logger.warning("波动率指数数据标准化失败", symbol=symbol)
                return
            
            self.logger.debug("🔍 波动率指数数据标准化完成", symbol=symbol)
            
            # 发布到NATS
            if self.nats_publisher:
                await self._publish_to_nats(symbol, normalized_data)
            
            self.logger.info("波动率指数数据处理完成", 
                           symbol=symbol,
                           vol_index=normalized_data.get('vol_index'))
            
        except Exception as e:
            self.logger.error("收集波动率指数数据失败", 
                            symbol=symbol, error=str(e))
    
    @abstractmethod
    async def _fetch_vol_index_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        获取波动率指数数据 (子类实现)
        
        Args:
            symbol: 交易对符号
            
        Returns:
            原始波动率指数数据字典，失败返回None
        """
        pass
    
    @abstractmethod
    async def _normalize_data(self, symbol: str, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        标准化波动率指数数据 (子类实现)
        
        Args:
            symbol: 交易对符号
            raw_data: 原始数据
            
        Returns:
            标准化后的数据字典，失败返回None
        """
        pass
    
    async def _publish_to_nats(self, symbol: str, data: Dict[str, Any]):
        """发布数据到NATS"""
        try:
            self.logger.debug("🔍 波动率指数数据开始发布到NATS", symbol=symbol)
            
            # 获取标准化的交易对符号
            normalized_symbol = data.get('symbol', symbol)
            
            # 发布到NATS
            success = await self.nats_publisher.publish_data(
                data_type=DataType.VOLATILITY_INDEX,
                exchange=self.exchange,
                market_type="perpetual",  # 波动率指数通常用于衍生品
                symbol=normalized_symbol,
                data=data
            )
            
            if success:
                self.logger.debug("🔍 波动率指数数据NATS发布成功", symbol=normalized_symbol)
            else:
                self.logger.error("波动率指数数据NATS发布失败", symbol=normalized_symbol)
                
        except Exception as e:
            self.logger.error("发布波动率指数数据到NATS失败", 
                            symbol=symbol, error=str(e))
    
    async def _make_http_request(self, url: str, params: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """发送HTTP请求"""
        for attempt in range(1, self.max_retries + 1):
            try:
                self.logger.debug("发送HTTP请求", 
                                attempt=attempt, 
                                url=url, 
                                params=params)
                
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.logger.debug("HTTP请求成功", status=response.status)
                        return data
                    else:
                        self.logger.warning("HTTP请求失败", 
                                          status=response.status,
                                          attempt=attempt)
                        
            except Exception as e:
                self.logger.error("HTTP请求异常", 
                                attempt=attempt, 
                                error=str(e))
            
            # 重试前等待
            if attempt < self.max_retries:
                await asyncio.sleep(self.retry_delay * attempt)
        
        return None
