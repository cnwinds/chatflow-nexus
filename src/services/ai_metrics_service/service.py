#!/usr/bin/env python3
"""
AI指标服务主类

基于UTCP协议实现的AI模型调用性能监控和费用统计服务。
"""

import asyncio
import logging
import time
import uuid
from typing import List, Dict, Any, Optional, Callable
from functools import wraps
from collections import deque

from src.utcp.utcp import UTCPService
from src.common import ConfigManager
from src.services.ai_metrics_service.calculator import CostCalculator
from src.services.ai_metrics_service.persistence import DatabasePersistence
from src.services.ai_metrics_service.models import CallMetrics
from src.services.ai_metrics_service.exceptions import AIMetricsError, MonitoringError, CostCalculationError

logger = logging.getLogger(__name__)


def require_db_initialized(func: Callable) -> Callable:
    """装饰器：确保数据库已初始化"""
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        if not self._db_initialized:
            await self.data_persistence.initialize()
            self._db_initialized = True
        return await func(self, *args, **kwargs)
    return wrapper


def handle_errors(error_type: type = AIMetricsError) -> Callable:
    """装饰器：统一错误处理"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            try:
                return await func(self, *args, **kwargs)
            except Exception as e:
                logger.error(f"{func.__name__} 失败: {e}")
                raise error_type(f"{func.__name__} 失败: {e}")
        return wrapper
    return decorator


class AIMetricsService(UTCPService):
    """AI指标服务主类"""
    # 插件不允许写__init__方法，只能通过init方法进行初始化

    def init(self) -> None:
        """插件初始化方法"""
        self.service_config = self.config
        self._init_components()

    def _init_components(self):
        """初始化服务组件"""
        # 使用合并后的配置
        cost_calculation_config = self.service_config.get("cost_calculation", {})
        custom_pricing = cost_calculation_config.get("custom_pricing", {})
        
        # 初始化费用计算器
        self.cost_calculator = CostCalculator(
            custom_pricing=custom_pricing
        )
        
        # 初始化数据库持久化组件
        self.data_persistence = DatabasePersistence(self.config_manager)
        
        # 标记为未初始化状态
        self._db_initialized = False
        
        # 简单的会话存储（替代collector）
        self._active_sessions: Dict[str, Dict[str, Any]] = {}
        
        # 批量插入队列配置
        batch_config = self.service_config.get("batch_insert", {})
        self._batch_size = batch_config.get("batch_size", 10)  # 默认每批10条
        self._batch_timeout = batch_config.get("batch_timeout", 5.0)  # 默认5秒超时
        self._metrics_queue: deque = deque()
        self._last_batch_time = time.time()
        self._batch_task: Optional[asyncio.Task] = None
        self._queue_lock = asyncio.Lock()
    
    @property
    def name(self) -> str:
        """服务名称"""
        return "ai_metrics_service"
    
    @property
    def description(self) -> str:
        """服务描述"""
        return "AI模型调用性能监控和费用统计服务（数据库版本）"
    
    def _create_tool_definition(self, name: str, description: str, 
                               properties: Dict[str, Any], required: List[str] = None) -> Dict[str, Any]:
        """创建工具定义的辅助方法"""
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required or []
                }
            }
        }
    
    async def get_tools(self) -> List[Dict[str, Any]]:
        """返回可用工具列表"""
        tools = [
            # 监控相关工具
            self._create_tool_definition(
                "start_monitoring", "开始监控",
                {"model_name": {"type": "string", "description": "模型名称（可选）"}}
            ),
            
            # 监控完成工具
            self._create_tool_definition(
                "finish_monitoring", "完成监控并保存记录到数据库",
                {
                    "monitor_id": {"type": "string", "description": "监控ID"},
                    "model_name": {"type": "string", "description": "模型名称（可选）"},
                    "provider": {"type": "string", "description": "提供商（可选，默认unknown）"},
                    "session_id": {"type": "string", "description": "会话ID（可选）"},
                    "prompt_tokens": {"type": "integer", "description": "输入token数量"},
                    "completion_tokens": {"type": "integer", "description": "输出token数量"},
                    "input_chars": {"type": "integer", "description": "输入字符数"},
                    "output_chars": {"type": "integer", "description": "输出字符数"},
                    "tool_count": {"type": "integer", "description": "工具数量"},
                    "tool_calls_made": {"type": "integer", "description": "工具调用次数"},
                    "http_first_byte_time": {"type": "number", "description": "HTTP首字节时间（毫秒）"},
                    "first_token_time": {"type": "number", "description": "第一个token时间（毫秒）"},
                    "result": {"type": "string", "description": "调用结果（可选）"}
                },
                ["monitor_id"]
            ),
            
            # 取消监控工具
            self._create_tool_definition(
                "cancel_monitor", "取消监控会话（当出现错误时使用）",
                {"monitor_id": {"type": "string", "description": "监控ID"}},
                ["monitor_id"]
            ),
            
            # 数据查询工具
            self._create_tool_definition(
                "get_statistics", "获取统计数据",
                {
                    "model_name": {"type": "string", "description": "模型名称（可选）"},
                            "period": {
                                "type": "string",
                        "description": "统计周期：hour/day/week/month",
                        "enum": ["hour", "day", "week", "month"]
                    }
                }
            ),
            self._create_tool_definition(
                "load_historical_data", "加载历史数据",
                {
                    "model_name": {"type": "string", "description": "模型名称（可选）"},
                    "start_time": {"type": "number", "description": "开始时间戳（可选）"},
                    "end_time": {"type": "number", "description": "结束时间戳（可选）"},
                    "limit": {"type": "integer", "description": "返回记录数量限制（默认100）"}
                }
            ),
            
            # 数据维护工具
            self._create_tool_definition(
                "cleanup_old_data", "清理旧数据",
                {"max_days": {"type": "integer", "description": "保留天数（默认30天）"}}
            ),
            
            
            # 系统信息工具
            self._create_tool_definition(
                "get_data_info", "获取数据统计信息", {}
            )
        ]
        
        return tools
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """执行工具调用"""
        # 工具映射表
        tool_handlers = {
            "start_monitoring": lambda: self.start_monitoring(),
            "finish_monitoring": lambda: self.finish_monitoring(
                arguments["monitor_id"],
                arguments.get("provider"),
                arguments.get("model_name"),
                arguments.get("session_id"),
                arguments.get("prompt_tokens", 0),
                arguments.get("completion_tokens", 0),
                arguments.get("input_chars", 0),
                arguments.get("output_chars", 0),
                arguments.get("tool_count", 0),
                arguments.get("tool_calls_made", 0),
                arguments.get("http_first_byte_time"),
                arguments.get("first_token_time"),
                arguments.get("result")
            ),
            "cancel_monitor": lambda: self.cancel_monitor(arguments["monitor_id"]),
            "get_statistics": lambda: self.get_statistics(
                arguments.get("model_name"), arguments.get("period", "day")
            ),
            "load_historical_data": lambda: self.load_historical_data(
                arguments.get("model_name"), arguments.get("start_time"),
                arguments.get("end_time"), arguments.get("limit", 100)
            ),
            "cleanup_old_data": lambda: self.cleanup_old_data(arguments.get("max_days", 30)),
            "get_data_info": lambda: self.get_data_info()
        }
        
        try:
            if tool_name not in tool_handlers:
                raise ValueError(f"未知的工具名称: {tool_name}")
            
            return await tool_handlers[tool_name]()
        except Exception as e:
            logger.error(f"执行工具 '{tool_name}' 时出错: {e}")
            return {
                "status": "error",
                "error": str(e),
                "message": f"执行工具 '{tool_name}' 失败"
            }

    @handle_errors(MonitoringError)
    async def start_monitoring(self) -> Dict[str, Any]:
        """开始监控"""
        monitor_id = str(uuid.uuid4())
        self._active_sessions[monitor_id] = {
            "start_time": time.time()
        }
        return {
            "monitor_id": monitor_id,
            "status": "started"
        }
    
    @handle_errors(MonitoringError)
    async def finish_monitoring(self, monitor_id: str,
                               provider: str = None,
                               model_name: str = None, 
                               session_id: str = None,
                               prompt_tokens: int = 0,
                               completion_tokens: int = 0,
                               input_chars: int = 0,
                               output_chars: int = 0,
                               tool_count: int = 0,
                               tool_calls_made: int = 0,
                               http_first_byte_time: float = None,
                               first_token_time: float = None,
                               result: str = None) -> Dict[str, Any]:
        """完成监控并保存记录到数据库"""
        # 获取会话信息
        if monitor_id not in self._active_sessions:
            raise MonitoringError(f"监控会话不存在: {monitor_id}")
        
        session_info = self._active_sessions[monitor_id]
        start_time = session_info["start_time"]
        actual_model_name = model_name
        
        # 清理会话数据
        del self._active_sessions[monitor_id]

        # 直接创建CallMetrics对象
        metrics = CallMetrics(
            monitor_id=monitor_id,
            provider=provider,
            model_name=actual_model_name,
            session_id=session_id,
            start_time=start_time,
            end_time=time.time(),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            input_chars=input_chars,
            output_chars=output_chars,
            tool_count=tool_count,
            tool_calls_made=tool_calls_made,
            http_first_byte_time=http_first_byte_time,
            first_token_time=first_token_time,
            result=result
        )
        
        # 计算费用
        total_cost = self.cost_calculator.calculate_cost(model_name, metrics.prompt_tokens, metrics.completion_tokens)
        
        # 计算输入和输出费用
        model_pricing = self.cost_calculator.get_model_pricing(model_name)
        input_cost = metrics.prompt_tokens * model_pricing.get("input_cost_per_token", 0)
        output_cost = metrics.completion_tokens * model_pricing.get("output_cost_per_token", 0)
        
        metrics.cost = total_cost
        metrics.input_cost = input_cost
        metrics.output_cost = output_cost
        
        # 添加到批量插入队列（不阻塞）
        asyncio.create_task(self._add_to_batch_queue(metrics))
        
        self.logger.debug(f"📊 指标数据已提交保存: "
                        f"total_time={metrics.total_time:.2f}ms, "
                        f"prompt_tokens={metrics.prompt_tokens}, "
                        f"completion_tokens={metrics.completion_tokens}, "
                        f"output_chars={metrics.output_chars}, "
                        f"tool_calls_made={metrics.tool_calls_made}")

        return {
            "monitor_id": monitor_id,
            "model_name": metrics.model_name,
            "provider": metrics.provider,
            "session_id": session_id,
            "result": result,
            "status": "finished_and_saved",
            "cost": metrics.cost,
            "metrics": metrics.to_dict()
        }

    @handle_errors(MonitoringError)
    async def cancel_monitor(self, monitor_id: str) -> Dict[str, Any]:
        """取消监控会话（当出现错误时使用）"""
        # 检查监控会话是否存在
        if monitor_id not in self._active_sessions:
            raise MonitoringError(f"监控会话不存在: {monitor_id}")
        
        # 获取会话信息
        session_info = self._active_sessions[monitor_id]
        start_time = session_info["start_time"]
        
        # 清理会话数据
        del self._active_sessions[monitor_id]
        
        # 记录取消信息
        logger.info(f"监控会话已取消: {monitor_id}, 持续时间: {time.time() - start_time:.2f}秒")
        
        return {
            "monitor_id": monitor_id,
            "status": "cancelled",
            "duration": time.time() - start_time,
            "message": "监控会话已成功取消"
        }

    @require_db_initialized
    @handle_errors(AIMetricsError)
    async def get_statistics(self, model_name: str = None, period: str = "day") -> Dict[str, Any]:
        """获取统计数据"""
        return await self.data_persistence.get_statistics(model_name, period)

    @require_db_initialized
    @handle_errors(AIMetricsError)
    async def load_historical_data(self, model_name: str = None, start_time: float = None,
                                 end_time: float = None, limit: int = 100) -> List[Dict[str, Any]]:
        """加载历史数据"""
        metrics_list = await self.data_persistence.load_historical_data(
            model_name, start_time, end_time, limit
        )
        return [metrics.to_dict() for metrics in metrics_list]

    @require_db_initialized
    @handle_errors(AIMetricsError)
    async def cleanup_old_data(self, max_days: int = 30) -> Dict[str, Any]:
        """清理旧数据"""
        cleaned_count = await self.data_persistence.cleanup_old_data(max_days)
        return {
            "cleaned_count": cleaned_count,
            "max_days": max_days,
            "status": "completed"
        }


    @require_db_initialized
    @handle_errors(AIMetricsError)
    async def get_data_info(self) -> Dict[str, Any]:
        """获取数据统计信息"""
        return await self.data_persistence.get_data_info()

    async def _ensure_db_initialized(self):
        """确保数据库已初始化"""
        if not self._db_initialized:
            await self.data_persistence.initialize()
            self._db_initialized = True
    
    async def _add_to_batch_queue(self, metrics: CallMetrics):
        """将指标添加到批量插入队列"""
        should_flush = False
        should_start_timer = False
        
        async with self._queue_lock:
            self._metrics_queue.append(metrics)
            
            # 如果队列达到批量大小，立即触发批量保存
            if len(self._metrics_queue) >= self._batch_size:
                should_flush = True
            else:
                # 需要启动或重置定时器任务
                should_start_timer = True
        
        # 在锁外执行批量保存和定时器操作
        if should_flush:
            await self._flush_batch_queue()
        elif should_start_timer:
            # 启动或重置定时器任务（在锁外执行，避免死锁）
            self._start_batch_timer()
    
    def _start_batch_timer(self):
        """启动批量保存定时器（非阻塞）"""
        # 取消之前的任务
        if self._batch_task and not self._batch_task.done():
            self._batch_task.cancel()
        
        # 创建新的定时任务
        self._batch_task = asyncio.create_task(self._batch_timer_task())
    
    async def _batch_timer_task(self):
        """批量保存定时器任务"""
        try:
            await asyncio.sleep(self._batch_timeout)
            # 检查队列是否还有数据需要保存
            async with self._queue_lock:
                if self._metrics_queue:
                    await self._flush_batch_queue()
        except asyncio.CancelledError:
            # 任务被取消是正常的（当队列达到批量大小时）
            pass
    
    async def _flush_batch_queue(self):
        """刷新批量队列，执行批量插入"""
        # 在锁内取出队列数据
        async with self._queue_lock:
            if not self._metrics_queue:
                return
            
            # 取出队列中的所有指标
            metrics_list = list(self._metrics_queue)
            self._metrics_queue.clear()
            self._last_batch_time = time.time()
            
            # 取消定时器任务（如果还在运行）
            if self._batch_task and not self._batch_task.done():
                self._batch_task.cancel()
                self._batch_task = None
        
        # 在锁外执行批量保存（避免长时间持有锁）
        try:
            await self._ensure_db_initialized()
            saved_count = await self.data_persistence.save_metrics_batch(metrics_list)
            self.logger.debug(f"✅ 批量保存指标数据成功: {saved_count}/{len(metrics_list)} 条记录")
        except Exception as e:
            self.logger.error(f"❌ 批量保存指标数据失败: {e}", exc_info=True)
            # 如果批量保存失败，尝试单条保存（降级策略）
            for metrics in metrics_list:
                try:
                    await self.data_persistence.save_metrics(metrics)
                except Exception as single_error:
                    self.logger.error(f"❌ 单条保存指标数据失败: monitor_id={metrics.monitor_id}, error={single_error}")
    
    async def flush_pending_metrics(self):
        """刷新待保存的指标数据（用于服务关闭时调用）"""
        await self._flush_batch_queue()
    
    async def _save_metrics_async(self, metrics):
        """异步保存指标数据（不阻塞主流程）- 保留用于兼容性"""
        try:
            await self._ensure_db_initialized()
            await self.data_persistence.save_metrics(metrics)
            self.logger.debug(f"✅ 指标数据保存成功: monitor_id={metrics.monitor_id}")
        except Exception as e:
            self.logger.error(f"❌ 保存指标数据失败: {e}", exc_info=True) 