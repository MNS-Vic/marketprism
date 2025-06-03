"""
标准API接口定义

定义所有服务API的标准格式和响应结构
"""

from typing import Dict, Any, Optional, Union
from dataclasses import dataclass
from datetime import datetime
import json


@dataclass
class APIResponse:
    """标准API响应"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    message: Optional[str] = None
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "message": self.message,
            "timestamp": self.timestamp
        }
    
    def to_json(self) -> str:
        """转换为JSON"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def success_response(data: Any = None, message: str = None) -> APIResponse:
    """创建成功响应"""
    return APIResponse(success=True, data=data, message=message)


def error_response(error: str, message: str = None) -> APIResponse:
    """创建错误响应"""
    return APIResponse(success=False, error=error, message=message)


class StandardAPIHandler:
    """标准API处理器"""
    
    @staticmethod
    def handle_request(func):
        """API请求处理装饰器"""
        async def wrapper(*args, **kwargs):
            try:
                result = await func(*args, **kwargs)
                return success_response(data=result)
            except Exception as e:
                return error_response(str(e))
        return wrapper
    
    @staticmethod
    def validate_params(required_params: list):
        """参数验证装饰器"""
        def decorator(func):
            async def wrapper(*args, **kwargs):
                for param in required_params:
                    if param not in kwargs:
                        return error_response(f"Missing required parameter: {param}")
                return await func(*args, **kwargs)
            return wrapper
        return decorator
