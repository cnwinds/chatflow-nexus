#!/usr/bin/env python3
"""
AI指标服务数据模型

定义性能监控和费用计算相关的数据模型，包括数据库表结构。
"""

import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime


@dataclass
class CallMetrics:
    """单次调用的完整指标"""
    monitor_id: str
    provider: str
    model_name: str
    session_id: Optional[str] = None
    start_time: float = 0.0
    end_time: Optional[float] = None
    
    # Token统计
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    
    # 内容统计
    input_chars: int = 0
    output_chars: int = 0
    
    # 工具相关
    tool_count: int = 0
    tool_calls_made: int = 0
    
    # 费用信息
    cost: float = 0.0
    input_cost: float = 0.0
    output_cost: float = 0.0
    
    # HTTP首字节时间（毫秒）
    http_first_byte_time: Optional[float] = None
    
    # 第一个token时间（毫秒）
    first_token_time: Optional[float] = None
    
    # 调用结果
    result: Optional[str] = None
    
    def __post_init__(self):
        """初始化后计算派生字段"""
        if self.end_time is None:
            self.end_time = time.time()
        
        # 计算总token数
        if self.total_tokens == 0:
            self.total_tokens = self.prompt_tokens + self.completion_tokens
    
    @property
    def total_time(self) -> float:
        """总耗时（毫秒）"""
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time) * 1000
    
    @property
    def tokens_per_second(self) -> float:
        """生成速度（tokens/秒）"""
        if self.total_time <= 0:
            return 0.0
        return self.completion_tokens / (self.total_time / 1000)
    
    @property
    def cost_per_token(self) -> float:
        """每token成本"""
        if self.total_tokens == 0:
            return 0.0
        return self.cost / self.total_tokens
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "monitor_id": self.monitor_id,
            "model_name": self.model_name,
            "provider": self.provider,
            "session_id": self.session_id,
            "start_time": self.start_time,
            "end_time": self.end_time,

            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "input_chars": self.input_chars,
            "output_chars": self.output_chars,
            "tool_count": self.tool_count,
            "tool_calls_made": self.tool_calls_made,
            "cost": self.cost,
            "input_cost": self.input_cost,
            "output_cost": self.output_cost,
            "http_first_byte_time": self.http_first_byte_time,
            "first_token_time": self.first_token_time,
            "result": self.result,
            "total_time": self.total_time,
            "tokens_per_second": self.tokens_per_second,
            "cost_per_token": self.cost_per_token
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CallMetrics':
        """从字典创建实例"""
        # 只保留dataclass定义的字段，过滤掉计算属性
        field_names = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in field_names}
        return cls(**filtered)


@dataclass
class ModelPricing:
    """模型定价信息"""
    model_name: str
    input_price_per_1k_tokens: float  # 每1000个输入token的价格
    output_price_per_1k_tokens: float  # 每1000个输出token的价格
    currency: str = "USD"
    last_updated: float = field(default_factory=time.time)
    
    @property
    def input_cost_per_token(self) -> float:
        """每输入token的成本"""
        return self.input_price_per_1k_tokens / 1000
    
    @property
    def output_cost_per_token(self) -> float:
        """每输出token的成本"""
        return self.output_price_per_1k_tokens / 1000
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "model_name": self.model_name,
            "input_price_per_1k_tokens": self.input_price_per_1k_tokens,
            "output_price_per_1k_tokens": self.output_price_per_1k_tokens,
            "currency": self.currency,
            "last_updated": self.last_updated
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ModelPricing':
        """从字典创建实例"""
        return cls(**data)

