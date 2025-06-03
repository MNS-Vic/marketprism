"""
统一代理配置管理器

解决各个交易所适配器中重复的代理配置逻辑
支持多种代理类型和配置源
"""

import os
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass
import structlog


@dataclass
class ProxyConfig:
    """代理配置数据类"""
    enabled: bool = False
    http_proxy: Optional[str] = None
    https_proxy: Optional[str] = None
    socks4_proxy: Optional[str] = None
    socks5_proxy: Optional[str] = None
    no_proxy: Optional[str] = None
    
    def get_http_proxy(self) -> Optional[str]:
        """获取HTTP代理URL"""
        return self.https_proxy or self.http_proxy
    
    def get_socks_proxy(self) -> Optional[str]:
        """获取SOCKS代理URL"""
        return self.socks5_proxy or self.socks4_proxy
    
    def has_proxy(self) -> bool:
        """检查是否配置了代理"""
        return self.enabled and (
            self.http_proxy or self.https_proxy or 
            self.socks4_proxy or self.socks5_proxy
        )
    
    def to_aiohttp_proxy(self) -> Optional[str]:
        """转换为aiohttp可用的代理URL"""
        if not self.has_proxy():
            return None
        return self.get_http_proxy() or self.get_socks_proxy()


class ProxyConfigManager:
    """统一的代理配置管理器"""
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
        self._cache = {}
    
    def get_proxy_config(self, 
                        exchange_config: Optional[Dict[str, Any]] = None,
                        service_config: Optional[Dict[str, Any]] = None) -> ProxyConfig:
        """
        获取代理配置，按优先级顺序：
        1. 交易所特定配置
        2. 服务级别配置  
        3. 环境变量
        4. 默认配置
        """
        config_key = self._generate_cache_key(exchange_config, service_config)
        
        if config_key in self._cache:
            return self._cache[config_key]
        
        # 1. 交易所特定配置优先
        if exchange_config and exchange_config.get('proxy'):
            proxy_config = self._parse_exchange_proxy_config(exchange_config['proxy'])
        
        # 2. 服务级别配置
        elif service_config and service_config.get('proxy'):
            proxy_config = self._parse_service_proxy_config(service_config['proxy'])
        
        # 3. 环境变量配置
        else:
            proxy_config = self._parse_env_proxy_config()
        
        # 缓存结果
        self._cache[config_key] = proxy_config
        
        if proxy_config.has_proxy():
            # 确定配置源
            if exchange_config and exchange_config.get('proxy'):
                source = "exchange"
            elif service_config and service_config.get('proxy'):
                source = "service"
            else:
                source = "environment"
                
            self.logger.info("代理配置已生效", 
                           http=proxy_config.get_http_proxy(),
                           socks=proxy_config.get_socks_proxy(),
                           source=source)
        
        return proxy_config
    
    def _parse_exchange_proxy_config(self, proxy_config: Dict[str, Any]) -> ProxyConfig:
        """解析交易所级别的代理配置"""
        return ProxyConfig(
            enabled=proxy_config.get('enabled', True),
            http_proxy=proxy_config.get('http_proxy') or proxy_config.get('http'),
            https_proxy=proxy_config.get('https_proxy') or proxy_config.get('https'),
            socks4_proxy=proxy_config.get('socks4_proxy') or proxy_config.get('socks4'),
            socks5_proxy=proxy_config.get('socks5_proxy') or proxy_config.get('socks5'),
            no_proxy=proxy_config.get('no_proxy')
        )
    
    def _parse_service_proxy_config(self, proxy_config: Dict[str, Any]) -> ProxyConfig:
        """解析服务级别的代理配置"""
        # 处理collector.yaml中的代理配置格式
        if 'rest_api' in proxy_config:
            rest_api = proxy_config['rest_api']
            return ProxyConfig(
                enabled=proxy_config.get('enabled', True),
                http_proxy=rest_api.get('http_proxy'),
                https_proxy=rest_api.get('https_proxy'),
                no_proxy=proxy_config.get('no_proxy')
            )
        
        # 处理统一格式
        return ProxyConfig(
            enabled=proxy_config.get('enabled', True),
            http_proxy=proxy_config.get('http_proxy'),
            https_proxy=proxy_config.get('https_proxy'),
            socks4_proxy=proxy_config.get('socks4_proxy'),
            socks5_proxy=proxy_config.get('socks5_proxy'),
            no_proxy=proxy_config.get('no_proxy')
        )
    
    def _parse_env_proxy_config(self) -> ProxyConfig:
        """解析环境变量代理配置"""
        return ProxyConfig(
            enabled=True,  # 环境变量存在即认为启用
            http_proxy=os.getenv('http_proxy') or os.getenv('HTTP_PROXY'),
            https_proxy=os.getenv('https_proxy') or os.getenv('HTTPS_PROXY'),
            socks4_proxy=os.getenv('socks4_proxy') or os.getenv('SOCKS4_PROXY'),
            socks5_proxy=os.getenv('socks5_proxy') or os.getenv('SOCKS5_PROXY'),
            no_proxy=os.getenv('no_proxy') or os.getenv('NO_PROXY')
        )
    
    def _generate_cache_key(self, 
                           exchange_config: Optional[Dict[str, Any]], 
                           service_config: Optional[Dict[str, Any]]) -> str:
        """生成缓存键"""
        parts = []
        
        if exchange_config and exchange_config.get('proxy'):
            parts.append(f"exchange:{hash(str(exchange_config['proxy']))}")
        
        if service_config and service_config.get('proxy'):
            parts.append(f"service:{hash(str(service_config['proxy']))}")
        
        if not parts:
            # 基于环境变量生成缓存键
            env_values = [
                os.getenv('http_proxy', ''),
                os.getenv('https_proxy', ''),
                os.getenv('socks5_proxy', '')
            ]
            parts.append(f"env:{hash('|'.join(env_values))}")
        
        return '|'.join(parts)
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        self.logger.debug("代理配置缓存已清空")
    
    def validate_proxy_url(self, proxy_url: str) -> bool:
        """验证代理URL格式"""
        if not proxy_url:
            return False
        
        try:
            from urllib.parse import urlparse
            parsed = urlparse(proxy_url)
            
            # 检查协议
            if parsed.scheme not in ['http', 'https', 'socks4', 'socks5']:
                return False
            
            # 检查主机和端口
            if not parsed.hostname:
                return False
            
            if parsed.port and (parsed.port < 1 or parsed.port > 65535):
                return False
            
            return True
            
        except Exception:
            return False
    
    def get_proxy_dict_for_requests(self, proxy_config: ProxyConfig) -> Dict[str, str]:
        """获取适用于requests库的代理字典"""
        if not proxy_config.has_proxy():
            return {}
        
        proxy_dict = {}
        
        if proxy_config.http_proxy:
            proxy_dict['http'] = proxy_config.http_proxy
        
        if proxy_config.https_proxy:
            proxy_dict['https'] = proxy_config.https_proxy
        elif proxy_config.http_proxy:
            proxy_dict['https'] = proxy_config.http_proxy
        
        return proxy_dict
    
    def get_proxy_for_aiohttp(self, proxy_config: ProxyConfig) -> Optional[str]:
        """获取适用于aiohttp的代理URL"""
        return proxy_config.to_aiohttp_proxy()
    
    def should_bypass_proxy(self, url: str, proxy_config: ProxyConfig) -> bool:
        """检查URL是否应该绕过代理"""
        if not proxy_config.no_proxy:
            return False
        
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            hostname = parsed.hostname
            
            if not hostname:
                return False
            
            no_proxy_list = [host.strip() for host in proxy_config.no_proxy.split(',')]
            
            for pattern in no_proxy_list:
                if pattern == hostname or hostname.endswith('.' + pattern):
                    return True
            
            return False
            
        except Exception:
            return False


# 全局代理配置管理器实例
proxy_manager = ProxyConfigManager()


def get_proxy_config(**kwargs) -> ProxyConfig:
    """便捷函数：获取代理配置"""
    return proxy_manager.get_proxy_config(**kwargs)