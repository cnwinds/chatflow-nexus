#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""用户服务"""

import bcrypt
from typing import Optional, Dict, Any
from src.common.database.manager import DatabaseManager
from src.agents.utils.jwt_utils import create_token

class UserService:
    """用户服务类"""
    
    @staticmethod
    def _hash_password(password: str) -> str:
        """对密码进行哈希处理
        
        Args:
            password: 明文密码
            
        Returns:
            str: 哈希后的密码
        """
        # 生成盐并哈希密码
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt(rounds=10)  # 使用rounds=10
        hashed = bcrypt.hashpw(password_bytes, salt)
        return hashed.decode('utf-8')
    
    @staticmethod
    def generate_password_hash(password: str) -> str:
        """生成密码哈希（别名方法）"""
        return UserService._hash_password(password)
    
    async def login_with_password(
        self, 
        db: DatabaseManager, 
        login_name: str, 
        password: str
    ) -> Optional[Dict[str, Any]]:
        """使用密码登录
        
        Args:
            db: 数据库管理器
            login_name: 登录名
            password: 密码
            
        Returns:
            登录成功返回token信息，失败返回None
        """
        # 查询用户（bcrypt需要先获取存储的哈希值才能验证）
        sql = """
            SELECT id, login_name, user_name, mobile, avatar, status, password_hash
            FROM users
            WHERE login_name = :login_name 
            AND status = 1
        """
        user = await db.execute_one(sql, {
            "login_name": login_name
        })
        
        if not user:
            return None
        
        # 使用bcrypt验证密码
        password_bytes = password.encode('utf-8')
        stored_hash = user["password_hash"].encode('utf-8')
        if not bcrypt.checkpw(password_bytes, stored_hash):
            return None
        
        # 生成token（移除password_hash字段）
        user.pop("password_hash", None)
        token_info = create_token(user["id"], user["login_name"])
        return token_info
    
    async def create_user(
        self,
        db: DatabaseManager,
        user_name: str,
        login_name: str,
        password: str,
        mobile: Optional[str] = None,
        login_type: int = 1
    ) -> bool:
        """创建用户
        
        Args:
            db: 数据库管理器
            user_name: 用户名
            login_name: 登录名
            password: 密码
            mobile: 手机号
            login_type: 登录类型
            
        Returns:
            创建是否成功
        """
        try:
            # 检查登录名是否已存在
            check_sql = """
                SELECT id FROM users
                WHERE login_name = :login_name AND login_type = :login_type
            """
            existing = await db.execute_one(check_sql, {
                "login_name": login_name,
                "login_type": login_type
            })
            
            if existing:
                return False
            
            # 如果提供了手机号，检查手机号是否已存在
            if mobile:
                mobile_check_sql = "SELECT id FROM users WHERE mobile = :mobile"
                existing_mobile = await db.execute_one(mobile_check_sql, {"mobile": mobile})
                if existing_mobile:
                    return False
            
            # 创建用户
            password_hash = self._hash_password(password)
            insert_sql = """
                INSERT INTO users (user_name, login_name, password_hash, mobile, login_type, status)
                VALUES (:user_name, :login_name, :password_hash, :mobile, :login_type, 1)
            """
            await db.execute_insert(insert_sql, {
                "user_name": user_name,
                "login_name": login_name,
                "password_hash": password_hash,
                "mobile": mobile,
                "login_type": login_type
            })
            
            return True
        except Exception as e:
            # 记录错误日志
            import logging
            logging.error(f"创建用户失败: {e}")
            return False
    
    async def get_user_by_id(self, db: DatabaseManager, user_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取用户信息
        
        Args:
            db: 数据库管理器
            user_id: 用户ID
            
        Returns:
            用户信息字典，不存在返回None
        """
        sql = """
            SELECT id, login_name, user_name, mobile, avatar, status, created_at
            FROM users
            WHERE id = :user_id AND status = 1
        """
        return await db.execute_one(sql, {"user_id": user_id})

