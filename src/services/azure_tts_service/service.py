#!/usr/bin/env python3
"""
Azure TTS服务
基于Azure Cognitive Services的文本转语音服务
提供文本转语音、SSML支持、情感表达等功能
支持默认语音和自定义语音（个人语音克隆）

# 调整韵律
https://learn.microsoft.com/zh-cn/azure/ai-services/speech-service/speech-synthesis-markup-voice#adjust-prosody

Attribute: contour
说明: 升降曲线表示音高的变化。这些变化以语音输出中指定时间处的目标数组形式表示。参数对集定义每个目标。
示例: <prosody contour="(0%,+20Hz) (10%,-2st) (40%,+10Hz)">
     每参数集中的第一个值以文本持续时间百分比的形式指定音节变化的位置。
     第二个值使用音节的相对值或枚举值指定音节的升高或降低量（请参阅 pitch）。
     音高升降曲线不适用于单个单词和简短短语。建议调整整个句子或长短语的音调轮廓。

Attribute: pitch
说明: 指示文本的基线音节。可以在句子级别应用音高更改。音调变化应为原始音频的 0.5 到 1.5 倍。
表达方式:
    1. 绝对值：以某个数字后接"Hz"（赫兹）表示
       示例: <prosody pitch="600Hz">some text</prosody>
    2. 相对值：
       - 以相对数字表示：以前面带有"+"或"-"且后接"Hz"或"st"的数字表示
         示例: <prosody pitch="+80Hz">some text</prosody> 或 <prosody pitch="-2st">some text</prosody>
         （"st"表示变化单位为半音，即标准全音阶中的半调）
       - 以百分比表示：以"+"（可选）或"-"开头且后跟"%"的数字表示
         示例: <prosody pitch="50%">some text</prosody> 或 <prosody pitch="-50%">some text</prosody>
    3. 常量值：
       - x-low（相当于 0.55，-45%）
       - low（相当于 0.8，-20%）
       - medium（相当于 1，默认值）
       - high（相当于 1.2，+20%）
       - x-high（相当于 1.45，+45%）

Attribute: range
说明: 表示文本音节范围的值。可使用用于描述 range 的相同绝对值、相对值或枚举值表示 pitch。

Attribute: rate
说明: 指示文本的讲出速率。可在字词或句子层面应用语速。语速变化应在原始音频的 0.5 到 2 倍范围内。
表达方式:
    1. 相对值：
       - 作为相对数值：表示为一个用作默认值乘数的数字
         例如：如果值为 1，则原始速率不会变化；如果值为 0.5，则速率为原始速率的一半；
         如果值为 2，则速率为原始速率的 2 倍
       - 以百分比表示：以"+"（可选）或"-"开头且后跟"%"的数字表示
         示例: <prosody rate="50%">some text</prosody> 或 <prosody rate="-50%">some text</prosody>
    2. 常量值：
       - x-slow（相当于 0.5，-50%）
       - slow（相当于 0.64，-46%）
       - medium（相当于 1，默认值）
       - fast（相当于 1.55，+55%）
       - x-fast（相当于 2，+100%）

Attribute: volume
说明: 指示语音的音量级别。可以在句子级别应用音量更改。
表达方式:
    1. 绝对值：以从 0.0 到 100.0 的数字表示（从最安静到最大声，例如 75）。默认值是 100.0
    2. 相对值：
       - 作为相对数值：表示为一个前面带有"+"或"-"的数字，用于指定音量的变化量
         示例: +10 或 -5.5
       - 以百分比表示：以"+"（可选）或"-"开头且后跟"%"的数字表示
         示例: <prosody volume="50%">some text</prosody> 或 <prosody volume="+3%">some text</prosody>
    3. 常量值：
       - silent（相当于 0）
       - x-soft（相当于 0.2）
       - soft（相当于 0.4）
       - medium（相当于 0.6）
       - loud（相当于 0.8）
       - x-loud（相当于 1，默认值）
"""

import logging
import asyncio
import io
import numpy as np
import base64
import struct
from typing import Dict, Any, Optional, List, Tuple, Callable
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from contextlib import contextmanager

try:
    import azure.cognitiveservices.speech as speechsdk
    AZURE_SPEECH_AVAILABLE = True
except ImportError:
    AZURE_SPEECH_AVAILABLE = False
    logging.warning("Azure Speech SDK未安装，TTS服务将不可用")

from src.utcp.utcp import UTCPService

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


