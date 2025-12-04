#!/usr/bin/env python3
"""
UTCP HTTP流式响应处理

这个模块实现了HTTP服务的流式响应处理，支持SSE、JSON流和文本流等格式。
"""

import asyncio
import json
import logging
from typing import AsyncIterator, Dict, Any, Optional, List
import aiohttp
from aiohttp import ClientResponse, ClientSession

from .streaming import StreamResponse, StreamType, StreamMetadata, StreamError, StreamConnectionError, StreamFormatError, StreamTimeoutError

logger = logging.getLogger(__name__)


class HTTPStreamResponse(StreamResponse):
    """HTTP服务的流式响应实现"""
    
    def __init__(self,
                 session: ClientSession,
                 response: ClientResponse,
                 stream_type: StreamType = StreamType.TEXT,
                 metadata: Optional[StreamMetadata] = None):
        """初始化HTTP流式响应
        
        Args:
            session: HTTP客户端会话
            response: HTTP响应对象
            stream_type: 流式类型
            metadata: 流式元数据
        """
        content_type = response.headers.get('Content-Type', 'text/plain')
        super().__init__(stream_type, content_type, metadata)
        self.session = session
        self.response = response
        self._bytes_received = 0
        self._start_time = asyncio.get_event_loop().time()
        
        # 从响应头中提取元数据
        if self.metadata:
            content_length = response.headers.get('Content-Length')
            if content_length:
                try:
                    self.metadata.total_size = int(content_length)
                except ValueError:
                    pass
    
    async def __aiter__(self) -> AsyncIterator[Any]:
        """异步迭代器实现"""
        if self._closed:
            logger.warning("尝试迭代已关闭的HTTP流式响应")
            return
        
        try:
            if self.stream_type == StreamType.SSE:
                async for item in self._parse_sse():
                    if self._closed:
                        break
                    yield item
            elif self.stream_type == StreamType.JSON:
                async for item in self._parse_json_stream():
                    if self._closed:
                        break
                    yield item
            else:
                async for item in self._parse_text_stream():
                    if self._closed:
                        break
                    yield item
        except asyncio.TimeoutError as e:
            error_msg = f"HTTP流式响应超时: {e}"
            logger.error(error_msg)
            self._set_error(StreamTimeoutError(error_msg, e))
            raise StreamTimeoutError(error_msg, e)
        except aiohttp.ClientError as e:
            error_msg = f"HTTP客户端错误: {e}"
            logger.error(error_msg)
            self._set_error(StreamConnectionError(error_msg, e))
            raise StreamConnectionError(error_msg, e)
        except Exception as e:
            error_msg = f"HTTP流式响应处理出错: {e}"
            logger.error(error_msg)
            self._set_error(StreamError(error_msg, e))
            raise StreamError(error_msg, e)
        finally:
            await self.close()
    
    async def _parse_sse(self) -> AsyncIterator[Dict[str, Any]]:
        """解析Server-Sent Events流"""
        buffer = ""
        
        async for chunk in self._iter_chunks():
            buffer += chunk
            
            # 处理完整的SSE事件
            while '\n\n' in buffer:
                event_data, buffer = buffer.split('\n\n', 1)
                event = self._parse_sse_event(event_data)
                if event:
                    yield event
    
    def _parse_sse_event(self, event_data: str) -> Optional[Dict[str, Any]]:
        """解析单个SSE事件
        
        Args:
            event_data: 事件数据字符串
            
        Returns:
            解析后的事件字典，如果解析失败返回None
        """
        event = {}
        
        for line in event_data.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith(':'):  # 跳过注释
                continue
            
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                
                if key == 'data':
                    # 尝试解析JSON数据
                    try:
                        event['data'] = json.loads(value)
                    except json.JSONDecodeError:
                        event['data'] = value
                elif key in ['event', 'id', 'retry']:
                    event[key] = value
        
        return event if event else None
    
    async def _parse_json_stream(self) -> AsyncIterator[Dict[str, Any]]:
        """解析JSON流（每行一个JSON对象）"""
        buffer = ""
        
        async for chunk in self._iter_chunks():
            buffer += chunk
            
            # 处理完整的JSON行
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                line = line.strip()
                
                if line:
                    try:
                        json_obj = json.loads(line)
                        yield json_obj
                    except json.JSONDecodeError as e:
                        logger.warning(f"JSON解析失败: {e}, 行内容: {line[:100]}")
                        # 继续处理下一行，不抛出异常
        
        # 处理缓冲区中剩余的数据（最后一行可能没有换行符）
        if buffer.strip():
            try:
                json_obj = json.loads(buffer.strip())
                yield json_obj
            except json.JSONDecodeError as e:
                logger.warning(f"JSON解析失败: {e}, 行内容: {buffer.strip()[:100]}")
                # 跳过无效的JSON
    
    async def _parse_text_stream(self) -> AsyncIterator[str]:
        """解析文本流"""
        async for chunk in self._iter_chunks():
            yield chunk
    
    async def _iter_chunks(self, chunk_size: int = 1024) -> AsyncIterator[str]:
        """迭代HTTP响应块
        
        Args:
            chunk_size: 块大小
            
        Yields:
            解码后的文本块
        """
        try:
            async for chunk in self.response.content.iter_chunked(chunk_size):
                if self._closed:
                    break
                
                # 解码字节数据
                try:
                    text_chunk = chunk.decode(self.metadata.encoding if self.metadata else 'utf-8')
                    self._bytes_received += len(chunk)
                    yield text_chunk
                except UnicodeDecodeError as e:
                    logger.warning(f"文本解码失败: {e}")
                    # 尝试使用错误处理策略
                    text_chunk = chunk.decode('utf-8', errors='replace')
                    self._bytes_received += len(chunk)
                    yield text_chunk
        except asyncio.CancelledError:
            logger.debug("HTTP流式响应被取消")
            raise
        except Exception as e:
            logger.error(f"迭代HTTP响应块时出错: {e}")
            raise
    
    async def close(self) -> None:
        """关闭HTTP响应"""
        if self._closed:
            return
        
        self._closed = True
        
        try:
            # 关闭HTTP响应
            if not self.response.closed:
                self.response.close()
            
            # 记录统计信息
            elapsed = asyncio.get_event_loop().time() - self._start_time
            logger.debug(f"HTTP流式响应已关闭，接收 {self._bytes_received} 字节，耗时 {elapsed:.2f}s")
            
        except Exception as e:
            logger.warning(f"关闭HTTP流式响应时出错: {e}")
    
    @property
    def bytes_received(self) -> int:
        """获取已接收的字节数"""
        return self._bytes_received
    
    @property
    def elapsed_time(self) -> float:
        """获取已经过的时间（秒）"""
        return asyncio.get_event_loop().time() - self._start_time
    
    @property
    def status_code(self) -> int:
        """获取HTTP状态码"""
        return self.response.status
    
    @property
    def headers(self) -> Dict[str, str]:
        """获取HTTP响应头"""
        return dict(self.response.headers)


