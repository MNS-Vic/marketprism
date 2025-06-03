"""
JWT Security Manager

Week 6 Day 4: API网关安全系统组件
"""

import asyncio
import logging
import json
import hmac
import hashlib
import base64
import secrets
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

class TokenType(Enum):
    """Token类型"""
    ACCESS = "access"
    REFRESH = "refresh"
    ID = "id"

class TokenStatus(Enum):
    """Token状态"""
    VALID = "valid"
    EXPIRED = "expired"
    INVALID = "invalid"
    REVOKED = "revoked"

@dataclass
class JWTClaims:
    """JWT声明"""
    sub: str  # 主题(用户ID)
    iss: str  # 发行者
    aud: str  # 受众
    exp: datetime  # 过期时间
    iat: datetime  # 发行时间
    nbf: Optional[datetime] = None  # 生效时间
    jti: Optional[str] = None  # JWT ID
    scope: List[str] = field(default_factory=list)  # 权限范围
    custom_claims: Dict[str, Any] = field(default_factory=dict)  # 自定义声明

@dataclass
class JWTSecurityManagerConfig:
    """JWT安全管理器配置"""
    enabled: bool = True
    version: str = "1.0.0"
    # 签名配置
    algorithm: str = "HS256"
    secret_key: str = ""
    # Token配置
    access_token_expiry_minutes: int = 60  # 访问令牌1小时过期
    refresh_token_expiry_days: int = 30    # 刷新令牌30天过期
    id_token_expiry_hours: int = 24        # ID令牌24小时过期
    # 发行者配置
    issuer: str = "marketprism-api-gateway"
    audience: str = "marketprism-services"
    # 安全配置
    enable_token_blacklist: bool = True
    max_token_age_hours: int = 720  # 最大令牌年龄30天
    enable_audience_validation: bool = True
    enable_issuer_validation: bool = True
    # 刷新策略
    allow_refresh_token_reuse: bool = False
    enable_token_rotation: bool = True

