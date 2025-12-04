import torch
import numpy as np
import gc
import logging
from typing import Optional, Callable, List
from dataclasses import dataclass
from enum import Enum
from silero_vad import load_silero_vad

logger = logging.getLogger(__name__)


class VadState(Enum):
    """VAD状态枚举"""
    SILENCE = "silence"
    SPEAKING = "speaking"


@dataclass
class SileroVadConfig:
    """Silero VAD 配置参数"""
    sample_rate: int = 16000  # 支持 8000 或 16000
    threshold: float = 0.5  # 语音概率阈值 (0.0-1.0)
    min_speech_duration_ms: int = 250  # 最小语音持续时长
    max_speech_duration_s: float = 10.0  # 最大语音持续时长
    min_silence_duration_ms: int = 100  # 最小静音持续时长（用于过滤短暂停顿）
    speech_pad_ms: int = 30  # 语音前后填充时长
    
    # 窗口大小（采样点数）- Silero要求
    window_size_samples: int = 512  # 16000hz用512, 8000hz用256
    
    def __post_init__(self):
        """验证配置"""
        if self.sample_rate not in [8000, 16000]:
            raise ValueError("sample_rate must be 8000 or 16000")
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError("threshold must be between 0.0 and 1.0")
        
        # 验证最小语音持续时长（毫秒）
        if self.min_speech_duration_ms < 0:
            raise ValueError("min_speech_duration_ms must be >= 0")
        if self.min_speech_duration_ms > 10000:  # 10秒
            raise ValueError("min_speech_duration_ms must be <= 10000 (10 seconds)")
        
        # 验证最大语音持续时长（秒）
        if self.max_speech_duration_s <= 0:
            raise ValueError("max_speech_duration_s must be > 0")
        if self.max_speech_duration_s > 600:  # 10分钟
            raise ValueError("max_speech_duration_s must be <= 600 (10 minutes)")
        
        # 确保最大时长大于最小时长
        min_duration_s = self.min_speech_duration_ms / 1000.0
        if self.max_speech_duration_s < min_duration_s:
            raise ValueError(f"max_speech_duration_s ({self.max_speech_duration_s}s) must be >= min_speech_duration_ms ({min_duration_s}s)")
        
        # 验证最小静音持续时长
        if self.min_silence_duration_ms < 0:
            raise ValueError("min_silence_duration_ms must be >= 0")
        
        # 验证语音填充时长
        if self.speech_pad_ms < 0:
            raise ValueError("speech_pad_ms must be >= 0")
        
        # 根据采样率自动设置窗口大小
        if self.sample_rate == 8000:
            self.window_size_samples = 256
        else:  # 16000
            self.window_size_samples = 512


class VadEvent:
    """VAD事件"""
    def __init__(self, event_type: str, timestamp_ms: float, audio_data: Optional[np.ndarray] = None):
        self.event_type = event_type  # 'speech_start' 或 'speech_end'
        self.timestamp_ms = timestamp_ms
        self.audio_data = audio_data
        
    def __repr__(self):
        audio_info = f", audio_len={len(self.audio_data)}" if self.audio_data is not None else ""
        return f"VadEvent({self.event_type}, {self.timestamp_ms:.0f}ms{audio_info})"


