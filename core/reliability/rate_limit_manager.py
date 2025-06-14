"""
MarketPrism Core Rate Limit Manager

基于真实交易所API文档的精确限流管理器
支持权重系统、端点特定限制、IP保护等高级功能

参考文档：
- Binance API 限制: https://developers.binance.com/docs/zh-CN/binance-spot-api-docs/rest-api/limits
- OKX API 限制: https://www.okx.com/docs-v5/en/#overview-rate-limit
- Deribit API 限制: https://docs.deribit.com/#rate-limits
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List, Callable, Union, Tuple
from datetime import datetime, timedelta, timezone
from functools import wraps
from dataclasses import dataclass, field
from enum import Enum
import threading
import json
from collections import defaultdict, deque

# Core模块导入
try:
    from ..monitoring import get_global_monitoring
    from ..errors import get_global_error_handler, MarketPrismError, ErrorSeverity, ErrorCategory
    CORE_AVAILABLE = True
except ImportError:
    CORE_AVAILABLE = False
    logging.warning("Core监控和错误处理模块不可用，使用降级实现")


class ExchangeType(Enum):
    """交易所类型"""
    BINANCE = "binance"
    OKX = "okx"
    DERIBIT = "deribit"
    BYBIT = "bybit"


class RequestType(Enum):
    """请求类型"""
    # 市场数据类
    MARKET_DATA = "market_data"
    ORDERBOOK_SNAPSHOT = "orderbook_snapshot"
    TRADE_HISTORY = "trade_history"
    KLINE_DATA = "kline_data"
    TICKER_DATA = "ticker_data"
    
    # 账户类
    ACCOUNT_INFO = "account_info"
    ORDER_HISTORY = "order_history"
    
    # 特殊数据类
    TOP_TRADER_DATA = "top_trader_data"
    FUNDING_RATE = "funding_rate"
    OPEN_INTEREST = "open_interest"
    
    # 系统类
    SYSTEM_STATUS = "system_status"
    EXCHANGE_INFO = "exchange_info"
    
    OTHER = "other"


class RequestPriority(Enum):
    """请求优先级"""
    CRITICAL = "critical"    # 关键业务请求
    HIGH = "high"           # 高优先级
    MEDIUM = "medium"       # 中等优先级
    LOW = "low"            # 低优先级
    BACKGROUND = "background"  # 后台任务


@dataclass
class EndpointConfig:
    """端点配置"""
    path: str
    weight: int = 1
    requests_per_minute: Optional[int] = None
    requests_per_second: Optional[int] = None
    data_source: str = "缓存"  # 撮合引擎、缓存、数据库
    
    # 特殊限制
    auth_required: bool = False
    account_based: bool = False  # 是否基于账户限制
    
    # 优化建议
    recommended_interval: float = 1.0  # 建议请求间隔（秒）
    max_batch_size: Optional[int] = None


@dataclass
class ExchangeRateLimitConfig:
    """交易所精确限流配置 - 基于官方文档"""
    exchange: ExchangeType
    
    # 基础限制
    ip_requests_per_minute: int
    ip_requests_per_second: Optional[int] = None
    
    # 权重系统（如Binance）
    weight_based: bool = False
    max_weight_per_minute: Optional[int] = None
    weight_reset_interval: int = 60  # 权重重置间隔（秒）
    
    # 账户限制
    account_requests_per_minute: Optional[int] = None
    order_requests_per_minute: Optional[int] = None
    
    # 安全配置
    ip_ban_threshold_429: int = 100  # 触发429后的危险阈值
    ip_ban_threshold_418: int = 200  # 触发418的阈值
    ban_duration_minutes: Tuple[int, int] = (2, 4320)  # 最短2分钟，最长3天
    
    # 端点配置
    endpoints: Dict[str, EndpointConfig] = field(default_factory=dict)
    
    # 特殊规则
    websocket_connection_limit: Optional[int] = None
    websocket_message_per_second: Optional[int] = None
    
    # 监控响应头
    weight_header_pattern: Optional[str] = None
    order_count_header_pattern: Optional[str] = None
    retry_after_header: str = "Retry-After"


class RateLimitViolation(Exception):
    """限流违规异常"""
    def __init__(self, message: str, wait_time: float = 0, exchange: str = None, endpoint: str = None):
        super().__init__(message)
        self.wait_time = wait_time
        self.exchange = exchange
        self.endpoint = endpoint


class RequestTracker:
    """请求跟踪器"""
    
    def __init__(self, window_size: int = 60):
        self.window_size = window_size
        self.requests = deque()
        self.weights = deque()
        self.lock = threading.RLock()
    
    def add_request(self, weight: int = 1):
        """添加请求记录"""
        current_time = time.time()
        with self.lock:
            self.requests.append(current_time)
            self.weights.append(weight)
            self._cleanup_old_requests(current_time)
    
    def get_current_rate(self) -> Tuple[int, int]:
        """获取当前请求率 (请求数, 总权重)"""
        current_time = time.time()
        with self.lock:
            self._cleanup_old_requests(current_time)
            return len(self.requests), sum(self.weights)
    
    def _cleanup_old_requests(self, current_time: float):
        """清理过期请求"""
        cutoff_time = current_time - self.window_size
        while self.requests and self.requests[0] < cutoff_time:
            self.requests.popleft()
            self.weights.popleft()


class ExchangeRateLimitManager:
    """单个交易所限流管理器"""
    
    def __init__(self, config: ExchangeRateLimitConfig):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{config.exchange.value}")
        
        # 请求跟踪器
        self.ip_tracker = RequestTracker(60)  # IP级别，按分钟
        self.ip_tracker_second = RequestTracker(1)  # IP级别，按秒
        self.account_tracker = RequestTracker(60) if config.account_requests_per_minute else None
        
        # 端点特定跟踪器
        self.endpoint_trackers: Dict[str, RequestTracker] = {}
        
        # 权重跟踪（如果适用）
        self.weight_tracker = RequestTracker(config.weight_reset_interval) if config.weight_based else None
        
        # 状态跟踪
        self.consecutive_failures = 0
        self.last_429_time: Optional[float] = None
        self.last_418_time: Optional[float] = None
        self.emergency_backoff_until: Optional[float] = None
        
        # 响应头监控
        self.last_weight_header: Optional[int] = None
        self.last_order_count_header: Optional[int] = None
        
        # 锁
        self.lock = threading.RLock()
    
    async def acquire_permit(self, 
                           request_type: RequestType,
                           endpoint: Optional[str] = None,
                           priority: RequestPriority = RequestPriority.MEDIUM,
                           account_based: bool = False) -> Dict[str, Any]:
        """获取请求许可"""
        
        current_time = time.time()
        
        # 检查紧急退避
        if self.emergency_backoff_until and current_time < self.emergency_backoff_until:
            wait_time = self.emergency_backoff_until - current_time
            return {
                'granted': False,
                'reason': 'Emergency backoff active',
                'wait_time': wait_time,
                'retry_after': wait_time
            }
        
        # 获取端点配置
        endpoint_config = self.config.endpoints.get(endpoint) if endpoint else None
        request_weight = endpoint_config.weight if endpoint_config else 1
        
        with self.lock:
            # 检查IP级别限制
            ip_check = self._check_ip_limits(request_weight)
            if not ip_check['allowed']:
                return {
                    'granted': False,
                    'reason': ip_check['reason'],
                    'wait_time': ip_check['wait_time'],
                    'retry_after': ip_check['wait_time']
                }
            
            # 检查权重限制（如Binance）
            if self.config.weight_based and self.weight_tracker:
                weight_check = self._check_weight_limits(request_weight)
                if not weight_check['allowed']:
                    return {
                        'granted': False,
                        'reason': weight_check['reason'],
                        'wait_time': weight_check['wait_time'],
                        'retry_after': weight_check['wait_time']
                    }
            
            # 检查账户级别限制
            if account_based and self.account_tracker:
                account_check = self._check_account_limits()
                if not account_check['allowed']:
                    return {
                        'granted': False,
                        'reason': account_check['reason'],
                        'wait_time': account_check['wait_time'],
                        'retry_after': account_check['wait_time']
                    }
            
            # 检查端点特定限制
            if endpoint_config and (endpoint_config.requests_per_minute or endpoint_config.requests_per_second):
                endpoint_check = self._check_endpoint_limits(endpoint, endpoint_config)
                if not endpoint_check['allowed']:
                    return {
                        'granted': False,
                        'reason': endpoint_check['reason'],
                        'wait_time': endpoint_check['wait_time'],
                        'retry_after': endpoint_check['wait_time']
                    }
            
            # 所有检查通过，记录请求
            self._record_request(request_weight, endpoint, account_based)
            
            return {
                'granted': True,
                'exchange': self.config.exchange.value,
                'request_type': request_type.value,
                'weight': request_weight,
                'endpoint': endpoint,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
    
    def _check_ip_limits(self, weight: int) -> Dict[str, Any]:
        """检查IP限制"""
        # 按分钟检查
        current_requests, current_weight = self.ip_tracker.get_current_rate()
        
        if current_requests >= self.config.ip_requests_per_minute:
            return {
                'allowed': False,
                'reason': f'IP minute limit exceeded: {current_requests}/{self.config.ip_requests_per_minute}',
                'wait_time': 60.0
            }
        
        # 按秒检查（如果配置了）
        if self.config.ip_requests_per_second:
            current_requests_sec, _ = self.ip_tracker_second.get_current_rate()
            if current_requests_sec >= self.config.ip_requests_per_second:
                return {
                    'allowed': False,
                    'reason': f'IP second limit exceeded: {current_requests_sec}/{self.config.ip_requests_per_second}',
                    'wait_time': 1.0
                }
        
        return {'allowed': True}
    
    def _check_weight_limits(self, weight: int) -> Dict[str, Any]:
        """检查权重限制（Binance专用）"""
        if not self.weight_tracker or not self.config.max_weight_per_minute:
            return {'allowed': True}
        
        _, current_weight = self.weight_tracker.get_current_rate()
        
        if current_weight + weight > self.config.max_weight_per_minute:
            return {
                'allowed': False,
                'reason': f'Weight limit exceeded: {current_weight + weight}/{self.config.max_weight_per_minute}',
                'wait_time': float(self.config.weight_reset_interval)
            }
        
        return {'allowed': True}
    
    def _check_account_limits(self) -> Dict[str, Any]:
        """检查账户限制"""
        if not self.account_tracker or not self.config.account_requests_per_minute:
            return {'allowed': True}
        
        current_requests, _ = self.account_tracker.get_current_rate()
        
        if current_requests >= self.config.account_requests_per_minute:
            return {
                'allowed': False,
                'reason': f'Account limit exceeded: {current_requests}/{self.config.account_requests_per_minute}',
                'wait_time': 60.0
            }
        
        return {'allowed': True}
    
    def _check_endpoint_limits(self, endpoint: str, config: EndpointConfig) -> Dict[str, Any]:
        """检查端点特定限制"""
        if endpoint not in self.endpoint_trackers:
            self.endpoint_trackers[endpoint] = RequestTracker(60)
        
        tracker = self.endpoint_trackers[endpoint]
        current_requests, _ = tracker.get_current_rate()
        
        if config.requests_per_minute and current_requests >= config.requests_per_minute:
            return {
                'allowed': False,
                'reason': f'Endpoint limit exceeded: {endpoint} {current_requests}/{config.requests_per_minute}',
                'wait_time': 60.0
            }
        
        # 检查秒级限制
        if config.requests_per_second:
            # 为简化，这里使用分钟级跟踪器，实际可以添加秒级跟踪器
            if current_requests > 0:  # 简化检查
                return {
                    'allowed': False,
                    'reason': f'Endpoint second limit: {endpoint}',
                    'wait_time': 1.0
                }
        
        return {'allowed': True}
    
    def _record_request(self, weight: int, endpoint: Optional[str], account_based: bool):
        """记录请求"""
        # IP级别记录
        self.ip_tracker.add_request(weight)
        self.ip_tracker_second.add_request(weight)
        
        # 权重记录
        if self.weight_tracker:
            self.weight_tracker.add_request(weight)
        
        # 账户级别记录
        if account_based and self.account_tracker:
            self.account_tracker.add_request(weight)
        
        # 端点记录
        if endpoint:
            if endpoint not in self.endpoint_trackers:
                self.endpoint_trackers[endpoint] = RequestTracker(60)
            self.endpoint_trackers[endpoint].add_request(weight)
    
    def record_response(self, 
                       status_code: int, 
                       headers: Dict[str, str] = None,
                       endpoint: Optional[str] = None):
        """记录响应"""
        
        # 监控响应头
        if headers:
            self._parse_response_headers(headers)
        
        # 处理错误状态码
        if status_code == 429:
            self._handle_429_response(headers, endpoint)
        elif status_code == 418:
            self._handle_418_response(headers, endpoint)
        elif 200 <= status_code < 300:
            # 成功响应，重置失败计数
            self.consecutive_failures = 0
        else:
            # 其他错误
            self.consecutive_failures += 1
    
    def _parse_response_headers(self, headers: Dict[str, str]):
        """解析响应头"""
        
        # Binance权重头
        if self.config.weight_header_pattern:
            for header_name, header_value in headers.items():
                if self.config.weight_header_pattern.lower() in header_name.lower():
                    try:
                        self.last_weight_header = int(header_value)
                    except ValueError:
                        pass
        
        # 订单计数头
        if self.config.order_count_header_pattern:
            for header_name, header_value in headers.items():
                if self.config.order_count_header_pattern.lower() in header_name.lower():
                    try:
                        self.last_order_count_header = int(header_value)
                    except ValueError:
                        pass
    
    def _handle_429_response(self, headers: Dict[str, str] = None, endpoint: str = None):
        """处理429响应"""
        self.last_429_time = time.time()
        self.consecutive_failures += 1
        
        # 提取Retry-After头
        retry_after = 60  # 默认1分钟
        if headers and self.config.retry_after_header in headers:
            try:
                retry_after = int(headers[self.config.retry_after_header])
            except ValueError:
                pass
        
        # 设置紧急退避
        self.emergency_backoff_until = time.time() + retry_after
        
        self.logger.warning(
            f"收到429响应",
            exchange=self.config.exchange.value,
            endpoint=endpoint,
            retry_after=retry_after,
            consecutive_failures=self.consecutive_failures
        )
    
    def _handle_418_response(self, headers: Dict[str, str] = None, endpoint: str = None):
        """处理418响应 - IP封禁"""
        self.last_418_time = time.time()
        
        # 提取ban时长
        ban_duration = 3600  # 默认1小时
        if headers and self.config.retry_after_header in headers:
            try:
                ban_duration = int(headers[self.config.retry_after_header])
            except ValueError:
                pass
        
        # 设置长期退避
        self.emergency_backoff_until = time.time() + ban_duration
        
        self.logger.critical(
            f"收到418响应 - IP被封禁",
            exchange=self.config.exchange.value,
            endpoint=endpoint,
            ban_duration=ban_duration
        )
        
        # 发送关键告警
        if CORE_AVAILABLE:
            error_handler = get_global_error_handler()
            if error_handler:
                error = MarketPrismError(
                    message=f"IP被{self.config.exchange.value}封禁",
                    severity=ErrorSeverity.CRITICAL,
                    category=ErrorCategory.EXTERNAL_SERVICE,
                    metadata={
                        'exchange': self.config.exchange.value,
                        'endpoint': endpoint,
                        'ban_duration': ban_duration
                    }
                )
                error_handler.handle_error(error)
    
    def get_status(self) -> Dict[str, Any]:
        """获取管理器状态"""
        current_time = time.time()
        ip_requests, ip_weight = self.ip_tracker.get_current_rate()
        
        status = {
            'exchange': self.config.exchange.value,
            'current_time': datetime.now(timezone.utc).isoformat(),
            'limits': {
                'ip_requests_per_minute': self.config.ip_requests_per_minute,
                'ip_requests_per_second': self.config.ip_requests_per_second,
                'max_weight_per_minute': self.config.max_weight_per_minute
            },
            'current_usage': {
                'ip_requests': ip_requests,
                'ip_weight': ip_weight
            },
            'safety_status': {
                'consecutive_failures': self.consecutive_failures,
                'last_429_time': self.last_429_time,
                'last_418_time': self.last_418_time,
                'emergency_backoff_until': self.emergency_backoff_until,
                'emergency_backoff_active': self.emergency_backoff_until and current_time < self.emergency_backoff_until
            },
            'response_headers': {
                'last_weight': self.last_weight_header,
                'last_order_count': self.last_order_count_header
            }
        }
        
        # 账户级别状态
        if self.account_tracker:
            account_requests, _ = self.account_tracker.get_current_rate()
            status['current_usage']['account_requests'] = account_requests
        
        # 权重使用率
        if self.config.weight_based and self.config.max_weight_per_minute:
            usage_rate = (ip_weight / self.config.max_weight_per_minute) * 100
            status['usage_percentage'] = {
                'weight': usage_rate,
                'risk_level': 'high' if usage_rate > 80 else 'medium' if usage_rate > 60 else 'low'
            }
        
        return status


class GlobalRateLimitManager:
    """全局限流管理器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.exchange_managers: Dict[ExchangeType, ExchangeRateLimitManager] = {}
        self.configs = self._load_exchange_configs()
        
        # 初始化交易所管理器
        for exchange, config in self.configs.items():
            self.exchange_managers[exchange] = ExchangeRateLimitManager(config)
        
        # 监控
        self.monitoring = get_global_monitoring() if CORE_AVAILABLE else None
        self.error_handler = get_global_error_handler() if CORE_AVAILABLE else None
    
    def _load_exchange_configs(self) -> Dict[ExchangeType, ExchangeRateLimitConfig]:
        """加载交易所配置 - 基于真实API文档"""
        configs = {}
        
        # === Binance配置 - 基于官方文档 ===
        binance_endpoints = {
            # 市场数据端点
            "/api/v3/depth": EndpointConfig(
                path="/api/v3/depth",
                weight=50,  # 根据depth参数：5-100: weight 1, 500: weight 5, 1000: weight 10, 5000: weight 50
                data_source="撮合引擎",
                recommended_interval=0.1
            ),
            "/api/v3/trades": EndpointConfig(
                path="/api/v3/trades",
                weight=1,
                data_source="缓存",
                recommended_interval=1.0
            ),
            "/api/v3/ticker/24hr": EndpointConfig(
                path="/api/v3/ticker/24hr",
                weight=1,  # 单个symbol weight 1, 无symbol weight 40
                data_source="缓存",
                recommended_interval=1.0
            ),
            "/api/v3/klines": EndpointConfig(
                path="/api/v3/klines",
                weight=1,
                data_source="数据库",
                recommended_interval=1.0
            ),
            "/api/v3/exchangeInfo": EndpointConfig(
                path="/api/v3/exchangeInfo",
                weight=10,
                data_source="缓存",
                recommended_interval=60.0
            ),
            # 账户相关端点
            "/api/v3/account": EndpointConfig(
                path="/api/v3/account",
                weight=10,
                auth_required=True,
                account_based=True,
                data_source="缓存 => 数据库"
            ),
            "/api/v3/order": EndpointConfig(
                path="/api/v3/order",
                weight=1,
                auth_required=True,
                account_based=True,
                data_source="数据库"
            ),
            # 大户持仓比例数据
            "/fapi/v1/topLongShortAccountRatio": EndpointConfig(
                path="/fapi/v1/topLongShortAccountRatio",
                weight=1,
                data_source="数据库",
                recommended_interval=300.0  # 5分钟间隔
            ),
            "/fapi/v1/topLongShortPositionRatio": EndpointConfig(
                path="/fapi/v1/topLongShortPositionRatio",
                weight=1,
                data_source="数据库",
                recommended_interval=300.0
            )
        }
        
        configs[ExchangeType.BINANCE] = ExchangeRateLimitConfig(
            exchange=ExchangeType.BINANCE,
            ip_requests_per_minute=1200,  # REST API 限制
            ip_requests_per_second=20,    # 突发限制
            weight_based=True,            # 使用权重系统
            max_weight_per_minute=6000,   # 权重限制
            account_requests_per_minute=180000,  # sapi接口的UID限制
            order_requests_per_minute=100,       # 下单限制
            ip_ban_threshold_429=1200,           # 429 后继续请求会导致 418
            ip_ban_threshold_418=2400,
            ban_duration_minutes=(2, 4320),      # 2分钟到3天
            endpoints=binance_endpoints,
            websocket_connection_limit=300,      # 每5分钟300次连接
            websocket_message_per_second=5,
            weight_header_pattern="X-MBX-USED-WEIGHT",
            order_count_header_pattern="X-MBX-ORDER-COUNT"
        )
        
        # === OKX配置 ===
        okx_endpoints = {
            "/api/v5/market/books": EndpointConfig(
                path="/api/v5/market/books",
                weight=1,
                requests_per_second=10,
                data_source="撮合引擎",
                recommended_interval=0.1
            ),
            "/api/v5/market/trades": EndpointConfig(
                path="/api/v5/market/trades",
                weight=1,
                requests_per_second=10,
                data_source="撮合引擎",
                recommended_interval=0.1
            ),
            "/api/v5/market/tickers": EndpointConfig(
                path="/api/v5/market/tickers",
                weight=1,
                requests_per_second=20,
                data_source="缓存",
                recommended_interval=1.0
            ),
            "/api/v5/market/candles": EndpointConfig(
                path="/api/v5/market/candles",
                weight=1,
                requests_per_second=20,
                data_source="缓存",
                recommended_interval=1.0
            )
        }
        
        configs[ExchangeType.OKX] = ExchangeRateLimitConfig(
            exchange=ExchangeType.OKX,
            ip_requests_per_minute=600,   # 相对保守的限制
            ip_requests_per_second=10,
            weight_based=False,
            endpoints=okx_endpoints,
            ip_ban_threshold_429=600,
            ip_ban_threshold_418=1200
        )
        
        # === Deribit配置 ===
        deribit_endpoints = {
            "/api/v2/public/get_order_book": EndpointConfig(
                path="/api/v2/public/get_order_book",
                weight=1,
                requests_per_second=5,
                recommended_interval=0.2
            ),
            "/api/v2/public/get_last_trades_by_instrument": EndpointConfig(
                path="/api/v2/public/get_last_trades_by_instrument",
                weight=1,
                requests_per_second=5,
                recommended_interval=1.0
            )
        }
        
        configs[ExchangeType.DERIBIT] = ExchangeRateLimitConfig(
            exchange=ExchangeType.DERIBIT,
            ip_requests_per_minute=300,   # 较低限制
            ip_requests_per_second=5,
            weight_based=False,
            endpoints=deribit_endpoints,
            ip_ban_threshold_429=300,
            ip_ban_threshold_418=600
        )
        
        return configs
    
    async def acquire_permit(self, 
                           exchange: Union[str, ExchangeType],
                           request_type: RequestType = RequestType.OTHER,
                           endpoint: Optional[str] = None,
                           priority: RequestPriority = RequestPriority.MEDIUM,
                           account_based: bool = False) -> Dict[str, Any]:
        """获取请求许可"""
        
        # 标准化交易所类型
        if isinstance(exchange, str):
            try:
                exchange = ExchangeType(exchange.lower())
            except ValueError:
                return {
                    'granted': False,
                    'reason': f'Unsupported exchange: {exchange}',
                    'wait_time': 0
                }
        
        if exchange not in self.exchange_managers:
            return {
                'granted': False,
                'reason': f'Exchange not configured: {exchange}',
                'wait_time': 0
            }
        
        # 委托给具体的交易所管理器
        manager = self.exchange_managers[exchange]
        result = await manager.acquire_permit(
            request_type=request_type,
            endpoint=endpoint,
            priority=priority,
            account_based=account_based
        )
        
        # 记录监控指标
        if self.monitoring:
            self.monitoring.collect_metric(
                "rate_limit_permit_requests",
                1,
                labels={
                    "exchange": exchange.value,
                    "request_type": request_type.value,
                    "granted": str(result['granted'])
                }
            )
        
        return result
    
    def record_response(self,
                       exchange: Union[str, ExchangeType],
                       status_code: int,
                       headers: Dict[str, str] = None,
                       endpoint: Optional[str] = None):
        """记录响应"""
        
        # 标准化交易所类型
        if isinstance(exchange, str):
            try:
                exchange = ExchangeType(exchange.lower())
            except ValueError:
                return
        
        if exchange not in self.exchange_managers:
            return
        
        # 委托给具体的交易所管理器
        manager = self.exchange_managers[exchange]
        manager.record_response(status_code, headers, endpoint)
        
        # 记录监控指标
        if self.monitoring:
            self.monitoring.collect_metric(
                "rate_limit_responses",
                1,
                labels={
                    "exchange": exchange.value,
                    "status_code": str(status_code),
                    "endpoint": endpoint or "unknown"
                }
            )
    
    def get_exchange_status(self, exchange: Union[str, ExchangeType]) -> Dict[str, Any]:
        """获取交易所状态"""
        
        # 标准化交易所类型
        if isinstance(exchange, str):
            try:
                exchange = ExchangeType(exchange.lower())
            except ValueError:
                return {"error": f"Unsupported exchange: {exchange}"}
        
        if exchange not in self.exchange_managers:
            return {"error": f"Exchange not configured: {exchange}"}
        
        return self.exchange_managers[exchange].get_status()
    
    def get_all_status(self) -> Dict[str, Any]:
        """获取所有交易所状态"""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_exchanges": len(self.exchange_managers),
            "exchanges": {
                exchange.value: manager.get_status()
                for exchange, manager in self.exchange_managers.items()
            }
        }


