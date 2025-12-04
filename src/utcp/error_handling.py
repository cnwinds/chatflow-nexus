#!/usr/bin/env python3
"""
UTCP错误处理和日志系统
提供统一的错误处理、日志记录和错误恢复机制
"""

import logging
import traceback
import functools
import asyncio
import time
from typing import Dict, Any, Optional, Callable, Union, List
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta


class ErrorSeverity(Enum):
    """错误严重程度枚举"""
    LOW = "low"           # 轻微错误，不影响核心功能
    MEDIUM = "medium"     # 中等错误，影响部分功能
    HIGH = "high"         # 严重错误，影响核心功能
    CRITICAL = "critical" # 致命错误，系统无法正常运行


class ErrorCategory(Enum):
    """错误分类枚举"""
    VALIDATION = "validation"         # 参数验证错误
    NETWORK = "network"              # 网络连接错误
    API = "api"                      # API调用错误
    SERVICE = "service"              # 服务内部错误
    CONFIGURATION = "configuration"  # 配置错误
    RESOURCE = "resource"            # 资源不足错误
    TIMEOUT = "timeout"              # 超时错误
    AUTHENTICATION = "authentication" # 认证错误
    PERMISSION = "permission"        # 权限错误
    DATA = "data"                    # 数据处理错误


@dataclass
class ErrorContext:
    """错误上下文信息"""
    service_name: str
    tool_name: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    additional_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UTCPError:
    """UTCP统一错误结构"""
    code: str
    message: str
    severity: ErrorSeverity
    category: ErrorCategory
    context: ErrorContext
    original_exception: Optional[Exception] = None
    stack_trace: Optional[str] = None
    user_message: Optional[str] = None
    recovery_suggestions: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """初始化后处理"""
        if self.original_exception and not self.stack_trace:
            self.stack_trace = traceback.format_exc()
        
        if not self.user_message:
            self.user_message = self._generate_user_message()
    
    def _generate_user_message(self) -> str:
        """生成用户友好的错误消息"""
        category_messages = {
            ErrorCategory.VALIDATION: "输入参数有误，请检查并重试",
            ErrorCategory.NETWORK: "网络连接出现问题，请稍后重试",
            ErrorCategory.API: "外部服务暂时不可用，请稍后重试",
            ErrorCategory.SERVICE: "服务内部出现错误，我们正在处理",
            ErrorCategory.CONFIGURATION: "服务配置有误，请联系管理员",
            ErrorCategory.RESOURCE: "系统资源不足，请稍后重试",
            ErrorCategory.TIMEOUT: "请求超时，请稍后重试",
            ErrorCategory.AUTHENTICATION: "身份验证失败，请检查凭据",
            ErrorCategory.PERMISSION: "权限不足，无法执行此操作",
            ErrorCategory.DATA: "数据处理出现错误，请检查输入"
        }
        
        base_message = category_messages.get(self.category, "操作失败，请稍后重试")
        
        if self.severity == ErrorSeverity.CRITICAL:
            return f"系统出现严重错误：{base_message}"
        elif self.severity == ErrorSeverity.HIGH:
            return f"操作失败：{base_message}"
        else:
            return base_message
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "status": "error",
            "error": {
                "code": self.code,
                "message": self.message,
                "severity": self.severity.value,
                "category": self.category.value,
                "user_message": self.user_message,
                "recovery_suggestions": self.recovery_suggestions,
                "context": {
                    "service": self.context.service_name,
                    "tool": self.context.tool_name,
                    "timestamp": self.context.timestamp.isoformat(),
                    "request_id": self.context.request_id
                }
            }
        }


class RetryConfig:
    """重试配置"""
    
    def __init__(self, 
                 max_attempts: int = 3,
                 base_delay: float = 1.0,
                 max_delay: float = 60.0,
                 exponential_base: float = 2.0,
                 jitter: bool = True):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
    
    def get_delay(self, attempt: int) -> float:
        """计算重试延迟时间"""
        delay = self.base_delay * (self.exponential_base ** (attempt - 1))
        delay = min(delay, self.max_delay)
        
        if self.jitter:
            import random
            delay *= (0.5 + random.random() * 0.5)  # 添加50%的随机抖动
        
        return delay


