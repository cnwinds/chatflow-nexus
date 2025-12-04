"""
UTCP (通用工具调用协议) 基础类和接口

这个模块定义了UTCP系统的核心抽象类和数据结构。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union, Callable, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import importlib
import importlib.util
import os
import logging
import inspect
import json
import aiohttp
from pathlib import Path

# 使用新的核心组件
from ..common import ConfigManager, LoggingManager
from ..common.exceptions import ConfigurationError, PathError, LoggingError
from ..common.config import get_config_manager
from ..common.logging import get_logging_manager
# 导入配置验证工具

from .streaming import StreamResponse
from typing import ForwardRef


logger = logging.getLogger(__name__)


class ServiceType(Enum):
    """服务类型枚举"""
    INPROCESS = "inprocess"  # 进程内集成
    HTTP = "http"           # HTTP远程调用


@dataclass
class UTCPServiceConfig:
    """UTCP服务配置数据类"""
    name: str
    type: ServiceType = ServiceType.INPROCESS
    tags: List[str] = field(default_factory=list)
    description: str = ""
    
    # 进程内服务配置
    module_path: Optional[str] = None
    class_name: Optional[str] = None
    
    # HTTP服务配置
    base_url: Optional[str] = None
    timeout: int = 30
    auto_start: bool = False
    start_command: Optional[str] = None
    start_args: Optional[List[str]] = field(default_factory=list)
    working_directory: Optional[str] = None
    health_check_url: Optional[str] = None
    
    # 通用配置
    config: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """配置验证"""
        # 处理字符串类型转换
        if isinstance(self.type, str):
            self.type = ServiceType(self.type)
        
        # 验证配置
        if self.type == ServiceType.INPROCESS:
            if not self.module_path or not self.class_name:
                raise ValueError(f"进程内服务 {self.name} 需要 module_path 和 class_name")
        elif self.type == ServiceType.HTTP:
            if not self.base_url:
                raise ValueError(f"HTTP服务 {self.name} 需要 base_url")
            # 确保base_url不为None
            if self.base_url is None:
                raise ValueError(f"HTTP服务 {self.name} 的 base_url 不能为 None")
            
            # 设置默认的健康检查URL
            if not self.health_check_url:
                self.health_check_url = f"{self.base_url.rstrip('/')}/health"


class ServiceValidationError(Exception):
    """服务验证错误"""
    pass


class ServiceLoadError(Exception):
    """服务加载错误"""
    pass


class ServiceProxy:
    """UTCP服务代理，处理不同的服务类型和加载策略"""
    
    def __init__(self, config: UTCPServiceConfig, manager: 'UTCPManager'):
        self.config = config
        self.manager = manager
        self._service: Optional['UTCPService'] = None
        self._loaded = False
        self._load_error: Optional[Exception] = None
        
    @property
    def name(self) -> str:
        return self.config.name
        
    @property
    def description(self) -> str:
        return self.config.description or f"服务: {self.config.name}"
        
    async def _load_service(self) -> 'UTCPService':
        """加载实际的服务实现"""
        if self._loaded:
            if self._load_error:
                raise self._load_error
            if self._service is None:
                raise ServiceLoadError(f"服务 {self.config.name} 加载失败")
            return self._service
            
        try:
            start_time = asyncio.get_event_loop().time()
            
            if self.config.type == ServiceType.HTTP:
                self._service = await self._create_http_service()
            else:
                self._service = await self._create_inprocess_service()
                
            self._loaded = True
            if self._service is None:
                raise ServiceLoadError(f"服务 {self.config.name} 创建失败")
            
            end_time = asyncio.get_event_loop().time()
            logger.info(f"服务 {self.config.name} 创建完成，耗时 {end_time - start_time:.3f} 秒")
            return self._service
            
        except Exception as e:
            self._load_error = e
            self._loaded = True
            logger.error(f"加载服务 {self.config.name} 失败: {e}")
            raise
            
    async def _create_http_service(self) -> 'UTCPHttpService':
        """创建HTTP服务实例"""
        if self.config.base_url is None:
            raise ServiceLoadError(f"HTTP服务 {self.config.name} 的 base_url 不能为 None")
        
        http_service = UTCPHttpService(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            config=self.config.config,
            service_name=self.config.name
        )
        # 异步获取工具列表
        await http_service.fetch_tools_async()

        return http_service
        
    async def _create_inprocess_service(self) -> 'UTCPService':
        """创建进程内服务实例"""
        # 智能检测模块路径
        module_path = self._resolve_module_path(self.config.module_path)
        
        # 动态导入模块
        spec = importlib.util.spec_from_file_location(
            self.config.name, module_path
        )
        if spec is None or spec.loader is None:
            raise ServiceLoadError(f"无法加载模块规范: {module_path}")
            
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # 获取服务类
        if self.config.class_name is None:
            raise ServiceLoadError(f"服务 {self.config.name} 的 class_name 不能为 None")
            
        if not hasattr(module, self.config.class_name):
            raise ServiceLoadError(
                f"模块 {module_path} 中未找到类 {self.config.class_name}"
            )
            
        service_class = getattr(module, self.config.class_name)
        
        # 验证服务类
        self.manager._validate_service_class(service_class)
        
        # 实例化服务并传递配置
        service_instance = self.manager._instantiate_service(service_class, self.config)
        
        # 验证服务实例
        await self.manager._validate_service_instance(service_instance)
        
        return service_instance
    
    def _resolve_module_path(self, module_path: str) -> str:
        """智能解析模块路径，支持新旧两种格式
        
        Args:
            module_path: 原始模块路径，如 "services/calculator_service"
            
        Returns:
            解析后的实际文件路径
        """
        from pathlib import Path
        
        # 如果已经是完整路径，直接返回
        if module_path.endswith('.py'):
            return module_path
        
        # 构建基础路径
        base_path = Path(__file__).parent.parent / module_path
        
        # 尝试新格式：{service_name}/service.py
        new_format_path = base_path / "service.py"
        if new_format_path.exists():
            logger.debug(f"使用路径: {new_format_path}")
            return str(new_format_path)
        
        # 尝试旧格式：{service_name}.py
        old_format_path = base_path.with_suffix('.py')
        if old_format_path.exists():
            logger.debug(f"使用文件: {old_format_path}")
            return str(old_format_path)
        
        # 如果都不存在，抛出错误
        raise ServiceLoadError(
            f"无法找到服务文件，尝试了以下路径:\n"
            f"  新格式: {new_format_path}\n"
            f"  旧格式: {old_format_path}\n"
            f"  原始路径: {module_path}"
        )
        
    async def get_tools(self) -> List[Dict[str, Any]]:
        """获取服务的工具列表"""
        try:
            service = await self._load_service()
            return await service.get_tools()
        except Exception as e:
            logger.error(f"获取服务 {self.config.name} 的工具失败: {e}")
            return []
            
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """调用服务上的工具"""
        service = await self._load_service()
        return await service.call_tool(tool_name, arguments)
        
    async def call_tool_stream(self, tool_name: str, arguments: Dict[str, Any]) -> 'StreamResponse':
        """调用服务上的流式工具"""
        service = await self._load_service()
        return await service.call_tool_stream(tool_name, arguments)
        
    def supports_streaming(self, tool_name: str) -> bool:
        """检查工具是否支持流式调用"""
        try:
            # 如果服务已加载，直接检查
            if self._service:
                return self._service.supports_streaming(tool_name)
            # 否则通过工具定义检查
            tools = asyncio.create_task(self.get_tools()).result() if hasattr(asyncio, 'current_task') else []
            for tool in tools:
                if tool.get("function", {}).get("name") == tool_name:
                    if is_streaming_supported and is_streaming_supported(tool):
                        return True
            return False
        except:
            return False
        
    def is_loaded(self) -> bool:
        """检查服务是否已加载"""
        return self._loaded and self._service is not None
        
    def get_load_error(self) -> Optional[Exception]:
        """获取加载错误（如果有）"""
        return self._load_error

class UTCPService(ABC):
    """所有UTCP服务的抽象基类"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None, config_manager=None, logger=None):
        """初始化UTCP服务
        
        Args:
            config: 服务配置字典
            config_manager: 配置管理器（可选）
            logger: 日志对象（可选）
        """
        self.config = config or {}
        self.config_manager = config_manager
        self.logger = logger or logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def init(self) -> None:
        """插件初始化抽象方法"""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """服务名称"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """服务描述"""
        pass
    
    @abstractmethod
    async def get_tools(self) -> List[Dict[str, Any]]:
        """返回OpenAI格式的可用工具列表
        
        Returns:
            工具定义列表，每个工具都是OpenAI函数调用格式的字典
        """
        pass
    
    @abstractmethod
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """使用给定参数执行工具
        
        Args:
            tool_name: 工具名称（仅工具名，不包含服务前缀）
            arguments: 工具参数字典
            
        Returns:
            工具执行结果
            
        Raises:
            ValueError: 当工具不存在或参数无效时
        """
        pass
    
    async def call_tool_stream(self, tool_name: str, arguments: Dict[str, Any]) -> 'StreamResponse':
        """调用流式工具（可选实现）
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            StreamResponse: 流式响应对象
            
        Raises:
            NotImplementedError: 当服务不支持流式调用时
            ValueError: 当工具不支持流式调用时
        """
        raise NotImplementedError(f"服务 {self.name} 不支持流式调用")
    
    def supports_streaming(self, tool_name: str) -> bool:
        """检查工具是否支持流式调用
        
        Args:
            tool_name: 工具名称
            
        Returns:
            bool: 是否支持流式调用
        """
        # 默认实现：检查工具定义中的流式支持信息
        try:
            tools = asyncio.create_task(self.get_tools()).result() if hasattr(asyncio, 'current_task') else []
            for tool in tools:
                if tool.get("function", {}).get("name") == tool_name:
                    if is_streaming_supported and is_streaming_supported(tool):
                        return True
            return False
        except:
            return False


class UTCPHttpService(UTCPService):
    """HTTP远程服务的基类，用于未来的HTTP远程服务调用"""
    
    def __init__(self, base_url: str, timeout: int = 30, config: Optional[Dict[str, Any]] = None, service_name: Optional[str] = None):
        """初始化HTTP服务
        
        Args:
            base_url: 远程服务的基础URL
            timeout: 请求超时时间（秒）
            config: 额外的配置参数
            service_name: 服务名称，如果提供则优先使用
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.config = config or {}
        self.session: Optional[aiohttp.ClientSession] = None
        self._tools_cache: Optional[List[Dict[str, Any]]] = None
        self._service_info: Optional[Dict[str, str]] = None
        self._configured_name = service_name  # 配置中指定的服务名称
    
    async def _ensure_session(self) -> None:
        """确保HTTP会话已创建"""
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self.session = aiohttp.ClientSession(timeout=timeout)
    
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """发起HTTP请求的通用方法
        
        Args:
            method: HTTP方法（GET, POST等）
            endpoint: API端点
            **kwargs: 传递给aiohttp的额外参数
            
        Returns:
            响应的JSON数据
            
        Raises:
            Exception: 当请求失败时
        """
        await self._ensure_session()
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        if self.session is None:
            raise Exception("HTTP会话未初始化")
            
        try:
            async with self.session.request(method, url, **kwargs) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(f"HTTP请求失败: {response.status} - {error_text}")
        except aiohttp.ClientError as e:
            raise Exception(f"HTTP客户端错误: {e}")
    
    @property
    def name(self) -> str:
        """服务名称，优先使用配置中的名称，然后从远程服务获取或使用默认值"""
        # 优先使用配置中指定的服务名称
        if self._configured_name:
            return self._configured_name
        
        if self._service_info is None:
            # 如果还没有获取服务信息，返回基于URL的默认名称
            return f"http_service_{self.base_url.split('/')[-1]}"
        return self._service_info.get("name", "unknown_http_service")
    
    @property
    def description(self) -> str:
        """服务描述，从远程服务获取或使用默认值"""
        if self._service_info is None:
            return f"HTTP远程服务: {self.base_url}"
        return self._service_info.get("description", f"HTTP远程服务: {self.base_url}")
    
    async def _fetch_service_info(self) -> None:
        """从远程服务获取服务信息"""
        try:
            info = await self._make_request("GET", "/info")
            self._service_info = info
        except Exception as e:
            logger.warning(f"无法获取远程服务信息: {e}")
            self._service_info = {
                "name": f"http_service_{self.base_url.split('/')[-1]}",
                "description": f"HTTP远程服务: {self.base_url}"
            }
    
    async def get_tools(self) -> List[Dict[str, Any]]:
        """获取远程服务的工具列表
        
        Returns:
            工具定义列表
        """
        if self._tools_cache is not None:
            return self._tools_cache
        
        # 如果工具缓存为空，说明服务尚未初始化
        # 在新的阻塞式加载模式下，这种情况不应该发生
        logger.warning(f"HTTP服务 {self.name} 的工具列表未初始化")
        return []
    
    async def fetch_tools_async(self) -> List[Dict[str, Any]]:
        """异步获取远程服务的工具列表
        
        Returns:
            工具定义列表
        """
        if self._tools_cache is not None:
            return self._tools_cache
        
        try:
            tools = await self._make_request("GET", "/tools")
            self._tools_cache = tools if isinstance(tools, list) else []
            return self._tools_cache
        except Exception as e:
            logger.error(f"获取远程工具列表失败: {e}")
            return []
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """通过HTTP调用远程工具
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            工具执行结果
        """
        payload = {
            "tool": tool_name,
            "arguments": arguments
        }
        
        try:
            response = await self._make_request("POST", "/call_tool", json=payload)
            return response.get("result")
        except Exception as e:
            logger.error(f"调用远程工具 '{tool_name}' 失败: {e}")
            raise
    
    async def call_tool_stream(self, tool_name: str, arguments: Dict[str, Any]) -> 'StreamResponse':
        """通过HTTP调用远程流式工具
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            StreamResponse: 流式响应对象
        """
        from .streaming import HTTPStreamResponse, StreamType
        
        payload = {
            "tool": tool_name,
            "arguments": arguments
        }
        
        await self._ensure_session()
        
        url = f"{self.base_url}/call_tool_stream"
        
        try:
            response = await self.session.post(url, json=payload)
            if response.status == 200:
                # 根据Content-Type确定流式类型
                content_type = response.headers.get('Content-Type', 'text/plain')
                if 'text/event-stream' in content_type:
                    stream_type = StreamType.SSE
                elif 'application/json' in content_type:
                    stream_type = StreamType.JSON
                else:
                    stream_type = StreamType.TEXT
                
                return HTTPStreamResponse(self.session, response, stream_type)
            else:
                error_text = await response.text()
                raise Exception(f"HTTP流式请求失败: {response.status} - {error_text}")
        except Exception as e:
            logger.error(f"调用远程流式工具 '{tool_name}' 失败: {e}")
            raise
    
    def supports_streaming(self, tool_name: str) -> bool:
        """检查工具是否支持流式调用"""
        try:
            tools = self._tools_cache or []
            for tool in tools:
                if tool.get("function", {}).get("name") == tool_name:
                    if is_streaming_supported and is_streaming_supported(tool):
                        return True
            return False
        except:
            return False
    
    async def health_check(self) -> bool:
        """检查远程服务健康状态
        
        Returns:
            服务是否健康
        """
        try:
            await self._make_request("GET", "/health")
            return True
        except Exception as e:
            logger.debug(f"健康检查失败: {e}")
            return False
    
    async def initialize(self) -> None:
        """初始化HTTP服务，获取服务信息和工具列表"""
        await self._fetch_service_info()
        await self.fetch_tools_async()
    
    async def close(self) -> None:
        """关闭HTTP会话"""
        if self.session:
            await self.session.close()
            self.session = None
    
    def __del__(self):
        """析构函数，确保会话被关闭"""
        try:
            # 检查session属性是否存在
            if hasattr(self, 'session') and self.session and not self.session.closed:
                logger.warning("HTTP服务会话未正确关闭，建议显式调用close()方法")
        except Exception as e:
            # 析构函数中的异常不应该被抛出，只记录日志
            logger.debug(f"UTCPHttpService析构时检查session失败: {e}")


