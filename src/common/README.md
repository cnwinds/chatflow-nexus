# AI玩具后端公用组件使用指南

## 概述

本目录包含AI玩具后端系统的核心公用组件，提供统一的配置管理、日志管理、数据库管理、Redis管理和工具功能。这些组件遵循统一的设计模式，确保系统的一致性和可维护性。

## 组件架构

```
src/common/
├── config/          # 配置管理
├── logging/         # 日志管理
├── database/        # 数据库管理
├── redis/           # Redis管理
├── utils/           # 工具函数
└── exceptions.py    # 异常定义
```

## 核心组件

### 1. 配置管理器 (ConfigManager)

#### 功能特性
- 统一配置文件管理
- 环境变量覆盖支持
- 配置验证和缓存
- 多级配置合并
- 服务配置管理

#### 基本使用

```python
#!/usr/bin/env python3
"""
服务启动模板 - 集成最佳实践
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.common.config import initialize_config
from src.common.logging import initialize_logging
from src.common.database import initialize_db
from src.common.redis import initialize_redis

async def init_env():
    """设置运行环境 - 最佳实践初始化流程"""
    runtime_root = Path(__file__).parent.parent.parent / "docker" / "runtime"
    service_src_root = Path(__file__).parent.parent / "services" # 可选，如果没有services可以不写
    
    # 1. 初始化配置管理器
    config_manager = initialize_config(
        runtime_root=runtime_root,
        service_src_root=service_src_root,  # 可选，如果没有services可以不写
        env_prefix='AI_AGENTS'
    )
    
    # 2. 初始化日志管理器（读取logging.json）
    logging_manager = initialize_logging(config_manager)
    logger = logging_manager.get_logger("my_service")
    
    # 3. 初始化数据库管理器（读取database.json）
    await initialize_db(config_manager, logging_manager)
    
    # 4. 初始化Redis管理器（读取redis.json）
    await initialize_redis(config_manager, logging_manager)
    
    # 读取自定义配置文件示例
    # aitoys_config = config_manager.get_config('ai-toys')
    # port = aitoys_config.get("chat.port", 8000)

    logger.info("环境初始化完成")
    return config_manager, logging_manager

async def main():
    """主函数 - 标准启动模式"""
    try:
        # 初始化环境
        config_manager, logging_manager = await init_env()
        logger = logging_manager.get_logger("my_service")
        
        # 启动服务逻辑
        logger.info("服务启动成功")
        
    except Exception as e:
        print(f"服务启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
```

#### 配置文件结构

```
docker/runtime/config/
├── database.json      # 数据库配置
├── redis.json         # Redis配置  
└── logging.json       # 日志配置
```

#### 配置文件示例

**database.json** (数据库配置)
```json
{
  "host": "localhost",
  "port": 3306,
  "database": "aitoys",
  "username": "root",
  "password": "${DB_PASSWORD}",
  "charset": "utf8mb4",
  "pool_size": 10,
  "max_overflow": 20,
  "pool_timeout": 30,
  "pool_recycle": 3600,
  "logging": {
    "log_queries": false,
    "log_slow_queries": true,
    "slow_query_threshold": 1.0
  }
}
```

**redis.json** (Redis配置)
```json
{
  "host": "localhost",
  "port": 6379,
  "database": 0,
  "password": "${REDIS_PASSWORD}",
  "key_prefix": "aitoys:",
  "default_serializer": "json",
  "connection_pool": {
    "max_connections": 20,
    "retry_on_timeout": true,
    "socket_timeout": 5,
    "socket_connect_timeout": 5
  },
  "logging": {
    "log_operations": false,
    "log_slow_operations": true,
    "slow_operation_threshold": 0.1
  }
}
```

**logging.json** (日志配置)
```json
{
  "level": "INFO",
  "console_enabled": true,
  "console_colors": true,
  "console_format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
  "file_enabled": true,
  "file_path": "app.log",
  "file_level": "INFO",
  "max_file_size": 10485760,
  "backup_count": 5,
  "json_file_enabled": true,
  "json_file_path": "app.json",
  "sensitive_data_filter": true,
  "sensitive_fields": ["password", "token", "secret", "api_key"],
  "performance_filter": true,
  "max_messages_per_minute": 100,
  "duplicate_filter": true,
  "max_duplicates": 3,
  "duplicate_time_window": 60
}
```

### 1. 日志管理器 (LoggingManager)

#### 功能特性
- 多处理器支持（控制台、文件、JSON）
- 彩色日志输出
- 日志轮转和压缩
- 敏感数据过滤
- 性能监控
- 结构化日志

#### 基本使用

```python
from src.common.logging import initialize_logging, get_logging_manager

# 初始化日志管理器（自动读取logging.json配置）
logging_manager = initialize_logging(config_manager)

# 获取日志记录器
logger = logging_manager.get_logger("my_service")

# 使用日志 - 最佳实践
logger.info("服务启动成功")
logger.error("数据库连接失败", extra={"error_code": "DB001"})

# 结构化日志 - 推荐用法
logger.info("用户登录成功", extra={
    "user_id": user_id,
    "device_id": device_id,
    "login_time": datetime.now().isoformat()
})

# 错误日志包含上下文
logger.error("数据库操作失败", extra={
    "operation": "user_login",
    "user_id": user_id,
    "error_code": "DB001",
    "error_message": str(e)
})
```

### 2. 数据库管理器 (DatabaseManager)

#### 功能特性
- 连接池管理
- 事务支持
- 查询日志记录
- 慢查询监控
- 健康检查
- 批量操作

