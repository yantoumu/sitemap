"""
任务执行器
负责独立的异步任务执行，遵循SOLID原则
"""

import asyncio
import copy
from typing import Dict, Set, Any, Optional
from abc import ABC, abstractmethod
import logging


class TaskResult:
    """任务结果封装"""
    
    def __init__(self, success: bool, data: Any = None, error: Optional[str] = None):
        self.success = success
        self.data = data
        self.error = error
        self.metadata = {}
    
    def add_metadata(self, key: str, value: Any) -> None:
        """添加元数据"""
        self.metadata[key] = value
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {
            'success': self.success,
            'error': self.error,
            'metadata': self.metadata
        }
        if self.data is not None:
            result.update(self.data)
        return result


class AsyncTask(ABC):
    """异步任务抽象基类"""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"{__name__}.{name}")
    
    @abstractmethod
    async def execute(self, data: Dict[str, Any]) -> TaskResult:
        """执行任务"""
        pass
    
    def validate_input(self, data: Dict[str, Any]) -> bool:
        """验证输入数据"""
        return True


class StorageTask(AsyncTask):
    """存储任务"""
    
    def __init__(self, storage_manager):
        super().__init__("StorageTask")
        self.storage = storage_manager
    
    def validate_input(self, data: Dict[str, Any]) -> bool:
        """验证存储任务输入"""
        required_keys = ['url_keywords_map', 'keyword_data']
        return all(key in data for key in required_keys)
    
    async def execute(self, data: Dict[str, Any]) -> TaskResult:
        """执行存储任务"""
        if not self.validate_input(data):
            return TaskResult(False, error="输入数据验证失败")
        
        try:
            # 创建数据副本，避免竞争
            url_keywords_map = copy.deepcopy(data['url_keywords_map'])
            keyword_data = copy.deepcopy(data['keyword_data'])
            
            self.logger.info(f"存储任务开始: {len(url_keywords_map)} 个URL")
            
            saved_count = 0
            failed_urls = []
            
            for url, keywords in url_keywords_map.items():
                try:
                    # 构建该URL的SEO数据
                    url_seo_data = {
                        keyword: keyword_data[keyword] 
                        for keyword in keywords 
                        if keyword in keyword_data
                    }
                    
                    if url_seo_data:
                        success = await self.storage.save_processed_url(
                            url, list(keywords), url_seo_data
                        )
                        if success:
                            saved_count += 1
                        else:
                            failed_urls.append(url)
                
                except Exception as e:
                    self.logger.warning(f"保存URL失败 {url}: {e}")
                    failed_urls.append(url)
            
            result = TaskResult(True, {
                'saved_count': saved_count,
                'failed_count': len(failed_urls)
            })
            
            result.add_metadata('failed_urls', failed_urls)
            result.add_metadata('total_urls', len(url_keywords_map))
            
            self.logger.info(f"存储任务完成: 成功 {saved_count}, 失败 {len(failed_urls)}")
            return result
            
        except Exception as e:
            self.logger.error(f"存储任务异常: {e}")
            return TaskResult(False, error=str(e))


