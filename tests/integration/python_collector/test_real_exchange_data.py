"""
Python Collector 真实交易所数据测试

连接真实的交易所API获取数据，测试数据标准化和处理流程
不使用Mock，使用真实的网络请求和数据
"""

import pytest
import asyncio
import ccxt
import time
from datetime import datetime, timezone
from decimal import Decimal

# 导入被测试的模块
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../services/python-collector/src'))

from marketprism_collector.normalizer import DataNormalizer
from marketprism_collector.types import (
    NormalizedTrade, NormalizedOrderBook, NormalizedTicker,
    PriceLevel, Exchange, MarketType, DataType
)


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def normalizer():
    """数据标准化器"""
    return DataNormalizer()


class TestRealBinanceData:
    """测试真实Binance数据"""
    
    @pytest.fixture
    def binance_exchange(self):
        """创建Binance交易所实例"""
        try:
            exchange = ccxt.binance({
                'apiKey': '',  # 只读数据不需要API密钥
                'secret': '',
                'sandbox': False,  # 使用真实环境
                'enableRateLimit': True,
            })
            return exchange
        except Exception as e:
            pytest.skip(f"无法创建Binance交易所实例: {e}")
    
    def test_fetch_real_ticker(self, binance_exchange, normalizer):
        """测试获取真实行情数据"""
        try:
            # 获取真实的BTCUSDT行情数据
            ticker_data = binance_exchange.fetch_ticker('BTC/USDT')
            
            # 验证原始数据结构
            assert 'symbol' in ticker_data
            assert 'last' in ticker_data
            assert 'bid' in ticker_data
            assert 'ask' in ticker_data
            assert 'high' in ticker_data
            assert 'low' in ticker_data
            assert 'open' in ticker_data
            assert 'close' in ticker_data
            assert 'baseVolume' in ticker_data
            assert 'quoteVolume' in ticker_data
            
            # 标准化数据
            normalized_ticker = normalizer.normalize_ticker(
                exchange_name="binance",
                raw_data=ticker_data
            )
            
            # 验证标准化后的数据
            assert isinstance(normalized_ticker, NormalizedTicker)
            assert normalized_ticker.exchange_name == "binance"
            assert normalized_ticker.symbol_name == "BTCUSDT"
            assert isinstance(normalized_ticker.last_price, Decimal)
            assert isinstance(normalized_ticker.volume, Decimal)
            assert isinstance(normalized_ticker.quote_volume, Decimal)
            assert normalized_ticker.last_price > 0
            assert normalized_ticker.volume >= 0
            
            print(f"真实行情数据: {normalized_ticker.symbol_name} = ${normalized_ticker.last_price}")
            
        except Exception as e:
            pytest.fail(f"获取真实行情数据失败: {e}")
    
    def test_fetch_real_orderbook(self, binance_exchange, normalizer):
        """测试获取真实订单簿数据"""
        try:
            # 获取真实的BTCUSDT订单簿数据
            orderbook_data = binance_exchange.fetch_order_book('BTC/USDT', limit=10)
            
            # 验证原始数据结构
            assert 'bids' in orderbook_data
            assert 'asks' in orderbook_data
            assert 'timestamp' in orderbook_data
            assert len(orderbook_data['bids']) > 0
            assert len(orderbook_data['asks']) > 0
            
            # 验证价格档位格式
            for bid in orderbook_data['bids'][:3]:
                assert len(bid) >= 2  # [price, quantity]
                assert isinstance(bid[0], (int, float))  # price
                assert isinstance(bid[1], (int, float))  # quantity
                assert bid[0] > 0
                assert bid[1] > 0
            
            for ask in orderbook_data['asks'][:3]:
                assert len(ask) >= 2
                assert isinstance(ask[0], (int, float))
                assert isinstance(ask[1], (int, float))
                assert ask[0] > 0
                assert ask[1] > 0
            
            # 标准化数据
            normalized_orderbook = normalizer.normalize_orderbook(
                exchange_name="binance",
                raw_data=orderbook_data
            )
            
            # 验证标准化后的数据
            assert isinstance(normalized_orderbook, NormalizedOrderBook)
            assert normalized_orderbook.exchange_name == "binance"
            assert normalized_orderbook.symbol_name == "BTCUSDT"
            assert len(normalized_orderbook.bids) > 0
            assert len(normalized_orderbook.asks) > 0
            
            # 验证价格档位
            for bid in normalized_orderbook.bids[:3]:
                assert isinstance(bid, PriceLevel)
                assert isinstance(bid.price, Decimal)
                assert isinstance(bid.quantity, Decimal)
                assert bid.price > 0
                assert bid.quantity > 0
            
            for ask in normalized_orderbook.asks[:3]:
                assert isinstance(ask, PriceLevel)
                assert isinstance(ask.price, Decimal)
                assert isinstance(ask.quantity, Decimal)
                assert ask.price > 0
                assert ask.quantity > 0
            
            # 验证买卖价格关系
            best_bid = normalized_orderbook.bids[0].price
            best_ask = normalized_orderbook.asks[0].price
            assert best_bid < best_ask, "最佳买价应该小于最佳卖价"
            
            print(f"真实订单簿: 买一 ${best_bid}, 卖一 ${best_ask}")
            
        except Exception as e:
            pytest.fail(f"获取真实订单簿数据失败: {e}")
    
    def test_fetch_real_trades(self, binance_exchange, normalizer):
        """测试获取真实交易数据"""
        try:
            # 获取真实的BTCUSDT最近交易数据
            trades_data = binance_exchange.fetch_trades('BTC/USDT', limit=10)
            
            # 验证原始数据结构
            assert isinstance(trades_data, list)
            assert len(trades_data) > 0
            
            for trade in trades_data[:3]:
                assert 'id' in trade
                assert 'timestamp' in trade
                assert 'symbol' in trade
                assert 'side' in trade
                assert 'amount' in trade
                assert 'price' in trade
                assert 'cost' in trade
                
                # 验证数据类型和范围
                assert isinstance(trade['price'], (int, float))
                assert isinstance(trade['amount'], (int, float))
                assert isinstance(trade['cost'], (int, float))
                assert trade['price'] > 0
                assert trade['amount'] > 0
                assert trade['cost'] > 0
                assert trade['side'] in ['buy', 'sell']
            
            # 标准化第一个交易数据
            first_trade = trades_data[0]
            normalized_trade = normalizer.normalize_trade(
                exchange_name="binance",
                raw_data=first_trade
            )
            
            # 验证标准化后的数据
            assert isinstance(normalized_trade, NormalizedTrade)
            assert normalized_trade.exchange_name == "binance"
            assert normalized_trade.symbol_name == "BTCUSDT"
            assert isinstance(normalized_trade.price, Decimal)
            assert isinstance(normalized_trade.quantity, Decimal)
            assert isinstance(normalized_trade.quote_quantity, Decimal)
            assert normalized_trade.price > 0
            assert normalized_trade.quantity > 0
            assert normalized_trade.quote_quantity > 0
            
            print(f"真实交易: {normalized_trade.quantity} BTC @ ${normalized_trade.price}")
            
        except Exception as e:
            pytest.fail(f"获取真实交易数据失败: {e}")