class UTCPLogger:
    """UTCP统一日志记录器"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self._setup_logger()
    
    def _setup_logger(self):
        """设置日志记录器"""
        if not self.logger.handlers:
            # 创建控制台处理器
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            
            # 创建格式化器
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(formatter)
            
            self.logger.addHandler(console_handler)
            self.logger.setLevel(logging.INFO)
    
    def log_error(self, error: UTCPError):
        """记录错误"""
        log_data = {
            "error_code": error.code,
            "severity": error.severity.value,
            "category": error.category.value,
            "service": error.context.service_name,
            "tool": error.context.tool_name,
            "message": error.message,
            "user_message": error.user_message,
            "request_id": error.context.request_id
        }
        
        if error.severity in [ErrorSeverity.CRITICAL, ErrorSeverity.HIGH]:
            self.logger.error(f"UTCP Error: {log_data}", extra={"error_data": log_data})
            if error.stack_trace:
                self.logger.error(f"Stack trace: {error.stack_trace}")
        elif error.severity == ErrorSeverity.MEDIUM:
            self.logger.warning(f"UTCP Warning: {log_data}", extra={"error_data": log_data})
        else:
            self.logger.info(f"UTCP Info: {log_data}", extra={"error_data": log_data})
    
    def log_operation(self, operation: str, context: ErrorContext, 
                     duration: Optional[float] = None, success: bool = True):
        """记录操作日志"""
        log_data = {
            "operation": operation,
            "service": context.service_name,
            "tool": context.tool_name,
            "duration": duration,
            "success": success,
            "timestamp": context.timestamp.isoformat(),
            "request_id": context.request_id
        }
        
        if success:
            self.logger.info(f"Operation completed: {operation}", extra={"operation_data": log_data})
        else:
            self.logger.warning(f"Operation failed: {operation}", extra={"operation_data": log_data})


class ErrorHandler:
    """UTCP错误处理器"""
    
    def __init__(self):
        self.logger = UTCPLogger("utcp.error_handler")
        self._error_stats: Dict[str, int] = {}
        self._last_error_time: Dict[str, datetime] = {}
    
    def create_error(self, 
                    code: str,
                    message: str,
                    severity: ErrorSeverity,
                    category: ErrorCategory,
                    context: ErrorContext,
                    original_exception: Optional[Exception] = None,
                    recovery_suggestions: Optional[List[str]] = None) -> UTCPError:
        """创建UTCP错误"""
        error = UTCPError(
            code=code,
            message=message,
            severity=severity,
            category=category,
            context=context,
            original_exception=original_exception,
            recovery_suggestions=recovery_suggestions or []
        )
        
        # 记录错误统计
        self._update_error_stats(error)
        
        # 记录日志
        self.logger.log_error(error)
        
        return error
    
    def _update_error_stats(self, error: UTCPError):
        """更新错误统计"""
        error_key = f"{error.context.service_name}:{error.code}"
        self._error_stats[error_key] = self._error_stats.get(error_key, 0) + 1
        self._last_error_time[error_key] = error.context.timestamp
    
    def get_error_stats(self) -> Dict[str, Any]:
        """获取错误统计信息"""
        return {
            "error_counts": self._error_stats.copy(),
            "last_error_times": {
                key: time.isoformat() for key, time in self._last_error_time.items()
            }
        }
    
    def should_circuit_break(self, service_name: str, error_threshold: int = 10, 
                           time_window: int = 300) -> bool:
        """判断是否应该熔断服务"""
        current_time = datetime.now()
        error_count = 0
        
        for key, count in self._error_stats.items():
            if key.startswith(f"{service_name}:"):
                last_error_time = self._last_error_time.get(key)
                if (last_error_time and 
                    (current_time - last_error_time).total_seconds() <= time_window):
                    error_count += count
        
        return error_count >= error_threshold


def with_error_handling(service_name: str, tool_name: Optional[str] = None,
                       retry_config: Optional[RetryConfig] = None):
    """错误处理装饰器"""
    def decorator(func: Callable):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            error_handler = ErrorHandler()
            context = ErrorContext(
                service_name=service_name,
                tool_name=tool_name,
                request_id=f"{service_name}_{int(time.time() * 1000)}"
            )
            
            start_time = time.time()
            attempt = 1
            max_attempts = retry_config.max_attempts if retry_config else 1
            
            while attempt <= max_attempts:
                try:
                    result = await func(*args, **kwargs)
                    
                    # 记录成功操作
                    duration = time.time() - start_time
                    error_handler.logger.log_operation(
                        f"{service_name}.{tool_name or func.__name__}",
                        context, duration, True
                    )
                    
                    return result
                    
                except Exception as e:
                    # 分析错误类型
                    category, severity = _analyze_exception(e)
                    
                    # 创建UTCP错误
                    utcp_error = error_handler.create_error(
                        code=f"{service_name.upper()}_{type(e).__name__.upper()}",
                        message=str(e),
                        severity=severity,
                        category=category,
                        context=context,
                        original_exception=e,
                        recovery_suggestions=_get_recovery_suggestions(category)
                    )
                    
                    # 判断是否应该重试
                    if (attempt < max_attempts and 
                        retry_config and 
                        _should_retry(category, severity)):
                        
                        delay = retry_config.get_delay(attempt)
                        error_handler.logger.logger.info(
                            f"Retrying {service_name}.{tool_name} in {delay:.2f}s "
                            f"(attempt {attempt + 1}/{max_attempts})"
                        )
                        await asyncio.sleep(delay)
                        attempt += 1
                        continue
                    
                    # 记录失败操作
                    duration = time.time() - start_time
                    error_handler.logger.log_operation(
                        f"{service_name}.{tool_name or func.__name__}",
                        context, duration, False
                    )
                    
                    return utcp_error.to_dict()
            
            # 如果所有重试都失败了
            return error_handler.create_error(
                code=f"{service_name.upper()}_MAX_RETRIES_EXCEEDED",
                message=f"操作在{max_attempts}次尝试后仍然失败",
                severity=ErrorSeverity.HIGH,
                category=ErrorCategory.SERVICE,
                context=context
            ).to_dict()
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # 同步函数的错误处理
            error_handler = ErrorHandler()
            context = ErrorContext(
                service_name=service_name,
                tool_name=tool_name,
                request_id=f"{service_name}_{int(time.time() * 1000)}"
            )
            
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                
                # 记录成功操作
                duration = time.time() - start_time
                error_handler.logger.log_operation(
                    f"{service_name}.{tool_name or func.__name__}",
                    context, duration, True
                )
                
                return result
                
            except Exception as e:
                # 分析错误类型
                category, severity = _analyze_exception(e)
                
                # 创建UTCP错误
                utcp_error = error_handler.create_error(
                    code=f"{service_name.upper()}_{type(e).__name__.upper()}",
                    message=str(e),
                    severity=severity,
                    category=category,
                    context=context,
                    original_exception=e,
                    recovery_suggestions=_get_recovery_suggestions(category)
                )
                
                # 记录失败操作
                duration = time.time() - start_time
                error_handler.logger.log_operation(
                    f"{service_name}.{tool_name or func.__name__}",
                    context, duration, False
                )
                
                return utcp_error.to_dict()
        
        # 根据函数类型返回相应的包装器
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def _analyze_exception(exception: Exception) -> tuple[ErrorCategory, ErrorSeverity]:
    """分析异常类型，返回分类和严重程度"""
    exception_type = type(exception).__name__
    exception_message = str(exception).lower()
    
    # 网络相关错误
    if any(keyword in exception_type.lower() for keyword in 
           ['connection', 'timeout', 'network', 'http', 'client']):
        return ErrorCategory.NETWORK, ErrorSeverity.MEDIUM
    
    # API相关错误
    if any(keyword in exception_message for keyword in 
           ['api', '401', '403', '404', '500', '502', '503']):
        return ErrorCategory.API, ErrorSeverity.MEDIUM
    
    # 验证错误
    if any(keyword in exception_type.lower() for keyword in 
           ['value', 'type', 'attribute', 'key']):
        return ErrorCategory.VALIDATION, ErrorSeverity.LOW
    
    # 权限错误
    if any(keyword in exception_message for keyword in 
           ['permission', 'unauthorized', 'forbidden']):
        return ErrorCategory.PERMISSION, ErrorSeverity.HIGH
    
    # 超时错误
    if 'timeout' in exception_message:
        return ErrorCategory.TIMEOUT, ErrorSeverity.MEDIUM
    
    # 默认为服务错误
    return ErrorCategory.SERVICE, ErrorSeverity.MEDIUM


def _should_retry(category: ErrorCategory, severity: ErrorSeverity) -> bool:
    """判断是否应该重试"""
    # 不重试的情况
    no_retry_categories = [
        ErrorCategory.VALIDATION,
        ErrorCategory.PERMISSION,
        ErrorCategory.AUTHENTICATION,
        ErrorCategory.CONFIGURATION
    ]
    
    if category in no_retry_categories:
        return False
    
    if severity == ErrorSeverity.CRITICAL:
        return False
    
    return True


def _get_recovery_suggestions(category: ErrorCategory) -> List[str]:
    """获取恢复建议"""
    suggestions = {
        ErrorCategory.VALIDATION: [
            "检查输入参数的格式和类型",
            "确保所有必需参数都已提供",
            "参考API文档确认参数要求"
        ],
        ErrorCategory.NETWORK: [
            "检查网络连接",
            "稍后重试",
            "确认目标服务是否可用"
        ],
        ErrorCategory.API: [
            "检查API密钥是否有效",
            "确认API服务状态",
            "检查请求频率限制"
        ],
        ErrorCategory.SERVICE: [
            "稍后重试",
            "检查服务配置",
            "联系技术支持"
        ],
        ErrorCategory.CONFIGURATION: [
            "检查配置文件",
            "确认环境变量设置",
            "联系管理员"
        ],
        ErrorCategory.TIMEOUT: [
            "增加超时时间",
            "稍后重试",
            "检查网络状况"
        ],
        ErrorCategory.AUTHENTICATION: [
            "检查认证凭据",
            "重新登录",
            "确认账户状态"
        ],
        ErrorCategory.PERMISSION: [
            "检查用户权限",
            "联系管理员",
            "确认操作权限"
        ]
    }
    
    return suggestions.get(category, ["稍后重试", "联系技术支持"])


# 全局错误处理器实例
global_error_handler = ErrorHandler()