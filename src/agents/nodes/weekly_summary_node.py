"""
每周会话总结
"""
import sys
from pathlib import Path
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, date, timedelta

# 确保可以导入 src 模块（当从外部项目加载时）
_file_path = Path(__file__).resolve()
_project_root = _file_path.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from stream_workflow.core import Node, ParameterSchema, StreamChunk, register_node
from stream_workflow.core.parameter import FieldSchema

from src.agents.nodes.daily_summary.repository import (
    GrowthSummaryRepository,
    WEEKLY_SUMMARY,
)
from src.agents.utcp_tools import call_utcp_tool


logger = logging.getLogger(__name__)


@register_node('weekly_summary')
class WeeklySummaryNode(Node):
    """每周会话总结节点。
    
    功能: 定时生成每周会话总结，对一周内的所有聊天会话进行汇总和分析。接收定时器触发事件，
    调用 LLM 对一周的会话内容进行总结，提取关键信息和趋势，生成结构化的每周总结报告。
    
    配置参数:
    - system_prompt: 系统提示词（必需），用于定义每周总结生成的角色和总结方向。支持 Jinja2 模板语法。
    - user_prompt: 用户提示词（必需），用于格式化每周总结请求，包含一周的会话内容和总结要求。
      支持 Jinja2 模板语法，可使用变量如 week_start_date、week_end_date、conversations、conversation_count 等。
    """
    
    # 节点元信息
    NAME = "每周总结"
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
        self.logger = logging.getLogger(__name__)
        
        # 从全局上下文获取配置
        self.engine = context.get_global_var("engine")
        self.db_manager = context.get_global_var("db_manager")
        self.ai_providers = context.get_global_var("ai_providers") or {}
        
        # 获取配置参数
        self.system_prompt = self.get_config("config.system_prompt")
        self.user_prompt = self.get_config("config.user_prompt")
        
        if not self.system_prompt or not self.user_prompt:
            self.logger.error("weekly_summary 节点缺少 system_prompt 或 user_prompt 配置")
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
            # 计算上周的日期范围（周一到周日）
            today = date.today()
            # 获取上周一
            days_since_monday = today.weekday()
            last_monday = today - timedelta(days=days_since_monday + 7)
            last_sunday = last_monday + timedelta(days=6)
            
            week_start_date = last_monday
            week_end_date = last_sunday
            
            self.logger.info(f"开始生成周报: {week_start_date} 到 {week_end_date}")
            
            # 查询所有正常状态的agent
            try:
                sql = """
                SELECT id as agent_id
                FROM agents
                WHERE status = 1
                """
                agents = await self.db_manager.execute_query(sql, {})
            except Exception as e:
                self.logger.error(f"查询agent列表失败: {e}", exc_info=True)
                return
            
            if not agents:
                self.logger.info("没有需要处理的agent")
                return
            
            # 批量处理所有agent
            for agent_info in agents:
                agent_id = agent_info.get('agent_id')
                if not agent_id:
                    continue
                
                # 重试机制：最多尝试3次
                max_retries = 3
                retry_count = 0
                success = False
                last_error = None
                
                while retry_count < max_retries and not success:
                    try:
                        await self._process_agent_weekly_summary(
                            agent_id, week_start_date, week_end_date
                        )
                        success = True
                        self.logger.info(f"Agent {agent_id} 的每周总结处理成功（尝试 {retry_count + 1}/{max_retries}）")
                    except Exception as e:
                        last_error = e
                        retry_count += 1
                        if retry_count < max_retries:
                            # 指数退避：1秒、2秒、4秒
                            delay = 2 ** (retry_count - 1)
                            self.logger.warning(
                                f"处理agent {agent_id} 的每周总结失败（尝试 {retry_count}/{max_retries}），"
                                f"{delay}秒后重试: {e}"
                            )
                            await asyncio.sleep(delay)
                        else:
                            self.logger.error(
                                f"处理agent {agent_id} 的每周总结失败，已重试{max_retries}次: {e}",
                                exc_info=True
                            )
                
                # 如果所有重试都失败，更新记录状态为failed
                if not success:
                    try:
                        await self.repository.update_summary_record(
                            agent_id,
                            week_end_date,
                            'failed',
                            None,
                            WEEKLY_SUMMARY,
                        )
                    except Exception as e:
                        self.logger.error(f"更新失败状态记录时出错: {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"处理每周总结触发失败: {e}", exc_info=True)
    
    async def _process_agent_weekly_summary(
        self, 
        agent_id: int, 
        week_start_date: date, 
        week_end_date: date
    ):
        """处理单个agent的每周总结
        
        Args:
            agent_id: agent ID
            week_start_date: 周开始日期
            week_end_date: 周结束日期
        """
        # 0. 跳过已完成的记录
        existing_record = await self.repository.get_summary_record(
            agent_id, week_end_date, WEEKLY_SUMMARY
        )
        if existing_record and existing_record.get("status") == "completed":
            self.logger.info(
                f"Agent {agent_id} 在 {week_start_date} - {week_end_date} 的周总结已完成，跳过"
            )
            return

        scheduled_time = datetime.now().strftime("%H:%M")
        await self.repository.create_summary_record(
            agent_id,
            week_end_date,
            scheduled_time,
            WEEKLY_SUMMARY,
        )

        # 1. 查询一周内的会话分析结果
        session_analyses = await self.repository.get_weekly_session_analysis(
            agent_id, 
            week_start_date, 
            week_end_date
        )
        
        if not session_analyses:
            # 没有会话，跳过
            self.logger.info(f"Agent {agent_id} 在 {week_start_date} 到 {week_end_date} 没有会话，跳过")
            await self.repository.update_summary_record(
                agent_id,
                week_end_date,
                "completed",
                None,
                WEEKLY_SUMMARY,
            )
            return
        
        # 2. 数据聚合
        aggregated_data = self._aggregate_weekly_data(session_analyses, week_start_date, week_end_date)
        
        # 3. 调用LLM生成总结
        summary_content = await self._generate_summary(aggregated_data)

        summary_payload = {
            "week_start_date": aggregated_data["week_start_date"],
            "week_end_date": aggregated_data["week_end_date"],
            "summary_text": summary_content,
            "aggregated_data": aggregated_data,
        }
        summary_json = json.dumps(summary_payload, ensure_ascii=False)
        await self.repository.update_summary_record(
            agent_id,
            week_end_date,
            "completed",
            summary_json,
            WEEKLY_SUMMARY,
        )
        
        self.logger.info(f"Agent {agent_id} 的每周总结已完成: {len(summary_content) if summary_content else 0} 字符")
    
    def _aggregate_weekly_data(
        self, 
        session_analyses: List[Dict[str, Any]], 
        week_start_date: date,
        week_end_date: date
    ) -> Dict[str, Any]:
        """聚合一周的会话分析数据
        
        Args:
            session_analyses: 会话分析结果列表
            week_start_date: 周开始日期
            week_end_date: 周结束日期
            
        Returns:
            聚合后的数据字典
        """
        total_duration_week = 0
        all_themes = []
        all_sentiments = []
        all_interests = []
        all_situation_modes = []
        sentence_lengths_by_day = {}  # {date: [lengths]}
        sessions = []
        
        for session_analysis in session_analyses:
            # 累计对话时长
            duration = session_analysis.get('conversation_duration', 0) or 0
            total_duration_week += duration
            
            # 获取创建日期
            created_at = session_analysis.get('created_at')
            if isinstance(created_at, datetime):
                session_date = created_at.date()
            elif isinstance(created_at, date):
                session_date = created_at
            else:
                session_date = week_start_date
            
            # 记录平均句长
            avg_length = session_analysis.get('avg_child_sentence_length')
            if avg_length is not None:
                if session_date not in sentence_lengths_by_day:
                    sentence_lengths_by_day[session_date] = []
                sentence_lengths_by_day[session_date].append(avg_length)
            
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
                
                situation_modes = item.get('situation_modes', [])
                if isinstance(situation_modes, list):
                    all_situation_modes.extend(situation_modes)
                
                # 构建会话详情
                session_detail = {
                    'theme': theme,
                    'situation_modes': situation_modes,
                    'golden_sentences': item.get('golden_sentences', []),
                    'content_summary': item.get('content_summary', ''),
                    'keywords': item.get('keywords', []),
                    'interest_intensity': interest,
                    'sentiment_intensity': sentiment
                }
                sessions.append(session_detail)
        
        # 计算平均值
        avg_sentiment = sum(all_sentiments) / len(all_sentiments) if all_sentiments else 0
        
        # 统计主题频率和兴趣分数
        theme_scores = {}
        for session in sessions:
            theme = session.get('theme')
            interest = session.get('interest_intensity', 0)
            if theme:
                if theme not in theme_scores:
                    theme_scores[theme] = {'count': 0, 'total_interest': 0, 'keywords': set()}
                theme_scores[theme]['count'] += 1
                theme_scores[theme]['total_interest'] += interest
                keywords = session.get('keywords', [])
                if isinstance(keywords, list):
                    theme_scores[theme]['keywords'].update(keywords)
        
        # 排序主题（按兴趣分数）
        sorted_themes = sorted(
            theme_scores.items(),
            key=lambda x: x[1]['total_interest'] / x[1]['count'] if x[1]['count'] > 0 else 0,
            reverse=True
        )
        
        # Top 3 主题
        top_themes = []
        for i, (theme, data) in enumerate(sorted_themes[:3], 1):
            avg_interest = data['total_interest'] / data['count'] if data['count'] > 0 else 0
            top_themes.append({
                'rank': i,
                'theme': theme,
                'score': round(avg_interest, 2),
                'keywords': list(data['keywords'])[:5]  # 最多5个关键词
            })
        
        # 计算思维模式分布
        mode_counts = {}
        for mode in all_situation_modes:
            mode_counts[mode] = mode_counts.get(mode, 0) + 1
        
        total_modes = len(all_situation_modes) if all_situation_modes else 1
        percent_imagination = round((mode_counts.get('想象与虚构', 0) / total_modes) * 100, 1)
        percent_knowledge = round((mode_counts.get('求知与探索', 0) / total_modes) * 100, 1)
        percent_social = round((mode_counts.get('生活与社交', 0) / total_modes) * 100, 1)
        
        # 计算平均句长变化趋势（周一 vs 周日）
        monday_lengths = sentence_lengths_by_day.get(week_start_date, [])
        sunday_lengths = sentence_lengths_by_day.get(week_end_date, [])
        
        len_mon = round(sum(monday_lengths) / len(monday_lengths), 1) if monday_lengths else 0
        len_sun = round(sum(sunday_lengths) / len(sunday_lengths), 1) if sunday_lengths else 0
        
        # 计算情感趋势（简化：整体平均）
        sentiment_trend = "整体积极" if avg_sentiment > 0 else "整体中性" if avg_sentiment == 0 else "整体消极"
        
        return {
            'week_start_date': week_start_date.strftime('%Y-%m-%d'),
            'week_end_date': week_end_date.strftime('%Y-%m-%d'),
            'conversation_count': len(session_analyses),
            'total_duration_week': total_duration_week,
            'len_mon': len_mon,
            'len_sun': len_sun,
            'sentiment_trend': sentiment_trend,
            'percent_imagination': percent_imagination,
            'percent_knowledge': percent_knowledge,
            'percent_social': percent_social,
            'top1_theme': top_themes[0]['theme'] if len(top_themes) > 0 else '',
            'top1_score': top_themes[0]['score'] if len(top_themes) > 0 else 0,
            'top1_keywords': ', '.join(top_themes[0]['keywords']) if len(top_themes) > 0 and top_themes[0]['keywords'] else '',
            'top2_theme': top_themes[1]['theme'] if len(top_themes) > 1 else '',
            'top2_score': top_themes[1]['score'] if len(top_themes) > 1 else 0,
            'top3_theme': top_themes[2]['theme'] if len(top_themes) > 2 else '',
            'top3_score': top_themes[2]['score'] if len(top_themes) > 2 else 0,
            'sessions': sessions
        }
    
    async def _generate_summary(self, aggregated_data: Dict[str, Any]) -> Optional[str]:
        """调用LLM生成总结
        
        Args:
            aggregated_data: 聚合后的数据
            
        Returns:
            LLM返回的总结内容
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
                "max_tokens": 3000,
                "temperature": 1.0,
                "top_p": 1.0,
            }
            
            resp = await call_utcp_tool(f"{service_name}.chat_completion", params)
            content = (resp or {}).get("content", "").strip()
            
            return content if content else None
                
        except Exception as e:
            self.logger.error(f"调用LLM生成周报失败: {e}", exc_info=True)
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