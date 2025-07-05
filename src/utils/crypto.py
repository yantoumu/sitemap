"""
加密工具模块
提供加密密钥生成和验证功能
"""

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import os
import secrets
import string
from typing import Optional
import logging


class LuckyCrypto:
    """
    吉利数字加密类
    支持66字符的自定义密钥长度
    """

    @staticmethod
    def generate_lucky_key() -> str:
        """
        生成66字符的吉利加密密钥

        Returns:
            str: 66字符的加密密钥
        """
        # 生成66个随机字符（包含大小写字母和数字）
        chars = string.ascii_letters + string.digits
        lucky_key = ''.join(secrets.choice(chars) for _ in range(66))
        return lucky_key

    @staticmethod
    def validate_lucky_key(key: str) -> bool:
        """
        验证66字符密钥是否有效

        Args:
            key: 待验证的密钥

        Returns:
            bool: 密钥是否有效
        """
        if len(key) != 66:
            return False

        # 检查是否只包含字母和数字
        return key.isalnum()

    @staticmethod
    def derive_fernet_key(lucky_key: str, salt: bytes = None) -> bytes:
        """
        从66字符密钥派生Fernet密钥

        Args:
            lucky_key: 66字符的吉利密钥
            salt: 盐值（可选）

        Returns:
            bytes: 32字节的Fernet密钥
        """
        if salt is None:
            # 使用固定盐值确保一致性
            salt = b'lucky_crypto_salt_66'

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )

        return kdf.derive(lucky_key.encode())

    @staticmethod
    def create_lucky_cipher(lucky_key: str) -> Optional[Fernet]:
        """
        从66字符密钥创建Fernet加密器

        Args:
            lucky_key: 66字符的吉利密钥

        Returns:
            Optional[Fernet]: Fernet加密器实例
        """
        try:
            if not LuckyCrypto.validate_lucky_key(lucky_key):
                return None

            # 派生Fernet密钥
            fernet_key = LuckyCrypto.derive_fernet_key(lucky_key)
            fernet_key_b64 = base64.urlsafe_b64encode(fernet_key)

            return Fernet(fernet_key_b64)
        except Exception:
            return None


class CryptoUtils:
    """加密工具类（保持向后兼容）"""
    
    @staticmethod
    def generate_key() -> str:
        """
        生成新的Fernet加密密钥
        
        Returns:
            str: Base64编码的加密密钥
        """
        return Fernet.generate_key().decode()
    
    @staticmethod
    def validate_key(key: str) -> bool:
        """
        验证加密密钥是否有效
        
        Args:
            key: 待验证的密钥
            
        Returns:
            bool: 密钥是否有效
        """
        try:
            if len(key) != 44:
                return False
            
            # 尝试创建Fernet实例
            Fernet(key.encode())
            return True
        except Exception:
            return False
    
    @staticmethod
    def create_cipher(key: str) -> Optional[Fernet]:
        """
        创建Fernet加密器
        
        Args:
            key: 加密密钥
            
        Returns:
            Optional[Fernet]: 加密器实例，失败返回None
        """
        try:
            return Fernet(key.encode())
        except Exception:
            return None
    
    @staticmethod
    def encrypt_text(text: str, key: str) -> Optional[str]:
        """
        加密文本
        
        Args:
            text: 待加密的文本
            key: 加密密钥
            
        Returns:
            Optional[str]: 加密后的文本，失败返回None
        """
        try:
            cipher = CryptoUtils.create_cipher(key)
            if cipher:
                encrypted = cipher.encrypt(text.encode())
                return encrypted.decode()
            return None
        except Exception:
            return None
    
    @staticmethod
    def decrypt_text(encrypted_text: str, key: str) -> Optional[str]:
        """
        解密文本
        
        Args:
            encrypted_text: 加密的文本
            key: 加密密钥
            
        Returns:
            Optional[str]: 解密后的文本，失败返回None
        """
        try:
            cipher = CryptoUtils.create_cipher(key)
            if cipher:
                decrypted = cipher.decrypt(encrypted_text.encode())
                return decrypted.decode()
            return None
        except Exception:
            return None
    
    @staticmethod
    def generate_secure_token(length: int = 32) -> str:
        """
        生成安全的随机令牌
        
        Args:
            length: 令牌长度
            
        Returns:
            str: 十六进制令牌
        """
        return secrets.token_hex(length)
    
    @staticmethod
    def generate_api_key(length: int = 32) -> str:
        """
        生成API密钥
        
        Args:
            length: 密钥长度
            
        Returns:
            str: Base64编码的API密钥
        """
        random_bytes = secrets.token_bytes(length)
        return base64.urlsafe_b64encode(random_bytes).decode().rstrip('=')


