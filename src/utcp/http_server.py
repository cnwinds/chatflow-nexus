#!/usr/bin/env python3
"""
UTCP HTTP服务器
为UTCP服务提供HTTP接口，支持远程调用
"""

import json
import asyncio
import logging
from typing import Dict, Any, Optional
from aiohttp import web, ClientSession
from aiohttp.web import Request, Response
from datetime import datetime

from .utcp import UTCPService
from .error_handling import ErrorHandler, ErrorContext, ErrorSeverity, ErrorCategory


class UTCPHttpServer:
    """UTCP HTTP服务器"""
    
    def __init__(self, service: UTCPService, host: str = "localhost", port: int = 8000):
        self.service = service
        self.host = host
        self.port = port
        self.app = web.Application()
        self.error_handler = ErrorHandler()
        self.logger = logging.getLogger(f"utcp.http_server.{service.name}")
        
        # 设置路由
        self._setup_routes()
    
    def _setup_routes(self):
        """设置HTTP路由"""
        self.app.router.add_get("/", self.index)
        self.app.router.add_get("/health", self.health_check)
        self.app.router.add_get("/info", self.get_service_info)
        self.app.router.add_get("/tools", self.get_tools)
        self.app.router.add_post("/call_tool", self.call_tool)
        self.app.router.add_post("/call_tool_stream", self.call_tool_stream)
        self.app.router.add_get("/stats", self.get_stats)
        
        # 添加CORS支持
        self.app.middlewares.append(self._cors_middleware)
        
        # 添加错误处理中间件
        self.app.middlewares.append(self._error_middleware)
    
    @web.middleware
    async def _cors_middleware(self, request: Request, handler):
        """CORS中间件"""
        response = await handler(request)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response
    
    @web.middleware
    async def _error_middleware(self, request: Request, handler):
        """错误处理中间件"""
        try:
            return await handler(request)
        except Exception as e:
            self.logger.error(f"HTTP请求处理错误: {e}")
            
            # 创建错误上下文
            context = ErrorContext(
                service_name=self.service.name,
                request_id=request.headers.get('X-Request-ID', 'unknown')
            )
            
            # 创建标准化错误
            error = self.error_handler.create_error(
                code=f"{self.service.name.upper()}_HTTP_ERROR",
                message=str(e),
                severity=ErrorSeverity.HIGH,
                category=ErrorCategory.SERVICE,
                context=context
            )
            
            return web.json_response(
                error.to_dict(),
                status=500
            )
    
    async def index(self, request: Request) -> Response:
        """首页"""
        info = {
            "service": self.service.name,
            "description": self.service.description,
            "version": "1.0.0",
            "timestamp": datetime.now().isoformat(),
            "endpoints": {
                "health": "/health",
                "info": "/info", 
                "tools": "/tools",
                "call_tool": "/call_tool (POST)",
                "stats": "/stats"
            }
        }
        
        return web.json_response(info)
    
    async def health_check(self, request: Request) -> Response:
        """健康检查"""
        health_info = {
            "status": "healthy",
            "service": self.service.name,
            "timestamp": datetime.now().isoformat(),
            "uptime": "unknown",  # 可以添加启动时间跟踪
            "version": "1.0.0"
        }
        
        return web.json_response(health_info)
    
    async def get_service_info(self, request: Request) -> Response:
        """获取服务信息"""
        info = {
            "name": self.service.name,
            "description": self.service.description,
            "type": "utcp_http_service",
            "version": "1.0.0",
            "timestamp": datetime.now().isoformat()
        }
        
        return web.json_response(info)
    
    async def get_tools(self, request: Request) -> Response:
        """获取工具列表"""
        try:
            tools = await self.service.get_tools()
            return web.json_response(tools)
        except Exception as e:
            self.logger.error(f"获取工具列表失败: {e}")
            return web.json_response({
                "error": "Failed to get tools",
                "message": str(e)
            }, status=500)
    
    async def call_tool(self, request: Request) -> Response:
        """调用工具"""
        try:
            # 解析请求数据
            data = await request.json()
            tool_name = data.get("tool")
            arguments = data.get("arguments", {})
            
            if not tool_name:
                return web.json_response({
                    "error": "Missing tool name",
                    "message": "请求中缺少工具名称"
                }, status=400)
            
            # 调用工具
            result = await self.service.call_tool(tool_name, arguments)
            
            # 返回结果
            return web.json_response({
                "status": "success",
                "result": result,
                "timestamp": datetime.now().isoformat()
            })
            
        except json.JSONDecodeError:
            return web.json_response({
                "error": "Invalid JSON",
                "message": "请求数据格式错误"
            }, status=400)
        except Exception as e:
            self.logger.error(f"工具调用失败: {e}")
            return web.json_response({
                "error": "Tool call failed",
                "message": str(e)
            }, status=500)
    
    async def call_tool_stream(self, request: Request) -> Response:
        """调用流式工具"""
        try:
            # 解析请求数据
            data = await request.json()
            tool_name = data.get("tool")
            arguments = data.get("arguments", {})
            
            if not tool_name:
                return web.json_response({
                    "error": "Missing tool name",
                    "message": "请求中缺少工具名称"
                }, status=400)
            
            # 检查工具是否支持流式调用
            if not self.service.supports_streaming(tool_name):
                return web.json_response({
                    "error": "Tool does not support streaming",
                    "message": f"工具 '{tool_name}' 不支持流式调用"
                }, status=400)
            
            # 调用流式工具
            stream_response = await self.service.call_tool_stream(tool_name, arguments)
            
            # 根据流式类型返回不同格式的响应
            if stream_response.stream_type.value == "sse":
                return await self._handle_sse_stream(stream_response, request)
            elif stream_response.stream_type.value == "json":
                return await self._handle_json_stream(stream_response, request)
            else:
                return await self._handle_text_stream(stream_response, request)
                
        except json.JSONDecodeError:
            return web.json_response({
                "error": "Invalid JSON",
                "message": "请求数据格式错误"
            }, status=400)
        except NotImplementedError as e:
            return web.json_response({
                "error": "Streaming not supported",
                "message": str(e)
            }, status=501)
        except Exception as e:
            self.logger.error(f"流式工具调用失败: {e}")
            return web.json_response({
                "error": "Stream tool call failed",
                "message": str(e)
            }, status=500)
    
    async def _handle_sse_stream(self, stream_response, request) -> Response:
        """处理Server-Sent Events流式响应"""
        response = web.StreamResponse(
            status=200,
            headers={
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Access-Control-Allow-Origin': '*'
            }
        )
        
        await response.prepare(request)
        
        try:
            async for chunk in stream_response:
                if isinstance(chunk, dict):
                    data = json.dumps(chunk, ensure_ascii=False)
                else:
                    data = str(chunk)
                
                sse_data = f"data: {data}\n\n"
                await response.write(sse_data.encode('utf-8'))
                
        except Exception as e:
            self.logger.error(f"SSE流式响应处理错误: {e}")
        finally:
            await stream_response.close()
            await response.write_eof()
        
        return response
    
    async def _handle_json_stream(self, stream_response, request) -> Response:
        """处理JSON流式响应"""
        response = web.StreamResponse(
            status=200,
            headers={
                'Content-Type': 'application/json',
                'Transfer-Encoding': 'chunked',
                'Access-Control-Allow-Origin': '*'
            }
        )
        
        await response.prepare(request)
        
        try:
            async for chunk in stream_response:
                if isinstance(chunk, (dict, list)):
                    data = json.dumps(chunk, ensure_ascii=False) + '\n'
                else:
                    data = json.dumps({"data": str(chunk)}, ensure_ascii=False) + '\n'
                
                await response.write(data.encode('utf-8'))
                
        except Exception as e:
            self.logger.error(f"JSON流式响应处理错误: {e}")
        finally:
            await stream_response.close()
            await response.write_eof()
        
        return response
    
    async def _handle_text_stream(self, stream_response, request) -> Response:
        """处理文本流式响应"""
        response = web.StreamResponse(
            status=200,
            headers={
                'Content-Type': 'text/plain; charset=utf-8',
                'Transfer-Encoding': 'chunked',
                'Access-Control-Allow-Origin': '*'
            }
        )
        
        await response.prepare(request)
        
        try:
            async for chunk in stream_response:
                data = str(chunk)
                await response.write(data.encode('utf-8'))
                
        except Exception as e:
            self.logger.error(f"文本流式响应处理错误: {e}")
        finally:
            await stream_response.close()
            await response.write_eof()
        
        return response
    
    async def get_stats(self, request: Request) -> Response:
        """获取统计信息"""
        stats = {
            "service": self.service.name,
            "tools_count": len(await self.service.get_tools()),
            "timestamp": datetime.now().isoformat(),
            "error_stats": self.error_handler.get_error_stats()
        }
        
        return web.json_response(stats)
    
    async def start(self):
        """启动HTTP服务器"""
        self.logger.info(f"启动UTCP HTTP服务器: {self.service.name}")
        self.logger.info(f"监听地址: http://{self.host}:{self.port}")
        
        runner = web.AppRunner(self.app)
        await runner.setup()
        
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        
        self.logger.info(f"UTCP HTTP服务器已启动: {self.service.name}")
        
        return runner
    
    def run(self):
        """运行HTTP服务器（阻塞）"""
        async def _run():
            runner = await self.start()
            try:
                # 保持服务器运行
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                self.logger.info("收到停止信号，关闭服务器...")
            finally:
                await runner.cleanup()
        
        asyncio.run(_run())


