"""
类型转换工具 - 统一处理MarketPrism中的数据类型

主要解决问题：
1. Decimal vs str 类型不匹配
2. 金融数据精度处理
3. 测试数据序列化/反序列化
4. 类型断言统一化
"""

from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Union, Any, Dict, List, Optional, TypeVar, Type
import json
from datetime import datetime, timezone
import numpy as np

# 设置全局Decimal精度
getcontext().prec = 28

T = TypeVar('T')

class FinancialTypeConverter:
    """金融数据类型转换器"""
    
    # 标准精度配置
    PRICE_PRECISION = 8
    QUANTITY_PRECISION = 8
    PERCENTAGE_PRECISION = 4
    
    @classmethod
    def to_decimal(cls, value: Union[str, int, float, Decimal], precision: int = None) -> Decimal:
        """转换为Decimal类型，保持金融精度"""
        if value is None:
            return Decimal('0')
            
        if isinstance(value, Decimal):
            return value
            
        # 处理字符串
        if isinstance(value, str):
            # 移除可能的货币符号和空格
            clean_value = value.strip().replace('$', '').replace(',', '')
            if not clean_value or clean_value in ['N/A', 'null', 'undefined']:
                return Decimal('0')
            
        # 转换为Decimal
        try:
            decimal_value = Decimal(str(value))
        except (ValueError, TypeError):
            return Decimal('0')
        
        # 应用精度
        if precision is not None:
            quantize_value = Decimal('0.1') ** precision
            decimal_value = decimal_value.quantize(quantize_value, rounding=ROUND_HALF_UP)
            
        return decimal_value
    
    @classmethod
    def to_price_decimal(cls, value: Union[str, int, float, Decimal]) -> Decimal:
        """转换为价格Decimal（8位精度）"""
        return cls.to_decimal(value, cls.PRICE_PRECISION)
    
    @classmethod
    def to_quantity_decimal(cls, value: Union[str, int, float, Decimal]) -> Decimal:
        """转换为数量Decimal（8位精度）"""
        return cls.to_decimal(value, cls.QUANTITY_PRECISION)
    
    @classmethod
    def to_percentage_decimal(cls, value: Union[str, int, float, Decimal]) -> Decimal:
        """转换为百分比Decimal（4位精度）"""
        return cls.to_decimal(value, cls.PERCENTAGE_PRECISION)
    
    @classmethod
    def to_string(cls, value: Union[str, int, float, Decimal]) -> str:
        """转换为字符串，保持精度"""
        if value is None:
            return "0"
            
        if isinstance(value, Decimal):
            # 移除尾部零
            return str(value.normalize())
        
        if isinstance(value, (int, float)):
            return str(value)
            
        return str(value)
    
    @classmethod
    def normalize_for_comparison(cls, value: Any) -> str:
        """标准化用于比较的值"""
        if isinstance(value, Decimal):
            # 移除尾部零并转换为字符串
            normalized = value.normalize()
            return str(normalized)
        elif isinstance(value, (int, float)):
            # 转换为Decimal再标准化
            decimal_val = Decimal(str(value))
            return str(decimal_val.normalize())
        else:
            return str(value)


