#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Agent Server配置模块"""

from pathlib import Path
from src.common.config import get_config_manager

_config_manager = None

def get_config():
    """获取配置管理器实例"""
    global _config_manager
    if _config_manager is None:
        runtime_root = Path(__file__).parent.parent.parent.parent / "docker" / "runtime"
        from src.common.config import initialize_config
        _config_manager = initialize_config(runtime_root=runtime_root, env_prefix='AI_TOYS')
    return _config_manager

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

