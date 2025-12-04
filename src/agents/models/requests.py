#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""请求模型定义"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal

# 认证相关
class LoginRequest(BaseModel):
    login_name: str = Field(..., description="登录名（手机号/邮箱/用户名）")
    password: str = Field(..., description="密码")

class RegisterRequest(BaseModel):
    user_name: str = Field(..., description="用户名")
    login_name: str = Field(..., description="登录名")
    password: str = Field(..., description="密码")
    mobile: Optional[str] = Field(None, description="手机号")
    login_type: int = Field(1, description="登录类型")

# Agent相关
class CreateAgentRequest(BaseModel):
    name: str = Field(..., description="Agent名称")
    description: Optional[str] = Field(None, description="描述")
    template_id: int = Field(..., description="模板ID")
    device_type: int = Field(1, description="设备类型")
    agent_config: Optional[Dict[str, Any]] = Field(None, description="Agent配置")

class UpdateAgentRequest(BaseModel):
    name: Optional[str] = Field(None, description="Agent名称")
    description: Optional[str] = Field(None, description="描述")
    agent_config: Optional[Dict[str, Any]] = Field(None, description="Agent配置")

# 会话相关
class CreateSessionRequest(BaseModel):
    agent_id: int = Field(..., description="Agent ID")
    title: Optional[str] = Field(None, description="会话标题")

# OpenAI Chat Completions请求
class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "function"]
    content: str
    name: Optional[str] = None

class ChatCompletionRequest(BaseModel):
    model: str = Field(..., description="模型名称，格式：agent-{agent_id}")
    messages: List[ChatMessage] = Field(..., description="消息列表")
    stream: bool = Field(False, description="是否流式输出")
    temperature: Optional[float] = Field(1.0, description="温度参数")
    max_tokens: Optional[int] = Field(None, description="最大token数")
    session_id: Optional[str] = Field(None, description="会话ID，不传则创建新会话")