def create_http_server(service: UTCPService, host: str = "localhost", port: int = 8000) -> UTCPHttpServer:
    """创建HTTP服务器"""
    return UTCPHttpServer(service, host, port)


async def run_service_as_http_server(service_class, host: str = "localhost", port: int = 8000):
    """将UTCP服务作为HTTP服务器运行"""
    # 创建服务实例
    service = service_class()
    
    # 创建HTTP服务器
    server = create_http_server(service, host, port)
    
    # 启动服务器
    await server.start()
    
    try:
        # 保持服务器运行
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 收到停止信号，关闭服务器...")


if __name__ == "__main__":
    # 示例：启动计算器服务的HTTP服务器
    import sys
    import os
    
    # 添加项目路径
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    
    from services.calculator_service import CalculatorService
    
    # 解析命令行参数
    import argparse
    parser = argparse.ArgumentParser(description='UTCP HTTP服务器')
    parser.add_argument('--host', default='localhost', help='服务器主机')
    parser.add_argument('--port', type=int, default=8000, help='服务器端口')
    parser.add_argument('--service', default='calculator', help='服务类型')
    
    args = parser.parse_args()
    
    # 服务映射
    service_classes = {
        'calculator': CalculatorService,
        # 可以添加更多服务
    }
    
    if args.service not in service_classes:
        print(f"❌ 未知服务类型: {args.service}")
        print(f"可用服务: {list(service_classes.keys())}")
        sys.exit(1)
    
    # 启动HTTP服务器
    asyncio.run(run_service_as_http_server(
        service_classes[args.service],
        args.host,
        args.port
    ))