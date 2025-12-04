#!/usr/bin/env python3
"""
UTCP 使用示例

展示如何使用UTCP框架和新的核心组件。
"""

from .utcp import UTCPManager, UTCPServiceConfig, ServiceType
from ..common.config import get_config_manager, initialize_config, initialize_logging

def example_basic_usage():
    """基本使用示例"""
    # 创建配置管理器
    config_manager = initialize_config(env_prefix="EXAMPLE")
    logging_manager =initialize_logging(config_manager)
    logger = logging_manager.get_logger("example_usage")
    logger.info("UTCP基本使用示例")
    
    # 创建UTCP管理器
    utcp_manager = UTCPManager(config_manager)
    
    logger.info(f"项目根目录: {config_manager.project_root}")
    logger.info(f"配置目录: {config_manager.config_dir}")
    logger.info(f"数据目录: {config_manager.data_dir}")
    logger.info(f"日志目录: {config_manager.logs_dir}")
    
    # 演示环境变量管理
    config_manager.set_env_var("EXAMPLE_DEBUG", "true")
    config_manager.set_env_var("EXAMPLE_TIMEOUT", "30")
    logger.info(f"环境变量 EXAMPLE_DEBUG: {config_manager.get_env_var('EXAMPLE_DEBUG')}")
    logger.info(f"环境变量 EXAMPLE_TIMEOUT: {config_manager.get_env_var('EXAMPLE_TIMEOUT')}")


def example_service_registration():
    """服务注册示例"""
    # 创建UTCP管理器
    utcp_manager = UTCPManager()
    
    # 注册进程内服务
    inprocess_config = UTCPServiceConfig(
        name="calculator",
        type=ServiceType.INPROCESS,
        module_path="services.calculator.service",
        class_name="CalculatorService",
        tags=["math", "utility"]
    )
    utcp_manager.register_service(inprocess_config)
    
    # 注册HTTP服务
    http_config = UTCPServiceConfig(
        name="weather",
        type=ServiceType.HTTP,
        base_url="http://localhost:8001",
        tags=["external", "api"]
    )
    utcp_manager.register_service(http_config)
    
    print("服务注册示例完成")


def example_config_loading():
    """配置加载示例"""
    config_manager = get_config_manager()
    
    # 加载全局配置
    global_config = config_manager.get_config("global")
    print(f"全局配置: {global_config}")
    
    # 加载服务配置
    services_config = config_manager.get_config("services")
    print(f"服务配置: {services_config}")
    
    # 加载特定服务的配置
    try:
        calculator_config = config_manager.get_service_config("calculator")
        print(f"计算器服务配置: {calculator_config}")
    except Exception as e:
        print(f"加载计算器服务配置失败: {e}")


if __name__ == '__main__':
    example_basic_usage()
    example_service_registration()
    example_config_loading()