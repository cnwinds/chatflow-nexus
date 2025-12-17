"""
AI Toys 后台管理系统主应用

集成所有后台管理功能，提供完整的Web应用
"""

from quart import Quart, render_template, request, jsonify, session, g
from quart_cors import cors
import os
import sys
import logging
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.admin.api import admin_bp, init_services
from src.common.database.manager import DatabaseManager, initialize_db
from src.common.logging.manager import LoggingManager
from src.common.config.manager import ConfigManager
from src.common.config import initialize_config
from src.common.logging import initialize_logging

# 创建Quart应用
app = Quart(__name__)
app.secret_key = 'ai-toys-admin-secret-key-2024'

# 启用CORS
cors(app)

# 注册蓝图
app.register_blueprint(admin_bp)

# 配置模板目录
app.template_folder = os.path.join(os.path.dirname(__file__), 'templates')
app.static_folder = os.path.join(os.path.dirname(__file__), 'static')

# 应用级变量（在应用生命周期内有效）
app.config_manager = None
app.logging_manager = None
app.db_manager = None


@app.route('/')
async def index():
    """首页重定向到后台管理"""
    return await render_template('admin/index.html')


@app.route('/health')
async def health_check():
    """健康检查接口"""
    try:
        # 检查数据库连接
        db_manager = app.db_manager
        if db_manager is None:
            db_status = "unhealthy: database manager not initialized"
        else:
            health = await db_manager.health_check()
            db_status = health.get('status', 'unknown')
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    return jsonify({
        'status': 'ok',
        'database': db_status,
        'version': '1.0.0'
    })


@app.errorhandler(404)
async def not_found(error):
    """404错误处理"""
    return await render_template('admin/404.html'), 404


@app.errorhandler(500)
async def internal_error(error):
    """500错误处理"""
    return await render_template('admin/500.html'), 500


@app.before_serving
async def startup():
    """应用启动时的初始化 - Quart生命周期钩子"""
    try:
        # 设置运行时根目录
        runtime_root = Path(__file__).parent.parent.parent / "docker" / "runtime"
        service_src_root = Path(__file__).parent.parent / "services"
        
        # 初始化配置管理器
        config_manager = initialize_config(
            runtime_root=runtime_root, 
            service_src_root=service_src_root, 
            env_prefix='AI_TOYS'
        )
        app.config_manager = config_manager
        
        # 合并admin特定的日志配置
        _merge_admin_logging_config(config_manager)
        
        # 初始化日志管理器
        logging_manager = initialize_logging(config_manager)
        app.logging_manager = logging_manager
        logger = logging_manager.get_logger("admin")
        
        # 初始化数据库管理器（在应用事件循环中）
        db_manager = await initialize_db(config_manager, logging_manager)
        app.db_manager = db_manager
        
        # 初始化服务
        init_services(db_manager)
        
        logger.info("所有服务初始化完成")
        
    except Exception as e:
        logger = logging.getLogger("admin")
        logger.error(f"服务初始化失败: {e}", exc_info=True)
        raise


@app.after_serving
async def shutdown():
    """应用关闭时的清理 - Quart生命周期钩子"""
    try:
        if app.db_manager:
            await app.db_manager.close()
            logger = app.logging_manager.get_logger("admin") if app.logging_manager else logging.getLogger("admin")
            logger.info("数据库连接已关闭")
    except Exception as e:
        logger = app.logging_manager.get_logger("admin") if app.logging_manager else logging.getLogger("admin")
        logger.error(f"关闭数据库连接时出错: {e}", exc_info=True)


def _merge_admin_logging_config(config_manager):
    """合并admin特定的日志配置到全局日志配置中"""
    try:
        # 获取基础日志配置
        logging_config = config_manager.get_config("logging")
        
        # 获取admin配置中的日志设置
        admin_config = config_manager.get_config("admin")
        if admin_config and "logging" in admin_config:
            # 合并配置，admin的配置优先级更高
            admin_logging = admin_config["logging"]
            merged_config = {**logging_config, **admin_logging}
            
            # 将合并后的配置设置回config_manager
            config_manager.set_config("logging", merged_config)
            
    except Exception as e:
        # 如果合并失败，忽略错误，使用默认配置
        print(f"警告：合并admin日志配置失败: {e}")


def create_app():
    """创建应用实例 - 工厂函数模式"""
    return app


if __name__ == '__main__':
    # 开发环境运行
    app.run(
        host='0.0.0.0',
        port=8100,
        debug=True
    )
