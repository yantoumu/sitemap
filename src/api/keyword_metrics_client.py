"""
关键词指标提交客户端
负责将关键词指标数据批量提交到后端API，支持gzip压缩和异步处理
"""

import aiohttp
import asyncio
import gzip
import json
from typing import List, Dict, Any, Optional, Tuple
from tenacity import retry, stop_after_attempt, wait_exponential
import logging
from datetime import datetime


class KeywordMetricsClient:
    """关键词指标提交客户端"""
    
    def __init__(self, api_url: str, api_key: str, batch_size: int = 100, 
                 max_retries: int = 3, timeout: int = 60, enable_gzip: bool = True):
        """
        初始化关键词指标客户端
        
        Args:
            api_url: API基础URL
            api_key: API密钥
            batch_size: 批量提交大小
            max_retries: 最大重试次数
            timeout: 请求超时时间（秒）
            enable_gzip: 是否启用gzip压缩
        """
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.timeout = timeout
        self.enable_gzip = enable_gzip
        self.logger = logging.getLogger(__name__)

        # 构建完整的API端点，处理可能的双斜杠问题
        if '/api/v1/keyword-metrics/batch' in self.api_url:
            # 如果URL已经包含完整路径，直接使用
            self.submit_endpoint = self.api_url
        else:
            # 否则拼接路径
            self.submit_endpoint = f"{self.api_url}/api/v1/keyword-metrics/batch"
        
        # 统计信息
        self.stats = {
            'total_batches': 0,
            'successful_batches': 0,
            'failed_batches': 0,
            'total_records': 0,
            'successful_records': 0,
            'compression_ratio': 0.0
        }
        
        self.logger.info(f"关键词指标客户端初始化完成: {self.submit_endpoint}")
        if self.enable_gzip:
            self.logger.info("已启用gzip压缩")
    
    async def submit_keyword_metrics_batch(self, metrics_data: List[Dict[str, Any]]) -> bool:
        """
        批量提交关键词指标数据
        
        Args:
            metrics_data: 关键词指标数据列表
            
        Returns:
            bool: 是否全部提交成功
        """
        if not metrics_data:
            self.logger.warning("没有数据需要提交")
            return True
        
        self.logger.info(f"开始批量提交 {len(metrics_data)} 条关键词指标数据")
        
        # 分批处理
        all_success = True
        total_batches = (len(metrics_data) + self.batch_size - 1) // self.batch_size
        
        for i in range(0, len(metrics_data), self.batch_size):
            batch = metrics_data[i:i + self.batch_size]
            batch_num = i // self.batch_size + 1
            
            try:
                success = await self._submit_single_batch(batch, batch_num, total_batches)
                
                # 更新统计
                self.stats['total_batches'] += 1
                self.stats['total_records'] += len(batch)
                
                if success:
                    self.stats['successful_batches'] += 1
                    self.stats['successful_records'] += len(batch)
                    self.logger.info(f"批次 {batch_num}/{total_batches} 提交成功 ({len(batch)} 条)")
                else:
                    self.stats['failed_batches'] += 1
                    all_success = False
                    self.logger.error(f"批次 {batch_num}/{total_batches} 提交失败")
                    
            except Exception as e:
                self.stats['failed_batches'] += 1
                self.stats['total_batches'] += 1
                self.stats['total_records'] += len(batch)
                all_success = False
                self.logger.error(f"批次 {batch_num}/{total_batches} 提交异常: {e}")
        
        # 计算成功率
        success_rate = (self.stats['successful_records'] / max(self.stats['total_records'], 1)) * 100
        self.logger.info(f"批量提交完成，成功率: {success_rate:.1f}%")
        
        return all_success
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def _submit_single_batch(self, batch: List[Dict[str, Any]], 
                                  batch_num: int, total_batches: int) -> bool:
        """
        提交单个批次，带重试机制
        
        Args:
            batch: 数据批次
            batch_num: 批次编号
            total_batches: 总批次数
            
        Returns:
            bool: 是否提交成功
            
        Raises:
            Exception: 提交失败时抛出异常触发重试
        """
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                # 准备请求数据和头部
                headers, data = self._prepare_request(batch)
                
                self.logger.debug(f"提交批次 {batch_num}/{total_batches} 到: {self.submit_endpoint}")
                
                async with session.post(
                    self.submit_endpoint,
                    data=data,
                    headers=headers
                ) as response:
                    
                    if response.status == 200:
                        response_data = await response.json()
                        return self._validate_response(response_data)
                    else:
                        error_text = await response.text()
                        self.logger.error(f"提交失败: HTTP {response.status} - {error_text}")
                        raise Exception(f"HTTP {response.status}: {error_text}")
                        
            except asyncio.TimeoutError:
                error_msg = f"请求超时 ({self.timeout}秒)"
                self.logger.error(error_msg)
                raise Exception(error_msg)
            except aiohttp.ClientError as e:
                error_msg = f"网络请求错误: {e}"
                self.logger.error(error_msg)
                raise Exception(error_msg)
    
    def _prepare_request(self, batch: List[Dict[str, Any]]) -> Tuple[Dict[str, str], bytes]:
        """
        准备请求数据和头部
        
        Args:
            batch: 数据批次
            
        Returns:
            Tuple[Dict[str, str], bytes]: (请求头, 请求数据)
        """
        # 准备请求头
        headers = {
            'X-API-Key': self.api_key,
            'User-Agent': 'SitemapKeywordAnalyzer/1.0'
        }
        
        # 序列化数据
        json_data = json.dumps(batch, ensure_ascii=False)
        
        if self.enable_gzip:
            # 启用gzip压缩
            compressed_data = gzip.compress(json_data.encode('utf-8'))
            headers['Content-Type'] = 'application/json'
            headers['Content-Encoding'] = 'gzip'
            
            # 计算压缩比
            original_size = len(json_data.encode('utf-8'))
            compressed_size = len(compressed_data)
            compression_ratio = (1 - compressed_size / original_size) * 100
            self.stats['compression_ratio'] = compression_ratio
            
            self.logger.debug(f"数据压缩: {original_size} -> {compressed_size} bytes "
                            f"(压缩率: {compression_ratio:.1f}%)")
            
            return headers, compressed_data
        else:
            # 不压缩
            headers['Content-Type'] = 'application/json'
            return headers, json_data.encode('utf-8')
    
    def _validate_response(self, response_data: Any) -> bool:
        """
        验证响应数据
        
        Args:
            response_data: 响应数据
            
        Returns:
            bool: 响应是否有效
        """
        if isinstance(response_data, dict):
            # 根据API文档，成功响应的code为0
            if 'code' in response_data:
                success = response_data['code'] == 0
                if not success and 'message' in response_data:
                    self.logger.error(f"API返回错误: {response_data['message']}")
                return success
            else:
                # 如果没有code字段，检查其他成功标识
                return response_data.get('success', True)
        
        # 非字典响应，认为成功
        return True
    
    async def test_connection(self) -> bool:
        """
        测试与API的连接
        
        Returns:
            bool: 连接是否正常
        """
        try:
            headers = {
                'X-API-Key': self.api_key,
                'User-Agent': 'SitemapKeywordAnalyzer/1.0'
            }
            timeout = aiohttp.ClientTimeout(total=10)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # 发送空数据测试连接
                test_data = json.dumps([]).encode('utf-8')
                
                async with session.post(
                    self.submit_endpoint,
                    data=test_data,
                    headers={**headers, 'Content-Type': 'application/json'}
                ) as response:
                    
                    if response.status in [200, 400]:  # 400也算连接正常（空数据错误）
                        self.logger.info("关键词指标API连接测试成功")
                        return True
                    else:
                        self.logger.warning(f"关键词指标API连接测试失败: HTTP {response.status}")
                        return False
                        
        except Exception as e:
            self.logger.error(f"关键词指标API连接测试异常: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        stats = self.stats.copy()
        
        if self.stats['total_batches'] > 0:
            stats['batch_success_rate'] = (
                self.stats['successful_batches'] / self.stats['total_batches'] * 100
            )
        else:
            stats['batch_success_rate'] = 0
        
        if self.stats['total_records'] > 0:
            stats['record_success_rate'] = (
                self.stats['successful_records'] / self.stats['total_records'] * 100
            )
        else:
            stats['record_success_rate'] = 0
        
        return stats
    
    def reset_statistics(self) -> None:
        """重置统计信息"""
        self.stats = {
            'total_batches': 0,
            'successful_batches': 0,
            'failed_batches': 0,
            'total_records': 0,
            'successful_records': 0,
            'compression_ratio': 0.0
        }
        self.logger.info("统计信息已重置")
