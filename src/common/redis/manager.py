"""
Redis管理器主类
"""

import logging
from typing import Dict, Any, List, Optional, Set, Union, Callable
from redis import Redis
from .connection import RedisConnectionPool
from .serializer import RedisSerializer
from .exceptions import RedisError, RedisConnectionError, RedisOperationError, RedisSerializationError
from ..exceptions import ConfigurationError

# 全局Redis管理器实例
_redis_manager = None


class RedisManager:
    """统一Redis管理器"""
    
    def __init__(self, config_manager, logging_manager):
        """初始化Redis管理器"""
        self.config_manager = config_manager
        self.logging_manager = logging_manager
        
        # 加载配置
        self._load_config()
        
        # 获取日志记录器
        self.logger = self.logging_manager.get_logger("redis")
        
        # 初始化序列化器
        self._init_serializer()
        
        # 初始化连接池
        self._init_connection_pool()
        
    
    def _load_config(self):
        """加载Redis配置"""
        try:
            # 尝试从配置文件加载
            self.config = self.config_manager.get_config("redis")
            if not self.config:
                # 如果配置文件为空，抛出异常
                raise ConfigurationError("Redis配置文件为空，请提供有效的Redis配置")
        except Exception as e:
            # 如果配置文件不存在或加载失败，抛出异常
            raise ConfigurationError(f"Redis配置加载失败: {e}")
    
    def _init_serializer(self):
        """初始化序列化器"""
        try:
            serializer_type = self.config.get('default_serializer', 'json')
            self.serializer = RedisSerializer(serializer_type, self.logger)
        except Exception as e:
            error_msg = f"Redis序列化器初始化失败: {e}"
            self.logger.error(error_msg)
            raise RedisSerializationError(error_msg)
    
    def _init_connection_pool(self):
        """初始化连接池"""
        try:
            self.pool = RedisConnectionPool(self.config, self.logger)
        except Exception as e:
            error_msg = f"Redis连接池初始化失败: {e}"
            self.logger.error(error_msg)
            raise RedisConnectionError(error_msg)
    
    async def initialize(self):
        """异步初始化Redis管理器"""
        try:
            # 连接池已经在__init__中初始化，这里只需要验证连接
            conn = self._get_connection()
            conn.ping()
            self.logger.debug("Redis管理器初始化完成")
        except Exception as e:
            error_msg = f"Redis管理器初始化失败: {e}"
            self.logger.error(error_msg)
            raise RedisConnectionError(error_msg)
    
    async def close(self):
        """异步关闭Redis管理器"""
        try:
            self.pool.close_all_connections()
            self.logger.info("Redis管理器已关闭")
        except Exception as e:
            self.logger.error(f"关闭Redis管理器时出错: {e}")
    
    def _get_connection(self) -> Redis:
        """获取Redis连接"""
        try:
            return self.pool.get_connection()
        except Exception as e:
            error_msg = f"获取Redis连接失败: {e}"
            self.logger.error(error_msg)
            raise RedisConnectionError(error_msg)
    
    def _add_key_prefix(self, key: str) -> str:
        """添加键前缀"""
        prefix = self.config.get('key_prefix', '')
        return f"{prefix}{key}" if prefix else key
    
    def _remove_key_prefix(self, key: str) -> str:
        """移除键前缀"""
        prefix = self.config.get('key_prefix', '')
        if prefix and key.startswith(prefix):
            return key[len(prefix):]
        return key
    
    def _log_operation(self, operation: str, key: str = None, execution_time: float = None):
        """记录操作日志"""
        if self.config.get('logging', {}).get('log_operations', False):
            self.logger.debug(f"Redis操作: {operation}, 键: {key}, 耗时: {execution_time:.3f}秒" if execution_time else f"Redis操作: {operation}, 键: {key}")
        
        # 记录慢操作
        slow_threshold = self.config.get('logging', {}).get('slow_operation_threshold', 0.1)
        if (execution_time and 
            self.config.get('logging', {}).get('log_slow_operations', True) and 
            execution_time > slow_threshold):
            self.logger.warning(f"Redis慢操作检测: {operation}, 键: {key}, 耗时: {execution_time:.3f}秒")
    
    # 基本操作
    def set(self, key: str, value: Any, expire: int = None) -> bool:
        """设置键值"""
        import time
        start_time = time.time()
        
        try:
            conn = self._get_connection()
            prefixed_key = self._add_key_prefix(key)
            
            # 序列化值
            serialized_value = self.serializer.serialize(value)
            
            # 设置值
            result = conn.set(prefixed_key, serialized_value, ex=expire)
            
            execution_time = time.time() - start_time
            self._log_operation("SET", key, execution_time)
            
            return bool(result)
            
        except Exception as e:
            error_msg = f"Redis SET操作失败: {key}, 错误: {e}"
            self.logger.error(error_msg)
            raise RedisOperationError(error_msg)
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取键值"""
        import time
        start_time = time.time()
        
        try:
            conn = self._get_connection()
            prefixed_key = self._add_key_prefix(key)
            
            # 获取值
            result = conn.get(prefixed_key)
            
            execution_time = time.time() - start_time
            self._log_operation("GET", key, execution_time)
            
            if result is None:
                return default
            
            # 反序列化值
            return self.serializer.deserialize(result)
            
        except Exception as e:
            error_msg = f"Redis GET操作失败: {key}, 错误: {e}"
            self.logger.error(error_msg)
            raise RedisOperationError(error_msg)
    
    def delete(self, *keys: str) -> int:
        """删除键"""
        import time
        start_time = time.time()
        
        try:
            conn = self._get_connection()
            prefixed_keys = [self._add_key_prefix(key) for key in keys]
            
            # 删除键
            result = conn.delete(*prefixed_keys)
            
            execution_time = time.time() - start_time
            self._log_operation("DELETE", f"{len(keys)}个键", execution_time)
            
            return result
            
        except Exception as e:
            error_msg = f"Redis DELETE操作失败: {keys}, 错误: {e}"
            self.logger.error(error_msg)
            raise RedisOperationError(error_msg)
    
    def exists(self, key: str) -> bool:
        """检查键是否存在"""
        try:
            conn = self._get_connection()
            prefixed_key = self._add_key_prefix(key)
            
            result = conn.exists(prefixed_key)
            return bool(result)
            
        except Exception as e:
            error_msg = f"Redis EXISTS操作失败: {key}, 错误: {e}"
            self.logger.error(error_msg)
            raise RedisOperationError(error_msg)
    
    # 批量操作
    def mset(self, mapping: Dict[str, Any], expire: int = None) -> bool:
        """批量设置键值"""
        import time
        start_time = time.time()
        
        try:
            conn = self._get_connection()
            
            # 序列化所有值并添加前缀
            serialized_mapping = {}
            for key, value in mapping.items():
                prefixed_key = self._add_key_prefix(key)
                serialized_value = self.serializer.serialize(value)
                serialized_mapping[prefixed_key] = serialized_value
            
            # 批量设置
            result = conn.mset(serialized_mapping)
            
            # 如果设置了过期时间，需要逐个设置
            if expire and result:
                pipe = conn.pipeline()
                for prefixed_key in serialized_mapping.keys():
                    pipe.expire(prefixed_key, expire)
                pipe.execute()
            
            execution_time = time.time() - start_time
            self._log_operation("MSET", f"{len(mapping)}个键", execution_time)
            
            return bool(result)
            
        except Exception as e:
            error_msg = f"Redis MSET操作失败: 错误: {e}"
            self.logger.error(error_msg)
            raise RedisOperationError(error_msg)
    
    def mget(self, keys: List[str]) -> List[Any]:
        """批量获取键值"""
        import time
        start_time = time.time()
        
        try:
            conn = self._get_connection()
            prefixed_keys = [self._add_key_prefix(key) for key in keys]
            
            # 批量获取
            results = conn.mget(prefixed_keys)
            
            execution_time = time.time() - start_time
            self._log_operation("MGET", f"{len(keys)}个键", execution_time)
            
            # 反序列化结果
            deserialized_results = []
            for result in results:
                if result is None:
                    deserialized_results.append(None)
                else:
                    deserialized_results.append(self.serializer.deserialize(result))
            
            return deserialized_results
            
        except Exception as e:
            error_msg = f"Redis MGET操作失败: 错误: {e}"
            self.logger.error(error_msg)
            raise RedisOperationError(error_msg)
    
    def delete_pattern(self, pattern: str) -> int:
        """按模式删除键"""
        import time
        start_time = time.time()
        
        try:
            conn = self._get_connection()
            prefixed_pattern = self._add_key_prefix(pattern)
            
            # 查找匹配的键
            keys = conn.keys(prefixed_pattern)
            
            if not keys:
                return 0
            
            # 删除键
            result = conn.delete(*keys)
            
            execution_time = time.time() - start_time
            self._log_operation("DELETE_PATTERN", pattern, execution_time)
            
            return result
            
        except Exception as e:
            error_msg = f"Redis DELETE_PATTERN操作失败: {pattern}, 错误: {e}"
            self.logger.error(error_msg)
            raise RedisOperationError(error_msg)
    
    # 数据结构操作
    def hset(self, name: str, mapping: Dict[str, Any]) -> int:
        """设置哈希字段"""
        try:
            conn = self._get_connection()
            prefixed_name = self._add_key_prefix(name)
            
            # 序列化所有值
            serialized_mapping = {}
            for field, value in mapping.items():
                serialized_mapping[field] = self.serializer.serialize(value)
            
            result = conn.hset(prefixed_name, mapping=serialized_mapping)
            return result
            
        except Exception as e:
            error_msg = f"Redis HSET操作失败: {name}, 错误: {e}"
            self.logger.error(error_msg)
            raise RedisOperationError(error_msg)
    
    def hget(self, name: str, key: str) -> Any:
        """获取哈希字段值"""
        try:
            conn = self._get_connection()
            prefixed_name = self._add_key_prefix(name)
            
            result = conn.hget(prefixed_name, key)
            
            if result is None:
                return None
            
            return self.serializer.deserialize(result)
            
        except Exception as e:
            error_msg = f"Redis HGET操作失败: {name}.{key}, 错误: {e}"
            self.logger.error(error_msg)
            raise RedisOperationError(error_msg)
    
    def hgetall(self, name: str) -> Dict[str, Any]:
        """获取所有哈希字段"""
        try:
            conn = self._get_connection()
            prefixed_name = self._add_key_prefix(name)
            
            result = conn.hgetall(prefixed_name)
            
            # 反序列化所有值
            deserialized_result = {}
            for field, value in result.items():
                field_str = field.decode('utf-8') if isinstance(field, bytes) else field
                deserialized_result[field_str] = self.serializer.deserialize(value)
            
            return deserialized_result
            
        except Exception as e:
            error_msg = f"Redis HGETALL操作失败: {name}, 错误: {e}"
            self.logger.error(error_msg)
            raise RedisOperationError(error_msg)
    
    def lpush(self, name: str, *values: Any) -> int:
        """左推入列表"""
        try:
            conn = self._get_connection()
            prefixed_name = self._add_key_prefix(name)
            
            # 序列化所有值
            serialized_values = [self.serializer.serialize(value) for value in values]
            
            result = conn.lpush(prefixed_name, *serialized_values)
            return result
            
        except Exception as e:
            error_msg = f"Redis LPUSH操作失败: {name}, 错误: {e}"
            self.logger.error(error_msg)
            raise RedisOperationError(error_msg)
    
    def rpop(self, name: str) -> Any:
        """右弹出列表"""
        try:
            conn = self._get_connection()
            prefixed_name = self._add_key_prefix(name)
            
            result = conn.rpop(prefixed_name)
            
            if result is None:
                return None
            
            return self.serializer.deserialize(result)
            
        except Exception as e:
            error_msg = f"Redis RPOP操作失败: {name}, 错误: {e}"
            self.logger.error(error_msg)
            raise RedisOperationError(error_msg)
    
    def sadd(self, name: str, *values: Any) -> int:
        """添加集合成员"""
        try:
            conn = self._get_connection()
            prefixed_name = self._add_key_prefix(name)
            
            # 序列化所有值
            serialized_values = [self.serializer.serialize(value) for value in values]
            
            result = conn.sadd(prefixed_name, *serialized_values)
            return result
            
        except Exception as e:
            error_msg = f"Redis SADD操作失败: {name}, 错误: {e}"
            self.logger.error(error_msg)
            raise RedisOperationError(error_msg)
    
    def smembers(self, name: str) -> Set[Any]:
        """获取集合所有成员"""
        try:
            conn = self._get_connection()
            prefixed_name = self._add_key_prefix(name)
            
            result = conn.smembers(prefixed_name)
            
            # 反序列化所有值
            deserialized_result = set()
            for value in result:
                deserialized_result.add(self.serializer.deserialize(value))
            
            return deserialized_result
            
        except Exception as e:
            error_msg = f"Redis SMEMBERS操作失败: {name}, 错误: {e}"
            self.logger.error(error_msg)
            raise RedisOperationError(error_msg)
    
    # 事务支持
    def pipeline(self):
        """获取管道对象"""
        try:
            conn = self._get_connection()
            return conn.pipeline()
        except Exception as e:
            error_msg = f"Redis PIPELINE创建失败: {e}"
            self.logger.error(error_msg)
            raise RedisOperationError(error_msg)
    
    def multi_exec(self, commands: List[Callable]) -> List[Any]:
        """执行多个命令（事务）"""
        try:
            pipe = self.pipeline()
            pipe.multi()
            
            # 执行所有命令
            for command in commands:
                command(pipe)
            
            # 执行事务
            results = pipe.execute()
            return results
            
        except Exception as e:
            error_msg = f"Redis事务执行失败: {e}"
            self.logger.error(error_msg)
            raise RedisOperationError(error_msg)
    
    # 健康检查
    def ping(self) -> bool:
        """Ping测试"""
        try:
            conn = self._get_connection()
            result = conn.ping()
            return bool(result)
        except Exception as e:
            self.logger.error(f"Redis PING失败: {e}")
            return False
    
    def health_check(self) -> Dict[str, Any]:
        """Redis健康检查"""
        try:
            # 连接池健康检查
            pool_healthy = self.pool.health_check()
            
            # Ping测试
            ping_healthy = self.ping()
            
            # 简单操作测试
            operation_healthy = False
            try:
                test_key = "health_check_test"
                self.set(test_key, "test_value", expire=10)
                result = self.get(test_key)
                operation_healthy = result == "test_value"
                self.delete(test_key)
            except Exception as e:
                self.logger.warning(f"Redis操作健康检查失败: {e}")
            
            # 获取连接池统计
            pool_stats = self.pool.get_pool_stats()
            
            return {
                "status": "healthy" if (pool_healthy and ping_healthy and operation_healthy) else "unhealthy",
                "pool_healthy": pool_healthy,
                "ping_healthy": ping_healthy,
                "operation_healthy": operation_healthy,
                "pool_stats": pool_stats,
                "config": {
                    "host": self.config.get('host'),
                    "port": self.config.get('port'),
                    "database": self.config.get('database')
                }
            }
            
        except Exception as e:
            error_msg = f"Redis健康检查失败: {e}"
            self.logger.error(error_msg)
            return {
                "status": "error",
                "error": error_msg
            }
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接统计信息"""
        try:
            return self.pool.get_pool_stats()
        except Exception as e:
            self.logger.error(f"获取Redis连接统计失败: {e}")
            return {"error": str(e)}


# 全局便捷访问函数
def get_redis_manager() -> RedisManager:
    """获取Redis管理器实例
    
    Returns:
        RedisManager: Redis管理器实例
        
    Raises:
        RuntimeError: Redis管理器未初始化
    """
    global _redis_manager
    if _redis_manager is None:
        raise RuntimeError("Redis管理器未初始化")
    return _redis_manager


async def initialize_redis(config_manager, logging_manager) -> RedisManager:
    """初始化Redis管理器
    
    Args:
        config_manager: 配置管理器
        logging_manager: 日志管理器
        
    Returns:
        RedisManager: 初始化后的Redis管理器实例
    """
    global _redis_manager
    
    # 创建Redis管理器
    redis_manager = RedisManager(config_manager, logging_manager)
    
    # 初始化Redis管理器
    await redis_manager.initialize()
    
    # 设置全局实例
    _redis_manager = redis_manager
    
    return redis_manager


def is_redis_ready() -> bool:
    """检查Redis管理器是否已初始化
    
    Returns:
        bool: 是否已初始化
    """
    global _redis_manager
    return _redis_manager is not None