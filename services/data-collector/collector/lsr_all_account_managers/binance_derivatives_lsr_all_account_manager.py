"""
Binance衍生品全市场多空持仓人数比例数据管理器（按账户数计算）

实现Binance特定的API调用和数据处理逻辑
"""

from typing import Dict, Any, List, Optional
import aiohttp
from decimal import Decimal
from datetime import datetime, timezone

from collector.data_types import Exchange, MarketType, NormalizedLSRAllAccount, ProductType
from collector.normalizer import DataNormalizer
from .base_lsr_all_account_manager import BaseLSRAllAccountManager


class BinanceDerivativesLSRAllAccountManager(BaseLSRAllAccountManager):
    """
    Binance衍生品全市场多空持仓人数比例数据管理器（按账户数计算）

    API文档: https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/market-data/rest-api/Long-Short-Ratio

    数据格式:
    [{
      "symbol": "BTCUSDT",
      "longShortRatio": "1.4342",
      "longAccount": "0.5344",
      "shortAccount": "0.4238",
      "timestamp": "1583139600000"
    }]
    """
    
    def __init__(self,
                 symbols: List[str],
                 normalizer: DataNormalizer,
                 nats_publisher: Any,
                 config: dict):
        """
        初始化Binance衍生品全市场多空持仓人数比例数据管理器

        Args:
            symbols: 交易对列表 (如: ['BTCUSDT', 'ETHUSDT'])
            normalizer: 数据标准化器
            nats_publisher: NATS发布器
            config: 配置信息
        """
        super().__init__(
            exchange=Exchange.BINANCE_DERIVATIVES,
            market_type=MarketType.DERIVATIVES,
            symbols=symbols,
            normalizer=normalizer,
            nats_publisher=nats_publisher,
            config=config
        )
        
        # Binance API配置 - 按账户数计算的API端点
        self.base_url = "https://fapi.binance.com"
        self.api_path = "/futures/data/globalLongShortAccountRatio"
        
        # Binance特定配置
        # 支持的周期: 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d
        self.period_mapping = {
            '5m': '5m',
            '15m': '15m', 
            '30m': '30m',
            '1h': '1h',
            '2h': '2h',
            '4h': '4h',
            '6h': '6h',
            '12h': '12h',
            '1d': '1d'
        }
        
        self.logger.info("🏭 BinanceDerivativesLSRAllAccountManager初始化完成",
                        data_type=self.data_type,
                        exchange=self.exchange.value,
                        market_type=self.market_type.value,
                        fetch_interval=self.fetch_interval,
                        period=self.period,
                        symbols=self.symbols)
        
        self.logger.info("Binance衍生品全市场多空持仓人数比例数据管理器初始化完成",
                        base_url=self.base_url,
                        supported_periods=list(self.period_mapping.keys()))

    async def _fetch_data_from_api(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        从Binance API获取全市场多空持仓人数比例数据
        
        Args:
            symbol: 交易对 (如: 'BTCUSDT')
            
        Returns:
            API响应数据或None
        """
        try:
            # 构建请求参数
            params = {
                'symbol': symbol,
                'period': '5m',  # 统一使用5分钟周期
                'limit': '1'     # 统一只获取最新1条数据
            }
            
            # 构建完整URL
            url = f"{self.base_url}{self.api_path}"
            
            self.logger.debug("发送Binance API请求",
                            url=url,
                            params=params)
            
            # 发送请求
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data and isinstance(data, list) and len(data) > 0:
                        # 添加额外信息到数据中
                        result = {
                            'data': data,
                            'symbol': symbol,
                            'exchange': 'binance_derivatives',
                            'data_type': 'lsr_all_account'
                        }
                        
                        self.logger.debug("成功获取Binance全市场多空持仓人数比例数据",
                                        symbol=symbol,
                                        data_points=len(data))
                        return result
                    else:
                        self.logger.warning("Binance API返回空数据",
                                          symbol=symbol,
                                          response_data=data)
                        return None
                else:
                    self.logger.error("Binance API请求失败",
                                    symbol=symbol,
                                    status=response.status,
                                    url=url)
                    return None
                    
        except Exception as e:
            self.logger.error("获取Binance全市场多空持仓人数比例数据异常",
                            symbol=symbol,
                            error=e)
            return None

    async def _normalize_data(self, raw_data: Dict[str, Any]) -> Optional[NormalizedLSRAllAccount]:
        """
        标准化Binance全市场多空持仓人数比例数据

        Args:
            raw_data: 原始API数据

        Returns:
            标准化数据或None
        """
        try:
            # 🔧 修复：更严格的数据验证
            if not raw_data:
                self.logger.warning("标准化数据失败：raw_data为None")
                return None

            if not isinstance(raw_data, dict):
                self.logger.warning("标准化数据失败：raw_data不是字典类型",
                                  data_type=type(raw_data).__name__)
                return None

            if not raw_data.get('data'):
                self.logger.warning("标准化数据失败：raw_data中没有data字段",
                                  raw_data_keys=list(raw_data.keys()) if isinstance(raw_data, dict) else None)
                return None

            symbol = raw_data.get('symbol')
            if not symbol:
                self.logger.warning("标准化数据失败：缺少symbol字段")
                return None

            # 🔧 修复：使用正确的 Binance 专用标准化方法
            # 提取实际的数据数组
            data_array = raw_data.get('data', [])
            if not data_array:
                self.logger.warning("Binance数据为空")
                return None

            # 添加周期信息到数据数组中
            data_array[0]['period'] = raw_data.get('period', self.period)

            # 使用 Binance 专用的标准化方法
            return self.normalizer.normalize_binance_lsr_all_account(data_array)

            from datetime import datetime, timezone
            from decimal import Decimal
            current_time = datetime.now(timezone.utc)

            def dec_or_none(x):
                try:
                    return Decimal(str(x)) if x is not None else None
                except Exception:
                    return None

            # 正确处理比例数据：0是有效值，只有None才使用默认值
            lsr_value = dec_or_none(norm.get('long_short_ratio'))
            if lsr_value is None:
                lsr_value = Decimal('0')
            long_acc_ratio = dec_or_none(norm.get('long_account_ratio'))
            if long_acc_ratio is None:
                long_acc_ratio = Decimal('0')
            short_acc_ratio = dec_or_none(norm.get('short_account_ratio'))
            if short_acc_ratio is None:
                short_acc_ratio = Decimal('0')

            normalized_data = NormalizedLSRAllAccount(
                exchange_name='binance_derivatives',
                symbol_name=norm.get('symbol', symbol),
                product_type=ProductType.PERPETUAL,
                instrument_id=norm.get('instrument_id', symbol),
                timestamp=current_time,
                long_short_ratio=lsr_value,
                long_account_ratio=long_acc_ratio,
                short_account_ratio=short_acc_ratio,
                period=norm.get('period', self.period),
                raw_data=raw_data
            )

            self.logger.debug("Binance全市场多空持仓人数比例数据标准化完成(委托 normalizer)",
                            symbol=normalized_data.symbol_name,
                            long_short_ratio=str(normalized_data.long_short_ratio),
                            long_account_ratio=str(normalized_data.long_account_ratio),
                            short_account_ratio=str(normalized_data.short_account_ratio))

            return normalized_data

        except Exception as e:
            self.logger.error("标准化Binance全市场多空持仓人数比例数据失败",
                            symbol=raw_data.get('symbol'),
                            error=e)
            return None
