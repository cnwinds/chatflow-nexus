"""
聊天记录上下文管理
"""
import logging
from typing import Any, Dict, List, Optional


class ChatRecordContext:
    """聊天记录上下文管理类"""
    
    def __init__(self, logger: logging.Logger = None):
        self._chat_context: List[Dict[str, Any]] = []
        self.logger = logger or logging.getLogger(__name__)
    
    def add_chat_context(self, role: str, content: str, **kwargs):
        """添加聊天上下文"""
        if not content or not content.strip():
            return
        
        message = {"role": role, "content": content.strip()}
        message.update({k: v for k, v in kwargs.items() if v is not None})
        
        self._chat_context.append(message)
    
    def sync_history_to_context(self, chat_history: List[Dict[str, Any]]):
        """同步历史到上下文"""
        self._chat_context.clear()
        
        for msg in chat_history:
            context_msg = {
                "role": msg.get("role"),
                "content": msg.get("content", "")
            }
            if msg.get("is_compressed"):
                context_msg["is_compressed"] = True
            
            self._chat_context.append(context_msg)
        
        self.logger.debug(f"已同步 {len(self._chat_context)} 条消息到上下文")
    
    def get_chat_messages(
        self,
        system_prompt: Optional[str] = None,
        user_prompt: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """构建 OpenAI 格式的消息列表"""
        messages = []
        
        # 复制上下文（排除最后一条用户消息）
        context = self._chat_context.copy()
        if context and context[-1].get("role") == "user":
            context = context[:-1]
        
        # 分离压缩和非压缩消息
        compressed_parts = []
        normal_messages = []
        
        for msg in context:
            if msg.get("is_compressed"):
                content = msg.get("content", "").strip()
                if content:
                    compressed_parts.append(content)
            else:
                normal_messages.append(msg)
        
        # 构建 system prompt
        if system_prompt and system_prompt.strip():
            final_system = system_prompt.strip()
            if compressed_parts:
                summary = "\n\n".join(compressed_parts)
                final_system = f"{final_system}\n\n## 历史对话摘要\n{summary}"
            
            messages.append({"role": "system", "content": final_system})
        
        # 添加正常消息
        messages.extend(normal_messages)
        
        # 添加当前用户消息
        if user_prompt and user_prompt.strip():
            messages.append({"role": "user", "content": user_prompt.strip()})
        
        self.logger.debug(f"构建消息: {len(messages)} 条 (包含 {len(compressed_parts)} 条压缩)")
        return messages
    
    def clear_chat_context(self):
        """清空上下文"""
        self._chat_context.clear()
    
    def get_context_count(self) -> int:
        """获取上下文消息数量"""
        return len(self._chat_context)