class TestRealOKXData:
    """测试真实OKX数据"""
    
    @pytest.fixture
    def okx_exchange(self):
        """创建OKX交易所实例"""
        try:
            exchange = ccxt.okx({
                'apiKey': '',  # 只读数据不需要API密钥
                'secret': '',
                'password': '',
                'sandbox': False,  # 使用真实环境
                'enableRateLimit': True,
            })
            return exchange
        except Exception as e:
            pytest.skip(f"无法创建OKX交易所实例: {e}")
    
    def test_fetch_real_ticker_okx(self, okx_exchange, normalizer):
        """测试获取真实OKX行情数据"""
        try:
            # 获取真实的BTC-USDT行情数据
            ticker_data = okx_exchange.fetch_ticker('BTC/USDT')
            
            # 验证原始数据
            assert 'symbol' in ticker_data
            assert 'last' in ticker_data
            assert ticker_data['last'] > 0
            
            # 标准化数据
            normalized_ticker = normalizer.normalize_ticker(
                exchange_name="okx",
                raw_data=ticker_data
            )
            
            # 验证标准化数据
            assert isinstance(normalized_ticker, NormalizedTicker)
            assert normalized_ticker.exchange_name == "okx"
            assert normalized_ticker.symbol_name in ["BTCUSDT", "BTC-USDT"]
            assert normalized_ticker.last_price > 0
            
            print(f"OKX真实行情: {normalized_ticker.symbol_name} = ${normalized_ticker.last_price}")
            
        except Exception as e:
            pytest.fail(f"获取OKX真实行情数据失败: {e}")


