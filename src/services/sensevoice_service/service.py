#!/usr/bin/env python3
"""
本地语音识别服务 (Local STT Service)
基于本地语音识别服务实现的语音识别功能，支持LID、SER、AEC功能

功能特性:
- 语音识别: 支持多种音频格式的语音转文字
- 语种识别 (LID): 自动检测语音中的语言类型
- 语音情感识别 (SER): 识别语音中的情感状态  
- 声学事件分类 (AEC): 检测和分类环境中的声学事件

支持的标签格式:
- 语种: <|语言代码|> - 模型返回的语言代码
- 情感: <|EMO_情感|> - 模型返回的情感状态
- 事件: <|事件名称|> - 模型返回的声学事件

所有标签值以模型实际返回为准，不做枚举限制。

原始数据格式示例:
{
    'result': [
        {
            'key': 'tmp7notzs6h', 
            'text': '🎼', 
            'raw_text': '<|en|><|EMO_UNKNOWN|><|BGM|><|woitn|>', 
            'clean_text': ''
        }
    ]
}

返回数据格式示例:
{
    "success": true,
    "text": "识别的文本",
    "confidence": 0.95,
    "language": "zh-CN",
    "raw_text": "<|zh|en|><|EMO_HAPPY|EMO_EXCITED|><|BGM|LAUGHTER|MUSIC|><|识别的文本|>",
    "clean_text": "识别的文本",
    "lid": ["zh", "en"],
    "ser": ["EMO_HAPPY", "EMO_EXCITED"],
    "aec": ["BGM", "LAUGHTER", "MUSIC"]
}

返回格式:
- 基础字段: success, text, confidence, language, raw_text, clean_text
- 详细标签: lid, ser, aec (数组格式，支持|分隔的多个值)
- 所有标签值以模型实际返回为准，不做枚举限制

功能特性:
- 语种识别 (LID): 自动检测语音中的语言类型，支持多语言
- 语音情感识别 (SER): 识别语音中的情感状态，支持多情感
- 声学事件分类 (AEC): 检测和分类环境中的声学事件，支持多事件
"""

import logging
import asyncio
import tempfile
import os
import json
import requests
from typing import Dict, Any, List, Optional, Callable
from functools import wraps
from pathlib import Path

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
                "confidence": 0.0,
                "char_list": [],
                "char_confidences": []
            }
    return wrapper


