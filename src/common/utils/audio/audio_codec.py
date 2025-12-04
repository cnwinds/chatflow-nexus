"""
音频编解码器

提供音频编码和解码功能，支持Opus格式
"""

import logging
from typing import List, Optional, Union

import numpy as np
import opuslib_next

from .audio_utils import (
    convert_float32_to_int16,
    convert_int16_to_float32,
    decode_opus as decode_opus_utils
)

logger = logging.getLogger(__name__)

class AudioCodec:
    """
    音频编解码器
    
    提供音频编码和解码功能，支持Opus格式
    """
    
    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        """
        初始化音频编解码器
        
        Args:
            sample_rate: 采样率
            channels: 声道数
        """
        self.sample_rate = sample_rate
        self.channels = channels
        
        # 初始化Opus编码器和解码器
        self._encoder = None
        self._decoder = None
        
        try:
            if opuslib_next:
                self._encoder = opuslib_next.Encoder(sample_rate, channels, 'voip')
                self._decoder = opuslib_next.Decoder(sample_rate, channels)
                logger.debug(f"音频编解码器初始化成功: {sample_rate}Hz, {channels}声道")
            else:
                logger.warning("opuslib_next未安装，音频编解码功能将不可用")
        except Exception as e:
            logger.error(f"音频编解码器初始化失败: {e}")
    
    def _calculate_frame_size(self, frame_duration_ms: int) -> tuple[int, int]:
        """
        根据帧持续时间计算帧大小
        
        Args:
            frame_duration_ms: 帧持续时间（毫秒）
            
        Returns:
            (帧大小样本数, 帧大小字节数)
        """
        frame_size_samples = int(self.sample_rate * frame_duration_ms / 1000)
        frame_size_bytes = frame_size_samples * 2  # 16位 = 2字节
        return frame_size_samples, frame_size_bytes

    async def encode_opus(self, pcm_data: bytes, frame_duration_ms: int = 60) -> List[bytes]:
        """
        将PCM音频数据编码为Opus帧列表
        
        Args:
            pcm_data: PCM音频数据 (字节)
            frame_duration_ms: 每帧的毫秒数，支持10ms、20ms、40ms、60ms等 (默认60ms)
            
        Returns:
            Opus编码的音频帧列表
        """
        try:
            if self._encoder is None:
                logger.error("Opus编码器未初始化")
                return []

            # 计算帧大小
            frame_size_samples, frame_size_bytes = self._calculate_frame_size(frame_duration_ms)
            
            # 补齐到帧大小的整数倍
            if len(pcm_data) % frame_size_bytes != 0:
                padding_needed = frame_size_bytes - (len(pcm_data) % frame_size_bytes)
                pcm_data = pcm_data + b'\x00' * padding_needed
            
            # 分帧编码
            opus_frames = []
            for i in range(0, len(pcm_data), frame_size_bytes):
                frame_bytes = pcm_data[i:i+frame_size_bytes]
                opus_frame = self._encoder.encode(frame_bytes, frame_size_samples)
                opus_frames.append(opus_frame)
            
            logger.debug(f"编码完成: {len(opus_frames)}帧, 每帧{frame_duration_ms}ms")
            return opus_frames
            
        except Exception as e:
            logger.error(f"Opus编码失败: {e}")
            return []
    
    def decode_opus(self, opus_data: Union[bytes, List[bytes]]) -> bytes:
        """
        将Opus音频数据解码为PCM格式
        
        Args:
            opus_data: Opus音频数据 (单个字节串或字节串列表)
            
        Returns:
            PCM音频数据
        """
        try:
            if self._decoder is None:
                logger.error("Opus解码器未初始化")
                return b''
            
            # 直接使用现有的解码函数，它已经能处理字节串列表
            if isinstance(opus_data, bytes):
                # 如果是单个字节串，直接传递给解码函数
                return decode_opus_utils([opus_data])
            else:
                return decode_opus_utils(opus_data)
            
        except Exception as e:
            logger.error(f"Opus解码失败: {e}")
            return b''
    
    def get_sample_rate(self) -> int:
        """获取采样率"""
        return self.sample_rate
    
    def get_channels(self) -> int:
        """获取声道数"""
        return self.channels
    
    def is_available(self) -> bool:
        """检查编解码器是否可用"""
        return self._encoder is not None and self._decoder is not None
    
    def close(self):
        """关闭编解码器"""
        try:
            if self._encoder:
                del self._encoder
                self._encoder = None
            if self._decoder:
                del self._decoder
                self._decoder = None
            logger.info("音频编解码器已关闭")
        except Exception as e:
            logger.error(f"关闭音频编解码器失败: {e}")
    
    def __del__(self):
        """析构函数"""
        self.close() 