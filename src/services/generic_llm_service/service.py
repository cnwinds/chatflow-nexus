#!/usr/bin/env python3
"""
通用 LLM 服务
基于 UTCP 协议实现的通用 OpenAI 兼容 LLM 服务
支持所有兼容 OpenAI API 的平台（百炼、讯飞星火、智谱、DeepSeek等）
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List, AsyncGenerator, Callable
from functools import wraps
from openai import AsyncOpenAI
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


class GenericLLMService(UTCPService):
    """
    通用 LLM 服务 - 兼容所有 OpenAI API 的服务
    
    配置示例:
    {
        "api_config": {
            "api_key": "your-api-key",
            "base_url": "https://api.openai.com/v1",
            "organization": "optional-org-id",  # 可选
            "api_version": "v1"  # 可选
        },
        "model_config": {
            "available_models": ["gpt-4", "gpt-3.5-turbo"],
            "model_alias": {
                "primary": "gpt-4",
                "secondary": "gpt-3.5-turbo",
                "fast": "gpt-3.5-turbo"
            },
            "default_model": "primary",
            "token_param_strategy": "auto"  # auto, max_tokens, max_completion_tokens
        },
        "service_config": {
            "max_tokens": 4000,
            "temperature": 0.7,
            "timeout": 60,
            "max_connections": 50,
            "enable_http2": true,
            "retry_attempts": 3,
            "retry_delay": 1.0
        },
        "feature_config": {
            "support_tools": true,
            "support_vision": false,
            "support_function_call": true,
            "estimate_tokens": true  # 是否估算token（当API不返回usage时）
        }
    }
    """
    
    def init(self) -> None:
        """插件初始化方法"""
        # API 配置
        api_config = self.config.get("api_config", {})
        self.api_key = api_config.get("api_key")
        self.base_url = api_config.get("base_url", "https://api.openai.com/v1")
        self.organization = api_config.get("organization")
        self.api_version = api_config.get("api_version")
        
        # 模型配置
        model_config = self.config.get("model_config", {})
        self.available_models = model_config.get("available_models", [])
        self.model_alias = model_config.get("model_alias", {})
        self.default_model = model_config.get("default_model", "primary")
        self.token_param_strategy = model_config.get("token_param_strategy", "auto")
        
        # 服务配置
        service_config = self.config.get("service_config", {})
        self.max_tokens = service_config.get("max_tokens", 4000)
        self.temperature = service_config.get("temperature", 0.7)
        self.timeout = service_config.get("timeout", 60)
        self.max_connections = service_config.get("max_connections", 50)
        self.enable_http2 = service_config.get("enable_http2", True)
        self.retry_attempts = service_config.get("retry_attempts", 3)
        self.retry_delay = service_config.get("retry_delay", 1.0)
        
        # 标准参数的默认值（可在 service_config 中配置）
        self.default_top_p = service_config.get("top_p")
        self.default_n = service_config.get("n")
        self.default_stop = service_config.get("stop")
        self.default_presence_penalty = service_config.get("presence_penalty")
        self.default_frequency_penalty = service_config.get("frequency_penalty")
        
        # 默认扩展参数（从配置文件读取）
        self.default_extra_params = service_config.get("default_extra_params", {})
        
        # 特性配置
        feature_config = self.config.get("feature_config", {})
        self.support_tools = feature_config.get("support_tools", True)
        self.support_vision = feature_config.get("support_vision", False)
        self.support_function_call = feature_config.get("support_function_call", True)
        self.estimate_tokens = feature_config.get("estimate_tokens", True)
        
        # 验证必需配置
        if not self.api_key:
            raise ValueError("通用 LLM 服务需要 api_key 配置")
        if not self.base_url:
            raise ValueError("通用 LLM 服务需要 base_url 配置")
        
        # 初始化异步HTTP客户端
        http_client_kwargs = {
            "timeout": self.timeout,
            "limits": httpx.Limits(max_connections=self.max_connections)
        }
        if self.enable_http2:
            http_client_kwargs["http2"] = True
            
        self.http_client = httpx.AsyncClient(**http_client_kwargs)
        
        # 初始化异步OpenAI客户端
        client_kwargs = {
            "base_url": self.base_url,
            "api_key": self.api_key,
            "http_client": self.http_client
        }
        if self.organization:
            client_kwargs["organization"] = self.organization
            
        self.client = AsyncOpenAI(**client_kwargs)
        
        logger.info(f"通用 LLM 服务初始化完成: base_url={self.base_url}, models={self.available_models}")
    
    async def cleanup(self) -> None:
        """清理资源"""
        if hasattr(self, 'http_client') and self.http_client:
            await self.http_client.aclose()
    
    def _get_token_param_name(self, model_name: str) -> str:
        """
        根据策略和模型名称获取正确的token参数名
        
        策略:
        - auto: 自动检测（默认使用 max_tokens，GPT-4o系列使用 max_completion_tokens）
        - max_tokens: 始终使用 max_tokens
        - max_completion_tokens: 始终使用 max_completion_tokens
        
        Args:
            model_name: 模型名称
            
        Returns:
            参数名称: 'max_tokens' 或 'max_completion_tokens'
        """
        if self.token_param_strategy == "max_completion_tokens":
            return "max_completion_tokens"
        elif self.token_param_strategy == "max_tokens":
            return "max_tokens"
        else:  # auto
            # GPT-4o 系列使用 max_completion_tokens
            if "gpt-4o" in model_name.lower():
                return "max_completion_tokens"
            return "max_tokens"
    
    def _resolve_model_name(self, model_name: str) -> str:
        """
        解析模型名称，支持别名或具体模型名称
        
        Args:
            model_name: 模型名称，可以是别名（如'primary'、'secondary'）或具体模型名称
            
        Returns:
            解析后的具体模型名称
            
        Raises:
            ValueError: 当模型名称无效且没有可用的默认模型时
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
        return "generic_llm_service"
    
    @property
    def description(self) -> str:
        """服务描述"""
        return "通用 OpenAI 兼容 LLM 服务，支持所有兼容 OpenAI API 的平台"
    
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
                "enum": ["system", "user", "assistant", "tool"]
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
            "max_tokens": {
                "type": "integer",
                "description": "最大token数",
                "default": 4000
            },
            "temperature": {
                "type": "number",
                "description": "温度参数（0-2）",
                "default": 0.7
            },
            "top_p": {
                "type": "number",
                "description": "nucleus sampling 参数（0-1）",
                "default": 1.0
            },
            "n": {
                "type": "integer",
                "description": "生成的回复数量",
                "default": 1
            },
            "stop": {
                "type": ["string", "array"],
                "description": "停止序列"
            },
            "presence_penalty": {
                "type": "number",
                "description": "存在惩罚（-2.0 到 2.0）",
                "default": 0
            },
            "frequency_penalty": {
                "type": "number",
                "description": "频率惩罚（-2.0 到 2.0）",
                "default": 0
            },
            "extra_params": {
                "type": "object",
                "description": "扩展参数，支持模型特有的参数（如seed、top_k、repetition_penalty等）。这些参数会直接传递给底层API",
                "additionalProperties": True
            }
        }
        
        # 如果支持工具调用，添加工具参数
        if self.support_tools:
            chat_params["tools"] = {
                "type": "array",
                "description": "可用工具列表（可选）",
                "items": {"type": "object"}
            }
            chat_params["tool_choice"] = {
                "type": ["string", "object"],
                "description": "工具选择策略：'auto'、'none' 或指定工具",
                "default": "auto"
            }
        
        tools = [
            # 聊天完成工具
            self._create_tool_definition(
                "chat_completion", 
                "执行聊天完成，获取LLM回复",
                chat_params, 
                ["messages"]
            ),
            
            # 流式聊天完成工具
            self._create_tool_definition(
                "chat_completion_stream", 
                "执行流式聊天完成，获取LLM流式回复",
                chat_params, 
                ["messages"],
                {
                    "supported": True,
                    "stream_type": "json",
                    "content_type": "application/json"
                }
            ),
            
            # 模型列表工具
            self._create_tool_definition(
                "list_models", 
                "列出所有可用的模型及别名配置",
                {}
            ),
        ]
        
        return tools
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """调用工具"""
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
        model = arguments.get("model", self.default_model)
        
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
            "temperature": arguments.get("temperature", self.temperature),
        }
        
        # 设置 token 限制
        max_tokens = arguments.get("max_tokens", self.max_tokens)
        request_params[token_param_name] = max_tokens
        
        # 添加标准可选参数（如果配置文件中有默认值或调用时指定）
        optional_params = {
            "top_p": self.default_top_p,
            "n": self.default_n,
            "stop": self.default_stop,
            "presence_penalty": self.default_presence_penalty,
            "frequency_penalty": self.default_frequency_penalty
        }
        
        for param, default_value in optional_params.items():
            # 优先使用调用时传入的值，否则使用配置文件默认值
            if param in arguments:
                request_params[param] = arguments[param]
            elif default_value is not None:
                request_params[param] = default_value
        
        # 合并扩展参数：配置文件的默认值 + 调用时传入的值
        # 优先级：调用时传入 > 配置文件默认值
        merged_extra_params = {}
        
        # 先添加配置文件中的默认扩展参数
        if self.default_extra_params:
            merged_extra_params.update(self.default_extra_params)
            logger.debug(f"使用配置文件默认扩展参数: {self.default_extra_params}")
        
        # 再添加调用时传入的扩展参数（会覆盖默认值）
        call_extra_params = arguments.get("extra_params", {})
        if call_extra_params:
            merged_extra_params.update(call_extra_params)
            logger.debug(f"合并调用时扩展参数: {call_extra_params}")
        
        # 将合并后的扩展参数添加到请求中
        if merged_extra_params:
            logger.debug(f"最终扩展参数: {merged_extra_params}")
            request_params.update(merged_extra_params)
        
        # 添加工具参数（如果支持且提供）
        if self.support_tools:
            tools = arguments.get("tools", [])
            if tools:
                request_params["tools"] = tools
                request_params["tool_choice"] = arguments.get("tool_choice", "auto")
        
        logger.debug(f"LLM 请求参数: {request_params}")
        
        # 重试机制
        last_error = None
        for attempt in range(self.retry_attempts):
            try:
                # 调用 OpenAI 兼容接口
                response = await self.client.chat.completions.create(**request_params)
                
                # 处理响应
                result = {
                    "status": "success",
                    "content": response.choices[0].message.content,
                    "used_model": resolved_model,
                    "request_model": model,
                    "finish_reason": response.choices[0].finish_reason
                }
                
                # 处理 usage 信息
                if hasattr(response, 'usage') and response.usage:
                    result["usage"] = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    }
                elif self.estimate_tokens:
                    # 估算 token 数量
                    tools = arguments.get("tools", [])
                    estimated_prompt_tokens = estimate_tokens_from_messages(messages, tools)
                    estimated_completion_tokens = estimate_tokens_from_text(
                        response.choices[0].message.content or ""
                    )
                    
                    result["usage"] = {
                        "prompt_tokens": estimated_prompt_tokens,
                        "completion_tokens": estimated_completion_tokens,
                        "total_tokens": estimated_prompt_tokens + estimated_completion_tokens,
                        "estimated": True
                    }
                
                # 处理工具调用
                if hasattr(response.choices[0].message, 'tool_calls') and response.choices[0].message.tool_calls:
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
                
            except Exception as e:
                last_error = e
                if attempt < self.retry_attempts - 1:
                    logger.warning(f"请求失败 (尝试 {attempt + 1}/{self.retry_attempts}): {e}")
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                else:
                    logger.error(f"请求失败，已达最大重试次数: {e}")
                    raise
        
        raise last_error
    
    @handle_llm_errors
    async def _chat_completion_stream(self, arguments: Dict[str, Any]) -> StreamResponse:
        """执行流式聊天完成"""
        messages = arguments.get("messages", [])
        model = arguments.get("model", self.default_model)
        
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
            "temperature": arguments.get("temperature", self.temperature),
            "stream": True
        }
        
        # 设置 token 限制
        max_tokens = arguments.get("max_tokens", self.max_tokens)
        request_params[token_param_name] = max_tokens
        
        # 添加标准可选参数（如果配置文件中有默认值或调用时指定）
        optional_params = {
            "top_p": self.default_top_p,
            "n": self.default_n,
            "stop": self.default_stop,
            "presence_penalty": self.default_presence_penalty,
            "frequency_penalty": self.default_frequency_penalty
        }
        
        for param, default_value in optional_params.items():
            # 优先使用调用时传入的值，否则使用配置文件默认值
            if param in arguments:
                request_params[param] = arguments[param]
            elif default_value is not None:
                request_params[param] = default_value
        
        # 合并扩展参数：配置文件的默认值 + 调用时传入的值
        # 优先级：调用时传入 > 配置文件默认值
        merged_extra_params = {}
        
        # 先添加配置文件中的默认扩展参数
        if self.default_extra_params:
            merged_extra_params.update(self.default_extra_params)
            logger.debug(f"使用配置文件默认扩展参数: {self.default_extra_params}")
        
        # 再添加调用时传入的扩展参数（会覆盖默认值）
        call_extra_params = arguments.get("extra_params", {})
        if call_extra_params:
            merged_extra_params.update(call_extra_params)
            logger.debug(f"合并调用时扩展参数: {call_extra_params}")
        
        # 将合并后的扩展参数添加到请求中
        if merged_extra_params:
            logger.debug(f"最终扩展参数: {merged_extra_params}")
            request_params.update(merged_extra_params)
        
        # 添加工具参数（如果支持且提供）
        tools = []
        if self.support_tools:
            tools = arguments.get("tools", [])
            if tools:
                request_params["tools"] = tools
                request_params["tool_choice"] = arguments.get("tool_choice", "auto")
        
        logger.debug(f"LLM 流式请求参数: {request_params}")
        
        # 调用流式接口
        llm_stream = await self.client.chat.completions.create(**request_params)
        
        # 使用通用工具函数处理流式响应
        async def stream_generator():
            async for chunk_data in process_openai_stream(
                llm_stream,
                resolved_model,
                model,
                messages,
                tools,
                estimate_tokens_func=estimate_tokens_from_messages if self.estimate_tokens else None
            ):
                yield chunk_data
        
        # 创建流式响应元数据
        metadata = StreamMetadata(
            encoding="utf-8",
            custom_headers={
                "X-Model": resolved_model,
                "X-Original-Model": model,
                "X-Service": "generic_llm_service",
                "X-Base-URL": self.base_url
            }
        )
        
        # 返回 LocalStreamResponse
        return LocalStreamResponse(
            stream_generator(),
            StreamType.JSON,
            "application/json",
            metadata
        )
    
    def _list_models(self) -> Dict[str, Any]:
        """列出所有可用的模型"""
        return {
            "status": "success",
            "available_models": self.available_models,
            "model_alias": self.model_alias,
            "default_model": self.default_model,
            "default_resolved": self.model_alias.get(self.default_model, "unknown"),
            "token_param_strategy": self.token_param_strategy
        }
    