#!/usr/bin/env python3
"""
MarketPrism 集中配置文件
提供统一的配置管理，包括环境变量、代理设置等
"""
import os
import json
import logging
from typing import Dict, List, Any, Optional

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 环境配置
ENV = os.environ.get("APP_ENV", "development")  # development, testing, production

# 基础目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 网络配置
class NetworkConfig:
    """网络相关配置"""
    # 代理配置
    USE_PROXY = os.environ.get("USE_PROXY", "false").lower() == "true"
    HTTP_PROXY = os.environ.get("HTTP_PROXY", "")
    HTTPS_PROXY = os.environ.get("HTTPS_PROXY", "")
    
    # 请求配置
    REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "30"))
    MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))
    RETRY_DELAY = int(os.environ.get("RETRY_DELAY", "5"))
    
    @classmethod
    def get_proxy_url(cls) -> Optional[str]:
        """获取代理URL"""
        if not cls.USE_PROXY:
            return None
        return cls.HTTP_PROXY or cls.HTTPS_PROXY or None
    
    @classmethod
    def get_proxy_dict(cls) -> Dict[str, str]:
        """获取代理字典，用于requests库"""
        if not cls.USE_PROXY or (not cls.HTTP_PROXY and not cls.HTTPS_PROXY):
            return {}
        
        proxy_dict = {}
        if cls.HTTP_PROXY:
            proxy_dict["http"] = cls.HTTP_PROXY
        if cls.HTTPS_PROXY:
            proxy_dict["https"] = cls.HTTPS_PROXY
        
        return proxy_dict
    
    @classmethod
    def update_from_env(cls):
        """从环境变量更新配置"""
        cls.USE_PROXY = os.environ.get("USE_PROXY", str(cls.USE_PROXY)).lower() == "true"
        cls.HTTP_PROXY = os.environ.get("HTTP_PROXY", cls.HTTP_PROXY)
        cls.HTTPS_PROXY = os.environ.get("HTTPS_PROXY", cls.HTTPS_PROXY)
        cls.REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", str(cls.REQUEST_TIMEOUT)))
        cls.MAX_RETRIES = int(os.environ.get("MAX_RETRIES", str(cls.MAX_RETRIES)))
        cls.RETRY_DELAY = int(os.environ.get("RETRY_DELAY", str(cls.RETRY_DELAY)))
    
    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "USE_PROXY": cls.USE_PROXY,
            "HTTP_PROXY": cls.HTTP_PROXY,
            "HTTPS_PROXY": cls.HTTPS_PROXY,
            "REQUEST_TIMEOUT": cls.REQUEST_TIMEOUT,
            "MAX_RETRIES": cls.MAX_RETRIES,
            "RETRY_DELAY": cls.RETRY_DELAY
        }
    
    @classmethod
    def to_env_dict(cls) -> Dict[str, str]:
        """转换为环境变量字典"""
        return {
            "USE_PROXY": str(cls.USE_PROXY).lower(),
            "HTTP_PROXY": cls.HTTP_PROXY,
            "HTTPS_PROXY": cls.HTTPS_PROXY,
            "REQUEST_TIMEOUT": str(cls.REQUEST_TIMEOUT),
            "MAX_RETRIES": str(cls.MAX_RETRIES),
            "RETRY_DELAY": str(cls.RETRY_DELAY)
        }

