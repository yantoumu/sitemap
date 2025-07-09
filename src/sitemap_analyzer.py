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

        try:
            # 加载配置
            self.config_loader = ConfigLoader(config_path, rules_path)
            self.config = self.config_loader.load_system_config()
            self.url_rules = self.config_loader.load_url_rules()
        except FileNotFoundError as e:
            self.logger.error(f"配置文件加载失败: {e}")
            self.logger.info("尝试使用默认配置...")
            # 如果配置文件不存在，尝试使用默认路径
            try:
                default_config_path = config_path.replace('system_config.yaml', 'config.yaml')
                self.config_loader = ConfigLoader(default_config_path, rules_path)
                self.config = self.config_loader.load_system_config()
                self.url_rules = self.config_loader.load_url_rules()
                self.logger.info(f"成功使用默认配置: {default_config_path}")
            except Exception as fallback_error:
                self.logger.error(f"默认配置也加载失败: {fallback_error}")
                raise
        except Exception as e:
            self.logger.error(f"配置加载异常: {e}")
            raise
        
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
        主处理流程 - 增强错误处理和数据验证

        Args:
            sitemap_urls: sitemap URL列表

        Returns:
            Dict[str, Any]: 处理结果统计
        """
        with TimingLogger(self.logger, "sitemap处理"):
            try:
                # 输入验证
                if not sitemap_urls:
                    self.logger.warning("没有提供sitemap URL")
                    return self._create_result_summary(0, 0, 0, 0)

                # 1. 清理过期数据
                try:
                    expired_count = self.storage.clean_expired_data()
                    self.logger.info(f"清理过期数据: {expired_count} 条")
                except Exception as e:
                    self.logger.error(f"清理过期数据失败: {e}")
                    expired_count = 0

                # 2. 解析所有sitemap
                all_urls = await self._parse_all_sitemaps(sitemap_urls)
                self.logger.info(f"共解析到 {len(all_urls)} 个URL")

                if not all_urls:
                    self.logger.warning("没有从sitemap中解析到任何URL")
                    return self._create_result_summary(0, 0, 0, 0)

                # 3. 过滤已处理的URL
                try:
                    new_urls = self.url_processor.filter_processed_urls(all_urls, self.storage)
                    self.logger.info(f"发现 {len(new_urls)} 个新URL待处理")
                except Exception as e:
                    self.logger.error(f"过滤URL失败: {e}")
                    # 如果过滤失败，使用所有URL
                    new_urls = list(all_urls)
                    self.logger.info(f"使用所有URL进行处理: {len(new_urls)} 个")

                if not new_urls:
                    self.logger.info("没有新URL需要处理")
                    return self._create_result_summary(len(all_urls), 0, 0, 0)

                # 4. 提取关键词
                try:
                    url_keywords_map = self.url_processor.extract_all_keywords(new_urls)

                    # 验证提取结果
                    if not isinstance(url_keywords_map, dict):
                        self.logger.error(f"关键词提取返回类型错误: {type(url_keywords_map)}")
                        return self._create_result_summary(len(all_urls), len(new_urls), 0, 0)

                    if not url_keywords_map:
                        self.logger.warning("没有提取到任何关键词")
                        return self._create_result_summary(len(all_urls), len(new_urls), 0, 0)

                    self.logger.info(f"成功提取关键词: {len(url_keywords_map)} 个URL")

                except Exception as e:
                    self.logger.error(f"关键词提取失败: {e}")
                    import traceback
                    self.logger.error(f"详细错误: {traceback.format_exc()}")
                    return self._create_result_summary(len(all_urls), len(new_urls), 0, 0)

                # 5. 处理关键词数据
                try:
                    data_result = await self.data_processor.process_keywords_data(url_keywords_map)

                    # 验证处理结果
                    if not isinstance(data_result, dict):
                        self.logger.error(f"数据处理返回类型错误: {type(data_result)}")
                        data_result = {'saved_urls': 0, 'submitted_records': 0}

                except Exception as e:
                    self.logger.error(f"关键词数据处理失败: {e}")
                    import traceback
                    self.logger.error(f"详细错误: {traceback.format_exc()}")
                    data_result = {'saved_urls': 0, 'submitted_records': 0}

                return self._create_result_summary(
                    len(all_urls), len(new_urls),
                    data_result.get('saved_urls', 0),
                    data_result.get('submitted_records', 0)
                )

            except Exception as e:
                self.logger.error(f"sitemap处理过程中发生严重错误: {e}")
                import traceback
                self.logger.error(f"完整错误堆栈: {traceback.format_exc()}")
                return self._create_result_summary(0, 0, 0, 0)
    
    async def _parse_all_sitemaps(self, sitemap_urls: List[str]) -> Set[str]:
        """
        解析所有sitemap - 增强并发控制和错误处理

        Args:
            sitemap_urls: sitemap URL列表

        Returns:
            Set[str]: 解析出的URL集合
        """
        all_urls = set()

        # 获取并发限制配置
        max_concurrent = getattr(self.config.system, 'max_concurrent', 10)

        async with aiohttp.ClientSession() as session:
            parser = SitemapParser(session, max_depth=5)

            # 使用信号量控制并发数量
            semaphore = asyncio.Semaphore(max_concurrent)

            async def parse_with_semaphore(sitemap_url: str) -> Set[str]:
                """带并发控制的解析函数"""
                async with semaphore:
                    try:
                        return await parser.parse_sitemap(sitemap_url)
                    except Exception as e:
                        self.logger.error(f"Sitemap解析失败 {sitemap_url}: {e}")
                        return set()

            # 创建并发任务
            tasks = [parse_with_semaphore(url) for url in sitemap_urls]

            # 执行任务
            progress = ProgressLogger(self.logger, len(tasks), 1)

            try:
                results = await asyncio.gather(*tasks, return_exceptions=True)

                successful_count = 0
                error_count = 0

                for i, result in enumerate(results):
                    progress.update()
                    if isinstance(result, Exception):
                        self.logger.error(f"Sitemap解析异常: {result}")
                        error_count += 1
                    elif isinstance(result, set):
                        all_urls.update(result)
                        successful_count += 1
                    else:
                        self.logger.warning(f"意外的结果类型: {type(result)}")
                        error_count += 1

                progress.finish()

                # 记录统计信息
                self.logger.info(f"Sitemap解析完成: 成功 {successful_count}/{len(sitemap_urls)}, 失败 {error_count}")

                if error_count > 0 and successful_count == 0:
                    self.logger.warning("所有sitemap解析都失败了，请检查网络连接和URL有效性")

            except Exception as e:
                self.logger.error(f"批量sitemap解析失败: {e}")
                # 即使出现异常，也要完成进度记录
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
