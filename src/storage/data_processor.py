"""
数据处理器
负责数据的加密、解密、验证和格式化
"""

from cryptography.fernet import Fernet
import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging

from ..utils.crypto import LuckyCrypto, CryptoUtils
from ..utils.log_security import LogSecurity


class DataProcessor:
    """数据处理器 - 负责数据的加密解密和格式化"""
    
    def __init__(self, encryption_key: str):
        """
        初始化数据处理器

        Args:
            encryption_key: 加密密钥（支持44字符Fernet密钥或66字符吉利密钥）
        """
        self.logger = logging.getLogger(__name__)

        # 检测密钥类型并创建相应的加密器
        if len(encryption_key) == 66 and LuckyCrypto.validate_lucky_key(encryption_key):
            # 66字符吉利密钥
            self.cipher = LuckyCrypto.create_lucky_cipher(encryption_key)
            self.key_type = "lucky_66"
            self.logger.info("使用66字符吉利密钥初始化加密器")
        elif len(encryption_key) == 44 and CryptoUtils.validate_key(encryption_key):
            # 44字符Fernet密钥
            self.cipher = Fernet(encryption_key.encode())
            self.key_type = "fernet_44"
            self.logger.info("使用44字符Fernet密钥初始化加密器")
        else:
            raise ValueError(f"无效的加密密钥长度: {len(encryption_key)}，支持44字符或66字符密钥")

        if self.cipher is None:
            raise ValueError("加密器初始化失败")
    
    def encrypt_url(self, url: str) -> str:
        """
        加密URL

        Args:
            url: 原始URL

        Returns:
            str: 加密后的URL（Fernet格式）
        """
        try:
            # Fernet加密返回bytes，直接decode为字符串
            # Fernet的输出格式是URL安全的base64，不需要额外处理
            encrypted_bytes = self.cipher.encrypt(url.encode('utf-8'))
            return encrypted_bytes.decode('ascii')
        except Exception as e:
            self.logger.error(f"URL加密失败: {e}")
            raise
    
    def decrypt_url(self, encrypted: str) -> str:
        """
        解密URL

        Args:
            encrypted: 加密的URL（Fernet格式字符串）

        Returns:
            str: 解密后的URL
        """
        try:
            # Fernet格式字符串转换为bytes，然后解密
            encrypted_bytes = encrypted.encode('ascii')
            decrypted_bytes = self.cipher.decrypt(encrypted_bytes)
            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            self.logger.error(f"URL解密失败: {e}")
            raise
    
    def get_url_hash(self, url: str) -> str:
        """
        生成URL哈希用于索引
        
        Args:
            url: URL
            
        Returns:
            str: URL哈希值
        """
        return hashlib.sha256(url.encode()).hexdigest()
    
    def create_url_record(self, url: str, keywords: List[str],
                         seo_data: Dict[str, Dict]) -> Optional[str]:
        """
        创建URL记录 - 简化版本，只返回加密的URL

        Args:
            url: 原始URL
            keywords: 关键词列表
            seo_data: SEO数据字典

        Returns:
            Optional[str]: 加密的URL，无成功数据返回None
        """
        try:
            # 检查是否有成功查询的关键词
            successful_keywords = [k for k in keywords if k in seo_data and seo_data[k]]

            if not successful_keywords:
                return None

            # 只返回加密的URL
            return self.encrypt_url(url)

        except Exception as e:
            self.logger.error(f"创建URL记录失败 {LogSecurity.sanitize_url(url)}: {e}")
            return None
    
    def create_empty_storage(self) -> Dict[str, Any]:
        """
        创建空的存储结构 - 简化版本，只存储加密URL列表

        Returns:
            Dict[str, Any]: 空存储结构
        """
        return {
            "version": "2.0",
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "processed_urls": [],  # 改为列表，只存储加密的URL
            "statistics": {
                "total_urls": 0,
                "last_cleanup": None
            }
        }
    
    def validate_storage_data(self, data: Any) -> bool:
        """
        验证存储数据格式 - 支持新旧版本

        Args:
            data: 存储数据

        Returns:
            bool: 数据格式是否有效
        """
        if not isinstance(data, dict):
            return False

        required_fields = ['version', 'processed_urls', 'statistics']
        for field in required_fields:
            if field not in data:
                return False

        # 支持新版本（列表）和旧版本（字典）
        if not isinstance(data['processed_urls'], (dict, list)):
            return False

        if not isinstance(data['statistics'], dict):
            return False

        return True
    
    def find_expired_records(self, data: Dict[str, Any],
                           retention_days: int) -> List[str]:
        """
        查找过期记录

        Args:
            data: 存储数据
            retention_days: 保留天数

        Returns:
            List[str]: 过期记录的哈希列表
        """
        if retention_days <= 0:
            return []

        processed_urls = data.get('processed_urls', {})

        # 检查数据格式：新版本是列表，旧版本是字典
        if isinstance(processed_urls, list):
            # 新版本格式：processed_urls是加密URL列表，没有时间戳，不需要清理
            self.logger.debug("新版本数据格式（列表），无需清理过期数据")
            return []
        elif isinstance(processed_urls, dict):
            # 旧版本格式：processed_urls是字典，包含时间戳
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            expired_hashes = []

            for url_hash, record in processed_urls.items():
                try:
                    processed_at = datetime.fromisoformat(record['processed_at'])
                    if processed_at < cutoff_date:
                        expired_hashes.append(url_hash)
                except (ValueError, KeyError):
                    # 如果日期格式错误，也删除
                    expired_hashes.append(url_hash)

            return expired_hashes
        else:
            self.logger.warning(f"未知的processed_urls数据格式: {type(processed_urls)}")
            return []
    
    def update_statistics(self, data: Dict[str, Any]) -> None:
        """
        更新统计信息 - 简化版本

        Args:
            data: 存储数据
        """
        data['statistics']['total_urls'] += 1
        data['last_updated'] = datetime.now().isoformat()
    
    def calculate_statistics(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        计算详细统计信息
        
        Args:
            data: 存储数据
            
        Returns:
            Dict[str, Any]: 统计信息
        """
        stats = data['statistics'].copy()
        processed_urls = data['processed_urls']
        stats['current_urls'] = len(processed_urls)

        # 检查数据格式：新版本是列表，旧版本是字典
        if isinstance(processed_urls, list):
            # 新版本格式：processed_urls是加密URL列表，无法提取详细统计
            stats['unique_keywords'] = 0
            stats['total_seo_records'] = 0
            stats['top_keywords'] = []
            stats['data_format'] = 'new_list_format'

        elif isinstance(processed_urls, dict):
            # 旧版本格式：processed_urls是字典，可以提取详细统计
            keyword_counts = {}
            total_seo_records = 0

            for record in processed_urls.values():
                for keyword in record.get('keywords', []):
                    keyword_counts[keyword] = keyword_counts.get(keyword, 0) + 1

                total_seo_records += len(record.get('seo_data', {}))

            stats['unique_keywords'] = len(keyword_counts)
            stats['total_seo_records'] = total_seo_records
            stats['data_format'] = 'legacy_dict_format'

            # 最常见的关键词
            if keyword_counts:
                sorted_keywords = sorted(keyword_counts.items(),
                                       key=lambda x: x[1], reverse=True)
                stats['top_keywords'] = sorted_keywords[:10]
            else:
                stats['top_keywords'] = []
        else:
            # 未知格式，提供基础统计
            stats['unique_keywords'] = 0
            stats['total_seo_records'] = 0
            stats['top_keywords'] = []
            stats['data_format'] = f'unknown_{type(processed_urls).__name__}'
        
        return stats
    
    def create_export_record(self, url_hash: str, record: Dict[str, Any], 
                           include_url: bool = False) -> Dict[str, Any]:
        """
        创建导出记录
        
        Args:
            url_hash: URL哈希
            record: 原始记录
            include_url: 是否包含解密的URL
            
        Returns:
            Dict[str, Any]: 导出记录
        """
        export_record = {
            'url_hash': url_hash,
            'keywords': record['keywords'],
            'processed_at': record['processed_at'],
            'seo_data': record['seo_data']
        }
        
        if include_url:
            try:
                export_record['url'] = self.decrypt_url(record['url'])
            except Exception:
                export_record['url'] = '[解密失败]'
        
        return export_record
    
    def format_json_data(self, data: Any, indent: int = 2) -> str:
        """
        格式化JSON数据
        
        Args:
            data: 待格式化的数据
            indent: 缩进空格数
            
        Returns:
            str: 格式化的JSON字符串
        """
        return json.dumps(data, indent=indent, ensure_ascii=False)
    
    def parse_json_data(self, json_str: str) -> Any:
        """
        解析JSON数据
        
        Args:
            json_str: JSON字符串
            
        Returns:
            Any: 解析后的数据
            
        Raises:
            json.JSONDecodeError: JSON格式错误
        """
        return json.loads(json_str)
