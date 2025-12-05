"""
系统工作流管理器

管理系统级别工作流的生命周期，提供向工作流发送任务的接口
"""

import asyncio
import yaml
from pathlib import Path
from typing import Optional

from stream_workflow.core import WorkflowEngine
from src.common.config import get_config_manager
from src.common.config.constants import ConfigPaths
from src.common.logging import get_logger

# 触发自定义节点注册（必须在模块级别）
from .nodes import *  # noqa: F401, F403


logger = get_logger(__name__)


class SystemWorkflowManager:
    """系统工作流管理器 - 管理系统级别的后台工作流"""
    
    _instance: Optional['SystemWorkflowManager'] = None
    _lock = asyncio.Lock()
    
    def __init__(self):
        """初始化系统工作流管理器"""
        self.engine: Optional[WorkflowEngine] = None
        self.context = None
        self._running = False
        self._logger = get_logger(__name__)
    
    @classmethod
    async def get_instance(cls) -> 'SystemWorkflowManager':
        """获取单例实例"""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    async def start(self):
        """启动系统工作流"""
        if self._running:
            self._logger.warning("系统工作流已经在运行")
            return
        
        try:
            # 加载工作流配置
            config_path = Path(__file__).parent / "workflows" / "workflow_system.yaml"
            
            if not config_path.exists():
                self._logger.error(f"系统工作流配置文件不存在: {config_path}")
                return False
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config_dict = yaml.safe_load(f)
            
            # 创建并启动工作流引擎
            self.engine = WorkflowEngine()
            self.engine.load_config_dict(config_dict)
            
            # 启动工作流（系统工作流不需要特殊的全局变量）
            # 从全局配置获取 ai_providers
            config_manager = get_config_manager()
            global_ai_providers = config_manager.get_config(ConfigPaths.CHAT_AI_PROVIDERS) or {}
            
            initial_data = {
                "ai_providers": global_ai_providers
            }
            self.context = await self.engine.start(initial_data=initial_data)
            
            self._running = True
            self._logger.info("系统工作流已启动")
            return True
            
        except Exception as e:
            self._logger.error(f"启动系统工作流失败: {e}", exc_info=True)
            return False
    
    async def stop(self):
        """停止系统工作流"""
        if not self._running:
            return
        
        try:
            if self.engine:
                await self.engine.stop()
                self.engine = None
            
            self._running = False
            self._logger.info("系统工作流已停止")
            
        except Exception as e:
            self._logger.error(f"停止系统工作流失败: {e}", exc_info=True)
    
    async def send_analysis_task(self, session_id: str, agent_id: int, copilot_mode: bool = False):
        """发送分析任务到系统工作流
        
        Args:
            session_id: 会话ID
            agent_id: 智能体ID
            copilot_mode: 是否copilot模式
        """
        if not self._running or not self.engine:
            self._logger.warning("系统工作流未运行，无法发送任务")
            return False
        
        try:
            # 获取分析节点
            analysis_node = self.engine.get_node("analysis")
            if not analysis_node:
                self._logger.error("未找到分析节点")
                return False
            
            # 发送任务到分析节点
            await analysis_node.feed_input_chunk("task_stream", {
                "session_id": session_id,
                "agent_id": agent_id,
                "copilot_mode": copilot_mode
            })
            
            self._logger.debug(f"已发送分析任务: session_id={session_id}, agent_id={agent_id}")
            return True
            
        except Exception as e:
            self._logger.error(f"发送分析任务失败: {e}", exc_info=True)
            return False
    
    @property
    def is_running(self) -> bool:
        """检查系统工作流是否正在运行"""
        return self._running


# 全局实例获取函数
async def get_system_workflow_manager() -> SystemWorkflowManager:
    """获取系统工作流管理器实例"""
    return await SystemWorkflowManager.get_instance()

