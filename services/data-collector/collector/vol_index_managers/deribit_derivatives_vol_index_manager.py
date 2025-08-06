"""
Deribit衍生品波动率指数管理器

实现Deribit交易所的波动率指数数据收集：
- 使用HTTP API获取波动率指数数据
- 支持BTC、ETH等主要加密货币
- 数据标准化和NATS发布
- 错误处理和重试机制
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Dict, Any, Optional
import structlog

from .base_vol_index_manager import BaseVolIndexManager
from collector.normalizer import DataNormalizer


class DeribitDerivativesVolIndexManager(BaseVolIndexManager):
    """Deribit衍生品波动率指数管理器"""
    
    def __init__(self, symbols: List[str], nats_publisher=None, config: dict = None):
        """
        初始化Deribit衍生品波动率指数管理器

        Args:
            symbols: 交易对列表 (如: ['BTC', 'ETH'])
            nats_publisher: NATS发布器实例
            config: 配置字典
        """
        super().__init__(
            exchange="deribit_derivatives",
            symbols=symbols,
            nats_publisher=nats_publisher,
            config=config
        )
        
        # Deribit API配置
        self.api_base_url = "https://www.deribit.com"
        self.vol_index_endpoint = "/api/v2/public/get_volatility_index_data"

        # 添加统一的数据标准化器
        self.normalizer = DataNormalizer()

        self.logger.info("Deribit衍生品波动率指数管理器初始化完成",
                        api_base_url=self.api_base_url,
                        endpoint=self.vol_index_endpoint)
    
    async def _fetch_vol_index_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        获取Deribit波动率指数数据
        
        Args:
            symbol: 交易对符号 (如: 'BTC', 'ETH')
            
        Returns:
            原始波动率指数数据字典，失败返回None
        """
        try:
            # 构建API请求URL
            url = f"{self.api_base_url}{self.vol_index_endpoint}"
            
            # 构建请求参数
            params = {
                'currency': symbol.upper(),  # BTC, ETH
                'start_timestamp': int((datetime.now(timezone.utc).timestamp() - 3600) * 1000),  # 1小时前
                'end_timestamp': int(datetime.now(timezone.utc).timestamp() * 1000),  # 现在
                'resolution': '60'  # 1分钟分辨率
            }
            
            self.logger.debug("🔍 请求Deribit波动率指数数据", 
                            symbol=symbol, 
                            url=url, 
                            params=params)
            
            # 发送HTTP请求
            response_data = await self._make_http_request(url, params)
            if not response_data:
                self.logger.warning("Deribit API请求失败", symbol=symbol)
                return None
            
            # 检查响应格式
            if 'result' not in response_data:
                self.logger.warning("Deribit API响应格式异常", 
                                  symbol=symbol, 
                                  response=response_data)
                return None
            
            result = response_data['result']
            
            # 检查是否有数据
            if not result or 'data' not in result or not result['data']:
                self.logger.warning("Deribit波动率指数数据为空", symbol=symbol)
                return None

            # 获取最新的波动率指数数据
            data_points = result['data']
            if not data_points:
                self.logger.warning("Deribit波动率指数数据点为空", symbol=symbol)
                return None

            # 取最后一个数据点 (最新数据)
            # Deribit API返回格式: [timestamp, open, high, low, close]
            latest_data_point = data_points[-1]

            if not isinstance(latest_data_point, list) or len(latest_data_point) < 5:
                self.logger.warning("Deribit波动率指数数据点格式异常",
                                  symbol=symbol,
                                  data_point=latest_data_point)
                return None

            # 解析数据点: [timestamp, open, high, low, close]
            timestamp = latest_data_point[0]  # 毫秒时间戳
            volatility_open = latest_data_point[1]
            volatility_high = latest_data_point[2]
            volatility_low = latest_data_point[3]
            volatility_close = latest_data_point[4]  # 使用收盘价作为当前波动率指数

            self.logger.debug("🔍 Deribit波动率指数数据获取成功",
                            symbol=symbol,
                            data_points_count=len(data_points),
                            latest_timestamp=timestamp,
                            volatility_index=volatility_close)

            return {
                'currency': symbol.upper(),
                'timestamp': timestamp,
                'volatility_index': volatility_close,
                'volatility_open': volatility_open,
                'volatility_high': volatility_high,
                'volatility_low': volatility_low,
                'raw_data': latest_data_point
            }
            
        except Exception as e:
            self.logger.error("获取Deribit波动率指数数据异常", 
                            symbol=symbol, error=str(e))
            return None
    
    async def _normalize_data(self, symbol: str, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        使用统一的标准化方法处理Deribit波动率指数数据

        Args:
            symbol: 交易对符号
            raw_data: 原始数据

        Returns:
            标准化后的数据字典，失败返回None
        """
        try:
            # 使用DataNormalizer的统一标准化方法
            normalized_obj = self.normalizer.normalize_deribit_volatility_index(raw_data)

            if not normalized_obj:
                self.logger.warning("波动率指数数据标准化失败", symbol=symbol)
                return None

            # 转换为字典格式以保持兼容性 - 修复版：使用ClickHouse兼容时间戳
            normalized_data = {
                'exchange': normalized_obj.exchange_name,
                'symbol': normalized_obj.symbol_name,  # 使用完整的交易对符号
                'currency': normalized_obj.currency,
                'vol_index': normalized_obj.volatility_value,  # 保持Decimal类型
                'volatility_index': normalized_obj.volatility_value,  # 保持Decimal类型
                'timestamp': normalized_obj.timestamp.strftime('%Y-%m-%d %H:%M:%S'),  # ClickHouse格式
                'market_type': normalized_obj.market_type,  # 使用正确的market_type (options)
                'data_source': 'marketprism'
            }

            self.logger.debug("🔍 Deribit波动率指数数据标准化完成",
                            symbol=symbol,
                            normalized_symbol=normalized_obj.symbol_name,
                            vol_index=str(normalized_obj.volatility_value),
                            market_type=normalized_obj.market_type,
                            timestamp=normalized_obj.timestamp.isoformat())

            return normalized_data

        except Exception as e:
            self.logger.error("波动率指数数据标准化异常",
                            symbol=symbol, error=str(e))
            return None


    
    async def _make_http_request(self, url: str, params: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """
        发送HTTP请求到Deribit API
        
        重写基类方法以添加Deribit特定的错误处理
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                self.logger.debug("发送Deribit API请求", 
                                attempt=attempt, 
                                url=url, 
                                params=params)
                
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # 检查Deribit API错误
                        if 'error' in data:
                            error_info = data['error']
                            self.logger.warning("Deribit API返回错误", 
                                              error_code=error_info.get('code'),
                                              error_message=error_info.get('message'),
                                              attempt=attempt)
                            
                            # 某些错误不需要重试
                            if error_info.get('code') in [10009, 10010]:  # 无效参数等
                                return None
                        else:
                            self.logger.debug("Deribit API请求成功", status=response.status)
                            return data
                    
                    elif response.status == 429:  # 限流
                        self.logger.warning("Deribit API限流", 
                                          status=response.status,
                                          attempt=attempt)
                        # 限流时等待更长时间
                        if attempt < self.max_retries:
                            await asyncio.sleep(self.retry_delay * attempt * 2)
                        continue
                    
                    else:
                        self.logger.warning("Deribit API请求失败", 
                                          status=response.status,
                                          attempt=attempt)
                        
            except Exception as e:
                self.logger.error("Deribit API请求异常", 
                                attempt=attempt, 
                                error=str(e))
            
            # 重试前等待
            if attempt < self.max_retries:
                await asyncio.sleep(self.retry_delay * attempt)
        
        return None
