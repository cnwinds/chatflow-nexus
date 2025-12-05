"""
聊天记录工具方法
"""
from src.common.logging import get_logger
from typing import Any, Dict, List
from datetime import datetime


def format_time(time_value: Any) -> str:
    """格式化时间"""
    if hasattr(time_value, 'isoformat'):
        return time_value.isoformat()
    elif isinstance(time_value, str):
        return time_value
    else:
        return str(time_value)


def create_message(role: str, content: str, emotion: str = "", audio_path: str = "") -> Dict[str, Any]:
    """创建消息对象"""
    message = {
        "role": role,
        "content": content,
        "created_at": datetime.now().isoformat()
    }
    
    if role == "user":
        if emotion:
            message["emotion"] = emotion
        if audio_path:
            message["audio_file_path"] = audio_path
    
    return message


def merge_consecutive_messages(chat_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """合并连续相同角色的消息"""
    if not chat_history:
        return []
    
    merged = []
    i = 0
    
    while i < len(chat_history):
        current = chat_history[i].copy()
        role = current.get("role")
        
        # 收集相同角色的连续消息
        contents = [current.get("content", "")]
        j = i + 1
        
        while j < len(chat_history) and chat_history[j].get("role") == role:
            contents.append(chat_history[j].get("content", ""))
            j += 1
        
        # 合并内容
        if len(contents) > 1:
            current["content"] = "\n".join(filter(None, contents))
            current["created_at"] = chat_history[j - 1].get("created_at", current["created_at"])
        
        merged.append(current)
        i = j
    
    # 验证交替模式
    verify_alternation(merged)
    return merged


def verify_alternation(history: List[Dict[str, Any]]):
    """验证消息交替模式"""
    logger = get_logger(__name__)
    
    prev_role = None
    for i, msg in enumerate(history):
        role = msg.get("role")
        if role == "system":
            continue
        
        if prev_role and prev_role == role:
            logger.warning(f"位置 {i-1} 和 {i} 存在连续的 {role} 消息")
        
        prev_role = role









