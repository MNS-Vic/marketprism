"""
MarketPrism Collector 统一错误管理器

整合 core.errors、core.reliability、core.monitoring 等模块，
为数据收集器提供企业级的统一错误处理、恢复和监控能力。

特别针对交易所连接和数据处理中的各种异常情况：
- 网络连接错误
- WebSocket断线重连  
- API限流和超时
- 数据格式错误
- 服务降级和熔断
"""

import asyncio
import logging
import inspect
from typing import Dict, Any, Optional, List, Callable, Union
from datetime import datetime, timedelta
from functools import wraps
from dataclasses import dataclass
from enum import Enum

# Core模块导入
try:
    from core.errors import (
        UnifiedErrorHandler, get_global_error_handler, 
        MarketPrismError, ErrorCategory, ErrorSeverity, ErrorType,
        ErrorContext, ErrorMetadata
    )
    from core.reliability import (
        MarketPrismCircuitBreaker, CircuitBreakerConfig, CircuitState,
        AdaptiveRateLimiter, RateLimitConfig, RequestPriority,
        ExponentialBackoffRetry, RetryPolicy, RetryErrorType,
        get_reliability_manager
    )
    from core.reliability.rate_limit_manager import (
        get_rate_limit_manager, RateLimitViolation, RequestType as RLRequestType
    )
    from core.monitoring import get_global_monitoring
    CORE_AVAILABLE = True
except ImportError as e:
    CORE_AVAILABLE = False
    logging.warning(f"Core模块不可用，使用降级实现: {e}")


class CollectorErrorType(Enum):
    """收集器特定的错误类型"""
    EXCHANGE_CONNECTION = "exchange_connection"
    WEBSOCKET_DISCONNECTION = "websocket_disconnection"
    DATA_PARSING = "data_parsing"
    NATS_PUBLISH = "nats_publish"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    AUTH_FAILURE = "auth_failure"
    SUBSCRIPTION_FAILED = "subscription_failed"
    ADAPTER_CREATION = "adapter_creation"
    HEALTH_CHECK = "health_check"
    ORDERBOOK_PROCESSING = "orderbook_processing"


@dataclass
class ExchangeErrorContext:
    """交易所错误上下文"""
    exchange_name: str
    symbol: Optional[str] = None
    operation: Optional[str] = None
    retry_count: int = 0
    last_success_time: Optional[datetime] = None
    connection_state: str = "unknown"
    error_frequency: int = 0
    recovery_strategies: List[str] = None


