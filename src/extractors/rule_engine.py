"""
规则引擎模块
负责域名匹配、URL模式匹配和规则应用
"""

import re
from typing import Optional, List, Dict, Pattern
from urllib.parse import urlparse
import logging

from ..config.schemas import URLExtractionRule, ExtractRule
from ..utils.log_security import LogSecurity


class RuleEngine:
    """URL规则引擎 - 支持分层规则策略"""

    def __init__(self, rules: Dict[str, URLExtractionRule]):
        """
        初始化规则引擎

        Args:
            rules: 域名到规则的映射字典
        """
        self.rules = rules
        self.compiled_patterns = self._compile_patterns()
        self.default_rule = self._create_default_rule()
        self.logger = logging.getLogger(__name__)

        self.logger.info(f"规则引擎初始化完成，加载 {len(rules)} 个特定域名规则，已创建通用默认规则")
    
    def _compile_patterns(self) -> Dict[str, Dict[str, List[Pattern]]]:
        """
        预编译所有正则表达式模式，提升匹配性能
        
        Returns:
            Dict[str, Dict[str, List[Pattern]]]: 编译后的模式字典
            格式: {domain: {'patterns': [Pattern], 'exclude_patterns': [Pattern]}}
        """
        compiled = {}
        
        for domain, rule in self.rules.items():
            domain_patterns = {
                'patterns': [],
                'exclude_patterns': []
            }
            
            # 编译匹配模式
            for pattern in rule.patterns:
                try:
                    compiled_pattern = re.compile(pattern)
                    domain_patterns['patterns'].append(compiled_pattern)
                except re.error as e:
                    self.logger.error(f"编译匹配模式失败 {domain} - {pattern}: {e}")
            
            # 编译排除模式
            for pattern in rule.exclude_patterns:
                try:
                    compiled_pattern = re.compile(pattern)
                    domain_patterns['exclude_patterns'].append(compiled_pattern)
                except re.error as e:
                    self.logger.error(f"编译排除模式失败 {domain} - {pattern}: {e}")
            
            compiled[domain] = domain_patterns
        
        return compiled

    def _create_default_rule(self) -> URLExtractionRule:
        """
        创建通用默认规则

        Returns:
            URLExtractionRule: 默认规则对象
        """
        # 创建通用的关键词提取规则
        default_extract_rule = ExtractRule(
            type="path_segment",
            position=-1,  # 最后一个路径段
            split_chars="-_",
            clean_regex="[^a-zA-Z0-9 ]"  # 保留空格
        )

        # 通用停用词列表
        default_stop_words = [
            "www", "com", "org", "net", "io", "co", "uk", "de", "fr", "es", "it", "ru", "cn", "jp",
            "game", "games", "play", "online", "free", "html5", "flash", "mobile",
            "the", "and", "or", "in", "on", "at", "to", "for", "of", "with", "by",
            "home", "index", "main", "page", "site", "web", "app", "download", "install",
            "about", "contact", "help", "support", "faq", "terms", "privacy", "policy",
            "login", "register", "signup", "signin", "logout", "profile", "account",
            "search", "category", "tag", "archive", "blog", "news", "article"
        ]

        # 创建默认规则
        default_rule = URLExtractionRule(
            domain="*",  # 通配符表示默认规则
            description="通用默认关键词提取规则",
            patterns=["^/.*"],  # 匹配所有路径
            extract_rules=[default_extract_rule],
            exclude_patterns=[
                ".*/sitemap.*",
                ".*/robots.*",
                ".*/feed.*",
                ".*/rss.*",
                ".*/api/.*",
                ".*/admin/.*",
                ".*/wp-.*",
                ".*/css/.*",
                ".*/js/.*",
                ".*/images/.*",
                ".*/img/.*",
                ".*/assets/.*",
                ".*/static/.*",
                ".*/$",  # 排除以/结尾的目录页面
                ".*/page/[0-9]+.*",  # 排除分页
                ".*/category/.*",  # 排除分类页面
                ".*/tag/.*"  # 排除标签页面
            ],
            stop_words=default_stop_words
        )

        return default_rule

    def get_rule_for_url(self, url: str) -> URLExtractionRule:
        """
        根据URL获取对应的提取规则 - 分层规则策略

        优先级：
        1. 特定域名规则（精确匹配）
        2. 特定域名规则（去除www匹配）
        3. 特定域名规则（子域名匹配）
        4. 通用默认规则

        Args:
            url: 待匹配的URL

        Returns:
            URLExtractionRule: 匹配的规则，始终返回规则（最低返回默认规则）
        """
        try:
            # 解析URL获取域名
            parsed_url = urlparse(url)
            if not parsed_url.netloc:
                self.logger.debug(f"无效URL，使用默认规则: {LogSecurity.sanitize_url(url)}")
                return self.default_rule

            domain = parsed_url.netloc.lower()

            # 移除www前缀进行匹配
            domain_without_www = domain.replace('www.', '', 1)

            # 优先级1：尝试精确匹配域名
            rule = self._match_domain_exact(domain, url)
            if rule:
                self.logger.debug(f"使用特定域名规则 (精确匹配): {domain}")
                return rule

            # 优先级2：尝试匹配去除www的域名
            if domain != domain_without_www:
                rule = self._match_domain_exact(domain_without_www, url)
                if rule:
                    self.logger.debug(f"使用特定域名规则 (去除www匹配): {domain_without_www}")
                    return rule

            # 优先级3：尝试子域名匹配
            rule = self._match_domain_subdomain(domain, url)
            if rule:
                self.logger.debug(f"使用特定域名规则 (子域名匹配): {domain}")
                return rule

            # 优先级4：使用默认规则
            self.logger.debug(f"使用通用默认规则: {domain}")
            return self.default_rule

        except Exception as e:
            self.logger.error(f"获取URL规则失败，使用默认规则 {LogSecurity.sanitize_url(url)}: {e}")
            return self.default_rule
    
    def _match_domain_exact(self, domain: str, url: str) -> Optional[URLExtractionRule]:
        """
        精确匹配域名
        
        Args:
            domain: 域名
            url: 完整URL
            
        Returns:
            Optional[URLExtractionRule]: 匹配的规则
        """
        if domain in self.rules:
            rule = self.rules[domain]
            if self._validate_url_patterns(url, rule):
                return rule
        return None
    
    def _match_domain_subdomain(self, domain: str, url: str) -> Optional[URLExtractionRule]:
        """
        子域名匹配
        
        Args:
            domain: 域名
            url: 完整URL
            
        Returns:
            Optional[URLExtractionRule]: 匹配的规则
        """
        # 尝试匹配父域名
        domain_parts = domain.split('.')
        if len(domain_parts) > 2:
            parent_domain = '.'.join(domain_parts[1:])
            if parent_domain in self.rules:
                rule = self.rules[parent_domain]
                if self._validate_url_patterns(url, rule):
                    return rule
        
        return None
    
    def _validate_url_patterns(self, url: str, rule: URLExtractionRule) -> bool:
        """
        验证URL是否符合规则的模式要求
        
        Args:
            url: 待验证的URL
            rule: 提取规则
            
        Returns:
            bool: 是否匹配
        """
        parsed_url = urlparse(url)
        path = parsed_url.path
        domain = rule.domain
        
        # 检查是否匹配任一包含模式
        patterns = self.compiled_patterns.get(domain, {}).get('patterns', [])
        if patterns:
            pattern_matched = any(pattern.search(path) for pattern in patterns)
            if not pattern_matched:
                return False
        
        # 检查是否匹配任一排除模式
        exclude_patterns = self.compiled_patterns.get(domain, {}).get('exclude_patterns', [])
        if exclude_patterns:
            excluded = any(pattern.search(path) for pattern in exclude_patterns)
            if excluded:
                return False
        
        return True
    
    def get_matching_domains(self) -> List[str]:
        """
        获取所有配置的域名列表
        
        Returns:
            List[str]: 域名列表
        """
        return list(self.rules.keys())
    
    def get_rule_by_domain(self, domain: str) -> URLExtractionRule:
        """
        根据域名直接获取规则

        Args:
            domain: 域名

        Returns:
            URLExtractionRule: 规则对象，如果没有特定规则则返回默认规则
        """
        specific_rule = self.rules.get(domain.lower())
        return specific_rule if specific_rule else self.default_rule

    def get_default_rule(self) -> URLExtractionRule:
        """
        获取默认规则

        Returns:
            URLExtractionRule: 默认规则对象
        """
        return self.default_rule

    def has_specific_rule(self, domain: str) -> bool:
        """
        检查域名是否有特定规则

        Args:
            domain: 域名

        Returns:
            bool: 是否有特定规则
        """
        domain = domain.lower()
        domain_without_www = domain.replace('www.', '', 1)

        # 检查精确匹配
        if domain in self.rules:
            return True

        # 检查去除www匹配
        if domain != domain_without_www and domain_without_www in self.rules:
            return True

        # 检查子域名匹配
        domain_parts = domain.split('.')
        if len(domain_parts) > 2:
            parent_domain = '.'.join(domain_parts[1:])
            if parent_domain in self.rules:
                return True

        return False

    def validate_rule(self, rule: URLExtractionRule) -> bool:
        """
        验证规则的有效性
        
        Args:
            rule: 待验证的规则
            
        Returns:
            bool: 规则是否有效
        """
        try:
            # 验证模式是否可以编译
            for pattern in rule.patterns:
                re.compile(pattern)
            
            for pattern in rule.exclude_patterns:
                re.compile(pattern)
            
            # 验证提取规则
            for extract_rule in rule.extract_rules:
                if extract_rule.type == 'custom_regex' and extract_rule.regex:
                    re.compile(extract_rule.regex)
            
            return True
            
        except re.error as e:
            self.logger.error(f"规则验证失败 {rule.domain}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"规则验证异常 {rule.domain}: {e}")
            return False
    
    def add_rule(self, domain: str, rule: URLExtractionRule) -> bool:
        """
        动态添加规则
        
        Args:
            domain: 域名
            rule: 规则对象
            
        Returns:
            bool: 是否添加成功
        """
        if not self.validate_rule(rule):
            return False
        
        try:
            self.rules[domain.lower()] = rule
            
            # 重新编译该域名的模式
            domain_patterns = {
                'patterns': [],
                'exclude_patterns': []
            }
            
            for pattern in rule.patterns:
                domain_patterns['patterns'].append(re.compile(pattern))
            
            for pattern in rule.exclude_patterns:
                domain_patterns['exclude_patterns'].append(re.compile(pattern))
            
            self.compiled_patterns[domain.lower()] = domain_patterns
            
            self.logger.info(f"成功添加规则: {domain}")
            return True
            
        except Exception as e:
            self.logger.error(f"添加规则失败 {domain}: {e}")
            return False
    
    def remove_rule(self, domain: str) -> bool:
        """
        移除规则
        
        Args:
            domain: 域名
            
        Returns:
            bool: 是否移除成功
        """
        domain = domain.lower()
        
        if domain in self.rules:
            del self.rules[domain]
            
            if domain in self.compiled_patterns:
                del self.compiled_patterns[domain]
            
            self.logger.info(f"成功移除规则: {domain}")
            return True
        
        return False
    
    def get_statistics(self) -> Dict[str, int]:
        """
        获取规则引擎统计信息
        
        Returns:
            Dict[str, int]: 统计信息
        """
        total_patterns = 0
        total_exclude_patterns = 0
        total_extract_rules = 0
        
        for rule in self.rules.values():
            total_patterns += len(rule.patterns)
            total_exclude_patterns += len(rule.exclude_patterns)
            total_extract_rules += len(rule.extract_rules)
        
        return {
            'total_domains': len(self.rules),
            'total_patterns': total_patterns,
            'total_exclude_patterns': total_exclude_patterns,
            'total_extract_rules': total_extract_rules
        }
