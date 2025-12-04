#!/usr/bin/env python3
"""
UTCP本地流式响应处理

这个模块实现了本地服务的流式响应处理，包装AsyncGenerator为标准流式响应。
"""

import asyncio
import logging
from typing import AsyncGenerator, AsyncIterator, Any, Optional, List
from .streaming import StreamResponse, StreamType, StreamMetadata, StreamError, StreamClosedError

logger = logging.getLogger(__name__)


class LocalStreamResponse(StreamResponse):
    """本地服务的流式响应实现"""
    
    def __init__(self, 
                 generator: AsyncGenerator[Any, None],
                 stream_type: StreamType = StreamType.TEXT,
                 content_type: str = "text/plain",
                 metadata: Optional[StreamMetadata] = None):
        """初始化本地流式响应
        
        Args:
            generator: 异步生成器
            stream_type: 流式类型
            content_type: 内容类型
            metadata: 流式元数据
        """
        super().__init__(stream_type, content_type, metadata)
        self.generator = generator
        self._items_yielded = 0
        self._start_time = asyncio.get_event_loop().time()
    
    async def __aiter__(self) -> AsyncIterator[Any]:
        """异步迭代器实现"""
        if self._closed:
            logger.warning("尝试迭代已关闭的本地流式响应")
            return
        
        try:
            async for item in self.generator:
                if self._closed:
                    logger.debug("流式响应已关闭，停止迭代")
                    break
                
                self._items_yielded += 1
                
                # 记录调试信息
                if self._items_yielded % 100 == 0:  # 每100项记录一次
                    elapsed = asyncio.get_event_loop().time() - self._start_time
                    logger.debug(f"本地流式响应已产出 {self._items_yielded} 项，耗时 {elapsed:.2f}s")
                
                yield item
                
        except GeneratorExit:
            logger.debug("生成器正常退出")
        except Exception as e:
            error_msg = f"本地流式响应迭代出错: {e}"
            logger.error(error_msg)
            self._set_error(StreamError(error_msg, e))
            raise StreamError(error_msg, e)
        finally:
            await self.close()
    
    async def close(self) -> None:
        """关闭生成器和流式响应"""
        if self._closed:
            return
        
        self._closed = True
        
        try:
            # 关闭异步生成器
            if hasattr(self.generator, 'aclose'):
                await self.generator.aclose()
            
            # 记录统计信息
            elapsed = asyncio.get_event_loop().time() - self._start_time
            logger.debug(f"本地流式响应已关闭，共产出 {self._items_yielded} 项，总耗时 {elapsed:.2f}s")
            
        except Exception as e:
            logger.warning(f"关闭本地流式响应时出错: {e}")
    
    @property
    def items_yielded(self) -> int:
        """获取已产出的项目数量"""
        return self._items_yielded
    
    @property
    def elapsed_time(self) -> float:
        """获取已经过的时间（秒）"""
        return asyncio.get_event_loop().time() - self._start_time


class LocalStreamBuffer:
    """本地流式缓冲区，用于缓存和管理流式数据"""
    
    def __init__(self, buffer_size: int = 1024):
        """初始化缓冲区
        
        Args:
            buffer_size: 缓冲区大小
        """
        self.buffer_size = buffer_size
        self._buffer: List[Any] = []
        self._closed = False
        self._condition = asyncio.Condition()
    
    async def put(self, item: Any) -> None:
        """向缓冲区添加项目
        
        Args:
            item: 要添加的项目
            
        Raises:
            StreamClosedError: 当缓冲区已关闭时
        """
        if self._closed:
            raise StreamClosedError("无法向已关闭的缓冲区添加项目")
        
        async with self._condition:
            # 如果缓冲区满了，等待消费者消费
            while len(self._buffer) >= self.buffer_size and not self._closed:
                await self._condition.wait()
            
            if self._closed:
                raise StreamClosedError("无法向已关闭的缓冲区添加项目")
            
            self._buffer.append(item)
            self._condition.notify()  # 通知等待的消费者
    
    async def get(self) -> Any:
        """从缓冲区获取项目
        
        Returns:
            缓冲区中的项目
            
        Raises:
            StreamClosedError: 当缓冲区已关闭且为空时
        """
        async with self._condition:
            # 等待直到有数据或缓冲区关闭
            while not self._buffer and not self._closed:
                await self._condition.wait()
            
            if self._buffer:
                item = self._buffer.pop(0)
                self._condition.notify()  # 通知等待的生产者
                return item
            elif self._closed:
                raise StreamClosedError("缓冲区已关闭且为空")
    
    async def close(self) -> None:
        """关闭缓冲区"""
        async with self._condition:
            self._closed = True
            self._condition.notify_all()  # 通知所有等待的协程
    
    @property
    def is_closed(self) -> bool:
        """检查缓冲区是否已关闭"""
        return self._closed
    
    @property
    def size(self) -> int:
        """获取缓冲区当前大小"""
        return len(self._buffer)
    
    @property
    def is_empty(self) -> bool:
        """检查缓冲区是否为空"""
        return len(self._buffer) == 0
    
    @property
    def is_full(self) -> bool:
        """检查缓冲区是否已满"""
        return len(self._buffer) >= self.buffer_size


