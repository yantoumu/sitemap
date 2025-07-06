"""
日志工具模块
提供统一的日志配置和管理功能
"""

import logging
import logging.config
from pathlib import Path
from typing import Optional
import sys


class LoggerManager:
    """日志管理器"""
    
    def __init__(self):
        """初始化日志管理器"""
        self._configured = False
        self._loggers = {}
    
    def setup_logging(self, config_file: Optional[str] = None, 
                     log_level: str = "INFO", 
                     log_file: Optional[str] = None) -> None:
        """
        设置日志配置
        
        Args:
            config_file: 日志配置文件路径
            log_level: 日志级别
            log_file: 日志文件路径
        """
        if self._configured:
            return
        
        if config_file and Path(config_file).exists():
            # 使用配置文件
            try:
                logging.config.fileConfig(config_file)
                self._configured = True
                return
            except Exception as e:
                print(f"加载日志配置文件失败: {e}")
        
        # 使用默认配置
        self._setup_default_logging(log_level, log_file)
        self._configured = True
    
    def _setup_default_logging(self, log_level: str, log_file: Optional[str]) -> None:
        """
        设置默认日志配置
        
        Args:
            log_level: 日志级别
            log_file: 日志文件路径
        """
        # 创建根日志器
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, log_level.upper()))
        
        # 清除现有处理器
        root_logger.handlers.clear()
        
        # 创建格式器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level.upper()))
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        # 文件处理器
        if log_file:
            try:
                # 确保日志目录存在
                log_path = Path(log_file)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                
                file_handler = logging.handlers.RotatingFileHandler(
                    log_file,
                    maxBytes=10*1024*1024,  # 10MB
                    backupCount=5,
                    encoding='utf-8'
                )
                file_handler.setLevel(getattr(logging, log_level.upper()))
                file_handler.setFormatter(formatter)
                root_logger.addHandler(file_handler)
                
            except Exception as e:
                print(f"创建文件日志处理器失败: {e}")
    
    def get_logger(self, name: str) -> logging.Logger:
        """
        获取日志器
        
        Args:
            name: 日志器名称
            
        Returns:
            logging.Logger: 日志器实例
        """
        if name not in self._loggers:
            self._loggers[name] = logging.getLogger(name)
        
        return self._loggers[name]
    
    def set_level(self, level: str) -> None:
        """
        设置全局日志级别
        
        Args:
            level: 日志级别
        """
        logging.getLogger().setLevel(getattr(logging, level.upper()))
        
        # 更新所有处理器的级别
        for handler in logging.getLogger().handlers:
            handler.setLevel(getattr(logging, level.upper()))


# 全局日志管理器实例
logger_manager = LoggerManager()


def setup_logging(config_file: Optional[str] = None, 
                 log_level: str = "INFO", 
                 log_file: Optional[str] = None) -> None:
    """
    设置日志配置（便捷函数）
    
    Args:
        config_file: 日志配置文件路径
        log_level: 日志级别
        log_file: 日志文件路径
    """
    logger_manager.setup_logging(config_file, log_level, log_file)


def get_logger(name: str) -> logging.Logger:
    """
    获取日志器（便捷函数）
    
    Args:
        name: 日志器名称
        
    Returns:
        logging.Logger: 日志器实例
    """
    return logger_manager.get_logger(name)


class ProgressLogger:
    """进度日志器"""
    
    def __init__(self, logger: logging.Logger, total: int, 
                 log_interval: int = 100):
        """
        初始化进度日志器
        
        Args:
            logger: 日志器
            total: 总数量
            log_interval: 日志间隔
        """
        self.logger = logger
        self.total = total
        self.log_interval = log_interval
        self.current = 0
    
    def update(self, count: int = 1) -> None:
        """
        更新进度

        Args:
            count: 增加的数量
        """
        self.current += count

        if self.current % self.log_interval == 0 or self.current == self.total:
            percentage = (self.current / self.total) * 100
            # 简化输出格式，只显示百分比和关键节点
            if percentage % 10 == 0 or self.current == self.total:
                self.logger.info(f"进度: {percentage:.0f}% ({self.current:,}/{self.total:,})")
            else:
                self.logger.debug(f"进度: {percentage:.1f}% ({self.current:,}/{self.total:,})")
    
    def finish(self) -> None:
        """完成进度记录"""
        if self.current < self.total:
            self.current = self.total
            self.logger.info(f"进度: {self.current}/{self.total} (100.0%)")


class TimingLogger:
    """计时日志器"""
    
    def __init__(self, logger: logging.Logger, operation: str):
        """
        初始化计时日志器
        
        Args:
            logger: 日志器
            operation: 操作名称
        """
        self.logger = logger
        self.operation = operation
        self.start_time = None
    
    def __enter__(self):
        """进入上下文"""
        import time
        self.start_time = time.time()
        self.logger.info(f"开始 {self.operation}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文"""
        import time
        if self.start_time:
            duration = time.time() - self.start_time
            if exc_type:
                self.logger.error(f"{self.operation} 失败，耗时: {duration:.2f}秒")
            else:
                self.logger.info(f"{self.operation} 完成，耗时: {duration:.2f}秒")


def log_function_call(logger: logging.Logger):
    """
    函数调用日志装饰器
    
    Args:
        logger: 日志器
        
    Returns:
        装饰器函数
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            logger.debug(f"调用函数: {func.__name__}")
            try:
                result = func(*args, **kwargs)
                logger.debug(f"函数 {func.__name__} 执行成功")
                return result
            except Exception as e:
                logger.error(f"函数 {func.__name__} 执行失败: {e}")
                raise
        return wrapper
    return decorator
