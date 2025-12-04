#!/usr/bin/env python3
"""
配置常量定义
"""

# 配置文件名称常量
class ConfigFiles:
    """配置文件名称常量"""
    CHAT = "chat"
    OTA = "ota"
    HARDWARE = "hardware"
    DATABASE = "database"
    REDIS = "redis"
    LOGGING = "logging"
    SERVICES = "services"

# 配置路径常量
class ConfigPaths:
    """配置路径常量"""
    # 聊天服务器配置路径
    CHAT_AI_PROVIDERS = f"{ConfigFiles.CHAT}.ai_providers"
    CHAT_HARDWARE = f"{ConfigFiles.CHAT}.hardware"
    CHAT_PATHS = f"{ConfigFiles.CHAT}.paths"
    CHAT_LOGGING = f"{ConfigFiles.CHAT}.logging"
    
    # OTA服务器配置路径
    OTA_LOGGING = f"{ConfigFiles.OTA}.logging"
    
    # 硬件配置路径
    HARDWARE_MAX_SESSIONS = f"{ConfigFiles.CHAT}.hardware.max_sessions"
    HARDWARE_SESSION_TIMEOUT = f"{ConfigFiles.CHAT}.hardware.session_timeout"
    HARDWARE_CLEANUP_INTERVAL = f"{ConfigFiles.CHAT}.hardware.cleanup_interval"
    HARDWARE_AUDIO = f"{ConfigFiles.CHAT}.hardware.audio"
    HARDWARE_PATHS = f"{ConfigFiles.CHAT}.hardware.paths"
    
    # 通用配置路径
    DATABASE_CONFIG = f"{ConfigFiles.DATABASE}"
    REDIS_CONFIG = f"{ConfigFiles.REDIS}"
    LOGGING_CONFIG = f"{ConfigFiles.LOGGING}"
    SERVICES_CONFIG = f"{ConfigFiles.SERVICES}"

# 默认值常量
class DefaultValues:
    """默认值常量"""
    # 硬件配置默认值
    MAX_SESSIONS = 100
    SESSION_TIMEOUT = 3600  # 1小时
    CLEANUP_INTERVAL = 300  # 5分钟
    AUDIO_FILES_DIR = "audio_files"
    
    # 服务器配置默认值
    HOST = "0.0.0.0"
    PORT = 8000
    MAX_CONNECTIONS = 100
    
    # 日志配置默认值
    LOG_LEVEL = "INFO"
    LOG_FILE_PATH = "chat-server.log"
