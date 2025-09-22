#!/usr/bin/env python3
"""
MarketPrism修复版数据标准化器
解决字段命名不统一和时间戳格式问题
"""

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)

class FixedMarketPrismNormalizer:
    """修复版MarketPrism数据标准化器"""
    
    def __init__(self):
        # ClickHouse表字段映射 - 确保完全匹配
        self.table_fields = {
            'orderbooks': [
                'timestamp', 'exchange', 'market_type', 'symbol', 
                'last_update_id', 'best_bid_price', 'best_ask_price', 
                'bids', 'asks', 'data_source'
            ],
            'trades': [
                'timestamp', 'exchange', 'market_type', 'symbol', 
                'trade_id', 'price', 'quantity', 'side', 
                'data_source', 'is_maker'
            ],
            'funding_rates': [
                'timestamp', 'exchange', 'market_type', 'symbol', 
                'funding_rate', 'funding_time', 'next_funding_time', 
                'data_source'
            ],
            'open_interests': [
                'timestamp', 'exchange', 'market_type', 'symbol', 
                'open_interest', 'open_interest_value', 'data_source'
            ],
            'liquidations': [
                'timestamp', 'exchange', 'market_type', 'symbol', 
                'side', 'price', 'quantity', 'data_source'
            ],
            'lsr_top_positions': [
                'timestamp', 'exchange', 'market_type', 'symbol', 
                'long_position_ratio', 'short_position_ratio', 'period', 
                'data_source'
            ],
            'lsr_all_accounts': [
                'timestamp', 'exchange', 'market_type', 'symbol', 
                'long_account_ratio', 'short_account_ratio', 'period', 
                'data_source'
            ],
            'volatility_indices': [
                'timestamp', 'exchange', 'market_type', 'symbol', 
                'index_value', 'underlying_asset', 'data_source'
            ]
        }
        
        # 字段映射规则 - 从原始字段名到标准字段名
        self.field_mappings = {
            # 通用映射
            'exchange_name': 'exchange',
            'symbol_name': 'symbol',
            
            # 资金费率特殊映射
            'current_funding_rate': 'funding_rate',
            
            # 波动率指数特殊映射
            'volatility_index': 'index_value',
            
            # 时间戳相关映射
            'trade_time': 'timestamp',
            'event_time': 'timestamp',
            'liquidation_time': 'timestamp',
        }
        
        # 禁用字段列表 - 这些字段不应出现在最终数据中
        self.excluded_fields = {
            'data_type', 'normalized', 'normalizer_version', 
            'publisher', 'normalized_at', 'collected_at',
            'raw_data', 'normalization_error'
        }
    
    def format_timestamp_for_clickhouse(self, dt: datetime) -> str:
        """统一的ClickHouse时间戳格式化方法"""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    
    def parse_timestamp_ms(self, timestamp_ms: int) -> str:
        """从毫秒时间戳解析为ClickHouse格式"""
        dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        return self.format_timestamp_for_clickhouse(dt)
    
    def current_timestamp(self) -> str:
        """获取当前时间的ClickHouse格式"""
        return self.format_timestamp_for_clickhouse(datetime.now(timezone.utc))
    
    def normalize_timestamp(self, timestamp_value: Any) -> str:
        """统一时间戳标准化"""
        try:
            if isinstance(timestamp_value, datetime):
                return self.format_timestamp_for_clickhouse(timestamp_value)
            elif isinstance(timestamp_value, (int, float)):
                # 毫秒时间戳
                if timestamp_value > 1e10:  # 毫秒级
                    return self.parse_timestamp_ms(int(timestamp_value))
                else:  # 秒级
                    dt = datetime.fromtimestamp(timestamp_value, tz=timezone.utc)
                    return self.format_timestamp_for_clickhouse(dt)
            elif isinstance(timestamp_value, str):
                # ISO 8601格式转换
                if 'T' in timestamp_value:
                    dt = datetime.fromisoformat(timestamp_value.replace('Z', '+00:00'))
                    return self.format_timestamp_for_clickhouse(dt)
                else:
                    # 已经是正确格式
                    return timestamp_value
            else:
                return self.current_timestamp()
        except Exception as e:
            logger.warning(f"时间戳标准化失败: {e}, 使用当前时间")
            return self.current_timestamp()
    
    def normalize_base_fields(self, data: Dict[str, Any], data_type: str, 
                            exchange: str, market_type: str = None) -> Dict[str, Any]:
        """标准化基础字段"""
        # 获取时间戳
        timestamp = data.get('timestamp')
        if not timestamp:
            timestamp = self.current_timestamp()
        else:
            timestamp = self.normalize_timestamp(timestamp)
        
        return {
            'timestamp': timestamp,
            'exchange': self.normalize_exchange_name(exchange),
            'market_type': self.normalize_market_type(market_type or 'spot'),
            'symbol': self.normalize_symbol_format(data.get('symbol', '')),
            'data_source': 'marketprism'
        }
    
    def normalize_exchange_name(self, exchange: str) -> str:
        """标准化交易所名称"""
        if not exchange:
            return 'unknown'
        
        exchange = exchange.lower()
        exchange_mapping = {
            'binance_spot': 'binance',
            'binance_derivatives': 'binance',
            'binance_perpetual': 'binance',
            'binance_futures': 'binance',
            'okx_spot': 'okx',
            'okx_derivatives': 'okx',
            'okx_perpetual': 'okx',
            'okx_swap': 'okx',
            'okx_futures': 'okx'
        }
        return exchange_mapping.get(exchange, exchange)
    
    def normalize_market_type(self, market_type: str) -> str:
        """标准化市场类型"""
        if not market_type:
            return 'spot'
        
        market_type = market_type.lower()
        market_type_mapping = {
            'swap': 'perpetual',
            'futures': 'perpetual',
            'perp': 'perpetual',
            'derivatives': 'perpetual',
            'perpetual': 'perpetual',
            'spot': 'spot'
        }
        return market_type_mapping.get(market_type, 'spot')
    
    def normalize_symbol_format(self, symbol: str) -> str:
        """标准化交易对格式为 XXX-XXX"""
        if not symbol:
            return ''
        
        # 移除常见的后缀
        symbol = symbol.replace('-SWAP', '').replace('_SWAP', '')
        symbol = symbol.replace('-PERP', '').replace('_PERP', '')
        
        # 统一分隔符
        if '/' in symbol:
            symbol = symbol.replace('/', '-')
        elif '_' in symbol:
            symbol = symbol.replace('_', '-')
        elif '-' not in symbol and len(symbol) >= 6:
            # 处理类似BTCUSDT的格式
            if symbol.endswith('USDT'):
                base = symbol[:-4]
                symbol = f"{base}-USDT"
            elif symbol.endswith('BTC'):
                base = symbol[:-3]
                symbol = f"{base}-BTC"
        
        return symbol.upper()
    
    def clean_and_map_fields(self, data: Dict[str, Any], table_name: str) -> Dict[str, Any]:
        """清理和映射字段到ClickHouse表结构"""
        allowed_fields = self.table_fields.get(table_name, [])
        if not allowed_fields:
            return {}
        
        cleaned_data = {}
        
        for field in allowed_fields:
            value = None
            
            # 1. 直接字段匹配
            if field in data:
                value = data[field]
            
            # 2. 字段映射
            elif field in self.field_mappings and self.field_mappings[field] in data:
                value = data[self.field_mappings[field]]
            
            # 3. 反向映射检查
            else:
                for original_field, mapped_field in self.field_mappings.items():
                    if mapped_field == field and original_field in data:
                        value = data[original_field]
                        break
            
            # 4. 特殊字段处理
            if value is None:
                if field == 'data_source':
                    value = 'marketprism'
                elif field == 'is_maker':
                    value = False
                elif field == 'open_interest_value':
                    value = '0.0'
                elif field == 'underlying_asset':
                    symbol = data.get('symbol', '')
                    value = symbol.split('-')[0] if '-' in symbol else ''
                elif field in ['funding_time', 'next_funding_time']:
                    value = data.get('timestamp', self.current_timestamp())
            
            # 5. 数据类型转换
            if value is not None:
                if field == 'timestamp' or field.endswith('_time'):
                    value = self.normalize_timestamp(value)
                elif field in ['price', 'quantity', 'funding_rate', 'open_interest', 
                              'open_interest_value', 'long_position_ratio', 
                              'short_position_ratio', 'long_account_ratio', 
                              'short_account_ratio', 'index_value',
                              'best_bid_price', 'best_ask_price']:
                    value = str(value)
                elif field in ['bids', 'asks'] and isinstance(value, (list, dict)):
                    value = json.dumps(value)
                elif field == 'last_update_id':
                    value = int(value) if value else 0
                
                cleaned_data[field] = value
        
        return cleaned_data
    
    def normalize_orderbook_data(self, data: Dict[str, Any], exchange: str, 
                               market_type: str) -> Dict[str, Any]:
        """标准化订单簿数据"""
        base_fields = self.normalize_base_fields(data, 'orderbook', exchange, market_type)
        
        # 合并所有字段
        all_data = {**data, **base_fields}
        
        # 清理和映射字段
        return self.clean_and_map_fields(all_data, 'orderbooks')
    
    def normalize_trade_data(self, data: Dict[str, Any], exchange: str, 
                           market_type: str) -> Dict[str, Any]:
        """标准化交易数据"""
        base_fields = self.normalize_base_fields(data, 'trade', exchange, market_type)
        
        # 合并所有字段
        all_data = {**data, **base_fields}
        
        # 清理和映射字段
        return self.clean_and_map_fields(all_data, 'trades')
    
    def normalize_funding_rate_data(self, data: Dict[str, Any], exchange: str, 
                                  market_type: str) -> Dict[str, Any]:
        """标准化资金费率数据"""
        base_fields = self.normalize_base_fields(data, 'funding_rate', exchange, market_type)
        
        # 合并所有字段
        all_data = {**data, **base_fields}
        
        # 清理和映射字段
        return self.clean_and_map_fields(all_data, 'funding_rates')
    
    def normalize_liquidation_data(self, data: Dict[str, Any], exchange: str, 
                                 market_type: str) -> Dict[str, Any]:
        """标准化强平数据"""
        base_fields = self.normalize_base_fields(data, 'liquidation', exchange, market_type)
        
        # 合并所有字段
        all_data = {**data, **base_fields}
        
        # 清理和映射字段
        return self.clean_and_map_fields(all_data, 'liquidations')
    
    def normalize_open_interest_data(self, data: Dict[str, Any], exchange: str, 
                                   market_type: str) -> Dict[str, Any]:
        """标准化未平仓量数据"""
        base_fields = self.normalize_base_fields(data, 'open_interest', exchange, market_type)
        
        # 合并所有字段
        all_data = {**data, **base_fields}
        
        # 清理和映射字段
        return self.clean_and_map_fields(all_data, 'open_interests')
    
    def normalize_lsr_top_position_data(self, data: Dict[str, Any], exchange: str, 
                                      market_type: str) -> Dict[str, Any]:
        """标准化LSR顶级持仓数据"""
        base_fields = self.normalize_base_fields(data, 'lsr_top_position', exchange, market_type)
        
        # 合并所有字段
        all_data = {**data, **base_fields}
        
        # 清理和映射字段
        return self.clean_and_map_fields(all_data, 'lsr_top_positions')
    
    def normalize_lsr_all_account_data(self, data: Dict[str, Any], exchange: str, 
                                     market_type: str) -> Dict[str, Any]:
        """标准化LSR全账户数据"""
        base_fields = self.normalize_base_fields(data, 'lsr_all_account', exchange, market_type)
        
        # 合并所有字段
        all_data = {**data, **base_fields}
        
        # 清理和映射字段
        return self.clean_and_map_fields(all_data, 'lsr_all_accounts')
    
    def normalize_volatility_index_data(self, data: Dict[str, Any], exchange: str, 
                                      market_type: str) -> Dict[str, Any]:
        """标准化波动率指数数据"""
        base_fields = self.normalize_base_fields(data, 'volatility_index', exchange, market_type)
        
        # 合并所有字段
        all_data = {**data, **base_fields}
        
        # 清理和映射字段
        return self.clean_and_map_fields(all_data, 'volatility_indices')

