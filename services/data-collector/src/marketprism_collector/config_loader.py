#!/usr/bin/env python3
"""
配置加载器

专用于OrderBook等特殊组件的配置加载
基于统一配置系统扩展
"""

from datetime import datetime, timezone
import os
import yaml
from typing import Dict, Any, Optional
from pathlib import Path
import structlog

from .config import config_path_manager

logger = structlog.get_logger(__name__)

class ConfigLoader:
    """配置加载器"""
    
    def __init__(self, config_dir: str = "config"):
        """
        初始化配置加载器 - 基于统一配置系统
        
        Args:
            config_dir: 配置文件目录 (可选, 优先使用全局配置管理器)
        """
        # 优先使用全局配置路径管理器
        self.config_dir = config_path_manager.config_root
        
        logger.info("配置加载器初始化 (基于统一配置系统)", config_dir=str(self.config_dir))
    
    def load_yaml(self, filename: str) -> Dict[str, Any]:
        """
        加载YAML配置文件
        
        Args:
            filename: 配置文件名
            
        Returns:
            配置字典
        """
        config_path = self.config_dir / filename
        
        if not config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            logger.info("配置文件加载成功", file=str(config_path))
            return config or {}
            
        except yaml.YAMLError as e:
            logger.error("YAML解析失败", file=str(config_path), exc_info=True)
            raise
        except Exception as e:
            logger.error("配置文件读取失败", file=str(config_path), exc_info=True)
            raise
    
    def load_realtime_orderbook_config(self) -> Dict[str, Any]:
        """加载实时订单簿写入器配置"""
        return self.load_yaml("realtime_orderbook_writer.yaml")
    
    def load_exchange_config(self, exchange_name: str) -> Dict[str, Any]:
        """
        加载交易所配置 - 使用统一配置路径管理器
        
        Args:
            exchange_name: 交易所名称
            
        Returns:
            交易所配置
        """
        # 使用统一配置路径管理器
        config_path = config_path_manager.get_exchange_config_path(exchange_name)
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            logger.info("交易所配置加载成功", exchange=exchange_name, file=str(config_path))
            return config or {}
            
        except FileNotFoundError:
            logger.error("交易所配置文件不存在", exchange=exchange_name, file=str(config_path))
            raise
        except yaml.YAMLError as e:
            logger.error("交易所配置YAML解析失败", exchange=exchange_name, file=str(config_path), exc_info=True)
            raise
        except Exception as e:
            logger.error("交易所配置加载失败", exchange=exchange_name, file=str(config_path), exc_info=True)
            raise
    
    def get_clickhouse_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        提取ClickHouse配置
        
        Args:
            config: 完整配置
            
        Returns:
            ClickHouse配置
        """
        clickhouse_config = config.get("clickhouse", {})
        
        # 环境变量覆盖
        env_overrides = {
            "host": os.getenv("CLICKHOUSE_HOST"),
            "port": os.getenv("CLICKHOUSE_PORT"),
            "database": os.getenv("CLICKHOUSE_DATABASE"),
            "user": os.getenv("CLICKHOUSE_USER"),
            "password": os.getenv("CLICKHOUSE_PASSWORD")
        }
        
        for key, value in env_overrides.items():
            if value is not None:
                if key == "port":
                    clickhouse_config[key] = int(value)
                else:
                    clickhouse_config[key] = value
        
        return clickhouse_config
    
    def get_exchange_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        提取交易所配置
        
        Args:
            config: 完整配置
            
        Returns:
            交易所配置
        """
        return config.get("exchange", {})
    
    def get_realtime_writer_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        提取实时写入器配置
        
        Args:
            config: 完整配置
            
        Returns:
            实时写入器配置
        """
        return config.get("realtime_writer", {})
    
    def get_monitoring_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        提取监控配置
        
        Args:
            config: 完整配置
            
        Returns:
            监控配置
        """
        return config.get("monitoring", {})
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        验证配置完整性
        
        Args:
            config: 配置字典
            
        Returns:
            是否有效
        """
        required_sections = ["clickhouse", "exchange", "realtime_writer"]
        
        for section in required_sections:
            if section not in config:
                logger.error("缺少必需的配置节", section=section)
                return False
        
        # 验证ClickHouse配置
        clickhouse_config = config["clickhouse"]
        required_clickhouse_fields = ["host", "port", "database"]
        
        for field in required_clickhouse_fields:
            if field not in clickhouse_config:
                logger.error("缺少ClickHouse配置字段", field=field)
                return False
        
        # 验证交易所配置
        exchange_config = config["exchange"]
        required_exchange_fields = ["name", "api"]
        
        for field in required_exchange_fields:
            if field not in exchange_config:
                logger.error("缺少交易所配置字段", field=field)
                return False
        
        # 验证实时写入器配置
        writer_config = config["realtime_writer"]
        if "symbols" not in writer_config or not writer_config["symbols"]:
            logger.error("实时写入器配置缺少交易对列表")
            return False
        
        logger.info("配置验证通过")
        return True

# 全局配置加载器实例
config_loader = ConfigLoader()

def load_realtime_orderbook_config() -> Dict[str, Any]:
    """加载实时订单簿写入器配置的便捷函数"""
    return config_loader.load_realtime_orderbook_config()

def get_clickhouse_config_from_file() -> Dict[str, Any]:
    """从配置文件获取ClickHouse配置的便捷函数"""
    config = load_realtime_orderbook_config()
    return config_loader.get_clickhouse_config(config)