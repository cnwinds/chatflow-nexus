"""
路由节点

负责将用户文本路由到当前激活的 agent，并处理 agent 之间的切换。
支持多个 agent 并行连接，根据路由指令动态切换激活的 agent。

输入:
- user_text: 来自 STT 的用户文本（流式）
- route_command: 来自 PostRouteNode 的路由指令（非流式），格式如 {"target_agent": "agent2", "user_query": "讲个故事吧", "text": "我来给你讲个有趣的故事。"}
  路由指令由 PostRouteNode 解析自格式：<route|agent_id|用户的需求|转场描述>
- agent_intro: 各个 agent 的自我介绍（非流式），格式如 {"agent_id": "agent2", "intro_text": "..."}

输出:
- user_text_to_agent1: 发送给 agent1 的用户文本
- user_text_to_agent2: 发送给 agent2 的用户文本
- intro_request: 广播自我介绍请求
- all_agents_intro: 广播所有 agent 介绍给每个 agent
"""

from typing import Any, Dict, Optional, Set
import asyncio

from stream_workflow.core import Node, ParameterSchema, StreamChunk, register_node
from stream_workflow.core.parameter import FieldSchema


@register_node("route_node")
class RouteNode(Node):
    """负责将用户文本路由到当前激活的 agent，并处理 agent 之间的切换。
    
    功能: 管理多个 agent 节点的路由和切换。接收用户文本输入，将其路由到当前激活的 agent。
    接收来自 PostRouteNode 的路由指令，根据指令切换激活的 agent，并将转场信息发送给目标 agent。
    支持 agent 自我介绍的管理和广播，确保所有 agent 了解其他 agent 的能力。
    
    配置参数:
    - default_agent: 默认激活的 agent ID，系统启动时默认使用的 agent，默认为 "agent1"。
    """
    
    EXECUTION_MODE = "streaming"
    
    INPUT_PARAMS = {
        "user_text": ParameterSchema(
            is_streaming=True,
            schema={"text": "string", "confidence": "float", "audio_file_path": "string", "emotion": "string"}
        ),
        "route_command": ParameterSchema(
            is_streaming=True,
            schema={"target_agent": "string", "user_query": "string", "text": "string"}
        ),
        "agent_intro": ParameterSchema(
            is_streaming=True,
            schema={"agent_id": "string", "intro_text": "string"}
        ),
        "init_trigger": ParameterSchema(
            is_streaming=True,
            schema={}
        )
    }
    
    OUTPUT_PARAMS = {
        "user_text_to_route": ParameterSchema(
            is_streaming=True,
            schema={"text": "string", "confidence": "float", "audio_file_path": "string", "emotion": "string"}
        ),
        "route_text": ParameterSchema(
            is_streaming=True,
            schema={"user_query": "string", "transition_text": "string"}
        ),
        "intro_request": ParameterSchema(
            is_streaming=True,
            schema={}
        ),
        "all_agents_intro": ParameterSchema(
            is_streaming=True,
            schema={"agents": "object"}
        )
    }    # 配置参数定义（使用 FieldSchema 格式）
    CONFIG_PARAMS = {
        "default_agent": FieldSchema({
            'type': 'string',
            'required': True,
            'description': '默认激活的agent ID'
        })
    }

    async def initialize(self, context):
        self.context = context
        # 当前激活的 agent ID
        self._active_agent = "agent1"
        # agent 介绍缓存
        self._agent_intros = {}
        # 期望的 agent 列表（从配置中获取）
        self._expected_agents = set()
        # 是否已经完成自我介绍广播
        self._intro_broadcasted = False

    async def run(self, context):
        """运行节点，等待流式输入"""
        self.engine = context.get_global_var("engine")

        # 从 workflow 连接关系中获取期望的 agent 节点
        # 期望的节点就是通过 user_text_to_route 输出连接到的节点
        self._expected_agents = self._get_connected_agents_from_workflow()
        
        # 从配置中获取默认激活的 agent（如果配置中有的话）
        self._active_agent = self.get_config("config.default_agent", "agent1")
        
        # 如果没有找到任何连接的 agent，使用默认值
        if not self._expected_agents:
            self.context.log_warning("未找到连接到 user_text_to_route 的节点，使用默认配置")
            self._expected_agents = set(self.get_config("config.agents", ["agent1"]))
        
        self.context.log_info(f"RouteNode 初始化完成，期望的 agents: {self._expected_agents}, 默认激活: {self._active_agent}")
        
        # 发送自我介绍请求
        await self.emit_chunk("intro_request", {})
        
        await asyncio.sleep(float("inf"))
    
    def _get_connected_agents_from_workflow(self) -> Set[str]:
        """从 workflow 连接关系中获取连接到 user_text_to_route 输出的节点"""
        connections = self.engine.get_connection_manager().get_connected_nodes(self.node_id, "user_text_to_route")
        
        connected_agents = set()
        for conn in connections:
            connected_agents.add(conn["target_node"])
        
        return connected_agents

    async def on_chunk_received(self, param_name: str, chunk: StreamChunk):
        """处理接收到的数据块"""
        if param_name == "user_text":
            await self._handle_user_text(chunk)
        elif param_name == "route_command":
            await self._handle_route_command(chunk)
        elif param_name == "agent_intro":
            await self._handle_agent_intro(chunk)

    async def _handle_user_text(self, chunk: StreamChunk):
        """处理用户文本，路由到当前激活的 agent"""
        text = (chunk.data or {}).get("text", "")
        confidence = (chunk.data or {}).get("confidence", 1.0)
        audio_file_path = (chunk.data or {}).get("audio_file_path", None)
        emotion = (chunk.data or {}).get("emotion", "")
        
        # 直接通过节点名称发送消息到对应的 agent
        target_node = self.engine.get_node(self._active_agent)
        if target_node:
            # 直接向目标节点发送 user_text 输入，包含音频文件路径和情感信息
            await target_node.feed_input_chunk("user_text", {
                "text": text, 
                "confidence": confidence,
                "audio_file_path": audio_file_path,
                "emotion": emotion
            })
        else:
            self.context.log_warning(f"找不到目标 agent 节点: {self._active_agent}")
        
    async def _handle_route_command(self, chunk: StreamChunk):
        """处理路由指令，切换激活的 agent"""
        data = chunk.data or {}
        target_agent = data.get("target_agent", "")
        user_query = data.get("user_query", "")  # 用户的原始问题
        transition_text = data.get("text", "")  # 转场描述
        
        if not target_agent:
            self.context.log_warning("路由指令缺少 target_agent")
            return
        
        if target_agent not in self._expected_agents:
            self.context.log_warning(f"未知的 target_agent: {target_agent}")
            return
        
        # 切换激活的 agent
        old_agent = self._active_agent
        self._active_agent = target_agent
        
        self.context.log_info(f"路由切换: {old_agent} -> {self._active_agent}, 用户需求: {user_query}")
        
        # 通过 route_text 输出发送给目标 agent
        # 直接通过节点名称发送消息到对应的 agent
        target_node = self.engine.get_node(self._active_agent)
        if target_node:
            await target_node.feed_input_chunk("route_text", {
                "user_query": user_query,
                "transition_text": transition_text
            })
        else:
            self.context.log_warning(f"找不到目标 agent 节点: {self._active_agent}")

    async def _handle_agent_intro(self, chunk: StreamChunk):
        """处理 agent 自我介绍"""
        data = chunk.data or {}
        agent_id = data.get("agent_id", "")
        intro_text = data.get("intro_text", "")
        
        if not agent_id or not intro_text:
            self.context.log_warning("agent 自我介绍缺少必要字段")
            return
        
        # 缓存 agent 介绍
        self._agent_intros[agent_id] = intro_text
        self.context.log_info(f"收到 agent {agent_id} 的自我介绍: {intro_text}")
        
        # 检查是否所有期望的 agent 都已响应
        if self._agent_intros.keys() >= self._expected_agents:
            await self._broadcast_all_intros()

    async def _broadcast_all_intros(self):
        """广播所有 agent 的自我介绍"""
        if self._intro_broadcasted:
            return
        
        self._intro_broadcasted = True
        self.context.log_info(f"广播所有 agent 介绍: {self._agent_intros}")
        
        # 发送给所有 agent
        await self.emit_chunk("all_agents_intro", {"agents": self._agent_intros})