class HTTPStreamClient:
    """HTTP流式客户端，用于创建和管理HTTP流式连接"""
    
    def __init__(self, timeout: int = 30):
        """初始化HTTP流式客户端
        
        Args:
            timeout: 请求超时时间（秒）
        """
        self.timeout = timeout
        self._session: Optional[ClientSession] = None
    
    async def _ensure_session(self) -> ClientSession:
        """确保HTTP会话已创建"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def create_stream(self, 
                          url: str,
                          method: str = "GET",
                          headers: Optional[Dict[str, str]] = None,
                          data: Optional[Any] = None,
                          stream_type: StreamType = StreamType.TEXT,
                          metadata: Optional[StreamMetadata] = None) -> HTTPStreamResponse:
        """创建HTTP流式响应
        
        Args:
            url: 请求URL
            method: HTTP方法
            headers: 请求头
            data: 请求数据
            stream_type: 流式类型
            metadata: 流式元数据
            
        Returns:
            HTTP流式响应对象
            
        Raises:
            StreamConnectionError: 连接失败时
            StreamError: 其他错误时
        """
        session = await self._ensure_session()
        
        try:
            # 准备请求参数
            request_kwargs = {
                'method': method,
                'url': url,
                'headers': headers or {}
            }
            
            # 添加数据
            if data is not None:
                if isinstance(data, dict):
                    request_kwargs['json'] = data
                else:
                    request_kwargs['data'] = data
            
            # 发起请求
            response = await session.request(**request_kwargs)
            
            # 检查响应状态
            if response.status >= 400:
                error_text = await response.text()
                if hasattr(response, 'close') and callable(response.close):
                    response.close()
                raise StreamConnectionError(f"HTTP请求失败: {response.status} - {error_text}")
            
            # 创建流式响应
            return HTTPStreamResponse(session, response, stream_type, metadata)
            
        except StreamConnectionError:
            # 重新抛出StreamConnectionError，不要包装
            raise
        except aiohttp.ClientError as e:
            error_msg = f"HTTP客户端错误: {e}"
            logger.error(error_msg)
            raise StreamConnectionError(error_msg, e)
        except Exception as e:
            error_msg = f"创建HTTP流式响应失败: {e}"
            logger.error(error_msg)
            raise StreamError(error_msg, e)
    
    async def close(self) -> None:
        """关闭HTTP客户端"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()
        return False