def ensure_encryption_key(env_var: str = 'ENCRYPTION_KEY') -> str:
    """
    确保加密密钥存在，不存在则生成新的
    
    Args:
        env_var: 环境变量名
        
    Returns:
        str: 加密密钥
    """
    logger = logging.getLogger(__name__)
    
    # 从环境变量获取
    key = os.getenv(env_var)
    
    if key and CryptoUtils.validate_key(key):
        logger.info("使用现有的加密密钥")
        return key
    
    # 生成新密钥
    new_key = CryptoUtils.generate_key()
    logger.warning(f"生成新的加密密钥，请设置环境变量 {env_var}={new_key}")
    
    return new_key


def create_env_file_template(file_path: str = '.env') -> None:
    """
    创建环境变量文件模板
    
    Args:
        file_path: 环境变量文件路径
    """
    logger = logging.getLogger(__name__)
    
    if os.path.exists(file_path):
        logger.info(f"环境变量文件已存在: {file_path}")
        return
    
    template = f"""# 网站地图关键词分析工具 - 环境变量配置
# 请填入实际值

# 数据加密密钥 (推荐66字符吉利密钥)
ENCRYPTION_KEY={LuckyCrypto.generate_lucky_key()}

# SEO API配置 - 统一管理所有API地址
SEO_API_URLS=https://api1.example.com,https://api2.example.com,https://k3.example.com,https://ads.example.com

# 后端API配置 - 统一的后端服务
BACKEND_API_URL=https://work.example.com
BACKEND_API_TOKEN={CryptoUtils.generate_api_key()}

# 可选配置
LOG_LEVEL=INFO
MAX_CONCURRENT=10
RETRY_TIMES=3
DATA_RETENTION_DAYS=30
"""
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(template)
        logger.info(f"创建环境变量文件模板: {file_path}")
    except Exception as e:
        logger.error(f"创建环境变量文件失败: {e}")


class SecureConfig:
    """安全配置管理器"""
    
    def __init__(self, encryption_key: str):
        """
        初始化安全配置管理器
        
        Args:
            encryption_key: 加密密钥
        """
        self.cipher = CryptoUtils.create_cipher(encryption_key)
        self.logger = logging.getLogger(__name__)
    
    def encrypt_config_value(self, value: str) -> Optional[str]:
        """
        加密配置值
        
        Args:
            value: 配置值
            
        Returns:
            Optional[str]: 加密后的值
        """
        if not self.cipher:
            return None
        
        try:
            encrypted = self.cipher.encrypt(value.encode())
            return encrypted.decode()
        except Exception as e:
            self.logger.error(f"加密配置值失败: {e}")
            return None
    
    def decrypt_config_value(self, encrypted_value: str) -> Optional[str]:
        """
        解密配置值
        
        Args:
            encrypted_value: 加密的配置值
            
        Returns:
            Optional[str]: 解密后的值
        """
        if not self.cipher:
            return None
        
        try:
            decrypted = self.cipher.decrypt(encrypted_value.encode())
            return decrypted.decode()
        except Exception as e:
            self.logger.error(f"解密配置值失败: {e}")
            return None
    
    def is_encrypted(self, value: str) -> bool:
        """
        检查值是否已加密
        
        Args:
            value: 待检查的值
            
        Returns:
            bool: 是否已加密
        """
        try:
            if not self.cipher:
                return False
            
            self.cipher.decrypt(value.encode())
            return True
        except Exception:
            return False
