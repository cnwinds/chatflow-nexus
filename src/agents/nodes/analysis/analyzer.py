"""
会话分析器

负责获取对话历史、调用大模型进行分析、解析结果。
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from src.common.database.manager import get_db_manager
from src.common.config import get_config_manager
from src.common.config.constants import ConfigPaths
from src.common.utils.llm_chat import LLMChat
from src.common.utils import parse_json_from_llm_response


logger = logging.getLogger(__name__)


class SessionAnalyzer:
    """会话分析器"""
    
    def __init__(
        self,
        system_prompt: str,
        user_prompt_template: str,
        engine=None,
        db_manager=None,
        llm_chat: Optional[LLMChat] = None
    ):
        """初始化分析器
        
        Args:
            system_prompt: 会话分析使用的系统提示词
            user_prompt_template: 会话分析使用的用户提示词模板
            engine: 工作流引擎，用于渲染jinja2模板
            db_manager: 数据库管理器，如果为None则使用全局管理器
            llm_chat: LLM聊天实例，如果为None则创建新实例
        """
        if not system_prompt or not user_prompt_template:
            raise ValueError("system_prompt 和 user_prompt_template 不能为空")
        
        self.db_manager = db_manager or get_db_manager()
        self.llm_chat = llm_chat or LLMChat()
        self.system_prompt = system_prompt
        self.user_prompt_template = user_prompt_template
        self.engine = engine

    @staticmethod
    def _coerce_datetime(value: Any) -> Optional[datetime]:
        """将数据库返回的时间转换为datetime"""
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    def _calculate_conversation_duration(self, messages: List[Dict[str, Any]]) -> int:
        """计算会话时长（秒）"""
        timestamps: List[datetime] = []
        for msg in messages:
            ts = self._coerce_datetime(msg.get("created_at"))
            if ts:
                timestamps.append(ts)
        if len(timestamps) < 2:
            return 0
        duration = max(timestamps) - min(timestamps)
        return max(int(duration.total_seconds()), 0)

    @staticmethod
    def _calculate_avg_child_sentence_length(messages: List[Dict[str, Any]]) -> float:
        """计算孩子平均句长（按字符计）"""
        lengths: List[int] = []
        for msg in messages:
            if msg.get("role") != "user":
                continue
            content = (msg.get("content") or "").strip()
            if not content:
                continue
            normalized = content.replace(" ", "").replace("\n", "")
            if normalized:
                lengths.append(len(normalized))
        if not lengths:
            return 0.0
        avg_length = sum(lengths) / len(lengths)
        return round(avg_length, 2)

    def _build_user_prompt(self, conversation_text: str) -> str:
        """根据模板构建用户提示词，使用jinja2渲染"""
        if not self.engine:
            raise ValueError("engine 未设置，无法渲染jinja2模板")
        return self.engine.render_template(self.user_prompt_template, conversation_text=conversation_text)

    @staticmethod
    def _resolve_llm_config(ai_providers: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """提取LLM所需的配置片段"""
        if not ai_providers:
            return {}
        
        # 如果包含llm键，优先使用其内部配置
        if isinstance(ai_providers, dict) and "llm" in ai_providers:
            llm_config = ai_providers.get("llm") or {}
            if isinstance(llm_config, dict):
                return llm_config
        
        # 否则直接返回原始配置（期望已经是扁平结构）
        return ai_providers
    
    async def get_conversation_history(
        self, 
        session_id: str
    ) -> Optional[Tuple[List[Dict[str, Any]], int, bool]]:
        """获取对话历史
        
        Args:
            session_id: 会话ID
            
        Returns:
            (对话记录列表, agent_id, copilot_mode) 或 None（如果对话历史为空）
        """
        try:
            sql = """
            SELECT id, role, content, agent_id, copilot_mode, created_at
            FROM chat_messages
            WHERE session_id = :session_id
            ORDER BY created_at ASC
            """
            results = await self.db_manager.execute_query(sql, {"session_id": session_id})
            
            if not results or len(results) < 2:
                logger.debug(f"对话历史为空或消息太少: session_id={session_id}, 消息数={len(results) if results else 0}")
                return None
            
            # 从第一条消息获取agent_id和copilot_mode
            first_message = results[0]
            agent_id = first_message.get('agent_id')
            copilot_mode = first_message.get('copilot_mode', False)
            
            return results, agent_id, copilot_mode
            
        except Exception as e:
            logger.error(f"获取对话历史失败: session_id={session_id}, 错误: {e}")
            return None
    
    def format_conversation_text(self, messages: List[Dict[str, Any]]) -> str:
        """格式化对话文本
        
        Args:
            messages: 对话记录列表
            
        Returns:
            格式化后的对话文本
        """
        conversation_lines = []
        
        for msg in messages:
            role = msg.get('role', '')
            content = msg.get('content', '').strip()
            
            if not content:
                continue
            
            conversation_lines.append(f"{role}：{content}")
        
        return "\n".join(conversation_lines)
    
    async def analyze_conversation(
        self,
        session_id: str,
        ai_providers: Optional[Dict[str, str]] = None
    ) -> Optional[Dict[str, Any]]:
        """分析对话内容
        
        Args:
            session_id: 会话ID
            ai_providers: AI提供商配置（可选）
            
        Returns:
            分析结果字典，如果失败则返回None
        """
        try:
            # 1. 获取对话历史
            history_result = await self.get_conversation_history(session_id)
            if not history_result:
                reason = "对话历史为空或消息太少"
                logger.info(f"跳过分析（{reason}）: session_id={session_id}")
                return {"skipped": True, "reason": reason}
            
            messages, agent_id, copilot_mode = history_result
            conversation_duration = self._calculate_conversation_duration(messages)
            avg_child_sentence_length = self._calculate_avg_child_sentence_length(messages)
            
            # 2. 格式化对话文本
            conversation_text = self.format_conversation_text(messages)
            if not conversation_text.strip():
                reason = "对话文本为空"
                logger.info(f"跳过分析（{reason}）: session_id={session_id}")
                return {"skipped": True, "reason": reason}
            
            logger.debug(f"开始分析对话: session_id={session_id}, 消息数={len(messages)}")
            
            # 3. 构建提示词
            system_prompt = self.system_prompt
            user_prompt = self._build_user_prompt(conversation_text)
            
            # 4. 准备LLM消息
            llm_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            logger.info(f"llm_messages: {llm_messages}")
            
            # 5. 加载LLM配置
            if not ai_providers:
                # 从chat.json配置文件加载ai_providers
                config_manager = get_config_manager()
                ai_providers = config_manager.get_config(ConfigPaths.CHAT_AI_PROVIDERS) or {}
                logger.debug(f"从配置文件加载ai_providers: {ai_providers}")
            
            llm_config = self._resolve_llm_config(ai_providers)
            if llm_config:
                self.llm_chat.load_config(llm_config)
            
            # 6. 调用大模型
            logger.debug(f"调用大模型进行分析: session_id={session_id}")
            llm_response = await self.llm_chat._call_llm_api(
                messages=llm_messages,
                max_tokens=3000,  # 分析结果可能较长，增加token限制
                temperature=1,  # 稍微降低温度，使分析更稳定
                context="会话分析",
                session_id=session_id,
                model="analysis"  # 使用分析模型
            )
            
            # 7. 解析响应内容
            response_content = llm_response.content
            
            # 8. 解析JSON
            try:
                analysis_result = parse_json_from_llm_response(response_content)
            except ValueError as e:
                snippet = (response_content or "")[:200]
                logger.error(
                    f"JSON解析失败: session_id={session_id}, 错误: {e}, 内容: {snippet}"
                )
                raise
            
            # 9. 验证JSON结构
            if not isinstance(analysis_result, dict):
                raise ValueError("分析结果必须是字典类型")
            
            if "session_analysis" not in analysis_result:
                raise ValueError("分析结果缺少'session_analysis'字段")
            
            if not isinstance(analysis_result["session_analysis"], list):
                raise ValueError("'session_analysis'必须是数组类型")
            
            # 验证每个分析项的结构
            for idx, item in enumerate(analysis_result["session_analysis"]):
                required_fields = [
                    "theme",
                    "interest_intensity",
                    "sentiment_intensity",
                    "situation_modes",
                    "content_summary",
                    "keywords",
                    "golden_sentences"
                ]
                for field in required_fields:
                    if field not in item:
                        raise ValueError(f"分析项[{idx}]缺少必需字段: {field}")
            
            logger.info(
                "分析成功: session_id=%s, 主题段落数=%d, 会话时长=%s秒, 平均句长=%.2f",
                session_id,
                len(analysis_result['session_analysis']),
                conversation_duration,
                avg_child_sentence_length
            )
            return {
                "analysis_result": analysis_result,
                "conversation_duration": conversation_duration,
                "avg_child_sentence_length": avg_child_sentence_length
            }
            
        except Exception as e:
            logger.error(f"分析对话失败: session_id={session_id}, 错误: {e}", exc_info=True)
            raise

