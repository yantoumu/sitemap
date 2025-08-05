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
from .api import SEOAPIManager, BackendAPIClient, EnhancedSEOAPIManager
from .api.simplified_backend_client import SimplifiedBackendClient
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
        
        self.logger.debug("网站地图关键词分析器初始化完成")
    
    def _initialize_components(self) -> None:
        """初始化各个组件"""
        # 规则引擎
        self.rule_engine = RuleEngine(self.url_rules)
        
        # 关键词提取器
        self.keyword_extractor = KeywordExtractor()
        
        # SEO API管理器 - 注释掉，不再使用
        # self.seo_api = EnhancedSEOAPIManager(
        #     api_urls=self.config.seo_api.urls,
        #     interval=self.config.seo_api.interval,
        #     batch_size=self.config.seo_api.batch_size,
        #     timeout=self.config.seo_api.timeout,
        #     enable_incremental_save=True,  # 启用增量保存
        #     enable_fault_tolerance=True,   # 启用容错处理
        #     save_interval=500,             # 每500个关键词保存一次（更频繁）
        #     git_commit_interval=2000,      # 每2000个关键词提交Git（更频繁）
        #     max_runtime_hours=7.5          # 7.5小时超时限制（更宽松）
        # )
        
        # 使用简化的后端客户端
        self.simplified_backend = SimplifiedBackendClient()
        
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

        # 数据处理器 - 传入None作为seo_api参数
        self.data_processor = DataProcessor(
            None, self.backend_api, self.storage
        )
        # 设置简化的后端客户端
        self.data_processor.simplified_backend = self.simplified_backend

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

                # 3. 应用排除规则过滤
                try:
                    # 先过滤被排除的URL
                    filtered_urls = self.url_processor.filter_excluded_urls(all_urls)
                    self.logger.info(f"排除规则过滤后剩余 {len(filtered_urls)} 个URL")
                except Exception as e:
                    self.logger.error(f"应用排除规则失败: {e}")
                    filtered_urls = list(all_urls)
                
                # 4. 过滤已处理的URL
                try:
                    new_urls = self.url_processor.filter_processed_urls(set(filtered_urls), self.storage)
                    self.logger.info(f"发现 {len(new_urls)} 个新URL待处理")
                except Exception as e:
                    self.logger.error(f"过滤URL失败: {e}")
                    # 如果过滤失败，使用过滤后的URL
                    new_urls = filtered_urls
                    self.logger.info(f"使用过滤后的URL进行处理: {len(new_urls)} 个")

                if not new_urls:
                    self.logger.info("没有新URL需要处理")
                    return self._create_result_summary(len(all_urls), 0, 0, 0)

                # 5. 提取关键词
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

                # 6. 直接提交URL-关键词映射（跳过SEO查询）
                try:
                    # 新流程：直接提交映射关系
                    success = await self.simplified_backend.submit_url_keywords_mapping(url_keywords_map)
                    
                    # 获取统计信息
                    stats = self.simplified_backend.get_statistics()
                    
                    data_result = {
                        'saved_urls': len(url_keywords_map) if success else 0,
                        'submitted_records': stats['total_submitted']
                    }
                    
                    self.logger.info(f"提交结果: {'成功' if success else '失败'}")
                    self.logger.info(f"统计信息: {stats}")

                except Exception as e:
                    self.logger.error(f"URL-关键词映射提交失败: {e}")
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
            # **self.data_processor.get_statistics()  # 注释掉，因为不再使用SEO查询
        }
    
    async def health_check(self) -> Dict[str, bool]:
        """
        健康检查

        Returns:
            Dict[str, bool]: 各组件健康状态
        """
        # 健康状态检查
        health_status = {}
        
        # 检查简化后端客户端
        try:
            health_status['simplified_backend'] = await self.simplified_backend.test_connection()
        except Exception:
            health_status['simplified_backend'] = False
        
        # 检查后端API（如果还在使用）
        try:
            health_status['backend_api'] = await self.backend_api.test_connection()
        except Exception:
            health_status['backend_api'] = False
        
        # 检查存储
        health_status['storage'] = self.storage.storage_file.parent.exists()

        # 检查配置
        health_status['config'] = self.config_loader.validate_config_files()

        return health_status
