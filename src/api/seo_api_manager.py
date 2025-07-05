"""
SEO API管理器
管理两个SEO API接口，确保严格串行请求，支持故障转移
"""

import asyncio
import aiohttp
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

from ..utils.log_security import LogSecurity


class SEOAPIManager:
    """SEO API串行管理器"""
    
    def __init__(self, api_urls: List[str], interval: float = 1.0, 
                 batch_size: int = 5, timeout: int = 30):
        """
        初始化SEO API管理器
        
        Args:
            api_urls: API端点URL列表
            interval: 请求间隔（秒）
            batch_size: 批量查询大小
            timeout: 请求超时时间（秒）
        """
        self.api_urls = api_urls
        self.interval = interval
        self.batch_size = batch_size
        self.timeout = timeout
        self.current_api_index = 0
        self.request_lock = asyncio.Lock()
        self.last_request_time = 0
        self.logger = logging.getLogger(__name__)
        
        # 统计信息
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'api_switches': 0,
            'total_keywords_queried': 0
        }
        
        self.logger.info(f"SEO API管理器初始化完成，API端点: {len(api_urls)}个")
    
    async def query_keywords_serial(self, keywords: List[str]) -> Dict[str, Dict]:
        """
        串行查询关键词，确保请求间隔
        
        Args:
            keywords: 关键词列表
            
        Returns:
            Dict[str, Dict]: 关键词到数据的映射
        """
        if not keywords:
            return {}
        
        async with self.request_lock:
            self.logger.info(f"开始串行查询 {len(keywords)} 个关键词")
            
            # 计算等待时间
            current_time = time.time()
            time_since_last = current_time - self.last_request_time
            
            if time_since_last < self.interval:
                wait_time = self.interval - time_since_last
                self.logger.info(f"等待 {wait_time:.2f} 秒以满足API限流要求")
                await asyncio.sleep(wait_time)
            
            # 批量处理
            results = {}
            for i in range(0, len(keywords), self.batch_size):
                batch = keywords[i:i + self.batch_size]
                
                # 尝试当前API
                try:
                    batch_results = await self._send_request(batch)
                    results.update(batch_results)
                    self.last_request_time = time.time()
                    
                    # 更新统计
                    self.stats['successful_requests'] += 1
                    self.stats['total_keywords_queried'] += len(batch)
                    
                except Exception as e:
                    self.logger.error(f"API {self.current_api_index} 请求失败: {e}")
                    self.stats['failed_requests'] += 1
                    
                    # 切换到备用API
                    self.switch_api()
                    
                    # 重试一次
                    try:
                        batch_results = await self._send_request(batch)
                        results.update(batch_results)
                        self.last_request_time = time.time()
                        
                        # 更新统计
                        self.stats['successful_requests'] += 1
                        self.stats['total_keywords_queried'] += len(batch)
                        
                    except Exception as e2:
                        self.logger.error(f"备用API也失败: {e2}")
                        self.stats['failed_requests'] += 1
                        
                        # 记录失败的关键词
                        for keyword in batch:
                            results[keyword] = None
                
                # 更新总请求数
                self.stats['total_requests'] += 1
                
                # 批次间等待
                if i + self.batch_size < len(keywords):
                    await asyncio.sleep(self.interval)
            
            self.logger.info(f"串行查询完成，成功: {len([r for r in results.values() if r])}/{len(keywords)}")
            return results
    
    async def _send_request(self, keywords: List[str]) -> Dict[str, Dict]:
        """
        发送API请求
        
        Args:
            keywords: 关键词列表
            
        Returns:
            Dict[str, Dict]: 查询结果
            
        Raises:
            Exception: 请求失败
        """
        if not keywords:
            return {}
        
        url = f"{self.api_urls[self.current_api_index]}/keywords"
        params = {"keyword": ",".join(keywords)}
        
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                self.logger.debug(f"发送请求到 API {self.current_api_index}: {len(keywords)} 个关键词")
                
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self._parse_response(data, keywords)
                    else:
                        error_text = await response.text()
                        raise Exception(f"API返回错误状态码: {response.status} - {error_text}")
                        
            except asyncio.TimeoutError:
                raise Exception(f"请求超时 ({self.timeout}秒)")
            except aiohttp.ClientError as e:
                raise Exception(f"网络请求错误: {e}")
    
    def _parse_response(self, data: Any, keywords: List[str]) -> Dict[str, Dict]:
        """
        解析API响应数据
        
        Args:
            data: API响应数据
            keywords: 请求的关键词列表
            
        Returns:
            Dict[str, Dict]: 解析后的数据
        """
        results = {}
        
        try:
            # 根据实际API响应格式解析
            if isinstance(data, dict):
                # 假设响应格式: {"keyword1": {...}, "keyword2": {...}}
                for keyword in keywords:
                    if keyword in data:
                        keyword_data = data[keyword]
                        if self._is_valid_keyword_data(keyword_data):
                            results[keyword] = keyword_data
                        else:
                            results[keyword] = None
                    else:
                        results[keyword] = None
            else:
                # 如果响应格式不符合预期，标记所有关键词为失败
                for keyword in keywords:
                    results[keyword] = None
                    
        except Exception as e:
            self.logger.error(f"解析API响应失败: {e}")
            # 解析失败，标记所有关键词为失败
            for keyword in keywords:
                results[keyword] = None
        
        return results
    
    def _is_valid_keyword_data(self, data: Any) -> bool:
        """
        验证关键词数据是否有效
        
        Args:
            data: 关键词数据
            
        Returns:
            bool: 数据是否有效
        """
        if not isinstance(data, dict):
            return False
        
        # 检查必要字段
        required_fields = ['avg_monthly_searches', 'competition']
        for field in required_fields:
            if field not in data:
                return False
        
        return True
    
    def switch_api(self) -> None:
        """切换到另一个API端点"""
        old_index = self.current_api_index
        self.current_api_index = (self.current_api_index + 1) % len(self.api_urls)
        self.stats['api_switches'] += 1
        
        self.logger.info(f"切换API端点: {old_index} -> {self.current_api_index}")
    
    def get_current_api_url(self) -> str:
        """
        获取当前使用的API URL
        
        Returns:
            str: 当前API URL
        """
        return self.api_urls[self.current_api_index]
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        stats = self.stats.copy()
        stats['current_api_index'] = self.current_api_index
        stats['current_api_url'] = self.get_current_api_url()
        stats['success_rate'] = (
            self.stats['successful_requests'] / max(self.stats['total_requests'], 1) * 100
        )
        
        return stats
    
    def reset_statistics(self) -> None:
        """重置统计信息"""
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'api_switches': 0,
            'total_keywords_queried': 0
        }
        self.logger.info("统计信息已重置")
    
    async def health_check(self) -> Dict[str, bool]:
        """
        检查所有API端点的健康状态
        
        Returns:
            Dict[str, bool]: API URL到健康状态的映射
        """
        health_status = {}
        
        for i, api_url in enumerate(self.api_urls):
            try:
                timeout = aiohttp.ClientTimeout(total=5)  # 健康检查使用较短超时
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    # 发送简单的健康检查请求
                    async with session.get(f"{api_url}/health") as response:
                        health_status[api_url] = response.status == 200
            except Exception:
                health_status[api_url] = False
        
        return health_status
