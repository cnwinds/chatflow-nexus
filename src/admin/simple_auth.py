"""
简化的后台管理系统认证模块

不依赖复杂的配置系统，直接使用环境变量
"""

import hashlib
import secrets
import os
import bcrypt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from quart import session, request, jsonify
from functools import wraps

from src.common.exceptions import AuthenticationError, ValidationError
from src.common.database.manager import DatabaseManager


class SimpleAdminAuth:
    """简化的后台管理系统认证类"""
    
    def __init__(self, db_manager: DatabaseManager = None):
        self.session_timeout = 3600  # 1小时超时
        self.db_manager = db_manager
    
    def hash_password(self, password: str) -> str:
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
    
    def generate_session_token(self) -> str:
        """生成会话令牌"""
        return secrets.token_urlsafe(32)
    
    def verify_password(self, password: str, hashed: str) -> bool:
        """验证密码
        
        Args:
            password: 明文密码
            hashed: 哈希后的密码
            
        Returns:
            bool: 密码是否正确
        """
        password_bytes = password.encode('utf-8')
        hashed_bytes = hashed.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    
    async def login(self, login_name: str, password: str) -> Dict[str, Any]:
        """
        系统用户登录
        
        Args:
            login_name: 登录名
            password: 密码
            
        Returns:
            用户信息和会话令牌
            
        Raises:
            AuthenticationError: 认证失败
        """
        try:
            if not self.db_manager:
                raise AuthenticationError("数据库管理器未初始化")
            
            # 查询系统用户 - 使用封装的DatabaseManager
            query = """
            SELECT id, login_name, user_name, password_hash, status, user_type
            FROM users 
            WHERE login_name = :login_name AND user_type = 1 AND status = 1
            """
            
            params = {"login_name": login_name}
            result = await self.db_manager.execute_query(query, params)
            
            if not result:
                raise AuthenticationError("用户不存在或权限不足")
            
            user = result[0]
            
            # 验证密码
            if not self.verify_password(password, user['password_hash']):
                raise AuthenticationError("密码错误")
            
            # 生成会话令牌
            session_token = self.generate_session_token()
            session_data = {
                'user_id': user['id'],
                'login_name': user['login_name'],
                'user_name': user['user_name'],
                'token': session_token,
                'login_time': datetime.now().isoformat()
            }
            
            # 存储会话信息
            session.update(session_data)
            
            return {
                'success': True,
                'user': {
                    'id': user['id'],
                    'login_name': user['login_name'],
                    'user_name': user['user_name'],
                    'user_type': user['user_type']
                },
                'token': session_token
            }
                
        except Exception as e:
            if isinstance(e, AuthenticationError):
                raise
            raise AuthenticationError(f"登录失败: {str(e)}")
    
    async def logout(self) -> Dict[str, Any]:
        """用户登出"""
        session.clear()
        return {'success': True, 'message': '登出成功'}
    
    async def get_current_user(self) -> Optional[Dict[str, Any]]:
        """获取当前登录用户"""
        if 'user_id' not in session:
            return None
        
        return {
            'id': session.get('user_id'),
            'login_name': session.get('login_name'),
            'user_name': session.get('user_name'),
            'login_time': session.get('login_time')
        }
    
    async def is_authenticated(self) -> bool:
        """检查是否已认证"""
        return 'user_id' in session and 'token' in session
    
    def require_auth(self, f):
        """认证装饰器"""
        @wraps(f)
        async def decorated_function(*args, **kwargs):
            if not await self.is_authenticated():
                return jsonify({'error': '需要登录', 'code': 401}), 401
            return await f(*args, **kwargs)
        return decorated_function


def create_auth_manager(db_manager: DatabaseManager = None) -> SimpleAdminAuth:
    """创建认证管理器"""
    return SimpleAdminAuth(db_manager)
