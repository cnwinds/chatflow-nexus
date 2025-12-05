#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""WebSocket API路由"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Header, Query, status
from typing import Optional
from src.common.logging import get_logger

logger = get_logger(__name__)

from src.agents.api.websocket_handler import WebSocketHandler
from src.agents.utils.dependencies import get_db_manager
from src.agents.utils.jwt_utils import verify_token
from src.agents.services.user_service import UserService

router = APIRouter()


@router.websocket("/ws/chat")
async def websocket_chat(
    websocket: WebSocket,
    token: Optional[str] = Query(None, description="访问令牌（Bearer token）"),
    protocol_version: Optional[str] = Query(None, description="协议版本"),
    client_id: Optional[str] = Query(None, description="客户端ID"),
    # 也支持从headers获取（用于非浏览器客户端）
    authorization: Optional[str] = Header(None),
    protocol_version_header: Optional[str] = Header(None, alias="Protocol-Version"),
    client_id_header: Optional[str] = Header(None, alias="Client-Id")
):
    """
    WebSocket聊天端点
    
    支持两种认证方式：
    1. URL参数（浏览器推荐）: ?token=<access_token>&protocol_version=1&client_id=<uuid>
    2. Headers（非浏览器客户端）: Authorization: Bearer <access_token>, Protocol-Version: 1, Client-Id: <uuid>
    """
    handler: Optional[WebSocketHandler] = None
    
    try:
        # 1. 获取认证信息（优先使用headers，如果没有则使用URL参数）
        auth_token = None
        if authorization and authorization.startswith("Bearer "):
            auth_token = authorization.replace("Bearer ", "")
        elif token:
            auth_token = token
        
        protocol_ver = protocol_version_header or protocol_version
        client_uuid = client_id_header or client_id
        
        if not auth_token:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="缺少token")
            return
        
        if not protocol_ver:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="缺少Protocol-Version")
            return
        
        if not client_uuid:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="缺少Client-Id")
            return
        
        # 2. 验证token
        payload = verify_token(auth_token)
        
        if not payload:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Token无效或已过期")
            return
        
        user_id = payload.get("user_id")
        if not user_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Token中缺少user_id")
            return
        
        # 3. 验证用户是否存在
        db = get_db_manager()
        user_service = UserService()
        user = await user_service.get_user_by_id(db, user_id)
        
        if not user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="用户不存在")
            return
        
        # 4. 接受WebSocket连接
        await websocket.accept()
        logger.info(f"WebSocket连接已建立: user_id={user_id}, client_id={client_uuid}")
        
        # 5. 创建处理器
        handler = WebSocketHandler(websocket, user_id, client_uuid, db)
        
        # 6. 消息循环
        connection_closed = False
        while not connection_closed:
            try:
                # 接收消息（支持文本和二进制）
                message = await websocket.receive()
                
                # 检查是否是断开消息
                if message.get("type") == "websocket.disconnect":
                    connection_closed = True
                    break
                
                if "text" in message:
                    # 文本消息
                    await handler.handle_message(message["text"])
                elif "bytes" in message:
                    # 二进制消息（音频数据）
                    await handler.handle_message(message["bytes"])
                else:
                    logger.warning(f"收到未知消息类型: {message.keys()}")
                    
            except WebSocketDisconnect:
                logger.info(f"WebSocket连接断开: user_id={user_id}, client_id={client_uuid}")
                connection_closed = True
                break
            except RuntimeError as e:
                # FastAPI WebSocket断开时的运行时错误
                if "disconnect" in str(e).lower() or "close" in str(e).lower():
                    logger.info(f"WebSocket连接已断开: user_id={user_id}, client_id={client_uuid}")
                    connection_closed = True
                    break
                else:
                    logger.error(f"处理WebSocket消息时出错: {e}", exc_info=True)
                    # 尝试发送错误消息，但如果连接已断开则忽略
                    try:
                        if not connection_closed:
                            await handler.send_error(500, f"服务器内部错误: {str(e)}")
                    except (WebSocketDisconnect, RuntimeError):
                        connection_closed = True
                        break
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"处理WebSocket消息时出错: {e}", exc_info=True)
                # 尝试发送错误消息，但如果连接已断开则忽略
                try:
                    if not connection_closed:
                        await handler.send_error(500, f"服务器内部错误: {str(e)}")
                except (WebSocketDisconnect, RuntimeError):
                    connection_closed = True
                    break
                except Exception:
                    pass
        
    except WebSocketDisconnect:
        logger.info("WebSocket连接已断开")
    except Exception as e:
        logger.error(f"WebSocket连接处理失败: {e}", exc_info=True)
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason=f"服务器错误: {str(e)}")
        except:
            pass
    finally:
        # 清理资源
        if handler:
            await handler.cleanup()

