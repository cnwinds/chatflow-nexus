"""
每日会话总结
"""
import sys
from pathlib import Path
import asyncio
import json
from src.common.logging import get_logger
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, date

# 确保可以导入 src 模块（当从外部项目加载时）
_file_path = Path(__file__).resolve()
_project_root = _file_path.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from stream_workflow.core import Node, ParameterSchema, StreamChunk, register_node
from stream_workflow.core.parameter import FieldSchema

from src.agents.nodes.daily_summary.repository import (
    GrowthSummaryRepository,
    DAILY_SUMMARY,
)
from src.agents.utcp_tools import call_utcp_tool
from src.common.utils import parse_json_from_llm_response


logger = get_logger(__name__)


@register_node('daily_summary')
class DailySummaryNode(Node):
    """每日会话总结节点。
    
    功能: 定时生成每日会话总结，对当天的所有聊天会话进行汇总和分析。接收定时器触发事件，
    调用 LLM 对当天的会话内容进行总结，提取关键信息和洞察，生成结构化的每日总结报告。
    
    配置参数:
    - system_prompt: 系统提示词（必需），用于定义每日总结生成的角色和总结方向。支持 Jinja2 模板语法。
    - user_prompt: 用户提示词（必需），用于格式化每日总结请求，包含当天的会话内容和总结要求。
      支持 Jinja2 模板语法，可使用变量如 date、conversations、conversation_count 等。
    """
    
    # 节点元信息
    NAME = "每日会话总结"

    EXECUTION_MODE = 'streaming'    # 输入参数定义
    INPUT_PARAMS = {
        "trigger": ParameterSchema(
            is_streaming=True,
            schema={'timestamp': 'string', 'timer_id': 'string', 'data': 'dict'}
        )
    }    # 输出参数定义
    OUTPUT_PARAMS = {

    }
    
    
    # 配置参数定义（使用 FieldSchema 格式）
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

    async def run(self, context):
        """节点执行逻辑"""
        self.context = context
        self.logger = get_logger(__name__)
        
        # 从全局上下文获取配置
        self.engine = context.get_global_var("engine")
        self.db_manager = context.get_global_var("db_manager")
        self.ai_providers = context.get_global_var("ai_providers") or {}
        
        # 获取配置参数
        self.system_prompt = self.get_config("config.system_prompt")
        self.user_prompt = self.get_config("config.user_prompt")
        
        if not self.system_prompt or not self.user_prompt:
            self.logger.error("daily_summary 节点缺少 system_prompt 或 user_prompt 配置")
            return {}
        
        # 初始化repository
        self.repository = GrowthSummaryRepository(self.db_manager)
        
        # 持续运行，等待接收trigger
        await asyncio.sleep(float("inf"))
    
    async def on_chunk_received(self, param_name: str, chunk: StreamChunk):
        """接收到trigger输入时的处理"""
        if param_name != "trigger":
            return
        
        try:
            # 查询需要处理的agent
            pending_agents = await self.repository.get_pending_agents(DAILY_SUMMARY)
            
            if not pending_agents:
                self.logger.info("没有需要处理的agent")
                return
            
            self.logger.info(f"找到 {len(pending_agents)} 个需要处理的agent")
            
            # 批量处理所有agent
            for agent_info in pending_agents:
                agent_id = agent_info.get('agent_id')
                summary_time = agent_info.get('summary_time', '18:00')
                summary_date = agent_info.get('summary_date')
                
                if not agent_id or not summary_date:
                    continue
                
                # 重试机制：最多尝试3次
                max_retries = 3
                retry_count = 0
                success = False
                last_error = None
                
                while retry_count < max_retries and not success:
                    try:
                        await self._process_agent_summary(agent_id, summary_date, summary_time)
                        success = True
                        if retry_count == 0:
                            self.logger.info(f"Agent {agent_id} 的每日总结处理成功")
                        else:
                            self.logger.info(
                                f"Agent {agent_id} 的每日总结处理成功（尝试 {retry_count + 1}/{max_retries}）"
                            )
                    except Exception as e:
                        last_error = e
                        retry_count += 1
                        if retry_count < max_retries:
                            # 指数退避：1秒、2秒、4秒
                            delay = 2 ** (retry_count - 1)
                            self.logger.warning(
                                f"处理agent {agent_id} 的每日总结失败（尝试 {retry_count}/{max_retries}），"
                                f"{delay}秒后重试: {e}"
                            )
                            await asyncio.sleep(delay)
                        else:
                            self.logger.error(
                                f"处理agent {agent_id} 的每日总结失败，已重试{max_retries}次: {e}",
                                exc_info=True
                            )
                
                # 如果所有重试都失败，更新记录状态为failed
                if not success:
                    try:
                        await self.repository.update_summary_record(
                            agent_id, 
                            summary_date, 
                            'failed',
                            None,
                            DAILY_SUMMARY,
                        )
                    except Exception as e:
                        self.logger.error(f"更新失败状态记录时出错: {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"处理每日总结触发失败: {e}", exc_info=True)
    
    async def _process_agent_summary(
        self, 
        agent_id: int, 
        summary_date: date, 
        scheduled_time: str
    ):
        """处理单个agent的每日总结
        
        Args:
            agent_id: agent ID
            summary_date: 总结日期
            scheduled_time: 计划执行时间
        """
        # 1. 创建执行记录
        await self.repository.create_summary_record(
            agent_id,
            summary_date,
            scheduled_time,
            DAILY_SUMMARY,
        )
        
        # 2. 查询当天的会话分析结果
        session_analyses = await self.repository.get_daily_session_analysis(agent_id, summary_date)
        
        if not session_analyses:
            # 没有会话，创建空记录
            self.logger.info(f"Agent {agent_id} 在 {summary_date} 没有会话，创建空记录")
            await self.repository.update_summary_record(
                agent_id,
                summary_date,
                'completed',
                None,
                DAILY_SUMMARY,
            )
            return
        
        # 3. 数据聚合
        aggregated_data = self._aggregate_session_data(session_analyses, summary_date)
        
        # 4. 调用LLM生成总结
        summary_content = await self._generate_summary(aggregated_data)
        
        # 5. 保存结果
        summary_content_json = json.dumps(summary_content, ensure_ascii=False) if summary_content else None
        await self.repository.update_summary_record(
            agent_id,
            summary_date,
            'completed',
            summary_content_json,
            DAILY_SUMMARY,
        )
        
        self.logger.info(f"Agent {agent_id} 的每日总结已完成")
    
    def _aggregate_session_data(
        self, 
        session_analyses: List[Dict[str, Any]], 
        summary_date: date
    ) -> Dict[str, Any]:
        """聚合会话分析数据
        
        Args:
            session_analyses: 会话分析结果列表
            summary_date: 总结日期
            
        Returns:
            聚合后的数据字典
        """
        total_duration = 0
        all_themes = []
        all_sentiments = []
        all_interests = []
        sessions = []
        
        for session_analysis in session_analyses:
            # 累计对话时长
            duration = session_analysis.get('conversation_duration', 0) or 0
            total_duration += duration
            
            # 解析analysis_result
            analysis_result = session_analysis.get('analysis_result')
            if not analysis_result or not isinstance(analysis_result, dict):
                continue
            
            session_analysis_list = analysis_result.get('session_analysis', [])
            if not isinstance(session_analysis_list, list):
                continue
            
            # 处理每个分析项
            for item in session_analysis_list:
                theme = item.get('theme')
                if theme:
                    all_themes.append(theme)
                
                sentiment = item.get('sentiment_intensity')
                if sentiment is not None:
                    all_sentiments.append(sentiment)
                
                interest = item.get('interest_intensity')
                if interest is not None:
                    all_interests.append(interest)
                
                # 构建会话详情
                session_detail = {
                    'theme': theme,
                    'situation_modes': item.get('situation_modes', []),
                    'golden_sentences': item.get('golden_sentences', []),
                    'content_summary': item.get('content_summary', ''),
                    'keywords': item.get('keywords', [])
                }
                sessions.append(session_detail)
        
        # 计算平均值
        avg_sentiment = sum(all_sentiments) / len(all_sentiments) if all_sentiments else 0
        avg_interest = sum(all_interests) / len(all_interests) if all_interests else 0
        
        # 去重主题列表
        theme_list = list(set(all_themes))
        
        return {
            'date': summary_date.strftime('%Y-%m-%d'),
            'conversation_count': len(session_analyses),
            'total_duration': total_duration,
            'theme_list': theme_list,
            'avg_sentiment': round(avg_sentiment, 2),
            'avg_interest': round(avg_interest, 2),
            'sessions': sessions
        }
    
    async def _generate_summary(self, aggregated_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """调用LLM生成总结
        
        Args:
            aggregated_data: 聚合后的数据
            
        Returns:
            LLM返回的总结内容（JSON格式）
        """
        try:
            # 获取LLM服务配置
            service_name, model_name = self._get_llm_completion_service("analysis")
            if not service_name:
                self.logger.error("无法获取LLM服务配置，跳过总结生成")
                return None
            
            # 使用Jinja2模板渲染提示词
            system_prompt_text = self.engine.render_template(self.system_prompt, **aggregated_data)
            user_prompt_text = self.engine.render_template(self.user_prompt, **aggregated_data)
            
            # 调用LLM
            params = {
                "messages": [
                    {"role": "system", "content": system_prompt_text},
                    {"role": "user", "content": user_prompt_text},
                ],
                "model": model_name,
                "max_tokens": 2000,
                "temperature": 1.0,
                "top_p": 1.0,
            }
            
            resp = await call_utcp_tool(f"{service_name}.chat_completion", params)
            content = (resp or {}).get("content", "").strip()
            
            if not content:
                self.logger.warning("LLM返回内容为空")
                return None
            
            # 尝试解析JSON
            try:
                summary_result = parse_json_from_llm_response(content)
                return summary_result
            except ValueError as e:
                snippet = content[:200]
                self.logger.error(f"解析LLM返回的JSON失败: {e}, 内容: {snippet}")
                # 如果解析失败，返回原始内容
                return {"raw_content": content}
                
        except Exception as e:
            self.logger.error(f"调用LLM生成总结失败: {e}", exc_info=True)
            return None
    
    def _get_llm_completion_service(self, model_key: str = "analysis") -> Tuple[str, str]:
        """从全局变量 ai_providers 读取配置，返回服务名和模型名"""
        try:
            llm_cfg = self.ai_providers.get("llm", {})
            model_config = llm_cfg.get(model_key)
            if not model_config:
                return ("", "")
            
            if "." in model_config:
                parts = model_config.split(".", 1)
                return (parts[0], parts[1])
            else:
                return (model_config, model_key)
        except Exception:
            return ("", "")