class SileroVAD:
    """
    Silero VAD 封装类
    
    用法示例:
        # 基础使用
        vad = SileroVAD()
        events = vad.process_audio(pcm_data)
        
        # 使用回调
        vad = SileroVAD(config=SileroVadConfig(threshold=0.6))
        vad.on_speech_start = lambda ts: print(f"开始说话: {ts}ms")
        vad.on_speech_end = lambda ts, audio: print(f"结束说话: {ts}ms, 时长: {len(audio)/16000:.2f}s")
        
        # 流式处理
        for chunk in audio_stream:
            events = vad.process_audio(chunk)
            for event in events:
                if event.event_type == 'speech_end':
                    save_audio(event.audio_data)
        
        # 流结束时
        final_audio = vad.force_end_speech()
    """
    
    def __init__(self, 
                 config: Optional[SileroVadConfig] = None,
                 use_onnx: bool = True):
        """
        初始化 Silero VAD
        
        Args:
            config: VAD配置
            use_onnx: 是否使用ONNX版本（更快，但需要onnxruntime）
        """
        self.config = config or SileroVadConfig()
        self.use_onnx = use_onnx
        
        # 加载模型
        self._load_model()
        
        # 初始化状态
        self.reset()
        
        # 回调函数
        self.on_speech_start: Optional[Callable[[float], None]] = None
        self.on_speech_end: Optional[Callable[[float, np.ndarray], None]] = None
        
    def _load_model(self):
        """加载 Silero VAD 模型"""
        try:
            self.model = load_silero_vad(onnx=self.use_onnx, opset_version=16)
        except Exception as e:
            raise RuntimeError(f"模型加载失败: {e}")
    
    def reset(self):
        """重置VAD状态"""
        self.state = VadState.SILENCE
        self.buffer = np.array([], dtype=np.float32)
        self.speech_buffer = []
        self.temp_end_buffer = []  # 用于存储可能的结束前的音频
        self.total_samples = 0
        self.speech_start_sample = 0
        self.current_speech_samples = 0
        self.silence_samples = 0
        
        # 重置模型状态 - OnnxWrapper和PyTorch模型都有reset_states方法
        self.model.reset_states()
        
    def _reset_onnx_states(self):
        """重置ONNX模型状态"""
        self._h = np.zeros((2, 1, 64), dtype=np.float32)
        self._c = np.zeros((2, 1, 64), dtype=np.float32)
        
    def process_audio(self, pcm_data: np.ndarray) -> List[VadEvent]:
        """
        处理PCM音频数据
        
        Args:
            pcm_data: PCM音频数据，numpy数组，float32类型，值域为[-1, 1]
                     或int16类型，值域为[-32768, 32767]
        
        Returns:
            事件列表
        """
        # 归一化到[-1, 1]
        if pcm_data.dtype == np.int16:
            pcm_data = pcm_data.astype(np.float32) / 32768.0
        elif pcm_data.dtype != np.float32:
            pcm_data = pcm_data.astype(np.float32)
        
        # 添加到缓冲区
        self.buffer = np.concatenate([self.buffer, pcm_data])
        events = []
        
        # 按窗口大小处理
        window_size = self.config.window_size_samples
        while len(self.buffer) >= window_size:
            window = self.buffer[:window_size]
            self.buffer = self.buffer[window_size:]
            
            event = self._process_window(window)
            if event is not None:
                events.append(event)
        
        return events
    
    def _process_window(self, window: np.ndarray) -> Optional[VadEvent]:
        """处理单个音频窗口"""
        self.total_samples += len(window)
        timestamp_ms = (self.total_samples / self.config.sample_rate) * 1000
        
        # 获取语音概率
        speech_prob = self._get_speech_probability(window)
        
        # 判断是否为语音
        is_speech = speech_prob >= self.config.threshold
        
        event = None
        min_speech_samples = int(self.config.min_speech_duration_ms * self.config.sample_rate / 1000)
        min_silence_samples = int(self.config.min_silence_duration_ms * self.config.sample_rate / 1000)
        max_speech_samples = int(self.config.max_speech_duration_s * self.config.sample_rate)
        
        if self.state == VadState.SILENCE:
            if is_speech:
                self.speech_buffer.append(window)
                self.current_speech_samples += len(window)
                
                # 检查是否达到最小语音时长
                if self.current_speech_samples >= min_speech_samples:
                    self.state = VadState.SPEAKING
                    self.speech_start_sample = self.total_samples - self.current_speech_samples
                    
                    event = VadEvent('speech_start', 
                                   (self.speech_start_sample / self.config.sample_rate) * 1000)
                    if self.on_speech_start:
                        self.on_speech_start(event.timestamp_ms)
                    
                    self.silence_samples = 0
            else:
                # 重置语音缓冲
                if self.current_speech_samples > 0:
                    self.speech_buffer = []
                    self.current_speech_samples = 0
        
        elif self.state == VadState.SPEAKING:
            self.speech_buffer.append(window)
            self.current_speech_samples += len(window)
            
            if is_speech:
                # 继续语音
                self.silence_samples = 0
                self.temp_end_buffer = []
                
                # 检查是否超过最大语音时长
                if self.current_speech_samples >= max_speech_samples:
                    event = self._end_speech(timestamp_ms)
            else:
                # 可能的语音结束
                self.silence_samples += len(window)
                self.temp_end_buffer.append(window)
                
                # 检查是否达到最小静音时长
                if self.silence_samples >= min_silence_samples:
                    # 移除末尾的静音部分
                    if self.temp_end_buffer:
                        for _ in range(len(self.temp_end_buffer)):
                            if self.speech_buffer:
                                self.speech_buffer.pop()
                    
                    event = self._end_speech(timestamp_ms)
        
        return event
    
    def _end_speech(self, timestamp_ms: float) -> Optional[VadEvent]:
        """结束当前语音片段"""
        # 添加padding
        pad_samples = int(self.config.speech_pad_ms * self.config.sample_rate / 1000)
        
        # 合并语音片段
        if self.speech_buffer:
            speech_audio = np.concatenate(self.speech_buffer)
            
            # 添加后置padding（如果缓冲区还有数据）
            if len(self.buffer) > 0:
                pad_end = min(pad_samples, len(self.buffer))
                speech_audio = np.concatenate([speech_audio, self.buffer[:pad_end]])
        else:
            speech_audio = np.array([], dtype=np.float32)
        
        # 计算音频时长（秒）
        audio_duration_s = len(speech_audio) / self.config.sample_rate
        min_duration_s = self.config.min_speech_duration_ms / 1000.0
        max_duration_s = self.config.max_speech_duration_s
        
        # 检查是否小于最小语音时长
        if audio_duration_s < min_duration_s:
            logger.debug(f"语音时长过短 ({audio_duration_s:.3f}秒 < {min_duration_s:.3f}秒)，已丢弃")
            # 重置状态但不触发事件
            self.state = VadState.SILENCE
            self.speech_buffer = []
            self.temp_end_buffer = []
            self.current_speech_samples = 0
            self.silence_samples = 0
            return None
        
        # 检查是否超过最大语音时长，如果超过则裁剪
        if audio_duration_s > max_duration_s:
            max_samples = int(max_duration_s * self.config.sample_rate)
            speech_audio = speech_audio[:max_samples]
            logger.debug(f"语音时长超过最大值 ({audio_duration_s:.3f}秒 > {max_duration_s:.3f}秒)，已裁剪到 {max_duration_s:.3f}秒")
        
        event = VadEvent('speech_end', timestamp_ms, speech_audio)
        
        if self.on_speech_end:
            self.on_speech_end(timestamp_ms, speech_audio)
        
        # 重置状态
        self.state = VadState.SILENCE
        self.speech_buffer = []
        self.temp_end_buffer = []
        self.current_speech_samples = 0
        self.silence_samples = 0
        
        return event
    
    def _get_speech_probability(self, window: np.ndarray) -> float:
        """获取语音概率 - 统一接口，OnnxWrapper和PyTorch模型接口相同"""
        with torch.no_grad():
            audio_tensor = torch.from_numpy(window).unsqueeze(0)  # (1, samples)
            speech_prob = self.model(audio_tensor, self.config.sample_rate).item()
        return speech_prob
    
    def force_end_speech(self) -> Optional[np.ndarray]:
        """
        强制结束当前语音片段（用于流结束时）
        
        Returns:
            当前的语音数据，如果没有则返回None
        """
        if self.state == VadState.SPEAKING and self.speech_buffer:
            timestamp_ms = (self.total_samples / self.config.sample_rate) * 1000
            event = self._end_speech(timestamp_ms)
            if event is not None:
                return event.audio_data
        
        return None
    
    def get_current_state(self) -> VadState:
        """获取当前VAD状态"""
        return self.state
    
    def get_speech_duration_ms(self) -> float:
        """获取当前语音片段的持续时长（毫秒）"""
        if self.state == VadState.SPEAKING:
            return (self.current_speech_samples / self.config.sample_rate) * 1000
        return 0.0
    
    def close(self):
        """关闭VAD并释放模型资源"""
        try:
            # 先清理所有缓冲区和状态（在删除模型之前）
            if hasattr(self, 'buffer'):
                self.buffer = np.array([], dtype=np.float32)
            if hasattr(self, 'speech_buffer'):
                self.speech_buffer.clear()
            if hasattr(self, 'temp_end_buffer'):
                self.temp_end_buffer.clear()
            
            # 重置状态（需要在删除模型之前，因为reset会调用model.reset_states()）
            if hasattr(self, 'model') and self.model is not None:
                try:
                    self.model.reset_states()
                except Exception:
                    pass  # 如果reset_states失败，继续清理
            
            # 显式释放模型资源
            if hasattr(self, 'model') and self.model is not None:
                try:
                    del self.model
                except Exception:
                    pass
                self.model = None
            
            # 重置其他状态变量
            if hasattr(self, 'state'):
                self.state = VadState.SILENCE
            if hasattr(self, 'total_samples'):
                self.total_samples = 0
            if hasattr(self, 'speech_start_sample'):
                self.speech_start_sample = 0
            if hasattr(self, 'current_speech_samples'):
                self.current_speech_samples = 0
            if hasattr(self, 'silence_samples'):
                self.silence_samples = 0
            
            # 手动触发垃圾回收
            gc.collect()
            
            # 如果模型在 CUDA 上，清理 GPU 缓存
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            logger.info("Silero VAD 模型已关闭并释放内存")
        except Exception as e:
            logger.error(f"关闭 Silero VAD 失败: {e}")


