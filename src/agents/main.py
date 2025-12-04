#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Agent Server主程序"""

import sys
import asyncio
import logging
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import uvicorn
import traceback
from contextlib import asynccontextmanager

# 导入基础设施组件
from src.common.config import initialize_config
from src.common.database.manager import initialize_db
from src.common.redis.manager import initialize_redis
from src.common.logging.manager import initialize_logging
from src.common.logging.http_request_response_log import fastapi_log_request_response_middleware

# 导入API路由
from src.agents.api import auth, agents, sessions, chat
from src.agents.utcp_tools import get_global_utcp_manager

# 全局管理器实例
config_manager = None
logging_manager = None
db_manager = None
redis_manager = None
logger = None

# ==================== Asyncio异常处理 ====================

def _handle_asyncio_exception(loop, context):
    """处理asyncio异常，抑制无害的连接重置错误"""
    exception = context.get('exception')
    
    # 抑制Windows上常见的连接重置错误（客户端提前关闭连接）
    if isinstance(exception, ConnectionResetError):
        # 只在调试模式下记录
        if logger and logger.level <= logging.DEBUG:
            logger.debug(f"客户端连接重置: {context.get('message', '')}")
        return
    
    # 其他异常正常处理
    if logger:
        logger.error(f"Asyncio异常: {context.get('message', '')}")
        if exception:
            logger.error(f"异常类型: {type(exception).__name__}, 异常信息: {str(exception)}")
    else:
        print(f"Asyncio异常: {context.get('message', '')}")
        if exception:
            print(f"异常类型: {type(exception).__name__}, 异常信息: {str(exception)}")

# ==================== 配置函数 ====================

def get_config():
    """获取配置管理器实例"""
    global config_manager
    if config_manager is None:
        runtime_root = Path(__file__).parent.parent.parent / "docker" / "runtime"
        service_src_root = Path(__file__).parent.parent / "services"
        config_manager = initialize_config(runtime_root=runtime_root, service_src_root=service_src_root, env_prefix='AI_AGENTS')
    return config_manager

def get_server_config():
    """获取服务器配置"""
    config = get_config()
    return {
        "host": config.get_config("agents.server.host", "0.0.0.0"),
        "port": config.get_config("agents.server.port", 8020),
        "debug": config.get_config("agents.debug", False),
    }

def get_cors_config():
    """获取CORS配置"""
    config = get_config()
    return {
        "allow_origins": config.get_config("agents.cors.allow_origins", ["*"]),
        "allow_credentials": config.get_config("agents.cors.allow_credentials", True),
        "allow_methods": config.get_config("agents.cors.allow_methods", ["*"]),
        "allow_headers": config.get_config("agents.cors.allow_headers", ["*"]),
    }

def load_config():
    """只加载配置文件，不初始化连接"""
    global config_manager
    try:
        # 初始化配置管理器（使用get_config确保使用正确的env_prefix）
        config_manager = get_config()
        
        # 获取服务器配置
        server_config = get_server_config()
        host = server_config["host"]
        port = server_config["port"]
        debug = server_config["debug"]
        
        return host, port, debug
        
    except Exception as e:
        error_msg = f"配置文件加载失败: {str(e)}"
        print(f"❌ {error_msg}")
        print("程序启动失败，请检查配置文件")
        raise

