#!/usr/bin/env python3
"""
UTCP时间服务
基于UTCP协议实现的时间和日期服务
提供获取当前时间、日期、时区等功能
"""

import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Callable
from functools import wraps
from src.utcp.utcp import UTCPService

logger = logging.getLogger(__name__)


def handle_time_errors(func: Callable) -> Callable:
    """装饰器：统一错误处理"""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except Exception as e:
            logger.error(f"{func.__name__} 失败: {e}")
            return {
                "status": "error",
                "error": str(e),
                "message": f"执行工具 '{func.__name__}' 失败"
            }
    return wrapper


class TimeService(UTCPService):
    """时间服务 - 提供时间、日期相关功能"""
    
    def init(self) -> None:
        """插件初始化方法"""
        pass
    
    @property
    def name(self) -> str:
        return "time_service"
    
    @property
    def description(self) -> str:
        return "提供时间、日期相关功能的服务，包括获取当前时间、日期信息、时间差计算等"
    
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
        """返回时间服务的所有工具定义"""
        return [
            # 时间获取工具
            self._create_tool_definition(
                "get_current_time", "获取当前时间，支持多种格式和时区",
                {
                    "format_type": {
                        "type": "string",
                        "enum": ["iso", "timestamp", "readable", "custom"],
                        "description": "时间格式类型",
                        "default": "iso"
                    },
                    "timezone_name": {
                        "type": "string",
                        "enum": ["local", "utc", "beijing", "tokyo", "london", "newyork"],
                        "description": "时区名称",
                        "default": "local"
                    }
                }
            ),
            
            # 日期信息工具
            self._create_tool_definition(
                "get_date_info", "获取指定日期的详细信息，包括星期、季度、是否闰年等",
                {
                    "date_string": {
                        "type": "string",
                        "description": "日期字符串，格式为YYYY-MM-DD，为空则使用当前日期",
                        "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
                    }
                }
            ),
            
            # 时间差计算工具
            self._create_tool_definition(
                "calculate_time_difference", "计算两个时间之间的差值",
                {
                    "start_time": {
                        "type": "string",
                        "description": "开始时间，格式为YYYY-MM-DD或YYYY-MM-DD HH:MM:SS"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "结束时间，格式为YYYY-MM-DD或YYYY-MM-DD HH:MM:SS"
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["days", "hours", "minutes", "seconds"],
                        "description": "返回结果的单位",
                        "default": "days"
                    }
                },
                ["start_time", "end_time"]
            ),
            
            # 时间戳格式化工具
            self._create_tool_definition(
                "format_timestamp", "将Unix时间戳格式化为可读的时间字符串",
                {
                    "timestamp": {
                        "type": "integer",
                        "description": "Unix时间戳"
                    },
                    "format_type": {
                        "type": "string",
                        "enum": ["iso", "readable", "custom"],
                        "description": "格式类型",
                        "default": "readable"
                    },
                    "timezone_name": {
                        "type": "string",
                        "enum": ["local", "utc", "beijing"],
                        "description": "时区名称",
                        "default": "local"
                    }
                },
                ["timestamp"]
            ),
        ]
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """执行时间服务的工具调用"""
        # 工具映射表
        tool_handlers = {
            "get_current_time": lambda: self._get_current_time(
                arguments.get("format_type", "iso"),
                arguments.get("timezone_name", "local")
            ),
            "get_date_info": lambda: self._get_date_info(arguments.get("date_string")),
            "calculate_time_difference": lambda: self._calculate_time_difference(
                arguments["start_time"],
                arguments["end_time"],
                arguments.get("unit", "days")
            ),
            "format_timestamp": lambda: self._format_timestamp(
                arguments["timestamp"],
                arguments.get("format_type", "readable"),
                arguments.get("timezone_name", "local")
            ),
        }
        
        try:
            if tool_name not in tool_handlers:
                raise ValueError(f"未知的工具名称: {tool_name}")
            
            return tool_handlers[tool_name]()
        except Exception as e:
            logger.error(f"执行工具 '{tool_name}' 时出错: {e}")
            return {
                "status": "error",
                "error": str(e),
                "message": f"执行工具 '{tool_name}' 失败"
            }
    
    @handle_time_errors
    def _get_current_time(self, format_type: str = "iso", timezone_name: str = "local") -> Dict[str, Any]:
        """获取当前时间"""
        # 获取当前时间
        now = datetime.now()
        
        # 处理时区
        if timezone_name.lower() == "utc":
            now = datetime.now(timezone.utc)
        elif timezone_name.lower() == "beijing":
            now = datetime.now(timezone(timedelta(hours=8)))
        elif timezone_name.lower() == "tokyo":
            now = datetime.now(timezone(timedelta(hours=9)))
        elif timezone_name.lower() == "london":
            now = datetime.now(timezone(timedelta(hours=0)))  # GMT
        elif timezone_name.lower() == "newyork":
            now = datetime.now(timezone(timedelta(hours=-5)))  # EST
        # local时区保持默认
        
        # 格式化时间
        if format_type.lower() == "iso":
            formatted_time = now.isoformat()
        elif format_type.lower() == "timestamp":
            formatted_time = str(int(now.timestamp()))
        elif format_type.lower() == "readable":
            formatted_time = now.strftime("%Y年%m月%d日 %H:%M:%S")
        elif format_type.lower() == "custom":
            formatted_time = now.strftime("%Y-%m-%d %H:%M:%S %A")
        else:
            formatted_time = now.isoformat()
        
        return {
            "status": "success",
            "current_time": formatted_time,
            "timezone": timezone_name,
            "format": format_type,
            "timestamp": int(now.timestamp()),
            "year": now.year,
            "month": now.month,
            "day": now.day,
            "hour": now.hour,
            "minute": now.minute,
            "second": now.second,
            "weekday": now.strftime("%A"),
            "weekday_chinese": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
        }
    
    @handle_time_errors
    def _get_date_info(self, date_string: str = None) -> Dict[str, Any]:
        """获取日期信息"""
        if date_string:
            target_date = datetime.strptime(date_string, "%Y-%m-%d")
        else:
            target_date = datetime.now()
        
        # 计算一些有用的信息
        year_start = datetime(target_date.year, 1, 1)
        days_in_year = (datetime(target_date.year + 1, 1, 1) - year_start).days
        day_of_year = (target_date - year_start).days + 1
        
        # 判断是否为闰年
        is_leap_year = target_date.year % 4 == 0 and (target_date.year % 100 != 0 or target_date.year % 400 == 0)
        
        # 获取月份天数
        if target_date.month == 12:
            next_month = datetime(target_date.year + 1, 1, 1)
        else:
            next_month = datetime(target_date.year, target_date.month + 1, 1)
        days_in_month = (next_month - datetime(target_date.year, target_date.month, 1)).days
        
        return {
            "status": "success",
            "date": target_date.strftime("%Y-%m-%d"),
            "year": target_date.year,
            "month": target_date.month,
            "day": target_date.day,
            "weekday": target_date.strftime("%A"),
            "weekday_chinese": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][target_date.weekday()],
            "day_of_year": day_of_year,
            "days_in_year": days_in_year,
            "days_in_month": days_in_month,
            "is_leap_year": is_leap_year,
            "quarter": (target_date.month - 1) // 3 + 1,
            "week_of_year": target_date.isocalendar()[1],
            "formatted_chinese": target_date.strftime("%Y年%m月%d日"),
            "formatted_readable": target_date.strftime("%Y年%m月%d日 %A")
        }
    
    @handle_time_errors
    def _calculate_time_difference(self, start_time: str, end_time: str, unit: str = "days") -> Dict[str, Any]:
        """计算时间差"""
        # 尝试解析不同格式的时间
        formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]
        
        start_dt = None
        end_dt = None
        
        for fmt in formats:
            try:
                start_dt = datetime.strptime(start_time, fmt)
                break
            except ValueError:
                continue
        
        for fmt in formats:
            try:
                end_dt = datetime.strptime(end_time, fmt)
                break
            except ValueError:
                continue
        
        if start_dt is None or end_dt is None:
            return {
                "status": "error",
                "error": "Invalid time format",
                "message": "时间格式错误，请使用 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS 格式"
            }
        
        # 计算时间差
        time_diff = end_dt - start_dt
        total_seconds = time_diff.total_seconds()
        
        # 根据单位返回结果
        if unit.lower() == "days":
            result_value = time_diff.days
        elif unit.lower() == "hours":
            result_value = total_seconds / 3600
        elif unit.lower() == "minutes":
            result_value = total_seconds / 60
        elif unit.lower() == "seconds":
            result_value = total_seconds
        else:
            result_value = time_diff.days
            unit = "days"
        
        return {
            "status": "success",
            "start_time": start_time,
            "end_time": end_time,
            "difference": {
                "value": result_value,
                "unit": unit,
                "total_days": time_diff.days,
                "total_hours": total_seconds / 3600,
                "total_minutes": total_seconds / 60,
                "total_seconds": total_seconds
            },
            "readable": f"{time_diff.days}天 {time_diff.seconds // 3600}小时 {(time_diff.seconds % 3600) // 60}分钟"
        }
    
    @handle_time_errors
    def _format_timestamp(self, timestamp: int, format_type: str = "readable", timezone_name: str = "local") -> Dict[str, Any]:
        """格式化时间戳"""
        # 将时间戳转换为datetime对象
        dt = datetime.fromtimestamp(timestamp)
        
        # 处理时区
        if timezone_name.lower() == "utc":
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        elif timezone_name.lower() == "beijing":
            dt = datetime.fromtimestamp(timestamp, tz=timezone(timedelta(hours=8)))
        
        # 格式化
        if format_type.lower() == "iso":
            formatted = dt.isoformat()
        elif format_type.lower() == "readable":
            formatted = dt.strftime("%Y年%m月%d日 %H:%M:%S")
        elif format_type.lower() == "custom":
            formatted = dt.strftime("%Y-%m-%d %H:%M:%S %A")
        else:
            formatted = dt.strftime("%Y年%m月%d日 %H:%M:%S")
        
        return {
            "status": "success",
            "timestamp": timestamp,
            "formatted_time": formatted,
            "timezone": timezone_name,
            "format": format_type,
            "year": dt.year,
            "month": dt.month,
            "day": dt.day,
            "hour": dt.hour,
            "minute": dt.minute,
            "second": dt.second
        }
    
if __name__ == "__main__":
    """作为HTTP服务器运行"""
    import sys
    import os
    import argparse
    import asyncio
    
    # 添加项目路径
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    
    from utcp.http_server import run_service_as_http_server
    
    # 解析命令行参数
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='localhost', help='服务器主机')
    parser.add_argument('--port', type=int, default=8006, help='服务器端口')
    
    args = parser.parse_args()

    # 启动HTTP服务器
    asyncio.run(run_service_as_http_server(TimeService, args.host, args.port))