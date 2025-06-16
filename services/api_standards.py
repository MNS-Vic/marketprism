"""
API标准模块
定义统一的API响应格式和错误处理标准
"""
from datetime import datetime
from typing import Dict, Any, List, Optional
import json


class APIStandards:
    """API标准类"""
    
    def __init__(self):
        self.response_format = {
            'status': str,
            'data': Any,
            'timestamp': str,
            'error': Optional[Dict]
        }
        
        self.error_codes = {
            400: 'Bad Request',
            401: 'Unauthorized',
            403: 'Forbidden',
            404: 'Not Found',
            429: 'Too Many Requests',
            500: 'Internal Server Error',
            502: 'Bad Gateway',
            503: 'Service Unavailable'
        }
    
    def success_response(self, data: Any, message: str = None) -> Dict[str, Any]:
        """创建成功响应"""
        response = {
            'status': 'success',
            'data': data,
            'timestamp': datetime.now().isoformat()
        }
        
        if message:
            response['message'] = message
        
        return response
    
    def error_response(self, message: str, code: int = 500, details: Dict = None) -> Dict[str, Any]:
        """创建错误响应"""
        response = {
            'status': 'error',
            'error': {
                'message': message,
                'code': code,
                'type': self.error_codes.get(code, 'Unknown Error')
            },
            'timestamp': datetime.now().isoformat()
        }
        
        if details:
            response['error']['details'] = details
        
        return response
    
    def paginated_response(self, data: List[Any], page: int, per_page: int, total: int) -> Dict[str, Any]:
        """创建分页响应"""
        pages = (total + per_page - 1) // per_page
        
        response = {
            'status': 'success',
            'data': data,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': pages,
                'has_next': page < pages,
                'has_prev': page > 1
            },
            'timestamp': datetime.now().isoformat()
        }
        
        return response
    
    def validation_error_response(self, validation_errors: Dict[str, List[str]]) -> Dict[str, Any]:
        """创建验证错误响应"""
        response = {
            'status': 'error',
            'error': {
                'message': 'Validation failed',
                'code': 400,
                'type': 'validation_error',
                'details': validation_errors
            },
            'timestamp': datetime.now().isoformat()
        }
        
        return response
    
    def rate_limit_response(self, retry_after: int = None) -> Dict[str, Any]:
        """创建速率限制响应"""
        response = {
            'status': 'error',
            'error': {
                'message': 'Rate limit exceeded',
                'code': 429,
                'type': 'rate_limit_error'
            },
            'timestamp': datetime.now().isoformat()
        }
        
        if retry_after:
            response['error']['retry_after'] = retry_after
        
        return response
    
    def health_check_response(self, status: str = 'healthy', details: Dict = None) -> Dict[str, Any]:
        """创建健康检查响应"""
        response = {
            'status': status,
            'timestamp': datetime.now().isoformat(),
            'service': 'marketprism'
        }
        
        if details:
            response['details'] = details
        
        return response