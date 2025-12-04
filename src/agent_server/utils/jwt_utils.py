#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""JWT工具模块"""

import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from src.agents.config import get_config

# JWT配置
SECRET_KEY = None
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24 * 7  # 默认7天

def get_secret_key() -> str:
    """获取JWT密钥"""
    global SECRET_KEY
    if SECRET_KEY is None:
        config = get_config()
        SECRET_KEY = config.get_config("agents.jwt.secret_key", "your-secret-key-change-in-production")
    return SECRET_KEY

def create_token(user_id: int, login_name: str, expire_hours: int = TOKEN_EXPIRE_HOURS) -> Dict[str, Any]:
    """创建JWT token
    
    Args:
        user_id: 用户ID
        login_name: 登录名
        expire_hours: 过期时间（小时）
        
    Returns:
        包含token和过期时间的字典
    """
    expire = datetime.utcnow() + timedelta(hours=expire_hours)
    payload = {
        "user_id": user_id,
        "login_name": login_name,
        "exp": expire,
        "iat": datetime.utcnow()
    }
    token = jwt.encode(payload, get_secret_key(), algorithm=ALGORITHM)
    
    return {
        "token": token,
        "expire": int(expire.timestamp()),
        "user_id": user_id
    }

def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """验证JWT token
    
    Args:
        token: JWT token字符串
        
    Returns:
        如果验证成功返回payload字典，失败返回None
    """
    try:
        payload = jwt.decode(token, get_secret_key(), algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