class UTCPManager:
    """管理所有UTCP服务和工具调用的核心管理器"""
    
    def __init__(self, config_manager=None):
        """初始化UTCP管理器
        
        Args:
            config_manager: 配置管理器实例，如果为None则使用默认实例
        """
        # 使用新的核心组件
        if config_manager is None:
            config_manager = get_config_manager()
        self.config_manager = config_manager
        
        # 创建日志管理器
        self.logging_manager = get_logging_manager()
        
        self.services: Dict[str, Union[UTCPService, ServiceProxy]] = {}
        self._service_configs: Dict[str, UTCPServiceConfig] = {}

        self._failed_services: Dict[str, Exception] = {}
        self._processes: Dict[str, asyncio.subprocess.Process] = {}  # service_name -> process
        self._initialized = False
        
        # 添加工具缓存机制
        self._tool_cache: Dict[str, str] = {}  # tool_name -> service_name
        self._tools_cache_valid = False
        
    def register_service(self, config: UTCPServiceConfig) -> None:
        """根据配置注册服务
        
        Args:
            config: 服务配置
        """
        # 创建适当的服务代理
        service_proxy = ServiceProxy(config, self)
        
        # 注册代理
        self.services[config.name] = service_proxy
        self._service_configs[config.name] = config
        
        # 使工具缓存失效
        self._invalidate_tool_cache()
    
    def _validate_service_class(self, service_class: type) -> None:
        """验证服务类是否正确实现了UTCPService接口
        
        Args:
            service_class: 要验证的服务类
            
        Raises:
            ServiceValidationError: 当服务类不符合要求时
        """
        if not issubclass(service_class, UTCPService):
            raise ServiceValidationError(f"服务类 {service_class.__name__} 必须继承自UTCPService")
        
        # 检查必需的抽象方法是否已实现
        required_methods = ['name', 'description', 'get_tools', 'call_tool']
        for method_name in required_methods:
            if not hasattr(service_class, method_name):
                raise ServiceValidationError(
                    f"服务类 {service_class.__name__} 缺少必需的方法: {method_name}"
                )
        
        # 检查name和description是否为属性
        if not isinstance(inspect.getattr_static(service_class, 'name'), property):
            raise ServiceValidationError(
                f"服务类 {service_class.__name__} 的 'name' 必须是属性"
            )
        
        if not isinstance(inspect.getattr_static(service_class, 'description'), property):
            raise ServiceValidationError(
                f"服务类 {service_class.__name__} 的 'description' 必须是属性"
            )
    
    async def _validate_service_instance(self, service: UTCPService) -> None:
        """验证服务实例是否正常工作
        
        Args:
            service: 要验证的服务实例
            
        Raises:
            ServiceValidationError: 当服务实例不符合要求时
        """
        try:
            # 验证name属性
            name = service.name
            if not isinstance(name, str) or not name.strip():
                raise ServiceValidationError(f"服务名称必须是非空字符串，得到: {name}")
            
            # 验证description属性
            description = service.description
            if not isinstance(description, str):
                raise ServiceValidationError(f"服务描述必须是字符串，得到: {description}")
            
            # 验证get_tools方法
            tools = await service.get_tools()
            if not isinstance(tools, list):
                raise ServiceValidationError(f"get_tools() 必须返回列表，得到: {type(tools)}")
            
            # 验证每个工具的格式
            for i, tool in enumerate(tools):
                self._validate_tool_definition(tool, service.name, i)
                
        except Exception as e:
            if isinstance(e, ServiceValidationError):
                raise
            raise ServiceValidationError(f"验证服务 {service.name} 时出错: {e}")
    
    def _validate_tool_definition(self, tool: Dict[str, Any], service_name: str, tool_index: int) -> None:
        """验证工具定义格式
        
        Args:
            tool: 工具定义字典
            service_name: 服务名称
            tool_index: 工具在列表中的索引
            
        Raises:
            ServiceValidationError: 当工具定义格式不正确时
        """
        if not isinstance(tool, dict):
            raise ServiceValidationError(
                f"服务 {service_name} 的工具 {tool_index} 必须是字典，得到: {type(tool)}"
            )
        
        # 检查必需的顶级字段
        if "type" not in tool:
            raise ServiceValidationError(
                f"服务 {service_name} 的工具 {tool_index} 缺少 'type' 字段"
            )
        
        if tool["type"] != "function":
            raise ServiceValidationError(
                f"服务 {service_name} 的工具 {tool_index} 的 'type' 必须是 'function'"
            )
        
        if "function" not in tool:
            raise ServiceValidationError(
                f"服务 {service_name} 的工具 {tool_index} 缺少 'function' 字段"
            )
        
        function_def = tool["function"]
        if not isinstance(function_def, dict):
            raise ServiceValidationError(
                f"服务 {service_name} 的工具 {tool_index} 的 'function' 必须是字典"
            )
        
        # 检查function字段的必需子字段
        required_function_fields = ["name", "description"]
        for field in required_function_fields:
            if field not in function_def:
                raise ServiceValidationError(
                    f"服务 {service_name} 的工具 {tool_index} 的function缺少 '{field}' 字段"
                )
            
            if not isinstance(function_def[field], str) or not function_def[field].strip():
                raise ServiceValidationError(
                    f"服务 {service_name} 的工具 {tool_index} 的function.{field} 必须是非空字符串"
                )
    
    def _discover_services_in_module(self, file_path: str, module_name: str) -> List[UTCPServiceConfig]:
        """在模块中发现服务类，但不立即加载
        
        Args:
            file_path: 模块文件路径
            module_name: 模块名称
            
        Returns:
            发现的服务配置列表
        """
        configs = []
        
        try:
            # 动态导入模块进行检查
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                raise ServiceLoadError(f"无法加载模块规范: {file_path}")
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # 查找UTCPService的子类
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, UTCPService) and 
                    attr != UTCPService):
                    
                    # 创建服务配置 - 使用类名推断服务名，避免预实例化
                    # 检查是否有类属性声明的服务名
                    if hasattr(attr, 'SERVICE_NAME'):
                        actual_service_name = getattr(attr, 'SERVICE_NAME')
                    else:
                        # 使用类名生成服务名，避免实例化
                        actual_service_name = attr_name.lower().replace('service', '').replace('utcp', '').strip('_')
                    
                    config = UTCPServiceConfig(
                        name=actual_service_name,
                        module_path=file_path,
                        class_name=attr_name,
                        tags=["discovered"],
                        description=f"从模块 {module_name} 发现的服务"
                    )
                    configs.append(config)
                    logger.debug(f"发现服务类: {attr_name} -> {config.name}")
            
            if not configs:
                logger.warning(f"模块 '{module_name}' 中未找到UTCPService子类")
                
        except Exception as e:
            logger.error(f"扫描服务模块 '{module_name}' 时出错: {e}")
            raise
        
        return configs
    

    def load_services_from_config_dict(self, config_data: Dict[str, Any], tags: Optional[List[str]] = None) -> None:
        """从配置字典加载UTCP服务
        
        Args:
            config_data: 服务配置字典（直接的服务配置，不需要services键）
            tags: 标签过滤列表
        """
        try:
            # 处理每个服务配置
            for service_name, service_data in config_data.items():
                try:
                    # 检查服务是否被禁用
                    if service_data.get('enabled', True) is False:
                        logger.info(f"跳过已禁用的服务: {service_name}")
                        continue
                    
                    # 确保服务名称在配置中
                    service_data['name'] = service_name
                    
                    # 处理模块路径 - 如果是相对路径，转换为绝对路径
                    if 'module_path' in service_data and service_data['module_path']:
                        module_path = service_data['module_path']
                        if not Path(module_path).is_absolute():
                            # 使用 config_manager.services_dir 解析模块路径
                            # 对于相对路径，假设相对于服务目录
                            absolute_path = str(self.config_manager.services_dir / module_path)
                            service_data['module_path'] = absolute_path
                            logger.debug(f"转换模块路径: {module_path} -> {absolute_path}")
                    
                    # 移除 enabled 字段，因为它不是 UTCPServiceConfig 的一部分
                    service_data_for_config = {k: v for k, v in service_data.items() if k != 'enabled'}
                    config = UTCPServiceConfig(**service_data_for_config)
                    
                    # 检查标签过滤
                    if tags is not None:
                        service_tags = config.tags
                        if not any(tag in service_tags for tag in tags):
                            logger.info(f"跳过不匹配标签的服务: {config.name} (标签: {service_tags})")
                            continue
                    
                    # 使用统一的注册方法
                    self.register_service(config)
                        
                except Exception as e:
                    logger.error(f"处理服务配置失败: {service_name} - {e}")
                    self._failed_services[service_name] = e
            
        except Exception as e:
            logger.error(f"从配置字典加载服务失败: {e}")
    
    async def start_remote_services(self) -> int:
        """所有配置的远程HTTP服务（auto_start为True的）"""
        http_services = []
        for config in self._service_configs.values():
            if (config.type == ServiceType.HTTP and config.auto_start and 
                config.name in self.services):
                service = self.services[config.name]
                # 如果是ServiceProxy，需要获取实际的HTTP服务
                if isinstance(service, ServiceProxy):
                    try:
                        actual_service = service._load_service()
                        if isinstance(actual_service, UTCPHttpService):
                            http_services.append((config, actual_service))
                    except Exception as e:
                        logger.error(f"加载HTTP服务 {config.name} 失败: {e}")
                elif isinstance(service, UTCPHttpService):
                    http_services.append((config, service))
        
        if not http_services:
            return 0  
        service_names = [config.name for config, _ in http_services]
        
        tasks = [self._start_and_initialize_http_service(config, http_service) for config, http_service in http_services]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        return len(http_services)
    
    async def _start_remote_service_process(self, config: UTCPServiceConfig) -> None:
        """启动远程HTTP服务进程
        
        Args:
            config: 服务配置
        """
        if not config.start_command:
            raise ValueError(f"HTTP服务 {config.name} 未配置启动命令")
        
        try:
            logger.info(f"启动远程服务进程: {config.name}")
            
            # 构建启动命令
            cmd = [config.start_command] + [arg for arg in (config.start_args or []) if arg is not None]
            cmd_str = ' '.join(cmd)
            logger.info(f"执行启动命令: {cmd_str}")
            
            # 启动进程（非阻塞）
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=config.working_directory
            )
            
            # 存储进程引用
            self._processes[config.name] = process
            
            logger.info(f"远程服务 {config.name} 进程已启动，PID: {process.pid}")
            
            # 监控进程启动状态（最多2秒）
            await self._monitor_process_startup(process, config.name, max_wait=2.0)
            
        except Exception as e:
            logger.error(f"启动远程服务进程 {config.name} 失败: {e}")
            raise
    
    async def _monitor_process_startup(self, process: asyncio.subprocess.Process, service_name: str, max_wait: float = 2.0) -> None:
        """监控进程启动状态
        
        Args:
            process: 进程对象
            service_name: 服务名称
            max_wait: 最大等待时间（秒）
        """
        start_time = asyncio.get_event_loop().time()
        collected_stdout = []
        collected_stderr = []
        
        while True:
            current_time = asyncio.get_event_loop().time()
            elapsed = current_time - start_time
            
            # 检查进程是否退出
            if process.returncode is not None:
                # 进程已退出，收集剩余输出
                try:
                    stdout, stderr = await process.communicate()
                    if stdout:
                        collected_stdout.append(stdout.decode('utf-8', errors='ignore'))
                    if stderr:
                        collected_stderr.append(stderr.decode('utf-8', errors='ignore'))
                except Exception:
                    pass
                
                # 输出失败信息
                stdout_text = ''.join(collected_stdout)
                stderr_text = ''.join(collected_stderr)
                
                error_msg = f"服务进程退出，返回码: {process.returncode}"
                if stdout_text.strip():
                    error_msg += f"\n标准输出: {stdout_text.strip()}"
                if stderr_text.strip():
                    error_msg += f"\n错误输出: {stderr_text.strip()}"
                
                raise Exception(error_msg)
            
            # 如果超过最大等待时间，认为启动成功
            if elapsed >= max_wait:
                break
            
            # 尝试读取输出（非阻塞）
            await self._read_process_output(process, collected_stdout, collected_stderr)
            
            # 短暂等待后继续监控
            await asyncio.sleep(0.1)
        
        # 启动成功，输出收集到的信息
        stdout_text = ''.join(collected_stdout)
        stderr_text = ''.join(collected_stderr)
        
        success_msg = f"远程服务 {service_name} 进程启动成功"
        if stdout_text.strip():
            success_msg += f"\n标准输出: {stdout_text.strip()}"
        if stderr_text.strip():
            success_msg += f"\n错误输出: {stderr_text.strip()}"
        
        logger.info(success_msg)
    
    async def _read_process_output(self, process: asyncio.subprocess.Process, stdout_buffer: list, stderr_buffer: list) -> None:
        """非阻塞读取进程输出
        
        Args:
            process: 进程对象
            stdout_buffer: 标准输出缓冲区
            stderr_buffer: 错误输出缓冲区
        """
        try:
            import platform
            
            # 读取标准输出
            if process.stdout and not process.stdout.at_eof():
                try:
                    if platform.system() == 'Windows':
                        try:
                            stdout_data = await asyncio.wait_for(
                                process.stdout.read(1024), timeout=0.1
                            )
                            if stdout_data:
                                stdout_buffer.append(stdout_data.decode('utf-8', errors='ignore'))
                        except asyncio.TimeoutError:
                            pass
                    else:
                        try:
                            # 使用非阻塞读取
                            stdout_data = await asyncio.wait_for(
                                process.stdout.read(1024), timeout=0.01
                            )
                            if stdout_data:
                                stdout_buffer.append(stdout_data.decode('utf-8', errors='ignore'))
                        except (asyncio.TimeoutError, Exception):
                            pass
                except Exception:
                    pass
            
            # 读取错误输出
            if process.stderr and not process.stderr.at_eof():
                try:
                    if platform.system() == 'Windows':
                        try:
                            stderr_data = await asyncio.wait_for(
                                process.stderr.read(1024), timeout=0.1
                            )
                            if stderr_data:
                                stderr_buffer.append(stderr_data.decode('utf-8', errors='ignore'))
                        except asyncio.TimeoutError:
                            pass
                    else:
                        try:
                            # 使用非阻塞读取
                            stderr_data = await asyncio.wait_for(
                                process.stderr.read(1024), timeout=0.01
                            )
                            if stderr_data:
                                stderr_buffer.append(stderr_data.decode('utf-8', errors='ignore'))
                        except (asyncio.TimeoutError, Exception):
                            pass
                except Exception:
                    pass
                
        except Exception as e:
            logger.debug(f"读取进程输出时出错: {e}")
    
    async def _start_and_initialize_http_service(self, config: UTCPServiceConfig, http_service: 'UTCPHttpService') -> None:
        """启动远程服务进程并初始化HTTP服务
        
        Args:
            config: 服务配置
            http_service: HTTP服务实例
        """
        # 1. 启动远程服务进程
        await self._start_remote_service_process(config)
        
        # 2. 等待服务就绪
        await self._wait_for_service_ready(config)
        
       
        # 3. 关闭HTTP会话，避免资源泄漏
        await http_service.close()
        
        logger.info(f"HTTP服务 {config.name} 启动并初始化完成，获取到 {len(http_service._tools_cache or [])} 个工具")
    
    async def _wait_for_service_ready(self, config: UTCPServiceConfig, max_wait: int = 30) -> None:
        """等待远程服务就绪
        
        Args:
            config: 服务配置
            max_wait: 最大等待时间（秒）
        """
        if config.name not in self.services:
            return
        
        service = self.services[config.name]
        if not isinstance(service, UTCPHttpService):
            return
        
        logger.info(f"等待服务 {config.name} 就绪...")
        
        for attempt in range(max_wait):
            try:
                if await service.health_check():
                    logger.info(f"服务 {config.name} 已就绪")
                    # 初始化服务信息和工具列表
                    await service.initialize()
                    return
            except Exception as e:
                logger.debug(f"健康检查失败 (尝试 {attempt + 1}/{max_wait}): {e}")
            
            await asyncio.sleep(1)
        
        logger.error(f"服务 {config.name} 在 {max_wait} 秒内未就绪")
        self._failed_services[config.name] = Exception(f"服务启动超时")
    
    async def shutdown_remote_services(self) -> None:
        """关闭所有服务（包括远程HTTP服务和进程内服务）"""
        close_tasks = []
        
        # 收集所有需要关闭的服务
        for service_name, service in self.services.items():
            try:
                actual_service = None
                
                # 如果是 ServiceProxy，获取实际的服务实例
                if isinstance(service, ServiceProxy):
                    if service.is_loaded() and service._service:
                        actual_service = service._service
                # 如果是直接的 UTCPService 实例（如 UTCPHttpService）
                elif isinstance(service, UTCPService):
                    actual_service = service
                
                # 如果找到了服务实例，检查是否有 close 方法
                if actual_service and hasattr(actual_service, 'close') and callable(getattr(actual_service, 'close', None)):
                    # 使用闭包正确捕获变量
                    def make_close_task(svc, name):
                        async def close_service():
                            try:
                                await svc.close()
                                logger.debug(f"服务 {name} 已关闭")
                            except Exception as e:
                                logger.warning(f"关闭服务 {name} 时出错: {e}")
                        return close_service
                    
                    close_tasks.append(make_close_task(actual_service, service_name)())
            except Exception as e:
                logger.warning(f"检查服务 {service_name} 时出错: {e}")
        
        if not close_tasks:
            logger.info("没有需要关闭的服务")
            return
        
        logger.info(f"关闭 {len(close_tasks)} 个服务")
        
        # 并行关闭所有服务
        await asyncio.gather(*close_tasks, return_exceptions=True)
    
    def get_failed_services(self) -> Dict[str, Exception]:
        """获取加载失败的服务列表
        
        Returns:
            失败服务名称到异常的映射
        """
        return self._failed_services.copy()
    

    
    async def get_all_tools(self, tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """获取所有服务的所有工具（OpenAI格式）
        
        Args:
            tags: 标签列表，如果提供则只返回包含这些标签的服务工具
            
        Returns:
            所有工具的定义列表，只包括原始工具名称
        """
        all_tools = []
        
        for service_name, service in self.services.items():
            try:
                # 检查服务标签过滤
                if tags is not None:
                    # 获取服务配置中的标签
                    service_config = self._service_configs.get(service_name)
                    if service_config:
                        service_tags = service_config.tags
                        # 检查是否有任何指定标签匹配
                        if not any(tag in service_tags for tag in tags):
                            logger.debug(f"跳过不匹配标签的服务: {service_name} (标签: {service_tags})")
                            continue
                    else:
                        # 如果没有配置信息，跳过该服务
                        logger.debug(f"跳过无配置信息的服务: {service_name}")
                        continue
                
                service_tools = await service.get_tools()
                for tool in service_tools:
                    # 只添加原始工具，不创建服务限定名版本
                    all_tools.append(tool)
                    
            except Exception as e:
                logger.error(f"获取服务 '{service_name}' 的工具时出错: {e}")
        
        return all_tools
    
    def parse_tool_ref(self, tool_ref: str) -> tuple[Optional[str], str]:
        """解析工具引用
        
        Args:
            tool_ref: 工具引用，可以是直接工具名或服务限定名
            
        Returns:
            (service_name, actual_tool_name) 或 (None, tool_name)
        """
        if "." in tool_ref:
            # 服务限定名格式：service.tool
            parts = tool_ref.split(".", 1)
            return parts[0], parts[1]
        else:
            # 直接工具名格式
            return None, tool_ref
    
    async def call_tool(self, tool_ref: str, arguments: Dict[str, Any]) -> Any:
        """按引用调用工具
        
        支持两种调用格式：
        1. 直接工具名：如 "add", "health_check" - 在所有服务中查找
        2. 服务限定名：如 "calc.add", "memory.search" - 在指定服务中查找
        
        Args:
            tool_ref: 工具引用，支持服务前缀格式
            arguments: 工具参数字典
            
        Returns:
            工具执行结果
            
        Raises:
            ValueError: 当工具不存在或存在歧义时
        """
        service_name, actual_tool_name = self.parse_tool_ref(tool_ref)
        
        if service_name:
            # 服务限定名调用
            if service_name not in self.services:
                raise ValueError(f"服务 '{service_name}' 不存在")
            
            service = self.services[service_name]
            return await service.call_tool(actual_tool_name, arguments)
        else:
            # 直接工具名调用 - 使用缓存机制
            if not self._tools_cache_valid:
                await self._rebuild_tool_cache()
            
            # 检查缓存
            if actual_tool_name in self._tool_cache:
                service_name = self._tool_cache[actual_tool_name]
                service = self.services[service_name]
                return await service.call_tool(actual_tool_name, arguments)
            
            # 缓存未命中，重新查找
            matching_services = []
            for svc_name, service in self.services.items():
                try:
                    tools = await service.get_tools()
                    if any(tool["function"]["name"] == actual_tool_name for tool in tools):
                        matching_services.append(svc_name)
                except Exception as e:
                    logger.error(f"检查服务 '{svc_name}' 的工具时出错: {e}")
            
            if len(matching_services) == 0:
                raise ValueError(f"工具 '{actual_tool_name}' 不存在")
            elif len(matching_services) > 1:
                services_str = "', '".join(matching_services)
                raise ValueError(
                    f"工具名 '{actual_tool_name}' 在多个服务中存在: '{services_str}'. "
                    f"请使用服务限定名，如: {matching_services[0]}.{actual_tool_name}"
                )
            else:
                # 唯一匹配，更新缓存并调用
                service_name = matching_services[0]
                self._tool_cache[actual_tool_name] = service_name
                service = self.services[service_name]
                return await service.call_tool(actual_tool_name, arguments)
    
    async def call_tool_stream(self, tool_ref: str, arguments: Dict[str, Any]) -> 'StreamResponse':
        """按引用调用流式工具
        
        支持两种调用格式：
        1. 直接工具名：如 "chat_completion_stream" - 在所有服务中查找
        2. 服务限定名：如 "azure_llm.chat_completion_stream" - 在指定服务中查找
        
        Args:
            tool_ref: 工具引用，支持服务前缀格式
            arguments: 工具参数字典
            
        Returns:
            StreamResponse: 流式响应对象
            
        Raises:
            ValueError: 当工具不存在或存在歧义时
            NotImplementedError: 当工具不支持流式调用时
        """
        service_name, actual_tool_name = self.parse_tool_ref(tool_ref)
        
        if service_name:
            # 服务限定名调用
            if service_name not in self.services:
                raise ValueError(f"服务 '{service_name}' 不存在")
            
            service = self.services[service_name]
            if not service.supports_streaming(actual_tool_name):
                raise ValueError(f"工具 '{actual_tool_name}' 不支持流式调用")
            return await service.call_tool_stream(actual_tool_name, arguments)
        else:
            # 直接工具名调用 - 查找支持流式的服务
            matching_services = []
            for svc_name, service in self.services.items():
                try:
                    if service.supports_streaming(actual_tool_name):
                        matching_services.append(svc_name)
                except Exception as e:
                    logger.error(f"检查服务 '{svc_name}' 的流式工具时出错: {e}")
            
            if len(matching_services) == 0:
                raise ValueError(f"流式工具 '{actual_tool_name}' 不存在")
            elif len(matching_services) > 1:
                services_str = "', '".join(matching_services)
                raise ValueError(
                    f"流式工具名 '{actual_tool_name}' 在多个服务中存在: '{services_str}'. "
                    f"请使用服务限定名，如: {matching_services[0]}.{actual_tool_name}"
                )
            else:
                # 唯一匹配，调用流式工具
                service_name = matching_services[0]
                service = self.services[service_name]
                return await service.call_tool_stream(actual_tool_name, arguments)
    
    async def _rebuild_tool_cache(self) -> None:
        """重建工具缓存"""
        self._tool_cache.clear()
        
        for svc_name, service in self.services.items():
            try:
                tools = await service.get_tools()
                for tool in tools:
                    tool_name = tool["function"]["name"]
                    if tool_name in self._tool_cache:
                        # 发现重复工具名，清除缓存并标记无效
                        self._tool_cache.clear()
                        self._tools_cache_valid = False
                        return
                    self._tool_cache[tool_name] = svc_name
            except Exception as e:
                logger.error(f"构建工具缓存时出错 (服务 {svc_name}): {e}")
        
        self._tools_cache_valid = True
    
    async def get_service_info(self) -> Dict[str, Dict[str, Any]]:
        """获取所有已注册服务的信息
        
        Returns:
            服务信息字典，包含每个服务的名称、描述和工具数量
        """
        info = {}
        for service_name, service in self.services.items():
            try:
                tools = await service.get_tools()
                info[service_name] = {
                    "name": service.name,
                    "description": service.description,
                    "tool_count": len(tools),
                    "tools": [tool["function"]["name"] for tool in tools]
                }
            except Exception as e:
                info[service_name] = {
                    "name": service.name,
                    "description": service.description,
                    "error": str(e)
                }
        
        return info
    
    def is_initialized(self) -> bool:
        """检查管理器是否已初始化"""
        return self._initialized
    
    def set_initialized(self, initialized: bool = True) -> None:
        """设置管理器初始化状态"""
        self._initialized = initialized

    def _instantiate_service(self, service_class: type, config: UTCPServiceConfig) -> UTCPService:
        """实例化服务，统一处理配置合并、验证和日志初始化
        插件不允许写__init__方法，只能通过init方法进行初始化
        
        Args:
            service_class: 服务类
            config: 服务配置
        Returns:
            服务实例
        """
        try:
            # 如果有配置管理器，直接获取合并后的配置（已包含环境变量替换和配置验证）
            if self.config_manager:
                # 使用module_path作为目录去加载默认配置文件
                merged_config = self.config_manager.get_service_config(
                    config.name, 
                    config.config or {}, 
                    module_path=config.module_path
                )
            else:
                # 如果没有配置管理器，直接使用传入的配置
                merged_config = config.config or {}
            
            # 日志初始化
            service_logger = self._setup_service_logging(config.name, merged_config)
            
            # 创建服务实例，使用基类的__init__方法
            service_instance = service_class(merged_config, self.config_manager, service_logger)
            
            # 调用插件的init方法进行初始化
            if service_instance and hasattr(service_instance, 'init'):
                try:
                    logger.debug(f"调用服务 {config.name} 的init方法")
                    service_instance.init()
                    logger.debug(f"服务 {config.name} init方法调用完成")
                except Exception as e:
                    logger.error(f"服务 {config.name} init方法调用失败: {e}")
                    raise ServiceLoadError(f"服务 {config.name} init方法调用失败: {e}")
            
            return service_instance
            
        except Exception as e:
            logger.error(f"实例化服务 {config.name} 失败: {e}")
            raise ServiceLoadError(f"实例化服务 {config.name} 失败: {e}")
    

    
    def _setup_service_logging(self, service_name: str, config: Dict[str, Any]) -> logging.Logger:
        """设置服务日志
        
        Args:
            service_name: 服务名称
            config: 服务配置
            
        Returns:
            配置好的日志对象
        """
        # 获取日志配置
        logging_config = config.get("logging", {})
        
        # 检查插件是否有自定义日志配置
        if logging_config:
            # 插件有日志配置，使用插件的日志配置
            logger.debug(f"服务 {service_name} 使用自定义日志配置")
            
            # 创建服务专用的日志对象
            service_logger = logging.getLogger(f"utcp.service.{service_name}")
            
            # 设置日志级别
            log_level = logging_config.get("level", "INFO")
            numeric_level = getattr(logging, log_level.upper(), logging.INFO)
            service_logger.setLevel(numeric_level)
            
            # 如果日志对象还没有处理器，添加一个
            if not service_logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                )
                handler.setFormatter(formatter)
                service_logger.addHandler(handler)
            
            # 设置是否传播到根日志器
            service_logger.propagate = logging_config.get("propagate", True)
            
            logger.debug(f"服务 {service_name} 自定义日志初始化完成，级别: {log_level}")
            return service_logger
        else:
            # 插件没有日志配置，使用UTCP的日志对象
            logger.debug(f"服务 {service_name} 使用UTCP默认日志对象")
            
            # 获取UTCP的日志对象
            try:
                # 尝试使用UTCP的日志管理器
                utcp_logger = self.logging_manager.get_logger(f"utcp.service.{service_name}")
                logger.debug(f"服务 {service_name} 使用UTCP日志管理器")
                return utcp_logger
            except Exception as e:
                # 如果获取失败，使用默认的日志对象
                logger.warning(f"获取UTCP日志对象失败，使用默认日志对象: {e}")
                default_logger = logging.getLogger(f"utcp.service.{service_name}")
                default_logger.setLevel(logging.INFO)
                
                # 确保有处理器
                if not default_logger.handlers:
                    handler = logging.StreamHandler()
                    formatter = logging.Formatter(
                        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                    )
                    handler.setFormatter(formatter)
                    default_logger.addHandler(handler)
                
                logger.debug(f"服务 {service_name} 使用默认日志对象")
                return default_logger

    def _invalidate_tool_cache(self) -> None:
        """使工具缓存失效"""
        self._tools_cache_valid = False
        self._tool_cache.clear()