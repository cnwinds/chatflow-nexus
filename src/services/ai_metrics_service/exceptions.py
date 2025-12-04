#!/usr/bin/env python3
"""
AI指标服务异常定义

定义服务中使用的各种异常类型。
"""


class AIMetricsError(Exception):
    """AI指标服务基础异常"""
    pass


class MonitoringError(AIMetricsError):
    """监控相关异常"""
    pass


class CostCalculationError(AIMetricsError):
    """费用计算异常"""
    pass


class DataPersistenceError(AIMetricsError):
    """数据持久化异常"""
    pass


class ConfigurationError(AIMetricsError):
    """配置相关异常"""
    pass


class ValidationError(AIMetricsError):
    """数据验证异常"""
    pass 