"""
配置版本管理器
"""

import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional


class VersionManager:
    """配置版本管理器"""
    
    def __init__(self, versions_dir: str = "config/versions"):
        self.versions_dir = Path(versions_dir)
        self.versions_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
        
        # 版本历史文件
        self.history_file = self.versions_dir / "version_history.json"
        self.current_version_file = self.versions_dir / "current_version.json"
        
        # 初始化版本历史
        self._init_version_history()
    
    def _init_version_history(self):
        """初始化版本历史"""
        if not self.history_file.exists():
            initial_history = {
                "versions": [],
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat()
            }
            self._save_json(self.history_file, initial_history)
    
    def create_version(self, config_data: Dict[str, Any], 
                      description: str = "", 
                      tags: List[str] = None) -> str:
        """创建新的配置版本"""
        try:
            version_id = self._generate_version_id()
            timestamp = datetime.now().isoformat()
            
            version_info = {
                "version_id": version_id,
                "timestamp": timestamp,
                "description": description,
                "tags": tags or [],
                "config_checksum": self._calculate_checksum(config_data),
                "size": len(json.dumps(config_data))
            }
            
            # 保存配置数据
            version_file = self.versions_dir / f"{version_id}.json"
            self._save_json(version_file, {
                "version_info": version_info,
                "config_data": config_data
            })
            
            # 更新版本历史
            self._update_version_history(version_info)
            
            # 更新当前版本
            self._update_current_version(version_id)
            
            self.logger.info(f"创建配置版本: {version_id}")
            return version_id
            
        except Exception as e:
            self.logger.error(f"创建配置版本失败: {e}")
            raise
    
    def get_version(self, version_id: str) -> Optional[Dict[str, Any]]:
        """获取指定版本的配置"""
        try:
            version_file = self.versions_dir / f"{version_id}.json"
            if not version_file.exists():
                return None
            
            version_data = self._load_json(version_file)
            return version_data.get("config_data")
            
        except Exception as e:
            self.logger.error(f"获取配置版本失败 {version_id}: {e}")
            return None
    
    def get_version_info(self, version_id: str) -> Optional[Dict[str, Any]]:
        """获取版本信息"""
        try:
            version_file = self.versions_dir / f"{version_id}.json"
            if not version_file.exists():
                return None
            
            version_data = self._load_json(version_file)
            return version_data.get("version_info")
            
        except Exception as e:
            self.logger.error(f"获取版本信息失败 {version_id}: {e}")
            return None
    
    def list_versions(self, limit: int = 50, tags: List[str] = None) -> List[Dict[str, Any]]:
        """列出版本历史"""
        try:
            history = self._load_json(self.history_file)
            versions = history.get("versions", [])
            
            # 按标签过滤
            if tags:
                versions = [v for v in versions if any(tag in v.get("tags", []) for tag in tags)]
            
            # 按时间排序（最新的在前）
            versions.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            
            return versions[:limit]
            
        except Exception as e:
            self.logger.error(f"列出版本历史失败: {e}")
            return []
    
    def get_current_version(self) -> Optional[str]:
        """获取当前版本ID"""
        try:
            if not self.current_version_file.exists():
                return None
            
            current_data = self._load_json(self.current_version_file)
            return current_data.get("version_id")
            
        except Exception as e:
            self.logger.error(f"获取当前版本失败: {e}")
            return None
    
    def rollback_to_version(self, version_id: str) -> bool:
        """回滚到指定版本"""
        try:
            # 检查版本是否存在
            if not self.get_version(version_id):
                self.logger.error(f"版本不存在: {version_id}")
                return False
            
            # 更新当前版本
            self._update_current_version(version_id)
            
            self.logger.info(f"回滚到版本: {version_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"回滚版本失败 {version_id}: {e}")
            return False
    
    def delete_version(self, version_id: str) -> bool:
        """删除指定版本"""
        try:
            version_file = self.versions_dir / f"{version_id}.json"
            if not version_file.exists():
                self.logger.warning(f"版本文件不存在: {version_id}")
                return False
            
            # 检查是否为当前版本
            current_version = self.get_current_version()
            if current_version == version_id:
                self.logger.error(f"不能删除当前版本: {version_id}")
                return False
            
            # 删除版本文件
            version_file.unlink()
            
            # 从历史中移除
            self._remove_from_history(version_id)
            
            self.logger.info(f"删除版本: {version_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"删除版本失败 {version_id}: {e}")
            return False
    
    def cleanup_old_versions(self, keep_count: int = 10) -> int:
        """清理旧版本，保留指定数量"""
        try:
            versions = self.list_versions()
            current_version = self.get_current_version()
            
            # 排除当前版本
            versions_to_check = [v for v in versions if v["version_id"] != current_version]
            
            if len(versions_to_check) <= keep_count:
                return 0
            
            # 删除多余的版本
            versions_to_delete = versions_to_check[keep_count:]
            deleted_count = 0
            
            for version in versions_to_delete:
                if self.delete_version(version["version_id"]):
                    deleted_count += 1
            
            self.logger.info(f"清理了 {deleted_count} 个旧版本")
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"清理旧版本失败: {e}")
            return 0
    
    def _generate_version_id(self) -> str:
        """生成版本ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"v_{timestamp}"
    
    def _calculate_checksum(self, data: Dict[str, Any]) -> str:
        """计算配置数据校验和"""
        import hashlib
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.md5(data_str.encode()).hexdigest()
    
    def _update_version_history(self, version_info: Dict[str, Any]):
        """更新版本历史"""
        history = self._load_json(self.history_file)
        history["versions"].append(version_info)
        history["last_updated"] = datetime.now().isoformat()
        self._save_json(self.history_file, history)
    
    def _update_current_version(self, version_id: str):
        """更新当前版本"""
        current_data = {
            "version_id": version_id,
            "updated_at": datetime.now().isoformat()
        }
        self._save_json(self.current_version_file, current_data)
    
    def _remove_from_history(self, version_id: str):
        """从历史中移除版本"""
        history = self._load_json(self.history_file)
        history["versions"] = [v for v in history["versions"] if v["version_id"] != version_id]
        history["last_updated"] = datetime.now().isoformat()
        self._save_json(self.history_file, history)
    
    def _save_json(self, file_path: Path, data: Dict[str, Any]):
        """保存JSON文件"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _load_json(self, file_path: Path) -> Dict[str, Any]:
        """加载JSON文件"""
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取版本管理统计信息"""
        try:
            versions = self.list_versions()
            current_version = self.get_current_version()
            
            return {
                "total_versions": len(versions),
                "current_version": current_version,
                "versions_dir": str(self.versions_dir),
                "disk_usage_mb": self._calculate_disk_usage(),
                "oldest_version": versions[-1]["timestamp"] if versions else None,
                "newest_version": versions[0]["timestamp"] if versions else None
            }
            
        except Exception as e:
            self.logger.error(f"获取统计信息失败: {e}")
            return {}
    
    def _calculate_disk_usage(self) -> float:
        """计算磁盘使用量（MB）"""
        total_size = 0
        for file_path in self.versions_dir.glob("*.json"):
            total_size += file_path.stat().st_size
        return round(total_size / (1024 * 1024), 2)
