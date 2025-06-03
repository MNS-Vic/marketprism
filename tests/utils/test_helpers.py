"""
MarketPrism测试助手函数

提供测试中常用的辅助功能
"""
import os
import sys
import time
import json
import asyncio
import datetime
import pytest
import random
import tempfile
import contextlib
from pathlib import Path
from typing import Dict, List, Any, Callable, Optional, Union, Tuple
import socket
import shutil
# Mock导入已移除 - 请使用真实的服务和数据进行测试
import logging
from contextlib import contextmanager, asynccontextmanager
import yaml

# 添加项目根目录到系统路径
project_root = Path(__file__).parent.parent.parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

class TestHelpers:
    """测试辅助函数集合"""
    
    @staticmethod
    def get_project_root() -> Path:
        """获取项目根目录"""
        return project_root
    
    @staticmethod
    def get_absolute_path(relative_path: str) -> str:
        """获取相对于项目根目录的绝对路径"""
        return str(project_root / relative_path)
    
    @staticmethod
    def get_test_file_path(filename: str) -> str:
        """获取测试文件目录下的文件路径"""
        return str(project_root / "tests" / "fixtures" / filename)
    
    @staticmethod
    def load_test_data(filename: str) -> Any:
        """
        从fixtures目录加载测试数据文件
        
        Args:
            filename: 文件名
            
        Returns:
            加载的数据对象
        """
        filepath = TestHelpers.get_test_file_path(filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
            
    @staticmethod
    def save_test_data(data: Any, filename: str) -> str:
        """
        保存测试数据到fixtures目录
        
        Args:
            data: 要保存的数据
            filename: 文件名
            
        Returns:
            保存的文件路径
        """
        filepath = TestHelpers.get_test_file_path(filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            if isinstance(data, (dict, list)):
                json.dump(data, f, indent=2)
            else:
                f.write(str(data))
                
        return filepath
        
    @staticmethod
    @contextlib.contextmanager
    def create_temp_file(content: str = None, suffix: str = None) -> str:
        """
        创建临时文件
        
        Args:
            content: 文件内容
            suffix: 文件后缀
            
        Yields:
            临时文件路径
        """
        with tempfile.NamedTemporaryFile(mode='w+', 
                                        delete=False, 
                                        suffix=suffix, 
                                        encoding='utf-8') as tmp:
            if content:
                tmp.write(content)
                
            yield tmp.name
            
        # 删除临时文件
        try:
            os.unlink(tmp.name)
        except:
            pass
            
    @staticmethod
    @contextlib.contextmanager
    def create_temp_dir() -> str:
        """
        创建临时目录
        
        Yields:
            临时目录路径
        """
        tmp_dir = tempfile.mkdtemp()
        yield tmp_dir
        
        # 删除临时目录
        try:
            import shutil
            shutil.rmtree(tmp_dir)
        except:
            pass
            
    @staticmethod
    def wait_for(condition_func: Callable[[], bool], 
                timeout: float = 10.0, 
                interval: float = 0.1) -> bool:
        """
        等待条件满足
        
        Args:
            condition_func: 条件函数，返回True表示条件满足
            timeout: 超时时间（秒）
            interval: 检查间隔（秒）
            
        Returns:
            bool: 是否在超时前满足条件
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            if condition_func():
                return True
            time.sleep(interval)
        return False
        
    @staticmethod
    async def async_wait_for(condition_func: Callable[[], bool], 
                            timeout: float = 10.0, 
                            interval: float = 0.1) -> bool:
        """
        异步等待条件满足
        
        Args:
            condition_func: 条件函数，返回True表示条件满足
            timeout: 超时时间（秒）
            interval: 检查间隔（秒）
            
        Returns:
            bool: 是否在超时前满足条件
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            if await condition_func() if asyncio.iscoroutinefunction(condition_func) else condition_func():
                return True
            await asyncio.sleep(interval)
        return False
        
    @staticmethod
    def find_free_port() -> int:
        """
        查找可用的网络端口
        
        Returns:
            int: 可用端口号
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]
            
    @staticmethod
    def get_time_range(days: int = 0, 
                      hours: int = 0, 
                      minutes: int = 0, 
                      seconds: int = 0, 
                      end_time: Union[datetime.datetime, float, None] = None) -> Tuple[float, float]:
        """
        获取时间范围（开始和结束时间戳）
        
        Args:
            days: 天数
            hours: 小时数
            minutes: 分钟数
            seconds: 秒数
            end_time: 结束时间，如未指定则使用当前时间
            
        Returns:
            Tuple[float, float]: (开始时间戳, 结束时间戳)
        """
        if end_time is None:
            end_time = datetime.datetime.now()
        elif isinstance(end_time, (int, float)):
            end_time = datetime.datetime.fromtimestamp(end_time)
            
        # 计算时间差
        delta = datetime.timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
        
        # 计算开始时间
        start_time = end_time - delta
        
        # 返回时间戳
        return start_time.timestamp(), end_time.timestamp()
        
    @staticmethod
    def setup_test_env(env_vars: Dict[str, str] = None) -> Dict[str, str]:
        """
        设置测试环境变量
        
        Args:
            env_vars: 要设置的环境变量字典
            
        Returns:
            Dict[str, str]: 原来的环境变量值
        """
        if not env_vars:
            return {}
            
        # 保存原来的环境变量值
        original_vars = {}
        
        for key, value in env_vars.items():
            if key in os.environ:
                original_vars[key] = os.environ[key]
            os.environ[key] = str(value)
            
        return original_vars
        
    @staticmethod
    def restore_env(original_vars: Dict[str, str]) -> None:
        """
        恢复环境变量
        
        Args:
            original_vars: 原来的环境变量值
        """
        for key, value in original_vars.items():
            os.environ[key] = value
            
    @staticmethod
    def compare_objects(obj1: Any, obj2: Any, 
                       exclude_keys: List[str] = None, 
                       float_tolerance: float = 0.0001) -> Tuple[bool, List[str]]:
        """
        比较两个对象是否相同
        
        Args:
            obj1: 第一个对象
            obj2: 第二个对象
            exclude_keys: 排除比较的键列表
            float_tolerance: 浮点数比较容差
            
        Returns:
            Tuple[bool, List[str]]: (是否相同, 差异说明列表)
        """
        exclude_keys = exclude_keys or []
        differences = []
        
        # 如果类型不同
        if type(obj1) != type(obj2):
            return False, [f"类型不同: {type(obj1)} != {type(obj2)}"]
            
        # 如果是字典
        if isinstance(obj1, dict):
            # 检查键集合
            keys1 = set(obj1.keys()) - set(exclude_keys)
            keys2 = set(obj2.keys()) - set(exclude_keys)
            
            if keys1 != keys2:
                extra_keys1 = keys1 - keys2
                extra_keys2 = keys2 - keys1
                if extra_keys1:
                    differences.append(f"对象1额外键: {extra_keys1}")
                if extra_keys2:
                    differences.append(f"对象2额外键: {extra_keys2}")
            
            # 递归比较共有的键
            for key in keys1.intersection(keys2):
                if key in exclude_keys:
                    continue
                    
                value_equal, value_diffs = TestHelpers.compare_objects(
                    obj1[key], obj2[key], exclude_keys, float_tolerance
                )
                
                if not value_equal:
                    differences.append(f"键'{key}'值不同: {value_diffs}")
                    
        # 如果是列表或元组
        elif isinstance(obj1, (list, tuple)):
            if len(obj1) != len(obj2):
                return False, [f"长度不同: {len(obj1)} != {len(obj2)}"]
                
            for i, (item1, item2) in enumerate(zip(obj1, obj2)):
                item_equal, item_diffs = TestHelpers.compare_objects(
                    item1, item2, exclude_keys, float_tolerance
                )
                
                if not item_equal:
                    differences.append(f"索引[{i}]处不同: {item_diffs}")
                    
        # 如果是浮点数
        elif isinstance(obj1, float) and isinstance(obj2, float):
            if abs(obj1 - obj2) > float_tolerance:
                differences.append(f"浮点值不同: {obj1} != {obj2}")
                
        # 其他类型直接比较
        elif obj1 != obj2:
            differences.append(f"值不同: {obj1} != {obj2}")
            
        return len(differences) == 0, differences
        
    @staticmethod
    def is_docker_available() -> bool:
        """
        检查Docker是否可用
        
        Returns:
            bool: Docker是否可用
        """
        try:
            import docker
            client = docker.from_env()
            client.ping()
            return True
        except:
            return False
            
    @staticmethod
    def is_nats_available(host: str = "localhost", port: int = 4222) -> bool:
        """
        检查NATS服务是否可用
        
        Args:
            host: NATS主机
            port: NATS端口
            
        Returns:
            bool: NATS是否可用
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.connect((host, port))
                return True
        except:
            return False
            
    @staticmethod
    def is_clickhouse_available(host: str = "localhost", port: int = 9000) -> bool:
        """
        检查ClickHouse服务是否可用
        
        Args:
            host: ClickHouse主机
            port: ClickHouse端口
            
        Returns:
            bool: ClickHouse是否可用
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.connect((host, port))
                return True
        except:
            return False
            
# 全局实例，便于直接导入使用
test_helpers = TestHelpers()

class TestEnvironment:
    """测试环境管理器"""
    
    def __init__(self):
        self.temp_dirs = []
        self.temp_files = []
        self.original_env = {}
    
    def create_temp_dir(self, prefix: str = 'test_') -> str:
        """创建临时目录"""
        temp_dir = tempfile.mkdtemp(prefix=prefix)
        self.temp_dirs.append(temp_dir)
        return temp_dir
    
    def create_temp_file(self, content: str = '', suffix: str = '.txt', prefix: str = 'test_') -> str:
        """创建临时文件"""
        fd, temp_file = tempfile.mkstemp(suffix=suffix, prefix=prefix)
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(content)
        except:
            os.close(fd)
            raise
        
        self.temp_files.append(temp_file)
        return temp_file
    
    def create_temp_json_file(self, data: Dict, prefix: str = 'test_') -> str:
        """创建临时JSON文件"""
        content = json.dumps(data, indent=2)
        return self.create_temp_file(content, suffix='.json', prefix=prefix)
    
    def create_temp_yaml_file(self, data: Dict, prefix: str = 'test_') -> str:
        """创建临时YAML文件"""
        content = yaml.dump(data, default_flow_style=False)
        return self.create_temp_file(content, suffix='.yaml', prefix=prefix)
    
    def set_env_var(self, key: str, value: str):
        """设置环境变量"""
        if key not in self.original_env:
            self.original_env[key] = os.environ.get(key)
        os.environ[key] = value
    
    # patch_object方法已移除 - 请使用真实的对象和服务进行测试
    
    def cleanup(self):
        """清理测试环境"""
        # patches相关代码已移除
        
        # 恢复环境变量
        for key, original_value in self.original_env.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value
        self.original_env.clear()
        
        # 删除临时文件
        for temp_file in self.temp_files:
            try:
                os.unlink(temp_file)
            except:
                pass
        self.temp_files.clear()
        
        # 删除临时目录
        for temp_dir in self.temp_dirs:
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
        self.temp_dirs.clear()


@contextmanager
def test_environment():
    """测试环境上下文管理器"""
    env = TestEnvironment()
    try:
        yield env
    finally:
        env.cleanup()


class AsyncTestHelper:
    """异步测试辅助工具"""
    
    @staticmethod
    async def wait_for_condition(
        condition: Callable[[], bool],
        timeout: float = 5.0,
        interval: float = 0.1,
        error_message: str = "Condition not met within timeout"
    ) -> bool:
        """等待条件满足"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if condition():
                return True
            await asyncio.sleep(interval)
        
        raise TimeoutError(error_message)
    
    @staticmethod
    async def wait_for_async_condition(
        condition: Callable[[], Any],
        timeout: float = 5.0,
        interval: float = 0.1,
        error_message: str = "Async condition not met within timeout"
    ) -> bool:
        """等待异步条件满足"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if await condition():
                return True
            await asyncio.sleep(interval)
        
        raise TimeoutError(error_message)
    
    @staticmethod
    async def run_with_timeout(coro, timeout: float = 5.0):
        """运行协程并设置超时"""
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Operation timed out after {timeout} seconds")


class DataAssertions:
    """数据断言工具"""
    
    @staticmethod
    def assert_trade_data_valid(trade_data: Dict):
        """断言交易数据有效"""
        required_fields = ['exchange', 'symbol', 'price', 'amount', 'timestamp', 'side']
        
        for field in required_fields:
            assert field in trade_data, f"Missing required field: {field}"
        
        assert isinstance(trade_data['price'], (int, float)), "Price must be numeric"
        assert trade_data['price'] > 0, "Price must be positive"
        
        assert isinstance(trade_data['amount'], (int, float)), "Amount must be numeric"
        assert trade_data['amount'] > 0, "Amount must be positive"
        
        assert isinstance(trade_data['timestamp'], (int, float)), "Timestamp must be numeric"
        assert trade_data['timestamp'] > 0, "Timestamp must be positive"
        
        assert trade_data['side'] in ['buy', 'sell'], "Side must be 'buy' or 'sell'"
    
    @staticmethod
    def assert_orderbook_data_valid(orderbook_data: Dict):
        """断言订单簿数据有效"""
        required_fields = ['exchange', 'symbol', 'bids', 'asks', 'timestamp']
        
        for field in required_fields:
            assert field in orderbook_data, f"Missing required field: {field}"
        
        assert isinstance(orderbook_data['bids'], list), "Bids must be a list"
        assert isinstance(orderbook_data['asks'], list), "Asks must be a list"
        
        # 检查买单格式
        for bid in orderbook_data['bids']:
            assert isinstance(bid, list), "Each bid must be a list"
            assert len(bid) >= 2, "Each bid must have at least price and amount"
            assert isinstance(bid[0], (int, float)), "Bid price must be numeric"
            assert isinstance(bid[1], (int, float)), "Bid amount must be numeric"
            assert bid[0] > 0, "Bid price must be positive"
            assert bid[1] > 0, "Bid amount must be positive"
        
        # 检查卖单格式
        for ask in orderbook_data['asks']:
            assert isinstance(ask, list), "Each ask must be a list"
            assert len(ask) >= 2, "Each ask must have at least price and amount"
            assert isinstance(ask[0], (int, float)), "Ask price must be numeric"
            assert isinstance(ask[1], (int, float)), "Ask amount must be numeric"
            assert ask[0] > 0, "Ask price must be positive"
            assert ask[1] > 0, "Ask amount must be positive"
        
        # 检查价格顺序
        if len(orderbook_data['bids']) > 1:
            for i in range(1, len(orderbook_data['bids'])):
                assert orderbook_data['bids'][i-1][0] >= orderbook_data['bids'][i][0], \
                    "Bids must be sorted in descending order"
        
        if len(orderbook_data['asks']) > 1:
            for i in range(1, len(orderbook_data['asks'])):
                assert orderbook_data['asks'][i-1][0] <= orderbook_data['asks'][i][0], \
                    "Asks must be sorted in ascending order"
    
    @staticmethod
    def assert_ticker_data_valid(ticker_data: Dict):
        """断言行情数据有效"""
        required_fields = ['exchange', 'symbol', 'timestamp']
        
        for field in required_fields:
            assert field in ticker_data, f"Missing required field: {field}"
        
        # 检查OHLCV字段（如果存在）
        ohlcv_fields = ['open', 'high', 'low', 'close', 'volume']
        for field in ohlcv_fields:
            if field in ticker_data:
                assert isinstance(ticker_data[field], (int, float)), f"{field} must be numeric"
                assert ticker_data[field] >= 0, f"{field} must be non-negative"
        
        # 检查价格逻辑
        if all(field in ticker_data for field in ['open', 'high', 'low', 'close']):
            assert ticker_data['high'] >= ticker_data['open'], "High must be >= open"
            assert ticker_data['high'] >= ticker_data['close'], "High must be >= close"
            assert ticker_data['low'] <= ticker_data['open'], "Low must be <= open"
            assert ticker_data['low'] <= ticker_data['close'], "Low must be <= close"
    
    @staticmethod
    def assert_data_freshness(data: Dict, max_age_seconds: float = 300):
        """断言数据新鲜度"""
        assert 'timestamp' in data, "Data must have timestamp field"
        
        current_time = time.time()
        data_age = current_time - data['timestamp']
        
        assert data_age <= max_age_seconds, \
            f"Data is too old: {data_age:.2f}s > {max_age_seconds}s"
    
    @staticmethod
    def assert_data_consistency(data_list: List[Dict], field: str):
        """断言数据一致性"""
        if not data_list:
            return
        
        first_value = data_list[0].get(field)
        for i, data in enumerate(data_list[1:], 1):
            assert data.get(field) == first_value, \
                f"Inconsistent {field} at index {i}: {data.get(field)} != {first_value}"


class PerformanceAssertions:
    """性能断言工具"""
    
    @staticmethod
    def assert_execution_time(func: Callable, max_time: float, *args, **kwargs):
        """断言执行时间"""
        start_time = time.time()
        result = func(*args, **kwargs)
        execution_time = time.time() - start_time
        
        assert execution_time <= max_time, \
            f"Execution time {execution_time:.3f}s exceeds limit {max_time}s"
        
        return result
    
    @staticmethod
    async def assert_async_execution_time(coro, max_time: float):
        """断言异步执行时间"""
        start_time = time.time()
        result = await coro
        execution_time = time.time() - start_time
        
        assert execution_time <= max_time, \
            f"Async execution time {execution_time:.3f}s exceeds limit {max_time}s"
        
        return result
    
    @staticmethod
    def assert_memory_usage(func: Callable, max_memory_mb: float, *args, **kwargs):
        """断言内存使用量"""
        try:
            import psutil
            import os
            
            process = psutil.Process(os.getpid())
            memory_before = process.memory_info().rss / 1024 / 1024  # MB
            
            result = func(*args, **kwargs)
            
            memory_after = process.memory_info().rss / 1024 / 1024  # MB
            memory_used = memory_after - memory_before
            
            assert memory_used <= max_memory_mb, \
                f"Memory usage {memory_used:.2f}MB exceeds limit {max_memory_mb}MB"
            
            return result
        except ImportError:
            pytest.skip("psutil not available for memory testing")


class LogCapture:
    """日志捕获工具"""
    
    def __init__(self, logger_name: str = None, level: int = logging.INFO):
        self.logger_name = logger_name
        self.level = level
        self.records = []
        self.handler = None
        self.logger = None
    
    def __enter__(self):
        self.handler = logging.Handler()
        self.handler.emit = lambda record: self.records.append(record)
        
        if self.logger_name:
            self.logger = logging.getLogger(self.logger_name)
        else:
            self.logger = logging.getLogger()
        
        self.logger.addHandler(self.handler)
        self.logger.setLevel(self.level)
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.logger and self.handler:
            self.logger.removeHandler(self.handler)
    
    def get_messages(self, level: int = None) -> List[str]:
        """获取日志消息"""
        if level is None:
            return [record.getMessage() for record in self.records]
        else:
            return [record.getMessage() for record in self.records if record.levelno >= level]
    
    def assert_log_contains(self, message: str, level: int = None):
        """断言日志包含特定消息"""
        messages = self.get_messages(level)
        assert any(message in msg for msg in messages), \
            f"Log message '{message}' not found in: {messages}"
    
    def assert_log_count(self, expected_count: int, level: int = None):
        """断言日志数量"""
        messages = self.get_messages(level)
        assert len(messages) == expected_count, \
            f"Expected {expected_count} log messages, got {len(messages)}"


class DatabaseTestHelper:
    """数据库测试辅助工具"""
    
    @staticmethod
    def create_test_table_sql(table_name: str, columns: Dict[str, str]) -> str:
        """创建测试表SQL"""
        column_definitions = []
        for col_name, col_type in columns.items():
            column_definitions.append(f"{col_name} {col_type}")
        
        return f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(column_definitions)})"
    
    @staticmethod
    def generate_insert_sql(table_name: str, data: List[Dict]) -> str:
        """生成插入SQL"""
        if not data:
            return ""
        
        columns = list(data[0].keys())
        column_names = ', '.join(columns)
        
        values_list = []
        for row in data:
            values = []
            for col in columns:
                value = row[col]
                if isinstance(value, str):
                    values.append(f"'{value}'")
                elif value is None:
                    values.append("NULL")
                else:
                    values.append(str(value))
            values_list.append(f"({', '.join(values)})")
        
        values_clause = ', '.join(values_list)
        return f"INSERT INTO {table_name} ({column_names}) VALUES {values_clause}"


class NetworkTestHelper:
    """网络测试辅助工具"""
    
    @staticmethod
    def find_free_port() -> int:
        """查找可用端口"""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]
    
    @staticmethod
    def is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
        """检查端口是否开放"""
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                result = s.connect_ex((host, port))
                return result == 0
        except:
            return False
    
    @staticmethod
    async def wait_for_port(host: str, port: int, timeout: float = 30.0):
        """等待端口开放"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if NetworkTestHelper.is_port_open(host, port):
                return True
            await asyncio.sleep(0.5)
        
        raise TimeoutError(f"Port {host}:{port} not available within {timeout}s")


# 便捷函数
def create_test_config(overrides: Dict = None) -> Dict:
    """创建测试配置"""
    default_config = {
        'database': {
            'host': 'localhost',
            'port': 9000,
            'database': 'test_marketprism'
        },
        'nats': {
            'servers': ['nats://localhost:4222'],
            'max_reconnect_attempts': 3
        },
        'exchanges': {
            'binance': {
                'enabled': True,
                'sandbox': True
            }
        },
        'logging': {
            'level': 'DEBUG'
        }
    }
    
    if overrides:
        default_config.update(overrides)
    
    return default_config


def assert_valid_uuid(value: str):
    """断言有效的UUID"""
    import uuid
    try:
        uuid.UUID(value)
    except ValueError:
        raise AssertionError(f"Invalid UUID: {value}")


def assert_valid_timestamp(timestamp: Union[int, float], tolerance: float = 300):
    """断言有效的时间戳"""
    current_time = time.time()
    assert abs(current_time - timestamp) <= tolerance, \
        f"Timestamp {timestamp} is too far from current time {current_time}"


def assert_json_schema(data: Dict, schema: Dict):
    """断言JSON模式"""
    try:
        import jsonschema
        jsonschema.validate(data, schema)
    except ImportError:
        pytest.skip("jsonschema not available for schema validation")
    except jsonschema.ValidationError as e:
        raise AssertionError(f"JSON schema validation failed: {e}")


@asynccontextmanager
async def async_test_timeout(timeout: float = 10.0):
    """异步测试超时上下文管理器"""
    try:
        async with asyncio.timeout(timeout):
            yield
    except asyncio.TimeoutError:
        raise TimeoutError(f"Test timed out after {timeout} seconds")