class TestDataNormalizer:
    """测试数据标准化器"""
    
    @staticmethod
    def normalize_market_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """标准化市场数据"""
        normalized = data.copy()
        
        # 价格字段
        price_fields = ['price', 'bid', 'ask', 'open', 'high', 'low', 'close', 'vwap']
        for field in price_fields:
            if field in normalized:
                normalized[field] = FinancialTypeConverter.to_price_decimal(normalized[field])
        
        # 数量字段
        quantity_fields = ['quantity', 'volume', 'base_volume', 'quote_volume', 'amount']
        for field in quantity_fields:
            if field in normalized:
                normalized[field] = FinancialTypeConverter.to_quantity_decimal(normalized[field])
        
        # 百分比字段
        percentage_fields = ['change', 'change_percent', 'percentage']
        for field in percentage_fields:
            if field in normalized:
                normalized[field] = FinancialTypeConverter.to_percentage_decimal(normalized[field])
        
        # 时间戳字段
        timestamp_fields = ['timestamp', 'time', 'datetime', 'created_at', 'updated_at']
        for field in timestamp_fields:
            if field in normalized and normalized[field]:
                normalized[field] = int(normalized[field])
        
        return normalized
    
    @staticmethod
    def normalize_orderbook_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """标准化订单簿数据"""
        normalized = data.copy()
        
        # 处理bids和asks
        for side in ['bids', 'asks']:
            if side in normalized and isinstance(normalized[side], list):
                normalized_side = []
                for entry in normalized[side]:
                    if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                        price = FinancialTypeConverter.to_price_decimal(entry[0])
                        quantity = FinancialTypeConverter.to_quantity_decimal(entry[1])
                        normalized_side.append([price, quantity])
                    elif isinstance(entry, dict):
                        price = FinancialTypeConverter.to_price_decimal(entry.get('price', 0))
                        quantity = FinancialTypeConverter.to_quantity_decimal(entry.get('quantity', 0))
                        normalized_side.append({'price': price, 'quantity': quantity})
                normalized[side] = normalized_side
        
        return normalized


class TestAssertionHelper:
    """测试断言辅助器"""
    
    @staticmethod
    def assert_decimal_equal(actual: Any, expected: Any, msg: str = None):
        """断言Decimal值相等"""
        actual_decimal = FinancialTypeConverter.to_decimal(actual)
        expected_decimal = FinancialTypeConverter.to_decimal(expected)
        
        if actual_decimal != expected_decimal:
            error_msg = f"Decimal values not equal: {actual_decimal} != {expected_decimal}"
            if msg:
                error_msg = f"{msg}: {error_msg}"
            raise AssertionError(error_msg)
    
    @staticmethod
    def assert_price_equal(actual: Any, expected: Any, msg: str = None):
        """断言价格相等"""
        actual_price = FinancialTypeConverter.to_price_decimal(actual)
        expected_price = FinancialTypeConverter.to_price_decimal(expected)
        
        if actual_price != expected_price:
            error_msg = f"Prices not equal: {actual_price} != {expected_price}"
            if msg:
                error_msg = f"{msg}: {error_msg}"
            raise AssertionError(error_msg)
    
    @staticmethod
    def assert_quantity_equal(actual: Any, expected: Any, msg: str = None):
        """断言数量相等"""
        actual_qty = FinancialTypeConverter.to_quantity_decimal(actual)
        expected_qty = FinancialTypeConverter.to_quantity_decimal(expected)
        
        if actual_qty != expected_qty:
            error_msg = f"Quantities not equal: {actual_qty} != {expected_qty}"
            if msg:
                error_msg = f"{msg}: {error_msg}"
            raise AssertionError(error_msg)
    
    @staticmethod
    def assert_financial_dict_equal(actual: Dict[str, Any], expected: Dict[str, Any], msg: str = None):
        """断言金融数据字典相等"""
        actual_normalized = TestDataNormalizer.normalize_market_data(actual)
        expected_normalized = TestDataNormalizer.normalize_market_data(expected)
        
        # 比较所有字段
        for key in expected_normalized:
            if key not in actual_normalized:
                error_msg = f"Missing key '{key}' in actual data"
                if msg:
                    error_msg = f"{msg}: {error_msg}"
                raise AssertionError(error_msg)
            
            actual_value = actual_normalized[key]
            expected_value = expected_normalized[key]
            
            if isinstance(expected_value, Decimal):
                TestAssertionHelper.assert_decimal_equal(actual_value, expected_value, 
                                                       f"Key '{key}'")
            elif actual_value != expected_value:
                error_msg = f"Key '{key}': {actual_value} != {expected_value}"
                if msg:
                    error_msg = f"{msg}: {error_msg}"
                raise AssertionError(error_msg)


