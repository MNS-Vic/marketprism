"""
Deribit衍生品波动率指数管理器

实现Deribit交易所的波动率指数数据收集：
- 使用HTTP API获取波动率指数数据
- 支持BTC、ETH等主要加密货币
- 数据标准化和NATS发布
- 错误处理和重试机制
"""

import asyncio
import aiohttp
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Optional
import structlog

from .base_vol_index_manager import BaseVolIndexManager
from collector.normalizer import DataNormalizer

import json


class DeribitDerivativesVolIndexManager(BaseVolIndexManager):
    """Deribit衍生品波动率指数管理器"""

    def __init__(self, symbols: List[str], nats_publisher=None, config: dict = None):
        """
        初始化Deribit衍生品波动率指数管理器

        Args:
            symbols: 交易对列表 (如: ['BTC', 'ETH'])
            nats_publisher: NATS发布器实例
            config: 配置字典
        """
        # 保存原始config以便从exchanges读取细粒度参数
        self.config = config or {}
        super().__init__(
            exchange="deribit_derivatives",
            symbols=symbols,
            nats_publisher=nats_publisher,
            config=config
        )

        # Deribit API配置（HTTP轮询）
        self.api_base_url = "https://www.deribit.com"
        self.vol_index_endpoint = "/api/v2/public/get_volatility_index_data"

        self.normalizer = DataNormalizer()

        self.logger.info(
            "Deribit衍生品波动率指数管理器初始化完成",
            api_base_url=self.api_base_url,
            endpoint=self.vol_index_endpoint,
            mode="http-polling"
        )

    async def _collection_loop(self):
        """数据收集循环：HTTP轮询 Deribit 波动率指数，按分辨率边界对齐（默认60s整分）"""
        self.logger.info("开始收集波动率指数数据", symbols=self.symbols, mode="http-polling")

        # 解析对齐分辨率（秒），默认60s
        def _get_resolution_seconds() -> int:
            try:
                res = ((self.__dict__.get('config') or {}).get('exchanges') or {}) \
                    .get('deribit_derivatives', {}).get('vol_index', {}).get('resolution')
                if not res:
                    dt_cfg = (getattr(self, 'config', {}) or {}).get('data_types', {}).get('volatility_index', {})
                    api_cfg = dt_cfg.get('api_config', {}) if isinstance(dt_cfg, dict) else {}
                    res = api_cfg.get('resolution', '60')
                return int(str(res))
            except Exception:
                return 60

        while self.is_running:
            try:
                # 对齐到下一个分辨率边界，给出微小缓冲，确保使用最新一个bar
                res = max(1, _get_resolution_seconds())
                now = datetime.now(timezone.utc)
                # 对齐到下一分钟（或下一分辨率边界的整分），避免与epoch偏移相关的不对齐
                if res % 60 == 0:
                    next_boundary = (now.replace(second=0, microsecond=0) + timedelta(seconds=res))
                else:
                    # 非60整数倍，退回到模运算方案
                    remainder = now.timestamp() % res
                    next_boundary = now + timedelta(seconds=(res - remainder))
                sleep_s = max(0.0, (next_boundary - now).total_seconds() + 0.2)  # +200ms 缓冲
                if sleep_s > 0.01 and self.is_running:
                    await asyncio.sleep(sleep_s)

                # 按顺序轮询所有币种（尽量在边界后立即获取）
                for symbol in self.symbols:
                    if not self.is_running:
                        break
                    await self._collect_symbol_data(symbol)

                # 不再固定sleep整分钟；下一轮再次对齐边界
                await asyncio.sleep(0)

            except asyncio.CancelledError:
                self.logger.info("波动率指数数据收集任务被取消")
                break
            except Exception as e:
                self.logger.error("波动率指数数据收集循环异常", error=str(e))
                if self.is_running:
                    await asyncio.sleep(5)



    async def _fetch_vol_index_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        获取Deribit波动率指数数据

        Args:
            symbol: 交易对符号 (如: 'BTC', 'ETH')

        Returns:
            原始波动率指数数据字典，失败返回None
        """
        try:
            # 构建API请求URL
            url = f"{self.api_base_url}{self.vol_index_endpoint}"

            # 构建请求参数
            # 从配置读取分辨率（默认60 = 1分钟）
            resolution = None
            try:
                # 优先 exchanges.deribit_derivatives.vol_index.resolution
                resolution = ((self.__dict__.get('config') or {}).get('exchanges') or {}) \
                    .get('deribit_derivatives', {}).get('vol_index', {}).get('resolution')
            except Exception:
                resolution = None
            if not resolution:
                # 兼容 data_types.volatility_index.api_config.resolution
                try:
                    cfg = (getattr(self, 'config', {}) or {})
                    dt_cfg = (cfg.get('data_types') or {}).get('volatility_index') or {}
                    api_cfg = (dt_cfg.get('api_config') or {}) if isinstance(dt_cfg, dict) else {}
                    resolution = api_cfg.get('resolution', '60')
                except Exception:
                    resolution = '60'
            params = {
                'currency': symbol.upper(),  # BTC, ETH
                'start_timestamp': int((datetime.now(timezone.utc).timestamp() - 3600) * 1000),  # 1小时前
                'end_timestamp': int(datetime.now(timezone.utc).timestamp() * 1000),  # 现在
                'resolution': str(resolution or '60')  # 默认1分钟分辨率
            }

            self.logger.debug("🔍 请求Deribit波动率指数数据",
                            symbol=symbol,
                            url=url,
                            params=params)

            # 发送HTTP请求
            response_data = await self._make_http_request(url, params)
            if not response_data:
                self.logger.warning("Deribit API请求失败", symbol=symbol)
                return None

            # 检查响应格式
            if 'result' not in response_data:
                self.logger.warning("Deribit API响应格式异常",
                                  symbol=symbol,
                                  response=response_data)
                return None

            result = response_data['result']

            # 检查是否有数据
            if not result or 'data' not in result or not result['data']:
                self.logger.warning("Deribit波动率指数数据为空", symbol=symbol)
                return None

            # 获取最新的波动率指数数据
            data_points = result['data']
            if not data_points:
                self.logger.warning("Deribit波动率指数数据点为空", symbol=symbol)
                return None

            # 取最后一个数据点 (最新数据)
            # Deribit API返回格式: [timestamp, open, high, low, close]
            latest_data_point = data_points[-1]

            if not isinstance(latest_data_point, list) or len(latest_data_point) < 5:
                self.logger.warning("Deribit波动率指数数据点格式异常",
                                  symbol=symbol,
                                  data_point=latest_data_point)
                return None

            # 解析数据点: [timestamp, open, high, low, close]
            timestamp = latest_data_point[0]  # 毫秒时间戳
            volatility_open = latest_data_point[1]
            volatility_high = latest_data_point[2]
            volatility_low = latest_data_point[3]
            volatility_close = latest_data_point[4]  # 使用收盘价作为当前波动率指数

            self.logger.debug("🔍 Deribit波动率指数数据获取成功",
                            symbol=symbol,
                            data_points_count=len(data_points),
                            latest_timestamp=timestamp,
                            volatility_index=volatility_close)

            return {
                'currency': symbol.upper(),
                'timestamp': timestamp,
                'volatility_index': volatility_close,
                'volatility_open': volatility_open,
                'volatility_high': volatility_high,
                'volatility_low': volatility_low,
                'raw_data': latest_data_point
            }

        except Exception as e:
            self.logger.error("获取Deribit波动率指数数据异常",
                            symbol=symbol, error=str(e))
            return None

    async def _normalize_data(self, symbol: str, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        使用统一的标准化方法处理Deribit波动率指数数据

        Args:
            symbol: 交易对符号
            raw_data: 原始数据

        Returns:
            标准化后的数据字典，失败返回None
        """
        try:
            # 统一改为委托 normalizer（就地完成时间戳统一为UTC毫秒字符串）
            norm = self.normalizer.normalize_vol_index(
                exchange="deribit_derivatives",
                market_type="options",  # Deribit 波动率指数来源于期权产品
                symbol=symbol,
                raw_data=raw_data
            )

            if not norm:
                self.logger.warning("波动率指数数据标准化失败", symbol=symbol)
                return None

            # 转换为字典格式以保持兼容性 - 使用统一的UTC毫秒字符串时间戳
            normalized_data = {
                'exchange': norm.get('exchange', 'deribit_derivatives'),
                'symbol': norm.get('symbol', symbol),
                'currency': norm.get('currency', symbol),
                'vol_index': norm.get('volatility_index'),  # 字符串格式
                'volatility_index': norm.get('volatility_index'),  # 字符串格式
                'timestamp': norm.get('timestamp'),  # UTC毫秒字符串格式
                'collected_at': norm.get('collected_at'),  # UTC毫秒字符串格式
                'market_type': norm.get('market_type', 'options'),
                'data_source': norm.get('data_source', 'marketprism')
            }

            self.logger.debug("🔍 Deribit波动率指数数据标准化完成(委托 normalizer)",
                            symbol=symbol,
                            normalized_symbol=norm.get('symbol', symbol),
                            vol_index=norm.get('volatility_index'),
                            market_type=norm.get('market_type', 'options'),
                            timestamp=norm.get('timestamp'))

            return normalized_data

        except Exception as e:
            self.logger.error("波动率指数数据标准化异常",
                            symbol=symbol, error=str(e))


    async def _make_http_request(self, url: str, params: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """
        发送HTTP请求到Deribit API（健壮性增强）
        """
        for attempt in range(1, self.max_retries + 1):
            temp_session = None
            try:
                self.logger.debug("发送Deribit API请求",
                                  attempt=attempt,
                                  url=url,
                                  params=params)

                # 确保HTTP会话存在
                session = self.session
                if session is None or getattr(session, 'closed', True):
                    timeout = aiohttp.ClientTimeout(total=self.request_timeout)
                    temp_session = aiohttp.ClientSession(timeout=timeout)
                    session = temp_session

                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        # 放宽content-type限制并增强健壮性
                        try:
                            data = await response.json(content_type=None)
                        except Exception as je:
                            self.logger.warning("Deribit响应JSON解析失败",
                                                status=response.status,
                                                attempt=attempt,
                                                error=str(je))
                            data = None

                        if isinstance(data, dict):
                            # 检查Deribit API错误
                            if 'error' in data:
                                error_info = data['error'] or {}
                                self.logger.warning("Deribit API返回错误",
                                                  error_code=error_info.get('code'),
                                                  error_message=error_info.get('message'),
                                                  attempt=attempt)
                                # 某些错误不需要重试
                                if error_info.get('code') in [10009, 10010]:
                                    return None
                            else:
                                self.logger.debug("Deribit API请求成功", status=response.status)
                                return data
                        else:
                            self.logger.warning("Deribit响应类型异常",
                                                 status=response.status,
                                                 attempt=attempt,
                                                 data_type=str(type(data)))
                    elif response.status == 429:
                        self.logger.warning("Deribit API限流",
                                          status=response.status,
                                          attempt=attempt)
                        if attempt < self.max_retries:
                            await asyncio.sleep(self.retry_delay * attempt * 2)
                        continue
                    else:
                        self.logger.warning("Deribit API请求失败",
                                          status=response.status,
                                          attempt=attempt)
            except Exception as e:
                self.logger.error("Deribit API请求异常",
                                  attempt=attempt,
                                  error=str(e))
            finally:
                # 关闭临时会话
                if temp_session is not None:
                    try:
                        await temp_session.close()
                    except Exception:
                        pass

            # 重试前等待
            if attempt < self.max_retries:
                await asyncio.sleep(self.retry_delay * attempt)

        return None

    async def stop(self):
        """停止：调用父类停止（HTTP会话关闭）"""
        await super().stop()
