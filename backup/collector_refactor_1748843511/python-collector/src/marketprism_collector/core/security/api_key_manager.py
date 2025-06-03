"""
API Key Manager

Week 6 Day 4: API网关安全系统组件
"""

import asyncio
import logging
import hashlib
import secrets
import json
from typing import Dict, Any, Optional, List, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

class APIKeyStatus(Enum):
    """API密钥状态"""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    REVOKED = "revoked"

class APIKeyScope(Enum):
    """API密钥权限范围"""
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"
    ADMIN = "admin"
    MONITORING = "monitoring"
    TRADING = "trading"

@dataclass
class APIKey:
    """API密钥数据模型"""
    key_id: str
    api_key: str
    api_secret: str
    name: str
    description: str
    status: APIKeyStatus
    scopes: List[APIKeyScope]
    client_id: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    usage_count: int = 0
    rate_limit: int = 1000  # 每小时请求限制
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class APIKeyManagerConfig:
    """API密钥管理器配置"""
    enabled: bool = True
    version: str = "1.0.0"
    # 密钥生成配置
    key_length: int = 32
    secret_length: int = 64
    default_expiry_days: int = 365
    # 安全配置
    enable_key_rotation: bool = True
    rotation_interval_days: int = 90
    max_keys_per_client: int = 10
    # 验证配置
    enable_signature_validation: bool = True
    timestamp_tolerance_seconds: int = 300
    # 缓存配置
    cache_ttl_seconds: int = 300
    max_cache_size: int = 10000

