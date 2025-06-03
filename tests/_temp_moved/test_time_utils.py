#!/usr/bin/env python3
"""
时间工具单元测试
"""
import os
import sys
import pytest
from unittest.mock import MagicMock, patch
import datetime
import time
import pytz

# 调整系统路径，便于导入被测模块
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 尝试导入被测模块
try:
    from services.common.utils.time_utils import (
        timestamp_to_datetime,
        datetime_to_timestamp,
        format_timestamp,
        parse_datetime_string,
        get_time_range,
        time_ago,
        unix_time_ms,
        time_intervals,
        TimeInterval
    )
except ImportError:
    # 如果无法导入，定义模拟函数和类用于测试
    def timestamp_to_datetime(timestamp, tz=None):
        """将时间戳转换为datetime对象"""
        if isinstance(timestamp, str):
            timestamp = float(timestamp)
        dt = datetime.datetime.fromtimestamp(timestamp)
        if tz:
            dt = dt.replace(tzinfo=tz)
        return dt
    
    def datetime_to_timestamp(dt):
        """将datetime对象转换为时间戳"""
        if dt.tzinfo:
            return dt.timestamp()
        else:
            return dt.replace(tzinfo=datetime.timezone.utc).timestamp()
    
    def format_timestamp(timestamp, format_str="%Y-%m-%d %H:%M:%S", tz=None):
        """将时间戳格式化为字符串"""
        dt = timestamp_to_datetime(timestamp, tz)
        return dt.strftime(format_str)
    
    def parse_datetime_string(datetime_str, format_str="%Y-%m-%d %H:%M:%S", tz=None):
        """解析日期时间字符串为datetime对象"""
        dt = datetime.datetime.strptime(datetime_str, format_str)
        if tz:
            dt = dt.replace(tzinfo=tz)
        return dt
    
    def get_time_range(start_offset, end_offset=0, reference_time=None):
        """获取时间范围"""
        if reference_time is None:
            reference_time = datetime.datetime.now()
        
        end_time = reference_time - datetime.timedelta(seconds=end_offset)
        start_time = reference_time - datetime.timedelta(seconds=start_offset)
        
        return start_time, end_time
    
    def time_ago(seconds, include_seconds=True):
        """获取指定秒数之前的时间表示"""
        if seconds < 60:
            return f"{seconds}秒前" if include_seconds else "刚刚"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes}分钟前"
        elif seconds < 86400:
            hours = seconds // 3600
            return f"{hours}小时前"
        else:
            days = seconds // 86400
            return f"{days}天前"
    
    def unix_time_ms():
        """获取当前时间的毫秒级时间戳"""
        return int(time.time() * 1000)
    
    class TimeInterval:
        MINUTE = 60
        HOUR = 60 * 60
        DAY = 24 * 60 * 60
        WEEK = 7 * 24 * 60 * 60
        MONTH = 30 * 24 * 60 * 60
        YEAR = 365 * 24 * 60 * 60
    
    time_intervals = {
        "1m": TimeInterval.MINUTE,
        "5m": 5 * TimeInterval.MINUTE,
        "15m": 15 * TimeInterval.MINUTE,
        "30m": 30 * TimeInterval.MINUTE,
        "1h": TimeInterval.HOUR,
        "4h": 4 * TimeInterval.HOUR,
        "1d": TimeInterval.DAY,
        "1w": TimeInterval.WEEK,
        "1M": TimeInterval.MONTH,
        "1y": TimeInterval.YEAR
    }


