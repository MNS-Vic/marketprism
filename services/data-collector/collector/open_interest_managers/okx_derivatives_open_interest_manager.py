"""
OKX衍生品未平仓量管理器

实现OKX永续合约未平仓量数据收集：
- 使用OKX公共API获取未平仓量和成交量数据
- 支持USD价值计算和变化统计
- 数据标准化和NATS发布
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional, List
import structlog

from .base_open_interest_manager import BaseOpenInterestManager
from ..data_types import NormalizedOpenInterest, ProductType
from ..normalizer import DataNormalizer


class OKXDerivativesOpenInterestManager(BaseOpenInterestManager):
    """OKX衍生品未平仓量管理器"""
    
    def __init__(self, symbols: List[str], nats_publisher=None):
        """
        初始化OKX衍生品未平仓量管理器
        
        Args:
            symbols: 交易对列表 (如: ['BTC-USDT', 'ETH-USDT'])
            nats_publisher: NATS发布器实例
        """
        super().__init__("okx_derivatives", symbols, nats_publisher)
        
        # OKX API配置
        self.api_base_url = "https://www.okx.com"
        self.open_interest_endpoint = "/api/v5/rubik/stat/contracts/open-interest-volume"
        
        self.logger.info("OKX衍生品未平仓量管理器初始化完成",
                        api_base_url=self.api_base_url)
    
    async def _fetch_open_interest_data(self, symbol: str) -> Dict[str, Any]:
        """
        获取OKX未平仓量数据
        
        Args:
            symbol: 交易对名称 (如: BTC-USDT)
            
        Returns:
            原始未平仓量数据
        """
        try:
            # 处理OKX格式的交易对
            # 如果symbol已经包含-SWAP后缀，直接使用；否则添加-SWAP后缀
            if symbol.endswith('-SWAP'):
                okx_symbol = symbol  # 已经是OKX格式：BTC-USDT-SWAP
            else:
                okx_symbol = f"{symbol}-SWAP"  # 转换：BTC-USDT -> BTC-USDT-SWAP

            # 构建API请求
            url = f"{self.api_base_url}{self.open_interest_endpoint}"
            params = {
                'ccy': okx_symbol.split('-')[0],  # 提取基础货币，如BTC
                'period': '5m',  # 5分钟间隔
                'limit': '1'     # 获取最新一条记录
            }
            
            self.logger.debug("获取OKX未平仓量数据",
                            symbol=symbol,
                            okx_symbol=okx_symbol,
                            url=url,
                            params=params)
            
            # 发送请求
            response_data = await self._make_http_request(url, params)
            
            # OKX API返回格式检查
            if not response_data or 'data' not in response_data:
                self.logger.warning("OKX未平仓量API响应格式异常",
                                  symbol=symbol,
                                  response=response_data)
                return {}
            
            # 获取数据列表
            data_list = response_data['data']
            if not data_list:
                self.logger.warning("OKX未平仓量数据为空", symbol=symbol)
                return {}
            
            # 获取最新的数据（第一条记录）
            if isinstance(data_list, list) and len(data_list) > 0:
                latest_item = data_list[0]  # 获取最新的记录
                if isinstance(latest_item, list) and len(latest_item) >= 3:
                    # OKX返回的是数组格式: [timestamp, openInterest, volume]
                    target_data = {
                        'timestamp': latest_item[0],
                        'openInterest': latest_item[1],
                        'volume': latest_item[2],
                        'symbol': okx_symbol,
                        'ccy': params['ccy']
                    }
                else:
                    self.logger.warning("OKX数据格式异常", symbol=symbol, item_format=type(latest_item))
                    return {}
            else:
                self.logger.warning("OKX未平仓量数据列表为空", symbol=symbol)
                return {}
            
            self.logger.debug("OKX未平仓量API响应",
                            symbol=symbol,
                            response_keys=list(target_data.keys()) if target_data else None)
            
            return target_data
            
        except Exception as e:
            self.logger.error("获取OKX未平仓量数据失败",
                            symbol=symbol,
                            error=str(e))
            raise
    
    def _normalize_open_interest_data(self, raw_data: Dict[str, Any], symbol: str) -> Optional[NormalizedOpenInterest]:
        """
        标准化OKX未平仓量数据
        
        Args:
            raw_data: OKX API原始数据
            symbol: 交易对名称
            
        Returns:
            标准化的未平仓量数据
        """
        try:
            if not raw_data:
                return None
            
            # 解析OKX未平仓量数据
            # OKX API返回格式（经过处理后）：
            # {
            #   "timestamp": "1640995200000",
            #   "openInterest": "123456.789",
            #   "volume": "987654.321",
            #   "symbol": "BTC-USDT-SWAP",
            #   "ccy": "BTC"
            # }
            
            # 标准化交易对名称
            normalizer = DataNormalizer()
            okx_symbol = raw_data.get('symbol', '')
            normalized_symbol = normalizer.normalize_symbol_format(okx_symbol, 'okx_derivatives')
            
            # 解析时间戳
            current_time = datetime.now(timezone.utc)
            data_timestamp = datetime.fromtimestamp(
                int(raw_data.get('timestamp', 0)) / 1000,
                tz=timezone.utc
            ) if raw_data.get('timestamp') else current_time
            
            # 解析未平仓量数据
            open_interest_value = Decimal(str(raw_data.get('openInterest', '0')))
            
            # OKX的未平仓量通常以USD计价，但我们需要根据实际情况调整
            # 这里假设openInterest已经是USD价值
            open_interest_usd = open_interest_value
            
            # 构建标准化数据
            normalized_data = NormalizedOpenInterest(
                exchange_name="okx_derivatives",
                symbol_name=normalized_symbol,
                product_type="perpetual",
                instrument_id=okx_symbol,
                open_interest_value=open_interest_value,
                open_interest_usd=open_interest_usd,
                open_interest_unit="USD",
                mark_price=None,  # OKX未平仓量API不返回价格信息
                index_price=None,
                timestamp=data_timestamp,
                collected_at=current_time,
                change_24h=None,  # 需要额外计算
                change_24h_percent=None,
                raw_data=raw_data
            )
            
            self.logger.debug("OKX未平仓量数据标准化完成",
                            symbol=symbol,
                            normalized_symbol=normalized_symbol,
                            open_interest_value=str(open_interest_value),
                            open_interest_usd=str(open_interest_usd),
                            timestamp=data_timestamp.isoformat())
            
            return normalized_data
            
        except Exception as e:
            self.logger.error("OKX未平仓量数据标准化失败",
                            symbol=symbol,
                            error=str(e),
                            raw_data=raw_data)
            return None
