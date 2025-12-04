"""
OpeningAgent 节点

负责生成开场白，在会话开始时自动触发。
输入: session_start 事件
输出: opening_text 文本
"""

import sys
from pathlib import Path
from typing import Any, Dict, Optional
import asyncio
from datetime import datetime
import time

# 确保可以导入 src 模块（当从外部项目加载时）
_file_path = Path(__file__).resolve()
_project_root = _file_path.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from stream_workflow.core import Node, ParameterSchema, StreamChunk, register_node
from stream_workflow.core.parameter import FieldSchema

from src.common.utils.llm_chat import LLMChat
from src.common.utils.date_utils import get_current_time, get_lunar_date_str


def calculate_time_context(history_result: Optional[Dict]) -> str:
    """
    根据聊天历史记录计算时间上下文
    
    Args:
        history_result: 聊天历史记录结果
        
    Returns:
        str: 时间上下文描述
    """
    time_context = "这是我们的第一次对话"
    
    if history_result and history_result.get("recent_chats"):
        # 获取最后一条记录的时间
        last_chat = history_result["recent_chats"][-1]  # 最后一条记录
        last_time_str = last_chat.get("created_at")

        if last_time_str:
            try:
                # 解析时间字符串
                last_time = datetime.fromisoformat(last_time_str.replace('Z', '+00:00'))
                current_time = datetime.now()
                
                # 计算时间差
                time_diff = current_time - last_time
                
                # 判断时间段
                def get_time_period(hour):
                    if 6 <= hour < 12:
                        return "上午"
                    elif 12 <= hour < 18:
                        return "下午"
                    elif 18 <= hour < 22:
                        return "晚上"
                    else:
                        return "深夜"
                
                current_period = get_time_period(current_time.hour)
                last_period = get_time_period(last_time.hour)
                
                # 根据时间差生成描述
                if time_diff.days > 0:
                    # 跨天的情况
                    if time_diff.days == 1:
                        time_context = "昨天聊过天"
                    elif time_diff.days < 7:
                        time_context = f"距离上次聊天已经{time_diff.days}天了"
                    elif time_diff.days < 30:
                        weeks = time_diff.days // 7
                        time_context = f"距离上次聊天已经{weeks}周了"
                    else:
                        months = time_diff.days // 30
                        time_context = f"距离上次聊天已经{months}个月了"
                elif current_period != last_period:
                    # 同一天但不同时间段
                    time_context = f"今天{last_period}我们聊过天"
                else:
                    time_context = "刚刚聊过天"
            except Exception as e:
                # 记录错误但不抛出异常，使用默认描述
                time_context = "距离上次聊天已经很久了"
    
    return time_context


