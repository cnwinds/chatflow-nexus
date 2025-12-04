"""
会话分析节点

负责执行会话分析任务，包含两种任务来源：
1. 启动时自动恢复 pending 状态的任务
2. 运行时接收来自外部的任务

输入:
- task_stream: 流式输入，包含 session_id, agent_id, copilot_mode

输出:
- 无（结果直接保存到数据库）
"""

import sys
from pathlib import Path
import asyncio
import logging
from typing import Any, Dict, Optional

# 确保可以导入 src 模块（当从外部项目加载时）
_file_path = Path(__file__).resolve()
_project_root = _file_path.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from stream_workflow.core import Node, ParameterSchema, StreamChunk, register_node
from stream_workflow.core.parameter import FieldSchema

from src.agents.nodes.analysis.analyzer import SessionAnalyzer
from src.agents.nodes.analysis.repository import SessionAnalysisRepository
from src.agents.nodes.analysis.retry_manager import RetryManager, RetryConfig


logger = logging.getLogger(__name__)


@register_node("analysis_node")
class AnalysisNode(Node):
    """会话分析节点。
    
    功能: 对会话进行自动分析，提取会话的关键信息和洞察。接收分析任务（包含 session_id、agent_id、copilot_mode），
    调用 LLM 对会话内容进行分析，将分析结果保存到数据库。支持系统启动时自动恢复未完成的分析任务，
    具备重试机制，确保分析任务的可靠执行。分析结果可用于后续的数据统计和用户洞察。
    
    配置参数:
    - system_prompt: 系统提示词（必需），用于定义分析任务的角色和分析方向。支持 Jinja2 模板语法。
    - user_prompt: 用户提示词（必需），用于格式化分析请求，包含会话内容和分析要求。支持 Jinja2 模板语法，
      可使用变量如 session_id、conversation_content、agent_id、copilot_mode 等。
    """
    
    EXECUTION_MODE = "streaming"    # 输入参数定义
    INPUT_PARAMS = {
        "task_stream": ParameterSchema(
            is_streaming=True,
            schema={'session_id': 'string', 'agent_id': 'integer', 'copilot_mode': 'boolean'}
        )
    }    # 输出参数定义
    OUTPUT_PARAMS = {

    }    # 配置参数定义（使用 FieldSchema 格式）
    CONFIG_PARAMS = {
        "system_prompt": FieldSchema({
            'type': 'string',
            'required': True,
            'description': '系统提示词'
        }),
        "user_prompt": FieldSchema({
            'type': 'string',
            'required': True,
            'description': '用户提示词'
        })
    }
    
    async def initialize(self, context):
        """初始化节点"""
        self.context = context
        self._logger = logging.getLogger(__name__)
        
        # 从全局上下文获取engine
        self.engine = context.get_global_var("engine")
        
        self.system_prompt = self.get_config("config.system_prompt")
        self.user_prompt_template = self.get_config("config.user_prompt")
        if not self.system_prompt or not self.user_prompt_template:
            raise ValueError("analysis_node 缺少 system_prompt 或 user_prompt 配置")
        
        # 初始化组件
        self.repository = SessionAnalysisRepository()
        self.analyzer = SessionAnalyzer(
            system_prompt=self.system_prompt,
            user_prompt_template=self.user_prompt_template,
            engine=self.engine
        )
        
        # 初始化重试管理器
        retry_config = RetryConfig(
            max_attempts=3,
            base_delay=1.0,
            max_delay=60.0,
            exponential_base=2.0,
            jitter=True
        )
        self.retry_manager = RetryManager(retry_config)
        
        self._logger.info("分析节点已初始化")
    
    async def run(self, context):
        """运行节点"""
        self.context = context
        
        # 1. 启动时恢复逻辑
        await self._recover_unfinished_tasks()
        
        # 2. 持续运行，等待接收任务
        await asyncio.sleep(float("inf"))
    
    async def _recover_unfinished_tasks(self):
        """恢复未完成的任务（系统启动时调用）"""
        try:
            # 1. 将处理中的任务重置为待处理（系统崩溃恢复）
            reset_count = await self.repository.reset_processing_to_pending()
            
            # 2. 获取待处理的任务
            pending_tasks = await self.repository.get_pending_analyses(limit=1000)
            
            if reset_count > 0 or pending_tasks:
                self._logger.info(
                    f"系统启动恢复：发现 {len(pending_tasks)} 个待处理任务，"
                    f"已重置 {reset_count} 个处理中任务"
                )
            else:
                self._logger.debug("系统启动恢复：未发现未完成的任务")
            
            # 3. 自动执行待处理的任务
            for task in pending_tasks:
                session_id = task.get('session_id')
                if session_id:
                    # 异步处理任务，不阻塞
                    asyncio.create_task(self._process_task(session_id))
            
        except Exception as e:
            self._logger.error(f"恢复未完成任务失败: {e}", exc_info=True)
    
    async def on_chunk_received(self, param_name: str, chunk: StreamChunk):
        """接收到任务时的处理"""
        if param_name == "task_stream":
            task_data = chunk.data or {}
            session_id = task_data.get("session_id")
            
            if session_id:
                # 异步处理任务，不阻塞
                asyncio.create_task(self._process_task(session_id))
            else:
                self._logger.warning(f"收到无效任务数据: {task_data}")
    
    async def _process_task(self, session_id: str):
        """处理单个分析任务
        
        Args:
            session_id: 会话ID
        """
        try:
            self._logger.info(f"开始处理分析任务: session_id={session_id}")
            
            # 1. 更新状态为处理中
            await self.repository.update_analysis_status(session_id, "processing")
            
            # 2. 执行分析（带重试机制）
            success, result, error_msg = await self.retry_manager.process_with_retry(
                lambda: self.analyzer.analyze_conversation(session_id),
                task_name=f"分析会话 {session_id}"
            )
            
            # 3. 检查是否跳过
            if result and isinstance(result, dict) and result.get("skipped"):
                reason = result.get("reason", "未知原因")
                await self.repository.mark_as_skipped(session_id, reason)
                self._logger.info(f"分析已跳过: session_id={session_id}, 原因: {reason}")
                return
            
            # 4. 处理分析结果
            if success and result:
                # 保存分析结果
                await self.repository.save_analysis_result(
                    session_id,
                    result.get("analysis_result"),
                    result.get("conversation_duration"),
                    result.get("avg_child_sentence_length")
                )
                self._logger.info(f"分析任务完成: session_id={session_id}")
            else:
                # 更新为失败状态
                await self.repository.update_analysis_status(
                    session_id,
                    "failed",
                    error_msg or "分析失败"
                )
                self._logger.warning(f"分析任务失败: session_id={session_id}, 错误: {error_msg}")
        
        except Exception as e:
            self._logger.error(f"处理分析任务异常: session_id={session_id}, 错误: {e}", exc_info=True)
            try:
                await self.repository.update_analysis_status(
                    session_id,
                    "failed",
                    str(e)
                )
            except Exception as update_error:
                self._logger.error(f"更新任务状态失败: {update_error}")

