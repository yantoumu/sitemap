"""
关键词处理器模块
负责关键词的标准化、清理和过滤
"""

import re
from typing import Set, List
import logging


class KeywordProcessor:
    """关键词处理器 - 负责关键词的标准化和过滤"""
    
    def __init__(self):
        """初始化关键词处理器"""
        self.logger = logging.getLogger(__name__)
        
        # 默认停用词
        self.default_stop_words = {
            # 英文停用词
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these',
            'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him',
            'her', 'us', 'them', 'my', 'your', 'his', 'its', 'our', 'their',
            
            # 网站常见词
            'www', 'com', 'net', 'org', 'html', 'htm', 'php', 'asp', 'aspx',
            'jsp', 'index', 'home', 'page', 'main', 'default', 'admin',
            
            # 中文停用词
            '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一',
            '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有',
            '看', '好', '自己', '这', '那', '里', '就是', '还是'
        }
    
    def normalize_keywords(self, keywords: Set[str]) -> Set[str]:
        """
        标准化关键词集合
        
        Args:
            keywords: 原始关键词集合
            
        Returns:
            Set[str]: 标准化后的关键词集合
        """
        normalized = set()
        
        for keyword in keywords:
            normalized_keyword = self.normalize_keyword(keyword)
            if normalized_keyword:
                normalized.add(normalized_keyword)
        
        return normalized
    
    def normalize_keyword(self, keyword: str) -> str:
        """
        标准化单个关键词
        
        Args:
            keyword: 原始关键词
            
        Returns:
            str: 标准化后的关键词
        """
        if not keyword:
            return ""
        
        # 转小写
        keyword = keyword.lower()
        
        # 去除首尾空白
        keyword = keyword.strip()
        
        # 验证长度（1-50字符）
        if len(keyword) < 1 or len(keyword) > 50:
            return ""
        
        # 注释掉数字过滤 - 根据需求应该保留数字
        # if keyword.isdigit():
        #     return ""
        
        return keyword
    
    def filter_keywords(self, keywords: Set[str], custom_stop_words: List[str]) -> Set[str]:
        """
        过滤停用词
        
        Args:
            keywords: 关键词集合
            custom_stop_words: 自定义停用词列表
            
        Returns:
            Set[str]: 过滤后的关键词集合
        """
        # 合并停用词
        all_stop_words = self.default_stop_words.copy()
        all_stop_words.update(word.lower() for word in custom_stop_words)
        
        # 过滤停用词
        filtered = {kw for kw in keywords if kw.lower() not in all_stop_words}
        
        return filtered
    
    def clean_keyword(self, keyword: str, clean_regex: str = None) -> str:
        """
        清理关键词
        
        Args:
            keyword: 原始关键词
            clean_regex: 清理正则表达式
            
        Returns:
            str: 清理后的关键词
        """
        if not keyword:
            return ""
        
        # 应用自定义清理规则
        if clean_regex:
            try:
                keyword = re.sub(clean_regex, "", keyword)
            except re.error as e:
                self.logger.error(f"清理正则表达式错误 {clean_regex}: {e}")
        
        # 默认清理：移除特殊字符，保留字母、数字、中文
        keyword = re.sub(r'[^\w\u4e00-\u9fa5]', '', keyword)
        
        return keyword.strip()
    
    def split_segment(self, segment: str, split_chars: str = "-_", clean_regex: str = None) -> Set[str]:
        """
        分割URL段为关键词 - 保持空格分割格式

        Args:
            segment: URL段
            split_chars: 分割字符
            clean_regex: 清理正则表达式

        Returns:
            Set[str]: 关键词集合
        """
        keywords = set()

        if not segment:
            return keywords

        # 将分隔符替换为空格，保持分割格式
        split_chars = split_chars or "-_"

        # 替换分隔符为空格
        processed_segment = re.sub(f'[{re.escape(split_chars)}]+', ' ', segment)

        # 应用清理规则
        if clean_regex:
            try:
                processed_segment = re.sub(clean_regex, "", processed_segment)
            except re.error as e:
                self.logger.error(f"清理正则表达式错误 {clean_regex}: {e}")

        # 默认清理：移除特殊字符，保留字母、数字、中文和空格
        processed_segment = re.sub(r'[^\w\u4e00-\u9fa5\s]', '', processed_segment)

        # 标准化空格并转小写
        processed_segment = re.sub(r'\s+', ' ', processed_segment).strip().lower()

        # 验证并添加关键词（保持空格分割格式）
        if processed_segment and len(processed_segment) <= 50:
            keywords.add(processed_segment)

        return keywords
    
    def add_stop_words(self, stop_words: List[str]) -> None:
        """
        添加全局停用词
        
        Args:
            stop_words: 停用词列表
        """
        self.default_stop_words.update(word.lower() for word in stop_words)
        self.logger.info(f"添加 {len(stop_words)} 个停用词")
    
    def get_stop_words_count(self) -> int:
        """
        获取停用词数量
        
        Returns:
            int: 停用词数量
        """
        return len(self.default_stop_words)

    def format_keywords_for_output(self, keywords: Set[str], format_type: str = "space") -> str:
        """
        格式化关键词用于输出

        Args:
            keywords: 关键词集合
            format_type: 格式类型，"space" 为空格分隔，"comma" 为逗号分隔

        Returns:
            str: 格式化后的关键词字符串
        """
        if not keywords:
            return ""

        sorted_keywords = sorted(keywords)

        if format_type == "space":
            return ' '.join(sorted_keywords)
        elif format_type == "comma":
            return ', '.join(sorted_keywords)
        else:
            # 默认使用空格分隔
            return ' '.join(sorted_keywords)

    def validate_keyword(self, keyword: str) -> bool:
        """
        验证关键词是否有效
        
        Args:
            keyword: 关键词
            
        Returns:
            bool: 是否有效
        """
        if not keyword or not isinstance(keyword, str):
            return False
        
        # 长度检查
        if len(keyword.strip()) < 1 or len(keyword.strip()) > 50:
            return False
        
        # 注释掉数字过滤 - 根据需求应该保留数字
        # if keyword.strip().isdigit():
        #     return False
        
        # 不能全为特殊字符
        if re.match(r'^[^\w\u4e00-\u9fa5]+$', keyword.strip()):
            return False
        
        return True
