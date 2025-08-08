"""
环境变量解析器 - 单一职责原则
负责环境变量的解析、验证和回退策略
"""

import os
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional, Any
from dataclasses import dataclass


@dataclass
class EnvResolutionResult:
    """环境变量解析结果"""
    value: Optional[str]
    source: str  # 'primary', 'fallback', 'missing'
    variable_name: str


class EnvResolver(ABC):
    """环境变量解析器接口"""
    
    @abstractmethod
    def resolve(self, var_name: str) -> EnvResolutionResult:
        """解析环境变量"""
        pass


class GitHubActionsEnvResolver(EnvResolver):
    """GitHub Actions环境变量解析器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.fallback_mapping = {
            'SITEMAP_API_URL': 'BACKEND_API_URL',
            'SITEMAP_SECRET_KEY': 'BACKEND_API_TOKEN'
        }
    
    def resolve(self, var_name: str) -> EnvResolutionResult:
        """解析环境变量，支持回退策略"""
        # 尝试主要变量
        primary_value = os.getenv(var_name)
        if primary_value:
            return EnvResolutionResult(primary_value, 'primary', var_name)
        
        # 尝试回退变量
        fallback_var = self.fallback_mapping.get(var_name)
        if fallback_var:
            fallback_value = os.getenv(fallback_var)
            if fallback_value:
                self.logger.info(f"使用回退变量: {fallback_var} → {var_name}")
                return EnvResolutionResult(fallback_value, 'fallback', fallback_var)
        
        return EnvResolutionResult(None, 'missing', var_name)


class LocalEnvResolver(EnvResolver):
    """本地环境变量解析器"""
    
    def __init__(self, env_file_path: Optional[str] = None):
        self.logger = logging.getLogger(__name__)
        self.env_file_path = env_file_path
        
    def resolve(self, var_name: str) -> EnvResolutionResult:
        """解析本地环境变量"""
        value = os.getenv(var_name)
        if value:
            return EnvResolutionResult(value, 'primary', var_name)
        
        return EnvResolutionResult(None, 'missing', var_name)


class EnvResolverFactory:
    """环境变量解析器工厂"""
    
    @staticmethod
    def create_resolver() -> EnvResolver:
        """根据运行环境创建合适的解析器"""
        is_github_actions = os.getenv('GITHUB_ACTIONS') == 'true'
        
        if is_github_actions:
            return GitHubActionsEnvResolver()
        else:
            return LocalEnvResolver()


class ConfigEnvSubstitution:
    """配置环境变量替换器"""
    
    def __init__(self, resolver: EnvResolver):
        self.resolver = resolver
        self.logger = logging.getLogger(__name__)
        self.critical_vars = {'SITEMAP_API_URL', 'SITEMAP_SECRET_KEY', 'ENCRYPTION_KEY'}
    
    def substitute(self, data: Any) -> Any:
        """递归替换配置中的环境变量"""
        if isinstance(data, dict):
            return {key: self.substitute(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [self.substitute(item) for item in data]
        elif isinstance(data, str) and data.startswith('${') and data.endswith('}'):
            return self._resolve_env_var(data)
        else:
            return data
    
    def _resolve_env_var(self, env_placeholder: str) -> str:
        """解析单个环境变量占位符"""
        var_name = env_placeholder[2:-1]  # 移除 ${ 和 }
        result = self.resolver.resolve(var_name)
        
        if result.value is None:
            # 对于关键环境变量，直接抛出错误，不返回占位符
            if var_name in self.critical_vars:
                self._handle_missing_var(var_name)
                # _handle_missing_var会抛出ValueError，这里不会执行到
                raise ValueError(f"关键环境变量未设置: {var_name}")
            else:
                # 非关键变量，记录警告并返回占位符
                self.logger.warning(f"可选环境变量未设置: {var_name}")
                return env_placeholder
        
        # 记录解析信息
        if result.source == 'fallback':
            self.logger.warning(f"环境变量回退: {var_name} → {result.variable_name}")
        
        return self._sanitize_value(result.value)
    
    def _handle_missing_var(self, var_name: str) -> None:
        """处理缺失的环境变量"""
        is_github_actions = os.getenv('GITHUB_ACTIONS') == 'true'
        
        if var_name in self.critical_vars:
            error_msg = f"关键环境变量未设置: {var_name}"
            if is_github_actions:
                error_msg += "。请检查GitHub Secrets配置。"
            else:
                error_msg += "。请检查.env文件配置。"
            
            self.logger.error(error_msg)
            raise ValueError(error_msg)
        else:
            self.logger.warning(f"可选环境变量未设置: {var_name}")
    
    def _sanitize_value(self, value: str) -> str:
        """清理环境变量值"""
        if not value:
            return ""
        
        # 移除控制字符
        cleaned = value.strip().replace('\n', '').replace('\r', '').replace('\t', '')
        
        # 特殊处理：URL列表
        if ',' in cleaned and ('http' in cleaned or 'api' in cleaned.lower()):
            return [url.strip() for url in cleaned.split(',') if url.strip()]
        
        return cleaned
