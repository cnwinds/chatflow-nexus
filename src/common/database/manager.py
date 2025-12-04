"""
数据库管理器主类 - 异步版本
"""

from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional, AsyncContextManager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import Pool

from .exceptions import DatabaseError, DatabaseConnectionError, DatabaseQueryError, DatabaseTransactionError
from ..exceptions import ConfigurationError

# 全局数据库管理器实例
_db_manager = None


class DatabaseManager:
    """统一数据库管理器 - 异步版本"""
    
    def __init__(self, config_manager, logging_manager):
        """初始化数据库管理器"""
        self.config_manager = config_manager
        self.logging_manager = logging_manager
        
        # 获取日志记录器
        self.logger = self.logging_manager.get_logger("database")
        
        # 加载配置
        self._load_config()
        
        # 初始化连接池（在 __init__ 中创建引擎和会话工厂）
        self._init_connection_pool()

    def _load_config(self):
        """加载数据库配置"""
        try:
            # 尝试从配置文件加载
            self.config = self.config_manager.get_config("database")
            if not self.config:
                # 如果配置文件为空，抛出异常
                raise ConfigurationError("数据库配置文件为空，请提供有效的数据库配置")
        except Exception as e:
            # 如果配置文件不存在或加载失败，抛出异常
            raise ConfigurationError(f"数据库配置加载失败: {e}")
    
    def _build_connection_url(self) -> str:
        """构建数据库连接URL"""
        host = self.config.get("host", "localhost")
        port = self.config.get("port", 3306)
        database = self.config.get("database", "")
        username = self.config.get("username", "")
        password = self.config.get("password", "")
        charset = self.config.get("charset", "utf8mb4")
        
        # 构建 MySQL 异步连接URL
        # 注意：aiomysql 需要正确的 URL 编码，特别是密码中的特殊字符
        from urllib.parse import quote_plus
        password_encoded = quote_plus(password) if password else ""
        return f"mysql+aiomysql://{username}:{password_encoded}@{host}:{port}/{database}?charset={charset}"
    
    def _init_connection_pool(self):
        """初始化连接池"""
        try:
            connection_url = self._build_connection_url()
            
            # 获取连接池配置
            pool_size = self.config.get("pool_size") or self.config.get("max_pool_size", 20)
            max_overflow = self.config.get("max_overflow", 10)
            pool_timeout = self.config.get("pool_timeout", 30)
            pool_recycle = self.config.get("pool_recycle", 3600)
            # 在 Windows 上，pool_pre_ping 可能导致事件循环问题，强制设为 False
            # 即使配置中指定了 True，在 Windows 上也应该禁用
            pool_pre_ping_config = self.config.get("pool_pre_ping")
            if pool_pre_ping_config is None:
                pool_pre_ping = False
            else:
                # 允许配置覆盖，但不建议在 Windows 上启用
                pool_pre_ping = bool(pool_pre_ping_config)
            charset = self.config.get("charset", "utf8mb4")
            
            # 创建异步引擎
            # 添加 connect_args 确保 aiomysql 正确工作
            # 使用 NullPool 或配置连接池以兼容 Windows 事件循环
            self.engine = create_async_engine(
                connection_url,
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_timeout=pool_timeout,
                pool_recycle=pool_recycle,
                pool_pre_ping=pool_pre_ping,
                echo=False,  # 生产环境建议设为 False
                connect_args={
                    "charset": charset,
                    "connect_timeout": 10,
                },
                # 禁用 pool_reset_on_return 以避免事件循环问题
                pool_reset_on_return=None,
            )
            
            # 创建异步会话工厂
            # 设置 expire_on_commit=False 避免自动过期
            # 在 Windows 上，可能需要额外的配置来确保事件循环兼容性
            self.async_session = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
                autocommit=False
            )
            
            self.logger.info(f"数据库连接池初始化成功 池大小：{pool_size}")
            
        except Exception as e:
            error_msg = f"数据库连接池初始化失败: {e}"
            self.logger.error(error_msg)
            raise DatabaseConnectionError(error_msg)
    
    async def initialize(self):
        """异步初始化数据库管理器"""
        try:
            # 验证连接
            health = await self.health_check()
            if health["status"] != "healthy":
                raise DatabaseConnectionError("数据库连接池健康检查失败")
            self.logger.debug("数据库管理器初始化完成")
        except Exception as e:
            error_msg = f"数据库管理器初始化失败: {e}"
            self.logger.error(error_msg)
            raise DatabaseConnectionError(error_msg)
    
    async def close(self):
        """异步关闭数据库管理器"""
        try:
            if self.engine:
                await self.engine.dispose()
            self.logger.info("数据库管理器已关闭")
        except Exception as e:
            self.logger.error(f"关闭数据库管理器时出错: {e}")
    
    async def get_connection(self) -> AsyncSession:
        """获取数据库连接（会话）
        
        Returns:
            AsyncSession: 异步数据库会话
            
        Note:
            使用完毕后需要调用 session.close() 或使用 async with 语句
        """
        try:
            return self.async_session()
        except Exception as e:
            error_msg = f"获取数据库连接失败: {e}"
            self.logger.error(error_msg)
            raise DatabaseConnectionError(error_msg)
    
    async def execute_query(self, sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """执行查询操作
        
        Args:
            sql: SQL查询语句
            params: 查询参数
            
        Returns:
            List[Dict[str, Any]]: 查询结果列表
        """
        try:
            # 记录查询日志
            if self.config.get('logging', {}).get('log_queries', False):
                self.logger.debug(f"执行查询: {sql}, 参数: {params}")
            
            import time
            start_time = time.time()
            
            async with self.async_session() as session:
                result = await session.execute(text(sql), params or {})
                rows = result.fetchall()
                
                # 转换为字典列表
                if rows:
                    # 获取列名
                    columns = list(result.keys())
                    # 将 Row 对象转换为字典
                    result_list = [dict(zip(columns, row)) for row in rows]
                else:
                    result_list = []
            
            # 记录慢查询
            execution_time = time.time() - start_time
            slow_threshold = self.config.get('logging', {}).get('slow_query_threshold', 1.0)
            if (self.config.get('logging', {}).get('log_slow_queries', True) and 
                execution_time > slow_threshold):
                self.logger.warning(f"慢查询检测: {sql} (耗时: {execution_time:.2f}秒)")
            
            return result_list
            
        except Exception as e:
            error_msg = f"查询执行失败: {sql}, 错误: {e}"
            self.logger.error(error_msg)
            raise DatabaseQueryError(error_msg)
    
    async def execute_update(self, sql: str, params: Optional[Dict[str, Any]] = None) -> int:
        """执行更新操作
        
        Args:
            sql: SQL更新语句
            params: 更新参数
            
        Returns:
            int: 受影响的行数
        """
        try:
            # 记录查询日志
            if self.config.get('logging', {}).get('log_queries', False):
                self.logger.debug(f"执行更新: {sql}, 参数: {params}")
            
            import time
            start_time = time.time()
            
            async with self.async_session() as session:
                result = await session.execute(text(sql), params or {})
                await session.commit()
                affected_rows = result.rowcount
            
            # 记录慢查询
            execution_time = time.time() - start_time
            slow_threshold = self.config.get('logging', {}).get('slow_query_threshold', 1.0)
            if (self.config.get('logging', {}).get('log_slow_queries', True) and 
                execution_time > slow_threshold):
                self.logger.warning(f"慢更新检测: {sql} {params} (耗时: {execution_time:.2f}秒)")
            
            return affected_rows
            
        except Exception as e:
            error_msg = f"更新执行失败: {sql}, 错误: {e}"
            self.logger.error(error_msg)
            raise DatabaseQueryError(error_msg)
    
    async def execute_insert(self, sql: str, params: Optional[Dict[str, Any]] = None) -> int:
        """执行插入操作并返回插入的ID
        
        Args:
            sql: SQL插入语句
            params: 插入参数
            
        Returns:
            int: 插入记录的ID
        """
        try:
            # 记录查询日志
            if self.config.get('logging', {}).get('log_queries', False):
                self.logger.debug(f"执行插入: {sql}, 参数: {params}")
            
            import time
            start_time = time.time()
            
            async with self.async_session() as session:
                result = await session.execute(text(sql), params or {})
                await session.commit()
                inserted_id = result.lastrowid
            
            # 记录慢查询
            execution_time = time.time() - start_time
            slow_threshold = self.config.get('logging', {}).get('slow_query_threshold', 1.0)
            if (self.config.get('logging', {}).get('log_slow_queries', True) and 
                execution_time > slow_threshold):
                self.logger.warning(f"慢插入检测: {sql} (耗时: {execution_time:.2f}秒)")
            
            return inserted_id
            
        except Exception as e:
            error_msg = f"插入执行失败: {sql}, 错误: {e}"
            self.logger.error(error_msg)
            raise DatabaseQueryError(error_msg)
    
    async def execute_many(self, sql: str, params_list: List[Dict[str, Any]]) -> int:
        """执行批量操作
        
        Args:
            sql: SQL语句
            params_list: 参数列表
            
        Returns:
            int: 受影响的总行数
        """
        try:
            # 记录查询日志
            if self.config.get('logging', {}).get('log_queries', False):
                self.logger.debug(f"执行批量操作: {sql}, 参数数量: {len(params_list)}")
            
            if not params_list:
                return 0
            
            import time
            start_time = time.time()
            
            async with self.async_session() as session:
                # 批量执行操作
                total_affected = 0
                stmt = text(sql)
                
                # 对于所有类型的语句，都使用批量执行方式
                for params in params_list:
                    result = await session.execute(stmt, params)
                    total_affected += result.rowcount
                
                await session.commit()
            
            # 记录慢查询
            execution_time = time.time() - start_time
            slow_threshold = self.config.get('logging', {}).get('slow_query_threshold', 1.0)
            if (self.config.get('logging', {}).get('log_slow_queries', True) and 
                execution_time > slow_threshold):
                self.logger.warning(f"慢批量操作检测: {sql} (耗时: {execution_time:.2f}秒)")
            
            return total_affected
            
        except Exception as e:
            error_msg = f"批量操作执行失败: {sql}, 错误: {e}"
            self.logger.error(error_msg)
            raise DatabaseQueryError(error_msg)
    
    @asynccontextmanager
    async def transaction(self) -> AsyncContextManager[AsyncSession]:
        """数据库事务上下文管理器
        
        Usage:
            async with db_manager.transaction() as session:
                # 执行数据库操作
                await session.execute(text("UPDATE ..."))
                # 事务会自动提交，如果出现异常会自动回滚
        """
        session = self.async_session()
        try:
            self.logger.debug("事务开始")
            yield session
            await session.commit()
            self.logger.debug("事务提交成功")
        except Exception as e:
            await session.rollback()
            self.logger.warning(f"事务回滚: {e}")
            raise DatabaseTransactionError(f"事务执行失败: {e}")
        finally:
            await session.close()
    
    async def health_check(self) -> Dict[str, Any]:
        """数据库健康检查
        
        Returns:
            Dict[str, Any]: 健康检查结果，包含 status 字段
        """
        try:
            async with self.async_session() as session:
                # 执行简单的查询来检查连接
                result = await session.execute(text("SELECT 1"))
                result.fetchone()
            
            return {
                "status": "healthy",
                "message": "数据库连接正常"
            }
        except Exception as e:
            error_msg = f"健康检查失败: {e}"
            self.logger.error(error_msg)
            return {
                "status": "unhealthy",
                "error": error_msg
            }
    
    def get_pool_stats(self) -> Dict[str, Any]:
        """获取连接池统计信息
        
        Returns:
            Dict[str, Any]: 连接池统计信息
        """
        try:
            pool: Pool = self.engine.pool
            
            stats = {
                "pool_size": pool.size(),
                "checked_in": pool.checkedin(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
            }
            
            # invalid() 方法在某些连接池类型中可能不存在
            try:
                stats["invalid"] = pool.invalid()
            except AttributeError:
                # AsyncAdaptedQueuePool 没有 invalid 方法，跳过
                pass
            
            return stats
        except Exception as e:
            self.logger.error(f"获取连接池统计失败: {e}")
            return {"error": str(e)}
    
    # 以下方法保持向后兼容，但内部调用异步方法
    async def execute_one(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """执行查询并获取单条记录
        
        Args:
            sql: SQL语句
            params: 参数
            
        Returns:
            Optional[Dict[str, Any]]: 单条记录，不存在返回None
        """
        try:
            result = await self.execute_query(sql, params)
            return result[0] if result else None
        except Exception as e:
            error_msg = f"获取单条记录失败: {sql}, 错误: {e}"
            self.logger.error(error_msg)
            raise DatabaseQueryError(error_msg)
    
    async def execute_count(self, sql: str, params: Optional[Dict[str, Any]] = None) -> int:
        """执行查询并获取记录数量
        
        Args:
            sql: SQL语句
            params: 参数
            
        Returns:
            int: 记录数量
        """
        try:
            result = await self.execute_query(sql, params)
            if result and len(result) > 0:
                # 获取第一个字段的值作为数量
                first_key = list(result[0].keys())[0]
                return result[0][first_key]
            return 0
        except Exception as e:
            error_msg = f"获取记录数量失败: {sql}, 错误: {e}"
            self.logger.error(error_msg)
            raise DatabaseQueryError(error_msg)
    
    async def execute_exists(self, sql: str, params: Optional[Dict[str, Any]] = None) -> bool:
        """执行查询并检查记录是否存在
        
        Args:
            sql: SQL语句
            params: 参数
            
        Returns:
            bool: 是否存在
        """
        try:
            result = await self.execute_query(sql, params)
            return len(result) > 0
        except Exception as e:
            error_msg = f"检查记录存在失败: {sql}, 错误: {e}"
            self.logger.error(error_msg)
            raise DatabaseQueryError(error_msg)

    def get_engine(self) -> AsyncEngine:
        """获取数据库引擎

        Returns:
            AsyncEngine: 异步数据库引擎
        """
        return self.engine

# 全局便捷访问函数
def get_db_manager() -> DatabaseManager:
    """获取数据库管理器实例
    
    Returns:
        DatabaseManager: 数据库管理器实例
        
    Raises:
        RuntimeError: 数据库管理器未初始化
    """
    global _db_manager
    if _db_manager is None:
        raise RuntimeError("数据库管理器未初始化")
    return _db_manager


async def initialize_db(config_manager, logging_manager) -> DatabaseManager:
    """初始化数据库管理器
    
    Args:
        config_manager: 配置管理器
        logging_manager: 日志管理器
        
    Returns:
        DatabaseManager: 初始化后的数据库管理器实例
    """
    global _db_manager
    
    # 创建数据库管理器
    db_manager = DatabaseManager(config_manager, logging_manager)
    
    # 初始化数据库管理器
    await db_manager.initialize()
    
    # 设置全局实例
    _db_manager = db_manager
    
    return db_manager


def is_db_ready() -> bool:
    """检查数据库管理器是否已初始化
    
    Returns:
        bool: 是否已初始化
    """
    global _db_manager
    return _db_manager is not None
