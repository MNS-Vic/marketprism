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
import aiohttp

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
        # 切换为“当前值”端点，支持 10s 周期
        self.open_interest_endpoint = "/fapi/v1/openInterest"

        self.logger.info("Binance衍生品未平仓量管理器初始化完成",
                        api_base_url=self.api_base_url)
        # 合约规格缓存：symbol -> contractSize
        self._contract_size_cache: Dict[str, Decimal] = {}
        self._http_session: Optional[aiohttp.ClientSession] = None

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
                'symbol': binance_symbol
            }

            self.logger.debug("获取Binance未平仓量数据",
                              symbol=symbol,
                              binance_symbol=binance_symbol,
                              url=url,
                              params=params)

            # 发送请求
            response_data = await self._make_http_request(url, params)

            # 期望返回：{ "openInterest": "10659.139", "symbol": "BTCUSDT", "time": 1583127900000 }
            if isinstance(response_data, dict) and response_data.get('openInterest') is not None:
                result = {
                    'timestamp': response_data.get('time'),
                    'openInterest': response_data.get('openInterest'),
                    'symbol': response_data.get('symbol') or binance_symbol
                }
                # 获取标记价（mark price）
                try:
                    mark_price = await self._get_mark_price(binance_symbol)
                    if mark_price is not None:
                        result['markPrice'] = str(mark_price)
                except Exception as e:
                    self.logger.warning("获取Binance标记价失败", symbol=symbol, error=str(e))
                # 获取合约大小（contractSize），做缓存。USDT本位合约通常合约面值=1
                try:
                    contract_size = await self._get_contract_size(binance_symbol)
                    if contract_size is None:
                        contract_size = Decimal('1')
                    result['contractSize'] = str(contract_size)
                except Exception as e:
                    self.logger.warning("获取Binance合约规格失败，使用默认1", symbol=symbol, error=str(e))
                    result['contractSize'] = '1'

                # 如果没拿到合约大小，默认 1（USDT 本位永续张面为 1 合约=1 USDT 面值，多数情况等价）
                result.setdefault('contractSize', '1')

                self.logger.debug("Binance未平仓量API响应",
                                  symbol=symbol,
                                  response_keys=list(result.keys()))
                return result
            else:
                self.logger.warning("Binance未平仓量API返回空或异常", symbol=symbol, response=response_data)
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

            # 统一改为委托 normalizer（就地完成时间戳统一为UTC毫秒字符串）
            normalizer = DataNormalizer()
            norm = normalizer.normalize_open_interest(
                exchange="binance_derivatives",
                market_type="perpetual",
                symbol=symbol,
                raw_data=raw_data
            )

            from datetime import datetime, timezone
            from decimal import Decimal
            current_time = datetime.now(timezone.utc)

            def dec_or_none(x):
                try:
                    return Decimal(str(x)) if x is not None else None
                except Exception:
                    return None

            # 正确处理未平仓量：0是有效值，只有None才使用默认值
            oi_value = dec_or_none(norm.get('open_interest_value'))
            if oi_value is None:
                oi_value = Decimal('0')  # 只有在真正为None时才使用默认值

            normalized_data = NormalizedOpenInterest(
                exchange_name="binance_derivatives",
                symbol_name=norm.get('symbol', symbol),
                product_type="perpetual",
                instrument_id=norm.get('instrument_id', raw_data.get('symbol','')),
                open_interest_value=oi_value,
                open_interest_usd=dec_or_none(norm.get('open_interest_usd')),
                open_interest_unit=norm.get('open_interest_unit', 'contracts'),
                mark_price=dec_or_none(norm.get('mark_price')),
                index_price=dec_or_none(norm.get('index_price')),
                timestamp=current_time,
                collected_at=current_time,
                change_24h=dec_or_none(norm.get('change_24h')),
                change_24h_percent=dec_or_none(norm.get('change_24h_percent')),
                raw_data=raw_data
            )

            self.logger.debug("Binance未平仓量数据标准化完成(委托 normalizer)",
                              symbol=symbol,
                              normalized_symbol=normalized_data.symbol_name,
                              open_interest_value=str(normalized_data.open_interest_value))

            return normalized_data

        except Exception as e:
            self.logger.error("Binance未平仓量数据标准化失败",
                            symbol=symbol,
                            error=str(e),
                            raw_data=raw_data)
            return None


    async def _get_mark_price(self, symbol_no_dash: str) -> Optional[Decimal]:
        """获取标记价（优先 premiumIndex 的 markPrice，回退 indexPrice，再回退 ticker 价），带一次重试和详细日志"""
        async def _try_premium_index(stage: str) -> Optional[Decimal]:
            url = f"{self.api_base_url}/fapi/v1/premiumIndex"
            params = {'symbol': symbol_no_dash}
            try:
                data = await self._make_http_request(url, params)
                if isinstance(data, dict):
                    self.logger.debug("Binance premiumIndex 响应",
                                      symbol=symbol_no_dash,
                                      stage=stage,
                                      keys=list(data.keys()))
                    mp = data.get('markPrice')
                    if mp is not None:
                        return Decimal(str(mp))
                    ip = data.get('indexPrice')
                    if ip is not None:
                        return Decimal(str(ip))
            except Exception as e:
                self.logger.debug("premiumIndex 请求失败", symbol=symbol_no_dash, stage=stage, error=str(e))
            return None

        price = await _try_premium_index(stage="first")
        if price is None:
            price = await _try_premium_index(stage="retry")

        if price is None:
            url = f"{self.api_base_url}/fapi/v1/ticker/price"
            params = {'symbol': symbol_no_dash}
            try:
                data = await self._make_http_request(url, params)
                if isinstance(data, dict):
                    self.logger.debug("Binance ticker/price 响应", symbol=symbol_no_dash, keys=list(data.keys()))
                    p = data.get('price')
                    if p is not None:
                        price = Decimal(str(p))
            except Exception as e:
                self.logger.debug("ticker/price 请求失败", symbol=symbol_no_dash, error=str(e))

        if price is None:
            self.logger.warning("Binance 标记价获取失败（所有回退均失效）", symbol=symbol_no_dash)
        else:
            self.logger.debug("Binance 标记价获取成功", symbol=symbol_no_dash, mark_price=str(price))
            return price


    async def _get_contract_size(self, symbol_no_dash: str) -> Optional[Decimal]:
        """获取USDT本位永续的合约面值。优先缓存，其次请求合约信息接口。
        Binance 永续合约（USDⓈ-M）大多数为 1 张 = 1 USDT 面值，但仍以接口为准。
        失败时返回 None 以便上层回退到默认1。
        """
        # 命中缓存
        if symbol_no_dash in self._contract_size_cache:
            return self._contract_size_cache[symbol_no_dash]

        # 尝试查询交易规则接口
        url = f"{self.api_base_url}/fapi/v1/exchangeInfo"
        params = {"symbol": symbol_no_dash}
        try:
            data = await self._make_http_request(url, params)
            # 预期格式 { "symbols": [ {"symbol": "BTCUSDT", "contractSize": "1" , ...} ] }
            if isinstance(data, dict):
                symbols = data.get("symbols") or []
                if isinstance(symbols, list) and symbols:
                    info = symbols[0]
                    raw = info.get("contractSize")
                    if raw is not None:
                        try:
                            size = Decimal(str(raw))
                            # 写入缓存
                            self._contract_size_cache[symbol_no_dash] = size
                            return size
                        except Exception:
                            pass
        except Exception as e:
            self.logger.debug("exchangeInfo 查询合约面值失败", symbol=symbol_no_dash, error=str(e))

        # 未获取到，返回 None 让上层使用默认值
        return None
