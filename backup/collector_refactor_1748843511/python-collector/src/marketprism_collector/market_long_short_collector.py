"""
市场多空仓人数比数据收集器

通过REST API定时收集币安和OKX的整个市场多空仓人数比数据，
标准化后推送到NATS
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List, Callable
import structlog

from .rest_client import RestClientManager, RestClientConfig, ExchangeRestClient
from .types import (
    Exchange, DataType, NormalizedMarketLongShortRatio
)


class MarketLongShortDataCollector:
    """市场多空仓人数比数据收集器"""
    
    def __init__(self, rest_client_manager: RestClientManager):
        self.rest_client_manager = rest_client_manager
        self.logger = structlog.get_logger(__name__)
        
        # 客户端映射
        self.clients: Dict[Exchange, ExchangeRestClient] = {}
        
        # 回调函数
        self.callbacks: List[Callable[[NormalizedMarketLongShortRatio], None]] = []
        
        # 配置
        self.symbols = ["BTC-USDT", "ETH-USDT"]  # 默认监控的交易对
        self.collection_interval = 300  # 5分钟收集一次
        
        # 状态
        self.is_running = False
        self.collection_task: Optional[asyncio.Task] = None
        
        # 统计
        self.stats = {
            'total_collections': 0,
            'successful_collections': 0,
            'failed_collections': 0,
            'last_collection_time': None,
            'data_points_collected': 0
        }
    
    async def start(self, symbols: Optional[List[str]] = None):
        """启动市场多空仓人数比数据收集器"""
        try:
            self.logger.info("启动市场多空仓人数比数据收集器")
            
            if symbols:
                self.symbols = symbols
            
            # 创建交易所REST客户端
            await self._setup_exchange_clients()
            
            # 启动定时收集任务
            self.is_running = True
            self.collection_task = asyncio.create_task(self._collection_loop())
            
            self.logger.info(
                "市场多空仓人数比数据收集器启动成功",
                symbols=self.symbols,
                interval=self.collection_interval
            )
            
        except Exception as e:
            self.logger.error("启动市场多空仓人数比数据收集器失败", error=str(e))
            await self.stop()
            raise
    
    async def stop(self):
        """停止市场多空仓人数比数据收集器"""
        try:
            self.logger.info("停止市场多空仓人数比数据收集器")
            self.is_running = False
            
            # 停止收集任务
            if self.collection_task:
                self.collection_task.cancel()
                try:
                    await self.collection_task
                except asyncio.CancelledError:
                    pass
            
            self.logger.info("市场多空仓人数比数据收集器已停止")
            
        except Exception as e:
            self.logger.error("停止市场多空仓人数比数据收集器失败", error=str(e))
    
    async def _setup_exchange_clients(self):
        """设置交易所REST客户端"""
        # Binance客户端配置
        binance_config = RestClientConfig(
            base_url="https://fapi.binance.com",
            timeout=10,
            max_retries=3,
            rate_limit_per_minute=1200,  # Binance限制
            verify_ssl=True
        )
        
        binance_client = self.rest_client_manager.create_exchange_client(
            Exchange.BINANCE, binance_config
        )
        self.clients[Exchange.BINANCE] = binance_client
        
        # OKX客户端配置
        okx_config = RestClientConfig(
            base_url="https://www.okx.com",
            timeout=10,
            max_retries=3,
            rate_limit_per_second=5,  # OKX限制：5次/2s
            verify_ssl=True
        )
        
        okx_client = self.rest_client_manager.create_exchange_client(
            Exchange.OKX, okx_config
        )
        self.clients[Exchange.OKX] = okx_client
        
        # 启动所有客户端
        await self.rest_client_manager.start_all()
        
        self.logger.info("交易所REST客户端设置完成")
    
    async def _collection_loop(self):
        """数据收集循环"""
        while self.is_running:
            try:
                await self._collect_all_data()
                
                # 等待下次收集
                await asyncio.sleep(self.collection_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("数据收集循环错误", error=str(e))
                await asyncio.sleep(30)  # 错误后等待30秒再重试
    
    async def _collect_all_data(self):
        """收集所有交易所的市场多空仓人数比数据"""
        self.stats['total_collections'] += 1
        collection_start = datetime.utcnow()
        
        try:
            # 并发收集所有交易所的数据
            tasks = []
            
            for exchange in [Exchange.BINANCE, Exchange.OKX]:
                for symbol in self.symbols:
                    task = asyncio.create_task(
                        self._collect_exchange_symbol_data(exchange, symbol)
                    )
                    tasks.append(task)
            
            # 等待所有任务完成
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            successful_count = 0
            for result in results:
                if isinstance(result, Exception):
                    self.logger.warning("数据收集任务失败", error=str(result))
                elif result:
                    successful_count += 1
                    self.stats['data_points_collected'] += 1
                    
                    # 发送到回调函数
                    for callback in self.callbacks:
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback(result)
                            else:
                                callback(result)
                        except Exception as e:
                            self.logger.error("回调函数执行失败", error=str(e))
            
            self.stats['successful_collections'] += 1
            self.stats['last_collection_time'] = collection_start
            
            self.logger.info(
                "数据收集完成",
                successful_count=successful_count,
                total_tasks=len(tasks),
                duration=(datetime.utcnow() - collection_start).total_seconds()
            )
            
        except Exception as e:
            self.stats['failed_collections'] += 1
            self.logger.error("数据收集失败", error=str(e))
    
    async def _collect_exchange_symbol_data(
        self, 
        exchange: Exchange, 
        symbol: str
    ) -> Optional[NormalizedMarketLongShortRatio]:
        """收集特定交易所和交易对的市场多空仓人数比数据"""
        try:
            client = self.clients.get(exchange)
            if not client:
                self.logger.warning("交易所客户端未找到", exchange=exchange.value)
                return None
            
            if exchange == Exchange.BINANCE:
                return await self._collect_binance_data(client, symbol)
            elif exchange == Exchange.OKX:
                return await self._collect_okx_data(client, symbol)
            else:
                self.logger.warning("不支持的交易所", exchange=exchange.value)
                return None
                
        except Exception as e:
            self.logger.error(
                "收集交易所数据失败",
                exchange=exchange.value,
                symbol=symbol,
                error=str(e)
            )
            return None
    
    async def _collect_binance_data(
        self, 
        client: ExchangeRestClient, 
        symbol: str
    ) -> Optional[NormalizedMarketLongShortRatio]:
        """收集Binance市场多空仓人数比数据"""
        try:
            # 转换交易对格式：BTC-USDT -> BTCUSDT
            binance_symbol = symbol.replace('-', '')
            
            # 获取多空账户数比 (Long-Short-Ratio)
            params = {
                'symbol': binance_symbol,
                'period': '5m',
                'limit': 1
            }
            
            response = await client.get(
                '/futures/data/topLongShortAccountRatio',
                params=params
            )
            
            if not response or not isinstance(response, list) or len(response) == 0:
                self.logger.warning("Binance返回空数据", symbol=symbol)
                return None
            
            data = response[0]  # 取最新的数据
            
            # 标准化数据
            normalized_data = NormalizedMarketLongShortRatio(
                exchange_name="binance",
                symbol_name=symbol,
                long_short_ratio=Decimal(str(data.get('longShortRatio', '0'))),
                long_account_ratio=Decimal(str(data.get('longAccount', '0'))),
                short_account_ratio=Decimal(str(data.get('shortAccount', '0'))),
                data_type="account",
                period="5m",
                instrument_type="futures",
                timestamp=datetime.utcfromtimestamp(int(data['timestamp']) / 1000),
                raw_data=data
            )
            
            self.logger.debug(
                "Binance市场多空仓人数比数据收集成功",
                symbol=symbol,
                long_short_ratio=str(normalized_data.long_short_ratio)
            )
            
            return normalized_data
            
        except Exception as e:
            self.logger.error("收集Binance数据失败", symbol=symbol, error=str(e))
            return None
    
    async def _collect_okx_data(
        self, 
        client: ExchangeRestClient, 
        symbol: str
    ) -> Optional[NormalizedMarketLongShortRatio]:
        """收集OKX市场多空仓人数比数据"""
        try:
            # 转换交易对格式：BTC-USDT -> BTC-USDT-SWAP
            okx_symbol = f"{symbol}-SWAP"
            
            # 获取合约多空持仓人数比
            params = {
                'instId': okx_symbol,
                'period': '5m',
                'limit': 1
            }
            
            response = await client.get(
                '/api/v5/rubik/stat/contracts/long-short-account-ratio-contract',
                params=params
            )
            
            if (not response or 
                response.get('code') != '0' or 
                not response.get('data') or 
                len(response['data']) == 0):
                self.logger.warning("OKX返回空数据或错误", symbol=symbol, response=response)
                return None
            
            data_point = response['data'][0]  # 取最新的数据
            
            # OKX返回格式：[timestamp, longShortAccountRatio]
            timestamp_ms = int(data_point[0])
            long_short_ratio = Decimal(str(data_point[1]))
            
            # 计算多空账户比例（假设总和为1）
            # 如果多空比为1.5，则多仓账户比例约为0.6，空仓账户比例约为0.4
            total_ratio = long_short_ratio + Decimal('1')
            long_account_ratio = long_short_ratio / total_ratio
            short_account_ratio = Decimal('1') / total_ratio
            
            # 标准化数据
            normalized_data = NormalizedMarketLongShortRatio(
                exchange_name="okx",
                symbol_name=symbol,
                long_short_ratio=long_short_ratio,
                long_account_ratio=long_account_ratio,
                short_account_ratio=short_account_ratio,
                data_type="account",
                period="5m",
                instrument_type="swap",
                timestamp=datetime.utcfromtimestamp(timestamp_ms / 1000),
                raw_data={'timestamp': timestamp_ms, 'longShortAccountRatio': str(long_short_ratio)}
            )
            
            self.logger.debug(
                "OKX市场多空仓人数比数据收集成功",
                symbol=symbol,
                long_short_ratio=str(normalized_data.long_short_ratio)
            )
            
            return normalized_data
            
        except Exception as e:
            self.logger.error("收集OKX数据失败", symbol=symbol, error=str(e))
            return None
    
    def register_callback(self, callback: Callable[[NormalizedMarketLongShortRatio], None]):
        """注册数据回调函数"""
        self.callbacks.append(callback)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'is_running': self.is_running,
            'symbols': self.symbols,
            'collection_interval': self.collection_interval,
            'total_collections': self.stats['total_collections'],
            'successful_collections': self.stats['successful_collections'],
            'failed_collections': self.stats['failed_collections'],
            'success_rate': (
                self.stats['successful_collections'] / self.stats['total_collections'] * 100
                if self.stats['total_collections'] > 0 else 0
            ),
            'data_points_collected': self.stats['data_points_collected'],
            'last_collection_time': (
                self.stats['last_collection_time'].isoformat()
                if self.stats['last_collection_time'] else None
            ),
            'exchanges': list(self.clients.keys()),
            'rest_clients': self.rest_client_manager.get_all_stats()
        }
    
    async def collect_once(self) -> List[NormalizedMarketLongShortRatio]:
        """手动触发一次数据收集（用于测试）"""
        results = []
        
        for exchange in [Exchange.BINANCE, Exchange.OKX]:
            for symbol in self.symbols:
                try:
                    data = await self._collect_exchange_symbol_data(exchange, symbol)
                    if data:
                        results.append(data)
                except Exception as e:
                    self.logger.error(
                        "手动收集数据失败",
                        exchange=exchange.value,
                        symbol=symbol,
                        error=str(e)
                    )
        
        return results