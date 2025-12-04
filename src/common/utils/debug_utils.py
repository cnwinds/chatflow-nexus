#!/usr/bin/env python3
"""
调试工具模块

提供通用的调试和日志工具函数。
"""

import logging
import traceback
from typing import Optional, List, Dict, Any, Callable
from functools import wraps


def log_call_stack(
    logger: Optional[logging.Logger] = None,
    message: str = "调用栈:",
    max_frames: int = 5,
    skip_frames: int = 1,
    include_args: bool = False,
    log_level: int = logging.INFO
) -> None:
    """
    输出当前调用栈的通用函数
    
    Args:
        logger: 日志记录器，如果为None则使用默认logger
        message: 调用栈前的说明信息
        max_frames: 最大显示帧数，默认5层
        skip_frames: 跳过的帧数，默认1（跳过当前函数）
        include_args: 是否包含函数参数信息
        log_level: 日志级别，默认INFO
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    stack = traceback.extract_stack()
    
    # 过滤掉指定数量的帧
    relevant_stack = stack[:-skip_frames] if skip_frames > 0 else stack
    
    if relevant_stack:
        logger.log(log_level, f"{message}")
        
        # 只显示最近的几层
        display_stack = relevant_stack[-max_frames:] if max_frames > 0 else relevant_stack
        
        for i, frame in enumerate(display_stack, 1):
            filename = frame.filename.split('/')[-1] if '/' in frame.filename else frame.filename
            filename = filename.split('\\')[-1] if '\\' in filename else filename
            
            frame_info = f"  {i}. {filename}:{frame.lineno} in {frame.name}()"
            
            if include_args and frame.line:
                frame_info += f" -> {frame.line.strip()}"
            
            logger.log(log_level, frame_info)
    else:
        logger.log(log_level, f"{message} (无调用栈信息)")


def log_call_stack_with_context(
    logger: Optional[logging.Logger] = None,
    message: str = "调用栈:",
    context: Optional[Dict[str, Any]] = None,
    max_frames: int = 5,
    skip_frames: int = 1,
    log_level: int = logging.INFO
) -> None:
    """
    输出当前调用栈并包含上下文信息
    
    Args:
        logger: 日志记录器，如果为None则使用默认logger
        message: 调用栈前的说明信息
        context: 上下文信息字典
        max_frames: 最大显示帧数，默认5层
        skip_frames: 跳过的帧数，默认1（跳过当前函数）
        log_level: 日志级别，默认INFO
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    # 输出上下文信息
    if context:
        context_str = ", ".join([f"{k}={v}" for k, v in context.items()])
        logger.log(log_level, f"{message} [上下文: {context_str}]")
    else:
        logger.log(log_level, f"{message}")
    
    # 输出调用栈
    log_call_stack(
        logger=logger,
        message="",  # 空消息，因为上面已经输出了
        max_frames=max_frames,
        skip_frames=skip_frames + 1,  # 额外跳过当前函数
        log_level=log_level
    )


def debug_call_stack(
    func: Optional[Callable] = None,
    *,
    logger: Optional[logging.Logger] = None,
    message: str = "函数调用栈:",
    max_frames: int = 5,
    log_level: int = logging.DEBUG
):
    """
    装饰器：在函数调用时输出调用栈
    
    Args:
        func: 被装饰的函数
        logger: 日志记录器
        message: 调用栈前的说明信息
        max_frames: 最大显示帧数
        log_level: 日志级别
    
    Usage:
        @debug_call_stack
        def my_function():
            pass
            
        @debug_call_stack(message="进入函数", max_frames=3)
        def another_function():
            pass
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            log_call_stack(
                logger=logger,
                message=f"{message} {func.__name__}",
                max_frames=max_frames,
                skip_frames=1,
                log_level=log_level
            )
            return func(*args, **kwargs)
        return wrapper
    
    if func is None:
        return decorator
    else:
        return decorator(func)


def log_exception_with_stack(
    logger: Optional[logging.Logger] = None,
    message: str = "异常调用栈:",
    exception: Optional[Exception] = None,
    max_frames: int = 10,
    log_level: int = logging.ERROR
) -> None:
    """
    输出异常信息和调用栈
    
    Args:
        logger: 日志记录器，如果为None则使用默认logger
        message: 异常前的说明信息
        exception: 异常对象，如果为None则获取当前异常
        max_frames: 最大显示帧数
        log_level: 日志级别，默认ERROR
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    if exception is None:
        exception = Exception("未指定异常")
    
    logger.log(log_level, f"{message} {type(exception).__name__}: {exception}")
    
    # 获取异常跟踪信息
    exc_type, exc_value, exc_traceback = type(exception), exception, exception.__traceback__
    
    if exc_traceback:
        # 提取堆栈帧
        stack = traceback.extract_tb(exc_traceback)
        
        if stack:
            logger.log(log_level, "异常堆栈:")
            display_stack = stack[-max_frames:] if max_frames > 0 else stack
            
            for i, frame in enumerate(display_stack, 1):
                filename = frame.filename.split('/')[-1] if '/' in frame.filename else frame.filename
                filename = filename.split('\\')[-1] if '\\' in filename else filename
                
                frame_info = f"  {i}. {filename}:{frame.lineno} in {frame.name}()"
                if frame.line:
                    frame_info += f" -> {frame.line.strip()}"
                
                logger.log(log_level, frame_info)
    else:
        logger.log(log_level, "无异常堆栈信息")


def get_simple_call_stack(max_frames: int = 3, skip_frames: int = 1) -> List[str]:
    """
    获取简化的调用栈信息列表
    
    Args:
        max_frames: 最大显示帧数
        skip_frames: 跳过的帧数
    
    Returns:
        调用栈信息列表，每个元素格式为 "filename:line function_name"
    """
    stack = traceback.extract_stack()
    relevant_stack = stack[:-skip_frames] if skip_frames > 0 else stack
    display_stack = relevant_stack[-max_frames:] if max_frames > 0 else relevant_stack
    
    result = []
    for frame in display_stack:
        filename = frame.filename.split('/')[-1] if '/' in frame.filename else frame.filename
        filename = filename.split('\\')[-1] if '\\' in filename else filename
        result.append(f"{filename}:{frame.lineno} {frame.name}")
    
    return result
