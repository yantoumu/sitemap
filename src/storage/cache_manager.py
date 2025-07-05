"""
缓存管理器
提供关键词查询结果的内存缓存功能
"""

import time
from typing import Any, Optional, Dict, Set
from datetime import datetime, timedelta
import logging
import threading


class CacheManager:
    """内存缓存管理器"""
    
    def __init__(self, default_ttl: int = 604800):  # 默认7天
        """
        初始化缓存管理器
        
        Args:
            default_ttl: 默认TTL（秒）
        """
        self.default_ttl = default_ttl
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.RLock()
        self.logger = logging.getLogger(__name__)
        
        # 统计信息
        self.stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0,
            'cleanups': 0
        }
        
        self.logger.info(f"缓存管理器初始化完成，默认TTL: {default_ttl}秒")
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值
        
        Args:
            key: 缓存键
            
        Returns:
            Optional[Any]: 缓存值，不存在或过期返回None
        """
        with self.lock:
            if key not in self.cache:
                self.stats['misses'] += 1
                return None
            
            cache_item = self.cache[key]
            
            # 检查是否过期
            if self._is_expired(cache_item):
                del self.cache[key]
                self.stats['misses'] += 1
                return None
            
            # 更新访问时间
            cache_item['last_accessed'] = time.time()
            self.stats['hits'] += 1
            
            return cache_item['value']
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 生存时间（秒），None使用默认TTL
        """
        if ttl is None:
            ttl = self.default_ttl
        
        with self.lock:
            current_time = time.time()
            
            self.cache[key] = {
                'value': value,
                'created_at': current_time,
                'last_accessed': current_time,
                'expires_at': current_time + ttl,
                'ttl': ttl
            }
            
            self.stats['sets'] += 1
    
    def exists(self, key: str) -> bool:
        """
        检查键是否存在且未过期
        
        Args:
            key: 缓存键
            
        Returns:
            bool: 是否存在
        """
        return self.get(key) is not None
    
    def delete(self, key: str) -> bool:
        """
        删除缓存项
        
        Args:
            key: 缓存键
            
        Returns:
            bool: 是否删除成功
        """
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                self.stats['deletes'] += 1
                return True
            return False
    
    def clear(self) -> None:
        """清空所有缓存"""
        with self.lock:
            cleared_count = len(self.cache)
            self.cache.clear()
            self.logger.info(f"清空缓存: {cleared_count} 项")
    
    def clear_expired(self) -> int:
        """
        清理过期缓存项
        
        Returns:
            int: 清理的项目数
        """
        with self.lock:
            expired_keys = []
            
            for key, cache_item in self.cache.items():
                if self._is_expired(cache_item):
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self.cache[key]
            
            if expired_keys:
                self.stats['cleanups'] += 1
                self.logger.debug(f"清理过期缓存: {len(expired_keys)} 项")
            
            return len(expired_keys)
    
    def _is_expired(self, cache_item: Dict[str, Any]) -> bool:
        """
        检查缓存项是否过期
        
        Args:
            cache_item: 缓存项
            
        Returns:
            bool: 是否过期
        """
        return time.time() > cache_item['expires_at']
    
    def get_size(self) -> int:
        """
        获取缓存大小
        
        Returns:
            int: 缓存项数量
        """
        return len(self.cache)
    
    def get_keys(self) -> Set[str]:
        """
        获取所有缓存键
        
        Returns:
            Set[str]: 缓存键集合
        """
        with self.lock:
            return set(self.cache.keys())
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        with self.lock:
            stats = self.stats.copy()
            stats['current_size'] = len(self.cache)
            stats['default_ttl'] = self.default_ttl
            
            # 计算命中率
            total_requests = stats['hits'] + stats['misses']
            if total_requests > 0:
                stats['hit_rate'] = (stats['hits'] / total_requests) * 100
            else:
                stats['hit_rate'] = 0
            
            return stats
    
    def reset_statistics(self) -> None:
        """重置统计信息"""
        with self.lock:
            self.stats = {
                'hits': 0,
                'misses': 0,
                'sets': 0,
                'deletes': 0,
                'cleanups': 0
            }
            self.logger.info("缓存统计信息已重置")
    
    def get_cache_info(self, key: str) -> Optional[Dict[str, Any]]:
        """
        获取缓存项详细信息
        
        Args:
            key: 缓存键
            
        Returns:
            Optional[Dict[str, Any]]: 缓存项信息
        """
        with self.lock:
            if key not in self.cache:
                return None
            
            cache_item = self.cache[key]
            current_time = time.time()
            
            return {
                'key': key,
                'created_at': datetime.fromtimestamp(cache_item['created_at']).isoformat(),
                'last_accessed': datetime.fromtimestamp(cache_item['last_accessed']).isoformat(),
                'expires_at': datetime.fromtimestamp(cache_item['expires_at']).isoformat(),
                'ttl': cache_item['ttl'],
                'remaining_ttl': max(0, int(cache_item['expires_at'] - current_time)),
                'is_expired': self._is_expired(cache_item)
            }
    
    def extend_ttl(self, key: str, additional_seconds: int) -> bool:
        """
        延长缓存项的TTL
        
        Args:
            key: 缓存键
            additional_seconds: 额外的秒数
            
        Returns:
            bool: 是否成功
        """
        with self.lock:
            if key not in self.cache:
                return False
            
            cache_item = self.cache[key]
            if self._is_expired(cache_item):
                del self.cache[key]
                return False
            
            cache_item['expires_at'] += additional_seconds
            cache_item['ttl'] += additional_seconds
            
            return True
    
    def get_memory_usage_estimate(self) -> Dict[str, Any]:
        """
        估算内存使用情况
        
        Returns:
            Dict[str, Any]: 内存使用估算
        """
        import sys
        
        with self.lock:
            total_size = 0
            
            # 估算缓存数据大小
            for key, cache_item in self.cache.items():
                total_size += sys.getsizeof(key)
                total_size += sys.getsizeof(cache_item)
                total_size += sys.getsizeof(cache_item['value'])
            
            return {
                'estimated_bytes': total_size,
                'estimated_kb': round(total_size / 1024, 2),
                'estimated_mb': round(total_size / 1024 / 1024, 2),
                'items_count': len(self.cache)
            }
