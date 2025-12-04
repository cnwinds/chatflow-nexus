#!/usr/bin/env python3
"""
LLM聊天模块 - 高内聚的LLM调用封装

提供统一的LLM聊天功能，包括阻塞调用和流式调用，
自动管理聊天消息，包括工具调用过程中的消息。
"""

import json
import time
import logging
from typing import Dict, Any, List, Optional, AsyncGenerator
from dataclasses import dataclass

from src.common.config import get_config_manager
from src.common.logging.manager import LoggingManager
from src.common.config.constants import ConfigPaths
from src.utcp.streaming import StreamResponse
from src.agents.utcp_tools import call_utcp_tool, call_utcp_tool_stream


class LLMResponseError(Exception):
    """LLM响应处理相关异常"""
    pass


class ToolCallValidationError(LLMResponseError):
    """工具调用数据验证异常"""
    pass


@dataclass
class ToolCall:
    """工具调用数据结构"""
    id: str
    type: str = "function"
    function_name: str = ""
    function_arguments: str = "{}"
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ToolCall':
        """从字典创建ToolCall实例"""
        if not isinstance(data, dict):
            raise ToolCallValidationError(f"工具调用数据必须是字典类型，实际类型: {type(data)}")
        
        # 验证必需字段
        if not data.get("id"):
            raise ToolCallValidationError("工具调用缺少必需的 'id' 字段")
        
        function_data = data.get("function", {})
        if not isinstance(function_data, dict):
            raise ToolCallValidationError("工具调用的 'function' 字段必须是字典类型")
        
        # 验证 function_arguments 是否为有效 JSON
        arguments = function_data.get("arguments", "{}")
        try:
            json.loads(arguments)
        except json.JSONDecodeError as e:
            raise ToolCallValidationError(f"工具调用参数不是有效的 JSON 格式: {e}")
        
        return cls(
            id=data["id"],
            type=data.get("type", "function"),
            function_name=function_data.get("name", ""),
            function_arguments=arguments
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "id": self.id,
            "type": self.type,
            "function": {
                "name": self.function_name,
                "arguments": self.function_arguments
            }
        }


