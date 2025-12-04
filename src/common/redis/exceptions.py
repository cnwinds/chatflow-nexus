"""
Redis异常定义
"""

from ..exceptions import RedisError, RedisConnectionError, RedisOperationError, RedisSerializationError

# 重新导出异常，保持模块独立性
__all__ = [
    'RedisError',
    'RedisConnectionError',
    'RedisOperationError', 
    'RedisSerializationError'
]