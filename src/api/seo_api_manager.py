"""
SEO API管理器
管理两个SEO API接口，确保严格串行请求，支持故障转移
"""

import asyncio
import aiohttp
import time
from typing import Dict, List, Optional, Any, Set
from datetime import datetime
import logging

from ..utils.log_security import LogSecurity


class SEOAPIManager:
    """SEO API串行管理器"""
    
    def __init__(self, api_urls: List[str], interval: float = 1.0,
                 batch_size: int = 5, timeout: int = 30):
        """
        初始化SEO API管理器 - 增强端点管理

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

        # 端点健康状态跟踪
        self.endpoint_health = {i: {'healthy': True, 'failures': 0, 'last_check': 0}
                               for i in range(len(api_urls))}
        self.max_failures = 3  # 连续失败阈值
        self.health_check_interval = 300  # 5分钟重新检查不健康端点

        # 智能端点选择：优先使用k3.seokey.vip
        self.current_api_index = self._select_best_endpoint()
        self.enable_failover = True  # 启用故障转移

        self.request_lock = asyncio.Lock()
        self.last_request_time = 0
        self.logger = logging.getLogger(__name__)

        # 记录使用的端点
        self.logger.info(f"🎯 选择端点: {self.api_urls[self.current_api_index]} (索引: {self.current_api_index})")

        # 统计信息
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'api_switches': 0,
            'total_keywords_queried': 0,
            'endpoint_failures': {i: 0 for i in range(len(api_urls))}
        }

        self.logger.info(f"SEO API管理器初始化完成，API端点: {len(api_urls)}个，故障转移: 启用")

    def _select_best_endpoint(self) -> int:
        """智能选择最佳端点"""
        # 优先选择k3.seokey.vip（已知稳定）
        for i, url in enumerate(self.api_urls):
            if 'k3.seokey.vip' in url and self.endpoint_health[i]['healthy']:
                return i

        # 如果k3不可用，选择其他健康端点
        for i, health in self.endpoint_health.items():
            if health['healthy']:
                return i

        # 如果都不健康，选择失败次数最少的
        return min(self.endpoint_health.keys(),
                  key=lambda x: self.endpoint_health[x]['failures'])

    def _mark_endpoint_failure(self, endpoint_index: int):
        """标记端点失败"""
        import time
        health = self.endpoint_health[endpoint_index]
        health['failures'] += 1
        self.stats['endpoint_failures'][endpoint_index] += 1

        if health['failures'] >= self.max_failures:
            health['healthy'] = False
            health['last_check'] = time.time()
            self.logger.warning(f"端点 {self.api_urls[endpoint_index]} 标记为不健康 (连续失败 {health['failures']} 次)")

    def _try_failover(self) -> bool:
        """尝试故障转移到其他端点"""
        if not self.enable_failover:
            return False

        # 检查是否有其他健康端点
        import time
        current_time = time.time()
        for i, health in self.endpoint_health.items():
            if i == self.current_api_index:
                continue

            # 重新检查之前不健康的端点
            if not health['healthy'] and (current_time - health['last_check']) > self.health_check_interval:
                health['healthy'] = True
                health['failures'] = 0
                self.logger.info(f"重新启用端点 {self.api_urls[i]} (健康检查间隔已过)")

            if health['healthy']:
                old_endpoint = self.api_urls[self.current_api_index]
                self.current_api_index = i
                self.stats['api_switches'] += 1
                self.logger.warning(f"🔄 故障转移: {old_endpoint} → {self.api_urls[i]}")
                return True

        return False

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
            # 减少冗余日志：只在大量关键词时显示INFO级别
            if len(keywords) > 50:
                self.logger.info(f"开始串行查询 {len(keywords)} 个关键词")
            else:
                self.logger.debug(f"开始串行查询 {len(keywords)} 个关键词")
            
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

                    # 不切换端点，直接记录失败的关键词
                    for keyword in batch:
                        results[keyword] = None
                
                # 更新总请求数
                self.stats['total_requests'] += 1
                
                # 批次间等待
                if i + self.batch_size < len(keywords):
                    await asyncio.sleep(self.interval)
            
            self.logger.info(f"串行查询完成，成功: {len([r for r in results.values() if r])}/{len(keywords)}")
            return results

    async def query_keywords_streaming(self, keywords: List[str],
                                     url_keywords_map: Dict[str, Set[str]] = None,
                                     storage_callback=None,
                                     submission_callback=None) -> Dict[str, Dict]:
        """
        流式查询关键词，支持实时存储和提交

        Args:
            keywords: 关键词列表
            url_keywords_map: URL到关键词的映射关系
            storage_callback: 存储回调函数 async def(keyword_data_list)
            submission_callback: 提交回调函数 async def(keyword_data_list)

        Returns:
            Dict[str, Dict]: 关键词到数据的映射
        """
        if not keywords:
            return {}

        self.logger.info(f"🔍 SEO数据查询: {len(keywords)} 个关键词")

        # 流式处理缓冲区
        storage_buffer = []
        submission_buffer = []
        results = {}
        processed_count = 0

        # 修复初始化问题：设置正确的初始时间
        if self.last_request_time == 0:
            self.last_request_time = time.time() - self.interval

        async with self.request_lock:
            self.logger.info(f"🔄 开始处理 {len(keywords)} 个关键词，分为 {(len(keywords) + self.batch_size - 1) // self.batch_size} 个批次")

            for i in range(0, len(keywords), self.batch_size):
                batch = keywords[i:i + self.batch_size]
                batch_num = i // self.batch_size + 1

                # 批次处理日志（仅调试模式）
                self.logger.debug(f"📋 处理批次 {batch_num}: {len(batch)} 个关键词")

                # 计算等待时间 - 添加保护机制
                current_time = time.time()
                time_since_last = current_time - self.last_request_time

                if time_since_last < self.interval:
                    wait_time = min(self.interval - time_since_last, self.interval)  # 限制最大等待时间
                    # 等待时间日志（仅调试模式）
                    self.logger.debug(f"⏱️ 等待 {wait_time:.2f} 秒")
                    await asyncio.sleep(wait_time)

                # 尝试当前API，支持故障转移
                batch_results = None
                max_retries = len(self.api_urls)  # 最多尝试所有端点

                for retry in range(max_retries):
                    try:
                        current_endpoint = self.api_urls[self.current_api_index]
                        self.logger.debug(f"查询批次 {i//self.batch_size + 1}: {len(batch)} 个关键词 (端点: {current_endpoint})")

                        batch_results = await self._send_request(batch)
                        self.logger.debug(f"批次查询完成: 收到 {len(batch_results)} 个结果")

                        # 成功时重置失败计数
                        self.endpoint_health[self.current_api_index]['failures'] = 0
                        break

                    except Exception as e:
                        self.logger.error(f"API {retry + 1} 请求失败: {e}")

                        # 标记当前端点失败
                        self._mark_endpoint_failure(self.current_api_index)

                        # 尝试故障转移
                        if retry < max_retries - 1:  # 不是最后一次尝试
                            if self._try_failover():
                                self.logger.info(f"故障转移成功，重试批次 {i//self.batch_size + 1}")
                                continue
                            else:
                                self.logger.error("无可用的健康端点，停止重试")
                                break
                        else:
                            self.logger.error(f"所有端点都已尝试，批次 {i//self.batch_size + 1} 失败")

                if batch_results is not None:
                    results.update(batch_results)
                    self.last_request_time = time.time()

                    # 流式处理：收集成功的数据
                    valid_count = 0
                    invalid_count = 0

                    for keyword, data in batch_results.items():
                        if data:  # 只处理成功的数据
                            processed_count += 1
                            valid_count += 1

                            keyword_data = {
                                "keyword": keyword,
                                "seo_data": data,
                                "timestamp": time.time()
                            }

                            # 添加到缓冲区
                            storage_buffer.append(keyword_data)
                            submission_buffer.append(keyword_data)

                            self.logger.debug(f"✅ 有效数据: {keyword} -> {data}")
                        else:
                            invalid_count += 1
                            self.logger.debug(f"📭 无搜索数据: {keyword} (API确认该关键词无搜索量数据)")

                    # 批次结果日志（仅调试模式）
                    self.logger.debug(f"📊 批次 {batch_num} 结果: 有效 {valid_count}, 无效 {invalid_count}, 缓冲区: 存储{len(storage_buffer)}/提交{len(submission_buffer)}")

                    # 累计进度日志（仅调试模式）
                    if processed_count > 0 and processed_count % 100 == 0:
                        self.logger.debug(f"📈 累计处理 {processed_count} 条有效数据")

                    # 每5条触发存储 (快速测试)
                    if len(storage_buffer) >= 5 and storage_callback:
                        self.logger.debug(f"💾 触发存储: {len(storage_buffer)} 条数据")
                        await storage_callback(storage_buffer.copy())
                        storage_buffer.clear()

                    # 每5条触发提交 (快速测试)
                    if len(submission_buffer) >= 5 and submission_callback:
                        self.logger.debug(f"📤 触发提交: {len(submission_buffer)} 条数据")
                        await submission_callback(submission_buffer.copy())
                        submission_buffer.clear()

                    # 更新统计
                    self.stats['successful_requests'] += 1
                    self.stats['total_keywords_queried'] += len(batch)
                else:
                    # 如果所有端点都失败，为这个批次创建空结果
                    for keyword in batch:
                        results[keyword] = None
                    self.logger.error(f"批次 {i//self.batch_size + 1} 完全失败，所有关键词标记为失败")
                    self.stats['failed_requests'] += 1

                self.stats['total_requests'] += 1

        # 处理剩余缓冲区数据
        if storage_buffer and storage_callback:
            self.logger.info(f"💾 最终存储: {len(storage_buffer)} 条数据")
            await storage_callback(storage_buffer)

        if submission_buffer and submission_callback:
            self.logger.info(f"📤 最终提交: {len(submission_buffer)} 条数据")
            await submission_callback(submission_buffer)

        self.logger.info(f"流式查询完成，处理 {processed_count} 条成功数据，总查询 {len(keywords)} 个关键词")
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
        
        url = f"{self.api_urls[self.current_api_index]}/api/keywords"
        params = {"keyword": ",".join(keywords)}
        
        # 完整的超时配置
        timeout = aiohttp.ClientTimeout(
            total=self.timeout,      # 总超时时间: 30秒
            connect=10,              # 连接超时时间: 10秒 (关键!)
            sock_read=15,            # 读取超时时间: 15秒
            sock_connect=5           # socket连接超时: 5秒
        )
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                # 简化日志
                self.logger.debug(f"HTTP请求: {url}")
                self.logger.debug(f"关键词: {list(keywords)}")

                async with session.get(url, params=params) as response:
                    self.logger.debug(f"HTTP响应: {response.status}")
                    if response.status == 200:
                        data = await response.json()
                        # 添加原始响应调试
                        self.logger.debug(f"🔍 API原始响应: {data}")
                        result = self._parse_response(data, keywords)
                        valid_count = len([r for r in result.values() if r])
                        self.logger.debug(f"📊 解析结果: {valid_count}/{len(result)} 个有效数据")
                        return result
                    else:
                        error_text = await response.text()
                        self.logger.error(f"API错误响应: {response.status} - {error_text[:100]}{'...' if len(error_text) > 100 else ''}")
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
            Dict[str, Dict]: 解析后的数据，包含状态信息
        """
        results = {}

        try:
            # 根据实际API响应格式解析
            if isinstance(data, dict) and 'data' in data and isinstance(data['data'], list):
                # 实际API响应格式: {"status": "success", "data": [{"keyword": "...", "metrics": {...}}]}

                # 检查API是否确认无数据
                total_results = data.get('total_results', len(data['data']))
                api_status = data.get('status', 'unknown')

                self.logger.debug(f"API响应状态: {api_status}, 总结果数: {total_results}, 数据项数: {len(data['data'])}")

                # 先初始化所有关键词为None
                for keyword in keywords:
                    results[keyword] = None

                # 如果API确认无数据（total_results=0且data为空）
                if total_results == 0 and len(data['data']) == 0:
                    # 记录API确认无数据的关键词
                    for keyword in keywords:
                        self.logger.debug(f"📭 API确认无数据: {keyword} (total_results=0)")
                else:
                    # 解析data数组中的关键词数据
                    for item in data['data']:
                        if isinstance(item, dict) and 'keyword' in item and 'metrics' in item:
                            keyword = item['keyword']
                            metrics = item['metrics']

                            # 检查关键词是否在请求列表中
                            if keyword in keywords:
                                if self._is_valid_keyword_data(metrics):
                                    results[keyword] = metrics
                                    self.logger.debug(f"✅ 解析成功: {keyword}")
                                else:
                                    self.logger.debug(f"❌ 数据验证失败: {keyword} -> {metrics}")
                            else:
                                self.logger.debug(f"⚠️ 意外的关键词: {keyword}")

                    # 检查是否有关键词在API响应中缺失（部分无数据）
                    returned_keywords = {item.get('keyword') for item in data['data']
                                       if isinstance(item, dict) and 'keyword' in item}
                    for keyword in keywords:
                        if keyword not in returned_keywords and results[keyword] is None:
                            self.logger.debug(f"📭 API未返回该关键词: {keyword}")

            else:
                # 如果响应格式不符合预期，标记所有关键词为失败
                self.logger.warning(f"⚠️ API响应格式不符合预期: {type(data)}")
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
        验证关键词数据是否有效 - 放宽验证条件

        Args:
            data: 关键词数据

        Returns:
            bool: 数据是否有效
        """
        # 放宽验证：只要不是None且是dict就认为有效
        if data is None:
            return False

        if not isinstance(data, dict):
            return False

        # 只要有任何数据就认为有效
        return len(data) > 0
    
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
