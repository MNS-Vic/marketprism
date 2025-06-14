"""
配置迁移工具

帮助从旧配置格式迁移到新的统一配置格式
"""

from datetime import datetime, timezone
import shutil
from typing import Dict, Any, List, Optional, Union, Callable
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
import structlog

from .base_config import BaseConfig
from .unified_config_manager import UnifiedConfigManager


class MigrationStatus(Enum):
    """迁移状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class MigrationResult:
    """迁移结果"""
    config_name: str
    status: MigrationStatus
    old_file: Optional[Path] = None
    new_file: Optional[Path] = None
    backup_file: Optional[Path] = None
    errors: List[str] = None
    warnings: List[str] = None
    migration_time: datetime = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []
        if self.migration_time is None:
            self.migration_time = datetime.now(timezone.utc)


class ConfigMigrationRule:
    """配置迁移规则"""
    
    def __init__(self, 
                 name: str,
                 description: str,
                 transformer: Callable[[Dict[str, Any]], Dict[str, Any]]):
        self.name = name
        self.description = description
        self.transformer = transformer


class ConfigMigrationTool:
    """
    配置迁移工具
    
    帮助从旧配置格式迁移到新的统一配置格式
    """
    
    def __init__(self, config_manager: UnifiedConfigManager):
        """
        初始化配置迁移工具
        
        Args:
            config_manager: 统一配置管理器
        """
        self.config_manager = config_manager
        self.logger = structlog.get_logger(__name__)
        
        # 迁移规则
        self.migration_rules: Dict[str, List[ConfigMigrationRule]] = {}
        
        # 迁移历史
        self.migration_history: List[MigrationResult] = []
        
        # 备份设置
        self.backup_enabled = True
        self.backup_dir = self.config_manager.config_dir / "backups"
        
        # 注册内置迁移规则
        self._register_builtin_rules()
        
    def register_migration_rule(self, config_name: str, rule: ConfigMigrationRule):
        """
        注册迁移规则
        
        Args:
            config_name: 配置名称
            rule: 迁移规则
        """
        if config_name not in self.migration_rules:
            self.migration_rules[config_name] = []
            
        self.migration_rules[config_name].append(rule)
        
        self.logger.debug(
            "注册配置迁移规则",
            config_name=config_name,
            rule_name=rule.name
        )
        
    def migrate_config(self, 
                      config_name: str,
                      old_config_file: Union[str, Path],
                      backup: bool = True) -> MigrationResult:
        """
        迁移单个配置
        
        Args:
            config_name: 配置名称
            old_config_file: 旧配置文件路径
            backup: 是否备份原文件
            
        Returns:
            MigrationResult: 迁移结果
        """
        result = MigrationResult(config_name=config_name)
        result.old_file = Path(old_config_file)
        
        try:
            # 检查旧配置文件是否存在
            if not result.old_file.exists():
                result.status = MigrationStatus.FAILED
                result.errors.append(f"旧配置文件不存在: {result.old_file}")
                return result
                
            result.status = MigrationStatus.IN_PROGRESS
            
            # 读取旧配置
            old_config_data = self._load_old_config(result.old_file)
            
            # 应用迁移规则
            new_config_data = self._apply_migration_rules(config_name, old_config_data)
            
            # 验证新配置
            validation_errors = self._validate_migrated_config(config_name, new_config_data)
            if validation_errors:
                result.errors.extend(validation_errors)
                
            # 获取新配置文件路径
            new_config_file = self.config_manager._config_files.get(config_name)
            if not new_config_file:
                # 生成默认路径
                new_config_file = self.config_manager.config_dir / f"{config_name}.yaml"
                
            result.new_file = new_config_file
            
            # 创建备份
            if backup and self.backup_enabled:
                result.backup_file = self._create_backup(result.old_file)
                
            # 保存新配置
            self._save_new_config(new_config_file, new_config_data)
            
            # 加载新配置到管理器
            load_result = self.config_manager.load_config(config_name, config_data=new_config_data)
            if not load_result.success:
                result.errors.extend(load_result.errors)
                result.warnings.extend(load_result.warnings)
                
            if result.errors:
                result.status = MigrationStatus.FAILED
            else:
                result.status = MigrationStatus.COMPLETED
                
            self.migration_history.append(result)
            
            self.logger.info(
                "配置迁移完成",
                config_name=config_name,
                status=result.status.value,
                old_file=str(result.old_file),
                new_file=str(result.new_file),
                errors=len(result.errors),
                warnings=len(result.warnings)
            )
            
            return result
            
        except Exception as e:
            result.status = MigrationStatus.FAILED
            result.errors.append(f"迁移异常: {e}")
            self.logger.error("配置迁移失败", config_name=config_name, error=str(e))
            return result
            
    def migrate_all_configs(self, 
                           old_config_dir: Union[str, Path],
                           backup: bool = True) -> Dict[str, MigrationResult]:
        """
        迁移所有配置
        
        Args:
            old_config_dir: 旧配置目录
            backup: 是否备份原文件
            
        Returns:
            Dict[str, MigrationResult]: 配置名称到迁移结果的映射
        """
        old_config_dir = Path(old_config_dir)
        results = {}
        
        if not old_config_dir.exists():
            self.logger.error("旧配置目录不存在", path=str(old_config_dir))
            return results
            
        # 查找配置文件
        config_files = []
        for pattern in ['*.yaml', '*.yml', '*.json']:
            config_files.extend(old_config_dir.glob(pattern))
            
        # 迁移每个配置文件
        for config_file in config_files:
            config_name = config_file.stem
            
            # 检查是否有对应的配置类
            if config_name in self.config_manager.registry.list_configs():
                result = self.migrate_config(config_name, config_file, backup)
                results[config_name] = result
            else:
                self.logger.warning(
                    "跳过未注册的配置文件",
                    config_name=config_name,
                    file=str(config_file)
                )
                
        return results
        
    def rollback_migration(self, config_name: str) -> bool:
        """
        回滚配置迁移
        
        Args:
            config_name: 配置名称
            
        Returns:
            bool: 回滚是否成功
        """
        try:
            # 查找迁移历史
            migration_result = None
            for result in reversed(self.migration_history):
                if result.config_name == config_name and result.status == MigrationStatus.COMPLETED:
                    migration_result = result
                    break
                    
            if not migration_result or not migration_result.backup_file:
                self.logger.error("没有找到可回滚的迁移", config_name=config_name)
                return False
                
            # 恢复备份文件
            if migration_result.backup_file.exists():
                if migration_result.new_file and migration_result.new_file.exists():
                    migration_result.new_file.unlink()
                    
                shutil.copy2(migration_result.backup_file, migration_result.old_file)
                
                self.logger.info(
                    "配置迁移回滚成功",
                    config_name=config_name,
                    backup_file=str(migration_result.backup_file),
                    restored_file=str(migration_result.old_file)
                )
                return True
            else:
                self.logger.error("备份文件不存在", backup_file=str(migration_result.backup_file))
                return False
                
        except Exception as e:
            self.logger.error("配置迁移回滚失败", config_name=config_name, error=str(e))
            return False
            
    def get_migration_status(self, config_name: str) -> Optional[MigrationStatus]:
        """
        获取配置迁移状态
        
        Args:
            config_name: 配置名称
            
        Returns:
            Optional[MigrationStatus]: 迁移状态
        """
        for result in reversed(self.migration_history):
            if result.config_name == config_name:
                return result.status
                
        return None
        
    def get_migration_history(self, config_name: Optional[str] = None) -> List[MigrationResult]:
        """
        获取迁移历史
        
        Args:
            config_name: 配置名称，如果不提供则返回所有
            
        Returns:
            List[MigrationResult]: 迁移历史列表
        """
        if config_name:
            return [r for r in self.migration_history if r.config_name == config_name]
        else:
            return self.migration_history.copy()
            
    def cleanup_backups(self, older_than_days: int = 30) -> int:
        """
        清理旧备份文件
        
        Args:
            older_than_days: 保留天数
            
        Returns:
            int: 清理的文件数量
        """
        if not self.backup_dir.exists():
            return 0
            
        cleaned_count = 0
        cutoff_time = datetime.now(timezone.utc).timestamp() - (older_than_days * 24 * 3600)
        
        try:
            for backup_file in self.backup_dir.glob("*"):
                if backup_file.is_file() and backup_file.stat().st_mtime < cutoff_time:
                    backup_file.unlink()
                    cleaned_count += 1
                    
            self.logger.info(f"清理了 {cleaned_count} 个旧备份文件")
            return cleaned_count
            
        except Exception as e:
            self.logger.error("清理备份文件失败", error=str(e))
            return 0
            
    def _register_builtin_rules(self):
        """注册内置迁移规则"""
        # ExchangeConfig 迁移规则
        self.register_migration_rule(
            "exchange",
            ConfigMigrationRule(
                name="normalize_exchange_names",
                description="标准化交易所名称",
                transformer=self._normalize_exchange_names
            )
        )
        
        # NATS配置迁移规则
        self.register_migration_rule(
            "nats",
            ConfigMigrationRule(
                name="update_nats_structure",
                description="更新NATS配置结构",
                transformer=self._update_nats_structure
            )
        )
        
    def _load_old_config(self, config_file: Path) -> Dict[str, Any]:
        """加载旧配置文件"""
        if config_file.suffix.lower() in ['.yaml', '.yml']:
            import yaml
            with open(config_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        elif config_file.suffix.lower() == '.json':
            import json
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            raise ValueError(f"不支持的配置文件格式: {config_file.suffix}")
            
    def _apply_migration_rules(self, config_name: str, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """应用迁移规则"""
        rules = self.migration_rules.get(config_name, [])
        
        for rule in rules:
            try:
                config_data = rule.transformer(config_data)
                self.logger.debug(
                    "应用迁移规则",
                    config_name=config_name,
                    rule_name=rule.name
                )
            except Exception as e:
                self.logger.warning(
                    "迁移规则执行失败",
                    config_name=config_name,
                    rule_name=rule.name,
                    error=str(e)
                )
                
        return config_data
        
    def _validate_migrated_config(self, config_name: str, config_data: Dict[str, Any]) -> List[str]:
        """验证迁移后的配置"""
        errors = []
        
        try:
            config_class = self.config_manager.registry.get_config_class(config_name)
            if config_class:
                config = config_class.from_dict(config_data)
                if not config.validate():
                    errors.extend(config.validation_errors)
        except Exception as e:
            errors.append(f"配置验证异常: {e}")
            
        return errors
        
    def _create_backup(self, config_file: Path) -> Path:
        """创建备份文件"""
        if not self.backup_dir.exists():
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_name = f"{config_file.stem}_{timestamp}{config_file.suffix}"
        backup_file = self.backup_dir / backup_name
        
        shutil.copy2(config_file, backup_file)
        return backup_file
        
    def _save_new_config(self, config_file: Path, config_data: Dict[str, Any]):
        """保存新配置文件"""
        # 确保目录存在
        config_file.parent.mkdir(parents=True, exist_ok=True)
        
        if config_file.suffix.lower() in ['.yaml', '.yml']:
            import yaml
            with open(config_file, 'w', encoding='utf-8') as f:
                yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)
        elif config_file.suffix.lower() == '.json':
            import json
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
        else:
            raise ValueError(f"不支持的配置文件格式: {config_file.suffix}")
            
    def _normalize_exchange_names(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """标准化交易所名称"""
        # 将旧的交易所名称映射到新的标准名称
        exchange_mapping = {
            "binance": "binance",
            "okex": "okx",
            "okx": "okx"
        }
        
        if "exchange" in config_data and isinstance(config_data["exchange"], str):
            old_name = config_data["exchange"].lower()
            if old_name in exchange_mapping:
                config_data["exchange"] = exchange_mapping[old_name]
                
        return config_data
        
    def _update_nats_structure(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """更新NATS配置结构"""
        # 将旧的单一服务器配置转换为服务器列表
        if "server" in config_data and "servers" not in config_data:
            config_data["servers"] = [config_data.pop("server")]
            
        return config_data