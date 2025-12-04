#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""聊天Workflow适配器 - 将OpenAI消息转换为workflow输入"""

import asyncio
from typing import AsyncGenerator, Dict, Any, Optional
from loguru import logger

from src.common.database.manager import DatabaseManager
from src.agents.workflow_chat import ChatWorkflowManager
from src.agents.workflow.user_data_adapter import AgentUserDataAdapter


class ChatWorkflowAdapter:
    """聊天Workflow适配器"""
    
    def __init__(self, db: DatabaseManager, agent_id: int, session_id: str):
        """初始化适配器
        
        Args:
            db: 数据库管理器
            agent_id: Agent ID
            session_id: 会话ID
        """
        self.db = db
        self.agent_id = agent_id
        self.session_id = session_id
        self.workflow_manager: Optional[ChatWorkflowManager] = None
        self._response_queue = asyncio.Queue()
        self._initialized = False
    
    async def initialize(self) -> None:
        """初始化workflow管理器"""
        if self._initialized:
            return
        
        try:
            # 加载UserData
            user_data = AgentUserDataAdapter(self.db)
            if not await user_data.load_from_agent_id(self.agent_id):
                raise ValueError(f"无法加载Agent配置: agent_id={self.agent_id}")
            
            # 创建ChatWorkflowManager
            # 注意：OpenAI API不需要TTS回调，所以传入空函数
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
            
            self.workflow_manager = ChatWorkflowManager(
                device_id=str(self.agent_id),  # 使用agent_id作为device_id
                tts_send=dummy_tts_send,
                send_tts_start=dummy_tts_start,
                send_tts_stop=dummy_tts_stop,
                send_sentence_start=dummy_sentence_start,
                send_sentence_end=dummy_sentence_end
            )
            
            # 附加workflow
            await self.workflow_manager.attach(self.session_id, copilot_mode=False)
            
            # 设置响应回调
            self._setup_response_callback()
            
            self._initialized = True
            logger.info(f"Workflow适配器初始化成功: agent_id={self.agent_id}, session_id={self.session_id}")
            
        except Exception as e:
            logger.error(f"初始化Workflow适配器失败: {str(e)}")
            raise
    
    def _setup_response_callback(self) -> None:
        """设置响应回调"""
        if not self.workflow_manager or not self.workflow_manager.context:
            return
        
        # 获取workflow引擎
        engine = self.workflow_manager.context.get_global_var("engine")
        if not engine:
            return
        
        # 添加外部连接来接收响应文本流
        async def response_callback(chunk: Dict[str, Any]) -> None:
            """响应文本流回调"""
            text = chunk.get("text", "")
            await self._response_queue.put({"text": text})
        
        # 连接到agent_node的response_text_stream输出
        try:
            engine.add_external_connection("agent_node", "response_text_stream", response_callback)
        except Exception as e:
            logger.warning(f"添加外部连接失败: {str(e)}")
    
    async def process_message(self, user_message: str) -> AsyncGenerator[Dict[str, Any], None]:
        """处理用户消息
        
        Args:
            user_message: 用户消息文本
            
        Yields:
            响应文本块
        """
        if not self._initialized:
            await self.initialize()
        
        if not self.workflow_manager or not self.workflow_manager.context:
            raise RuntimeError("Workflow管理器未初始化")
        
        try:
            # 清空响应队列
            while not self._response_queue.empty():
                try:
                    self._response_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            
            # 获取workflow引擎
            engine = self.workflow_manager.context.get_global_var("engine")
            if not engine:
                raise RuntimeError("Workflow引擎未初始化")
            
            # 发送用户消息到workflow
            # 通过agent_node的user_text输入发送
            agent_node = engine.get_node("agent_node")
            if not agent_node:
                raise RuntimeError("agent_node未找到")
            
            await agent_node.feed_input_chunk(
                "user_text",
                {
                    "text": user_message,
                    "confidence": 1.0,
                    "audio_file_path": None,
                    "emotion": "neutral"
                }
            )
            
            # 等待响应
            response_complete = False
            while not response_complete:
                try:
                    # 等待响应块，设置超时
                    chunk = await asyncio.wait_for(self._response_queue.get(), timeout=30.0)
                    if chunk.get("text") == "":
                        # 空文本表示响应结束
                        response_complete = True
                    else:
                        yield chunk
                except asyncio.TimeoutError:
                    logger.warning("等待响应超时")
                    response_complete = True
                except Exception as e:
                    logger.error(f"获取响应块失败: {str(e)}")
                    response_complete = True
            
        except Exception as e:
            logger.error(f"处理消息失败: {str(e)}")
            raise
    
    async def close(self) -> None:
        """关闭适配器"""
        if self.workflow_manager:
            try:
                await self.workflow_manager.close_session()
            except Exception as e:
                logger.error(f"关闭workflow会话失败: {str(e)}")

