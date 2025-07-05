"""
关键词批量查询系统
支持两个API接口的并行查询，严格控制请求间隔和批次处理
"""

import asyncio
import aiohttp
import time
import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import logging

from ..config.schemas import KeywordAPIConfig
from ..utils.progress_tracker import ProgressTracker, create_console_progress_callback
from ..utils.log_security import LogSecurity


class KeywordBatchQueryManager:
    """关键词批量查询管理器"""
    
    def __init__(self, config: KeywordAPIConfig):
        """
        初始化查询管理器
        
        Args:
            config: 关键词API配置
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 请求控制
        self.last_request_times = {endpoint: 0 for endpoint in config.api_endpoints}
        self.request_locks = {endpoint: asyncio.Lock() for endpoint in config.api_endpoints}
        
        # 统计信息
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'total_keywords_queried': 0,
            'api_usage': {endpoint: 0 for endpoint in config.api_endpoints}
        }
        
        self.logger.info(f"关键词批量查询管理器初始化完成")
        self.logger.info(f"API端点: {config.api_endpoints}")
        self.logger.info(f"批次大小: {config.batch_size}, 间隔: {config.interval_seconds}秒")
    
    async def query_keywords_batch(self, keywords: List[str], 
                                 progress_callback: Optional[callable] = None) -> Dict[str, Dict[str, Any]]:
        """
        批量查询关键词
        
        Args:
            keywords: 关键词列表
            progress_callback: 进度回调函数
            
        Returns:
            Dict[str, Dict[str, Any]]: 关键词查询结果，格式为 {keyword: {api1_result, api2_result}}
        """
        if not keywords:
            return {}
        
        self.logger.info(f"开始批量查询 {len(keywords)} 个关键词")
        
        # 创建进度跟踪器
        tracker = ProgressTracker(keywords, self.config.batch_size)
        if progress_callback:
            tracker.add_progress_callback(progress_callback)
        else:
            tracker.add_progress_callback(create_console_progress_callback())
        
        # 存储所有结果
        all_results = {}
        
        # 处理每个批次
        for batch_id, batch in enumerate(tracker.batches):
            batch_keywords = batch.keywords
            
            self.logger.info(f"处理批次 {batch_id + 1}/{len(tracker.batches)}: {batch_keywords}")
            
            # 并行查询两个API
            api_results = await self._query_batch_parallel(batch_keywords, tracker, batch_id)
            
            # 合并结果
            for keyword in batch_keywords:
                all_results[keyword] = api_results.get(keyword, {})
            
            # 如果不是最后一个批次，等待间隔时间
            if batch_id < len(tracker.batches) - 1:
                self.logger.info(f"等待 {self.config.interval_seconds} 秒间隔...")
                await asyncio.sleep(self.config.interval_seconds)
        
        # 标记完成
        tracker.mark_completed()
        
        # 打印最终统计
        self._print_final_stats(all_results)
        
        return all_results
    
    async def _query_batch_parallel(self, keywords: List[str], 
                                  tracker: ProgressTracker, batch_id: int) -> Dict[str, Dict[str, Any]]:
        """
        并行查询一个批次的关键词（同时查询两个API）
        
        Args:
            keywords: 关键词列表
            tracker: 进度跟踪器
            batch_id: 批次ID
            
        Returns:
            Dict[str, Dict[str, Any]]: 批次查询结果
        """
        # 开始批次
        tracker.start_batch(batch_id, "并行查询两个API")
        
        # 并行查询两个API
        tasks = []
        for i, api_endpoint in enumerate(self.config.api_endpoints):
            task = self._query_single_api(keywords, api_endpoint, f"api_{i+1}")
            tasks.append(task)
        
        try:
            # 等待所有API查询完成
            api_results_list = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 合并结果
            merged_results = {}
            for keyword in keywords:
                merged_results[keyword] = {}
            
            # 处理每个API的结果
            for i, api_result in enumerate(api_results_list):
                api_name = f"api_{i+1}"
                
                if isinstance(api_result, Exception):
                    self.logger.error(f"API {i+1} 查询失败: {api_result}")
                    # 为所有关键词添加失败标记
                    for keyword in keywords:
                        merged_results[keyword][api_name] = None
                else:
                    # 添加成功结果
                    for keyword in keywords:
                        merged_results[keyword][api_name] = api_result.get(keyword)
            
            # 完成批次
            tracker.complete_batch(batch_id, merged_results, success=True)
            
            return merged_results
            
        except Exception as e:
            self.logger.error(f"批次 {batch_id + 1} 查询失败: {e}")
            
            # 创建失败结果
            failed_results = {}
            for keyword in keywords:
                failed_results[keyword] = {"api_1": None, "api_2": None}
            
            tracker.complete_batch(batch_id, failed_results, success=False, error_message=str(e))
            return failed_results
    
    async def _query_single_api(self, keywords: List[str], api_endpoint: str, api_name: str) -> Dict[str, Any]:
        """
        查询单个API
        
        Args:
            keywords: 关键词列表
            api_endpoint: API端点
            api_name: API名称
            
        Returns:
            Dict[str, Any]: API查询结果
        """
        async with self.request_locks[api_endpoint]:
            # 检查请求间隔
            current_time = time.time()
            time_since_last = current_time - self.last_request_times[api_endpoint]
            
            if time_since_last < self.config.interval_seconds:
                wait_time = self.config.interval_seconds - time_since_last
                self.logger.debug(f"{api_name} 等待 {wait_time:.2f} 秒")
                await asyncio.sleep(wait_time)
            
            # 发送请求
            try:
                result = await self._send_api_request(keywords, api_endpoint, api_name)
                self.last_request_times[api_endpoint] = time.time()
                
                # 更新统计
                self.stats['successful_requests'] += 1
                self.stats['api_usage'][api_endpoint] += 1
                
                return result
                
            except Exception as e:
                self.logger.error(f"{api_name} 请求失败: {e}")
                self.stats['failed_requests'] += 1
                
                # 返回失败结果
                return {keyword: None for keyword in keywords}
            finally:
                self.stats['total_requests'] += 1
                self.stats['total_keywords_queried'] += len(keywords)
    
    async def _send_api_request(self, keywords: List[str], api_endpoint: str, api_name: str) -> Dict[str, Any]:
        """
        发送API请求
        
        Args:
            keywords: 关键词列表
            api_endpoint: API端点
            api_name: API名称
            
        Returns:
            Dict[str, Any]: API响应结果
        """
        url = f"{api_endpoint}/api/keywords"
        params = {"keyword": ",".join(keywords)}
        
        timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
        
        # 使用安全日志记录，隐藏敏感URL
        safe_url = LogSecurity.sanitize_url(url)
        self.logger.debug(f"{api_name} 发送请求: {len(keywords)} 个关键词到 {safe_url}")
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for attempt in range(self.config.max_retries + 1):
                try:
                    async with session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            self.logger.debug(f"{api_name} 请求成功")
                            return self._parse_api_response(data, keywords)
                        else:
                            error_text = await response.text()
                            raise Exception(f"HTTP {response.status}: {error_text}")
                            
                except asyncio.TimeoutError:
                    if attempt < self.config.max_retries:
                        self.logger.warning(f"{api_name} 请求超时，重试 {attempt + 1}/{self.config.max_retries}")
                        await asyncio.sleep(self.config.retry_delay)
                        continue
                    else:
                        raise Exception(f"请求超时 ({self.config.timeout_seconds}秒)")
                        
                except aiohttp.ClientError as e:
                    if attempt < self.config.max_retries:
                        self.logger.warning(f"{api_name} 网络错误，重试 {attempt + 1}/{self.config.max_retries}: {e}")
                        await asyncio.sleep(self.config.retry_delay)
                        continue
                    else:
                        raise Exception(f"网络请求错误: {e}")
    
    def _parse_api_response(self, data: Any, keywords: List[str]) -> Dict[str, Any]:
        """
        解析API响应
        
        Args:
            data: API响应数据
            keywords: 请求的关键词列表
            
        Returns:
            Dict[str, Any]: 解析后的结果
        """
        results = {}
        
        try:
            if isinstance(data, dict):
                # 假设API返回格式: {"keyword1": {...}, "keyword2": {...}}
                for keyword in keywords:
                    if keyword in data and self._is_valid_response_data(data[keyword]):
                        results[keyword] = data[keyword]
                    else:
                        results[keyword] = None
            else:
                # 响应格式不符合预期
                for keyword in keywords:
                    results[keyword] = None
                    
        except Exception as e:
            self.logger.error(f"解析API响应失败: {e}")
            for keyword in keywords:
                results[keyword] = None
        
        return results
    
    def _is_valid_response_data(self, data: Any) -> bool:
        """
        验证响应数据是否有效
        
        Args:
            data: 响应数据
            
        Returns:
            bool: 数据是否有效
        """
        if not isinstance(data, dict):
            return False
        
        # 检查基本字段（根据实际API调整）
        return len(data) > 0
    
    def _print_final_stats(self, results: Dict[str, Dict[str, Any]]) -> None:
        """打印最终统计信息"""
        total_keywords = len(results)
        successful_api1 = sum(1 for r in results.values() if r.get('api_1') is not None)
        successful_api2 = sum(1 for r in results.values() if r.get('api_2') is not None)
        both_successful = sum(1 for r in results.values() 
                            if r.get('api_1') is not None and r.get('api_2') is not None)
        
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"最终统计结果")
        self.logger.info(f"{'='*60}")
        self.logger.info(f"总关键词数: {total_keywords}")
        self.logger.info(f"API 1 成功: {successful_api1} ({successful_api1/total_keywords*100:.1f}%)")
        self.logger.info(f"API 2 成功: {successful_api2} ({successful_api2/total_keywords*100:.1f}%)")
        self.logger.info(f"两个API都成功: {both_successful} ({both_successful/total_keywords*100:.1f}%)")
        self.logger.info(f"总请求数: {self.stats['total_requests']}")
        self.logger.info(f"成功请求: {self.stats['successful_requests']}")
        self.logger.info(f"失败请求: {self.stats['failed_requests']}")
        self.logger.info(f"{'='*60}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        return self.stats.copy()
    
    def save_results(self, results: Dict[str, Dict[str, Any]], filename: str) -> None:
        """
        保存查询结果到文件
        
        Args:
            results: 查询结果
            filename: 文件名
        """
        try:
            output_data = {
                "timestamp": datetime.now().isoformat(),
                "total_keywords": len(results),
                "statistics": self.get_statistics(),
                "results": results
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"查询结果已保存到: {filename}")
            
        except Exception as e:
            self.logger.error(f"保存结果失败: {e}")


def create_default_config(test_mode: bool = False) -> KeywordAPIConfig:
    """
    创建默认配置

    Args:
        test_mode: 是否启用测试模式

    Returns:
        KeywordAPIConfig: 默认配置
    """
    # 从环境变量读取SEO API地址列表
    import os
    api_urls = os.getenv('SEO_API_URLS', '').split(',')
    api_urls = [url.strip() for url in api_urls if url.strip()]

    # 如果没有配置API URL，使用空列表
    if not api_urls:
        api_urls = []

    return KeywordAPIConfig(
        api_endpoints=api_urls,
        batch_size=5,
        interval_seconds=60,
        timeout_seconds=30,
        max_retries=3,
        retry_delay=5.0,
        test_mode=test_mode
    )
