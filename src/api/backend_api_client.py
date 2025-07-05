"""
后端API客户端
负责批量提交数据到后端系统，支持认证和重试
"""

import aiohttp
import asyncio
from typing import List, Dict, Optional, Any
from tenacity import retry, stop_after_attempt, wait_exponential
import logging
import json
from datetime import datetime

from ..utils.log_security import LogSecurity


class BackendAPIClient:
    """后端API客户端"""
    
    def __init__(self, api_url: str, auth_token: Optional[str] = None,
                 batch_size: int = 100, max_retries: int = 3, timeout: int = 30):
        """
        初始化后端API客户端

        Args:
            api_url: 后端API URL
            auth_token: 认证令牌
            batch_size: 批量提交大小
            max_retries: 最大重试次数
            timeout: 请求超时时间（秒）
        """
        # 清理URL中的换行符和回车符（修复aiohttp安全检查问题）
        self.api_url = self._sanitize_url(api_url)
        self.auth_token = self._sanitize_token(auth_token)
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)
        
        # 统计信息
        self.stats = {
            'total_submissions': 0,
            'successful_submissions': 0,
            'failed_submissions': 0,
            'total_records': 0,
            'successful_records': 0
        }
        
        # 使用安全日志记录，隐藏敏感URL
        safe_url = LogSecurity.sanitize_url(api_url)
        self.logger.info(f"后端API客户端初始化完成: {safe_url}")

    def _sanitize_url(self, url: str) -> str:
        """
        清理URL中的换行符和回车符

        Args:
            url: 原始URL

        Returns:
            str: 清理后的URL
        """
        if not url:
            return ""

        # 移除换行符、回车符和其他控制字符
        cleaned_url = url.strip().replace('\n', '').replace('\r', '').replace('\t', '')

        # 确保URL格式正确
        if cleaned_url and not cleaned_url.startswith(('http://', 'https://')):
            self.logger.warning(f"URL格式可能不正确: {cleaned_url}")

        return cleaned_url.rstrip('/')

    def _sanitize_token(self, token: Optional[str]) -> Optional[str]:
        """
        清理认证令牌中的换行符和回车符

        Args:
            token: 原始令牌

        Returns:
            Optional[str]: 清理后的令牌
        """
        if not token:
            return None

        # 移除换行符、回车符和其他控制字符
        return token.strip().replace('\n', '').replace('\r', '').replace('\t', '')
    
    async def submit_batch(self, data: List[Dict]) -> bool:
        """
        批量提交数据
        
        Args:
            data: 待提交的数据列表
            
        Returns:
            bool: 是否全部提交成功
        """
        if not data:
            self.logger.warning("没有数据需要提交")
            return True
        
        self.logger.info(f"开始批量提交 {len(data)} 条数据")
        
        # 准备请求头
        headers = self._prepare_headers()
        
        # 分批处理
        all_success = True
        for i in range(0, len(data), self.batch_size):
            batch = data[i:i + self.batch_size]
            
            try:
                success = await self._submit_single_batch(batch, headers)
                if success:
                    self.stats['successful_submissions'] += 1
                    self.stats['successful_records'] += len(batch)
                    self.logger.info(f"批次 {i//self.batch_size + 1} 提交成功 ({len(batch)} 条)")
                else:
                    self.stats['failed_submissions'] += 1
                    all_success = False
                    self.logger.error(f"批次 {i//self.batch_size + 1} 提交失败")
                    
            except Exception as e:
                self.stats['failed_submissions'] += 1
                all_success = False
                self.logger.error(f"批次 {i//self.batch_size + 1} 提交异常: {e}")
            
            # 更新总统计
            self.stats['total_submissions'] += 1
            self.stats['total_records'] += len(batch)
        
        success_rate = (self.stats['successful_records'] / max(self.stats['total_records'], 1)) * 100
        self.logger.info(f"批量提交完成，成功率: {success_rate:.1f}%")
        
        return all_success
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def _submit_single_batch(self, batch: List[Dict], headers: Dict[str, str]) -> bool:
        """
        提交单个批次，带重试机制
        
        Args:
            batch: 数据批次
            headers: 请求头
            
        Returns:
            bool: 是否提交成功
            
        Raises:
            Exception: 提交失败时抛出异常触发重试
        """
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                # 准备提交数据
                submit_data = self._prepare_submit_data(batch)
                
                # 使用安全日志记录，隐藏敏感URL
                safe_url = LogSecurity.sanitize_url(self.api_url)
                self.logger.debug(f"提交数据到: {safe_url}")
                
                async with session.post(
                    self.api_url,
                    json=submit_data,
                    headers=headers
                ) as response:
                    
                    if response.status == 200:
                        response_data = await response.json()
                        return self._validate_response(response_data)
                    elif response.status == 201:
                        # 创建成功
                        return True
                    else:
                        error_text = await response.text()
                        self.logger.error(f"提交失败: {response.status} - {error_text}")
                        raise Exception(f"HTTP {response.status}: {error_text}")
                        
            except asyncio.TimeoutError:
                error_msg = f"请求超时 ({self.timeout}秒)"
                self.logger.error(error_msg)
                raise Exception(error_msg)
            except aiohttp.ClientError as e:
                error_msg = f"网络请求错误: {e}"
                self.logger.error(error_msg)
                raise Exception(error_msg)
    
    def _prepare_headers(self) -> Dict[str, str]:
        """
        准备请求头
        
        Returns:
            Dict[str, str]: 请求头字典
        """
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'SitemapKeywordAnalyzer/1.0'
        }
        
        if self.auth_token:
            headers['Authorization'] = f'Bearer {self.auth_token}'
        
        return headers
    
    def _prepare_submit_data(self, batch: List[Dict]) -> Dict[str, Any]:
        """
        准备提交数据格式
        
        Args:
            batch: 原始数据批次
            
        Returns:
            Dict[str, Any]: 格式化的提交数据
        """
        return {
            'data': batch,
            'timestamp': datetime.now().isoformat(),
            'source': 'sitemap_keyword_analyzer',
            'batch_size': len(batch)
        }
    
    def _validate_response(self, response_data: Any) -> bool:
        """
        验证响应数据
        
        Args:
            response_data: 响应数据
            
        Returns:
            bool: 响应是否有效
        """
        if isinstance(response_data, dict):
            # 检查是否有成功标识
            if 'success' in response_data:
                return response_data['success'] is True
            elif 'status' in response_data:
                return response_data['status'] == 'success'
            else:
                # 如果没有明确的成功标识，认为成功
                return True
        
        # 非字典响应，认为成功
        return True
    
    async def test_connection(self) -> bool:
        """
        测试与后端API的连接

        Returns:
            bool: 连接是否正常
        """
        try:
            headers = self._prepare_headers()
            timeout = aiohttp.ClientTimeout(total=10)

            # 清理URL，确保没有换行符或回车符
            clean_api_url = self._sanitize_url(self.api_url)
            test_url = f"{clean_api_url}/health"

            # 清理headers，确保没有换行符或回车符
            clean_headers = self._sanitize_headers(headers)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(test_url, headers=clean_headers) as response:
                    if response.status in [200, 404]:  # 404也算连接正常
                        self.logger.info("后端API连接测试成功")
                        return True
                    else:
                        self.logger.warning(f"后端API连接测试失败: HTTP {response.status}")
                        return False

        except Exception as e:
            self.logger.error(f"后端API连接测试异常: {e}")
            return False

    def _sanitize_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """
        清理HTTP头中的换行符和回车符

        Args:
            headers: 原始HTTP头

        Returns:
            Dict[str, str]: 清理后的HTTP头
        """
        clean_headers = {}
        for key, value in headers.items():
            # 清理key和value中的控制字符
            clean_key = str(key).strip().replace('\n', '').replace('\r', '').replace('\t', '')
            clean_value = str(value).strip().replace('\n', '').replace('\r', '').replace('\t', '')

            if clean_key and clean_value:  # 只保留非空的头
                clean_headers[clean_key] = clean_value

        return clean_headers
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        stats = self.stats.copy()
        
        if self.stats['total_submissions'] > 0:
            stats['submission_success_rate'] = (
                self.stats['successful_submissions'] / self.stats['total_submissions'] * 100
            )
        else:
            stats['submission_success_rate'] = 0
        
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
            'total_submissions': 0,
            'successful_submissions': 0,
            'failed_submissions': 0,
            'total_records': 0,
            'successful_records': 0
        }
        self.logger.info("统计信息已重置")
    
    async def submit_single_record(self, record: Dict) -> bool:
        """
        提交单条记录
        
        Args:
            record: 单条记录
            
        Returns:
            bool: 是否提交成功
        """
        return await self.submit_batch([record])
