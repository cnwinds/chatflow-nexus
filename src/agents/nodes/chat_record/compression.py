"""
聊天记录压缩逻辑
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.agents.utcp_tools import call_utcp_tool
from src.common.utils.llm_stream_utils import estimate_tokens_from_messages
from .utils import format_time


class ChatRecordCompression:
    """聊天记录压缩处理类"""
    
    def __init__(
        self,
        engine: Any,
        ai_providers: Dict[str, Any],
        compress_system_prompt: str,
        compress_user_prompt: str,
        compress_token_threshold: int,
        keep_last_rounds: int,
        memory_max_length: int = 4000,
        logger: logging.Logger = None
    ):
        self.engine = engine
        self.ai_providers = ai_providers
        self.compress_system_prompt = compress_system_prompt
        self.compress_user_prompt = compress_user_prompt
        self.compress_token_threshold = compress_token_threshold
        self.keep_last_rounds = keep_last_rounds
        self.memory_max_length = memory_max_length
        self.logger = logger or logging.getLogger(__name__)
        self._is_compressing = False
    
    def check_and_compress(self, chat_history: List[Dict[str, Any]]) -> bool:
        """检查是否需要压缩，返回是否需要压缩"""
        if self._is_compressing:
            return False
        
        token_count = estimate_tokens_from_messages(chat_history)
        if token_count > self.compress_token_threshold:
            self.logger.info(f"Token 超过阈值 ({token_count} > {self.compress_token_threshold})，触发压缩")
            return True
        return False
    
    def is_compressing(self) -> bool:
        """是否正在压缩"""
        return self._is_compressing
    
    def set_compressing(self, value: bool):
        """设置压缩状态"""
        self._is_compressing = value
    
    def find_keep_start_index(self, chat_history: List[Dict[str, Any]]) -> Optional[int]:
        """找到需要保留的消息起点（最后 N 轮的第一条 user 消息）"""
        rounds = self.keep_last_rounds
        if len(chat_history) < 2 * rounds:
            return None
        
        last_idx = len(chat_history) - 1
        
        # 验证最后一条是 assistant
        if chat_history[last_idx].get("role") != "assistant":
            return None
        
        # 计算第一轮 user 索引
        first_user_idx = last_idx - (2 * rounds - 1)
        if first_user_idx < 0:
            return None
        
        # 验证完整性
        for i in range(rounds):
            user_idx = first_user_idx + i * 2
            assistant_idx = user_idx + 1
            
            if (user_idx >= len(chat_history) or 
                assistant_idx >= len(chat_history)):
                return None
            
            if (chat_history[user_idx].get("role") != "user" or 
                chat_history[assistant_idx].get("role") != "assistant"):
                return None
        
        return first_user_idx
    
    async def compress_messages(self, messages: List[Dict[str, Any]]) -> Optional[str]:
        """调用 LLM 压缩消息"""
        if not self.compress_system_prompt or not self.compress_user_prompt:
            self.logger.warning("压缩提示词未配置")
            return None
        
        return await self._call_llm(
            self.compress_system_prompt,
            self.compress_user_prompt,
            messages
        )
    
    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        messages: List[Dict[str, Any]],
        max_tokens: int = 2000,
        temperature: float = 1.0
    ) -> Optional[str]:
        """通用 LLM 调用"""
        try:
            service, model = self._get_llm_service()
            if not service:
                return None
            
            # 渲染提示词
            vars = self._build_prompt_vars(messages)
            system_text = self.engine.render_template(system_prompt, **vars)
            user_text = self.engine.render_template(user_prompt, **vars)
            
            # 调用 LLM
            result = await call_utcp_tool(f"{service}.chat_completion", {
                "messages": [
                    {"role": "system", "content": system_text},
                    {"role": "user", "content": user_text}
                ],
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": 1.0
            })
            
            return (result or {}).get("content", "").strip() or None
        except Exception as e:
            self.logger.error(f"LLM 调用异常: {e}", exc_info=True)
            return None
    
    def _build_prompt_vars(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """构建提示词变量"""
        return {
            "messages": "\n".join([f"{m['role']}: {m['content']}" for m in messages]),
            "message_count": len(messages),
            "memory_max_length": self.memory_max_length
        }
    
    def _get_llm_service(self) -> Tuple[str, str]:
        """获取 LLM 服务配置"""
        try:
            llm_config = self.ai_providers.get("llm", {})
            model_config = llm_config.get("primary")
            
            if not model_config:
                return ("", "")
            
            if "." in model_config:
                parts = model_config.split(".", 1)
                return (parts[0], parts[1])
            else:
                return (model_config, "primary")
        except Exception:
            return ("", "")

