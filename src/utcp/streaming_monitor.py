#!/usr/bin/env python3
"""
UTCP流式调用监控和错误处理

这个模块提供流式调用的监控、错误处理和性能指标收集功能。
"""

import asyncio
import time
import logging
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum
import json

logger = logging.getLogger(__name__)


class StreamErrorType(Enum):
    """流式错误类型"""
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    FORMAT = "format"
    SERVICE = "service"
    UNKNOWN = "unknown"


@dataclass
class StreamMetrics:
    """流式调用性能指标"""
    start_time: float
    end_time: Optional[float] = None
    total_chunks: int = 0
    total_bytes: int = 0
    first_chunk_time: Optional[float] = None
    last_chunk_time: Optional[float] = None
    error_count: int = 0
    timeout_count: int = 0
    
    @property
    def duration(self) -> float:
        """总耗时（秒）"""
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time
    
    @property
    def throughput(self) -> float:
        """吞吐量（字节/秒）"""
        duration = self.duration
        if duration > 0:
            return self.total_bytes / duration
        return 0.0
    
    @property
    def chunk_rate(self) -> float:
        """块速率（块/秒）"""
        duration = self.duration
        if duration > 0:
            return self.total_chunks / duration
        return 0.0
    
    @property
    def first_chunk_latency(self) -> Optional[float]:
        """首块延迟（秒）"""
        if self.first_chunk_time:
            return self.first_chunk_time - self.start_time
        return None


@dataclass
class StreamError:
    """流式错误信息"""
    error_type: StreamErrorType
    message: str
    timestamp: float
    service_name: Optional[str] = None
    tool_name: Optional[str] = None
    retry_count: int = 0
    context: Dict[str, Any] = field(default_factory=dict)


class StreamHealthChecker:
    """流式连接健康检查器"""
    
    def __init__(self, check_interval: float = 30.0, timeout: float = 10.0):
        self.check_interval = check_interval
        self.timeout = timeout
        self.health_status: Dict[str, bool] = {}
        self.last_check: Dict[str, float] = {}
        self._running = False
        self._check_task: Optional[asyncio.Task] = None
    
    async def start(self):
        """启动健康检查"""
        if not self._running:
            self._running = True
            self._check_task = asyncio.create_task(self._health_check_loop())
            logger.info("流式连接健康检查器已启动")
    
    async def stop(self):
        """停止健康检查"""
        self._running = False
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
            logger.info("流式连接健康检查器已停止")
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while self._running:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查循环错误: {e}")
                await asyncio.sleep(5.0)  # 错误后短暂等待
    
    async def _perform_health_checks(self):
        """执行健康检查"""
        current_time = time.time()
        
        # 检查所有注册的服务
        for service_name in list(self.health_status.keys()):
            try:
                is_healthy = await self._check_service_health(service_name)
                self.health_status[service_name] = is_healthy
                self.last_check[service_name] = current_time
                
                if not is_healthy:
                    logger.warning(f"服务 {service_name} 健康检查失败")
                
            except Exception as e:
                logger.error(f"检查服务 {service_name} 健康状态时出错: {e}")
                self.health_status[service_name] = False
    
    async def _check_service_health(self, service_name: str) -> bool:
        """检查单个服务的健康状态"""
        # 这里可以实现具体的健康检查逻辑
        # 例如发送ping请求、检查连接状态等
        try:
            # 模拟健康检查
            await asyncio.sleep(0.1)
            return True
        except Exception:
            return False
    
    def register_service(self, service_name: str):
        """注册需要健康检查的服务"""
        self.health_status[service_name] = True
        self.last_check[service_name] = time.time()
        logger.debug(f"已注册服务健康检查: {service_name}")
    
    def is_healthy(self, service_name: str) -> bool:
        """检查服务是否健康"""
        return self.health_status.get(service_name, False)


