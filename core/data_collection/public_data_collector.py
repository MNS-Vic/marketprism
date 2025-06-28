"""
MarketPrism 公开数据收集器
使用公开API端点收集市场数据，无需API密钥
"""

import asyncio
import aiohttp
import websockets
import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Callable
import structlog
from dataclasses import dataclass
import yaml
from pathlib import Path

logger = structlog.get_logger(__name__)

@dataclass
class DataSourceConfig:
    """数据源配置"""
    name: str
    enabled: bool
    base_url: str
    websocket_url: str
    endpoints: Dict[str, str]
    symbols: List[str]
    rate_limits: Dict[str, int]

class PublicDataCollector:
    """公开数据收集器"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or "config/public_data_sources.yaml"
        self.config = self._load_config()
        self.data_sources = self._parse_data_sources()
        self.session: Optional[aiohttp.ClientSession] = None
        self.websocket_connections: Dict[str, Any] = {}
        self.is_running = False
        self.data_callbacks: List[Callable] = []
        
        # 统计信息
        self.stats = {
            'rest_requests': 0,
            'websocket_messages': 0,
            'errors': 0,
            'last_update': None
        }
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            config_file = Path(self.config_path)
            if not config_file.exists():
                logger.warning(f"配置文件不存在: {self.config_path}")
                return {}
                
            with open(config_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return {}
    
    def _parse_data_sources(self) -> Dict[str, DataSourceConfig]:
        """解析数据源配置"""
        sources = {}
        data_sources_config = self.config.get('data_sources', {})
        
        for name, config in data_sources_config.items():
            if config.get('enabled', False):
                sources[name] = DataSourceConfig(
                    name=config.get('name', name),
                    enabled=config.get('enabled', False),
                    base_url=config.get('base_url', ''),
                    websocket_url=config.get('websocket_url', ''),
                    endpoints=config.get('endpoints', {}),
                    symbols=config.get('symbols', []),
                    rate_limits=config.get('rate_limits', {})
                )
        
        logger.info(f"已配置 {len(sources)} 个数据源", sources=list(sources.keys()))
        return sources
    
    def add_data_callback(self, callback: Callable[[str, str, Dict[str, Any]], None]):
        """添加数据回调函数"""
        self.data_callbacks.append(callback)
    
    async def start(self):
        """启动数据收集器"""
        if self.is_running:
            logger.warning("数据收集器已在运行")
            return
        
        logger.info("启动公开数据收集器...")
        self.is_running = True
        
        # 创建HTTP会话
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={'User-Agent': 'MarketPrism/1.0'}
        )
        
        # 启动数据收集任务
        tasks = []
        
        # REST API数据收集
        for source_name, source_config in self.data_sources.items():
            if source_config.enabled:
                task = asyncio.create_task(
                    self._collect_rest_data(source_name, source_config)
                )
                tasks.append(task)
                
                # WebSocket数据收集
                ws_task = asyncio.create_task(
                    self._collect_websocket_data(source_name, source_config)
                )
                tasks.append(ws_task)
        
        logger.info(f"启动了 {len(tasks)} 个数据收集任务")
        
        # 等待所有任务完成（实际上会一直运行）
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"数据收集任务异常: {e}")
    
    async def stop(self):
        """停止数据收集器"""
        logger.info("停止数据收集器...")
        self.is_running = False
        
        # 关闭WebSocket连接
        for ws in self.websocket_connections.values():
            if ws and not ws.closed:
                await ws.close()
        
        # 关闭HTTP会话
        if self.session:
            await self.session.close()
        
        logger.info("数据收集器已停止")
    
    async def _collect_rest_data(self, source_name: str, source_config: DataSourceConfig):
        """收集REST API数据"""
        logger.info(f"启动 {source_name} REST数据收集")
        
        while self.is_running:
            try:
                # 收集行情数据
                await self._fetch_tickers(source_name, source_config)
                
                # 收集订单簿数据
                await self._fetch_orderbooks(source_name, source_config)
                
                # 等待下一次收集
                interval = self.config.get('collection', {}).get('intervals', {}).get('ticker_rest_seconds', 30)
                await asyncio.sleep(interval)
                
            except Exception as e:
                logger.error(f"{source_name} REST数据收集异常: {e}")
                self.stats['errors'] += 1
                await asyncio.sleep(5)  # 错误后短暂等待
    
    async def _fetch_tickers(self, source_name: str, source_config: DataSourceConfig):
        """获取行情数据"""
        if source_name == "binance":
            await self._fetch_binance_tickers(source_config)
        elif source_name == "okx":
            await self._fetch_okx_tickers(source_config)
        elif source_name == "coinbase":
            await self._fetch_coinbase_tickers(source_config)
    
    async def _fetch_binance_tickers(self, config: DataSourceConfig):
        """获取Binance行情数据"""
        try:
            url = f"{config.base_url}/api/v3/ticker/24hr"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    self.stats['rest_requests'] += 1
                    
                    for ticker in data:
                        if ticker['symbol'] in config.symbols:
                            processed_data = {
                                'timestamp': datetime.now(timezone.utc),
                                'symbol': ticker['symbol'],
                                'exchange': 'binance',
                                'last_price': float(ticker['lastPrice']),
                                'volume_24h': float(ticker['volume']),
                                'price_change_24h': float(ticker['priceChangePercent']),
                                'high_24h': float(ticker['highPrice']),
                                'low_24h': float(ticker['lowPrice'])
                            }
                            
                            # 调用数据回调
                            for callback in self.data_callbacks:
                                try:
                                    await callback('ticker', 'binance', processed_data)
                                except Exception as e:
                                    logger.error(f"数据回调异常: {e}")
                    
                    self.stats['last_update'] = datetime.now(timezone.utc)
                    logger.debug(f"Binance行情数据收集成功，{len(data)}个交易对")
                    
        except Exception as e:
            logger.error(f"Binance行情数据收集失败: {e}")
            self.stats['errors'] += 1

    async def _fetch_okx_tickers(self, config: DataSourceConfig):
        """获取OKX行情数据"""
        try:
            url = f"{config.base_url}/api/v5/market/tickers?instType=SPOT"
            async with self.session.get(url) as response:
                if response.status == 200:
                    result = await response.json()
                    data = result.get('data', [])
                    self.stats['rest_requests'] += 1

                    for ticker in data:
                        if ticker['instId'] in config.symbols:
                            processed_data = {
                                'timestamp': datetime.now(timezone.utc),
                                'symbol': ticker['instId'],
                                'exchange': 'okx',
                                'last_price': float(ticker['last']),
                                'volume_24h': float(ticker['vol24h']),
                                'price_change_24h': float(ticker['chgUtc']),
                                'high_24h': float(ticker['high24h']),
                                'low_24h': float(ticker['low24h'])
                            }

                            # 调用数据回调
                            for callback in self.data_callbacks:
                                try:
                                    await callback('ticker', 'okx', processed_data)
                                except Exception as e:
                                    logger.error(f"数据回调异常: {e}")

                    self.stats['last_update'] = datetime.now(timezone.utc)
                    logger.debug(f"OKX行情数据收集成功，{len(data)}个交易对")

        except Exception as e:
            logger.error(f"OKX行情数据收集失败: {e}")
            self.stats['errors'] += 1

    async def _fetch_coinbase_tickers(self, config: DataSourceConfig):
        """获取Coinbase行情数据"""
        try:
            for symbol in config.symbols:
                url = f"{config.base_url}/products/{symbol}/ticker"
                async with self.session.get(url) as response:
                    if response.status == 200:
                        ticker = await response.json()
                        self.stats['rest_requests'] += 1

                        processed_data = {
                            'timestamp': datetime.now(timezone.utc),
                            'symbol': symbol,
                            'exchange': 'coinbase',
                            'last_price': float(ticker['price']),
                            'volume_24h': float(ticker['volume']),
                            'price_change_24h': 0.0,  # Coinbase不直接提供24h变化
                            'high_24h': 0.0,
                            'low_24h': 0.0
                        }

                        # 调用数据回调
                        for callback in self.data_callbacks:
                            try:
                                await callback('ticker', 'coinbase', processed_data)
                            except Exception as e:
                                logger.error(f"数据回调异常: {e}")

                # 避免请求过于频繁
                await asyncio.sleep(0.1)

            self.stats['last_update'] = datetime.now(timezone.utc)
            logger.debug(f"Coinbase行情数据收集成功")

        except Exception as e:
            logger.error(f"Coinbase行情数据收集失败: {e}")
            self.stats['errors'] += 1

    async def _fetch_orderbooks(self, source_name: str, source_config: DataSourceConfig):
        """获取订单簿数据"""
        # 为了避免过于频繁的请求，只收集主要交易对的订单簿
        main_symbols = source_config.symbols[:3]  # 只收集前3个交易对

        for symbol in main_symbols:
            try:
                if source_name == "binance":
                    await self._fetch_binance_orderbook(source_config, symbol)
                elif source_name == "okx":
                    await self._fetch_okx_orderbook(source_config, symbol)
                elif source_name == "coinbase":
                    await self._fetch_coinbase_orderbook(source_config, symbol)

                # 避免请求过于频繁
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"{source_name} {symbol} 订单簿收集失败: {e}")
                self.stats['errors'] += 1

    async def _fetch_binance_orderbook(self, config: DataSourceConfig, symbol: str):
        """获取Binance订单簿"""
        try:
            url = f"{config.base_url}/api/v3/depth?symbol={symbol}&limit=20"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    self.stats['rest_requests'] += 1

                    processed_data = {
                        'timestamp': datetime.now(timezone.utc),
                        'symbol': symbol,
                        'exchange': 'binance',
                        'bids': [[float(bid[0]), float(bid[1])] for bid in data['bids'][:10]],
                        'asks': [[float(ask[0]), float(ask[1])] for ask in data['asks'][:10]]
                    }

                    # 调用数据回调
                    for callback in self.data_callbacks:
                        try:
                            await callback('orderbook', 'binance', processed_data)
                        except Exception as e:
                            logger.error(f"数据回调异常: {e}")

        except Exception as e:
            logger.error(f"Binance {symbol} 订单簿收集失败: {e}")

    async def _collect_websocket_data(self, source_name: str, source_config: DataSourceConfig):
        """收集WebSocket数据"""
        logger.info(f"启动 {source_name} WebSocket数据收集")

        while self.is_running:
            try:
                if source_name == "binance":
                    await self._connect_binance_websocket(source_config)
                elif source_name == "okx":
                    await self._connect_okx_websocket(source_config)
                # Coinbase WebSocket实现较复杂，暂时跳过

            except Exception as e:
                logger.error(f"{source_name} WebSocket连接异常: {e}")
                self.stats['errors'] += 1

            # 重连等待
            if self.is_running:
                await asyncio.sleep(30)

    async def _connect_binance_websocket(self, config: DataSourceConfig):
        """连接Binance WebSocket"""
        # 构建流URL - 订阅所有配置的交易对的ticker流
        streams = [f"{symbol.lower()}@ticker" for symbol in config.symbols[:5]]  # 限制5个交易对
        stream_url = f"{config.websocket_url}/ws/{'/'.join(streams)}"

        try:
            async with websockets.connect(stream_url) as websocket:
                logger.info(f"Binance WebSocket已连接: {len(streams)}个流")
                self.websocket_connections['binance'] = websocket

                async for message in websocket:
                    if not self.is_running:
                        break

                    try:
                        data = json.loads(message)
                        self.stats['websocket_messages'] += 1

                        # 处理ticker数据
                        if 'e' in data and data['e'] == '24hrTicker':
                            processed_data = {
                                'timestamp': datetime.now(timezone.utc),
                                'symbol': data['s'],
                                'exchange': 'binance',
                                'last_price': float(data['c']),
                                'volume_24h': float(data['v']),
                                'price_change_24h': float(data['P']),
                                'high_24h': float(data['h']),
                                'low_24h': float(data['l'])
                            }

                            # 调用数据回调
                            for callback in self.data_callbacks:
                                try:
                                    await callback('ticker', 'binance', processed_data)
                                except Exception as e:
                                    logger.error(f"WebSocket数据回调异常: {e}")

                    except json.JSONDecodeError:
                        logger.warning("WebSocket消息JSON解析失败")
                    except Exception as e:
                        logger.error(f"WebSocket消息处理异常: {e}")

        except Exception as e:
            logger.error(f"Binance WebSocket连接失败: {e}")

        finally:
            if 'binance' in self.websocket_connections:
                del self.websocket_connections['binance']

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'rest_requests': self.stats['rest_requests'],
            'websocket_messages': self.stats['websocket_messages'],
            'errors': self.stats['errors'],
            'last_update': self.stats['last_update'].isoformat() if self.stats['last_update'] else None,
            'active_sources': len(self.data_sources),
            'websocket_connections': len(self.websocket_connections)
        }
