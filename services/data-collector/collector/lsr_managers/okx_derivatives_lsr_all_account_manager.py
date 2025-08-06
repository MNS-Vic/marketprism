"""
OKX衍生品全市场多空持仓人数比例数据管理器（按账户数计算）

实现OKX特定的API调用和数据处理逻辑
"""

from typing import Dict, Any, List, Optional
import aiohttp

from collector.data_types import Exchange, MarketType, NormalizedLSRAllAccount
from collector.normalizer import DataNormalizer
from .base_lsr_manager import BaseLSRManager


class OKXDerivativesLSRAllAccountManager(BaseLSRManager):
    """
    OKX衍生品全市场多空持仓人数比例数据管理器（按账户数计算）

    API文档: https://www.okx.com/docs-v5/zh/#trading-statistics-rest-api-get-contract-long-short-ratio

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
        初始化OKX衍生品全市场多空持仓人数比例数据管理器（按账户数计算）

        Args:
            symbols: 交易对列表 (如: ['BTC-USDT-SWAP', 'ETH-USDT-SWAP'])
            normalizer: 数据标准化器
            nats_publisher: NATS发布器
            config: 配置信息
        """
        super().__init__(
            exchange=Exchange.OKX_DERIVATIVES,
            market_type=MarketType.DERIVATIVES,
            data_type='lsr_all_account',
            symbols=symbols,
            normalizer=normalizer,
            nats_publisher=nats_publisher,
            config=config
        )
        
        # OKX API配置 - 按账户数计算的API端点
        self.base_url = "https://www.okx.com"
        # 使用正确的All Account API端点
        self.api_path = "/api/v5/rubik/stat/contracts/long-short-account-ratio"
        
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
        
        self.logger.info("OKX衍生品全市场多空持仓人数比例数据管理器（按账户数）初始化完成",
                        base_url=self.base_url,
                        inst_type=self.inst_type)

    async def _fetch_data_from_api(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        从OKX API获取多空持仓人数比例数据
        
        Args:
            symbol: 交易对 (如: 'BTC-USDT-SWAP')
            
        Returns:
            API响应数据或None
        """
        try:
            # 构建请求参数
            # All Account API使用ccy参数，不是instId
            # 从symbol中提取币种，例如 BTC-USDT-SWAP -> BTC
            ccy = symbol.split('-')[0] if '-' in symbol else symbol

            params = {
                'ccy': ccy,  # 使用币种而不是完整的交易对
                'period': '5m',  # 统一使用5分钟周期
                'limit': '1'     # 统一只获取最新1条数据
                # All Account API不需要instType参数
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
                                      reason=response.reason,
                                      url=url,
                                      params=params)
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

    async def _process_raw_data(self, symbol: str, raw_data: Dict[str, Any]) -> None:
        """处理原始数据 - 重写以传递正确的参数"""
        try:
            # 从symbol中提取币种，例如 BTC-USDT-SWAP -> BTC
            ccy = symbol.split('-')[0] if '-' in symbol else symbol

            # 添加请求参数到原始数据中，供标准化使用
            raw_data['ccy'] = ccy  # All Account API使用ccy参数
            raw_data['period'] = self.period

            # 标准化数据
            normalized_data = await self._normalize_data(raw_data)

            if normalized_data:
                self.stats['data_points_processed'] += 1

                # 发布到NATS
                await self._publish_to_nats(normalized_data)

                self.logger.info(f"{self.data_type}数据处理完成",
                               data_type=self.data_type,
                               exchange=self.exchange.value,
                               symbol=normalized_data.symbol_name,
                               long_account_ratio=normalized_data.long_account_ratio,
                               short_account_ratio=normalized_data.short_account_ratio,
                               long_short_ratio=normalized_data.long_short_ratio)
            else:
                # 确保统计字段存在
                if 'data_points_failed' not in self.stats:
                    self.stats['data_points_failed'] = 0
                self.stats['data_points_failed'] += 1
                self.logger.warning(f"{self.data_type}数据标准化失败", symbol=symbol)

        except Exception as e:
            # 确保统计字段存在
            if 'data_points_failed' not in self.stats:
                self.stats['data_points_failed'] = 0
            self.stats['data_points_failed'] += 1
            self.logger.error(f"{self.data_type}数据处理异常",
                            symbol=symbol,
                            error=e)

    async def _normalize_data(self, raw_data: Dict[str, Any]) -> Optional[NormalizedLSRAllAccount]:
        """
        标准化OKX全市场多空持仓人数比例数据

        Args:
            raw_data: OKX API原始响应数据

        Returns:
            标准化的数据对象或None
        """
        try:
            # 使用normalizer进行标准化
            normalized_data = self.normalizer.normalize_okx_lsr_all_account(raw_data)
            
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
        将标准格式交易对转换为OKX格式
        
        Args:
            standard_symbol: 标准格式 (如: 'BTC-USDT')
            
        Returns:
            OKX格式 (如: 'BTC-USDT-SWAP')
        """
        if standard_symbol.endswith('-SWAP'):
            return standard_symbol
        return f"{standard_symbol}-SWAP"

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
            'manager_type': 'OKXDerivativesLSRAllAccountManager',
            'exchange': self.exchange.value,
            'market_type': self.market_type.value,
            'data_type': self.data_type,
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
