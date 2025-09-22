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
import aiohttp

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
        # 切换为合约维度当前值接口（仅永续）
        self.open_interest_endpoint = "/api/v5/public/open-interest"

        self.logger.info("OKX衍生品未平仓量管理器初始化完成",
                        api_base_url=self.api_base_url)
        # 合约规格缓存：instId -> { 'ctVal': Decimal, 'ctValCcy': str }
        self._instrument_cache: Dict[str, Dict[str, Any]] = {}

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
                'instType': 'SWAP',
                'instId': okx_symbol  # 例如 BTC-USDT-SWAP
            }

            self.logger.debug("获取OKX未平仓量数据",
                              symbol=symbol,
                              okx_symbol=okx_symbol,
                              url=url,
                              params=params)

            # 发送请求（优先 instId+instType）
            response_data = await self._make_http_request(url, params)
            self.logger.debug("OKX OI 第一次响应",
                              symbol=symbol,
                              okx_symbol=okx_symbol,
                              keys=list(response_data.keys()) if isinstance(response_data, dict) else None)

            # 尝试回退：若结构/数据为空，改用仅 instId；再回退 uly
            def extract_list(resp):
                if isinstance(resp, dict):
                    lst = resp.get('data') or []
                    return lst if isinstance(lst, list) else []
                return []

            data_list = extract_list(response_data)
            self.logger.debug("OKX OI 第一次 data_list 长度", length=len(data_list))
            if not data_list:
                # 回退1：仅 instId
                alt_params1 = {'instId': okx_symbol}
                self.logger.debug("OKX OI回退请求#1: 仅instId", params=alt_params1)
                response_data = await self._make_http_request(url, alt_params1)
                self.logger.debug("OKX OI 回退#1 响应",
                                  keys=list(response_data.keys()) if isinstance(response_data, dict) else None)
                data_list = extract_list(response_data)
                self.logger.debug("OKX OI 回退#1 data_list 长度", length=len(data_list))

            if not data_list:
                # 回退2：instType+uly（去掉-SWAP）
                uly = okx_symbol.replace('-SWAP', '')
                alt_params2 = {'instType': 'SWAP', 'uly': uly}
                self.logger.debug("OKX OI回退请求#2: instType+uly", params=alt_params2)
                response_data = await self._make_http_request(url, alt_params2)
                self.logger.debug("OKX OI 回退#2 响应",
                                  keys=list(response_data.keys()) if isinstance(response_data, dict) else None)
                data_list = extract_list(response_data)
                self.logger.debug("OKX OI 回退#2 data_list 长度", length=len(data_list))

            if not data_list:
                self.logger.warning("OKX未平仓量数据为空（含回退失败）",
                                    symbol=symbol,
                                    okx_symbol=okx_symbol,
                                    last_params=params)
                return {}

            # 取第一条（当前值）
            item = data_list[0]
            # 规范化为内部通用raw结构
            # 按OKX官方字段命名保留原始结构，避免在Manager层改名
            target_data = {
                'ts': item.get('ts'),
                'oi': item.get('oi'),
                'instId': item.get('instId') or okx_symbol,
                'oiCcy': item.get('oiCcy')
            }
            self.logger.debug("OKX OI raw assembled",
                              keys=list(target_data.keys()),
                              has_markPx=('markPx' in target_data),
                              has_ctVal=('ctVal' in target_data))

            # 获取标记价（mark price）
            try:
                mark_price = await self._get_mark_price(okx_symbol)
                if mark_price is not None:
                    target_data['markPx'] = str(mark_price)
            except Exception as e:
                self.logger.warning("获取OKX标记价失败", symbol=symbol, error=str(e))


            # 获取合约面值（ctVal，带缓存）
            try:
                ct_val, ct_ccy = await self._get_instrument_ctval(okx_symbol)
                if ct_val is not None:
                    target_data['ctVal'] = str(ct_val)
                    target_data['ctValCcy'] = ct_ccy
            except Exception as e:
                self.logger.warning("获取OKX合约面值失败", symbol=symbol, error=str(e))

            self.logger.debug("OKX OI fetch 汇总",
                              raw_keys=list(target_data.keys()),
                              has_markPrice=('markPrice' in target_data),
                              has_ctVal=('ctVal' in target_data))

            return target_data

            # 获取合约规格（ctVal/ctValCcy），带缓存
            try:
                ct_val, ct_val_ccy = await self._get_instrument_ctval(okx_symbol)
                if ct_val is not None:
                    target_data['ctVal'] = str(ct_val)
                if ct_val_ccy is not None:
                    target_data['ctValCcy'] = ct_val_ccy
            except Exception as e:
                self.logger.warning("获取OKX合约规格失败", symbol=symbol, error=str(e))

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
        标准化OKX未平仓量数据（委托到 normalizer 层，Manager 不做数据格式转换）
        """
        try:
            if not raw_data:
                return None

            normalizer = DataNormalizer()
            normalized = normalizer.normalize_okx_open_interest(raw_data)

            if normalized:
                self.logger.debug(
                    "OKX未平仓量数据标准化完成(由 normalizer 处理)",
                    symbol=symbol,
                    normalized_symbol=normalized.symbol_name,
                    open_interest_value=str(normalized.open_interest_value)
                )
            else:
                self.logger.warning("OKX未平仓量数据标准化失败", symbol=symbol)

            return normalized

        except Exception as e:
            self.logger.error("OKX未平仓量数据标准化失败",
                              symbol=symbol,
                              error=str(e),
                              raw_data=raw_data)
            return None


    async def _get_mark_price(self, inst_id: str) -> Optional[Decimal]:
        """获取标记价（OKX mark price）"""
        try:
            url = f"{self.api_base_url}/api/v5/public/mark-price"
            params = { 'instId': inst_id }
            data = await self._make_http_request(url, params)
            if isinstance(data, dict):
                arr = data.get('data') or []
                if arr:
                    mp = (arr[0] or {}).get('markPx')
                    if mp is not None:
                        return Decimal(str(mp))
        except Exception:
            pass
        return None

    async def _get_instrument_ctval(self, inst_id: str) -> (Optional[Decimal], Optional[str]):
        """获取合约面值（ctVal, ctValCcy），使用缓存减少请求"""
        if inst_id in self._instrument_cache:
            cache = self._instrument_cache[inst_id]
            return cache.get('ctVal'), cache.get('ctValCcy')
        try:
            url = f"{self.api_base_url}/api/v5/public/instruments"
            params = { 'instType': 'SWAP', 'instId': inst_id }
            data = await self._make_http_request(url, params)
            if isinstance(data, dict):
                arr = data.get('data') or []
                for it in arr:
                    if it.get('instId') == inst_id:
                        ctval = it.get('ctVal')
                        ctvalccy = it.get('ctValCcy')
                        ct_val = Decimal(str(ctval)) if ctval is not None else None
                        self._instrument_cache[inst_id] = { 'ctVal': ct_val, 'ctValCcy': ctvalccy }
                        return ct_val, ctvalccy
        except Exception:
            pass
        return None, None

