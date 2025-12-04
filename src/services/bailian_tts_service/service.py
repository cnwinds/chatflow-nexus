#!/usr/bin/env python3
"""
百炼 TTS服务
基于阿里云百炼平台的文本转语音服务
提供文本转语音、SSML支持、情感表达等功能
支持CosyVoice模型和SSML标记语言

百炼平台文档：
https://bailian.console.aliyun.com/?tab=doc#/doc/?type=model&url=2842586
https://help.aliyun.com/zh/model-studio/introduction-to-cosyvoice-ssml-markup-language
"""

import logging
import asyncio
import io
import base64
import time
from typing import Dict, Any, Optional, List, Callable
from functools import wraps
from concurrent.futures import ThreadPoolExecutor
import json

try:
    import dashscope
    from dashscope.audio.tts_v2 import *
    DASHSCOPE_AVAILABLE = True
except ImportError:
    DASHSCOPE_AVAILABLE = False
    logging.warning("dashscope SDK未安装，TTS服务将不可用")

from src.utcp.utcp import UTCPService
from src.utcp.streaming import LocalStreamResponse, StreamType, StreamMetadata

logger = logging.getLogger(__name__)


def handle_tts_errors(func: Callable) -> Callable:
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
                "audio_data": "",
                "audio_size": 0
            }
    return wrapper


