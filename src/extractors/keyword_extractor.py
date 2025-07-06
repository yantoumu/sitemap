"""
关键词提取器模块
从URL中根据规则提取关键词，支持多种提取方式
"""

import re
from typing import Set, List
from urllib.parse import urlparse, parse_qs, unquote
import logging

from ..config.schemas import URLExtractionRule, ExtractRule
from ..utils.log_security import LogSecurity
from .keyword_processor import KeywordProcessor


class KeywordExtractor:
    """关键词提取器 - 负责从URL中提取关键词"""

    def __init__(self):
        """初始化关键词提取器"""
        self.logger = logging.getLogger(__name__)
        self.processor = KeywordProcessor()
    
    def extract_keywords(self, url: str, rule: URLExtractionRule) -> Set[str]:
        """
        根据规则从URL提取关键词
        
        Args:
            url: 待提取的URL
            rule: 提取规则
            
        Returns:
            Set[str]: 提取的关键词集合
        """
        keywords = set()
        
        try:
            for extract_rule in rule.extract_rules:
                if extract_rule.type == "path_segment":
                    keywords.update(self._extract_from_path(url, extract_rule))
                elif extract_rule.type == "query_param":
                    keywords.update(self._extract_from_query(url, extract_rule))
                elif extract_rule.type == "custom_regex":
                    keywords.update(self._extract_with_regex(url, extract_rule))
            
            # 标准化关键词
            keywords = self.processor.normalize_keywords(keywords)

            # 过滤停用词
            keywords = self.processor.filter_keywords(keywords, rule.stop_words)
            
            # 减少冗余DEBUG日志 - 只在提取到关键词时记录
            if keywords and len(keywords) > 0:
                self.logger.debug(f"从URL提取 {len(keywords)} 个关键词: {LogSecurity.sanitize_url(url)}")
            return keywords
            
        except Exception as e:
            self.logger.error(f"关键词提取失败 {LogSecurity.sanitize_url(url)}: {e}")
            return set()
    
    def _extract_from_path(self, url: str, rule: ExtractRule) -> Set[str]:
        """
        从URL路径提取关键词 - 使用智能提取逻辑

        Args:
            url: URL
            rule: 提取规则

        Returns:
            Set[str]: 关键词集合
        """
        keywords = set()

        try:
            parsed_url = urlparse(url)
            path = parsed_url.path.strip('/')

            if not path:
                return keywords

            # 分割路径段
            path_segments = [segment for segment in path.split('/') if segment]

            if not path_segments:
                return keywords

            # 智能过滤有意义的路径段
            meaningful_segments = self._filter_meaningful_segments(path_segments, parsed_url.netloc)

            # 根据位置提取
            position = rule.position
            if position is not None:
                if position < 0:
                    # 负数表示从末尾开始
                    if abs(position) <= len(meaningful_segments):
                        segment = meaningful_segments[position]
                        keywords.update(self._split_segment(segment, rule))
                else:
                    # 正数表示从开头开始（从0开始）
                    if position < len(meaningful_segments):
                        segment = meaningful_segments[position]
                        keywords.update(self._split_segment(segment, rule))
            else:
                # 如果没有指定位置，提取所有有意义的段并组合
                if meaningful_segments:
                    # 将所有有意义的段组合为一个关键词
                    combined_segments = []
                    for segment in meaningful_segments:
                        # 将分隔符替换为空格
                        processed_segment = re.sub(r'[-_]+', ' ', segment)
                        # 清理特殊字符
                        processed_segment = re.sub(r'[^\w\u4e00-\u9fa5\s]', '', processed_segment)
                        # 标准化空格
                        processed_segment = re.sub(r'\s+', ' ', processed_segment).strip().lower()
                        if processed_segment:
                            combined_segments.append(processed_segment)

                    if combined_segments:
                        combined_keyword = ' '.join(combined_segments)
                        if len(combined_keyword) <= 50:
                            keywords.add(combined_keyword)

        except Exception as e:
            self.logger.error(f"路径提取失败 {LogSecurity.sanitize_url(url)}: {e}")

        return keywords
    
    def _extract_from_query(self, url: str, rule: ExtractRule) -> Set[str]:
        """
        从URL查询参数提取关键词
        
        Args:
            url: URL
            rule: 提取规则
            
        Returns:
            Set[str]: 关键词集合
        """
        keywords = set()
        
        try:
            parsed_url = urlparse(url)
            query_params = parse_qs(parsed_url.query)
            
            param_name = rule.param_name
            if param_name and param_name in query_params:
                values = query_params[param_name]
                for value in values:
                    # URL解码
                    decoded_value = unquote(value)
                    keywords.update(self._split_segment(decoded_value, rule))
            
        except Exception as e:
            self.logger.error(f"查询参数提取失败 {LogSecurity.sanitize_url(url)}: {e}")
        
        return keywords
    
    def _extract_with_regex(self, url: str, rule: ExtractRule) -> Set[str]:
        """
        使用自定义正则表达式提取关键词
        
        Args:
            url: URL
            rule: 提取规则
            
        Returns:
            Set[str]: 关键词集合
        """
        keywords = set()
        
        try:
            if not rule.regex:
                return keywords
            
            pattern = re.compile(rule.regex)
            matches = pattern.findall(url)
            
            for match in matches:
                if isinstance(match, tuple):
                    # 如果有多个捕获组，取第一个
                    match = match[0] if match else ""
                
                if match:
                    keywords.update(self._split_segment(match, rule))
            
        except re.error as e:
            self.logger.error(f"正则表达式错误 {rule.regex}: {e}")
        except Exception as e:
            self.logger.error(f"正则提取失败 {LogSecurity.sanitize_url(url)}: {e}")
        
        return keywords
    
    def _split_segment(self, segment: str, rule: ExtractRule) -> Set[str]:
        """
        分割URL段为关键词

        Args:
            segment: URL段
            rule: 提取规则

        Returns:
            Set[str]: 关键词集合
        """
        if not segment:
            return set()

        # URL解码
        segment = unquote(segment)

        # 使用处理器分割段
        return self.processor.split_segment(
            segment,
            rule.split_chars or "-_",
            rule.clean_regex
        )

    def _filter_meaningful_segments(self, path_segments: List[str], domain: str) -> List[str]:
        """
        过滤出有意义的路径段 - 优化版本，减少过度过滤

        Args:
            path_segments: 路径段列表
            domain: 域名

        Returns:
            List[str]: 有意义的路径段列表
        """
        # 严格的干扰词（技术性词汇）
        strict_stop_words = {
            'www', 'index', 'home', 'main', 'default',
            'admin', 'api', 'v1', 'v2', 'v3', 'css', 'js',
            'images', 'img', 'assets', 'static', 'uploads',
            'sitemap', 'robots', 'feed', 'rss'
        }

        # 语言代码
        language_codes = {
            'en', 'es', 'fr', 'de', 'it', 'pt', 'ru', 'zh', 'ja', 'ko',
            'ar', 'hi', 'tr', 'pl', 'nl', 'sv', 'da', 'no', 'fi'
        }

        meaningful_segments = []
        for segment in path_segments:
            segment_lower = segment.lower()

            # 跳过严格的干扰词
            if segment_lower in strict_stop_words:
                continue

            # 跳过语言代码（但只有当它们是单独的段时）
            if segment_lower in language_codes and len(segment) <= 3:
                continue

            # 跳过纯数字（但保留包含字母的数字组合）
            if segment.isdigit():
                continue

            # 跳过单字符（除非是中文）
            if len(segment) == 1 and not re.search(r'[\u4e00-\u9fa5]', segment):
                continue

            # 检查是否包含字母或中文字符
            if re.search(r'[a-zA-Z\u4e00-\u9fa5]', segment):
                meaningful_segments.append(segment)

        return meaningful_segments

    def add_stop_words(self, stop_words: List[str]) -> None:
        """
        添加全局停用词

        Args:
            stop_words: 停用词列表
        """
        self.processor.add_stop_words(stop_words)

    def get_stop_words_count(self) -> int:
        """
        获取停用词数量

        Returns:
            int: 停用词数量
        """
        return self.processor.get_stop_words_count()
