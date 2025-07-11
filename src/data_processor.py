"""
数据处理器
负责关键词数据的查询、保存和提交处理
"""

import asyncio
import time
from typing import List, Set, Dict, Any
from datetime import datetime
import logging

from .api import SEOAPIManager, BackendAPIClient
from .api.keyword_data_transformer import KeywordDataTransformer
from .api.keyword_metrics_client import KeywordMetricsClient
from .storage import StorageManager
from .utils import get_logger, TimingLogger, ProgressLogger


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

        # 1. 获取所有唯一关键词 - 添加类型安全检查
        all_keywords = set()

        # 防御性检查：确保url_keywords_map是字典类型
        if not isinstance(url_keywords_map, dict):
            self.logger.error(f"❌ url_keywords_map类型错误: {type(url_keywords_map)}, 期望dict类型")
            self.logger.error(f"❌ 数据内容: {str(url_keywords_map)[:200]}...")
            return self._create_empty_result()

        try:
            for keywords in url_keywords_map.values():
                if isinstance(keywords, (set, list, tuple)):
                    all_keywords.update(keywords)
                else:
                    self.logger.warning(f"⚠️ 跳过无效关键词类型: {type(keywords)}")
        except AttributeError as e:
            self.logger.error(f"❌ AttributeError: {e}")
            self.logger.error(f"❌ url_keywords_map类型: {type(url_keywords_map)}")
            self.logger.error(f"❌ url_keywords_map内容: {str(url_keywords_map)[:500]}...")
            import traceback
            self.logger.error(f"❌ 完整堆栈: {traceback.format_exc()}")
            return self._create_empty_result()
        except Exception as e:
            self.logger.error(f"❌ 提取关键词时发生错误: {e}")
            self.logger.error(f"❌ url_keywords_map类型: {type(url_keywords_map)}")
            return self._create_empty_result()

        self.logger.info(f"共提取 {len(all_keywords)} 个唯一关键词")

        # 2. 过滤已处理的关键词（去重检查）
        new_keywords = self._filter_processed_keywords(all_keywords)
        if len(new_keywords) < len(all_keywords):
            filtered_count = len(all_keywords) - len(new_keywords)
            self.logger.info(f"过滤已处理关键词: {filtered_count} 个，剩余 {len(new_keywords)} 个待处理")

            # 更新URL映射，只保留新关键词
            url_keywords_map = self._update_url_keywords_map(url_keywords_map, new_keywords)

            if not new_keywords:
                self.logger.info("所有关键词都已处理，跳过查询")
                return self._create_empty_result()
        else:
            self.logger.info("所有关键词都是新的，无需过滤")

        # 3. 查询关键词数据
        keyword_data = await self._query_keywords(list(new_keywords), url_keywords_map)

        # 4. 严格过滤成功数据
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

        # 5. 并行处理：直接使用asyncio.gather同时执行本地存储和后端提交
        storage_result, submit_result = await self._execute_parallel_simple(
            successful_data['url_keywords_map'],
            successful_data['keyword_data']
        )

        # 输出最终统计信息
        successful_keywords = len(successful_data['keyword_data'])
        submitted_records = submit_result.get('submitted_count', 0)

        self.logger.info(f"📊 处理完成统计:")
        self.logger.info(f"   ✅ 成功查询关键词: {successful_keywords} 个")
        self.logger.info(f"   ✅ 成功提交记录: {submitted_records} 条")

        return {
            'total_keywords': len(all_keywords),
            'successful_keywords': successful_keywords,
            'saved_urls': storage_result.get('saved_count', 0),
            'submitted_records': submitted_records,
            'storage_success': storage_result.get('success', False),
            'submit_success': submit_result.get('success', False),
            'storage_error': storage_result.get('error'),
            'submit_error': submit_result.get('error')
        }

    def _filter_processed_keywords(self, keywords: set) -> set:
        """
        过滤已处理的关键词

        Args:
            keywords: 关键词集合

        Returns:
            set: 未处理的关键词集合
        """
        new_keywords = set()
        processed_count = 0

        for keyword in keywords:
            if not self.storage.is_keyword_processed(keyword):
                new_keywords.add(keyword)
            else:
                processed_count += 1

        if processed_count > 0:
            self.logger.debug(f"发现 {processed_count} 个已处理关键词")

        return new_keywords

    def _update_url_keywords_map(self, url_keywords_map: Dict[str, Set[str]],
                                new_keywords: set) -> Dict[str, Set[str]]:
        """
        更新URL关键词映射，只保留新关键词

        Args:
            url_keywords_map: 原始URL关键词映射
            new_keywords: 新关键词集合

        Returns:
            Dict[str, Set[str]]: 更新后的URL关键词映射
        """
        updated_map = {}

        for url, keywords in url_keywords_map.items():
            # 只保留新关键词
            url_new_keywords = keywords.intersection(new_keywords)
            if url_new_keywords:
                updated_map[url] = url_new_keywords

        return updated_map
    
    async def _query_keywords(self, keywords: List[str],
                                     url_keywords_map: Dict[str, Set[str]] = None) -> Dict[str, Dict]:
        """
        查询所有关键词数据 - 流式处理版本

        Args:
            keywords: 关键词列表
            url_keywords_map: URL到关键词的映射关系

        Returns:
            Dict[str, Dict]: 关键词数据映射
        """
        if not keywords:
            return {}

        # 创建流式存储和提交回调
        async def storage_callback(keyword_data_list):
            """流式存储回调 - 简化日志"""
            try:
                from datetime import datetime

                self.logger.debug(f"💾 本地存储: 保存 {len(keyword_data_list)} 条数据")

                saved_count = 0
                for data in keyword_data_list:
                    keyword = data['keyword']
                    seo_data = data['seo_data']

                    # 保存已处理的关键词（仅保存加密标识）
                    success = await self.storage.save_processed_keyword(keyword)
                    if success:
                        saved_count += 1
                    else:
                        self.logger.debug(f"关键词 {keyword} 存储失败")

                self.logger.debug(f"💾 本地存储完成: 成功保存 {saved_count}/{len(keyword_data_list)} 条数据")

            except Exception as e:
                self.logger.error(f"❌ 本地存储失败: {e}")

        async def submission_callback(keyword_data_list):
            """流式提交回调 - 详细后端API日志"""
            try:
                from datetime import datetime

                # 后端提交日志（仅调试模式）
                self.logger.debug(f"🚀 后端API提交: {len(keyword_data_list)} 条数据")

                # 准备提交数据 - 转换为正确的API格式，包含URL信息
                keyword_data_dict = {}
                for data in keyword_data_list:
                    keyword_data_dict[data['keyword']] = data['seo_data']

                # 使用正确的数据格式转换方法，传递URL映射信息
                submit_data = self._prepare_legacy_submit_data(keyword_data_dict, url_keywords_map)

                # 提交到后端
                start_time = time.time()
                if self.keyword_metrics_client:
                    success = await self.keyword_metrics_client.submit_keyword_metrics_batch(submit_data)
                    api_type = "新API (keyword-metrics)"
                elif self.backend_api:
                    success = await self.backend_api.submit_batch(submit_data)
                    api_type = "后端API (work.seokey.vip)"
                else:
                    success = False
                    api_type = "未配置"
                    self.logger.warning("❌ 没有配置后端API客户端")

                end_time = time.time()
                duration = end_time - start_time

                # 提交结果日志（仅调试模式）
                if success:
                    self.logger.debug(f"✅ 后端API提交成功: {len(keyword_data_list)} 条数据")
                else:
                    self.logger.error(f"❌ 后端API提交失败:")
                    self.logger.error(f"   API类型: {api_type}")
                    self.logger.error(f"   提交状态: 失败")
                    self.logger.error(f"   数据量: {len(keyword_data_list)} 条")
                    self.logger.error(f"   耗时: {duration:.2f} 秒")

            except Exception as e:
                self.logger.error(f"❌ 后端API提交异常: {e}")
                import traceback
                self.logger.debug(f"异常详情: {traceback.format_exc()}")

        with TimingLogger(self.logger, f"弹性查询 {len(keywords)} 个关键词"):
            # 检查是否是增强版API管理器
            if hasattr(self.seo_api, 'query_keywords_with_resilience'):
                self.logger.info("🚀 使用增强版弹性查询")
                return await self.seo_api.query_keywords_with_resilience(
                    keywords,
                    storage_callback=storage_callback,
                    submission_callback=submission_callback
                )
            else:
                self.logger.info("📡 使用标准流式查询")
                return await self.seo_api.query_keywords_streaming(
                    keywords,
                    url_keywords_map,
                    storage_callback=storage_callback,
                    submission_callback=submission_callback
                )

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

    def _prepare_legacy_submit_data(self, keyword_data: Dict[str, Dict],
                                   url_keywords_map: Dict[str, Set[str]] = None) -> List[Dict]:
        """
        准备符合API文档规范的提交数据 - 简化版本

        Args:
            keyword_data: 关键词数据
            url_keywords_map: URL到关键词的映射关系

        Returns:
            List[Dict]: 符合API文档格式的提交数据列表
        """
        # 创建关键词到URL的反向映射
        keyword_to_urls = {}
        if url_keywords_map:
            for url, keywords in url_keywords_map.items():
                for keyword in keywords:
                    if keyword not in keyword_to_urls:
                        keyword_to_urls[keyword] = []
                    keyword_to_urls[keyword].append(url)

        submit_data = []

        for keyword, data in keyword_data.items():
            # 只处理必要的字段转换
            # 1. null值转换为0
            low_bid = data.get('low_top_of_page_bid_micro', 0) or 0
            high_bid = data.get('high_top_of_page_bid_micro', 0) or 0

            # 2. 确保monthly_searches中的year和month为字符串
            original_monthly_searches = data.get('monthly_searches', [])
            self.logger.debug(f"🔍 处理关键词 {keyword} 的 monthly_searches:")
            self.logger.debug(f"   原始数据类型: {type(original_monthly_searches)}")
            self.logger.debug(f"   原始数据长度: {len(original_monthly_searches) if isinstance(original_monthly_searches, list) else 'N/A'}")
            self.logger.debug(f"   原始数据内容: {original_monthly_searches}")

            monthly_searches = []
            for i, item in enumerate(original_monthly_searches):
                self.logger.debug(f"   处理第 {i+1} 项: {item}")
                if isinstance(item, dict):
                    # 支持英文和中文字段名
                    year_value = None
                    month_value = None
                    searches_value = None

                    # 检查英文字段名（正常情况）
                    if 'year' in item and 'month' in item and 'searches' in item:
                        year_value = item['year']
                        month_value = item['month']
                        searches_value = item['searches']
                        self.logger.debug(f"   ✅ 检测到英文字段名")
                    # 检查中文字段名（异常情况，需要修复）
                    elif '年' in item and '月' in item and 'searches' in item:
                        year_value = item['年']
                        month_value = item['月']
                        searches_value = item['searches']
                        # 静默修复中文字段名，不输出警告
                        self.logger.debug(f"   🔧 自动修复中文字段名: 年={year_value}, 月={month_value}")

                    if year_value is not None and month_value is not None and searches_value is not None:
                        converted_item = {
                            "year": str(year_value),
                            "month": str(month_value),
                            "searches": searches_value
                        }
                        monthly_searches.append(converted_item)
                        self.logger.debug(f"   ✅ 转换成功: {converted_item}")
                    else:
                        self.logger.info(f"   ❌ 跳过无效项: 缺少必需字段")
                else:
                    self.logger.info(f"   ❌ 跳过无效项: 类型={type(item)}, 不是字典")

            self.logger.debug(f"   最终 monthly_searches 长度: {len(monthly_searches)}")
            self.logger.debug(f"   最终 monthly_searches 内容: {monthly_searches}")

            # 获取该关键词对应的URL列表
            urls = keyword_to_urls.get(keyword, [])

            # 如果没有URL映射，使用默认URL
            if not urls:
                urls = [f"https://example.com/{keyword.replace(' ', '-')}"]

            # 为每个URL创建一条提交记录
            for url in urls:
                submit_record = {
                    "keyword": keyword,
                    "url": url,  # 使用真实的URL
                    "metrics": {
                        "avg_monthly_searches": data.get('avg_monthly_searches', 0),
                        "latest_searches": data.get('latest_searches', 0),
                        "max_monthly_searches": data.get('max_monthly_searches', 0),
                        "competition": data.get('competition', 'UNKNOWN'),
                        "competition_index": data.get('competition_index', 0),
                        "low_top_of_page_bid_micro": low_bid,
                        "high_top_of_page_bid_micro": high_bid,
                        "monthly_searches": monthly_searches,
                        "data_quality": data.get('data_quality', {
                            "status": "unknown",
                            "complete": False,
                            "has_missing_months": True,
                            "only_last_month_has_data": False,
                            "total_months": 0,
                            "available_months": 0,
                            "missing_months_count": 0,
                            "missing_months": [],
                            "warnings": ["no_data_quality_provided"]
                        })
                    }
                }

                submit_data.append(submit_record)

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
                # 使用后端API客户端 (work.seokey.vip)
                success = await self.backend_api.submit_batch(submit_data)
                if success:
                    self.logger.info(f"成功提交 {len(submit_data)} 条数据到后端API")
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

        # 如果是列表，返回空字典而不是抛出异常
        if isinstance(url_keywords_map, list):
            self.logger.error(f"url_keywords_map是列表类型，无法转换为字典: {type(url_keywords_map)}")
            self.logger.error(f"列表内容预览: {url_keywords_map[:3] if len(url_keywords_map) > 0 else '空列表'}")
            # 返回空字典而不是抛出异常，让程序继续运行
            return {}

        # 其他类型都无法处理，返回空字典
        self.logger.error(f"url_keywords_map类型不支持: {type(url_keywords_map)}")
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
        过滤已处理的URL - 增强错误处理

        Args:
            urls: URL集合
            storage: 存储管理器

        Returns:
            List[str]: 新URL列表
        """
        if not urls:
            self.logger.warning("输入URL集合为空")
            return []

        if not isinstance(urls, (set, list, tuple)):
            self.logger.error(f"URLs类型错误: {type(urls)}, 期望set/list/tuple")
            return []

        new_urls = []
        processed_count = 0
        error_count = 0

        for url in urls:
            try:
                if not isinstance(url, str):
                    self.logger.warning(f"跳过非字符串URL: {type(url)} - {url}")
                    error_count += 1
                    continue

                if not storage.is_url_processed(url):
                    new_urls.append(url)
                else:
                    processed_count += 1

            except Exception as e:
                self.logger.error(f"检查URL处理状态失败 {url}: {e}")
                error_count += 1
                # 如果检查失败，保守地将URL加入新URL列表
                new_urls.append(url)

        self.logger.info(f"URL过滤完成: 新URL {len(new_urls)}, 已处理 {processed_count}, 错误 {error_count}")
        return new_urls
    
    def extract_all_keywords(self, urls: List[str]) -> Dict[str, Set[str]]:
        """
        从所有URL提取关键词 - 并行优化版本

        Args:
            urls: URL列表

        Returns:
            Dict[str, Set[str]]: URL到关键词集合的映射
        """
        import asyncio
        import concurrent.futures
        import os

        try:
            # 如果URL数量较少，使用原始顺序处理
            if len(urls) < 1000:
                result = self._extract_keywords_sequential(urls)
            else:
                # 并行处理大量URL（同步版本）
                result = self._extract_keywords_parallel_sync(urls)

            # 防御性检查：确保返回字典类型
            if not isinstance(result, dict):
                self.logger.error(f"❌ extract_all_keywords返回类型错误: {type(result)}, 期望dict类型")
                return {}

            return result

        except Exception as e:
            self.logger.error(f"❌ extract_all_keywords执行失败: {e}")
            import traceback
            self.logger.error(f"❌ 完整堆栈: {traceback.format_exc()}")
            return {}

    def _extract_keywords_sequential(self, urls: List[str]) -> Dict[str, Set[str]]:
        """
        顺序提取关键词（用于小批量URL）

        Args:
            urls: URL列表

        Returns:
            Dict[str, Set[str]]: URL到关键词集合的映射
        """
        url_keywords_map = {}
        log_interval = max(100, len(urls) // 10)
        progress = ProgressLogger(self.logger, len(urls), log_interval)

        for url in urls:
            progress.update()
            rule = self.rule_engine.get_rule_for_url(url)
            keywords = self.keyword_extractor.extract_keywords(url, rule)
            if keywords:
                url_keywords_map[url] = keywords

        progress.finish()
        self.logger.info(f"从 {len(urls)} 个URL中提取到 {len(url_keywords_map)} 个有效URL的关键词")
        return url_keywords_map

    def _extract_keywords_parallel_sync(self, urls: List[str]) -> Dict[str, Set[str]]:
        """
        并行提取关键词（同步版本，用于大批量URL）

        Args:
            urls: URL列表

        Returns:
            Dict[str, Set[str]]: URL到关键词集合的映射
        """
        import concurrent.futures
        import os

        # 确定并行度：CPU核心数的2倍，但不超过6（降低资源消耗）
        max_workers = min(6, (os.cpu_count() or 4) * 2)

        # 计算批次大小：确保每个批次有足够的工作量，但不会过大
        batch_size = max(200, min(1000, len(urls) // (max_workers * 2)))

        self.logger.info(f"并行关键词提取: {len(urls)} 个URL, {max_workers} 个工作线程, 批次大小 {batch_size}")

        # 分批处理，限制内存使用
        batches = [urls[i:i + batch_size] for i in range(0, len(urls), batch_size)]

        # 进度跟踪
        log_interval = max(500, len(urls) // 20)
        progress = ProgressLogger(self.logger, len(urls), log_interval)

        # 并行处理批次
        url_keywords_map = {}

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有批次任务
                future_to_batch = {
                    executor.submit(self._process_url_batch, batch, progress): batch
                    for batch in batches
                }

                # 收集结果
                for future in concurrent.futures.as_completed(future_to_batch):
                    try:
                        batch_result = future.result()
                        url_keywords_map.update(batch_result)
                    except Exception as e:
                        batch = future_to_batch[future]
                        self.logger.error(f"批次处理失败 ({len(batch)} URLs): {e}")

        except Exception as e:
            self.logger.error(f"并行处理异常: {e}")
            # 即使出现异常，也要完成进度记录
        finally:
            progress.finish()

        self.logger.info(f"并行提取完成: 从 {len(urls)} 个URL中提取到 {len(url_keywords_map)} 个有效URL的关键词")
        return url_keywords_map

    async def _extract_keywords_parallel(self, urls: List[str]) -> Dict[str, Set[str]]:
        """
        并行提取关键词（用于大批量URL）

        Args:
            urls: URL列表

        Returns:
            Dict[str, Set[str]]: URL到关键词集合的映射
        """
        import concurrent.futures
        import os

        # 确定并行度：CPU核心数的2倍，但不超过8
        max_workers = min(8, (os.cpu_count() or 4) * 2)

        # 计算批次大小：确保每个批次有足够的工作量
        batch_size = max(500, len(urls) // (max_workers * 4))

        self.logger.info(f"并行关键词提取: {len(urls)} 个URL, {max_workers} 个工作线程, 批次大小 {batch_size}")

        # 分批处理
        batches = [urls[i:i + batch_size] for i in range(0, len(urls), batch_size)]

        # 进度跟踪
        log_interval = max(1000, len(urls) // 20)
        progress = ProgressLogger(self.logger, len(urls), log_interval)

        # 并行处理批次
        url_keywords_map = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有批次任务
            future_to_batch = {
                executor.submit(self._process_url_batch, batch, progress): batch
                for batch in batches
            }

            # 收集结果
            for future in concurrent.futures.as_completed(future_to_batch):
                try:
                    batch_result = future.result()
                    url_keywords_map.update(batch_result)
                except Exception as e:
                    batch = future_to_batch[future]
                    self.logger.error(f"批次处理失败 ({len(batch)} URLs): {e}")

        progress.finish()
        self.logger.info(f"并行提取完成: 从 {len(urls)} 个URL中提取到 {len(url_keywords_map)} 个有效URL的关键词")
        return url_keywords_map

    def _process_url_batch(self, urls_batch: List[str], progress: 'ProgressLogger') -> Dict[str, Set[str]]:
        """
        处理URL批次

        Args:
            urls_batch: URL批次
            progress: 进度记录器

        Returns:
            Dict[str, Set[str]]: 批次结果
        """
        batch_result = {}

        for url in urls_batch:
            try:
                rule = self.rule_engine.get_rule_for_url(url)
                keywords = self.keyword_extractor.extract_keywords(url, rule)
                if keywords:
                    batch_result[url] = keywords

                # 线程安全的进度更新
                progress.update()

            except Exception as e:
                # 记录错误但继续处理
                if self.logger.isEnabledFor(logging.DEBUG):
                    self.logger.debug(f"URL处理失败 {url}: {e}")

        return batch_result
