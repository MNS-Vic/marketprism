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
            
            # 统一改为委托 normalizer（就地完成时间戳统一为UTC毫秒字符串）
            normalizer = DataNormalizer()
            norm = normalizer.normalize_funding_rate(
                exchange="binance_derivatives",
                market_type="perpetual",
                symbol=symbol,
                raw_data=raw_data
            )

            # 保持返回类型与基类一致：封装为 NormalizedFundingRate（内部仍使用 datetime 字段，发布时再转字符串）
            # 解析必要字段，时间字段暂用当前时间占位，确保下游发布格式化为毫秒UTC字符串
            from datetime import datetime, timezone
            from decimal import Decimal
            current_time = datetime.now(timezone.utc)

            # 从 norm 中提取字段（字符串）转为 Decimal/None 供 NormalizedFundingRate 使用
            def dec_or_none(x):
                try:
                    return Decimal(str(x)) if x is not None else None
                except Exception:
                    return None

            # 正确处理资金费率：0是有效值，只有None才使用默认值
            funding_rate_value = dec_or_none(norm.get('current_funding_rate'))
            if funding_rate_value is None:
                funding_rate_value = Decimal('0')  # 只有在真正为None时才使用默认值

            normalized_data = NormalizedFundingRate(
                exchange_name="binance_derivatives",
                symbol_name=norm.get('symbol', symbol),
                product_type="perpetual",
                instrument_id=norm.get('instrument_id', raw_data.get('symbol','')),
                current_funding_rate=funding_rate_value,
                estimated_funding_rate=dec_or_none(norm.get('estimated_funding_rate')),
                next_funding_time=current_time,  # 占位，发布时用 norm 的字符串字段
                funding_interval=norm.get('funding_interval','8h'),
                mark_price=dec_or_none(norm.get('mark_price')),
                index_price=dec_or_none(norm.get('index_price')),
                premium_index=dec_or_none(norm.get('premium_index')),
                timestamp=current_time,
                raw_data=raw_data
            )

            self.logger.debug("Binance资金费率数据标准化完成(委托 normalizer)",
                              symbol=symbol,
                              normalized_symbol=normalized_data.symbol_name,
                              current_funding_rate=str(normalized_data.current_funding_rate))

            return normalized_data
            
        except Exception as e:
            self.logger.error("Binance资金费率数据标准化失败",
                            symbol=symbol,
                            error=str(e),
                            raw_data=raw_data)
            return None
