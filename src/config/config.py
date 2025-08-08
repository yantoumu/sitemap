"""
配置加载器
负责加载和验证系统配置及URL提取规则
"""

import yaml
import os
from pathlib import Path
from typing import Dict, List, Any
from dotenv import load_dotenv
import logging

from .schemas import AppConfig, URLExtractionRule


class ConfigLoader:
    """配置加载器"""
    
    def __init__(self, config_path: str, rules_path: str):
        """
        初始化配置加载器
        
        Args:
            config_path: 系统配置文件路径
            rules_path: URL规则配置文件路径
        """
        self.config_path = Path(config_path)
        self.rules_path = Path(rules_path)
        self.logger = logging.getLogger(__name__)
        
        # 加载环境变量 - GitHub Actions环境优先
        is_github_actions = os.getenv('GITHUB_ACTIONS') == 'true'

        if is_github_actions:
            self.logger.debug("检测到GitHub Actions环境，跳过.env文件加载")
        else:
            # 本地环境：加载.env文件
            project_root = Path(__file__).parent.parent.parent
            env_file = project_root / '.env'

            if env_file.exists():
                result = load_dotenv(dotenv_path=env_file)
                self.logger.debug(f"加载环境变量文件: {env_file} (结果: {result})")
            else:
                # 尝试当前工作目录
                result = load_dotenv()
                self.logger.debug(f"加载当前目录环境变量文件 (结果: {result})")
        
    def load_system_config(self) -> AppConfig:
        """
        加载系统配置
        
        Returns:
            AppConfig: 验证后的系统配置
            
        Raises:
            FileNotFoundError: 配置文件不存在
            ValueError: 配置验证失败
        """
        try:
            # 检查配置文件是否存在
            if not self.config_path.exists():
                raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
            
            # 读取YAML配置文件
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            if not config_data:
                raise ValueError("配置文件为空")
            
            # 处理环境变量替换
            config_data = self._substitute_env_vars(config_data)
            
            # 验证并创建配置对象
            app_config = AppConfig(**config_data)
            
            self.logger.debug(f"成功加载系统配置: {self.config_path}")
            return app_config
            
        except yaml.YAMLError as e:
            raise ValueError(f"YAML配置文件格式错误: {e}")
        except Exception as e:
            self.logger.error(f"加载系统配置失败: {e}")
            raise
    
    def load_url_rules(self) -> Dict[str, URLExtractionRule]:
        """
        加载URL提取规则
        
        Returns:
            Dict[str, URLExtractionRule]: 域名到规则的映射
            
        Raises:
            FileNotFoundError: 规则文件不存在
            ValueError: 规则验证失败
        """
        try:
            # 检查规则文件是否存在
            if not self.rules_path.exists():
                raise FileNotFoundError(f"规则文件不存在: {self.rules_path}")
            
            # 读取YAML规则文件
            with open(self.rules_path, 'r', encoding='utf-8') as f:
                rules_data = yaml.safe_load(f)
            
            if not rules_data or 'rules' not in rules_data:
                raise ValueError("规则文件格式错误，缺少'rules'字段")
            
            # 验证并创建规则对象
            url_rules = {}
            for rule_data in rules_data['rules']:
                rule = URLExtractionRule(**rule_data)
                url_rules[rule.domain] = rule
            
            self.logger.debug(f"成功加载URL规则: {len(url_rules)}个域名规则")
            return url_rules
            
        except yaml.YAMLError as e:
            raise ValueError(f"YAML规则文件格式错误: {e}")
        except Exception as e:
            self.logger.error(f"加载URL规则失败: {e}")
            raise
    
    def _substitute_env_vars(self, data: Any) -> Any:
        """
        递归替换配置中的环境变量

        Args:
            data: 配置数据

        Returns:
            Any: 替换环境变量后的数据
        """
        if isinstance(data, dict):
            return {key: self._substitute_env_vars(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [self._substitute_env_vars(item) for item in data]
        elif isinstance(data, str) and data.startswith('${') and data.endswith('}'):
            # 提取环境变量名
            env_var = data[2:-1]
            env_value = os.getenv(env_var)

            if env_value is None:
                # 智能回退：尝试向后兼容变量
                fallback_var = self._get_fallback_env_var(env_var)
                if fallback_var:
                    env_value = os.getenv(fallback_var)
                    if env_value:
                        self.logger.info(f"使用回退变量: {fallback_var} → {env_var}")

                # 处理缺失的关键环境变量
                if env_value is None and env_var in {'SITEMAP_API_URL', 'SITEMAP_SECRET_KEY', 'ENCRYPTION_KEY'}:
                    is_github_actions = os.getenv('GITHUB_ACTIONS') == 'true'
                    error_msg = f"关键环境变量未设置: {env_var}"
                    error_msg += "。请检查GitHub Secrets配置。" if is_github_actions else "。请检查.env文件配置。"
                    raise ValueError(error_msg)
                elif env_value is None:
                    self.logger.warning(f"可选环境变量未设置: {env_var}")
                    return data

            # 清理环境变量值中的换行符和回车符（修复aiohttp安全检查问题）
            cleaned_value = self._sanitize_env_value(env_value)

            # 特殊处理：如果是URL列表字符串，转换为列表
            if ',' in cleaned_value and ('http' in cleaned_value or 'api' in cleaned_value.lower()):
                return [url.strip() for url in cleaned_value.split(',') if url.strip()]

            return cleaned_value
        else:
            return data

    def _sanitize_env_value(self, value: str) -> str:
        """
        清理环境变量值中的换行符和回车符

        Args:
            value: 原始环境变量值

        Returns:
            str: 清理后的值
        """
        if not value:
            return ""

        # 移除换行符、回车符和其他控制字符
        cleaned = value.strip().replace('\n', '').replace('\r', '').replace('\t', '')

        # 记录清理操作（仅在调试模式下）
        if cleaned != value.strip():
            self.logger.debug("环境变量值包含控制字符，已自动清理")

        return cleaned

    def _get_fallback_env_var(self, env_var: str) -> str:
        """
        获取向后兼容的环境变量名称

        Args:
            env_var: 当前环境变量名

        Returns:
            str: 向后兼容的环境变量名，如果没有则返回None
        """
        fallback_mapping = {
            'SITEMAP_API_URL': 'BACKEND_API_URL',
            'SITEMAP_SECRET_KEY': 'BACKEND_API_TOKEN'
        }
        fallback_var = fallback_mapping.get(env_var)

        # 智能选择：如果新变量指向localhost，优先使用旧变量
        if env_var == 'SITEMAP_API_URL':
            sitemap_url = os.getenv('SITEMAP_API_URL')
            backend_url = os.getenv('BACKEND_API_URL')

            # 如果SITEMAP_API_URL指向localhost，但BACKEND_API_URL指向真实服务器
            if (sitemap_url and 'localhost' in sitemap_url and
                backend_url and 'localhost' not in backend_url):
                self.logger.info(f"检测到 {env_var} 指向localhost，自动使用 BACKEND_API_URL")
                return 'BACKEND_API_URL'

        return fallback_var

    def validate_config_files(self) -> bool:
        """
        验证配置文件是否存在且格式正确
        
        Returns:
            bool: 验证是否通过
        """
        try:
            # 验证系统配置
            self.load_system_config()
            
            # 验证URL规则
            self.load_url_rules()
            
            self.logger.debug("配置文件验证通过")
            return True
            
        except Exception as e:
            self.logger.error(f"配置文件验证失败: {e}")
            return False
    
    def get_required_env_vars(self) -> List[str]:
        """
        获取必需的环境变量列表
        
        Returns:
            List[str]: 必需的环境变量名称列表
        """
        return [
            'SITEMAP_API_URL',    # 简化后端API地址
            'SITEMAP_SECRET_KEY', # 简化后端API密钥
            'SITEMAP_URLS',       # 要监控的sitemap URL列表
            'ENCRYPTION_KEY',     # 数据加密密钥
            # 已废弃的环境变量 (不再检查):
            # 'BACKEND_API_URL',    # 被 SITEMAP_API_URL 替代
            # 'BACKEND_API_TOKEN',  # 被 SITEMAP_SECRET_KEY 替代
            # 'SEO_API_URLS',       # SEO查询功能已移除
        ]
    
    def check_env_vars(self) -> Dict[str, bool]:
        """
        检查环境变量是否设置
        
        Returns:
            Dict[str, bool]: 环境变量名称到是否设置的映射
        """
        required_vars = self.get_required_env_vars()
        env_status = {}
        
        for var in required_vars:
            env_status[var] = os.getenv(var) is not None
            
        return env_status


def create_default_config() -> Dict[str, Any]:
    """
    创建默认配置字典
    
    Returns:
        Dict[str, Any]: 默认配置
    """
    return {
        # 简化后端API配置 (新)
        'simplified_backend': {
            'url': '${SITEMAP_API_URL}',
            'secret_key': '${SITEMAP_SECRET_KEY}',
            'batch_size': 100,
            'timeout': 30
        },
        
        # 已废弃配置 (保留用于兼容性，但不使用)
        # 'seo_api': {
        #     'urls': '${SEO_API_URLS}',  # SEO查询功能已移除
        #     'interval': 1.0,
        #     'batch_size': 5,
        #     'timeout': 30
        # },
        # 'backend_api': {
        #     'url': '${BACKEND_API_URL}',    # 被simplified_backend.url替代
        #     'auth_token': '${BACKEND_API_TOKEN}',  # 被simplified_backend.secret_key替代
        #     'batch_size': 100,
        #     'timeout': 30
        # },
        'system': {
            'max_concurrent': 10,
            'retry_times': 3,
            'retry_delay': 1.0
        },
        'storage': {
            'encryption_key': '${ENCRYPTION_KEY}',
            'storage_file': 'data/processed_urls.json',
            'data_retention_days': 0
        },
        'cache': {
            'ttl': 604800
        },
        'logging': {
            'level': 'INFO',
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            'file': 'logs/sitemap_analyzer.log',
            'max_size': '10MB',
            'backup_count': 5
        }
    }