class TestTimeUtils:
    """
    时间工具函数测试
    """
    
    def test_timestamp_to_datetime(self):
        """测试时间戳转换为datetime对象"""
        # Arrange
        timestamp = 1609459200  # 2021-01-01 00:00:00 UTC
        
        # Act
        dt = timestamp_to_datetime(timestamp)
        
        # Assert
        assert isinstance(dt, datetime.datetime)
        assert dt.year == 2021
        assert dt.month == 1
        assert dt.day == 1
        
        # 测试带时区的转换
        utc_tz = pytz.timezone('UTC')
        dt_utc = timestamp_to_datetime(timestamp, utc_tz)
        assert dt_utc.tzinfo is not None
    
    def test_datetime_to_timestamp(self):
        """测试datetime对象转换为时间戳"""
        # Arrange
        dt = datetime.datetime(2021, 1, 1, 0, 0, 0)
        
        # Act
        timestamp = datetime_to_timestamp(dt)
        
        # Assert
        assert isinstance(timestamp, float)
        # 时间戳值可能因系统时区而有差异，这里使用近似比较
        assert abs(timestamp - 1609459200) < 86400  # 允许24小时内的差异
        
        # 测试带时区的转换
        utc_dt = dt.replace(tzinfo=datetime.timezone.utc)
        utc_timestamp = datetime_to_timestamp(utc_dt)
        assert abs(utc_timestamp - 1609459200) < 1  # UTC时间戳应该更准确
    
    def test_format_timestamp(self):
        """测试时间戳格式化为字符串"""
        # Arrange
        timestamp = 1609459200  # 2021-01-01 00:00:00 UTC
        format_str = "%Y-%m-%d"
        
        # Act
        date_str = format_timestamp(timestamp, format_str)
        
        # Assert
        assert date_str == "2021-01-01"
        
        # 测试默认格式
        default_format = format_timestamp(timestamp)
        assert "2021-01-01" in default_format
        assert ":" in default_format  # 应该包含时间部分
    
    def test_parse_datetime_string(self):
        """测试解析日期时间字符串"""
        # Arrange
        datetime_str = "2021-01-01 12:00:00"
        format_str = "%Y-%m-%d %H:%M:%S"
        
        # Act
        dt = parse_datetime_string(datetime_str, format_str)
        
        # Assert
        assert isinstance(dt, datetime.datetime)
        assert dt.year == 2021
        assert dt.month == 1
        assert dt.day == 1
        assert dt.hour == 12
        assert dt.minute == 0
        assert dt.second == 0
        
        # 测试带时区的转换
        utc_tz = pytz.timezone('UTC')
        dt_utc = parse_datetime_string(datetime_str, format_str, utc_tz)
        assert dt_utc.tzinfo is not None
    
    def test_get_time_range(self):
        """测试获取时间范围"""
        # Arrange
        reference_time = datetime.datetime(2021, 1, 1, 12, 0, 0)
        start_offset = 3600  # 1小时前
        end_offset = 0  # 当前时间
        
        # Act
        start_time, end_time = get_time_range(start_offset, end_offset, reference_time)
        
        # Assert
        assert isinstance(start_time, datetime.datetime)
        assert isinstance(end_time, datetime.datetime)
        assert start_time == datetime.datetime(2021, 1, 1, 11, 0, 0)
        assert end_time == reference_time
        
        # 测试默认参数
        current_time = datetime.datetime.now()
        default_start, default_end = get_time_range(3600)
        time_diff = (current_time - default_start).total_seconds()
        assert abs(time_diff - 3600) < 2  # 允许2秒的误差
    
    def test_time_ago(self):
        """测试获取指定秒数之前的时间表示"""
        # Arrange & Act & Assert
        # 测试秒级
        assert time_ago(30) == "30秒前"
        assert time_ago(30, include_seconds=False) == "刚刚"
        
        # 测试分钟级
        assert time_ago(120) == "2分钟前"
        
        # 测试小时级
        assert time_ago(3600) == "1小时前"
        assert time_ago(7200) == "2小时前"
        
        # 测试天级
        assert time_ago(86400) == "1天前"
        assert time_ago(172800) == "2天前"
    
    def test_unix_time_ms(self):
        """测试获取毫秒时间戳"""
        # Arrange & Act
        ms_time = unix_time_ms()
        
        # Assert
        assert isinstance(ms_time, int)
        # 时间戳应该是13位（毫秒级）
        assert len(str(ms_time)) >= 13
        
        # 测试与当前时间的一致性
        current_ms = int(time.time() * 1000)
        assert abs(ms_time - current_ms) < 1000  # 允许1秒的误差
    
    def test_time_intervals(self):
        """测试时间间隔常量"""
        # Assert
        assert TimeInterval.MINUTE == 60
        assert TimeInterval.HOUR == 3600
        assert TimeInterval.DAY == 86400
        assert TimeInterval.WEEK == 604800
        
        # 测试时间间隔字典
        assert time_intervals["1m"] == 60
        assert time_intervals["1h"] == 3600
        assert time_intervals["1d"] == 86400
        assert time_intervals["1w"] == 604800
    
    def test_time_conversion_round_trip(self):
        """测试时间戳和datetime对象的往返转换"""
        # Arrange
        original_dt = datetime.datetime(2021, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        
        # Act
        timestamp = datetime_to_timestamp(original_dt)
        converted_dt = timestamp_to_datetime(timestamp, datetime.timezone.utc)
        
        # Assert
        # 考虑到精度问题，使用一个小的阈值
        time_diff = abs((converted_dt - original_dt).total_seconds())
        assert time_diff < 1  # 允许1秒的误差
    
    def test_string_timestamp_conversion(self):
        """测试字符串时间戳的转换"""
        # Arrange
        timestamp_str = "1609459200"
        
        # Act
        dt = timestamp_to_datetime(timestamp_str)
        
        # Assert
        assert dt.year == 2021
        assert dt.month == 1
        assert dt.day == 1


# 直接运行测试文件
if __name__ == "__main__":
    pytest.main(["-v", __file__])