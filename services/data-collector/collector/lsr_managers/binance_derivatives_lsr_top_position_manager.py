"""
Binance衍生品顶级大户多空持仓比例数据管理器（按持仓量计算）

实现Binance特定的API调用和数据处理逻辑
"""

from typing import Dict, Any, List, Optional
import aiohttp

from collector.data_types import Exchange, MarketType, NormalizedLSRTopPosition
from collector.normalizer import DataNormalizer
from .base_lsr_manager import BaseLSRManager


class BinanceDerivativesLSRTopPositionManager(BaseLSRManager):
    """
    Binance衍生品多空持仓比例数据管理器（按持仓量计算）

    API文档: https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/market-data/rest-api/Top-Trader-Long-Short-Ratio

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
        初始化Binance衍生品多空持仓比例数据管理器
        
        Args:
            symbols: 交易对列表 (如: ['BTCUSDT', 'ETHUSDT'])
            normalizer: 数据标准化器
            nats_publisher: NATS发布器
            config: 配置信息
        """
        super().__init__(
            exchange=Exchange.BINANCE_DERIVATIVES,
            market_type=MarketType.DERIVATIVES,
            data_type='lsr_top_position',
            symbols=symbols,
            normalizer=normalizer,
            nats_publisher=nats_publisher,
            config=config
        )
        
        # Binance API配置
        self.base_url = "https://fapi.binance.com"
        self.api_path = "/futures/data/topLongShortPositionRatio"
        
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
        
        self.logger.info("Binance衍生品多空持仓比例数据管理器初始化完成",
                        base_url=self.base_url,
                        supported_periods=list(self.period_mapping.keys()))

    async def _fetch_data_from_api(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        从Binance API获取顶级交易者多空持仓比例数据
        
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
            
            # 发送HTTP请求
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Binance API直接返回数组
                    if isinstance(data, list) and data:
                        self.stats['data_points_received'] += len(data)
                        
                        self.logger.debug("Binance API请求成功",
                                        symbol=symbol,
                                        data_points=len(data))
                        
                        # 添加周期信息到数据中
                        return {
                            'data': data,
                            'period': self.period,
                            'symbol': symbol
                        }
                    else:
                        self.logger.warning("Binance API返回空数据",
                                          symbol=symbol,
                                          response=data)
                        return None
                else:
                    # 尝试解析错误信息
                    try:
                        error_data = await response.json()
                        self.logger.warning("Binance API HTTP错误",
                                          symbol=symbol,
                                          status=response.status,
                                          error=error_data)
                    except:
                        self.logger.warning("Binance API HTTP错误",
                                          symbol=symbol,
                                          status=response.status,
                                          reason=response.reason)
                    return None
                    
        except aiohttp.ClientError as e:
            self.logger.error("Binance API网络错误",
                            symbol=symbol,
                            error=e)
            return None
        except Exception as e:
            self.logger.error("Binance API请求异常",
                            symbol=symbol,
                            error=e)
            return None

    async def _normalize_data(self, raw_data: Dict[str, Any]) -> Optional[NormalizedLSRTopPosition]:
        """
        标准化Binance顶级交易者多空持仓比例数据
        
        Args:
            raw_data: Binance API原始响应数据
            
        Returns:
            标准化的数据对象或None
        """
        try:
            # 提取实际的数据数组
            data_array = raw_data.get('data', [])
            if not data_array:
                self.logger.warning("Binance数据为空")
                return None
            
            # 添加周期信息到数据数组中
            data_array[0]['period'] = raw_data.get('period', self.period)
            
            # 使用normalizer进行标准化
            normalized_data = self.normalizer.normalize_binance_lsr_top_position(data_array)
            
            if normalized_data:
                self.logger.debug("Binance数据标准化成功",
                                symbol=normalized_data.symbol_name,
                                long_short_ratio=str(normalized_data.long_short_ratio),
                                timestamp=normalized_data.timestamp.strftime('%Y-%m-%d %H:%M:%S'))
            else:
                self.logger.warning("Binance数据标准化失败",
                                  raw_data_preview=str(raw_data)[:200])
            
            return normalized_data
            
        except Exception as e:
            self.logger.error("Binance数据标准化异常",
                            error=e,
                            raw_data_preview=str(raw_data)[:200])
            return None

    def _get_binance_symbol_format(self, standard_symbol: str) -> str:
        """
        将标准格式交易对转换为Binance格式
        
        Args:
            standard_symbol: 标准格式 (如: 'BTC-USDT')
            
        Returns:
            Binance格式 (如: 'BTCUSDT')
        """
        return standard_symbol.replace('-', '')

    async def get_supported_symbols(self) -> List[str]:
        """
        获取支持的交易对列表
        
        Returns:
            支持的交易对列表
        """
        try:
            # 可以调用Binance的exchangeInfo API获取支持的交易对
            # 这里返回配置的交易对
            return self.symbols
            
        except Exception as e:
            self.logger.error("获取支持的交易对失败", error=e)
            return []

    def get_supported_periods(self) -> List[str]:
        """
        获取支持的数据周期列表
        
        Returns:
            支持的周期列表
        """
        return list(self.period_mapping.keys())

    def get_manager_info(self) -> Dict[str, Any]:
        """
        获取管理器信息
        
        Returns:
            管理器信息字典
        """
        return {
            'manager_type': 'BinanceDerivativesLSRPositionManager',
            'exchange': self.exchange.value,
            'market_type': self.market_type.value,
            'symbols': self.symbols,
            'base_url': self.base_url,
            'api_path': self.api_path,
            'supported_periods': self.get_supported_periods(),
            'fetch_interval': self.fetch_interval,
            'period': self.period,
            'limit': self.limit,
            'is_running': self.is_running,
            'stats': self.get_stats()
        }
