#!/usr/bin/env python3
"""
MarketPrism监控告警服务SSL/TLS配置模块
提供HTTPS加密和证书管理功能
"""

import ssl
import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import datetime

logger = logging.getLogger(__name__)

class SSLConfig:
    """SSL配置类"""
    
    def __init__(self):
        # SSL配置路径
        self.ssl_enabled = os.getenv('SSL_ENABLED', 'true').lower() == 'true'
        self.cert_dir = Path(os.getenv('SSL_CERT_DIR', 'certs'))
        self.cert_file = self.cert_dir / os.getenv('SSL_CERT_FILE', 'server.crt')
        self.key_file = self.cert_dir / os.getenv('SSL_KEY_FILE', 'server.key')
        self.ca_file = self.cert_dir / os.getenv('SSL_CA_FILE', 'ca.crt')
        
        # SSL安全配置
        self.ssl_protocols = os.getenv('SSL_PROTOCOLS', 'TLSv1.2,TLSv1.3').split(',')
        self.ssl_ciphers = os.getenv('SSL_CIPHERS', 'ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')
        self.require_client_cert = os.getenv('SSL_REQUIRE_CLIENT_CERT', 'false').lower() == 'true'
        
        # 自动生成证书配置
        self.auto_generate_cert = os.getenv('SSL_AUTO_GENERATE', 'true').lower() == 'true'
        self.cert_validity_days = int(os.getenv('SSL_CERT_VALIDITY_DAYS', '365'))
        self.cert_subject = {
            'country': os.getenv('SSL_CERT_COUNTRY', 'CN'),
            'state': os.getenv('SSL_CERT_STATE', 'Beijing'),
            'city': os.getenv('SSL_CERT_CITY', 'Beijing'),
            'organization': os.getenv('SSL_CERT_ORG', 'MarketPrism'),
            'unit': os.getenv('SSL_CERT_UNIT', 'Monitoring'),
            'common_name': os.getenv('SSL_CERT_CN', 'localhost')
        }

class CertificateManager:
    """证书管理器"""
    
    def __init__(self, config: SSLConfig):
        self.config = config
        
    def ensure_certificates_exist(self) -> bool:
        """确保证书文件存在"""
        try:
            # 创建证书目录
            self.config.cert_dir.mkdir(parents=True, exist_ok=True)
            
            # 检查证书是否存在且有效
            if self._certificates_valid():
                logger.info("SSL证书已存在且有效")
                return True
            
            # 自动生成证书
            if self.config.auto_generate_cert:
                logger.info("自动生成SSL证书...")
                return self._generate_self_signed_certificate()
            else:
                logger.error("SSL证书不存在且未启用自动生成")
                return False
                
        except Exception as e:
            logger.error(f"证书检查失败: {e}")
            return False
    
    def _certificates_valid(self) -> bool:
        """检查证书是否有效"""
        try:
            if not (self.config.cert_file.exists() and self.config.key_file.exists()):
                return False
            
            # 检查证书是否过期
            with open(self.config.cert_file, 'rb') as f:
                cert = x509.load_pem_x509_certificate(f.read())
                
            now = datetime.datetime.utcnow()
            if now < cert.not_valid_before or now > cert.not_valid_after:
                logger.warning("SSL证书已过期或尚未生效")
                return False
            
            # 检查证书是否即将过期（30天内）
            days_until_expiry = (cert.not_valid_after - now).days
            if days_until_expiry < 30:
                logger.warning(f"SSL证书将在{days_until_expiry}天后过期")
            
            return True
            
        except Exception as e:
            logger.error(f"证书验证失败: {e}")
            return False
    
    def _generate_self_signed_certificate(self) -> bool:
        """生成自签名证书"""
        try:
            # 生成私钥
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
            )
            
            # 创建证书主题
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, self.config.cert_subject['country']),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, self.config.cert_subject['state']),
                x509.NameAttribute(NameOID.LOCALITY_NAME, self.config.cert_subject['city']),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, self.config.cert_subject['organization']),
                x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, self.config.cert_subject['unit']),
                x509.NameAttribute(NameOID.COMMON_NAME, self.config.cert_subject['common_name']),
            ])
            
            # 创建证书
            cert = x509.CertificateBuilder().subject_name(
                subject
            ).issuer_name(
                issuer
            ).public_key(
                private_key.public_key()
            ).serial_number(
                x509.random_serial_number()
            ).not_valid_before(
                datetime.datetime.utcnow()
            ).not_valid_after(
                datetime.datetime.utcnow() + datetime.timedelta(days=self.config.cert_validity_days)
            ).add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName("localhost"),
                    x509.DNSName("127.0.0.1"),
                    x509.DNSName("monitoring.marketprism.local"),
                ]),
                critical=False,
            ).add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            ).add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_encipherment=True,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    content_commitment=False,
                    data_encipherment=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            ).sign(private_key, hashes.SHA256())
            
            # 保存私钥
            with open(self.config.key_file, 'wb') as f:
                f.write(private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                ))
            
            # 保存证书
            with open(self.config.cert_file, 'wb') as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))
            
            # 设置文件权限
            os.chmod(self.config.key_file, 0o600)
            os.chmod(self.config.cert_file, 0o644)
            
            logger.info(f"成功生成自签名证书: {self.config.cert_file}")
            return True
            
        except Exception as e:
            logger.error(f"生成自签名证书失败: {e}")
            return False
    
    def get_certificate_info(self) -> Optional[Dict[str, Any]]:
        """获取证书信息"""
        try:
            if not self.config.cert_file.exists():
                return None
            
            with open(self.config.cert_file, 'rb') as f:
                cert = x509.load_pem_x509_certificate(f.read())
            
            subject = cert.subject
            issuer = cert.issuer
            
            return {
                'subject': {
                    'common_name': subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value,
                    'organization': subject.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)[0].value,
                    'country': subject.get_attributes_for_oid(NameOID.COUNTRY_NAME)[0].value,
                },
                'issuer': {
                    'common_name': issuer.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value,
                    'organization': issuer.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)[0].value,
                },
                'valid_from': cert.not_valid_before.isoformat(),
                'valid_until': cert.not_valid_after.isoformat(),
                'serial_number': str(cert.serial_number),
                'signature_algorithm': cert.signature_algorithm_oid._name,
                'is_self_signed': cert.issuer == cert.subject
            }
            
        except Exception as e:
            logger.error(f"获取证书信息失败: {e}")
            return None

