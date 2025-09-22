"""
OKX衍生品全市场多空持仓人数比例数据管理器（按账户数计算）

实现OKX特定的API调用和数据处理逻辑
"""

from typing import Dict, Any, List, Optional
import aiohttp
from decimal import Decimal
from datetime import datetime, timezone

from collector.data_types import Exchange, MarketType, NormalizedLSRAllAccount, ProductType
from collector.normalizer import DataNormalizer
from .base_lsr_all_account_manager import BaseLSRAllAccountManager


class OKXDerivativesLSRAllAccountManager(BaseLSRAllAccountManager):
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
        
        self.logger.info("🏭 OKXDerivativesLSRAllAccountManager初始化完成",
                        data_type=self.data_type,
                        exchange=self.exchange.value,
                        market_type=self.market_type.value,
                        fetch_interval=self.fetch_interval,
                        period=self.period,
                        symbols=self.symbols)
        
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
            }
            
            # 构建完整URL
            url = f"{self.base_url}{self.api_path}"
            
            # 发送请求
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # 检查API响应状态
                    if data.get('code') == '0' and data.get('data'):
                        # 添加symbol信息到数据中
                        result = data.copy()
                        result['symbol'] = symbol
                        result['ccy'] = ccy
                        result['exchange'] = 'okx_derivatives'
                        result['data_type'] = 'lsr_all_account'
                        
                        self.logger.debug("成功获取OKX全市场多空持仓人数比例数据",
                                        symbol=symbol,
                                        ccy=ccy,
                                        data_points=len(data['data']))
                        return result
                    else:
                        self.logger.warning("OKX API返回错误",
                                          symbol=symbol,
                                          ccy=ccy,
                                          code=data.get('code'),
                                          msg=data.get('msg'))
                        return None
                else:
                    self.logger.error("OKX API请求失败",
                                    symbol=symbol,
                                    ccy=ccy,
                                    status=response.status,
                                    url=url)
                    return None
                    
        except Exception as e:
            self.logger.error("获取OKX全市场多空持仓人数比例数据异常",
                            symbol=symbol,
                            error=e)
            return None

    async def _normalize_data(self, raw_data: Dict[str, Any]) -> Optional[NormalizedLSRAllAccount]:
        """
        标准化OKX全市场多空持仓人数比例数据
        
        Args:
            raw_data: 原始API数据
            
        Returns:
            标准化数据或None
        """
        try:
            if not raw_data or not raw_data.get('data'):
                return None

            symbol = raw_data['symbol']

            # 🔧 修复：使用正确的 OKX 专用标准化方法
            return self.normalizer.normalize_okx_lsr_all_account(raw_data)

            # 保持返回类型与基类一致：封装为 NormalizedLSRAllAccount（内部仍使用 datetime 字段，发布时再转字符串）
            from datetime import datetime, timezone
            from decimal import Decimal
            current_time = datetime.now(timezone.utc)

            # 从 norm 中提取字段（字符串）转为 Decimal/None 供 NormalizedLSRAllAccount 使用
            def dec_or_none(x):
                try:
                    return Decimal(str(x)) if x is not None else None
                except Exception:
                    return None

            normalized_data = NormalizedLSRAllAccount(
                exchange_name='okx_derivatives',
                symbol_name=norm.get('symbol', symbol),
                product_type=ProductType.PERPETUAL,
                instrument_id=norm.get('instrument_id', symbol),
                timestamp=current_time,  # 占位，发布时用 norm 的字符串字段
                long_short_ratio=dec_or_none(norm.get('long_short_ratio')) or Decimal('0'),
                long_account_ratio=dec_or_none(norm.get('long_account_ratio')) or Decimal('0'),
                short_account_ratio=dec_or_none(norm.get('short_account_ratio')) or Decimal('0'),
                period=norm.get('period', self.period),
                raw_data=raw_data
            )

            self.logger.debug("OKX全市场多空持仓人数比例数据标准化完成(委托 normalizer)",
                            symbol=normalized_data.symbol_name,
                            long_short_ratio=str(normalized_data.long_short_ratio),
                            long_account_ratio=str(normalized_data.long_account_ratio),
                            short_account_ratio=str(normalized_data.short_account_ratio))

            return normalized_data

        except Exception as e:
            self.logger.error("标准化OKX全市场多空持仓人数比例数据失败",
                            symbol=raw_data.get('symbol'),
                            error=e)
            return None
