#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Agent管理API路由"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from loguru import logger
from typing import List, Optional
import json

from src.agents.models.requests import CreateAgentRequest, UpdateAgentRequest
from src.agents.models.responses import BaseResponse, AgentInfo
from src.agents.services.agent_service import AgentService
from src.agents.dependencies import get_db_manager, get_current_user

router = APIRouter()
agent_service = AgentService()

def parse_agent_config(agent_config, agent_id=None):
    """解析 agent_config，将 JSON 字符串转换为字典"""
    if isinstance(agent_config, str):
        try:
            return json.loads(agent_config) if agent_config else {}
        except json.JSONDecodeError:
            if agent_id:
                logger.warning(f"解析 agent_config 失败: agent_id={agent_id}, 使用空字典")
            return {}
    elif agent_config is None:
        return {}
    return agent_config

@router.get("/templates", response_model=BaseResponse[List[dict]])
async def get_templates(
    device_type: Optional[int] = Query(None, description="设备类型"),
    current_user = Depends(get_current_user),
    db = Depends(get_db_manager)
):
    """获取可用的Agent模板列表"""
    try:
        # 构建查询条件
        where_conditions = ["status = 1"]  # 只查询正常状态的模板
        params = {}
        
        if device_type is not None:
            if device_type not in [0, 1, 2, 3, 4, 5]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="设备类型不支持"
                )
            where_conditions.append("device_type = :device_type")
            params["device_type"] = device_type
        
        # 查询模板列表
        sql = f"""
        SELECT id, name, description, avatar, gender, device_type, 
               creator_id, created_at, updated_at, status
        FROM agent_templates 
        WHERE {' AND '.join(where_conditions)}
        ORDER BY created_at DESC
        """
        
        templates = await db.execute_query(sql, params)
        
        template_list = []
        for template in templates:
            template_info = {
                "id": template['id'],
                "name": template['name'],
                "description": template.get('description'),
                "avatar": template.get('avatar'),
                "gender": template['gender'],
                "device_type": template['device_type'],
            }
            template_list.append(template_info)
        
        return BaseResponse(data=template_list)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取模板列表失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取模板列表失败"
        )

@router.get("", response_model=BaseResponse[List[AgentInfo]])
async def get_agents(
    current_user = Depends(get_current_user),
    db = Depends(get_db_manager)
):
    """获取用户的所有agent列表"""
    try:
        agents = await agent_service.get_user_agents(db, current_user['id'])
        agent_list = []
        for agent in agents:
            # 处理 created_at - 可能是 datetime 对象或字符串
            created_at = agent.get('created_at')
            if created_at:
                created_at_str = created_at.isoformat() if hasattr(created_at, 'isoformat') else str(created_at)
            else:
                created_at_str = None
            
            # 处理 updated_at - 可能是 datetime 对象或字符串
            updated_at = agent.get('updated_at')
            if updated_at:
                updated_at_str = updated_at.isoformat() if hasattr(updated_at, 'isoformat') else str(updated_at)
            else:
                updated_at_str = None
            
            # 处理 agent_config - 可能是 JSON 字符串或字典
            agent_config = parse_agent_config(agent.get('agent_config'), agent.get('id'))
            
            agent_list.append(AgentInfo(
                id=agent['id'],
                name=agent['name'],
                description=agent.get('description'),
                avatar=agent.get('avatar'),
                gender=agent.get('gender', 0),
                device_type=agent['device_type'],
                template_id=agent['template_id'],
                template_name=agent.get('template_name'),
                agent_config=agent_config,
                status=agent.get('status', 1),  # 默认状态为1（正常）
                created_at=created_at_str,
                updated_at=updated_at_str
            ))
        return BaseResponse(data=agent_list)
    except Exception as e:
        logger.error(f"获取agent列表失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取agent列表失败"
        )

