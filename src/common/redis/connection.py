"""
Redis连接管理模块
"""

import time
import logging
from typing import Dict, Any, Optional
import redis
from redis import Redis
from .exceptions import RedisConnectionError


class RedisConnection:
    """Redis连接管理器"""
    
    def __init__(self, config: Dict[str, Any], logger: logging.Logger):
        """初始化Redis连接管理器"""
        self.config = config
        self.logger = logger
        self.connection: Optional[Redis] = None
        self._last_ping_time = 0
        self._ping_interval = 30  # 30秒检查一次连接
        
    def connect(self) -> Redis:
        """建立Redis连接"""
        try:
            # 基础连接参数
            connection_params = {
                'host': self.config.get('host', 'localhost'),
                'port': self.config.get('port', 6379),
                'db': self.config.get('database', 0),
                'password': self.config.get('password'),
                'socket_timeout': self.config.get('socket_timeout', 30),
                'socket_connect_timeout': self.config.get('connection_timeout', 10),
                'decode_responses': False,  # 我们手动处理编码
                'retry_on_timeout': True,
                'health_check_interval': 30
            }
            
            # 移除None值
            connection_params = {k: v for k, v in connection_params.items() if v is not None}
            
            # 创建连接
            self.connection = redis.Redis(**connection_params)
            
            # 测试连接
            self.connection.ping()
            
            self.logger.info(f"Redis连接成功: {self.config.get('host', 'localhost')}:{self.config.get('port', 6379)}")
            return self.connection
            
        except Exception as e:
            error_msg = f"Redis连接失败: {e}"
            self.logger.error(error_msg)
            raise RedisConnectionError(error_msg)
    
    def is_connected(self) -> bool:
        """检查连接是否有效"""
        if not self.connection:
            return False
            
        try:
            # 避免频繁ping，使用时间间隔控制
            current_time = time.time()
            if current_time - self._last_ping_time > self._ping_interval:
                self.connection.ping()
                self._last_ping_time = current_time
            return True
        except Exception:
            return False
    
    def ensure_connection(self) -> Redis:
        """确保连接有效，如果无效则重连"""
        if not self.is_connected():
            if self.config.get('auto_reconnect', True):
                self.logger.info("检测到Redis连接断开，尝试重连...")
                return self.reconnect()
            else:
                raise RedisConnectionError("Redis连接已断开且未启用自动重连")
        
        return self.connection
    
    def reconnect(self) -> Redis:
        """重新连接Redis"""
        max_attempts = self.config.get('max_reconnect_attempts', 3)
        delay = self.config.get('reconnect_delay', 1.0)
        
        for attempt in range(max_attempts):
            try:
                if self.connection:
                    try:
                        self.connection.close()
                    except Exception:
                        pass
                
                self.connection = None
                time.sleep(delay * (attempt + 1))  # 递增延迟
                
                return self.connect()
                
            except RedisConnectionError as e:
                if attempt == max_attempts - 1:
                    error_msg = f"Redis重连失败，已尝试 {max_attempts} 次: {e}"
                    self.logger.error(error_msg)
                    raise RedisConnectionError(error_msg)
                else:
                    self.logger.warning(f"Redis重连尝试 {attempt + 1} 失败，将在 {delay * (attempt + 2)} 秒后重试")
    
    def close(self):
        """关闭Redis连接"""
        if self.connection:
            try:
                self.connection.close()
                self.logger.info("Redis连接已关闭")
            except Exception as e:
                self.logger.warning(f"关闭Redis连接时出现警告: {e}")
            finally:
                self.connection = None
    
    def get_connection_info(self) -> Dict[str, Any]:
        """获取连接信息"""
        if not self.connection:
            return {"status": "disconnected"}
        
        try:
            info = self.connection.info()
            return {
                "status": "connected",
                "server_info": {
                    "redis_version": info.get('redis_version'),
                    "used_memory": info.get('used_memory'),
                    "connected_clients": info.get('connected_clients'),
                    "uptime_in_seconds": info.get('uptime_in_seconds')
                },
                "host": self.config.get('host'),
                "port": self.config.get('port'),
                "database": self.config.get('database')
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }


class RedisConnectionPool:
    """Redis连接池管理器"""
    
    def __init__(self, config: Dict[str, Any], logger: logging.Logger):
        """初始化Redis连接池"""
        self.config = config
        self.logger = logger
        
        # 连接池配置
        self.max_connections = config.get('max_connections', 50)
        
        # 创建连接池
        self._create_pool()
    
    def _create_pool(self):
        """创建Redis连接池"""
        try:
            # 连接池参数
            pool_params = {
                'host': self.config.get('host', 'localhost'),
                'port': self.config.get('port', 6379),
                'db': self.config.get('database', 0),
                'password': self.config.get('password'),
                'socket_timeout': self.config.get('socket_timeout', 30),
                'socket_connect_timeout': self.config.get('connection_timeout', 10),
                'max_connections': self.max_connections,
                'retry_on_timeout': True,
                'health_check_interval': 30
            }
            
            # 移除None值
            pool_params = {k: v for k, v in pool_params.items() if v is not None}
            
            # 创建连接池
            self.pool = redis.ConnectionPool(**pool_params)
            
            # 测试连接池
            test_conn = redis.Redis(connection_pool=self.pool)
            test_conn.ping()
            
            self.logger.info(f"Redis连接池创建成功，最大连接数: {self.max_connections}")
            
        except Exception as e:
            error_msg = f"Redis连接池创建失败: {e}"
            self.logger.error(error_msg)
            raise RedisConnectionError(error_msg)
    
    def get_connection(self) -> Redis:
        """从连接池获取连接"""
        try:
            return redis.Redis(connection_pool=self.pool, decode_responses=False)
        except Exception as e:
            error_msg = f"从Redis连接池获取连接失败: {e}"
            self.logger.error(error_msg)
            raise RedisConnectionError(error_msg)
    
    def return_connection(self, connection: Redis):
        """归还连接到连接池（Redis连接池自动管理）"""
        # Redis连接池会自动管理连接的归还
        pass
    
    def close_all_connections(self):
        """关闭所有连接"""
        try:
            self.pool.disconnect()
            self.logger.info("Redis连接池已关闭")
        except Exception as e:
            self.logger.error(f"关闭Redis连接池时出错: {e}")
    
    def get_pool_stats(self) -> Dict[str, Any]:
        """获取连接池统计信息"""
        try:
            return {
                "max_connections": self.max_connections,
                "created_connections": self.pool._created_connections,
                "available_connections": len(self.pool._available_connections),
                "in_use_connections": len(self.pool._in_use_connections)
            }
        except Exception as e:
            self.logger.error(f"获取Redis连接池统计失败: {e}")
            return {"error": str(e)}
    
    def health_check(self) -> bool:
        """连接池健康检查"""
        try:
            conn = self.get_connection()
            conn.ping()
            return True
        except Exception as e:
            self.logger.error(f"Redis连接池健康检查失败: {e}")
            return False