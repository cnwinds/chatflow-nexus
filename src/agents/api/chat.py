#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""OpenAI兼容的聊天API路由"""

import uuid
import time
import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, status, Header
from fastapi.responses import StreamingResponse
from src.common.logging import get_logger
from typing import Optional, AsyncGenerator, Dict, Any

logger = get_logger(__name__)

from src.agents.models.requests import ChatCompletionRequest
from src.agents.models.responses import BaseResponse, ChatCompletionResponse, ChatCompletionChunk
from src.agents.workflow_chat import ChatWorkflowManager
from src.agents.user_data import UserData
from src.agents.services.session_service import SessionService
from src.agents.utils.dependencies import get_db_manager, get_current_user

router = APIRouter()
session_service = SessionService()

@router.post("/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    authorization: Optional[str] = Header(None),
    db = Depends(get_db_manager)
):
    """
    OpenAI兼容的聊天完成接口（已废弃）
    
    注意：此接口已废弃，请使用WebSocket接口 /ws/chat
    """
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
        
        # 提取最后一条用户消息
        user_message = None
        for msg in reversed(request.messages):
            role = msg.role if hasattr(msg, 'role') else msg.get("role")
            if role == "user":
                user_message = msg.content if hasattr(msg, 'content') else msg.get("content", "")
                break
        
        if not user_message:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="消息列表中必须包含至少一条用户消息"
            )
        
        # 创建响应队列和回调
        response_queue = asyncio.Queue()
        
        async def text_callback(text: str):
            """文本响应回调"""
            await response_queue.put({"text": text})
        
        # 创建 workflow manager（传入文本响应回调）
        workflow_manager = await _create_workflow_manager(
            db, agent_id, session_id, user['id'], text_response_callback=text_callback
        )
        
        try:
            if request.stream:
                # 流式响应
                return StreamingResponse(
                    _stream_chat_response(workflow_manager, user_message, agent_id, response_queue),
                    media_type="text/event-stream"
                )
            else:
                # 非流式响应
                response = await _chat_completion(
                    workflow_manager, user_message, agent_id, session_id, db, response_queue
                )
                return response
        finally:
            # 关闭workflow会话
            if workflow_manager:
                try:
                    await workflow_manager.close_session()
                except Exception as e:
                    logger.error(f"关闭workflow会话失败: {str(e)}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"聊天完成失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"聊天完成失败: {str(e)}"
        )


async def _create_workflow_manager(
    db, agent_id: int, session_id: str, user_id: int, 
    text_response_callback: Optional[callable] = None
) -> ChatWorkflowManager:
    """创建并初始化 workflow manager
    
    Args:
        db: 数据库管理器
        agent_id: Agent ID
        session_id: 会话ID
        user_id: 用户ID
        text_response_callback: 文本响应回调（可选）
    """
    # 加载UserData
    user_data = UserData(db)
    if not await user_data.load_from_agent_id(agent_id):
        raise ValueError(f"无法加载Agent配置: agent_id={agent_id}")
    
    # TTS回调（OpenAI API不需要，传入空函数）
    async def dummy_tts_send(data: bytes) -> bool:
        return True
    
    async def dummy_tts_start() -> bool:
        return True
    
    async def dummy_tts_stop() -> bool:
        return True
    
    async def dummy_sentence_start(text: str) -> bool:
        return True
    
    async def dummy_sentence_end(text: str) -> bool:
        return True
    
    # 创建 workflow manager（传入文本响应回调）
    workflow_manager = ChatWorkflowManager(
        user_id=user_id,
        agent_id=agent_id,
        tts_send=dummy_tts_send,
        send_tts_start=dummy_tts_start,
        send_tts_stop=dummy_tts_stop,
        send_sentence_start=dummy_sentence_start,
        send_sentence_end=dummy_sentence_end,
        text_response_callback=text_response_callback
    )
    
    # 附加workflow，传入已加载的 user_data 避免重复加载
    await workflow_manager.attach(session_id, copilot_mode=False, user_data=user_data)
    
    logger.info(f"Workflow管理器初始化成功: agent_id={agent_id}, session_id={session_id}")
    return workflow_manager