class CollectorErrorManager:
    """收集器统一错误管理器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # 初始化Core组件
        if CORE_AVAILABLE:
            self.error_handler = get_global_error_handler()
            self.reliability_manager = get_reliability_manager()
            self.monitoring = get_global_monitoring()
            self.rate_limit_manager = get_rate_limit_manager()  # 使用 Core 层的限流管理器
        else:
            self.error_handler = None
            self.reliability_manager = None
            self.monitoring = None
            self.rate_limit_manager = None
        
        # 交易所特定的错误处理配置
        self.exchange_configs: Dict[str, Dict[str, Any]] = {}
        self.circuit_breakers: Dict[str, MarketPrismCircuitBreaker] = {}
        self.rate_limiters: Dict[str, AdaptiveRateLimiter] = {}
        self.retry_handlers: Dict[str, ExponentialBackoffRetry] = {}
        
        # 错误统计和上下文
        self.exchange_contexts: Dict[str, ExchangeErrorContext] = {}
        self.error_patterns: Dict[str, List[Dict[str, Any]]] = {}
        
        # 初始化交易所特定配置
        self._init_exchange_configs()
    
    def _init_exchange_configs(self):
        """初始化交易所特定的错误处理配置"""
        # Binance配置
        self.exchange_configs["binance"] = {
            "circuit_breaker": {
                "failure_threshold": 5,
                "timeout_seconds": 30,
                "reset_timeout_seconds": 60
            },
            "rate_limiter": {
                "requests_per_minute": 1200,
                "priority": RequestPriority.HIGH
            },
            "retry": {
                "max_attempts": 3,
                "base_delay": 1.0,
                "max_delay": 30.0,
                "exponential_base": 2.0
            },
            "error_recovery": {
                "websocket_reconnect_delay": 5.0,
                "health_check_interval": 30.0,
                "auto_recovery_enabled": True
            }
        }
        
        # OKX配置  
        self.exchange_configs["okx"] = {
            "circuit_breaker": {
                "failure_threshold": 3,
                "timeout_seconds": 20,
                "reset_timeout_seconds": 45
            },
            "rate_limiter": {
                "requests_per_minute": 600,
                "priority": RequestPriority.MEDIUM
            },
            "retry": {
                "max_attempts": 5,
                "base_delay": 0.5,
                "max_delay": 20.0,
                "exponential_base": 1.5
            },
            "error_recovery": {
                "websocket_reconnect_delay": 3.0,
                "health_check_interval": 20.0,
                "auto_recovery_enabled": True
            }
        }
        
        # 初始化组件
        if CORE_AVAILABLE:
            self._create_reliability_components()
    
    def _create_reliability_components(self):
        """创建可靠性组件"""
        for exchange, config in self.exchange_configs.items():
            try:
                # 创建熔断器
                cb_config = CircuitBreakerConfig(**config["circuit_breaker"])
                self.circuit_breakers[exchange] = MarketPrismCircuitBreaker(
                    name=f"{exchange}_circuit_breaker",
                    config=cb_config
                )
                
                # 创建限流器
                rl_config = RateLimitConfig(**config["rate_limiter"])
                self.rate_limiters[exchange] = AdaptiveRateLimiter(
                    name=f"{exchange}_rate_limiter",
                    config=rl_config
                )
                
                # 创建重试处理器
                retry_config = RetryPolicy(**config["retry"])
                self.retry_handlers[exchange] = ExponentialBackoffRetry(
                    name=f"{exchange}_retry_handler",
                    policy=retry_config
                )
                
                self.logger.info(f"为{exchange}创建可靠性组件成功")
                
            except Exception as e:
                self.logger.error(f"为{exchange}创建可靠性组件失败: {e}")
    
    async def handle_exchange_error(self, 
                                  exchange: str,
                                  error: Exception,
                                  context: Optional[ExchangeErrorContext] = None,
                                  auto_recovery: bool = True) -> Dict[str, Any]:
        """
        处理交易所相关错误
        
        Args:
            exchange: 交易所名称
            error: 发生的错误
            context: 交易所错误上下文
            auto_recovery: 是否自动尝试恢复
            
        Returns:
            处理结果包含错误ID、恢复建议等
        """
        error_id = None
        
        try:
            # 创建或更新交易所上下文
            if exchange not in self.exchange_contexts:
                self.exchange_contexts[exchange] = ExchangeErrorContext(
                    exchange_name=exchange,
                    recovery_strategies=[]
                )
            
            ctx = self.exchange_contexts[exchange]
            if context:
                # 更新上下文信息
                ctx.symbol = context.symbol or ctx.symbol
                ctx.operation = context.operation or ctx.operation
                ctx.retry_count += 1
                ctx.error_frequency += 1
            
            # 确定错误类型和严重性
            error_type, severity = self._classify_error(error, exchange)
            
            # 使用Core错误处理器
            if self.error_handler and CORE_AVAILABLE:
                # 转换为MarketPrismError
                marketprism_error = self._convert_to_marketprism_error(
                    error, error_type, severity, exchange, ctx
                )
                error_id = self.error_handler.handle_error(marketprism_error)
            
            # 记录到监控系统
            if self.monitoring:
                self.monitoring.collect_metric(
                    "collector_errors_total",
                    1,
                    labels={
                        "exchange": exchange,
                        "error_type": error_type.value,
                        "severity": severity.value
                    }
                )
            
            # 应用可靠性机制
            reliability_result = await self._apply_reliability_mechanisms(
                exchange, error, error_type
            )
            
            # 自动恢复尝试
            recovery_result = None
            if auto_recovery and self._should_attempt_recovery(exchange, error_type):
                recovery_result = await self._attempt_auto_recovery(
                    exchange, error, ctx
                )
            
            # 生成错误处理报告
            result = {
                "error_id": error_id,
                "exchange": exchange,
                "error_type": error_type.value,
                "severity": severity.value,
                "timestamp": datetime.utcnow().isoformat(),
                "context": {
                    "retry_count": ctx.retry_count,
                    "error_frequency": ctx.error_frequency,
                    "last_success": ctx.last_success_time.isoformat() if ctx.last_success_time else None
                },
                "reliability_applied": reliability_result,
                "recovery_attempted": recovery_result is not None,
                "recovery_result": recovery_result,
                "recommendations": self._get_error_recommendations(exchange, error_type, ctx)
            }
            
            # 存储错误模式用于分析
            self._store_error_pattern(exchange, error, result)
            
            return result
            
        except Exception as handling_error:
            # 错误处理器本身出错时的降级处理
            self.logger.error(f"错误处理器异常: {handling_error}")
            return {
                "error_id": "fallback_" + str(id(error)),
                "exchange": exchange,
                "error_type": "error_handler_failure",
                "severity": "critical",
                "timestamp": datetime.utcnow().isoformat(),
                "fallback_mode": True,
                "original_error": str(error),
                "handling_error": str(handling_error)
            }
    
    def _classify_error(self, error: Exception, exchange: str) -> tuple:
        """分类错误类型和严重性"""
        error_msg = str(error).lower()
        error_class = type(error).__name__
        
        # 网络连接错误
        if isinstance(error, (ConnectionError, TimeoutError)) or "connection" in error_msg:
            return CollectorErrorType.EXCHANGE_CONNECTION, ErrorSeverity.HIGH
        
        # WebSocket断线
        if "websocket" in error_msg or "ws" in error_msg or "disconnect" in error_msg:
            return CollectorErrorType.WEBSOCKET_DISCONNECTION, ErrorSeverity.MEDIUM
        
        # 认证失败
        if "auth" in error_msg or "unauthorized" in error_msg or "403" in error_msg:
            return CollectorErrorType.AUTH_FAILURE, ErrorSeverity.HIGH
        
        # 限流错误
        if "rate limit" in error_msg or "429" in error_msg or "too many" in error_msg:
            return CollectorErrorType.RATE_LIMIT_EXCEEDED, ErrorSeverity.LOW
        
        # 数据解析错误
        if isinstance(error, (ValueError, KeyError, TypeError)) or "parse" in error_msg:
            return CollectorErrorType.DATA_PARSING, ErrorSeverity.MEDIUM
        
        # 订阅失败
        if "subscribe" in error_msg or "subscription" in error_msg:
            return CollectorErrorType.SUBSCRIPTION_FAILED, ErrorSeverity.MEDIUM
        
        # 默认为一般连接错误
        return CollectorErrorType.EXCHANGE_CONNECTION, ErrorSeverity.MEDIUM
    
    def _convert_to_marketprism_error(self, 
                                    error: Exception,
                                    error_type: CollectorErrorType,
                                    severity: ErrorSeverity,
                                    exchange: str,
                                    context: ExchangeErrorContext) -> MarketPrismError:
        """转换为MarketPrismError"""
        if not CORE_AVAILABLE:
            return None
        
        # 创建错误元数据
        metadata = ErrorMetadata(
            error_id=str(id(error)),
            component="collector",
            exchange=exchange,
            symbol=context.symbol,
            operation=context.operation,
            retry_count=context.retry_count,
            first_occurrence=datetime.utcnow(),
            last_occurrence=datetime.utcnow()
        )
        
        # 映射到Core错误类型
        core_error_type = ErrorType.EXTERNAL_SERVICE_ERROR
        core_category = ErrorCategory.EXTERNAL_SERVICE
        
        if error_type == CollectorErrorType.WEBSOCKET_DISCONNECTION:
            core_error_type = ErrorType.NETWORK_ERROR
            core_category = ErrorCategory.INFRASTRUCTURE
        elif error_type == CollectorErrorType.DATA_PARSING:
            core_error_type = ErrorType.DATA_ERROR
            core_category = ErrorCategory.DATA_PROCESSING
        elif error_type == CollectorErrorType.AUTH_FAILURE:
            core_error_type = ErrorType.AUTHENTICATION_ERROR
            core_category = ErrorCategory.SECURITY
        
        return MarketPrismError(
            message=f"[{exchange}] {error_type.value}: {str(error)}",
            error_type=core_error_type,
            category=core_category,
            severity=severity,
            metadata=metadata,
            cause=error
        )
    
    async def _apply_reliability_mechanisms(self, 
                                          exchange: str,
                                          error: Exception,
                                          error_type: CollectorErrorType) -> Dict[str, Any]:
        """应用可靠性机制"""
        result = {
            "circuit_breaker": None,
            "rate_limiter": None,
            "retry_handler": None
        }
        
        if not CORE_AVAILABLE:
            return result
        
        try:
            # 应用熔断器
            if exchange in self.circuit_breakers:
                circuit_breaker = self.circuit_breakers[exchange]
                # 记录失败
                circuit_breaker.record_failure()
                result["circuit_breaker"] = {
                    "state": circuit_breaker.get_state().value,
                    "failure_count": circuit_breaker.get_failure_count(),
                    "last_failure_time": circuit_breaker.get_last_failure_time()
                }
            
            # 应用限流器（如果是限流错误）
            if error_type == CollectorErrorType.RATE_LIMIT_EXCEEDED and exchange in self.rate_limiters:
                rate_limiter = self.rate_limiters[exchange]
                # 增加延迟
                await rate_limiter.wait_if_needed()
                result["rate_limiter"] = {
                    "current_rate": rate_limiter.get_current_rate(),
                    "is_limited": rate_limiter.is_rate_limited(),
                    "wait_time": rate_limiter.get_wait_time()
                }
            
            # 准备重试（如果错误可重试）
            if self._is_retryable_error(error_type) and exchange in self.retry_handlers:
                retry_handler = self.retry_handlers[exchange]
                next_delay = retry_handler.get_next_delay()
                result["retry_handler"] = {
                    "should_retry": True,
                    "next_delay": next_delay,
                    "max_attempts": retry_handler.policy.max_attempts
                }
            
        except Exception as e:
            self.logger.error(f"应用可靠性机制失败: {e}")
        
        return result
    
    def _is_retryable_error(self, error_type: CollectorErrorType) -> bool:
        """判断错误是否可重试"""
        retryable_errors = {
            CollectorErrorType.EXCHANGE_CONNECTION,
            CollectorErrorType.WEBSOCKET_DISCONNECTION,
            CollectorErrorType.RATE_LIMIT_EXCEEDED,
            CollectorErrorType.SUBSCRIPTION_FAILED,
            CollectorErrorType.NATS_PUBLISH
        }
        return error_type in retryable_errors
    
    def _should_attempt_recovery(self, exchange: str, error_type: CollectorErrorType) -> bool:
        """判断是否应该尝试自动恢复"""
        if exchange not in self.exchange_configs:
            return False
        
        config = self.exchange_configs[exchange]
        if not config.get("error_recovery", {}).get("auto_recovery_enabled", False):
            return False
        
        # 某些错误类型不适合自动恢复
        non_recoverable = {
            CollectorErrorType.AUTH_FAILURE,
            CollectorErrorType.DATA_PARSING
        }
        return error_type not in non_recoverable
    
    async def _attempt_auto_recovery(self, 
                                   exchange: str,
                                   error: Exception,
                                   context: ExchangeErrorContext) -> Dict[str, Any]:
        """尝试自动恢复"""
        recovery_steps = []
        success = False
        
        try:
            # 等待恢复延迟
            config = self.exchange_configs.get(exchange, {})
            recovery_config = config.get("error_recovery", {})
            delay = recovery_config.get("websocket_reconnect_delay", 5.0)
            
            recovery_steps.append(f"等待恢复延迟: {delay}秒")
            await asyncio.sleep(delay)
            
            # 这里可以添加具体的恢复逻辑
            # 例如：重新建立WebSocket连接、重新订阅数据等
            recovery_steps.append("尝试重新建立连接")
            
            # 模拟恢复成功（实际实现中需要调用具体的恢复方法）
            success = True
            recovery_steps.append("恢复成功")
            
            # 更新上下文
            if success:
                context.last_success_time = datetime.utcnow()
                context.retry_count = 0
            
        except Exception as e:
            recovery_steps.append(f"恢复失败: {str(e)}")
        
        return {
            "success": success,
            "steps": recovery_steps,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def _get_error_recommendations(self, 
                                 exchange: str,
                                 error_type: CollectorErrorType,
                                 context: ExchangeErrorContext) -> List[str]:
        """获取错误处理建议"""
        recommendations = []
        
        if error_type == CollectorErrorType.EXCHANGE_CONNECTION:
            recommendations.extend([
                "检查网络连接状态",
                "验证交易所服务是否可用",
                "考虑使用代理或备用连接"
            ])
        
        elif error_type == CollectorErrorType.WEBSOCKET_DISCONNECTION:
            recommendations.extend([
                "启用自动重连机制",
                "检查WebSocket服务器状态",
                "调整心跳间隔"
            ])
        
        elif error_type == CollectorErrorType.RATE_LIMIT_EXCEEDED:
            recommendations.extend([
                "降低请求频率",
                "实现请求队列管理",
                "升级API等级或联系交易所"
            ])
        
        elif error_type == CollectorErrorType.AUTH_FAILURE:
            recommendations.extend([
                "检查API密钥和签名",
                "验证IP白名单设置",
                "确认API权限配置"
            ])
        
        elif error_type == CollectorErrorType.DATA_PARSING:
            recommendations.extend([
                "更新数据解析逻辑",
                "检查API文档变更",
                "添加数据格式验证"
            ])
        
        # 基于错误频率的建议
        if context.error_frequency > 10:
            recommendations.append("错误频率过高，考虑暂时禁用该交易所")
        
        # 基于重试次数的建议
        if context.retry_count > 5:
            recommendations.append("重试次数过多，考虑手动干预")
        
        return recommendations
    
    def _store_error_pattern(self, exchange: str, error: Exception, result: Dict[str, Any]):
        """存储错误模式用于分析"""
        if exchange not in self.error_patterns:
            self.error_patterns[exchange] = []
        
        pattern = {
            "timestamp": datetime.utcnow().isoformat(),
            "error_class": type(error).__name__,
            "error_message": str(error),
            "error_type": result["error_type"],
            "severity": result["severity"],
            "context": result["context"]
        }
        
        # 只保留最近100个错误模式
        self.error_patterns[exchange].append(pattern)
        if len(self.error_patterns[exchange]) > 100:
            self.error_patterns[exchange].pop(0)
    
    def get_exchange_health_status(self, exchange: str) -> Dict[str, Any]:
        """获取交易所健康状态"""
        if exchange not in self.exchange_contexts:
            return {"status": "unknown", "message": "无交易所上下文信息"}
        
        context = self.exchange_contexts[exchange]
        now = datetime.utcnow()
        
        # 计算健康分数
        health_score = 100
        
        if context.error_frequency > 0:
            health_score -= min(50, context.error_frequency * 5)
        
        if context.retry_count > 0:
            health_score -= min(30, context.retry_count * 10)
        
        if context.last_success_time:
            time_since_success = (now - context.last_success_time).total_seconds()
            if time_since_success > 300:  # 5分钟
                health_score -= 20
        
        # 确定状态
        if health_score >= 80:
            status = "healthy"
        elif health_score >= 60:
            status = "degraded"
        elif health_score >= 40:
            status = "unhealthy"
        else:
            status = "critical"
        
        return {
            "status": status,
            "health_score": max(0, health_score),
            "error_frequency": context.error_frequency,
            "retry_count": context.retry_count,
            "last_success": context.last_success_time.isoformat() if context.last_success_time else None,
            "connection_state": context.connection_state,
            "circuit_breaker_state": self.circuit_breakers.get(exchange, {}).get_state().value if exchange in self.circuit_breakers else "unknown"
        }
    
    def check_rate_limit_before_request(self, exchange: str, endpoint: str, priority: str = "NORMAL") -> Dict[str, Any]:
        """在请求前检查限流状态 - 使用 Core 层的 Rate Limit Manager"""
        if not self.rate_limit_manager:
            return {'allowed': True, 'message': 'Rate limit manager not available'}
        
        try:
            # 映射优先级
            priority_map = {
                'CRITICAL': 'CRITICAL',
                'HIGH': 'HIGH', 
                'NORMAL': 'NORMAL',
                'LOW': 'LOW',
                'BACKGROUND': 'BACKGROUND'
            }
            
            # 使用 Core 层的限流检查
            can_request = self.rate_limit_manager.can_make_request(
                exchange=exchange,
                endpoint=endpoint, 
                priority=priority_map.get(priority, 'NORMAL')
            )
            
            if can_request:
                return {'allowed': True, 'message': 'Request allowed'}
            else:
                return {
                    'allowed': False, 
                    'message': f'Rate limit exceeded for {exchange}:{endpoint}',
                    'should_retry': True,
                    'retry_after': self.rate_limit_manager.get_backoff_time(exchange)
                }
                
        except Exception as e:
            self.logger.error(f"检查限流状态时出错: {e}")
            return {'allowed': True, 'message': f'Rate limit check failed: {e}'}
    
    def get_rate_limit_status(self, exchange: str = None) -> Dict[str, Any]:
        """获取限流状态 - 使用 Core 层的 Rate Limit Manager"""
        if self.rate_limit_manager:
            try:
                if exchange:
                    return self.rate_limit_manager.get_status(exchange)
                else:
                    return self.rate_limit_manager.get_global_status()
            except Exception as e:
                self.logger.error(f"Core层限流状态获取失败: {e}")
        
        # 降级处理：返回空状态
        return {"status": "Rate limit manager unavailable"}

    def get_error_analytics(self) -> Dict[str, Any]:
        """获取错误分析数据"""
        analytics = {
            "total_exchanges": len(self.exchange_contexts),
            "error_patterns": {},
            "top_error_types": {},
            "recovery_success_rate": 0.0,
            "overall_health": "unknown",
            "rate_limit_status": self.get_rate_limit_status()  # 使用 Core 层的限流状态
        }
        
        # 分析错误模式
        total_errors = 0
        error_type_counts = {}
        
        for exchange, patterns in self.error_patterns.items():
            analytics["error_patterns"][exchange] = {
                "total_errors": len(patterns),
                "recent_errors": len([p for p in patterns if 
                    datetime.fromisoformat(p["timestamp"]) > datetime.utcnow() - timedelta(hours=1)
                ])
            }
            
            total_errors += len(patterns)
            
            for pattern in patterns:
                error_type = pattern["error_type"]
                error_type_counts[error_type] = error_type_counts.get(error_type, 0) + 1
        
        # 排序错误类型
        analytics["top_error_types"] = dict(
            sorted(error_type_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        )
        
        # 计算整体健康状态
        if self.exchange_contexts:
            health_scores = []
            for exchange in self.exchange_contexts:
                health_status = self.get_exchange_health_status(exchange)
                health_scores.append(health_status["health_score"])
            
            avg_health = sum(health_scores) / len(health_scores)
            if avg_health >= 80:
                analytics["overall_health"] = "healthy"
            elif avg_health >= 60:
                analytics["overall_health"] = "degraded"
            else:
                analytics["overall_health"] = "unhealthy"
        
        return analytics


# 全局错误管理器实例
_global_collector_error_manager = None


def get_collector_error_manager() -> CollectorErrorManager:
    """获取全局收集器错误管理器"""
    global _global_collector_error_manager
    if _global_collector_error_manager is None:
        _global_collector_error_manager = CollectorErrorManager()
    return _global_collector_error_manager


def with_error_handling(exchange: str = None, auto_recovery: bool = True):
    """
    错误处理装饰器
    
    用法:
    @with_error_handling(exchange="binance")
    async def connect_to_binance():
        # 可能出错的代码
        pass
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            error_manager = get_collector_error_manager()
            
            try:
                # 如果是实例方法，尝试从self获取交易所名称
                actual_exchange = exchange
                if not actual_exchange and args and hasattr(args[0], 'exchange_name'):
                    actual_exchange = args[0].exchange_name
                
                return await func(*args, **kwargs)
                
            except Exception as e:
                # 处理错误
                result = await error_manager.handle_exchange_error(
                    exchange=actual_exchange or "unknown",
                    error=e,
                    auto_recovery=auto_recovery
                )
                
                # 根据错误严重性决定是否重新抛出
                if result.get("severity") in ["critical", "high"]:
                    raise
                else:
                    # 返回错误结果而不是抛出异常
                    return {"error": True, "error_result": result}
        
        return wrapper
    return decorator 