#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""会话管理API路由"""

from fastapi import APIRouter, Depends, HTTPException, status
from src.common.logging import get_logger
from typing import List

logger = get_logger(__name__)

from src.agents.models.requests import CreateSessionRequest
from src.agents.models.responses import BaseResponse, SessionInfo, MessageInfo
from src.agents.services.session_service import SessionService
from src.agents.utils.dependencies import get_db_manager, get_current_user

router = APIRouter()
session_service = SessionService()

@router.get("", response_model=BaseResponse[List[SessionInfo]])
async def get_sessions(
    current_user = Depends(get_current_user),
    db = Depends(get_db_manager)
):
    """获取用户的会话列表"""
    try:
        sessions = await session_service.get_user_sessions(db, current_user['id'])
        session_list = []
        for session in sessions:
            session_list.append(SessionInfo(
                session_id=session['session_id'],
                user_id=session['user_id'],
                agent_id=session['agent_id'],
                agent_name=session.get('agent_name', '未知Agent'),
                title=session.get('title', '新对话'),
                created_at=session['created_at'],
                updated_at=session['updated_at'],
                message_count=session.get('message_count', 0)
            ))
        return BaseResponse(data=session_list)
    except Exception as e:
        logger.error(f"获取会话列表失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取会话列表失败"
        )

@router.post("", response_model=BaseResponse[SessionInfo])
async def create_session(
    request: CreateSessionRequest,
    current_user = Depends(get_current_user),
    db = Depends(get_db_manager)
):
    """创建新会话"""
    try:
        # 验证agent是否属于当前用户
        from src.agents.services.agent_service import AgentService
        agent_service = AgentService()
        agent = await agent_service.get_agent_detail(db, request.agent_id, current_user['id'])
        
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent不存在或无权限访问"
            )
        
        session = await session_service.create_session(
            db, current_user['id'], request.agent_id, request.title
        )
        
        return BaseResponse(data=SessionInfo(
            session_id=session['session_id'],
            user_id=session['user_id'],
            agent_id=session['agent_id'],
            agent_name=agent['name'],
            title=session['title'],
            created_at=session['created_at'],
            updated_at=session['updated_at'],
            message_count=session['message_count']
        ))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建会话失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="创建会话失败"
        )

@router.get("/{session_id}/messages", response_model=BaseResponse[List[MessageInfo]])
async def get_session_messages(
    session_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db_manager)
):
    """获取会话消息历史"""
    try:
        messages = await session_service.get_session_messages(db, session_id)
        message_list = []
        for msg in messages:
            message_list.append(MessageInfo(
                id=msg['id'],
                session_id=msg['session_id'],
                role=msg['role'],
                content=msg['content'],
                created_at=msg['created_at']
            ))
        return BaseResponse(data=message_list)
    except Exception as e:
        logger.error(f"获取会话消息失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取会话消息失败"
        )

@router.delete("/{session_id}", response_model=BaseResponse[None])
async def delete_session(
    session_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db_manager)
):
    """删除会话"""
    try:
        success = await session_service.delete_session(db, session_id, current_user['id'])
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="会话不存在或无权限访问"
            )
        
        return BaseResponse(message="删除成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除会话失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除会话失败"
        )

