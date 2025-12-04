"""
日志过滤器
"""

import logging
import re
import time
from typing import Any, Dict, List, Optional


class SensitiveDataFilter(logging.Filter):
    """敏感数据过滤器"""
    
    def __init__(self, sensitive_fields: List[str] = None, replacement: str = "***"):
        super().__init__()
        self.sensitive_fields = sensitive_fields or [
            'password', 'token', 'key', 'secret', 'auth', 'credential'
        ]
        self.replacement = replacement
        self._compile_patterns()
    
    def _compile_patterns(self):
        """编译敏感字段模式"""
        self.patterns = []
        for field in self.sensitive_fields:
            # 匹配字段名（不区分大小写）
            pattern = re.compile(
                rf'({field}["\']?\s*[:=]\s*["\']?)([^"\s,}}]+)',
                re.IGNORECASE
            )
            self.patterns.append(pattern)
    
    def filter(self, record):
        """过滤敏感数据"""
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = self._mask_sensitive_data(record.msg)
        
        if hasattr(record, 'args') and record.args:
            record.args = tuple(
                self._mask_sensitive_data(str(arg)) if isinstance(arg, str) else arg
                for arg in record.args
            )
        
        return True
    
    def _mask_sensitive_data(self, text: str) -> str:
        """掩码敏感数据"""
        for pattern in self.patterns:
            text = pattern.sub(rf'\1{self.replacement}', text)
        return text


class PerformanceFilter(logging.Filter):
    """性能过滤器 - 限制日志频率"""
    
    def __init__(self, max_messages_per_minute: int = 60):
        super().__init__()
        self.max_messages_per_minute = max_messages_per_minute
        self.message_counts = {}
        self.last_cleanup = time.time()
    
    def filter(self, record):
        """过滤高频日志"""
        current_time = time.time()
        message_key = f"{record.name}:{record.levelname}:{record.getMessage()}"
        
        # 清理旧记录
        if current_time - self.last_cleanup > 60:
            self._cleanup_old_records(current_time)
            self.last_cleanup = current_time
        
        # 检查消息频率
        if message_key in self.message_counts:
            count, first_time = self.message_counts[message_key]
            if current_time - first_time < 60:  # 1分钟内
                if count >= self.max_messages_per_minute:
                    # 超过限制，记录一次警告并跳过
                    if count == self.max_messages_per_minute:
                        record.msg = f"[频率限制] {record.msg} (已跳过 {count} 条相似消息)"
                        self.message_counts[message_key] = (count + 1, first_time)
                        return True
                    else:
                        self.message_counts[message_key] = (count + 1, first_time)
                        return False
                else:
                    self.message_counts[message_key] = (count + 1, first_time)
            else:
                # 重置计数
                self.message_counts[message_key] = (1, current_time)
        else:
            self.message_counts[message_key] = (1, current_time)
        
        return True
    
    def _cleanup_old_records(self, current_time: float):
        """清理超过1分钟的记录"""
        keys_to_remove = []
        for key, (count, first_time) in self.message_counts.items():
            if current_time - first_time > 60:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self.message_counts[key]


class LevelFilter(logging.Filter):
    """级别过滤器"""
    
    def __init__(self, min_level: int = logging.INFO, max_level: int = logging.CRITICAL):
        super().__init__()
        self.min_level = min_level
        self.max_level = max_level
    
    def filter(self, record):
        """过滤日志级别"""
        return self.min_level <= record.levelno <= self.max_level


class ModuleFilter(logging.Filter):
    """模块过滤器"""
    
    def __init__(self, include_modules: List[str] = None, exclude_modules: List[str] = None):
        super().__init__()
        self.include_modules = include_modules or []
        self.exclude_modules = exclude_modules or []
    
    def filter(self, record):
        """过滤模块"""
        module_name = record.name
        
        # 排除模块
        if self.exclude_modules:
            for exclude in self.exclude_modules:
                if module_name.startswith(exclude):
                    return False
        
        # 包含模块
        if self.include_modules:
            for include in self.include_modules:
                if module_name.startswith(include):
                    return True
            return False
        
        return True


class DuplicateFilter(logging.Filter):
    """重复消息过滤器"""
    
    def __init__(self, max_duplicates: int = 3, time_window: int = 60):
        super().__init__()
        self.max_duplicates = max_duplicates
        self.time_window = time_window
        self.duplicate_counts = {}
        self.last_cleanup = time.time()
    
    def filter(self, record):
        """过滤重复消息"""
        current_time = time.time()
        message_hash = hash(f"{record.name}:{record.levelname}:{record.getMessage()}")
        
        # 清理旧记录
        if current_time - self.last_cleanup > self.time_window:
            self._cleanup_old_records(current_time)
            self.last_cleanup = current_time
        
        if message_hash in self.duplicate_counts:
            count, first_time = self.duplicate_counts[message_hash]
            if current_time - first_time < self.time_window:
                if count >= self.max_duplicates:
                    # 超过重复限制，跳过
                    self.duplicate_counts[message_hash] = (count + 1, first_time)
                    return False
                else:
                    self.duplicate_counts[message_hash] = (count + 1, first_time)
            else:
                # 重置计数
                self.duplicate_counts[message_hash] = (1, current_time)
        else:
            self.duplicate_counts[message_hash] = (1, current_time)
        
        return True
    
    def _cleanup_old_records(self, current_time: float):
        """清理旧记录"""
        keys_to_remove = []
        for key, (count, first_time) in self.duplicate_counts.items():
            if current_time - first_time > self.time_window:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self.duplicate_counts[key] 