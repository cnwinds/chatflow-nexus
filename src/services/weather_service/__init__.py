#!/usr/bin/env python3
"""
UTCP天气服务包

基于UTCP协议实现的天气查询服务，提供获取当前天气、天气预报和空气质量等功能
"""

from .service import WeatherService

__all__ = ['WeatherService'] 