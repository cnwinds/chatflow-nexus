#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""依赖注入模块"""

from fastapi import Depends, Header, HTTPException, status
from typing import Optional, Dict, Any

from src.common.database.manager import get_db_manager, DatabaseManager
from src.agents.utils.jwt_utils import verify_token
from src.agents.services.user_service import UserService

async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: DatabaseManager = Depends(get_db_manager)
) -> Dict[str, Any]:
    """获取当前用户信息
    
    Args:
        authorization: Authorization header，格式为 "Bearer {token}"
        db: 数据库管理器
        
    Returns:
        用户信息字典
        
    Raises:
        HTTPException: 如果token无效或用户不存在
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少认证token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 提取token
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证格式，应为 'Bearer {token}'",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 验证token
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 获取用户信息
    user_service = UserService()
    user = await user_service.get_user_by_id(db, payload["user_id"])
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被禁用",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user

async def get_current_user_id(
    user: Dict[str, Any] = Depends(get_current_user)
) -> int:
    """获取当前用户ID
    
    Args:
        user: 当前用户信息（通过get_current_user获取）
        
    Returns:
        用户ID
    """
    return user["id"]

# 导出依赖函数
__all__ = ["get_current_user", "get_current_user_id", "get_db_manager"]

