"""
OKX衍生品资金费率管理器

实现OKX永续合约资金费率数据收集：
- 使用OKX公共API获取资金费率数据
- 支持当前和预估资金费率
- 数据标准化和NATS发布
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional, List
import structlog

from .base_funding_rate_manager import BaseFundingRateManager
from ..data_types import NormalizedFundingRate, ProductType
from ..normalizer import DataNormalizer


class OKXDerivativesFundingRateManager(BaseFundingRateManager):
    """OKX衍生品资金费率管理器"""
    
    def __init__(self, symbols: List[str], nats_publisher=None):
        """
        初始化OKX衍生品资金费率管理器
        
        Args:
            symbols: 交易对列表 (如: ['BTC-USDT', 'ETH-USDT'])
            nats_publisher: NATS发布器实例
        """
        super().__init__("okx_derivatives", symbols, nats_publisher)
        
        # OKX API配置
        self.api_base_url = "https://www.okx.com"
        self.funding_rate_endpoint = "/api/v5/public/funding-rate"
        
        self.logger.info("OKX衍生品资金费率管理器初始化完成",
                        api_base_url=self.api_base_url)
    
    async def _fetch_funding_rate_data(self, symbol: str) -> Dict[str, Any]:
        """
        获取OKX资金费率数据
        
        Args:
            symbol: 交易对名称 (如: BTC-USDT)
            
        Returns:
            原始资金费率数据
        """
        try:
            # 处理OKX格式的交易对
            # 如果symbol已经包含-SWAP后缀，直接使用；否则添加-SWAP后缀
            if symbol.endswith('-SWAP'):
                okx_symbol = symbol  # 已经是OKX格式：BTC-USDT-SWAP
            else:
                okx_symbol = f"{symbol}-SWAP"  # 转换：BTC-USDT -> BTC-USDT-SWAP

            # 构建API请求
            url = f"{self.api_base_url}{self.funding_rate_endpoint}"
            params = {
                'instId': okx_symbol
            }
            
            self.logger.debug("获取OKX资金费率数据",
                            symbol=symbol,
                            okx_symbol=okx_symbol,
                            url=url)
            
            # 发送请求
            response_data = await self._make_http_request(url, params)
            
            # OKX API返回格式检查
            if not response_data or 'data' not in response_data:
                self.logger.warning("OKX资金费率API响应格式异常",
                                  symbol=symbol,
                                  response=response_data)
                return {}
            
            # 获取第一条数据（最新的资金费率）
            funding_data = response_data['data']
            if not funding_data:
                self.logger.warning("OKX资金费率数据为空", symbol=symbol)
                return {}
            
            # 返回第一条记录
            result = funding_data[0] if isinstance(funding_data, list) else funding_data
            
            self.logger.debug("OKX资金费率API响应",
                            symbol=symbol,
                            response_keys=list(result.keys()) if result else None)
            
            return result
            
        except Exception as e:
            self.logger.error("获取OKX资金费率数据失败",
                            symbol=symbol,
                            error=str(e))
            raise
    
    def _normalize_funding_rate_data(self, raw_data: Dict[str, Any], symbol: str) -> Optional[NormalizedFundingRate]:
        """
        标准化OKX资金费率数据
        
        Args:
            raw_data: OKX API原始数据
            symbol: 交易对名称
            
        Returns:
            标准化的资金费率数据
        """
        try:
            if not raw_data:
                return None
            
            # 解析OKX资金费率数据
            # OKX API返回格式：
            # {
            #   "instType": "SWAP",
            #   "instId": "BTC-USDT-SWAP",
            #   "fundingRate": "0.0001",
            #   "nextFundingRate": "0.0001",
            #   "fundingTime": "1640995200000"
            # }
            
            # 标准化交易对名称
            okx_symbol = raw_data.get('instId', '')
            normalizer = DataNormalizer()
            normalized_symbol = normalizer.normalize_symbol_format(okx_symbol, 'okx_derivatives')
            
            # 解析时间戳
            current_time = datetime.now(timezone.utc)
            funding_time = datetime.fromtimestamp(
                int(raw_data.get('fundingTime', 0)) / 1000,
                tz=timezone.utc
            ) if raw_data.get('fundingTime') else current_time
            
            # 解析费率数据
            current_funding_rate = Decimal(str(raw_data.get('fundingRate', '0')))
            estimated_funding_rate = None
            if raw_data.get('nextFundingRate'):
                estimated_funding_rate = Decimal(str(raw_data.get('nextFundingRate')))
            
            # 构建标准化数据
            normalized_data = NormalizedFundingRate(
                exchange_name="okx_derivatives",
                symbol_name=normalized_symbol,
                product_type="perpetual",
                instrument_id=okx_symbol,
                current_funding_rate=current_funding_rate,
                estimated_funding_rate=estimated_funding_rate,
                next_funding_time=funding_time,
                funding_interval="8h",
                mark_price=None,  # OKX资金费率API不返回标记价格
                index_price=None,  # OKX资金费率API不返回指数价格
                premium_index=None,
                timestamp=funding_time,
                raw_data=raw_data
            )
            
            self.logger.debug("OKX资金费率数据标准化完成",
                            symbol=symbol,
                            normalized_symbol=normalized_symbol,
                            current_funding_rate=str(current_funding_rate),
                            estimated_funding_rate=str(estimated_funding_rate) if estimated_funding_rate else None,
                            next_funding_time=funding_time.isoformat())
            
            return normalized_data
            
        except Exception as e:
            self.logger.error("OKX资金费率数据标准化失败",
                            symbol=symbol,
                            error=str(e),
                            raw_data=raw_data)
            return None