class SubmitTask(AsyncTask):
    """提交任务"""
    
    def __init__(self, data_transformer, keyword_metrics_client, backend_api=None):
        super().__init__("SubmitTask")
        self.data_transformer = data_transformer
        self.keyword_metrics_client = keyword_metrics_client
        self.backend_api = backend_api
    
    def validate_input(self, data: Dict[str, Any]) -> bool:
        """验证提交任务输入"""
        required_keys = ['keyword_data', 'url_keywords_map']
        return all(key in data for key in required_keys)
    
    async def execute(self, data: Dict[str, Any]) -> TaskResult:
        """执行提交任务"""
        if not self.validate_input(data):
            return TaskResult(False, error="输入数据验证失败")
        
        try:
            # 使用引用传递，避免大数据集的深拷贝导致内存问题
            # 数据在此处是只读的，不需要深拷贝
            keyword_data = data['keyword_data']
            url_keywords_map = data['url_keywords_map']

            self.logger.info(f"提交任务开始: {len(keyword_data)} 个关键词")
            
            # 准备提交数据
            submit_data = await self._prepare_submit_data(keyword_data, url_keywords_map)
            
            if not submit_data:
                self.logger.info("提交任务: 没有数据需要提交")
                return TaskResult(True, {'submitted_count': 0})
            
            # 提交数据
            success = await self._submit_data(submit_data)
            submitted_count = len(submit_data) if success else 0
            
            result = TaskResult(success, {
                'submitted_count': submitted_count,
                'total_records': len(submit_data)
            })
            
            result.add_metadata('api_type', 'new' if self.keyword_metrics_client else 'legacy')
            
            self.logger.info(f"提交任务完成: {'成功' if success else '失败'} "
                           f"提交 {submitted_count} 条记录")
            
            return result
            
        except Exception as e:
            self.logger.error(f"提交任务异常: {e}")
            return TaskResult(False, error=str(e))
    
    async def _prepare_submit_data(self, keyword_data: Dict[str, Dict], 
                                  url_keywords_map: Dict[str, Set[str]]) -> list:
        """准备提交数据"""
        if self.keyword_metrics_client:
            # 使用新API格式
            query_response = {
                'status': 'success',
                'data': [
                    {'keyword': keyword, 'metrics': data}
                    for keyword, data in keyword_data.items()
                ]
            }
            return self.data_transformer.transform_query_response_to_submit_format(
                query_response, url_keywords_map
            )
        else:
            # 使用旧API格式
            return [
                {
                    'keyword': keyword,
                    'avg_monthly_searches': data.get('avg_monthly_searches', 0),
                    'latest_searches': data.get('latest_searches', 0),
                    'competition': data.get('competition', 'UNKNOWN'),
                    'monthly_trend': data.get('monthly_searches', [])
                }
                for keyword, data in keyword_data.items()
            ]
    
    async def _submit_data(self, submit_data: list) -> bool:
        """提交数据到后端"""
        try:
            if self.keyword_metrics_client:
                return await self.keyword_metrics_client.submit_keyword_metrics_batch(submit_data)
            elif self.backend_api:
                return await self.backend_api.submit_batch(submit_data)
            else:
                self.logger.warning("没有配置提交客户端")
                return False
        except Exception as e:
            self.logger.error(f"数据提交失败: {e}")
            return False


class TaskExecutor:
    """任务执行器 - 负责并行执行异步任务"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.active_tasks = set()
    
    async def execute_parallel(self, *tasks: AsyncTask, data: Dict[str, Any]) -> Dict[str, TaskResult]:
        """
        并行执行多个任务
        
        Args:
            *tasks: 要执行的任务列表
            data: 输入数据
            
        Returns:
            Dict[str, TaskResult]: 任务名称到结果的映射
        """
        if not tasks:
            return {}
        
        self.logger.info(f"开始并行执行 {len(tasks)} 个任务")
        
        # 创建异步任务
        async_tasks = []
        task_names = []
        
        for task in tasks:
            async_task = asyncio.create_task(
                self._execute_single_task(task, data),
                name=task.name
            )
            async_tasks.append(async_task)
            task_names.append(task.name)
            self.active_tasks.add(async_task)
        
        try:
            # 并行执行，收集异常
            results = await asyncio.gather(*async_tasks, return_exceptions=True)
            
            # 处理结果
            task_results = {}
            for i, (task_name, result) in enumerate(zip(task_names, results)):
                if isinstance(result, Exception):
                    self.logger.error(f"任务 {task_name} 发生异常: {result}")
                    task_results[task_name] = TaskResult(False, error=str(result))
                else:
                    task_results[task_name] = result
            
            # 记录执行统计
            successful_tasks = sum(1 for r in task_results.values() if r.success)
            self.logger.info(f"并行执行完成: {successful_tasks}/{len(tasks)} 个任务成功")
            
            return task_results
            
        finally:
            # 清理活跃任务
            for task in async_tasks:
                self.active_tasks.discard(task)
    
    async def _execute_single_task(self, task: AsyncTask, data: Dict[str, Any]) -> TaskResult:
        """执行单个任务"""
        try:
            return await task.execute(data)
        except Exception as e:
            self.logger.error(f"任务 {task.name} 执行异常: {e}")
            return TaskResult(False, error=str(e))
    
    async def cancel_all_tasks(self) -> None:
        """取消所有活跃任务"""
        if self.active_tasks:
            self.logger.info(f"取消 {len(self.active_tasks)} 个活跃任务")
            for task in self.active_tasks:
                task.cancel()
            
            # 等待任务取消完成
            await asyncio.gather(*self.active_tasks, return_exceptions=True)
            self.active_tasks.clear()
    
    def get_active_task_count(self) -> int:
        """获取活跃任务数量"""
        return len(self.active_tasks)
