#!/usr/bin/env python3
"""
UTCP文件读取服务
提供文件读取、配置文件解析、Markdown目录提取等功能
"""

import logging
from pathlib import Path
from typing import Dict, Any, List, Callable, Optional
from functools import wraps
from src.utcp.utcp import UTCPService

from src.services.file_service.utils import (
    validate_relative_path,
    read_file_lines_with_encoding,
    read_file_with_encoding
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
                "read_file_lines", "按行范围读取文本文件",
                {
                    "file_path": {
                        "type": "string",
                        "description": "文件相对路径"
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
                "read_config_value", "读取配置文件中指定key的值",
                {
                    "file_path": {
                        "type": "string",
                        "description": "配置文件相对路径（支持yaml, json, ini格式）"
                    },
                    "key_path": {
                        "type": "string",
                        "description": "点号分隔的key路径，如 'database.host' 或 'items[0].name'"
                    }
                },
                ["file_path", "key_path"]
            ),
            
            self._create_tool_definition(
                "list_config_keys", "获取配置文件中指定key的所有子key列表",
                {
                    "file_path": {
                        "type": "string",
                        "description": "配置文件相对路径（支持yaml, json, ini格式）"
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
                "get_markdown_toc", "提取Markdown文件的目录结构",
                {
                    "file_path": {
                        "type": "string",
                        "description": "Markdown文件相对路径"
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
                "get_markdown_section", "获取Markdown文件中指定章节的内容",
                {
                    "file_path": {
                        "type": "string",
                        "description": "Markdown文件相对路径"
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
    def _read_file_lines(self, file_path: str, start_line: Optional[int] = None, 
                        end_line: Optional[int] = None) -> Dict[str, Any]:
        """按行范围读取文本文件"""
        path = validate_relative_path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        if not path.is_file():
            raise ValueError(f"路径不是文件: {file_path}")
        
        lines, encoding = read_file_lines_with_encoding(path, start_line, end_line)
        
        return {
            "status": "success",
            "file_path": file_path,
            "start_line": start_line,
            "end_line": end_line,
            "total_lines": len(lines),
            "encoding": encoding,
            "content": "".join(lines),
            "lines": [line.rstrip('\n\r') for line in lines]
        }
    
    @handle_file_errors
    def _read_config_value(self, file_path: str, key_path: str) -> Dict[str, Any]:
        """读取配置文件中指定key的值"""
        path = validate_relative_path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        parser = get_parser(path)
        data = parser.parse(path)
        value = parser.get_value(data, key_path)
        
        return {
            "status": "success",
            "file_path": file_path,
            "key_path": key_path,
            "value": value,
            "value_type": type(value).__name__
        }
    
    @handle_file_errors
    def _list_config_keys(self, file_path: str, key_path: Optional[str] = None) -> Dict[str, Any]:
        """获取配置文件中指定key的所有子key列表"""
        path = validate_relative_path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        parser = get_parser(path)
        data = parser.parse(path)
        keys = parser.list_keys(data, key_path)
        
        return {
            "status": "success",
            "file_path": file_path,
            "key_path": key_path or "",
            "keys": keys,
            "count": len(keys)
        }
    
    @handle_file_errors
    def _get_markdown_toc(self, file_path: str, format: str = "list", 
                         max_level: int = 6) -> Dict[str, Any]:
        """提取Markdown文件的目录结构"""
        path = validate_relative_path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        if path.suffix.lower() != '.md':
            raise ValueError(f"文件不是Markdown格式: {file_path}")
        
        content, encoding = read_file_with_encoding(path)
        toc = MarkdownParser.extract_toc(content)
        
        result = {
            "status": "success",
            "file_path": file_path,
            "encoding": encoding,
            "total_headings": len(toc)
        }
        
        if format == "markdown":
            result["toc_markdown"] = MarkdownParser.format_toc(toc, max_level)
        else:
            result["toc"] = toc
        
        return result
    
    @handle_file_errors
    def _get_markdown_section(self, file_path: str, section_title: str, 
                             include_title: bool = True) -> Dict[str, Any]:
        """获取Markdown文件中指定章节的内容"""
        path = validate_relative_path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        if path.suffix.lower() != '.md':
            raise ValueError(f"文件不是Markdown格式: {file_path}")
        
        content, encoding = read_file_with_encoding(path)
        section = MarkdownParser.extract_section(content, section_title, include_title)
        
        if section is None:
            return {
                "status": "error",
                "file_path": file_path,
                "error": "章节未找到",
                "message": f"未找到标题为 '{section_title}' 的章节"
            }
        
        return {
            "status": "success",
            "file_path": file_path,
            "encoding": encoding,
            "section": section
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

