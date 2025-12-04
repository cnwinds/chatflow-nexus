#!/usr/bin/env python3
"""
Azure LLM服务
基于UTCP协议实现的Azure OpenAI LLM服务，提供统一的LLM调用接口
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List, AsyncGenerator, Callable
from functools import wraps
from openai import AsyncAzureOpenAI
from openai.types.chat import ChatCompletionChunk
import json
import httpx

from src.utcp.utcp import UTCPService
from src.utcp.streaming import StreamResponse, LocalStreamResponse, StreamType, StreamMetadata
from src.common.utils.llm_stream_utils import (
    process_openai_stream,
    estimate_tokens_from_messages,
    estimate_tokens_from_text
)

# 配置日志
logger = logging.getLogger(__name__)


def handle_llm_errors(func: Callable) -> Callable:
    """装饰器：统一错误处理"""
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except Exception as e:
            logger.error(f"{func.__name__} 失败: {e}")
            return {
                "status": "error",
                "error": "Internal error",
                "message": f"工具执行出错: {str(e)}"
            }
    return wrapper


class AzureLLMService(UTCPService):
    """Azure LLM服务 - 统一的LLM调用接口"""
    
    # 插件不允许写__init__方法，只能通过init方法进行初始化
    
    def init(self) -> None:
        """插件初始化方法"""
        # 初始化配置相关属性
        api_config = self.config.get("api_config", {})
        service_config = self.config.get("service_config", {})
        model_config = self.config.get("model_config", {})
        
        # Azure OpenAI配置
        self.api_key = api_config.get("api_key")
        self.endpoint = api_config.get("endpoint")
        self.api_version = api_config.get("api_version", "2024-02-15-preview")
        
        # 模型配置
        self.available_models = model_config.get("available_models", [])
        self.model_alias = model_config.get("model_alias", {})
        self.default_model = model_config.get("default_model", "primary")
        
        # 模型参数
        self.max_tokens = service_config.get("max_tokens", 4000)
        self.temperature = service_config.get("temperature", 0.7)
        self.timeout = service_config.get("timeout", 60)
        
        # 验证必需配置
        if not all([self.api_key, self.endpoint]):
            raise ValueError("Azure LLM服务需要 api_key 和 endpoint 配置")
        
        # 初始化异步HTTP客户端
        self.http_client = httpx.AsyncClient(
            http2=True,
            timeout=30.0,
            limits=httpx.Limits(max_connections=50)
        )
        
        # 初始化异步Azure OpenAI客户端，使用HTTP2
        self.client = AsyncAzureOpenAI(
            api_version=self.api_version,
            azure_endpoint=self.endpoint,
            api_key=self.api_key,
            http_client=self.http_client
        )
    
    async def cleanup(self) -> None:
        """清理资源"""
        if hasattr(self, 'http_client') and self.http_client:
            await self.http_client.aclose()
        
    def _get_token_param_name(self, model_name: str) -> str:
        """根据模型名称获取正确的token参数名
        
        Args:
            model_name: 模型名称
            
        Returns:
            参数名称: 'max_tokens' 或 'max_completion_tokens'
        """
        # GPT-5模型使用max_completion_tokens
        if model_name.startswith("gpt-5"):
            return "max_completion_tokens"
        else:
            return "max_tokens"
    
    def _resolve_model_name(self, model_name: str) -> str:
        """解析模型名称，支持别名或具体模型名称
        
        Args:
            model_name: 模型名称，可以是别名（如'primary'、'secondary'）或具体模型名称
            
        Returns:
            解析后的具体模型名称
            
        Raises:
            ValueError: 当模型名称无效时
        """
        # 如果是别名，获取具体模型名称
        if model_name in self.model_alias:
            resolved_model = self.model_alias[model_name]
            logger.debug(f"模型别名: {model_name} -> {resolved_model}")
            return resolved_model
        
        # 如果是具体模型名称，验证是否在可用模型列表中
        if model_name in self.available_models:
            logger.debug(f"使用具体模型: {model_name}")
            return model_name
        
        # 如果都不匹配，使用默认模型
        if self.default_model in self.model_alias:
            default_resolved = self.model_alias[self.default_model]
            logger.warning(f"无效的模型名称 '{model_name}'，使用默认模型: {default_resolved}")
            return default_resolved
        
        # 如果连默认模型都没有，使用第一个可用模型
        if self.available_models:
            logger.warning(f"无效的模型名称 '{model_name}'，使用第一个可用模型: {self.available_models[0]}")
            return self.available_models[0]
        
        # 最后的后备方案
        raise ValueError(f"无效的模型名称 '{model_name}'，且没有可用的默认模型")
    
    @property
    def name(self) -> str:
        """服务名称"""
        return "azure_llm"
    
    @property
    def description(self) -> str:
        """服务描述"""
        return "Azure OpenAI LLM服务，提供统一的LLM调用接口"
    
    def _create_tool_definition(self, name: str, description: str, 
                               properties: Dict[str, Any], required: List[str] = None,
                               streaming: Dict[str, Any] = None) -> Dict[str, Any]:
        """创建工具定义的辅助方法"""
        tool_def = {
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
        
        if streaming:
            tool_def["function"]["streaming"] = streaming
            
        return tool_def
    
    async def get_tools(self) -> List[Dict[str, Any]]:
        """返回可用工具列表"""
        # 消息参数定义
        message_properties = {
            "role": {
                "type": "string",
                "enum": ["system", "user", "assistant"]
            },
            "content": {
                "type": "string",
                "description": "消息内容"
            }
        }
        
        # 聊天完成参数
        chat_params = {
            "messages": {
                "type": "array",
                "description": "聊天消息列表",
                "items": {
                    "type": "object",
                    "properties": message_properties,
                    "required": ["role", "content"]
                }
            },
            "model": {
                "type": "string",
                "description": "模型名称，支持别名（如'primary'、'secondary'、'fast'等）或具体模型名称",
                "default": "primary"
            },
            "tools": {
                "type": "array",
                "description": "可用工具列表（可选）",
                "items": {
                    "type": "object"
                }
            },
            "tool_choice": {
                "type": "string",
                "enum": ["auto", "none"],
                "description": "工具选择策略",
                "default": "auto"
            },
            "max_tokens": {
                "type": "integer",
                "description": "最大token数",
                "default": 4000
            },
            "temperature": {
                "type": "number",
                "description": "温度参数",
                "default": 0.7
            }
        }
        
        return [
            # 聊天完成工具
            self._create_tool_definition(
                "chat_completion", "执行聊天完成，获取LLM回复",
                chat_params, ["messages"]
            ),
            
            # 流式聊天完成工具
            self._create_tool_definition(
                "chat_completion_stream", "执行流式聊天完成，获取LLM流式回复",
                chat_params, ["messages"],
                {
                    "supported": True,
                    "stream_type": "json",
                    "content_type": "application/json"
                }
            ),
            
            # 模型列表工具
            self._create_tool_definition(
                "list_models", "列出所有可用的模型",
                {}
            )
        ]
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """调用工具"""
        # 工具映射表
        tool_handlers = {
            "chat_completion": lambda: self._chat_completion(arguments),
            "chat_completion_stream": lambda: self._chat_completion_stream(arguments),
            "list_models": lambda: self._list_models(),
        }
        
        try:
            if tool_name not in tool_handlers:
                raise ValueError(f"未知工具: {tool_name}")
            
            return await tool_handlers[tool_name]()
        except Exception as e:
            logger.error(f"调用工具 '{tool_name}' 时出错: {e}")
            return {
                "status": "error",
                "error": "Internal error",
                "message": f"工具执行出错: {str(e)}"
            }
    
    async def call_tool_stream(self, tool_name: str, arguments: Dict[str, Any]) -> StreamResponse:
        """调用流式工具"""
        try:
            if tool_name == "chat_completion_stream":
                return await self._chat_completion_stream(arguments)
            else:
                raise ValueError(f"工具 '{tool_name}' 不支持流式调用")
        except Exception as e:
            logger.error(f"调用流式工具 '{tool_name}' 时出错: {e}")
            raise
    
    def supports_streaming(self, tool_name: str) -> bool:
        """检查工具是否支持流式调用"""
        return tool_name == "chat_completion_stream"
    
    @handle_llm_errors
    async def _chat_completion(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """执行聊天完成"""
        messages = arguments.get("messages", [])
        model = arguments.get("model", "primary")
        tools = arguments.get("tools", [])
        tool_choice = arguments.get("tool_choice", "auto")
        max_tokens = arguments.get("max_tokens", self.max_tokens)
        temperature = arguments.get("temperature", self.temperature)
        
        if not messages:
            return {
                "status": "error",
                "error": "Missing messages",
                "message": "消息列表不能为空"
            }
        
        # 解析模型名称
        resolved_model = self._resolve_model_name(model)
        
        # 获取正确的token参数名
        token_param_name = self._get_token_param_name(resolved_model)
        logger.debug(f"使用模型: {resolved_model}, token参数: {token_param_name}")
        
        # 构建请求参数
        request_params = {
            "model": resolved_model,
            "messages": messages,
            "temperature": temperature,
        }
        
        # 根据模型类型使用正确的token参数
        # request_params[token_param_name] = max_tokens
        
        # 添加工具参数（如果提供）
        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = tool_choice
        
        logger.debug(f"Azure OpenAI请求参数: {request_params}")
        
        # 调用Azure OpenAI异步接口
        response = await self.client.chat.completions.create(**request_params)
        
        # 处理响应
        result = {
            "status": "success",
            "content": response.choices[0].message.content,
            "used_model": resolved_model,
            "request_model": model
        }
        
        # 处理usage信息
        if hasattr(response, 'usage') and response.usage:
            result["usage"] = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        else:
            # 如果没有usage信息，基于字符数估算token数量
            estimated_prompt_tokens = estimate_tokens_from_messages(messages, tools)
            estimated_completion_tokens = estimate_tokens_from_text(response.choices[0].message.content or "")
            
            result["usage"] = {
                "prompt_tokens": estimated_prompt_tokens,
                "completion_tokens": estimated_completion_tokens,
                "total_tokens": estimated_prompt_tokens + estimated_completion_tokens
            }
            
        # 处理工具调用
        if response.choices[0].message.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "type": tool_call.type,
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments
                    }
                }
                for tool_call in response.choices[0].message.tool_calls
            ]
        
        return result
    
    @handle_llm_errors
    async def _chat_completion_stream(self, arguments: Dict[str, Any]) -> StreamResponse:
        """执行流式聊天完成，返回标准StreamResponse"""
        messages = arguments.get("messages", [])
        model = arguments.get("model", "primary")
        tools = arguments.get("tools", [])
        tool_choice = arguments.get("tool_choice", "auto")
        max_tokens = arguments.get("max_tokens", self.max_tokens)
        temperature = arguments.get("temperature", self.temperature)
        
        if not messages:
            raise ValueError("消息列表不能为空")
        
        # 解析模型名称
        resolved_model = self._resolve_model_name(model)
        
        # 获取正确的token参数名
        token_param_name = self._get_token_param_name(resolved_model)
        logger.debug(f"流式请求使用模型: {resolved_model}, token参数: {token_param_name}")
        
        # 构建请求参数
        request_params = {
            "model": resolved_model,
            "messages": messages,
            "temperature": temperature,
            "stream": True
        }
        
        # 根据模型类型使用正确的token参数
        # request_params[token_param_name] = max_tokens
        
        # 添加工具参数（如果提供）
        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = tool_choice
        
        logger.debug(f"Azure OpenAI流式请求参数: {request_params}")
        
        # 调用Azure OpenAI流式接口
        azure_stream = await self.client.chat.completions.create(**request_params)
        
        # 使用通用工具函数处理流式响应（使用默认的 token 估算函数）
        async def azure_stream_generator():
            async for chunk_data in process_openai_stream(
                azure_stream,
                resolved_model,
                model,
                messages,
                tools,
                estimate_tokens_func=None  # 使用默认的估算函数
            ):
                yield chunk_data
        
        # 创建流式响应元数据
        metadata = StreamMetadata(
            encoding="utf-8",
            custom_headers={
                "X-Model": resolved_model,
                "X-Original-Model": model,
                "X-Service": "azure_llm_service"
            }
        )
        
        # 返回LocalStreamResponse
        return LocalStreamResponse(
            azure_stream_generator(),
            StreamType.JSON,
            "application/json",
            metadata
        )
    
    async def _list_models(self) -> Dict[str, Any]:
        """列出所有可用的模型"""
        return {
            "status": "success",
            "available_models": self.available_models,
            "model_alias": self.model_alias,
            "default_model": self.default_model,
            "default_resolved": self.model_alias.get(self.default_model, "unknown")
        }
    