# 全局实例
_global_rate_limit_manager: Optional[GlobalRateLimitManager] = None


def get_rate_limit_manager() -> GlobalRateLimitManager:
    """获取全局限流管理器"""
    global _global_rate_limit_manager
    if _global_rate_limit_manager is None:
        _global_rate_limit_manager = GlobalRateLimitManager()
    return _global_rate_limit_manager


# 添加别名以保持向后兼容性
RateLimitManager = GlobalRateLimitManager


def with_rate_limit(exchange: str,
                   request_type: RequestType = RequestType.OTHER,
                   endpoint: Optional[str] = None,
                   priority: RequestPriority = RequestPriority.MEDIUM,
                   account_based: bool = False):
    """
    限流装饰器
    
    用法:
    @with_rate_limit("binance", RequestType.ORDERBOOK_SNAPSHOT, "/api/v3/depth")
    async def get_binance_orderbook():
        # API 请求代码
        pass
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            manager = get_rate_limit_manager()
            
            # 获取请求许可
            permit = await manager.acquire_permit(
                exchange=exchange,
                request_type=request_type,
                endpoint=endpoint,
                priority=priority,
                account_based=account_based
            )
            
            if not permit['granted']:
                wait_time = permit.get('wait_time', 0)
                raise RateLimitViolation(
                    message=permit['reason'],
                    wait_time=wait_time,
                    exchange=exchange,
                    endpoint=endpoint
                )
            
            # 执行实际请求
            try:
                result = await func(*args, **kwargs)
                
                # 记录成功响应
                manager.record_response(exchange, 200, endpoint=endpoint)
                
                return result
                
            except Exception as e:
                # 尝试提取状态码
                status_code = 500
                headers = {}
                
                if hasattr(e, 'response'):
                    if hasattr(e.response, 'status_code'):
                        status_code = e.response.status_code
                    if hasattr(e.response, 'headers'):
                        headers = dict(e.response.headers)
                
                # 记录错误响应
                manager.record_response(exchange, status_code, headers, endpoint)
                
                # 重新抛出异常
                raise
        
        return wrapper
    return decorator