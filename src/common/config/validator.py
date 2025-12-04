#!/usr/bin/env python3
"""
UTCP通用配置验证工具

提供灵活的配置验证功能，支持：
- 必需字段检查
- 类型验证
- 范围验证
- 自定义验证规则
"""

import logging
from typing import Dict, Any, List, Optional, Union, Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class ValidationType(Enum):
    """验证类型枚举"""
    REQUIRED = "required"
    TYPE = "type"
    RANGE = "range"
    CUSTOM = "custom"
    PATTERN = "pattern"

@dataclass
class ValidationRule:
    """验证规则数据类"""
    type: ValidationType
    message: Optional[str] = None
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    pattern: Optional[str] = None
    custom_validator: Optional[Callable[[Any], bool]] = None

class ConfigValidator:
    """通用配置验证器"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化配置验证器
        
        Args:
            config: 要验证的配置字典
        """
        self.config = config
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def validate_required_keys(self, required_keys: List[str]) -> bool:
        """验证必需字段
        
        Args:
            required_keys: 必需字段的路径列表，支持点分隔的嵌套路径
            
        Returns:
            bool: 验证是否通过
        """
        missing_keys = []
        
        for key_path in required_keys:
            keys = key_path.split('.')
            value = self.config
            
            for key in keys:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    missing_keys.append(key_path)
                    break
        
        if missing_keys:
            error_msg = f"缺少必需的配置项: {', '.join(missing_keys)}"
            self.errors.append(error_msg)
            logger.error(error_msg)
            return False
        
        return True
    
    def validate_rules(self, validation_rules: Dict[str, Dict[str, Any]]) -> bool:
        """验证配置规则
        
        Args:
            validation_rules: 验证规则字典，格式为 {路径: 规则}
            
        Returns:
            bool: 验证是否通过
        """
        all_valid = True
        
        for key_path, rule in validation_rules.items():
            keys = key_path.split('.')
            value = self.config
            
            # 获取配置值
            for key in keys:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    # 如果路径不存在，跳过验证（除非是必需字段）
                    if rule.get("required", False):
                        error_msg = f"配置项 {key_path} 不存在"
                        self.errors.append(error_msg)
                        logger.error(error_msg)
                        all_valid = False
                    break
            else:
                # 验证值
                if not self._validate_value(key_path, value, rule):
                    all_valid = False
        
        return all_valid
    
    def _validate_value(self, key_path: str, value: Any, rule: Dict[str, Any]) -> bool:
        """验证单个配置值
        
        Args:
            key_path: 配置项路径
            value: 配置值
            rule: 验证规则
            
        Returns:
            bool: 验证是否通过
        """
        # 类型检查
        expected_type = rule.get("type")
        if expected_type:
            if not self._validate_type(key_path, value, expected_type):
                return False
        
        # 范围检查
        min_val = rule.get("min")
        max_val = rule.get("max")
        if min_val is not None or max_val is not None:
            if not self._validate_range(key_path, value, min_val, max_val):
                return False
        
        # 模式检查
        pattern = rule.get("pattern")
        if pattern:
            if not self._validate_pattern(key_path, value, pattern):
                return False
        
        # 自定义验证
        custom_validator = rule.get("custom")
        if custom_validator and callable(custom_validator):
            if not self._validate_custom(key_path, value, custom_validator):
                return False
        
        return True
    
    def _validate_type(self, key_path: str, value: Any, expected_type: str) -> bool:
        """验证类型
        
        Args:
            key_path: 配置项路径
            value: 配置值
            expected_type: 期望的类型
            
        Returns:
            bool: 类型是否匹配
        """
        type_map = {
            "int": int,
            "float": (int, float),
            "str": str,
            "bool": bool,
            "list": list,
            "dict": dict
        }
        
        if expected_type not in type_map:
            logger.warning(f"未知的类型验证: {expected_type}")
            return True
        
        expected_types = type_map[expected_type]
        if not isinstance(value, expected_types):
            error_msg = f"配置项 {key_path} 必须是 {expected_type} 类型，当前类型: {type(value).__name__}"
            self.errors.append(error_msg)
            logger.error(error_msg)
            return False
        
        return True
    
    def _validate_range(self, key_path: str, value: Any, min_val: Optional[Union[int, float]], 
                       max_val: Optional[Union[int, float]]) -> bool:
        """验证范围
        
        Args:
            key_path: 配置项路径
            value: 配置值
            min_val: 最小值
            max_val: 最大值
            
        Returns:
            bool: 范围是否有效
        """
        if not isinstance(value, (int, float)):
            return True  # 非数值类型跳过范围验证
        
        if min_val is not None and value < min_val:
            error_msg = f"配置项 {key_path} 值 {value} 小于最小值 {min_val}"
            self.errors.append(error_msg)
            logger.error(error_msg)
            return False
        
        if max_val is not None and value > max_val:
            error_msg = f"配置项 {key_path} 值 {value} 大于最大值 {max_val}"
            self.errors.append(error_msg)
            logger.error(error_msg)
            return False
        
        return True
    
    def _validate_pattern(self, key_path: str, value: Any, pattern: str) -> bool:
        """验证模式（正则表达式）
        
        Args:
            key_path: 配置项路径
            value: 配置值
            pattern: 正则表达式模式
            
        Returns:
            bool: 模式是否匹配
        """
        import re
        
        if not isinstance(value, str):
            return True  # 非字符串类型跳过模式验证
        
        if not re.match(pattern, value):
            error_msg = f"配置项 {key_path} 值 '{value}' 不匹配模式 '{pattern}'"
            self.errors.append(error_msg)
            logger.error(error_msg)
            return False
        
        return True
    
    def _validate_custom(self, key_path: str, value: Any, validator: Callable[[Any], bool]) -> bool:
        """自定义验证
        
        Args:
            key_path: 配置项路径
            value: 配置值
            validator: 自定义验证函数
            
        Returns:
            bool: 自定义验证是否通过
        """
        try:
            if not validator(value):
                error_msg = f"配置项 {key_path} 自定义验证失败"
                self.errors.append(error_msg)
                logger.error(error_msg)
                return False
        except Exception as e:
            error_msg = f"配置项 {key_path} 自定义验证异常: {e}"
            self.errors.append(error_msg)
            logger.error(error_msg)
            return False
        
        return True
    
    def validate(self, validation_config: Dict[str, Any]) -> bool:
        """执行完整的配置验证
        
        Args:
            validation_config: 验证配置，包含 required_keys 和 rules
            
        Returns:
            bool: 验证是否通过
        """
        self.errors.clear()
        self.warnings.clear()
        
        # 验证必需字段
        required_keys = validation_config.get("required_keys", [])
        required_valid = self.validate_required_keys(required_keys)
        
        # 验证规则
        validation_rules = validation_config.get("rules", {})
        rules_valid = self.validate_rules(validation_rules)
        
        # 记录验证结果
        if required_valid and rules_valid:
            pass
        else:
            logger.error(f"配置验证失败，共 {len(self.errors)} 个错误")
        
        return required_valid and rules_valid
    
    def get_errors(self) -> List[str]:
        """获取验证错误列表"""
        return self.errors.copy()
    
    def get_warnings(self) -> List[str]:
        """获取验证警告列表"""
        return self.warnings.copy()
    
    def has_errors(self) -> bool:
        """是否有验证错误"""
        return len(self.errors) > 0
    
    def raise_if_errors(self) -> None:
        """如果有错误则抛出异常"""
        if self.has_errors():
            raise ValueError(f"配置验证失败:\n" + "\n".join(self.errors))

# 便捷函数
def validate_config(config: Dict[str, Any], validation_config: Dict[str, Any]) -> bool:
    """便捷的配置验证函数
    
    Args:
        config: 要验证的配置
        validation_config: 验证配置
        
    Returns:
        bool: 验证是否通过
    """
    validator = ConfigValidator(config)
    return validator.validate(validation_config)

def validate_config_strict(config: Dict[str, Any], validation_config: Dict[str, Any]) -> None:
    """严格的配置验证函数，失败时抛出异常
    
    Args:
        config: 要验证的配置
        validation_config: 验证配置
        
    Raises:
        ValueError: 验证失败时抛出
    """
    validator = ConfigValidator(config)
    if not validator.validate(validation_config):
        validator.raise_if_errors() 