"""
Binance衍生品未平仓量管理器

实现Binance永续合约未平仓量数据收集：
- 使用Binance衍生品API获取未平仓量统计数据
- 支持USD价值计算和24小时变化统计
- 数据标准化和NATS发布
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional, List
import structlog

from .base_open_interest_manager import BaseOpenInterestManager
from ..data_types import NormalizedOpenInterest, ProductType
from ..normalizer import DataNormalizer


class BinanceDerivativesOpenInterestManager(BaseOpenInterestManager):
    """Binance衍生品未平仓量管理器"""
    
    def __init__(self, symbols: List[str], nats_publisher=None):
        """
        初始化Binance衍生品未平仓量管理器
        
        Args:
            symbols: 交易对列表 (如: ['BTC-USDT', 'ETH-USDT'])
            nats_publisher: NATS发布器实例
        """
        super().__init__("binance_derivatives", symbols, nats_publisher)
        
        # Binance衍生品API配置
        self.api_base_url = "https://fapi.binance.com"
        self.open_interest_endpoint = "/futures/data/openInterestHist"
        
        self.logger.info("Binance衍生品未平仓量管理器初始化完成",
                        api_base_url=self.api_base_url)
    
    async def _fetch_open_interest_data(self, symbol: str) -> Dict[str, Any]:
        """
        获取Binance未平仓量数据
        
        Args:
            symbol: 交易对名称 (如: BTC-USDT)
            
        Returns:
            原始未平仓量数据
        """
        try:
            # 转换为Binance格式的交易对
            binance_symbol = symbol.replace('-', '')  # BTC-USDT -> BTCUSDT
            
            # 构建API请求
            url = f"{self.api_base_url}{self.open_interest_endpoint}"
            params = {
                'symbol': binance_symbol,
                'period': '5m',  # 5分钟间隔
                'limit': 1       # 获取最新一条记录
            }
            
            self.logger.debug("获取Binance未平仓量数据",
                            symbol=symbol,
                            binance_symbol=binance_symbol,
                            url=url,
                            params=params)
            
            # 发送请求
            response_data = await self._make_http_request(url, params)
            
            # Binance API返回的是数组，取第一条记录
            if isinstance(response_data, list) and len(response_data) > 0:
                result = response_data[0]
                self.logger.debug("Binance未平仓量API响应",
                                symbol=symbol,
                                response_keys=list(result.keys()) if result else None)
                return result
            else:
                self.logger.warning("Binance未平仓量API返回空数据", symbol=symbol)
                return {}
            
        except Exception as e:
            self.logger.error("获取Binance未平仓量数据失败",
                            symbol=symbol,
                            error=str(e))
            raise
    
    def _normalize_open_interest_data(self, raw_data: Dict[str, Any], symbol: str) -> Optional[NormalizedOpenInterest]:
        """
        标准化Binance未平仓量数据
        
        Args:
            raw_data: Binance API原始数据
            symbol: 交易对名称
            
        Returns:
            标准化的未平仓量数据
        """
        try:
            if not raw_data:
                return None
            
            # 解析Binance未平仓量数据
            # Binance API返回格式：
            # {
            #   "symbol": "BTCUSDT",
            #   "sumOpenInterest": "15845.12345678",
            #   "sumOpenInterestValue": "1234567890.12345678",
            #   "CMCCirculatingSupply": "165880.538",
            #   "timestamp": 1640995200000
            # }
            
            # 标准化交易对名称
            normalizer = DataNormalizer()
            normalized_symbol = normalizer.normalize_symbol_format(raw_data.get('symbol', ''), 'binance_derivatives')
            
            # 解析时间戳
            current_time = datetime.now(timezone.utc)
            data_timestamp = datetime.fromtimestamp(
                int(raw_data.get('timestamp', 0)) / 1000,
                tz=timezone.utc
            ) if raw_data.get('timestamp') else current_time
            
            # 解析未平仓量数据
            open_interest_value = Decimal(str(raw_data.get('sumOpenInterest', '0')))
            open_interest_usd = Decimal(str(raw_data.get('sumOpenInterestValue', '0')))
            
            # 构建标准化数据
            normalized_data = NormalizedOpenInterest(
                exchange_name="binance_derivatives",
                symbol_name=normalized_symbol,
                product_type="perpetual",
                instrument_id=raw_data.get('symbol', ''),
                open_interest_value=open_interest_value,
                open_interest_usd=open_interest_usd,
                open_interest_unit="contracts",
                mark_price=None,  # Binance未平仓量API不返回价格信息
                index_price=None,
                timestamp=data_timestamp,
                collected_at=current_time,
                change_24h=None,  # 需要额外计算
                change_24h_percent=None,
                raw_data=raw_data
            )
            
            self.logger.debug("Binance未平仓量数据标准化完成",
                            symbol=symbol,
                            normalized_symbol=normalized_symbol,
                            open_interest_value=str(open_interest_value),
                            open_interest_usd=str(open_interest_usd),
                            timestamp=data_timestamp.isoformat())
            
            return normalized_data
            
        except Exception as e:
            self.logger.error("Binance未平仓量数据标准化失败",
                            symbol=symbol,
                            error=str(e),
                            raw_data=raw_data)
            return None