class SenseVoiceService(UTCPService):
    """SenseVoice语音识别服务 - 使用本地语音识别服务"""

    def init(self) -> None:
        """插件初始化方法"""
        try:
            self._load_config()
            self._validate_config()
        except Exception as e:
            logger.error(f"Local STT服务初始化失败: {e}")
            self.server_url = None
    
    def _load_config(self) -> None:
        """加载配置"""
        service_config = self.config.get("service_config", {})
        
        # 服务配置
        self.server_url = service_config.get("server_url", "http://192.168.23.220:50000")
        self.timeout = service_config.get("timeout", 30)
    
    def _validate_config(self) -> None:
        """验证配置"""
        if not self.server_url:
            raise ValueError("未配置本地语音识别服务地址")
    
    @property
    def name(self) -> str:
        """服务名称"""
        return "sensevoice_service"
    
    @property
    def description(self) -> str:
        """服务描述"""
        return "提供SenseVoice语音识别功能，基于本地语音识别服务"
    
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
        """返回Local STT服务的所有工具定义"""
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
        """执行Local STT工具"""
        # 工具映射表
        tool_handlers = {
            "recognize_speech": lambda: self._recognize_speech(arguments),
            "recognize_speech_file": lambda: self._recognize_speech_file(arguments),
        }
        
        try:
            if tool_name not in tool_handlers:
                raise ValueError(f"未知的Local STT工具: {tool_name}")
            
            return await tool_handlers[tool_name]()
        except Exception as e:
            logger.error(f"执行工具 '{tool_name}' 时出错: {e}")
            return {
                "success": False,
                "error": str(e),
                "text": "",
                "confidence": 0.0,
                "char_list": [],
                "char_confidences": []
            }
    
    @handle_stt_errors
    async def _recognize_speech(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """识别音频数据中的语音"""
        audio_data = arguments.get("audio_data")
        audio_format = arguments.get("audio_format", "wav")
        language = arguments.get("language", "zh")
        
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
        try:
            # 准备请求数据
            with open(file_path, 'rb') as f:
                files_data = [('files', (os.path.basename(file_path), f.read(), 'audio/wav'))]
            
            # 生成文件键名
            key = os.path.splitext(os.path.basename(file_path))[0]
            
            form_data = {
                'keys': key,
                'lang': language
            }

            # 发送请求到本地语音识别服务
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: requests.post(
                    f"{self.server_url.rstrip('/')}/api/v1/asr",
                    files=files_data,
                    data=form_data,
                    timeout=self.timeout
                )
            )
            
            response.raise_for_status()
            result = response.json()
            
            # 处理识别结果
            return self._process_recognition_result(result, language)
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"请求本地语音识别服务失败: {e}")
        except Exception as e:
            raise Exception(f"识别音频文件失败: {e}")
    
    def _process_recognition_result(self, result: Dict[str, Any], language: str) -> Dict[str, Any]:
        """处理识别结果"""
        try:
            # 解析本地服务的响应格式
            results = result.get("result", [])
            if not results:
                return {
                    "success": True,
                    "text": "",
                    "confidence": 0.0,
                    "language": language,
                    "char_list": [],
                    "char_confidences": []
                }
            
            # 获取第一个识别结果
            first_result = results[0]
            recognized_text = first_result.get('text', '')
            raw_text = first_result.get('raw_text', '')
            clean_text = first_result.get('clean_text', '')
            confidence = first_result.get('confidence', 0.9)  # 默认置信度
            char_list = first_result.get('char_list', [])
            char_confidences = first_result.get('char_confidences', [])
            
            # 基础返回结果
            base_result = {
                "success": True,
                "text": recognized_text,
                "confidence": confidence,
                "language": language,
                "char_list": char_list,
                "char_confidences": char_confidences
            }
            
            # 解析LID、SER、AEC信息（始终返回详细标签字段）
            if raw_text:
                parsed_info = self._parse_raw_text(raw_text)
                base_result.update(parsed_info)
                base_result["raw_text"] = raw_text
                base_result["clean_text"] = clean_text
            
            return base_result
            
        except Exception as e:
            logger.error(f"处理识别结果失败: {e}")
            return {
                "success": False,
                "error": f"处理识别结果失败: {e}",
                "text": "",
                "confidence": 0.0,
                "char_list": [],
                "char_confidences": []
            }
    
    def _parse_raw_text(self, raw_text: str) -> Dict[str, Any]:
        """解析原始文本中的LID、SER、AEC信息"""
        import re
        
        # 使用一个正则表达式匹配所有标签
        pattern = r'<\|([^|]+)\|>'
        matches = re.findall(pattern, raw_text)
        
        parsed_info = {}
        
        if matches:
            # 按位置获取内容：第一个是语言，第二个是情感，其余是事件
            if len(matches) >= 1:
                # 语言支持|拆分
                languages = [lang.strip() for lang in matches[0].split("|") if lang.strip()]
                parsed_info["lid"] = languages
            
            if len(matches) >= 2:
                # 情感支持|拆分
                emotions = [emo.strip() for emo in matches[1].split("|") if emo.strip()]
                parsed_info["ser"] = emotions
            
            if len(matches) >= 3:
                # 事件支持|拆分
                all_events = "|".join(matches[2:])
                events = [event.strip() for event in all_events.split("|") if event.strip()]
                parsed_info["aec"] = events
        
        return parsed_info
    
    
    
    def _cleanup_temp_file(self, file_path: str) -> None:
        """清理临时文件"""
        try:
            os.unlink(file_path)
        except Exception as e:
            logger.warning(f"清理临时文件失败: {e}")
    
    def is_available(self) -> bool:
        """检查服务是否可用"""
        try:
            response = requests.get(f"{self.server_url.rstrip('/')}/", timeout=5)
            return (self.server_url is not None and 
                    response.status_code == 200)
        except:
            return False
    
    def get_service_info(self) -> Dict[str, Any]:
        """获取服务信息"""
        return {
            "name": self.name,
            "description": self.description,
            "available": self.is_available(),
            "server_url": self.server_url,
            "timeout": self.timeout
        }
