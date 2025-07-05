"""
进度跟踪工具
用于跟踪关键词批量查询的进度和状态
"""

import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
import logging


@dataclass
class BatchProgress:
    """单个批次的进度信息"""
    batch_id: int
    keywords: List[str]
    status: str = "pending"  # pending, processing, completed, failed
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    api_endpoint: Optional[str] = None
    error_message: Optional[str] = None
    results: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration(self) -> Optional[float]:
        """计算批次处理时长"""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None
    
    @property
    def is_completed(self) -> bool:
        """检查批次是否已完成"""
        return self.status in ["completed", "failed"]


class ProgressTracker:
    """关键词查询进度跟踪器"""
    
    def __init__(self, total_keywords: List[str], batch_size: int = 5):
        """
        初始化进度跟踪器
        
        Args:
            total_keywords: 所有关键词列表
            batch_size: 批次大小
        """
        self.total_keywords = total_keywords
        self.batch_size = batch_size
        self.total_batches = (len(total_keywords) + batch_size - 1) // batch_size
        
        # 创建批次
        self.batches: List[BatchProgress] = []
        for i in range(0, len(total_keywords), batch_size):
            batch_keywords = total_keywords[i:i + batch_size]
            batch_id = len(self.batches)
            self.batches.append(BatchProgress(
                batch_id=batch_id,
                keywords=batch_keywords
            ))
        
        # 统计信息
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.current_batch_index = 0
        
        # 回调函数
        self.progress_callbacks: List[Callable] = []
        
        # 日志
        self.logger = logging.getLogger(__name__)
        
        self.logger.info(f"进度跟踪器初始化完成: {len(total_keywords)}个关键词, {self.total_batches}个批次")
    
    def add_progress_callback(self, callback: Callable) -> None:
        """
        添加进度回调函数
        
        Args:
            callback: 回调函数，接收ProgressTracker实例作为参数
        """
        self.progress_callbacks.append(callback)
    
    def start_batch(self, batch_id: int, api_endpoint: str) -> None:
        """
        开始处理批次
        
        Args:
            batch_id: 批次ID
            api_endpoint: 使用的API端点
        """
        if batch_id < len(self.batches):
            batch = self.batches[batch_id]
            batch.status = "processing"
            batch.start_time = time.time()
            batch.api_endpoint = api_endpoint
            
            self.current_batch_index = batch_id
            
            self.logger.info(f"开始处理批次 {batch_id + 1}/{self.total_batches}: {len(batch.keywords)}个关键词")
            self._notify_callbacks()
    
    def complete_batch(self, batch_id: int, results: Dict[str, Any], 
                      success: bool = True, error_message: Optional[str] = None) -> None:
        """
        完成批次处理
        
        Args:
            batch_id: 批次ID
            results: 查询结果
            success: 是否成功
            error_message: 错误信息（如果失败）
        """
        if batch_id < len(self.batches):
            batch = self.batches[batch_id]
            batch.end_time = time.time()
            batch.results = results
            batch.status = "completed" if success else "failed"
            batch.error_message = error_message
            
            status_text = "成功" if success else "失败"
            self.logger.info(f"批次 {batch_id + 1}/{self.total_batches} 处理{status_text}")
            
            if error_message:
                self.logger.error(f"批次 {batch_id + 1} 错误: {error_message}")
            
            self._notify_callbacks()
    
    def get_progress_summary(self) -> Dict[str, Any]:
        """
        获取进度摘要
        
        Returns:
            Dict[str, Any]: 进度摘要信息
        """
        completed_batches = sum(1 for batch in self.batches if batch.is_completed)
        successful_batches = sum(1 for batch in self.batches if batch.status == "completed")
        failed_batches = sum(1 for batch in self.batches if batch.status == "failed")
        
        processed_keywords = sum(len(batch.keywords) for batch in self.batches if batch.is_completed)
        successful_keywords = sum(
            len([k for k, v in batch.results.items() if v is not None])
            for batch in self.batches if batch.status == "completed"
        )
        
        # 计算预计完成时间
        estimated_completion = None
        if completed_batches > 0 and completed_batches < self.total_batches:
            avg_batch_time = sum(
                batch.duration for batch in self.batches 
                if batch.duration is not None
            ) / completed_batches
            
            remaining_batches = self.total_batches - completed_batches
            estimated_seconds = remaining_batches * (avg_batch_time + 60)  # 包含60秒间隔
            estimated_completion = datetime.now() + timedelta(seconds=estimated_seconds)
        
        # 计算总耗时
        current_time = self.end_time or time.time()
        total_duration = current_time - self.start_time
        
        return {
            "total_keywords": len(self.total_keywords),
            "processed_keywords": processed_keywords,
            "successful_keywords": successful_keywords,
            "failed_keywords": processed_keywords - successful_keywords,
            "total_batches": self.total_batches,
            "completed_batches": completed_batches,
            "successful_batches": successful_batches,
            "failed_batches": failed_batches,
            "current_batch": self.current_batch_index + 1,
            "progress_percentage": (completed_batches / self.total_batches) * 100,
            "success_rate": (successful_keywords / max(processed_keywords, 1)) * 100,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "estimated_completion": estimated_completion.isoformat() if estimated_completion else None,
            "total_duration_seconds": total_duration,
            "is_completed": completed_batches == self.total_batches
        }
    
    def get_batch_details(self) -> List[Dict[str, Any]]:
        """
        获取所有批次的详细信息
        
        Returns:
            List[Dict[str, Any]]: 批次详细信息列表
        """
        details = []
        for batch in self.batches:
            batch_info = {
                "batch_id": batch.batch_id + 1,
                "keywords": batch.keywords,
                "status": batch.status,
                "api_endpoint": batch.api_endpoint,
                "start_time": datetime.fromtimestamp(batch.start_time).isoformat() if batch.start_time else None,
                "end_time": datetime.fromtimestamp(batch.end_time).isoformat() if batch.end_time else None,
                "duration_seconds": batch.duration,
                "results_count": len([v for v in batch.results.values() if v is not None]) if batch.results else 0,
                "error_message": batch.error_message
            }
            details.append(batch_info)
        
        return details
    
    def mark_completed(self) -> None:
        """标记整个查询过程完成"""
        self.end_time = time.time()
        total_duration = self.end_time - self.start_time
        
        summary = self.get_progress_summary()
        self.logger.info(f"关键词查询完成! 总耗时: {total_duration:.2f}秒")
        self.logger.info(f"成功率: {summary['success_rate']:.1f}% ({summary['successful_keywords']}/{summary['total_keywords']})")
        
        self._notify_callbacks()
    
    def _notify_callbacks(self) -> None:
        """通知所有回调函数"""
        for callback in self.progress_callbacks:
            try:
                callback(self)
            except Exception as e:
                self.logger.error(f"进度回调函数执行失败: {e}")
    
    def print_progress(self) -> None:
        """打印当前进度（用于控制台输出）"""
        summary = self.get_progress_summary()
        
        print(f"\n{'='*60}")
        print(f"关键词查询进度")
        print(f"{'='*60}")
        print(f"总关键词数: {summary['total_keywords']}")
        print(f"已处理: {summary['processed_keywords']} ({summary['progress_percentage']:.1f}%)")
        print(f"成功: {summary['successful_keywords']}")
        print(f"失败: {summary['failed_keywords']}")
        print(f"当前批次: {summary['current_batch']}/{summary['total_batches']}")
        print(f"成功率: {summary['success_rate']:.1f}%")
        
        if summary['estimated_completion']:
            print(f"预计完成时间: {summary['estimated_completion']}")
        
        if summary['is_completed']:
            print(f"总耗时: {summary['total_duration_seconds']:.2f}秒")
            print("✅ 查询已完成!")
        
        print(f"{'='*60}")


