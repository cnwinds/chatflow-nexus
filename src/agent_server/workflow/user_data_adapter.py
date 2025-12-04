#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""UserData适配器 - 从agent_id加载配置"""

import json
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

from src.common.database.manager import DatabaseManager
from src.agents.user_data import Config, Memory, UserData


class AgentUserDataAdapter(UserData):
    """Agent UserData适配器 - 从agent_id加载配置，而不是device_id"""
    
    async def load_from_agent_id(self, agent_id: int) -> bool:
        """通过agent_id加载用户数据
        
        Args:
            agent_id: Agent ID
            
        Returns:
            bool: 是否加载成功
        """
        self.logger.info(f"开始加载Agent配置: agent_id={agent_id}")
        
        try:
            # 查询Agent、用户信息
            sql = """
                SELECT 
                    a.id as agent_id,
                    a.name as agent_name,
                    a.agent_config,
                    a.memory_data,
                    a.gender as agent_gender,
                    a.user_id,
                    a.device_id,
                    u.user_name as user_name,
                    at.name as template_name,
                    at.agent_config as template_agent_config
                FROM agents a
                LEFT JOIN users u ON a.user_id = u.id
                LEFT JOIN agent_templates at ON a.template_id = at.id
                WHERE a.id = :agent_id 
                AND a.status = 1
                AND u.status = 1
                LIMIT 1
            """
            
            result = await self.db_manager.execute_query(sql, {"agent_id": agent_id})
            
            if not result:
                self.logger.warning(f"未找到Agent {agent_id} 的有效配置")
                return False
            
            agent_info = result[0]
            
            # 设置信息（使用agent_id作为device_id的替代）
            self.device_id = agent_info['agent_id']  # 使用agent_id作为标识
            self.device_name = agent_info['agent_name']
            self.device_type = 0  # 默认类型
            self.user_id = agent_info['user_id']
            self.user_name = agent_info['user_name']
            self.agent_id = agent_info['agent_id']
            self.agent_name = agent_info['agent_name']
            self.agent_gender = agent_info['agent_gender']
            
            # 加载配置和记忆数据
            await self._load_user_config_from_agent(agent_info)
            await self._load_user_memory_from_agent(agent_info)
            self._config_loaded = True
            self._user_config_modified = False
            self._user_memory_modified = False
            
            # 计算孩子年龄
            birth_date = self.get_config("profile.child_info.birth_date")
            if birth_date:
                self.set_config("profile.child_info._age", self.calculate_age_from_birth_date(birth_date))
            
            # 加载克隆声音信息
            await self._load_clone_voices()
            
            # 设置 AI 提供者
            self.ai_providers = self._get_merged_ai_providers()
            
            self.logger.info(f"Agent配置加载完成: agent_id={agent_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"加载Agent配置失败: agent_id={agent_id}, 错误: {str(e)}")
            return False
    
    async def _load_user_config_from_agent(self, agent_info: Dict[str, Any]) -> None:
        """从Agent信息加载配置"""
        try:
            # 获取Agent配置
            agent_config = agent_info.get('agent_config', {})
            if isinstance(agent_config, str):
                try:
                    agent_config = json.loads(agent_config)
                except json.JSONDecodeError:
                    agent_config = {}
            elif agent_config is None:
                agent_config = {}
            
            # 获取模板配置（作为默认值）
            template_config = agent_info.get('template_agent_config', {})
            if isinstance(template_config, str):
                try:
                    template_config = json.loads(template_config)
                except json.JSONDecodeError:
                    template_config = {}
            elif template_config is None:
                template_config = {}
            
            # 合并配置（agent_config优先）
            merged_config = self._deep_merge(template_config, agent_config)
            
            # 创建Config对象
            self._user_config = Config.from_dict(merged_config)
            
        except Exception as e:
            self.logger.error(f"加载Agent配置失败: {str(e)}")
            self._user_config = Config()
    
    async def _load_user_memory_from_agent(self, agent_info: Dict[str, Any]) -> None:
        """从Agent信息加载记忆数据"""
        try:
            memory_data = agent_info.get('memory_data', {})
            if isinstance(memory_data, str):
                try:
                    memory_data = json.loads(memory_data)
                except json.JSONDecodeError:
                    memory_data = {}
            elif memory_data is None:
                memory_data = {}
            
            # 创建Memory对象
            self._user_memory = Memory.from_dict(memory_data)
            
        except Exception as e:
            self.logger.error(f"加载Agent记忆数据失败: {str(e)}")
            self._user_memory = Memory()
    
    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """深度合并字典"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

