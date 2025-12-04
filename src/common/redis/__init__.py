"""
Redis核心模块
"""

from .manager import RedisManager
from .exceptions import (
    RedisError,
    RedisConnectionError,
    RedisOperationError,
    RedisSerializationError
)

__all__ = [
    'RedisManager',
    'RedisError',
    'RedisConnectionError',
    'RedisOperationError',
    'RedisSerializationError'
]