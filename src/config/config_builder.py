"""
配置构建器 - 建造者模式
提供灵活的配置构建和验证机制
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod

from .schemas import AppConfig
from .env_resolver import EnvResolverFactory, ConfigEnvSubstitution
from .validation_chain import ConfigValidationChain


class ConfigBuilder(ABC):
    """配置构建器接口"""
    
    @abstractmethod
    def load_raw_config(self) -> Dict[str, Any]:
        """加载原始配置"""
        pass
    
    @abstractmethod
    def resolve_environment_variables(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """解析环境变量"""
        pass
    
    @abstractmethod
    def validate_config(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """验证配置"""
        pass
    
    @abstractmethod
    def build_config_object(self, config_data: Dict[str, Any]) -> AppConfig:
        """构建配置对象"""
        pass


class StandardConfigBuilder(ConfigBuilder):
    """标准配置构建器"""
    
    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.logger = logging.getLogger(__name__)
        self.env_resolver = EnvResolverFactory.create_resolver()
        self.env_substitution = ConfigEnvSubstitution(self.env_resolver)
        self.validation_chain = ConfigValidationChain()
    
    def load_raw_config(self) -> Dict[str, Any]:
        """加载YAML配置文件"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            if not config_data:
                raise ValueError("配置文件为空")
            
            self.logger.debug(f"成功加载配置文件: {self.config_path}")
            return config_data
            
        except yaml.YAMLError as e:
            raise ValueError(f"YAML配置文件格式错误: {e}")
    
    def resolve_environment_variables(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """解析环境变量占位符"""
        try:
            resolved_data = self.env_substitution.substitute(config_data)
            self.logger.debug("环境变量解析完成")
            return resolved_data
        except Exception as e:
            self.logger.error(f"环境变量解析失败: {e}")
            raise
    
    def validate_config(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """验证配置数据"""
        validation_result = self.validation_chain.validate(config_data)
        
        if not validation_result.is_valid:
            error_msg = "配置验证失败:\n" + "\n".join(validation_result.errors)
            raise ValueError(error_msg)
        
        # 返回修复后的数据（如果有）
        return validation_result.fixed_data or config_data
    
    def build_config_object(self, config_data: Dict[str, Any]) -> AppConfig:
        """构建Pydantic配置对象"""
        try:
            app_config = AppConfig(**config_data)
            self.logger.debug("配置对象构建成功")
            return app_config
        except Exception as e:
            self.logger.error(f"配置对象构建失败: {e}")
            raise


class ConfigDirector:
    """配置构建指挥者"""
    
    def __init__(self, builder: ConfigBuilder):
        self.builder = builder
        self.logger = logging.getLogger(__name__)
    
    def construct_config(self) -> AppConfig:
        """构建完整配置"""
        try:
            # 1. 加载原始配置
            self.logger.debug("步骤1: 加载原始配置")
            raw_config = self.builder.load_raw_config()
            
            # 2. 解析环境变量
            self.logger.debug("步骤2: 解析环境变量")
            resolved_config = self.builder.resolve_environment_variables(raw_config)
            
            # 3. 验证配置
            self.logger.debug("步骤3: 验证配置")
            validated_config = self.builder.validate_config(resolved_config)
            
            # 4. 构建配置对象
            self.logger.debug("步骤4: 构建配置对象")
            app_config = self.builder.build_config_object(validated_config)
            
            self.logger.info("配置构建完成")
            return app_config
            
        except Exception as e:
            self.logger.error(f"配置构建失败: {e}")
            raise


class ConfigFactory:
    """配置工厂"""
    
    @staticmethod
    def create_config_loader(config_path: str) -> ConfigDirector:
        """创建配置加载器"""
        builder = StandardConfigBuilder(config_path)
        return ConfigDirector(builder)
    
    @staticmethod
    def load_config(config_path: str) -> AppConfig:
        """快速加载配置"""
        director = ConfigFactory.create_config_loader(config_path)
        return director.construct_config()


class ConfigHealthChecker:
    """配置健康检查器"""
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def check_health(self) -> Dict[str, bool]:
        """执行配置健康检查"""
        health_status = {}
        
        # 检查后端API配置
        health_status['backend_api_url'] = self._check_backend_api_url()
        health_status['backend_api_token'] = self._check_backend_api_token()
        
        # 检查存储配置
        health_status['encryption_key'] = self._check_encryption_key()
        
        # 检查系统配置
        health_status['system_config'] = self._check_system_config()
        
        return health_status
    
    def _check_backend_api_url(self) -> bool:
        """检查后端API URL"""
        url = self.config.backend_api.url
        
        if not url:
            return False
        
        if not url.startswith(('http://', 'https://')):
            return False
        
        if 'localhost' in url:
            is_github_actions = os.getenv('GITHUB_ACTIONS') == 'true'
            if is_github_actions:
                self.logger.warning("GitHub Actions环境中使用localhost URL")
                return False
        
        return True
    
    def _check_backend_api_token(self) -> bool:
        """检查后端API令牌"""
        token = self.config.backend_api.auth_token
        return bool(token and len(token) > 10)
    
    def _check_encryption_key(self) -> bool:
        """检查加密密钥"""
        key = self.config.storage.encryption_key
        return bool(key and len(key) in [44, 66])
    
    def _check_system_config(self) -> bool:
        """检查系统配置"""
        system = self.config.system
        return (
            1 <= system.max_concurrent <= 100 and
            0 <= system.retry_times <= 10 and
            system.retry_delay > 0
        )
