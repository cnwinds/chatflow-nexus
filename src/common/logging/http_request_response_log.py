"""
HTTP请求和应答日志中间件
"""

import json
import time
import logging
from typing import Dict, Any, Optional
from fastapi import Request, Response
from fastapi.responses import StreamingResponse
import hashlib


class RequestResponseLogger:
    """请求和应答日志记录器"""
    
    def __init__(self, logger: logging.Logger):
        """初始化日志记录器"""
        self.logger = logger
        self.sensitive_fields = {'password', 'token', 'authorization', 'mobile_code', 'newPassword'}
    
    def _mask_sensitive_data(self, data: Any) -> Any:
        """掩码敏感数据"""
        if isinstance(data, dict):
            masked_data = {}
            for key, value in data.items():
                if key.lower() in self.sensitive_fields:
                    masked_data[key] = "***"
                else:
                    masked_data[key] = self._mask_sensitive_data(value)
            return masked_data
        elif isinstance(data, list):
            return [self._mask_sensitive_data(item) for item in data]
        else:
            return data
    
    async def _get_request_body(self, request: Request) -> Optional[Dict[str, Any]]:
        """获取请求体内容"""
        try:
            # 检查Content-Type
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type:
                # 对于JSON请求，尝试读取body
                body = await request.body()
                if body:
                    try:
                        return json.loads(body.decode())
                    except json.JSONDecodeError:
                        return {"raw_body": body.decode()[:200] + "..." if len(body) > 200 else body.decode()}
            elif "application/x-www-form-urlencoded" in content_type:
                # 对于表单数据，返回表单参数
                return dict(request.query_params)
            elif "multipart/form-data" in content_type:
                # 对于文件上传，只记录文件名
                return {"files": "multipart_data"}
        except Exception as e:
            self.logger.warning(f"读取请求体失败: {str(e)}")
        return None
    
    def _get_response_body(self, response: Response) -> Optional[str]:
        """获取响应体内容"""
        try:
            if hasattr(response, 'body'):
                body = response.body
                if isinstance(body, bytes):
                    # 尝试解码为JSON
                    try:
                        return json.dumps(json.loads(body.decode()), ensure_ascii=False)
                    except:
                        return body.decode()[:1000] + "..." if len(body) > 1000 else body.decode()
                elif isinstance(body, str):
                    return body[:1000] + "..." if len(body) > 1000 else body
        except Exception as e:
            self.logger.warning(f"读取响应体失败: {str(e)}")
        return None
    
    async def _format_request_log(self, request: Request, request_id: str) -> str:
        """格式化请求日志"""
        # 获取请求体
        request_body = await self._get_request_body(request)
        if request_body:
            request_body = self._mask_sensitive_data(request_body)
        
        # 获取查询参数
        query_params = dict(request.query_params)
        if query_params:
            query_params = self._mask_sensitive_data(query_params)
        
        # 获取请求头（排除敏感信息）
        headers = dict(request.headers)
        sensitive_headers = {'authorization', 'cookie', 'x-api-key'}
        for header in sensitive_headers:
            if header in headers:
                headers[header] = "***"
        
        log_data = {
            "request_id": request_id,
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "query_params": query_params,
            "headers": headers,
            "client_ip": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("user-agent", ""),
            "request_body": request_body
        }
        
        return json.dumps(log_data, ensure_ascii=False, indent=2)
    
    def _format_response_log(self, response: Response, request_id: str, process_time: float) -> str:
        """格式化响应日志"""
        # 获取响应体
        response_body = self._get_response_body(response)
        
        log_data = {
            "request_id": request_id,
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "process_time_ms": round(process_time * 1000, 2),
            "response_body": response_body
        }
        
        return json.dumps(log_data, ensure_ascii=False, indent=2)
    
    async def log_request(self, request: Request, request_id: str):
        """记录请求日志"""
        try:
            log_message = await self._format_request_log(request, request_id)
            self.logger.debug(f"REQUEST [{request_id}]:\n{log_message}")
        except Exception as e:
            self.logger.error(f"记录请求日志失败: {str(e)}")
    
    def log_response(self, response: Response, request_id: str, process_time: float):
        """记录响应日志"""
        try:
            log_message = self._format_response_log(response, request_id, process_time)
            self.logger.debug(f"RESPONSE [{request_id}]:\n{log_message}")
        except Exception as e:
            self.logger.error(f"记录响应日志失败: {str(e)}")
    
    def log_error(self, request: Request, request_id: str, error: Exception, process_time: float):
        """记录错误日志"""
        try:
            error_data = {
                "request_id": request_id,
                "error_type": type(error).__name__,
                "error_message": str(error),
                "process_time_ms": round(process_time * 1000, 2),
                "request_info": {
                    "method": request.method,
                    "url": str(request.url),
                    "client_ip": request.client.host if request.client else "unknown"
                }
            }
            
            log_message = json.dumps(error_data, ensure_ascii=False, indent=2)
            self.logger.error(f"ERROR [{request_id}]:\n{log_message}")
        except Exception as e:
            self.logger.error(f"记录错误日志失败: {str(e)}")


