#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""WebSocket消息模型定义"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Literal


# ==================== Hello消息 ====================

class AudioParams(BaseModel):
    """音频参数"""
    format: str = Field(..., description="音频格式，如opus")
    sample_rate: int = Field(..., description="采样率")
    channels: int = Field(..., description="通道数")
    frame_duration: int = Field(..., description="帧长（毫秒）")


class HelloRequest(BaseModel):
    """客户端Hello请求"""
    type: Literal["hello"] = "hello"
    version: int = Field(..., description="协议版本")
    transport: str = Field(..., description="传输方式")
    features: Optional[Dict[str, Any]] = Field(None, description="支持的特性")
    audio_params: Optional[AudioParams] = Field(None, description="音频参数")


class HelloResponse(BaseModel):
    """服务端Hello响应"""
    type: Literal["hello"] = "hello"
    transport: str = Field(..., description="传输方式")
    audio_params: Optional[AudioParams] = Field(None, description="音频参数")


# ==================== Listen消息 ====================

class ListenMessage(BaseModel):
    """语音监听消息"""
    session_id: Optional[str] = Field(None, description="会话ID")
    type: Literal["listen"] = "listen"
    state: Literal["start", "stop", "detect"] = Field(..., description="监听状态")
    mode: Optional[Literal["auto", "manual", "realtime"]] = Field(None, description="监听模式，仅在state=start时使用")
    text: Optional[str] = Field(None, description="唤醒词，仅在state=detect时使用")
    agent_id: Optional[int] = Field(None, description="Agent ID")


# ==================== Text消息 ====================

class TextMessage(BaseModel):
    """文本消息"""
    session_id: Optional[str] = Field(None, description="会话ID")
    type: Literal["text"] = "text"
    content: str = Field(..., description="文本内容")
    agent_id: Optional[int] = Field(None, description="Agent ID")


# ==================== TTS消息 ====================

class TTSMessage(BaseModel):
    """TTS状态消息（服务端发送）"""
    type: Literal["tts"] = "tts"
    state: Literal["start", "stop", "sentence_start"] = Field(..., description="TTS状态")
    text: Optional[str] = Field(None, description="文本内容，仅在sentence_start时携带")


# ==================== LLM消息 ====================

class LLMMessage(BaseModel):
    """LLM响应消息（服务端发送）"""
    type: Literal["llm"] = "llm"
    content: Optional[str] = Field(None, description="文本内容")
    emotion: Optional[str] = Field(None, description="情感类型")
    finished: Optional[bool] = Field(False, description="是否完成")


# ==================== Abort消息 ====================

class AbortMessage(BaseModel):
    """中止消息"""
    session_id: Optional[str] = Field(None, description="会话ID")
    type: Literal["abort"] = "abort"
    reason: Optional[str] = Field(None, description="中止原因")


# ==================== MCP消息 ====================

class MCPMessage(BaseModel):
    """MCP协议消息"""
    session_id: Optional[str] = Field(None, description="会话ID")
    type: Literal["mcp"] = "mcp"
    payload: Dict[str, Any] = Field(..., description="MCP Payload")


# ==================== Error消息 ====================

class ErrorMessage(BaseModel):
    """错误消息（服务端发送）"""
    type: Literal["error"] = "error"
    code: int = Field(..., description="错误码")
    message: str = Field(..., description="错误消息")
    details: Optional[Dict[str, Any]] = Field(None, description="错误详情")

