"""
简化的后端API客户端
直接提交URL-关键词映射，支持gzip压缩和批量处理
"""

import asyncio
import aiohttp
import gzip
import json
import os
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

from ..utils import get_logger, TimingLogger


class SimplifiedBackendClient:
    """简化的后端API客户端 - 直接提交URL-关键词映射"""
    
    def __init__(self, api_url: str = None, secret_key: str = None, 
                 batch_size: int = 100, timeout: int = 30):
        """
        初始化客户端
        
        Args:
            api_url: API端点URL
            secret_key: 认证密钥
            batch_size: 批量大小（默认100）
            timeout: 请求超时时间（秒）
        """
        self.api_url = api_url or os.getenv('SITEMAP_API_URL', 'http://localhost:5001/api/sitemap/keywords')
        self.secret_key = secret_key or os.getenv('SITEMAP_SECRET_KEY', 'your-secret-key-2024')
        self.batch_size = batch_size
        self.timeout = timeout
        self.logger = get_logger(__name__)
        
        # 统计信息
        self.total_submitted = 0
        self.total_batches = 0
        self.failed_batches = 0
        
        self.logger.info(f"初始化SimplifiedBackendClient: URL={self.api_url}, 批量大小={self.batch_size}")
    
    async def submit_url_keywords_mapping(self, url_keywords_map: Dict[str, Any]) -> bool:
        """
        提交URL-关键词映射
        
        Args:
            url_keywords_map: URL到关键词的映射
                - Dict[str, str]: 一对一映射
                - Dict[str, List[str]]: 一对多映射
                - Dict[str, Set[str]]: 一对多映射（集合）
        
        Returns:
            bool: 是否全部提交成功
        """
        with TimingLogger(self.logger, f"提交 {len(url_keywords_map)} 个URL"):
            # 转换数据格式
            flat_mapping = self._flatten_url_keywords_map(url_keywords_map)
            
            if not flat_mapping:
                self.logger.warning("没有数据需要提交")
                return True
            
            # 分批处理
            batches = self._create_batches(flat_mapping, self.batch_size)
            self.logger.info(f"分成 {len(batches)} 批提交，每批最多 {self.batch_size} 条")
            
            # 并发提交所有批次
            results = await self._submit_batches(batches)
            
            # 统计结果
            success_count = sum(1 for r in results if r)
            self.logger.info(f"提交完成: {success_count}/{len(batches)} 批成功")
            
            return success_count == len(batches)
    
    def _flatten_url_keywords_map(self, url_keywords_map: Dict[str, Any]) -> Dict[str, str]:
        """
        扁平化URL-关键词映射
        
        Args:
            url_keywords_map: 原始映射（可能包含集合或列表）
        
        Returns:
            Dict[str, str]: 扁平化的一对一映射
        """
        flat_mapping = {}
        
        for url, keywords in url_keywords_map.items():
            # 处理不同类型的关键词数据
            if isinstance(keywords, str):
                # 已经是字符串
                flat_mapping[url] = keywords
            elif isinstance(keywords, (list, set, tuple)):
                # 多个关键词：选择第一个或合并
                if keywords:
                    # 策略1：选择第一个关键词
                    # flat_mapping[url] = list(keywords)[0]
                    
                    # 策略2：用逗号合并所有关键词
                    flat_mapping[url] = ', '.join(sorted(keywords))
            else:
                self.logger.warning(f"跳过无效关键词类型 {type(keywords)} for URL: {url}")
        
        self.logger.debug(f"扁平化映射: {len(url_keywords_map)} -> {len(flat_mapping)} 条记录")
        return flat_mapping
    
    def _create_batches(self, flat_mapping: Dict[str, str], batch_size: int) -> List[Dict[str, str]]:
        """
        创建批次
        
        Args:
            flat_mapping: 扁平化的映射
            batch_size: 批量大小
        
        Returns:
            List[Dict[str, str]]: 批次列表
        """
        items = list(flat_mapping.items())
        batches = []
        
        for i in range(0, len(items), batch_size):
            batch = dict(items[i:i + batch_size])
            batches.append(batch)
        
        return batches
    
    async def _submit_batches(self, batches: List[Dict[str, str]]) -> List[bool]:
        """
        并发提交所有批次
        
        Args:
            batches: 批次列表
        
        Returns:
            List[bool]: 每批的提交结果
        """
        async with aiohttp.ClientSession() as session:
            tasks = [self._submit_single_batch(session, batch, i) for i, batch in enumerate(batches)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            processed_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self.logger.error(f"批次 {i+1} 提交异常: {result}")
                    processed_results.append(False)
                else:
                    processed_results.append(result)
            
            return processed_results
    
    async def _submit_single_batch(self, session: aiohttp.ClientSession, 
                                  batch: Dict[str, str], batch_index: int) -> bool:
        """
        提交单个批次
        
        Args:
            session: HTTP会话
            batch: 批次数据
            batch_index: 批次索引
        
        Returns:
            bool: 是否成功
        """
        try:
            # 准备请求数据
            request_data = {
                "key": self.secret_key,
                "data": batch
            }
            
            # JSON序列化
            json_data = json.dumps(request_data, ensure_ascii=False)
            json_bytes = json_data.encode('utf-8')
            
            # gzip压缩
            compressed_data = gzip.compress(json_bytes)
            
            # 记录压缩信息
            compression_ratio = len(compressed_data) / len(json_bytes) * 100
            self.logger.debug(f"批次 {batch_index + 1}: {len(batch)} 条, "
                            f"原始 {len(json_bytes)} 字节, "
                            f"压缩后 {len(compressed_data)} 字节 ({compression_ratio:.1f}%)")
            
            # 发送请求
            headers = {
                'Content-Type': 'application/json',
                'Content-Encoding': 'gzip'
            }
            
            async with session.post(
                self.api_url,
                data=compressed_data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                response_text = await response.text()
                
                if response.status == 200:
                    self.logger.info(f"✅ 批次 {batch_index + 1} 提交成功")
                    self.total_submitted += len(batch)
                    self.total_batches += 1
                    return True
                else:
                    self.logger.error(f"❌ 批次 {batch_index + 1} 提交失败: "
                                    f"状态码={response.status}, 响应={response_text}")
                    self.failed_batches += 1
                    return False
                    
        except asyncio.TimeoutError:
            self.logger.error(f"❌ 批次 {batch_index + 1} 提交超时")
            self.failed_batches += 1
            return False
        except Exception as e:
            self.logger.error(f"❌ 批次 {batch_index + 1} 提交异常: {e}")
            self.failed_batches += 1
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        return {
            'total_submitted': self.total_submitted,
            'total_batches': self.total_batches,
            'failed_batches': self.failed_batches,
            'success_rate': (self.total_batches - self.failed_batches) / self.total_batches * 100 
                           if self.total_batches > 0 else 0
        }
    
    async def test_connection(self) -> bool:
        """
        测试连接
        
        Returns:
            bool: 是否连接成功
        """
        try:
            test_data = {"test.example.com": "测试关键词"}
            self.logger.info(f"测试连接到 {self.api_url}")
            
            # 使用测试数据尝试提交
            result = await self.submit_url_keywords_mapping(test_data)
            
            if result:
                self.logger.info("✅ 连接测试成功")
            else:
                self.logger.warning("⚠️ 连接测试失败")
            
            return result
            
        except Exception as e:
            self.logger.error(f"连接测试异常: {e}")
            return False