@register_node("opening_agent_node")
class OpeningAgentNode(Node):
    """负责生成开场白，在会话开始时自动触发。
    
    功能: 在会话启动时自动生成开场白文本。接收 session_start 事件，调用 LLM 生成个性化的开场白，
    考虑聊天历史记录和时间上下文（如上次聊天时间、时间段等），生成符合场景的问候语。
    支持流式输出，可以实时发送生成的文本给下游节点。可通过用户配置启用或禁用。
    
    配置参数:
    - system_prompt: 系统提示词（必需），用于定义开场白生成的角色和风格。支持 Jinja2 模板语法，
      可使用变量如 has_history、recent_content、time_context、current_time、weekday 等。
    - user_prompt: 用户提示词（必需），用于格式化开场白生成的请求。支持 Jinja2 模板语法，
      可使用变量如 has_history、recent_content、time_context、current_time、weekday 等。
    """
    
    EXECUTION_MODE = "streaming"    # 输入参数定义
    INPUT_PARAMS = {
        "session_start": ParameterSchema(
            is_streaming=True,
            schema={'session_id': 'string'}
        )
    }    # 输出参数定义
    OUTPUT_PARAMS = {
        "opening_text": ParameterSchema(
            is_streaming=True,
            schema={'text': 'string'}
        )
    }
    
    # 配置参数定义（使用 FieldSchema 格式）
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
        })
    }

    async def initialize(self, context):
        self.context = context
        # 初始化 enabled 属性，避免在 on_chunk_received 中访问时出错
        self.enabled = True
    
    async def run(self, context):
        # 从全局上下文获取配置
        self.agent_id = context.get_global_var("agent_id")
        self.session_id = context.get_global_var("session_id")
        self.engine = context.get_global_var("engine")
        self.user_data = context.get_global_var("user_data")

        # 从节点配置获取 prompt 配置
        self.system_prompt = self.get_config("config.system_prompt")
        self.user_prompt = self.get_config("config.user_prompt")
        
        # 验证必需配置
        if not self.system_prompt or not self.user_prompt:
            raise ValueError("OpeningAgent 配置错误：必须提供 config.system_prompt 和 config.user_prompt")

        # 加载配置
        ai_providers = context.get_global_var("ai_providers") or {}
        self._llm_config = ai_providers.get("llm", {})

        # 检查是否启用
        user = context.get_global_var("user")
        if user and hasattr(user, 'config') and user.config:
            try:
                # 通过 ConfigProxy 实时访问配置
                self.enabled = user.config.function_settings.enable_opening_say_hello
            except (AttributeError, TypeError):
                self.enabled = True
        else:
            self.enabled = True
        
        if not self.enabled:
            context.log_info("OpeningAgent: 开场白功能已禁用")
            return

        # 1. 初始化 LLM（会自动加载基础配置）
        self.llm: Optional[LLMChat] = LLMChat()
        self.llm.load_config(self._llm_config)
        
        # 注意：chat_record 在 start_session 时设置，在 on_chunk_received 中获取
        
        await asyncio.sleep(float("inf"))
    
    async def on_chunk_received(self, param_name: str, chunk: StreamChunk):
        if param_name != "session_start":
            return
        
        if not self.enabled:
            # 未启用，发送空文本
            await self.emit_chunk("opening_text", {"text": ""})
            return
        
        try:
            # 在需要时获取 chat_record（此时应该已经通过 start_session 设置）
            chat_record = self.context.get_global_var("chat_record_node")
            if not chat_record:
                self.context.log_warning("chat_record_node 未找到，使用空历史记录")
                history_result = {
                    "status": "success",
                    "recent_chats": [],
                    "total_count": 0
                }
            else:
                history_result = chat_record.get_recent_history_summary(limit=10)
            time_context = calculate_time_context(history_result)

            # 获取角色提示词（其余上下文保持默认）
            char_prompt = self.user_data.get_config("profile.character.prompt") if self.user_data else ""

            format_vars = self._build_format_vars(history_result, time_context, char_prompt or "")
            
            # 使用 engine 提供的 Jinja2 模板渲染提示词
            system_prompt_text = self.engine.render_template(self.system_prompt, **format_vars)
            user_prompt_text = self.engine.render_template(self.user_prompt, **format_vars)

            # 调用 LLM 生成开场白
            messages = [
                {"role": "system", "content": system_prompt_text},
                {"role": "user", "content": user_prompt_text}
            ]
            
            # 流式响应回调：将内容增量发送到输出流
            async def on_delta(chunk_type: str, data: Dict[str, Any]):
                if chunk_type == "content_delta":
                    delta = (data.get("delta") or {}).get("content", "")
                    if delta:
                        await self.emit_chunk("opening_text", {"text": delta})

            # 使用 LLMChat 工具类进行流式调用
            try:
                await self.llm.call_llm_stream(
                    messages=messages,
                    context="OpeningAgent 开场白生成",
                    content_callback=on_delta,
                    session_id=self.session_id,
                    model="primary"
                )
            except Exception as e:
                self.context.log_error(f"开场白生成失败: {e}")
                raise
            finally:
                # 发送空文本表示流结束
                await self.emit_chunk("opening_text", {"text": ""})
            
            # 注意：聊天上下文和持久化保存已由 chat_record_node 通过工作流连接自动处理
            
        except Exception as e:
            # 失败时发送空文本，输出错误日志
            self.context.log_error(f"OpeningAgent 开场白生成失败: {e}")
            await self.emit_chunk("opening_text", {"text": ""})

    def _build_format_vars(self, history_result: Dict[str, Any], time_context: str, char_prompt: str) -> Dict[str, Any]:
        """根据提示模板要求准备格式化变量。"""
        history = history_result or {}
        recent_chats = history.get("recent_chats", [])
        total_count = history.get("total_count", 0)

        child_name = ""
        child_age = 5.0
        child_birthday = ""
        long_term_memory = None
        guidance_topic = None
        guidance_strategy = None

        if self.user_data:
            child_name = self.user_data.get_config("profile.child_info.name") or ""
            child_age = self.user_data.get_config("profile.child_info._age") or 5.0
            child_birthday = self.user_data.get_config("profile.child_info.birth_date") or ""
            long_term_memory = self.user_data.get_memory("chat.long_term_memory") or None
            guidance_topic = self.user_data.get_config("guidance.topic") or None
            guidance_strategy = self.user_data.get_config("guidance.strategy") or None

        weekday_map = {
            "Monday": "星期一",
            "Tuesday": "星期二",
            "Wednesday": "星期三",
            "Thursday": "星期四",
            "Friday": "星期五",
            "Saturday": "星期六",
            "Sunday": "星期日",
        }
        weekday = weekday_map.get(time.strftime("%A"), time.strftime("%A"))

        now = datetime.now()
        return {
            "has_history": total_count > 0,
            "recent_content": "\n".join([f"{chat.get('role')}: {chat.get('content')}" for chat in recent_chats]),
            "time_context": time_context,
            "current_time": get_current_time(now),  # 公历时间
            "lunar_date": get_lunar_date_str(now),  # 农历日期（可选）
            "weekday": weekday,
            "prompt": char_prompt,
            "character_prompt": char_prompt,
            "child_name": child_name,
            "child_age": child_age,
            "child_birthday": child_birthday,
            "long_term_memory": long_term_memory,
            "guidance_topic": guidance_topic,
            "guidance_strategy": guidance_strategy,
        }
