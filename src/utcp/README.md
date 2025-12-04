# UTCP 服务开发指南

## 概述

UTCP (通用工具调用协议) 是一个用于构建和管理 AI 工具服务的框架。本指南将教你如何快速创建一个 UTCP 服务。

## 快速开始

### 1. 创建服务目录结构

```
src/services/your_service/
├── __init__.py
├── service.py
├── default_config.json
└── README.md
```

### 2. 编写服务类

```python
#!/usr/bin/env python3
"""
你的服务描述
"""

import logging
from typing import Dict, List, Any, Optional
from src.utcp.utcp import UTCPService

logger = logging.getLogger(__name__)

class YourService(UTCPService):
    """你的服务类"""
    
    # 插件不允许写__init__方法，只能通过init方法进行初始化
    
    def init(self) -> None:
        """插件初始化方法"""
        # 从配置中获取参数
        self.api_key = self.config.get("api_key")
        self.timeout = self.config.get("timeout", 30)
        
        # 验证必需配置
        if not self.api_key:
            raise ValueError("需要 api_key 配置")
        
        # 初始化其他资源
        self.session = None
        
        if self.logger:
            self.logger.info("服务初始化完成")
    
    @property
    def name(self) -> str:
        """服务名称"""
        return "your_service"
    
    @property
    def description(self) -> str:
        """服务描述"""
        return "你的服务描述"
    
    async def get_tools(self) -> List[Dict[str, Any]]:
        """返回可用工具列表"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "your_tool",
                    "description": "你的工具描述",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "param1": {
                                "type": "string",
                                "description": "参数1描述"
                            },
                            "param2": {
                                "type": "integer",
                                "description": "参数2描述",
                                "default": 10
                            }
                        },
                        "required": ["param1"]
                    }
                }
            }
        ]
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """调用工具"""
        try:
            if tool_name == "your_tool":
                return await self._your_tool(arguments)
            else:
                raise ValueError(f"未知的工具: {tool_name}")
        except Exception as e:
            if self.logger:
                self.logger.error(f"调用工具 {tool_name} 失败: {e}")
            return {
                "error": f"工具调用失败: {str(e)}",
                "success": False
            }
    
    async def _your_tool(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """你的工具实现"""
        param1 = arguments.get("param1")
        param2 = arguments.get("param2", 10)
        
        # 你的业务逻辑
        result = f"处理参数: {param1}, {param2}"
        
        return {
            "success": True,
            "result": result,
            "data": {
                "param1": param1,
                "param2": param2
            }
        }
```

### 3. 创建配置文件

```json
{
  "service_config": {
    "timeout": 30,
    "max_retries": 3,
    "enable_cache": true
  },
  "api_config": {
    "api_key": "",
    "base_url": "https://api.example.com",
    "version": "v1"
  },
  "logging": {
    "level": "INFO",
    "enable_detailed_logs": false
  },
  "validation": {
    "required_keys": [
      "api_config.api_key"
    ],
    "rules": {
      "service_config.timeout": {
        "type": "int",
        "min": 5,
        "max": 300
      }
    }
  }
}
```

### 4. 注册服务

在 `docker/runtime/config/services.json` 中添加：

```json
{
  "your_service": {
    "type": "inprocess",
    "module_path": "your_service",
    "class_name": "YourService",
    "tags": [
      "your_tag",
      "utility"
    ],
    "description": "你的服务描述",
    "config": {
      "api_key": "your_api_key_here",
      "timeout": 30
    }
  }
}
```

## 详细说明

### 必需的方法和属性

#### 1. `init()` 方法
- **用途**：服务初始化
- **调用时机**：服务加载时自动调用
- **职责**：
  - 从 `self.config` 读取配置
  - 验证必需参数
  - 初始化资源（数据库连接、HTTP会话等）
  - 记录初始化日志

#### 2. `name` 属性
- **类型**：字符串
- **用途**：服务唯一标识符
- **示例**：`"search_service"`, `"calculator_service"`

#### 3. `description` 属性
- **类型**：字符串
- **用途**：服务功能描述
- **示例**：`"提供网络搜索服务"`

#### 4. `get_tools()` 方法
- **类型**：异步方法
- **返回**：工具定义列表
- **格式**：OpenAI 函数调用格式

#### 5. `call_tool()` 方法
- **类型**：异步方法
- **参数**：`tool_name`（工具名）, `arguments`（参数字典）
- **返回**：工具执行结果

### 配置管理

#### 配置来源
1. **默认配置**：`default_config.json`
2. **运行时配置**：`services.json` 中的 `config` 字段
3. **环境变量**：通过配置管理器自动替换

#### 配置访问
```python
def init(self) -> None:
    # 直接访问配置
    api_key = self.config.get("api_key")
    
    # 访问嵌套配置
    timeout = self.config.get("service_config", {}).get("timeout", 30)
    
    # 使用配置管理器（如果需要）
    if self.config_manager:
        merged_config = self.config_manager.get_service_config(self.name)
```

### 错误处理

