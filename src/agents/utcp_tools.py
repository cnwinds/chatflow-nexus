#!/usr/bin/env python3
"""
全局UTCP管理器

提供全局的UTCP管理器实例，避免每个ChatClient都创建独立的UTCPManager。
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, List
from src.utcp.utcp import UTCPManager
from src.common.config import get_config_manager

# 全局UTCP管理器实例
_global_utcp_manager: Optional[UTCPManager] = None
_initialization_lock = asyncio.Lock()
_initialization_complete = False

logger = logging.getLogger(__name__)


async def get_global_utcp_manager() -> UTCPManager:
    """
    获取全局UTCP管理器实例
    
    Returns:
        UTCPManager: 全局UTCP管理器实例
        
    Raises:
        RuntimeError: 当UTCP管理器未初始化时
    """
    global _global_utcp_manager, _initialization_complete
    
    if _global_utcp_manager is None:
        async with _initialization_lock:
            if _global_utcp_manager is None:
                await _initialize_global_utcp_manager()
    
    if _global_utcp_manager is None:
        raise RuntimeError("全局UTCP管理器初始化失败")
    
    return _global_utcp_manager


async def _initialize_global_utcp_manager():
    """初始化全局UTCP管理器"""
    global _global_utcp_manager, _initialization_complete
    
    # 记录开始时间
    start_time = time.time()
    
    try:
        logger.info("开始初始化全局UTCP管理器")
        
        # 获取配置管理器
        config_manager = get_config_manager()
        
        # 创建UTCP管理器
        _global_utcp_manager = UTCPManager(config_manager)
        
        # 加载服务配置
        services_config = config_manager.get_config("services")
        if services_config:
            logger.info(f"从配置加载 {len(services_config)} 个服务")
            _global_utcp_manager.load_services_from_config_dict(services_config)
            
            # 启动远程服务
            remote_services_count = await _global_utcp_manager.start_remote_services()
            if remote_services_count > 0:
                logger.info(f"启动了 {remote_services_count} 个远程服务")
        else:
            logger.warning("未找到服务配置，跳过UTCP服务初始化")
        
        # 等待所有服务真正创建完成
        service_info = await _global_utcp_manager.get_service_info()
        total_services = len(service_info)
        
        # 计算并记录初始化时间
        end_time = time.time()
        initialization_time = end_time - start_time
        
        _initialization_complete = True
        
        logger.info(f"全局UTCP管理器初始化完成，总耗时: {initialization_time:.3f}秒，总服务数: {total_services}")
        
    except Exception as e:
        logger.error(f"初始化全局UTCP管理器失败: {e}")
        _global_utcp_manager = None
        raise


async def get_utcp_tools(tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    获取UTCP工具列表
    
    Args:
        tags: 标签过滤列表
        
    Returns:
        工具定义列表
    """
    utcp_manager = await get_global_utcp_manager()
    return await utcp_manager.get_all_tools(tags=tags)


async def call_utcp_tool(tool_ref: str, arguments: Dict[str, Any]) -> Any:
    """
    调用UTCP工具
    
    Args:
        tool_ref: 工具引用
        arguments: 工具参数
        
    Returns:
        工具执行结果
    """
    utcp_manager = await get_global_utcp_manager()
    return await utcp_manager.call_tool(tool_ref, arguments)


async def call_utcp_tool_stream(tool_ref: str, arguments: Dict[str, Any]):
    """
    调用UTCP流式工具
    
    Args:
        tool_ref: 工具引用
        arguments: 工具参数
        
    Returns:
        流式响应对象
    """
    utcp_manager = await get_global_utcp_manager()
    return await utcp_manager.call_tool_stream(tool_ref, arguments)


async def get_utcp_service_info() -> Dict[str, Dict[str, Any]]:
    """
    获取UTCP服务信息
    
    Returns:
        服务信息字典
    """
    utcp_manager = await get_global_utcp_manager()
    return await utcp_manager.get_service_info()


def is_utcp_initialized() -> bool:
    """
    检查UTCP是否已初始化
    
    Returns:
        是否已初始化
    """
    return _initialization_complete and _global_utcp_manager is not None


async def shutdown_global_utcp():
    """关闭全局UTCP管理器"""
    global _global_utcp_manager
    
    if _global_utcp_manager:
        try:
            await _global_utcp_manager.shutdown_remote_services()
            logger.info("全局UTCP管理器已关闭")
        except Exception as e:
            logger.error(f"关闭全局UTCP管理器时出错: {e}")
        finally:
            _global_utcp_manager = None
