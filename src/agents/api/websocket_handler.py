#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""WebSocket消息处理器"""

import json
import asyncio
from typing import Optional, Dict, Any, Callable, Awaitable
from src.common.logging import get_logger

logger = get_logger(__name__)

from src.agents.models.websocket_messages import (
    HelloRequest, HelloResponse, ListenMessage, TextMessage,
    TTSMessage, LLMMessage, AbortMessage, MCPMessage, ErrorMessage, AudioParams
)
from src.agents.workflow_chat import ChatWorkflowManager
from src.agents.user_data import UserData
from src.common.database.manager import get_db_manager


class WebSocketHandler:
    """WebSocket连接处理器"""
    
    def __init__(self, websocket, user_id: int, client_id: str, db):
        """
        初始化WebSocket处理器
        
        Args:
            websocket: WebSocket连接对象
            user_id: 用户ID
            client_id: 客户端ID
            db: 数据库管理器
        """
        self.websocket = websocket
        self.user_id = user_id
        self.client_id = client_id
        self.db = db
        
        # 连接状态
        self.hello_exchanged = False
        self.current_session_id: Optional[str] = None
        self.current_agent_id: Optional[int] = None
        self.workflow_manager: Optional[ChatWorkflowManager] = None
        
        # 音频参数
        self.audio_params: Optional[AudioParams] = None
        
    async def send_json(self, data: Dict[str, Any]):
        """发送JSON消息"""
        try:
            await self.websocket.send_json(data)
        except (RuntimeError, ConnectionError) as e:
            # 连接已关闭，不记录错误
            if "disconnect" not in str(e).lower() and "close" not in str(e).lower():
                logger.error(f"发送WebSocket消息失败: {e}")
            raise
        except Exception as e:
            logger.error(f"发送WebSocket消息失败: {e}")
            raise
    
    async def send_bytes(self, data: bytes):
        """发送二进制数据"""
        try:
            await self.websocket.send_bytes(data)
        except (RuntimeError, ConnectionError) as e:
            # 连接已关闭，不记录错误
            if "disconnect" not in str(e).lower() and "close" not in str(e).lower():
                logger.error(f"发送WebSocket二进制数据失败: {e}")
            raise
        except Exception as e:
            logger.error(f"发送WebSocket二进制数据失败: {e}")
            raise
    
    async def send_error(self, code: int, message: str, details: Optional[Dict[str, Any]] = None):
        """发送错误消息"""
        try:
            error_msg = ErrorMessage(
                type="error",
                code=code,
                message=message,
                details=details
            )
            await self.send_json(error_msg.dict())
        except (RuntimeError, ConnectionError):
            # 连接已关闭，忽略错误
            pass
        except Exception as e:
            logger.debug(f"发送错误消息失败（连接可能已关闭）: {e}")
    
    async def handle_hello(self, message: Dict[str, Any]):
        """处理hello消息"""
        try:
            hello_req = HelloRequest(**message)
            
            # 保存客户端音频参数
            if hello_req.audio_params:
                self.audio_params = hello_req.audio_params
            
            # 发送服务端hello响应
            hello_resp = HelloResponse(
                type="hello",
                transport="websocket",
                audio_params=AudioParams(
                    format="opus",
                    sample_rate=24000,  # 服务端TTS采样率
                    channels=1,
                    frame_duration=60
                )
            )
            await self.send_json(hello_resp.dict())
            
            self.hello_exchanged = True
            logger.info(f"Hello消息交换成功: user_id={self.user_id}, client_id={self.client_id}")
            
        except Exception as e:
            logger.error(f"处理hello消息失败: {e}")
            await self.send_error(400, f"Hello消息处理失败: {str(e)}")
    
    async def handle_listen(self, message: Dict[str, Any]):
        """处理listen消息"""
        try:
            listen_msg = ListenMessage(**message)
            session_id = listen_msg.session_id or self.current_session_id
            
            if not session_id:
                await self.send_error(400, "缺少session_id")
                return
            
            if listen_msg.state == "start":
                # 开始监听 - 需要确保workflow已初始化
                if not self.workflow_manager:
                    await self.send_error(400, "Workflow未初始化，请先发送文本消息")
                    return
                
                # 如果workflow已初始化，VAD节点会自动处理音频流
                logger.info(f"开始监听: session_id={session_id}, mode={listen_msg.mode}")
                
            elif listen_msg.state == "stop":
                # 停止监听
                logger.info(f"停止监听: session_id={session_id}")
                
            elif listen_msg.state == "detect":
                # 唤醒词检测
                logger.info(f"唤醒词检测: session_id={session_id}, text={listen_msg.text}")
                
        except Exception as e:
            logger.error(f"处理listen消息失败: {e}")
            await self.send_error(400, f"Listen消息处理失败: {str(e)}")
    
    async def handle_text(self, message: Dict[str, Any]):
        """处理文本消息"""
        try:
            text_msg = TextMessage(**message)
            session_id = text_msg.session_id
            agent_id = text_msg.agent_id
            
            if not agent_id:
                await self.send_error(400, "缺少agent_id")
                return
            
            # 验证agent是否属于当前用户
            from src.agents.services.agent_service import AgentService
            agent_service = AgentService()
            agent = await agent_service.get_agent_detail(self.db, agent_id, self.user_id)
            
            if not agent:
                await self.send_error(404, "Agent不存在或无权限访问")
                return
            
            # 获取或创建会话
            if not session_id:
                from src.agents.services.session_service import SessionService
                session_service = SessionService()
                session = await session_service.create_session(self.db, self.user_id, agent_id)
                session_id = session['session_id']
            
            # 更新当前会话和agent
            self.current_session_id = session_id
            self.current_agent_id = agent_id
            
            # 初始化或复用workflow manager
            if not self.workflow_manager or self.workflow_manager.agent_id != agent_id:
                await self._initialize_workflow(agent_id, session_id)
            
            # 推送文本到workflow
            if self.workflow_manager:
                logger.info(f"准备推送文本消息到workflow: session_id={session_id}, agent_id={agent_id}, content={text_msg.content[:100]}")
                await self.workflow_manager.push_text(text_msg.content, emotion="neutral")
                logger.info(f"文本消息已推送到workflow: session_id={session_id}, content={text_msg.content[:50]}")
            else:
                logger.error(f"Workflow manager未初始化，无法推送文本消息")
            
        except Exception as e:
            logger.error(f"处理文本消息失败: {e}")
            await self.send_error(500, f"文本消息处理失败: {str(e)}")
    
    async def handle_abort(self, message: Dict[str, Any]):
        """处理中止消息"""
        try:
            abort_msg = AbortMessage(**message)
            logger.info(f"收到中止消息: session_id={abort_msg.session_id}, reason={abort_msg.reason}")
            
            # 可以在这里实现中止逻辑，比如停止TTS播放等
            # 目前workflow会自动处理中断
            
        except Exception as e:
            logger.error(f"处理中止消息失败: {e}")
            await self.send_error(400, f"Abort消息处理失败: {str(e)}")
    
    async def handle_mcp(self, message: Dict[str, Any]):
        """处理MCP消息"""
        try:
            mcp_msg = MCPMessage(**message)
            logger.info(f"收到MCP消息: session_id={mcp_msg.session_id}")
            
            # TODO: 实现MCP消息处理逻辑
            
        except Exception as e:
            logger.error(f"处理MCP消息失败: {e}")
            await self.send_error(400, f"MCP消息处理失败: {str(e)}")
    
    async def handle_binary(self, data: bytes):
        """处理二进制音频数据"""
        try:
            if not self.workflow_manager:
                logger.warning("收到音频数据但workflow未初始化")
                return
            
            # 推送OPUS音频数据到workflow的VAD节点
            await self.workflow_manager.push_opus(data)
            
        except Exception as e:
            logger.error(f"处理二进制音频数据失败: {e}")
    
    async def _initialize_workflow(self, agent_id: int, session_id: str):
        """初始化workflow manager"""
        try:
            # 加载UserData
            user_data = UserData(self.db)
            if not await user_data.load_from_agent_id(agent_id):
                raise ValueError(f"无法加载Agent配置: agent_id={agent_id}")
            
            # 创建TTS回调函数
            async def tts_send(data: bytes) -> bool:
                """发送TTS音频数据"""
                try:
                    await self.send_bytes(data)
                    return True
                except Exception as e:
                    logger.error(f"发送TTS音频失败: {e}")
                    return False
            
            async def tts_start() -> bool:
                """TTS开始"""
                try:
                    tts_msg = TTSMessage(type="tts", state="start")
                    await self.send_json(tts_msg.dict())
                    return True
                except Exception as e:
                    logger.error(f"发送TTS开始消息失败: {e}")
                    return False
            
            async def tts_stop() -> bool:
                """TTS停止"""
                try:
                    tts_msg = TTSMessage(type="tts", state="stop")
                    await self.send_json(tts_msg.dict())
                    return True
                except Exception as e:
                    logger.error(f"发送TTS停止消息失败: {e}")
                    return False
            
            async def sentence_start(text: str) -> bool:
                """句子开始"""
                try:
                    tts_msg = TTSMessage(type="tts", state="sentence_start", text=text)
                    await self.send_json(tts_msg.dict())
                    return True
                except Exception as e:
                    logger.error(f"发送句子开始消息失败: {e}")
                    return False
            
            async def sentence_end(text: str) -> bool:
                """句子结束（协议中没有，但workflow可能调用）"""
                return True
            
            # 创建文本响应回调
            async def text_response_callback(text: str):
                """文本响应回调"""
                try:
                    logger.debug(f"收到文本响应回调: text长度={len(text) if text else 0}, text={text[:100] if text else 'empty'}")
                    # 空字符串表示响应完成
                    if text == "":
                        logger.info("文本响应完成，发送finished消息")
                        llm_msg = LLMMessage(
                            type="llm",
                            content=None,
                            finished=True
                        )
                    else:
                        llm_msg = LLMMessage(
                            type="llm",
                            content=text,
                            finished=False
                        )
                    logger.debug(f"准备发送LLM消息: finished={llm_msg.finished}, content长度={len(llm_msg.content) if llm_msg.content else 0}")
                    await self.send_json(llm_msg.dict())
                    logger.debug(f"已发送LLM消息: finished={llm_msg.finished}, content长度={len(llm_msg.content) if llm_msg.content else 0}")
                except Exception as e:
                    logger.error(f"发送LLM响应失败: {e}", exc_info=True)
            
            # 关闭旧的workflow manager
            if self.workflow_manager:
                try:
                    await self.workflow_manager.close_session()
                except Exception as e:
                    logger.warning(f"关闭旧workflow失败: {e}")
            
            # 创建新的workflow manager
            self.workflow_manager = ChatWorkflowManager(
                user_id=self.user_id,
                agent_id=agent_id,
                tts_send=tts_send,
                send_tts_start=tts_start,
                send_tts_stop=tts_stop,
                send_sentence_start=sentence_start,
                send_sentence_end=sentence_end,
                text_response_callback=text_response_callback
            )
            
            # 附加workflow
            await self.workflow_manager.attach(session_id, copilot_mode=False, user_data=user_data)
            
            logger.info(f"Workflow初始化成功: agent_id={agent_id}, session_id={session_id}")
            
        except Exception as e:
            logger.error(f"初始化workflow失败: {e}")
            raise
    
    async def handle_message(self, message: Any):
        """处理接收到的消息"""
        try:
            # 如果是二进制数据
            if isinstance(message, bytes):
                logger.debug(f"收到二进制消息，长度: {len(message)}")
                await self.handle_binary(message)
                return
            
            # 如果是文本消息，解析JSON
            if isinstance(message, str):
                logger.debug(f"收到文本消息（字符串）: {message[:100]}")
                message = json.loads(message)
            
            logger.debug(f"解析后的消息类型: {message.get('type')}, 完整消息: {message}")
            
            # 检查hello消息是否已交换
            if not self.hello_exchanged:
                if message.get("type") == "hello":
                    await self.handle_hello(message)
                else:
                    logger.warning(f"Hello未交换，收到非hello消息: {message.get('type')}")
                    await self.send_error(400, "请先发送hello消息")
                return
            
            # 根据消息类型路由
            msg_type = message.get("type")
            logger.info(f"路由消息到处理器: type={msg_type}")
            
            if msg_type == "hello":
                await self.handle_hello(message)
            elif msg_type == "listen":
                await self.handle_listen(message)
            elif msg_type == "text":
                await self.handle_text(message)
            elif msg_type == "abort":
                await self.handle_abort(message)
            elif msg_type == "mcp":
                await self.handle_mcp(message)
            else:
                logger.warning(f"未知的消息类型: {msg_type}")
                await self.send_error(400, f"未知的消息类型: {msg_type}")
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            await self.send_error(400, f"JSON解析失败: {str(e)}")
        except Exception as e:
            logger.error(f"处理消息失败: {e}", exc_info=True)
            await self.send_error(500, f"消息处理失败: {str(e)}")
    
    async def cleanup(self):
        """清理资源"""
        try:
            if self.workflow_manager:
                await self.workflow_manager.close_session()
                self.workflow_manager = None
            logger.info(f"WebSocket连接清理完成: user_id={self.user_id}, client_id={self.client_id}")
        except Exception as e:
            logger.error(f"清理WebSocket连接失败: {e}")

