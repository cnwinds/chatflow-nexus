"""
统一日志管理器
"""

import logging
import logging.handlers
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from .formatters import ColoredFormatter, JsonFormatter, StructuredFormatter
from .filters import SensitiveDataFilter, PerformanceFilter, LevelFilter, ModuleFilter, DuplicateFilter
from ..exceptions import LoggingError


class LoggingManager:
    """统一日志管理器"""
    
    def __init__(self, config_manager):
        """初始化日志管理器"""
        self.config_manager = config_manager
        self.loggers = {}
        self.handlers = {}
        self._setup_logging()
    
    def _setup_logging(self):
        """设置日志系统"""
        try:
            # 加载日志配置
            logging_config = self.config_manager.get_config("logging")
            
            # 设置根日志级别
            root_level = logging_config.get('level', 'INFO')
            logging.getLogger().setLevel(getattr(logging, root_level.upper()))
            
            # 清除现有的处理器
            root_logger = logging.getLogger()
            for handler in root_logger.handlers[:]:
                root_logger.removeHandler(handler)
            
            # 创建处理器
            self._create_handlers(logging_config)
            
            # 设置根日志器
            self._setup_root_logger(logging_config)
            
        except Exception as e:
            # 如果配置失败，使用基本配置
            self._setup_basic_logging()
            raise LoggingError(f"日志配置失败，使用基本配置: {e}")
    
    def _create_handlers(self, config: Dict[str, Any]):
        """创建日志处理器"""
        # 控制台处理器
        if config.get('console_enabled', True):
            console_handler = self._create_console_handler(config)
            self.handlers['console'] = console_handler
        
        # 文件处理器
        if config.get('file_enabled', False):
            file_handler = self._create_file_handler(config)
            self.handlers['file'] = file_handler
        
        # 错误文件处理器
        if config.get('error_file_enabled', False):
            error_handler = self._create_error_handler(config)
            self.handlers['error'] = error_handler
        
        # JSON 文件处理器
        if config.get('json_file_enabled', False):
            json_handler = self._create_json_handler(config)
            self.handlers['json'] = json_handler
    
    def _create_console_handler(self, config: Dict[str, Any]) -> logging.Handler:
        """创建控制台处理器"""
        handler = logging.StreamHandler()
        
        # 设置级别
        level = config.get('console_level', config.get('level', 'INFO'))
        handler.setLevel(getattr(logging, level.upper()))
        
        # 设置格式化器
        if config.get('console_colors', True):
            formatter = ColoredFormatter(
                fmt=config.get('console_format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
                datefmt=config.get('date_format', '%Y-%m-%d %H:%M:%S')
            )
        else:
            formatter = StructuredFormatter(
                fmt=config.get('console_format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
                datefmt=config.get('date_format', '%Y-%m-%d %H:%M:%S')
            )
        
        handler.setFormatter(formatter)
        
        # 添加过滤器
        self._add_filters_to_handler(handler, config, 'console')
        
        return handler
    
    def _create_file_handler(self, config: Dict[str, Any]) -> logging.Handler:
        """创建文件处理器"""
        file_path = config.get('file_path')

        if not file_path:
            file_path = self.config_manager.logs_dir / "app.log"
        else:
            file_path = self.config_manager.logs_dir / file_path

        # 确保日志目录存在
        log_dir = Path(file_path).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建轮转处理器
        max_bytes = config.get('max_file_size', 10 * 1024 * 1024)  # 10MB
        backup_count = config.get('backup_count', 5)
        
        handler = logging.handlers.RotatingFileHandler(
            file_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        
        # 设置级别
        level = config.get('file_level', config.get('level', 'INFO'))
        handler.setLevel(getattr(logging, level.upper()))
        
        # 设置格式化器
        formatter = StructuredFormatter(
            fmt=config.get('file_format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
            datefmt=config.get('date_format', '%Y-%m-%d %H:%M:%S')
        )
        handler.setFormatter(formatter)
        
        # 添加过滤器
        self._add_filters_to_handler(handler, config, 'file')
        
        return handler
    
    def _create_error_handler(self, config: Dict[str, Any]) -> logging.Handler:
        """创建错误文件处理器"""
        error_file_path = config.get('error_file_path')
        if not error_file_path:
            error_file_path = self.config_manager.logs_dir / "error.log"
        else:
            error_file_path = self.config_manager.logs_dir / error_file_path
        
        # 确保日志目录存在
        log_dir = Path(error_file_path).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        
        handler = logging.handlers.RotatingFileHandler(
            error_file_path,
            maxBytes=config.get('max_file_size', 10 * 1024 * 1024),
            backupCount=config.get('backup_count', 5),
            encoding='utf-8'
        )
        
        # 只记录错误级别以上的日志
        handler.setLevel(logging.ERROR)
        
        # 设置格式化器
        formatter = StructuredFormatter(
            fmt=config.get('error_format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
            datefmt=config.get('date_format', '%Y-%m-%d %H:%M:%S')
        )
        handler.setFormatter(formatter)
        
        return handler
    
    def _create_json_handler(self, config: Dict[str, Any]) -> logging.Handler:
        """创建 JSON 文件处理器"""
        json_file_path = config.get('json_file_path')
        if not json_file_path:
            json_file_path = self.config_manager.logs_dir / "app.json"
        
        # 确保日志目录存在
        log_dir = Path(json_file_path).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        
        handler = logging.handlers.RotatingFileHandler(
            json_file_path,
            maxBytes=config.get('max_file_size', 10 * 1024 * 1024),
            backupCount=config.get('backup_count', 5),
            encoding='utf-8'
        )
        
        # 设置级别
        level = config.get('json_level', config.get('level', 'INFO'))
        handler.setLevel(getattr(logging, level.upper()))
        
        # 设置 JSON 格式化器
        formatter = JsonFormatter(
            include_timestamp=config.get('json_include_timestamp', True),
            include_level=config.get('json_include_level', True),
            include_logger=config.get('json_include_logger', True)
        )
        handler.setFormatter(formatter)
        
        return handler
    
    def _add_filters_to_handler(self, handler: logging.Handler, config: Dict[str, Any], handler_type: str):
        """为处理器添加过滤器"""
        # 敏感数据过滤器
        if config.get('sensitive_data_filter', True):
            sensitive_fields = config.get('sensitive_fields', [])
            handler.addFilter(SensitiveDataFilter(sensitive_fields))
        
        # 性能过滤器
        if config.get('performance_filter', False):
            max_messages = config.get('max_messages_per_minute', 60)
            handler.addFilter(PerformanceFilter(max_messages))
        
        # 重复消息过滤器
        if config.get('duplicate_filter', False):
            max_duplicates = config.get('max_duplicates', 3)
            time_window = config.get('duplicate_time_window', 60)
            handler.addFilter(DuplicateFilter(max_duplicates, time_window))
        
        # 模块过滤器
        include_modules = config.get(f'{handler_type}_include_modules', [])
        exclude_modules = config.get(f'{handler_type}_exclude_modules', [])
        if include_modules or exclude_modules:
            handler.addFilter(ModuleFilter(include_modules, exclude_modules))
    
    def _setup_root_logger(self, config: Dict[str, Any]):
        """设置根日志器"""
        root_logger = logging.getLogger()
        
        # 添加所有处理器
        for handler in self.handlers.values():
            root_logger.addHandler(handler)
        
        # 设置传播
        root_logger.propagate = config.get('propagate', True)
    
    def _setup_basic_logging(self):
        """设置基本日志配置"""
        # 创建基本控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(formatter)
        
        # 设置根日志器
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(console_handler)
        
        self.handlers['console'] = console_handler
    
    def get_logger(self, name: str) -> logging.Logger:
        """获取日志记录器"""
        if name in self.loggers:
            return self.loggers[name]
        
        logger = logging.getLogger(name)
        self.loggers[name] = logger
        return logger
    
    def update_log_level(self, logger_name: str, level: str):
        """更新日志级别"""
        try:
            level_num = getattr(logging, level.upper())
            
            if logger_name == 'root':
                logging.getLogger().setLevel(level_num)
            else:
                logger = self.get_logger(logger_name)
                logger.setLevel(level_num)
                
        except AttributeError:
            raise LoggingError(f"无效的日志级别: {level}")
    
    def get_log_stats(self) -> Dict[str, Any]:
        """获取日志统计信息"""
        stats = {
            'config': {
                'level': logging.getLogger().level,
                'handlers': list(self.handlers.keys()),
                'loggers': list(self.loggers.keys())
            },
            'handlers': {}
        }
        
        for name, handler in self.handlers.items():
            stats['handlers'][name] = {
                'level': handler.level,
                'formatter': type(handler.formatter).__name__ if handler.formatter else None,
                'filters': [type(f).__name__ for f in handler.filters]
            }
        
        return stats
    
    def reload_config(self):
        """重新加载日志配置"""
        try:
            # 清除现有配置
            self.loggers.clear()
            self.handlers.clear()
            
            # 重新设置
            self._setup_logging()
            
        except Exception as e:
            raise LoggingError(f"重新加载日志配置失败: {e}")
    
    def add_handler(self, name: str, handler: logging.Handler):
        """添加自定义处理器"""
        self.handlers[name] = handler
        logging.getLogger().addHandler(handler)
    
    def remove_handler(self, name: str):
        """移除处理器"""
        if name in self.handlers:
            handler = self.handlers[name]
            logging.getLogger().removeHandler(handler)
            del self.handlers[name]
    
    def setup_logging(self):
        """设置日志系统（兼容性方法）"""
        # 这个方法已经在上面的 _setup_logging 中调用了
        pass


# 全局日志管理器实例
_logging_manager = None


def get_logging_manager() -> LoggingManager:
    """获取日志管理器实例
    
    Returns:
        LoggingManager: 日志管理器实例
        
    Raises:
        RuntimeError: 日志管理器未初始化
    """
    global _logging_manager
    if _logging_manager is None:
        raise RuntimeError("日志管理器未初始化")
    return _logging_manager


def initialize_logging(config_manager) -> LoggingManager:
    """初始化日志管理器
    
    Args:
        config_manager: 配置管理器
        
    Returns:
        LoggingManager: 初始化后的日志管理器实例
    """
    global _logging_manager
    
    # 创建日志管理器
    logging_manager = LoggingManager(config_manager)
    
    # 设置全局实例
    _logging_manager = logging_manager
    
    return logging_manager


def is_logging_ready() -> bool:
    """检查日志管理器是否已初始化
    
    Returns:
        bool: 是否已初始化
    """
    global _logging_manager
    return _logging_manager is not None


def get_logger(name: str = None) -> logging.Logger:
    """获取日志记录器（便捷函数）
    
    这是一个便捷函数，用于获取日志记录器。如果日志管理器已初始化，
    则使用日志管理器获取；否则回退到标准logging模块。
    
    Args:
        name: 日志记录器名称，默认为None（使用调用模块的名称）
        
    Returns:
        logging.Logger: 日志记录器实例
    """
    if name is None:
        import inspect
        frame = inspect.currentframe().f_back
        name = frame.f_globals.get('__name__', 'root')
    
    try:
        logging_manager = get_logging_manager()
        return logging_manager.get_logger(name)
    except RuntimeError:
        # 如果日志管理器未初始化，回退到标准logging
        return logging.getLogger(name) 