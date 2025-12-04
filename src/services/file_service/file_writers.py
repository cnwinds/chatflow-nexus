"""
文件格式写入器：YAML, JSON, INI
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Union
import yaml
from ruamel.yaml import YAML as RuamelYAML
from configparser import ConfigParser

logger = logging.getLogger(__name__)


def set_nested_value(data: Any, key_path: List[Union[str, int]], value: Any) -> None:
    """
    在嵌套结构中设置值
    
    Args:
        data: 数据结构（dict, list等）
        key_path: key路径列表
        value: 要设置的值
        
    Raises:
        KeyError: 如果路径无效
    """
    current = data
    
    # 导航到目标位置的父级
    for i, key in enumerate(key_path[:-1]):
        if isinstance(current, dict):
            if key not in current:
                # 创建新的字典
                current[key] = {}
            current = current[key]
        elif isinstance(current, list):
            if not isinstance(key, int):
                raise KeyError(f"列表索引必须是整数，得到: {type(key).__name__}")
            if key < 0 or key >= len(current):
                raise KeyError(f"列表索引 {key} 超出范围 [0, {len(current)-1}]")
            current = current[key]
        else:
            raise KeyError(f"无法从 {type(current).__name__} 类型中访问key '{key}'")
    
    # 设置值
    final_key = key_path[-1]
    if isinstance(current, dict):
        current[final_key] = value
    elif isinstance(current, list):
        if not isinstance(final_key, int):
            raise KeyError(f"列表索引必须是整数，得到: {type(final_key).__name__}")
        if final_key < 0 or final_key >= len(current):
            raise KeyError(f"列表索引 {final_key} 超出范围 [0, {len(current)-1}]")
        current[final_key] = value
    else:
        raise KeyError(f"无法在 {type(current).__name__} 类型中设置值")


class YAMLWriter:
    """YAML文件写入器（保持格式和注释）"""
    
    @staticmethod
    def write(file_path: Path, data: Dict[str, Any]) -> None:
        """写入YAML文件，保持格式"""
        try:
            yaml_writer = RuamelYAML()
            yaml_writer.preserve_quotes = True
            yaml_writer.width = 4096  # 避免长行换行
            
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml_writer.dump(data, f)
        except Exception as e:
            raise ValueError(f"写入YAML文件失败: {e}")
    
    @staticmethod
    def set_value(data: Dict[str, Any], key_path: str, value: Any) -> None:
        """设置指定key的值"""
        from src.services.file_service.file_parsers import parse_key_path
        path = parse_key_path(key_path)
        set_nested_value(data, path, value)


class JSONWriter:
    """JSON文件写入器"""
    
    @staticmethod
    def write(file_path: Path, data: Dict[str, Any]) -> None:
        """写入JSON文件，格式化输出"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            raise ValueError(f"写入JSON文件失败: {e}")
    
    @staticmethod
    def set_value(data: Dict[str, Any], key_path: str, value: Any) -> None:
        """设置指定key的值"""
        from src.services.file_service.file_parsers import parse_key_path
        path = parse_key_path(key_path)
        set_nested_value(data, path, value)


class INIWriter:
    """INI文件写入器"""
    
    @staticmethod
    def write(file_path: Path, config: ConfigParser) -> None:
        """写入INI文件"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                config.write(f)
        except Exception as e:
            raise ValueError(f"写入INI文件失败: {e}")
    
    @staticmethod
    def set_value(config: ConfigParser, key_path: str, value: str) -> None:
        """设置指定key的值"""
        from src.services.file_service.file_parsers import parse_key_path
        path = parse_key_path(key_path)
        
        if len(path) < 2:
            raise ValueError(f"INI格式的key路径必须包含section和key，如 'section.key'，当前: {key_path}")
        
        section = path[0]
        key = '.'.join(str(p) for p in path[1:])
        
        # 如果section不存在，创建它
        if not config.has_section(section):
            config.add_section(section)
        
        config.set(section, key, str(value))


def get_writer(file_path: Path):
    """
    根据文件扩展名获取相应的写入器
    
    Args:
        file_path: 文件路径
        
    Returns:
        写入器实例
    """
    ext = file_path.suffix.lower()
    
    if ext in ['.yaml', '.yml']:
        return YAMLWriter()
    elif ext == '.json':
        return JSONWriter()
    elif ext in ['.ini', '.cfg']:
        return INIWriter()
    else:
        raise ValueError(f"不支持的文件格式: {ext}")

