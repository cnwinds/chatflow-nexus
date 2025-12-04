"""
日志格式化器
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict


class ColoredFormatter(logging.Formatter):
    """彩色日志格式化器"""
    
    # 颜色代码
    COLORS = {
        'DEBUG': '\033[36m',    # 青色
        'INFO': '\033[32m',     # 绿色
        'WARNING': '\033[33m',  # 黄色
        'ERROR': '\033[31m',    # 红色
        'CRITICAL': '\033[35m', # 紫色
        'RESET': '\033[0m'      # 重置
    }
    
    def __init__(self, fmt=None, datefmt=None, style='%', use_colors=True):
        super().__init__(fmt, datefmt, style)
        self.use_colors = use_colors
    
    def format(self, record):
        # 添加颜色
        if self.use_colors and hasattr(record, 'levelname'):
            color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
            record.levelname = f"{color}{record.levelname}{self.COLORS['RESET']}"
        
        try:
            return super().format(record)
        except Exception as e:
            # 如果格式化失败，返回基本格式
            try:
                asctime = getattr(record, 'asctime', 'N/A')
                return f"{asctime} - {record.name} - {record.levelname} - [格式化错误: {e}] {record.msg}"
            except:
                return f"N/A - {record.name} - {record.levelname} - [格式化错误: {e}] {record.msg}"


class JsonFormatter(logging.Formatter):
    """JSON 日志格式化器"""
    
    def __init__(self, include_timestamp=True, include_level=True, include_logger=True):
        super().__init__()
        self.include_timestamp = include_timestamp
        self.include_level = include_level
        self.include_logger = include_logger
    
    def format(self, record):
        try:
            log_entry = {
                'message': record.getMessage()
            }
            
            if self.include_timestamp:
                log_entry['timestamp'] = datetime.fromtimestamp(record.created).isoformat()
            
            if self.include_level:
                log_entry['level'] = record.levelname
            
            if self.include_logger:
                log_entry['logger'] = record.name
            
            # 添加异常信息
            if record.exc_info:
                log_entry['exception'] = self.formatException(record.exc_info)
            
            # 添加额外字段
            if hasattr(record, 'extra_fields'):
                log_entry.update(record.extra_fields)
            
            # 添加所有 record 属性
            for key, value in record.__dict__.items():
                if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 
                              'filename', 'module', 'lineno', 'funcName', 'created', 
                              'msecs', 'relativeCreated', 'thread', 'threadName', 
                              'processName', 'process', 'getMessage', 'exc_info', 
                              'exc_text', 'stack_info', 'extra_fields']:
                    log_entry[key] = value
            
            return json.dumps(log_entry, ensure_ascii=False, default=str)
        except Exception as e:
            # 如果格式化失败，返回基本JSON格式
            return json.dumps({
                'timestamp': datetime.fromtimestamp(record.created).isoformat(),
                'level': record.levelname,
                'logger': record.name,
                'message': f"[格式化错误: {e}] {record.msg}",
                'error': str(e)
            }, ensure_ascii=False)


class StructuredFormatter(logging.Formatter):
    """结构化日志格式化器"""
    
    def __init__(self, fmt=None, datefmt=None, include_extra=True):
        if fmt is None:
            fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        super().__init__(fmt, datefmt)
        self.include_extra = include_extra
    
    def format(self, record):
        try:
            # 格式化基本消息
            formatted = super().format(record)
            
            # 添加额外字段
            if self.include_extra and hasattr(record, 'extra_fields'):
                extra_str = ' '.join([f"{k}={v}" for k, v in record.extra_fields.items()])
                if extra_str:
                    formatted += f" [{extra_str}]"
            
            return formatted
        except Exception as e:
            # 如果格式化失败，返回基本格式
            try:
                asctime = getattr(record, 'asctime', 'N/A')
                return f"{asctime} - {record.name} - {record.levelname} - [格式化错误: {e}] {record.msg}"
            except:
                return f"N/A - {record.name} - {record.levelname} - [格式化错误: {e}] {record.msg}" 