#### 初始化错误
```python
def init(self) -> None:
    try:
        # 初始化逻辑
        if not self.config.get("api_key"):
            raise ValueError("缺少必需的 api_key 配置")
        
        # 其他初始化...
        
    except Exception as e:
        if self.logger:
            self.logger.error(f"服务初始化失败: {e}")
        raise  # 重新抛出异常，让框架知道初始化失败
```

#### 工具调用错误
```python
async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
    try:
        if tool_name == "your_tool":
            return await self._your_tool(arguments)
        else:
            raise ValueError(f"未知的工具: {tool_name}")
    except Exception as e:
        if self.logger:
            self.logger.error(f"工具调用失败: {e}")
        return {
            "error": str(e),
            "success": False
        }
```

### 日志记录

```python
def init(self) -> None:
    if self.logger:
        self.logger.info("开始初始化服务")
    
    # 初始化逻辑
    
    if self.logger:
        self.logger.info("服务初始化完成")

async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
    if self.logger:
        self.logger.debug(f"调用工具: {tool_name}, 参数: {arguments}")
    
    # 工具调用逻辑
    
    if self.logger:
        self.logger.debug(f"工具调用完成: {tool_name}")
```

## 实际示例

### 搜索服务示例

```python
class SearchService(UTCPService):
    def init(self) -> None:
        self.api_key = self.config.get("api_key")
        self.base_url = self.config.get("base_url", "https://api.search.com")
        self.timeout = self.config.get("timeout", 30)
        
        if not self.api_key:
            raise ValueError("需要 api_key 配置")
        
        self.session = None
    
    @property
    def name(self) -> str:
        return "search_service"
    
    @property
    def description(self) -> str:
        return "提供网络搜索服务"
    
    async def get_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "执行网络搜索",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "搜索查询"
                            },
                            "count": {
                                "type": "integer",
                                "description": "结果数量",
                                "default": 10
                            }
                        },
                        "required": ["query"]
                    }
                }
            }
        ]
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if tool_name == "web_search":
            return await self._web_search(arguments)
        else:
            raise ValueError(f"未知工具: {tool_name}")
    
    async def _web_search(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        query = arguments.get("query")
        count = arguments.get("count", 10)
        
        # 实际的搜索逻辑
        results = await self._perform_search(query, count)
        
        return {
            "success": True,
            "query": query,
            "results": results
        }
```

## 最佳实践

### 1. 命名规范
- 服务名称：使用下划线分隔，如 `search_service`
- 工具名称：使用下划线分隔，如 `web_search`
- 配置键：使用下划线分隔，如 `api_key`

### 2. 错误处理
- 初始化时验证所有必需配置
- 工具调用时提供详细的错误信息
- 使用统一的错误返回格式

### 3. 日志记录
- 记录重要的操作和错误
- 使用适当的日志级别
- 避免记录敏感信息

### 4. 配置管理
- 提供合理的默认值
- 验证配置参数的有效性
- 使用环境变量管理敏感信息

### 5. 性能优化
- 复用资源（如HTTP会话）
- 实现适当的缓存机制
- 避免在工具调用中重复初始化

## 常见问题

### Q: 为什么不能写 `__init__` 方法？
A: UTCP 框架需要统一管理服务的初始化流程，包括配置合并、日志设置等。自定义 `__init__` 会破坏这个流程。

### Q: 如何访问数据库？
A: 通过 `get_db_manager()` 获取已初始化的数据库管理器：
```python
def init(self) -> None:
    try:
        from src.common.database.manager import get_db_manager
        
        # 获取已初始化的数据库管理器
        db_manager = get_db_manager()
        
        # 使用 db_manager 进行数据库操作
        result = db_manager.execute_query("SELECT * FROM your_table")
        
    except RuntimeError as e:
        raise Exception("数据库管理器未初始化，请确保在程序启动时已初始化数据库")
```

### Q: 如何支持流式响应？
A: 重写 `call_tool_stream` 方法：
```python
async def call_tool_stream(self, tool_name: str, arguments: Dict[str, Any]) -> 'StreamResponse':
    if tool_name == "streaming_tool":
        return await self._streaming_tool(arguments)
    else:
        raise NotImplementedError(f"工具 {tool_name} 不支持流式调用")
```

### Q: 如何测试服务？
A: 创建测试文件：
```python
async def test_service():
    from src.services.your_service.service import YourService
    
    service = YourService()
    service.init()
    
    tools = await service.get_tools()
    print(f"工具列表: {tools}")
    
    result = await service.call_tool("your_tool", {"param1": "test"})
    print(f"调用结果: {result}")
```

## 总结

遵循这个指南，你可以快速创建一个符合 UTCP 框架规范的服务。记住核心原则：

1. **不要写 `__init__` 方法**，使用 `init()` 方法进行初始化
2. **实现所有必需的抽象方法**：`name`, `description`, `init`, `get_tools`, `call_tool`
3. **提供良好的错误处理和日志记录**
4. **使用统一的配置管理方式**

这样创建的服务可以无缝集成到 UTCP 框架中，并被其他组件正确调用。
