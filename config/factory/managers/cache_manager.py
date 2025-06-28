"""
配置缓存管理器
"""

import logging
import time
from typing import Dict, Any, Optional
import threading


class CacheManager:
    """配置缓存管理器"""
    
    def __init__(self, max_size: int = 1000, ttl: int = 300):
        self.max_size = max_size
        self.ttl = ttl
        self.cache = {}
        self.access_times = {}
        self.lock = threading.RLock()
        self.logger = logging.getLogger(__name__)
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        with self.lock:
            if key in self.cache:
                # 检查是否过期
                if time.time() - self.access_times[key] > self.ttl:
                    del self.cache[key]
                    del self.access_times[key]
                    return None
                
                # 更新访问时间
                self.access_times[key] = time.time()
                return self.cache[key]
            
            return None
    
    def set(self, key: str, value: Any):
        """设置缓存值"""
        with self.lock:
            # 检查缓存大小
            if len(self.cache) >= self.max_size:
                self._evict_oldest()
            
            self.cache[key] = value
            self.access_times[key] = time.time()
    
    def _evict_oldest(self):
        """淘汰最旧的缓存项"""
        if not self.access_times:
            return
        
        oldest_key = min(self.access_times.keys(), key=lambda k: self.access_times[k])
        del self.cache[oldest_key]
        del self.access_times[oldest_key]
    
    def clear(self):
        """清空缓存"""
        with self.lock:
            self.cache.clear()
            self.access_times.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        with self.lock:
            return {
                "size": len(self.cache),
                "max_size": self.max_size,
                "ttl": self.ttl,
                "keys": list(self.cache.keys())
            }
