"""
增强版SEO API管理器
支持增量保存、容错处理和长时间运行优化
"""

import asyncio
import aiohttp
import time
from typing import Dict, List, Optional, Any, Set, Callable
from datetime import datetime
import logging

from ..utils.log_security import LogSecurity
from ..utils.incremental_saver import IncrementalSaver
from ..utils.fault_tolerant_processor import FaultTolerantProcessor, BatchResult
from .seo_api_manager import SEOAPIManager


class EnhancedSEOAPIManager(SEOAPIManager):
    """增强版SEO API管理器"""
    
    def __init__(self, api_urls: List[str], interval: float = 1.0,
                 batch_size: int = 5, timeout: int = 30,
                 enable_incremental_save: bool = True,
                 enable_fault_tolerance: bool = True,
                 save_interval: int = 1000,
                 git_commit_interval: int = 5000,
                 max_runtime_hours: float = 5.5):
        """
        初始化增强版SEO API管理器
        
        Args:
            api_urls: API端点URL列表
            interval: 请求间隔（秒）
            batch_size: 批次大小
            timeout: 请求超时时间（秒）
            enable_incremental_save: 是否启用增量保存
            enable_fault_tolerance: 是否启用容错处理
            save_interval: 本地保存间隔（关键词数量）
            git_commit_interval: Git提交间隔（关键词数量）
            max_runtime_hours: 最大运行时间（小时）
        """
        # 调用父类初始化
        super().__init__(api_urls, interval, batch_size, timeout)
        
        # 增量保存器
        self.incremental_saver = None
        if enable_incremental_save:
            self.incremental_saver = IncrementalSaver(
                save_interval=save_interval,
                git_commit_interval=git_commit_interval,
                max_runtime_hours=max_runtime_hours
            )
        
        # 容错处理器
        self.fault_processor = None
        if enable_fault_tolerance:
            self.fault_processor = FaultTolerantProcessor(
                max_retries=2,  # 最多重试2次
                retry_delay_base=5.0,  # 基础延迟5秒
                failure_threshold=0.3,  # 30%失败率阈值
                circuit_breaker_threshold=5  # 连续5次失败触发熔断
            )
        
        # 处理状态
        self.total_processed_keywords = 0
        self.is_emergency_mode = False
        
        # 更新日志信息
        features = []
        if enable_incremental_save:
            features.append("增量保存")
        if enable_fault_tolerance:
            features.append("容错处理")
        
        feature_str = f", 功能: {', '.join(features)}" if features else ""
        
        self.logger.info(f"🚀 增强版SEO API管理器初始化完成{feature_str}")
    
    async def query_keywords_with_resilience(self,
                                           keywords: List[str],
                                           storage_callback: Optional[Callable] = None,
                                           submission_callback: Optional[Callable] = None) -> Dict[str, Dict]:
        """
        带弹性处理的关键词查询
        
        Args:
            keywords: 关键词列表
            storage_callback: 存储回调函数
            submission_callback: 提交回调函数
            
        Returns:
            Dict[str, Dict]: 查询结果
        """
        self.logger.info(f"🎯 开始弹性关键词查询: {len(keywords)} 个关键词")
        
        if self.incremental_saver:
            self.logger.info(f"⏱️ 运行时限制: {self.incremental_saver.max_runtime_seconds/3600:.1f} 小时")
        
        results = {}
        storage_buffer = []
        submission_buffer = []
        
        # 分批处理
        total_batches = (len(keywords) + self.batch_size - 1) // self.batch_size
        
        for i in range(0, len(keywords), self.batch_size):
            batch_num = i // self.batch_size + 1
            batch = keywords[i:i + self.batch_size]
            
            # 检查是否接近超时
            if self.incremental_saver and self.incremental_saver.is_approaching_timeout():
                self.logger.warning(f"🚨 接近超时限制，触发紧急保存")
                await self._emergency_save(storage_buffer, submission_buffer, 
                                         storage_callback, submission_callback)
                self.is_emergency_mode = True
                break
            
            # 获取端点
            endpoint_index = self._get_next_endpoint()
            
            # 处理批次
            if self.fault_processor:
                # 使用容错处理
                batch_result = await self.fault_processor.process_batch_with_retry(
                    batch_num, batch, self._send_request_to_endpoint, batch, endpoint_index
                )
                
                # 更新统计
                self.fault_processor.update_stats(batch_result)
                
                # 检查是否应该继续处理
                if not self.fault_processor.should_continue_processing():
                    self.logger.error(f"❌ 失败率过高，停止处理")
                    break
                
                batch_results = batch_result.results if batch_result.success else {}
                
            else:
                # 普通处理
                try:
                    batch_results = await self._send_request_to_endpoint(batch, endpoint_index)
                except Exception as e:
                    self.logger.error(f"❌ 批次 {batch_num} 处理失败: {e}")
                    batch_results = {keyword: None for keyword in batch}
            
            # 处理结果
            if batch_results:
                results.update(batch_results)
                
                # 统计有效数据
                valid_count = len([r for r in batch_results.values() if r is not None])
                self.total_processed_keywords += len(batch)
                
                if valid_count > 0:
                    self.logger.debug(f"✅ 批次 {batch_num}/{total_batches}: "
                                    f"{valid_count}/{len(batch)} 个有效结果")
                    
                    # 添加到缓冲区
                    for keyword, data in batch_results.items():
                        if data:
                            keyword_data = {
                                "keyword": keyword,
                                "seo_data": data,
                                "timestamp": time.time()
                            }
                            storage_buffer.append(keyword_data)
                            submission_buffer.append(keyword_data)
                
                # 增量保存检查
                if self.incremental_saver:
                    # 本地保存
                    if await self.incremental_saver.save_checkpoint(
                        self.total_processed_keywords, 
                        lambda: storage_callback(storage_buffer) if storage_callback and storage_buffer else None
                    ):
                        storage_buffer.clear()
                    
                    # Git提交
                    await self.incremental_saver.commit_to_git(self.total_processed_keywords)
                
                # 流式提交检查
                if len(submission_buffer) >= 100 and submission_callback:
                    self.logger.info(f"📤 流式提交: {len(submission_buffer)} 条数据")
                    await submission_callback(submission_buffer)
                    submission_buffer.clear()
            
            # 等待间隔
            await asyncio.sleep(self.interval)
        
        # 最终保存
        await self._final_save(storage_buffer, submission_buffer, 
                             storage_callback, submission_callback)
        
        # 输出统计信息
        self._log_final_stats()
        
        return results
    
    async def _emergency_save(self, storage_buffer, submission_buffer,
                            storage_callback, submission_callback):
        """紧急保存"""
        self.logger.warning(f"🚨 执行紧急保存")
        
        # 保存缓冲区数据
        if storage_buffer and storage_callback:
            await storage_callback(storage_buffer)
            storage_buffer.clear()
        
        if submission_buffer and submission_callback:
            await submission_callback(submission_buffer)
            submission_buffer.clear()
        
        # 增量保存器紧急保存
        if self.incremental_saver:
            await self.incremental_saver.emergency_save(
                reason="接近超时限制"
            )
    
    async def _final_save(self, storage_buffer, submission_buffer,
                        storage_callback, submission_callback):
        """最终保存"""
        # 保存剩余数据
        if storage_buffer and storage_callback:
            self.logger.info(f"💾 最终存储: {len(storage_buffer)} 条数据")
            await storage_callback(storage_buffer)
        
        if submission_buffer and submission_callback:
            self.logger.info(f"📤 最终提交: {len(submission_buffer)} 条数据")
            await submission_callback(submission_buffer)
        
        # 强制最终保存
        if self.incremental_saver:
            await self.incremental_saver.save_checkpoint(
                self.total_processed_keywords, force=True
            )
            await self.incremental_saver.commit_to_git(
                self.total_processed_keywords, force=True
            )
    
    def _log_final_stats(self):
        """输出最终统计信息"""
        if self.fault_processor:
            self.logger.info(f"📊 {self.fault_processor.get_stats_summary()}")
        
        if self.incremental_saver:
            self.logger.info(f"⏱️ {self.incremental_saver.get_progress_summary()}")
        
        if self.is_emergency_mode:
            self.logger.warning(f"⚠️ 任务在紧急模式下结束（接近超时）")
        else:
            self.logger.info(f"✅ 任务正常完成")
    
    def get_failed_keywords(self) -> Set[str]:
        """获取失败的关键词列表"""
        if self.fault_processor:
            return self.fault_processor.get_failed_keywords()
        return set()
    
    def get_enhanced_statistics(self) -> Dict[str, Any]:
        """获取增强统计信息"""
        stats = self.get_statistics()
        
        if self.fault_processor:
            stats['fault_tolerance'] = {
                'total_batches': self.fault_processor.stats.total_batches,
                'success_rate': self.fault_processor.stats.success_rate,
                'keyword_success_rate': self.fault_processor.stats.keyword_success_rate,
                'retried_batches': self.fault_processor.stats.retried_batches,
                'failed_keywords_count': len(self.get_failed_keywords())
            }
        
        if self.incremental_saver:
            runtime_info = self.incremental_saver.get_runtime_info()
            stats['runtime'] = {
                'elapsed_hours': runtime_info['elapsed_hours'],
                'remaining_hours': runtime_info['remaining_hours'],
                'is_approaching_timeout': runtime_info['is_approaching_timeout'],
                'total_processed': self.total_processed_keywords
            }
        
        stats['emergency_mode'] = self.is_emergency_mode
        
        return stats