def generate_request_id() -> str:
    """生成请求ID"""
    import uuid
    return str(uuid.uuid4())


async def fastapi_log_request_response_middleware(request: Request, call_next):
    """紧凑格式的请求和应答日志中间件（性能优化版本）"""
    import json
    from fastapi.responses import StreamingResponse, Response
    import logging
    
    # 获取日志记录器（使用根日志记录器确保有处理器）
    logger = logging.getLogger("http")
    
    # 检查是否启用 debug 日志级别
    is_debug_enabled = logger.isEnabledFor(logging.DEBUG)

    # 记录请求开始时间
    start_time = time.time()
    
    # 只在 debug 模式下获取请求体
    request_body = ""
    if is_debug_enabled:
        try:
            body = await request.body()
            if body:
                request_body = body.decode('utf-8', errors='replace')
        except:
            pass
    
    # 记录请求开始日志
    if is_debug_enabled:
        log_message = f"-> {request.method} {request.url.path} " \
                     f"headers:{dict(request.headers)} " \
                     f"body:{request_body}"
        # 截断过长的日志
        if len(log_message) > 1024:
            log_message = log_message[:1024] + "...[truncated]"
        logger.debug(log_message)
    else:
        # 非 debug 模式下只记录基本信息
        logger.info(f"-> {request.method} {request.url.path}")
    
    try:
        # 处理请求
        response = await call_next(request)
        
        # 计算处理时间
        process_time = time.time() - start_time
        
        # 只在 debug 模式下获取响应内容
        if is_debug_enabled:
            # 获取响应内容
            response_body = b""
            
            # 如果是 StreamingResponse，需要特殊处理
            if isinstance(response, StreamingResponse):
                # 收集流式响应的所有数据
                chunks = []
                async for chunk in response.body_iterator:
                    chunks.append(chunk)
                    response_body += chunk
                
                # 重新创建响应，因为原始的 body_iterator 已经被消耗
                response = Response(
                    content=response_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type
                )
            else:
                # 对于普通响应，直接获取 body
                response_body = response.body
            
            # 解析响应内容
            response_content = ""
            try:
                if isinstance(response_body, bytes):
                    response_content = response_body.decode('utf-8')
                elif isinstance(response_body, str):
                    response_content = response_body
            except UnicodeDecodeError:
                response_content = f"[binary_data_{len(response_body)}_bytes]"
            
            # 记录请求完成日志（详细格式）
            log_message = f"<- {request.method} {request.url.path} ({process_time:.3f}s) {response.status_code} " \
                         f"body:{response_content} " 
            # 截断过长的日志
            if len(log_message) > 1024:
                log_message = log_message[:1024] + "...[truncated]"
            logger.debug(log_message)
        else:
            # 非 debug 模式下只记录基本信息
            logger.info(f"<- {request.method} {request.url.path} ({process_time:.3f}s) {response.status_code}")
        
        return response
        
    except Exception as e:
        # 计算处理时间
        process_time = time.time() - start_time
        
        # 检查是否是HTTPException，如果是则不需要重复记录
        from fastapi import HTTPException
        if isinstance(e, HTTPException):
            # HTTPException已经被处理过，不需要重复记录
            pass
        else:
            # 记录未处理的错误日志
            error_message = f"请求失败: {request.method} {request.url.path} ({process_time:.3f}s) " \
                           f"error:{type(e).__name__}:{str(e)} "
            # 截断过长的日志
            if len(error_message) > 1024:
                error_message = error_message[:1024] + "...[truncated]"
            logger.error(error_message)
        
        # 重新抛出异常
        raise
