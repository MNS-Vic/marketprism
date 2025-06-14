"""
配置加密系统

提供配置数据的加密、解密和安全存储功能。
支持多种加密算法、密钥管理和安全策略。
"""

import os
import json
import base64
import hashlib
import secrets
import logging
from typing import Dict, Any, Optional, Union, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
# import asyncio  # 移除不必要的导入
from threading import Lock

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    from cryptography.hazmat.backends import default_backend
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

logger = logging.getLogger(__name__)


class EncryptionType(Enum):
    """加密类型"""
    AES_256_GCM = "aes_256_gcm"
    AES_256_CBC = "aes_256_cbc"
    AES_128_GCM = "aes_128_gcm"
    RSA_2048 = "rsa_2048"
    RSA_4096 = "rsa_4096"
    HYBRID = "hybrid"  # RSA + AES 混合加密


class KeyDerivationType(Enum):
    """密钥派生类型"""
    PBKDF2 = "pbkdf2"
    SCRYPT = "scrypt"
    DIRECT = "direct"


class SecurityLevel(Enum):
    """安全级别"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class EncryptionConfig:
    """加密配置"""
    encryption_type: EncryptionType = EncryptionType.AES_256_GCM
    key_derivation_type: KeyDerivationType = KeyDerivationType.PBKDF2
    security_level: SecurityLevel = SecurityLevel.HIGH
    iterations: int = 100000  # PBKDF2/Scrypt 迭代次数
    salt_length: int = 32  # 盐值长度
    key_rotation_interval: int = 30  # 密钥轮换间隔（天）
    compress_before_encrypt: bool = True
    verify_integrity: bool = True
    secure_delete: bool = True  # 安全删除


@dataclass
class EncryptedData:
    """加密数据结构"""
    data: bytes
    encryption_type: EncryptionType
    salt: Optional[bytes] = None
    iv: Optional[bytes] = None
    tag: Optional[bytes] = None
    public_key: Optional[bytes] = None
    signature: Optional[bytes] = None
    timestamp: datetime = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    key_id: Optional[str] = None
    checksum: Optional[str] = None


@dataclass
class EncryptionKey:
    """加密密钥"""
    key_id: str
    key_data: bytes
    encryption_type: EncryptionType
    created_at: datetime
    expires_at: Optional[datetime] = None
    usage_count: int = 0
    max_usage: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class EncryptionError(Exception):
    """加密错误"""
    pass


class DecryptionError(Exception):
    """解密错误"""
    pass


class KeyManagementError(Exception):
    """密钥管理错误"""
    pass


class ConfigEncryption:
    """
    配置加密系统
    
    提供配置数据的加密、解密和安全存储功能。
    支持多种加密算法、密钥管理和安全策略。
    """
    
    def __init__(
        self,
        config: Optional[EncryptionConfig] = None,
        key_storage_path: Optional[str] = None,
        master_password: Optional[str] = None
    ):
        if not CRYPTO_AVAILABLE:
            raise EncryptionError("Cryptography library not available")
        
        self.config = config or EncryptionConfig()
        self.key_storage_path = Path(key_storage_path) if key_storage_path else None
        self.master_password = master_password
        
        # 密钥存储
        self.keys: Dict[str, EncryptionKey] = {}
        self.active_key_id: Optional[str] = None
        
        # 性能统计
        self.encryption_count = 0
        self.decryption_count = 0
        self.key_generation_count = 0
        self.key_rotation_count = 0
        
        # 线程安全
        self._lock = Lock()
        
        # 初始化
        self._initialize()
    
    def _initialize(self):
        """初始化加密系统"""
        try:
            # 加载密钥
            if self.key_storage_path and self.key_storage_path.exists():
                self._load_keys()
            
            # 生成默认密钥
            if not self.keys:
                self._generate_default_key()
            
            logger.info(f"ConfigEncryption initialized with {len(self.keys)} keys")
            
        except Exception as e:
            logger.error(f"Failed to initialize ConfigEncryption: {e}")
            raise EncryptionError(f"Initialization failed: {e}")
    
    def encrypt(
        self,
        data: Union[str, bytes, Dict[str, Any]],
        key_id: Optional[str] = None
    ) -> EncryptedData:
        """
        加密数据
        
        Args:
            data: 要加密的数据
            key_id: 密钥ID，为空则使用活跃密钥
            
        Returns:
            EncryptedData: 加密后的数据
        """
        with self._lock:
            try:
                # 数据预处理
                if isinstance(data, dict):
                    data = json.dumps(data, ensure_ascii=False).encode('utf-8')
                elif isinstance(data, str):
                    data = data.encode('utf-8')
                
                # 压缩数据
                if self.config.compress_before_encrypt:
                    data = self._compress_data(data)
                
                # 获取密钥
                key_id = key_id or self.active_key_id
                if not key_id or key_id not in self.keys:
                    raise EncryptionError(f"Key not found: {key_id}")
                
                encryption_key = self.keys[key_id]
                
                # 根据加密类型进行加密
                if encryption_key.encryption_type == EncryptionType.AES_256_GCM:
                    encrypted_data = self._encrypt_aes_gcm(data, encryption_key)
                elif encryption_key.encryption_type == EncryptionType.AES_256_CBC:
                    encrypted_data = self._encrypt_aes_cbc(data, encryption_key)
                elif encryption_key.encryption_type == EncryptionType.RSA_2048:
                    encrypted_data = self._encrypt_rsa(data, encryption_key)
                elif encryption_key.encryption_type == EncryptionType.HYBRID:
                    encrypted_data = self._encrypt_hybrid(data, encryption_key)
                else:
                    raise EncryptionError(f"Unsupported encryption type: {encryption_key.encryption_type}")
                
                # 更新使用计数
                encryption_key.usage_count += 1
                
                # 添加完整性校验
                if self.config.verify_integrity:
                    encrypted_data.checksum = self._calculate_checksum(encrypted_data.data)
                
                # 更新统计
                self.encryption_count += 1
                
                logger.debug(f"Data encrypted successfully with key {key_id}")
                return encrypted_data
                
            except Exception as e:
                logger.error(f"Encryption failed: {e}")
                raise EncryptionError(f"Encryption failed: {e}")
    
    def decrypt(
        self,
        encrypted_data: EncryptedData,
        key_id: Optional[str] = None
    ) -> bytes:
        """
        解密数据
        
        Args:
            encrypted_data: 加密的数据
            key_id: 密钥ID，为空则使用数据中的密钥ID
            
        Returns:
            bytes: 解密后的数据
        """
        with self._lock:
            try:
                # 获取密钥
                key_id = key_id or encrypted_data.key_id
                if not key_id or key_id not in self.keys:
                    raise DecryptionError(f"Key not found: {key_id}")
                
                encryption_key = self.keys[key_id]
                
                # 验证完整性
                if self.config.verify_integrity and encrypted_data.checksum:
                    calculated_checksum = self._calculate_checksum(encrypted_data.data)
                    if calculated_checksum != encrypted_data.checksum:
                        raise DecryptionError("Data integrity check failed")
                
                # 根据加密类型进行解密
                if encrypted_data.encryption_type == EncryptionType.AES_256_GCM:
                    data = self._decrypt_aes_gcm(encrypted_data, encryption_key)
                elif encrypted_data.encryption_type == EncryptionType.AES_256_CBC:
                    data = self._decrypt_aes_cbc(encrypted_data, encryption_key)
                elif encrypted_data.encryption_type == EncryptionType.RSA_2048:
                    data = self._decrypt_rsa(encrypted_data, encryption_key)
                elif encrypted_data.encryption_type == EncryptionType.HYBRID:
                    data = self._decrypt_hybrid(encrypted_data, encryption_key)
                else:
                    raise DecryptionError(f"Unsupported encryption type: {encrypted_data.encryption_type}")
                
                # 解压缩数据
                if self.config.compress_before_encrypt:
                    data = self._decompress_data(data)
                
                # 更新统计
                self.decryption_count += 1
                
                logger.debug(f"Data decrypted successfully with key {key_id}")
                return data
                
            except Exception as e:
                logger.error(f"Decryption failed: {e}")
                raise DecryptionError(f"Decryption failed: {e}")
    
    def encrypt_config_value(
        self,
        key: str,
        value: Any,
        encryption_key_id: Optional[str] = None
    ) -> str:
        """
        加密配置值并返回Base64编码的字符串
        
        Args:
            key: 配置键
            value: 配置值
            encryption_key_id: 加密密钥ID
            
        Returns:
            str: Base64编码的加密数据
        """
        try:
            # 创建配置数据
            config_data = {
                'key': key,
                'value': value,
                'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            
            # 加密数据
            encrypted_data = self.encrypt(config_data, encryption_key_id)
            
            # 序列化并编码
            serialized_data = self._serialize_encrypted_data(encrypted_data)
            return base64.b64encode(serialized_data).decode('utf-8')
            
        except Exception as e:
            logger.error(f"Failed to encrypt config value for key {key}: {e}")
            raise EncryptionError(f"Config value encryption failed: {e}")
    
    def decrypt_config_value(self, encrypted_value: str) -> Tuple[str, Any]:
        """
        解密配置值
        
        Args:
            encrypted_value: Base64编码的加密数据
            
        Returns:
            Tuple[str, Any]: (配置键, 配置值)
        """
        try:
            # 解码数据
            serialized_data = base64.b64decode(encrypted_value.encode('utf-8'))
            
            # 反序列化
            encrypted_data = self._deserialize_encrypted_data(serialized_data)
            
            # 解密数据
            decrypted_data = self.decrypt(encrypted_data)
            
            # 解析配置数据
            config_data = json.loads(decrypted_data.decode('utf-8'))
            
            return config_data['key'], config_data['value']
            
        except Exception as e:
            logger.error(f"Failed to decrypt config value: {e}")
            raise DecryptionError(f"Config value decryption failed: {e}")
    
    def generate_key(
        self,
        encryption_type: EncryptionType = None,
        key_id: Optional[str] = None
    ) -> str:
        """
        生成新的加密密钥
        
        Args:
            encryption_type: 加密类型
            key_id: 密钥ID，为空则自动生成
            
        Returns:
            str: 密钥ID
        """
        with self._lock:
            try:
                encryption_type = encryption_type or self.config.encryption_type
                key_id = key_id or self._generate_key_id()
                
                # 生成密钥
                if encryption_type in [EncryptionType.AES_256_GCM, EncryptionType.AES_256_CBC]:
                    key_data = secrets.token_bytes(32)  # 256 bits
                elif encryption_type == EncryptionType.AES_128_GCM:
                    key_data = secrets.token_bytes(16)  # 128 bits
                elif encryption_type in [EncryptionType.RSA_2048, EncryptionType.RSA_4096]:
                    key_size = 2048 if encryption_type == EncryptionType.RSA_2048 else 4096
                    private_key = rsa.generate_private_key(
                        public_exponent=65537,
                        key_size=key_size,
                        backend=default_backend()
                    )
                    key_data = private_key.private_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PrivateFormat.PKCS8,
                        encryption_algorithm=serialization.NoEncryption()
                    )
                else:
                    raise KeyManagementError(f"Unsupported encryption type: {encryption_type}")
                
                # 创建密钥对象
                encryption_key = EncryptionKey(
                    key_id=key_id,
                    key_data=key_data,
                    encryption_type=encryption_type,
                    created_at=datetime.datetime.now(datetime.timezone.utc),
                    expires_at=datetime.datetime.now(datetime.timezone.utc) + timedelta(days=self.config.key_rotation_interval)
                )
                
                # 存储密钥
                self.keys[key_id] = encryption_key
                
                # 设置为活跃密钥
                if not self.active_key_id:
                    self.active_key_id = key_id
                
                # 保存密钥
                if self.key_storage_path:
                    self._save_keys()
                
                # 更新统计
                self.key_generation_count += 1
                
                logger.info(f"Generated new key: {key_id} ({encryption_type.value})")
                return key_id
                
            except Exception as e:
                logger.error(f"Key generation failed: {e}")
                raise KeyManagementError(f"Key generation failed: {e}")
    
    def rotate_key(self, old_key_id: str) -> str:
        """
        轮换密钥
        
        Args:
            old_key_id: 旧密钥ID
            
        Returns:
            str: 新密钥ID
        """
        with self._lock:
            try:
                if old_key_id not in self.keys:
                    raise KeyManagementError(f"Key not found: {old_key_id}")
                
                old_key = self.keys[old_key_id]
                
                # 生成新密钥
                new_key_id = self.generate_key(old_key.encryption_type)
                
                # 更新活跃密钥
                if self.active_key_id == old_key_id:
                    self.active_key_id = new_key_id
                
                # 标记旧密钥过期
                old_key.expires_at = datetime.datetime.now(datetime.timezone.utc)
                
                # 更新统计
                self.key_rotation_count += 1
                
                logger.info(f"Key rotated: {old_key_id} -> {new_key_id}")
                return new_key_id
                
            except Exception as e:
                logger.error(f"Key rotation failed: {e}")
                raise KeyManagementError(f"Key rotation failed: {e}")
    
    def delete_key(self, key_id: str, secure: bool = True) -> bool:
        """
        删除密钥
        
        Args:
            key_id: 密钥ID
            secure: 是否安全删除
            
        Returns:
            bool: 删除是否成功
        """
        with self._lock:
            try:
                if key_id not in self.keys:
                    return False
                
                # 安全删除密钥数据
                if secure and self.config.secure_delete:
                    key_data = self.keys[key_id].key_data
                    self._secure_delete_bytes(key_data)
                
                # 删除密钥
                del self.keys[key_id]
                
                # 更新活跃密钥
                if self.active_key_id == key_id:
                    self.active_key_id = next(iter(self.keys.keys())) if self.keys else None
                
                # 保存密钥
                if self.key_storage_path:
                    self._save_keys()
                
                logger.info(f"Key deleted: {key_id}")
                return True
                
            except Exception as e:
                logger.error(f"Key deletion failed: {e}")
                return False
    
    def list_keys(self) -> List[Dict[str, Any]]:
        """
        列出所有密钥
        
        Returns:
            List[Dict[str, Any]]: 密钥信息列表
        """
        with self._lock:
            keys_info = []
            for key_id, key in self.keys.items():
                keys_info.append({
                    'key_id': key_id,
                    'encryption_type': key.encryption_type.value,
                    'created_at': key.created_at.isoformat(),
                    'expires_at': key.expires_at.isoformat() if key.expires_at else None,
                    'usage_count': key.usage_count,
                    'max_usage': key.max_usage,
                    'is_active': key_id == self.active_key_id,
                    'is_expired': key.expires_at and key.expires_at < datetime.datetime.now(datetime.timezone.utc),
                    'metadata': key.metadata
                })
            return keys_info
    
    def get_encryption_stats(self) -> Dict[str, Any]:
        """
        获取加密统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        with self._lock:
            return {
                'encryption_count': self.encryption_count,
                'decryption_count': self.decryption_count,
                'key_generation_count': self.key_generation_count,
                'key_rotation_count': self.key_rotation_count,
                'total_keys': len(self.keys),
                'active_key_id': self.active_key_id,
                'expired_keys': len([k for k in self.keys.values() 
                                   if k.expires_at and k.expires_at < datetime.datetime.now(datetime.timezone.utc)]),
                'config': {
                    'encryption_type': self.config.encryption_type.value,
                    'security_level': self.config.security_level.value,
                    'key_rotation_interval': self.config.key_rotation_interval
                }
            }
    
    # AES-GCM 加密/解密
    def _encrypt_aes_gcm(self, data: bytes, key: EncryptionKey) -> EncryptedData:
        """AES-GCM 加密"""
        iv = secrets.token_bytes(12)  # 96-bit IV for GCM
        cipher = Cipher(algorithms.AES(key.key_data), modes.GCM(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        
        ciphertext = encryptor.update(data) + encryptor.finalize()
        
        return EncryptedData(
            data=ciphertext,
            encryption_type=key.encryption_type,
            iv=iv,
            tag=encryptor.tag,
            key_id=key.key_id
        )
    
    def _decrypt_aes_gcm(self, encrypted_data: EncryptedData, key: EncryptionKey) -> bytes:
        """AES-GCM 解密"""
        cipher = Cipher(
            algorithms.AES(key.key_data),
            modes.GCM(encrypted_data.iv, encrypted_data.tag),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()
        
        return decryptor.update(encrypted_data.data) + decryptor.finalize()
    
    # AES-CBC 加密/解密
    def _encrypt_aes_cbc(self, data: bytes, key: EncryptionKey) -> EncryptedData:
        """AES-CBC 加密"""
        iv = secrets.token_bytes(16)  # 128-bit IV for CBC
        
        # PKCS7 padding
        padding_length = 16 - (len(data) % 16)
        padded_data = data + bytes([padding_length] * padding_length)
        
        cipher = Cipher(algorithms.AES(key.key_data), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        
        ciphertext = encryptor.update(padded_data) + encryptor.finalize()
        
        return EncryptedData(
            data=ciphertext,
            encryption_type=key.encryption_type,
            iv=iv,
            key_id=key.key_id
        )
    
    def _decrypt_aes_cbc(self, encrypted_data: EncryptedData, key: EncryptionKey) -> bytes:
        """AES-CBC 解密"""
        cipher = Cipher(
            algorithms.AES(key.key_data),
            modes.CBC(encrypted_data.iv),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()
        
        padded_data = decryptor.update(encrypted_data.data) + decryptor.finalize()
        
        # Remove PKCS7 padding
        padding_length = padded_data[-1]
        return padded_data[:-padding_length]
    
    # RSA 加密/解密
    def _encrypt_rsa(self, data: bytes, key: EncryptionKey) -> EncryptedData:
        """RSA 加密"""
        private_key = serialization.load_pem_private_key(
            key.key_data,
            password=None,
            backend=default_backend()
        )
        public_key = private_key.public_key()
        
        # RSA 有大小限制，需要分块加密
        max_chunk_size = (private_key.key_size // 8) - 42  # OAEP padding overhead
        encrypted_chunks = []
        
        for i in range(0, len(data), max_chunk_size):
            chunk = data[i:i + max_chunk_size]
            encrypted_chunk = public_key.encrypt(
                chunk,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            encrypted_chunks.append(encrypted_chunk)
        
        # 合并加密块
        encrypted_data = b''.join(encrypted_chunks)
        
        # 存储公钥
        public_key_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        return EncryptedData(
            data=encrypted_data,
            encryption_type=key.encryption_type,
            public_key=public_key_bytes,
            key_id=key.key_id
        )
    
    def _decrypt_rsa(self, encrypted_data: EncryptedData, key: EncryptionKey) -> bytes:
        """RSA 解密"""
        private_key = serialization.load_pem_private_key(
            key.key_data,
            password=None,
            backend=default_backend()
        )
        
        # 计算块大小
        key_size_bytes = private_key.key_size // 8
        encrypted_chunks = []
        
        # 分割加密数据
        for i in range(0, len(encrypted_data.data), key_size_bytes):
            encrypted_chunks.append(encrypted_data.data[i:i + key_size_bytes])
        
        # 解密每个块
        decrypted_chunks = []
        for encrypted_chunk in encrypted_chunks:
            decrypted_chunk = private_key.decrypt(
                encrypted_chunk,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            decrypted_chunks.append(decrypted_chunk)
        
        return b''.join(decrypted_chunks)
    
    # 混合加密/解密 (RSA + AES)
    def _encrypt_hybrid(self, data: bytes, key: EncryptionKey) -> EncryptedData:
        """混合加密 (RSA + AES)"""
        # 生成随机 AES 密钥
        aes_key = secrets.token_bytes(32)  # 256-bit AES key
        
        # 用 AES 加密数据
        iv = secrets.token_bytes(12)  # 96-bit IV for GCM
        cipher = Cipher(algorithms.AES(aes_key), modes.GCM(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        
        ciphertext = encryptor.update(data) + encryptor.finalize()
        
        # 用 RSA 加密 AES 密钥
        private_key = serialization.load_pem_private_key(
            key.key_data,
            password=None,
            backend=default_backend()
        )
        public_key = private_key.public_key()
        
        encrypted_aes_key = public_key.encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        # 组合加密数据: encrypted_aes_key + iv + tag + ciphertext
        combined_data = (
            len(encrypted_aes_key).to_bytes(4, 'big') +
            encrypted_aes_key +
            iv +
            encryptor.tag +
            ciphertext
        )
        
        return EncryptedData(
            data=combined_data,
            encryption_type=key.encryption_type,
            key_id=key.key_id
        )
    
    def _decrypt_hybrid(self, encrypted_data: EncryptedData, key: EncryptionKey) -> bytes:
        """混合解密 (RSA + AES)"""
        data = encrypted_data.data
        
        # 解析组合数据
        aes_key_length = int.from_bytes(data[:4], 'big')
        encrypted_aes_key = data[4:4 + aes_key_length]
        iv = data[4 + aes_key_length:4 + aes_key_length + 12]
        tag = data[4 + aes_key_length + 12:4 + aes_key_length + 12 + 16]
        ciphertext = data[4 + aes_key_length + 12 + 16:]
        
        # 用 RSA 解密 AES 密钥
        private_key = serialization.load_pem_private_key(
            key.key_data,
            password=None,
            backend=default_backend()
        )
        
        aes_key = private_key.decrypt(
            encrypted_aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        # 用 AES 解密数据
        cipher = Cipher(algorithms.AES(aes_key), modes.GCM(iv, tag), backend=default_backend())
        decryptor = cipher.decryptor()
        
        return decryptor.update(ciphertext) + decryptor.finalize()
    
    def _compress_data(self, data: bytes) -> bytes:
        """压缩数据"""
        try:
            import gzip
            return gzip.compress(data)
        except ImportError:
            return data
    
    def _decompress_data(self, data: bytes) -> bytes:
        """解压缩数据"""
        try:
            import gzip
            return gzip.decompress(data)
        except ImportError:
            return data
    
    def _calculate_checksum(self, data: bytes) -> str:
        """计算校验和"""
        return hashlib.sha256(data).hexdigest()
    
    def _generate_key_id(self) -> str:
        """生成密钥ID"""
        return f"key_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(8)}"
    
    def _generate_default_key(self):
        """生成默认密钥"""
        key_id = self.generate_key()
        logger.info(f"Generated default key: {key_id}")
    
    def _serialize_encrypted_data(self, encrypted_data: EncryptedData) -> bytes:
        """序列化加密数据"""
        data_dict = {
            'data': base64.b64encode(encrypted_data.data).decode('utf-8'),
            'encryption_type': encrypted_data.encryption_type.value,
            'salt': base64.b64encode(encrypted_data.salt).decode('utf-8') if encrypted_data.salt else None,
            'iv': base64.b64encode(encrypted_data.iv).decode('utf-8') if encrypted_data.iv else None,
            'tag': base64.b64encode(encrypted_data.tag).decode('utf-8') if encrypted_data.tag else None,
            'public_key': base64.b64encode(encrypted_data.public_key).decode('utf-8') if encrypted_data.public_key else None,
            'timestamp': encrypted_data.timestamp.isoformat(),
            'key_id': encrypted_data.key_id,
            'checksum': encrypted_data.checksum
        }
        return json.dumps(data_dict).encode('utf-8')
    
    def _deserialize_encrypted_data(self, data: bytes) -> EncryptedData:
        """反序列化加密数据"""
        data_dict = json.loads(data.decode('utf-8'))
        
        return EncryptedData(
            data=base64.b64decode(data_dict['data']),
            encryption_type=EncryptionType(data_dict['encryption_type']),
            salt=base64.b64decode(data_dict['salt']) if data_dict['salt'] else None,
            iv=base64.b64decode(data_dict['iv']) if data_dict['iv'] else None,
            tag=base64.b64decode(data_dict['tag']) if data_dict['tag'] else None,
            public_key=base64.b64decode(data_dict['public_key']) if data_dict['public_key'] else None,
            timestamp=datetime.fromisoformat(data_dict['timestamp']),
            key_id=data_dict['key_id'],
            checksum=data_dict['checksum']
        )
    
    def _save_keys(self):
        """保存密钥到文件"""
        if not self.key_storage_path:
            return
        
        try:
            # 确保目录存在
            self.key_storage_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 序列化密钥数据
            keys_data = {}
            for key_id, key in self.keys.items():
                keys_data[key_id] = {
                    'key_data': base64.b64encode(key.key_data).decode('utf-8'),
                    'encryption_type': key.encryption_type.value,
                    'created_at': key.created_at.isoformat(),
                    'expires_at': key.expires_at.isoformat() if key.expires_at else None,
                    'usage_count': key.usage_count,
                    'max_usage': key.max_usage,
                    'metadata': key.metadata
                }
            
            storage_data = {
                'keys': keys_data,
                'active_key_id': self.active_key_id,
                'version': '1.0'
            }
            
            # 如果有主密码，加密存储
            if self.master_password:
                # 这里应该用主密码加密存储数据
                # 为了简化，暂时直接存储
                pass
            
            # 写入文件
            with open(self.key_storage_path, 'w') as f:
                json.dump(storage_data, f, indent=2)
            
            logger.debug(f"Keys saved to {self.key_storage_path}")
            
        except Exception as e:
            logger.error(f"Failed to save keys: {e}")
            raise KeyManagementError(f"Failed to save keys: {e}")
    
    def _load_keys(self):
        """从文件加载密钥"""
        try:
            with open(self.key_storage_path, 'r') as f:
                storage_data = json.load(f)
            
            # 解析密钥数据
            for key_id, key_data in storage_data['keys'].items():
                encryption_key = EncryptionKey(
                    key_id=key_id,
                    key_data=base64.b64decode(key_data['key_data']),
                    encryption_type=EncryptionType(key_data['encryption_type']),
                    created_at=datetime.fromisoformat(key_data['created_at']),
                    expires_at=datetime.fromisoformat(key_data['expires_at']) if key_data['expires_at'] else None,
                    usage_count=key_data['usage_count'],
                    max_usage=key_data['max_usage'],
                    metadata=key_data['metadata']
                )
                self.keys[key_id] = encryption_key
            
            # 设置活跃密钥
            self.active_key_id = storage_data.get('active_key_id')
            
            logger.debug(f"Loaded {len(self.keys)} keys from {self.key_storage_path}")
            
        except Exception as e:
            logger.error(f"Failed to load keys: {e}")
            raise KeyManagementError(f"Failed to load keys: {e}")
    
    def _secure_delete_bytes(self, data: bytes):
        """安全删除字节数据"""
        try:
            # 覆写内存
            import ctypes
            address = id(data)
            ctypes.memset(address, 0, len(data))
        except:
            # 如果无法直接操作内存，至少清除引用
            del data


# 工厂函数和便利类
def create_encryption_system(
    encryption_type: EncryptionType = EncryptionType.AES_256_GCM,
    security_level: SecurityLevel = SecurityLevel.HIGH,
    key_storage_path: Optional[str] = None,
    master_password: Optional[str] = None
) -> ConfigEncryption:
    """
    创建加密系统实例
    
    Args:
        encryption_type: 加密类型
        security_level: 安全级别
        key_storage_path: 密钥存储路径
        master_password: 主密码
        
    Returns:
        ConfigEncryption: 加密系统实例
    """
    config = EncryptionConfig(
        encryption_type=encryption_type,
        security_level=security_level
    )
    
    return ConfigEncryption(
        config=config,
        key_storage_path=key_storage_path,
        master_password=master_password
    )


class SimpleConfigEncryption:
    """
    简化的配置加密接口
    
    提供更简单的API用于常见的配置加密需求
    """
    
    def __init__(self, password: str = None):
        self.encryption = create_encryption_system(
            encryption_type=EncryptionType.AES_256_GCM,
            security_level=SecurityLevel.MEDIUM
        )
        self.password = password
    
    def encrypt_value(self, value: Any) -> str:
        """加密值"""
        return self.encryption.encrypt_config_value("value", value)
    
    def decrypt_value(self, encrypted_value: str) -> Any:
        """解密值"""
        _, value = self.encryption.decrypt_config_value(encrypted_value)
        return value
    
    def encrypt_dict(self, data: Dict[str, Any]) -> Dict[str, str]:
        """加密字典"""
        encrypted_dict = {}
        for key, value in data.items():
            encrypted_dict[key] = self.encrypt_value(value)
        return encrypted_dict
    
    def decrypt_dict(self, encrypted_dict: Dict[str, str]) -> Dict[str, Any]:
        """解密字典"""
        decrypted_dict = {}
        for key, encrypted_value in encrypted_dict.items():
            decrypted_dict[key] = self.decrypt_value(encrypted_value)
        return decrypted_dict