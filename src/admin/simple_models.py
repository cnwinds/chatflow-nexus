"""
简化的后台管理系统数据模型

不依赖复杂的配置系统，直接使用环境变量
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import os
import logging
import bcrypt

from src.common.database.manager import DatabaseManager

# 获取日志记录器
logger = logging.getLogger(__name__)


@dataclass
class AIMetricsData:
    """AI指标数据模型"""
    id: int
    monitor_id: str
    provider: str
    model_name: str
    session_id: Optional[str]
    start_time: datetime
    end_time: Optional[datetime]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    input_chars: int
    output_chars: int
    tool_count: int
    tool_calls_made: int
    cost: float
    input_cost: float
    output_cost: float
    total_time: float
    http_first_byte_time: Optional[float]
    result: Optional[str]


@dataclass
class MetricsSummary:
    """指标汇总数据"""
    provider: str
    model_name: str
    total_calls: int
    avg_total_time: float
    p95_total_time: float
    max_total_time: float
    min_total_time: float
    total_cost: float
    total_tokens: int


@dataclass
class TimeSeriesData:
    """时间序列数据"""
    date: str
    provider: str
    model_name: str
    avg_total_time: float
    max_total_time: float
    min_total_time: float
    p95_total_time: float
    total_calls: int
    total_cost: float


class SimpleAIMetricsService:
    """简化的AI指标服务类"""
    
    def __init__(self, db_manager: DatabaseManager = None):
        self.db_manager = db_manager
    
    async def get_metrics_by_time_range(
        self, 
        start_date: datetime, 
        end_date: datetime,
        provider: Optional[str] = None,
        model_name: Optional[str] = None
    ) -> List[AIMetricsData]:
        """
        根据时间范围获取AI指标数据
        
        Args:
            start_date: 开始时间
            end_date: 结束时间
            provider: 提供商过滤（可选）
            model_name: 模型名称过滤（可选）
            
        Returns:
            AI指标数据列表
        """
        try:
            if not self.db_manager:
                raise Exception("数据库管理器未初始化")
            
            # 构建查询条件 - 使用SQLAlchemy标准参数格式
            where_conditions = ["start_time >= :start_date", "start_time <= :end_date"]
            params = {"start_date": start_date, "end_date": end_date}
            
            if provider:
                where_conditions.append("provider = :provider")
                params["provider"] = provider
            
            if model_name:
                where_conditions.append("model_name = :model_name")
                params["model_name"] = model_name
            
            query = f"""
            SELECT id, monitor_id, provider, model_name, session_id,
                   start_time, end_time, prompt_tokens, completion_tokens,
                   total_tokens, input_chars, output_chars, tool_count,
                   tool_calls_made, cost, input_cost, output_cost,
                   total_time, http_first_byte_time, result
            FROM ai_metrics
            WHERE {' AND '.join(where_conditions)}
            ORDER BY start_time DESC
            """
            
            # 使用封装的DatabaseManager执行查询
            results = await self.db_manager.execute_query(query, params)
            
            metrics_list = []
            for row in results:
                metrics = AIMetricsData(
                    id=row['id'],
                    monitor_id=row['monitor_id'],
                    provider=row['provider'],
                    model_name=row['model_name'],
                    session_id=row['session_id'],
                    start_time=row['start_time'],
                    end_time=row['end_time'],
                    prompt_tokens=row['prompt_tokens'] or 0,
                    completion_tokens=row['completion_tokens'] or 0,
                    total_tokens=row['total_tokens'] or 0,
                    input_chars=row['input_chars'] or 0,
                    output_chars=row['output_chars'] or 0,
                    tool_count=row['tool_count'] or 0,
                    tool_calls_made=row['tool_calls_made'] or 0,
                    cost=float(row['cost'] or 0),
                    input_cost=float(row['input_cost'] or 0),
                    output_cost=float(row['output_cost'] or 0),
                    total_time=float(row['total_time'] or 0),
                    http_first_byte_time=float(row['http_first_byte_time']) if row['http_first_byte_time'] else None,
                    result=row['result']
                )
                metrics_list.append(metrics)
            
            return metrics_list
                
        except Exception as e:
            raise Exception(f"查询AI指标数据失败: {str(e)}")
    
    async def get_provider_model_summary(
        self, 
        start_date: datetime, 
        end_date: datetime
    ) -> List[MetricsSummary]:
        """
        获取提供商和模型的分组汇总数据
        
        Args:
            start_date: 开始时间
            end_date: 结束时间
            
        Returns:
            汇总数据列表
        """
        try:
            logger.info(f"开始获取提供商模型汇总数据，时间范围: {start_date} 到 {end_date}")
            
            if not self.db_manager:
                logger.error("数据库管理器未初始化")
                raise Exception("数据库管理器未初始化")
            
            query = """
            SELECT provider, model_name,
                   COUNT(*) as total_calls,
                   AVG(total_time) as avg_total_time,
                   MAX(total_time) as max_total_time,
                   MIN(total_time) as min_total_time,
                   SUM(cost) as total_cost,
                   SUM(total_tokens) as total_tokens
            FROM ai_metrics
            WHERE start_time >= :start_date AND start_time <= :end_date
            GROUP BY provider, model_name
            ORDER BY total_calls DESC
            """
            
            params = {"start_date": start_date, "end_date": end_date}
            logger.debug(f"执行查询: {query}, 参数: {params}")
            
            # 使用封装的DatabaseManager执行查询
            results = await self.db_manager.execute_query(query, params)
            
            # 获取原始数据用于计算95分位值
            raw_data = await self._get_raw_summary_data(start_date, end_date)
            
            summary_list = []
            for row in results:
                # 计算95分位值
                p95_time = self._calculate_p95_summary_time(
                    row['provider'] or 'unknown',
                    row['model_name'],
                    raw_data
                )
                
                summary = MetricsSummary(
                    provider=row['provider'] or 'unknown',
                    model_name=row['model_name'],
                    total_calls=int(row['total_calls'] or 0),
                    avg_total_time=float(row['avg_total_time'] or 0),
                    p95_total_time=p95_time,
                    max_total_time=float(row['max_total_time'] or 0),
                    min_total_time=float(row['min_total_time'] or 0),
                    total_cost=float(row['total_cost'] or 0),
                    total_tokens=int(row['total_tokens'] or 0)
                )
                summary_list.append(summary)
            
            logger.info(f"成功获取汇总数据: {len(summary_list)} 条记录")
            return summary_list
                
        except Exception as e:
            logger.error(f"查询汇总数据失败: {str(e)}", exc_info=True)
            raise Exception(f"查询汇总数据失败: {str(e)}")
    
    async def get_time_series_data(
        self, 
        start_date: datetime, 
        end_date: datetime,
        group_by: str = 'day'
    ) -> List[TimeSeriesData]:
        """
        获取时间序列数据用于图表展示
        
        Args:
            start_date: 开始时间
            end_date: 结束时间
            group_by: 分组方式 ('day', 'hour')
            
        Returns:
            时间序列数据列表
        """
        try:
            logger.info(f"开始获取时间序列数据，时间范围: {start_date} 到 {end_date}, 分组: {group_by}")
            
            if not self.db_manager:
                logger.error("数据库管理器未初始化")
                raise Exception("数据库管理器未初始化")
            
            # 根据分组方式选择时间格式化
            if group_by == 'hour':
                time_format = "%Y-%m-%d %H:00:00"
            else:  # day
                time_format = "%Y-%m-%d"
            
            query = """
            SELECT DATE_FORMAT(start_time, :time_format) as date,
                   provider, model_name,
                   AVG(total_time) as avg_total_time,
                   MAX(total_time) as max_total_time,
                   MIN(total_time) as min_total_time,
                   COUNT(*) as total_calls,
                   SUM(cost) as total_cost
            FROM ai_metrics
            WHERE start_time >= :start_date AND start_time <= :end_date
            GROUP BY DATE_FORMAT(start_time, :time_format), provider, model_name
            ORDER BY date, provider, model_name
            """
            
            params = {
                "time_format": time_format,
                "start_date": start_date,
                "end_date": end_date
            }
            
            logger.debug(f"执行查询: {query}, 参数: {params}")
            results = await self.db_manager.execute_query(query, params)
            
            # 获取原始数据用于计算95分位值
            raw_data = await self._get_raw_time_data(start_date, end_date, time_format)
            
            time_series_list = []
            for row in results:
                # 计算95分位值
                p95_time = self._calculate_p95_time(
                    row['date'], 
                    row['provider'] or 'unknown', 
                    row['model_name'], 
                    raw_data
                )
                
                data = TimeSeriesData(
                    date=row['date'],
                    provider=row['provider'] or 'unknown',
                    model_name=row['model_name'],
                    avg_total_time=float(row['avg_total_time'] or 0),
                    max_total_time=float(row['max_total_time'] or 0),
                    min_total_time=float(row['min_total_time'] or 0),
                    p95_total_time=p95_time,
                    total_calls=row['total_calls'],
                    total_cost=float(row['total_cost'] or 0)
                )
                time_series_list.append(data)
            
            logger.info(f"成功获取时间序列数据: {len(time_series_list)} 条记录")
            return time_series_list
                
        except Exception as e:
            logger.error(f"查询时间序列数据失败: {str(e)}", exc_info=True)
            raise Exception(f"查询时间序列数据失败: {str(e)}")
    
    async def _get_raw_time_data(self, start_date: datetime, end_date: datetime, time_format: str) -> dict:
        """获取原始时间数据用于计算95分位值"""
        try:
            query = """
            SELECT DATE_FORMAT(start_time, :time_format) as date,
                   provider, model_name, total_time
            FROM ai_metrics
            WHERE start_time >= :start_date AND start_time <= :end_date
            ORDER BY date, provider, model_name, total_time
            """
            
            params = {
                "time_format": time_format,
                "start_date": start_date,
                "end_date": end_date
            }
            
            results = await self.db_manager.execute_query(query, params)
            
            # 按日期、提供商、模型分组存储时间数据
            raw_data = {}
            for row in results:
                key = (row['date'], row['provider'] or 'unknown', row['model_name'])
                if key not in raw_data:
                    raw_data[key] = []
                raw_data[key].append(float(row['total_time']))
            
            return raw_data
            
        except Exception as e:
            logger.error(f"获取原始时间数据失败: {str(e)}", exc_info=True)
            return {}
    
    def _calculate_p95_time(self, date: str, provider: str, model_name: str, raw_data: dict) -> float:
        """计算95分位值"""
        try:
            key = (date, provider, model_name)
            if key not in raw_data or not raw_data[key]:
                return 0.0
            
            times = raw_data[key]
            if len(times) == 0:
                return 0.0
            
            # 排序
            times.sort()
            
            # 计算95分位值索引
            p95_index = int(len(times) * 0.95)
            if p95_index >= len(times):
                p95_index = len(times) - 1
            
            return float(times[p95_index])
            
        except Exception as e:
            logger.error(f"计算95分位值失败: {str(e)}", exc_info=True)
            return 0.0
    
    async def _get_raw_summary_data(self, start_date: datetime, end_date: datetime) -> dict:
        """获取原始汇总数据用于计算95分位值"""
        try:
            query = """
            SELECT provider, model_name, total_time
            FROM ai_metrics
            WHERE start_time >= :start_date AND start_time <= :end_date
            ORDER BY provider, model_name, total_time
            """
            
            params = {
                "start_date": start_date,
                "end_date": end_date
            }
            
            results = await self.db_manager.execute_query(query, params)
            
            # 按提供商、模型分组存储时间数据
            raw_data = {}
            for row in results:
                key = (row['provider'] or 'unknown', row['model_name'])
                if key not in raw_data:
                    raw_data[key] = []
                raw_data[key].append(float(row['total_time']))
            
            return raw_data
            
        except Exception as e:
            logger.error(f"获取原始汇总数据失败: {str(e)}", exc_info=True)
            return {}
    
    def _calculate_p95_summary_time(self, provider: str, model_name: str, raw_data: dict) -> float:
        """计算汇总数据的95分位值"""
        try:
            key = (provider, model_name)
            if key not in raw_data or not raw_data[key]:
                return 0.0
            
            times = raw_data[key]
            if len(times) == 0:
                return 0.0
            
            # 排序
            times.sort()
            
            # 计算95分位值索引
            p95_index = int(len(times) * 0.95)
            if p95_index >= len(times):
                p95_index = len(times) - 1
            
            return float(times[p95_index])
            
        except Exception as e:
            logger.error(f"计算汇总95分位值失败: {str(e)}", exc_info=True)
            return 0.0
    
    async def get_available_providers(self) -> List[str]:
        """获取可用的提供商列表"""
        try:
            logger.info("开始查询可用的提供商列表")
            
            if not self.db_manager:
                logger.error("数据库管理器未初始化")
                raise Exception("数据库管理器未初始化")
            
            query = """
            SELECT DISTINCT provider 
            FROM ai_metrics 
            WHERE provider IS NOT NULL AND provider != ''
            ORDER BY provider
            """
            
            logger.debug(f"执行查询: {query}")
            results = await self.db_manager.execute_query(query)
            
            providers = [row['provider'] for row in results]
            logger.info(f"成功查询到 {len(providers)} 个提供商: {providers}")
            return providers
                
        except Exception as e:
            logger.error(f"查询提供商列表失败: {str(e)}", exc_info=True)
            raise Exception(f"查询提供商列表失败: {str(e)}")
    
    async def get_available_models(self, provider: Optional[str] = None) -> List[str]:
        """获取可用的模型列表"""
        try:
            logger.info(f"开始查询可用的模型列表，提供商: {provider}")
            
            if not self.db_manager:
                logger.error("数据库管理器未初始化")
                raise Exception("数据库管理器未初始化")
            
            if provider:
                query = """
                SELECT DISTINCT model_name 
                FROM ai_metrics 
                WHERE provider = :provider
                ORDER BY model_name
                """
                params = {"provider": provider}
                logger.debug(f"执行查询: {query}, 参数: {params}")
                results = await self.db_manager.execute_query(query, params)
            else:
                query = """
                SELECT DISTINCT model_name 
                FROM ai_metrics 
                ORDER BY model_name
                """
                logger.debug(f"执行查询: {query}")
                results = await self.db_manager.execute_query(query)
            
            models = [row['model_name'] for row in results]
            logger.info(f"成功查询到 {len(models)} 个模型: {models}")
            return models
                
        except Exception as e:
            logger.error(f"查询模型列表失败: {str(e)}", exc_info=True)
            raise Exception(f"查询模型列表失败: {str(e)}")


@dataclass
class UserData:
    """用户数据模型"""
    id: int
    login_name: str
    user_name: str
    mobile: Optional[str]
    avatar: Optional[str]
    gender: int
    user_type: int
    status: int
    created_at: datetime
    updated_at: datetime


@dataclass
class DeviceData:
    """设备数据模型"""
    id: int
    device_uuid: str
    name: str
    device_type: int
    status: int
    binding_status: int
    battery: int
    volume: int
    ip: Optional[str]
    signal_strength: Optional[int]
    created_at: datetime
    updated_at: datetime
    last_active: Optional[datetime]


@dataclass
class AgentTemplateData:
    """Agent模板数据模型"""
    id: int
    name: str
    description: Optional[str]
    avatar: Optional[str]
    gender: int
    device_type: int
    creator_id: int
    module_params: Optional[Dict[str, Any]]
    agent_config: Optional[Dict[str, Any]]
    status: int
    created_at: datetime
    updated_at: datetime


@dataclass
class AgentData:
    """Agent数据模型"""
    id: int
    name: str
    description: Optional[str]
    avatar: Optional[str]
    gender: int
    user_id: int
    device_id: Optional[int]
    template_id: int
    device_type: int
    agent_config: Optional[Dict[str, Any]]
    module_params: Optional[Dict[str, Any]]
    memory_data: Optional[Dict[str, Any]]
    status: int
    created_at: datetime
    updated_at: datetime
    user_name: Optional[str] = None
    device_uuid: Optional[str] = None
    device_name: Optional[str] = None


class SimpleAgentService:
    """简化的Agent管理服务类"""
    
    def __init__(self, db_manager: DatabaseManager = None):
        self.db_manager = db_manager
    
    async def get_all_agents(self) -> List[AgentData]:
        """
        获取所有agents列表，包含关联的用户和设备信息
        
        Returns:
            Agent数据列表
        """
        try:
            if not self.db_manager:
                raise Exception("数据库管理器未初始化")
            
            query = """
            SELECT 
                a.id, a.name, a.description, a.avatar, a.gender,
                a.user_id, a.device_id, a.template_id, a.device_type,
                a.agent_config, a.module_params, a.memory_data,
                a.status, a.created_at, a.updated_at,
                u.user_name,
                d.device_uuid, d.name as device_name
            FROM agents a
            LEFT JOIN users u ON a.user_id = u.id
            LEFT JOIN devices d ON a.device_id = d.id
            WHERE a.status != 2
            ORDER BY a.created_at DESC
            """
            
            results = await self.db_manager.execute_query(query)
            
            agents_list = []
            for row in results:
                agent = AgentData(
                    id=row['id'],
                    name=row['name'],
                    description=row['description'],
                    avatar=row['avatar'],
                    gender=row['gender'],
                    user_id=row['user_id'],
                    device_id=row['device_id'],
                    template_id=row['template_id'],
                    device_type=row['device_type'],
                    agent_config=row['agent_config'],
                    module_params=row['module_params'],
                    memory_data=row['memory_data'],
                    status=row['status'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    user_name=row['user_name'],
                    device_uuid=row['device_uuid'],
                    device_name=row['device_name']
                )
                agents_list.append(agent)
            
            return agents_list
                
        except Exception as e:
            raise Exception(f"查询agents列表失败: {str(e)}")
    
    async def get_agent_by_id(self, agent_id: int) -> Optional[AgentData]:
        """
        根据ID获取单个agent详情
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Agent数据或None
        """
        try:
            if not self.db_manager:
                raise Exception("数据库管理器未初始化")
            
            query = """
            SELECT 
                a.id, a.name, a.description, a.avatar, a.gender,
                a.user_id, a.device_id, a.template_id, a.device_type,
                a.agent_config, a.module_params, a.memory_data,
                a.status, a.created_at, a.updated_at,
                u.user_name,
                d.device_uuid, d.name as device_name
            FROM agents a
            LEFT JOIN users u ON a.user_id = u.id
            LEFT JOIN devices d ON a.device_id = d.id
            WHERE a.id = :agent_id AND a.status != 2
            """
            
            params = {"agent_id": agent_id}
            results = await self.db_manager.execute_query(query, params)
            
            if not results:
                return None
            
            row = results[0]
            return AgentData(
                id=row['id'],
                name=row['name'],
                description=row['description'],
                avatar=row['avatar'],
                gender=row['gender'],
                user_id=row['user_id'],
                device_id=row['device_id'],
                template_id=row['template_id'],
                device_type=row['device_type'],
                agent_config=row['agent_config'],
                module_params=row['module_params'],
                memory_data=row['memory_data'],
                status=row['status'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                user_name=row['user_name'],
                device_uuid=row['device_uuid'],
                device_name=row['device_name']
            )
                
        except Exception as e:
            raise Exception(f"查询agent详情失败: {str(e)}")
    
    async def update_agent_config(self, agent_id: int, config_json: Dict[str, Any]) -> bool:
        """
        更新agent的agent_config配置
        
        Args:
            agent_id: Agent ID
            config_json: 新的配置JSON
            
        Returns:
            是否更新成功
        """
        try:
            if not self.db_manager:
                raise Exception("数据库管理器未初始化")
            
            # 验证JSON格式
            import json
            json.dumps(config_json)  # 验证JSON是否有效
            
            query = """
            UPDATE agents 
            SET agent_config = :agent_config, updated_at = CURRENT_TIMESTAMP
            WHERE id = :agent_id AND status != 2
            """
            
            params = {
                "agent_id": agent_id,
                "agent_config": json.dumps(config_json, ensure_ascii=False)
            }
            
            result = await self.db_manager.execute_update(query, params)
            return result > 0
                
        except Exception as e:
            raise Exception(f"更新agent配置失败: {str(e)}")
    
    async def update_agent_memory_data(self, agent_id: int, memory_data_json: Dict[str, Any]) -> bool:
        """
        更新agent的memory_data配置
        
        Args:
            agent_id: Agent ID
            memory_data_json: 新的记忆数据JSON
            
        Returns:
            是否更新成功
        """
        try:
            if not self.db_manager:
                raise Exception("数据库管理器未初始化")
            
            # 验证JSON格式
            import json
            json.dumps(memory_data_json)  # 验证JSON是否有效
            
            query = """
            UPDATE agents 
            SET memory_data = :memory_data, updated_at = CURRENT_TIMESTAMP
            WHERE id = :agent_id AND status != 2
            """
            
            params = {
                "agent_id": agent_id,
                "memory_data": json.dumps(memory_data_json, ensure_ascii=False)
            }
            
            result = await self.db_manager.execute_update(query, params)
            return result > 0
                
        except Exception as e:
            raise Exception(f"更新agent记忆数据失败: {str(e)}")
    
    async def update_agent_basic_info(self, agent_id: int, name: str = None, description: str = None, 
                                avatar: str = None, gender: int = None) -> bool:
        """
        更新agent的基本信息
        
        Args:
            agent_id: Agent ID
            name: Agent名称
            description: Agent描述
            avatar: Agent头像
            gender: 性别
            
        Returns:
            是否更新成功
        """
        try:
            if not self.db_manager:
                raise Exception("数据库管理器未初始化")
            
            # 构建更新字段
            update_fields = []
            params = {"agent_id": agent_id}
            
            if name is not None:
                if not name.strip():
                    raise Exception("Agent名称不能为空")
                update_fields.append("name = :name")
                params["name"] = name.strip()
            
            if description is not None:
                update_fields.append("description = :description")
                params["description"] = description
            
            if avatar is not None:
                update_fields.append("avatar = :avatar")
                params["avatar"] = avatar
            
            if gender is not None:
                update_fields.append("gender = :gender")
                params["gender"] = gender
            
            if not update_fields:
                return True  # 没有字段需要更新
            
            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            
            query = f"""
            UPDATE agents 
            SET {', '.join(update_fields)}
            WHERE id = :agent_id AND status != 2
            """
            
            result = await self.db_manager.execute_update(query, params)
            return result > 0
                
        except Exception as e:
            raise Exception(f"更新agent基本信息失败: {str(e)}")
    
    async def get_agents_by_user(self, user_id: int) -> List[AgentData]:
        """
        根据用户ID获取agents列表
        
        Args:
            user_id: 用户ID
            
        Returns:
            Agent数据列表
        """
        try:
            if not self.db_manager:
                raise Exception("数据库管理器未初始化")
            
            query = """
            SELECT 
                a.id, a.name, a.description, a.avatar, a.gender,
                a.user_id, a.device_id, a.template_id, a.device_type,
                a.agent_config, a.module_params, a.memory_data,
                a.status, a.created_at, a.updated_at,
                u.user_name,
                d.device_uuid, d.name as device_name
            FROM agents a
            LEFT JOIN users u ON a.user_id = u.id
            LEFT JOIN devices d ON a.device_id = d.id
            WHERE a.user_id = :user_id AND a.status != 2
            ORDER BY a.created_at DESC
            """
            
            params = {"user_id": user_id}
            results = await self.db_manager.execute_query(query, params)
            
            agents_list = []
            for row in results:
                agent = AgentData(
                    id=row['id'],
                    name=row['name'],
                    description=row['description'],
                    avatar=row['avatar'],
                    gender=row['gender'],
                    user_id=row['user_id'],
                    device_id=row['device_id'],
                    template_id=row['template_id'],
                    device_type=row['device_type'],
                    agent_config=row['agent_config'],
                    module_params=row['module_params'],
                    memory_data=row['memory_data'],
                    status=row['status'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    user_name=row['user_name'],
                    device_uuid=row['device_uuid'],
                    device_name=row['device_name']
                )
                agents_list.append(agent)
            
            return agents_list
                
        except Exception as e:
            raise Exception(f"查询用户agents失败: {str(e)}")
    
    async def transfer_agent_to_user(self, agent_id: int, target_user_id: int) -> Dict[str, Any]:
        """
        将agent和关联设备迁移给另一个用户
        
        Args:
            agent_id: 要迁移的Agent ID
            target_user_id: 目标用户ID
            
        Returns:
            迁移结果信息
        """
        try:
            if not self.db_manager:
                raise Exception("数据库管理器未初始化")
            
            # 使用事务确保原子性
            async with self.db_manager.transaction():
                # 1. 获取agent信息(验证存在性)
                agent = await self.get_agent_by_id(agent_id)
                if not agent:
                    raise Exception("Agent不存在")
                
                if agent.status == 2:
                    raise Exception("Agent已被删除")
                
                # 2. 验证target_user存在且状态正常
                user_service = SimpleUserService(self.db_manager)
                users = await user_service.get_all_users()
                target_user = next((u for u in users if u.id == target_user_id), None)
                
                if not target_user:
                    raise Exception("目标用户不存在")
                
                if target_user.status != 1:
                    raise Exception("目标用户状态异常")
                
                # 检查是否已经是owner
                if agent.user_id == target_user_id:
                    return {
                        "success": True,
                        "message": "Agent已经是该用户的",
                        "agent_id": agent_id,
                        "target_user_id": target_user_id
                    }
                
                original_user_id = agent.user_id
                device_id = agent.device_id
                
                # 3. 如果agent有关联设备，处理设备绑定关系
                if device_id:
                    # 删除原用户的user_devices记录
                    delete_user_device_query = """
                    DELETE FROM user_devices 
                    WHERE user_id = :user_id AND device_id = :device_id
                    """
                    await self.db_manager.execute_update(delete_user_device_query, {
                        "user_id": original_user_id,
                        "device_id": device_id
                    })
                    
                    # 检查设备是否还有其他owner
                    check_other_owners_query = """
                    SELECT COUNT(*) as owner_count FROM user_devices 
                    WHERE device_id = :device_id
                    """
                    other_owners = await self.db_manager.execute_query(check_other_owners_query, {
                        "device_id": device_id
                    })
                    
                    # 如果没有其他owner，更新设备绑定状态为等待绑定
                    if other_owners[0]['owner_count'] == 0:
                        device_service = SimpleDeviceService(self.db_manager)
                        await device_service.update_binding_status(device_id, 0)
                    
                    # 创建新用户的user_devices记录
                    create_user_device_query = """
                    INSERT INTO user_devices (user_id, device_id, is_owner, created_at, updated_at)
                    VALUES (:user_id, :device_id, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                    await self.db_manager.execute_insert(create_user_device_query, {
                        "user_id": target_user_id,
                        "device_id": device_id
                    })
                    
                    # 更新设备绑定状态为绑定完成
                    device_service = SimpleDeviceService(self.db_manager)
                    await device_service.update_binding_status(device_id, 1)
                
                # 4. 更新agent表的user_id为target_user_id
                update_agent_query = """
                UPDATE agents 
                SET user_id = :target_user_id, updated_at = CURRENT_TIMESTAMP
                WHERE id = :agent_id
                """
                await self.db_manager.execute_update(update_agent_query, {
                    "target_user_id": target_user_id,
                    "agent_id": agent_id
                })
                
                # 5. 记录迁移日志到device_binding_logs
                if device_id:
                    import json
                    log_query = """
                    INSERT INTO device_binding_logs (user_id, device_id, action_type, additional_info, created_at)
                    VALUES (:user_id, :device_id, 5, :additional_info, CURRENT_TIMESTAMP)
                    """
                    additional_info = json.dumps({
                        "original_user_id": original_user_id,
                        "target_user_id": target_user_id,
                        "agent_id": agent_id,
                        "action": "transfer"
                    })
                    await self.db_manager.execute_insert(log_query, {
                        "user_id": target_user_id,
                        "device_id": device_id,
                        "additional_info": additional_info
                    })
                
                return {
                    "success": True,
                    "message": "迁移成功",
                    "agent_id": agent_id,
                    "original_user_id": original_user_id,
                    "target_user_id": target_user_id,
                    "device_id": device_id,
                    "agent_name": agent.name
                }
                
        except Exception as e:
            raise Exception(f"迁移agent失败: {str(e)}")


def create_metrics_service(db_manager: DatabaseManager = None) -> SimpleAIMetricsService:
    """创建指标服务实例"""
    return SimpleAIMetricsService(db_manager)


class SimpleUserService:
    """简化的用户管理服务类"""
    
    def __init__(self, db_manager: DatabaseManager = None):
        self.db_manager = db_manager
    
    async def get_all_users(self) -> List[UserData]:
        """
        获取所有用户列表
        
        Returns:
            用户数据列表
        """
        try:
            if not self.db_manager:
                raise Exception("数据库管理器未初始化")
            
            query = """
            SELECT id, login_name, user_name, mobile, avatar, gender, 
                   user_type, status, created_at, updated_at
            FROM users
            WHERE status != 2
            ORDER BY created_at DESC
            """
            
            results = await self.db_manager.execute_query(query)
            
            users_list = []
            for row in results:
                user = UserData(
                    id=row['id'],
                    login_name=row['login_name'],
                    user_name=row['user_name'],
                    mobile=row['mobile'],
                    avatar=row['avatar'],
                    gender=row['gender'],
                    user_type=row['user_type'],
                    status=row['status'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                )
                users_list.append(user)
            
            return users_list
                
        except Exception as e:
            raise Exception(f"查询用户列表失败: {str(e)}")
    
    async def get_users_with_filter(self, user_name: str = None, mobile: str = None, 
                             login_name: str = None, user_type: int = None, 
                             status: int = None) -> List[UserData]:
        """
        根据过滤条件获取用户列表
        
        Args:
            user_name: 用户名过滤
            mobile: 手机号过滤
            login_name: 登录名过滤
            user_type: 用户类型过滤
            status: 状态过滤
            
        Returns:
            用户数据列表
        """
        try:
            if not self.db_manager:
                raise Exception("数据库管理器未初始化")
            
            # 构建查询条件
            where_conditions = ["status != 2"]
            params = {}
            
            if user_name:
                where_conditions.append("user_name LIKE :user_name")
                params["user_name"] = f"%{user_name}%"
            
            if mobile:
                where_conditions.append("mobile LIKE :mobile")
                params["mobile"] = f"%{mobile}%"
            
            if login_name:
                where_conditions.append("login_name LIKE :login_name")
                params["login_name"] = f"%{login_name}%"
            
            if user_type is not None:
                where_conditions.append("user_type = :user_type")
                params["user_type"] = user_type
            
            if status is not None:
                where_conditions.append("status = :status")
                params["status"] = status
            
            query = f"""
            SELECT id, login_name, user_name, mobile, avatar, gender, 
                   user_type, status, created_at, updated_at
            FROM users
            WHERE {' AND '.join(where_conditions)}
            ORDER BY created_at DESC
            """
            
            results = await self.db_manager.execute_query(query, params)
            
            users_list = []
            for row in results:
                user = UserData(
                    id=row['id'],
                    login_name=row['login_name'],
                    user_name=row['user_name'],
                    mobile=row['mobile'],
                    avatar=row['avatar'],
                    gender=row['gender'],
                    user_type=row['user_type'],
                    status=row['status'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                )
                users_list.append(user)
            
            return users_list
                
        except Exception as e:
            raise Exception(f"查询用户列表失败: {str(e)}")
    
    async def update_user(self, user_id: int, login_name: str = None, password: str = None, 
                   status: int = None) -> bool:
        """
        更新用户信息
        
        Args:
            user_id: 用户ID
            login_name: 新的登录名
            password: 新的密码（可选）
            status: 新的状态
            
        Returns:
            是否更新成功
        """
        try:
            if not self.db_manager:
                raise Exception("数据库管理器未初始化")
            
            # 构建更新字段
            update_fields = []
            params = {"user_id": user_id}
            
            if login_name is not None:
                # 检查登录名是否已存在
                check_query = """
                SELECT id FROM users 
                WHERE login_name = :login_name AND id != :user_id AND status != 2
                """
                existing = await self.db_manager.execute_query(check_query, {
                    "login_name": login_name,
                    "user_id": user_id
                })
                if existing:
                    raise Exception("登录名已存在")
                
                update_fields.append("login_name = :login_name")
                params["login_name"] = login_name
            
            if password is not None:
                # 对密码进行哈希处理 - 使用bcrypt算法
                import bcrypt
                password_bytes = password.encode('utf-8')
                salt = bcrypt.gensalt(rounds=10)
                hashed_password = bcrypt.hashpw(password_bytes, salt)
                update_fields.append("password_hash = :password_hash")
                params["password_hash"] = hashed_password.decode('utf-8')
            
            if status is not None:
                update_fields.append("status = :status")
                params["status"] = status
            
            if not update_fields:
                return True  # 没有字段需要更新
            
            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            
            query = f"""
            UPDATE users 
            SET {', '.join(update_fields)}
            WHERE id = :user_id AND status != 2
            """
            
            result = await self.db_manager.execute_update(query, params)
            return result > 0
                
        except Exception as e:
            raise Exception(f"更新用户信息失败: {str(e)}")


class SimpleDeviceService:
    """简化的设备管理服务类"""
    
    def __init__(self, db_manager: DatabaseManager = None):
        self.db_manager = db_manager
    
    async def get_device_by_uuid(self, device_uuid: str) -> Optional[DeviceData]:
        """
        根据设备UUID获取设备信息
        
        Args:
            device_uuid: 设备UUID
            
        Returns:
            设备数据或None
        """
        try:
            if not self.db_manager:
                raise Exception("数据库管理器未初始化")
            
            query = """
            SELECT id, device_uuid, name, device_type, status, binding_status,
                   battery, volume, ip, signal_strength, created_at, updated_at, last_active
            FROM devices
            WHERE device_uuid = :device_uuid
            """
            
            params = {"device_uuid": device_uuid}
            results = await self.db_manager.execute_query(query, params)
            
            if not results:
                return None
            
            row = results[0]
            return DeviceData(
                id=row['id'],
                device_uuid=row['device_uuid'],
                name=row['name'],
                device_type=row['device_type'],
                status=row['status'],
                binding_status=row['binding_status'],
                battery=row['battery'],
                volume=row['volume'],
                ip=row['ip'],
                signal_strength=row['signal_strength'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                last_active=row['last_active']
            )
                
        except Exception as e:
            raise Exception(f"查询设备信息失败: {str(e)}")
    
    async def create_device(self, device_uuid: str, name: str, device_type: int = 1) -> int:
        """
        创建新设备
        
        Args:
            device_uuid: 设备UUID
            name: 设备名称
            device_type: 设备类型
            
        Returns:
            设备ID
        """
        try:
            if not self.db_manager:
                raise Exception("数据库管理器未初始化")
            
            query = """
            INSERT INTO devices (device_uuid, name, device_type, status, binding_status, 
                               battery, volume, created_at, updated_at)
            VALUES (:device_uuid, :name, :device_type, 0, 0, 100, 50, 
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
            
            params = {
                "device_uuid": device_uuid,
                "name": name,
                "device_type": device_type
            }
            
            result = await self.db_manager.execute_insert(query, params)
            return result
            
        except Exception as e:
            raise Exception(f"创建设备失败: {str(e)}")
    
    async def update_binding_status(self, device_id: int, binding_status: int) -> bool:
        """
        更新设备绑定状态
        
        Args:
            device_id: 设备ID
            binding_status: 绑定状态(0-等待绑定, 1-绑定完成)
            
        Returns:
            是否更新成功
        """
        try:
            if not self.db_manager:
                raise Exception("数据库管理器未初始化")
            
            query = """
            UPDATE devices 
            SET binding_status = :binding_status, updated_at = CURRENT_TIMESTAMP
            WHERE id = :device_id
            """
            
            params = {
                "device_id": device_id,
                "binding_status": binding_status
            }
            
            result = await self.db_manager.execute_update(query, params)
            return result > 0
                
        except Exception as e:
            raise Exception(f"更新设备绑定状态失败: {str(e)}")
    
    async def get_all_devices(self) -> List[DeviceData]:
        """
        获取所有设备列表
        
        Returns:
            设备数据列表
        """
        try:
            if not self.db_manager:
                raise Exception("数据库管理器未初始化")
            
            query = """
            SELECT id, device_uuid, name, device_type, status, binding_status,
                   battery, volume, ip, signal_strength, created_at, updated_at, last_active
            FROM devices
            ORDER BY created_at DESC
            """
            
            results = await self.db_manager.execute_query(query)
            
            devices_list = []
            for row in results:
                device = DeviceData(
                    id=row['id'],
                    device_uuid=row['device_uuid'],
                    name=row['name'],
                    device_type=row['device_type'],
                    status=row['status'],
                    binding_status=row['binding_status'],
                    battery=row['battery'],
                    volume=row['volume'],
                    ip=row['ip'],
                    signal_strength=row['signal_strength'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    last_active=row['last_active']
                )
                devices_list.append(device)
            
            return devices_list
                
        except Exception as e:
            raise Exception(f"查询设备列表失败: {str(e)}")
    
    async def get_devices_with_filter(self, device_uuid: str = None, name: str = None,
                               device_type: int = None, status: int = None,
                               binding_status: int = None) -> List[DeviceData]:
        """
        根据过滤条件获取设备列表
        
        Args:
            device_uuid: 设备UUID过滤
            name: 设备名称过滤
            device_type: 设备类型过滤
            status: 状态过滤
            binding_status: 绑定状态过滤
            
        Returns:
            设备数据列表
        """
        try:
            if not self.db_manager:
                raise Exception("数据库管理器未初始化")
            
            # 构建查询条件
            where_conditions = []
            params = {}
            
            if device_uuid:
                where_conditions.append("device_uuid LIKE :device_uuid")
                params["device_uuid"] = f"%{device_uuid}%"
            
            if name:
                where_conditions.append("name LIKE :name")
                params["name"] = f"%{name}%"
            
            if device_type is not None:
                where_conditions.append("device_type = :device_type")
                params["device_type"] = device_type
            
            if status is not None:
                where_conditions.append("status = :status")
                params["status"] = status
            
            if binding_status is not None:
                where_conditions.append("binding_status = :binding_status")
                params["binding_status"] = binding_status
            
            where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
            
            query = f"""
            SELECT id, device_uuid, name, device_type, status, binding_status,
                   battery, volume, ip, signal_strength, created_at, updated_at, last_active
            FROM devices
            {where_clause}
            ORDER BY created_at DESC
            """
            
            results = await self.db_manager.execute_query(query, params)
            
            devices_list = []
            for row in results:
                device = DeviceData(
                    id=row['id'],
                    device_uuid=row['device_uuid'],
                    name=row['name'],
                    device_type=row['device_type'],
                    status=row['status'],
                    binding_status=row['binding_status'],
                    battery=row['battery'],
                    volume=row['volume'],
                    ip=row['ip'],
                    signal_strength=row['signal_strength'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    last_active=row['last_active']
                )
                devices_list.append(device)
            
            return devices_list
                
        except Exception as e:
            raise Exception(f"查询设备列表失败: {str(e)}")
    
    async def get_device_by_id(self, device_id: int) -> Optional[DeviceData]:
        """
        根据设备ID获取设备信息
        
        Args:
            device_id: 设备ID
            
        Returns:
            设备数据或None
        """
        try:
            if not self.db_manager:
                raise Exception("数据库管理器未初始化")
            
            query = """
            SELECT id, device_uuid, name, device_type, status, binding_status,
                   battery, volume, ip, signal_strength, created_at, updated_at, last_active
            FROM devices
            WHERE id = :device_id
            """
            
            params = {"device_id": device_id}
            results = await self.db_manager.execute_query(query, params)
            
            if not results:
                return None
            
            row = results[0]
            return DeviceData(
                id=row['id'],
                device_uuid=row['device_uuid'],
                name=row['name'],
                device_type=row['device_type'],
                status=row['status'],
                binding_status=row['binding_status'],
                battery=row['battery'],
                volume=row['volume'],
                ip=row['ip'],
                signal_strength=row['signal_strength'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                last_active=row['last_active']
            )
                
        except Exception as e:
            raise Exception(f"查询设备信息失败: {str(e)}")
    
    async def get_device_users(self, device_id: int) -> List[UserData]:
        """
        获取设备关联的用户列表
        
        Args:
            device_id: 设备ID
            
        Returns:
            用户数据列表
        """
        try:
            if not self.db_manager:
                raise Exception("数据库管理器未初始化")
            
            query = """
            SELECT u.id, u.login_name, u.user_name, u.mobile, u.avatar, u.gender,
                   u.user_type, u.status, u.created_at, u.updated_at
            FROM users u
            INNER JOIN user_devices ud ON u.id = ud.user_id
            WHERE ud.device_id = :device_id AND u.status != 2
            ORDER BY ud.created_at DESC
            """
            
            params = {"device_id": device_id}
            results = await self.db_manager.execute_query(query, params)
            
            users_list = []
            for row in results:
                user = UserData(
                    id=row['id'],
                    login_name=row['login_name'],
                    user_name=row['user_name'],
                    mobile=row['mobile'],
                    avatar=row['avatar'],
                    gender=row['gender'],
                    user_type=row['user_type'],
                    status=row['status'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                )
                users_list.append(user)
            
            return users_list
                
        except Exception as e:
            raise Exception(f"查询设备关联用户失败: {str(e)}")


class SimpleAgentTemplateService:
    """简化的Agent模板管理服务类"""
    
    def __init__(self, db_manager: DatabaseManager = None):
        self.db_manager = db_manager
    
    async def get_all_templates(self) -> List[AgentTemplateData]:
        """
        获取所有Agent模板列表
        
        Returns:
            Agent模板数据列表
        """
        try:
            if not self.db_manager:
                raise Exception("数据库管理器未初始化")
            
            query = """
            SELECT id, name, description, avatar, gender, device_type,
                   creator_id, module_params, agent_config, status, 
                   created_at, updated_at
            FROM agent_templates
            WHERE status != 2
            ORDER BY created_at DESC
            """
            
            results = await self.db_manager.execute_query(query)
            
            templates_list = []
            for row in results:
                # 解析JSON字段
                import json
                module_params = row['module_params']
                agent_config = row['agent_config']
                
                # 如果字段是字符串，尝试解析为JSON
                if isinstance(module_params, str):
                    try:
                        module_params = json.loads(module_params) if module_params else {}
                    except json.JSONDecodeError:
                        module_params = {}
                
                if isinstance(agent_config, str):
                    try:
                        agent_config = json.loads(agent_config) if agent_config else {}
                    except json.JSONDecodeError:
                        agent_config = {}
                
                template = AgentTemplateData(
                    id=row['id'],
                    name=row['name'],
                    description=row['description'],
                    avatar=row['avatar'],
                    gender=row['gender'],
                    device_type=row['device_type'],
                    creator_id=row['creator_id'],
                    module_params=module_params,
                    agent_config=agent_config,
                    status=row['status'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                )
                templates_list.append(template)
            
            return templates_list
                
        except Exception as e:
            raise Exception(f"查询Agent模板列表失败: {str(e)}")
    
    async def get_template_by_id(self, template_id: int) -> Optional[AgentTemplateData]:
        """
        根据ID获取单个模板详情
        
        Args:
            template_id: 模板ID
            
        Returns:
            模板数据或None
        """
        try:
            if not self.db_manager:
                raise Exception("数据库管理器未初始化")
            
            query = """
            SELECT id, name, description, avatar, gender, device_type,
                   creator_id, module_params, agent_config, status, 
                   created_at, updated_at
            FROM agent_templates
            WHERE id = :template_id AND status != 2
            """
            
            params = {"template_id": template_id}
            results = await self.db_manager.execute_query(query, params)
            
            if not results:
                return None
            
            row = results[0]
            # 解析JSON字段
            import json
            module_params = row['module_params']
            agent_config = row['agent_config']
            
            # 如果字段是字符串，尝试解析为JSON
            if isinstance(module_params, str):
                try:
                    module_params = json.loads(module_params) if module_params else {}
                except json.JSONDecodeError:
                    module_params = {}
            
            if isinstance(agent_config, str):
                try:
                    agent_config = json.loads(agent_config) if agent_config else {}
                except json.JSONDecodeError:
                    agent_config = {}
            
            return AgentTemplateData(
                id=row['id'],
                name=row['name'],
                description=row['description'],
                avatar=row['avatar'],
                gender=row['gender'],
                device_type=row['device_type'],
                creator_id=row['creator_id'],
                module_params=module_params,
                agent_config=agent_config,
                status=row['status'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
                
        except Exception as e:
            raise Exception(f"查询模板详情失败: {str(e)}")
    
    async def create_template(self, name: str, description: str = None, avatar: str = None, 
                       gender: int = 0, device_type: int = 1, creator_id: int = 0,
                       module_params: Dict[str, Any] = None, 
                       agent_config: Dict[str, Any] = None) -> int:
        """
        创建新模板
        
        Args:
            name: 模板名称
            description: 模板描述
            avatar: 模板头像
            gender: 性别
            device_type: 设备类型
            creator_id: 创建者ID
            module_params: 模块参数
            agent_config: Agent配置
            
        Returns:
            新创建的模板ID
        """
        try:
            if not self.db_manager:
                raise Exception("数据库管理器未初始化")
            
            if not name:
                raise Exception("模板名称不能为空")
            
            import json
            query = """
            INSERT INTO agent_templates (name, description, avatar, gender, device_type,
                                       creator_id, module_params, agent_config, status,
                                       created_at, updated_at)
            VALUES (:name, :description, :avatar, :gender, :device_type,
                    :creator_id, :module_params, :agent_config, 1,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
            
            params = {
                "name": name,
                "description": description,
                "avatar": avatar,
                "gender": gender,
                "device_type": device_type,
                "creator_id": creator_id,
                "module_params": json.dumps(module_params or {}),
                "agent_config": json.dumps(agent_config or {})
            }
            
            result = await self.db_manager.execute_insert(query, params)
            return result
            
        except Exception as e:
            raise Exception(f"创建模板失败: {str(e)}")
    
    async def update_template(self, template_id: int, name: str = None, description: str = None,
                       avatar: str = None, gender: int = None, device_type: int = None,
                       module_params: Dict[str, Any] = None, agent_config: Dict[str, Any] = None) -> bool:
        """
        更新模板基本信息和配置
        
        Args:
            template_id: 模板ID
            name: 模板名称
            description: 模板描述
            avatar: 模板头像
            gender: 性别
            device_type: 设备类型
            module_params: 模块参数
            agent_config: Agent配置
            
        Returns:
            是否更新成功
        """
        try:
            if not self.db_manager:
                raise Exception("数据库管理器未初始化")
            
            # 构建更新字段
            update_fields = []
            params = {"template_id": template_id}
            
            if name is not None:
                update_fields.append("name = :name")
                params["name"] = name
            
            if description is not None:
                update_fields.append("description = :description")
                params["description"] = description
            
            if avatar is not None:
                update_fields.append("avatar = :avatar")
                params["avatar"] = avatar
            
            if gender is not None:
                update_fields.append("gender = :gender")
                params["gender"] = gender
            
            if device_type is not None:
                update_fields.append("device_type = :device_type")
                params["device_type"] = device_type
            
            if module_params is not None:
                import json
                update_fields.append("module_params = :module_params")
                params["module_params"] = json.dumps(module_params)
            
            if agent_config is not None:
                import json
                update_fields.append("agent_config = :agent_config")
                params["agent_config"] = json.dumps(agent_config, ensure_ascii=False)
            
            if not update_fields:
                return True  # 没有字段需要更新
            
            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            
            query = f"""
            UPDATE agent_templates 
            SET {', '.join(update_fields)}
            WHERE id = :template_id AND status != 2
            """
            
            result = await self.db_manager.execute_update(query, params)
            return result > 0
                
        except Exception as e:
            raise Exception(f"更新模板失败: {str(e)}")
    
    async def update_template_config(self, template_id: int, agent_config: Dict[str, Any]) -> bool:
        """
        更新模板的agent_config配置
        
        Args:
            template_id: 模板ID
            agent_config: 新的配置JSON
            
        Returns:
            是否更新成功
        """
        try:
            if not self.db_manager:
                raise Exception("数据库管理器未初始化")
            
            # 验证JSON格式
            import json
            json.dumps(agent_config)  # 验证JSON是否有效
            
            query = """
            UPDATE agent_templates 
            SET agent_config = :agent_config, updated_at = CURRENT_TIMESTAMP
            WHERE id = :template_id AND status != 2
            """
            
            params = {
                "template_id": template_id,
                "agent_config": json.dumps(agent_config, ensure_ascii=False)
            }
            
            result = await self.db_manager.execute_update(query, params)
            return result > 0
                
        except Exception as e:
            raise Exception(f"更新模板配置失败: {str(e)}")
    
    async def delete_template(self, template_id: int) -> bool:
        """
        软删除模板（将status设为2）
        
        Args:
            template_id: 模板ID
            
        Returns:
            是否删除成功
        """
        try:
            if not self.db_manager:
                raise Exception("数据库管理器未初始化")
            
            query = """
            UPDATE agent_templates 
            SET status = 2, updated_at = CURRENT_TIMESTAMP
            WHERE id = :template_id AND status != 2
            """
            
            params = {"template_id": template_id}
            result = await self.db_manager.execute_update(query, params)
            return result > 0
                
        except Exception as e:
            raise Exception(f"删除模板失败: {str(e)}")


class SimpleDeviceBindingService:
    """简化的设备绑定服务类"""
    
    def __init__(self, db_manager: DatabaseManager = None):
        self.db_manager = db_manager
    
    async def bind_device(self, device_uuid: str, user_id: int, template_id: int, 
                   device_name: str = None, device_type: int = 1) -> Dict[str, Any]:
        """
        执行设备绑定操作
        
        Args:
            device_uuid: 设备UUID
            user_id: 用户ID
            template_id: 模板ID
            device_name: 设备名称(可选)
            device_type: 设备类型(可选)
            
        Returns:
            绑定结果和创建的Agent信息
        """
        try:
            if not self.db_manager:
                raise Exception("数据库管理器未初始化")
            
            # 使用事务上下文管理器
            async with self.db_manager.transaction():
                # 1. 检查设备是否存在
                device_service = SimpleDeviceService(self.db_manager)
                device = await device_service.get_device_by_uuid(device_uuid)
                
                if not device:
                    # 创建设备
                    if not device_name:
                        device_name = f"设备-{device_uuid[:8]}"
                    device_id = await device_service.create_device(device_uuid, device_name, device_type)
                else:
                    device_id = device.id
                    # 检查设备是否已绑定
                    if device.binding_status == 1:
                        raise Exception("设备已被绑定")
                
                # 2. 检查用户-设备关联是否已存在
                check_query = """
                SELECT id FROM user_devices 
                WHERE user_id = :user_id AND device_id = :device_id
                """
                existing = await self.db_manager.execute_query(check_query, {
                    "user_id": user_id, 
                    "device_id": device_id
                })
                
                if existing:
                    raise Exception("用户已绑定该设备")
                
                # 3. 创建用户-设备关联
                user_device_query = """
                INSERT INTO user_devices (user_id, device_id, is_owner, created_at, updated_at)
                VALUES (:user_id, :device_id, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
                await self.db_manager.execute_insert(user_device_query, {
                    "user_id": user_id,
                    "device_id": device_id
                })
                
                # 4. 获取模板信息
                template_service = SimpleAgentTemplateService(self.db_manager)
                templates = await template_service.get_all_templates()
                template = next((t for t in templates if t.id == template_id), None)
                
                if not template:
                    raise Exception("模板不存在")
                
                # 5. 创建Agent实例
                agent_name = f"{template.name}-{device_uuid[:8]}"
                agent_query = """
                INSERT INTO agents (name, description, avatar, gender, user_id, device_id, 
                                  template_id, device_type, agent_config, module_params, 
                                  memory_data, status, created_at, updated_at)
                VALUES (:name, :description, :avatar, :gender, :user_id, :device_id,
                        :template_id, :device_type, :agent_config, :module_params,
                        :memory_data, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
                
                import json
                agent_params = {
                    "name": agent_name,
                    "description": template.description,
                    "avatar": template.avatar,
                    "gender": template.gender,
                    "user_id": user_id,
                    "device_id": device_id,
                    "template_id": template_id,
                    "device_type": device_type,
                    "agent_config": json.dumps(template.agent_config or {}),
                    "module_params": json.dumps(template.module_params or {}),
                    "memory_data": "{}"
                }
                
                agent_id = await self.db_manager.execute_insert(agent_query, agent_params)
                
                # 6. 更新设备绑定状态
                await device_service.update_binding_status(device_id, 1)
                
                return {
                    "success": True,
                    "device_id": device_id,
                    "agent_id": agent_id,
                    "agent_name": agent_name,
                    "message": "设备绑定成功"
                }
                
        except Exception as e:
            raise Exception(f"设备绑定失败: {str(e)}")


def create_user_service(db_manager: DatabaseManager = None) -> SimpleUserService:
    """创建用户服务实例"""
    return SimpleUserService(db_manager)


def create_device_service(db_manager: DatabaseManager = None) -> SimpleDeviceService:
    """创建设备服务实例"""
    return SimpleDeviceService(db_manager)


def create_agent_template_service(db_manager: DatabaseManager = None) -> SimpleAgentTemplateService:
    """创建Agent模板服务实例"""
    return SimpleAgentTemplateService(db_manager)


def create_device_binding_service(db_manager: DatabaseManager = None) -> SimpleDeviceBindingService:
    """创建设备绑定服务实例"""
    return SimpleDeviceBindingService(db_manager)


def create_agent_service(db_manager: DatabaseManager = None) -> SimpleAgentService:
    """创建Agent服务实例"""
    return SimpleAgentService(db_manager)