class JsonEncoder(json.JSONEncoder):
    """支持Decimal的JSON编码器"""
    
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def serialize_for_test(obj: Any) -> str:
    """序列化对象用于测试"""
    return json.dumps(obj, cls=JsonEncoder, sort_keys=True, indent=2)


def deserialize_from_test(json_str: str) -> Any:
    """从测试JSON反序列化"""
    return json.loads(json_str)


# 便捷函数
def normalize_numeric(value: Any) -> Union[Decimal, str]:
    """标准化数值类型"""
    if isinstance(value, (int, float)):
        return FinancialTypeConverter.to_decimal(value)
    return str(value)


def compare_financial_values(actual: Any, expected: Any) -> bool:
    """比较金融值是否相等"""
    try:
        # 直接比较Decimal值，避免字符串转换的精度问题
        if isinstance(actual, Decimal) and isinstance(expected, (str, int, float)):
            expected_decimal = FinancialTypeConverter.to_decimal(expected)
            return actual == expected_decimal
        elif isinstance(expected, Decimal) and isinstance(actual, (str, int, float)):
            actual_decimal = FinancialTypeConverter.to_decimal(actual)
            return actual_decimal == expected
        elif isinstance(actual, Decimal) and isinstance(expected, Decimal):
            return actual == expected
        else:
            # 都转换为Decimal再比较
            actual_decimal = FinancialTypeConverter.to_decimal(actual)
            expected_decimal = FinancialTypeConverter.to_decimal(expected)
            return actual_decimal == expected_decimal
    except:
        return False


# 测试工厂类
class FinancialTestDataFactory:
    """金融测试数据工厂"""
    
    @staticmethod
    def create_price(base: float = 45000.0, variation: float = 100.0) -> Decimal:
        """创建测试价格"""
        import random
        price = base + random.uniform(-variation, variation)
        return FinancialTypeConverter.to_price_decimal(price)
    
    @staticmethod
    def create_quantity(base: float = 1.0, variation: float = 0.5) -> Decimal:
        """创建测试数量"""
        import random
        quantity = base + random.uniform(-variation, variation)
        return FinancialTypeConverter.to_quantity_decimal(max(0.00000001, quantity))
    
    @staticmethod
    def create_orderbook_entry(price: float, quantity: float) -> Dict[str, Decimal]:
        """创建订单簿条目 - 兼容PriceLevel格式"""
        return {
            'price': FinancialTypeConverter.to_price_decimal(price),
            'quantity': FinancialTypeConverter.to_quantity_decimal(quantity)
        }
    
    @staticmethod
    def create_ticker_data(symbol: str = "BTCUSDT") -> Dict[str, Any]:
        """创建ticker测试数据"""
        base_price = 45000.0
        return TestDataNormalizer.normalize_market_data({
            'symbol': symbol,
            'price': base_price,
            'bid': base_price - 0.5,
            'ask': base_price + 0.5,
            'volume': 1000.5,
            'change': 250.75,
            'change_percent': 0.56,
            'timestamp': int(datetime.now().timestamp() * 1000)
        })


if __name__ == "__main__":
    # 测试示例
    print("🧪 测试金融类型转换器...")
    
    # 测试Decimal转换
    price1 = FinancialTypeConverter.to_price_decimal("45000.12345678")
    price2 = FinancialTypeConverter.to_price_decimal(45000.12345678)
    
    print(f"价格1: {price1} (类型: {type(price1)})")
    print(f"价格2: {price2} (类型: {type(price2)})")
    
    # 测试比较
    print(f"价格相等: {compare_financial_values(price1, '45000.12345678')}")
    
    # 测试数据工厂
    ticker = FinancialTestDataFactory.create_ticker_data()
    print(f"Ticker数据: {serialize_for_test(ticker)}")
    
    print("✅ 类型转换器测试完成") 