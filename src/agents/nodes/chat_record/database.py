"""
聊天记录数据库操作
"""
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from src.common.database.manager import DatabaseManager
from .utils import format_time


class ChatRecordDatabase:
    """聊天记录数据库操作类"""
    
    def __init__(self, db_manager: DatabaseManager, logger: logging.Logger = None):
        self.db_manager = db_manager
        self.logger = logger or logging.getLogger(__name__)
    
    async def save_chat_record(
        self,
        session_id: str,
        agent_id: int,
        role: str,
        content: str,
        emotion: str = "neutral",
        audio_path: str = "",
        copilot_mode: bool = False
    ):
        """保存聊天记录到数据库"""
        try:
            sql = """
                INSERT INTO chat_messages (session_id, agent_id, role, content, emotion, audio_file_path, copilot_mode, created_at)
                VALUES (:session_id, :agent_id, :role, :content, :emotion, :audio_file_path, :copilot_mode, :created_at)
            """
            
            current_time = datetime.now()
            params = {
                "session_id": session_id,
                "agent_id": agent_id,
                "role": role,
                "content": content,
                "emotion": emotion,
                "audio_file_path": audio_path,
                "copilot_mode": copilot_mode,
                "created_at": current_time
            }
            
            affected_rows = await self.db_manager.execute_update(sql, params)
            
            if affected_rows > 0:
                self.logger.debug(f"聊天记录保存成功：会话{session_id}, 智能体{agent_id}, 角色{role}")
            else:
                self.logger.warning(f"聊天记录保存失败：数据库更新返回0行")
        except Exception as e:
            self.logger.error(f"保存异常: {e}", exc_info=True)
    
    async def fetch_compressed_record(
        self,
        agent_id: int,
        copilot_mode: Optional[bool] = None
    ) -> Optional[Dict[str, Any]]:
        """获取最新压缩记录"""
        try:
            where_clause = "WHERE agent_id = :agent_id"
            params = {"agent_id": agent_id}
            
            if copilot_mode is not None:
                where_clause += " AND copilot_mode = :copilot_mode"
                params["copilot_mode"] = copilot_mode
            
            sql = f"""
                SELECT id, agent_id, compressed_content, content_last_time, created_at
                FROM chat_compressed_messages
                {where_clause}
                ORDER BY created_at DESC
                LIMIT 1
            """
            
            result = await self.db_manager.execute_query(sql, params)
            
            if result:
                record = result[0]
                created_at = format_time(record['created_at'])
                content_last_time = format_time(record['content_last_time'])
                
                compressed_record = {
                    'id': record['id'],
                    'agent_id': record['agent_id'],
                    'compressed_content': record['compressed_content'],
                    'content_last_time': content_last_time,
                    'created_at': created_at
                }
                
                self.logger.info(f"找到压缩记录: {content_last_time}")
                return compressed_record
            
            return None
        except Exception as e:
            self.logger.error(f"获取压缩记录异常: {e}", exc_info=True)
            return None
    
    async def fetch_uncompressed_records(
        self,
        agent_id: int,
        limit: int = 100,
        start_time: Optional[str] = None,
        copilot_mode: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """获取未压缩记录"""
        try:
            where_clause = "WHERE agent_id = :agent_id"
            params = {"agent_id": agent_id, "limit": limit}
            
            if start_time:
                where_clause += " AND created_at > :start_time"
                try:
                    time_str = start_time.replace('Z', '+00:00')
                    params["start_time"] = datetime.fromisoformat(time_str)
                except Exception:
                    self.logger.warning(f"无法解析时间格式: {start_time}")
                    params["start_time"] = start_time
            
            if copilot_mode is not None:
                where_clause += " AND copilot_mode = :copilot_mode"
                params["copilot_mode"] = copilot_mode
            
            sql = f"""
                SELECT id, role, content, emotion, audio_file_path, created_at
                FROM chat_messages
                {where_clause}
                ORDER BY created_at ASC
                LIMIT :limit
            """
            
            result = await self.db_manager.execute_query(sql, params)
            
            chat_history = []
            for record in result:
                message = {
                    'id': record['id'],
                    'role': record['role'],
                    'content': record['content'],
                    'created_at': format_time(record['created_at'])
                }
                if record.get('emotion'):
                    message['emotion'] = record['emotion']
                if record.get('audio_file_path'):
                    message['audio_file_path'] = record['audio_file_path']
                chat_history.append(message)
            
            self.logger.info(f"查询到 {len(chat_history)} 条未压缩消息")
            return chat_history
        except Exception as e:
            self.logger.error(f"查询未压缩消息异常: {e}", exc_info=True)
            return []
    
    async def save_compressed_message(
        self,
        agent_id: int,
        compressed_content: str,
        content_last_time: str,
        copilot_mode: bool = False
    ) -> bool:
        """保存压缩消息到数据库"""
        try:
            # 解析时间字符串
            try:
                if isinstance(content_last_time, str):
                    time_str = content_last_time.replace('Z', '+00:00')
                    last_time = datetime.fromisoformat(time_str)
                else:
                    last_time = content_last_time
            except Exception:
                self.logger.error(f"无法解析时间格式: {content_last_time}")
                return False
            
            sql = """
                INSERT INTO chat_compressed_messages (agent_id, compressed_content, content_last_time, copilot_mode, created_at)
                VALUES (:agent_id, :compressed_content, :content_last_time, :copilot_mode, :created_at)
            """
            
            affected_rows = await self.db_manager.execute_update(sql, {
                "agent_id": agent_id,
                "compressed_content": compressed_content,
                "content_last_time": last_time,
                "copilot_mode": copilot_mode,
                "created_at": datetime.now()
            })
            
            if affected_rows > 0:
                self.logger.debug(f"压缩消息保存成功：智能体{agent_id}, 模式{copilot_mode}")
                return True
            else:
                self.logger.warning(f"压缩消息保存失败：数据库更新返回0行")
                return False
        except Exception as e:
            self.logger.error(f"保存压缩异常: {e}", exc_info=True)
            return False
    
    async def get_chat_history_by_agent(
        self,
        agent_id: int,
        limit: int = 10,
        days: int = 7,
        copilot_mode: Optional[bool] = None
    ) -> Dict[str, Any]:
        """按智能体获取聊天历史"""
        try:
            where_clause = "WHERE agent_id = :agent_id"
            params = {"agent_id": agent_id, "limit": limit}
            
            if days is not None:
                where_clause += " AND created_at >= :start_time"
                params["start_time"] = datetime.now() - timedelta(days=days)
            
            if copilot_mode is not None:
                where_clause += " AND copilot_mode = :copilot_mode"
                params["copilot_mode"] = copilot_mode
            
            sql = f"""
                SELECT id, role, content, emotion, audio_file_path, created_at
                FROM chat_messages
                {where_clause}
                ORDER BY created_at ASC
                LIMIT :limit
            """
            
            result = await self.db_manager.execute_query(sql, params)
            
            chat_history = []
            for record in result:
                message = {
                    'id': record['id'],
                    'role': record['role'],
                    'content': record['content'],
                    'created_at': format_time(record['created_at'])
                }
                if record.get('emotion'):
                    message['emotion'] = record['emotion']
                if record.get('audio_file_path'):
                    message['audio_file_path'] = record['audio_file_path']
                chat_history.append(message)
            
            return {
                "status": "success",
                "recent_chats": chat_history,
                "total_count": len(chat_history)
            }
        except Exception as e:
            self.logger.error(f"查询历史异常: {e}", exc_info=True)
            return {
                "status": "success",
                "recent_chats": [],
                "total_count": 0
            }









