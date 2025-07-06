#!/usr/bin/env python3
"""
日志安全工具
防止敏感信息泄露到日志中
"""

import re
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


class LogSecurity:
    """日志安全处理类"""
    
    # 敏感信息模式
    SENSITIVE_PATTERNS = [
        # API密钥模式
        (r'["\']?api[_-]?key["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)["\']?', 'API_KEY'),
        (r'["\']?token["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)["\']?', 'TOKEN'),
        (r'["\']?secret["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)["\']?', 'SECRET'),
        (r'["\']?password["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)["\']?', 'PASSWORD'),
        
        # 特定API密钥格式
        (r'sitemap-update-api-key-\d+', 'API_KEY'),
        (r'[A-Za-z0-9_-]{32,}', 'LONG_KEY'),  # 长密钥
        
        # Fernet密钥格式
        (r'[A-Za-z0-9_-]{44}=?', 'FERNET_KEY'),
    ]
    
    # 敏感域名模式
    SENSITIVE_DOMAINS = [
        'seokey.vip',
        'api1.seokey.vip',
        'api2.seokey.vip',
        'k3.seokey.vip',
        'ads.seokey.vip',
        'work.seokey.vip'
    ]
    
    @classmethod
    def sanitize_url(cls, url: str) -> str:
        """
        对URL进行脱敏处理 - 隐藏所有域名以保护隐私

        Args:
            url: 原始URL

        Returns:
            str: 脱敏后的URL，格式为 https://***
        """
        if not url:
            return url

        try:
            parsed = urlparse(url)

            # 对所有URL进行脱敏，只保留协议，隐藏域名和路径
            if parsed.scheme:
                return f"{parsed.scheme}://***"
            else:
                return "https://***"

        except Exception:
            # 如果解析失败，返回通用脱敏格式
            return "https://***"
    
    @classmethod
    def sanitize_text(cls, text: str) -> str:
        """
        对文本进行脱敏处理
        
        Args:
            text: 原始文本
            
        Returns:
            str: 脱敏后的文本
        """
        if not text:
            return text
            
        sanitized = text
        
        # 处理敏感模式
        for pattern, replacement_type in cls.SENSITIVE_PATTERNS:
            sanitized = re.sub(
                pattern, 
                lambda m: m.group(0).replace(m.group(1), f'***{replacement_type}***'),
                sanitized,
                flags=re.IGNORECASE
            )
        
        # 处理敏感域名
        for domain in cls.SENSITIVE_DOMAINS:
            sanitized = sanitized.replace(domain, '***')
        
        return sanitized
    
    @classmethod
    def sanitize_dict(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        对字典数据进行脱敏处理
        
        Args:
            data: 原始字典
            
        Returns:
            Dict[str, Any]: 脱敏后的字典
        """
        if not isinstance(data, dict):
            return data
            
        sanitized = {}
        
        for key, value in data.items():
            # 检查键名是否敏感
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in ['key', 'token', 'secret', 'password']):
                sanitized[key] = '***REDACTED***'
            elif isinstance(value, str):
                if 'url' in key_lower:
                    sanitized[key] = cls.sanitize_url(value)
                else:
                    sanitized[key] = cls.sanitize_text(value)
            elif isinstance(value, dict):
                sanitized[key] = cls.sanitize_dict(value)
            elif isinstance(value, list):
                sanitized[key] = [cls.sanitize_text(str(item)) if isinstance(item, str) else item for item in value]
            else:
                sanitized[key] = value
                
        return sanitized
    
    @classmethod
    def safe_log_url(cls, logger: logging.Logger, level: int, message: str, url: str) -> None:
        """
        安全地记录包含URL的日志
        
        Args:
            logger: 日志记录器
            level: 日志级别
            message: 日志消息
            url: URL地址
        """
        safe_url = cls.sanitize_url(url)
        logger.log(level, f"{message}: {safe_url}")
    
    @classmethod
    def safe_log_data(cls, logger: logging.Logger, level: int, message: str, data: Any) -> None:
        """
        安全地记录包含数据的日志
        
        Args:
            logger: 日志记录器
            level: 日志级别
            message: 日志消息
            data: 数据对象
        """
        if isinstance(data, dict):
            safe_data = cls.sanitize_dict(data)
        elif isinstance(data, str):
            safe_data = cls.sanitize_text(data)
        else:
            safe_data = cls.sanitize_text(str(data))
            
        logger.log(level, f"{message}: {safe_data}")


class SecureLogger:
    """安全日志记录器包装类"""
    
    def __init__(self, logger: logging.Logger):
        """
        初始化安全日志记录器
        
        Args:
            logger: 原始日志记录器
        """
        self.logger = logger
        self.security = LogSecurity()
    
    def info(self, message: str, *args, **kwargs) -> None:
        """安全的info日志"""
        safe_message = self.security.sanitize_text(message)
        self.logger.info(safe_message, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs) -> None:
        """安全的warning日志"""
        safe_message = self.security.sanitize_text(message)
        self.logger.warning(safe_message, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs) -> None:
        """安全的error日志"""
        safe_message = self.security.sanitize_text(message)
        self.logger.error(safe_message, *args, **kwargs)
    
    def debug(self, message: str, *args, **kwargs) -> None:
        """安全的debug日志"""
        safe_message = self.security.sanitize_text(message)
        self.logger.debug(safe_message, *args, **kwargs)
    
    def log_url(self, level: int, message: str, url: str) -> None:
        """安全地记录URL"""
        LogSecurity.safe_log_url(self.logger, level, message, url)
    
    def log_data(self, level: int, message: str, data: Any) -> None:
        """安全地记录数据"""
        LogSecurity.safe_log_data(self.logger, level, message, data)


def get_secure_logger(name: str) -> SecureLogger:
    """
    获取安全日志记录器
    
    Args:
        name: 日志记录器名称
        
    Returns:
        SecureLogger: 安全日志记录器
    """
    logger = logging.getLogger(name)
    return SecureLogger(logger)
