#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""聊天服务"""

import uuid
import time
import json
from typing import List, Dict, Any, Optional, AsyncGenerator
from datetime import datetime
from loguru import logger

from src.common.database.manager import DatabaseManager
from src.agents.workflow.chat_workflow_adapter import ChatWorkflowAdapter

class ChatService:
    """聊天服务类"""
    
    async def chat_completion(
        self, db: DatabaseManager, session_id: str, agent_id: int, user_id: int,
        messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """非流式聊天完成
        
        Args:
            db: 数据库管理器
            session_id: 会话ID
            agent_id: Agent ID
            user_id: 用户ID
            messages: OpenAI格式的消息列表
            
        Returns:
            OpenAI格式的响应
        """
        try:
            # 创建workflow适配器
            adapter = ChatWorkflowAdapter(db, agent_id, session_id)
            await adapter.initialize()
            
            # 提取最后一条用户消息
            user_message = None
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    user_message = msg.get("content", "")
                    break
            
            if not user_message:
                raise ValueError("消息列表中必须包含至少一条用户消息")
            
            # 调用workflow处理
            full_response = ""
            async for chunk in adapter.process_message(user_message):
                if chunk.get("text"):
                    full_response += chunk["text"]
            
            # 保存消息到数据库
            await self._save_messages(db, session_id, agent_id, user_message, full_response)
            
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
                    "prompt_tokens": 0,  # TODO: 实现token计数
                    "completion_tokens": 0,
                    "total_tokens": 0
                }
            }
            
        except Exception as e:
            logger.error(f"聊天完成失败: {str(e)}")
            raise
    
    async def stream_chat_completion(
        self, db: DatabaseManager, session_id: str, agent_id: int, user_id: int,
        messages: List[Dict[str, Any]]
    ) -> AsyncGenerator[str, None]:
        """流式聊天完成
        
        Args:
            db: 数据库管理器
            session_id: 会话ID
            agent_id: Agent ID
            user_id: 用户ID
            messages: OpenAI格式的消息列表
            
        Yields:
            SSE格式的流式响应
        """
        try:
            # 创建workflow适配器
            adapter = ChatWorkflowAdapter(db, agent_id, session_id)
            await adapter.initialize()
            
            # 提取最后一条用户消息
            user_message = None
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    user_message = msg.get("content", "")
                    break
            
            if not user_message:
                raise ValueError("消息列表中必须包含至少一条用户消息")
            
            # 生成响应ID
            response_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
            created_time = int(time.time())
            model_name = f"agent-{agent_id}"
            
            full_response = ""
            
            # 流式输出
            async for chunk in adapter.process_message(user_message):
                if chunk.get("text"):
                    text = chunk["text"]
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
            
            # 保存消息到数据库
            await self._save_messages(db, session_id, agent_id, user_message, full_response)
            
        except Exception as e:
            logger.error(f"流式聊天完成失败: {str(e)}")
            error_chunk = {
                "error": {
                    "message": str(e),
                    "type": "server_error"
                }
            }
            yield f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n"
    
    async def _save_messages(
        self, db: DatabaseManager, session_id: str, agent_id: int,
        user_message: str, assistant_message: str
    ) -> None:
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

