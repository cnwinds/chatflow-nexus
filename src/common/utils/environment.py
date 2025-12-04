"""
环境变量管理工具
"""

import os
from typing import Dict, Any, Optional, List
from ..exceptions import EnvironmentError


class EnvironmentManager:
    """环境变量管理器"""
    
    def __init__(self, prefix: str = ""):
        """初始化环境变量管理器"""
        self.prefix = prefix
        self._cache = {}
    
    def get(self, name: str, default: str = None) -> str:
        """获取环境变量"""
        full_name = f"{self.prefix}_{name}"
        
        if full_name in self._cache:
            return self._cache[full_name]
        
        value = os.getenv(full_name, default)
        self._cache[full_name] = value
        return value
    
    def set(self, name: str, value: str):
        """设置环境变量"""
        full_name = f"{self.prefix}_{name}"
        os.environ[full_name] = value
        self._cache[full_name] = value
    
    def get_bool(self, name: str, default: bool = False) -> bool:
        """获取布尔环境变量"""
        value = self.get(name, str(default))
        return value.lower() in ('true', '1', 'yes', 'on')
    
    def get_int(self, name: str, default: int = 0) -> int:
        """获取整数环境变量"""
        value = self.get(name, str(default))
        try:
            return int(value)
        except ValueError:
            return default
    
    def get_float(self, name: str, default: float = 0.0) -> float:
        """获取浮点数环境变量"""
        value = self.get(name, str(default))
        try:
            return float(value)
        except ValueError:
            return default
    
    def get_list(self, name: str, default: List[str] = None, separator: str = ',') -> List[str]:
        """获取列表环境变量"""
        if default is None:
            default = []
        
        value = self.get(name)
        if value is None:
            return default
        
        return [item.strip() for item in value.split(separator) if item.strip()]
    
    def get_dict(self, name: str, default: Dict[str, str] = None, separator: str = ',', key_value_separator: str = '=') -> Dict[str, str]:
        """获取字典环境变量"""
        if default is None:
            default = {}
        
        value = self.get(name)
        if value is None:
            return default
        
        result = {}
        for item in value.split(separator):
            if key_value_separator in item:
                key, val = item.split(key_value_separator, 1)
                result[key.strip()] = val.strip()
        
        return result
    
    def exists(self, name: str) -> bool:
        """检查环境变量是否存在"""
        full_name = f"{self.prefix}_{name}"
        return full_name in os.environ
    
    def remove(self, name: str):
        """删除环境变量"""
        full_name = f"{self.prefix}_{name}"
        if full_name in os.environ:
            del os.environ[full_name]
        if full_name in self._cache:
            del self._cache[full_name]
    
    def get_all(self) -> Dict[str, str]:
        """获取所有以指定前缀开头的环境变量"""
        result = {}
        for key, value in os.environ.items():
            if key.startswith(f"{self.prefix}_"):
                short_name = key[len(f"{self.prefix}_"):]
                result[short_name] = value
        
        return result
    
    def set_multiple(self, variables: Dict[str, str]):
        """批量设置环境变量"""
        for name, value in variables.items():
            self.set(name, value)
    
    def clear_cache(self):
        """清除缓存"""
        self._cache.clear()
    
    def validate_required(self, required_vars: List[str]) -> List[str]:
        """验证必需的环境变量"""
        missing = []
        for var in required_vars:
            if not self.exists(var):
                missing.append(var)
        return missing
    
    def get_service_config(self, service_name: str) -> Dict[str, Any]:
        """获取服务特定的环境变量配置"""
        config = {}
        service_prefix = f"{service_name.upper()}"
        
        for key, value in os.environ.items():
            if key.startswith(f"{service_prefix}_"):
                config_key = key[len(f"{service_prefix}_"):].lower()
                config[config_key] = value
        
        return config
    
    def export_to_dict(self) -> Dict[str, str]:
        """导出所有环境变量到字典"""
        return dict(os.environ)
    
    def import_from_dict(self, env_dict: Dict[str, str]):
        """从字典导入环境变量"""
        for key, value in env_dict.items():
            os.environ[key] = value
            self._cache[key] = value 