async def _stream_chat_response(
    workflow_manager: ChatWorkflowManager, 
    user_message: str, 
    agent_id: int,
    response_queue: asyncio.Queue
) -> AsyncGenerator[str, None]:
    """流式聊天响应生成器"""
    
    # 生成响应ID
    response_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
    created_time = int(time.time())
    model_name = f"agent-{agent_id}"
    
    try:
        # 发送用户消息到workflow
        await workflow_manager.push_text(user_message, emotion="neutral")
        
        # 流式输出
        full_response = ""
        response_complete = False
        
        while not response_complete:
            try:
                chunk = await asyncio.wait_for(response_queue.get(), timeout=30.0)
                text = chunk.get("text", "")
                
                if text == "":
                    # 空文本表示响应结束
                    response_complete = True
                else:
                    full_response += text
                    
                    # 构建SSE格式的chunk
                    chunk_data = {
                        "id": response_id,
                        "object": "chat.completion.chunk",
                        "created": created_time,
                        "model": model_name,
                        "choices": [{
                            "index": 0,
                            "delta": {
                                "role": "assistant",
                                "content": text
                            },
                            "finish_reason": None
                        }]
                    }
                    
                    yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
                    
            except asyncio.TimeoutError:
                logger.warning("等待响应超时")
                response_complete = True
            except Exception as e:
                logger.error(f"获取响应块失败: {str(e)}")
                response_complete = True
        
        # 发送结束chunk
        final_chunk = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created_time,
            "model": model_name,
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }]
        }
        yield f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        logger.error(f"流式聊天完成失败: {str(e)}")
        error_chunk = {
            "error": {
                "message": str(e),
                "type": "server_error"
            }
        }
        yield f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n"


async def _chat_completion(
    workflow_manager: ChatWorkflowManager,
    user_message: str,
    agent_id: int,
    session_id: str,
    db,
    response_queue: asyncio.Queue
) -> Dict[str, Any]:
    """非流式聊天完成"""
    
    try:
        # 发送用户消息到workflow
        await workflow_manager.push_text(user_message, emotion="neutral")
        
        # 等待响应
        full_response = ""
        response_complete = False
        
        while not response_complete:
            try:
                chunk = await asyncio.wait_for(response_queue.get(), timeout=30.0)
                text = chunk.get("text", "")
                
                if text == "":
                    response_complete = True
                else:
                    full_response += text
                    
            except asyncio.TimeoutError:
                logger.warning("等待响应超时")
                response_complete = True
            except Exception as e:
                logger.error(f"获取响应块失败: {str(e)}")
                response_complete = True
        
        # 保存消息到数据库
        await _save_messages(db, session_id, agent_id, user_message, full_response)
        
        # 构建OpenAI格式响应
        response_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
        return {
            "id": response_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": f"agent-{agent_id}",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": full_response
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }
        
    except Exception as e:
        logger.error(f"聊天完成失败: {str(e)}")
        raise


async def _save_messages(db, session_id: str, agent_id: int, user_message: str, assistant_message: str):
    """保存消息到数据库"""
    try:
        # 保存用户消息
        user_sql = """
        INSERT INTO chat_messages (session_id, agent_id, role, content, copilot_mode, created_at)
        VALUES (:session_id, :agent_id, 'user', :content, FALSE, NOW())
        """
        await db.execute_insert(user_sql, {
            "session_id": session_id,
            "agent_id": agent_id,
            "content": user_message
        })
        
        # 保存助手消息
        assistant_sql = """
        INSERT INTO chat_messages (session_id, agent_id, role, content, copilot_mode, created_at)
        VALUES (:session_id, :agent_id, 'assistant', :content, FALSE, NOW())
        """
        await db.execute_insert(assistant_sql, {
            "session_id": session_id,
            "agent_id": agent_id,
            "content": assistant_message
        })
        
    except Exception as e:
        logger.error(f"保存消息失败: {str(e)}")

