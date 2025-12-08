"""
Agent 节点

输入:
- user_text: 用户文本
- confidence: 置信度
- tts_current_sentence: TTS 当前播放句子（反馈回路）
- tts_all_complete: TTS 全部完成（反馈回路）

输出:
- response_text_stream: 文本增量（流，空文本表示结束）
"""

import sys
from pathlib import Path
from typing import Any, Dict, Optional
import time
import json
# 确保可以导入 src 模块（当从外部项目加载时）
_file_path = Path(__file__).resolve()
_project_root = _file_path.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from stream_workflow.core.parameter import FieldSchema
from stream_workflow.core import Node, ParameterSchema, StreamChunk, register_node

from src.common.utils.llm_chat import LLMChat
from src.common.utils.date_utils import get_current_time, get_lunar_date_str
from src.common.logging import get_logger
from datetime import datetime

logger = get_logger(__name__)


@register_node("agent_node")
class AgentNode(Node):
    """负责与 AI 进行对话，处理用户文本并生成回复。
    
    功能: 接收用户文本输入，调用 LLM 生成回复，支持流式输出。可以处理普通对话、路由指令和自我介绍请求。
    支持多 agent 协作，可以接收其他 agent 的介绍信息，并在生成回复时考虑可用的 agent。
    
    配置参数:
    - system_prompt: 系统提示词，用于定义 agent 的角色和行为。支持 Jinja2 模板语法，可使用变量如 agent_id、agent_intro、user_message 等。
    - user_prompt: 用户提示词，用于格式化用户输入。支持 Jinja2 模板语法，可使用变量如 user_message、confidence、emotion 等。
    - intro: agent 介绍文本，当收到自我介绍请求时会发送给其他 agent。支持 Jinja2 模板语法，可使用变量如 agent_id。
    """
    
    EXECUTION_MODE = "streaming"    # 输入参数定义
    INPUT_PARAMS = {
        "user_text": ParameterSchema(
            is_streaming=True,
            schema={'text': 'string', 'confidence': 'float', 'audio_file_path': 'string', 'emotion': 'string'}
        ),
        "tts_status": ParameterSchema(
            is_streaming=True,
            schema={'state': 'string', 'text': 'string'}
        ),
        "intro_request": ParameterSchema(
            is_streaming=True,
            schema={}
        ),
        "all_agents_intro": ParameterSchema(
            is_streaming=True,
            schema={'agents': 'object'}
        ),
        "route_text": ParameterSchema(
            is_streaming=True,
            schema={'user_query': 'string', 'transition_text': 'string'}
        )
    }    # 输出参数定义
    OUTPUT_PARAMS = {
        "response_text_stream": ParameterSchema(
            is_streaming=True,
            schema={'text': 'string'}
        ),
        "agent_intro": ParameterSchema(
            is_streaming=True,
            schema={'agent_id': 'string', 'intro_text': 'string'}
        )
    }    # 配置参数定义（使用 FieldSchema 格式）
    CONFIG_PARAMS = {
        "system_prompt": FieldSchema({
            'type': 'string',
            'required': True,
            'description': '系统提示词'
        }),
        "user_prompt": FieldSchema({
            'type': 'string',
            'required': True,
            'description': '用户提示词'
        }),
        "intro": FieldSchema({
            'type': 'string',
            'required': True,
            'description': 'agent介绍'
        })
    }

    async def initialize(self, context):
        """初始化节点 - 在run之前调用，确保所有资源在接收数据前已准备好"""
        self.context = context

        # 从全局上下文获取配置
        self.agent_id = context.get_global_var("agent_id")
        self.session_id = context.get_global_var("session_id")
        self.engine = context.get_global_var("engine")
        self.user_data = context.get_global_var("user_data")

        # 从节点配置获取 agent 特定配置
        self.intro = self.get_config("config.intro")
        self.system_prompt = self.get_config("config.system_prompt")
        self.user_prompt = self.get_config("config.user_prompt")
        
        # 验证必需配置
        if not self.system_prompt or not self.user_prompt:
            self.context.log_error(f"Agent {self.node_id} 配置错误：必须提供 config.system_prompt 和 config.user_prompt")
            return
        
        # 存储其他 agent 的介绍信息
        self.available_agents = {}

        # 加载配置
        ai_providers = context.get_global_var("ai_providers") or {}
        self.llm_config = ai_providers.get("llm", {})
        
        # 1. 初始化 LLM（会自动加载基础配置）
        self.llm: Optional[LLMChat] = LLMChat()
        self.llm.load_config(self.llm_config)

        # 2. 创建聊天记录管理器
        self.chat_record = context.get_global_var("chat_record_node")
        
        # 3. 获取工具列表（全局 UTCP）
        from src.agents.utcp_tools import get_utcp_tools
        self.tools = await get_utcp_tools(tags=["llm_tools"])

        self._is_playing: bool = False

    async def run(self, context):
        """运行节点 - 持续运行，等待处理流式数据"""
        import asyncio
        await asyncio.sleep(float("inf"))

    async def on_chunk_received(self, param_name: str, chunk: StreamChunk):
        # 播放反馈：更新内部播放状态
        if param_name == "tts_status":
            data = chunk.data or {}
            state = data.get("state", "")
            if state == "start":
                self._is_playing = True
            elif state == "stop":
                self._is_playing = False
            return

        # 处理自我介绍请求
        if param_name == "intro_request":
            await self._handle_intro_request()
            return
        
        # 处理其他 agent 介绍
        if param_name == "all_agents_intro":
            await self._handle_all_agents_intro(chunk)
            return

        # 处理路由文本
        if param_name == "route_text":
            await self._handle_route_text(chunk)
            return

        if param_name == "user_text":
            text = (chunk.data or {}).get("text", "")
            confidence = (chunk.data or {}).get("confidence", None)
            audio_file_path = (chunk.data or {}).get("audio_file_path", None)
            emotion = (chunk.data or {}).get("emotion", None)

            if not text:
                await self.emit_chunk("response_text_stream", {"text": ""})
                return
            
            # 准备格式化变量并调用 LLM
            format_vars = self._prepare_format_vars(
                user_message=text,
                confidence=confidence,
                emotion=emotion
            )
            
            await self._call_llm_and_stream(format_vars, context_name=f"{self.node_id} 流式对话")

    def _prepare_format_vars(self, user_message: str, confidence: Optional[float] = None,
                            emotion: Optional[str] = None, transition_text: Optional[str] = None,
                            user_query: Optional[str] = None) -> Dict[str, Any]:
        """准备格式化变量（公共方法）
        
        Args:
            user_message: 用户消息文本
            confidence: 置信度（可选）
            emotion: 用户情感（可选）
            transition_text: 转场文本（路由场景使用）
            user_query: 用户原始需求（路由场景使用）
            
        Returns:
            格式化变量字典
        """
        # 获取公共数据
        voice_name = self.user_data.get_memory("preferences.current_voice") or "original"
        char_prompt = self.user_data.get_config("profile.character.prompt") or ""
        long_term_memory = self.user_data.get_memory("chat.long_term_memory") or None
        
        
        # 获取模式指示器
        # 判断低置信度模式（根据置信度阈值判断）
        raw_thresholds = self.user_data.get_config("audio_settings.confidence_threshold")
        default_thresholds = [0.8, 0.5]
        
        # 判断输入是否满足要求：必须是包含至少2个数字的列表/元组
        if (isinstance(raw_thresholds, (list, tuple)) and 
            len(raw_thresholds) >= 2 and 
            all(isinstance(x, (int, float)) for x in raw_thresholds[:2])):
            confidence_thresholds = [float(raw_thresholds[0]), float(raw_thresholds[1])]
        else:
            confidence_thresholds = default_thresholds
            logger.warning(f"置信度阈值配置无效: {raw_thresholds}，使用默认值: {default_thresholds}")
        
        threshold2 = confidence_thresholds[1]
        is_low_confidence = confidence is not None and confidence < threshold2
        
        # 低置信度情况下，根据是否开启呀呀学语模式决定显示哪个模式
        if is_low_confidence:
            enable_baby_talk_mode = self.user_data.get_config("audio_settings.enable_baby_talk_mode") or False
            if enable_baby_talk_mode:
                mode_indicator = "🎵"
            else:
                mode_indicator = "⚠️"
        else:
            mode_indicator = ""
        
        # 获取可用声音列表
        available_voices = self.user_data.get_config("clone_voice._voice_names") or []
        
        # 获取引导话题和策略（从 memory 中获取）
        guidance_topic = self.user_data.get_config("guidance.topic") or None
        guidance_strategy = self.user_data.get_config("guidance.strategy") or None
        
        now = datetime.now()
        format_vars = {
            "character_prompt": char_prompt,

            "current_time": get_current_time(now),  # 公历时间
            "lunar_date": get_lunar_date_str(now),  # 农历日期（可选）
            "weekday": time.strftime("%A"),
            "mode_indicator": mode_indicator,
            "voice_name": voice_name,

            "confidence": confidence if confidence is not None else 1.0,
            "user_emotion": emotion or "neutral",
            "user_message": user_message,

            "long_term_memory": long_term_memory,  # 模板中使用 tojson 过滤器

            "available_agents": self.available_agents,
            "current_agent_id": self.node_id,
            "current_agent_intro": self.intro or "",  # 当前伙伴专长

            "available_voices": available_voices,

            "guidance_topic": guidance_topic,
            "guidance_strategy": guidance_strategy,
            
            "has_transition": transition_text is not None,
            "transition_text": transition_text,
        }
        
        return format_vars
    
    async def _call_llm_and_stream(self, format_vars: Dict[str, Any], context_name: str):
        """调用 LLM 并处理流式响应（使用 LLMChat 工具类）
        
        Args:
            format_vars: 格式化变量字典
            context_name: 上下文名称（用于日志）
        """
        # 渲染提示词模板
        system_prompt_text = self.engine.render_template(self.system_prompt, **format_vars)
        user_prompt_text = self.engine.render_template(self.user_prompt, **format_vars)

        # 获取消息列表（chat_record_node 已自动添加上下文）
        if self.chat_record is None:
            self.context.log_warning(f"Agent {self.node_id} chat_record_node 未找到，使用空历史记录")
            # 构建基本消息列表（无历史记录）
            messages = []
            if system_prompt_text and system_prompt_text.strip():
                messages.append({"role": "system", "content": system_prompt_text.strip()})
            if user_prompt_text and user_prompt_text.strip():
                messages.append({"role": "user", "content": user_prompt_text.strip()})
        else:
            # 等待历史记录加载完成（如果正在加载）
            await self.chat_record.wait_for_history_loaded()
            messages = self.chat_record.get_chat_messages(system_prompt_text, user_prompt_text)
        
        # 流式响应回调：将内容增量发送到输出流
        async def on_delta(chunk_type: str, data: Dict[str, Any]):
            if chunk_type == "content_delta":
                delta = (data.get("delta") or {}).get("content", "")
                if delta:
                    await self.emit_chunk("response_text_stream", {"text": delta})
        
        # 使用 LLMChat 工具类进行流式调用
        try:
            await self.llm.call_llm_stream(
                messages=messages,
                tools=self.tools,
                context=context_name,
                content_callback=on_delta,
                session_id=self.session_id,
                model="primary"
            )
        except Exception as e:
            self.context.log_error(f"LLM调用失败: {e}")
            raise
        finally:
            # 发送空文本表示流结束
            await self.emit_chunk("response_text_stream", {"text": ""})
    
    async def _handle_intro_request(self):
        """处理自我介绍请求"""
        try:
            if not self.intro:
                self.context.log_error(f"Agent {self.node_id} 配置错误：必须提供 config.intro")
                return
            
            # 使用 engine 提供的 Jinja2 模板渲染自我介绍文本
            format_vars = {"agent_id": self.node_id}
            intro_text = self.engine.render_template(self.intro, **format_vars)
            
            # 发送自我介绍
            await self.emit_chunk("agent_intro", {
                "agent_id": self.node_id,
                "intro_text": intro_text
            })
            
            self.context.log_info(f"Agent {self.node_id} 发送自我介绍: {intro_text}")
            
        except Exception as e:
            self.context.log_error(f"Agent {self.node_id} 处理自我介绍请求失败: {e}")

    async def _handle_all_agents_intro(self, chunk: StreamChunk):
        """处理所有 agent 介绍"""
        try:
            data = chunk.data or {}
            agents = data.get("agents", {})
            
            # 过滤掉自己的介绍
            self.available_agents = {k: v for k, v in agents.items() if k != self.node_id}
            
            self.context.log_info(f"Agent {self.node_id} 收到其他 agent 介绍: {self.available_agents}")
            
        except Exception as e:
            self.context.log_error(f"Agent {self.node_id} 处理其他 agent 介绍失败: {e}")

    async def _handle_route_text(self, chunk: StreamChunk):
        """处理路由文本，基于用户问题和已有转场内容继续生成"""
        try:
            data = chunk.data or {}
            user_query = data.get("user_query", "")
            transition_text = data.get("transition_text", "")

            # 准备格式化变量并调用 LLM
            format_vars = self._prepare_format_vars(
                user_message=user_query,
                transition_text=transition_text,
                user_query=user_query
            )
            
            await self._call_llm_and_stream(format_vars, context_name=f"{self.node_id} 路由继续生成")
            
        except Exception as e:
            self.context.log_error(f"Agent {self.node_id} 处理路由文本失败: {e}")
            await self.emit_chunk("response_text_stream", {"text": ""})
    