class TestRealDataComparison:
    """测试真实数据对比"""
    
    def test_cross_exchange_price_comparison(self):
        """测试跨交易所价格对比"""
        try:
            # 创建多个交易所实例
            binance = ccxt.binance({'enableRateLimit': True})
            okx = ccxt.okx({'enableRateLimit': True})
            
            # 获取同一交易对的价格
            symbol = 'BTC/USDT'
            
            binance_ticker = binance.fetch_ticker(symbol)
            time.sleep(1)  # 避免请求过快
            okx_ticker = okx.fetch_ticker(symbol)
            
            binance_price = Decimal(str(binance_ticker['last']))
            okx_price = Decimal(str(okx_ticker['last']))
            
            # 验证价格合理性
            assert binance_price > 0
            assert okx_price > 0
            
            # 计算价格差异
            price_diff = abs(binance_price - okx_price)
            price_diff_percent = (price_diff / binance_price) * 100
            
            print(f"Binance BTC价格: ${binance_price}")
            print(f"OKX BTC价格: ${okx_price}")
            print(f"价格差异: ${price_diff} ({price_diff_percent:.2f}%)")
            
            # 价格差异应该在合理范围内（通常小于1%）
            assert price_diff_percent < 5, f"价格差异过大: {price_diff_percent:.2f}%"
            
        except Exception as e:
            pytest.fail(f"跨交易所价格对比失败: {e}")
    
    def test_data_freshness(self):
        """测试数据新鲜度"""
        try:
            binance = ccxt.binance({'enableRateLimit': True})
            
            # 获取行情数据
            ticker = binance.fetch_ticker('BTC/USDT')
            
            # 检查时间戳
            if ticker['timestamp']:
                data_time = datetime.fromtimestamp(ticker['timestamp'] / 1000, tz=timezone.utc)
                current_time = datetime.now(timezone.utc)
                time_diff = (current_time - data_time).total_seconds()
                
                print(f"数据时间: {data_time}")
                print(f"当前时间: {current_time}")
                print(f"数据延迟: {time_diff:.2f}秒")
                
                # 数据应该是最近的（小于60秒）
                assert time_diff < 60, f"数据过旧: {time_diff:.2f}秒"
            
        except Exception as e:
            pytest.fail(f"数据新鲜度测试失败: {e}")


