"""
核心基础设施组件

提供统一的配置管理、日志管理、数据库管理、Redis管理和工具功能。
"""

from .config.manager import ConfigManager
from .logging.manager import LoggingManager
from .database.manager import DatabaseManager, get_db_manager, initialize_db, is_db_ready
from .redis.manager import RedisManager, get_redis_manager, initialize_redis, is_redis_ready
from .utils.environment import EnvironmentManager
from .exceptions import (
    CoreError,
    ConfigurationError,
    PathError,
    LoggingError,
    ValidationError,
    DatabaseError,
    DatabaseConnectionError,
    DatabaseQueryError,
    DatabaseTransactionError,
    RedisError,
    RedisConnectionError,
    RedisOperationError,
    RedisSerializationError
)

__all__ = [
    'ConfigManager',
    'LoggingManager',
    'DatabaseManager',
    'get_db_manager',
    'initialize_db',
    'is_db_ready',
    'RedisManager',
    'get_redis_manager',
    'initialize_redis',
    'is_redis_ready',
    'EnvironmentManager',
    'CoreError',
    'ConfigurationError',
    'PathError',
    'LoggingError',
    'ValidationError',
    'DatabaseError',
    'DatabaseConnectionError',
    'DatabaseQueryError',
    'DatabaseTransactionError',
    'RedisError',
    'RedisConnectionError',
    'RedisOperationError',
    'RedisSerializationError'
]

__version__ = "1.0.0" 