# 数据库配置
class DBConfig:
    """数据库相关配置"""
    # ClickHouse配置
    CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "localhost")
    CLICKHOUSE_PORT = os.environ.get("CLICKHOUSE_PORT", "8123")
    CLICKHOUSE_USER = os.environ.get("CLICKHOUSE_USER", "default")
    CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "")
    CLICKHOUSE_DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "marketprism")
    
    @classmethod
    def get_clickhouse_url(cls) -> str:
        """获取ClickHouse URL"""
        auth = ""
        if cls.CLICKHOUSE_USER:
            auth = f"{cls.CLICKHOUSE_USER}"
            if cls.CLICKHOUSE_PASSWORD:
                auth += f":{cls.CLICKHOUSE_PASSWORD}"
            auth += "@"
        
        return f"http://{auth}{cls.CLICKHOUSE_HOST}:{cls.CLICKHOUSE_PORT}/{cls.CLICKHOUSE_DATABASE}"
    
    @classmethod
    def update_from_env(cls):
        """从环境变量更新配置"""
        cls.CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", cls.CLICKHOUSE_HOST)
        cls.CLICKHOUSE_PORT = os.environ.get("CLICKHOUSE_PORT", cls.CLICKHOUSE_PORT)
        cls.CLICKHOUSE_USER = os.environ.get("CLICKHOUSE_USER", cls.CLICKHOUSE_USER)
        cls.CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", cls.CLICKHOUSE_PASSWORD)
        cls.CLICKHOUSE_DATABASE = os.environ.get("CLICKHOUSE_DATABASE", cls.CLICKHOUSE_DATABASE)
    
    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "CLICKHOUSE_HOST": cls.CLICKHOUSE_HOST,
            "CLICKHOUSE_PORT": cls.CLICKHOUSE_PORT,
            "CLICKHOUSE_USER": cls.CLICKHOUSE_USER,
            "CLICKHOUSE_PASSWORD": "***" if cls.CLICKHOUSE_PASSWORD else "",
            "CLICKHOUSE_DATABASE": cls.CLICKHOUSE_DATABASE
        }
    
    @classmethod
    def to_env_dict(cls) -> Dict[str, str]:
        """转换为环境变量字典"""
        return {
            "CLICKHOUSE_HOST": cls.CLICKHOUSE_HOST,
            "CLICKHOUSE_PORT": cls.CLICKHOUSE_PORT,
            "CLICKHOUSE_USER": cls.CLICKHOUSE_USER,
            "CLICKHOUSE_PASSWORD": cls.CLICKHOUSE_PASSWORD,
            "CLICKHOUSE_DATABASE": cls.CLICKHOUSE_DATABASE
        }

# 消息队列配置
class MQConfig:
    """消息队列相关配置"""
    # NATS配置
    NATS_URL = os.environ.get("NATS_URL", "nats://localhost:4222")
    
    @classmethod
    def update_from_env(cls):
        """从环境变量更新配置"""
        cls.NATS_URL = os.environ.get("NATS_URL", cls.NATS_URL)
    
    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "NATS_URL": cls.NATS_URL
        }
    
    @classmethod
    def to_env_dict(cls) -> Dict[str, str]:
        """转换为环境变量字典"""
        return {
            "NATS_URL": cls.NATS_URL
        }

# 交易所API配置
class ExchangeConfig:
    """交易所API相关配置"""
    # 币安API配置
    BINANCE_BASE_URL = os.environ.get("BINANCE_BASE_URL", "https://api1.binance.com")
    BINANCE_WS_URL = os.environ.get("BINANCE_WS_URL", "wss://stream.binance.com:9443/ws")
    BINANCE_API_KEY = os.environ.get("MP_BINANCE_API_KEY", "")
    BINANCE_API_SECRET = os.environ.get("MP_BINANCE_SECRET", "")
    
    # 交易对配置
    DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
    SYMBOLS = os.environ.get("SYMBOLS", ",".join(DEFAULT_SYMBOLS)).split(",")
    
    @classmethod
    def update_from_env(cls):
        """从环境变量更新配置"""
        cls.BINANCE_BASE_URL = os.environ.get("BINANCE_BASE_URL", cls.BINANCE_BASE_URL)
        cls.BINANCE_WS_URL = os.environ.get("BINANCE_WS_URL", cls.BINANCE_WS_URL)
        cls.BINANCE_API_KEY = os.environ.get("MP_BINANCE_API_KEY", cls.BINANCE_API_KEY)
        cls.BINANCE_API_SECRET = os.environ.get("MP_BINANCE_SECRET", cls.BINANCE_API_SECRET)
        
        symbols_str = os.environ.get("SYMBOLS", ",".join(cls.DEFAULT_SYMBOLS))
        cls.SYMBOLS = symbols_str.split(",") if symbols_str else cls.DEFAULT_SYMBOLS
    
    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "BINANCE_BASE_URL": cls.BINANCE_BASE_URL,
            "BINANCE_WS_URL": cls.BINANCE_WS_URL,
            "BINANCE_API_KEY": "***" if cls.BINANCE_API_KEY else "",
            "BINANCE_API_SECRET": "***" if cls.BINANCE_API_SECRET else "",
            "SYMBOLS": cls.SYMBOLS
        }
    
    @classmethod
    def to_env_dict(cls) -> Dict[str, str]:
        """转换为环境变量字典"""
        return {
            "BINANCE_BASE_URL": cls.BINANCE_BASE_URL,
            "BINANCE_WS_URL": cls.BINANCE_WS_URL,
            "MP_BINANCE_API_KEY": cls.BINANCE_API_KEY,
            "MP_BINANCE_SECRET": cls.BINANCE_API_SECRET,
            "SYMBOLS": ",".join(cls.SYMBOLS)
        }