async def create_buffered_stream(generator: AsyncGenerator[Any, None], 
                                buffer_size: int = 1024) -> LocalStreamResponse:
    """创建带缓冲的本地流式响应
    
    Args:
        generator: 原始异步生成器
        buffer_size: 缓冲区大小
        
    Returns:
        带缓冲的本地流式响应
    """
    buffer = LocalStreamBuffer(buffer_size)
    
    async def buffered_generator():
        """缓冲生成器"""
        try:
            # 启动生产者任务
            producer_task = asyncio.create_task(_producer(generator, buffer))
            
            # 消费数据
            while True:
                try:
                    item = await buffer.get()
                    yield item
                except StreamClosedError:
                    break
            
            # 等待生产者完成
            await producer_task
            
        except Exception as e:
            logger.error(f"缓冲流式响应出错: {e}")
            raise
        finally:
            await buffer.close()
    
    return LocalStreamResponse(buffered_generator())


async def _producer(generator: AsyncGenerator[Any, None], buffer: LocalStreamBuffer) -> None:
    """生产者协程，将数据从生成器放入缓冲区
    
    Args:
        generator: 数据源生成器
        buffer: 目标缓冲区
    """
    try:
        async for item in generator:
            await buffer.put(item)
    except Exception as e:
        logger.error(f"生产者出错: {e}")
    finally:
        await buffer.close()


def create_text_stream(text: str, chunk_size: int = 1) -> LocalStreamResponse:
    """创建文本流式响应（用于测试和演示）
    
    Args:
        text: 要流式输出的文本
        chunk_size: 每次输出的字符数
        
    Returns:
        文本流式响应
    """
    async def text_generator():
        """文本生成器"""
        for i in range(0, len(text), chunk_size):
            chunk = text[i:i + chunk_size]
            yield chunk
            await asyncio.sleep(0.01)  # 模拟延迟
    
    return LocalStreamResponse(
        text_generator(),
        stream_type=StreamType.TEXT,
        content_type="text/plain"
    )


def create_json_stream(data_list: List[Any], delay: float = 0.1) -> LocalStreamResponse:
    """创建JSON流式响应（用于测试和演示）
    
    Args:
        data_list: 要流式输出的数据列表
        delay: 每项之间的延迟（秒）
        
    Returns:
        JSON流式响应
    """
    async def json_generator():
        """JSON生成器"""
        for item in data_list:
            yield item
            if delay > 0:
                await asyncio.sleep(delay)
    
    return LocalStreamResponse(
        json_generator(),
        stream_type=StreamType.JSON,
        content_type="application/json"
    )


async def merge_streams(*streams: LocalStreamResponse) -> LocalStreamResponse:
    """合并多个本地流式响应
    
    Args:
        *streams: 要合并的流式响应
        
    Returns:
        合并后的流式响应
    """
    async def merged_generator():
        """合并生成器"""
        tasks = []
        
        # 为每个流创建迭代任务
        for i, stream in enumerate(streams):
            task = asyncio.create_task(_stream_to_queue(stream, i))
            tasks.append(task)
        
        # 使用队列收集所有流的数据
        queue = asyncio.Queue()
        
        # 启动收集任务
        collector_tasks = []
        for i, stream in enumerate(streams):
            task = asyncio.create_task(_collect_stream(stream, queue, i))
            collector_tasks.append(task)
        
        # 等待所有流完成
        completed_streams = 0
        while completed_streams < len(streams):
            try:
                stream_id, item = await asyncio.wait_for(queue.get(), timeout=1.0)
                if item is None:  # 流结束标记
                    completed_streams += 1
                else:
                    yield item
            except asyncio.TimeoutError:
                # 检查是否所有流都已完成
                all_done = all(task.done() for task in collector_tasks)
                if all_done:
                    break
        
        # 清理任务
        for task in collector_tasks:
            if not task.done():
                task.cancel()
    
    return LocalStreamResponse(merged_generator())


async def _collect_stream(stream: LocalStreamResponse, queue: asyncio.Queue, stream_id: int) -> None:
    """收集单个流的数据到队列
    
    Args:
        stream: 流式响应
        queue: 目标队列
        stream_id: 流标识
    """
    try:
        async for item in stream:
            await queue.put((stream_id, item))
    except Exception as e:
        logger.error(f"收集流 {stream_id} 时出错: {e}")
    finally:
        await queue.put((stream_id, None))  # 结束标记


async def _stream_to_queue(stream: LocalStreamResponse, stream_id: int) -> None:
    """将流数据转换到队列（辅助函数）"""
    # 这个函数目前未使用，但保留以备将来扩展
    pass