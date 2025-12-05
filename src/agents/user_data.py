#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""UserData模块占位实现"""

import json
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, date
from src.common.logging import get_logger


@dataclass
class Config:
    """配置类"""
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Config':
        """从字典创建Config对象"""
        return cls()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {}


@dataclass
class Memory:
    """记忆类"""
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Memory':
        """从字典创建Memory对象"""
        return cls()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {}


class UserData:
    """用户数据基类"""
    
    def __init__(self, db_manager=None):
        self.db_manager = db_manager
        self.logger = get_logger(self.__class__.__name__)
        
        # 用户信息
        self.user_id: Optional[int] = None
        self.user_name: Optional[str] = None
        
        # Agent信息
        self.agent_id: Optional[int] = None
        self.agent_name: Optional[str] = None
        self.agent_gender: int = 0
        
        # 配置和记忆
        self._user_config: Config = Config()
        self._user_memory: Memory = Memory()
        self._config_loaded: bool = False
        self._user_config_modified: bool = False
        self._user_memory_modified: bool = False
        
        # AI提供者
        self.ai_providers: Dict[str, Any] = {}
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        # 简单的点号分隔键访问
        keys = key.split('.')
        value = self._user_config.to_dict()
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, default)
            else:
                return default
        return value if value is not None else default
    
    def set_config(self, key: str, value: Any) -> None:
        """设置配置值"""
        # 简单的点号分隔键设置
        keys = key.split('.')
        config_dict = self._user_config.to_dict()
        current = config_dict
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        current[keys[-1]] = value
        self._user_config = Config.from_dict(config_dict)
        self._user_config_modified = True
    
    def calculate_age_from_birth_date(self, birth_date: str) -> int:
        """从出生日期计算年龄"""
        try:
            if isinstance(birth_date, str):
                birth = datetime.strptime(birth_date, "%Y-%m-%d").date()
            elif isinstance(birth_date, date):
                birth = birth_date
            else:
                return 0
            
            today = date.today()
            age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
            return max(0, age)
        except Exception:
            return 0
    
    def _get_merged_ai_providers(self) -> Dict[str, Any]:
        """获取合并的AI提供者配置"""
        return {}
    
    async def _load_clone_voices(self) -> None:
        """加载克隆声音信息"""
        pass
    
    async def load_from_agent_id(self, agent_id: int) -> bool:
        """通过agent_id加载用户数据
        
        Args:
            agent_id: Agent ID
            
        Returns:
            bool: 是否加载成功
        """
        self.logger.info(f"开始加载Agent配置: agent_id={agent_id}")
        
        try:
            if not self.db_manager:
                self.logger.error("数据库管理器未初始化")
                return False
            
            # 查询Agent、用户信息
            sql = """
                SELECT 
                    a.id as agent_id,
                    a.name as agent_name,
                    a.agent_config,
                    a.memory_data,
                    a.gender as agent_gender,
                    a.user_id,
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
            
            # 设置信息
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
    
    def get_memory(self, key: str, default: Any = None) -> Any:
        """获取记忆值"""
        # 简单的点号分隔键访问
        keys = key.split('.')
        value = self._user_memory.to_dict()
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, default)
            else:
                return default
        return value if value is not None else default
    
    async def save(self) -> bool:
        """保存用户数据到数据库
        
        Returns:
            bool: 是否保存成功
        """
        try:
            if not self.db_manager or not self.agent_id:
                self.logger.warning("数据库管理器或agent_id未初始化，跳过保存")
                return False
            
            # 只保存修改过的配置和记忆
            updates = {}
            
            if self._user_config_modified:
                config_dict = self._user_config.to_dict()
                updates['agent_config'] = json.dumps(config_dict, ensure_ascii=False)
            
            if self._user_memory_modified:
                memory_dict = self._user_memory.to_dict()
                updates['memory_data'] = json.dumps(memory_dict, ensure_ascii=False)
            
            if not updates:
                self.logger.debug("没有需要保存的数据")
                return True
            
            # 更新数据库
            set_clauses = []
            params = {"agent_id": self.agent_id}
            
            for key, value in updates.items():
                set_clauses.append(f"{key} = :{key}")
                params[key] = value
            
            sql = f"""
                UPDATE agents 
                SET {', '.join(set_clauses)}, updated_at = NOW()
                WHERE id = :agent_id
            """
            
            await self.db_manager.execute_update(sql, params)
            
            # 重置修改标志
            self._user_config_modified = False
            self._user_memory_modified = False
            
            self.logger.info(f"用户数据保存成功: agent_id={self.agent_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"保存用户数据失败: agent_id={self.agent_id}, 错误: {str(e)}")
            return False
    
    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """深度合并字典"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

