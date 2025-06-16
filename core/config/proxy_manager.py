"""
MarketPrism 代理配置管理器
支持不同服务的分离代理配置
"""

import os
import yaml
import logging
from typing import Dict, Optional, Any, Union
from pathlib import Path

logger = logging.getLogger(__name__)

class ProxyManager:
    """代理配置管理器"""
    
    def __init__(self, config_path: Optional[str] = None, environment: str = "development"):
        """
        初始化代理管理器
        
        Args:
            config_path: 代理配置文件路径
            environment: 环境名称 (development, testing, production)
        """
        self.environment = environment
        self.config_path = config_path or self._get_default_config_path()
        self.config = self._load_config()
        
    def _get_default_config_path(self) -> str:
        """获取默认配置文件路径"""
        # 尝试从项目根目录找到配置文件
        current_dir = Path(__file__).parent
        while current_dir.parent != current_dir:
            config_file = current_dir / "config" / "proxy.yaml"
            if config_file.exists():
                return str(config_file)
            current_dir = current_dir.parent
        
        # 如果找不到，使用相对路径
        return "config/proxy.yaml"
    
    def _load_config(self) -> Dict[str, Any]:
        """加载代理配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            logger.info(f"代理配置已加载: {self.config_path}")
            return config
        except FileNotFoundError:
            logger.warning(f"代理配置文件未找到: {self.config_path}，使用默认配置")
            return self._get_default_config()
        except Exception as e:
            logger.error(f"加载代理配置失败: {e}，使用默认配置")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "global": {"enabled": False},
            "services": {},
            "environments": {}
        }
    
    def get_service_proxy_config(self, service_name: str) -> Dict[str, Any]:
        """
        获取指定服务的代理配置
        
        Args:
            service_name: 服务名称 (如 'data-collector', 'api-gateway')
            
        Returns:
            服务的代理配置字典
        """
        # 优先使用环境特定配置
        env_config = self.config.get("environments", {}).get(self.environment, {})
        if service_name in env_config:
            config = env_config[service_name].copy()
            logger.debug(f"使用环境 {self.environment} 的 {service_name} 代理配置")
        else:
            # 回退到服务默认配置
            config = self.config.get("services", {}).get(service_name, {}).copy()
            logger.debug(f"使用默认的 {service_name} 代理配置")
        
        # 如果服务配置不存在或未启用，返回禁用配置
        if not config or not config.get("enabled", False):
            return {"enabled": False}
        
        return config
    
    def is_proxy_enabled(self, service_name: str) -> bool:
        """
        检查指定服务是否启用代理
        
        Args:
            service_name: 服务名称
            
        Returns:
            是否启用代理
        """
        config = self.get_service_proxy_config(service_name)
        return config.get("enabled", False)
    
    def get_http_proxy(self, service_name: str) -> Optional[str]:
        """
        获取HTTP代理地址
        
        Args:
            service_name: 服务名称
            
        Returns:
            HTTP代理地址或None
        """
        config = self.get_service_proxy_config(service_name)
        if not config.get("enabled", False):
            return None
        
        rest_api = config.get("rest_api", {})
        return rest_api.get("http_proxy")
    
    def get_https_proxy(self, service_name: str) -> Optional[str]:
        """
        获取HTTPS代理地址
        
        Args:
            service_name: 服务名称
            
        Returns:
            HTTPS代理地址或None
        """
        config = self.get_service_proxy_config(service_name)
        if not config.get("enabled", False):
            return None
        
        rest_api = config.get("rest_api", {})
        return rest_api.get("https_proxy")
    
    def get_socks_proxy(self, service_name: str) -> Optional[str]:
        """
        获取SOCKS代理地址
        
        Args:
            service_name: 服务名称
            
        Returns:
            SOCKS代理地址或None
        """
        config = self.get_service_proxy_config(service_name)
        if not config.get("enabled", False):
            return None
        
        websocket = config.get("websocket", {})
        return websocket.get("socks_proxy")
    
    def get_no_proxy(self, service_name: str) -> Optional[str]:
        """
        获取不使用代理的地址列表
        
        Args:
            service_name: 服务名称
            
        Returns:
            不使用代理的地址列表
        """
        config = self.get_service_proxy_config(service_name)
        return config.get("no_proxy")
    
    def get_proxy_dict(self, service_name: str) -> Dict[str, Optional[str]]:
        """
        获取代理配置字典，适用于requests等库
        
        Args:
            service_name: 服务名称
            
        Returns:
            代理配置字典
        """
        if not self.is_proxy_enabled(service_name):
            return {}
        
        proxy_dict = {}
        
        http_proxy = self.get_http_proxy(service_name)
        if http_proxy:
            proxy_dict["http"] = http_proxy
        
        https_proxy = self.get_https_proxy(service_name)
        if https_proxy:
            proxy_dict["https"] = https_proxy
        
        return proxy_dict
    
    def get_aiohttp_connector_kwargs(self, service_name: str) -> Dict[str, Any]:
        """
        获取aiohttp连接器的代理参数
        
        Args:
            service_name: 服务名称
            
        Returns:
            aiohttp连接器参数字典
        """
        if not self.is_proxy_enabled(service_name):
            return {}
        
        # aiohttp 3.x 不支持在ClientSession中直接设置proxy参数
        # 需要在请求时设置，这里返回空字典
        return {}
    
    def get_aiohttp_request_kwargs(self, service_name: str) -> Dict[str, Any]:
        """
        获取aiohttp请求的代理参数
        
        Args:
            service_name: 服务名称
            
        Returns:
            aiohttp请求参数字典
        """
        if not self.is_proxy_enabled(service_name):
            return {}
        
        kwargs = {}
        
        # HTTP代理配置
        http_proxy = self.get_http_proxy(service_name)
        if http_proxy:
            kwargs["proxy"] = http_proxy
        
        return kwargs
    
    def set_environment_variables(self, service_name: str) -> None:
        """
        设置环境变量代理配置
        
        Args:
            service_name: 服务名称
        """
        if not self.is_proxy_enabled(service_name):
            # 清除代理环境变量
            for var in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"]:
                if var in os.environ:
                    del os.environ[var]
            logger.debug(f"已清除 {service_name} 的代理环境变量")
            return
        
        http_proxy = self.get_http_proxy(service_name)
        if http_proxy:
            os.environ["http_proxy"] = http_proxy
            os.environ["HTTP_PROXY"] = http_proxy
        
        https_proxy = self.get_https_proxy(service_name)
        if https_proxy:
            os.environ["https_proxy"] = https_proxy
            os.environ["HTTPS_PROXY"] = https_proxy
        
        no_proxy = self.get_no_proxy(service_name)
        if no_proxy:
            os.environ["no_proxy"] = no_proxy
            os.environ["NO_PROXY"] = no_proxy
        
        logger.info(f"已设置 {service_name} 的代理环境变量")
    
    def clear_environment_variables(self) -> None:
        """清除所有代理环境变量"""
        proxy_vars = [
            "http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
            "no_proxy", "NO_PROXY", "all_proxy", "ALL_PROXY"
        ]
        
        for var in proxy_vars:
            if var in os.environ:
                del os.environ[var]
        
        logger.info("已清除所有代理环境变量")
    
    def validate_proxy_config(self, service_name: str) -> bool:
        """
        验证代理配置是否有效
        
        Args:
            service_name: 服务名称
            
        Returns:
            配置是否有效
        """
        config = self.get_service_proxy_config(service_name)
        
        if not config.get("enabled", False):
            return True  # 禁用状态认为是有效的
        
        # 检查是否至少配置了一种代理
        rest_api = config.get("rest_api", {})
        websocket = config.get("websocket", {})
        
        has_http = rest_api.get("http_proxy") or rest_api.get("https_proxy")
        has_socks = websocket.get("socks_proxy")
        
        if not (has_http or has_socks):
            logger.warning(f"{service_name} 启用了代理但未配置任何代理地址")
            return False
        
        return True
    
    def get_service_list(self) -> list:
        """获取所有配置的服务列表"""
        services = set()
        
        # 从服务配置中获取
        services.update(self.config.get("services", {}).keys())
        
        # 从环境配置中获取
        for env_config in self.config.get("environments", {}).values():
            services.update(env_config.keys())
        
        return sorted(list(services))
    
    def reload_config(self) -> None:
        """重新加载配置文件"""
        self.config = self._load_config()
        logger.info("代理配置已重新加载")


# 全局代理管理器实例
_proxy_manager = None

def get_proxy_manager(environment: str = None) -> ProxyManager:
    """
    获取全局代理管理器实例
    
    Args:
        environment: 环境名称，如果为None则使用环境变量或默认值
        
    Returns:
        代理管理器实例
    """
    global _proxy_manager
    
    if environment is None:
        environment = os.getenv("MARKETPRISM_ENV", "development")
    
    if _proxy_manager is None or _proxy_manager.environment != environment:
        _proxy_manager = ProxyManager(environment=environment)
    
    return _proxy_manager


def configure_service_proxy(service_name: str, environment: str = None) -> None:
    """
    为指定服务配置代理
    
    Args:
        service_name: 服务名称
        environment: 环境名称
    """
    proxy_manager = get_proxy_manager(environment)
    proxy_manager.set_environment_variables(service_name)


def clear_service_proxy() -> None:
    """清除服务代理配置"""
    proxy_manager = get_proxy_manager()
    proxy_manager.clear_environment_variables()


# 便捷函数
def is_proxy_enabled_for_service(service_name: str, environment: str = None) -> bool:
    """检查服务是否启用代理"""
    proxy_manager = get_proxy_manager(environment)
    return proxy_manager.is_proxy_enabled(service_name)


def get_service_proxy_dict(service_name: str, environment: str = None) -> Dict[str, Optional[str]]:
    """获取服务的代理配置字典"""
    proxy_manager = get_proxy_manager(environment)
    return proxy_manager.get_proxy_dict(service_name) 