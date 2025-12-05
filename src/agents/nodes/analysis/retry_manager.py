"""
重试管理器

处理失败任务的重试逻辑，使用指数退避策略。
"""

import asyncio
import random
from src.common.logging import get_logger
from typing import Optional, Callable, Any
from dataclasses import dataclass


logger = get_logger(__name__)


@dataclass
class RetryConfig:
    """重试配置"""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True


class RetryManager:
    """重试管理器"""
    
    def __init__(self, config: Optional[RetryConfig] = None):
        """初始化重试管理器
        
        Args:
            config: 重试配置，如果为None则使用默认配置
        """
        self.config = config or RetryConfig()
    
    def should_retry(self, error: Exception, attempt: int) -> bool:
        """判断是否应该重试
        
        Args:
            error: 异常对象
            attempt: 当前尝试次数
            
        Returns:
            是否应该重试
        """
        if attempt >= self.config.max_attempts:
            return False
        
        # 不重试的情况
        error_type = type(error).__name__
        no_retry_errors = [
            'ValueError',
            'TypeError',
            'KeyError',
            'AttributeError',
            'JSONDecodeError',
        ]
        
        if error_type in no_retry_errors:
            return False
        
        # 网络错误、超时等可重试
        retry_errors = [
            'ConnectionError',
            'TimeoutError',
            'NetworkError',
            'ServiceUnavailable',
        ]
        
        error_str = str(error).lower()
        if any(retry_error.lower() in error_str for retry_error in retry_errors):
            return True
        
        # 默认重试（除了明确的不可重试错误）
        return True
    
    def get_retry_delay(self, attempt: int) -> float:
        """计算重试延迟时间（指数退避）
        
        Args:
            attempt: 当前尝试次数（从1开始）
            
        Returns:
            延迟时间（秒）
        """
        # 计算指数延迟
        delay = self.config.base_delay * (self.config.exponential_base ** (attempt - 1))
        
        # 限制最大延迟
        delay = min(delay, self.config.max_delay)
        
        # 添加随机抖动（避免雷群效应）
        if self.config.jitter:
            delay *= (0.5 + random.random() * 0.5)  # 50%到100%之间的随机值
        
        return delay
    
    async def process_with_retry(
        self,
        func: Callable[[], Any],
        task_name: str = "任务"
    ) -> tuple[bool, Optional[Any], Optional[str]]:
        """带重试的处理逻辑
        
        Args:
            func: 要执行的异步函数
            task_name: 任务名称（用于日志）
            
        Returns:
            (是否成功, 结果, 错误信息)
        """
        attempt = 1
        
        while attempt <= self.config.max_attempts:
            try:
                result = await func()
                if attempt > 1:
                    logger.info(f"{task_name}在第{attempt}次尝试时成功")
                return True, result, None
                
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"{task_name}第{attempt}次尝试失败: {error_msg}")
                
                # 判断是否应该重试
                if not self.should_retry(e, attempt):
                    logger.error(f"{task_name}失败且不应重试: {error_msg}")
                    return False, None, error_msg
                
                # 如果还有重试机会
                if attempt < self.config.max_attempts:
                    delay = self.get_retry_delay(attempt)
                    logger.info(f"{task_name}将在{delay:.2f}秒后重试（第{attempt + 1}/{self.config.max_attempts}次）")
                    await asyncio.sleep(delay)
                    attempt += 1
                else:
                    # 所有重试都失败了
                    logger.error(f"{task_name}在{self.config.max_attempts}次尝试后仍然失败")
                    return False, None, error_msg
        
        return False, None, "达到最大重试次数"

