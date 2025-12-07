#!/usr/bin/env python3
"""
UTCP文件读取服务
提供文件读取、配置文件解析、Markdown目录提取等功能
"""

import logging
from pathlib import Path
from typing import Dict, Any, List, Callable, Optional, Union
from functools import wraps
from src.utcp.utcp import UTCPService

from src.services.file_service.utils import (
    validate_relative_path,
    validate_relative_dir_path,
    read_file_lines_with_encoding,
    read_file_with_encoding,
    detect_encoding,
    expand_file_paths
)
from src.services.file_service.file_parsers import (
    get_parser,
    MarkdownParser
)
from src.services.file_service.file_writers import get_writer

logger = logging.getLogger(__name__)


def handle_file_errors(func: Callable) -> Callable:
    """装饰器：统一错误处理"""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except Exception as e:
            logger.error(f"{func.__name__} 失败: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "message": f"执行工具 '{func.__name__}' 失败"
            }
    return wrapper


class FileService(UTCPService):
    """文件服务 - 提供文件读写、配置解析等功能"""
    
    def init(self) -> None:
        """插件初始化方法"""
        pass
    
    @property
    def name(self) -> str:
        return "file_service"
    
    @property
    def description(self) -> str:
        return "提供文件读写、配置文件解析、Markdown目录提取等功能的服务"
    
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
        """返回文件读取服务的所有工具定义"""
        return [
            # 文本读取工具
            self._create_tool_definition(
                "read_file_lines", "按行范围读取文本文件（支持批量：文件路径列表或通配符模式，如 *.py 或 ['file1.txt', 'file2.txt']）",
                {
                    "file_path": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}}
                        ],
                        "description": "文件相对路径（字符串、路径列表或通配符模式，如 '*.py', '**/*.md', ['file1.txt', 'file2.txt']）"
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "起始行号（从1开始），可选，不指定则从第1行开始",
                        "minimum": 1
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "结束行号（从1开始），可选，不指定则到文件末尾",
                        "minimum": 1
                    }
                },
                ["file_path"]
            ),
            
            # 配置文件读取工具
            self._create_tool_definition(
                "read_config_value", "读取配置文件中指定key的值（支持批量：文件路径列表或通配符模式）",
                {
                    "file_path": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}}
                        ],
                        "description": "配置文件相对路径（字符串、路径列表或通配符模式，支持yaml, json, ini格式）"
                    },
                    "key_path": {
                        "type": "string",
                        "description": "点号分隔的key路径，如 'database.host' 或 'items[0].name'"
                    }
                },
                ["file_path", "key_path"]
            ),
            
            self._create_tool_definition(
                "list_config_keys", "获取配置文件中指定key的所有子key列表（支持批量：文件路径列表或通配符模式）",
                {
                    "file_path": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}}
                        ],
                        "description": "配置文件相对路径（字符串、路径列表或通配符模式，支持yaml, json, ini格式）"
                    },
                    "key_path": {
                        "type": "string",
                        "description": "点号分隔的key路径，可选，为空则返回根级keys"
                    }
                },
                ["file_path"]
            ),
            
            # Markdown目录工具
            self._create_tool_definition(
                "get_markdown_toc", "提取Markdown文件的目录结构（支持批量：文件路径列表或通配符模式）",
                {
                    "file_path": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}}
                        ],
                        "description": "Markdown文件相对路径（字符串、路径列表或通配符模式，如 '*.md', 'docs/**/*.md'）"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["list", "markdown"],
                        "description": "返回格式：list返回结构化数据，markdown返回格式化的目录",
                        "default": "list"
                    },
                    "max_level": {
                        "type": "integer",
                        "description": "最大标题级别（1-6），仅当format为markdown时有效",
                        "minimum": 1,
                        "maximum": 6,
                        "default": 6
                    }
                },
                ["file_path"]
            ),
            
            # Markdown章节提取工具
            self._create_tool_definition(
                "get_markdown_section", "获取Markdown文件中指定章节的内容（支持批量：文件路径列表或通配符模式）",
                {
                    "file_path": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}}
                        ],
                        "description": "Markdown文件相对路径（字符串、路径列表或通配符模式，如 '*.md'）"
                    },
                    "section_title": {
                        "type": "string",
                        "description": "章节标题文本（支持完整匹配、部分匹配或点号分隔的路径，如 '第一章.第一节' 或 '1.2.3'）"
                    },
                    "include_title": {
                        "type": "boolean",
                        "description": "是否包含标题行本身，默认为true",
                        "default": True
                    }
                },
                ["file_path", "section_title"]
            ),
            
            # 配置文件写入工具
            self._create_tool_definition(
                "write_config_value", "写入配置值到指定key",
                {
                    "file_path": {
                        "type": "string",
                        "description": "配置文件相对路径（支持yaml, json, ini格式）"
                    },
                    "key_path": {
                        "type": "string",
                        "description": "点号分隔的key路径"
                    },
                    "value": {
                        "type": "string",
                        "description": "要写入的值（字符串格式，对于复杂类型需要JSON格式）"
                    }
                },
                ["file_path", "key_path", "value"]
            ),
            
            self._create_tool_definition(
                "write_file_lines", "写入文本行到文件",
                {
                    "file_path": {
                        "type": "string",
                        "description": "文件相对路径"
                    },
                    "lines": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要写入的行列表"
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "插入位置的行号（从1开始），可选，不指定则追加到文件末尾",
                        "minimum": 1
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["append", "insert", "overwrite"],
                        "description": "写入模式：append追加，insert插入，overwrite覆盖",
                        "default": "append"
                    }
                },
                ["file_path", "lines"]
            ),
            
            # 文件搜索工具
            self._create_tool_definition(
                "search_in_file", "在文件中全文搜索关键词（支持批量：文件路径列表或通配符模式）",
                {
                    "file_path": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}}
                        ],
                        "description": "文件相对路径（字符串、路径列表或通配符模式，如 '*.py', 'src/**/*.ts'）"
                    },
                    "keyword": {
                        "type": "string",
                        "description": "要搜索的关键词"
                    },
                    "case_sensitive": {
                        "type": "boolean",
                        "description": "是否区分大小写，默认为false（不区分大小写）",
                        "default": False
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "最大返回结果数量，可选，默认返回所有匹配结果",
                        "minimum": 1,
                        "default": 100
                    }
                },
                ["file_path", "keyword"]
            ),
            
            # 文件元信息工具
            self._create_tool_definition(
                "get_file_metadata", "获取文件的元信息（大小、修改时间等）（支持批量：文件路径列表或通配符模式）",
                {
                    "file_path": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}}
                        ],
                        "description": "文件相对路径（字符串、路径列表或通配符模式，如 '*.py', ['file1.txt', 'file2.txt']）"
                    }
                },
                ["file_path"]
            ),
            
            # 目录结构工具
            self._create_tool_definition(
                "list_directory", "获取目录结构（支持批量：目录路径列表）",
                {
                    "dir_path": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}}
                        ],
                        "description": "目录相对路径（字符串或路径列表，如 'src', ['src', 'docs']）"
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "是否递归列出子目录，默认为false（只列出当前目录）",
                        "default": False
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "最大递归深度（仅当recursive为true时有效），0表示不限制，默认为0",
                        "minimum": 0,
                        "default": 0
                    },
                    "include_files": {
                        "type": "boolean",
                        "description": "是否包含文件，默认为true",
                        "default": True
                    },
                    "include_dirs": {
                        "type": "boolean",
                        "description": "是否包含子目录，默认为true",
                        "default": True
                    },
                    "file_extensions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "文件扩展名过滤列表（如 ['py', 'js']），可选，为空则不过滤"
                    },
                    "exclude_patterns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "排除模式列表（如 ['__pycache__', '*.pyc']），可选"
                    }
                },
                ["dir_path"]
            )
        ]
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """执行文件读取服务的工具调用"""
        tool_handlers = {
            "read_file_lines": lambda: self._read_file_lines(
                arguments["file_path"],
                arguments.get("start_line"),
                arguments.get("end_line")
            ),
            "read_config_value": lambda: self._read_config_value(
                arguments["file_path"],
                arguments["key_path"]
            ),
            "list_config_keys": lambda: self._list_config_keys(
                arguments["file_path"],
                arguments.get("key_path")
            ),
            "get_markdown_toc": lambda: self._get_markdown_toc(
                arguments["file_path"],
                arguments.get("format", "list"),
                arguments.get("max_level", 6)
            ),
            "get_markdown_section": lambda: self._get_markdown_section(
                arguments["file_path"],
                arguments["section_title"],
                arguments.get("include_title", True)
            ),
            "write_config_value": lambda: self._write_config_value(
                arguments["file_path"],
                arguments["key_path"],
                arguments["value"]
            ),
            "write_file_lines": lambda: self._write_file_lines(
                arguments["file_path"],
                arguments["lines"],
                arguments.get("start_line"),
                arguments.get("mode", "append")
            ),
            "search_in_file": lambda: self._search_in_file(
                arguments["file_path"],
                arguments["keyword"],
                arguments.get("case_sensitive", False),
                arguments.get("max_results", 100)
            ),
            "get_file_metadata": lambda: self._get_file_metadata(
                arguments["file_path"]
            ),
            "list_directory": lambda: self._list_directory(
                arguments["dir_path"],
                arguments.get("recursive", False),
                arguments.get("max_depth", 0),
                arguments.get("include_files", True),
                arguments.get("include_dirs", True),
                arguments.get("file_extensions"),
                arguments.get("exclude_patterns")
            ),
        }
        
        try:
            if tool_name not in tool_handlers:
                raise ValueError(f"未知的工具名称: {tool_name}")
            
            return tool_handlers[tool_name]()
        except Exception as e:
            logger.error(f"执行工具 '{tool_name}' 时出错: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "message": f"执行工具 '{tool_name}' 失败"
            }
    
    @handle_file_errors
    def _read_file_lines(self, file_path: Union[str, List[str]], start_line: Optional[int] = None, 
                        end_line: Optional[int] = None) -> Dict[str, Any]:
        """按行范围读取文本文件（支持批量）"""
        paths = expand_file_paths(file_path)
        
        if not paths:
            return {
                "status": "error",
                "error": "未找到匹配的文件",
                "message": f"文件路径 '{file_path}' 未匹配到任何文件"
            }
        
        results = []
        for path in paths:
            try:
                lines, encoding = read_file_lines_with_encoding(path, start_line, end_line)
                results.append({
                    "status": "success",
                    "file_path": str(path),
                    "start_line": start_line,
                    "end_line": end_line,
                    "total_lines": len(lines),
                    "encoding": encoding,
                    "content": "".join(lines),
                    "lines": [line.rstrip('\n\r') for line in lines]
                })
            except Exception as e:
                results.append({
                    "status": "error",
                    "file_path": str(path),
                    "error": str(e),
                    "message": f"读取文件失败: {e}"
                })
        
        # 如果只有一个文件，返回单个结果（保持向后兼容）
        if len(results) == 1:
            return results[0]
        
        return {
            "status": "success",
            "total_files": len(paths),
            "results": results
        }
    
    @handle_file_errors
    def _read_config_value(self, file_path: Union[str, List[str]], key_path: str) -> Dict[str, Any]:
        """读取配置文件中指定key的值（支持批量）"""
        paths = expand_file_paths(file_path)
        
        if not paths:
            return {
                "status": "error",
                "error": "未找到匹配的文件",
                "message": f"文件路径 '{file_path}' 未匹配到任何文件"
            }
        
        results = []
        for path in paths:
            try:
                parser = get_parser(path)
                data = parser.parse(path)
                value = parser.get_value(data, key_path)
                results.append({
                    "status": "success",
                    "file_path": str(path),
                    "key_path": key_path,
                    "value": value,
                    "value_type": type(value).__name__
                })
            except Exception as e:
                results.append({
                    "status": "error",
                    "file_path": str(path),
                    "key_path": key_path,
                    "error": str(e),
                    "message": f"读取配置值失败: {e}"
                })
        
        if len(results) == 1:
            return results[0]
        
        return {
            "status": "success",
            "total_files": len(paths),
            "key_path": key_path,
            "results": results
        }
    
    @handle_file_errors
    def _list_config_keys(self, file_path: Union[str, List[str]], key_path: Optional[str] = None) -> Dict[str, Any]:
        """获取配置文件中指定key的所有子key列表（支持批量）"""
        paths = expand_file_paths(file_path)
        
        if not paths:
            return {
                "status": "error",
                "error": "未找到匹配的文件",
                "message": f"文件路径 '{file_path}' 未匹配到任何文件"
            }
        
        results = []
        for path in paths:
            try:
                parser = get_parser(path)
                data = parser.parse(path)
                keys = parser.list_keys(data, key_path)
                results.append({
                    "status": "success",
                    "file_path": str(path),
                    "key_path": key_path or "",
                    "keys": keys,
                    "count": len(keys)
                })
            except Exception as e:
                results.append({
                    "status": "error",
                    "file_path": str(path),
                    "key_path": key_path or "",
                    "error": str(e),
                    "message": f"列出配置键失败: {e}"
                })
        
        if len(results) == 1:
            return results[0]
        
        return {
            "status": "success",
            "total_files": len(paths),
            "key_path": key_path or "",
            "results": results
        }
    
    @handle_file_errors
    def _get_markdown_toc(self, file_path: Union[str, List[str]], format: str = "list", 
                         max_level: int = 6) -> Dict[str, Any]:
        """提取Markdown文件的目录结构（支持批量）"""
        paths = expand_file_paths(file_path)
        
        if not paths:
            return {
                "status": "error",
                "error": "未找到匹配的文件",
                "message": f"文件路径 '{file_path}' 未匹配到任何文件"
            }
        
        results = []
        for path in paths:
            try:
                if path.suffix.lower() != '.md':
                    results.append({
                        "status": "error",
                        "file_path": str(path),
                        "error": "文件不是Markdown格式",
                        "message": f"文件不是Markdown格式: {path}"
                    })
                    continue
                
                content, encoding = read_file_with_encoding(path)
                toc = MarkdownParser.extract_toc(content)
                
                result = {
                    "status": "success",
                    "file_path": str(path),
                    "encoding": encoding,
                    "total_headings": len(toc)
                }
                
                if format == "markdown":
                    result["toc_markdown"] = MarkdownParser.format_toc(toc, max_level)
                else:
                    result["toc"] = toc
                
                results.append(result)
            except Exception as e:
                results.append({
                    "status": "error",
                    "file_path": str(path),
                    "error": str(e),
                    "message": f"提取目录失败: {e}"
                })
        
        if len(results) == 1:
            return results[0]
        
        return {
            "status": "success",
            "total_files": len(paths),
            "format": format,
            "results": results
        }
    
    @handle_file_errors
    def _get_markdown_section(self, file_path: Union[str, List[str]], section_title: str, 
                             include_title: bool = True) -> Dict[str, Any]:
        """获取Markdown文件中指定章节的内容（支持批量）"""
        paths = expand_file_paths(file_path)
        
        if not paths:
            return {
                "status": "error",
                "error": "未找到匹配的文件",
                "message": f"文件路径 '{file_path}' 未匹配到任何文件"
            }
        
        results = []
        for path in paths:
            try:
                if path.suffix.lower() != '.md':
                    results.append({
                        "status": "error",
                        "file_path": str(path),
                        "error": "文件不是Markdown格式",
                        "message": f"文件不是Markdown格式: {path}"
                    })
                    continue
                
                content, encoding = read_file_with_encoding(path)
                section = MarkdownParser.extract_section(content, section_title, include_title)
                
                if section is None:
                    results.append({
                        "status": "error",
                        "file_path": str(path),
                        "error": "章节未找到",
                        "message": f"未找到标题为 '{section_title}' 的章节"
                    })
                else:
                    results.append({
                        "status": "success",
                        "file_path": str(path),
                        "encoding": encoding,
                        "section": section
                    })
            except Exception as e:
                results.append({
                    "status": "error",
                    "file_path": str(path),
                    "error": str(e),
                    "message": f"提取章节失败: {e}"
                })
        
        if len(results) == 1:
            return results[0]
        
        return {
            "status": "success",
            "total_files": len(paths),
            "section_title": section_title,
            "results": results
        }
    
    @handle_file_errors
    def _write_config_value(self, file_path: str, key_path: str, value: str) -> Dict[str, Any]:
        """写入配置值到指定key"""
        path = validate_relative_path(file_path)
        
        # 解析值（尝试JSON解析，失败则作为字符串）
        try:
            import json
            parsed_value = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            parsed_value = value
        
        # 读取现有配置
        parser = get_parser(path)
        data = parser.parse(path)
        
        # 设置值
        writer = get_writer(path)
        
        # 对于INI格式，需要特殊处理（值必须是字符串）
        from src.services.file_service.file_parsers import INIParser
        if isinstance(parser, INIParser):
            writer.set_value(data, key_path, str(parsed_value))
        else:
            writer.set_value(data, key_path, parsed_value)
        
        writer.write(path, data)
        
        return {
            "status": "success",
            "file_path": file_path,
            "key_path": key_path,
            "value": parsed_value,
            "message": "配置值已成功写入"
        }
    
    @handle_file_errors
    def _write_file_lines(self, file_path: str, lines: List[str], 
                         start_line: Optional[int] = None, mode: str = "append") -> Dict[str, Any]:
        """写入文本行到文件"""
        path = validate_relative_path(file_path)
        
        # 确保目录存在
        path.parent.mkdir(parents=True, exist_ok=True)
        
        if mode == "overwrite":
            # 覆盖模式：直接写入
            encoding = "utf-8"
            with open(path, 'w', encoding=encoding) as f:
                f.write('\n'.join(lines))
                if lines:  # 如果最后一行需要换行
                    f.write('\n')
        elif mode == "insert":
            # 插入模式：在指定行插入
            if start_line is None:
                raise ValueError("插入模式需要指定 start_line 参数")
            
            if path.exists():
                all_lines, encoding = read_file_lines_with_encoding(path)
                # 转换为字符串列表（去除换行符）
                all_lines = [line.rstrip('\n\r') for line in all_lines]
                # 插入新行
                insert_pos = start_line - 1  # 转换为0-based索引
                all_lines[insert_pos:insert_pos] = lines
                
                with open(path, 'w', encoding=encoding) as f:
                    f.write('\n'.join(all_lines))
                    f.write('\n')
            else:
                encoding = "utf-8"
                with open(path, 'w', encoding=encoding) as f:
                    f.write('\n'.join(lines))
                    f.write('\n')
        else:  # append
            # 追加模式：追加到文件末尾
            encoding = "utf-8"
            with open(path, 'a', encoding=encoding) as f:
                f.write('\n'.join(lines))
                if lines:  # 如果最后一行需要换行
                    f.write('\n')
        
        return {
            "status": "success",
            "file_path": file_path,
            "mode": mode,
            "start_line": start_line,
            "lines_written": len(lines),
            "encoding": encoding,
            "message": f"成功写入 {len(lines)} 行"
        }
    
    @handle_file_errors
    def _search_in_file(self, file_path: Union[str, List[str]], keyword: str, 
                       case_sensitive: bool = False, max_results: int = 100) -> Dict[str, Any]:
        """在文件中全文搜索关键词（支持批量）"""
        paths = expand_file_paths(file_path)
        
        if not paths:
            return {
                "status": "error",
                "error": "未找到匹配的文件",
                "message": f"文件路径 '{file_path}' 未匹配到任何文件"
            }
        
        results = []
        for path in paths:
            try:
                # 读取文件内容
                lines, encoding = read_file_lines_with_encoding(path)
                
                # 准备搜索
                search_keyword = keyword if case_sensitive else keyword.lower()
                matches = []
                
                # 逐行搜索
                for line_num, line in enumerate(lines, start=1):
                    line_content = line.rstrip('\n\r')
                    search_line = line_content if case_sensitive else line_content.lower()
                    
                    if search_keyword in search_line:
                        # 找到所有匹配位置
                        start_pos = 0
                        positions = []
                        while True:
                            pos = search_line.find(search_keyword, start_pos)
                            if pos == -1:
                                break
                            positions.append(pos)
                            start_pos = pos + 1
                        
                        matches.append({
                            "line_number": line_num,
                            "content": line_content,
                            "positions": positions,
                            "match_count": len(positions)
                        })
                        
                        # 限制结果数量
                        if len(matches) >= max_results:
                            break
                
                results.append({
                    "status": "success",
                    "file_path": str(path),
                    "keyword": keyword,
                    "case_sensitive": case_sensitive,
                    "encoding": encoding,
                    "total_matches": len(matches),
                    "total_lines": len(lines),
                    "matches": matches,
                    "truncated": len(matches) >= max_results
                })
            except Exception as e:
                results.append({
                    "status": "error",
                    "file_path": str(path),
                    "keyword": keyword,
                    "error": str(e),
                    "message": f"搜索失败: {e}"
                })
        
        if len(results) == 1:
            return results[0]
        
        # 汇总所有文件的匹配结果
        total_matches = sum(r.get("total_matches", 0) for r in results if r.get("status") == "success")
        
        return {
            "status": "success",
            "total_files": len(paths),
            "keyword": keyword,
            "case_sensitive": case_sensitive,
            "total_matches": total_matches,
            "results": results
        }
    
    @handle_file_errors
    def _get_file_metadata(self, file_path: Union[str, List[str]]) -> Dict[str, Any]:
        """获取文件的元信息（大小、修改时间等）（支持批量）"""
        import os
        from datetime import datetime
        
        paths = expand_file_paths(file_path)
        
        if not paths:
            return {
                "status": "error",
                "error": "未找到匹配的文件",
                "message": f"文件路径 '{file_path}' 未匹配到任何文件"
            }
        
        results = []
        for path in paths:
            try:
                # 获取文件统计信息
                stat_info = path.stat()
                
                # 文件大小
                size = stat_info.st_size
                size_human = self._format_file_size(size)
                
                # 时间信息
                mtime = datetime.fromtimestamp(stat_info.st_mtime)
                ctime = datetime.fromtimestamp(stat_info.st_ctime)
                
                # 尝试获取创建时间（Windows）
                try:
                    if hasattr(stat_info, 'st_birthtime'):
                        birthtime = datetime.fromtimestamp(stat_info.st_birthtime)
                    else:
                        birthtime = ctime  # 在Unix系统上，ctime通常是创建时间
                except:
                    birthtime = ctime
                
                # 文件扩展名和类型
                suffix = path.suffix.lower()
                extension = suffix[1:] if suffix else ""
                
                # 判断是否为文本文件（简单判断）
                text_extensions = {'.txt', '.py', '.js', '.ts', '.json', '.yaml', '.yml', 
                                  '.md', '.html', '.css', '.xml', '.ini', '.conf', '.log',
                                  '.sh', '.bat', '.ps1', '.java', '.cpp', '.c', '.h',
                                  '.go', '.rs', '.php', '.rb', '.pl', '.sql', '.r',
                                  '.swift', '.kt', '.scala', '.clj', '.lua', '.vim'}
                is_text_file = suffix in text_extensions or extension == ""
                
                # 如果是文本文件，尝试获取编码和行数
                encoding = None
                line_count = None
                if is_text_file:
                    try:
                        encoding = detect_encoding(path)
                        with open(path, 'r', encoding=encoding) as f:
                            line_count = sum(1 for _ in f)
                    except:
                        pass
                
                results.append({
                    "status": "success",
                    "file_path": str(path),
                    "file_name": path.name,
                    "file_dir": str(path.parent),
                    "size": size,
                    "size_human": size_human,
                    "extension": extension,
                    "is_text_file": is_text_file,
                    "encoding": encoding,
                    "line_count": line_count,
                    "modified_time": mtime.isoformat(),
                    "created_time": birthtime.isoformat(),
                    "accessed_time": datetime.fromtimestamp(stat_info.st_atime).isoformat(),
                    "is_readable": os.access(path, os.R_OK),
                    "is_writable": os.access(path, os.W_OK),
                    "is_executable": os.access(path, os.X_OK)
                })
            except Exception as e:
                results.append({
                    "status": "error",
                    "file_path": str(path),
                    "error": str(e),
                    "message": f"获取元信息失败: {e}"
                })
        
        if len(results) == 1:
            return results[0]
        
        # 汇总统计信息
        total_size = sum(r.get("size", 0) for r in results if r.get("status") == "success")
        
        return {
            "status": "success",
            "total_files": len(paths),
            "total_size": total_size,
            "total_size_human": self._format_file_size(total_size),
            "results": results
        }
    
    def _format_file_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"
    
    def _expand_dir_paths(self, dir_path: Union[str, List[str]]) -> List[Path]:
        """
        展开目录路径，支持单个路径或路径列表
        
        Args:
            dir_path: 目录路径（字符串或列表）
            
        Returns:
            展开后的目录路径列表
        """
        if isinstance(dir_path, list):
            dirs = []
            for d in dir_path:
                dirs.append(validate_relative_dir_path(d))
            return dirs
        else:
            return [validate_relative_dir_path(dir_path)]
    
    def _should_exclude(self, path: Path, exclude_patterns: Optional[List[str]]) -> bool:
        """
        检查路径是否应该被排除
        
        Args:
            path: 路径对象
            exclude_patterns: 排除模式列表
            
        Returns:
            如果应该排除返回True
        """
        if not exclude_patterns:
            return False
        
        path_str = str(path)
        name = path.name
        
        for pattern in exclude_patterns:
            # 简单的通配符匹配
            if '*' in pattern or '?' in pattern:
                import fnmatch
                if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(path_str, pattern):
                    return True
            else:
                # 精确匹配
                if pattern in name or pattern in path_str:
                    return True
        
        return False
    
    def _list_directory_recursive(
        self, 
        dir_path: Path, 
        current_depth: int,
        max_depth: int,
        include_files: bool,
        include_dirs: bool,
        file_extensions: Optional[List[str]],
        exclude_patterns: Optional[List[str]],
        base_path: Path
    ) -> List[Dict[str, Any]]:
        """
        递归列出目录内容
        
        Args:
            dir_path: 目录路径
            current_depth: 当前深度
            max_depth: 最大深度（0表示不限制）
            include_files: 是否包含文件
            include_dirs: 是否包含目录
            file_extensions: 文件扩展名过滤
            exclude_patterns: 排除模式
            base_path: 基础路径（用于计算相对路径）
            
        Returns:
            目录项列表
        """
        from datetime import datetime
        items = []
        
        # 检查深度限制
        if max_depth > 0 and current_depth >= max_depth:
            return items
        
        if not dir_path.exists() or not dir_path.is_dir():
            return items
        
        try:
            # 列出目录内容
            for item in sorted(dir_path.iterdir()):
                # 检查是否应该排除
                if self._should_exclude(item, exclude_patterns):
                    continue
                
                # 计算相对路径
                try:
                    rel_path = item.relative_to(base_path)
                except ValueError:
                    rel_path = item
                
                item_info = {
                    "name": item.name,
                    "path": str(rel_path),
                    "type": "directory" if item.is_dir() else "file"
                }
                
                # 如果是文件
                if item.is_file():
                    if not include_files:
                        continue
                    
                    # 文件扩展名过滤
                    if file_extensions:
                        ext = item.suffix.lower().lstrip('.')
                        if ext not in [e.lower().lstrip('.') for e in file_extensions]:
                            continue
                    
                    # 添加文件信息
                    try:
                        stat_info = item.stat()
                        item_info.update({
                            "size": stat_info.st_size,
                            "size_human": self._format_file_size(stat_info.st_size),
                            "modified_time": datetime.fromtimestamp(stat_info.st_mtime).isoformat()
                        })
                    except:
                        pass
                    
                    items.append(item_info)
                
                # 如果是目录
                elif item.is_dir():
                    if include_dirs:
                        items.append(item_info)
                    
                    # 递归处理子目录
                    if max_depth == 0 or current_depth + 1 < max_depth:
                        sub_items = self._list_directory_recursive(
                            item, current_depth + 1, max_depth,
                            include_files, include_dirs,
                            file_extensions, exclude_patterns, base_path
                        )
                        if sub_items:
                            item_info["children"] = sub_items
                            item_info["children_count"] = len(sub_items)
        
        except PermissionError:
            logger.warning(f"无权限访问目录: {dir_path}")
        except Exception as e:
            logger.error(f"列出目录内容失败: {dir_path}, 错误: {e}")
        
        return items
    
    @handle_file_errors
    def _list_directory(
        self, 
        dir_path: Union[str, List[str]], 
        recursive: bool = False,
        max_depth: int = 0,
        include_files: bool = True,
        include_dirs: bool = True,
        file_extensions: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """获取目录结构（支持批量）"""
        from datetime import datetime
        import fnmatch
        
        dirs = self._expand_dir_paths(dir_path)
        
        if not dirs:
            return {
                "status": "error",
                "error": "未找到匹配的目录",
                "message": f"目录路径 '{dir_path}' 未匹配到任何目录"
            }
        
        results = []
        for dir_path_obj in dirs:
            try:
                if not dir_path_obj.exists():
                    results.append({
                        "status": "error",
                        "dir_path": str(dir_path_obj),
                        "error": "目录不存在",
                        "message": f"目录不存在: {dir_path_obj}"
                    })
                    continue
                
                if not dir_path_obj.is_dir():
                    results.append({
                        "status": "error",
                        "dir_path": str(dir_path_obj),
                        "error": "路径不是目录",
                        "message": f"路径不是目录: {dir_path_obj}"
                    })
                    continue
                
                # 列出目录内容
                if recursive:
                    items = self._list_directory_recursive(
                        dir_path_obj, 0, max_depth,
                        include_files, include_dirs,
                        file_extensions, exclude_patterns, dir_path_obj
                    )
                else:
                    # 非递归模式，只列出当前目录
                    items = []
                    try:
                        for item in sorted(dir_path_obj.iterdir()):
                            # 检查是否应该排除
                            if self._should_exclude(item, exclude_patterns):
                                continue
                            
                            item_info = {
                                "name": item.name,
                                "path": str(item.relative_to(dir_path_obj)),
                                "type": "directory" if item.is_dir() else "file"
                            }
                            
                            # 如果是文件
                            if item.is_file():
                                if not include_files:
                                    continue
                                
                                # 文件扩展名过滤
                                if file_extensions:
                                    ext = item.suffix.lower().lstrip('.')
                                    if ext not in [e.lower().lstrip('.') for e in file_extensions]:
                                        continue
                                
                                # 添加文件信息
                                try:
                                    stat_info = item.stat()
                                    item_info.update({
                                        "size": stat_info.st_size,
                                        "size_human": self._format_file_size(stat_info.st_size),
                                        "modified_time": datetime.fromtimestamp(stat_info.st_mtime).isoformat()
                                    })
                                except:
                                    pass
                                
                                items.append(item_info)
                            
                            # 如果是目录
                            elif item.is_dir():
                                if include_dirs:
                                    items.append(item_info)
                    
                    except PermissionError:
                        logger.warning(f"无权限访问目录: {dir_path_obj}")
                    except Exception as e:
                        logger.error(f"列出目录内容失败: {dir_path_obj}, 错误: {e}")
                
                # 统计信息
                file_count = sum(1 for item in items if item.get("type") == "file")
                dir_count = sum(1 for item in items if item.get("type") == "directory")
                total_size = sum(item.get("size", 0) for item in items if item.get("type") == "file")
                
                results.append({
                    "status": "success",
                    "dir_path": str(dir_path_obj),
                    "recursive": recursive,
                    "max_depth": max_depth if recursive else None,
                    "items": items,
                    "file_count": file_count,
                    "dir_count": dir_count,
                    "total_size": total_size,
                    "total_size_human": self._format_file_size(total_size),
                    "total_items": len(items)
                })
            
            except Exception as e:
                results.append({
                    "status": "error",
                    "dir_path": str(dir_path_obj),
                    "error": str(e),
                    "message": f"列出目录失败: {e}"
                })
        
        # 如果只有一个目录，返回单个结果（保持向后兼容）
        if len(results) == 1:
            return results[0]
        
        # 汇总统计信息
        total_files = sum(r.get("file_count", 0) for r in results if r.get("status") == "success")
        total_dirs = sum(r.get("dir_count", 0) for r in results if r.get("status") == "success")
        total_size = sum(r.get("total_size", 0) for r in results if r.get("status") == "success")
        
        return {
            "status": "success",
            "total_directories": len(dirs),
            "total_files": total_files,
            "total_dirs": total_dirs,
            "total_size": total_size,
            "total_size_human": self._format_file_size(total_size),
            "results": results
        }
    
if __name__ == "__main__":
    """作为HTTP服务器运行"""
    import sys
    import os
    import argparse
    import asyncio
    
    # 添加项目路径
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    
    from utcp.http_server import run_service_as_http_server
    
    # 解析命令行参数
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='localhost', help='服务器主机')
    parser.add_argument('--port', type=int, default=8010, help='服务器端口')
    
    args = parser.parse_args()
    
    # 启动HTTP服务器
    asyncio.run(run_service_as_http_server(FileService, args.host, args.port))

