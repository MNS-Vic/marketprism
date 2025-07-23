"""
统一错误处理器
集成Binance官方错误码管理
"""

import json
import asyncio
import structlog
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone

from .binance_error_codes import binance_error_manager, BinanceErrorSeverity


class BinanceAPIError(Exception):
    """Binance API错误异常"""
    
    def __init__(self, code: int, message: str, response_data: Optional[Dict] = None):
        self.code = code
        self.message = message
        self.response_data = response_data or {}
        self.error_info = binance_error_manager.get_error_info(code)
        super().__init__(self.format_message())
    
    def format_message(self) -> str:
        """格式化错误消息"""
        return binance_error_manager.format_error_message(self.code, self.message)
    
    @property
    def is_retryable(self) -> bool:
        """是否可重试"""
        return binance_error_manager.is_retryable_error(self.code)
    
    @property
    def severity(self) -> str:
        """错误严重程度"""
        return binance_error_manager.get_error_severity(self.code)
    
    @property
    def category(self) -> str:
        """错误分类"""
        return binance_error_manager.categorize_error(self.code)


class ErrorHandler:
    """统一错误处理器"""
    
    def __init__(self, logger: structlog.BoundLogger):
        self.logger = logger
        self.error_stats = {
            'total_errors': 0,
            'by_code': {},
            'by_category': {},
            'by_severity': {},
            'retryable_errors': 0,
            'critical_errors': 0
        }
    
    def parse_binance_error(self, response_text: str, status_code: int = None) -> BinanceAPIError:
        """解析Binance API错误响应"""
        try:
            # 尝试解析JSON响应
            if response_text.strip().startswith('{'):
                error_data = json.loads(response_text)
                code = error_data.get('code', -9999)
                message = error_data.get('msg', 'Unknown error')
                return BinanceAPIError(code, message, error_data)
            else:
                # 非JSON响应，可能是HTML错误页面
                if status_code == 429:
                    return BinanceAPIError(-1003, "Too many requests", {'status_code': status_code})
                elif status_code == 503:
                    return BinanceAPIError(-1008, "Service unavailable", {'status_code': status_code})
                else:
                    return BinanceAPIError(-1000, f"HTTP {status_code}: {response_text[:100]}", {'status_code': status_code})
        
        except json.JSONDecodeError:
            # JSON解析失败
            return BinanceAPIError(-1000, f"Invalid response format: {response_text[:100]}")
    
    def handle_api_error(self, error: BinanceAPIError, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """处理API错误"""
        context = context or {}
        
        # 更新错误统计
        self._update_error_stats(error)
        
        # 记录错误日志
        self._log_error(error, context)
        
        # 生成处理建议
        handling_advice = self._generate_handling_advice(error)
        
        return {
            'error_code': error.code,
            'error_name': error.error_info.name if error.error_info else 'UNKNOWN',
            'error_message': error.message,
            'formatted_message': error.format_message(),
            'category': error.category,
            'severity': error.severity,
            'is_retryable': error.is_retryable,
            'handling_advice': handling_advice,
            'context': context,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def _update_error_stats(self, error: BinanceAPIError):
        """更新错误统计"""
        self.error_stats['total_errors'] += 1
        
        # 按错误码统计
        code_key = str(error.code)
        self.error_stats['by_code'][code_key] = self.error_stats['by_code'].get(code_key, 0) + 1
        
        # 按分类统计
        category = error.category
        self.error_stats['by_category'][category] = self.error_stats['by_category'].get(category, 0) + 1
        
        # 按严重程度统计
        severity = error.severity
        self.error_stats['by_severity'][severity] = self.error_stats['by_severity'].get(severity, 0) + 1
        
        # 特殊统计
        if error.is_retryable:
            self.error_stats['retryable_errors'] += 1
        
        if error.severity == 'critical':
            self.error_stats['critical_errors'] += 1
    
    def _log_error(self, error: BinanceAPIError, context: Dict[str, Any]):
        """记录错误日志"""
        log_level = self._get_log_level(error.severity)
        
        log_data = {
            'error_code': error.code,
            'error_name': error.error_info.name if error.error_info else 'UNKNOWN',
            'error_message': error.message,
            'category': error.category,
            'severity': error.severity,
            'is_retryable': error.is_retryable,
            'context': context
        }
        
        if log_level == 'critical':
            self.logger.critical("🚨 Binance API严重错误", **log_data)
        elif log_level == 'error':
            self.logger.error("❌ Binance API错误", **log_data)
        elif log_level == 'warning':
            self.logger.warning("⚠️ Binance API警告", **log_data)
        else:
            self.logger.info("ℹ️ Binance API信息", **log_data)
    
    def _get_log_level(self, severity: str) -> str:
        """根据严重程度获取日志级别"""
        severity_to_log_level = {
            'critical': 'critical',
            'high': 'error',
            'medium': 'warning',
            'low': 'info'
        }
        return severity_to_log_level.get(severity, 'info')
    
    def _generate_handling_advice(self, error: BinanceAPIError) -> Dict[str, Any]:
        """生成处理建议"""
        advice = {
            'user_action': binance_error_manager.get_user_action(error.code),
            'retry_recommended': error.is_retryable,
            'retry_delay': self._get_retry_delay(error),
            'max_retries': self._get_max_retries(error),
            'escalation_required': error.severity in ['critical', 'high']
        }
        
        # 特殊错误的额外建议
        if error.code == -1003:  # API限流
            advice.update({
                'specific_actions': [
                    '减少API请求频率',
                    '使用WebSocket获取实时数据',
                    '实现指数退避重试策略',
                    '检查是否有多个进程同时请求'
                ],
                'retry_delay': 60  # API限流建议等待1分钟
            })
        elif error.code == -1021:  # 时间同步问题
            advice.update({
                'specific_actions': [
                    '同步系统时间',
                    '增加recvWindow参数',
                    '检查网络延迟'
                ]
            })
        elif error.code in [-2018, -2019]:  # 余额不足
            advice.update({
                'specific_actions': [
                    '检查账户余额',
                    '充值或转入资金',
                    '减少订单金额'
                ]
            })
        
        return advice
    
    def _get_retry_delay(self, error: BinanceAPIError) -> int:
        """获取重试延迟（秒）"""
        if not error.is_retryable:
            return 0
        
        # 根据错误类型设置不同的重试延迟
        if error.code == -1003:  # API限流
            return 60
        elif error.code in [-1007, -1008]:  # 超时或服务繁忙
            return 30
        elif error.severity == 'critical':
            return 120
        elif error.severity == 'high':
            return 60
        else:
            return 10
    
    def _get_max_retries(self, error: BinanceAPIError) -> int:
        """获取最大重试次数"""
        if not error.is_retryable:
            return 0
        
        if error.code == -1003:  # API限流
            return 3
        elif error.severity == 'critical':
            return 5
        elif error.severity == 'high':
            return 3
        else:
            return 2
    
    def get_error_stats(self) -> Dict[str, Any]:
        """获取错误统计"""
        return self.error_stats.copy()
    
    def reset_error_stats(self):
        """重置错误统计"""
        self.error_stats = {
            'total_errors': 0,
            'by_code': {},
            'by_category': {},
            'by_severity': {},
            'retryable_errors': 0,
            'critical_errors': 0
        }


class RetryHandler:
    """重试处理器"""
    
    def __init__(self, error_handler: ErrorHandler):
        self.error_handler = error_handler
        self.logger = error_handler.logger
    
    async def retry_with_backoff(self, func, *args, max_retries: int = 3, 
                                base_delay: float = 1.0, max_delay: float = 60.0, 
                                context: Dict[str, Any] = None, **kwargs):
        """带指数退避的重试机制"""
        context = context or {}
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                return await func(*args, **kwargs)
            
            except Exception as e:
                last_error = e
                
                # 如果是Binance API错误，使用错误处理器分析
                if isinstance(e, BinanceAPIError):
                    error_info = self.error_handler.handle_api_error(e, {
                        **context,
                        'attempt': attempt + 1,
                        'max_retries': max_retries
                    })
                    
                    # 如果不可重试，直接抛出异常
                    if not error_info['is_retryable']:
                        raise e
                    
                    # 使用错误处理器建议的延迟时间
                    delay = min(error_info['handling_advice']['retry_delay'], max_delay)
                else:
                    # 非Binance API错误，使用指数退避
                    delay = min(base_delay * (2 ** attempt), max_delay)
                
                if attempt < max_retries:
                    self.logger.warning(f"⏳ 第{attempt + 1}次重试失败，{delay}秒后重试", 
                                      error=str(e), delay=delay)
                    await asyncio.sleep(delay)
                else:
                    self.logger.error(f"❌ 重试{max_retries}次后仍然失败", error=str(e))
        
        # 所有重试都失败，抛出最后一个异常
        raise last_error