class StreamMonitor:
    """流式调用监控器"""
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.active_streams: Dict[str, StreamMetrics] = {}
        self.completed_streams: List[StreamMetrics] = []
        self.errors: List[StreamError] = []
        self.health_checker = StreamHealthChecker()
        self._lock = asyncio.Lock()
    
    async def start(self):
        """启动监控器"""
        await self.health_checker.start()
        logger.info("流式调用监控器已启动")
    
    async def stop(self):
        """停止监控器"""
        await self.health_checker.stop()
        logger.info("流式调用监控器已停止")
    
    def start_stream_monitoring(self, stream_id: str, service_name: str = None, tool_name: str = None) -> str:
        """开始流式调用监控"""
        metrics = StreamMetrics(start_time=time.time())
        self.active_streams[stream_id] = metrics
        
        logger.debug(f"开始监控流式调用: {stream_id}")
        return stream_id
    
    def record_chunk(self, stream_id: str, chunk_size: int):
        """记录流式数据块"""
        if stream_id in self.active_streams:
            metrics = self.active_streams[stream_id]
            metrics.total_chunks += 1
            metrics.total_bytes += chunk_size
            
            current_time = time.time()
            if metrics.first_chunk_time is None:
                metrics.first_chunk_time = current_time
            metrics.last_chunk_time = current_time
    
    def record_error(self, stream_id: str, error_type: StreamErrorType, message: str, 
                    service_name: str = None, tool_name: str = None, context: Dict[str, Any] = None):
        """记录流式错误"""
        error = StreamError(
            error_type=error_type,
            message=message,
            timestamp=time.time(),
            service_name=service_name,
            tool_name=tool_name,
            context=context or {}
        )
        
        self.errors.append(error)
        
        # 更新流式指标中的错误计数
        if stream_id in self.active_streams:
            metrics = self.active_streams[stream_id]
            metrics.error_count += 1
            
            if error_type == StreamErrorType.TIMEOUT:
                metrics.timeout_count += 1
        
        logger.error(f"流式调用错误 [{stream_id}]: {error_type.value} - {message}")
        
        # 保持错误历史记录在限制范围内
        if len(self.errors) > self.max_history:
            self.errors = self.errors[-self.max_history:]
    
    def finish_stream_monitoring(self, stream_id: str):
        """完成流式调用监控"""
        if stream_id in self.active_streams:
            metrics = self.active_streams[stream_id]
            metrics.end_time = time.time()
            
            # 移动到完成列表
            self.completed_streams.append(metrics)
            del self.active_streams[stream_id]
            
            # 保持历史记录在限制范围内
            if len(self.completed_streams) > self.max_history:
                self.completed_streams = self.completed_streams[-self.max_history:]
            
            logger.debug(f"完成流式调用监控: {stream_id}, 耗时: {metrics.duration:.2f}s, 块数: {metrics.total_chunks}")
    
    def get_stream_metrics(self, stream_id: str) -> Optional[StreamMetrics]:
        """获取流式调用指标"""
        return self.active_streams.get(stream_id)
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """获取性能摘要"""
        all_streams = list(self.active_streams.values()) + self.completed_streams
        
        if not all_streams:
            return {
                "total_streams": 0,
                "active_streams": 0,
                "avg_duration": 0.0,
                "avg_throughput": 0.0,
                "avg_chunk_rate": 0.0,
                "total_errors": len(self.errors),
                "error_rate": 0.0
            }
        
        completed_streams = [s for s in all_streams if s.end_time is not None]
        
        avg_duration = sum(s.duration for s in completed_streams) / len(completed_streams) if completed_streams else 0.0
        avg_throughput = sum(s.throughput for s in completed_streams) / len(completed_streams) if completed_streams else 0.0
        avg_chunk_rate = sum(s.chunk_rate for s in completed_streams) / len(completed_streams) if completed_streams else 0.0
        
        total_errors = sum(s.error_count for s in all_streams)
        error_rate = total_errors / len(all_streams) if all_streams else 0.0
        
        return {
            "total_streams": len(all_streams),
            "active_streams": len(self.active_streams),
            "completed_streams": len(completed_streams),
            "avg_duration": avg_duration,
            "avg_throughput": avg_throughput,
            "avg_chunk_rate": avg_chunk_rate,
            "total_errors": total_errors,
            "error_rate": error_rate,
            "recent_errors": len([e for e in self.errors if time.time() - e.timestamp < 300])  # 最近5分钟的错误
        }
    
    def get_error_summary(self) -> Dict[str, Any]:
        """获取错误摘要"""
        if not self.errors:
            return {"total_errors": 0, "error_types": {}, "recent_errors": []}
        
        # 按错误类型统计
        error_types = {}
        for error in self.errors:
            error_type = error.error_type.value
            if error_type not in error_types:
                error_types[error_type] = 0
            error_types[error_type] += 1
        
        # 最近的错误
        recent_errors = [
            {
                "type": e.error_type.value,
                "message": e.message,
                "timestamp": e.timestamp,
                "service": e.service_name,
                "tool": e.tool_name
            }
            for e in self.errors[-10:]  # 最近10个错误
        ]
        
        return {
            "total_errors": len(self.errors),
            "error_types": error_types,
            "recent_errors": recent_errors
        }


class StreamTimeoutHandler:
    """流式调用超时处理器"""
    
    def __init__(self, default_timeout: float = 60.0):
        self.default_timeout = default_timeout
        self.active_timeouts: Dict[str, asyncio.Task] = {}
    
    async def set_timeout(self, stream_id: str, timeout: float = None, 
                         callback: Callable[[str], None] = None) -> str:
        """设置流式调用超时"""
        timeout = timeout or self.default_timeout
        
        async def timeout_handler():
            try:
                await asyncio.sleep(timeout)
                if callback:
                    callback(stream_id)
                logger.warning(f"流式调用超时: {stream_id}, 超时时间: {timeout}s")
            except asyncio.CancelledError:
                pass
        
        # 取消现有的超时任务
        if stream_id in self.active_timeouts:
            self.active_timeouts[stream_id].cancel()
        
        # 创建新的超时任务
        self.active_timeouts[stream_id] = asyncio.create_task(timeout_handler())
        return stream_id
    
    def cancel_timeout(self, stream_id: str):
        """取消流式调用超时"""
        if stream_id in self.active_timeouts:
            self.active_timeouts[stream_id].cancel()
            del self.active_timeouts[stream_id]
    
    def clear_all_timeouts(self):
        """清除所有超时任务"""
        for task in self.active_timeouts.values():
            task.cancel()
        self.active_timeouts.clear()


# 全局监控器实例
_global_monitor: Optional[StreamMonitor] = None


def get_global_monitor() -> StreamMonitor:
    """获取全局流式监控器"""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = StreamMonitor()
    return _global_monitor


async def start_global_monitoring():
    """启动全局流式监控"""
    monitor = get_global_monitor()
    await monitor.start()


async def stop_global_monitoring():
    """停止全局流式监控"""
    global _global_monitor
    if _global_monitor:
        await _global_monitor.stop()
        _global_monitor = None