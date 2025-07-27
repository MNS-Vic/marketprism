"""
Binance衍生品资金费率管理器

实现Binance永续合约资金费率数据收集：
- 使用Binance衍生品API获取资金费率数据
- 支持标记价格和资金费率信息
- 数据标准化和NATS发布
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional, List
import structlog

from .base_funding_rate_manager import BaseFundingRateManager
from ..data_types import NormalizedFundingRate, ProductType
from ..normalizer import DataNormalizer


class BinanceDerivativesFundingRateManager(BaseFundingRateManager):
    """Binance衍生品资金费率管理器"""
    
    def __init__(self, symbols: List[str], nats_publisher=None):
        """
        初始化Binance衍生品资金费率管理器
        
        Args:
            symbols: 交易对列表 (如: ['BTC-USDT', 'ETH-USDT'])
            nats_publisher: NATS发布器实例
        """
        super().__init__("binance_derivatives", symbols, nats_publisher)
        
        # Binance衍生品API配置
        self.api_base_url = "https://fapi.binance.com"
        self.funding_rate_endpoint = "/fapi/v1/premiumIndex"
        
        self.logger.info("Binance衍生品资金费率管理器初始化完成",
                        api_base_url=self.api_base_url)
    
    async def _fetch_funding_rate_data(self, symbol: str) -> Dict[str, Any]:
        """
        获取Binance资金费率数据
        
        Args:
            symbol: 交易对名称 (如: BTC-USDT)
            
        Returns:
            原始资金费率数据
        """
        try:
            # 转换为Binance格式的交易对
            binance_symbol = symbol.replace('-', '')  # BTC-USDT -> BTCUSDT
            
            # 构建API请求
            url = f"{self.api_base_url}{self.funding_rate_endpoint}"
            params = {
                'symbol': binance_symbol
            }
            
            self.logger.debug("获取Binance资金费率数据",
                            symbol=symbol,
                            binance_symbol=binance_symbol,
                            url=url)
            
            # 发送请求
            response_data = await self._make_http_request(url, params)
            
            self.logger.debug("Binance资金费率API响应",
                            symbol=symbol,
                            response_keys=list(response_data.keys()) if response_data else None)
            
            return response_data
            
        except Exception as e:
            self.logger.error("获取Binance资金费率数据失败",
                            symbol=symbol,
                            error=str(e))
            raise
    
    def _normalize_funding_rate_data(self, raw_data: Dict[str, Any], symbol: str) -> Optional[NormalizedFundingRate]:
        """
        标准化Binance资金费率数据
        
        Args:
            raw_data: Binance API原始数据
            symbol: 交易对名称
            
        Returns:
            标准化的资金费率数据
        """
        try:
            if not raw_data:
                return None
            
            # 解析Binance资金费率数据
            # Binance API返回格式：
            # {
            #   "symbol": "BTCUSDT",
            #   "markPrice": "43000.00000000",
            #   "indexPrice": "42995.12345678", 
            #   "estimatedSettlePrice": "42995.12345678",
            #   "lastFundingRate": "0.00010000",
            #   "nextFundingTime": 1640995200000,
            #   "interestRate": "0.00010000",
            #   "time": 1640995190000
            # }
            
            # 标准化交易对名称
            normalizer = DataNormalizer()
            normalized_symbol = normalizer.normalize_symbol_format(raw_data.get('symbol', ''), 'binance_derivatives')
            
            # 解析时间戳
            current_time = datetime.now(timezone.utc)
            next_funding_time = datetime.fromtimestamp(
                int(raw_data.get('nextFundingTime', 0)) / 1000, 
                tz=timezone.utc
            )
            data_timestamp = datetime.fromtimestamp(
                int(raw_data.get('time', 0)) / 1000,
                tz=timezone.utc
            ) if raw_data.get('time') else current_time
            
            # 解析价格和费率数据
            current_funding_rate = Decimal(str(raw_data.get('lastFundingRate', '0')))
            mark_price = Decimal(str(raw_data.get('markPrice', '0'))) if raw_data.get('markPrice') else None
            index_price = Decimal(str(raw_data.get('indexPrice', '0'))) if raw_data.get('indexPrice') else None
            
            # 计算溢价指数
            premium_index = None
            if mark_price and index_price:
                premium_index = mark_price - index_price
            
            # 构建标准化数据
            normalized_data = NormalizedFundingRate(
                exchange_name="binance_derivatives",
                symbol_name=normalized_symbol,
                product_type="perpetual",
                instrument_id=raw_data.get('symbol', ''),
                current_funding_rate=current_funding_rate,
                estimated_funding_rate=None,  # Binance不提供预估费率
                next_funding_time=next_funding_time,
                funding_interval="8h",
                mark_price=mark_price,
                index_price=index_price,
                premium_index=premium_index,
                timestamp=data_timestamp,
                raw_data=raw_data
            )
            
            self.logger.debug("Binance资金费率数据标准化完成",
                            symbol=symbol,
                            normalized_symbol=normalized_symbol,
                            current_funding_rate=str(current_funding_rate),
                            mark_price=str(mark_price) if mark_price else None,
                            next_funding_time=next_funding_time.isoformat())
            
            return normalized_data
            
        except Exception as e:
            self.logger.error("Binance资金费率数据标准化失败",
                            symbol=symbol,
                            error=str(e),
                            raw_data=raw_data)
            return None
