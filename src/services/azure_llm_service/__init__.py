#!/usr/bin/env python3
"""
Azure LLM服务包

基于UTCP协议实现的Azure OpenAI LLM服务，提供统一的LLM调用接口
"""

from .service import AzureLLMService

__all__ = ['AzureLLMService'] 