@router.get("/{agent_id}", response_model=BaseResponse[AgentInfo])
async def get_agent_detail(
    agent_id: int,
    current_user = Depends(get_current_user),
    db = Depends(get_db_manager)
):
    """获取agent详情"""
    try:
        agent = await agent_service.get_agent_detail(db, agent_id, current_user['id'])
        
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent不存在或无权限访问"
            )
        
        # 处理 agent_config - 可能是 JSON 字符串或字典
        agent_config = parse_agent_config(agent.get('agent_config'), agent.get('id'))
        
        return BaseResponse(data=AgentInfo(
            id=agent['id'],
            name=agent['name'],
            description=agent.get('description'),
            avatar=agent.get('avatar'),
            gender=agent.get('gender', 0),
            device_type=agent['device_type'],
            template_id=agent['template_id'],
            template_name=agent.get('template_name'),
            agent_config=agent_config,
            status=agent.get('status', 1),
            created_at=agent['created_at'].isoformat() if hasattr(agent['created_at'], 'isoformat') else str(agent['created_at']),
            updated_at=agent.get('updated_at').isoformat() if agent.get('updated_at') and hasattr(agent['updated_at'], 'isoformat') else (str(agent['updated_at']) if agent.get('updated_at') else None)
        ))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取agent详情失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取agent详情失败"
        )

@router.post("", response_model=BaseResponse[AgentInfo])
async def create_agent(
    request: CreateAgentRequest,
    current_user = Depends(get_current_user),
    db = Depends(get_db_manager)
):
    """创建新agent"""
    try:
        agent = await agent_service.create_agent(
            db, current_user['id'], request.name, request.template_id,
            request.device_type, request.description, request.agent_config
        )
        
        if not agent:
            # 尝试获取更详细的错误信息
            try:
                template = await db.execute_one(
                    "SELECT id, status FROM agent_templates WHERE id = :template_id",
                    {"template_id": request.template_id}
                )
                if not template:
                    detail = f"模板ID {request.template_id} 不存在"
                elif template.get('status') != 1:
                    detail = f"模板ID {request.template_id} 状态异常（状态码: {template.get('status')}），无法使用"
                else:
                    detail = "创建agent失败，可能是数据库操作失败"
            except Exception:
                detail = f"创建agent失败，请检查模板ID {request.template_id} 是否正确"
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=detail
            )
        
        # 处理 agent_config - 可能是 JSON 字符串或字典
        agent_config = parse_agent_config(agent.get('agent_config'), agent.get('id'))
        
        return BaseResponse(data=AgentInfo(
            id=agent['id'],
            name=agent['name'],
            description=agent.get('description'),
            avatar=agent.get('avatar'),
            gender=agent.get('gender', 0),
            device_type=agent['device_type'],
            template_id=agent['template_id'],
            template_name=agent.get('template_name'),
            agent_config=agent_config,
            status=agent.get('status', 1),
            created_at=agent['created_at'].isoformat() if hasattr(agent['created_at'], 'isoformat') else str(agent['created_at']),
            updated_at=agent.get('updated_at').isoformat() if agent.get('updated_at') and hasattr(agent['updated_at'], 'isoformat') else (str(agent['updated_at']) if agent.get('updated_at') else None)
        ))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建agent失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="创建agent失败"
        )

@router.put("/{agent_id}", response_model=BaseResponse[AgentInfo])
async def update_agent(
    agent_id: int,
    request: UpdateAgentRequest,
    current_user = Depends(get_current_user),
    db = Depends(get_db_manager)
):
    """更新agent配置"""
    try:
        agent = await agent_service.update_agent(
            db, agent_id, current_user['id'],
            request.name, request.description, request.agent_config
        )
        
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent不存在或更新失败"
            )
        
        return BaseResponse(data=AgentInfo(
            id=agent['id'],
            name=agent['name'],
            description=agent.get('description'),
            avatar=agent.get('avatar'),
            gender=agent.get('gender', 0),
            device_type=agent['device_type'],
            template_id=agent['template_id'],
            template_name=agent.get('template_name'),
            agent_config=agent.get('agent_config', {}),
            status=agent['status'],
            created_at=agent['created_at'].isoformat() if hasattr(agent['created_at'], 'isoformat') else str(agent['created_at']),
            updated_at=agent.get('updated_at').isoformat() if agent.get('updated_at') and hasattr(agent['updated_at'], 'isoformat') else (str(agent['updated_at']) if agent.get('updated_at') else None)
        ))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新agent失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="更新agent失败"
        )

@router.delete("/{agent_id}", response_model=BaseResponse[None])
async def delete_agent(
    agent_id: int,
    current_user = Depends(get_current_user),
    db = Depends(get_db_manager)
):
    """删除agent"""
    try:
        success = await agent_service.delete_agent(db, agent_id, current_user['id'])
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent不存在或删除失败"
            )
        
        return BaseResponse(message="删除成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除agent失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除agent失败"
        )

