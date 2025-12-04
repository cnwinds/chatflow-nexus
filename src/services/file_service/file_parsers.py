"""
文件格式解析器：YAML, JSON, INI, Markdown
"""

import json
import re
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
import yaml
from configparser import ConfigParser

logger = logging.getLogger(__name__)


def parse_key_path(key_path: str) -> List[Union[str, int]]:
    """
    解析点号分隔的key路径，支持数组索引
    
    Args:
        key_path: 点号分隔的路径，如 "database.host" 或 "items[0].name"
        
    Returns:
        key路径列表，包含字符串和整数索引
    """
    if not key_path:
        return []
    
    parts = []
    current = ""
    i = 0
    
    while i < len(key_path):
        if key_path[i] == '.':
            if current:
                parts.append(current)
                current = ""
        elif key_path[i] == '[':
            # 处理数组索引
            if current:
                parts.append(current)
                current = ""
            i += 1
            index_str = ""
            while i < len(key_path) and key_path[i] != ']':
                index_str += key_path[i]
                i += 1
            if i < len(key_path) and key_path[i] == ']':
                try:
                    parts.append(int(index_str))
                except ValueError:
                    raise ValueError(f"无效的数组索引: [{index_str}]")
            else:
                raise ValueError(f"未闭合的数组索引: [{index_str}")
        else:
            current += key_path[i]
        i += 1
    
    if current:
        parts.append(current)
    
    return parts


def get_nested_value(data: Any, key_path: List[Union[str, int]]) -> Any:
    """
    从嵌套结构中获取值
    
    Args:
        data: 数据结构（dict, list等）
        key_path: key路径列表
        
    Returns:
        找到的值
        
    Raises:
        KeyError: 如果key不存在
    """
    current = data
    
    for key in key_path:
        if isinstance(current, dict):
            if key not in current:
                raise KeyError(f"Key '{key}' 不存在")
            current = current[key]
        elif isinstance(current, list):
            if not isinstance(key, int):
                raise KeyError(f"列表索引必须是整数，得到: {type(key).__name__}")
            if key < 0 or key >= len(current):
                raise KeyError(f"列表索引 {key} 超出范围 [0, {len(current)-1}]")
            current = current[key]
        else:
            raise KeyError(f"无法从 {type(current).__name__} 类型中访问key '{key}'")
    
    return current


def get_nested_keys(data: Any, key_path: List[Union[str, int]] = None) -> List[str]:
    """
    获取嵌套结构中的子key列表
    
    Args:
        data: 数据结构
        key_path: 可选的key路径，如果提供则先导航到该位置
        
    Returns:
        子key列表
    """
    if key_path:
        try:
            data = get_nested_value(data, key_path)
        except KeyError as e:
            return []
    
    if isinstance(data, dict):
        return list(data.keys())
    elif isinstance(data, list):
        return [f"[{i}]" for i in range(len(data))]
    else:
        return []


class YAMLParser:
    """YAML文件解析器"""
    
    @staticmethod
    def parse(file_path: Path) -> Dict[str, Any]:
        """解析YAML文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = yaml.safe_load(f)
                return content if content is not None else {}
        except yaml.YAMLError as e:
            raise ValueError(f"YAML解析错误: {e}")
        except Exception as e:
            raise ValueError(f"读取YAML文件失败: {e}")
    
    @staticmethod
    def get_value(data: Dict[str, Any], key_path: str) -> Any:
        """获取指定key的值"""
        path = parse_key_path(key_path)
        return get_nested_value(data, path)
    
    @staticmethod
    def list_keys(data: Dict[str, Any], key_path: str = None) -> List[str]:
        """列出子keys"""
        path = parse_key_path(key_path) if key_path else []
        return get_nested_keys(data, path)


class JSONParser:
    """JSON文件解析器"""
    
    @staticmethod
    def parse(file_path: Path) -> Dict[str, Any]:
        """解析JSON文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON解析错误: {e}")
        except Exception as e:
            raise ValueError(f"读取JSON文件失败: {e}")
    
    @staticmethod
    def get_value(data: Dict[str, Any], key_path: str) -> Any:
        """获取指定key的值"""
        path = parse_key_path(key_path)
        return get_nested_value(data, path)
    
    @staticmethod
    def list_keys(data: Dict[str, Any], key_path: str = None) -> List[str]:
        """列出子keys"""
        path = parse_key_path(key_path) if key_path else []
        return get_nested_keys(data, path)


