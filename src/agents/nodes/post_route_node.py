"""
后路由节点

负责收集来自LLM的流式文本内容，使用split_text_by_sentences分割句子，
收集到完整句子后才发送给TTS节点。同时解析路由指令并发送给RouteNode。

输入:
- text_stream: 统一的文本流输入（来自agent_node）

输出:
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
    """负责收集LLM流式文本，识别路由指令，对普通文本断句。
    
    功能: 接收来自 agent 节点的流式文本输出，识别其中的路由指令（格式：<route|agent_id|用户需求|转场描述>），
    将路由指令发送给路由节点，将普通文本按句子分割后发送给 TTS 节点。
    
    配置参数: 无
    """
    
    EXECUTION_MODE = "streaming"
    
    INPUT_PARAMS = {
        "text_stream": ParameterSchema(
            is_streaming=True,
            schema={"text": "string"}
        )
    }
    
    OUTPUT_PARAMS = {
        "sentence_stream": ParameterSchema(
            is_streaming=True,
            schema={"text": "string"}
        ),
        "route_command": ParameterSchema(
            is_streaming=True,
            schema={"target_agent": "string", "user_query": "string", "text": "string"}
        )
    }
    
    CONFIG_PARAMS = {}
    
    # 路由指令格式: <route|agent_id|用户需求|转场描述>
    _ROUTE_PATTERN = re.compile(r'<route\|([^|]+)\|([^|]+)\|([^|>]+)>')

    async def initialize(self, context):
        """初始化节点状态"""
        self.context = context
        self._buffer = ""  # 文本缓冲区

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
        """处理缓冲区内容：使用 split_text_by_sentences 分割，识别路由指令"""
        # 使用 split_text_by_sentences 分割句子
        # 该函数会将 <...> 标签作为独立句子返回
        remaining, sentences = split_text_by_sentences(self._buffer)
        
        # 处理每个完整句子
        for sentence in sentences:
            # 检查是否是路由指令（去除空白字符进行匹配，但发送时保留所有空白字符）
            route_match = self._ROUTE_PATTERN.match(sentence.strip())
            
            if route_match:
                # 是路由指令，提取并发送
                await self._process_route_command(route_match)
            else:
                # 普通句子，发送给 TTS（完全保留所有空白字符）
                # 只检查是否包含非空白字符
                if sentence.strip():
                    await self.emit_chunk("sentence_stream", {"text": sentence})
                    self.context.log_debug(f"发送句子: {sentence[:50]}...")
        
        # 更新缓冲区为剩余文本
        self._buffer = remaining

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
        # 检查是否包含非空白字符
        if not self._buffer.strip():
            return
        
        # 处理所有剩余内容
        await self._process_buffer()
        
        # 如果还有剩余文本，作为最后一句发送（完全保留所有空白字符）
        if self._buffer.strip():
            await self.emit_chunk("sentence_stream", {"text": self._buffer})
            self.context.log_debug(f"最终发送: {self._buffer[:50]}...")
            self._buffer = ""
