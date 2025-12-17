"""
后台管理系统配置

提供系统配置和初始化功能
"""

import os
from typing import Dict, Any


class AdminConfig:
    """后台管理系统配置类"""
    
    # 应用配置
    SECRET_KEY = os.getenv('ADMIN_SECRET_KEY', 'ai-toys-admin-secret-key-2024')
    DEBUG = os.getenv('ADMIN_DEBUG', 'False').lower() == 'true'
    HOST = os.getenv('ADMIN_HOST', '0.0.0.0')
    PORT = int(os.getenv('ADMIN_PORT', '8100'))
    
    
    
    
    @classmethod
    def validate_config(cls) -> Dict[str, Any]:
        """验证配置"""
        errors = []
        warnings = []
        
        # 检查安全配置
        if len(cls.SECRET_KEY) < 32:
            warnings.append("SECRET_KEY长度不足，建议使用更长的密钥")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        }


# 创建配置实例
config = AdminConfig()
