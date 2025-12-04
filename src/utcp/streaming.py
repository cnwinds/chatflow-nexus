#!/usr/bin/env python3
"""
UTCP流式响应接口和实现

这个模块定义了UTCP系统的流式响应核心接口和类型。
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Any, Optional, List, AsyncGenerator
from enum import Enum
from dataclasses import dataclass, field
import asyncio
import json
import aiohttp
import logging

logger = logging.getLogger(__name__)


class StreamType(Enum):
    """流式响应类型枚举"""
    TEXT = "text"           # 文本流
    JSON = "json"           # JSON流
    BINARY = "binary"       # 二进制流
    SSE = "sse"            # Server-Sent Events
    WEBSOCKET = "websocket" # WebSocket流


@dataclass
class StreamMetadata:
    """流式响应元数据"""
    total_size: Optional[int] = None
    estimated_duration: Optional[float] = None
    encoding: str = "utf-8"
    compression: Optional[str] = None
    custom_headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class StreamToolRequest:
    """流式工具调用请求"""
    tool_name: str
    arguments: Dict[str, Any]
    stream_type: StreamType = StreamType.TEXT
    buffer_size: int = 1024
    timeout: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class StreamError(Exception):
    """流式处理基础错误"""
    pass


class StreamTimeoutError(StreamError):
    """流式处理超时错误"""
    pass


class StreamConnectionError(StreamError):
    """流式连接错误"""
    pass


class StreamFormatError(StreamError):
    """流式数据格式错误"""
    pass


class StreamResponse(ABC):
    """流式响应的抽象基类"""
    
    def __init__(self, 
                 stream_type: StreamType,
                 content_type: str = "text/plain",
                 metadata: Optional[StreamMetadata] = None):
        self.stream_type = stream_type
        self.content_type = content_type
        self.metadata = metadata or StreamMetadata()
        self._closed = False
    
    @abstractmethod
    async def __aiter__(self) -> AsyncIterator[Any]:
        """异步迭代器接口"""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """关闭流式响应"""
        pass
    
    @property
    def is_closed(self) -> bool:
        """检查流是否已关闭"""
        return self._closed
    
    async def collect(self, max_items: Optional[int] = None) -> List[Any]:
        """收集所有流式数据（用于测试和调试）"""
        items = []
        count = 0
        async for item in self:
            items.append(item)
            count += 1
            if max_items and count >= max_items:
                break
        return items
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()
        return False


class LocalStreamResponse(StreamResponse):
    """本地服务的流式响应实现"""
    
    def __init__(self, 
                 generator: AsyncGenerator[Any, None],
                 stream_type: StreamType = StreamType.TEXT,
                 content_type: str = "text/plain",
                 metadata: Optional[StreamMetadata] = None):
        super().__init__(stream_type, content_type, metadata)
        self.generator = generator
    
    async def __aiter__(self) -> AsyncIterator[Any]:
        """异步迭代器实现"""
        try:
            async for item in self.generator:
                if self._closed:
                    break
                yield item
        except GeneratorExit:
            pass
        except Exception as e:
            logger.error(f"本地流式响应处理错误: {e}")
            raise StreamError(f"本地流式响应处理错误: {e}")
        finally:
            await self.close()
    
    async def close(self) -> None:
        """关闭生成器"""
        if not self._closed:
            self._closed = True
            try:
                await self.generator.aclose()
            except Exception as e:
                logger.debug(f"关闭本地流式响应时出错: {e}")


class HTTPStreamResponse(StreamResponse):
    """HTTP服务的流式响应实现"""
    
    def __init__(self,
                 session: aiohttp.ClientSession,
                 response: aiohttp.ClientResponse,
                 stream_type: StreamType = StreamType.TEXT,
                 metadata: Optional[StreamMetadata] = None):
        content_type = response.headers.get('Content-Type', 'text/plain')
        super().__init__(stream_type, content_type, metadata)
        self.session = session
        self.response = response
    
    async def __aiter__(self) -> AsyncIterator[Any]:
        """异步迭代器实现"""
        try:
            if self.stream_type == StreamType.SSE:
                async for line in self._parse_sse():
                    if self._closed:
                        break
                    yield line
            elif self.stream_type == StreamType.JSON:
                async for chunk in self._parse_json_stream():
                    if self._closed:
                        break
                    yield chunk
            else:
                async for chunk in self._parse_text_stream():
                    if self._closed:
                        break
                    yield chunk
        except Exception as e:
            logger.error(f"HTTP流式响应处理错误: {e}")
            raise StreamConnectionError(f"HTTP流式响应处理错误: {e}")
        finally:
            await self.close()
    
    async def _parse_sse(self) -> AsyncIterator[Dict[str, Any]]:
        """解析Server-Sent Events流"""
        try:
            async for line in self.response.content:
                line_str = line.decode('utf-8').strip()
                if line_str.startswith('data: '):
                    data_content = line_str[6:]
                    if data_content == '[DONE]':
                        # OpenAI风格的结束标记
                        break
                    try:
                        data = json.loads(data_content)
                        yield data
                    except json.JSONDecodeError as e:
                        logger.debug(f"SSE JSON解析失败: {e}, 原始数据: {data_content}")
                        yield {"data": data_content}
                elif line_str.startswith('event: '):
                    # 处理事件类型（可选）
                    continue
                elif line_str == '':
                    # 空行分隔事件
                    continue
        except Exception as e:
            logger.error(f"SSE流解析错误: {e}")
            raise StreamFormatError(f"SSE流解析错误: {e}")
    
    async def _parse_json_stream(self) -> AsyncIterator[Dict[str, Any]]:
        """解析JSON流"""
        buffer = ""
        try:
            async for chunk in self.response.content.iter_chunked(1024):
                try:
                    buffer += chunk.decode('utf-8')
                except UnicodeDecodeError as e:
                    logger.warning(f"JSON流解码错误: {e}")
                    continue
                    
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    if line:
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError as e:
                            logger.debug(f"JSON行解析失败: {e}, 原始数据: {line}")
                            continue
        except Exception as e:
            logger.error(f"JSON流解析错误: {e}")
            raise StreamFormatError(f"JSON流解析错误: {e}")
    
    async def _parse_text_stream(self) -> AsyncIterator[str]:
        """解析文本流"""
        try:
            async for chunk in self.response.content.iter_chunked(1024):
                try:
                    yield chunk.decode('utf-8')
                except UnicodeDecodeError as e:
                    logger.warning(f"文本流解码错误: {e}")
                    # 尝试使用错误替换策略
                    yield chunk.decode('utf-8', errors='replace')
        except Exception as e:
            logger.error(f"文本流解析错误: {e}")
            raise StreamFormatError(f"文本流解析错误: {e}")
    
    async def close(self) -> None:
        """关闭HTTP响应"""
        if not self._closed:
            self._closed = True
            try:
                self.response.close()
            except Exception as e:
                logger.debug(f"关闭HTTP流式响应时出错: {e}")


class StreamAdapter:
    """流式响应适配器，用于创建统一的流式接口"""
    
    @staticmethod
    def adapt_local(generator: AsyncGenerator[Any, None], 
                   stream_type: StreamType = StreamType.TEXT,
                   content_type: str = "text/plain",
                   metadata: Optional[StreamMetadata] = None) -> LocalStreamResponse:
        """适配本地异步生成器为流式响应"""
        return LocalStreamResponse(generator, stream_type, content_type, metadata)
    
    @staticmethod
    def adapt_http(session: aiohttp.ClientSession,
                  response: aiohttp.ClientResponse,
                  stream_type: StreamType = StreamType.TEXT,
                  metadata: Optional[StreamMetadata] = None) -> HTTPStreamResponse:
        """适配HTTP响应为流式响应"""
        return HTTPStreamResponse(session, response, stream_type, metadata)
    
    @staticmethod
    async def create_from_iterable(items: List[Any],
                                  stream_type: StreamType = StreamType.TEXT,
                                  content_type: str = "text/plain",
                                  delay: float = 0.0,
                                  metadata: Optional[StreamMetadata] = None) -> LocalStreamResponse:
        """从可迭代对象创建流式响应（用于测试）
        
        Args:
            items: 要流式输出的数据项列表
            stream_type: 流式类型
            content_type: 内容类型
            delay: 每个项目之间的延迟（秒）
            metadata: 流式元数据
            
        Returns:
            LocalStreamResponse: 本地流式响应对象
        """
        async def generator():
            try:
                for item in items:
                    if delay > 0:
                        await asyncio.sleep(delay)
                    yield item
            except Exception as e:
                logger.error(f"测试流式生成器错误: {e}")
                raise StreamError(f"测试流式生成器错误: {e}")
        
        return LocalStreamResponse(generator(), stream_type, content_type, metadata)


def get_tool_streaming_info(tool_definition: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """从工具定义中提取流式支持信息
    
    Args:
        tool_definition: OpenAI格式的工具定义
        
    Returns:
        流式支持信息字典，如果不支持流式则返回None
    """
    function_def = tool_definition.get("function", {})
    return function_def.get("streaming")


def is_streaming_supported(tool_definition: Dict[str, Any]) -> bool:
    """检查工具定义是否支持流式调用
    
    Args:
        tool_definition: OpenAI格式的工具定义
        
    Returns:
        是否支持流式调用
    """
    streaming_info = get_tool_streaming_info(tool_definition)
    return streaming_info is not None and streaming_info.get("supported", False)


def get_stream_tool_name(tool_definition: Dict[str, Any]) -> Optional[str]:
    """获取工具的流式版本名称
    
    Args:
        tool_definition: OpenAI格式的工具定义
        
    Returns:
        流式工具名称，如果不支持流式则返回None
    """
    streaming_info = get_tool_streaming_info(tool_definition)
    if streaming_info:
        return streaming_info.get("stream_tool_name")
    return None