def create_ssl_context(config: SSLConfig) -> Optional[ssl.SSLContext]:
    """创建SSL上下文"""
    try:
        if not config.ssl_enabled:
            logger.info("SSL未启用")
            return None
        
        # 确保证书存在
        cert_manager = CertificateManager(config)
        if not cert_manager.ensure_certificates_exist():
            logger.error("无法获取有效的SSL证书")
            return None
        
        # 创建SSL上下文
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        
        # 加载证书和私钥
        ssl_context.load_cert_chain(
            certfile=str(config.cert_file),
            keyfile=str(config.key_file)
        )
        
        # 配置SSL协议
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        ssl_context.maximum_version = ssl.TLSVersion.TLSv1_3
        
        # 配置加密套件
        if config.ssl_ciphers:
            ssl_context.set_ciphers(config.ssl_ciphers)
        
        # 客户端证书验证
        if config.require_client_cert:
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            if config.ca_file.exists():
                ssl_context.load_verify_locations(str(config.ca_file))
        else:
            ssl_context.verify_mode = ssl.CERT_NONE
        
        # 安全选项
        ssl_context.options |= ssl.OP_NO_SSLv2
        ssl_context.options |= ssl.OP_NO_SSLv3
        ssl_context.options |= ssl.OP_NO_COMPRESSION
        ssl_context.options |= ssl.OP_SINGLE_DH_USE
        ssl_context.options |= ssl.OP_SINGLE_ECDH_USE
        
        logger.info("SSL上下文创建成功")
        return ssl_context
        
    except Exception as e:
        logger.error(f"创建SSL上下文失败: {e}")
        return None

def get_ssl_info() -> Dict[str, Any]:
    """获取SSL配置信息"""
    config = SSLConfig()
    cert_manager = CertificateManager(config)
    
    info = {
        'ssl_enabled': config.ssl_enabled,
        'cert_file': str(config.cert_file),
        'key_file': str(config.key_file),
        'auto_generate': config.auto_generate_cert,
        'require_client_cert': config.require_client_cert,
        'certificate_info': cert_manager.get_certificate_info()
    }
    
    return info

# 导出主要组件
__all__ = [
    'SSLConfig',
    'CertificateManager', 
    'create_ssl_context',
    'get_ssl_info'
]
