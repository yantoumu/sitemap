"""
增量数据保存管理器
实现定期保存和Git提交功能，确保长时间运行任务的数据安全
"""

import asyncio
import time
import subprocess
import os
from typing import Optional, Callable, Dict, Any
from pathlib import Path
import logging

from ..utils.log_security import LogSecurity


class IncrementalSaver:
    """增量数据保存管理器"""
    
    def __init__(self, 
                 save_interval: int = 1000,  # 每1000个关键词保存一次
                 git_commit_interval: int = 5000,  # 每5000个关键词提交一次Git
                 max_runtime_hours: float = 5.5,  # 最大运行时间（小时）
                 enable_git_commit: bool = False):  # 是否启用Git提交
        """
        初始化增量保存管理器
        
        Args:
            save_interval: 本地保存间隔（处理的关键词数量）
            git_commit_interval: Git提交间隔（处理的关键词数量）
            max_runtime_hours: 最大运行时间（小时）
            enable_git_commit: 是否启用Git提交（仅在GitHub Actions中启用）
        """
        self.save_interval = save_interval
        self.git_commit_interval = git_commit_interval
        self.max_runtime_seconds = max_runtime_hours * 3600
        self.enable_git_commit = enable_git_commit
        
        self.start_time = time.time()
        self.last_save_count = 0
        self.last_git_commit_count = 0
        self.total_processed = 0
        
        self.logger = logging.getLogger(__name__)
        
        # 检查是否在GitHub Actions环境中
        self.is_github_actions = os.getenv('GITHUB_ACTIONS') == 'true'
        if self.is_github_actions:
            self.enable_git_commit = True
            self.logger.info("🔄 检测到GitHub Actions环境，启用Git自动提交")
        
        self.logger.info(f"📊 增量保存配置: 本地保存间隔={save_interval}, Git提交间隔={git_commit_interval}")
    
    def should_save_locally(self, processed_count: int) -> bool:
        """检查是否应该进行本地保存"""
        return processed_count - self.last_save_count >= self.save_interval
    
    def should_commit_git(self, processed_count: int) -> bool:
        """检查是否应该进行Git提交"""
        if not self.enable_git_commit:
            return False
        return processed_count - self.last_git_commit_count >= self.git_commit_interval
    
    def is_approaching_timeout(self) -> bool:
        """检查是否接近超时"""
        elapsed = time.time() - self.start_time
        return elapsed > self.max_runtime_seconds
    
    def get_runtime_info(self) -> Dict[str, Any]:
        """获取运行时信息"""
        elapsed = time.time() - self.start_time
        remaining = max(0, self.max_runtime_seconds - elapsed)
        
        return {
            'elapsed_seconds': elapsed,
            'elapsed_hours': elapsed / 3600,
            'remaining_seconds': remaining,
            'remaining_hours': remaining / 3600,
            'total_processed': self.total_processed,
            'is_approaching_timeout': self.is_approaching_timeout()
        }
    
    async def save_checkpoint(self, 
                            processed_count: int,
                            save_callback: Optional[Callable] = None,
                            force: bool = False) -> bool:
        """
        保存检查点
        
        Args:
            processed_count: 已处理的关键词数量
            save_callback: 保存回调函数
            force: 强制保存
            
        Returns:
            bool: 是否执行了保存
        """
        self.total_processed = processed_count
        
        if not force and not self.should_save_locally(processed_count):
            return False
        
        try:
            if save_callback:
                await save_callback()
            
            self.last_save_count = processed_count
            runtime_info = self.get_runtime_info()
            
            self.logger.info(f"💾 检查点保存: 已处理 {processed_count} 个关键词 "
                           f"(运行时间: {runtime_info['elapsed_hours']:.1f}h)")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 检查点保存失败: {e}")
            return False
    
    async def commit_to_git(self, 
                          processed_count: int,
                          force: bool = False) -> bool:
        """
        提交数据到Git
        
        Args:
            processed_count: 已处理的关键词数量
            force: 强制提交
            
        Returns:
            bool: 是否执行了提交
        """
        if not force and not self.should_commit_git(processed_count):
            return False
        
        if not self.enable_git_commit:
            self.logger.debug("Git提交未启用，跳过")
            return False
        
        try:
            # 检查是否有数据文件
            data_file = Path("data/processed_urls.json")
            if not data_file.exists():
                self.logger.warning("数据文件不存在，跳过Git提交")
                return False
            
            # 配置Git用户信息
            subprocess.run(['git', 'config', '--local', 'user.email', 'action@github.com'], 
                         check=True, capture_output=True)
            subprocess.run(['git', 'config', '--local', 'user.name', 'GitHub Action'], 
                         check=True, capture_output=True)
            
            # 添加数据文件
            subprocess.run(['git', 'add', 'data/processed_urls.json'], 
                         check=True, capture_output=True)
            
            # 检查是否有变更
            result = subprocess.run(['git', 'diff', '--staged', '--quiet'], 
                                  capture_output=True)
            
            if result.returncode == 0:
                self.logger.debug("没有新数据需要提交")
                return False
            
            # 获取文件大小
            file_size = data_file.stat().st_size
            file_size_mb = file_size / (1024 * 1024)
            
            # 提交数据
            runtime_info = self.get_runtime_info()
            commit_msg = (f"data: 增量保存 {processed_count} 个关键词 "
                         f"({file_size_mb:.1f}MB, {runtime_info['elapsed_hours']:.1f}h) [skip ci]")
            
            subprocess.run(['git', 'commit', '-m', commit_msg], 
                         check=True, capture_output=True)
            
            # 推送到GitHub
            subprocess.run(['git', 'push', 'origin', 'main'], 
                         check=True, capture_output=True)
            
            self.last_git_commit_count = processed_count
            
            self.logger.info(f"✅ Git提交成功: {processed_count} 个关键词 "
                           f"({file_size_mb:.1f}MB)")
            
            return True
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"❌ Git提交失败: {e}")
            return False
        except Exception as e:
            self.logger.error(f"❌ Git提交异常: {e}")
            return False
    
    async def emergency_save(self, 
                           save_callback: Optional[Callable] = None,
                           reason: str = "超时") -> bool:
        """
        紧急保存（接近超时时）
        
        Args:
            save_callback: 保存回调函数
            reason: 紧急保存原因
            
        Returns:
            bool: 是否保存成功
        """
        self.logger.warning(f"🚨 触发紧急保存: {reason}")
        
        # 强制本地保存
        local_saved = await self.save_checkpoint(
            self.total_processed, save_callback, force=True)
        
        # 强制Git提交
        git_committed = await self.commit_to_git(
            self.total_processed, force=True)
        
        runtime_info = self.get_runtime_info()
        self.logger.warning(f"🚨 紧急保存完成: 本地保存={local_saved}, "
                          f"Git提交={git_committed}, "
                          f"已处理={self.total_processed}个关键词, "
                          f"运行时间={runtime_info['elapsed_hours']:.1f}h")
        
        return local_saved or git_committed
    
    def get_progress_summary(self) -> str:
        """获取进度摘要"""
        runtime_info = self.get_runtime_info()
        
        return (f"进度摘要: 已处理 {self.total_processed} 个关键词, "
               f"运行时间 {runtime_info['elapsed_hours']:.1f}h, "
               f"剩余时间 {runtime_info['remaining_hours']:.1f}h")