class JWTSecurityManager:
    """
    JWT Security Manager
    
    企业级JWT安全管理系统：
    - JWT令牌生成与验证
    - 多类型令牌支持（访问/刷新/ID）
    - 令牌黑名单管理
    - 安全声明验证
    - 令牌轮换策略
    """
    
    def __init__(self, config: JWTSecurityManagerConfig):
        self.config = config
        self.is_started = False
        
        # 初始化密钥
        if not self.config.secret_key:
            self.config.secret_key = secrets.token_hex(64)
            
        # 令牌存储
        self.active_tokens: Dict[str, Dict[str, Any]] = {}
        self.blacklisted_tokens: Dict[str, datetime] = {}
        self.refresh_tokens: Dict[str, Dict[str, Any]] = {}
        
        # 统计信息
        self.token_stats: Dict[str, int] = {
            "tokens_issued": 0,
            "tokens_validated": 0,
            "tokens_revoked": 0,
            "validation_failures": 0
        }
        
        # 清理任务
        self.cleanup_task: Optional[asyncio.Task] = None
        
    async def start(self):
        """启动JWT安全管理器"""
        logger.info(f"启动 JWT Security Manager v{self.config.version}")
        
        # 验证配置
        await self._validate_configuration()
        
        # 启动清理任务
        self.cleanup_task = asyncio.create_task(self._token_cleanup_worker())
        
        self.is_started = True
        logger.info("✅ JWT Security Manager 启动完成")
        
    async def stop(self):
        """停止JWT安全管理器"""
        logger.info("停止 JWT Security Manager")
        
        if self.cleanup_task:
            self.cleanup_task.cancel()
            
        self.is_started = False
        
    async def _validate_configuration(self):
        """验证配置"""
        if not self.config.secret_key:
            raise ValueError("JWT secret key is required")
            
        if self.config.algorithm not in ["HS256", "HS384", "HS512"]:
            raise ValueError(f"Unsupported algorithm: {self.config.algorithm}")
            
        logger.info(f"JWT配置验证通过 - 算法: {self.config.algorithm}")
        
    def _encode_token(self, claims: JWTClaims, token_type: TokenType) -> str:
        """编码JWT令牌"""
        try:
            # 构建Header
            header = {
                "alg": self.config.algorithm,
                "typ": "JWT"
            }
            
            # 构建Payload
            payload = {
                "sub": claims.sub,
                "iss": claims.iss,
                "aud": claims.aud,
                "exp": int(claims.exp.timestamp()),
                "iat": int(claims.iat.timestamp()),
                "token_type": token_type.value
            }
            
            if claims.nbf:
                payload["nbf"] = int(claims.nbf.timestamp())
                
            if claims.jti:
                payload["jti"] = claims.jti
                
            if claims.scope:
                payload["scope"] = " ".join(claims.scope)
                
            # 添加自定义声明
            payload.update(claims.custom_claims)
            
            # Base64编码
            header_encoded = base64.urlsafe_b64encode(
                json.dumps(header, separators=(',', ':')).encode()
            ).decode().rstrip('=')
            
            payload_encoded = base64.urlsafe_b64encode(
                json.dumps(payload, separators=(',', ':')).encode()
            ).decode().rstrip('=')
            
            # 生成签名
            message = f"{header_encoded}.{payload_encoded}"
            signature = self._sign_message(message)
            
            # 组装JWT
            jwt_token = f"{message}.{signature}"
            
            return jwt_token
            
        except Exception as e:
            logger.error(f"JWT编码失败: {e}")
            raise
            
    def _decode_token(self, token: str) -> Dict[str, Any]:
        """解码JWT令牌"""
        try:
            # 分割JWT
            parts = token.split('.')
            if len(parts) != 3:
                raise ValueError("Invalid JWT format")
                
            header_encoded, payload_encoded, signature = parts
            
            # 验证签名
            message = f"{header_encoded}.{payload_encoded}"
            expected_signature = self._sign_message(message)
            
            if not hmac.compare_digest(signature, expected_signature):
                raise ValueError("Invalid JWT signature")
                
            # 解码Payload
            payload_decoded = base64.urlsafe_b64decode(
                payload_encoded + '=' * (4 - len(payload_encoded) % 4)
            )
            payload = json.loads(payload_decoded)
            
            return payload
            
        except Exception as e:
            logger.error(f"JWT解码失败: {e}")
            raise
            
    def _sign_message(self, message: str) -> str:
        """签名消息"""
        if self.config.algorithm == "HS256":
            hash_func = hashlib.sha256
        elif self.config.algorithm == "HS384":
            hash_func = hashlib.sha384
        elif self.config.algorithm == "HS512":
            hash_func = hashlib.sha512
        else:
            raise ValueError(f"Unsupported algorithm: {self.config.algorithm}")
            
        signature = hmac.new(
            self.config.secret_key.encode(),
            message.encode(),
            hash_func
        ).digest()
        
        return base64.urlsafe_b64encode(signature).decode().rstrip('=')
        
    async def generate_access_token(
        self,
        user_id: str,
        scopes: List[str],
        custom_claims: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """生成访问令牌"""
        try:
            now = datetime.now()
            exp = now + timedelta(minutes=self.config.access_token_expiry_minutes)
            jti = f"access_{secrets.token_hex(16)}"
            
            claims = JWTClaims(
                sub=user_id,
                iss=self.config.issuer,
                aud=self.config.audience,
                exp=exp,
                iat=now,
                jti=jti,
                scope=scopes,
                custom_claims=custom_claims or {}
            )
            
            token = self._encode_token(claims, TokenType.ACCESS)
            
            # 存储活跃令牌
            self.active_tokens[jti] = {
                "token": token,
                "user_id": user_id,
                "token_type": TokenType.ACCESS,
                "issued_at": now,
                "expires_at": exp,
                "scopes": scopes
            }
            
            self.token_stats["tokens_issued"] += 1
            
            logger.info(f"生成访问令牌: 用户={user_id}, JTI={jti}")
            
            return {
                "access_token": token,
                "token_type": "Bearer",
                "expires_in": self.config.access_token_expiry_minutes * 60,
                "expires_at": exp.isoformat(),
                "jti": jti
            }
            
        except Exception as e:
            logger.error(f"生成访问令牌失败: {e}")
            raise
            
    async def generate_refresh_token(
        self,
        user_id: str,
        access_token_jti: str
    ) -> Dict[str, Any]:
        """生成刷新令牌"""
        try:
            now = datetime.now()
            exp = now + timedelta(days=self.config.refresh_token_expiry_days)
            jti = f"refresh_{secrets.token_hex(16)}"
            
            claims = JWTClaims(
                sub=user_id,
                iss=self.config.issuer,
                aud=self.config.audience,
                exp=exp,
                iat=now,
                jti=jti,
                custom_claims={"access_token_jti": access_token_jti}
            )
            
            token = self._encode_token(claims, TokenType.REFRESH)
            
            # 存储刷新令牌
            self.refresh_tokens[jti] = {
                "token": token,
                "user_id": user_id,
                "access_token_jti": access_token_jti,
                "issued_at": now,
                "expires_at": exp,
                "used": False
            }
            
            logger.info(f"生成刷新令牌: 用户={user_id}, JTI={jti}")
            
            return {
                "refresh_token": token,
                "expires_in": self.config.refresh_token_expiry_days * 24 * 3600,
                "expires_at": exp.isoformat(),
                "jti": jti
            }
            
        except Exception as e:
            logger.error(f"生成刷新令牌失败: {e}")
            raise
            
    async def validate_token(
        self,
        token: str,
        required_scopes: Optional[List[str]] = None,
        token_type: Optional[TokenType] = None
    ) -> Dict[str, Any]:
        """验证JWT令牌"""
        try:
            self.token_stats["tokens_validated"] += 1
            
            # 解码令牌
            payload = self._decode_token(token)
            
            # 基础验证
            validation_result = await self._validate_token_claims(payload, token_type)
            if not validation_result["valid"]:
                self.token_stats["validation_failures"] += 1
                return validation_result
                
            # 检查黑名单
            jti = payload.get("jti")
            if jti and jti in self.blacklisted_tokens:
                self.token_stats["validation_failures"] += 1
                return {
                    "valid": False,
                    "reason": "Token has been revoked",
                    "error_code": "TOKEN_REVOKED"
                }
                
            # 权限范围验证
            if required_scopes:
                scope_check = await self._validate_token_scopes(payload, required_scopes)
                if not scope_check["valid"]:
                    self.token_stats["validation_failures"] += 1
                    return scope_check
                    
            # 返回验证结果
            return {
                "valid": True,
                "user_id": payload["sub"],
                "scopes": payload.get("scope", "").split() if payload.get("scope") else [],
                "token_type": payload.get("token_type"),
                "jti": jti,
                "issued_at": datetime.fromtimestamp(payload["iat"]).isoformat(),
                "expires_at": datetime.fromtimestamp(payload["exp"]).isoformat(),
                "custom_claims": {k: v for k, v in payload.items() 
                                if k not in ["sub", "iss", "aud", "exp", "iat", "nbf", "jti", "scope", "token_type"]}
            }
            
        except Exception as e:
            self.token_stats["validation_failures"] += 1
            logger.error(f"令牌验证失败: {e}")
            return {
                "valid": False,
                "reason": "Token validation error",
                "error_code": "VALIDATION_ERROR",
                "error": str(e)
            }
            
    async def _validate_token_claims(self, payload: Dict[str, Any], expected_type: Optional[TokenType] = None) -> Dict[str, Any]:
        """验证令牌声明"""
        now = datetime.now()
        
        # 验证过期时间
        if "exp" not in payload:
            return {"valid": False, "reason": "Missing expiration claim", "error_code": "MISSING_EXP"}
            
        exp = datetime.fromtimestamp(payload["exp"])
        if now >= exp:
            return {"valid": False, "reason": "Token has expired", "error_code": "TOKEN_EXPIRED"}
            
        # 验证生效时间
        if "nbf" in payload:
            nbf = datetime.fromtimestamp(payload["nbf"])
            if now < nbf:
                return {"valid": False, "reason": "Token not yet valid", "error_code": "TOKEN_NOT_YET_VALID"}
                
        # 验证发行者
        if self.config.enable_issuer_validation:
            if payload.get("iss") != self.config.issuer:
                return {"valid": False, "reason": "Invalid issuer", "error_code": "INVALID_ISSUER"}
                
        # 验证受众
        if self.config.enable_audience_validation:
            aud = payload.get("aud")
            if aud != self.config.audience:
                return {"valid": False, "reason": "Invalid audience", "error_code": "INVALID_AUDIENCE"}
                
        # 验证令牌类型
        if expected_type:
            token_type = payload.get("token_type")
            if token_type != expected_type.value:
                return {"valid": False, "reason": f"Expected {expected_type.value} token", "error_code": "INVALID_TOKEN_TYPE"}
                
        # 验证令牌年龄
        if "iat" in payload:
            iat = datetime.fromtimestamp(payload["iat"])
            age_hours = (now - iat).total_seconds() / 3600
            if age_hours > self.config.max_token_age_hours:
                return {"valid": False, "reason": "Token too old", "error_code": "TOKEN_TOO_OLD"}
                
        return {"valid": True}
        
    async def _validate_token_scopes(self, payload: Dict[str, Any], required_scopes: List[str]) -> Dict[str, Any]:
        """验证令牌权限范围"""
        token_scopes = payload.get("scope", "").split() if payload.get("scope") else []
        token_scopes_set = set(token_scopes)
        required_scopes_set = set(required_scopes)
        
        # 检查是否包含所有必需的权限
        if not required_scopes_set.issubset(token_scopes_set):
            missing_scopes = required_scopes_set - token_scopes_set
            return {
                "valid": False,
                "reason": "Insufficient token scope",
                "error_code": "INSUFFICIENT_SCOPE",
                "missing_scopes": list(missing_scopes),
                "available_scopes": token_scopes
            }
            
        return {"valid": True}
        
    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """使用刷新令牌获取新的访问令牌"""
        try:
            # 验证刷新令牌
            validation = await self.validate_token(refresh_token, token_type=TokenType.REFRESH)
            if not validation["valid"]:
                return validation
                
            user_id = validation["user_id"]
            jti = validation["jti"]
            
            # 检查刷新令牌是否已使用
            refresh_info = self.refresh_tokens.get(jti)
            if not refresh_info:
                return {"valid": False, "reason": "Refresh token not found", "error_code": "REFRESH_TOKEN_NOT_FOUND"}
                
            if refresh_info["used"] and not self.config.allow_refresh_token_reuse:
                return {"valid": False, "reason": "Refresh token already used", "error_code": "REFRESH_TOKEN_USED"}
                
            # 标记刷新令牌已使用
            refresh_info["used"] = True
            
            # 获取原访问令牌的权限范围
            old_access_jti = refresh_info["access_token_jti"]
            old_access_info = self.active_tokens.get(old_access_jti, {})
            scopes = old_access_info.get("scopes", [])
            
            # 生成新的访问令牌
            new_access_token = await self.generate_access_token(user_id, scopes)
            
            # 如果启用令牌轮换，生成新的刷新令牌
            new_refresh_token = None
            if self.config.enable_token_rotation:
                new_refresh_token = await self.generate_refresh_token(
                    user_id, 
                    new_access_token["jti"]
                )
                # 撤销旧的刷新令牌
                await self.revoke_token(jti)
                
            result = {"access_token": new_access_token}
            if new_refresh_token:
                result["refresh_token"] = new_refresh_token
                
            logger.info(f"刷新令牌成功: 用户={user_id}")
            return result
            
        except Exception as e:
            logger.error(f"刷新令牌失败: {e}")
            return {
                "valid": False,
                "reason": "Token refresh error",
                "error_code": "REFRESH_ERROR",
                "error": str(e)
            }
            
    async def revoke_token(self, jti: str) -> bool:
        """撤销令牌"""
        try:
            revoked = False
            
            # 撤销访问令牌
            if jti in self.active_tokens:
                del self.active_tokens[jti]
                revoked = True
                
            # 撤销刷新令牌
            if jti in self.refresh_tokens:
                del self.refresh_tokens[jti]
                revoked = True
                
            # 添加到黑名单
            if self.config.enable_token_blacklist:
                self.blacklisted_tokens[jti] = datetime.now()
                revoked = True
                
            if revoked:
                self.token_stats["tokens_revoked"] += 1
                logger.info(f"撤销令牌: JTI={jti}")
                
            return revoked
            
        except Exception as e:
            logger.error(f"撤销令牌失败: {e}")
            return False
            
    async def revoke_user_tokens(self, user_id: str) -> int:
        """撤销用户的所有令牌"""
        revoked_count = 0
        
        # 撤销访问令牌
        for jti, token_info in list(self.active_tokens.items()):
            if token_info["user_id"] == user_id:
                await self.revoke_token(jti)
                revoked_count += 1
                
        # 撤销刷新令牌
        for jti, token_info in list(self.refresh_tokens.items()):
            if token_info["user_id"] == user_id:
                await self.revoke_token(jti)
                revoked_count += 1
                
        logger.info(f"撤销用户令牌: 用户={user_id}, 数量={revoked_count}")
        return revoked_count
        
    async def _token_cleanup_worker(self):
        """令牌清理工作任务"""
        while self.is_started:
            try:
                current_time = datetime.now()
                
                # 清理过期的访问令牌
                expired_access = []
                for jti, token_info in self.active_tokens.items():
                    if current_time >= token_info["expires_at"]:
                        expired_access.append(jti)
                        
                for jti in expired_access:
                    del self.active_tokens[jti]
                    
                # 清理过期的刷新令牌
                expired_refresh = []
                for jti, token_info in self.refresh_tokens.items():
                    if current_time >= token_info["expires_at"]:
                        expired_refresh.append(jti)
                        
                for jti in expired_refresh:
                    del self.refresh_tokens[jti]
                    
                # 清理过期的黑名单条目
                expired_blacklist = []
                for jti, revoked_time in self.blacklisted_tokens.items():
                    # 黑名单条目保留24小时
                    if (current_time - revoked_time).total_seconds() > 86400:
                        expired_blacklist.append(jti)
                        
                for jti in expired_blacklist:
                    del self.blacklisted_tokens[jti]
                    
                if expired_access or expired_refresh or expired_blacklist:
                    logger.debug(f"清理过期令牌: 访问令牌={len(expired_access)}, 刷新令牌={len(expired_refresh)}, 黑名单={len(expired_blacklist)}")
                    
                await asyncio.sleep(300)  # 每5分钟清理一次
                
            except Exception as e:
                logger.error(f"令牌清理任务出错: {e}")
                await asyncio.sleep(60)
                
    def get_token_info(self, jti: str) -> Optional[Dict[str, Any]]:
        """获取令牌信息"""
        # 检查访问令牌
        if jti in self.active_tokens:
            token_info = self.active_tokens[jti]
            return {
                "jti": jti,
                "token_type": token_info["token_type"].value,
                "user_id": token_info["user_id"],
                "issued_at": token_info["issued_at"].isoformat(),
                "expires_at": token_info["expires_at"].isoformat(),
                "scopes": token_info.get("scopes", [])
            }
            
        # 检查刷新令牌
        if jti in self.refresh_tokens:
            token_info = self.refresh_tokens[jti]
            return {
                "jti": jti,
                "token_type": "refresh",
                "user_id": token_info["user_id"],
                "issued_at": token_info["issued_at"].isoformat(),
                "expires_at": token_info["expires_at"].isoformat(),
                "used": token_info["used"]
            }
            
        return None
        
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "active_tokens": len(self.active_tokens),
            "refresh_tokens": len(self.refresh_tokens),
            "blacklisted_tokens": len(self.blacklisted_tokens),
            "tokens_issued": self.token_stats["tokens_issued"],
            "tokens_validated": self.token_stats["tokens_validated"],
            "tokens_revoked": self.token_stats["tokens_revoked"],
            "validation_failures": self.token_stats["validation_failures"]
        }
        
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        return {
            "component": "JWT Security Manager",
            "status": "running" if self.is_started else "stopped",
            "version": self.config.version,
            "algorithm": self.config.algorithm,
            "statistics": self.get_statistics()
        }