class INIParser:
    """INI文件解析器"""
    
    @staticmethod
    def parse(file_path: Path) -> ConfigParser:
        """解析INI文件"""
        try:
            config = ConfigParser()
            # 保持大小写
            config.optionxform = str
            config.read(file_path, encoding='utf-8')
            return config
        except Exception as e:
            raise ValueError(f"INI解析错误: {e}")
    
    @staticmethod
    def get_value(config: ConfigParser, key_path: str) -> str:
        """获取指定key的值"""
        path = parse_key_path(key_path)
        
        if len(path) < 2:
            raise ValueError(f"INI格式的key路径必须包含section和key，如 'section.key'，当前: {key_path}")
        
        section = path[0]
        key = '.'.join(str(p) for p in path[1:])
        
        if not config.has_section(section):
            raise KeyError(f"Section '{section}' 不存在")
        
        if not config.has_option(section, key):
            raise KeyError(f"Key '{key}' 在section '{section}' 中不存在")
        
        return config.get(section, key)
    
    @staticmethod
    def list_keys(config: ConfigParser, key_path: str = None) -> List[str]:
        """列出子keys"""
        if not key_path:
            # 返回所有sections
            return config.sections()
        
        path = parse_key_path(key_path)
        
        if len(path) == 1:
            # 返回指定section的所有keys
            section = path[0]
            if not config.has_section(section):
                return []
            return list(config.options(section))
        else:
            # INI格式不支持更深层的嵌套
            return []


