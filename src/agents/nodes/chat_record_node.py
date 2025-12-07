"""
聊天记录管理节点
- 记录和保存聊天内容到数据库
- 监控 token 数量，自动压缩历史记录
- 提供聊天历史和长期记忆服务
- 支持 copilot 模式区分
"""
import sys
import asyncio
from src.common.logging import get_logger
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

# 确保可以导入 src 模块（当从外部项目加载时）
_file_path = Path(__file__).resolve()
_project_root = _file_path.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from stream_workflow.core import Node, ParameterSchema, StreamChunk, register_node
from stream_workflow.core.parameter import FieldSchema
from src.common.database.manager import get_db_manager

from src.agents.nodes.chat_record.database import ChatRecordDatabase
from src.agents.nodes.chat_record.compression import ChatRecordCompression
from src.agents.nodes.chat_record.memory import ChatRecordMemory
from src.agents.nodes.chat_record.context import ChatRecordContext
from src.agents.nodes.chat_record.utils import format_time, create_message, merge_consecutive_messages


@register_node('chat_record_node')
class ChatRecordNode(Node):
    """聊天记录管理节点
    
    核心功能：
    1. 记录所有聊天内容到数据库
    2. 监控 token 数量，超过阈值时自动压缩历史
    3. 为其他节点提供聊天历史和长期记忆
    4. 支持 copilot 模式的独立记录
    
    配置参数：
    - compress_token_threshold: 压缩阈值，默认 8000
    - load_history_limit: 启动时加载的历史记录数量，默认 100
    - keep_last_rounds: 压缩时保留最后几轮对话，默认 1
    - compress_system_prompt: 压缩系统提示词（支持 Jinja2）
    - compress_user_prompt: 压缩用户提示词（支持 Jinja2）
    - memory_extract_system_prompt: 记忆提取系统提示词（支持 Jinja2）
    - memory_extract_user_prompt: 记忆提取用户提示词（支持 Jinja2）
    - memory_extract_max_length: 记忆提取结果最长字符数，默认 4000
    """
    
    EXECUTION_MODE = 'streaming'
    
    INPUT_PARAMS = {
        "user_text": ParameterSchema(
            is_streaming=True,
            schema={'text': 'string', 'confidence': 'float', 'audio_file_path': 'string', 'emotion': 'string'}
        ),
        "ai_text": ParameterSchema(
            is_streaming=True,
            schema={'text': 'string'}
        )
    }
    
    OUTPUT_PARAMS = {}
    
    CONFIG_PARAMS = {
        "compress_token_threshold": FieldSchema({'type': 'integer', 'description': '压缩token阈值'}),
        "load_history_limit": FieldSchema({'type': 'integer', 'description': '加载历史记录限制'}),
        "keep_last_rounds": FieldSchema({'type': 'integer', 'description': '压缩时保留最后几轮对话'}),
        "compress_system_prompt": FieldSchema({'type': 'string', 'required': True, 'description': '压缩系统提示词'}),
        "compress_user_prompt": FieldSchema({'type': 'string', 'required': True, 'description': '压缩用户提示词'}),
        "memory_extract_system_prompt": FieldSchema({'type': 'string', 'required': True, 'description': '记忆提取系统提示词'}),
        "memory_extract_user_prompt": FieldSchema({'type': 'string', 'required': True, 'description': '记忆提取用户提示词'}),
        "memory_extract_max_length": FieldSchema({'type': 'integer', 'description': '记忆提取结果最大字符数'})
    }

    async def initialize(self, context):
        """初始化节点"""
        self._logger = get_logger(__name__)
        
        # 注册到全局上下文
        context.set_global_var("chat_record_node", self)
        self.context = context
        
        # 加载全局配置
        self._load_global_config(context)
        
        # 加载节点配置
        self._load_node_config()
        
        # 初始化数据库管理器
        try:
            db_manager = get_db_manager()
        except RuntimeError as e:
            self._logger.error(f"数据库管理器未初始化: {e}")
            raise Exception("数据库管理器未初始化，请确保在程序启动时已初始化数据库")
        
        # 初始化工具类
        self.db = ChatRecordDatabase(db_manager)
        self.compression = ChatRecordCompression(
            self.engine,
            self.ai_providers,
            self.compress_system_prompt,
            self.compress_user_prompt,
            self.compress_token_threshold,
            self.keep_last_rounds,
            self.memory_extract_max_length
        )
        self.memory = ChatRecordMemory(
            self.user_data,
            self.engine,
            self.ai_providers,
            self.memory_extract_system_prompt,
            self.memory_extract_user_prompt,
            self.memory_extract_max_length
        )
        self.context_manager = ChatRecordContext()
        
        # 初始化状态
        self._chat_history: List[Dict[str, Any]] = []
        self._ai_text_buffer: str = ""

    def _load_global_config(self, context):
        """加载全局配置"""
        self.session_id = context.get_global_var("session_id")
        self.user_data = context.get_global_var("user_data")
        self.engine = context.get_global_var("engine")
        self.ai_providers = context.get_global_var("ai_providers") or {}
        self.copilot_mode = context.get_global_var("copilot_mode") or False
        self.agent_id = self.user_data.agent_id if self.user_data else None
    
    def _load_node_config(self):
        """加载节点配置"""
        config = self.get_config("config") or {}
        self.compress_token_threshold = int(config.get("compress_token_threshold", 8000))
        self.load_history_limit = int(config.get("load_history_limit", 100))
        self.keep_last_rounds = int(config.get("keep_last_rounds", 1))
        
        # 加载提示词模板
        self.compress_system_prompt = self.get_config("config.compress_system_prompt")
        self.compress_user_prompt = self.get_config("config.compress_user_prompt")
        self.memory_extract_system_prompt = self.get_config("config.memory_extract_system_prompt")
        self.memory_extract_user_prompt = self.get_config("config.memory_extract_user_prompt")
        self.memory_extract_max_length = int(config.get("memory_extract_max_length", 4000))

    async def run(self, context):
        """节点主循环"""
        await self._load_history()
        await asyncio.sleep(float("inf"))
    
    async def _load_history(self):
        """加载历史记录"""
        try:
            self._logger.info(f"开始加载聊天历史: agent_id={self.agent_id} (copilot={self.copilot_mode})")
            
            # 加载压缩记录
            compressed_record = await self.db.fetch_compressed_record(self.agent_id, self.copilot_mode)
            if compressed_record:
                self._add_compressed_to_history(compressed_record)
                start_time = compressed_record['content_last_time']
            else:
                start_time = None
            
            # 加载未压缩记录
            uncompressed_records = await self.db.fetch_uncompressed_records(
                self.agent_id,
                self.load_history_limit,
                start_time,
                self.copilot_mode
            )
            self._add_records_to_history(uncompressed_records)
            
            # 合并和验证
            before_count = len(self._chat_history)
            self._chat_history = merge_consecutive_messages(self._chat_history)
            after_count = len(self._chat_history)
            
            if before_count != after_count:
                self._logger.info(f"加载完成: 合并前 {before_count} 条 -> 合并后 {after_count} 条")
            else:
                self._logger.info(f"加载完成: 共 {after_count} 条消息")
            
            self.context_manager.sync_history_to_context(self._chat_history)
            await self._check_and_compress()
            
        except Exception as e:
            self._logger.error(f"加载历史异常: {e}", exc_info=True)
    
    # ==================== 消息处理 ====================
    
    async def on_chunk_received(self, param_name: str, chunk: StreamChunk):
        """处理流式输入"""
        data = chunk.data or {}
        
        if param_name == "user_text":
            await self._handle_user_input(data)
        elif param_name == "ai_text":
            await self._handle_ai_output(data)
    
    async def _handle_user_input(self, data: Dict[str, Any]):
        """处理用户输入"""
        text = (data.get("text") or "").strip()
        if not text:
            return
        
        emotion = data.get("emotion") or "neutral"
        audio_path = data.get("audio_file_path") or ""
        
        await self._save_message("user", text, emotion, audio_path)
    
    async def _handle_ai_output(self, data: Dict[str, Any]):
        """处理 AI 输出（流式）"""
        text = data.get("text", "")
        
        if text == "":  # 流结束
            if self._ai_text_buffer.strip():
                await self._save_message("assistant", self._ai_text_buffer.strip())
                self._ai_text_buffer = ""
        else:
            self._ai_text_buffer += text
    
    async def _save_message(self, role: str, content: str, emotion: str = "neutral", audio_path: str = ""):
        """保存消息（数据库 + 内存）"""
        # 保存到数据库
        await self.db.save_chat_record(
            self.session_id,
            self.agent_id,
            role,
            content,
            emotion,
            audio_path,
            self.copilot_mode
        )
        
        # 添加到内存
        message = create_message(role, content, emotion, audio_path)
        self._chat_history.append(message)
        self.context_manager.add_chat_context(role, content)
        
        # 检查是否需要压缩
        await self._check_and_compress()
    
    def _add_compressed_to_history(self, record: Dict[str, Any]):
        """添加压缩记录到历史"""
        self._chat_history.append({
            "role": "assistant",
            "content": record['compressed_content'],
            "created_at": record['created_at'],
            "is_compressed": True
        })
    
    def _add_records_to_history(self, records: List[Dict[str, Any]]):
        """批量添加记录到历史"""
        for record in records:
            message = {
                "role": record['role'],
                "content": record['content'],
                "created_at": record['created_at']
            }
            
            if record.get('emotion'):
                message['emotion'] = record['emotion']
            if record.get('audio_file_path'):
                message['audio_file_path'] = record['audio_file_path']
            
            self._chat_history.append(message)

    # ==================== 压缩逻辑 ====================
    
    async def _check_and_compress(self):
        """检查并触发压缩"""
        if not self.compression.check_and_compress(self._chat_history):
            return
        
        asyncio.create_task(self._compress_chat_history())
    
    async def _compress_chat_history(self):
        """压缩聊天历史"""
        if self.compression.is_compressing():
            return
        
        self.compression.set_compressing(True)
        
        try:
            # 1. 检查消息数量
            min_required = 2 * self.keep_last_rounds
            if len(self._chat_history) <= min_required:
                self._logger.info(f"历史记录不足（{len(self._chat_history)} <= {min_required}），跳过压缩")
                return
            
            # 2. 找到保留起点
            keep_start = self.compression.find_keep_start_index(self._chat_history)
            if not keep_start or keep_start <= 0:
                self._logger.info(f"无法找到完整的 {self.keep_last_rounds} 轮对话，跳过压缩")
                return
            
            # 3. 分离消息
            to_compress = self._chat_history[:keep_start]
            to_keep = self._chat_history[keep_start:]
            
            # 4. 过滤已压缩消息
            uncompressed = [msg for msg in to_compress if not msg.get("is_compressed")]
            if not uncompressed:
                self._logger.warning("没有需要压缩的消息")
                return
            
            # 5. 调用 LLM 压缩
            compressed_content = await self.compression.compress_messages(uncompressed)
            if not compressed_content:
                self._logger.warning("压缩失败")
                return
            
            # 6. 保存压缩结果
            last_time = format_time(uncompressed[-1].get('created_at'))
            if not await self.db.save_compressed_message(
                self.agent_id,
                compressed_content,
                last_time,
                self.copilot_mode
            ):
                return
            
            # 7. 重建历史
            compressed_msg = {
                "role": "assistant",
                "content": compressed_content,
                "created_at": to_compress[0].get('created_at', datetime.now().isoformat()),
                "is_compressed": True
            }
            self._chat_history = [compressed_msg] + to_keep
            
            # 8. 同步和提取记忆
            self._chat_history = merge_consecutive_messages(self._chat_history)
            self.context_manager.sync_history_to_context(self._chat_history)
            await self.memory.extract_memory(uncompressed)
            
            self._logger.info(f"压缩完成: 压缩了 {len(uncompressed)} 条消息")
            
        except Exception as e:
            self._logger.error(f"压缩异常: {e}", exc_info=True)
        finally:
            self.compression.set_compressing(False)

    # ==================== 上下文管理 ====================
    
    def add_chat_context(self, role: str, content: str, **kwargs):
        """添加聊天上下文"""
        self.context_manager.add_chat_context(role, content, **kwargs)
    
    def get_chat_messages(self, system_prompt: Optional[str] = None, user_prompt: Optional[str] = None) -> List[Dict[str, Any]]:
        """构建 OpenAI 格式的消息列表"""
        return self.context_manager.get_chat_messages(system_prompt, user_prompt)
    
    def clear_chat_context(self):
        """清空上下文"""
        self.context_manager.clear_chat_context()
    
    def get_context_count(self) -> int:
        """获取上下文消息数量"""
        return self.context_manager.get_context_count()

    # ==================== 外部接口 ====================
    
    def get_chat_history_list(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取聊天历史列表"""
        history = self._chat_history.copy()
        if limit:
            history = history[-limit:]
        return history

    def get_recent_history_summary(self, limit: int = 10) -> Dict[str, Any]:
        """提供最近聊天历史摘要，供其他节点快速使用。"""
        history = self._chat_history or []
        total_count = len(history)
        if limit > 0:
            recent = history[-limit:]
        else:
            recent = history
        # 返回复制，防止外部修改内部缓存
        return {
            "status": "success",
            "recent_chats": [chat.copy() for chat in recent],
            "total_count": total_count
        }
    
    def get_memory(self) -> Dict[str, Any]:
        """获取长期记忆"""
        return self.memory.get_memory()
    
    async def save_chat_record(
        self,
        role: str,
        content: str,
        emotion: Optional[str] = None,
        audio_file_path: Optional[str] = None
    ) -> bool:
        """保存聊天记录（外部调用）"""
        if not self.session_id:
            self._logger.error("未设置 session_id")
            return False
        
        try:
            await self.db.save_chat_record(
                self.session_id,
                self.agent_id,
                role,
                content,
                emotion or "neutral",
                audio_file_path or "",
                self.copilot_mode
            )
            return True
        except Exception as e:
            self._logger.error(f"保存失败: {e}", exc_info=True)
            return False
    
    async def get_chat_history(self, limit: int = 10, days: int = 7) -> Dict[str, Any]:
        """获取聊天历史（外部调用）"""
        return await self.get_chat_history_by_agent(limit, days)
    
    async def get_chat_history_by_agent(self, limit: int = 10, days: int = 7) -> Dict[str, Any]:
        """按智能体获取聊天历史"""
        return await self.db.get_chat_history_by_agent(
            self.agent_id,
            limit,
            days,
            self.copilot_mode
        )
