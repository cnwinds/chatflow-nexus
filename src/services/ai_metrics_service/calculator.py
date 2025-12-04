#!/usr/bin/env python3
"""
AI指标服务费用计算器

使用自定义配置实现费用计算功能，支持多种模型的价格配置。

参考litellm的模型价格配置
https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json
"""

import logging
from typing import Dict, Any, Optional, Tuple

from src.services.ai_metrics_service.exceptions import CostCalculationError

logger = logging.getLogger(__name__)


class CostCalculator:
    """费用计算器 - 基于自定义配置"""
    
    def __init__(self, custom_pricing: Optional[Dict[str, Dict[str, Any]]] = None):
        """
        初始化费用计算器
        
        Args:
            custom_pricing: 自定义价格配置，格式为 {model_name: {"input_cost_per_token": float, "output_cost_per_token": float}}
        """
        self.custom_pricing = custom_pricing or {}
        logger.debug(f"费用计算器初始化完成，配置了 {len(self.custom_pricing)} 个模型的价格")
    
    def calculate_cost(self, model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
        """
        计算API调用费用
        
        Args:
            model_name: 模型名称
            prompt_tokens: 输入token数量
            completion_tokens: 输出token数量
            
        Returns:
            float: 调用费用（美元）
        """
        try:
            return self._calculate_with_custom_pricing(model_name, prompt_tokens, completion_tokens)
        except Exception as e:
            # 如果计算失败，记录错误并返回0
            logger.error(f"费用计算失败: {str(e)}")
            return 0.0
    
    def _calculate_with_custom_pricing(self, model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
        """使用自定义价格计算费用"""
        if model_name not in self.custom_pricing:
            logger.warning(f"模型 {model_name} 没有配置价格信息")
            return 0.0
        
        # 使用自定义价格计算
        model_pricing = self.custom_pricing[model_name]
        prompt_cost = prompt_tokens * model_pricing.get("input_cost_per_token", 0)
        completion_cost = completion_tokens * model_pricing.get("output_cost_per_token", 0)
        total_cost = prompt_cost + completion_cost
        
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"自定义费用计算: {model_name}, 输入: {prompt_tokens} tokens (${prompt_cost:.6f}), "
                       f"输出: {completion_tokens} tokens (${completion_cost:.6f}), 总计: ${total_cost:.6f}")
        
        return total_cost
    
    def calculate_cost_from_usage(self, model_name: str, usage_data: Dict[str, Any]) -> Tuple[float, float, float]:
        """
        从usage数据计算费用
        
        Args:
            model_name: 模型名称
            usage_data: 使用量数据，格式为 {"usage": {"prompt_tokens": int, "completion_tokens": int}}
            
        Returns:
            Tuple[float, float, float]: (总费用, 输入费用, 输出费用)
        """
        try:
            usage = usage_data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            
            # 使用自定义定价
            if model_name in self.custom_pricing:
                model_pricing = self.custom_pricing[model_name]
                prompt_cost = prompt_tokens * model_pricing.get("input_cost_per_token", 0)
                completion_cost = completion_tokens * model_pricing.get("output_cost_per_token", 0)
                total_cost = prompt_cost + completion_cost
            else:
                prompt_cost = completion_cost = total_cost = 0.0
            
            return total_cost, prompt_cost, completion_cost
            
        except Exception as e:
            logger.error(f"从usage数据计算费用失败: {e}")
            return 0.0, 0.0, 0.0
    
    def update_custom_pricing(self, model_name: str, input_price: float, output_price: float) -> None:
        """更新自定义价格"""
        if self.custom_pricing is None:
            self.custom_pricing = {}
        self.custom_pricing[model_name] = {
            "input_cost_per_token": input_price,
            "output_cost_per_token": output_price
        }
        logger.info(f"更新模型 {model_name} 的价格: 输入 ${input_price:.6f}/token, 输出 ${output_price:.6f}/token")
    
    def get_model_pricing(self, model_name: str) -> Dict[str, float]:
        """获取模型价格信息"""
        if model_name in self.custom_pricing:
            return {
                "input_cost_per_token": self.custom_pricing[model_name].get("input_cost_per_token", 0),
                "output_cost_per_token": self.custom_pricing[model_name].get("output_cost_per_token", 0)
            }
        
        # 如果获取失败，返回默认值
        return {
            "input_cost_per_token": 0,
            "output_cost_per_token": 0
        }
    
    def list_available_models(self) -> Dict[str, Dict[str, float]]:
        """列出所有可用模型的价格信息"""
        models = {}
        
        # 添加自定义定价的模型
        for model_name, pricing in self.custom_pricing.items():
            models[model_name] = {
                "input_cost_per_token": pricing.get("input_cost_per_token", 0),
                "output_cost_per_token": pricing.get("output_cost_per_token", 0)
            }
        
        return models
    
    def validate_pricing_config(self) -> Dict[str, Any]:
        """验证价格配置"""
        errors = []
        warnings = []
        
        # 检查自定义定价格式
        for model_name, pricing in self.custom_pricing.items():
            if not isinstance(pricing, dict):
                errors.append(f"模型 {model_name} 的价格配置格式错误")
                continue
            
            required_keys = ["input_cost_per_token", "output_cost_per_token"]
            for key in required_keys:
                if key not in pricing:
                    errors.append(f"模型 {model_name} 缺少价格配置: {key}")
                elif not isinstance(pricing[key], (int, float)) or pricing[key] < 0:
                    errors.append(f"模型 {model_name} 的价格配置 {key} 必须是正数")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        } 