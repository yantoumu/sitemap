"""
数据处理器
负责关键词数据的查询、保存和提交处理
"""

import asyncio
from typing import List, Set, Dict, Any
from datetime import datetime
import logging

from .api import SEOAPIManager, BackendAPIClient
from .api.keyword_data_transformer import KeywordDataTransformer
from .api.keyword_metrics_client import KeywordMetricsClient
from .storage import StorageManager
from .utils import get_logger, TimingLogger


class DataProcessor:
    """数据处理器 - 负责关键词数据的处理流程"""
    
    def __init__(self, seo_api: SEOAPIManager, backend_api: BackendAPIClient,
                 storage: StorageManager, keyword_metrics_client: KeywordMetricsClient = None):
        """
        初始化数据处理器

        Args:
            seo_api: SEO API管理器
            backend_api: 后端API客户端
            storage: 存储管理器
            keyword_metrics_client: 关键词指标客户端（可选，用于新API）
        """
        self.seo_api = seo_api
        self.backend_api = backend_api
        self.storage = storage
        self.keyword_metrics_client = keyword_metrics_client
        self.data_transformer = KeywordDataTransformer()
        self.logger = get_logger(__name__)
    
    async def process_keywords_data(self, url_keywords_map: Dict[str, Set[str]]) -> Dict[str, Any]:
        """
        处理关键词数据的完整流程 - 异步并行处理版本

        Args:
            url_keywords_map: URL到关键词集合的映射

        Returns:
            Dict[str, Any]: 处理结果统计
        """
        # 数据类型验证和转换
        url_keywords_map = self._validate_and_convert_url_keywords_map(url_keywords_map)

        if not url_keywords_map:
            return self._create_empty_result()

        # 1. 获取所有唯一关键词
        all_keywords = set()
        for keywords in url_keywords_map.values():
            all_keywords.update(keywords)

        self.logger.info(f"共提取 {len(all_keywords)} 个唯一关键词")

        # 2. 查询关键词数据
        keyword_data = await self._query_keywords(list(all_keywords))

        # 3. 严格过滤成功数据
        successful_data = self._filter_successful_data(keyword_data, url_keywords_map)

        if not successful_data['keyword_data'] and not successful_data['url_keywords_map']:
            self.logger.warning("没有成功查询的数据，跳过后续处理")
            return {
                'total_keywords': len(all_keywords),
                'successful_keywords': 0,
                'saved_urls': 0,
                'submitted_records': 0,
                'storage_success': False,
                'submit_success': False
            }

        # 4. 并行处理：直接使用asyncio.gather同时执行本地存储和后端提交
        storage_result, submit_result = await self._execute_parallel_simple(
            successful_data['url_keywords_map'],
            successful_data['keyword_data']
        )

        return {
            'total_keywords': len(all_keywords),
            'successful_keywords': len(successful_data['keyword_data']),
            'saved_urls': storage_result.get('saved_count', 0),
            'submitted_records': submit_result.get('submitted_count', 0),
            'storage_success': storage_result.get('success', False),
            'submit_success': submit_result.get('success', False),
            'storage_error': storage_result.get('error'),
            'submit_error': submit_result.get('error')
        }
    
    async def _query_keywords(self, keywords: List[str]) -> Dict[str, Dict]:
        """
        查询所有关键词数据
        
        Args:
            keywords: 关键词列表
            
        Returns:
            Dict[str, Dict]: 关键词数据映射
        """
        if not keywords:
            return {}
        
        with TimingLogger(self.logger, f"查询 {len(keywords)} 个关键词"):
            return await self.seo_api.query_keywords_serial(keywords)

    def _filter_successful_data(self, keyword_data: Dict[str, Dict],
                               url_keywords_map: Dict[str, Set[str]]) -> Dict[str, Any]:
        """
        严格过滤成功数据，丢弃查询失败的数据

        Args:
            keyword_data: 原始关键词数据
            url_keywords_map: 原始URL关键词映射

        Returns:
            Dict[str, Any]: 过滤后的成功数据
        """
        # 防御性类型检查：确保url_keywords_map是字典类型
        if not isinstance(url_keywords_map, dict):
            self.logger.error(f"url_keywords_map类型错误: 期望dict，实际{type(url_keywords_map)}")
            raise TypeError(f"url_keywords_map必须是字典类型，实际类型: {type(url_keywords_map)}")

        # 防御性类型检查：确保keyword_data是字典类型
        if not isinstance(keyword_data, dict):
            self.logger.error(f"keyword_data类型错误: 期望dict，实际{type(keyword_data)}")
            raise TypeError(f"keyword_data必须是字典类型，实际类型: {type(keyword_data)}")

        # 过滤出成功查询的关键词
        successful_keywords = {k: v for k, v in keyword_data.items() if v}

        # 过滤URL映射，只保留有成功关键词的URL
        successful_url_keywords_map = {}
        for url, keywords in url_keywords_map.items():
            # 找出该URL下成功查询的关键词
            url_successful_keywords = keywords.intersection(successful_keywords.keys())
            if url_successful_keywords:
                successful_url_keywords_map[url] = url_successful_keywords

        self.logger.info(f"数据过滤完成: {len(successful_keywords)}/{len(keyword_data)} 个关键词成功, "
                        f"{len(successful_url_keywords_map)}/{len(url_keywords_map)} 个URL有效")

        return {
            'keyword_data': successful_keywords,
            'url_keywords_map': successful_url_keywords_map
        }

    async def _execute_parallel_simple(self, url_keywords_map: Dict[str, Set[str]],
                                      keyword_data: Dict[str, Dict]) -> tuple:
        """
        简单并行处理：直接使用asyncio.gather

        Args:
            url_keywords_map: 成功的URL关键词映射
            keyword_data: 成功的关键词数据

        Returns:
            tuple: (storage_result, submit_result)
        """
        self.logger.info("开始并行处理：本地存储 + 后端提交")

        # 直接并行执行，无需数据副本（数据只读）
        storage_task = self._storage_simple(url_keywords_map, keyword_data)
        submit_task = self._submit_simple(keyword_data, url_keywords_map)

        # 并行执行，收集异常
        results = await asyncio.gather(storage_task, submit_task, return_exceptions=True)

        # 处理结果
        storage_result = results[0] if not isinstance(results[0], Exception) else {
            'success': False, 'saved_count': 0, 'error': f"{type(results[0]).__name__}: {str(results[0])}"
        }
        submit_result = results[1] if not isinstance(results[1], Exception) else {
            'success': False, 'submitted_count': 0, 'error': f"{type(results[1]).__name__}: {str(results[1])}"
        }

        # 记录异常详情
        if isinstance(results[0], Exception):
            self.logger.error(f"存储任务异常: {type(results[0]).__name__}: {results[0]}")
        if isinstance(results[1], Exception):
            self.logger.error(f"提交任务异常: {type(results[1]).__name__}: {results[1]}")

        self.logger.info(f"并行处理完成 - "
                       f"存储: {'成功' if storage_result.get('success') else '失败'}, "
                       f"提交: {'成功' if submit_result.get('success') else '失败'}")

        return storage_result, submit_result

    async def _storage_simple(self, url_keywords_map: Dict[str, Set[str]],
                            keyword_data: Dict[str, Dict]) -> Dict[str, Any]:
        """
        简化的存储任务

        Args:
            url_keywords_map: URL关键词映射
            keyword_data: 关键词数据

        Returns:
            Dict[str, Any]: 存储结果
        """
        try:
            self.logger.info(f"存储任务开始: {len(url_keywords_map)} 个URL")

            saved_count = 0
            for url, keywords in url_keywords_map.items():
                # 构建该URL的SEO数据（直接使用原数据，无需副本）
                url_seo_data = {
                    keyword: keyword_data[keyword]
                    for keyword in keywords
                    if keyword in keyword_data and keyword_data[keyword]
                }

                if url_seo_data:
                    success = await self.storage.save_processed_url(
                        url, list(keywords), url_seo_data
                    )
                    if success:
                        saved_count += 1

            self.logger.info(f"存储任务完成: 成功保存 {saved_count} 个URL")
            return {'success': True, 'saved_count': saved_count}

        except Exception as e:
            self.logger.error(f"存储任务失败: {e}")
            return {'success': False, 'saved_count': 0, 'error': str(e)}

    async def _submit_simple(self, keyword_data: Dict[str, Dict],
                           url_keywords_map: Dict[str, Set[str]]) -> Dict[str, Any]:
        """
        简化的提交任务

        Args:
            keyword_data: 关键词数据
            url_keywords_map: URL关键词映射

        Returns:
            Dict[str, Any]: 提交结果
        """
        try:
            self.logger.info(f"提交任务开始: {len(keyword_data)} 个关键词")

            # 准备提交数据（直接使用原数据，无需副本）
            submit_data = await self._prepare_submit_data(keyword_data, url_keywords_map)

            if not submit_data:
                self.logger.info("提交任务: 没有数据需要提交")
                return {'success': True, 'submitted_count': 0}

            # 提交到后端
            success = await self._submit_to_backend(submit_data, url_keywords_map)
            submitted_count = len(submit_data) if success else 0

            self.logger.info(f"提交任务完成: {'成功' if success else '失败'} "
                           f"提交 {submitted_count} 条记录")

            return {'success': success, 'submitted_count': submitted_count}

        except Exception as e:
            self.logger.error(f"提交任务失败: {e}")
            return {'success': False, 'submitted_count': 0, 'error': str(e)}

    async def _prepare_submit_data(self, keyword_data: Dict[str, Dict],
                                  url_keywords_map: Dict[str, Set[str]]) -> List[Dict]:
        """
        准备提交数据

        Args:
            keyword_data: 关键词数据
            url_keywords_map: URL到关键词集合的映射

        Returns:
            List[Dict]: 提交数据列表
        """
        if self.keyword_metrics_client:
            # 使用新的API格式
            return await self._prepare_new_api_submit_data(keyword_data, url_keywords_map)
        else:
            # 使用旧的API格式（向后兼容）
            return self._prepare_legacy_submit_data(keyword_data)

    async def _save_successful_data(self, url_keywords_map: Dict[str, Set[str]],
                                   keyword_data: Dict[str, Dict]) -> int:
        """
        保存成功查询的数据
        
        Args:
            url_keywords_map: URL关键词映射
            keyword_data: 关键词数据
            
        Returns:
            int: 保存的URL数量
        """
        saved_count = 0
        
        for url, keywords in url_keywords_map.items():
            # 构建该URL的SEO数据
            url_seo_data = {}
            for keyword in keywords:
                if keyword in keyword_data and keyword_data[keyword]:
                    url_seo_data[keyword] = keyword_data[keyword]
            
            # 只有有成功数据才保存
            if url_seo_data:
                success = await self.storage.save_processed_url(
                    url, list(keywords), url_seo_data
                )
                if success:
                    saved_count += 1
        
        self.logger.info(f"成功保存 {saved_count} 个URL的数据")
        return saved_count
    
    async def _prepare_submit_data(self, keyword_data: Dict[str, Dict],
                                  url_keywords_map: Dict[str, Set[str]]) -> List[Dict]:
        """
        准备提交数据

        Args:
            keyword_data: 关键词数据
            url_keywords_map: URL到关键词集合的映射

        Returns:
            List[Dict]: 提交数据列表
        """
        if self.keyword_metrics_client:
            # 使用新的API格式
            return await self._prepare_new_api_submit_data(keyword_data, url_keywords_map)
        else:
            # 使用旧的API格式（向后兼容）
            return self._prepare_legacy_submit_data(keyword_data)

    async def _prepare_new_api_submit_data(self, keyword_data: Dict[str, Dict],
                                          url_keywords_map: Dict[str, Set[str]]) -> List[Dict]:
        """
        准备新API格式的提交数据

        Args:
            keyword_data: 关键词数据
            url_keywords_map: URL到关键词集合的映射

        Returns:
            List[Dict]: 符合新API格式的提交数据列表
        """
        # 构建查询API响应格式
        query_response = {
            'status': 'success',
            'data': []
        }

        for keyword, data in keyword_data.items():
            # 数据已经在_filter_successful_data中过滤过，这里直接使用
            query_response['data'].append({
                'keyword': keyword,
                'metrics': data
            })

        # 使用转换器转换为提交格式
        submit_data = self.data_transformer.transform_query_response_to_submit_format(
            query_response, url_keywords_map
        )

        # 打印转换统计
        stats = self.data_transformer.get_transformation_stats(submit_data)
        self.logger.info(f"数据转换完成: {stats}")

        return submit_data

    def _prepare_legacy_submit_data(self, keyword_data: Dict[str, Dict]) -> List[Dict]:
        """
        准备旧API格式的提交数据（向后兼容）

        Args:
            keyword_data: 关键词数据

        Returns:
            List[Dict]: 旧格式的提交数据列表
        """
        submit_data = []

        for keyword, data in keyword_data.items():
            # 数据已经在_filter_successful_data中过滤过，这里直接使用
            submit_data.append({
                'keyword': keyword,
                'avg_monthly_searches': data.get('avg_monthly_searches', 0),
                'latest_searches': data.get('latest_searches', 0),
                'competition': data.get('competition', 'UNKNOWN'),
                'monthly_trend': data.get('monthly_searches', []),
                'timestamp': datetime.now().isoformat()
            })

        return submit_data
    
    async def _submit_to_backend(self, submit_data: List[Dict],
                                url_keywords_map: Dict[str, Set[str]]) -> bool:
        """
        提交数据到后端

        Args:
            submit_data: 提交数据列表
            url_keywords_map: URL到关键词集合的映射

        Returns:
            bool: 是否提交成功
        """
        try:
            if self.keyword_metrics_client:
                # 使用新的关键词指标客户端
                success = await self.keyword_metrics_client.submit_keyword_metrics_batch(submit_data)
                if success:
                    self.logger.info(f"成功提交 {len(submit_data)} 条关键词指标数据到新API")
                    # 打印统计信息（如果客户端支持）
                    if hasattr(self.keyword_metrics_client, 'get_statistics'):
                        stats = self.keyword_metrics_client.get_statistics()
                        self.logger.info(f"提交统计: {stats}")
                else:
                    self.logger.error("关键词指标数据提交失败")
                return success
            else:
                # 使用旧的后端API客户端（向后兼容）
                success = await self.backend_api.submit_batch(submit_data)
                if success:
                    self.logger.info(f"成功提交 {len(submit_data)} 条数据到旧API")
                else:
                    self.logger.error("数据提交失败")
                return success
        except Exception as e:
            self.logger.error(f"提交数据异常: {e}")
            return False
    
    def _create_empty_result(self) -> Dict[str, Any]:
        """
        创建空结果
        
        Returns:
            Dict[str, Any]: 空结果
        """
        return {
            'total_keywords': 0,
            'successful_keywords': 0,
            'saved_urls': 0,
            'submitted_records': 0
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取处理统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        return {
            'storage_stats': self.storage.get_statistics(),
            'seo_api_stats': self.seo_api.get_statistics(),
            'backend_api_stats': self.backend_api.get_statistics()
        }

    def _validate_and_convert_url_keywords_map(self, url_keywords_map) -> Dict[str, Set[str]]:
        """
        验证和转换url_keywords_map数据类型

        Args:
            url_keywords_map: 输入的URL关键词映射（可能是各种类型）

        Returns:
            Dict[str, Set[str]]: 标准化的URL关键词映射

        Raises:
            TypeError: 如果数据类型无法转换
        """
        # 如果是None或空，返回空字典
        if not url_keywords_map:
            return {}

        # 如果已经是正确的字典类型，直接返回
        if isinstance(url_keywords_map, dict):
            # 验证字典的值是否为Set类型
            for url, keywords in url_keywords_map.items():
                if not isinstance(keywords, set):
                    self.logger.warning(f"URL {url} 的关键词不是set类型，正在转换: {type(keywords)}")
                    if isinstance(keywords, (list, tuple)):
                        url_keywords_map[url] = set(keywords)
                    else:
                        self.logger.error(f"无法转换关键词类型: {type(keywords)}")
                        url_keywords_map[url] = set()
            return url_keywords_map

        # 如果是列表，尝试转换（这可能是问题所在）
        if isinstance(url_keywords_map, list):
            self.logger.error(f"url_keywords_map是列表类型，无法转换为字典: {type(url_keywords_map)}")
            self.logger.error(f"列表内容预览: {url_keywords_map[:3] if len(url_keywords_map) > 0 else '空列表'}")
            raise TypeError(f"url_keywords_map不能是列表类型，期望字典类型，实际: {type(url_keywords_map)}")

        # 其他类型都无法处理
        self.logger.error(f"url_keywords_map类型不支持: {type(url_keywords_map)}")
        raise TypeError(f"url_keywords_map类型不支持: {type(url_keywords_map)}")

        return {}
    
    async def health_check(self) -> Dict[str, bool]:
        """
        健康检查
        
        Returns:
            Dict[str, bool]: 各组件健康状态
        """
        health_status = {}
        
        # 检查后端API连接
        try:
            health_status['backend_api'] = await self.backend_api.test_connection()
        except Exception:
            health_status['backend_api'] = False
        
        # 检查SEO API
        try:
            seo_health = await self.seo_api.health_check()
            health_status['seo_api'] = any(seo_health.values())
        except Exception:
            health_status['seo_api'] = False
        
        # 检查存储
        health_status['storage'] = self.storage.storage_file.parent.exists()
        
        return health_status


class URLProcessor:
    """URL处理器 - 负责URL的解析和关键词提取"""
    
    def __init__(self, rule_engine, keyword_extractor):
        """
        初始化URL处理器
        
        Args:
            rule_engine: 规则引擎
            keyword_extractor: 关键词提取器
        """
        self.rule_engine = rule_engine
        self.keyword_extractor = keyword_extractor
        self.logger = get_logger(__name__)
    
    def filter_processed_urls(self, urls: Set[str], storage: StorageManager) -> List[str]:
        """
        过滤已处理的URL
        
        Args:
            urls: URL集合
            storage: 存储管理器
            
        Returns:
            List[str]: 新URL列表
        """
        new_urls = []
        for url in urls:
            if not storage.is_url_processed(url):
                new_urls.append(url)
        return new_urls
    
    def extract_all_keywords(self, urls: List[str]) -> Dict[str, Set[str]]:
        """
        从所有URL提取关键词
        
        Args:
            urls: URL列表
            
        Returns:
            Dict[str, Set[str]]: URL到关键词集合的映射
        """
        from .utils import ProgressLogger

        url_keywords_map = {}
        # 优化进度输出：对于大量URL，减少输出频率
        log_interval = max(1000, len(urls) // 20)  # 最少1000，或总数的5%
        progress = ProgressLogger(self.logger, len(urls), log_interval)
        
        for url in urls:
            progress.update()
            rule = self.rule_engine.get_rule_for_url(url)
            # 现在get_rule_for_url总是返回规则（特定规则或默认规则）
            keywords = self.keyword_extractor.extract_keywords(url, rule)
            if keywords:
                url_keywords_map[url] = keywords
            else:
                # 减少冗余DEBUG日志 - 只在DEBUG级别且每1000个记录一次
                if self.logger.isEnabledFor(logging.DEBUG) and len(url_keywords_map) % 1000 == 0:
                    self.logger.debug(f"处理进度: {len(url_keywords_map)} 个URL已提取关键词")
        
        progress.finish()
        self.logger.info(f"从 {len(urls)} 个URL中提取到 {len(url_keywords_map)} 个有效URL的关键词")
        return url_keywords_map
