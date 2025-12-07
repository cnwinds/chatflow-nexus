#!/usr/bin/env python3
"""
智谱Web搜索服务
基于智谱AI Web Search API实现的网络搜索服务
提供结构化搜索结果、多引擎支持、域名过滤等功能

API文档：https://docs.bigmodel.cn/cn/guide/tools/web-search
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List, Callable
from functools import wraps
from concurrent.futures import ThreadPoolExecutor

try:
    from zai import ZhipuAiClient
    ZAI_AVAILABLE = True
except ImportError:
    ZAI_AVAILABLE = False
    logging.warning("zai-sdk未安装，Web搜索服务将不可用。请运行: pip install zai-sdk")

from src.utcp.utcp import UTCPService

logger = logging.getLogger(__name__)


def handle_search_errors(func: Callable) -> Callable:
    """装饰器：统一错误处理"""
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except Exception as e:
            logger.error(f"{func.__name__} 失败: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "message": f"网络搜索失败: {str(e)}"
            }
    return wrapper


class WebSearchService(UTCPService):
    """智谱Web搜索服务 - 基于智谱AI Web Search API"""
    
    def init(self) -> None:
        """插件初始化方法"""
        try:
            self._validate_dependencies()
            self._load_config()
            self._setup_logging()
            self._initialize_client()
        except Exception as e:
            logger.error(f"智谱Web搜索服务初始化失败: {e}")
            raise
    
    def _validate_dependencies(self) -> None:
        """验证依赖"""
        if not ZAI_AVAILABLE:
            raise ImportError("zai-sdk未安装，请运行: pip install zai-sdk")
    
    def _load_config(self) -> None:
        """加载配置"""
        # 服务配置
        self.service_config = self.config.get("service_config", {})
        self.api_config = self.config.get("api_config", {})
        self.logging_config = self.config.get("logging", {})
        
        # API配置
        self.api_key = self.api_config.get("api_key", "")
        
        # 服务配置
        self.default_search_engine = self.service_config.get("default_search_engine", "search_pro")
        self.default_count = self.service_config.get("default_count", 10)
        self.default_content_size = self.service_config.get("default_content_size", "high")
        self.default_recency_filter = self.service_config.get("default_recency_filter", "noLimit")
        self.timeout = self.service_config.get("timeout", 30)
        
        # 验证必需配置
        if not self.api_key:
            raise ValueError("智谱Web搜索服务需要 api_key 配置")
        
        # 验证搜索引擎类型
        valid_engines = ["search_std", "search_pro", "search_pro_sogou", "search_pro_quark"]
        if self.default_search_engine not in valid_engines:
            logger.warning(f"未知的搜索引擎类型: {self.default_search_engine}，将使用 search_pro")
            self.default_search_engine = "search_pro"
    
    def _setup_logging(self) -> None:
        """设置日志配置"""
        log_level = self.logging_config.get("level", "INFO")
        enable_detailed_logs = self.logging_config.get("enable_detailed_logs", False)
        
        if enable_detailed_logs:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(getattr(logging, log_level, logging.INFO))
    
    def _initialize_client(self) -> None:
        """初始化智谱AI客户端"""
        self.client = ZhipuAiClient(api_key=self.api_key)
        # 初始化线程池执行器，用于执行同步SDK调用
        self.executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="web_search")
        logger.info("智谱Web搜索客户端初始化成功")
    
    @property
    def name(self) -> str:
        """服务名称"""
        return "web_search_service"
    
    @property
    def description(self) -> str:
        """服务描述"""
        return "提供网络搜索服务，基于智谱AI Web Search API，支持结构化搜索结果、多引擎支持、域名过滤等功能"
    
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
        return [
            # 网络搜索工具
            self._create_tool_definition(
                "web_search", "执行网络搜索，获取结构化搜索结果（标题/URL/摘要/网站名/图标等）",
                {
                    "search_query": {
                        "type": "string",
                        "description": "搜索查询词"
                    },
                    "search_engine": {
                        "type": "string",
                        "enum": ["search_std", "search_pro", "search_pro_sogou", "search_pro_quark"],
                        "description": "搜索引擎类型：search_std(基础版,0.01元/次)、search_pro(高级版,0.03元/次)、search_pro_sogou(搜狗,0.05元/次)、search_pro_quark(夸克,0.05元/次)",
                        "default": "search_pro"
                    },
                    "count": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                        "description": "返回结果数量（1-50）",
                        "default": 10
                    },
                    "search_domain_filter": {
                        "type": "string",
                        "description": "域名过滤，只搜索指定域名的内容（如：www.sohu.com）",
                        "default": ""
                    },
                    "search_recency_filter": {
                        "type": "string",
                        "enum": ["noLimit", "day", "week", "month", "year"],
                        "description": "时间范围过滤：noLimit(不限)、day(一天内)、week(一周内)、month(一月内)、year(一年内)",
                        "default": "noLimit"
                    },
                    "content_size": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "网页摘要字数：low(较少)、medium(中等)、high(较多)",
                        "default": "high"
                    }
                },
                ["search_query"]
            )
        ]
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """执行Web搜索服务工具"""
        tool_handlers = {
            "web_search": lambda: self._web_search(arguments)
        }
        
        try:
            if tool_name not in tool_handlers:
                raise ValueError(f"未知的Web搜索工具: {tool_name}")
            
            return await tool_handlers[tool_name]()
        except Exception as e:
            logger.error(f"执行工具 '{tool_name}' 时出错: {e}")
            return {
                "status": "error",
                "error": str(e),
                "message": f"网络搜索操作失败: {str(e)}"
            }
    
    def _web_search_sync(self, request_params: Dict[str, Any]) -> Any:
        """同步执行网络搜索（在线程池中调用）"""
        return self.client.web_search.web_search(**request_params)
    
    @handle_search_errors
    async def _web_search(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """执行网络搜索"""
        search_query = arguments.get("search_query")
        search_engine = arguments.get("search_engine", self.default_search_engine)
        count = arguments.get("count", self.default_count)
        search_domain_filter = arguments.get("search_domain_filter", "")
        search_recency_filter = arguments.get("search_recency_filter", self.default_recency_filter)
        content_size = arguments.get("content_size", self.default_content_size)
        
        if not search_query:
            raise ValueError("搜索查询词不能为空")
        
        # 验证参数
        if count < 1 or count > 50:
            raise ValueError("count参数必须在1-50之间")
        
        valid_engines = ["search_std", "search_pro", "search_pro_sogou", "search_pro_quark"]
        if search_engine not in valid_engines:
            raise ValueError(f"search_engine必须是以下之一: {', '.join(valid_engines)}")
        
        valid_recency = ["noLimit", "day", "week", "month", "year"]
        if search_recency_filter not in valid_recency:
            raise ValueError(f"search_recency_filter必须是以下之一: {', '.join(valid_recency)}")
        
        valid_content_size = ["low", "medium", "high"]
        if content_size not in valid_content_size:
            raise ValueError(f"content_size必须是以下之一: {', '.join(valid_content_size)}")
        
        logger.info(f"执行网络搜索: query={search_query}, engine={search_engine}, count={count}")
        
        # 构建请求参数
        request_params = {
            "search_engine": search_engine,
            "search_query": search_query,
            "count": count,
            "search_recency_filter": search_recency_filter,
            "content_size": content_size
        }
        
        # 如果指定了域名过滤，则添加该参数
        if search_domain_filter:
            request_params["search_domain_filter"] = search_domain_filter
        print("===========================",request_params)
        # 调用智谱AI Web Search API（同步调用包装为异步）
        try:
            # 在线程池中执行同步API调用
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                self.executor,
                self._web_search_sync,
                request_params
            )
            
            # 调试：打印完整API响应
            logger.debug(f"API原始响应类型: {type(response)}")
            logger.debug(f"API原始响应内容: {response}")
            
            # 处理响应结果
            if response:
                # 提取搜索结果
                results = []
                
                # 检查是否是WebSearchResp对象（有search_result属性）
                if hasattr(response, 'search_result'):
                    search_result_list = response.search_result
                    if search_result_list:
                        # 将SearchResultResp对象转换为字典
                        for item in search_result_list:
                            result_dict = {
                                "title": getattr(item, 'title', ''),
                                "url": getattr(item, 'link', ''),
                                "snippet": getattr(item, 'content', ''),
                                "site_name": getattr(item, 'media', ''),
                                "icon": getattr(item, 'icon', ''),
                                "publish_date": getattr(item, 'publish_date', ''),
                                "refer": getattr(item, 'refer', ''),
                                "images": getattr(item, 'images', None)
                            }
                            results.append(result_dict)
                elif isinstance(response, dict):
                    # 如果响应是字典，尝试提取搜索结果
                    if "search_result" in response:
                        results = response["search_result"]
                    elif "results" in response:
                        results = response["results"]
                    elif "data" in response:
                        results = response["data"]
                    else:
                        # 如果响应结构不同，直接使用整个响应
                        results = [response] if response else []
                elif isinstance(response, list):
                    results = response
                else:
                    results = []
                
                return {
                    "status": "success",
                    "query": search_query,
                    "search_engine": search_engine,
                    "results": results,
                    "total_results": len(results),
                    "search_metadata": {
                        "count": count,
                        "domain_filter": search_domain_filter if search_domain_filter else None,
                        "recency_filter": search_recency_filter,
                        "content_size": content_size
                    }
                }
            else:
                raise Exception("API返回空响应")
                
        except Exception as e:
            logger.error(f"调用智谱AI Web Search API失败: {e}", exc_info=True)
            raise Exception(f"网络搜索API调用失败: {str(e)}")
    
    async def close(self) -> None:
        """关闭服务"""
        # 关闭线程池执行器
        if hasattr(self, 'executor') and self.executor:
            self.executor.shutdown(wait=True)
            logger.info("Web搜索服务线程池已关闭")
        logger.info("Web搜索服务已关闭")

