#!/usr/bin/env python3
"""
UTCP天气查询服务
基于UTCP协议实现的天气查询服务，进程内集成版本
提供获取当前天气、天气预报和空气质量等功能
"""

import logging
import aiohttp
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable
from functools import wraps
from src.utcp.utcp import UTCPService

# 配置日志
logger = logging.getLogger(__name__)


def handle_weather_errors(func: Callable) -> Callable:
    """装饰器：统一错误处理"""
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except Exception as e:
            logger.error(f"{func.__name__} 失败: {e}")
            return {
                "status": "error",
                "error": str(e),
                "message": f"天气查询失败: {str(e)}"
            }
    return wrapper


class WeatherService(UTCPService):
    """天气查询服务 - UTCP进程内集成版本"""
    
    # 插件不允许写__init__方法，只能通过init方法进行初始化
    
    def init(self) -> None:
        """插件初始化方法"""
        # 初始化配置相关属性
        self.base_url = self.config.get("base_url", "https://api.open-meteo.com/v1")
        self.geocoding_url = "https://geocoding-api.open-meteo.com/v1/search"
        self.session = None
        
        # 从配置获取默认位置和API密钥
        self.default_location = self.config.get("default_location", "北京")
        self.api_key = self.config.get("api_key")  # 对于Open-Meteo不需要，但保留以备将来使用其他API
        self.timeout = self.config.get("timeout", 30)
        
        # 天气代码映射
        self.weather_codes = {
            0: ("晴天", "万里无云"),
            1: ("晴天", "基本晴朗"),
            2: ("多云", "部分多云"),
            3: ("阴天", "阴云密布"),
            45: ("雾", "有雾"),
            48: ("雾", "结霜雾"),
            51: ("毛毛雨", "轻微毛毛雨"),
            53: ("毛毛雨", "中等毛毛雨"),
            55: ("毛毛雨", "密集毛毛雨"),
            61: ("小雨", "轻微降雨"),
            63: ("中雨", "中等降雨"),
            65: ("大雨", "强降雨"),
            71: ("小雪", "轻微降雪"),
            73: ("中雪", "中等降雪"),
            75: ("大雪", "强降雪"),
            95: ("雷暴", "雷暴天气")
        }
    
    @property
    def name(self) -> str:
        """服务名称"""
        return "weather_service"
    
    @property
    def description(self) -> str:
        """服务描述"""
        return "提供实时天气、天气预报和空气质量查询服务"
    
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
        return [
            # 当前天气工具
            self._create_tool_definition(
                "get_current_weather", "获取指定城市的当前天气信息",
                {
                    "city": {
                        "type": "string",
                        "description": "城市名称",
                        "default": "北京"
                    },
                    "country": {
                        "type": "string",
                        "description": "国家代码（可选）",
                        "default": ""
                    }
                }
            ),
            
            # 天气预报工具
            self._create_tool_definition(
                "get_weather_forecast", "获取指定城市的天气预报",
                {
                    "city": {
                        "type": "string",
                        "description": "城市名称",
                        "default": "北京"
                    },
                    "days": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 7,
                        "description": "预报天数（1-7天）",
                        "default": 3
                    },
                    "country": {
                        "type": "string",
                        "description": "国家代码（可选）",
                        "default": ""
                    }
                }
            ),
            
            # 空气质量工具
            self._create_tool_definition(
                "get_air_quality", "获取指定城市的空气质量信息",
                {
                    "city": {
                        "type": "string",
                        "description": "城市名称",
                        "default": "北京"
                    },
                    "country": {
                        "type": "string",
                        "description": "国家代码（可选）",
                        "default": ""
                    }
                }
            ),
        ]
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """执行天气服务工具"""
        # 工具映射表
        tool_handlers = {
            "get_current_weather": lambda: self._get_current_weather(arguments),
            "get_weather_forecast": lambda: self._get_weather_forecast(arguments),
            "get_air_quality": lambda: self._get_air_quality(arguments),
        }
        
        try:
            if tool_name not in tool_handlers:
                raise ValueError(f"未知的天气工具: {tool_name}")
            
            return await tool_handlers[tool_name]()
        except Exception as e:
            logger.error(f"执行工具 '{tool_name}' 时出错: {e}")
            return {
                "status": "error",
                "error": str(e),
                "message": f"天气查询失败: {str(e)}"
            }
    
    async def _ensure_session(self) -> None:
        """确保HTTP会话已创建"""
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self.session = aiohttp.ClientSession(timeout=timeout)
    
    async def _make_request(self, url: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """发起HTTP请求的通用方法"""
        await self._ensure_session()
        
        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"HTTP请求失败: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"HTTP请求异常: {e}")
            return None
    
    async def _get_coordinates(self, city: str, country: str = "") -> Optional[Dict[str, Any]]:
        """通过城市名称获取经纬度坐标"""
        try:
            params = {
                "name": city,
                "count": 1,
                "language": "zh,en",
                "format": "json"
            }
            
            if country:
                params["country"] = country
            
            data = await self._make_request(self.geocoding_url, params)
            
            if data and data.get("results") and len(data["results"]) > 0:
                result = data["results"][0]
                return {
                    "latitude": result["latitude"],
                    "longitude": result["longitude"],
                    "name": result["name"],
                    "country": result.get("country", ""),
                    "admin1": result.get("admin1", "")
                }
            else:
                logger.warning(f"未找到城市坐标: {city}")
                return None
        except Exception as e:
            logger.error(f"获取坐标失败: {e}")
            return None
    
    def _get_weather_description(self, code: int) -> Dict[str, str]:
        """根据天气代码获取天气描述"""
        if code in self.weather_codes:
            weather_type, description = self.weather_codes[code]
            return {
                "type": weather_type,
                "description": description,
                "code": code
            }
        else:
            return {
                "type": "未知",
                "description": f"天气代码: {code}",
                "code": code
            }
    
    @handle_weather_errors
    async def _get_current_weather(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """获取当前天气"""
        city = arguments.get("city", self.default_location)
        country = arguments.get("country", "")
        
        # 获取城市坐标
        coords = await self._get_coordinates(city, country)
        if not coords:
            raise ValueError(f"无法获取城市坐标: {city}")
        
        # 构建天气API请求参数
        params = {
            "latitude": coords["latitude"],
            "longitude": coords["longitude"],
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m,wind_direction_10m",
            "timezone": "auto"
        }
        
        # 发起天气API请求
        weather_data = await self._make_request(f"{self.base_url}/forecast", params)
        
        if not weather_data or "current" not in weather_data:
            raise ValueError("获取天气数据失败")
        
        current = weather_data["current"]
        
        # 处理天气信息
        weather_info = self._get_weather_description(current.get("weather_code", 0))
        
        return {
            "status": "success",
            "location": {
                "city": coords["name"],
                "country": coords["country"],
                "admin1": coords["admin1"],
                "latitude": coords["latitude"],
                "longitude": coords["longitude"]
            },
            "current_weather": {
                "temperature": current.get("temperature_2m"),
                "feels_like": current.get("apparent_temperature"),
                "humidity": current.get("relative_humidity_2m"),
                "precipitation": current.get("precipitation"),
                "wind_speed": current.get("wind_speed_10m"),
                "wind_direction": current.get("wind_direction_10m"),
                "weather": weather_info,
                "time": current.get("time")
            },
            "units": weather_data.get("current_units", {})
        }
    
    @handle_weather_errors
    async def _get_weather_forecast(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """获取天气预报"""
        city = arguments.get("city", self.default_location)
        days = arguments.get("days", 3)
        country = arguments.get("country", "")
        
        # 获取城市坐标
        coords = await self._get_coordinates(city, country)
        if not coords:
            raise ValueError(f"无法获取城市坐标: {city}")
        
        # 构建天气预报API请求参数
        params = {
            "latitude": coords["latitude"],
            "longitude": coords["longitude"],
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
            "timezone": "auto"
        }
        
        # 发起天气预报API请求
        forecast_data = await self._make_request(f"{self.base_url}/forecast", params)
        
        if not forecast_data or "daily" not in forecast_data:
            raise ValueError("获取天气预报数据失败")
        
        daily = forecast_data["daily"]
        
        # 处理预报数据
        forecasts = []
        for i in range(min(days, len(daily["time"]))):
            weather_info = self._get_weather_description(daily["weather_code"][i])
            forecasts.append({
                "date": daily["time"][i],
                "max_temperature": daily["temperature_2m_max"][i],
                "min_temperature": daily["temperature_2m_min"][i],
                "precipitation": daily["precipitation_sum"][i],
                "weather": weather_info
            })
        
        return {
            "status": "success",
            "location": {
                "city": coords["name"],
                "country": coords["country"],
                "admin1": coords["admin1"]
            },
            "forecast_days": days,
            "forecasts": forecasts,
            "units": forecast_data.get("daily_units", {})
        }
    
    @handle_weather_errors
    async def _get_air_quality(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """获取空气质量信息"""
        city = arguments.get("city", self.default_location)
        country = arguments.get("country", "")
        
        # 获取城市坐标
        coords = await self._get_coordinates(city, country)
        if not coords:
            raise ValueError(f"无法获取城市坐标: {city}")
        
        # 构建空气质量API请求参数
        params = {
            "latitude": coords["latitude"],
            "longitude": coords["longitude"],
            "hourly": "pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,european_aqi",
            "timezone": "auto"
        }
        
        # 发起空气质量API请求
        air_quality_data = await self._make_request(f"{self.base_url}/air-quality", params)
        
        if not air_quality_data or "hourly" not in air_quality_data:
            raise ValueError("获取空气质量数据失败")
        
        hourly = air_quality_data["hourly"]
        
        # 获取最新的空气质量数据
        latest_index = -1
        for i, time_str in enumerate(hourly["time"]):
            if time_str:  # 找到最新的有效数据
                latest_index = i
                break
        
        if latest_index == -1:
            raise ValueError("未找到有效的空气质量数据")
        
        # 空气质量等级评估
        def get_aqi_level(aqi_value):
            if aqi_value <= 20:
                return "优秀"
            elif aqi_value <= 40:
                return "良好"
            elif aqi_value <= 60:
                return "中等"
            elif aqi_value <= 80:
                return "较差"
            elif aqi_value <= 100:
                return "差"
            else:
                return "很差"
        
        aqi_value = hourly["european_aqi"][latest_index]
        
        return {
            "status": "success",
            "location": {
                "city": coords["name"],
                "country": coords["country"],
                "admin1": coords["admin1"]
            },
            "air_quality": {
                "aqi": aqi_value,
                "level": get_aqi_level(aqi_value),
                "pm10": hourly["pm10"][latest_index],
                "pm2_5": hourly["pm2_5"][latest_index],
                "carbon_monoxide": hourly["carbon_monoxide"][latest_index],
                "nitrogen_dioxide": hourly["nitrogen_dioxide"][latest_index],
                "time": hourly["time"][latest_index]
            },
            "units": air_quality_data.get("hourly_units", {})
        }
    
    async def close(self) -> None:
        """关闭HTTP会话"""
        if self.session:
            await self.session.close()
            self.session = None
    
    def __del__(self):
        """析构函数，确保会话被关闭"""
        try:
            # 检查session属性是否存在
            if hasattr(self, 'session') and self.session and not self.session.closed:
                logger.warning("WeatherService会话未正确关闭，建议显式调用close()方法")
        except Exception as e:
            # 析构函数中的异常不应该被抛出，只记录日志
            logger.debug(f"WeatherService析构时检查session失败: {e}")

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
    parser.add_argument('--port', type=int, default=8007, help='服务器端口')
    
    args = parser.parse_args()

    # 启动HTTP服务器
    asyncio.run(run_service_as_http_server(WeatherService, args.host, args.port))