# 测试和验证
if __name__ == "__main__":
    normalizer = FixedMarketPrismNormalizer()
    
    # 测试时间戳标准化
    print("=== 时间戳标准化测试 ===")
    test_timestamps = [
        "2025-08-04T16:00:00+00:00",  # ISO 8601
        1691234567890,  # 毫秒时间戳
        datetime.now(timezone.utc),  # datetime对象
        "2025-08-04 16:00:00"  # 已正确格式
    ]
    
    for ts in test_timestamps:
        result = normalizer.normalize_timestamp(ts)
        print(f"{ts} -> {result}")
    
    print("\n=== 数据标准化测试 ===")
    
    # 测试交易数据
    trade_data = {
        'symbol': 'BTCUSDT',
        'trade_id': '12345',
        'price': 50000.00,
        'quantity': 0.1,
        'side': 'buy',
        'is_maker': False,
        'timestamp': "2025-08-04T16:00:00+00:00",
        'data_type': 'trade',  # 应该被过滤
        'normalized': True,    # 应该被过滤
    }
    
    normalized_trade = normalizer.normalize_trade_data(
        trade_data, 'binance_derivatives', 'perpetual'
    )
    print(f"交易数据标准化: {normalized_trade}")
    
    # 测试资金费率数据
    funding_data = {
        'symbol': 'BTC-USDT',
        'current_funding_rate': 0.0001,  # 应该映射到funding_rate
        'next_funding_time': 1691238000000,
        'timestamp': "2025-08-04T16:00:00+00:00",
        'data_type': 'funding_rate',  # 应该被过滤
    }
    
    normalized_funding = normalizer.normalize_funding_rate_data(
        funding_data, 'binance_derivatives', 'perpetual'
    )
    print(f"资金费率数据标准化: {normalized_funding}")
