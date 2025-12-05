"""
打断控制器节点

职责:
- 在 AI 说话期间监听 ASR 最终文本, 判定是立即打断、忽略, 还是等全段播放完成后再处理。
- 以全段边界(等待 tts_status:stop)为准, 统一排队与下发。

输入:
- recognized_text: ASR识别流(仅处理 is_final=True 的段落)
- tts_status: TTS状态通知 (state: "start" | "stop" | "sentence_start" | "sentence_end")
- sentence_stream: AI回答的完整句子流（来自 post_route_node.sentence_stream）

输出:
- interrupt_signal: 空消息 -> 连接到 tts_node.interrupt
- routed_user_text: 需要进入对话流的用户文本
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import asyncio
import time
import json
import jinja2

# 确保可以导入 src 模块（当从外部项目加载时）
_file_path = Path(__file__).resolve()
_project_root = _file_path.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from stream_workflow.core import Node, ParameterSchema, StreamChunk, register_node
from stream_workflow.core.parameter import FieldSchema
from src.agents.utcp_tools import call_utcp_tool
from src.common.logging import get_logger


@register_node("interrupt_controller_node")
class InterruptControllerNode(Node):
    """负责在 AI 说话期间监听 ASR 最终文本，判定是立即打断、忽略，还是等全段播放完成后再处理。
    
    功能: 智能打断控制器，在 AI 说话期间监听用户语音识别结果，使用 LLM 进行意图分类，判断用户是否想要打断 AI。
    支持三种处理策略：interrupt（立即打断并处理用户输入）、ignore（忽略用户输入）、wait（等待当前段落播放完成后再处理）。
    具备限流机制，防止频繁打断，支持等待队列管理，确保用户输入不会丢失。
    
    配置参数:
    - system_prompt: 系统提示词（必需），用于定义打断意图分类的角色和判断标准。支持 Jinja2 模板语法，
      可使用变量如 user_text、user_question、ai_response、ai_current_sentence、asr_confidence 等。
    - user_prompt: 用户提示词（必需），用于格式化意图分类请求，包含用户输入和对话上下文。支持 Jinja2 模板语法，
      可使用变量如 user_text、user_question、ai_response、ai_current_sentence、asr_confidence 等。
    
    注意: 打断策略的具体参数（如启用状态、最小置信度、队列长度、超时时间等）从用户配置中加载，不在节点配置中设置。
    """
    
    EXECUTION_MODE = "streaming"

    INPUT_PARAMS = {
        # 对齐 STT 节点输出: recognized_text
        # schema: {"text": "string", "confidence": "float", "audio_file_path": "string", "emotion": "string"}
        "recognized_text": ParameterSchema(is_streaming=True, schema={"text": "string", "confidence": "float", "audio_file_path": "string", "emotion": "string"}),
        # 订阅 TTS 状态通知 (来自 tts_node 输出)
        "tts_status": ParameterSchema(is_streaming=True, schema={"state": "string", "text": "string"}),
        # AI回答的完整句子流（来自 post_route_node.sentence_stream）
        "sentence_stream": ParameterSchema(is_streaming=True, schema={"text": "string"}),
    }

    OUTPUT_PARAMS = {
        # 发送给 tts_node.interrupt 的信号
        "interrupt_signal": ParameterSchema(is_streaming=True, schema={}),
        # 送往对话/LLM 的用户文本(对齐 route.user_text)
        "routed_user_text": ParameterSchema(
            is_streaming=True,
            schema={
                "text": "string",
                "confidence": "float",
                "audio_file_path": "string",
                "emotion": "string",
            }
        ),
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

    async def run(self, context):
        self._logger = get_logger(__name__)

        # 从全局上下文获取 agent_id（用于日志标识）
        self._agent_id = context.get_global_var("agent_id") or "unknown"

        # 加载配置
        self._ai_providers = context.get_global_var("ai_providers") or {}

        # 策略配置(带默认值)
        policy = context.get_global_var("user.config.function_settings.interrupt_policy") or {}
        self._enabled: bool = bool(policy.get("enabled", True))
        self._min_confidence: float = float(policy.get("min_confidence", 0.5))
        self._max_queue_len: int = int(policy.get("max_queue_len", 8))
        self._queue_timeout_sec: float = float(policy.get("queue_timeout_sec", 10.0))
        self._min_interrupt_interval_sec: float = float(policy.get("min_interrupt_interval_sec", 0.8))

        # 运行状态
        self._is_tts_active: bool = False
        self._pending_queue: List[Dict[str, Any]] = []  # FIFO
        self._last_interrupt_ts: float = 0.0
        # 跟踪AI说话上下文
        self._current_ai_sentence: str = ""
        self._previous_ai_sentence: str = ""
        # 跟踪完整对话内容
        self._last_user_question: str = ""  # 最近一次完整的用户提问
        self._current_ai_response: str = ""  # 当前正在播放的完整AI回答（累积所有句子）

        # 从节点配置获取 prompt 配置
        self._system_prompt = self.get_config("config.system_prompt")
        self._user_prompt = self.get_config("config.user_prompt")
        
        context.log_info("InterruptController 初始化完成")
        await asyncio.sleep(float("inf"))

    async def shutdown(self):
        """清理节点资源"""
        # 清空等待队列
        if hasattr(self, '_pending_queue'):
            self._pending_queue.clear()
        
        # 重置状态
        if hasattr(self, '_is_tts_active'):
            self._is_tts_active = False
        if hasattr(self, '_current_ai_sentence'):
            self._current_ai_sentence = ""
        if hasattr(self, '_previous_ai_sentence'):
            self._previous_ai_sentence = ""
        if hasattr(self, '_last_user_question'):
            self._last_user_question = ""
        if hasattr(self, '_current_ai_response'):
            self._current_ai_response = ""

    async def on_chunk_received(self, param_name: str, chunk: StreamChunk):
        if not self._enabled:
            return

        if param_name == "tts_status":
            data = chunk.data or {}
            state = data.get("state", "")
            
            if state == "start":
                self._logger.info(f"[agent_id={self._agent_id}] 收到 tts_status:start, 标记 is_tts_active=True")
                self._is_tts_active = True
                # 开始新的AI回答，重置当前回答内容
                self._current_ai_response = ""
                return
            
            elif state == "stop":
                self._logger.info(f"[agent_id={self._agent_id}] 收到 tts_status:stop, 标记 is_tts_active=False 并下发队列")
                self._is_tts_active = False
                # 段落结束, 统一下发队列
                await self._drain_pending_queue()
                return
            
            elif state == "sentence_start":
                # 更新当前/上一句AI说话文本（用于跟踪当前正在播放的句子）
                s_text = (data.get("text") or "").strip()
                self._logger.info(f"[agent_id={self._agent_id}] 收到 tts_status:sentence_start, 句子文本: {s_text}")
                if s_text:
                    self._previous_ai_sentence = self._current_ai_sentence
                    self._current_ai_sentence = s_text
                return
            
            # sentence_end 状态不需要特殊处理
            return

        if param_name == "sentence_stream":
            # 从 post_route_node 接收完整句子，累积到当前AI回答中
            data = chunk.data or {}
            s_text = (data.get("text") or "").strip()
            if s_text:
                # 累积到当前AI回答中
                if self._current_ai_response:
                    self._current_ai_response += " " + s_text
                else:
                    self._current_ai_response = s_text
            return

        if param_name == "recognized_text":
            data = chunk.data or {}
            text = (data.get("text") or "").strip()
            confidence = float(data.get("confidence") or 0.0)
            # recognized_text 即为最终结果
            if not text:
                return
            audio_file_path = data.get("audio_file_path") or ""
            emotion = data.get("emotion") or "neutral"

            # TTS 未在说话, 直接透传
            if not self._is_tts_active:
                self._logger.info(f"[agent_id={self._agent_id}] TTS空闲, 直通用户文本: {text}")
                # 保存为最近一次完整的用户提问
                self._last_user_question = text
                await self.emit_chunk(
                    "routed_user_text",
                    {
                        "text": text,
                        "confidence": confidence,
                        "audio_file_path": audio_file_path,
                        "emotion": emotion,
                    },
                )
                return

            # TTS 在说话, 做意图分类（携带完整的对话上下文）
            result = await self._safe_classify(text, confidence, {
                "user_question": self._last_user_question,  # 用户最近一次完整的提问
                "ai_response": self._current_ai_response,  # AI当前正在播放的完整回答
                "ai_current_sentence": self._current_ai_sentence,  # 当前正在播放的句子
            })
            label = result.get("label")
            score = result.get("score")
            self._logger.info(f"[agent_id={self._agent_id}] 分类结果 label={label} score={score} text={text}")

            if label == "interrupt":
                if self._can_interrupt_now():
                    self._logger.info(f"[agent_id={self._agent_id}] 触发中断: 发出 interrupt_signal 并直送用户话语")
                    await self.emit_chunk("interrupt_signal", {})
                    self._last_interrupt_ts = time.time()
                    # 立即将该用户文本送往对话层
                    await self.emit_chunk(
                        "routed_user_text",
                        {
                            "text": text,
                            "confidence": confidence,
                            "audio_file_path": audio_file_path,
                            "emotion": emotion,
                        },
                    )
                else:
                    # 限流命中, 降级为 wait 策略
                    self._logger.debug("中断限流命中, 降级入队等待")
                    self._enqueue_wait(text, confidence, audio_file_path, emotion)
            elif label == "ignore":
                # 丢弃
                self._logger.debug("分类为 ignore, 丢弃该文本")
                return
            else:
                # wait 默认入队
                self._logger.debug("分类为 wait, 入队等待段落结束")
                self._enqueue_wait(text, confidence, audio_file_path, emotion)

    async def _safe_classify(self, text: str, confidence: float, context_info: Dict[str, Any]) -> Dict[str, Any]:
        """使用 LLM 进行意图分类，如果模型不可用则返回 wait"""
        try:
            llm_result = await self._classify_with_llm(text, confidence, context_info)
            if llm_result and llm_result.get("label") in ("interrupt", "ignore", "wait"):
                return llm_result
        except Exception as e:
            self._logger.warning(f"分类器异常, 默认wait: {e}")
        
        # 模型不可用或返回无效结果，返回 wait
        return {"label": "wait", "score": 0.0}
    
    async def _classify_with_llm(self, user_text: str, confidence: float, context: Dict[str, Any]) -> Dict[str, Any]:
        """调用 LLM 进行意图分类，严格返回 {label, score}。失败抛异常或返回空。"""
        service_name, model_name = self._get_llm_completion_service("primary")
        if not service_name:
            return {}
        
        # 检查是否配置了 prompt
        if not self._system_prompt or not self._user_prompt:
            return {}
        
        # 提取完整的对话上下文
        user_question = context.get("user_question") or ""
        ai_response = context.get("ai_response") or ""
        ai_current_sentence = context.get("ai_current_sentence") or ""

        # 准备格式化变量
        format_vars = {
            "user_text": user_text,
            "user_question": user_question,
            "ai_response": ai_response,
            "ai_current_sentence": ai_current_sentence,
            "asr_confidence": confidence if confidence is not None else 1.0,
        }
        
        # 使用 Jinja2 模板渲染提示词
        system_prompt_text = self.engine.render_template(self._system_prompt, **format_vars)
        user_prompt_text = self.engine.render_template(self._user_prompt, **format_vars)
        
        messages = [
            {"role": "system", "content": system_prompt_text},
            {"role": "user", "content": user_prompt_text},
        ]
        params = {
            "messages": messages,
            "model": model_name,
            "max_tokens": 64,
            "temperature": 1.0,
            "top_p": 1.0,
        }
        resp = await call_utcp_tool(f"{service_name}.chat_completion", params)
        content = (resp or {}).get("content", "").strip()
        try:
            parsed = json.loads(content)
            label = parsed.get("label")
            score = float(parsed.get("score", 0))
            if label in ("interrupt", "ignore", "wait"):
                # 轻度规范化分数
                score = max(0.0, min(1.0, score))
                return {"label": label, "score": score}
        except Exception:
            # 如果模型未按JSON返回，做一次简易解析
            lowered = content.lower()
            for lab in ("interrupt", "ignore", "wait"):
                if lab in lowered:
                    return {"label": lab, "score": 0.65}
        return {}
    
    def _get_llm_completion_service(self, model_key: str = "primary") -> tuple[str, str]:
        """
        从全局变量 ai_providers 读取配置，返回服务名和模型名。
        
        Args:
            model_key: 模型配置key，如 "primary" 或 "fast"
        
        Returns:
            (service_name, model_name) 元组，如 ("azure_llm", "primary")
        """
        try:
            llm_cfg = self._ai_providers.get("llm", {})
            model_config = llm_cfg.get(model_key)
            # 解析配置，格式如 "azure_llm.primary" 或 "azure_llm"
            if "." in model_config:
                parts = model_config.split(".", 1)
                service_name = parts[0]
                model_name = parts[1]
            else:
                service_name = model_config
                model_name = model_key
            
            return (service_name, model_name)
        except Exception:
            return ("azure_llm", "primary")
    
    def _can_interrupt_now(self) -> bool:
        now = time.time()
        return (now - self._last_interrupt_ts) >= self._min_interrupt_interval_sec

    def _enqueue_wait(self, text: str, confidence: float, audio_file_path: str, emotion: str):
        # 超长则丢弃最早
        if len(self._pending_queue) >= self._max_queue_len:
            try:
                self._logger.warning("等待队列溢出, 丢弃最早项")
                self._pending_queue.pop(0)
            except Exception:
                self._pending_queue.clear()
        self._pending_queue.append({
            "text": text,
            "confidence": confidence,
            "ts": time.time(),
            "audio_file_path": audio_file_path,
            "emotion": emotion,
        })

    async def _drain_pending_queue(self):
        if not self._pending_queue:
            self._logger.debug("等待队列为空, 无需下发")
            return
        now = time.time()
        deliver_items: List[Dict[str, Any]] = []
        # 过滤过期, 保序
        for item in self._pending_queue:
            if (now - float(item.get("ts", now))) <= self._queue_timeout_sec:
                deliver_items.append(item)

        self._pending_queue.clear()

        # 只发送最后一条消息
        if deliver_items:
            last_item = deliver_items[-1]
            self._logger.info(f"[agent_id={self._agent_id}] 下发等待队列的最后一条消息（共{len(deliver_items)}条）")
            await self.emit_chunk(
                "routed_user_text",
                {
                    "text": last_item.get("text", ""),
                    "confidence": last_item.get("confidence", 0.0),
                    "audio_file_path": last_item.get("audio_file_path", ""),
                    "emotion": last_item.get("emotion", "neutral"),
                },
            )
