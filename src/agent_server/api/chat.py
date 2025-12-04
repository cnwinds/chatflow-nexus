#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""OpenAI兼容的聊天API路由"""

import uuid
import time
from fastapi import APIRouter, Depends, HTTPException, status, Header
from fastapi.responses import StreamingResponse
from loguru import logger
from typing import Optional, AsyncGenerator
import json

from src.agents.models.requests import ChatCompletionRequest
from src.agents.models.responses import BaseResponse, ChatCompletionResponse, ChatCompletionChunk
from src.agents.services.chat_service import ChatService
from src.agents.services.session_service import SessionService
from src.agents.dependencies import get_db_manager, get_current_user

router = APIRouter()
chat_service = ChatService()
session_service = SessionService()

@router.post("/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    authorization: Optional[str] = Header(None),
    db = Depends(get_db_manager)
):
    """OpenAI兼容的聊天完成接口"""
    try:
        # 解析agent_id
        if not request.model.startswith("agent-"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="模型名称格式错误，应为 agent-{agent_id}"
            )
        
        agent_id = int(request.model.replace("agent-", ""))
        
        # 获取当前用户
        user = None
        if authorization and authorization.startswith("Bearer "):
            try:
                from src.agents.utils.jwt_utils import verify_token
                from src.agents.services.user_service import UserService
                token = authorization.replace("Bearer ", "")
                payload = verify_token(token)
                if payload:
                    user_service = UserService()
                    user = await user_service.get_user_by_id(db, payload["user_id"])
            except Exception as e:
                logger.debug(f"获取用户失败: {e}")
                pass
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="需要登录"
            )
        
        # 验证agent是否属于当前用户
        from src.agents.services.agent_service import AgentService
        agent_service = AgentService()
        agent = await agent_service.get_agent_detail(db, agent_id, user['id'])
        
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent不存在或无权限访问"
            )
        
        # 获取或创建会话
        session_id = request.session_id
        if not session_id:
            session = await session_service.create_session(db, user['id'], agent_id)
            session_id = session['session_id']
        
        # 调用聊天服务
        if request.stream:
            # 流式响应
            return StreamingResponse(
                chat_service.stream_chat_completion(
                    db, session_id, agent_id, user['id'], request.messages
                ),
                media_type="text/event-stream"
            )
        else:
            # 非流式响应
            response = await chat_service.chat_completion(
                db, session_id, agent_id, user['id'], request.messages
            )
            return response
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"聊天完成失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"聊天完成失败: {str(e)}"
        )

