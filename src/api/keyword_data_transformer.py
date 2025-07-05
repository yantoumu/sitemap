"""
关键词数据转换器
负责将查询API返回的数据转换为符合后端API接口规范的格式
"""

from typing import Dict, List, Any, Optional, Set
import logging
from datetime import datetime


class KeywordDataTransformer:
    """关键词数据转换器 - 将查询API数据转换为提交API格式"""
    
    def __init__(self):
        """初始化转换器"""
        self.logger = logging.getLogger(__name__)
    
    def transform_query_response_to_submit_format(
        self, 
        query_response: Dict[str, Any], 
        url_keywords_map: Dict[str, Set[str]]
    ) -> List[Dict[str, Any]]:
        """
        将查询API响应转换为提交API格式
        
        Args:
            query_response: 查询API的响应数据
            url_keywords_map: URL到关键词集合的映射
            
        Returns:
            List[Dict[str, Any]]: 符合提交API格式的数据列表
        """
        if not query_response or 'data' not in query_response:
            self.logger.warning("查询响应数据为空或格式不正确")
            return []
        
        # 提取查询结果数据
        query_data = query_response['data']
        if not isinstance(query_data, list):
            self.logger.error("查询响应data字段不是列表格式")
            return []
        
        # 创建关键词到URL的反向映射
        keyword_to_urls = self._create_keyword_to_urls_mapping(url_keywords_map)
        
        submit_data = []
        
        for keyword_data in query_data:
            if not self._validate_keyword_data(keyword_data):
                continue
            
            keyword = keyword_data['keyword']
            metrics = keyword_data['metrics']
            
            # 获取该关键词对应的URLs
            urls = keyword_to_urls.get(keyword, set())
            
            if not urls:
                self.logger.debug(f"关键词 '{keyword}' 没有对应的URL，跳过")
                continue
            
            # 为每个URL创建一条提交记录
            for url in urls:
                submit_record = self._create_submit_record(keyword, url, metrics)
                if submit_record:
                    submit_data.append(submit_record)
        
        self.logger.info(f"转换完成：{len(submit_data)} 条提交记录")
        return submit_data
    
    def _create_keyword_to_urls_mapping(self, url_keywords_map: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
        """
        创建关键词到URL的反向映射
        
        Args:
            url_keywords_map: URL到关键词集合的映射
            
        Returns:
            Dict[str, Set[str]]: 关键词到URL集合的映射
        """
        keyword_to_urls = {}
        
        for url, keywords in url_keywords_map.items():
            for keyword in keywords:
                if keyword not in keyword_to_urls:
                    keyword_to_urls[keyword] = set()
                keyword_to_urls[keyword].add(url)
        
        return keyword_to_urls
    
    def _validate_keyword_data(self, keyword_data: Dict[str, Any]) -> bool:
        """
        验证关键词数据格式
        
        Args:
            keyword_data: 关键词数据
            
        Returns:
            bool: 数据是否有效
        """
        if not isinstance(keyword_data, dict):
            return False
        
        if 'keyword' not in keyword_data or 'metrics' not in keyword_data:
            self.logger.warning(f"关键词数据缺少必要字段: {keyword_data}")
            return False
        
        metrics = keyword_data['metrics']
        if not isinstance(metrics, dict):
            self.logger.warning(f"metrics字段不是字典格式: {keyword_data}")
            return False
        
        # 检查核心必要字段
        core_required_fields = ['avg_monthly_searches']

        for field in core_required_fields:
            if field not in metrics:
                self.logger.warning(f"metrics缺少核心字段 '{field}': {keyword_data['keyword']}")
                return False
        
        return True
    
    def _create_submit_record(self, keyword: str, url: str, metrics: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        创建单条提交记录
        
        Args:
            keyword: 关键词
            url: 对应的URL
            metrics: 指标数据
            
        Returns:
            Optional[Dict[str, Any]]: 提交记录，失败返回None
        """
        try:
            # 处理出价字段的null值
            low_bid = metrics.get('low_top_of_page_bid_micro')
            high_bid = metrics.get('high_top_of_page_bid_micro')
            
            # null值转换为0
            low_bid = low_bid if low_bid is not None else 0
            high_bid = high_bid if high_bid is not None else 0
            
            # 构建符合API文档的记录格式，使用默认值处理缺失字段
            submit_record = {
                "keyword": keyword,
                "url": url,
                "metrics": {
                    "avg_monthly_searches": metrics.get('avg_monthly_searches', 0),
                    "latest_searches": metrics.get('latest_searches', metrics.get('avg_monthly_searches', 0)),
                    "max_monthly_searches": metrics.get('max_monthly_searches', metrics.get('avg_monthly_searches', 0)),
                    "competition": metrics.get('competition', 'UNKNOWN'),
                    "competition_index": metrics.get('competition_index', 0),
                    "low_top_of_page_bid_micro": low_bid,
                    "high_top_of_page_bid_micro": high_bid,
                    "monthly_searches": self._transform_monthly_searches(metrics.get('monthly_searches', [])),
                    "data_quality": metrics.get('data_quality', {
                        "status": "unknown",
                        "complete": False,
                        "has_missing_months": True,
                        "only_last_month_has_data": False,
                        "total_months": 0,
                        "available_months": 0,
                        "missing_months_count": 0,
                        "missing_months": [],
                        "warnings": ["数据不完整"]
                    })
                }
            }
            
            return submit_record
            
        except Exception as e:
            self.logger.error(f"创建提交记录失败 - 关键词: {keyword}, URL: {url}, 错误: {e}")
            return None
    
    def _transform_monthly_searches(self, monthly_searches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        转换月度搜索数据格式
        
        Args:
            monthly_searches: 原始月度搜索数据
            
        Returns:
            List[Dict[str, Any]]: 转换后的月度搜索数据
        """
        if not isinstance(monthly_searches, list):
            return []
        
        transformed = []
        for item in monthly_searches:
            if isinstance(item, dict) and all(k in item for k in ['year', 'month', 'searches']):
                # 确保年月字段支持字符串和数字格式（API文档要求）
                transformed_item = {
                    "year": str(item['year']),  # 转换为字符串格式
                    "month": str(item['month']),  # 转换为字符串格式
                    "searches": item['searches']
                }
                transformed.append(transformed_item)
        
        return transformed
    
    def get_transformation_stats(self, submit_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        获取转换统计信息
        
        Args:
            submit_data: 转换后的提交数据
            
        Returns:
            Dict[str, Any]: 统计信息
        """
        if not submit_data:
            return {
                'total_records': 0,
                'unique_keywords': 0,
                'unique_urls': 0,
                'avg_records_per_keyword': 0
            }
        
        keywords = set()
        urls = set()
        
        for record in submit_data:
            keywords.add(record['keyword'])
            urls.add(record['url'])
        
        return {
            'total_records': len(submit_data),
            'unique_keywords': len(keywords),
            'unique_urls': len(urls),
            'avg_records_per_keyword': len(submit_data) / len(keywords) if keywords else 0
        }