class AppConfig:
    """应用配置类"""
    
    @staticmethod
    def update_all():
        """更新所有配置"""
        NetworkConfig.update_from_env()
        DBConfig.update_from_env()
        MQConfig.update_from_env()
        ExchangeConfig.update_from_env()
    
    @staticmethod
    def get_all_config() -> Dict[str, Any]:
        """获取所有配置"""
        return {
            "ENV": ENV,
            "NETWORK": NetworkConfig.to_dict(),
            "DATABASE": DBConfig.to_dict(),
            "QUEUE": MQConfig.to_dict(),
            "EXCHANGE": ExchangeConfig.to_dict()
        }
    
    @staticmethod
    def get_all_env() -> Dict[str, str]:
        """获取所有环境变量配置"""
        env_dict = {}
        env_dict.update(NetworkConfig.to_env_dict())
        env_dict.update(DBConfig.to_env_dict())
        env_dict.update(MQConfig.to_env_dict())
        env_dict.update(ExchangeConfig.to_env_dict())
        env_dict["APP_ENV"] = ENV
        
        return env_dict
    
    @staticmethod
    def print_config():
        """打印当前配置"""
        config = AppConfig.get_all_config()
        logger.info(f"当前应用配置: {json.dumps(config, indent=2, ensure_ascii=False)}")
    
    @staticmethod
    def set_proxy(use_proxy: bool, http_proxy: Optional[str] = None, https_proxy: Optional[str] = None):
        """设置代理"""
        NetworkConfig.USE_PROXY = use_proxy
        
        if http_proxy:
            NetworkConfig.HTTP_PROXY = http_proxy
        
        if https_proxy:
            NetworkConfig.HTTPS_PROXY = https_proxy
        
        # 更新环境变量
        os.environ["USE_PROXY"] = str(use_proxy).lower()
        
        if http_proxy:
            os.environ["HTTP_PROXY"] = http_proxy
        
        if https_proxy:
            os.environ["HTTPS_PROXY"] = https_proxy
        
        logger.info(f"代理设置已更新: USE_PROXY={use_proxy}, HTTP_PROXY={NetworkConfig.HTTP_PROXY}, HTTPS_PROXY={NetworkConfig.HTTPS_PROXY}")
    
    @staticmethod
    def detect_system_proxy():
        """检测系统代理"""
        http_proxy = os.environ.get("HTTP_PROXY", os.environ.get("http_proxy", ""))
        https_proxy = os.environ.get("HTTPS_PROXY", os.environ.get("https_proxy", ""))
        
        if http_proxy or https_proxy:
            NetworkConfig.HTTP_PROXY = http_proxy
            NetworkConfig.HTTPS_PROXY = https_proxy
            return True
        
        return False
    
    @staticmethod
    def setup_test_proxy():
        """设置测试代理"""
        # 常用测试代理地址
        test_proxies = [
            "http://127.0.0.1:1087",
            "http://127.0.0.1:1080",
            "http://127.0.0.1:7890",
            "http://127.0.0.1:8080",
            "http://127.0.0.1:8888"
        ]
        
        import aiohttp
        import asyncio
        
        async def test_proxy(proxy):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get("https://api.binance.com/api/v3/time", 
                                           proxy=proxy, 
                                           timeout=5) as resp:
                        if resp.status == 200:
                            return proxy
            except:
                pass
            return None
        
        async def find_working_proxy():
            tasks = [test_proxy(proxy) for proxy in test_proxies]
            results = await asyncio.gather(*tasks)
            return next((proxy for proxy in results if proxy), None)
        
        try:
            proxy = asyncio.run(find_working_proxy())
            if proxy:
                logger.info(f"找到可用代理: {proxy}")
                AppConfig.set_proxy(True, proxy, proxy)
                return True
            else:
                logger.warning("未找到可用代理")
                return False
        except Exception as e:
            logger.error(f"测试代理出错: {str(e)}")
            return False

# 初始化配置
AppConfig.update_all()

# 导出配置
__all__ = [
    "AppConfig", 
    "NetworkConfig", 
    "DBConfig", 
    "MQConfig", 
    "ExchangeConfig",
    "ENV"
] 