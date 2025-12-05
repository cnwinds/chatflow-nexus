"""
每日总结数据库操作类

处理每日总结记录的存储和查询。
"""

import json
from src.common.logging import get_logger
from typing import Dict, Any, List, Optional
from datetime import datetime, date

from src.common.database.manager import get_db_manager


logger = get_logger(__name__)


DAILY_SUMMARY = "daily"
WEEKLY_SUMMARY = "weekly"
VALID_SUMMARY_TYPES = {DAILY_SUMMARY, WEEKLY_SUMMARY}


def _normalize_summary_type(summary_type: str) -> str:
    """规范化总结类型输入"""
    summary_type = (summary_type or DAILY_SUMMARY).lower()
    if summary_type not in VALID_SUMMARY_TYPES:
        raise ValueError(f"不支持的总结类型: {summary_type}")
    return summary_type


class GrowthSummaryRepository:
    """成长记录数据库操作类，支持日总结与周总结"""
    
    def __init__(self, db_manager=None):
        """初始化数据库操作类
        
        Args:
            db_manager: 数据库管理器，如果为None则使用全局管理器
        """
        self.db_manager = db_manager or get_db_manager()
    
    async def get_pending_agents(self, summary_type: str = DAILY_SUMMARY) -> List[Dict[str, Any]]:
        """查询需要处理的agent（当前时间匹配配置时间，且今天没有完成记录）
        
        包含两种情况：
        1. 今天的任务：当前时间匹配配置时间（每15分钟检查一次）
        2. 历史补跑：过去日期且已过执行时间，但还没完成
        
        Returns:
            需要处理的agent列表，每个元素包含 agent_id, summary_time, summary_date
        """
        try:
            summary_type = _normalize_summary_type(summary_type)
            sql = """
            SELECT a.id as agent_id, 
                COALESCE(JSON_UNQUOTE(JSON_EXTRACT(a.agent_config, '$.function_settings.daily_summary_time')), '18:00') as summary_time,
                d.summary_date
            FROM agents a
            CROSS JOIN (
                SELECT CURDATE() as summary_date
                UNION ALL SELECT CURDATE() - INTERVAL 1 DAY
                UNION ALL SELECT CURDATE() - INTERVAL 2 DAY
                UNION ALL SELECT CURDATE() - INTERVAL 3 DAY
                UNION ALL SELECT CURDATE() - INTERVAL 4 DAY
                UNION ALL SELECT CURDATE() - INTERVAL 5 DAY
                UNION ALL SELECT CURDATE() - INTERVAL 6 DAY
                UNION ALL SELECT CURDATE() - INTERVAL 7 DAY
            ) d
            WHERE a.status = 1
            AND d.summary_date >= DATE(a.created_at)
            AND (
                -- 今天的任务：当前时间 >= 配置时间（包含准点执行和补跑）
                (d.summary_date = CURDATE() 
                AND TIME_FORMAT(NOW(), '%H:%i') >= COALESCE(JSON_UNQUOTE(JSON_EXTRACT(a.agent_config, '$.function_settings.daily_summary_time')), '18:00'))
                OR
                -- 历史补跑：过去的日期直接补跑
                d.summary_date < CURDATE()
            )
            -- 排除已完成的
            AND NOT EXISTS (
                SELECT 1 
                FROM growth_summary_records dsr
                WHERE dsr.agent_id = a.id 
                    AND dsr.summary_date = d.summary_date
                    AND dsr.summary_type = :summary_type
                    AND dsr.status = 'completed'
            )
            ORDER BY d.summary_date ASC, a.id ASC
            """
            results = await self.db_manager.execute_query(sql, {"summary_type": summary_type})
            return results or []
        except Exception as e:
            logger.error(f"查询待处理agent失败: {e}", exc_info=True)
            return []
            
    async def create_summary_record(
        self, 
        agent_id: int, 
        summary_date: date, 
        scheduled_time: str,
        summary_type: str = DAILY_SUMMARY
    ) -> bool:
        """创建执行记录
        
        Args:
            agent_id: agent ID
            summary_date: 总结日期
            scheduled_time: 计划执行时间（格式：HH:MM）
            
        Returns:
            是否创建成功
        """
        try:
            summary_type = _normalize_summary_type(summary_type)
            sql = """
            INSERT INTO growth_summary_records (agent_id, summary_date, summary_type, scheduled_time, status)
            VALUES (:agent_id, :summary_date, :summary_type, :scheduled_time, 'pending')
            ON DUPLICATE KEY UPDATE
                scheduled_time = VALUES(scheduled_time),
                status = 'pending',
                created_at = CURRENT_TIMESTAMP,
                completed_at = NULL,
                summary_content = NULL
            """
            params = {
                "agent_id": agent_id,
                "summary_date": summary_date,
                "summary_type": summary_type,
                "scheduled_time": scheduled_time
            }
            await self.db_manager.execute_update(sql, params)
            logger.debug(f"创建总结记录成功: agent_id={agent_id}, summary_date={summary_date}")
            return True
        except Exception as e:
            logger.error(f"创建总结记录失败: agent_id={agent_id}, 错误: {e}")
            return False
    
    async def update_summary_record(
        self, 
        agent_id: int, 
        summary_date: date, 
        status: str, 
        summary_content: Optional[str] = None,
        summary_type: str = DAILY_SUMMARY
    ) -> bool:
        """更新执行记录
        
        Args:
            agent_id: agent ID
            summary_date: 总结日期
            status: 状态（completed/failed）
            summary_content: 总结内容（JSON字符串）
            
        Returns:
            是否更新成功
        """
        try:
            summary_type = _normalize_summary_type(summary_type)
            sql = """
            UPDATE growth_summary_records
            SET status = :status,
                completed_at = CURRENT_TIMESTAMP,
                summary_content = :summary_content
            WHERE agent_id = :agent_id 
              AND summary_date = :summary_date
              AND summary_type = :summary_type
            """
            params = {
                "agent_id": agent_id,
                "summary_date": summary_date,
                "status": status,
                "summary_type": summary_type,
                "summary_content": summary_content
            }
            affected_rows = await self.db_manager.execute_update(sql, params)
            logger.debug(f"更新总结记录成功: agent_id={agent_id}, summary_date={summary_date}, status={status}")
            return affected_rows > 0
        except Exception as e:
            logger.error(f"更新总结记录失败: agent_id={agent_id}, 错误: {e}")
            return False
    
    async def get_summary_record(
        self, 
        agent_id: int, 
        summary_date: date,
        summary_type: str = DAILY_SUMMARY
    ) -> Optional[Dict[str, Any]]:
        """获取执行记录
        
        Args:
            agent_id: agent ID
            summary_date: 总结日期
            
        Returns:
            执行记录字典，如果不存在则返回None
        """
        try:
            summary_type = _normalize_summary_type(summary_type)
            sql = """
            SELECT id, agent_id, summary_date, summary_type, scheduled_time, status, 
                   created_at, completed_at, summary_content
            FROM growth_summary_records
            WHERE agent_id = :agent_id 
              AND summary_date = :summary_date
              AND summary_type = :summary_type
            """
            result = await self.db_manager.execute_one(sql, {
                "agent_id": agent_id,
                "summary_date": summary_date,
                "summary_type": summary_type
            })
            
            if result and result.get('summary_content'):
                try:
                    result['summary_content'] = json.loads(result['summary_content'])
                except (json.JSONDecodeError, TypeError):
                    result['summary_content'] = None
            
            return result
        except Exception as e:
            logger.error(f"获取总结记录失败: agent_id={agent_id}, 错误: {e}")
            return None
    
    async def get_daily_session_analysis(
        self, 
        agent_id: int, 
        summary_date: date
    ) -> List[Dict[str, Any]]:
        """查询指定agent指定日期的所有会话分析结果
        
        Args:
            agent_id: agent ID
            summary_date: 总结日期
            
        Returns:
            会话分析结果列表，每个元素包含 analysis_result, conversation_duration, avg_child_sentence_length 等
        """
        try:
            sql = """
            SELECT id, session_id, agent_id, conversation_duration, 
                   avg_child_sentence_length, analysis_result, status, 
                   created_at, updated_at
            FROM session_analysis
            WHERE agent_id = :agent_id 
              AND DATE(created_at) = :summary_date
              AND status = 'completed'
            ORDER BY created_at ASC
            """
            results = await self.db_manager.execute_query(sql, {
                "agent_id": agent_id,
                "summary_date": summary_date
            })
            
            if not results:
                return []
            
            # 解析 analysis_result JSON字段
            parsed_results = []
            for result in results:
                if result.get('analysis_result'):
                    try:
                        result['analysis_result'] = json.loads(result['analysis_result'])
                    except (json.JSONDecodeError, TypeError):
                        result['analysis_result'] = None
                parsed_results.append(result)
            
            return parsed_results
        except Exception as e:
            logger.error(f"查询会话分析结果失败: agent_id={agent_id}, summary_date={summary_date}, 错误: {e}")
            return []
    
    async def get_weekly_session_analysis(
        self, 
        agent_id: int, 
        week_start_date: date,
        week_end_date: date
    ) -> List[Dict[str, Any]]:
        """查询指定agent指定日期范围内的所有会话分析结果（用于周报）
        
        Args:
            agent_id: agent ID
            week_start_date: 周开始日期
            week_end_date: 周结束日期
            
        Returns:
            会话分析结果列表
        """
        try:
            sql = """
            SELECT id, session_id, agent_id, conversation_duration, 
                   avg_child_sentence_length, analysis_result, status, 
                   created_at, updated_at
            FROM session_analysis
            WHERE agent_id = :agent_id 
              AND DATE(created_at) BETWEEN :week_start_date AND :week_end_date
              AND status = 'completed'
            ORDER BY created_at ASC
            """
            results = await self.db_manager.execute_query(sql, {
                "agent_id": agent_id,
                "week_start_date": week_start_date,
                "week_end_date": week_end_date
            })
            
            if not results:
                return []
            
            # 解析 analysis_result JSON字段
            parsed_results = []
            for result in results:
                if result.get('analysis_result'):
                    try:
                        result['analysis_result'] = json.loads(result['analysis_result'])
                    except (json.JSONDecodeError, TypeError):
                        result['analysis_result'] = None
                parsed_results.append(result)
            
            return parsed_results
        except Exception as e:
            logger.error(f"查询周报会话分析结果失败: agent_id={agent_id}, week_start={week_start_date}, week_end={week_end_date}, 错误: {e}")
            return []

