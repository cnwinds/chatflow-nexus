#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Agent服务"""

from typing import List, Dict, Any, Optional
from src.common.database.manager import DatabaseManager

class AgentService:
    """Agent服务类"""
    
    async def get_user_agents(self, db: DatabaseManager, user_id: int) -> List[Dict[str, Any]]:
        """获取用户的所有agent列表"""
        sql = """
            SELECT a.id, a.name, a.description, a.avatar, a.gender, a.device_type,
                   a.template_id, a.agent_config, a.status, a.created_at, a.updated_at,
                   t.name as template_name
            FROM agents a
            LEFT JOIN agent_templates t ON a.template_id = t.id
            WHERE a.user_id = :user_id AND a.status != 2
            ORDER BY a.created_at DESC
        """
        return await db.execute_query(sql, {"user_id": user_id})
    
    async def get_agent_detail(self, db: DatabaseManager, agent_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """获取agent详情"""
        sql = """
            SELECT a.id, a.name, a.description, a.avatar, a.gender, a.device_type,
                   a.template_id, a.module_params, a.agent_config, a.memory_data,
                   a.status, a.created_at, a.updated_at,
                   t.name as template_name
            FROM agents a
            LEFT JOIN agent_templates t ON a.template_id = t.id
            WHERE a.id = :agent_id AND a.user_id = :user_id AND a.status != 2
        """
        return await db.execute_one(sql, {"agent_id": agent_id, "user_id": user_id})
    
    async def create_agent(self, db: DatabaseManager, user_id: int, name: str, template_id: int, 
                          device_type: int = 1, description: Optional[str] = None,
                          agent_config: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """创建新agent"""
        import json
        from datetime import datetime
        
        try:
            # 查询模板
            template = await db.execute_one(
                "SELECT * FROM agent_templates WHERE id = :template_id AND status = 1",
                {"template_id": template_id}
            )
            
            if not template:
                # 检查模板是否存在但状态不是1
                template_check = await db.execute_one(
                    "SELECT id, status FROM agent_templates WHERE id = :template_id",
                    {"template_id": template_id}
                )
                if template_check:
                    from loguru import logger
                    logger.warning(f"模板ID {template_id} 存在但状态为 {template_check.get('status')}，无法使用")
                    return None
                else:
                    from loguru import logger
                    logger.warning(f"模板ID {template_id} 不存在")
                    return None
            
            # 获取模板配置
            template_agent_config = template.get('agent_config', {})
            if isinstance(template_agent_config, str):
                try:
                    template_agent_config = json.loads(template_agent_config)
                except json.JSONDecodeError:
                    template_agent_config = {}
            elif template_agent_config is None:
                template_agent_config = {}
            
            # 合并用户提供的配置
            if agent_config:
                # 深度合并配置
                def deep_merge(base: dict, override: dict) -> dict:
                    result = base.copy()
                    for key, value in override.items():
                        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                            result[key] = deep_merge(result[key], value)
                        else:
                            result[key] = value
                    return result
                template_agent_config = deep_merge(template_agent_config, agent_config)
            
            # 从模板的character配置中提取基础信息
            character = template_agent_config.get('profile', {}).get('character', {})
            if not name:
                name = character.get('name', template.get('name', '新智能体'))
            if not description:
                description = character.get('description', template.get('description'))
            
            # 插入agent
            sql = """
            INSERT INTO agents (name, description, avatar, gender, user_id, template_id, 
                              device_type, module_params, agent_config, status, created_at, updated_at)
            VALUES (:name, :description, :avatar, :gender, :user_id, :template_id,
                   :device_type, :module_params, :agent_config, 1, NOW(), NOW())
            """
            
            params = {
                "name": name,
                "description": description,
                "avatar": character.get('avatar_url') or template.get('avatar'),
                "gender": character.get('gender', template.get('gender', 0)),
                "user_id": user_id,
                "template_id": template_id,
                "device_type": device_type,
                "module_params": json.dumps(template.get('module_params', {})),
                "agent_config": json.dumps(template_agent_config, ensure_ascii=False)
            }
            
            agent_id = await db.execute_insert(sql, params)
            
            if not agent_id:
                return None
            
            # 返回创建的agent详情
            return await self.get_agent_detail(db, agent_id, user_id)
            
        except Exception as e:
            from loguru import logger
            logger.error(f"创建agent失败: user_id={user_id}, template_id={template_id}, 错误: {str(e)}")
            return None
    
    async def update_agent(self, db: DatabaseManager, agent_id: int, user_id: int,
                          name: Optional[str] = None, description: Optional[str] = None,
                          agent_config: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """更新agent"""
        import json
        
        update_data = {}
        if name is not None:
            update_data['name'] = name
        if description is not None:
            update_data['description'] = description
        if agent_config is not None:
            update_data['agent_config'] = agent_config
        
        if not update_data:
            return await self.get_agent_detail(db, agent_id, user_id)
        
        # 构建更新SQL
        set_clauses = []
        params = {"agent_id": agent_id, "user_id": user_id}
        
        if 'name' in update_data:
            set_clauses.append("name = :name")
            params["name"] = update_data['name']
        
        if 'description' in update_data:
            set_clauses.append("description = :description")
            params["description"] = update_data['description']
        
        if 'agent_config' in update_data:
            set_clauses.append("agent_config = :agent_config")
            import json
            params["agent_config"] = json.dumps(update_data['agent_config'], ensure_ascii=False)
        
        if not set_clauses:
            return await self.get_agent_detail(db, agent_id, user_id)
        
        set_clauses.append("updated_at = NOW()")
        
        sql = f"""
            UPDATE agents
            SET {', '.join(set_clauses)}
            WHERE id = :agent_id AND user_id = :user_id AND status != 2
        """
        
        affected_rows = await db.execute_update(sql, params)
        if affected_rows == 0:
            return None
        
        return await self.get_agent_detail(db, agent_id, user_id)
    
    async def delete_agent(self, db: DatabaseManager, agent_id: int, user_id: int) -> bool:
        """删除agent（软删除，将status设置为2）"""
        sql = """
            UPDATE agents
            SET status = 2, updated_at = NOW()
            WHERE id = :agent_id AND user_id = :user_id AND status != 2
        """
        affected_rows = await db.execute_update(sql, {"agent_id": agent_id, "user_id": user_id})
        return affected_rows > 0

