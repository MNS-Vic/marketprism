"""
MarketPrism Collector 错误处理适配器

提供收集器特定的错误处理功能，基于core/errors/统一错误处理框架
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass

# 使用Core错误处理模块
from core.errors import (
    UnifiedErrorHandler, get_global_error_handler,
    MarketPrismError, ErrorCategory, ErrorSeverity, ErrorType,
    ErrorContext, ErrorMetadata
)
from core.reliability import (
    get_reliability_manager,
    MarketPrismCircuitBreaker, CircuitBreakerConfig,
    AdaptiveRateLimiter, RateLimitConfig, RequestPriority
)


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


class CollectorErrorAdapter:
    """收集器错误处理适配器 - 基于Core错误处理框架"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # 使用Core错误处理器
        self.error_handler = get_global_error_handler()
        self.reliability_manager = get_reliability_manager()
        
        # 收集器特定的上下文
        self.exchange_contexts: Dict[str, ExchangeErrorContext] = {}
    
    async def handle_exchange_error(self, 
                                  exchange: str,
                                  error: Exception,
                                  context: Optional[ExchangeErrorContext] = None) -> Dict[str, Any]:
        """处理交易所错误 - 简化版本"""
        
        # 创建或更新上下文
        if exchange not in self.exchange_contexts:
            self.exchange_contexts[exchange] = ExchangeErrorContext(exchange_name=exchange)
        
        ctx = self.exchange_contexts[exchange]
        if context:
            ctx.symbol = context.symbol or ctx.symbol
            ctx.operation = context.operation or ctx.operation
            ctx.retry_count += 1
        
        # 分类错误
        error_type, severity = self._classify_error(error)
        
        # 转换为MarketPrismError并使用Core处理器
        marketprism_error = self._convert_to_marketprism_error(
            error, error_type, severity, exchange, ctx
        )
        
        error_id = self.error_handler.handle_error(marketprism_error)
        
        return {
            "error_id": error_id,
            "exchange": exchange,
            "error_type": error_type.value,
            "severity": severity.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "context": {
                "retry_count": ctx.retry_count,
                "symbol": ctx.symbol,
                "operation": ctx.operation
            }
        }
    
    def _classify_error(self, error: Exception) -> tuple:
        """分类错误类型和严重性"""
        error_msg = str(error).lower()
        
        if isinstance(error, (ConnectionError, TimeoutError)) or "connection" in error_msg:
            return CollectorErrorType.EXCHANGE_CONNECTION, ErrorSeverity.HIGH
        elif "websocket" in error_msg or "disconnect" in error_msg:
            return CollectorErrorType.WEBSOCKET_DISCONNECTION, ErrorSeverity.MEDIUM
        elif "auth" in error_msg or "unauthorized" in error_msg:
            return CollectorErrorType.AUTH_FAILURE, ErrorSeverity.HIGH
        elif "rate limit" in error_msg or "429" in error_msg:
            return CollectorErrorType.RATE_LIMIT_EXCEEDED, ErrorSeverity.LOW
        elif isinstance(error, (ValueError, KeyError, TypeError)):
            return CollectorErrorType.DATA_PARSING, ErrorSeverity.MEDIUM
        else:
            return CollectorErrorType.EXCHANGE_CONNECTION, ErrorSeverity.MEDIUM
    
    def _convert_to_marketprism_error(self, 
                                    error: Exception,
                                    error_type: CollectorErrorType,
                                    severity: ErrorSeverity,
                                    exchange: str,
                                    context: ExchangeErrorContext) -> MarketPrismError:
        """转换为MarketPrismError"""
        
        metadata = ErrorMetadata(
            error_id=str(id(error)),
            retry_count=context.retry_count,
            first_occurrence=datetime.now(timezone.utc),
            last_occurrence=datetime.now(timezone.utc),
            tags=[f"component:collector", f"exchange:{exchange}"]
        )

        # 添加额外的上下文信息到tags
        if context.symbol:
            metadata.tags.append(f"symbol:{context.symbol}")
        if context.operation:
            metadata.tags.append(f"operation:{context.operation}")
        
        # 映射错误类型
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


# 全局实例
collector_error_adapter = CollectorErrorAdapter()


# 便利函数
async def handle_collector_error(exchange: str, error: Exception, **kwargs):
    """处理收集器错误的便利函数"""
    return await collector_error_adapter.handle_exchange_error(exchange, error, **kwargs)


def log_collector_error(message: str, **kwargs):
    """记录收集器错误的便利函数"""
    logger = logging.getLogger("collector_error")
    logger.error(message, **kwargs)