class TestRealDataValidation:
    """测试真实数据验证"""
    
    def test_data_consistency(self):
        """测试数据一致性"""
        try:
            binance = ccxt.binance({'enableRateLimit': True})
            
            # 获取行情和订单簿数据
            ticker = binance.fetch_ticker('BTC/USDT')
            orderbook = binance.fetch_order_book('BTC/USDT', limit=5)
            
            ticker_price = Decimal(str(ticker['last']))
            best_bid = Decimal(str(orderbook['bids'][0][0]))
            best_ask = Decimal(str(orderbook['asks'][0][0]))
            
            print(f"行情价格: ${ticker_price}")
            print(f"最佳买价: ${best_bid}")
            print(f"最佳卖价: ${best_ask}")
            
            # 验证价格关系
            assert best_bid < best_ask, "买价应该小于卖价"
            assert best_bid <= ticker_price <= best_ask, "行情价格应该在买卖价之间"
            
            # 验证价差合理性
            spread = best_ask - best_bid
            spread_percent = (spread / ticker_price) * 100
            
            print(f"买卖价差: ${spread} ({spread_percent:.4f}%)")
            
            # 价差应该在合理范围内
            assert spread_percent < 1, f"买卖价差过大: {spread_percent:.4f}%"
            
        except Exception as e:
            pytest.fail(f"数据一致性测试失败: {e}")
    
    def test_volume_validation(self):
        """测试成交量验证"""
        try:
            binance = ccxt.binance({'enableRateLimit': True})
            
            # 获取24小时行情数据
            ticker = binance.fetch_ticker('BTC/USDT')
            
            base_volume = ticker['baseVolume']  # BTC成交量
            quote_volume = ticker['quoteVolume']  # USDT成交量
            vwap = ticker['vwap']  # 成交量加权平均价格
            
            if base_volume and quote_volume and vwap:
                base_volume = Decimal(str(base_volume))
                quote_volume = Decimal(str(quote_volume))
                vwap = Decimal(str(vwap))
                
                # 验证成交量关系
                calculated_quote_volume = base_volume * vwap
                volume_diff_percent = abs(calculated_quote_volume - quote_volume) / quote_volume * 100
                
                print(f"基础成交量: {base_volume} BTC")
                print(f"报价成交量: {quote_volume} USDT")
                print(f"VWAP: ${vwap}")
                print(f"计算的报价成交量: {calculated_quote_volume} USDT")
                print(f"成交量差异: {volume_diff_percent:.2f}%")
                
                # 成交量计算差异应该在合理范围内
                assert volume_diff_percent < 10, f"成交量计算差异过大: {volume_diff_percent:.2f}%"
            
        except Exception as e:
            pytest.fail(f"成交量验证失败: {e}")


class TestRealNetworkResilience:
    """测试真实网络弹性"""
    
    def test_network_timeout_handling(self):
        """测试网络超时处理"""
        try:
            # 创建带有短超时的交易所实例
            binance = ccxt.binance({
                'enableRateLimit': True,
                'timeout': 1000,  # 1秒超时
            })
            
            start_time = time.time()
            
            try:
                ticker = binance.fetch_ticker('BTC/USDT')
                end_time = time.time()
                
                response_time = end_time - start_time
                print(f"响应时间: {response_time:.2f}秒")
                
                # 验证响应时间合理
                assert response_time < 5, f"响应时间过长: {response_time:.2f}秒"
                
                # 验证数据有效性
                assert 'last' in ticker
                assert ticker['last'] > 0
                
            except ccxt.RequestTimeout:
                print("网络超时，这是预期的行为")
                # 超时是可以接受的
                pass
                
        except Exception as e:
            pytest.fail(f"网络超时处理测试失败: {e}")
    
    def test_rate_limit_handling(self):
        """测试请求频率限制处理"""
        try:
            binance = ccxt.binance({
                'enableRateLimit': True,  # 启用频率限制
            })
            
            # 连续发送多个请求
            request_count = 5
            start_time = time.time()
            
            for i in range(request_count):
                ticker = binance.fetch_ticker('BTC/USDT')
                assert 'last' in ticker
                assert ticker['last'] > 0
                print(f"请求 {i+1}/{request_count} 完成")
            
            end_time = time.time()
            total_time = end_time - start_time
            
            print(f"总请求时间: {total_time:.2f}秒")
            print(f"平均请求时间: {total_time/request_count:.2f}秒/请求")
            
            # 验证频率限制生效（应该有延迟）
            assert total_time > request_count * 0.1, "频率限制可能未生效"
            
        except Exception as e:
            pytest.fail(f"频率限制处理测试失败: {e}")


if __name__ == "__main__":
    # 运行测试前的说明
    print("=" * 60)
    print("真实交易所数据集成测试")
    print("=" * 60)
    print("此测试将连接真实的交易所API获取数据")
    print("需要网络连接，可能会受到API频率限制")
    print("=" * 60)
    
    pytest.main([__file__, "-v", "-s"]) 