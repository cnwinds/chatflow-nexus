#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""响应模型定义"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Generic, TypeVar

T = TypeVar('T')

class BaseResponse(BaseModel, Generic[T]):
    """基础响应模型"""
    code: int = Field(0, description="响应码，0表示成功")
    message: str = Field("success", description="响应消息")
    data: Optional[T] = Field(None, description="响应数据")

# 认证响应
class LoginResponse(BaseModel):
    token: str = Field(..., description="JWT Token")
    expire: int = Field(..., description="过期时间（秒）")
    user_id: int = Field(..., description="用户ID")

class UserInfo(BaseModel):
    id: int
    user_name: str
    login_name: str
    mobile: Optional[str] = None
    avatar: Optional[str] = None

# Agent响应
class AgentInfo(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    avatar: Optional[str] = None
    gender: int = 0
    device_type: int
    template_id: int
    template_name: Optional[str] = None
    agent_config: Dict[str, Any] = {}
    status: int
    created_at: str
    updated_at: Optional[str] = None

# 会话响应
class SessionInfo(BaseModel):
    session_id: str
    user_id: int
    agent_id: int
    agent_name: str
    title: Optional[str] = None
    created_at: str
    updated_at: str
    message_count: int = 0

class MessageInfo(BaseModel):
    id: int
    session_id: str
    role: str
    content: str
    created_at: str

# OpenAI Chat Completions响应
class ChatCompletionChoice(BaseModel):
    index: int
    message: Dict[str, Any]
    finish_reason: Optional[str] = None

class ChatCompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: Optional[ChatCompletionUsage] = None

class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[Dict[str, Any]]

