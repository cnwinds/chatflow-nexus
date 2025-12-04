"""
VAD 节点

基于硬件侧已有的 VADDetector 实现语音活动检测。
支持两种模式：
- manual: 收到空包表示语音结束，可以开始识别
- realtime: 使用 VAD 判断连续的语音是否完成了一句话

输入: 流式 Opus 音频数据
输出: 一次性完整 PCM 音频数据 + 语音结束事件
"""

import sys
from pathlib import Path
import asyncio
import logging
from typing import Any, Dict, Optional
import opuslib_next

# 确保可以导入 src 模块（当从外部项目加载时）
_file_path = Path(__file__).resolve()
_project_root = _file_path.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from stream_workflow.core import Node, ParameterSchema, StreamChunk, register_node
from stream_workflow.core.parameter import FieldSchema

# 使用新的 Silero VAD 实现
from src.common.utils.audio.silero_vad import SileroVAD, SileroVadConfig


@register_node("vad_node")
class VADNode(Node):
    """流式 VAD 节点，接收 Opus 数据包，完成语音段切分。
    
    功能: 接收流式 Opus 音频数据，进行语音活动检测（VAD），识别语音段的开始和结束。
    支持两种监听模式：manual（手动模式，收到空包表示语音结束）和 realtime（实时模式，使用 SileroVAD 自动检测语音结束）。
    在检测到语音结束后，一次性输出完整的 PCM 音频数据，供下游 STT 节点使用。
    
    配置参数:
    - vad_threshold: VAD 阈值（可选），用于判断语音活动的概率阈值，默认从用户配置中获取。
    - silence_timeout: 静音超时时间（秒，可选），连续静音超过此时间后判定为语音结束，默认从用户配置中获取。
    - sample_rate: 采样率（可选），音频采样率，默认 16000 Hz，从用户配置中获取。
    - channels: 声道数（可选），音频声道数，默认 1（单声道），从用户配置中获取。
    
    注意: 实际使用的配置会从全局硬件配置和用户配置中加载，节点配置参数仅作为可选覆盖。
    """

    EXECUTION_MODE = "streaming"

    INPUT_PARAMS = {
        "audio_stream": ParameterSchema(
            is_streaming=True,
            schema={"data": "bytes"}  # 单个 Opus 数据包
        )
    }

    OUTPUT_PARAMS = {
        # 完整的一段语音（PCM）
        "speech_audio": ParameterSchema(
            is_streaming=True,
            schema={
                "data": "bytes",  # PCM 原始字节
                "format": "string",  # 固定 "pcm"
                "sample_rate": "int",
                "channels": "int"
            }
        ),
        # 语音结束事件（可用于触发下游）
        "speech_ended": ParameterSchema(
            is_streaming=True,
            schema={"ended": "boolean"}
        )
    }
    
    # 配置参数定义（使用 FieldSchema 格式）
    CONFIG_PARAMS = {
        "vad_threshold": FieldSchema({
            'type': 'number',
            'required': False,
            'description': 'VAD阈值'
        }),
        "silence_timeout": FieldSchema({
            'type': 'number',
            'required': False,
            'description': '静音超时时间（秒）'
        }),
        "sample_rate": FieldSchema({
            'type': 'integer',
            'required': False,
            'description': '采样率'
        }),
        "channels": FieldSchema({
            'type': 'integer',
            'required': False,
            'description': '声道数'
        })
    }

    async def run(self, context):
        self.context = context
        self.user_data = context.get_global_var("user_data")
        self.logger = logging.getLogger(__name__)

        self.vad_cfg = self._load_config(context)
        
        # 只在 realtime 模式下创建 VAD 对象
        if self.vad_cfg.get("listen_mode") == "realtime":
            # 创建 SileroVAD 配置
            vad_config = SileroVadConfig(
                sample_rate=self.vad_cfg.get("sample_rate", 16000),
                threshold=self.vad_cfg.get("threshold", 0.5),
                min_silence_duration_ms=int(self.vad_cfg.get("silence_timeout", 0.3) * 1000),
                min_speech_duration_ms=int(self.vad_cfg.get("min_recording_duration", 0.5) * 1000),
                max_speech_duration_s=float(self.vad_cfg.get("max_recording_duration", 60.0)),
                speech_pad_ms=60,  # 固定为 60ms
                # window_size_samples 使用默认值 512
            )
            
            self.vad: Optional[SileroVAD] = SileroVAD(
                config=vad_config,
                use_onnx=self.vad_cfg.get("use_onnx", True)
            )
        else:
            self.vad: Optional[SileroVAD] = None
            
        # 两种模式都需要 Opus 解码器
        self.decoder = opuslib_next.Decoder(self.sample_rate, 1)
        
        if self.vad_cfg.get("listen_mode") == "manual":
            # Manual 模式下，创建音频缓存
            self.audio_buffer = bytearray()
        
        await asyncio.sleep(float("inf"))
    
    async def shutdown(self):
        """清理节点资源"""
        # 关闭 VAD 模型
        if hasattr(self, 'vad') and self.vad is not None:
            self.vad.close()
            self.vad = None
        
        # 清理 Opus 解码器
        if hasattr(self, 'decoder') and self.decoder is not None:
            del self.decoder
            self.decoder = None
        
        # 清空音频缓冲区
        if hasattr(self, 'audio_buffer'):
            self.audio_buffer.clear()
    
    def _load_config(self, context) -> Dict[str, Any]:
        """加载VAD配置"""
        from src.common.config import get_config_manager
        from src.common.config.constants import ConfigPaths
        
        # 1. 获取配置管理器
        config_manager = get_config_manager()
        
        # 2. 从chat.json加载硬件配置
        hardware_config = config_manager.get_config(ConfigPaths.CHAT_HARDWARE) or {}
        audio_config = hardware_config.get("audio", {})
            
        sample_rate = int(audio_config.get("sample_rate", 16000))
        channels = int(audio_config.get("channels", 1))
        threshold = float(audio_config.get("vad_threshold", 0.5))
        silence_timeout = float(audio_config.get("silence_timeout", 0.5))
        listen_mode = audio_config.get("listen_mode", "manual")
        min_recording_duration = float(audio_config.get("min_recording_duration", 0.5))
        max_recording_duration = float(audio_config.get("max_recording_duration", 60.0))
        close_connection_no_voice_time = float(audio_config.get("close_connection_no_voice_time", 120))
        
        # 用户配置覆盖
        sample_rate = self.user_data.get_config("audio_settings.sample_rate", sample_rate)
        channels = self.user_data.get_config("audio_settings.channels", channels)
        threshold = self.user_data.get_config("audio_settings.vad_threshold", threshold)
        silence_timeout = self.user_data.get_config("audio_settings.silence_timeout", silence_timeout)
        listen_mode = self.user_data.get_config("audio_settings.listen_mode", listen_mode)
        min_recording_duration = self.user_data.get_config("audio_settings.min_recording_duration", min_recording_duration)
        max_recording_duration = self.user_data.get_config("audio_settings.max_recording_duration", max_recording_duration)
        close_connection_no_voice_time = self.user_data.get_config("audio_settings.close_connection_no_voice_time", close_connection_no_voice_time)
        
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)

        return {
            "enable_vad": listen_mode == "realtime",
            "use_onnx": True,
            "opset_version": 16,
            "threshold": float(threshold),
            "silence_timeout": float(silence_timeout),
            "sample_rate": int(sample_rate),
            "channels": int(channels),
            "listen_mode": listen_mode,
            "min_recording_duration": float(min_recording_duration),
            "max_recording_duration": float(max_recording_duration),
            "close_connection_no_voice_time": float(close_connection_no_voice_time)
        }

    async def on_chunk_received(self, param_name: str, chunk: StreamChunk):
        if param_name != "audio_stream":
            return

        # 读取输入的 Opus 数据包
        data: bytes = chunk.data.get("data", b"")
        
        # 根据 listen_mode 处理不同的逻辑
        if self.vad_cfg.get("listen_mode") == "manual":
            # Manual 模式：收到空包表示语音结束
            if not data:
                # 空包表示语音结束，取出所有缓存的音频数据
                pcm_bytes: bytes = bytes(self.audio_buffer)
                if pcm_bytes:
                    # 检查录音时长（manual 模式下也需要检查最小录音时长）
                    min_duration = self.vad_cfg.get("min_recording_duration", 0.5)
                    # 计算时长：PCM 16位 = 2字节/样本
                    duration = len(pcm_bytes) / (self.sample_rate * 2)
                    if duration < min_duration:
                        self.logger.debug(f"录音时长过短 ({duration:.2f}秒 < {min_duration}秒)，已丢弃")
                        self.audio_buffer.clear()
                        await self.emit_chunk("speech_ended", {"ended": True})
                        return
                    
                    await self.emit_chunk("speech_audio", {
                        "data": pcm_bytes,
                        "format": "pcm",
                        "sample_rate": self.sample_rate,
                        "channels": self.channels,
                    })
                await self.emit_chunk("speech_ended", {"ended": True})
                # 清空缓存
                self.audio_buffer.clear()
            else:
                # 非空包，解码 Opus 数据并缓存 PCM 数据
                try:
                    pcm_frame = self.decoder.decode(data, 960)
                    self.audio_buffer.extend(pcm_frame)
                except opuslib_next.OpusError as e:
                    # 解码错误，跳过这个包
                    pass
        else:
            # Realtime 模式：使用 SileroVAD 检测语音结束
            if not data:
                return
                
            try:
                # 解码 Opus 数据包
                pcm_frame = self.decoder.decode(data, 960)
                
                # 转换为 numpy 数组
                import numpy as np
                audio_int16 = np.frombuffer(pcm_frame, dtype=np.int16)
                audio_float32 = audio_int16.astype(np.float32) / 32768.0
                
                # 送入 SileroVAD 处理
                events = self.vad.process_audio(audio_float32)
                
                # 处理事件
                for event in events:
                    if event.event_type == 'speech_end' and event.audio_data is not None:
                        # 将 numpy 数组转换为 PCM 字节
                        audio_int16 = (event.audio_data * 32767).astype(np.int16)
                        pcm_bytes = audio_int16.tobytes()
                        
                        if pcm_bytes:
                            # VAD 已经根据 min_speech_duration_ms 和 max_speech_duration_s 进行了过滤
                            # 这里直接输出即可
                            await self.emit_chunk("speech_audio", {
                                "data": pcm_bytes,
                                "format": "pcm",
                                "sample_rate": self.sample_rate,
                                "channels": self.channels,
                            })
                        await self.emit_chunk("speech_ended", {"ended": True})
                        
            except opuslib_next.OpusError as e:
                # 解码错误，跳过这个包
                pass
            except Exception as e:
                # 其他错误，记录并继续
                self.logger.error(f"处理音频数据时发生错误: {e}")