@dataclass
class Usage:
    """Token使用统计"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    
    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> 'Usage':
        """从字典创建Usage实例"""
        if not data:
            return cls()
        return cls(
            prompt_tokens=data.get('prompt_tokens', 0),
            completion_tokens=data.get('completion_tokens', 0),
            total_tokens=data.get('total_tokens', 0)
        )


@dataclass
class LLMResponse:
    """标准化的LLM响应数据结构"""
    content: str
    tool_calls: List[ToolCall]
    usage: Usage
    used_model: str
    request_model: str

    @classmethod
    def create(cls, content: str, tool_calls: Optional[List[Dict[str, Any]]] = None, 
               usage: Optional[Dict[str, Any]] = None, used_model: str = None, 
               request_model: str = None) -> 'LLMResponse':
        """创建LLMResponse实例"""
        parsed_tool_calls = []
        if tool_calls:
            try:
                parsed_tool_calls = [ToolCall.from_dict(tc) for tc in tool_calls]
            except (ToolCallValidationError, TypeError, AttributeError) as e:
                raise LLMResponseError(f"解析工具调用数据失败: {e}") from e
        
        return cls(
            content=content or "",
            tool_calls=parsed_tool_calls,
            usage=Usage.from_dict(usage),
            used_model=used_model,
            request_model=request_model
        )
    
    def has_tool_calls(self) -> bool:
        """检查是否包含工具调用"""
        return len(self.tool_calls) > 0
    
    def get_tool_calls_dict(self) -> List[Dict[str, Any]]:
        """获取工具调用的字典格式"""
        return [tc.to_dict() for tc in self.tool_calls]
    
    def get_used_model(self) -> str:
        """获取使用的模型"""
        return self.used_model
    
    def get_request_model(self) -> str:
        """获取请求的模型"""
        return self.request_model


class LLMChat:
    """LLM聊天模块"""
    
    # 常量定义
    DEFAULT_MAX_TOKENS = 1500
    DEFAULT_TEMPERATURE = 1.0
    DEFAULT_TOP_P = 1.0
    DEFAULT_MAX_ITERATIONS = 10
    
    def __init__(self):
        # 使用核心组件
        self.config_manager = get_config_manager()
        self.logging_manager = LoggingManager(self.config_manager)
        self.logger = self.logging_manager.get_logger("llm_chat")
        
        # 原始配置
        self.llm_config = None
        self._config_loaded = False
        
        # 预解析的配置（提前解析，避免每次调用时重复解析）
        self._parsed_configs = {}
        self._default_model_key = None
        
        # 消息管理
        self.conversation_history: List[Dict[str, Any]] = []
    
    def load_config(self, config: Dict[str, Any] = None):
        """
        加载并解析LLM配置
        
        Args:
            config: LLM配置字典
        """
        if not self._config_loaded:
            # 保存原始配置
            self.llm_config = config or {"primary": "azure_llm.primary", "fast": "ollama_llm.fast"}
            
            # 提前解析所有配置
            self._parse_all_configs()
            
            self._config_loaded = True
    
    def _parse_all_configs(self):
        """提前解析所有配置项，避免运行时重复解析"""
        # 解析每个配置项
        for key, provider_model in self.llm_config.items():
            if "." in provider_model:
                service_name, model_name = provider_model.split(".", 1)
            else:
                service_name = provider_model
                model_name = key
            
            provider = service_name.split("_")[0]
            
            # 提前拼接好完整的服务名，避免运行时拼接
            self._parsed_configs[key] = {
                "provider": provider,
                "service_name": service_name + ".chat_completion",
                "stream_service_name": service_name + ".chat_completion_stream",
                "model_name": model_name
            }
        
        # 设置默认模型（优先使用primary，否则使用第一个）
        if "primary" in self._parsed_configs:
            self._default_model_key = "primary"
        else:
            self._default_model_key = next(iter(self._parsed_configs)) if self._parsed_configs else None
    
    def _get_service_names(self, model: Optional[str] = None) -> tuple[str, str, str, str]:
        """
        根据model获取服务名（直接返回预解析的配置）
        
        Args:
            model: 模型名称（可选，如 "primary", "fast"），如果为None则使用默认模型
            
        Returns:
            (provider, service_name, stream_service_name, model_name)
        """
        # 确定使用哪个模型配置
        model_key = model if model else self._default_model_key
        # 从预解析的配置中获取
        if model_key and model_key in self._parsed_configs:
            parsed = self._parsed_configs[model_key]
        elif self._default_model_key and self._default_model_key in self._parsed_configs:
            # 如果指定的模型不存在，使用默认模型
            parsed = self._parsed_configs[self._default_model_key]
            self.logger.warning(f"模型 {model_key} 不存在，使用默认模型 {self._default_model_key}")
        else:
            # 使用硬编码的默认值
            self.logger.warning("没有可用的配置，使用硬编码默认值")
            return (
                "azure",
                "azure_llm.chat_completion",
                "azure_llm.chat_completion_stream",
                "primary"
            )
        
        # 直接返回预解析好的配置，无需运行时拼接
        return (
            parsed["provider"],
            parsed["service_name"],
            parsed["stream_service_name"],
            parsed["model_name"]
        )
    
    # 公共接口方法
    async def call_llm(self, messages: List[Dict[str, Any]], 
                      tools: Optional[List[Dict[str, Any]]] = None,
                      max_iterations: int = DEFAULT_MAX_ITERATIONS,
                      max_tokens: int = DEFAULT_MAX_TOKENS,
                      temperature: float = DEFAULT_TEMPERATURE,
                      top_p: float = DEFAULT_TOP_P,
                      context: str = "聊天对话",
                      session_id: str = None,
                      model: Optional[str] = None) -> LLMResponse:
        """
        统一的LLM调用接口（阻塞调用）
        
        Args:
            messages: 消息列表
            tools: 工具列表
            max_iterations: 最大迭代次数
            max_tokens: 最大token数
            temperature: 温度参数
            top_p: top_p参数
            context: 上下文描述
            model: 指定模型名称，默认为None
            
        Returns:
            LLMResponse: 完整的LLM响应对象
        """
        conversation_history = messages.copy()
        iteration_count = 0
        
        while iteration_count < max_iterations:
            try:
                # 调用LLM API
                response = await self._call_llm_api(conversation_history, tools, 
                                                  max_tokens, temperature, top_p, context, session_id, model)
                
                if not response:
                    raise ValueError("Invalid API response")
                
                if response.has_tool_calls():
                    # 处理工具调用
                    tool_calls_data = response.get_tool_calls_dict()
                    
                    conversation_history.append({
                        "role": "assistant",
                        "content": response.content or "",
                        "tool_calls": tool_calls_data
                    })
                    
                    await self._process_tool_calls(response.tool_calls, conversation_history)
                    iteration_count += 1
                    continue
                else:
                    # 无工具调用，返回响应
                    content = response.content or ""
                    conversation_history.append({
                        "role": "assistant",
                        "content": content
                    })
                    return response
                    
            except Exception as e:
                self.logger.error(f"Error processing chat with tools: {e}")
                raise
        
        self.logger.warning(f"Reached max iterations ({max_iterations})")
        error_response = LLMResponse.create("抱歉，工具调用次数过多，请重新开始对话。")
        return error_response
    
    async def call_llm_stream(self, messages: List[Dict[str, Any]], 
                            tools: Optional[List[Dict[str, Any]]] = None,
                            max_iterations: int = DEFAULT_MAX_ITERATIONS,
                            max_tokens: int = DEFAULT_MAX_TOKENS,
                            temperature: float = DEFAULT_TEMPERATURE,
                            top_p: float = DEFAULT_TOP_P,
                            context: str = "流式聊天",
                            session_id: str = None,
                            model: Optional[str] = None,
                            content_callback: Optional[callable] = None) -> LLMResponse:
        """
        流式LLM调用接口（通过回调处理流式内容）
        
        Args:
            messages: 消息列表
            tools: 工具列表
            max_iterations: 最大迭代次数
            max_tokens: 最大token数
            temperature: 温度参数
            top_p: top_p参数
            context: 上下文描述
            model: 指定模型名称，默认为None
            content_callback: 内容回调函数，用于实时处理流式内容，接收参数(chunk_type, chunk_data)
            
        Returns:
            LLMResponse: 最终的完整响应
        """
        conversation_history = messages.copy()
        iteration_count = 0
        
        while iteration_count < max_iterations:
            try:
                # 使用流式API调用，支持回调函数
                response = await self._call_llm_stream_api(
                    conversation_history, tools, max_tokens, temperature, 
                    top_p, context, session_id, model, content_callback)
                
                if not response:
                    raise ValueError("Invalid API response")
                
                if response.has_tool_calls():
                    # 处理工具调用
                    tool_calls_data = response.get_tool_calls_dict()
                    
                    conversation_history.append({
                        "role": "assistant",
                        "content": response.content or "",
                        "tool_calls": tool_calls_data
                    })
                    
                    await self._process_tool_calls(response.tool_calls, conversation_history)
                    iteration_count += 1
                    continue
                else:
                    # 无工具调用，返回响应
                    content = response.content or ""
                    conversation_history.append({
                        "role": "assistant",
                        "content": content
                    })
                    return response
                    
            except Exception as e:
                self.logger.error(f"Error processing stream chat with tools: {e}")
                raise
        
        self.logger.warning(f"Reached max iterations ({max_iterations})")
        # 返回错误响应
        error_response = LLMResponse.create("抱歉，工具调用次数过多，请重新开始对话。")
        return error_response
    
    # 消息管理方法
    def add_message(self, role: str, content: str = None, **kwargs) -> None:
        """添加消息到对话历史"""
        # 如果content在kwargs中，优先使用kwargs中的content
        if content is None and "content" in kwargs:
            content = kwargs.pop("content")
        
        message = {"role": role, "content": content}
        message.update(kwargs)
        self.conversation_history.append(message)
    
    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """获取对话历史"""
        return self.conversation_history.copy()
    
    def clear_conversation(self) -> None:
        """清空对话历史"""
        self.conversation_history = []
    
    # 私有方法（实现细节）
    async def _call_llm_api(self, messages: List[Dict[str, Any]], 
                           tools: Optional[List[Dict[str, Any]]] = None,
                           max_tokens: int = DEFAULT_MAX_TOKENS,
                           temperature: float = DEFAULT_TEMPERATURE,
                           top_p: float = DEFAULT_TOP_P,
                           context: str = "聊天", 
                           session_id: str = None,
                           model: Optional[str] = None) -> LLMResponse:
        """调用LLM API（阻塞版本）"""
        start_time = time.time()
        
        try:
            # 开始AI指标监控
            monitor_id = None
            try:
                result = await call_utcp_tool("ai_metrics_service.start_monitoring", {})
                monitor_id = result.get("monitor_id")
            except Exception as e:
                self.logger.debug(f"启动AI指标监控失败: {e}")

            self._log_request_details(messages, context, tools)
            
            # 动态获取服务名称（使用预解析的配置）
            provider, service_name, stream_service_name, model_name = self._get_service_names(model)
            # 准备API参数
            api_params = self._prepare_api_params(messages, tools, max_tokens, temperature, top_p, model_name)
            # 调用API
            result = await call_utcp_tool(service_name, api_params)
            
            # 完成监控
            if monitor_id:
                try:
                    await call_utcp_tool("ai_metrics_service.finish_monitoring", {
                        "monitor_id": monitor_id,
                        "provider": provider,
                        "model_name": result.get("used_model"),
                        "session_id": session_id,
                        "prompt_tokens": result.get("usage", {}).get("prompt_tokens", 0),
                        "completion_tokens": result.get("usage", {}).get("completion_tokens", 0)
                    })
                except Exception as e:
                    self.logger.debug(f"完成AI指标监控失败: {e}")
            
            # 计算处理时间
            process_duration = (time.time() - start_time) * 1000
            return await self._handle_llm_response(result, context, process_duration)
            
        except Exception as e:
            self.logger.error(f"❌ {context}API调用失败: {e}")
            if monitor_id:
                try:
                    await call_utcp_tool("ai_metrics_service.finish_monitoring", {
                        "monitor_id": monitor_id,
                        "provider": provider,
                        "result": str(e)
                    })
                except Exception:
                    pass
            raise
    
    async def _call_llm_stream_api(self, messages: List[Dict[str, Any]], 
                                                tools: Optional[List[Dict[str, Any]]] = None,
                                                max_tokens: int = DEFAULT_MAX_TOKENS,
                                                temperature: float = DEFAULT_TEMPERATURE,
                                                top_p: float = DEFAULT_TOP_P,
                                                context: str = "流式聊天",
                                                session_id: str = None,
                                                model: Optional[str] = None,
                                                content_callback: Optional[callable] = None) -> LLMResponse:
        """调用LLM API（流式版本，支持回调函数）"""
        # 开始AI指标监控
        monitor_id = None
        try:
            result = await call_utcp_tool("ai_metrics_service.start_monitoring", {})
            monitor_id = result.get("monitor_id")
        except Exception as e:
            self.logger.debug(f"启动AI指标监控失败: {e}")
        start_time = time.time()
        first_token_time = None
        
        try:
            self._log_request_details(messages, context, tools)
            
            # 计算输入统计
            total_input_chars = sum(len(str(msg.get('content', ''))) for msg in messages)
            tool_count = len(tools) if tools else 0
            
            self.logger.debug(f"🚀 开始{context}流式API调用")
            
            # 动态获取服务名称（使用预解析的配置）
            provider, service_name, stream_service_name, model_name = self._get_service_names(model)
            
            # API调用阶段
            api_params = self._prepare_api_params(messages, tools, max_tokens, temperature, top_p, model_name)
            
            stream_response = await call_utcp_tool_stream(stream_service_name, api_params)
            
            # 记录HTTP首字节时间
            http_first_byte_time = time.time()
            http_first_byte_duration = (http_first_byte_time - start_time) * 1000
            
            self.logger.debug(f"🌐 HTTP首字节时间: {http_first_byte_duration:.2f}ms")
            
            # 处理流式响应，支持回调函数
            response_data = await self._process_stream_response(
                stream_response, monitor_id, content_callback)
            
            # 计算输出统计
            output_chars = len(response_data.get("content", ""))
            tool_calls_made = len(response_data.get("tool_calls", []))
            
            # 计算第一个token的延迟
            first_token_duration = None
            if response_data.get("first_token_time"):
                first_token_duration = (response_data["first_token_time"] - start_time) * 1000
                self.logger.debug(f"🎯 第一个token延迟: {first_token_duration:.2f}ms")
            
            # 使用集成的完成监控接口
            if monitor_id:
                try:
                    await call_utcp_tool("ai_metrics_service.finish_monitoring", {
                        "monitor_id": monitor_id,
                        "provider": provider,
                        "model_name": response_data.get("used_model"),
                        "session_id": session_id,
                        "prompt_tokens": response_data.get("usage", {}).get("prompt_tokens", 0),
                        "completion_tokens": response_data.get("usage", {}).get("completion_tokens", 0),
                        "input_chars": total_input_chars,
                        "output_chars": output_chars,
                        "tool_count": tool_count,
                        "tool_calls_made": tool_calls_made,
                        "http_first_byte_time": http_first_byte_duration,
                        "first_token_time": first_token_duration
                    })
                except Exception as e:
                    self.logger.debug(f"完成AI指标监控失败: {e}")
            
            # 使用统一的响应处理接口
            process_duration = (time.time() - start_time) * 1000
            return await self._handle_llm_response(response_data, context, process_duration)
            
        except Exception as e:
            self.logger.error(f"❌ {context}流式API调用失败: {e}")
            if monitor_id:
                try:
                    await call_utcp_tool("ai_metrics_service.finish_monitoring", {
                        "monitor_id": monitor_id,
                        "provider": provider,
                        "result": str(e)
                    })
                except Exception:
                    pass
            raise
    
    async def _process_tool_calls(self, tool_calls: List[ToolCall], conversation_history: List[Dict[str, Any]]):
        """处理工具调用"""
        for tool_call in tool_calls:
            tool_name = tool_call.function_name
            try:
                arguments = json.loads(tool_call.function_arguments)
            except json.JSONDecodeError:
                self.logger.error(f"Invalid JSON in tool arguments: {tool_call.function_arguments}")
                arguments = {}
            
            self.logger.info(f"Calling tool: {tool_name}, args: {arguments}")
            
            try:
                tool_result = await call_utcp_tool(tool_name, arguments)
                result_str = self._format_tool_result(tool_result)
                self.logger.info(f"Tool result: {tool_name}, result: {result_str}")
                
            except Exception as e:
                result_str = f"工具调用失败: {str(e)}"
                self.logger.error(f"Tool call failed: {tool_name}, error: {e}")
            
            conversation_history.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result_str
            })
    
    def _format_tool_result(self, tool_result: Any) -> str:
        """格式化工具结果为字符串"""
        if isinstance(tool_result, str):
            return tool_result
        elif isinstance(tool_result, (int, float)):
            return str(tool_result)
        elif isinstance(tool_result, (list, dict)):
            return json.dumps(tool_result, ensure_ascii=False)
        else:
            return str(tool_result)
    
    def _prepare_api_params(self, messages: List[Dict[str, Any]], 
                           tools: Optional[List[Dict[str, Any]]], 
                           max_tokens: int, 
                           temperature: float, 
                           top_p: float,
                           model: str) -> Dict[str, Any]:
        """准备API调用参数"""
        api_params = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p
        }
        
        if tools:
            api_params["tools"] = tools
            api_params["tool_choice"] = "auto"
        
        api_params["model"] = model
        
        return api_params
    
    def _log_request_details(self, messages: List[Dict[str, Any]], context: str = "LLM请求", tools: Optional[List[Dict[str, Any]]] = None) -> None:
        """记录LLM请求的详细信息用于调试"""
        if not messages:
            self.logger.debug("📊 消息列表为空")
            return
            
        # 只有在debug级别启用时才进行json序列化
        import logging
        if self.logger.isEnabledFor(logging.DEBUG):
            import json
            self.logger.debug(f"📋 Messages: {json.dumps(messages, ensure_ascii=False, separators=(',', ':'))}")
    
    
    def _process_api_response(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """处理API响应"""
        # 这里需要根据实际的API响应格式进行处理
        # 暂时返回基本结构
        return {
            "content": result.get("content", ""),
            "tool_calls": result.get("tool_calls", []),
            "usage": result.get("usage"),
            "used_model": result.get("used_model", "unknown")
        }
    
    
    async def _process_stream_response(self, stream_response, monitor_id: Optional[str] = None, content_callback: Optional[callable] = None) -> Dict[str, Any]:
        """处理流式响应数据，支持回调函数"""
        # 类型检查：确保 stream_response 是 StreamResponse 对象
        from src.utcp.streaming import StreamResponse as StreamResponseType
        
        if not isinstance(stream_response, StreamResponseType):
            error_msg = f"stream_response 必须是 StreamResponse 对象，实际类型: {type(stream_response)}, 值: {stream_response}"
            self.logger.error(error_msg)
            raise TypeError(error_msg)
        
        full_content = ""
        tool_calls = []
        usage_info = None
        used_model = None
        first_token_time = None
        
        async for chunk in stream_response:
            chunk_type = chunk.get("type")
            
            # 调用回调函数处理实时内容
            if content_callback:
                try:
                    await content_callback(chunk_type, chunk)
                except Exception as e:
                    self.logger.warning(f"回调函数执行失败: {e}")
            
            if chunk_type == "content_delta":
                # 记录第一个token的时间
                if first_token_time is None:
                    first_token_time = time.time()
                    self.logger.debug(f"🎯 第一个token时间: {first_token_time}")
                
                self.logger.debug(f"🔍 流式响应内容: {chunk}")
                full_content = await self._handle_content_delta(chunk, full_content)
            elif chunk_type == "tool_calls_delta":
                tool_calls = self._handle_tool_calls_delta(chunk, tool_calls)
            elif chunk_type == "completion":
                full_content, tool_calls, usage_info, used_model = self._handle_completion(chunk, full_content, tool_calls)
            elif chunk_type == "error":
                self._handle_stream_error(chunk)
        
        return {
            "content": full_content.strip(),
            "tool_calls": tool_calls,
            "usage": usage_info,
            "used_model": used_model,
            "first_token_time": first_token_time
        }
    
    async def _handle_llm_response(self, response_data: Dict[str, Any], 
                                 context: str, process_duration: float) -> LLMResponse:
        """统一的LLM响应处理方法"""
        
        # 提取响应数据
        content = response_data.get("content", "")
        tool_calls = response_data.get("tool_calls", [])
        usage_info = response_data.get("usage")
        used_model = response_data.get("used_model")
        request_model = response_data.get("request_model")
        
        # 记录基本的完成信息
        content_length = len(content)
        tool_call_count = len(tool_calls)
        
        # 构建日志消息
        self.logger.info(f"{context} - 耗时: {process_duration:.2f}ms, 字符数: {content_length}, 工具调用: {'是' if tool_call_count > 0 else '否'} ({tool_call_count}个)，内容：{content}")
        
        return LLMResponse.create(content, tool_calls, usage_info, used_model, request_model)
    
    
    async def _handle_content_delta(self, chunk: Dict[str, Any], full_content: str) -> str:
        """处理内容增量"""
        delta_content = chunk.get("delta", {}).get("content", "")
        if delta_content:
            full_content = chunk.get("full_content", full_content + delta_content)
        return full_content
    
    def _handle_tool_calls_delta(self, chunk: Dict[str, Any], tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """处理工具调用增量"""
        tool_call_deltas = chunk.get("delta", {}).get("tool_calls", [])
        
        for tool_call_delta in tool_call_deltas:
            index = tool_call_delta.get("index", 0)
            
            # 确保tool_calls列表足够长
            while len(tool_calls) <= index:
                tool_calls.append({})
            
            # 更新工具调用信息
            self._update_tool_call_at_index(tool_calls, index, tool_call_delta)
        
        return tool_calls
    
    def _update_tool_call_at_index(self, tool_calls: List[Dict[str, Any]], index: int, delta: Dict[str, Any]) -> None:
        """更新指定索引的工具调用信息"""
        if "id" in delta:
            tool_calls[index]["id"] = delta["id"]
        if "type" in delta:
            tool_calls[index]["type"] = delta["type"]
        if "function" in delta:
            if "function" not in tool_calls[index]:
                tool_calls[index]["function"] = {}
            
            function_delta = delta["function"]
            if "name" in function_delta:
                tool_calls[index]["function"]["name"] = function_delta["name"]
            if "arguments" in function_delta:
                current_args = tool_calls[index]["function"].get("arguments", "")
                tool_calls[index]["function"]["arguments"] = current_args + function_delta["arguments"]
    
    def _handle_completion(self, chunk: Dict[str, Any], full_content: str, tool_calls: List[Dict[str, Any]]) -> tuple:
        """处理完成信息"""
        final_content = chunk.get("content", "")
        final_tool_calls = chunk.get("tool_calls")
        usage_info = chunk.get("usage")
        used_model = chunk.get("used_model")
        
        # 使用最终数据（如果有的话）
        if final_content:
            full_content = final_content
        if final_tool_calls:
            tool_calls = final_tool_calls
        
        return full_content, tool_calls, usage_info, used_model
    
    def _handle_stream_error(self, chunk: Dict[str, Any]) -> None:
        """处理流式错误"""
        error_msg = chunk.get("error", "流式响应处理错误")
        self.logger.error(f"流式响应错误: {error_msg}")
        raise Exception(error_msg)
