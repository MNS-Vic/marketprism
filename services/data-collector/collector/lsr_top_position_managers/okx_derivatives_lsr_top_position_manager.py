"""
OKX衍生品顶级大户多空持仓比例数据管理器（按持仓量计算）

实现OKX特定的API调用和数据处理逻辑
"""

from typing import Dict, Any, List, Optional
import aiohttp
from decimal import Decimal
from datetime import datetime, timezone

from collector.data_types import Exchange, MarketType, NormalizedLSRTopPosition, ProductType
from collector.normalizer import DataNormalizer
from .base_lsr_top_position_manager import BaseLSRTopPositionManager


class OKXDerivativesLSRTopPositionManager(BaseLSRTopPositionManager):
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
            symbols=symbols,
            normalizer=normalizer,
            nats_publisher=nats_publisher,
            config=config
        )
        
        # OKX API配置
        self.base_url = "https://www.okx.com"
        # 🔧 修复：使用正确的OKX LSR Top Position API端点
        # 根据OKX官方文档，使用合约多空账户比例（按账户数量）
        self.api_path = "/api/v5/rubik/stat/contracts/long-short-account-ratio"
        
        # OKX特定配置
        self.inst_type = "SWAP"  # 永续合约

        # 429退避机制配置
        self.backoff_delays = [1, 2, 4, 8, 16]  # 指数退避延迟（秒）
        self.current_backoff_index = 0
        self.last_429_time = None

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
        
        self.logger.info("🏭 OKXDerivativesLSRTopPositionManager初始化完成",
                        data_type=self.data_type,
                        exchange=self.exchange.value,
                        market_type=self.market_type.value,
                        fetch_interval=self.fetch_interval,
                        period=self.period,
                        symbols=self.symbols)
        
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
            # 检查是否需要重置退避策略
            self._reset_backoff_if_needed()

            # 🔧 修复：构建正确的请求参数
            # 从symbol提取币种 (BTC-USDT-SWAP -> BTC)
            ccy = symbol.split('-')[0] if '-' in symbol else symbol

            params = {
                'ccy': ccy,      # 使用币种而不是完整的交易对
                'period': '5m'   # 使用5分钟周期
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
                        result['exchange'] = 'okx_derivatives'
                        result['data_type'] = 'lsr_top_position'
                        
                        self.logger.debug("成功获取OKX顶级大户多空持仓比例数据",
                                        symbol=symbol,
                                        data_points=len(data['data']))
                        return result
                    else:
                        self.logger.warning("OKX API返回错误",
                                          symbol=symbol,
                                          code=data.get('code'),
                                          msg=data.get('msg'))
                        return None
                elif response.status == 429:
                    # 处理429限流错误
                    await self._handle_rate_limit(symbol)
                    return None
                else:
                    self.logger.error("OKX API请求失败",
                                    symbol=symbol,
                                    status=response.status,
                                    url=url)
                    return None

        except Exception as e:
            self.logger.error("获取OKX顶级大户多空持仓比例数据异常",
                            symbol=symbol,
                            error=e)
            return None

    async def _handle_rate_limit(self, symbol: str):
        """处理429限流错误，实施退避策略"""
        import asyncio
        from datetime import datetime, timezone

        current_time = datetime.now(timezone.utc)

        # 更新退避索引
        if self.current_backoff_index < len(self.backoff_delays) - 1:
            self.current_backoff_index += 1

        delay = self.backoff_delays[self.current_backoff_index]
        self.last_429_time = current_time

        self.logger.warning(f"⚠️ OKX API限流，执行退避策略",
                           symbol=symbol,
                           backoff_delay=delay,
                           backoff_level=self.current_backoff_index + 1)

        await asyncio.sleep(delay)

    def _reset_backoff_if_needed(self):
        """如果距离上次429错误超过一定时间，重置退避索引"""
        from datetime import datetime, timezone, timedelta

        if self.last_429_time:
            current_time = datetime.now(timezone.utc)
            if current_time - self.last_429_time > timedelta(minutes=5):
                self.current_backoff_index = 0
                self.last_429_time = None

    async def _normalize_data(self, raw_data: Dict[str, Any]) -> Optional[NormalizedLSRTopPosition]:
        """
        标准化OKX顶级大户多空持仓比例数据

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
            normalized_data = self.normalizer.normalize_okx_lsr_top_position(raw_data)

            if normalized_data:
                self.logger.debug("OKX顶级大户多空持仓比例数据标准化完成",
                                symbol=normalized_data.symbol_name,
                                long_short_ratio=str(normalized_data.long_short_ratio),
                                long_position_ratio=str(normalized_data.long_position_ratio),
                                short_position_ratio=str(normalized_data.short_position_ratio))
            else:
                self.logger.warning("OKX顶级大户多空持仓比例数据标准化失败",
                                  raw_data_preview=str(raw_data)[:200])

            return normalized_data



        except Exception as e:
            self.logger.error("标准化OKX顶级大户多空持仓比例数据失败",
                            symbol=raw_data.get('symbol'),
                            error=e)
            return None
