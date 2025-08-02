"""
配置管理模块

负责加载和管理所有配置文件，支持环境变量覆盖和配置验证
"""

from datetime import datetime, timezone
import os
import yaml
from typing import Dict, List, Optional, Any
from pathlib import Path
from pydantic import BaseModel, Field, field_validator, ConfigDict
from dotenv import load_dotenv

from .data_types import ExchangeConfig, DataType


class ConfigPathManager:
    """配置路径管理器 - 整合自config_paths.py"""
    
    # 标准配置路径映射
    CONFIG_PATHS = {
        'exchanges': 'exchanges',
        'monitoring': 'monitoring',
        'infrastructure': 'infrastructure',
        'environments': 'environments',
        'collector': 'collector',
        'test': 'test'
    }
    
    def __init__(self, config_root: Optional[Path] = None):
        if config_root is None:
            # 优先使用服务本地配置目录
            current_file = Path(__file__)
            service_root = current_file.parent.parent  # services/data-collector/
            local_config_root = service_root / "config"

            if local_config_root.exists():
                config_root = local_config_root
            else:
                # 回退到项目根目录的config文件夹（向后兼容）
                project_root = current_file.parent.parent.parent.parent.parent
                config_root = project_root / "config"

        self.config_root = Path(config_root)
    
    def get_config_path(self, category: str, filename: str) -> Path:
        """获取配置文件完整路径"""
        if category not in self.CONFIG_PATHS:
            raise ValueError(f"未知配置类别: {category}")
        
        category_path = self.CONFIG_PATHS[category]
        return self.config_root / category_path / filename
    
    def get_exchange_config_path(self, exchange_name: str) -> Path:
        """获取交易所配置文件路径"""
        return self.get_config_path('exchanges', f"{exchange_name}.yml")
    
    def get_collector_config_path(self, config_name: str) -> Path:
        """获取收集器配置文件路径"""
        return self.get_config_path('collector', f"{config_name}.yml")
    
    def list_config_files(self, category: str) -> list:
        """列出指定类别的所有配置文件"""
        category_dir = self.config_root / self.CONFIG_PATHS[category]
        if not category_dir.exists():
            return []
        
        return [f.name for f in category_dir.glob("*.yml")]


class NATSConfig(BaseModel):
    """NATS配置 - 🔧 配置统一：从统一配置文件读取"""
    url: str = Field("nats://localhost:4222", description="NATS服务器URL（默认值，应从统一配置读取）")
    client_name: str = Field("marketprism-collector", description="客户端名称")
    
    # 流配置
    streams: Dict[str, Dict[str, Any]] = Field(
        default_factory=lambda: {
            "MARKET_DATA": {
                "name": "MARKET_DATA",
                "subjects": ["market.>"],
                "retention": "limits",
                "max_msgs": 1000000,
                "max_bytes": 1073741824,  # 1GB
                "max_age": 86400,  # 24 hours
                "max_consumers": 10,
                "replicas": 1
            }
        },
        description="流配置"
    )

    model_config = ConfigDict(
        # Add any custom configuration here if needed
    )

    def model_dump(self, **kwargs):
        """Pydantic V2 兼容方法"""
        # 使用BaseModel的原生方法，避免递归
        return super().model_dump(**kwargs)

    def model_dump_json(self, **kwargs):
        """Pydantic V2 兼容方法"""
        # 使用BaseModel的原生方法，避免递归
        return super().model_dump_json(**kwargs)


class ProxyConfig(BaseModel):
    """代理配置"""
    enabled: bool = Field(False, description="是否启用代理")
    http_proxy: Optional[str] = Field(None, description="HTTP代理地址")
    https_proxy: Optional[str] = Field(None, description="HTTPS代理地址")
    no_proxy: Optional[str] = Field(None, description="不使用代理的地址")

    model_config = ConfigDict(
        # Add any custom configuration here if needed
    )

    def model_dump(self, **kwargs):
        """Pydantic V2 兼容方法"""
        # 使用BaseModel的原生方法，避免递归
        return super().model_dump(**kwargs)

    def model_dump_json(self, **kwargs):
        """Pydantic V2 兼容方法"""
        # 使用BaseModel的原生方法，避免递归
        return super().model_dump_json(**kwargs)


