"""
配置验证链 - 责任链模式
提供可扩展的配置验证机制
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    fixed_data: Optional[Dict[str, Any]] = None


class ConfigValidator(ABC):
    """配置验证器基类"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.next_validator: Optional['ConfigValidator'] = None
    
    def set_next(self, validator: 'ConfigValidator') -> 'ConfigValidator':
        """设置下一个验证器"""
        self.next_validator = validator
        return validator
    
    def validate(self, config_data: Dict[str, Any]) -> ValidationResult:
        """验证配置数据"""
        result = self._validate_impl(config_data)
        
        if self.next_validator and result.is_valid:
            next_result = self.next_validator.validate(
                result.fixed_data or config_data
            )
            # 合并结果
            result.errors.extend(next_result.errors)
            result.warnings.extend(next_result.warnings)
            result.is_valid = result.is_valid and next_result.is_valid
            if next_result.fixed_data:
                result.fixed_data = next_result.fixed_data
        
        return result
    
    @abstractmethod
    def _validate_impl(self, config_data: Dict[str, Any]) -> ValidationResult:
        """具体验证实现"""
        pass


class EnvVarValidator(ConfigValidator):
    """环境变量验证器"""
    
    def _validate_impl(self, config_data: Dict[str, Any]) -> ValidationResult:
        """验证环境变量占位符"""
        errors = []
        warnings = []
        fixed_data = None
        
        # 检查是否有未替换的环境变量占位符
        unresolved_vars = self._find_unresolved_vars(config_data)
        
        if unresolved_vars:
            for var_path, var_name in unresolved_vars:
                errors.append(f"未解析的环境变量: {var_name} (位置: {var_path})")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            fixed_data=fixed_data
        )
    
    def _find_unresolved_vars(self, data: Any, path: str = "") -> List[tuple]:
        """查找未解析的环境变量"""
        unresolved = []
        
        if isinstance(data, dict):
            for key, value in data.items():
                current_path = f"{path}.{key}" if path else key
                unresolved.extend(self._find_unresolved_vars(value, current_path))
        elif isinstance(data, list):
            for i, item in enumerate(data):
                current_path = f"{path}[{i}]"
                unresolved.extend(self._find_unresolved_vars(item, current_path))
        elif isinstance(data, str) and data.startswith('${') and data.endswith('}'):
            var_name = data[2:-1]
            unresolved.append((path, var_name))
        
        return unresolved


class URLValidator(ConfigValidator):
    """URL验证器"""
    
    def _validate_impl(self, config_data: Dict[str, Any]) -> ValidationResult:
        """验证URL格式"""
        errors = []
        warnings = []
        fixed_data = None
        
        # 验证后端API URL
        backend_api = config_data.get('backend_api', {})
        url = backend_api.get('url', '')
        
        if url and not url.startswith(('http://', 'https://')):
            errors.append(f"无效的后端API URL格式: {url}")
        elif url and 'localhost' in url:
            warnings.append("后端API URL指向localhost，可能在生产环境中无法访问")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            fixed_data=fixed_data
        )


class RequiredFieldValidator(ConfigValidator):
    """必需字段验证器"""
    
    def __init__(self):
        super().__init__()
        self.required_fields = {
            'backend_api.url': '后端API URL',
            'storage.encryption_key': '加密密钥',
            'system.max_concurrent': '最大并发数'
        }
    
    def _validate_impl(self, config_data: Dict[str, Any]) -> ValidationResult:
        """验证必需字段"""
        errors = []
        warnings = []
        
        for field_path, field_desc in self.required_fields.items():
            if not self._get_nested_value(config_data, field_path):
                errors.append(f"缺少必需字段: {field_desc} ({field_path})")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """获取嵌套字段值"""
        keys = path.split('.')
        current = data
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        
        return current


class ConfigValidationChain:
    """配置验证链管理器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.chain = self._build_validation_chain()
    
    def _build_validation_chain(self) -> ConfigValidator:
        """构建验证链"""
        env_validator = EnvVarValidator()
        url_validator = URLValidator()
        required_validator = RequiredFieldValidator()
        
        # 构建链：环境变量 → 必需字段 → URL格式
        env_validator.set_next(required_validator).set_next(url_validator)
        
        return env_validator
    
    def validate(self, config_data: Dict[str, Any]) -> ValidationResult:
        """执行完整验证"""
        self.logger.debug("开始配置验证链处理")
        
        result = self.chain.validate(config_data)
        
        # 记录验证结果
        if result.errors:
            for error in result.errors:
                self.logger.error(f"配置验证错误: {error}")
        
        if result.warnings:
            for warning in result.warnings:
                self.logger.warning(f"配置验证警告: {warning}")
        
        self.logger.debug(f"配置验证完成: {'通过' if result.is_valid else '失败'}")
        
        return result