#### 基本使用

```python
from src.common.database import initialize_db, get_db_manager

# 初始化数据库管理器（自动读取database.json配置）
db_manager = await initialize_db(config_manager, logging_manager)

# 执行查询 - 最佳实践：使用参数化查询
results = db_manager.execute_query(
    "SELECT * FROM users WHERE status = :status",
    {"status": 1}
)

# 执行更新
affected_rows = db_manager.execute_update(
    "UPDATE users SET last_login = NOW() WHERE id = :id",
    {"id": user_id}
)

# 事务操作 - 确保数据一致性
try:
    with db_manager.transaction() as conn:
        # 插入用户
        user_id = db_manager.execute_insert(
            "INSERT INTO users (name, email) VALUES (:name, :email)",
            {"name": "张三", "email": "zhangsan@example.com"}
        )
        
        # 插入用户配置
        db_manager.execute_update(
            "INSERT INTO user_configs (user_id, config_key, config_value) VALUES (:user_id, :key, :value)",
            {"user_id": user_id, "key": "theme", "value": "dark"}
        )
        # 如果任何操作失败，整个事务会回滚
except Exception as e:
    logger.error(f"用户创建失败: {e}")

# 批量操作 - 提高性能
params_list = [
    {"name": "user1", "email": "user1@example.com"},
    {"name": "user2", "email": "user2@example.com"}
]
affected_rows = db_manager.execute_many(
    "INSERT INTO users (name, email) VALUES (:name, :email)",
    params_list
)
```

#### 高级功能

```python
# 批量操作
params_list = [
    {"name": "user1", "email": "user1@example.com"},
    {"name": "user2", "email": "user2@example.com"}
]
affected_rows = db_manager.execute_many(
    "INSERT INTO users (name, email) VALUES (:name, :email)",
    params_list
)

# 健康检查
health = db_manager.health_check()
print(f"数据库状态: {health['status']}")

# 连接统计
stats = db_manager.get_connection_stats()
print(f"活跃连接数: {stats['active_connections']}")
```

### 3. Redis管理器 (RedisManager)

#### 功能特性
- 连接池管理
- 自动序列化/反序列化
- 键前缀管理
- 批量操作
- 数据结构支持
- 事务支持

#### 基本使用

```python
from src.common.redis import initialize_redis, get_redis_manager

# 初始化Redis管理器（自动读取redis.json配置）
redis_manager = await initialize_redis(config_manager, logging_manager)

# 基本操作 - 最佳实践：使用有意义的键命名
user_key = f"user:{user_id}"
session_key = f"session:{session_id}"
cache_key = f"cache:user:{user_id}:profile"

# 设置合理的过期时间
redis_manager.set(user_key, {"name": "张三", "age": 25}, expire=3600)  # 1小时
redis_manager.set(session_key, session_data, expire=86400)  # 24小时
user_data = redis_manager.get(user_key, {})

# 批量操作 - 提高性能
user_ids = [1, 2, 3, 4, 5]
keys = [f"user:{user_id}" for user_id in user_ids]
user_data_list = redis_manager.mget(keys)

# 批量设置
user_mapping = {
    f"user:{user_id}": user_data for user_id, user_data in zip(user_ids, user_data_list)
}
redis_manager.mset(user_mapping, expire=3600)

# 哈希操作
redis_manager.hset("user:profile:123", {
    "name": "张三",
    "email": "zhangsan@example.com",
    "age": 25
})
profile = redis_manager.hgetall("user:profile:123")
```

#### 高级功能

```python
# 列表操作
redis_manager.lpush("task:queue", "task1", "task2", "task3")
task = redis_manager.rpop("task:queue")

# 集合操作
redis_manager.sadd("online_users", "user1", "user2", "user3")
online_users = redis_manager.smembers("online_users")

# 事务操作
def transaction_commands(pipe):
    pipe.set("counter", 0)
    pipe.incr("counter")
    pipe.expire("counter", 60)

results = redis_manager.multi_exec([transaction_commands])

# 健康检查
health = redis_manager.health_check()
print(f"Redis状态: {health['status']}")
```


## 故障排除

### 常见问题

1. **配置管理器未初始化**
   ```python
   # 错误：RuntimeError: 配置管理器未初始化
   # 解决：确保在main函数中调用initialize_config()
   ```

2. **数据库连接失败**
   ```python
   # 检查数据库配置和连接信息
   health = db_manager.health_check()
   print(health)
   ```

3. **Redis连接失败**
   ```python
   # 检查Redis配置和连接
   health = redis_manager.health_check()
   print(health)
   ```

4. **日志文件权限问题**
   ```bash
   # 确保日志目录有写权限
   chmod 755 docker/runtime/log
   ```

### 调试技巧

1. **启用调试日志**
   ```json
   {
     "level": "DEBUG",
     "console_enabled": true
   }
   ```

2. **查看组件状态**
   ```python
   # 检查各组件是否就绪
   from src.common.config import is_config_ready
   from src.common.database import is_db_ready
   from src.common.redis import is_redis_ready
   
   print(f"配置管理器: {is_config_ready()}")
   print(f"数据库管理器: {is_db_ready()}")
   print(f"Redis管理器: {is_redis_ready()}")
   ```

## 版本信息

- **版本**: 1.0.0
- **Python要求**: >= 3.8
- **依赖**: SQLAlchemy, Redis, aiohttp

## 贡献指南

1. 遵循现有的代码风格
2. 添加适当的错误处理
3. 更新相关文档
4. 编写单元测试
5. 确保向后兼容性

---