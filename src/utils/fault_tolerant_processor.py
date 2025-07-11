"""
容错处理器
实现批次失败容错、重试机制和优雅降级
"""

import asyncio
import time
import random
from typing import List, Dict, Any, Optional, Callable, Set
from dataclasses import dataclass
import logging

from ..utils.log_security import LogSecurity


@dataclass
class BatchResult:
    """批次处理结果"""
    batch_id: int
    keywords: List[str]
    success: bool
    results: Dict[str, Any]
    error: Optional[str] = None
    retry_count: int = 0
    processing_time: float = 0.0


@dataclass
class ProcessingStats:
    """处理统计信息"""
    total_batches: int = 0
    successful_batches: int = 0
    failed_batches: int = 0
    retried_batches: int = 0
    total_keywords: int = 0
    successful_keywords: int = 0
    failed_keywords: int = 0
    total_processing_time: float = 0.0
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_batches == 0:
            return 0.0
        return self.successful_batches / self.total_batches
    
    @property
    def keyword_success_rate(self) -> float:
        """关键词成功率"""
        if self.total_keywords == 0:
            return 0.0
        return self.successful_keywords / self.total_keywords


class FaultTolerantProcessor:
    """容错处理器"""
    
    def __init__(self,
                 max_retries: int = 3,
                 retry_delay_base: float = 1.0,
                 retry_delay_max: float = 60.0,
                 failure_threshold: float = 0.5,  # 失败率阈值
                 circuit_breaker_threshold: int = 10,  # 连续失败阈值
                 enable_exponential_backoff: bool = True):
        """
        初始化容错处理器
        
        Args:
            max_retries: 最大重试次数
            retry_delay_base: 基础重试延迟（秒）
            retry_delay_max: 最大重试延迟（秒）
            failure_threshold: 失败率阈值，超过此值触发降级
            circuit_breaker_threshold: 连续失败次数阈值
            enable_exponential_backoff: 是否启用指数退避
        """
        self.max_retries = max_retries
        self.retry_delay_base = retry_delay_base
        self.retry_delay_max = retry_delay_max
        self.failure_threshold = failure_threshold
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.enable_exponential_backoff = enable_exponential_backoff
        
        self.stats = ProcessingStats()
        self.failed_batches: List[BatchResult] = []
        self.consecutive_failures = 0
        self.circuit_breaker_open = False
        self.circuit_breaker_open_time = 0.0
        self.circuit_breaker_timeout = 300.0  # 5分钟后重试
        
        self.logger = logging.getLogger(__name__)
        
        self.logger.info(f"🛡️ 容错处理器初始化: 最大重试={max_retries}, "
                        f"失败阈值={failure_threshold:.1%}, "
                        f"熔断阈值={circuit_breaker_threshold}")
    
    def _calculate_retry_delay(self, retry_count: int) -> float:
        """计算重试延迟"""
        if not self.enable_exponential_backoff:
            return self.retry_delay_base
        
        # 指数退避 + 随机抖动
        delay = self.retry_delay_base * (2 ** retry_count)
        delay = min(delay, self.retry_delay_max)
        
        # 添加随机抖动（±20%）
        jitter = delay * 0.2 * (random.random() - 0.5)
        delay += jitter
        
        return max(0.1, delay)
    
    def _should_open_circuit_breaker(self) -> bool:
        """检查是否应该打开熔断器"""
        return self.consecutive_failures >= self.circuit_breaker_threshold
    
    def _should_close_circuit_breaker(self) -> bool:
        """检查是否应该关闭熔断器"""
        if not self.circuit_breaker_open:
            return False
        
        elapsed = time.time() - self.circuit_breaker_open_time
        return elapsed > self.circuit_breaker_timeout
    
    def _update_circuit_breaker(self, success: bool):
        """更新熔断器状态"""
        if success:
            self.consecutive_failures = 0
            if self.circuit_breaker_open:
                self.circuit_breaker_open = False
                self.logger.info("🔓 熔断器关闭，恢复正常处理")
        else:
            self.consecutive_failures += 1
            
            if not self.circuit_breaker_open and self._should_open_circuit_breaker():
                self.circuit_breaker_open = True
                self.circuit_breaker_open_time = time.time()
                self.logger.warning(f"🔒 熔断器打开: 连续失败 {self.consecutive_failures} 次")
    
    async def process_batch_with_retry(self,
                                     batch_id: int,
                                     keywords: List[str],
                                     process_func: Callable,
                                     *args, **kwargs) -> BatchResult:
        """
        带重试的批次处理
        
        Args:
            batch_id: 批次ID
            keywords: 关键词列表
            process_func: 处理函数
            *args, **kwargs: 传递给处理函数的参数
            
        Returns:
            BatchResult: 批次处理结果
        """
        # 检查熔断器状态
        if self.circuit_breaker_open:
            if self._should_close_circuit_breaker():
                self.logger.info("🔄 尝试关闭熔断器")
            else:
                self.logger.warning(f"⚡ 熔断器开启，跳过批次 {batch_id}")
                return BatchResult(
                    batch_id=batch_id,
                    keywords=keywords,
                    success=False,
                    results={},
                    error="熔断器开启"
                )
        
        start_time = time.time()
        last_error = None
        
        for retry_count in range(self.max_retries + 1):
            try:
                # 如果是重试，先等待
                if retry_count > 0:
                    delay = self._calculate_retry_delay(retry_count - 1)
                    self.logger.info(f"🔄 批次 {batch_id} 第 {retry_count} 次重试 "
                                   f"(延迟 {delay:.1f}s)")
                    await asyncio.sleep(delay)
                
                # 执行处理函数
                results = await process_func(*args, **kwargs)
                
                # 成功处理
                processing_time = time.time() - start_time
                self._update_circuit_breaker(True)
                
                # 统计成功的关键词数量
                successful_keywords = len([r for r in results.values() if r is not None])
                
                batch_result = BatchResult(
                    batch_id=batch_id,
                    keywords=keywords,
                    success=True,
                    results=results,
                    retry_count=retry_count,
                    processing_time=processing_time
                )
                
                if retry_count > 0:
                    self.logger.info(f"✅ 批次 {batch_id} 重试成功 "
                                   f"(第 {retry_count} 次重试)")
                
                return batch_result
                
            except Exception as e:
                last_error = str(e)
                self.logger.warning(f"❌ 批次 {batch_id} 处理失败 "
                                  f"(尝试 {retry_count + 1}/{self.max_retries + 1}): {e}")
                
                # 如果是最后一次尝试，记录失败
                if retry_count == self.max_retries:
                    self._update_circuit_breaker(False)
                    break
        
        # 所有重试都失败了
        processing_time = time.time() - start_time
        
        batch_result = BatchResult(
            batch_id=batch_id,
            keywords=keywords,
            success=False,
            results={keyword: None for keyword in keywords},
            error=last_error,
            retry_count=self.max_retries,
            processing_time=processing_time
        )
        
        self.failed_batches.append(batch_result)
        
        return batch_result
    
    def update_stats(self, batch_result: BatchResult):
        """更新统计信息"""
        self.stats.total_batches += 1
        self.stats.total_keywords += len(batch_result.keywords)
        self.stats.total_processing_time += batch_result.processing_time
        
        if batch_result.success:
            self.stats.successful_batches += 1
            # 统计成功的关键词
            successful_count = len([r for r in batch_result.results.values() if r is not None])
            self.stats.successful_keywords += successful_count
            self.stats.failed_keywords += len(batch_result.keywords) - successful_count
        else:
            self.stats.failed_batches += 1
            self.stats.failed_keywords += len(batch_result.keywords)
            
        if batch_result.retry_count > 0:
            self.stats.retried_batches += 1
    
    def should_continue_processing(self) -> bool:
        """检查是否应该继续处理"""
        # 如果还没有足够的样本，继续处理
        if self.stats.total_batches < 10:
            return True
        
        # 检查失败率是否超过阈值
        if self.stats.success_rate < (1 - self.failure_threshold):
            self.logger.warning(f"⚠️ 失败率过高: {(1-self.stats.success_rate):.1%}, "
                              f"阈值: {self.failure_threshold:.1%}")
            return False
        
        return True
    
    def get_failed_keywords(self) -> Set[str]:
        """获取所有失败的关键词"""
        failed_keywords = set()
        for batch_result in self.failed_batches:
            failed_keywords.update(batch_result.keywords)
        return failed_keywords
    
    def get_stats_summary(self) -> str:
        """获取统计摘要"""
        return (f"处理统计: 批次 {self.stats.successful_batches}/{self.stats.total_batches} "
               f"({self.stats.success_rate:.1%}), "
               f"关键词 {self.stats.successful_keywords}/{self.stats.total_keywords} "
               f"({self.stats.keyword_success_rate:.1%}), "
               f"重试 {self.stats.retried_batches} 次, "
               f"平均耗时 {self.stats.total_processing_time/max(1,self.stats.total_batches):.1f}s")
