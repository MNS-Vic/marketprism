#!/usr/bin/env python3
"""
DEPRECATED: 本模块仅供历史参考，标准实现请使用 collector/normalizer.py。未来版本可能移除。
Normalizer时间戳和字段标准化修复方案
解决时间戳格式不统一和字段映射问题
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional
from decimal import Decimal

class FixedNormalizer:
    """修复后的标准化器"""
    
    @staticmethod
    def format_timestamp_for_clickhouse(dt: datetime) -> str:
        """统一的ClickHouse时间戳格式化方法"""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    
    @staticmethod
    def parse_timestamp_ms(timestamp_ms: int) -> str:
        """从毫秒时间戳解析为ClickHouse格式"""
        dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        return FixedNormalizer.format_timestamp_for_clickhouse(dt)
    
    @staticmethod
    def current_timestamp() -> str:
        """获取当前时间的ClickHouse格式"""
        return FixedNormalizer.format_timestamp_for_clickhouse(datetime.now(timezone.utc))
    
    @staticmethod
    def normalize_base_fields(data: Dict[str, Any], data_type: str, exchange: str, market_type: str = None) -> Dict[str, Any]:
        """标准化基础字段 - 只保留ClickHouse表需要的字段"""
        base_fields = {
            'timestamp': data.get('timestamp', FixedNormalizer.current_timestamp()),
            'exchange': exchange,
            'market_type': market_type or 'spot',
            'symbol': data.get('symbol', ''),
            'data_source': 'marketprism'
        }
        
        # 确保时间戳是ClickHouse格式
        if isinstance(base_fields['timestamp'], datetime):
            base_fields['timestamp'] = FixedNormalizer.format_timestamp_for_clickhouse(base_fields['timestamp'])
        elif isinstance(base_fields['timestamp'], str) and 'T' in base_fields['timestamp']:
            # 如果是ISO格式，转换为ClickHouse格式
            try:
                dt = datetime.fromisoformat(base_fields['timestamp'].replace('Z', '+00:00'))
                base_fields['timestamp'] = FixedNormalizer.format_timestamp_for_clickhouse(dt)
            except:
                base_fields['timestamp'] = FixedNormalizer.current_timestamp()
        
        return base_fields
    
    @staticmethod
    def normalize_trade_data(raw_data: Dict[str, Any], exchange: str, market_type: str) -> Dict[str, Any]:
        """标准化交易数据 - 只保留trades表需要的字段"""
        base = FixedNormalizer.normalize_base_fields(raw_data, 'trade', exchange, market_type)
        
        trade_data = {
            **base,
            'trade_id': str(raw_data.get('trade_id', '')),
            'price': str(raw_data.get('price', '0')),
            'quantity': str(raw_data.get('quantity', '0')),
            'side': raw_data.get('side', 'unknown'),
            'is_maker': bool(raw_data.get('is_maker', False))
        }
        
        return trade_data
    
    @staticmethod
    def normalize_orderbook_data(raw_data: Dict[str, Any], exchange: str, market_type: str) -> Dict[str, Any]:
        """标准化订单簿数据 - 只保留orderbooks表需要的字段"""
        base = FixedNormalizer.normalize_base_fields(raw_data, 'orderbook', exchange, market_type)
        
        orderbook_data = {
            **base,
            'last_update_id': int(raw_data.get('last_update_id', 0)),
            'best_bid_price': str(raw_data.get('best_bid_price', '0')),
            'best_ask_price': str(raw_data.get('best_ask_price', '0')),
            'bids': raw_data.get('bids', '[]'),
            'asks': raw_data.get('asks', '[]')
        }
        
        # 确保bids和asks是字符串格式
        if isinstance(orderbook_data['bids'], list):
            import json
            orderbook_data['bids'] = json.dumps(orderbook_data['bids'])
        if isinstance(orderbook_data['asks'], list):
            import json
            orderbook_data['asks'] = json.dumps(orderbook_data['asks'])
        
        return orderbook_data
    
    @staticmethod
    def normalize_funding_rate_data(raw_data: Dict[str, Any], exchange: str, market_type: str) -> Dict[str, Any]:
        """标准化资金费率数据 - 只保留funding_rates表需要的字段"""
        base = FixedNormalizer.normalize_base_fields(raw_data, 'funding_rate', exchange, market_type)
        
        funding_data = {
            **base,
            'funding_rate': str(raw_data.get('funding_rate', '0')),
            'funding_time': base['timestamp'],  # 使用相同的时间戳
            'next_funding_time': raw_data.get('next_funding_time', base['timestamp'])
        }
        
        # 处理next_funding_time的时间戳格式
        if isinstance(funding_data['next_funding_time'], int):
            funding_data['next_funding_time'] = FixedNormalizer.parse_timestamp_ms(funding_data['next_funding_time'])
        elif isinstance(funding_data['next_funding_time'], datetime):
            funding_data['next_funding_time'] = FixedNormalizer.format_timestamp_for_clickhouse(funding_data['next_funding_time'])
        elif isinstance(funding_data['next_funding_time'], str) and 'T' in funding_data['next_funding_time']:
            try:
                dt = datetime.fromisoformat(funding_data['next_funding_time'].replace('Z', '+00:00'))
                funding_data['next_funding_time'] = FixedNormalizer.format_timestamp_for_clickhouse(dt)
            except:
                funding_data['next_funding_time'] = base['timestamp']
        
        return funding_data
    
    @staticmethod
    def normalize_liquidation_data(raw_data: Dict[str, Any], exchange: str, market_type: str) -> Dict[str, Any]:
        """标准化强平数据 - 只保留liquidations表需要的字段"""
        base = FixedNormalizer.normalize_base_fields(raw_data, 'liquidation', exchange, market_type)
        
        liquidation_data = {
            **base,
            'side': raw_data.get('side', 'unknown'),
            'price': str(raw_data.get('price', '0')),
            'quantity': str(raw_data.get('quantity', '0'))
        }
        
        return liquidation_data
    
    @staticmethod
    def normalize_open_interest_data(raw_data: Dict[str, Any], exchange: str, market_type: str) -> Dict[str, Any]:
        """标准化未平仓量数据 - 只保留open_interests表需要的字段"""
        base = FixedNormalizer.normalize_base_fields(raw_data, 'open_interest', exchange, market_type)
        
        oi_data = {
            **base,
            'open_interest': str(raw_data.get('open_interest', '0')),
            'open_interest_value': str(raw_data.get('open_interest_value', '0'))
        }
        
        return oi_data
    
    @staticmethod
    def normalize_lsr_top_position_data(raw_data: Dict[str, Any], exchange: str, market_type: str) -> Dict[str, Any]:
        """标准化LSR顶级持仓数据 - 只保留lsr_top_positions表需要的字段"""
        base = FixedNormalizer.normalize_base_fields(raw_data, 'lsr_top_position', exchange, market_type)
        
        lsr_data = {
            **base,
            'long_position_ratio': str(raw_data.get('long_position_ratio', '0')),
            'short_position_ratio': str(raw_data.get('short_position_ratio', '0')),
            'period': raw_data.get('period', '5m')
        }
        
        return lsr_data
    
    @staticmethod
    def normalize_lsr_all_account_data(raw_data: Dict[str, Any], exchange: str, market_type: str) -> Dict[str, Any]:
        """标准化LSR全账户数据 - 只保留lsr_all_accounts表需要的字段"""
        base = FixedNormalizer.normalize_base_fields(raw_data, 'lsr_all_account', exchange, market_type)
        
        lsr_data = {
            **base,
            'long_account_ratio': str(raw_data.get('long_account_ratio', '0')),
            'short_account_ratio': str(raw_data.get('short_account_ratio', '0')),
            'period': raw_data.get('period', '5m')
        }
        
        return lsr_data
    
    @staticmethod
    def normalize_volatility_index_data(raw_data: Dict[str, Any], exchange: str, market_type: str) -> Dict[str, Any]:
        """标准化波动率指数数据 - 只保留volatility_indices表需要的字段"""
        base = FixedNormalizer.normalize_base_fields(raw_data, 'volatility_index', exchange, market_type)
        
        vol_data = {
            **base,
            'index_value': str(raw_data.get('index_value', '0')),
            'underlying_asset': raw_data.get('underlying_asset', base['symbol'].split('-')[0] if '-' in base['symbol'] else '')
        }
        
        return vol_data

# 使用示例和测试
if __name__ == "__main__":
    # 测试时间戳格式化
    print("=== 时间戳格式化测试 ===")
    
    # 当前时间
    current = FixedNormalizer.current_timestamp()
    print(f"当前时间: {current}")
    
    # 毫秒时间戳
    ms_timestamp = 1691234567890
    parsed = FixedNormalizer.parse_timestamp_ms(ms_timestamp)
    print(f"毫秒时间戳 {ms_timestamp} -> {parsed}")
    
    # ISO格式转换
    iso_time = "2025-08-04T05:18:12.566000+00:00"
    base = FixedNormalizer.normalize_base_fields({'timestamp': iso_time}, 'test', 'binance')
    print(f"ISO时间戳 {iso_time} -> {base['timestamp']}")
    
    print("\n=== 数据标准化测试 ===")
    
    # 测试交易数据
    trade_raw = {
        'trade_id': '12345',
        'price': '50000.00',
        'quantity': '0.1',
        'side': 'buy',
        'is_maker': False,
        'symbol': 'BTC-USDT',
        'timestamp': iso_time
    }
    
    trade_normalized = FixedNormalizer.normalize_trade_data(trade_raw, 'binance_derivatives', 'perpetual')
    print(f"交易数据标准化: {trade_normalized}")
    
    # 测试资金费率数据
    funding_raw = {
        'funding_rate': '0.0001',
        'next_funding_time': 1691238000000,  # 毫秒时间戳
        'symbol': 'BTC-USDT'
    }
    
    funding_normalized = FixedNormalizer.normalize_funding_rate_data(funding_raw, 'binance_derivatives', 'perpetual')
    print(f"资金费率数据标准化: {funding_normalized}")