async def initialize_managers():
    """初始化所有管理器"""
    global config_manager, logging_manager, db_manager, redis_manager, logger
    
    try:
        # 确保配置管理器已初始化
        if config_manager is None:
            config_manager = get_config()
        
        # 阶段1: 初始化日志管理器
        logging_manager = initialize_logging(config_manager)
        logger = logging_manager.get_logger("agents")
        
        # 设置asyncio异常处理器
        loop = asyncio.get_event_loop()
        loop.set_exception_handler(_handle_asyncio_exception)
        
        logger.info("Agent Server启动中...")
        
        # 阶段2: 初始化数据库管理器
        logger.info("正在初始化数据库连接...")
        db_manager = await initialize_db(config_manager, logging_manager)
        logger.info("数据库连接初始化成功")
        
        # 阶段3: 初始化Redis管理器
        logger.info("正在初始化Redis连接...")
        redis_manager = await initialize_redis(config_manager, logging_manager)
        logger.info("Redis连接初始化成功")
        
        # 初始化全局UTCP管理器
        logger.info("正在初始化UTCP连接...")
        await get_global_utcp_manager()
        logger.info("UTCP连接初始化成功")

        # 初始化并启动系统工作流管理器
        from src.agents.workflow_system import get_system_workflow_manager
        system_workflow = await get_system_workflow_manager()
        await system_workflow.start()
        
        logger.info("Agent Server启动完成")
        
        return config_manager, logging_manager, db_manager, redis_manager, logger
        
    except Exception as e:
        error_msg = f"服务启动失败: {str(e)}"
        if logger:
            logger.error(error_msg)
        else:
            print(error_msg)
        
        print(f"错误: {error_msg}")
        print("程序启动失败，请检查配置和网络连接")
        raise

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理器"""
    global config_manager, logging_manager, db_manager, redis_manager, logger
    
    system_workflow = None
    
    try:
        # 初始化所有管理器
        config_manager, logging_manager, db_manager, redis_manager, logger = await initialize_managers()
        
        # 保存系统工作流管理器引用，用于关闭
        from src.agents.workflow_system import get_system_workflow_manager
        system_workflow = await get_system_workflow_manager()
        
        yield
        
    except Exception as e:
        error_msg = f"服务启动失败: {str(e)}"
        if logger:
            logger.error(error_msg)
        else:
            print(error_msg)
        
        print(f"错误: {error_msg}")
        print("程序启动失败，请检查配置和网络连接")
        raise
    finally:
        if logger:
            logger.info("Agent Server关闭中...")
        
        # 优雅关闭所有组件，使用超时避免卡死
        shutdown_tasks = []
        
        # 1. 关闭系统工作流
        if system_workflow and system_workflow.is_running:
            async def stop_workflow():
                try:
                    await asyncio.wait_for(system_workflow.stop(), timeout=5.0)
                    if logger:
                        logger.info("系统工作流已关闭")
                except asyncio.TimeoutError:
                    if logger:
                        logger.warning("关闭系统工作流超时")
                except Exception as e:
                    if logger:
                        logger.error(f"关闭系统工作流时出错: {e}")
            shutdown_tasks.append(stop_workflow())
        
        # 2. 关闭UTCP管理器
        async def stop_utcp():
            try:
                from src.agents.utcp_tools import shutdown_global_utcp
                await asyncio.wait_for(shutdown_global_utcp(), timeout=10.0)
            except asyncio.TimeoutError:
                if logger:
                    logger.warning("关闭UTCP管理器超时")
            except Exception as e:
                if logger:
                    logger.error(f"关闭UTCP管理器时出错: {e}")
        shutdown_tasks.append(stop_utcp())
        
        # 3. 关闭Redis管理器
        if redis_manager:
            async def stop_redis():
                try:
                    await asyncio.wait_for(redis_manager.close(), timeout=5.0)
                except asyncio.TimeoutError:
                    if logger:
                        logger.warning("关闭Redis管理器超时")
                except Exception as e:
                    if logger:
                        logger.error(f"关闭Redis管理器时出错: {e}")
            shutdown_tasks.append(stop_redis())
        
        # 4. 关闭数据库管理器
        if db_manager:
            async def stop_db():
                try:
                    await asyncio.wait_for(db_manager.close(), timeout=5.0)
                except asyncio.TimeoutError:
                    if logger:
                        logger.warning("关闭数据库管理器超时")
                except Exception as e:
                    if logger:
                        logger.error(f"关闭数据库管理器时出错: {e}")
            shutdown_tasks.append(stop_db())
        
        # 并行执行所有关闭任务，但设置总体超时
        if shutdown_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*shutdown_tasks, return_exceptions=True),
                    timeout=15.0
                )
            except asyncio.TimeoutError:
                if logger:
                    logger.warning("部分组件关闭超时，强制退出")
        
        if logger:
            logger.info("服务关闭完成")

# 初始化FastAPI应用
app = FastAPI(
    title="OpenAI Compatible Chat API",
    description="基于OpenAI接口协议的对话服务",
    version="1.0.0",
    lifespan=lifespan,
    debug=False
)

# 配置跨域
cors_config = get_cors_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_config["allow_origins"],
    allow_credentials=cors_config["allow_credentials"],
    allow_methods=cors_config["allow_methods"],
    allow_headers=cors_config["allow_headers"],
)

# 使用请求和应答日志中间件
app.middleware("http")(fastapi_log_request_response_middleware)

# 添加异常处理器
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    error_detail = str(exc.errors())
    if logger:
        logger.warning(f"请求验证错误: {request.method} {request.url.path}\n{error_detail}")
    
    serializable_errors = []
    for error in exc.errors():
        serializable_error = {
            "type": error.get("type"),
            "loc": error.get("loc"),
            "msg": error.get("msg"),
            "input": error.get("input")
        }
        if "ctx" in error and "error" in error["ctx"]:
            ctx_error = error["ctx"]["error"]
            if isinstance(ctx_error, ValueError):
                serializable_error["ctx"] = {
                    "error": f"ValueError: {ctx_error.args[0] if ctx_error.args else str(ctx_error)}"
                }
            else:
                serializable_error["ctx"] = {
                    "error": str(ctx_error)
                }
        else:
            serializable_error["ctx"] = error.get("ctx", {})
        
        serializable_errors.append(serializable_error)
    
    return JSONResponse(
        status_code=422,
        content={"detail": serializable_errors, "body": exc.body}
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    if logger:
        logger.error(f"未处理异常: {request.method} {request.url.path}\n"
                     f"错误: {str(exc)}\n"
                     f"堆栈: {traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"}
    )

# 注册路由
app.include_router(auth.router, prefix="/auth", tags=["认证"])
app.include_router(agents.router, prefix="/agents", tags=["Agent管理"])
app.include_router(sessions.router, prefix="/sessions", tags=["会话管理"])
app.include_router(chat.router, prefix="/v1", tags=["OpenAI兼容API"])

# 健康检查路由
@app.get("/", tags=["健康检查"])
async def health_check():
    health_status = {
        "status": "ok",
        "service": "agents",
        "components": {}
    }
    
    if db_manager:
        try:
            db_health = await db_manager.health_check()
            health_status["components"]["database"] = "healthy" if db_health.get("status") == "healthy" else "unhealthy"
        except Exception as e:
            health_status["components"]["database"] = f"unhealthy: {str(e)}"
    
    if redis_manager:
        try:
            redis_health = redis_manager.health_check()
            health_status["components"]["redis"] = "healthy" if redis_health.get("status") == "healthy" else "unhealthy"
        except Exception as e:
            health_status["components"]["redis"] = f"unhealthy: {str(e)}"
    
    return health_status

# 主函数
if __name__ == "__main__":
    host, port, debug = load_config()
    
    # 配置uvicorn以支持优雅关闭
    uvicorn.run(
        "src.agents.main:app",
        host=host,
        port=port,
        reload=False,
        timeout_keep_alive=30,
        timeout_graceful_shutdown=15,  # 优雅关闭超时时间
    )

