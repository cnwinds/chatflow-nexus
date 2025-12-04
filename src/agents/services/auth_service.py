#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""认证服务"""

from typing import Optional, Dict, Any
from src.agents.services.user_service import UserService
from src.common.database.manager import DatabaseManager

class AuthService:
    """认证服务类"""
    
    def __init__(self):
        self.user_service = UserService()
    
    async def login(self, db: DatabaseManager, login_name: str, password: str) -> Optional[Dict[str, Any]]:
        """用户登录
        
        Args:
            db: 数据库管理器
            login_name: 登录名
            password: 密码
            
        Returns:
            登录成功返回token信息，失败返回None
        """
        return await self.user_service.login_with_password(db, login_name, password)
    
    async def register(self, db: DatabaseManager, user_name: str, login_name: str, password: str, mobile: Optional[str] = None, login_type: int = 1) -> bool:
        """用户注册
        
        Args:
            db: 数据库管理器
            user_name: 用户名
            login_name: 登录名
            password: 密码
            mobile: 手机号
            login_type: 登录类型
            
        Returns:
            注册是否成功
        """
        return await self.user_service.create_user(db, user_name, login_name, password, mobile, login_type)

