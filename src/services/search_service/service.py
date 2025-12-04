#!/usr/bin/env python3
"""
UTCP搜索服务
基于UTCP协议实现的搜索服务，使用 Brave Search API
提供网络搜索、图片搜索等功能
api申请地址：https://api-dashboard.search.brave.com/app/keys
"""

import logging
import aiohttp
import asyncio
from typing import Dict, Any, Optional, List, Callable
from functools import wraps
from src.utcp.utcp import UTCPService

# 配置日志
logger = logging.getLogger(__name__)


def handle_search_errors(func: Callable) -> Callable:
    """装饰器：统一错误处理"""
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except Exception as e:
            logger.error(f"{func.__name__} 失败: {e}")
            return {
                "status": "error",
                "error": str(e),
                "message": f"搜索操作失败: {str(e)}"
            }
    return wrapper


class SearchService(UTCPService):
    """搜索服务 - 使用 Brave Search API"""
    
    # 插件不允许写__init__方法，只能通过init方法进行初始化
    
    def init(self) -> None:
        """插件初始化方法"""
        # 初始化配置相关属性
        self.base_url = self.config.get("base_url", "https://api.search.brave.com/res/v1")
        self.api_key = self.config.get("api_key")
        
        if not self.api_key:
            raise ValueError("Brave Search API 需要 api_key 配置")
        
        self.timeout = self.config.get("timeout", 30)
        self.default_country = self.config.get("default_country", "CN")
        self.default_language = self.config.get("default_language", "zh")
        
        self.session = None
    
    @property
    def name(self) -> str:
        """服务名称"""
        return "search_service"
    
    @property
    def description(self) -> str:
        """服务描述"""
        return "提供网络搜索、图片搜索等服务，基于 Brave Search API"
    
    def _create_tool_definition(self, name: str, description: str, 
                               properties: Dict[str, Any], required: List[str] = None) -> Dict[str, Any]:
        """创建工具定义的辅助方法"""
        return {
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
    
    async def get_tools(self) -> List[Dict[str, Any]]:
        """返回可用工具列表"""
        # 通用搜索参数
        common_params = {
            "count": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20,
                "description": "返回结果数量（1-20）",
                "default": 10
            },
            "country": {
                "type": "string",
                "description": "搜索国家代码（如CN、US等）",
                "default": "CN"
            },
            "language": {
                "type": "string",
                "description": "搜索语言代码（如zh、en等）",
                "default": "zh"
            },
            "safesearch": {
                "type": "string",
                "enum": ["off", "moderate", "strict"],
                "description": "安全搜索级别",
                "default": "moderate"
            }
        }
        
        return [
            # 网络搜索工具
            self._create_tool_definition(
                "web_search", "执行网络搜索，获取搜索结果",
                {
                    "query": {
                        "type": "string",
                        "description": "搜索查询词"
                    },
                    **common_params
                },
                ["query"]
            ),
            
            # 图片搜索工具
            self._create_tool_definition(
                "image_search", "执行图片搜索，获取图片搜索结果",
                {
                    "query": {
                        "type": "string",
                        "description": "图片搜索查询词"
                    },
                    **common_params
                },
                ["query"]
            ),
            
            # 新闻搜索工具
            self._create_tool_definition(
                "news_search", "执行新闻搜索，获取新闻搜索结果",
                {
                    "query": {
                        "type": "string",
                        "description": "新闻搜索查询词"
                    },
                    **common_params
                },
                ["query"]
            ),
        ]
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """执行搜索服务工具"""
        # 工具映射表
        tool_handlers = {
            "web_search": lambda: self._web_search(arguments),
            "image_search": lambda: self._image_search(arguments),
            "news_search": lambda: self._news_search(arguments),
        }
        
        try:
            if tool_name not in tool_handlers:
                raise ValueError(f"未知的搜索工具: {tool_name}")
            
            return await tool_handlers[tool_name]()
        except Exception as e:
            logger.error(f"执行工具 '{tool_name}' 时出错: {e}")
            return {
                "status": "error",
                "error": str(e),
                "message": f"搜索操作失败: {str(e)}"
            }
    
    async def _ensure_session(self) -> None:
        """确保HTTP会话已创建"""
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self.session = aiohttp.ClientSession(timeout=timeout)
    
    async def _make_request(self, endpoint: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """发起HTTP请求的通用方法"""
        await self._ensure_session()
        
        if self.session is None:
            logger.error("HTTP会话未创建")
            return None
        
        url = f"{self.base_url}/{endpoint}"
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key
        }
        
        try:
            async with self.session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"HTTP请求失败: {response.status} - {await response.text()}")
                    return None
        except Exception as e:
            logger.error(f"HTTP请求异常: {e}")
            return None
    
    @handle_search_errors
    async def _web_search(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """执行网络搜索"""
        query = arguments.get("query")
        count = arguments.get("count", 10)
        country = arguments.get("country", self.default_country)
        language = arguments.get("language", self.default_language)
        safesearch = arguments.get("safesearch", "moderate")
        
        if not query:
            raise ValueError("搜索查询词不能为空")
        
        params = {
            "q": query,
            "count": count,
            "country": country,
            "lang": language,
            "safesearch": safesearch
        }
        
        result = await self._make_request("web/search", params)
        
        if result:
            return {
                "status": "success",
                "query": query,
                "results": result.get("web", {}).get("results", []),
                "total_results": result.get("web", {}).get("total", 0),
                "search_metadata": {
                    "country": country,
                    "language": language,
                    "safesearch": safesearch
                }
            }
        else:
            raise Exception("网络搜索请求失败")
    
    @handle_search_errors
    async def _image_search(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """执行图片搜索"""
        query = arguments.get("query")
        count = arguments.get("count", 10)
        country = arguments.get("country", self.default_country)
        language = arguments.get("language", self.default_language)
        safesearch = arguments.get("safesearch", "moderate")
        
        if not query:
            raise ValueError("图片搜索查询词不能为空")
        
        params = {
            "q": query,
            "count": count,
            "country": country,
            "lang": language,
            "safesearch": safesearch
        }
        
        result = await self._make_request("images/search", params)
        
        if result:
            return {
                "status": "success",
                "query": query,
                "results": result.get("images", []),
                "total_results": len(result.get("images", [])),
                "search_metadata": {
                    "country": country,
                    "language": language,
                    "safesearch": safesearch
                }
            }
        else:
            raise Exception("图片搜索请求失败")
    
    @handle_search_errors
    async def _news_search(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """执行新闻搜索"""
        query = arguments.get("query")
        count = arguments.get("count", 10)
        country = arguments.get("country", self.default_country)
        language = arguments.get("language", self.default_language)
        safesearch = arguments.get("safesearch", "moderate")
        
        if not query:
            raise ValueError("新闻搜索查询词不能为空")
        
        params = {
            "q": query,
            "count": count,
            "country": country,
            "lang": language,
            "safesearch": safesearch
        }
        
        result = await self._make_request("news/search", params)
        
        if result:
            return {
                "status": "success",
                "query": query,
                "results": result.get("news", []),
                "total_results": len(result.get("news", [])),
                "search_metadata": {
                    "country": country,
                    "language": language,
                    "safesearch": safesearch
                }
            }
        else:
            raise Exception("新闻搜索请求失败")
    
    async def close(self) -> None:
        """关闭服务"""
        if self.session:
            await self.session.close()
            self.session = None
    
    def __del__(self):
        """析构函数"""
        try:
            # 检查session属性是否存在
            if hasattr(self, 'session') and self.session and not self.session.closed:
                asyncio.create_task(self.session.close())
        except Exception as e:
            # 析构函数中的异常不应该被抛出，只记录日志
            logger.debug(f"SearchService析构时关闭session失败: {e}") 