class MarkdownParser:
    """Markdown文件解析器"""
    
    @staticmethod
    def extract_toc(content: str) -> List[Dict[str, Any]]:
        """
        提取Markdown文件的目录结构
        
        Args:
            content: Markdown文件内容
            
        Returns:
            目录项列表，每个项包含 level, line_number, text, anchor
        """
        lines = content.split('\n')
        toc = []
        
        for line_num, line in enumerate(lines, start=1):
            # 匹配标题行 (# ## ### 等)
            match = re.match(r'^(#{1,6})\s+(.+)$', line.strip())
            if match:
                level = len(match.group(1))
                text = match.group(2).strip()
                
                # 生成锚点链接（简化版，移除特殊字符）
                anchor = re.sub(r'[^\w\s-]', '', text.lower())
                anchor = re.sub(r'[-\s]+', '-', anchor)
                
                toc.append({
                    'level': level,
                    'line_number': line_num,
                    'text': text,
                    'anchor': anchor
                })
        
        return toc
    
    @staticmethod
    def format_toc(toc: List[Dict[str, Any]], max_level: int = 6) -> str:
        """
        格式化目录为Markdown格式
        
        Args:
            toc: 目录项列表
            max_level: 最大标题级别
            
        Returns:
            格式化的目录字符串
        """
        if not toc:
            return ""
        
        result = []
        for item in toc:
            if item['level'] <= max_level:
                indent = "  " * (item['level'] - 1)
                result.append(f"{indent}- [{item['text']}](#{item['anchor']})")
        
        return "\n".join(result)
    
    @staticmethod
    def _find_section_by_path(toc: List[Dict[str, Any]], path_parts: List[str]) -> Optional[Dict[str, Any]]:
        """
        根据点号分隔的路径查找章节
        
        Args:
            toc: 目录项列表
            path_parts: 路径部分列表，如 ["第一章", "第一节"]
            
        Returns:
            匹配的章节项，如果未找到则返回None
        """
        if not path_parts or not toc:
            return None
        
        # 查找第一级标题（匹配路径的第一部分）
        first_level_item = None
        for item in toc:
            if item['level'] == 1:
                # 尝试完整匹配
                if item['text'] == path_parts[0]:
                    first_level_item = item
                    break
                # 尝试部分匹配
                elif path_parts[0].lower() in item['text'].lower():
                    first_level_item = item
                    break
        
        if not first_level_item:
            return None
        
        # 如果只有一个路径部分，直接返回
        if len(path_parts) == 1:
            return first_level_item
        current_level = first_level_item['level']
        current_line = first_level_item['line_number']
        
        # 查找当前级别下的下一级标题
        for path_index in range(1, len(path_parts)):
            target_level = current_level + 1
            target_text = path_parts[path_index]
            found = False
            
            for item in toc:
                # 必须在当前标题之后，且在下一个同级或更高级标题之前
                if item['line_number'] <= current_line:
                    continue
                
                # 如果遇到同级或更高级的标题，说明已经超出当前章节范围
                if item['level'] <= current_level:
                    break
                
                # 检查是否匹配目标级别和文本
                if item['level'] == target_level:
                    # 尝试完整匹配
                    if item['text'] == target_text:
                        first_level_item = item
                        current_level = item['level']
                        current_line = item['line_number']
                        found = True
                        break
                    # 尝试部分匹配
                    elif target_text.lower() in item['text'].lower():
                        first_level_item = item
                        current_level = item['level']
                        current_line = item['line_number']
                        found = True
                        break
            
            if not found:
                return None
        
        return first_level_item
    
    @staticmethod
    def extract_section(content: str, section_title: str, include_title: bool = True) -> Optional[Dict[str, Any]]:
        """
        提取Markdown文件中指定章节的内容
        
        Args:
            content: Markdown文件内容
            section_title: 章节标题文本（支持完整匹配、部分匹配或点号分隔的路径，如 "第一章.第一节"）
            include_title: 是否包含标题行本身
            
        Returns:
            包含章节信息的字典，如果未找到则返回None
            包含: start_line, end_line, level, title, content, anchor
        """
        lines = content.split('\n')
        toc = MarkdownParser.extract_toc(content)
        
        if not toc:
            return None
        
        # 检查是否使用点号分隔的路径
        if '.' in section_title:
            # 使用点号分隔的路径查找章节
            path_parts = [part.strip() for part in section_title.split('.')]
            matched_item = MarkdownParser._find_section_by_path(toc, path_parts)
        else:
            # 使用原来的逻辑：优先完整匹配，其次部分匹配
            matched_item = None
            # 先尝试完整匹配
            for item in toc:
                if item['text'] == section_title:
                    matched_item = item
                    break
            
            # 如果没有完整匹配，尝试部分匹配
            if not matched_item:
                for item in toc:
                    if section_title.lower() in item['text'].lower():
                        matched_item = item
                        break
        
        if not matched_item:
            return None
        
        # 找到章节的起始行（标题行）
        start_line_idx = matched_item['line_number'] - 1  # 转换为0-based索引
        
        # 找到章节的结束行（下一个同级或更高级的标题）
        section_level = matched_item['level']
        end_line_idx = len(lines)  # 默认到文件末尾
        
        for item in toc:
            if item['line_number'] > matched_item['line_number']:
                # 找到下一个同级或更高级的标题
                if item['level'] <= section_level:
                    end_line_idx = item['line_number'] - 1  # 转换为0-based索引
                    break
        
        # 提取章节内容
        if include_title:
            section_lines = lines[start_line_idx:end_line_idx]
        else:
            section_lines = lines[start_line_idx + 1:end_line_idx] if start_line_idx + 1 < end_line_idx else []
        
        section_content = '\n'.join(section_lines)
        
        return {
            'level': matched_item['level'],
            'title': matched_item['text'],
            'anchor': matched_item['anchor'],
            'start_line': matched_item['line_number'],
            'end_line': end_line_idx + 1 if end_line_idx < len(lines) else len(lines),
            'content': section_content,
            'line_count': len(section_lines)
        }


def get_parser(file_path: Path):
    """
    根据文件扩展名获取相应的解析器
    
    Args:
        file_path: 文件路径
        
    Returns:
        解析器实例
    """
    ext = file_path.suffix.lower()
    
    if ext in ['.yaml', '.yml']:
        return YAMLParser()
    elif ext == '.json':
        return JSONParser()
    elif ext in ['.ini', '.cfg']:
        return INIParser()
    else:
        raise ValueError(f"不支持的文件格式: {ext}")