def create_console_progress_callback() -> Callable:
    """
    创建控制台进度回调函数
    
    Returns:
        Callable: 进度回调函数
    """
    def callback(tracker: ProgressTracker):
        tracker.print_progress()
    
    return callback


async def demo_progress_tracker():
    """演示进度跟踪器的使用"""
    # 模拟关键词列表
    keywords = [f"keyword_{i}" for i in range(1, 23)]  # 22个关键词，需要5个批次
    
    # 创建进度跟踪器
    tracker = ProgressTracker(keywords, batch_size=5)
    
    # 添加控制台输出回调
    tracker.add_progress_callback(create_console_progress_callback())
    
    # 模拟批次处理
    for i, batch in enumerate(tracker.batches):
        tracker.start_batch(i, f"https://api{i%2+1}.example.com")
        
        # 模拟处理时间
        await asyncio.sleep(2)
        
        # 模拟结果
        results = {keyword: {"data": f"result_for_{keyword}"} for keyword in batch.keywords}
        
        # 模拟偶尔的失败
        success = i != 2  # 第3个批次失败
        error_msg = "模拟API错误" if not success else None
        
        tracker.complete_batch(i, results, success, error_msg)
        
        # 模拟60秒间隔（这里用3秒代替）
        if i < len(tracker.batches) - 1:
            print("等待60秒间隔...")
            await asyncio.sleep(3)
    
    tracker.mark_completed()


if __name__ == "__main__":
    asyncio.run(demo_progress_tracker())