async def create_sse_stream(url: str, 
                          headers: Optional[Dict[str, str]] = None,
                          timeout: int = 30) -> HTTPStreamResponse:
    """创建Server-Sent Events流式连接
    
    Args:
        url: SSE端点URL
        headers: 请求头
        timeout: 超时时间
        
    Returns:
        SSE流式响应
    """
    client = HTTPStreamClient(timeout=timeout)
    
    # 设置SSE特定的请求头
    sse_headers = {
        'Accept': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive'
    }
    if headers:
        sse_headers.update(headers)
    
    return await client.create_stream(
        url=url,
        headers=sse_headers,
        stream_type=StreamType.SSE
    )


async def create_json_stream(url: str,
                           method: str = "POST",
                           data: Optional[Dict[str, Any]] = None,
                           headers: Optional[Dict[str, str]] = None,
                           timeout: int = 30) -> HTTPStreamResponse:
    """创建JSON流式连接
    
    Args:
        url: JSON流端点URL
        method: HTTP方法
        data: 请求数据
        headers: 请求头
        timeout: 超时时间
        
    Returns:
        JSON流式响应
    """
    client = HTTPStreamClient(timeout=timeout)
    
    # 设置JSON特定的请求头
    json_headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    if headers:
        json_headers.update(headers)
    
    return await client.create_stream(
        url=url,
        method=method,
        data=data,
        headers=json_headers,
        stream_type=StreamType.JSON
    )


class HTTPStreamPool:
    """HTTP流式连接池，用于管理多个并发流式连接"""
    
    def __init__(self, max_connections: int = 10, timeout: int = 30):
        """初始化连接池
        
        Args:
            max_connections: 最大连接数
            timeout: 连接超时时间
        """
        self.max_connections = max_connections
        self.timeout = timeout
        self._clients: List[HTTPStreamClient] = []
        self._semaphore = asyncio.Semaphore(max_connections)
    
    async def create_stream(self, *args, **kwargs) -> HTTPStreamResponse:
        """从连接池创建流式连接"""
        async with self._semaphore:
            client = HTTPStreamClient(timeout=self.timeout)
            self._clients.append(client)
            
            try:
                return await client.create_stream(*args, **kwargs)
            except Exception:
                # 如果创建失败，从池中移除客户端
                if client in self._clients:
                    self._clients.remove(client)
                await client.close()
                raise
    
    async def close_all(self) -> None:
        """关闭所有连接"""
        tasks = []
        for client in self._clients:
            tasks.append(asyncio.create_task(client.close()))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        self._clients.clear()
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close_all()
        return False