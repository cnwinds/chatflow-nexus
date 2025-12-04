#!/usr/bin/env python3
"""
AI指标服务数据持久化组件

负责数据的数据库持久化存储、查询和统计功能。
"""

import json
import time
import logging
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime, timedelta
from functools import wraps

from src.common.database.manager import get_db_manager
from src.services.ai_metrics_service.models import CallMetrics
from src.services.ai_metrics_service.exceptions import DataPersistenceError

logger = logging.getLogger(__name__)


def require_initialized(func: Callable) -> Callable:
    """装饰器：确保数据库已初始化"""
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        if not self._initialized:
            await self.initialize()
        return await func(self, *args, **kwargs)
    return wrapper


def handle_persistence_errors(func: Callable) -> Callable:
    """装饰器：统一错误处理"""
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except Exception as e:
            logger.error(f"{func.__name__} 失败: {e}")
            raise DataPersistenceError(f"{func.__name__} 失败: {e}")
    return wrapper


class DatabasePersistence:
    """基于数据库的数据持久化组件"""
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        self.db_manager = None
        self._initialized = False
    
    @handle_persistence_errors
    async def initialize(self) -> None:
        """初始化数据库连接和表结构"""
        # 获取数据库管理器
        self.db_manager = get_db_manager()
        
        self._initialized = True
    
    @require_initialized
    @handle_persistence_errors
    async def save_metrics(self, metrics: CallMetrics) -> None:
        """保存指标数据到数据库"""
        # 转换为数据库格式
        metrics_data = {
            'monitor_id': metrics.monitor_id,
            'provider': metrics.provider,
            'model_name': metrics.model_name,
            'session_id': metrics.session_id,
            'start_time': datetime.fromtimestamp(metrics.start_time),
            'end_time': datetime.fromtimestamp(metrics.end_time) if metrics.end_time else None,
            'prompt_tokens': metrics.prompt_tokens,
            'completion_tokens': metrics.completion_tokens,
            'total_tokens': metrics.total_tokens,
            'input_chars': metrics.input_chars,
            'output_chars': metrics.output_chars,
            'tool_count': metrics.tool_count,
            'tool_calls_made': metrics.tool_calls_made,
            'cost': metrics.cost,
            'input_cost': metrics.input_cost,
            'output_cost': metrics.output_cost,
            'total_time': metrics.total_time,
            'http_first_byte_time': metrics.http_first_byte_time,
            'first_token_time': metrics.first_token_time,
            'result': metrics.result
        }
        
        # 构建SQL语句
        fields = ', '.join(metrics_data.keys())
        placeholders = ', '.join([f':{key}' for key in metrics_data.keys()])
        sql = f"INSERT INTO ai_metrics ({fields}) VALUES ({placeholders})"
        
        # 执行插入
        await self.db_manager.execute_update(sql, metrics_data)
        
        logger.debug(f"保存指标数据: {metrics.monitor_id}")
    
    @require_initialized
    @handle_persistence_errors
    async def load_historical_data(self, 
                                  model_name: str = None,
                                  start_time: float = None,
                                  end_time: float = None,
                                  limit: int = 100) -> List[CallMetrics]:
        """从数据库加载历史数据"""
        # 构建查询条件
        conditions = []
        params = {}
        
        if model_name:
            conditions.append("model_name = :model_name")
            params["model_name"] = model_name
        
        if start_time:
            conditions.append("start_time >= :start_time")
            params["start_time"] = datetime.fromtimestamp(start_time)
        
        if end_time:
            conditions.append("start_time <= :end_time")
            params["end_time"] = datetime.fromtimestamp(end_time)
        
        # 构建SQL
        sql = "SELECT * FROM ai_metrics"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        
        sql += " ORDER BY start_time DESC"
        
        if limit > 0:
            sql += f" LIMIT {limit}"
        
        # 执行查询
        results = await self.db_manager.execute_query(sql, params if params else None)
        
        # 转换为CallMetrics对象
        metrics_list = []
        for row in results:
            # 转换时间戳
            row['start_time'] = row['start_time'].timestamp()
            if row['end_time']:
                row['end_time'] = row['end_time'].timestamp()
            
            # 移除数据库字段
            row.pop('id', None)
            
            metrics = CallMetrics.from_dict(row)
            metrics_list.append(metrics)
        
        logger.debug(f"加载历史数据: {len(metrics_list)} 条记录")
        return metrics_list
    
    @require_initialized
    @handle_persistence_errors
    async def get_statistics(self, model_name: str = None,
                           period: str = "day") -> Dict[str, Any]:
        """获取统计数据"""
        # 计算时间范围
        now = datetime.now()
        if period == "hour":
            start_time = now - timedelta(hours=1)
        elif period == "day":
            start_time = now - timedelta(days=1)
        elif period == "week":
            start_time = now - timedelta(weeks=1)
        elif period == "month":
            start_time = now - timedelta(days=30)
        else:
            start_time = datetime(1970, 1, 1)  # 全部时间
        
        # 构建查询条件
        conditions = ["start_time >= :start_time"]
        params = {"start_time": start_time}
        
        if model_name:
            conditions.append("model_name = :model_name")
            params["model_name"] = model_name
        
        where_clause = " AND ".join(conditions)
        
        # 执行统计查询
        sql = f"""
        SELECT 
            COUNT(*) as total_calls,
            SUM(total_tokens) as total_tokens,
            SUM(cost) as total_cost,
            AVG(TIMESTAMPDIFF(MICROSECOND, start_time, end_time) / 1000) as avg_time_ms,
            AVG(total_tokens) as avg_tokens,
            AVG(cost) as avg_cost,
            model_name,
            provider
        FROM ai_metrics 
        WHERE {where_clause}
        GROUP BY model_name, provider
        """
        
        results = await self.db_manager.execute_query(sql, params)
        
        # 处理结果
        if not results:
            return {
                "total_calls": 0,
                "total_tokens": 0,
                "total_cost": 0.0,
                "avg_time": 0.0,
                "avg_tokens": 0,
                "avg_cost": 0.0,
                "period": period,
                "model_name": model_name,
                "model_breakdown": {}
            }
        
        # 计算总计
        total_calls = sum(r['total_calls'] for r in results)
        total_tokens = sum(r['total_tokens'] for r in results)
        total_cost = sum(r['total_cost'] for r in results)
        
        # 构建模型分组统计
        model_breakdown = {}
        for row in results:
            model = row['model_name']
            model_breakdown[model] = {
                "calls": row['total_calls'],
                "tokens": row['total_tokens'],
                "cost": float(row['total_cost']),
                "avg_time": float(row['avg_time_ms']) if row['avg_time_ms'] else 0.0,
                "avg_tokens": float(row['avg_tokens']) if row['avg_tokens'] else 0,
                "avg_cost": float(row['avg_cost']) if row['avg_cost'] else 0.0
            }
        
        # 计算总体平均值
        avg_time = sum(r['avg_time_ms'] * r['total_calls'] for r in results) / total_calls if total_calls > 0 else 0.0
        avg_tokens = total_tokens / total_calls if total_calls > 0 else 0
        avg_cost = total_cost / total_calls if total_calls > 0 else 0.0
        
        return {
            "total_calls": total_calls,
            "total_tokens": total_tokens,
            "total_cost": float(total_cost),
            "avg_time": avg_time,
            "avg_tokens": avg_tokens,
            "avg_cost": avg_cost,
            "period": period,
            "model_name": model_name,
            "model_breakdown": model_breakdown
        }
    
    @require_initialized
    @handle_persistence_errors
    async def cleanup_old_data(self, max_days: int = 30) -> int:
        """清理旧数据"""
        cutoff_time = datetime.now() - timedelta(days=max_days)
        
        # 删除旧数据
        affected_rows = await self.db_manager.execute_update(
            "DELETE FROM ai_metrics WHERE start_time < :cutoff_time",
            {"cutoff_time": cutoff_time}
        )
        
        if affected_rows > 0:
            logger.info(f"清理了 {affected_rows} 条旧数据")
        
        return affected_rows
    
    
    @require_initialized
    @handle_persistence_errors
    async def get_data_info(self) -> Dict[str, Any]:
        """获取数据统计信息"""
        # 获取记录总数
        total_records = await self.db_manager.execute_query(
            "SELECT COUNT(*) as count FROM ai_metrics"
        )[0]['count']
        
        # 获取最早和最晚记录时间
        time_range = await self.db_manager.execute_query(
            "SELECT MIN(start_time) as earliest, MAX(start_time) as latest FROM ai_metrics"
        )[0]
        
        # 获取模型数量
        model_count = await self.db_manager.execute_query(
            "SELECT COUNT(DISTINCT model_name) as count FROM ai_metrics"
        )[0]['count']
        
        return {
            "total_records": total_records,
            "earliest_record": time_range['earliest'].isoformat() if time_range['earliest'] else None,
            "latest_record": time_range['latest'].isoformat() if time_range['latest'] else None,
            "model_count": model_count,
            "storage_type": "database"
        }


# 为了保持向后兼容，保留原来的类名
DataPersistence = DatabasePersistence 