"""
MarketPrism统一配置加载器

提供标准化的服务配置加载方式
"""

from pathlib import Path
from typing import Dict, Any
import yaml

class ServiceConfigLoader:
    """统一服务配置加载器"""
    
    def __init__(self):
        self.config_root = Path(__file__).parent
        self.services_config_dir = self.config_root / "services"
    
    def load_service_config(self, service_name: str) -> Dict[str, Any]:
        """加载服务配置"""
        config_dir = self.services_config_dir / service_name
        
        # 查找主配置文件
        config_files = list(config_dir.glob("*.yaml"))
        if not config_files:
            raise FileNotFoundError(f"未找到服务 {service_name} 的配置文件")
        
        # 加载第一个配置文件
        config_file = config_files[0]
        with open(config_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def get_config_path(self, service_name: str) -> Path:
        """获取服务配置路径"""
        return self.services_config_dir / service_name
    
    def list_services(self) -> list:
        """列出所有可用的服务"""
        return [d.name for d in self.services_config_dir.iterdir() if d.is_dir()]

# 全局实例
config_loader = ServiceConfigLoader()
