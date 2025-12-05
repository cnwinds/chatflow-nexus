#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""会话服务"""

import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from src.common.database.manager import DatabaseManager
from src.common.logging import get_logger

logger = get_logger(__name__)

class SessionService:
    """会话服务类"""
    
    async def create_session(self, db: DatabaseManager, user_id: int, agent_id: int, 
                            title: Optional[str] = None) -> Dict[str, Any]:
        """创建新会话
        
        Args:
            db: 数据库管理器
            user_id: 用户ID
            agent_id: Agent ID
            title: 会话标题（可选）
            
        Returns:
            会话信息
        """
        session_id = str(uuid.uuid4())
        now = datetime.now()
        
        return {
            "session_id": session_id,
            "user_id": user_id,
            "agent_id": agent_id,
            "title": title or "新对话",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "message_count": 0
        }
    
    async def get_user_sessions(self, db: DatabaseManager, user_id: int, 
                                limit: int = 50) -> List[Dict[str, Any]]:
        """获取用户的会话列表
        
        Args:
            db: 数据库管理器
            user_id: 用户ID
            limit: 返回数量限制
            
        Returns:
            会话列表
        """
        try:
            # 从chat_messages表聚合会话信息
            sql = """
            SELECT 
                cm.session_id,
                cm.agent_id,
                a.name as agent_name,
                MIN(cm.created_at) as created_at,
                MAX(cm.created_at) as updated_at,
                COUNT(*) as message_count,
                (
                    SELECT content 
                    FROM chat_messages cm2 
                    WHERE cm2.session_id = cm.session_id 
                    AND cm2.role = 'user' 
                    ORDER BY cm2.created_at ASC 
                    LIMIT 1
                ) as first_message
            FROM chat_messages cm
            LEFT JOIN agents a ON cm.agent_id = a.id
            WHERE cm.session_id IN (
                SELECT DISTINCT session_id 
                FROM chat_messages 
                WHERE agent_id IN (SELECT id FROM agents WHERE user_id = :user_id)
            )
            GROUP BY cm.session_id, cm.agent_id, a.name
            ORDER BY updated_at DESC
            LIMIT :limit
            """
            sessions = await db.execute_query(sql, {"user_id": user_id, "limit": limit})
            
            result = []
            for session in sessions:
                # 使用第一条用户消息作为标题
                title = session.get('first_message', '新对话')
                if title and len(title) > 50:
                    title = title[:50] + "..."
                
                result.append({
                    "session_id": session['session_id'],
                    "user_id": user_id,
                    "agent_id": session['agent_id'],
                    "agent_name": session.get('agent_name', '未知Agent'),
                    "title": title or "新对话",
                    "created_at": session['created_at'].isoformat() if hasattr(session['created_at'], 'isoformat') else str(session['created_at']),
                    "updated_at": session['updated_at'].isoformat() if hasattr(session['updated_at'], 'isoformat') else str(session['updated_at']),
                    "message_count": session.get('message_count', 0)
                })
            
            return result
        except Exception as e:
            logger.error(f"获取会话列表失败: user_id={user_id}, 错误: {str(e)}")
            return []
    
    async def get_session_messages(self, db: DatabaseManager, session_id: str, 
                                   limit: int = 100) -> List[Dict[str, Any]]:
        """获取会话消息历史
        
        Args:
            db: 数据库管理器
            session_id: 会话ID
            limit: 返回数量限制
            
        Returns:
            消息列表
        """
        try:
            sql = """
            SELECT id, session_id, role, content, created_at
            FROM chat_messages
            WHERE session_id = :session_id
            ORDER BY created_at ASC
            LIMIT :limit
            """
            messages = await db.execute_query(sql, {"session_id": session_id, "limit": limit})
            
            result = []
            for msg in messages:
                result.append({
                    "id": msg['id'],
                    "session_id": msg['session_id'],
                    "role": msg['role'],
                    "content": msg['content'],
                    "created_at": msg['created_at'].isoformat() if hasattr(msg['created_at'], 'isoformat') else str(msg['created_at'])
                })
            
            return result
        except Exception as e:
            logger.error(f"获取会话消息失败: session_id={session_id}, 错误: {str(e)}")
            return []
    
    async def delete_session(self, db: DatabaseManager, session_id: str, user_id: int) -> bool:
        """删除会话及其所有消息
        
        Args:
            db: 数据库管理器
            session_id: 会话ID
            user_id: 用户ID（用于验证权限）
            
        Returns:
            是否删除成功
        """
        try:
            # 验证会话属于该用户
            sql = """
            SELECT COUNT(*) as count
            FROM chat_messages cm
            JOIN agents a ON cm.agent_id = a.id
            WHERE cm.session_id = :session_id AND a.user_id = :user_id
            """
            result = await db.execute_one(sql, {"session_id": session_id, "user_id": user_id})
            
            if not result or result.get('count', 0) == 0:
                return False
            
            # 删除会话的所有消息
            delete_sql = """
            DELETE FROM chat_messages
            WHERE session_id = :session_id
            """
            await db.execute_update(delete_sql, {"session_id": session_id})
            
            return True
        except Exception as e:
            logger.error(f"删除会话失败: session_id={session_id}, user_id={user_id}, 错误: {str(e)}")
            return False

