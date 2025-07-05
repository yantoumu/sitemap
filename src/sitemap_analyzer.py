"""
网站地图关键词分析器
主要的业务逻辑处理类
"""

import asyncio
import aiohttp
from pathlib import Path
from typing import List, Set, Dict, Any
from datetime import datetime
import logging

from .config import ConfigLoader, AppConfig
from .parsers import SitemapParser
from .extractors import RuleEngine, KeywordExtractor
from .api import SEOAPIManager, BackendAPIClient
from .storage import StorageManager
from .data_processor import DataProcessor, URLProcessor
from .utils import get_logger, ProgressLogger, TimingLogger


class SitemapKeywordAnalyzer:
    """网站地图关键词分析器"""
    
    def __init__(self, config_path: str, rules_path: str):
        """
        初始化分析器
        
        Args:
            config_path: 系统配置文件路径
            rules_path: URL规则配置文件路径
        """
        self.logger = get_logger(__name__)
        
        # 加载配置
        self.config_loader = ConfigLoader(config_path, rules_path)
        self.config = self.config_loader.load_system_config()
        self.url_rules = self.config_loader.load_url_rules()
        
        # 初始化组件
        self._initialize_components()
        
        self.logger.info("网站地图关键词分析器初始化完成")
    
    def _initialize_components(self) -> None:
        """初始化各个组件"""
        # 规则引擎
        self.rule_engine = RuleEngine(self.url_rules)
        
        # 关键词提取器
        self.keyword_extractor = KeywordExtractor()
        
        # SEO API管理器
        self.seo_api = SEOAPIManager(
            self.config.seo_api.urls,
            self.config.seo_api.interval,
            self.config.seo_api.batch_size,
            self.config.seo_api.timeout
        )
        
        # 后端API客户端
        self.backend_api = BackendAPIClient(
            self.config.backend_api.url,
            self.config.backend_api.auth_token,
            self.config.backend_api.batch_size,
            timeout=self.config.backend_api.timeout
        )
        
        # 存储管理器
        self.storage = StorageManager(
            self.config.storage.encryption_key,
            self.config.storage.storage_file,
            self.config.storage.data_retention_days
        )

        # 数据处理器
        self.data_processor = DataProcessor(
            self.seo_api, self.backend_api, self.storage
        )

        # URL处理器
        self.url_processor = URLProcessor(
            self.rule_engine, self.keyword_extractor
        )
    
    async def process_sitemaps(self, sitemap_urls: List[str]) -> Dict[str, Any]:
        """
        主处理流程
        
        Args:
            sitemap_urls: sitemap URL列表
            
        Returns:
            Dict[str, Any]: 处理结果统计
        """
        with TimingLogger(self.logger, "sitemap处理"):
            # 1. 清理过期数据
            expired_count = self.storage.clean_expired_data()
            self.logger.info(f"清理过期数据: {expired_count} 条")
            
            # 2. 解析所有sitemap
            all_urls = await self._parse_all_sitemaps(sitemap_urls)
            self.logger.info(f"共解析到 {len(all_urls)} 个URL")
            
            # 3. 过滤已处理的URL
            new_urls = self.url_processor.filter_processed_urls(all_urls, self.storage)
            self.logger.info(f"发现 {len(new_urls)} 个新URL待处理")

            if not new_urls:
                self.logger.info("没有新URL需要处理")
                return self._create_result_summary(0, 0, 0, 0)

            # 4. 提取关键词
            url_keywords_map = self.url_processor.extract_all_keywords(new_urls)

            # 5. 处理关键词数据
            data_result = await self.data_processor.process_keywords_data(url_keywords_map)

            return self._create_result_summary(
                len(all_urls), len(new_urls),
                data_result['saved_urls'], data_result['submitted_records']
            )
    
    async def _parse_all_sitemaps(self, sitemap_urls: List[str]) -> Set[str]:
        """
        解析所有sitemap
        
        Args:
            sitemap_urls: sitemap URL列表
            
        Returns:
            Set[str]: 解析出的URL集合
        """
        all_urls = set()
        
        async with aiohttp.ClientSession() as session:
            parser = SitemapParser(session, max_depth=5)
            
            # 创建并发任务
            tasks = []
            for sitemap_url in sitemap_urls:
                task = parser.parse_sitemap(sitemap_url)
                tasks.append(task)
            
            # 执行任务
            progress = ProgressLogger(self.logger, len(tasks), 1)
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, result in enumerate(results):
                progress.update()
                if isinstance(result, Exception):
                    self.logger.error(f"Sitemap解析错误: {result}")
                else:
                    all_urls.update(result)
            
            progress.finish()
        
        return all_urls
    

    
    def _create_result_summary(self, total_urls: int, new_urls: int, 
                              saved_urls: int, submitted_records: int) -> Dict[str, Any]:
        """
        创建结果摘要
        
        Args:
            total_urls: 总URL数
            new_urls: 新URL数
            saved_urls: 保存的URL数
            submitted_records: 提交的记录数
            
        Returns:
            Dict[str, Any]: 结果摘要
        """
        return {
            'total_urls_found': total_urls,
            'new_urls_processed': new_urls,
            'urls_saved': saved_urls,
            'records_submitted': submitted_records,
            'processing_time': datetime.now().isoformat(),
            **self.data_processor.get_statistics()
        }
    
    async def health_check(self) -> Dict[str, bool]:
        """
        健康检查

        Returns:
            Dict[str, bool]: 各组件健康状态
        """
        # 获取数据处理器的健康状态
        health_status = await self.data_processor.health_check()

        # 检查配置
        health_status['config'] = self.config_loader.validate_config_files()

        return health_status
