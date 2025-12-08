"""
后路由节点

负责收集来自LLM的流式文本内容，识别路由指令，对普通文本进行处理。
- 非路由指令：直接输出原始文本流到 text_stream（保持原始格式，支持markdown），
  同时发送给 chat_record_node 保存和客户端显示
- 路由指令：解析并发送给 RouteNode
- TTS支持：使用 split_text_by_sentences 分割句子发送给 TTS 节点

输入:
- text_stream: 统一的文本流输入（来自agent_node）

输出:
- text_stream: 原始文本流（非路由指令时直接输出，保持原始格式），发送给 chat_record_node 和客户端
- sentence_stream: 完整句子流，发送给TTS节点
- route_command: 路由指令，发送给RouteNode
"""

import sys
from pathlib import Path
from typing import List
import asyncio
import re

# 确保可以导入 src 模块（当从外部项目加载时）
_file_path = Path(__file__).resolve()
_project_root = _file_path.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from stream_workflow.core import Node, ParameterSchema, StreamChunk, register_node
from src.common.utils.audio.audio_utils import split_text_by_sentences


@register_node("post_route_node")
class PostRouteNode(Node):
    """负责收集LLM流式文本，识别路由指令，处理普通文本。
    
    功能: 接收来自 agent 节点的流式文本输出，识别其中的路由指令（格式：<route|agent_id|用户需求|转场描述>），
    - 非路由指令：直接输出原始文本流到 text_stream（保持原始格式，支持markdown），
      同时发送给 chat_record_node 保存和客户端显示
    - 路由指令：解析并发送给路由节点
    - TTS支持：使用 split_text_by_sentences 分割句子发送给 TTS 节点
    
    配置参数: 无
    """
    
    EXECUTION_MODE = "streaming"    # 输入参数定义
    INPUT_PARAMS = {
        "text_stream": ParameterSchema(
            is_streaming=True,
            schema={'text': 'string'}
        )
    }    # 输出参数定义
    OUTPUT_PARAMS = {
        "sentence_stream": ParameterSchema(
            is_streaming=True,
            schema={'text': 'string'}
        ),
        "route_command": ParameterSchema(
            is_streaming=True,
            schema={'target_agent': 'string', 'user_query': 'string', 'text': 'string'}
        ),
        "text_stream": ParameterSchema(
            is_streaming=True,
            schema={'text': 'string'}
        )
    }
    
    CONFIG_PARAMS = {}
    
    # 路由指令格式: <route|agent_id|用户需求|转场描述>
    _ROUTE_PATTERN = re.compile(r'<route\|([^|]+)\|([^|]+)\|([^|>]+)>')

    async def initialize(self, context):
        """初始化节点状态"""
        self.context = context
        self._buffer = ""  # 文本缓冲区
        self._processed_length = 0  # 已处理的文本长度（用于 text_stream 直通）

    async def run(self, context):
        """节点主循环"""
        context.log_info("PostRoute 节点初始化完成")
        await asyncio.sleep(float("inf"))

    async def on_chunk_received(self, param_name: str, chunk: StreamChunk):
        """处理接收到的数据块"""
        if param_name == "text_stream":
            text = (chunk.data or {}).get("text", "")
            await self._process_text_chunk(text)

    async def _process_text_chunk(self, text: str):
        """处理文本块的核心逻辑"""
        try:
            # 空文本表示流结束
            if text == "":
                await self._flush_remaining()
                # 确保发送空文本以触发chat_record_node保存AI回复
                await self.emit_chunk("text_stream", {"text": ""})
                await self.emit_chunk("sentence_stream", {"text": ""})
                self.context.log_info("PostRoute 完成流处理")
                return
            
            # 累积到缓冲区
            self._buffer += text
            
            # 处理缓冲区中的内容
            await self._process_buffer()
            
        except Exception as e:
            self.context.log_error(f"PostRoute 处理文本失败: {e}", exc_info=True)

    async def _process_buffer(self):
        """处理缓冲区内容：识别路由指令，非路由指令直接输出原始文本流"""
        while True:
            # 检查缓冲区中是否包含路由指令
            route_match = self._ROUTE_PATTERN.search(self._buffer)
            
            if route_match:
                # 找到路由指令，需要分离路由指令前后的文本
                route_start = route_match.start()
                route_end = route_match.end()
                
                # 路由指令前的文本，直接输出到 text_stream（直通，只发送新增部分）
                if route_start > 0:
                    before_route = self._buffer[:route_start]
                    # 只发送新增的增量部分到 text_stream
                    if len(before_route) > self._processed_length:
                        new_text = before_route[self._processed_length:]
                        await self.emit_chunk("text_stream", {"text": new_text})
                        self._processed_length = len(before_route)
                    
                    # 同时处理成句子发送给 sentence_stream
                    remaining, sentences = split_text_by_sentences(before_route)
                    for sentence in sentences:
                        await self.emit_chunk("sentence_stream", {"text": sentence})
                
                # 处理路由指令
                route_text = self._buffer[route_start:route_end]
                route_match_obj = self._ROUTE_PATTERN.match(route_text.strip())
                if route_match_obj:
                    await self._process_route_command(route_match_obj)
                
                # 更新缓冲区为路由指令后的文本，重置已处理长度
                self._buffer = self._buffer[route_end:]
                self._processed_length = 0
                
                # 继续处理剩余缓冲区（可能还有更多内容）
                if not self._buffer:
                    break
            else:
                # 没有找到路由指令，检查是否可能包含不完整的路由指令
                # 如果缓冲区以 <route| 开头但还没完整，保留在缓冲区中等待更多内容
                if self._buffer.strip().startswith("<route|") and ">" not in self._buffer:
                    # 可能是不完整的路由指令，等待更多内容
                    break
                
                # 没有路由指令，直接输出到 text_stream（直通，只发送新增部分）
                # 同时使用 split_text_by_sentences 分割句子发送给 sentence_stream
                if self._buffer:
                    # 只发送新增的增量部分到 text_stream（直通）
                    if len(self._buffer) > self._processed_length:
                        new_text = self._buffer[self._processed_length:]
                        await self.emit_chunk("text_stream", {"text": new_text})
                        self._processed_length = len(self._buffer)
                    
                    # 分割句子发送给 sentence_stream（只发送已完成的句子）
                    remaining, sentences = split_text_by_sentences(self._buffer)
                    for sentence in sentences:
                        await self.emit_chunk("sentence_stream", {"text": sentence})
                    
                    # 更新缓冲区为剩余文本（未完成的句子）
                    # 调整已处理长度：因为已完成句子已从缓冲区移除，剩余文本都已发送过
                    self._buffer = remaining
                    self._processed_length = len(remaining)
                break

    async def _process_route_command(self, match: re.Match):
        """处理路由指令"""
        agent_id = match.group(1).strip()
        user_query = match.group(2).strip()
        transition = match.group(3).strip()
        
        # 转场描述发送给 TTS
        if transition:
            await self.emit_chunk("sentence_stream", {"text": transition})
            self.context.log_debug(f"发送转场描述: {transition[:50]}...")
        
        # 路由指令发送给 route_node
        await self.emit_chunk("route_command", {
            "target_agent": agent_id,
            "user_query": user_query,
            "text": transition
        })
        
        self.context.log_info(
            f"路由指令: {agent_id} | 需求: {user_query} | 转场: {transition}"
        )

    async def _flush_remaining(self):
        """清空缓冲区，发送所有剩余内容"""
        # 处理所有剩余内容
        await self._process_buffer()
        
        # 如果还有剩余文本，发送到 text_stream 和 sentence_stream
        if self._buffer.strip():
            # 只发送新增的增量部分到 text_stream
            if len(self._buffer) > self._processed_length:
                new_text = self._buffer[self._processed_length:]
                await self.emit_chunk("text_stream", {"text": new_text})
            await self.emit_chunk("sentence_stream", {"text": self._buffer})
            self.context.log_debug(f"最终发送剩余文本: {self._buffer[:50]}...")
            self._buffer = ""
            self._processed_length = 0