# 使用示例
if __name__ == "__main__":
    import time
    
    print("=" * 60)
    print("Silero VAD 使用示例")
    print("=" * 60)
    
    # 创建VAD实例
    config = SileroVadConfig(
        sample_rate=16000,
        threshold=0.5,  # 可以根据环境调整 (0.3-0.7)
        min_silence_duration_ms=500,  # 500ms静音认为结束
        min_speech_duration_ms=250,   # 250ms语音才算开始
        speech_pad_ms=30
    )
    
    vad = SileroVAD(config=config, use_onnx=False)  # 改为True使用ONNX版本（推荐）
    
    # 设置回调
    def on_start(ts):
        print(f"🎤 语音开始: {ts:.0f}ms")
    
    def on_end(ts, audio):
        duration = len(audio) / config.sample_rate
        print(f"🔇 语音结束: {ts:.0f}ms, 时长: {duration:.2f}秒, 样本数: {len(audio)}")
    
    vad.on_speech_start = on_start
    vad.on_speech_end = on_end
    
    # 生成测试数据
    print("\n生成测试音频...")
    silence = np.random.randn(16000) * 0.001  # 1秒静音
    speech = np.random.randn(32000) * 0.1     # 2秒语音
    
    test_audio = np.concatenate([
        silence,
        speech,
        silence * 0.5,  # 0.5秒静音
        speech * 1.2,   # 2秒语音（稍强）
        silence
    ]).astype(np.float32)
    
    print(f"总音频长度: {len(test_audio)/16000:.2f}秒")
    print("\n开始处理...\n")
    
    # 分块处理（模拟实时流）
    chunk_size = 512  # 32ms chunks
    start_time = time.time()
    
    for i in range(0, len(test_audio), chunk_size):
        chunk = test_audio[i:i+chunk_size]
        events = vad.process_audio(chunk)
    
    # 流结束时强制结束
    final_audio = vad.force_end_speech()
    if final_audio is not None:
        print(f"⚠️  强制结束最后片段: {len(final_audio)/16000:.2f}秒")
    
    elapsed = time.time() - start_time
    print(f"\n处理完成，用时: {elapsed:.3f}秒")
    print(f"实时率: {len(test_audio)/16000/elapsed:.2f}x")
    
    print("\n" + "=" * 60)
    print("提示:")
    print("- threshold 越高越严格，建议 0.4-0.6")
    print("- 噪声环境可以降低到 0.3")
    print("- 使用 use_onnx=True 可获得更快的性能")
    print("=" * 60)