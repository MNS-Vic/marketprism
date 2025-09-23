"""
OKX衍生品顶级大户多空持仓比例数据管理器（按持仓量计算）

实现OKX特定的API调用和数据处理逻辑
"""

from typing import Dict, Any, List, Optional
import aiohttp

from collector.data_types import Exchange, MarketType, NormalizedLSRTopPosition
from collector.normalizer import DataNormalizer
from .base_lsr_manager import BaseLSRManager


class OKXDerivativesLSRTopPositionManager(BaseLSRManager):
    """
    OKX衍生品顶级大户多空持仓比例数据管理器（按持仓量计算）

    API文档: https://www.okx.com/docs-v5/zh/#trading-statistics-rest-api-get-top-traders-contract-long-short-ratio-by-position

    数据格式:
    {
      "code": "0",
      "msg": "",
      "data": [{
        "ts": "1597026383085",
        "longShortRatio": "1.4342",
        "longRatio": "0.5344",
        "shortRatio": "0.4656"
      }]
    }
    """
    
    def __init__(self,
                 symbols: List[str],
                 normalizer: DataNormalizer,
                 nats_publisher: Any,
                 config: dict):
        """
        初始化OKX衍生品顶级大户多空持仓比例数据管理器（按持仓量计算）

        Args:
            symbols: 交易对列表 (如: ['BTC-USDT-SWAP', 'ETH-USDT-SWAP'])
            normalizer: 数据标准化器
            nats_publisher: NATS发布器
            config: 配置信息
        """
        super().__init__(
            exchange=Exchange.OKX_DERIVATIVES,
            market_type=MarketType.DERIVATIVES,
            data_type='lsr_top_position',
            symbols=symbols,
            normalizer=normalizer,
            nats_publisher=nats_publisher,
            config=config
        )
        
        # OKX API配置
        self.base_url = "https://www.okx.com"
        self.api_path = "/api/v5/rubik/stat/contracts/long-short-position-ratio-contract-top-trader"
        
        # OKX特定配置
        self.inst_type = "SWAP"  # 永续合约

        # OKX支持的周期格式映射
        self.period_mapping = {
            '5m': '5m',
            '15m': '15m',
            '30m': '30m',
            '1h': '1H',  # OKX使用大写H
            '2h': '2H',
            '4h': '4H',
            '6h': '6H',
            '12h': '12H',
            '1d': '1D'   # OKX使用大写D
        }
        
        self.logger.info("OKX衍生品顶级大户多空持仓比例数据管理器（按持仓量）初始化完成",
                        base_url=self.base_url,
                        inst_type=self.inst_type)

    async def _fetch_data_from_api(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        从OKX API获取顶级交易者多空持仓比例数据
        
        Args:
            symbol: 交易对 (如: 'BTC-USDT-SWAP')
            
        Returns:
            API响应数据或None
        """
        try:
            # 构建请求参数
            params = {
                'instId': symbol,
                'period': '5m',  # 统一使用5分钟周期
                'limit': '1',    # 统一只获取最新1条数据
                'instType': self.inst_type  # 添加产品类型参数
            }
            
            # 构建完整URL
            url = f"{self.base_url}{self.api_path}"
            
            self.logger.debug("发送OKX API请求",
                            url=url,
                            params=params)
            
            # 发送HTTP请求
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # 检查API响应状态
                    if data.get('code') == '0':
                        self.stats['data_points_received'] += len(data.get('data', []))
                        
                        self.logger.debug("OKX API请求成功",
                                        symbol=symbol,
                                        data_points=len(data.get('data', [])))
                        return data
                    else:
                        self.logger.warning("OKX API返回错误",
                                          symbol=symbol,
                                          code=data.get('code'),
                                          msg=data.get('msg'))
                        return None
                else:
                    self.logger.warning("OKX API HTTP错误",
                                      symbol=symbol,
                                      status=response.status,
                                      reason=response.reason)
                    return None
                    
        except aiohttp.ClientError as e:
            self.logger.error("OKX API网络错误",
                            symbol=symbol,
                            error=e)
            return None
        except Exception as e:
            self.logger.error("OKX API请求异常",
                            symbol=symbol,
                            error=e)
            return None

    async def _normalize_data(self, raw_data: Dict[str, Any]) -> Optional[NormalizedLSRTopPosition]:
        """
        标准化OKX顶级大户多空持仓比例数据

        Args:
            raw_data: OKX API原始响应数据（基类已添加instId和period）

        Returns:
            标准化的数据对象或None
        """
        try:
            # 使用normalizer进行标准化
            normalized_data = self.normalizer.normalize_okx_lsr_top_position(raw_data)
            
            if normalized_data:
                self.logger.debug("OKX数据标准化成功",
                                symbol=normalized_data.symbol_name,
                                long_short_ratio=str(normalized_data.long_short_ratio),
                                timestamp=normalized_data.timestamp.strftime('%Y-%m-%d %H:%M:%S'))
            else:
                self.logger.warning("OKX数据标准化失败",
                                  raw_data_preview=str(raw_data)[:200])
            
            return normalized_data
            
        except Exception as e:
            self.logger.error("OKX数据标准化异常",
                            error=e,
                            raw_data_preview=str(raw_data)[:200])
            return None

    def _get_okx_symbol_format(self, standard_symbol: str) -> str:
        """
        将标准格式交易对转换为OKX永续格式（统一使用Normalizer）
        """
        try:
            return self.normalizer.normalize_okx_perp_symbol(standard_symbol)
        except Exception:
            s = (standard_symbol or "").upper()
            return s if s.endswith('-SWAP') else f"{s}-SWAP"

    async def get_supported_symbols(self) -> List[str]:
        """
        获取支持的交易对列表
        
        Returns:
            支持的交易对列表
        """
        try:
            # 可以调用OKX的instruments API获取支持的交易对
            # 这里返回配置的交易对
            return self.symbols
            
        except Exception as e:
            self.logger.error("获取支持的交易对失败", error=e)
            return []

    def get_manager_info(self) -> Dict[str, Any]:
        """
        获取管理器信息
        
        Returns:
            管理器信息字典
        """
        return {
            'manager_type': 'OKXDerivativesLSRTopPositionManager',
            'exchange': self.exchange.value,
            'market_type': self.market_type.value,
            'symbols': self.symbols,
            'base_url': self.base_url,
            'api_path': self.api_path,
            'inst_type': self.inst_type,
            'fetch_interval': self.fetch_interval,
            'period': self.period,
            'limit': self.limit,
            'is_running': self.is_running,
            'stats': self.get_stats()
        }
