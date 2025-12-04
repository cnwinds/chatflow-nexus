#!/usr/bin/env python3
"""
Azure语音识别服务
基于Azure语音服务实现的语音识别功能
"""

import logging
import asyncio
import tempfile
import os
import json
from typing import Dict, Any, List, Optional, Callable
from functools import wraps
from pathlib import Path

try:
    import azure.cognitiveservices.speech as speechsdk
    AZURE_SPEECH_AVAILABLE = True
except ImportError:
    AZURE_SPEECH_AVAILABLE = False
    logging.warning("azure-cognitiveservices-speech 未安装，Azure STT服务将不可用")

from src.utcp.utcp import UTCPService

logger = logging.getLogger(__name__)


def handle_stt_errors(func: Callable) -> Callable:
    """装饰器：统一错误处理"""
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except Exception as e:
            logger.error(f"{func.__name__} 失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "text": "",
                "confidence": 0.0
            }
    return wrapper


class AzureSTTService(UTCPService):
    """Azure语音识别服务 - 使用Azure语音服务"""

    def init(self) -> None:
        """插件初始化方法"""
        try:
            self._load_config()
            self._validate_config()
            self.speech_config = self._create_speech_config()
        except Exception as e:
            logger.error(f"Azure STT服务初始化失败: {e}")
            self.speech_config = None
    
    def _load_config(self) -> None:
        """加载配置"""
        azure_config = self.config.get("azure_config", {})
        service_config = self.config.get("service_config", {})
        
        # Azure配置
        self.subscription_key = azure_config.get("subscription_key")
        self.region = azure_config.get("service_region", "eastus")
        
        # 服务配置
        self.language = service_config.get("default_language", "zh-CN")
        self.timeout = service_config.get("timeout", 30)
        self.enable_detailed_output = service_config.get("enable_detailed_output", False)
        self.output_format = service_config.get("output_format", "simple")
        self.max_audio_duration = service_config.get("max_audio_duration", 60)
    
    def _validate_config(self) -> None:
        """验证配置"""
        if not self.subscription_key:
            raise ValueError("未配置Azure语音服务密钥")
        
        if not AZURE_SPEECH_AVAILABLE:
            raise ValueError("Azure语音SDK未安装")
    
    def _create_speech_config(self) -> speechsdk.SpeechConfig:
        """创建Azure语音配置"""
        speech_config = speechsdk.SpeechConfig(
            subscription=self.subscription_key, 
            region=self.region
        )
        
        # 设置识别语言
        speech_config.speech_recognition_language = self.language
        
        # 设置输出格式
        if self.enable_detailed_output:
            speech_config.output_format = speechsdk.OutputFormat.Detailed
            speech_config.set_property(
                speechsdk.PropertyId.SpeechServiceResponse_RequestDetailedResultTrueFalse, 
                "true"
            )
        else:
            speech_config.output_format = speechsdk.OutputFormat.Simple
        
        logger.debug(f"Azure语音配置创建成功: {self.region}, {self.language}")
        return speech_config
    
    @property
    def name(self) -> str:
        """服务名称"""
        return "azure_stt_service"
    
    @property
    def description(self) -> str:
        """服务描述"""
        return "提供Azure语音识别功能，基于Azure语音服务"
    
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
        """返回Azure STT服务的所有工具定义"""
        return [
            self._create_tool_definition(
                "recognize_speech", "识别音频数据中的语音内容",
                {
                    "audio_data": {
                        "type": "string",
                        "description": "Base64编码的音频数据"
                    },
                    "audio_format": {
                        "type": "string",
                        "description": "音频格式（wav, mp3, opus等）",
                        "enum": ["wav", "mp3", "opus", "pcm"],
                        "default": "wav"
                    },
                    "language": {
                        "type": "string",
                        "description": "识别语言代码",
                        "default": "zh-CN"
                    }
                },
                ["audio_data"]
            ),
            
            self._create_tool_definition(
                "recognize_speech_file", "识别音频文件中的语音内容",
                {
                    "file_path": {
                        "type": "string",
                        "description": "音频文件路径"
                    },
                    "language": {
                        "type": "string",
                        "description": "识别语言代码",
                        "default": "zh-CN"
                    }
                },
                ["file_path"]
            )
        ]
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """执行Azure STT工具"""
        # 工具映射表
        tool_handlers = {
            "recognize_speech": lambda: self._recognize_speech(arguments),
            "recognize_speech_file": lambda: self._recognize_speech_file(arguments),
        }
        
        try:
            if tool_name not in tool_handlers:
                raise ValueError(f"未知的Azure STT工具: {tool_name}")
            
            return await tool_handlers[tool_name]()
        except Exception as e:
            logger.error(f"执行工具 '{tool_name}' 时出错: {e}")
            return {
                "success": False,
                "error": str(e),
                "text": "",
                "confidence": 0.0
            }
    
    @handle_stt_errors
    async def _recognize_speech(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """识别音频数据中的语音"""
        audio_data = arguments.get("audio_data")
        audio_format = arguments.get("audio_format", "wav")
        language = arguments.get("language", "zh-CN")
        
        if not audio_data:
            raise ValueError("缺少音频数据")
        
        # 直接使用音频数据
        if isinstance(audio_data, str):
            # 如果是字符串，尝试解码为字节
            audio_bytes = audio_data.encode('utf-8')
        else:
            # 如果已经是字节数据，直接使用
            audio_bytes = audio_data
        
        # 创建临时文件并识别
        with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as temp_file:
            temp_file.write(audio_bytes)
            temp_file_path = temp_file.name
        
        try:
            return await self._recognize_audio_file(temp_file_path, language)
        finally:
            self._cleanup_temp_file(temp_file_path)
    
    @handle_stt_errors
    async def _recognize_speech_file(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """识别音频文件中的语音"""
        file_path = arguments.get("file_path")
        language = arguments.get("language", "zh-CN")
        
        if not file_path:
            raise ValueError("缺少文件路径")
        
        if not os.path.exists(file_path):
            raise ValueError(f"文件不存在: {file_path}")
        
        return await self._recognize_audio_file(file_path, language)
    
    async def _recognize_audio_file(self, file_path: str, language: str) -> Dict[str, Any]:
        """识别音频文件 - 核心识别逻辑"""
        # 创建音频配置和识别器
        audio_config = speechsdk.audio.AudioConfig(filename=file_path)
        speech_recognizer = speechsdk.SpeechRecognizer(
            speech_config=self.speech_config, 
            audio_config=audio_config
        )
        
        # 执行识别
        result = await asyncio.get_event_loop().run_in_executor(
            None, 
            lambda: speech_recognizer.recognize_once_async().get()
        )
        
        # 处理识别结果
        return self._process_recognition_result(result, language)
    
    def _process_recognition_result(self, result: speechsdk.SpeechRecognitionResult, language: str) -> Dict[str, Any]:
        """处理识别结果"""
        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            return self._handle_successful_recognition(result, language)
        elif result.reason == speechsdk.ResultReason.NoMatch:
            return self._handle_no_match()
        elif result.reason == speechsdk.ResultReason.Canceled:
            return self._handle_cancellation(result)
        else:
            return self._handle_unknown_result(result)
    
    def _handle_successful_recognition(self, result: speechsdk.SpeechRecognitionResult, language: str) -> Dict[str, Any]:
        """处理成功识别"""
        recognized_text = result.text
        confidence = 0.9  # 默认置信度
        
        # 如果启用详细输出，尝试获取更多信息
        if self.enable_detailed_output:
            confidence = self._extract_confidence_from_detailed_result(result)
        
        return {
            "success": True,
            "text": recognized_text,
            "confidence": confidence,
            "language": language
        }
    
    def _extract_confidence_from_detailed_result(self, result: speechsdk.SpeechRecognitionResult) -> float:
        """从详细结果中提取置信度"""
        try:
            detailed_result_json = result.properties.get(
                speechsdk.PropertyId.SpeechServiceResponse_JsonResult
            )
            if detailed_result_json:
                detailed_result = json.loads(detailed_result_json)
                n_best = detailed_result.get('NBest', [])
                if n_best:
                    return n_best[0].get('Confidence', 0.9)
        except Exception as e:
            logger.warning(f"解析详细结果失败: {e}")
        
        return 0.9
    
    def _handle_no_match(self) -> Dict[str, Any]:
        """处理无匹配结果"""
        return {
            "success": True,
            "text": "",
            "confidence": 0.0,
            "error": ""
        }
    
    def _handle_cancellation(self, result: speechsdk.SpeechRecognitionResult) -> Dict[str, Any]:
        """处理取消结果"""
        cancellation_details = result.cancellation_details
        error_msg = f"识别被取消: {cancellation_details.reason}"
        
        if cancellation_details.reason == speechsdk.CancellationReason.Error:
            error_msg += f", 错误详情: {cancellation_details.error_details}"
        
        return {
            "success": False,
            "error": error_msg,
            "text": "",
            "confidence": 0.0
        }
    
    def _handle_unknown_result(self, result: speechsdk.SpeechRecognitionResult) -> Dict[str, Any]:
        """处理未知结果"""
        return {
            "success": False,
            "error": f"未知识别结果: {result.reason}",
            "text": "",
            "confidence": 0.0
        }
    
    def _cleanup_temp_file(self, file_path: str) -> None:
        """清理临时文件"""
        try:
            os.unlink(file_path)
        except Exception as e:
            logger.warning(f"清理临时文件失败: {e}")
    
    def is_available(self) -> bool:
        """检查服务是否可用"""
        return (AZURE_SPEECH_AVAILABLE and 
                self.speech_config is not None and 
                self.subscription_key is not None)
    
    def get_service_info(self) -> Dict[str, Any]:
        """获取服务信息"""
        return {
            "name": self.name,
            "description": self.description,
            "available": self.is_available(),
            "azure_speech_available": AZURE_SPEECH_AVAILABLE,
            "subscription_key_configured": self.subscription_key is not None,
            "region": self.region,
            "language": self.language,
            "timeout": self.timeout,
            "enable_detailed_output": self.enable_detailed_output,
            "max_audio_duration": self.max_audio_duration
        } 