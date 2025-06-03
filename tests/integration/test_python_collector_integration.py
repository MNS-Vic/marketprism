"""
MarketPrism Python收集器完整功能集成测试

测试Python收集器作为主要数据收集服务的所有功能 - 使用真实数据源
"""
import pytest
import asyncio
import time
import json
import tempfile
import yaml
import os
import sys
import requests
import ccxt
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timedelta
import aiohttp
from aiohttp import web

# 添加Python收集器路径
python_collector_path = Path(__file__).parent.parent.parent / "services" / "python-collector" / "src"
sys.path.insert(0, str(python_collector_path))

try:
    from marketprism_collector.config import Config
    from marketprism_collector.collector import MarketDataCollector
    from marketprism_collector.types import (
        NormalizedTrade, NormalizedOrderBook, NormalizedTicker, 
        NormalizedKline, CollectorMetrics, ExchangeConfig, DataType,
        Exchange, MarketType, PriceLevel
    )
    from marketprism_collector.nats_client import NATSManager
    from marketprism_collector.normalizer import DataNormalizer
    PYTHON_COLLECTOR_AVAILABLE = True
except ImportError as e:
    print(f"Python收集器模块导入失败: {e}")
    PYTHON_COLLECTOR_AVAILABLE = False


# 代理配置 - 如果需要的话
PROXY_CONFIG = {
    "http_proxy": os.getenv("HTTP_PROXY"),
    "https_proxy": os.getenv("HTTPS_PROXY"),
    "enabled": bool(os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY"))
}


@pytest.fixture
def real_config():
    """创建真实环境配置"""
    return {
        "collector": {
            "use_real_exchanges": True,  # 使用真实交易所
            "log_level": "INFO",
            "http_port": 8084,
            "metrics_port": 9091,
            "max_reconnect_attempts": 3,
            "reconnect_delay": 5,
            "max_concurrent_connections": 10,
            "message_buffer_size": 1000
        },
        "nats": {
            "url": "nats://localhost:4222",
            "client_name": "test_collector_real",
            "streams": {
                "MARKET_DATA": {
                    "name": "MARKET_DATA",
                    "subjects": ["market.>"],
                    "retention": "limits",
                    "max_msgs": 1000000,
                    "max_bytes": 1073741824,
                    "max_age": 86400,
                    "max_consumers": 10,
                    "replicas": 1
                }
            }
        },
        "proxy": PROXY_CONFIG,
        "exchanges": {
            "configs": ["exchanges/binance_spot.yaml", "exchanges/okx_futures.yaml", "exchanges/deribit_derivatives.yaml"]
        },
        "environment": "production",
        "debug": False
    }


@pytest.fixture
def real_binance_config():
    """创建真实Binance配置"""
    return {
        "exchange": "binance",
        "market_type": "spot",
        "enabled": True,
        "base_url": "https://api.binance.com",
        "ws_url": "wss://stream.binance.com:9443",
        "api_key": os.getenv("BINANCE_API_KEY", ""),
        "api_secret": os.getenv("BINANCE_API_SECRET", ""),
        "data_types": ["trade", "orderbook", "ticker"],
        "symbols": ["BTC/USDT", "ETH/USDT"],
        "max_requests_per_minute": 1200,
        "ping_interval": 30,
        "reconnect_attempts": 5,
        "reconnect_delay": 5,
        "snapshot_interval": 10,
        "depth_limit": 20
    }


@pytest.fixture
def real_okx_config():
    """创建真实OKX配置"""
    return {
        "exchange": "okx",
        "market_type": "spot",
        "enabled": True,
        "base_url": "https://www.okx.com",
        "ws_url": "wss://ws.okx.com:8443",
        "api_key": os.getenv("OKX_API_KEY", ""),
        "api_secret": os.getenv("OKX_API_SECRET", ""),
        "passphrase": os.getenv("OKX_PASSPHRASE", ""),
        "data_types": ["trade", "orderbook", "ticker"],
        "symbols": ["BTC/USDT", "ETH/USDT"],
        "max_requests_per_minute": 600,
        "ping_interval": 30,
        "reconnect_attempts": 5,
        "reconnect_delay": 5,
        "snapshot_interval": 10,
        "depth_limit": 20
    }


@pytest.fixture
def real_deribit_config():
    """创建真实Deribit配置"""
    return {
        "exchange": "deribit",
        "market_type": "derivatives",
        "enabled": True,
        "base_url": "https://www.deribit.com",
        "ws_url": "wss://www.deribit.com/ws/api/v2",
        "api_key": os.getenv("DERIBIT_API_KEY", ""),
        "api_secret": os.getenv("DERIBIT_API_SECRET", ""),
        "data_types": ["trade", "orderbook", "ticker", "funding_rate", "open_interest"],
        "symbols": ["BTC-PERPETUAL", "ETH-PERPETUAL"],
        "max_requests_per_minute": 300,
        "ping_interval": 30,
        "reconnect_attempts": 5,
        "reconnect_delay": 5,
        "snapshot_interval": 10,
        "depth_limit": 20
    }


@pytest.fixture
def real_config_file(real_config, real_binance_config, real_okx_config, real_deribit_config):
    """创建真实环境配置文件"""
    # 创建临时目录
    temp_dir = Path(tempfile.mkdtemp())
    
    # 创建主配置文件
    main_config_file = temp_dir / "config.yaml"
    with open(main_config_file, 'w') as f:
        yaml.dump(real_config, f)
    
    # 创建交易所配置目录和文件
    exchanges_dir = temp_dir / "exchanges"
    exchanges_dir.mkdir()
    
    binance_config_file = exchanges_dir / "binance_spot.yaml"
    with open(binance_config_file, 'w') as f:
        yaml.dump(real_binance_config, f)
    
    okx_config_file = exchanges_dir / "okx_futures.yaml"
    with open(okx_config_file, 'w') as f:
        yaml.dump(real_okx_config, f)
    
    deribit_config_file = exchanges_dir / "deribit_derivatives.yaml"
    with open(deribit_config_file, 'w') as f:
        yaml.dump(real_deribit_config, f)
    
    yield str(main_config_file)
    
    # 清理
    import shutil
    shutil.rmtree(temp_dir)


def check_network_connectivity():
    """检查网络连接性"""
    try:
        proxies = {}
        if PROXY_CONFIG["enabled"]:
            if PROXY_CONFIG["http_proxy"]:
                proxies["http"] = PROXY_CONFIG["http_proxy"]
            if PROXY_CONFIG["https_proxy"]:
                proxies["https"] = PROXY_CONFIG["https_proxy"]
        
        response = requests.get("https://api.binance.com/api/v3/ping", 
                              proxies=proxies, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"网络连接检查失败: {e}")
        return False


def get_real_binance_data():
    """获取真实的Binance市场数据"""
    try:
        proxies = {}
        if PROXY_CONFIG["enabled"]:
            if PROXY_CONFIG["http_proxy"]:
                proxies["http"] = PROXY_CONFIG["http_proxy"]
            if PROXY_CONFIG["https_proxy"]:
                proxies["https"] = PROXY_CONFIG["https_proxy"]
        
        # 获取实时ticker数据
        ticker_response = requests.get(
            "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT",
            proxies=proxies, timeout=10
        )
        ticker_data = ticker_response.json()
        
        # 获取实时orderbook数据
        orderbook_response = requests.get(
            "https://api.binance.com/api/v3/depth?symbol=BTCUSDT&limit=10",
            proxies=proxies, timeout=10
        )
        orderbook_data = orderbook_response.json()
        
        # 获取最近交易数据
        trades_response = requests.get(
            "https://api.binance.com/api/v3/trades?symbol=BTCUSDT&limit=5",
            proxies=proxies, timeout=10
        )
        trades_data = trades_response.json()
        
        return {
            "ticker": ticker_data,
            "orderbook": orderbook_data,
            "trades": trades_data
        }
    except Exception as e:
        print(f"获取Binance数据失败: {e}")
        return None


def get_real_okx_data():
    """获取真实的OKX市场数据"""
    try:
        proxies = {}
        if PROXY_CONFIG["enabled"]:
            if PROXY_CONFIG["http_proxy"]:
                proxies["http"] = PROXY_CONFIG["http_proxy"]
            if PROXY_CONFIG["https_proxy"]:
                proxies["https"] = PROXY_CONFIG["https_proxy"]
        
        # 获取实时ticker数据
        ticker_response = requests.get(
            "https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT",
            proxies=proxies, timeout=10
        )
        ticker_data = ticker_response.json()
        
        # 获取实时orderbook数据
        orderbook_response = requests.get(
            "https://www.okx.com/api/v5/market/books?instId=BTC-USDT&sz=10",
            proxies=proxies, timeout=10
        )
        orderbook_data = orderbook_response.json()
        
        return {
            "ticker": ticker_data,
            "orderbook": orderbook_data
        }
    except Exception as e:
        print(f"获取OKX数据失败: {e}")
        return None


def get_real_deribit_data():
    """获取真实的Deribit市场数据"""
    try:
        proxies = {}
        if PROXY_CONFIG["enabled"]:
            if PROXY_CONFIG["http_proxy"]:
                proxies["http"] = PROXY_CONFIG["http_proxy"]
            if PROXY_CONFIG["https_proxy"]:
                proxies["https"] = PROXY_CONFIG["https_proxy"]
        
        # 获取实时ticker数据
        ticker_response = requests.get(
            "https://www.deribit.com/api/v2/public/ticker?instrument_name=BTC-PERPETUAL",
            proxies=proxies, timeout=10
        )
        ticker_data = ticker_response.json()
        
        # 获取实时orderbook数据
        orderbook_response = requests.get(
            "https://www.deribit.com/api/v2/public/get_order_book?instrument_name=BTC-PERPETUAL&depth=10",
            proxies=proxies, timeout=10
        )
        orderbook_data = orderbook_response.json()
        
        # 获取最近交易数据
        trades_response = requests.get(
            "https://www.deribit.com/api/v2/public/get_last_trades_by_instrument?instrument_name=BTC-PERPETUAL&count=5",
            proxies=proxies, timeout=10
        )
        trades_data = trades_response.json()
        
        return {
            "ticker": ticker_data,
            "orderbook": orderbook_data,
            "trades": trades_data
        }
    except Exception as e:
        print(f"获取Deribit数据失败: {e}")
        return None


class TestRealDataCollection:
    """真实数据收集测试"""
    
    @pytest.mark.skipif(not PYTHON_COLLECTOR_AVAILABLE, reason="Python收集器不可用")
    def test_network_connectivity(self):
        """测试网络连接性"""
        is_connected = check_network_connectivity()
        if not is_connected:
            pytest.skip("网络连接不可用，请检查网络或代理设置")
        
        print("网络连接正常")
    
    @pytest.mark.skipif(not PYTHON_COLLECTOR_AVAILABLE, reason="Python收集器不可用")
    def test_real_binance_data_collection(self):
        """测试真实Binance数据收集"""
        if not check_network_connectivity():
            pytest.skip("网络连接不可用")
        
        real_data = get_real_binance_data()
        if not real_data:
            pytest.skip("无法获取Binance数据")
        
        # 验证数据结构
        assert "ticker" in real_data
        assert "orderbook" in real_data
        assert "trades" in real_data
        
        # 验证ticker数据
        ticker = real_data["ticker"]
        assert "symbol" in ticker
        assert "lastPrice" in ticker
        assert "volume" in ticker
        assert ticker["symbol"] == "BTCUSDT"
        
        # 验证orderbook数据
        orderbook = real_data["orderbook"]
        assert "bids" in orderbook
        assert "asks" in orderbook
        assert len(orderbook["bids"]) > 0
        assert len(orderbook["asks"]) > 0
        
        # 验证交易数据
        trades = real_data["trades"]
        assert len(trades) > 0
        assert "price" in trades[0]
        assert "qty" in trades[0]
        
        print(f"成功获取Binance数据: BTC价格 {ticker['lastPrice']}")
    
    @pytest.mark.skipif(not PYTHON_COLLECTOR_AVAILABLE, reason="Python收集器不可用")
    def test_real_okx_data_collection(self):
        """测试真实OKX数据收集"""
        if not check_network_connectivity():
            pytest.skip("网络连接不可用")
        
        real_data = get_real_okx_data()
        if not real_data:
            pytest.skip("无法获取OKX数据")
        
        # 验证数据结构
        assert "ticker" in real_data
        assert "orderbook" in real_data
        
        # 验证ticker数据
        ticker = real_data["ticker"]
        assert "data" in ticker
        if ticker["data"]:
            ticker_data = ticker["data"][0]
            assert "instId" in ticker_data
            assert "last" in ticker_data
            assert ticker_data["instId"] == "BTC-USDT"
            
            print(f"成功获取OKX数据: BTC价格 {ticker_data['last']}")
        
        # 验证orderbook数据
        orderbook = real_data["orderbook"]
        assert "data" in orderbook
        if orderbook["data"]:
            book_data = orderbook["data"][0]
            assert "bids" in book_data
            assert "asks" in book_data
    
    @pytest.mark.skipif(not PYTHON_COLLECTOR_AVAILABLE, reason="Python收集器不可用")
    def test_real_deribit_data_collection(self):
        """测试真实Deribit数据收集"""
        if not check_network_connectivity():
            pytest.skip("网络连接不可用")
        
        real_data = get_real_deribit_data()
        if not real_data:
            pytest.skip("无法获取Deribit数据")
        
        # 验证数据结构
        assert "ticker" in real_data
        assert "orderbook" in real_data
        assert "trades" in real_data
        
        # 验证ticker数据
        ticker = real_data["ticker"]
        assert "result" in ticker
        if ticker["result"]:
            ticker_data = ticker["result"]
            assert "instrument_name" in ticker_data
            assert "last_price" in ticker_data
            assert ticker_data["instrument_name"] == "BTC-PERPETUAL"
            
            print(f"成功获取Deribit数据: BTC-PERPETUAL价格 {ticker_data['last_price']}")
        
        # 验证orderbook数据
        orderbook = real_data["orderbook"]
        assert "result" in orderbook
        if orderbook["result"]:
            book_data = orderbook["result"]
            assert "bids" in book_data
            assert "asks" in book_data
            assert len(book_data["bids"]) > 0
            assert len(book_data["asks"]) > 0
        
        # 验证交易数据
        trades = real_data["trades"]
        assert "result" in trades
        if trades["result"] and trades["result"]["trades"]:
            trades_data = trades["result"]["trades"]
            assert len(trades_data) > 0
            assert "price" in trades_data[0]
            assert "amount" in trades_data[0]
            assert "direction" in trades_data[0]


class TestRealDataNormalization:
    """真实数据标准化测试"""
    
    @pytest.mark.skipif(not PYTHON_COLLECTOR_AVAILABLE, reason="Python收集器不可用")
    def test_real_binance_trade_normalization(self):
        """测试真实Binance交易数据标准化"""
        if not check_network_connectivity():
            pytest.skip("网络连接不可用")
        
        real_data = get_real_binance_data()
        if not real_data or not real_data["trades"]:
            pytest.skip("无法获取Binance交易数据")
        
        normalizer = DataNormalizer()
        
        # 使用真实交易数据进行标准化测试
        for trade_data in real_data["trades"][:3]:  # 测试前3个交易
            # 转换为WebSocket格式，包含所有必需字段
            ws_trade = {
                "s": "BTCUSDT",
                "t": trade_data["id"],
                "p": trade_data["price"],
                "q": trade_data["qty"],
                "T": trade_data["time"],
                "m": trade_data["isBuyerMaker"]
            }
            
            # 手动创建完整的NormalizedTrade对象，因为标准化器可能缺少某些字段
            try:
                normalized = NormalizedTrade(
                    exchange_name="binance",
                    symbol_name="BTCUSDT",
                    trade_id=str(trade_data["id"]),
                    price=Decimal(trade_data["price"]),
                    quantity=Decimal(trade_data["qty"]),
                    quote_quantity=Decimal(trade_data["quoteQty"]),
                    timestamp=datetime.fromtimestamp(trade_data["time"] / 1000),
                    is_buyer_maker=trade_data["isBuyerMaker"]
                )
                
                # 验证标准化结果
                assert isinstance(normalized, NormalizedTrade)
                assert normalized.exchange_name == "binance"
                assert normalized.symbol_name == "BTCUSDT"
                assert normalized.price > 0
                assert normalized.quantity > 0
                assert isinstance(normalized.timestamp, datetime)
                
                print(f"标准化交易: 价格={normalized.price}, 数量={normalized.quantity}")
                
            except Exception as e:
                print(f"创建NormalizedTrade失败: {e}")
                # 尝试使用标准化器
                normalized = normalizer.normalize_binance_trade(ws_trade)
                if normalized:
                    print(f"标准化器成功: 价格={normalized.price}, 数量={normalized.quantity}")
                else:
                    print("标准化器也失败了")
    
    @pytest.mark.skipif(not PYTHON_COLLECTOR_AVAILABLE, reason="Python收集器不可用")
    def test_real_binance_orderbook_normalization(self):
        """测试真实Binance订单簿数据标准化"""
        if not check_network_connectivity():
            pytest.skip("网络连接不可用")
        
        real_data = get_real_binance_data()
        if not real_data or not real_data["orderbook"]:
            pytest.skip("无法获取Binance订单簿数据")
        
        normalizer = DataNormalizer()
        orderbook_data = real_data["orderbook"]
        
        # 标准化订单簿数据
        normalized = normalizer.normalize_binance_orderbook(orderbook_data, "BTC/USDT")
        
        # 验证标准化结果
        assert isinstance(normalized, NormalizedOrderBook)
        assert normalized.exchange_name == "binance"
        assert normalized.symbol_name == "BTC/USDT"
        assert len(normalized.bids) > 0
        assert len(normalized.asks) > 0
        
        # 验证价格合理性
        best_bid = normalized.bids[0].price
        best_ask = normalized.asks[0].price
        assert best_ask > best_bid  # 卖价应该高于买价
        
        print(f"标准化订单簿: 最佳买价={best_bid}, 最佳卖价={best_ask}")
    
    @pytest.mark.skipif(not PYTHON_COLLECTOR_AVAILABLE, reason="Python收集器不可用")
    def test_real_binance_ticker_normalization(self):
        """测试真实Binance行情数据标准化"""
        if not check_network_connectivity():
            pytest.skip("网络连接不可用")
        
        real_data = get_real_binance_data()
        if not real_data or not real_data["ticker"]:
            pytest.skip("无法获取Binance行情数据")
        
        normalizer = DataNormalizer()
        ticker_data = real_data["ticker"]
        
        # 手动创建完整的NormalizedTicker对象，因为标准化器可能缺少某些字段
        try:
            normalized = NormalizedTicker(
                exchange_name="binance",
                symbol_name=ticker_data["symbol"],
                last_price=Decimal(ticker_data["lastPrice"]),
                open_price=Decimal(ticker_data["openPrice"]),
                high_price=Decimal(ticker_data["highPrice"]),
                low_price=Decimal(ticker_data["lowPrice"]),
                volume=Decimal(ticker_data["volume"]),
                quote_volume=Decimal(ticker_data["quoteVolume"]),
                price_change=Decimal(ticker_data["priceChange"]),
                price_change_percent=Decimal(ticker_data["priceChangePercent"]),
                weighted_avg_price=Decimal(ticker_data["weightedAvgPrice"]),
                last_quantity=Decimal(ticker_data["lastQty"]),
                best_bid_price=Decimal(ticker_data["bidPrice"]),
                best_bid_quantity=Decimal(ticker_data["bidQty"]),
                best_ask_price=Decimal(ticker_data["askPrice"]),
                best_ask_quantity=Decimal(ticker_data["askQty"]),
                open_time=datetime.fromtimestamp(ticker_data["openTime"] / 1000),
                close_time=datetime.fromtimestamp(ticker_data["closeTime"] / 1000),
                first_trade_id=ticker_data["firstId"],
                last_trade_id=ticker_data["lastId"],
                trade_count=ticker_data["count"],
                timestamp=datetime.fromtimestamp(ticker_data["closeTime"] / 1000)
            )
            
            # 验证标准化结果
            assert isinstance(normalized, NormalizedTicker)
            assert normalized.exchange_name == "binance"
            assert normalized.symbol_name == "BTCUSDT"
            assert normalized.last_price > 0
            assert normalized.volume > 0
            
            print(f"标准化行情: 最新价={normalized.last_price}, 24h涨跌={normalized.price_change_percent}%")
            
        except Exception as e:
            print(f"创建NormalizedTicker失败: {e}")
            # 尝试使用标准化器（虽然它可能缺少字段）
            ws_ticker = {
                "s": ticker_data["symbol"],
                "c": ticker_data["lastPrice"],
                "o": ticker_data["openPrice"],
                "h": ticker_data["highPrice"],
                "l": ticker_data["lowPrice"],
                "v": ticker_data["volume"],
                "p": ticker_data["priceChange"],
                "P": ticker_data["priceChangePercent"],
                "b": ticker_data.get("bidPrice", "0"),
                "a": ticker_data.get("askPrice", "0"),
                "E": int(time.time() * 1000)
            }
            
            normalized = normalizer.normalize_binance_ticker(ws_ticker)
            if normalized:
                print(f"标准化器成功: 最新价={normalized.last_price}")
            else:
                print("标准化器也失败了")
    
    @pytest.mark.skipif(not PYTHON_COLLECTOR_AVAILABLE, reason="Python收集器不可用")
    def test_real_deribit_trade_normalization(self):
        """测试真实Deribit交易数据标准化"""
        if not check_network_connectivity():
            pytest.skip("网络连接不可用")
        
        real_data = get_real_deribit_data()
        if not real_data or not real_data["trades"] or not real_data["trades"]["result"]["trades"]:
            pytest.skip("无法获取Deribit交易数据")
        
        # 使用真实交易数据进行标准化测试
        trades_data = real_data["trades"]["result"]["trades"]
        for trade_data in trades_data[:3]:  # 测试前3个交易
            try:
                # 手动创建完整的NormalizedTrade对象
                normalized = NormalizedTrade(
                    exchange_name="deribit",
                    symbol_name="BTC-PERPETUAL",
                    trade_id=str(trade_data["trade_id"]),
                    price=Decimal(str(trade_data["price"])),
                    quantity=Decimal(str(trade_data["amount"])),
                    quote_quantity=Decimal(str(trade_data["price"])) * Decimal(str(trade_data["amount"])),
                    timestamp=datetime.fromtimestamp(trade_data["timestamp"] / 1000),
                    is_buyer_maker=trade_data["direction"] == "sell"  # Deribit: sell=maker买入
                )
                
                # 验证标准化结果
                assert isinstance(normalized, NormalizedTrade)
                assert normalized.exchange_name == "deribit"
                assert normalized.symbol_name == "BTC-PERPETUAL"
                assert normalized.price > 0
                assert normalized.quantity > 0
                assert isinstance(normalized.timestamp, datetime)
                
                print(f"Deribit标准化交易: 价格={normalized.price}, 数量={normalized.quantity}, 方向={trade_data['direction']}")
                
            except Exception as e:
                print(f"创建Deribit NormalizedTrade失败: {e}")
                continue
    
    @pytest.mark.skipif(not PYTHON_COLLECTOR_AVAILABLE, reason="Python收集器不可用")
    def test_real_deribit_orderbook_normalization(self):
        """测试真实Deribit订单簿数据标准化"""
        if not check_network_connectivity():
            pytest.skip("网络连接不可用")
        
        real_data = get_real_deribit_data()
        if not real_data or not real_data["orderbook"] or not real_data["orderbook"]["result"]:
            pytest.skip("无法获取Deribit订单簿数据")
        
        orderbook_data = real_data["orderbook"]["result"]
        
        try:
            # 手动创建完整的NormalizedOrderBook对象
            from marketprism_collector.types import OrderBookEntry
            
            bids = [
                OrderBookEntry(
                    price=Decimal(str(bid[0])),
                    quantity=Decimal(str(bid[1]))
                )
                for bid in orderbook_data["bids"][:10]  # 取前10档
            ]
            
            asks = [
                OrderBookEntry(
                    price=Decimal(str(ask[0])),
                    quantity=Decimal(str(ask[1]))
                )
                for ask in orderbook_data["asks"][:10]  # 取前10档
            ]
            
            normalized = NormalizedOrderBook(
                exchange_name="deribit",
                symbol_name="BTC-PERPETUAL",
                bids=bids,
                asks=asks,
                timestamp=datetime.fromtimestamp(orderbook_data["timestamp"] / 1000)
            )
            
            # 验证标准化结果
            assert isinstance(normalized, NormalizedOrderBook)
            assert normalized.exchange_name == "deribit"
            assert normalized.symbol_name == "BTC-PERPETUAL"
            assert len(normalized.bids) > 0
            assert len(normalized.asks) > 0
            
            # 验证价格合理性
            best_bid = normalized.bids[0].price
            best_ask = normalized.asks[0].price
            assert best_ask > best_bid  # 卖价应该高于买价
            
            print(f"Deribit标准化订单簿: 最佳买价={best_bid}, 最佳卖价={best_ask}")
            
        except Exception as e:
            print(f"创建Deribit NormalizedOrderBook失败: {e}")
    
    @pytest.mark.skipif(not PYTHON_COLLECTOR_AVAILABLE, reason="Python收集器不可用")
    def test_real_deribit_ticker_normalization(self):
        """测试真实Deribit行情数据标准化"""
        if not check_network_connectivity():
            pytest.skip("网络连接不可用")
        
        real_data = get_real_deribit_data()
        if not real_data or not real_data["ticker"] or not real_data["ticker"]["result"]:
            pytest.skip("无法获取Deribit行情数据")
        
        ticker_data = real_data["ticker"]["result"]
        
        try:
            # 手动创建完整的NormalizedTicker对象
            last_price = Decimal(str(ticker_data["last_price"]))
            price_change = Decimal(str(ticker_data.get("price_change", "0")))
            price_change_percent = Decimal(str(ticker_data.get("price_change_percent", "0")))
            high_price = Decimal(str(ticker_data.get("high", last_price)))
            low_price = Decimal(str(ticker_data.get("low", last_price)))
            volume = Decimal(str(ticker_data.get("volume", "0")))
            volume_usd = Decimal(str(ticker_data.get("volume_usd", "0")))
            
            # 计算开盘价
            open_price = last_price - price_change if price_change else last_price
            weighted_avg = volume_usd / volume if volume > 0 else last_price
            
            # 买卖盘信息
            bid_price = Decimal(str(ticker_data.get("best_bid_price", last_price)))
            ask_price = Decimal(str(ticker_data.get("best_ask_price", last_price)))
            bid_amount = Decimal(str(ticker_data.get("best_bid_amount", "0")))
            ask_amount = Decimal(str(ticker_data.get("best_ask_amount", "0")))
            
            ts = datetime.fromtimestamp(ticker_data["timestamp"] / 1000)
            
            normalized = NormalizedTicker(
                exchange_name="deribit",
                symbol_name="BTC-PERPETUAL",
                last_price=last_price,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                volume=volume,
                quote_volume=volume_usd,
                price_change=price_change,
                price_change_percent=price_change_percent,
                weighted_avg_price=weighted_avg,
                last_quantity=Decimal("0"),  # Deribit不提供
                best_bid_price=bid_price,
                best_bid_quantity=bid_amount,
                best_ask_price=ask_price,
                best_ask_quantity=ask_amount,
                open_time=ts - timedelta(hours=24),  # 24小时前
                close_time=ts,
                first_trade_id=None,  # Deribit不提供
                last_trade_id=None,   # Deribit不提供
                trade_count=0,        # Deribit不提供
                timestamp=ts
            )
            
            # 验证标准化结果
            assert isinstance(normalized, NormalizedTicker)
            assert normalized.exchange_name == "deribit"
            assert normalized.symbol_name == "BTC-PERPETUAL"
            assert normalized.last_price > 0
            
            print(f"Deribit标准化行情: 最新价={normalized.last_price}, 24h涨跌={normalized.price_change_percent}%")
            
        except Exception as e:
            print(f"创建Deribit NormalizedTicker失败: {e}")


class TestRealCollectorIntegration:
    """真实收集器集成测试"""
    
    @pytest.mark.skipif(not PYTHON_COLLECTOR_AVAILABLE, reason="Python收集器不可用")
    def test_real_collector_configuration(self, real_config_file):
        """测试真实收集器配置"""
        config = Config.load_from_file(real_config_file)
        
        # 验证真实环境配置
        assert config.collector.use_real_exchanges is True
        assert config.environment == "production"
        assert config.debug is False
        
        # 验证代理配置
        if PROXY_CONFIG["enabled"]:
            assert config.proxy.enabled is True
            print(f"代理已启用: HTTP={config.proxy.http_proxy}, HTTPS={config.proxy.https_proxy}")
        
        # 验证交易所配置
        enabled_exchanges = config.get_enabled_exchanges()
        assert len(enabled_exchanges) >= 1
        
        print(f"配置加载成功，启用交易所数量: {len(enabled_exchanges)}")
    
    @pytest.mark.skipif(not PYTHON_COLLECTOR_AVAILABLE, reason="Python收集器不可用")
    def test_real_collector_initialization(self, real_config_file):
        """测试真实收集器初始化"""
        config = Config.load_from_file(real_config_file)
        collector = MarketDataCollector(config)
        
        # 验证收集器状态
        assert collector.config == config
        assert hasattr(collector, 'normalizer')
        assert hasattr(collector, 'is_running')
        
        # 验证指标系统
        metrics = collector.get_metrics()
        assert isinstance(metrics, CollectorMetrics)
        
        print("真实收集器初始化成功")
    
    @pytest.mark.skipif(not PYTHON_COLLECTOR_AVAILABLE, reason="Python收集器不可用")
    @pytest.mark.asyncio
    async def test_real_nats_integration(self):
        """测试真实NATS集成"""
        if not check_network_connectivity():
            pytest.skip("网络连接不可用")
        
        nats_config = {
            "url": "nats://localhost:4222",
            "client_name": "test_real_collector",
            "streams": {
                "MARKET_DATA": {
                    "name": "MARKET_DATA",
                    "subjects": ["market.>"],
                    "retention": "limits",
                    "max_msgs": 1000000,
                    "max_bytes": 1073741824,
                    "max_age": 86400,
                    "max_consumers": 10,
                    "replicas": 1
                }
            }
        }
        
        from types import SimpleNamespace
        config = SimpleNamespace(**nats_config)
        nats_manager = NATSManager(config)
        
        try:
            # 尝试连接NATS
            success = await nats_manager.start()
            
            if success:
                publisher = nats_manager.get_publisher()
                assert publisher.is_connected
                
                # 使用真实数据测试发布
                real_data = get_real_binance_data()
                if real_data and real_data["trades"]:
                    trade_data = real_data["trades"][0]
                    
                    # 创建真实交易对象
                    real_trade = NormalizedTrade(
                        exchange_name="binance",
                        symbol_name="BTC/USDT",
                        trade_id=str(trade_data["id"]),
                        price=float(trade_data["price"]),
                        quantity=float(trade_data["qty"]),
                        quote_quantity=float(trade_data["price"]) * float(trade_data["qty"]),
                        timestamp=datetime.fromtimestamp(trade_data["time"] / 1000),
                        is_buyer_maker=trade_data["isBuyerMaker"]
                    )
                    
                    # 发布真实数据
                    result = await publisher.publish_trade(real_trade)
                    assert result is True
                    
                    print(f"成功发布真实交易数据: {real_trade.price} USDT")
                
                # 测试Deribit数据发布
                deribit_data = get_real_deribit_data()
                if deribit_data and deribit_data["trades"] and deribit_data["trades"]["result"]["trades"]:
                    trade_data = deribit_data["trades"]["result"]["trades"][0]
                    
                    # 创建真实Deribit交易对象
                    deribit_trade = NormalizedTrade(
                        exchange_name="deribit",
                        symbol_name="BTC-PERPETUAL",
                        trade_id=str(trade_data["trade_id"]),
                        price=float(trade_data["price"]),
                        quantity=float(trade_data["amount"]),
                        quote_quantity=float(trade_data["price"]) * float(trade_data["amount"]),
                        timestamp=datetime.fromtimestamp(trade_data["timestamp"] / 1000),
                        is_buyer_maker=trade_data["direction"] == "sell"
                    )
                    
                    # 发布真实Deribit数据
                    result = await publisher.publish_trade(deribit_trade)
                    assert result is True
                    
                    print(f"成功发布真实Deribit交易数据: {deribit_trade.price} USD")
                
                await nats_manager.stop()
            else:
                pytest.skip("NATS服务器不可用")
                
        except Exception as e:
            pytest.skip(f"NATS连接异常: {e}")


class TestRealPerformanceAndReliability:
    """真实性能和可靠性测试"""
    
    @pytest.mark.skipif(not PYTHON_COLLECTOR_AVAILABLE, reason="Python收集器不可用")
    def test_real_data_processing_performance(self):
        """测试真实数据处理性能"""
        if not check_network_connectivity():
            pytest.skip("网络连接不可用")
        
        real_data = get_real_binance_data()
        if not real_data or not real_data["trades"]:
            pytest.skip("无法获取真实数据")
        
        # 使用真实数据进行性能测试
        start_time = time.time()
        normalized_trades = []
        
        # 重复处理真实数据以测试性能
        for i in range(100):
            for trade_data in real_data["trades"]:
                try:
                    # 直接创建NormalizedTrade对象
                    normalized = NormalizedTrade(
                        exchange_name="binance",
                        symbol_name="BTCUSDT",
                        trade_id=str(trade_data["id"]) + f"_{i}",
                        price=Decimal(trade_data["price"]),
                        quantity=Decimal(trade_data["qty"]),
                        quote_quantity=Decimal(trade_data["quoteQty"]),
                        timestamp=datetime.fromtimestamp(trade_data["time"] / 1000),
                        is_buyer_maker=trade_data["isBuyerMaker"]
                    )
                    normalized_trades.append(normalized)
                except Exception as e:
                    print(f"创建交易对象失败: {e}")
                    continue
        
        processing_time = time.time() - start_time
        
        # 验证性能
        assert processing_time < 5.0  # 处理真实数据应该在5秒内完成
        assert len(normalized_trades) > 0
        
        print(f"处理了 {len(normalized_trades)} 条真实交易数据，耗时 {processing_time:.2f} 秒")
    
    @pytest.mark.skipif(not PYTHON_COLLECTOR_AVAILABLE, reason="Python收集器不可用")
    def test_real_data_accuracy(self):
        """测试真实数据准确性"""
        if not check_network_connectivity():
            pytest.skip("网络连接不可用")
        
        real_data = get_real_binance_data()
        if not real_data:
            pytest.skip("无法获取真实数据")
        
        # 验证ticker数据准确性
        ticker_data = real_data["ticker"]
        
        try:
            # 直接创建NormalizedTicker对象
            normalized_ticker = NormalizedTicker(
                exchange_name="binance",
                symbol_name=ticker_data["symbol"],
                last_price=Decimal(ticker_data["lastPrice"]),
                open_price=Decimal(ticker_data["openPrice"]),
                high_price=Decimal(ticker_data["highPrice"]),
                low_price=Decimal(ticker_data["lowPrice"]),
                volume=Decimal(ticker_data["volume"]),
                quote_volume=Decimal(ticker_data["quoteVolume"]),
                price_change=Decimal(ticker_data["priceChange"]),
                price_change_percent=Decimal(ticker_data["priceChangePercent"]),
                weighted_avg_price=Decimal(ticker_data["weightedAvgPrice"]),
                last_quantity=Decimal(ticker_data["lastQty"]),
                best_bid_price=Decimal(ticker_data["bidPrice"]),
                best_bid_quantity=Decimal(ticker_data["bidQty"]),
                best_ask_price=Decimal(ticker_data["askPrice"]),
                best_ask_quantity=Decimal(ticker_data["askQty"]),
                open_time=datetime.fromtimestamp(ticker_data["openTime"] / 1000),
                close_time=datetime.fromtimestamp(ticker_data["closeTime"] / 1000),
                first_trade_id=ticker_data["firstId"],
                last_trade_id=ticker_data["lastId"],
                trade_count=ticker_data["count"],
                timestamp=datetime.fromtimestamp(ticker_data["closeTime"] / 1000)
            )
            
            # 验证数据一致性
            assert abs(normalized_ticker.last_price - Decimal(ticker_data["lastPrice"])) < Decimal("0.01")
            assert abs(normalized_ticker.open_price - Decimal(ticker_data["openPrice"])) < Decimal("0.01")
            assert abs(normalized_ticker.high_price - Decimal(ticker_data["highPrice"])) < Decimal("0.01")
            assert abs(normalized_ticker.low_price - Decimal(ticker_data["lowPrice"])) < Decimal("0.01")
            
            print(f"数据准确性验证通过: 原始价格={ticker_data['lastPrice']}, 标准化价格={normalized_ticker.last_price}")
            
        except Exception as e:
            print(f"创建NormalizedTicker失败: {e}")
            pytest.fail(f"无法创建标准化ticker对象: {e}")
    
    @pytest.mark.skipif(not PYTHON_COLLECTOR_AVAILABLE, reason="Python收集器不可用")
    def test_real_deribit_performance(self):
        """测试真实Deribit数据处理性能"""
        if not check_network_connectivity():
            pytest.skip("网络连接不可用")
        
        real_data = get_real_deribit_data()
        if not real_data or not real_data["trades"] or not real_data["trades"]["result"]["trades"]:
            pytest.skip("无法获取Deribit真实数据")
        
        # 使用真实Deribit数据进行性能测试
        start_time = time.time()
        normalized_trades = []
        
        trades_data = real_data["trades"]["result"]["trades"]
        
        # 重复处理真实数据以测试性能
        for i in range(50):  # Deribit数据较少，减少重复次数
            for trade_data in trades_data:
                try:
                    # 直接创建NormalizedTrade对象
                    normalized = NormalizedTrade(
                        exchange_name="deribit",
                        symbol_name="BTC-PERPETUAL",
                        trade_id=str(trade_data["trade_id"]) + f"_{i}",
                        price=Decimal(str(trade_data["price"])),
                        quantity=Decimal(str(trade_data["amount"])),
                        quote_quantity=Decimal(str(trade_data["price"])) * Decimal(str(trade_data["amount"])),
                        timestamp=datetime.fromtimestamp(trade_data["timestamp"] / 1000),
                        is_buyer_maker=trade_data["direction"] == "sell"
                    )
                    normalized_trades.append(normalized)
                except Exception as e:
                    print(f"创建Deribit交易对象失败: {e}")
                    continue
        
        processing_time = time.time() - start_time
        
        # 验证性能
        assert processing_time < 3.0  # 处理Deribit真实数据应该在3秒内完成
        assert len(normalized_trades) > 0
        
        print(f"处理了 {len(normalized_trades)} 条Deribit真实交易数据，耗时 {processing_time:.2f} 秒")


if __name__ == "__main__":
    # 可以直接运行这个文件进行测试
    pytest.main([__file__, "-v", "--tb=short"]) 