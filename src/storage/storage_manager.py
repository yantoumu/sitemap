"""
存储管理器
负责URL-关键词的加密存储和去重检查
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
import aiofiles
import asyncio
import logging

from .data_processor import DataProcessor
from ..utils.log_security import LogSecurity


class StorageManager:
    """加密存储管理器"""
    
    def __init__(self, encryption_key: str, storage_file: str,
                 retention_days: int = 30):
        """
        初始化存储管理器

        Args:
            encryption_key: 加密密钥
            storage_file: 存储文件路径
            retention_days: 数据保留天数
        """
        self.processor = DataProcessor(encryption_key)
        self.storage_file = Path(storage_file)
        self.retention_days = retention_days
        self.lock = asyncio.Lock()
        self.logger = logging.getLogger(__name__)
        self.data = self._initialize_storage()

        self.logger.info(f"存储管理器初始化完成: {storage_file}")
    
    def _initialize_storage(self) -> Dict[str, Any]:
        """
        初始化存储结构
        
        Returns:
            Dict[str, Any]: 存储数据结构
        """
        if self.storage_file.exists():
            try:
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if self.processor.validate_storage_data(data):
                        # 检查是否需要迁移旧版本数据
                        if isinstance(data.get('processed_urls'), dict):
                            self.logger.info("检测到旧版本数据格式，进行迁移...")
                            migrated_data = self._migrate_old_data(data)
                            # 立即保存迁移后的数据
                            self._save_data_sync(migrated_data)
                            return migrated_data
                        else:
                            self.logger.info(f"加载现有存储数据: {len(data.get('processed_urls', []))} 条URL记录")
                            return data
                    else:
                        self.logger.warning("存储数据格式无效，创建新的存储结构")
                        return self.processor.create_empty_storage()
            except Exception as e:
                self.logger.error(f"加载存储文件失败: {e}")
                return self.processor.create_empty_storage()
        else:
            return self.processor.create_empty_storage()

    def _save_data_sync(self, data: Dict[str, Any]) -> None:
        """
        同步保存数据到文件

        Args:
            data: 要保存的数据
        """
        try:
            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self.logger.info(f"数据已同步保存到: {self.storage_file}")
        except Exception as e:
            self.logger.error(f"同步保存数据失败: {e}")

    def encrypt_url(self, url: str) -> str:
        """加密URL"""
        return self.processor.encrypt_url(url)

    def decrypt_url(self, encrypted: str) -> str:
        """解密URL"""
        return self.processor.decrypt_url(encrypted)

    def get_url_hash(self, url: str) -> str:
        """生成URL哈希"""
        return self.processor.get_url_hash(url)

    def _migrate_old_data(self, old_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        迁移旧版本数据到新格式

        Args:
            old_data: 旧版本数据

        Returns:
            Dict[str, Any]: 新格式数据
        """
        try:
            new_data = self.processor.create_empty_storage()

            # 从旧版本的字典格式提取加密URL
            old_urls = old_data.get('processed_urls', {})
            for url_hash, record in old_urls.items():
                if isinstance(record, dict) and 'url' in record:
                    encrypted_url = record['url']
                    if encrypted_url not in new_data['processed_urls']:
                        new_data['processed_urls'].append(encrypted_url)

            # 更新统计
            new_data['statistics']['total_urls'] = len(new_data['processed_urls'])
            new_data['created_at'] = old_data.get('created_at', new_data['created_at'])

            self.logger.info(f"数据迁移完成: {len(new_data['processed_urls'])} 条URL记录")
            return new_data

        except Exception as e:
            self.logger.error(f"数据迁移失败: {e}")
            return self.processor.create_empty_storage()

    def is_url_processed(self, url: str) -> bool:
        """
        检查URL是否已处理

        Args:
            url: 待检查的URL

        Returns:
            bool: 是否已处理
        """
        encrypted_url = self.encrypt_url(url)
        return encrypted_url in self.data['processed_urls']

    def is_keyword_processed(self, keyword: str) -> bool:
        """
        检查关键词是否已处理

        Args:
            keyword: 待检查的关键词

        Returns:
            bool: 是否已处理
        """
        try:
            encrypted_keyword = self.processor.encrypt_url(keyword)

            # 关键词数据文件路径
            keyword_file = Path(self.storage_file).parent / "processed_keywords.json"

            if not keyword_file.exists():
                return False

            # 读取已处理关键词列表
            with open(keyword_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if not content.strip():
                    return False
                processed_keywords = json.loads(content)

            return encrypted_keyword in processed_keywords

        except Exception as e:
            self.logger.warning(f"检查关键词处理状态失败 {keyword}: {e}")
            return False
    
    async def save_processed_url(self, url: str, keywords: List[str],
                                seo_data: Dict[str, Dict]) -> bool:
        """
        保存成功查询的URL - 简化版本，只保存加密URL

        Args:
            url: 原始URL
            keywords: 关键词列表
            seo_data: SEO数据字典

        Returns:
            bool: 是否保存成功
        """
        async with self.lock:
            try:
                # 创建URL记录（返回加密的URL或None）
                encrypted_url = self.processor.create_url_record(url, keywords, seo_data)
                if not encrypted_url:
                    # 使用安全日志记录，隐藏敏感URL
                    safe_url = LogSecurity.sanitize_url(url)
                    self.logger.debug(f"URL无成功关键词，跳过保存: {safe_url}")
                    return False

                # 检查是否已存在（避免重复）
                if encrypted_url not in self.data['processed_urls']:
                    # 保存加密的URL到列表
                    self.data['processed_urls'].append(encrypted_url)

                    # 更新统计
                    self.processor.update_statistics(self.data)

                    # 异步保存到磁盘
                    await self._save_to_disk()

                    # 使用安全日志记录，隐藏敏感URL
                    safe_url = LogSecurity.sanitize_url(url)
                    self.logger.debug(f"成功保存URL: {safe_url}")
                    return True
                else:
                    # 使用安全日志记录，隐藏敏感URL
                    safe_url = LogSecurity.sanitize_url(url)
                    self.logger.debug(f"URL已存在，跳过保存: {safe_url}")
                    return False

            except Exception as e:
                # 使用安全日志记录，隐藏敏感URL
                safe_url = LogSecurity.sanitize_url(url)
                self.logger.error(f"保存URL数据失败 {safe_url}: {e}")
                return False
    
    async def _save_to_disk(self) -> None:
        """异步保存到磁盘 - 增强容错性"""
        import tempfile
        import shutil

        try:
            # 确保目录存在
            self.storage_file.parent.mkdir(parents=True, exist_ok=True)

            # 检查磁盘空间（简单检查）
            try:
                disk_usage = shutil.disk_usage(self.storage_file.parent)
                if disk_usage.free < 100 * 1024 * 1024:  # 100MB
                    self.logger.warning("磁盘空间不足，可能影响数据保存")
            except Exception:
                pass  # 忽略磁盘空间检查失败

            # 使用临时文件确保原子性写入
            json_data = self.processor.format_json_data(self.data)

            # 创建临时文件
            temp_file = self.storage_file.with_suffix('.tmp')

            try:
                # 写入临时文件
                async with aiofiles.open(temp_file, 'w', encoding='utf-8') as f:
                    await f.write(json_data)

                # 原子性移动（在大多数文件系统上是原子的）
                temp_file.replace(self.storage_file)

            except Exception as e:
                # 清理临时文件
                if temp_file.exists():
                    temp_file.unlink()
                raise e

        except OSError as e:
            self.logger.error(f"文件系统错误，保存失败: {e}")
            raise
        except Exception as e:
            self.logger.error(f"保存到磁盘失败: {e}")
            raise
    
    def get_processed_urls_count(self) -> int:
        """
        获取已处理URL数量
        
        Returns:
            int: 已处理URL数量
        """
        return len(self.data['processed_urls'])
    
    def get_keywords_for_url(self, url: str) -> List[str]:
        """
        获取URL对应的关键词

        Args:
            url: URL

        Returns:
            List[str]: 关键词列表
        """
        url_hash = self.processor.get_url_hash(url)
        if url_hash in self.data['processed_urls']:
            return self.data['processed_urls'][url_hash]['keywords']
        return []

    def get_seo_data_for_url(self, url: str) -> Dict[str, Dict]:
        """
        获取URL对应的SEO数据

        Args:
            url: URL

        Returns:
            Dict[str, Dict]: SEO数据
        """
        url_hash = self.processor.get_url_hash(url)
        if url_hash in self.data['processed_urls']:
            return self.data['processed_urls'][url_hash].get('seo_data', {})
        return {}
    
    def clean_expired_data(self) -> int:
        """
        清理过期数据

        Returns:
            int: 清理的记录数
        """
        expired_hashes = self.processor.find_expired_records(self.data, self.retention_days)

        # 删除过期记录（仅适用于旧版本字典格式）
        if expired_hashes and isinstance(self.data['processed_urls'], dict):
            for url_hash in expired_hashes:
                if url_hash in self.data['processed_urls']:
                    del self.data['processed_urls'][url_hash]

            # 更新统计
            self.data['statistics']['last_cleanup'] = datetime.now().isoformat()
            self.logger.info(f"清理了 {len(expired_hashes)} 条过期数据")
        elif expired_hashes:
            self.logger.debug("新版本数据格式不支持过期清理")

        return len(expired_hashes)
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取存储统计信息

        Returns:
            Dict[str, Any]: 统计信息
        """
        stats = self.processor.calculate_statistics(self.data)
        stats['storage_file'] = str(self.storage_file)
        stats['retention_days'] = self.retention_days

        # 计算文件大小
        if self.storage_file.exists():
            stats['file_size_bytes'] = self.storage_file.stat().st_size
            stats['file_size_mb'] = round(stats['file_size_bytes'] / 1024 / 1024, 2)
        else:
            stats['file_size_bytes'] = 0
            stats['file_size_mb'] = 0

        return stats
    
    async def export_data(self, export_file: str, include_urls: bool = False) -> bool:
        """
        导出数据
        
        Args:
            export_file: 导出文件路径
            include_urls: 是否包含解密的URL
            
        Returns:
            bool: 是否导出成功
        """
        try:
            export_data = {
                'export_time': datetime.now().isoformat(),
                'total_records': len(self.data['processed_urls']),
                'statistics': self.get_statistics(),
                'records': []
            }
            
            for url_hash, record in self.data['processed_urls'].items():
                export_record = self.processor.create_export_record(
                    url_hash, record, include_urls
                )
                export_data['records'].append(export_record)
            
            # 异步写入导出文件
            json_data = self.processor.format_json_data(export_data)
            async with aiofiles.open(export_file, 'w', encoding='utf-8') as f:
                await f.write(json_data)
            
            self.logger.info(f"数据导出成功: {export_file}")
            return True

        except Exception as e:
            self.logger.error(f"数据导出失败: {e}")
            return False

    async def save_processed_keyword(self, keyword: str) -> bool:
        """
        保存已处理的关键词 (仅保存加密标识)

        Args:
            keyword: 关键词

        Returns:
            bool: 保存是否成功
        """
        try:
            # 加密关键词
            encrypted_keyword = self.processor.encrypt_url(keyword)

            # 关键词数据文件路径
            keyword_file = Path(self.storage_file).parent / "processed_keywords.json"

            # 确保目录存在
            keyword_file.parent.mkdir(parents=True, exist_ok=True)

            # 读取现有数据
            existing_data = []
            if keyword_file.exists():
                try:
                    async with aiofiles.open(keyword_file, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        if content.strip():
                            existing_data = json.loads(content)
                except (json.JSONDecodeError, Exception) as e:
                    self.logger.warning(f"读取已处理关键词文件失败: {e}")
                    existing_data = []

            # 检查是否已存在（避免重复）
            if encrypted_keyword not in existing_data:
                # 添加新的加密关键词
                existing_data.append(encrypted_keyword)

                # 写入文件
                async with aiofiles.open(keyword_file, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(existing_data, ensure_ascii=False, indent=2))

                self.logger.debug(f"保存已处理关键词: {keyword}")
                return True
            else:
                self.logger.debug(f"关键词已存在，跳过保存: {keyword}")
                return False

        except Exception as e:
            self.logger.error(f"保存已处理关键词失败 {keyword}: {e}")
            return False
            
        except Exception as e:
            self.logger.error(f"数据导出失败: {e}")
            return False