class BailianTTSService(UTCPService):
    """百炼 TTS服务 - 基于阿里云百炼平台"""

    def init(self) -> None:
        """插件初始化方法"""
        try:
            self._validate_dependencies()
            self._load_config()
            self._setup_logging()
            self._initialize_executor()
            self._initialize_stats()
        except Exception as e:
            logger.error(f"百炼 TTS服务初始化失败: {e}")
            raise
    
    def _validate_dependencies(self) -> None:
        """验证依赖"""
        if not DASHSCOPE_AVAILABLE:
            raise ImportError("dashscope SDK未安装，请运行: pip install dashscope")
    
    def _load_config(self) -> None:
        """加载配置"""
        # 服务配置
        self.service_config = self.config.get("service_config", {})
        self.bailian_config = self.config.get("bailian_config", {})
        self.voice_config = self.config.get("voice_config", {})
        self.logging_config = self.config.get("logging", {})
        self.validation_config = self.config.get("validation", {})
        
        # 百炼平台配置
        self.api_key = self.bailian_config.get("api_key", "")
        
        # 设置dashscope API Key
        if self.api_key:
            dashscope.api_key = self.api_key
        
        # 服务配置
        self.default_voice = self.service_config.get("default_voice", "longhuhu")
        self.audio_format = "opus"
        self.enable_ssml = self.service_config.get("enable_ssml", True)
        self.max_text_length = self.service_config.get("max_text_length", 5000)
        self.timeout = self.service_config.get("timeout", 30)
        
        # 语音配置
        self.available_voices = self.voice_config.get("available_voices", {})
        self.model_name = self.voice_config.get("model_name", "cosyvoice-1.5")
        
        # 验证必需配置
        if not self.api_key:
            raise ValueError("百炼 TTS服务需要 api_key 配置")
    
    def _setup_logging(self) -> None:
        """设置日志配置"""
        log_level = self.logging_config.get("level", "INFO")
        
        # 设置日志级别
        numeric_level = getattr(logging, log_level.upper(), logging.INFO)
        logger.setLevel(numeric_level)
        
        # 存储日志配置
        self.log_level = log_level
    
    def _initialize_executor(self) -> None:
        """初始化线程池"""
        self.executor = ThreadPoolExecutor(max_workers=10)
    
    def _initialize_stats(self) -> None:
        """初始化统计信息"""
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_characters": 0,
            "total_audio_duration": 0.0
        }
    
    @property
    def name(self) -> str:
        """服务名称"""
        return "bailian_tts_service"
    
    @property
    def description(self) -> str:
        """服务描述"""
        return "基于阿里云百炼平台的文本转语音服务，支持CosyVoice模型和SSML标记语言"
    
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
        """获取可用工具列表"""
        return [
            self._create_tool_definition(
                "synthesize_speech", "将文本转换为语音",
                {
                    "text": {
                        "type": "string",
                        "description": "要转换的文本内容"
                    },
                    "voice": {
                        "type": "string",
                        "description": "语音名称（可选）"
                    },
                    "emotion": {
                        "type": "string",
                        "description": "情感类型（可选），如果平台不支持则忽略"
                    },
                    "voice_params": {
                        "type": "object",
                        "description": "语音参数（可选），支持rate（语速）、pitch（音高）、range（音高范围）、volume（音量）、contour（音高轮廓）"
                    }
                },
                ["text"]
            ),
            
            self._create_tool_definition(
                "synthesize_speech_stream", "流式将文本转换为语音，实时返回音频块",
                {
                    "text": {
                        "type": "string",
                        "description": "要转换的文本内容"
                    },
                    "voice": {
                        "type": "string",
                        "description": "语音名称（可选）"
                    },
                    "emotion": {
                        "type": "string",
                        "description": "情感类型（可选），如果平台不支持则忽略"
                    },
                    "voice_params": {
                        "type": "object",
                        "description": "语音参数（可选），支持rate（语速）、pitch（音高）、range（音高范围）、volume（音量）、contour（音高轮廓）"
                    }
                },
                ["text"]
            ),
            
            self._create_tool_definition(
                "get_available_voices", "获取可用的语音列表",
                {
                    "language": {
                        "type": "string",
                        "description": "语言代码（可选）",
                        "enum": ["zh-CN", "en-US"]
                    }
                }
            ),
            
            self._create_tool_definition(
                "get_service_status", "获取服务状态和统计信息",
                {}
            )
        ]
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """调用工具"""
        # 工具映射表
        tool_handlers = {
            "synthesize_speech": lambda: self._synthesize_speech_tool(arguments),
            "get_available_voices": lambda: self._get_available_voices_tool(arguments),
            "get_service_status": lambda: self._get_service_status_tool(arguments)
        }
        
        try:
            if tool_name not in tool_handlers:
                raise ValueError(f"未知工具: {tool_name}")
            
            return await tool_handlers[tool_name]()
        except Exception as e:
            logger.error(f"执行工具 '{tool_name}' 时出错: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def call_tool_stream(self, tool_name: str, arguments: Dict[str, Any]):
        """调用流式工具"""
        try:
            if tool_name == "synthesize_speech_stream":
                return await self._synthesize_speech_stream(arguments)
            else:
                raise ValueError(f"工具 '{tool_name}' 不支持流式调用")
        except Exception as e:
            logger.error(f"执行流式工具 '{tool_name}' 时出错: {e}")
            # 返回错误流
            async def error_generator():
                yield {
                    "success": False,
                    "error": str(e),
                    "audio_data": b"",
                    "chunk_index": 0,
                    "total_size": 0
                }
            
            return LocalStreamResponse(
                error_generator(),
                StreamType.JSON,
                "application/json",
                StreamMetadata()
            )
    
    def supports_streaming(self, tool_name: str) -> bool:
        """检查工具是否支持流式调用"""
        return tool_name == "synthesize_speech_stream"
    
    def _validate_text_length(self, text: str) -> str:
        """验证文本长度"""
        if len(text) > self.max_text_length:
            logger.warning(f"文本长度超过限制: {len(text)} > {self.max_text_length}")
            return text[:self.max_text_length]
        return text
    
    def _validate_voice(self, voice: Optional[str]) -> str:
        """验证语音是否支持，不支持则返回默认语音
        
        Args:
            voice: 要验证的语音名称
            
        Returns:
            验证后的语音名称（如果传入的语音不支持，则返回默认语音）
        """
        if not voice:
            return self.default_voice
        
        # 获取所有可用语音列表
        all_available_voices = self._get_available_voices()
        
        # 检查语音是否在可用列表中
        if voice not in all_available_voices:
            logger.warning(f"语音 '{voice}' 不在可用列表中，将使用默认语音 '{self.default_voice}'")
            return self.default_voice
        
        return voice
    
    def _create_ssml(self, text: str, voice: Optional[str] = None, 
                    emotion: Optional[str] = None, voice_params: Optional[Dict[str, Any]] = None) -> str:
        """创建SSML标记（百炼平台CosyVoice SSML格式）
        
        根据文档：https://help.aliyun.com/zh/model-studio/introduction-to-cosyvoice-ssml-markup-language
        百炼平台的SSML格式简单，属性直接设置在<speak>标签上，不需要嵌套标签。
        
        Args:
            text: 要转换的文本内容
            voice: 语音名称
            emotion: 情感类型（可选），如果平台不支持则忽略
            voice_params: 语音参数（可选），支持rate、pitch、volume等
        
        Returns:
            SSML格式的字符串
        """
        # 验证语音是否支持，不支持则切回默认语音
        voice = self._validate_voice(voice)
        
        # 构建<speak>标签的属性
        attrs = []
        
        # voice属性：指定发音人（音色）
        if voice:
            attrs.append(f'voice="{voice}"')
        
        # 处理voice_params，转换为<speak>标签的属性
        if voice_params and isinstance(voice_params, dict):
            # rate: 语速 [0.5,2]之间的小数
            if "rate" in voice_params:
                rate = voice_params["rate"]
                attrs.append(f'rate="{rate}"')
            
            # pitch: 音高 [0.5,2]之间的小数
            if "pitch" in voice_params:
                pitch = voice_params["pitch"]
                attrs.append(f'pitch="{pitch}"')
            
            # volume: 音量 [0,100]之间的整数
            if "volume" in voice_params:
                volume = voice_params["volume"]
                attrs.append(f'volume="{volume}"')
            
            # effect: 音效（robot、lolita、lowpass、echo等）
            if "effect" in voice_params:
                effect = voice_params["effect"]
                attrs.append(f'effect="{effect}"')
        
        # 转义XML特殊字符
        def escape_xml(text: str) -> str:
            """转义XML特殊字符"""
            text = text.replace("&", "&amp;")
            text = text.replace("<", "&lt;")
            text = text.replace(">", "&gt;")
            text = text.replace('"', "&quot;")
            text = text.replace("'", "&apos;")
            return text
        
        # 转义文本中的特殊字符
        escaped_text = escape_xml(text)
        
        # 构建SSML字符串
        # 百炼平台只需要简单的<speak>标签，不需要命名空间和版本号
        if attrs:
            attrs_str = " ".join(attrs)
            ssml = f'<speak {attrs_str}>{escaped_text}</speak>'
        else:
            ssml = f'<speak>{escaped_text}</speak>'
        
        return ssml
    
    def _call_bailian_api_sync(self, text: str, voice: Optional[str] = None, 
                               emotion: Optional[str] = None, voice_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """同步调用百炼平台TTS API（使用dashscope SDK）"""
        # 验证语音是否支持，不支持则切回默认语音
        voice = self._validate_voice(voice)
        
        # 如果有voice_params，使用SSML格式
        # 注意：emotion参数会被忽略，因为百炼平台可能不支持
        use_ssml = voice_params and self.enable_ssml
        
        if use_ssml:
            # 使用SSML格式，voice参数包含在SSML中
            input_text = self._create_ssml(text, voice, emotion, voice_params)
        else:
            # 不使用SSML，直接使用文本
            input_text = text
        
        try:
            logger.debug(f"百炼TTS调用: model={self.model_name}, voice={voice}, use_ssml={use_ssml}, input_text={input_text[:100] if len(input_text) > 100 else input_text}")
            
            # 实例化SpeechSynthesizer，在构造方法中传入model和voice
            # 如果使用SSML格式，voice参数仍然需要在构造时传入（虽然SSML中也会包含voice）
            synthesizer = SpeechSynthesizer(model=self.model_name, voice=voice, format=AudioFormat.OGG_OPUS_16KHZ_MONO_16KBPS)
            
            # 调用call方法，只传入文本，返回音频数据（bytes）
            audio_data = synthesizer.call(input_text)
            
            if audio_data:
                # 获取请求ID和首包延迟等指标
                request_id = synthesizer.get_last_request_id()
                first_package_delay = synthesizer.get_first_package_delay()
                
                logger.debug(f"百炼TTS合成成功: requestId={request_id}, 首包延迟={first_package_delay}毫秒, 音频大小={len(audio_data)}字节")
                
                return {
                    "success": True,
                    "audio_data": audio_data,
                    "audio_size": len(audio_data),
                    "format": "opus",  # 固定返回opus格式
                    "request_id": request_id,
                    "first_package_delay": first_package_delay
                }
            else:
                raise ValueError("API返回的音频数据为空")
                
        except Exception as e:
            # 其他错误
            error_msg = str(e)
            logger.error(f"百炼TTS API调用失败: model={self.model_name}, voice={voice}, use_ssml={use_ssml}, input_text_preview={input_text[:50]}, error={error_msg}")
            raise Exception(f"API调用失败: {error_msg}")
    
    async def _call_bailian_api(self, text: str, voice: Optional[str] = None, 
                                emotion: Optional[str] = None, voice_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """异步调用百炼平台TTS API"""
        # 在线程池中执行同步调用
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self.executor,
            self._call_bailian_api_sync,
            text,
            voice,
            emotion,
            voice_params
        )
        return result
    
    async def synthesize_speech(self, text: str, voice: Optional[str] = None, 
                               emotion: Optional[str] = None, voice_params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """合成语音"""
        self.stats["total_requests"] += 1
        self.stats["total_characters"] += len(text)
        
        start_time = time.time()
        actual_voice = voice or self.default_voice
        
        try:
            # 验证文本长度
            text = self._validate_text_length(text)
            
            # 调用API（emotion参数会被忽略，如果平台不支持）
            result = await self._call_bailian_api(text, actual_voice, emotion, voice_params)
            
            if result.get("success"):
                execution_time = time.time() - start_time
                
                # 估算音频时长（基于文本长度）
                estimated_duration = len(text) / (150 / 60)  # 假设150字/分钟
                self.stats["total_audio_duration"] += estimated_duration
                self.stats["successful_requests"] += 1
                
                logger.info(f"生成文本: {text[:50]}... 语音: {actual_voice} 音频大小: {result['audio_size']}字节, 生成时间: {execution_time:.3f}秒")
                
                result["execution_time"] = execution_time
                result["audio_duration"] = estimated_duration
                result["text_length"] = len(text)
                result["voice"] = actual_voice
                
                return result
            else:
                self.stats["failed_requests"] += 1
                logger.error(f"语音合成失败: {result.get('error', '未知错误')}")
                return None
                
        except Exception as e:
            self.stats["failed_requests"] += 1
            logger.error(f"语音合成异常: {e}")
            return None
    
    async def synthesize_speech_stream(self, text: str, voice: Optional[str] = None, 
                                      emotion: Optional[str] = None, voice_params: Optional[Dict[str, Any]] = None):
        """流式合成语音"""
        self.stats["total_requests"] += 1
        self.stats["total_characters"] += len(text)
        
        start_time = time.time()
        actual_voice = voice or self.default_voice
        
        try:
            # 验证文本长度
            text = self._validate_text_length(text)
            
            # 调用API（百炼平台可能不支持真正的流式，这里先返回完整音频）
            # emotion参数会被忽略，如果平台不支持
            result = await self._call_bailian_api(text, actual_voice, emotion, voice_params)
            
            if result.get("success"):
                audio_data = result["audio_data"]
                audio_size = len(audio_data)
                
                # 将音频数据分块返回（模拟流式）
                chunk_size = 8192  # 8KB每块
                chunk_count = 0
                
                for i in range(0, audio_size, chunk_size):
                    chunk = audio_data[i:i + chunk_size]
                    chunk_count += 1
                    
                    yield {
                        "success": True,
                        "type": "audio_chunk",
                        "audio_chunk": chunk,
                        "chunk_index": chunk_count,
                        "total_size": audio_size,
                        "chunk_size": len(chunk)
                    }
                
                # 发送最终元数据
                execution_time = time.time() - start_time
                estimated_duration = len(text) / (150 / 60)
                self.stats["total_audio_duration"] += estimated_duration
                self.stats["successful_requests"] += 1
                
                yield {
                    "success": True,
                    "type": "metadata",
                    "audio_size": audio_size,
                    "text_length": len(text),
                    "voice": actual_voice,
                    "audio_duration": estimated_duration,
                    "execution_time": execution_time,
                    "chunk_count": chunk_count,
                    "audio_format": result.get("format", self.audio_format)
                }
            else:
                self.stats["failed_requests"] += 1
                yield {
                    "success": False,
                    "error": result.get("error", "未知错误")
                }
                
        except Exception as e:
            self.stats["failed_requests"] += 1
            logger.error(f"流式语音合成异常: {e}")
            yield {
                "success": False,
                "error": str(e)
            }
    
    def _get_available_voices(self, language: Optional[str] = None) -> List[str]:
        """获取可用语音列表"""
        if language:
            return self.available_voices.get(language, [])
        else:
            # 返回所有语音
            all_voices = []
            for voices in self.available_voices.values():
                all_voices.extend(voices)
            return all_voices
    
    @handle_tts_errors
    async def _synthesize_speech_tool(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """合成语音工具"""
        text = arguments.get("text", "")
        voice = arguments.get("voice") or self.default_voice
        emotion = arguments.get("emotion")
        voice_params = arguments.get("voice_params")
        
        if not text:
            raise ValueError("文本内容不能为空")
        
        # emotion参数会被忽略，如果平台不支持
        result = await self.synthesize_speech(text, voice, emotion, voice_params)
        
        if result:
            return {
                "success": True,
                "audio_data": result["audio_data"],
                "audio_size": result["audio_size"],
                "text_length": result["text_length"],
                "voice": result["voice"],
                "audio_duration": result["audio_duration"],
                "execution_time": result["execution_time"],
                "audio_format": result.get("format", self.audio_format)
            }
        else:
            raise ValueError("语音合成失败")
    
    async def _synthesize_speech_stream(self, arguments: Dict[str, Any]):
        """流式合成语音工具"""
        text = arguments.get("text", "")
        voice = arguments.get("voice") or self.default_voice
        emotion = arguments.get("emotion")
        voice_params = arguments.get("voice_params")
        
        if not text:
            raise ValueError("文本内容不能为空")
        
        async def audio_stream_generator():
            try:
                # emotion参数会被忽略，如果平台不支持
                async for chunk_data in self.synthesize_speech_stream(text, voice, emotion, voice_params):
                    yield chunk_data
            except Exception as e:
                logger.error(f"流式音频生成失败: {e}")
                yield {
                    "success": False,
                    "error": str(e),
                }
        
        return LocalStreamResponse(
            audio_stream_generator(),
            StreamType.JSON,
            "application/json",
            StreamMetadata()
        )
    
    async def _get_available_voices_tool(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """获取可用语音工具"""
        language = arguments.get("language")
        voices = self._get_available_voices(language)
        
        return {
            "success": True,
            "voices": voices,
            "language": language,
            "total_count": len(voices)
        }
    
    async def _get_service_status_tool(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """获取服务状态工具"""
        return {
            "success": True,
            "service_name": self.name,
            "status": "running",
            "stats": self.stats.copy(),
            "config": {
                "default_voice": self.default_voice,
                "audio_format": "opus",
                "enable_ssml": self.enable_ssml,
                "max_text_length": self.max_text_length,
                "timeout": self.timeout,
                "model_name": self.model_name,
                "log_level": self.log_level,
            }
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """获取服务统计信息"""
        return self.stats.copy()
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        self._initialize_stats()
    
    async def close(self) -> None:
        """关闭服务"""
        # 关闭线程池
        if hasattr(self, 'executor') and self.executor:
            self.executor.shutdown(wait=True)
        
        logger.info("BailianTTSService已关闭")
    
    def __del__(self):
        """析构函数"""
        # 注意：这里不能使用await，所以只是记录日志
        if hasattr(self, 'executor') and self.executor:
            self.executor.shutdown(wait=False)

