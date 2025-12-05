"""
数据库操作类

处理会话分析结果的存储和查询。
"""

import json
from src.common.logging import get_logger
from typing import Dict, Any, List, Optional
from datetime import datetime

from src.common.database.manager import get_db_manager


logger = get_logger(__name__)


class SessionAnalysisRepository:
    """会话分析数据库操作类"""
    
    def __init__(self, db_manager=None):
        """初始化数据库操作类
        
        Args:
            db_manager: 数据库管理器，如果为None则使用全局管理器
        """
        self.db_manager = db_manager or get_db_manager()
    
    async def create_analysis_task(
        self, 
        session_id: str, 
        agent_id: int, 
        copilot_mode: bool = False
    ) -> bool:
        """创建分析任务记录
        
        Args:
            session_id: 会话ID
            agent_id: 智能体ID
            copilot_mode: 是否星宝领航员模式
            
        Returns:
            是否创建成功
        """
        try:
            sql = """
            INSERT INTO session_analysis (session_id, agent_id, copilot_mode, status, retry_count)
            VALUES (:session_id, :agent_id, :copilot_mode, 'pending', 0)
            ON DUPLICATE KEY UPDATE
                agent_id = VALUES(agent_id),
                copilot_mode = VALUES(copilot_mode),
                status = 'pending',
                retry_count = 0,
                error_message = NULL,
                updated_at = CURRENT_TIMESTAMP
            """
            params = {
                "session_id": session_id,
                "agent_id": agent_id,
                "copilot_mode": copilot_mode
            }
            await self.db_manager.execute_update(sql, params)
            logger.debug(f"创建分析任务成功: session_id={session_id}, agent_id={agent_id}")
            return True
        except Exception as e:
            logger.error(f"创建分析任务失败: session_id={session_id}, 错误: {e}")
            return False
    
    async def update_analysis_status(
        self, 
        session_id: str, 
        status: str, 
        error_message: Optional[str] = None
    ) -> bool:
        """更新分析状态
        
        Args:
            session_id: 会话ID
            status: 状态（pending, processing, completed, failed, skipped）
            error_message: 错误信息（可选）
            
        Returns:
            是否更新成功
        """
        try:
            sql = """
            UPDATE session_analysis 
            SET status = :status, 
                error_message = :error_message,
                updated_at = CURRENT_TIMESTAMP
            WHERE session_id = :session_id
            """
            params = {
                "session_id": session_id,
                "status": status,
                "error_message": error_message
            }
            await self.db_manager.execute_update(sql, params)
            logger.debug(f"更新分析状态成功: session_id={session_id}, status={status}")
            return True
        except Exception as e:
            logger.error(f"更新分析状态失败: session_id={session_id}, 错误: {e}")
            return False
    
    async def mark_as_skipped(
        self, 
        session_id: str, 
        reason: str
    ) -> bool:
        """标记分析任务为跳过状态
        
        Args:
            session_id: 会话ID
            reason: 跳过原因
            
        Returns:
            是否更新成功
        """
        return await self.update_analysis_status(session_id, "skipped", reason)
    
    async def save_analysis_result(
        self, 
        session_id: str, 
        analysis_result: Dict[str, Any],
        conversation_duration: Optional[int] = None,
        avg_child_sentence_length: Optional[float] = None
    ) -> bool:
        """保存分析结果
        
        Args:
            session_id: 会话ID
            analysis_result: 分析结果字典
            conversation_duration: 会话时长（秒）
            avg_child_sentence_length: 孩子平均句长
            
        Returns:
            是否保存成功
        """
        try:
            # 将分析结果转换为JSON字符串
            analysis_json = json.dumps(analysis_result, ensure_ascii=False)
            
            sql = """
            UPDATE session_analysis 
            SET analysis_result = :analysis_result,
                conversation_duration = :conversation_duration,
                avg_child_sentence_length = :avg_child_sentence_length,
                status = 'completed',
                error_message = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE session_id = :session_id
            """
            params = {
                "session_id": session_id,
                "analysis_result": analysis_json,
                "conversation_duration": conversation_duration,
                "avg_child_sentence_length": avg_child_sentence_length
            }
            await self.db_manager.execute_update(sql, params)
            logger.debug(f"保存分析结果成功: session_id={session_id}")
            return True
        except Exception as e:
            logger.error(f"保存分析结果失败: session_id={session_id}, 错误: {e}")
            return False
    
    async def get_analysis_by_session_id(self, session_id: str) -> Optional[Dict[str, Any]]:
        """根据session_id获取分析结果
        
        Args:
            session_id: 会话ID
            
        Returns:
            分析结果字典，如果不存在则返回None
        """
        try:
            sql = """
            SELECT id, session_id, agent_id, analysis_result, status, retry_count, 
                   error_message, copilot_mode, created_at, updated_at
            FROM session_analysis
            WHERE session_id = :session_id
            """
            result = await self.db_manager.execute_one(sql, {"session_id": session_id})
            
            if not result:
                return None
            
            # 解析JSON字段
            if result.get('analysis_result'):
                try:
                    result['analysis_result'] = json.loads(result['analysis_result'])
                except (json.JSONDecodeError, TypeError):
                    result['analysis_result'] = None
            
            return result
        except Exception as e:
            logger.error(f"获取分析结果失败: session_id={session_id}, 错误: {e}")
            return None
    
    async def get_pending_analyses(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取待处理的分析任务
        
        Args:
            limit: 返回数量限制
            
        Returns:
            待处理任务列表
        """
        try:
            sql = """
            SELECT id, session_id, agent_id, copilot_mode, retry_count, created_at
            FROM session_analysis
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT :limit
            """
            results = await self.db_manager.execute_query(sql, {"limit": limit})
            return results or []
        except Exception as e:
            logger.error(f"获取待处理分析任务失败: {e}")
            return []
    
    async def get_failed_analyses(self, max_retry_count: int = 3, limit: int = 10) -> List[Dict[str, Any]]:
        """获取失败的分析任务（用于重试）
        
        Args:
            max_retry_count: 最大重试次数
            limit: 返回数量限制
            
        Returns:
            失败任务列表
        """
        try:
            sql = """
            SELECT id, session_id, agent_id, copilot_mode, retry_count, error_message, created_at
            FROM session_analysis
            WHERE status = 'failed' AND retry_count < :max_retry_count
            ORDER BY updated_at ASC
            LIMIT :limit
            """
            results = await self.db_manager.execute_query(sql, {
                "max_retry_count": max_retry_count,
                "limit": limit
            })
            return results or []
        except Exception as e:
            logger.error(f"获取失败分析任务失败: {e}")
            return []
    
    async def increment_retry_count(self, session_id: str) -> bool:
        """增加重试次数
        
        Args:
            session_id: 会话ID
            
        Returns:
            是否更新成功
        """
        try:
            sql = """
            UPDATE session_analysis 
            SET retry_count = retry_count + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE session_id = :session_id
            """
            await self.db_manager.execute_update(sql, {"session_id": session_id})
            logger.debug(f"增加重试次数成功: session_id={session_id}")
            return True
        except Exception as e:
            logger.error(f"增加重试次数失败: session_id={session_id}, 错误: {e}")
            return False
    
    async def get_processing_analyses(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取处理中的分析任务（用于系统崩溃恢复）
        
        Args:
            limit: 返回数量限制
            
        Returns:
            处理中任务列表
        """
        try:
            sql = """
            SELECT id, session_id, agent_id, copilot_mode, retry_count, updated_at
            FROM session_analysis
            WHERE status = 'processing'
            ORDER BY updated_at ASC
            LIMIT :limit
            """
            results = await self.db_manager.execute_query(sql, {"limit": limit})
            return results or []
        except Exception as e:
            logger.error(f"获取处理中分析任务失败: {e}")
            return []
    
    async def reset_processing_to_pending(self) -> int:
        """将处理中的任务重置为待处理状态（系统崩溃恢复）
        
        Returns:
            重置的任务数量
        """
        try:
            sql = """
            UPDATE session_analysis 
            SET status = 'pending',
                error_message = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE status = 'processing'
            """
            affected_rows = await self.db_manager.execute_update(sql)
            if affected_rows > 0:
                logger.info(f"系统启动恢复：将 {affected_rows} 个处理中任务重置为待处理状态")
            return affected_rows
        except Exception as e:
            logger.error(f"重置处理中任务失败: {e}")
            return 0
    
    async def get_processing_progress(self) -> Dict[str, Any]:
        """获取处理进度统计
        
        Returns:
            处理进度统计字典
        """
        try:
            sql = """
            SELECT 
                status,
                COUNT(*) as count,
                MAX(updated_at) as last_updated
            FROM session_analysis
            GROUP BY status
            """
            results = await self.db_manager.execute_query(sql)
            
            stats = {
                "pending": 0,
                "processing": 0,
                "completed": 0,
                "failed": 0,
                "skipped": 0,
                "total": 0
            }
            
            for row in results or []:
                status = row.get('status', '').lower()
                count = row.get('count', 0)
                if status in stats:
                    stats[status] = count
                    stats["total"] += count
            
            # 获取当前正在处理的session_id（如果有）
            current_processing_sql = """
            SELECT session_id, updated_at
            FROM session_analysis
            WHERE status = 'processing'
            ORDER BY updated_at DESC
            LIMIT 1
            """
            current_result = await self.db_manager.execute_one(current_processing_sql)
            if current_result:
                stats["current_processing_session_id"] = current_result.get('session_id')
                stats["current_processing_updated_at"] = current_result.get('updated_at')
            else:
                stats["current_processing_session_id"] = None
                stats["current_processing_updated_at"] = None
            
            return stats
        except Exception as e:
            logger.error(f"获取处理进度失败: {e}")
            return {
                "pending": 0,
                "processing": 0,
                "completed": 0,
                "failed": 0,
                "skipped": 0,
                "total": 0,
                "current_processing_session_id": None,
                "current_processing_updated_at": None
            }