class APIKeyManager:
    """
    API Key Manager
    
    企业级API密钥管理系统：
    - API密钥生成与管理
    - 密钥验证与授权
    - 权限范围控制
    - 使用频率监控
    - 密钥轮换管理
    """
    
    def __init__(self, config: APIKeyManagerConfig):
        self.config = config
        self.is_started = False
        
        # 密钥存储
        self.api_keys: Dict[str, APIKey] = {}
        self.key_lookup: Dict[str, str] = {}  # api_key -> key_id
        
        # 使用统计
        self.usage_stats: Dict[str, Dict[str, Any]] = {}
        self.rate_limit_tracking: Dict[str, List[datetime]] = {}
        
        # 验证缓存
        self.validation_cache: Dict[str, Dict[str, Any]] = {}
        self.cache_timestamps: Dict[str, datetime] = {}
        
        # 密钥轮换任务
        self.rotation_task: Optional[asyncio.Task] = None
        
    async def start(self):
        """启动API密钥管理器"""
        logger.info(f"启动 API Key Manager v{self.config.version}")
        
        # 初始化管理器
        await self._initialize_manager()
        
        # 启动密钥轮换任务
        if self.config.enable_key_rotation:
            self.rotation_task = asyncio.create_task(self._key_rotation_worker())
        
        # 启动缓存清理任务
        asyncio.create_task(self._cache_cleanup_worker())
        
        # 启动使用统计清理任务
        asyncio.create_task(self._usage_cleanup_worker())
        
        self.is_started = True
        logger.info("✅ API Key Manager 启动完成")
        
    async def stop(self):
        """停止API密钥管理器"""
        logger.info("停止 API Key Manager")
        
        if self.rotation_task:
            self.rotation_task.cancel()
            
        self.is_started = False
        
    async def _initialize_manager(self):
        """初始化管理器"""
        logger.info("初始化 API Key Manager")
        
        # 创建默认系统密钥
        await self._create_default_keys()
        
    async def _create_default_keys(self):
        """创建默认系统密钥"""
        try:
            # 创建系统监控密钥
            monitoring_key = await self.create_api_key(
                name="System Monitoring",
                description="系统监控专用密钥",
                client_id="system",
                scopes=[APIKeyScope.MONITORING, APIKeyScope.READ_ONLY],
                expires_in_days=None  # 永不过期
            )
            logger.info(f"创建系统监控密钥: {monitoring_key['key_id']}")
            
        except Exception as e:
            logger.error(f"创建默认密钥时出错: {e}")
            
    async def create_api_key(
        self,
        name: str,
        description: str,
        client_id: str,
        scopes: List[APIKeyScope],
        expires_in_days: Optional[int] = None,
        rate_limit: int = 1000,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """创建新的API密钥"""
        try:
            # 检查客户端密钥数量限制
            client_keys = [k for k in self.api_keys.values() if k.client_id == client_id]
            if len(client_keys) >= self.config.max_keys_per_client:
                raise ValueError(f"客户端 {client_id} 已达到最大密钥数量限制")
                
            # 生成密钥
            key_id = self._generate_key_id()
            api_key = self._generate_api_key()
            api_secret = self._generate_api_secret()
            
            # 计算过期时间
            expires_at = None
            if expires_in_days is not None:
                expires_at = datetime.now() + timedelta(days=expires_in_days)
            elif self.config.default_expiry_days > 0:
                expires_at = datetime.now() + timedelta(days=self.config.default_expiry_days)
                
            # 创建密钥对象
            key_obj = APIKey(
                key_id=key_id,
                api_key=api_key,
                api_secret=api_secret,
                name=name,
                description=description,
                status=APIKeyStatus.ACTIVE,
                scopes=scopes,
                client_id=client_id,
                created_at=datetime.now(),
                expires_at=expires_at,
                rate_limit=rate_limit,
                metadata=metadata or {}
            )
            
            # 存储密钥
            self.api_keys[key_id] = key_obj
            self.key_lookup[api_key] = key_id
            
            # 初始化统计
            self.usage_stats[key_id] = {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "last_used": None,
                "created_at": datetime.now()
            }
            
            logger.info(f"创建API密钥: {name} ({key_id})")
            
            return {
                "key_id": key_id,
                "api_key": api_key,
                "api_secret": api_secret,
                "expires_at": expires_at.isoformat() if expires_at else None
            }
            
        except Exception as e:
            logger.error(f"创建API密钥时出错: {e}")
            raise
            
    async def validate_api_key(
        self,
        api_key: str,
        required_scopes: Optional[List[APIKeyScope]] = None,
        request_signature: Optional[str] = None,
        request_timestamp: Optional[str] = None,
        request_data: Optional[str] = None
    ) -> Dict[str, Any]:
        """验证API密钥"""
        try:
            # 检查缓存
            cache_key = f"{api_key}:{':'.join(s.value for s in (required_scopes or []))}"
            if cache_key in self.validation_cache:
                cache_time = self.cache_timestamps.get(cache_key)
                if cache_time and (datetime.now() - cache_time).seconds < self.config.cache_ttl_seconds:
                    cached_result = self.validation_cache[cache_key].copy()
                    if cached_result["valid"]:
                        await self._record_key_usage(cached_result["key_id"])
                    return cached_result
                    
            # 查找密钥
            key_id = self.key_lookup.get(api_key)
            if not key_id:
                result = {
                    "valid": False,
                    "reason": "API key not found",
                    "error_code": "INVALID_KEY"
                }
                self._cache_validation_result(cache_key, result)
                return result
                
            key_obj = self.api_keys[key_id]
            
            # 验证密钥状态
            status_check = await self._check_key_status(key_obj)
            if not status_check["valid"]:
                self._cache_validation_result(cache_key, status_check)
                return status_check
                
            # 验证权限范围
            if required_scopes:
                scope_check = await self._check_key_scopes(key_obj, required_scopes)
                if not scope_check["valid"]:
                    self._cache_validation_result(cache_key, scope_check)
                    return scope_check
                    
            # 验证频率限制
            rate_check = await self._check_rate_limit(key_obj)
            if not rate_check["valid"]:
                self._cache_validation_result(cache_key, rate_check)
                return rate_check
                
            # 验证请求签名（如果提供）
            if (self.config.enable_signature_validation and 
                request_signature and request_timestamp and request_data):
                signature_check = await self._validate_signature(
                    key_obj, request_signature, request_timestamp, request_data
                )
                if not signature_check["valid"]:
                    self._cache_validation_result(cache_key, signature_check)
                    return signature_check
                    
            # 记录使用
            await self._record_key_usage(key_id)
            
            result = {
                "valid": True,
                "key_id": key_id,
                "client_id": key_obj.client_id,
                "scopes": [s.value for s in key_obj.scopes],
                "rate_limit": key_obj.rate_limit,
                "metadata": key_obj.metadata
            }
            
            self._cache_validation_result(cache_key, result)
            return result
            
        except Exception as e:
            logger.error(f"验证API密钥时出错: {e}")
            return {
                "valid": False,
                "reason": "Validation error",
                "error_code": "VALIDATION_ERROR",
                "error": str(e)
            }
            
    async def _check_key_status(self, key_obj: APIKey) -> Dict[str, Any]:
        """检查密钥状态"""
        # 检查是否已撤销或暂停
        if key_obj.status in [APIKeyStatus.REVOKED, APIKeyStatus.SUSPENDED]:
            return {
                "valid": False,
                "reason": f"API key is {key_obj.status.value}",
                "error_code": "KEY_DISABLED"
            }
            
        # 检查是否过期
        if key_obj.expires_at and datetime.now() > key_obj.expires_at:
            # 自动更新状态为过期
            key_obj.status = APIKeyStatus.EXPIRED
            return {
                "valid": False,
                "reason": "API key has expired",
                "error_code": "KEY_EXPIRED",
                "expired_at": key_obj.expires_at.isoformat()
            }
            
        return {"valid": True}
        
    async def _check_key_scopes(self, key_obj: APIKey, required_scopes: List[APIKeyScope]) -> Dict[str, Any]:
        """检查密钥权限范围"""
        key_scopes = set(key_obj.scopes)
        required_scopes_set = set(required_scopes)
        
        # 检查是否有ADMIN权限（可以访问所有范围）
        if APIKeyScope.ADMIN in key_scopes:
            return {"valid": True}
            
        # 检查是否包含所有必需的权限
        if not required_scopes_set.issubset(key_scopes):
            missing_scopes = required_scopes_set - key_scopes
            return {
                "valid": False,
                "reason": "Insufficient permissions",
                "error_code": "INSUFFICIENT_SCOPE",
                "missing_scopes": [s.value for s in missing_scopes],
                "available_scopes": [s.value for s in key_scopes]
            }
            
        return {"valid": True}
        
    async def _check_rate_limit(self, key_obj: APIKey) -> Dict[str, Any]:
        """检查频率限制"""
        key_id = key_obj.key_id
        current_time = datetime.now()
        
        # 初始化追踪记录
        if key_id not in self.rate_limit_tracking:
            self.rate_limit_tracking[key_id] = []
            
        # 清理过期记录（超过1小时）
        cutoff_time = current_time - timedelta(hours=1)
        self.rate_limit_tracking[key_id] = [
            req_time for req_time in self.rate_limit_tracking[key_id]
            if req_time > cutoff_time
        ]
        
        # 检查当前小时请求数
        if len(self.rate_limit_tracking[key_id]) >= key_obj.rate_limit:
            return {
                "valid": False,
                "reason": "Rate limit exceeded",
                "error_code": "RATE_LIMIT_EXCEEDED",
                "limit": key_obj.rate_limit,
                "used": len(self.rate_limit_tracking[key_id]),
                "reset_time": (current_time + timedelta(hours=1)).isoformat()
            }
            
        return {"valid": True}
        
    async def _validate_signature(
        self,
        key_obj: APIKey,
        signature: str,
        timestamp: str,
        request_data: str
    ) -> Dict[str, Any]:
        """验证请求签名"""
        try:
            # 验证时间戳
            request_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            current_time = datetime.now()
            time_diff = abs((current_time - request_time).total_seconds())
            
            if time_diff > self.config.timestamp_tolerance_seconds:
                return {
                    "valid": False,
                    "reason": "Request timestamp is too old or too far in future",
                    "error_code": "INVALID_TIMESTAMP"
                }
                
            # 计算期望的签名
            message = f"{timestamp}:{request_data}"
            expected_signature = hashlib.hmac.new(
                key_obj.api_secret.encode(),
                message.encode(),
                hashlib.sha256
            ).hexdigest()
            
            # 比较签名
            if not secrets.compare_digest(signature, expected_signature):
                return {
                    "valid": False,
                    "reason": "Invalid signature",
                    "error_code": "INVALID_SIGNATURE"
                }
                
            return {"valid": True}
            
        except Exception as e:
            logger.error(f"签名验证时出错: {e}")
            return {
                "valid": False,
                "reason": "Signature validation error",
                "error_code": "SIGNATURE_ERROR"
            }
            
    async def _record_key_usage(self, key_id: str):
        """记录密钥使用"""
        current_time = datetime.now()
        
        # 更新密钥对象
        if key_id in self.api_keys:
            key_obj = self.api_keys[key_id]
            key_obj.last_used_at = current_time
            key_obj.usage_count += 1
            
        # 更新统计
        if key_id in self.usage_stats:
            self.usage_stats[key_id]["total_requests"] += 1
            self.usage_stats[key_id]["last_used"] = current_time
            
        # 记录到频率限制追踪
        if key_id not in self.rate_limit_tracking:
            self.rate_limit_tracking[key_id] = []
        self.rate_limit_tracking[key_id].append(current_time)
        
    def _cache_validation_result(self, cache_key: str, result: Dict[str, Any]):
        """缓存验证结果"""
        if len(self.validation_cache) >= self.config.max_cache_size:
            # 清理最老的缓存条目
            oldest_key = min(self.cache_timestamps.keys(), 
                           key=lambda k: self.cache_timestamps[k])
            del self.validation_cache[oldest_key]
            del self.cache_timestamps[oldest_key]
            
        self.validation_cache[cache_key] = result
        self.cache_timestamps[cache_key] = datetime.now()
        
    def _generate_key_id(self) -> str:
        """生成密钥ID"""
        return f"mk_{secrets.token_hex(16)}"
        
    def _generate_api_key(self) -> str:
        """生成API密钥"""
        return f"ak_{secrets.token_hex(self.config.key_length)}"
        
    def _generate_api_secret(self) -> str:
        """生成API密钥密码"""
        return secrets.token_hex(self.config.secret_length)
        
    async def _key_rotation_worker(self):
        """密钥轮换工作任务"""
        while self.is_started:
            try:
                current_time = datetime.now()
                rotation_cutoff = current_time - timedelta(days=self.config.rotation_interval_days)
                
                for key_id, key_obj in self.api_keys.items():
                    if (key_obj.created_at < rotation_cutoff and 
                        key_obj.status == APIKeyStatus.ACTIVE):
                        
                        logger.info(f"密钥需要轮换: {key_obj.name} ({key_id})")
                        # 这里可以发送轮换通知或自动轮换
                        
                await asyncio.sleep(86400)  # 每天检查一次
                
            except Exception as e:
                logger.error(f"密钥轮换任务出错: {e}")
                await asyncio.sleep(3600)
                
    async def _cache_cleanup_worker(self):
        """缓存清理工作任务"""
        while self.is_started:
            try:
                current_time = datetime.now()
                expired_keys = []
                
                for cache_key, cache_time in self.cache_timestamps.items():
                    if (current_time - cache_time).seconds > self.config.cache_ttl_seconds:
                        expired_keys.append(cache_key)
                        
                for key in expired_keys:
                    del self.validation_cache[key]
                    del self.cache_timestamps[key]
                    
                if expired_keys:
                    logger.debug(f"清理了 {len(expired_keys)} 个过期缓存条目")
                    
                await asyncio.sleep(300)  # 每5分钟清理一次
                
            except Exception as e:
                logger.error(f"缓存清理任务出错: {e}")
                await asyncio.sleep(60)
                
    async def _usage_cleanup_worker(self):
        """使用统计清理工作任务"""
        while self.is_started:
            try:
                current_time = datetime.now()
                cutoff_time = current_time - timedelta(hours=1)
                
                for key_id in list(self.rate_limit_tracking.keys()):
                    self.rate_limit_tracking[key_id] = [
                        req_time for req_time in self.rate_limit_tracking[key_id]
                        if req_time > cutoff_time
                    ]
                    
                    if not self.rate_limit_tracking[key_id]:
                        del self.rate_limit_tracking[key_id]
                        
                await asyncio.sleep(1800)  # 每30分钟清理一次
                
            except Exception as e:
                logger.error(f"使用统计清理任务出错: {e}")
                await asyncio.sleep(300)
                
    async def revoke_api_key(self, key_id: str) -> bool:
        """撤销API密钥"""
        if key_id in self.api_keys:
            key_obj = self.api_keys[key_id]
            key_obj.status = APIKeyStatus.REVOKED
            
            # 从查找表中移除
            if key_obj.api_key in self.key_lookup:
                del self.key_lookup[key_obj.api_key]
                
            logger.info(f"撤销API密钥: {key_obj.name} ({key_id})")
            return True
            
        return False
        
    async def suspend_api_key(self, key_id: str) -> bool:
        """暂停API密钥"""
        if key_id in self.api_keys:
            key_obj = self.api_keys[key_id]
            key_obj.status = APIKeyStatus.SUSPENDED
            logger.info(f"暂停API密钥: {key_obj.name} ({key_id})")
            return True
            
        return False
        
    async def activate_api_key(self, key_id: str) -> bool:
        """激活API密钥"""
        if key_id in self.api_keys:
            key_obj = self.api_keys[key_id]
            if key_obj.status == APIKeyStatus.SUSPENDED:
                key_obj.status = APIKeyStatus.ACTIVE
                # 重新添加到查找表
                self.key_lookup[key_obj.api_key] = key_id
                logger.info(f"激活API密钥: {key_obj.name} ({key_id})")
                return True
                
        return False
        
    def get_api_key_info(self, key_id: str) -> Optional[Dict[str, Any]]:
        """获取API密钥信息"""
        if key_id in self.api_keys:
            key_obj = self.api_keys[key_id]
            usage_stats = self.usage_stats.get(key_id, {})
            
            return {
                "key_id": key_id,
                "name": key_obj.name,
                "description": key_obj.description,
                "status": key_obj.status.value,
                "scopes": [s.value for s in key_obj.scopes],
                "client_id": key_obj.client_id,
                "created_at": key_obj.created_at.isoformat(),
                "expires_at": key_obj.expires_at.isoformat() if key_obj.expires_at else None,
                "last_used_at": key_obj.last_used_at.isoformat() if key_obj.last_used_at else None,
                "usage_count": key_obj.usage_count,
                "rate_limit": key_obj.rate_limit,
                "usage_stats": usage_stats,
                "metadata": key_obj.metadata
            }
            
        return None
        
    def list_api_keys(self, client_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出API密钥"""
        keys = []
        
        for key_id, key_obj in self.api_keys.items():
            if client_id and key_obj.client_id != client_id:
                continue
                
            key_info = self.get_api_key_info(key_id)
            if key_info:
                # 不返回敏感信息
                key_info.pop("api_secret", None)
                keys.append(key_info)
                
        return keys
        
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        total_keys = len(self.api_keys)
        active_keys = sum(1 for k in self.api_keys.values() if k.status == APIKeyStatus.ACTIVE)
        expired_keys = sum(1 for k in self.api_keys.values() if k.status == APIKeyStatus.EXPIRED)
        revoked_keys = sum(1 for k in self.api_keys.values() if k.status == APIKeyStatus.REVOKED)
        
        total_usage = sum(stats.get("total_requests", 0) for stats in self.usage_stats.values())
        
        return {
            "total_keys": total_keys,
            "active_keys": active_keys,
            "expired_keys": expired_keys,
            "revoked_keys": revoked_keys,
            "total_usage": total_usage,
            "cache_size": len(self.validation_cache),
            "rate_limit_tracking": len(self.rate_limit_tracking)
        }
        
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        return {
            "component": "API Key Manager",
            "status": "running" if self.is_started else "stopped",
            "version": self.config.version,
            "statistics": self.get_statistics()
        }