class CollectorConfig(BaseModel):
    """收集器配置"""
    use_real_exchanges: bool = Field(True, description="是否使用真实交易所")
    log_level: str = Field("INFO", description="日志级别")
    http_port: int = Field(8080, description="HTTP服务端口")
    metrics_port: int = Field(9090, description="指标服务端口")
    max_reconnect_attempts: int = Field(5, description="最大重连尝试次数")
    reconnect_delay: int = Field(5, description="重连延迟(秒)")
    
    # OrderBook Manager配置
    enable_orderbook_manager: bool = Field(False, description="是否启用OrderBook Manager")
    enable_scheduler: bool = Field(True, description="是否启用任务调度器")

    # TDD测试配置 - 用于控制组件启用/禁用
    enable_nats: bool = Field(True, description="是否启用NATS连接")
    enable_http_server: bool = Field(True, description="是否启用HTTP服务器")
    enable_top_trader_collector: bool = Field(True, description="是否启用大户持仓收集器")

    # 性能配置
    max_concurrent_connections: int = Field(10, description="最大并发连接数")
    message_buffer_size: int = Field(1000, description="消息缓冲区大小")
    
    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v):
        allowed_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in allowed_levels:
            raise ValueError(f'日志级别必须是以下之一: {allowed_levels}')
        return v.upper()

    model_config = ConfigDict(
        # Add any custom configuration here if needed
    )

    def model_dump(self, **kwargs):
        """Pydantic V2 兼容方法"""
        # 使用BaseModel的原生方法，避免递归
        return super().model_dump(**kwargs)

    def model_dump_json(self, **kwargs):
        """Pydantic V2 兼容方法"""
        # 使用BaseModel的原生方法，避免递归
        return super().model_dump_json(**kwargs)


