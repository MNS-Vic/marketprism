#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MarketPrism 测试数据样本
提供各种测试场景下需要的示例数据
"""

import datetime
import json
import uuid
import random
from typing import Dict, List, Any, Optional

# 交易对样本
SYMBOLS = [
    "BTC-USDT", "ETH-USDT", "BNB-USDT", "SOL-USDT", "ADA-USDT",
    "XRP-USDT", "DOT-USDT", "DOGE-USDT", "AVAX-USDT", "SHIB-USDT"
]

# 交易所样本
EXCHANGES = ["binance", "okex", "deribit", "bybit", "kraken"]

# 合约类型
CONTRACT_TYPES = ["spot", "futures", "perpetual", "option"]

def generate_timestamp(days_ago: int = 0, hours_ago: int = 0, minutes_ago: int = 0) -> int:
    """
    生成指定时间前的时间戳
    
    参数:
        days_ago: 天数偏移
        hours_ago: 小时偏移
        minutes_ago: 分钟偏移
        
    返回:
        Unix时间戳(秒)
    """
    now = datetime.datetime.now()
    target_time = now - datetime.timedelta(
        days=days_ago,
        hours=hours_ago,
        minutes=minutes_ago
    )
    return int(target_time.timestamp())

def generate_trade_data(count: int = 100, exchange: str = None) -> List[Dict[str, Any]]:
    """
    生成交易数据样本
    
    参数:
        count: 生成记录数量
        exchange: 指定交易所，默认随机选择
        
    返回:
        交易数据列表
    """
    trades = []
    
    for i in range(count):
        # 选择交易所和交易对
        ex = exchange or random.choice(EXCHANGES)
        symbol = random.choice(SYMBOLS)
        
        # 基础价格 (BTC约4万, ETH约2000等)
        base_price = {
            "BTC": 40000, "ETH": 2000, "BNB": 300, "SOL": 80, "ADA": 0.5,
            "XRP": 0.5, "DOT": 6, "DOGE": 0.1, "AVAX": 30, "SHIB": 0.00001
        }.get(symbol.split("-")[0], 10)
        
        # 随机波动
        price_variation = random.uniform(-0.02, 0.02)  # ±2%波动
        price = base_price * (1 + price_variation)
        
        # 生成交易数据
        trade = {
            "exchange": ex,
            "symbol": symbol,
            "trade_id": str(uuid.uuid4()),
            "price": round(price, 6),
            "volume": round(random.uniform(0.01, 10), 6),
            "timestamp": generate_timestamp(minutes_ago=random.randint(0, 60)),
            "side": random.choice(["buy", "sell"]),
            "contract_type": random.choice(CONTRACT_TYPES)
        }
        
        trades.append(trade)
    
    return trades

def generate_orderbook_data(symbol: str = "BTC-USDT", depth: int = 10) -> Dict[str, Any]:
    """
    生成订单簿数据样本
    
    参数:
        symbol: 交易对
        depth: 档位数量
        
    返回:
        订单簿数据
    """
    # 基础价格
    base_price = {
        "BTC": 40000, "ETH": 2000, "BNB": 300, "SOL": 80, "ADA": 0.5,
        "XRP": 0.5, "DOT": 6, "DOGE": 0.1, "AVAX": 30, "SHIB": 0.00001
    }.get(symbol.split("-")[0], 10)
    
    # 生成卖单(asks)和买单(bids)
    asks = []
    bids = []
    
    for i in range(depth):
        # 卖单从基础价格向上
        ask_price = base_price * (1 + 0.0001 * (i + 1))
        ask_volume = round(random.uniform(0.1, 5), 6)
        asks.append([round(ask_price, 6), ask_volume])
        
        # 买单从基础价格向下
        bid_price = base_price * (1 - 0.0001 * (i + 1))
        bid_volume = round(random.uniform(0.1, 5), 6)
        bids.append([round(bid_price, 6), bid_volume])
    
    # 构建订单簿
    orderbook = {
        "exchange": random.choice(EXCHANGES),
        "symbol": symbol,
        "timestamp": generate_timestamp(),
        "asks": asks,
        "bids": bids
    }
    
    return orderbook

def generate_funding_rate_data(count: int = 20) -> List[Dict[str, Any]]:
    """
    生成资金费率数据样本
    
    参数:
        count: 生成记录数量
        
    返回:
        资金费率数据列表
    """
    funding_rates = []
    
    for i in range(count):
        # 选择交易所和交易对
        exchange = random.choice(EXCHANGES)
        symbol = random.choice(SYMBOLS)
        
        # 生成资金费率数据
        funding_rate = {
            "exchange": exchange,
            "symbol": symbol,
            "funding_rate": round(random.uniform(-0.001, 0.001), 6),  # 通常在±0.1%范围内
            "next_funding_time": generate_timestamp(hours_ago=-8),  # 未来8小时
            "timestamp": generate_timestamp(hours_ago=i*8)  # 每8小时一次
        }
        
        funding_rates.append(funding_rate)
    
    return funding_rates

def to_json_file(data: Any, file_path: str) -> None:
    """
    将数据保存为JSON文件
    
    参数:
        data: 要保存的数据
        file_path: 文件路径
    """
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"数据已保存到 {file_path}")

# 使用示例
if __name__ == "__main__":
    # 生成交易数据
    trades = generate_trade_data(10)
    print(json.dumps(trades[0], indent=2, ensure_ascii=False))
    
    # 生成订单簿数据
    orderbook = generate_orderbook_data()
    print(json.dumps(orderbook, indent=2, ensure_ascii=False))
    
    # 生成资金费率数据
    funding_rates = generate_funding_rate_data(3)
    print(json.dumps(funding_rates[0], indent=2, ensure_ascii=False))