class AzureTTSService(UTCPService):
    """Azure TTS服务 - 基于Azure Cognitive Services"""

    def init(self) -> None:
        """插件初始化方法"""
        try:
            self._validate_dependencies()
            self._load_config()
            self._setup_logging()
            self._initialize_executor()
            self._initialize_stats()
            self._initialize_default_speech_config()
            self._initialize_synthesizer_pool()
        except Exception as e:
            logger.error(f"Azure TTS服务初始化失败: {e}")
            raise
    
    def _validate_dependencies(self) -> None:
        """验证依赖"""
        if not AZURE_SPEECH_AVAILABLE:
            raise ImportError("Azure Speech SDK未安装，请运行: pip install azure-cognitiveservices-speech")
    
    def _load_config(self) -> None:
        """加载配置"""
        # 服务配置
        self.service_config = self.config.get("service_config", {})
        self.azure_config = self.config.get("azure_config", {})
        self.voice_config = self.config.get("voice_config", {})
        self.logging_config = self.config.get("logging", {})
        self.validation_config = self.config.get("validation", {})
        
        # 初始化情绪验证字典
        self._init_emotion_validation()
        
        # Azure配置
        self.subscription_key = self.azure_config.get("subscription_key", "")
        self.service_region = self.azure_config.get("service_region", "eastus")
        self.endpoint = self.azure_config.get("endpoint", "")
        self.enable_logging = self.azure_config.get("enable_logging", True)
        # 服务配置
        self.default_voice = self.service_config.get("default_voice", "zh-CN-YunxiNeural")
        self.default_language = self.service_config.get("default_language", "zh-CN")
        self.sample_rate = self.service_config.get("sample_rate", 16000)
        self.audio_format = "opus"
        self.enable_emotion = self.service_config.get("enable_emotion", True)
        self.max_text_length = self.service_config.get("max_text_length", 5000)
        self.timeout = self.service_config.get("timeout", 30)
        self.enable_custom_voice = self.service_config.get("enable_custom_voice", True)
        self.custom_voice_style = self.service_config.get("custom_voice_style", "Prompt")
        
        # 语音配置
        self.available_voices = self.voice_config.get("available_voices", {})
        self.default_emotions = self.voice_config.get("default_emotions", {})
        self.custom_voice_config = self.voice_config.get("custom_voice_config", {})
        
        # 优化配置
        self.optimization_config = self.config.get("optimization", {})
        self.enable_connection_pool = self.optimization_config.get("enable_connection_pool", True)
        self.enable_connection_prewarming = self.optimization_config.get("enable_connection_prewarming", True)
        self.connection_pool_size = self.optimization_config.get("connection_pool_size", 5)
    
    def _init_emotion_validation(self) -> None:
        """初始化情绪验证字典"""
        self.valid_emotions = {
            "advertisement_upbeat": "表达一种兴奋和高能量的语气来推销产品或服务",
            "affectionate": "语调温暖亲切，音调较高，声音充满活力",
            "angry": "表达愤怒和恼怒的语气",
            "assistant": "为数字助理表达一种温暖而轻松的语气",
            "calm": "说话时表现出冷静、沉着、镇定的态度",
            "chat": "表达一种随意、轻松的语气",
            "cheerful": "表达积极、快乐的语气",
            "customerservice": "以友好、乐于助人的语气为客户支持",
            "depressed": "以较低的音调和能量表达忧郁和沮丧的语调",
            "disgruntled": "表达一种轻蔑和抱怨的语气",
            "documentary-narration": "以轻松、有趣和信息丰富的风格讲述纪录片",
            "embarrassed": "当说话者感到不舒服时，表达不确定和犹豫的语气",
            "empathetic": "表达一种关心和理解的感觉",
            "envious": "当你渴望得到别人拥有的东西时，表达一种钦佩的语气",
            "excited": "表达一种乐观向上、充满希望的语气",
            "fearful": "表达一种害怕和紧张的语气",
            "friendly": "表达一种愉快、热情和温暖的语气",
            "gentle": "表达温和、礼貌、愉快的语调",
            "hopeful": "表达一种温暖而渴望的语气",
            "lyrical": "以旋律优美、感伤的方式表达情感",
            "narration-professional": "表达内容阅读的专业、客观的语气",
            "narration-relaxed": "表达一种舒缓而悦耳的语调来阅读内容",
            "newscast": "表达叙述新闻的正式和专业的语气",
            "newscast-casual": "表达一般新闻传递的多变而随意的语气",
            "newscast-formal": "表达正式、自信和权威的新闻传递语气",
            "poetry-reading": "朗读诗歌时表达情感和节奏感",
            "sad": "表達出悲恸的語音",
            "serious": "表达严厉而命令的语气",
            "shouting": "表达一种听起来好像声音来自遥远的地方或另一个地方的语调",
            "sports_commentary": "表达出一种轻松而有趣的体育赛事转播语气",
            "sports_commentary_excited": "表达一种强烈而充满活力的语气，用于播报体育赛事中激动人心的时刻",
            "whispering": "表达一种试图发出安静、柔和声音的柔和音调",
            "terrified": "表达一种恐惧的语气，语速较快，声音颤抖",
            "unfriendly": "表达出一种冷漠、漠不关心的语气"
        }
        
        logger.debug(f"情绪验证字典初始化完成，支持 {len(self.valid_emotions)} 种情绪")
    
    def _validate_emotion(self, emotion: str) -> bool:
        """验证情绪是否有效"""
        if not emotion:
            return True  # 空情绪是允许的
        
        if emotion not in self.valid_emotions:
            logger.warning(f"无效的情绪: {emotion}，支持的情绪: {list(self.valid_emotions.keys())}")
            return False
        
        logger.debug(f"情绪验证通过: {emotion} - {self.valid_emotions[emotion]}")
        return True
    
    def _get_emotion_description(self, emotion: str) -> str:
        """获取情绪描述"""
        return self.valid_emotions.get(emotion, "未知情绪")
    
    def _get_available_emotions(self) -> dict:
        """获取所有可用的情绪"""
        return self.valid_emotions.copy()
    
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
        self.executor = ThreadPoolExecutor(max_workers=self.connection_pool_size)
        # 信号量，控制应用层并发
        self.synthesis_semaphore = asyncio.Semaphore(self.connection_pool_size)
    
    def _initialize_default_speech_config(self) -> None:
        """初始化默认语音配置"""
        self._default_speech_config = self._create_speech_config()
    
    def _initialize_synthesizer_pool(self) -> None:
        """初始化合成器对象池"""
        self.synthesizer_pool = []
        self.pool_lock = asyncio.Lock() if hasattr(asyncio, 'Lock') else None
        
        if self.enable_connection_pool:
            # 创建多个合成器实例
            for i in range(self.connection_pool_size):
                try:
                    synthesizer = self._create_synthesizer_with_connection()
                    if synthesizer:
                        self.synthesizer_pool.append(synthesizer)
                        logger.debug(f"创建合成器实例 {i+1}/{self.connection_pool_size}")
                except Exception as e:
                    logger.warning(f"创建合成器实例 {i+1} 失败: {e}")
            
            logger.info(f"合成器池初始化完成，可用实例: {len(self.synthesizer_pool)}")
        else:
            logger.info("连接复用已禁用，将使用传统模式")
    
    def _create_synthesizer_with_connection(self) -> Optional[speechsdk.SpeechSynthesizer]:
        """创建带连接预热的合成器"""
        try:
            # 使用默认语音配置
            synthesizer = speechsdk.SpeechSynthesizer(speech_config=self._default_speech_config, audio_config=None)
            # 如果启用连接预热，预建立连接
            if self.enable_connection_prewarming:
                try:
                    connection = speechsdk.Connection.from_speech_synthesizer(synthesizer)
                    connection.open(True)
                    logger.debug("连接预热成功")
                except Exception as e:
                    logger.warning(f"连接预热失败: {e}")
            
            return synthesizer
        except Exception as e:
            logger.error(f"创建合成器失败: {e}")
            return None
    
    def _get_synthesizer_from_pool(self) -> Optional[speechsdk.SpeechSynthesizer]:
        """从池中获取合成器，如果池为空则创建新的"""
        # 如果连接池未启用，直接创建新合成器
        if not self.enable_connection_pool:
            logger.debug("连接复用未启用，创建新合成器")
            return self._create_synthesizer_with_connection()
        
        # 如果池中有可用合成器，从池中获取
        if self.synthesizer_pool:
            try:
                synthesizer = self.synthesizer_pool.pop(0)
                self.synthesizer_pool.append(synthesizer)  # 放回池底
                logger.debug(f"从池中获取合成器，剩余: {len(self.synthesizer_pool)}")
                return synthesizer
            except Exception as e:
                logger.warning(f"从池中获取合成器失败: {e}")
        
        # 如果池为空，创建新合成器
        logger.debug("池为空，创建新合成器")
        return self._create_synthesizer_with_connection()
    
    @contextmanager
    def _synthesizer_context(self):
        """合成器上下文管理器，确保合成器正确返回到池中"""
        synthesizer = None
        try:
            synthesizer = self._get_synthesizer_from_pool()
            if not synthesizer:
                logger.error("无法获取或创建合成器")
                yield None
                return
            yield synthesizer
        except Exception as e:
            logger.error(f"合成器使用过程中出错: {e}")
            raise
        finally:
            if synthesizer:
                self._return_synthesizer_to_pool(synthesizer)
    
    def _return_synthesizer_to_pool(self, synthesizer: speechsdk.SpeechSynthesizer) -> None:
        """将合成器返回池中"""
        if not self.enable_connection_pool:
            return
        
        try:
            if synthesizer not in self.synthesizer_pool:
                self.synthesizer_pool.append(synthesizer)
                logger.debug(f"合成器已返回池中，当前池大小: {len(self.synthesizer_pool)}")
        except Exception as e:
            logger.warning(f"返回合成器到池中失败: {e}")
    
    def _initialize_stats(self) -> None:
        """初始化统计信息"""
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_characters": 0,
            "total_audio_duration": 0.0,
            "default_voice_requests": 0,
            "custom_voice_requests": 0
        }
    
    def _is_default_voice(self, voice_id: str) -> bool:
        """判断是否为默认语音"""
        for voices in self.available_voices.values():
            if voice_id in voices:
                return True
        return False
    
    def _is_custom_voice(self, voice_id: str) -> bool:
        """判断是否为自定义语音（个人语音克隆）"""
        return not self._is_default_voice(voice_id) and self.enable_custom_voice
    
    @property
    def name(self) -> str:
        """服务名称"""
        return "azure_tts_service"
    
    @property
    def description(self) -> str:
        """服务描述"""
        return "基于Azure Cognitive Services的文本转语音服务，支持默认语音和自定义语音（个人语音克隆）"
    
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
                "synthesize_speech", "将文本转换为语音，支持默认语音和自定义语音",
                {
                    "text": {
                        "type": "string",
                        "description": "要转换的文本内容"
                    },
                    "voice": {
                        "type": "string",
                        "description": "语音名称或自定义语音ID（可选）"
                    },
                    "emotion": {
                        "type": "string",
                        "description": "情感类型（可选）",
                        "enum": ["cheerful", "sad", "angry", "calm", "friendly", "terrified", "unfriendly", "whispering", "hopeful"]
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
                        "description": "语音名称或自定义语音ID（可选）"
                    },
                    "emotion": {
                        "type": "string",
                        "description": "情感类型（可选）",
                        "enum": ["cheerful", "sad", "angry", "calm", "friendly", "terrified", "unfriendly", "whispering", "hopeful"]
                    }
                },
                ["text"]
            ),
            
            self._create_tool_definition(
                "get_available_voices", "获取可用的默认语音列表",
                {
                    "language": {
                        "type": "string",
                        "description": "语言代码（可选）",
                        "enum": ["zh-CN", "en-US"]
                    }
                }
            ),
            
            self._create_tool_definition(
                "get_voice_type_info", "获取语音类型信息",
                {
                    "voice_id": {
                        "type": "string",
                        "description": "语音ID"
                    }
                },
                ["voice_id"]
            ),
            
            self._create_tool_definition(
                "get_available_emotions", "获取所有可用的情绪列表",
                {}
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
            "get_voice_type_info": lambda: self._get_voice_type_info_tool(arguments),
            "get_available_emotions": lambda: self._get_available_emotions_tool(arguments),
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
        from src.utcp.streaming import LocalStreamResponse, StreamType, StreamMetadata
        
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
    
    def _create_speech_config(self, voice: Optional[str] = None) -> speechsdk.SpeechConfig:
        """创建Azure Speech配置"""
        voice = voice or self.default_voice
        
        # 创建语音配置
        if self.endpoint:
            speech_config = speechsdk.SpeechConfig(
                subscription=self.subscription_key, 
                endpoint=self.endpoint
            )
        else:
            speech_config = speechsdk.SpeechConfig(
                subscription=self.subscription_key, 
                region=self.service_region
            )
        
        # 设置语音
        speech_config.speech_synthesis_voice_name = voice
        # 设置音频输出格式
        self._set_audio_format(speech_config)
        
        return speech_config
    
    def _set_audio_format(self, speech_config: speechsdk.SpeechConfig) -> None:
        """设置音频输出格式 - 固定使用opus格式"""
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Ogg16Khz16BitMonoOpus
        )
    
    def _create_default_voice_ssml(self, text: str, voice: str, emotion: Optional[str] = None, voice_params: Optional[Dict[str, Any]] = None) -> str:
        """创建默认语音的SSML标记"""
        # 基础SSML
        ssml = f'<speak version="1.0" xml:lang="en-US" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="http://www.w3.org/2001/mstts">'
        ssml += f'<voice name="{voice}">'

        # 添加情感表达
        if emotion and self.enable_emotion:
            ssml += f'<mstts:express-as style="{emotion}" styledegree="1">'
            ssml += self._wrap_with_prosody(text, voice_params, use_single_quote=False)
            ssml += f'</mstts:express-as>'
        else:
            ssml += self._wrap_with_prosody(text, voice_params, use_single_quote=False)
        
        ssml += '</voice></speak>'
        return ssml
    
    def _create_custom_voice_ssml(self, text: str, speaker_profile_id: str, emotion: Optional[str] = None, voice_params: Optional[Dict[str, Any]] = None) -> str:
        """创建自定义语音的SSML标记"""
        # 使用自定义语音的SSML格式（仅在提供 emotion 且启用时加上 express-as）
        ssml = "<speak version='1.0' xml:lang='en-US' xmlns='http://www.w3.org/2001/10/synthesis' xmlns:mstts='http://www.w3.org/2001/mstts'>"
        ssml += f"<voice name='DragonLatestNeural'>"
        ssml += f"<mstts:ttsembedding speakerProfileId='{speaker_profile_id}'/>"

        if emotion and getattr(self, 'enable_emotion', True):
            ssml += f"<mstts:express-as style='{emotion}' styledegree='1'>"
            ssml += self._wrap_with_prosody(text, voice_params, use_single_quote=True)
            ssml += "</mstts:express-as>"
        else:
            ssml += self._wrap_with_prosody(text, voice_params, use_single_quote=True)

        ssml += "</voice></speak>"
        return ssml

    def _wrap_with_prosody(self, content_text: str, voice_params: Optional[Dict[str, Any]], use_single_quote: bool = False) -> str:
        """根据 voice_params 包裹 prosody，统一类级公用实现。
        use_single_quote 控制 SSML 属性是否使用单引号（与原有两处实现保持一致）。
        """
        quote = "'" if use_single_quote else '"'
        if not voice_params or not isinstance(voice_params, dict):
            return f"<lang xml:lang={quote}{self.default_language}{quote}> {content_text} </lang>"

        allowed_keys = {"rate", "pitch", "range", "volume", "contour"}
        attrs: list[str] = []
        for key in allowed_keys:
            value = voice_params.get(key)
            if value is None:
                continue
            try:
                value_str = str(value).strip()
                if value_str:
                    if use_single_quote:
                        attrs.append(f"{key}='{value_str}'")
                    else:
                        attrs.append(f"{key}=\"{value_str}\"")
            except Exception:
                continue

        if not attrs:
            return f"<lang xml:lang={quote}{self.default_language}{quote}> {content_text} </lang>"

        prosody_attr = " ".join(attrs)
        return (
            f"<prosody {prosody_attr}><lang xml:lang={quote}{self.default_language}{quote}> "
            f"{content_text} </lang></prosody>"
        )
    
    def _create_ssml(self, text: str, voice: str, emotion: Optional[str] = None, voice_params: Optional[Dict[str, Any]] = None) -> str:
        """创建SSML标记（根据语音类型选择不同的生成方法）"""
        # 验证情绪参数
        if emotion and not self._validate_emotion(emotion):
            logger.warning(f"使用无效情绪: {emotion}，将忽略情绪设置")
            emotion = None
        
        if self._is_default_voice(voice):
            return self._create_default_voice_ssml(text, voice, emotion, voice_params)
        elif self._is_custom_voice(voice):
            return self._create_custom_voice_ssml(text, voice, emotion, voice_params)
        else:
            # 默认使用默认语音的SSML格式
            logger.warning(f"未知语音类型: {voice}，使用默认语音格式")
            return self._create_default_voice_ssml(text, self.default_voice, emotion, voice_params)
    
    def _synthesize_speech_sync(self, text: str, voice: Optional[str] = None, 
                               emotion: Optional[str] = None, voice_params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """同步合成语音"""
        voice = voice or self.default_voice
        
        # 更新统计信息
        self._update_voice_stats(voice)
        
        # 检查文本长度
        text = self._validate_text_length(text)
        
        # 使用上下文管理器确保合成器正确返回池中
        with self._synthesizer_context() as speech_synthesizer:
            if not speech_synthesizer:
                logger.error("无法获取或创建合成器")
                return None
            
            # 执行语音合成
            ssml_text = self._create_ssml(text, voice, emotion, voice_params)
            result = speech_synthesizer.speak_ssml_async(ssml_text).get()

            # 处理结果
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                audio_data = result.audio_data
                
                # 获取延迟信息
                first_byte_client_latency = int(result.properties.get_property(speechsdk.PropertyId.SpeechServiceResponse_SynthesisFirstByteLatencyMs))
                finished_client_latency = int(result.properties.get_property(speechsdk.PropertyId.SpeechServiceResponse_SynthesisFinishLatencyMs))
                network_latency = int(result.properties.get_property(speechsdk.PropertyId.SpeechServiceResponse_SynthesisNetworkLatencyMs))
                first_byte_service_latency = int(result.properties.get_property(speechsdk.PropertyId.SpeechServiceResponse_SynthesisServiceLatencyMs))
                
                logger.debug(f"语音合成成功: {len(text)} 字符 -> {len(audio_data)} 字节")
                
                # 计算音频时长（PCM格式）
                audio_duration = len(audio_data) / (self.sample_rate * 2)  # 16位 = 2字节
                
                return {
                    "audio_data": audio_data,
                    "first_byte_client_latency": first_byte_client_latency,
                    "finished_client_latency": finished_client_latency,
                    "network_latency": network_latency,
                    "first_byte_service_latency": first_byte_service_latency,
                    "audio_duration": audio_duration
                }
            elif result.reason == speechsdk.ResultReason.Canceled:
                cancellation_details = result.cancellation_details
                logger.error(f"语音合成取消: {cancellation_details.reason} 错误详情: {cancellation_details.error_details}， ssml: {ssml_text}")
                return None
            else:
                logger.error(f"语音合成失败: {result.reason}")
                return None
    
    def _update_voice_stats(self, voice: str) -> None:
        """更新语音统计信息"""
        if self._is_default_voice(voice):
            self.stats["default_voice_requests"] += 1
            logger.debug(f"使用默认语音: {voice}")
        elif self._is_custom_voice(voice):
            self.stats["custom_voice_requests"] += 1
            logger.debug(f"使用自定义语音: {voice}")
        else:
            logger.warning(f"未知语音类型: {voice}")
    
    def _validate_text_length(self, text: str) -> str:
        """验证文本长度"""
        if len(text) > self.max_text_length:
            logger.warning(f"文本长度超过限制: {len(text)} > {self.max_text_length}")
            return text[:self.max_text_length]
        return text
    
    async def synthesize_speech_stream(self, text: str, voice: Optional[str] = None, 
                                    emotion: Optional[str] = None, voice_params: Optional[Dict[str, Any]] = None):
        """流式合成语音，使用纯异步方式"""
        import asyncio
        import time
        
        self.stats["total_requests"] += 1
        self.stats["total_characters"] += len(text)
        
        # 记录开始时间
        start_time = time.time()
        actual_voice = voice or self.default_voice
        
        # 创建Opus解析器
        from src.common.utils.audio.opus_stream_parse import OpusStreamParser
        opus_parser = OpusStreamParser()
        
        chunk_count = 0
        total_audio_size = 0
        
        try:
            # 获取合成器
            speech_synthesizer = self._get_synthesizer_from_pool()
            if not speech_synthesizer:
                raise Exception("无法获取或创建合成器")
            
            try:
                # 创建SSML
                ssml_text = self._create_ssml(text, voice, emotion, voice_params)
                
                # 获取正在运行的事件循环（复用，避免重复获取）
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    self.executor,
                    lambda: speech_synthesizer.start_speaking_ssml_async(ssml_text).get()
                )
                
                # 创建音频流
                audio_data_stream = speechsdk.AudioDataStream(result)
                audio_buffer = bytes(19200)
                
                # 流式读取音频数据
                while True:
                    # 使用自定义线程池执行同步的 read_data 操作
                    filled_size = await loop.run_in_executor(
                        self.executor,
                        audio_data_stream.read_data,
                        audio_buffer
                    )
                    
                    if filled_size == 0:
                        break
                    
                    audio_chunk = audio_buffer[:filled_size]
                    
                    # 解析Opus格式数据
                    parsed_packets = opus_parser.process_chunk(audio_chunk)
                    
                    # 生成解析后的数据
                    for packet in parsed_packets:
                        chunk_count += 1
                        
                        if packet['type'] == 'header':
                            # Opus文件头信息
                            yield {
                                "success": True,
                                "type": "opus_header",
                                "data": packet['data'],
                                "page_info": packet.get('page_info', {}),
                                "chunk_index": chunk_count
                            }
                        elif packet['type'] == 'tags':
                            # Opus标签信息
                            yield {
                                "success": True,
                                "type": "opus_tags",
                                "data": packet['data'],
                                "page_info": packet.get('page_info', {}),
                                "chunk_index": chunk_count
                            }
                        elif packet['type'] == 'audio':
                            # Opus音频数据包
                            audio_packets = packet.get('packets', [])
                            total_audio_size += sum(len(p.get('data', b'')) for p in audio_packets)
                            
                            # 处理每个音频包
                            for audio_packet in audio_packets:
                                audio_data = audio_packet.get('data', b'')
                                if audio_data:
                                    yield {
                                        "success": True,
                                        "type": "opus_packet",
                                        "audio_chunk": audio_data,
                                        "packet_info": {
                                            "toc": audio_packet.get('toc', 0),
                                            "config": audio_packet.get('config', 0),
                                            "stereo": audio_packet.get('stereo', 0),
                                            "frame_count": audio_packet.get('frame_count', 0),
                                            "duration": audio_packet.get('duration', 0)
                                        },
                                        "page_info": packet.get('page_info', {}),
                                        "chunk_index": chunk_count,
                                        "total_size": total_audio_size
                                    }
                    
                    # 让出控制权，避免阻塞事件循环
                    await asyncio.sleep(0)
            
            finally:
                # 返还合成器到池中
                self._return_synthesizer_to_pool(speech_synthesizer)
            
            # 更新统计信息
            self.stats["successful_requests"] += 1
            execution_time = time.time() - start_time
            
            # 计算音频时长
            estimated_duration = len(text) / (150 / 60)
            audio_duration = max(estimated_duration, 0.1)
            self.stats["total_audio_duration"] += audio_duration
            
            # 输出日志
            connection_pool_status = "连接池" if self.enable_connection_pool else "新建连接"
            logger.info(
                f"流式生成文本: {text} 语音: {actual_voice} "
                f"音频时长: {audio_duration:.2f}秒, 生成时间: {execution_time:.3f}秒, "
                f"块数: {chunk_count}, 总大小: {total_audio_size}字节, "
                f"连接模式: {connection_pool_status}"
            )
            
            # 发送最终元数据
            yield {
                "success": True,
                "type": "metadata",
                "audio_size": total_audio_size,
                "text_length": len(text),
                "voice": actual_voice,
                "audio_duration": audio_duration,
                "execution_time": execution_time,
                "chunk_count": chunk_count,
                "audio_format": "opus",
                "sample_rate": self.sample_rate
            }
        
        except Exception as e:
            self.stats["failed_requests"] += 1
            logger.error(f"流式语音合成异常: {e}")
            yield {
                "success": False,
                "error": str(e),
                "audio_data": b"",
                "chunk_index": 0,
                "total_size": 0
            }

    async def synthesize_speech(self, text: str, voice: Optional[str] = None, 
                            emotion: Optional[str] = None, 
                            voice_params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """异步合成语音"""
        import time
        
        # 使用信号量控制并发
        async with self.synthesis_semaphore:
            self.stats["total_requests"] += 1
            self.stats["total_characters"] += len(text)
            
            # 记录开始时间
            start_time = time.time()
            actual_voice = voice or self.default_voice
            
            try:
                # 直接在线程池中执行同步合成
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    self.executor,
                    self._synthesize_speech_sync,
                    text, actual_voice, emotion, voice_params
                )
                
                if result:
                    # 计算执行时间
                    execution_time = time.time() - start_time
                    
                    # 更新统计信息
                    self.stats["successful_requests"] += 1
                    self.stats["total_audio_duration"] += result.get("audio_duration", 0)
                    
                    # 输出日志
                    connection_pool_status = "连接池" if self.enable_connection_pool else "新建连接"
                    logger.info(
                        f"生成文本: {text} 语音: {actual_voice} "
                        f"音频时长: {result.get('audio_duration', 0):.2f}秒, "
                        f"生成时间: {execution_time:.3f}秒, "
                        f"连接模式: {connection_pool_status}"
                    )
                    
                    # 更新执行时间
                    result["execution_time"] = execution_time
                    result["finished_client_latency"] = int(execution_time * 1000)
                    
                    return result
                else:
                    self.stats["failed_requests"] += 1
                    logger.error("语音合成失败: 没有生成音频数据")
                    return None
                    
            except Exception as e:
                self.stats["failed_requests"] += 1
                logger.error(f"语音合成异常: {e}")
                return None

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
    
    def _get_voice_type_info(self, voice_id: str) -> Dict[str, Any]:
        """获取语音类型信息"""
        if self._is_default_voice(voice_id):
            return {
                "type": "default",
                "voice_id": voice_id,
                "supported": True,
                "description": "标准Azure语音"
            }
        elif self._is_custom_voice(voice_id):
            return {
                "type": "custom",
                "voice_id": voice_id,
                "supported": True,
                "description": "个人语音克隆"
            }
        else:
            return {
                "type": "unknown",
                "voice_id": voice_id,
                "supported": False,
                "description": "未知语音类型"
            }
    
    @handle_tts_errors
    async def _synthesize_speech_tool(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """合成语音工具"""
        text = arguments.get("text", "")
        voice = arguments.get("voice") or self.default_voice
        emotion = arguments.get("emotion")
        voice_params = arguments.get("voice_params")
        
        if not text:
            raise ValueError("文本内容不能为空")
        
        # 获取语音类型信息
        voice_info = self._get_voice_type_info(voice)
        
        result = await self.synthesize_speech(text, voice, emotion, voice_params)
        
        if result:
            # 从结果中提取音频数据和延迟信息
            audio_data = result["audio_data"]
            first_byte_client_latency = result["first_byte_client_latency"]
            finished_client_latency = result["finished_client_latency"]
            network_latency = result["network_latency"]
            first_byte_service_latency = result["first_byte_service_latency"]
            audio_duration = result["audio_duration"]
            execution_time = result["execution_time"]
            
            return {
                "success": True,
                "audio_data": audio_data,
                "audio_size": len(audio_data),
                "text_length": len(text),
                "voice": voice,
                "first_byte_client_latency": first_byte_client_latency,
                "finished_client_latency": finished_client_latency,
                "network_latency": network_latency,
                "first_byte_service_latency": first_byte_service_latency,
                "audio_duration": audio_duration,
                "execution_time": execution_time,
                "voice_type": voice_info["type"],
                "emotion": emotion,
                "audio_format": "opus",  # 固定使用opus格式
                "sample_rate": self.sample_rate
            }
        else:
            raise ValueError("语音合成失败")
    
    async def _synthesize_speech_stream(self, arguments: Dict[str, Any]):
        """流式合成语音工具"""
        from src.utcp.streaming import LocalStreamResponse, StreamType, StreamMetadata
        
        text = arguments.get("text", "")
        voice = arguments.get("voice") or self.default_voice
        emotion = arguments.get("emotion")
        voice_params = arguments.get("voice_params")
        
        if not text:
            raise ValueError("文本内容不能为空")
        
        # 获取语音类型信息
        voice_info = self._get_voice_type_info(voice)
        
        async def audio_stream_generator():
            try:
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
            "total_count": len(voices),
            "voice_type": "default"
        }
    
    async def _get_voice_type_info_tool(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """获取语音类型信息工具"""
        voice_id = arguments.get("voice_id", "")
        
        if not voice_id:
            return {
                "success": False,
                "error": "语音ID不能为空"
            }
        
        voice_info = self._get_voice_type_info(voice_id)
        
        return {
            "success": True,
            "voice_info": voice_info
        }
    
    async def _get_available_emotions_tool(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """获取可用情绪工具"""
        emotions = self._get_available_emotions()
        
        return {
            "success": True,
            "emotions": emotions,
            "total_count": len(emotions),
            "description": "Azure TTS支持的所有情绪类型"
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
                "default_language": self.default_language,
                "sample_rate": self.sample_rate,
                "audio_format": "opus",  # 固定使用opus格式
                "enable_emotion": self.enable_emotion,
                "enable_custom_voice": self.enable_custom_voice,
                "max_text_length": self.max_text_length,
                "timeout": self.timeout,
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
        # 清理合成器池
        if hasattr(self, 'synthesizer_pool') and self.synthesizer_pool:
            logger.info(f"清理合成器池，当前大小: {len(self.synthesizer_pool)}")
            for synthesizer in self.synthesizer_pool:
                try:
                    # 尝试关闭连接
                    if hasattr(synthesizer, 'close'):
                        synthesizer.close()
                except Exception as e:
                    logger.warning(f"关闭合成器时出错: {e}")
            self.synthesizer_pool.clear()
        
        # 关闭线程池
        if hasattr(self, 'executor') and self.executor:
            self.executor.shutdown(wait=True)
        
        logger.info("AzureTTSService已关闭")
    
    def __del__(self):
        """析构函数"""
        if hasattr(self, 'executor') and self.executor:
            self.executor.shutdown(wait=False) 