class Config(BaseModel):
    """主配置类"""
    collector: CollectorConfig = Field(default_factory=CollectorConfig, description="收集器配置")
    nats: NATSConfig = Field(default_factory=NATSConfig, description="NATS配置")
    proxy: ProxyConfig = Field(default_factory=ProxyConfig, description="代理配置")
    exchanges: List[ExchangeConfig] = Field(default_factory=list, description="交易所配置")
    
    # 环境配置
    environment: str = Field("development", description="运行环境")
    debug: bool = Field(False, description="调试模式")
    is_testnet: bool = Field(False, description="是否使用测试网")  # 添加缺失的is_testnet属性

    model_config = ConfigDict(
        # Add any custom configuration here if needed
    )

    def model_dump(self, **kwargs):
        """Pydantic V2 兼容方法"""
        # 使用BaseModel的原生方法，避免递归
        return super().model_dump(**kwargs)

    def model_dump_json(self, **kwargs):
        """Pydantic V2 兼容方法"""
        # 使用BaseModel的原生方法，避免递归
        return super().model_dump_json(**kwargs)
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "Config":
        """从字典创建配置对象"""
        # 处理exchanges字段
        if 'exchanges' in config_dict:
            exchanges_data = config_dict['exchanges']
            # 如果exchanges是字典形式，转换为列表
            if isinstance(exchanges_data, dict):
                exchanges_list = []
                for name, config in exchanges_data.items():
                    exchange_config = dict(config)
                    exchange_config['name'] = name
                    # 确保设置exchange字段
                    if 'exchange' not in exchange_config:
                        from .data_types import Exchange
                        try:
                            exchange_config['exchange'] = Exchange(name.lower())
                        except ValueError:
                            # 如果exchange名称不在枚举中，使用第一个作为默认值
                            exchange_config['exchange'] = Exchange.BINANCE
                    exchanges_list.append(ExchangeConfig(**exchange_config))
                config_dict['exchanges'] = exchanges_list
            # 如果exchanges已经是列表，直接处理
            elif isinstance(exchanges_data, list):
                processed_exchanges = []
                for ex in exchanges_data:
                    if isinstance(ex, dict):
                        exchange_config = dict(ex)
                        # 确保设置exchange字段
                        if 'exchange' not in exchange_config:
                            from .data_types import Exchange
                            name = exchange_config.get('name', 'binance')
                            try:
                                exchange_config['exchange'] = Exchange(name.lower())
                            except ValueError:
                                exchange_config['exchange'] = Exchange.BINANCE
                        processed_exchanges.append(ExchangeConfig(**exchange_config))
                    else:
                        processed_exchanges.append(ex)
                config_dict['exchanges'] = processed_exchanges
        
        return cls(**config_dict)
    
    @classmethod
    def load_from_file(cls, config_path: str) -> "Config":
        """从配置文件加载配置"""
        config_file = Path(config_path)
        
        if not config_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        
        # 加载环境变量
        env_file = config_file.parent / ".env"
        if env_file.exists():
            load_dotenv(env_file)
        
        # 读取主配置文件
        with open(config_file, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        
        # 加载交易所配置
        exchanges = []
        if 'exchanges' in config_data and 'configs' in config_data['exchanges']:
            for exchange_config_file in config_data['exchanges']['configs']:
                exchange_config_path = cls._resolve_config_path(
                    exchange_config_file, config_file.parent
                )
                exchange_config = cls._load_exchange_config(exchange_config_path)
                if exchange_config:
                    exchanges.append(exchange_config)
        
        # 创建配置对象
        config_data['exchanges'] = exchanges
        
        # 应用环境变量覆盖
        config_data = cls._apply_env_overrides(config_data)
        
        return cls(**config_data)
    
    @classmethod
    def get_path_manager(cls) -> ConfigPathManager:
        """获取配置路径管理器"""
        return ConfigPathManager()
    
    @staticmethod
    def _resolve_config_path(config_path: str, base_dir: Path) -> Path:
        """解析配置文件路径"""
        if os.path.isabs(config_path):
            return Path(config_path)
        else:
            # 交易所配置文件相对于项目根目录的config文件夹
            # 从当前文件位置找到项目根目录
            current_file = Path(__file__)
            project_root = current_file.parent.parent.parent.parent.parent
            config_root = project_root / "config"
            return config_root / config_path
    
    @staticmethod
    def _load_exchange_config(config_path: Path) -> Optional[ExchangeConfig]:
        """加载交易所配置"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                exchange_data = yaml.safe_load(f)
            
            # 从环境变量设置API密钥
            exchange_name = exchange_data.get('exchange', '').upper()
            market_type = exchange_data.get('market_type', '').upper()
            prefix = f"{exchange_name}_{market_type}"
            
            # API密钥环境变量
            api_key_env = f"{prefix}_API_KEY"
            api_secret_env = f"{prefix}_API_SECRET"
            passphrase_env = f"{prefix}_PASSPHRASE"
            
            if os.getenv(api_key_env):
                exchange_data['api_key'] = os.getenv(api_key_env)
            if os.getenv(api_secret_env):
                exchange_data['api_secret'] = os.getenv(api_secret_env)
            if os.getenv(passphrase_env):
                exchange_data['passphrase'] = os.getenv(passphrase_env)
            
            return ExchangeConfig(**exchange_data)
            
        except Exception as e:
            print(f"加载交易所配置失败 {config_path}: {e}")
            return None
    
    @staticmethod
    def _apply_env_overrides(config_data: Dict[str, Any]) -> Dict[str, Any]:
        """应用环境变量覆盖"""
        # NATS配置覆盖
        if os.getenv('NATS_URL'):
            if 'nats' not in config_data:
                config_data['nats'] = {}
            config_data['nats']['url'] = os.getenv('NATS_URL')
        
        # 收集器配置覆盖
        if os.getenv('LOG_LEVEL'):
            if 'collector' not in config_data:
                config_data['collector'] = {}
            config_data['collector']['log_level'] = os.getenv('LOG_LEVEL')
        
        if os.getenv('HTTP_PORT'):
            if 'collector' not in config_data:
                config_data['collector'] = {}
            config_data['collector']['http_port'] = int(os.getenv('HTTP_PORT'))
        
        # 代理配置覆盖
        if os.getenv('HTTP_PROXY') or os.getenv('HTTPS_PROXY'):
            if 'proxy' not in config_data:
                config_data['proxy'] = {}
            config_data['proxy']['enabled'] = True
            if os.getenv('HTTP_PROXY'):
                config_data['proxy']['http_proxy'] = os.getenv('HTTP_PROXY')
            if os.getenv('HTTPS_PROXY'):
                config_data['proxy']['https_proxy'] = os.getenv('HTTPS_PROXY')
            if os.getenv('NO_PROXY'):
                config_data['proxy']['no_proxy'] = os.getenv('NO_PROXY')
        
        # 环境配置
        if os.getenv('ENVIRONMENT'):
            config_data['environment'] = os.getenv('ENVIRONMENT')
        
        if os.getenv('DEBUG'):
            config_data['debug'] = os.getenv('DEBUG').lower() in ['true', '1', 'yes']
        
        return config_data
    
    def get_enabled_exchanges(self) -> List[ExchangeConfig]:
        """获取启用的交易所配置"""
        return [ex for ex in self.exchanges if ex.enabled]
    
    def get_exchange_by_name(self, exchange_name: str) -> Optional[ExchangeConfig]:
        """通过名称获取交易所配置"""
        for exchange in self.exchanges:
            if exchange.exchange.value == exchange_name.lower():
                return exchange
        return None
    
    def setup_proxy_env(self):
        """设置代理环境变量"""
        if self.proxy.enabled:
            if self.proxy.http_proxy:
                os.environ['HTTP_PROXY'] = self.proxy.http_proxy
            if self.proxy.https_proxy:
                os.environ['HTTPS_PROXY'] = self.proxy.https_proxy
            if self.proxy.no_proxy:
                os.environ['NO_PROXY'] = self.proxy.no_proxy


# 全局配置路径管理器实例
config_path_manager = ConfigPathManager()


def create_default_config() -> Config:
    """创建默认配置"""
    return Config(
        collector=CollectorConfig(),
        nats=NATSConfig(),
        proxy=ProxyConfig(),
        exchanges=[
            # 默认Binance现货配置
            ExchangeConfig(
                exchange="binance",
                market_type="spot",
                enabled=True,
                base_url="https://api.binance.com",
                ws_url="wss://stream.binance.com:9443/ws",
                data_types=[DataType.TRADE, DataType.ORDERBOOK, DataType.TICKER],
                symbols=["BTCUSDT", "ETHUSDT", "ADAUSDT"]
            )
        ]
    ) 