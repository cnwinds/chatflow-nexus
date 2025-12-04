#!/usr/bin/env python3
"""
LLM 流式响应处理工具

提供通用的 OpenAI 流式响应处理函数，简化 LLM 服务的流式响应处理逻辑。
"""

import logging
import json
from typing import Dict, Any, List, Optional, AsyncIterator, TYPE_CHECKING

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionChunk
else:
    ChatCompletionChunk = Any  # type: ignore

logger = logging.getLogger(__name__)


def estimate_tokens_from_messages(messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> int:
    """
    基于消息列表和工具列表估算输入token数量
    
    Args:
        messages: 消息列表
        tools: 工具列表（可选）
        
    Returns:
        估算的token数量
    """
    total_chars = 0
    
    # 计算消息内容
    for message in messages:
        # 计算角色名称长度
        role = message.get("role", "")
        total_chars += len(role)
        
        # 计算内容长度
        content = message.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        
        # 计算工具调用长度（如果有）
        tool_calls = message.get("tool_calls", [])
        for tool_call in tool_calls:
            tool_call_str = json.dumps(tool_call, ensure_ascii=False)
            total_chars += len(tool_call_str)
    
    # 计算工具定义长度（如果有）
    if tools:
        for tool in tools:
            tool_str = json.dumps(tool, ensure_ascii=False)
            total_chars += len(tool_str)
    
    # 估算token数量（大约4个字符=1个token）
    estimated_tokens = max(1, total_chars // 4)
    return estimated_tokens


def estimate_tokens_from_text(text: str) -> int:
    """
    基于文本估算输出token数量
    
    Args:
        text: 文本内容
        
    Returns:
        估算的token数量
    """
    if not text:
        return 0
    
    # 估算token数量（大约4个字符=1个token）
    estimated_tokens = max(1, len(text) // 4)
    return estimated_tokens


def create_default_token_estimator() -> callable:
    """
    创建默认的token估算函数，用于 process_openai_stream
    
    Returns:
        一个函数，接受 (messages_or_none, tools_or_none, text) 参数
    """
    def estimate_tokens(messages_or_none: Optional[List[Dict[str, Any]]], 
                       tools_or_none: Optional[List[Dict[str, Any]]], 
                       text: Optional[str] = None) -> int:
        """统一的 token 估算函数"""
        if text is not None:
            # 估算文本的 token
            return estimate_tokens_from_text(text)
        elif messages_or_none is not None:
            # 估算消息的 token
            return estimate_tokens_from_messages(messages_or_none, tools_or_none)
        else:
            return 0
    
    return estimate_tokens


async def process_openai_stream(
    stream: AsyncIterator[ChatCompletionChunk],
    resolved_model: str,
    request_model: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    estimate_tokens_func: Optional[callable] = None
) -> AsyncIterator[Dict[str, Any]]:
    """
    处理 OpenAI 兼容的流式响应，转换为标准化的流式数据格式
    
    Args:
        stream: OpenAI 流式响应迭代器
        resolved_model: 解析后的模型名称
        request_model: 请求的模型名称（可能是别名）
        messages: 消息列表（用于估算 token）
        tools: 工具列表（用于估算 token）
        estimate_tokens_func: 可选的 token 估算函数，接收 (messages, tools, text) 参数
        
    Yields:
        标准化的流式响应数据字典，包含以下类型：
        - "content_delta": 内容增量
        - "tool_calls_delta": 工具调用增量
        - "completion": 完成信息
        - "error": 错误信息
    """
    full_content = ""
    tool_calls = []
    usage_info = None
    
    try:
        async for chunk in stream:
            if not chunk.choices or not chunk.choices[0].delta:
                # 处理使用信息（可能在任何chunk中）
                if hasattr(chunk, 'usage') and chunk.usage:
                    usage_info = {
                        "prompt_tokens": chunk.usage.prompt_tokens,
                        "completion_tokens": chunk.usage.completion_tokens,
                        "total_tokens": chunk.usage.total_tokens
                    }
                continue
            
            delta = chunk.choices[0].delta
            chunk_data = {
                "type": "content_delta",
                "delta": {},
                "used_model": resolved_model,
                "request_model": request_model
            }
            
            # 处理内容增量
            if delta.content:
                content_chunk = delta.content
                full_content += content_chunk
                chunk_data["delta"]["content"] = content_chunk
                chunk_data["full_content"] = full_content
            
            # 处理工具调用增量
            if delta.tool_calls:
                chunk_data["type"] = "tool_calls_delta"
                chunk_data["delta"]["tool_calls"] = []
                
                for tool_call in delta.tool_calls:
                    if tool_call.index is not None:
                        # 确保tool_calls列表足够长
                        while len(tool_calls) <= tool_call.index:
                            tool_calls.append({})
                        
                        tool_call_data = {"index": tool_call.index}
                        
                        # 更新工具调用信息
                        if tool_call.id:
                            tool_calls[tool_call.index]["id"] = tool_call.id
                            tool_call_data["id"] = tool_call.id
                        if tool_call.type:
                            tool_calls[tool_call.index]["type"] = tool_call.type
                            tool_call_data["type"] = tool_call.type
                        if tool_call.function:
                            if "function" not in tool_calls[tool_call.index]:
                                tool_calls[tool_call.index]["function"] = {}
                            if tool_call.function.name:
                                tool_calls[tool_call.index]["function"]["name"] = tool_call.function.name
                                tool_call_data["function"] = {"name": tool_call.function.name}
                            if tool_call.function.arguments:
                                current_args = tool_calls[tool_call.index]["function"].get("arguments", "")
                                tool_calls[tool_call.index]["function"]["arguments"] = current_args + tool_call.function.arguments
                                if "function" not in tool_call_data:
                                    tool_call_data["function"] = {}
                                tool_call_data["function"]["arguments"] = tool_call.function.arguments
                        
                        chunk_data["delta"]["tool_calls"].append(tool_call_data)
            
            # 处理使用信息（可能在任何chunk中）
            if hasattr(chunk, 'usage') and chunk.usage:
                usage_info = {
                    "prompt_tokens": chunk.usage.prompt_tokens,
                    "completion_tokens": chunk.usage.completion_tokens,
                    "total_tokens": chunk.usage.total_tokens
                }
            
            # 只有当有实际内容时才yield
            if chunk_data["delta"]:
                yield chunk_data
        
        # 如果没有获取到usage信息，使用估算函数
        if usage_info is None:
            try:
                if estimate_tokens_func:
                    # 使用提供的估算函数
                    estimated_prompt_tokens = estimate_tokens_func(messages, tools, None)
                    estimated_completion_tokens = estimate_tokens_func(None, None, full_content)
                else:
                    # 使用默认的估算函数
                    estimated_prompt_tokens = estimate_tokens_from_messages(messages, tools)
                    estimated_completion_tokens = estimate_tokens_from_text(full_content)
                
                usage_info = {
                    "prompt_tokens": estimated_prompt_tokens,
                    "completion_tokens": estimated_completion_tokens,
                    "total_tokens": estimated_prompt_tokens + estimated_completion_tokens
                }
            except Exception as e:
                logger.warning(f"Token估算失败: {e}")
        
        # 发送最终完成信息
        yield {
            "type": "completion",
            "content": full_content,
            "tool_calls": tool_calls if tool_calls else None,
            "usage": usage_info,
            "used_model": resolved_model,
            "request_model": request_model
        }
        
    except Exception as e:
        logger.error(f"流式响应处理错误: {e}")
        yield {
            "type": "error",
            "error": str(e)
        }

