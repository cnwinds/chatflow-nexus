"""
STT 节点

输入: 
- speech_audio: 一段完整的 PCM 音频
- speech_ended: 语音结束事件（辅助触发）

输出:
- recognized_text: 文本
- confidence: 置信度
"""

import sys
from typing import Any, Dict, Optional, List
import asyncio
import time
import os
import io
import wave
import datetime
from pathlib import Path
from pydub import AudioSegment

# 确保可以导入 src 模块（当从外部项目加载时）
_file_path = Path(__file__).resolve()
_project_root = _file_path.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from stream_workflow.core import Node, ParameterSchema, StreamChunk, register_node
from stream_workflow.core.parameter import FieldSchema

from src.agents.utcp_tools import call_utcp_tool
from src.common.utils.audio.audio_utils import convert_pcm_to_wav
from src.common.config import get_config_manager
from src.common.config.constants import ConfigPaths

@register_node("stt_node")
class STTNode(Node):
    """语音转文字节点。
    
    功能: 将完整的 PCM 音频数据转换为文本。接收来自 VAD 节点的完整语音段音频，
    调用 STT 服务进行语音识别，输出识别结果文本、置信度、音频文件路径和情感识别结果。
    支持字符级置信度标记，根据置信度阈值对识别结果进行标记（高置信度直接输出，中等置信度用[]标记，低置信度用()标记）。
    自动保存音频文件为 MP3 格式，按年份和周数组织目录结构。
    
    配置参数: 无（配置从全局 ai_providers 和用户配置中加载，包括 STT 服务名称、语言、置信度阈值等）
    """
    
    EXECUTION_MODE = "streaming"

    INPUT_PARAMS = {
        "speech_audio": ParameterSchema(
            is_streaming=True,
            schema={
                "data": "bytes",
                "format": "string",
                "sample_rate": "int",
                "channels": "int",
            }
        ),
        "speech_ended": ParameterSchema(
            is_streaming=True,
            schema={"ended": "boolean"}
        )
    }

    OUTPUT_PARAMS = {
        "recognized_text": ParameterSchema(
            is_streaming=True,
            schema={"text": "string", "confidence": "float", "audio_file_path": "string", "emotion": "string"}
        )
    }
    
    # 配置参数定义（使用 FieldSchema 格式）
    CONFIG_PARAMS = {}

    async def initialize(self, context):
        """初始化节点 - 在run之前调用，确保所有资源在接收数据前已准备好"""
        self._context = context
        self._session_id = context.get_global_var("session_id")

        self._latest_audio: Optional[Dict[str, Any]] = None
        self._cfg = self._load_config(context)
        self._sequence_number = 0  # 流水号计数器
        
        context.log_info(f"STT 节点初始化完成: {self._cfg}")

    async def run(self, context):
        """运行节点 - 持续运行，等待处理流式数据"""
        await asyncio.sleep(float("inf"))

    def _load_config(self, context) -> Dict[str, Any]:
        """加载STT配置"""
        # 从全局变量获取合并后的 ai_providers 配置
        ai_providers = context.get_global_var("ai_providers") or {}
        
        # 2. 解析 STT 服务配置
        service_name = "azure_stt_service"  # 默认值
        if ai_providers and "stt" in ai_providers:
            stt_config = ai_providers["stt"]
            if isinstance(stt_config, dict) and stt_config:
                first_key = next(iter(stt_config))
                service_name = stt_config[first_key]
        
        # 3. 加载语言配置
        language = context.get_global_var("user.config.audio_settings.language")
        
        # 4. 加载音频文件目录配置
        config_manager = get_config_manager()
        audio_files_dir = config_manager.get_config("chat.paths.audio_files_dir", "audio_files")
        audio_files_dir = os.path.join(config_manager.runtime_root, audio_files_dir)

        # 5. 加载字符置信度阈值配置（数组格式 [threshold1, threshold2]）
        thresholds = context.get_global_var("user.config.audio_settings.confidence_threshold")
        if not isinstance(thresholds, list) or len(thresholds) < 2:
            thresholds = [0.8, 0.5]  # 默认值

        return {
            "service_name": service_name,
            "provider_name": service_name.split("_")[0],
            "language": language,
            "audio_files_dir": audio_files_dir,
            "confidence_threshold": thresholds
        }
    
    def _get_audio_file_paths(self, filename: str) -> tuple[str, str]:
        """
        获取音频文件的相对路径和绝对路径
        
        Args:
            filename: 文件名
            
        Returns:
            tuple: (相对路径, 绝对路径)
        """
        # 创建年份周数子目录
        now = datetime.datetime.now()
        year = now.year
        week_number = now.isocalendar()[1]  # 获取周数
        subdir = f"{year}_W{week_number:02d}"
        
        # 使用 pathlib 拼接路径
        base_dir = Path(self._cfg.get("audio_files_dir"))
        target_dir = base_dir / subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成相对路径和绝对路径
        relative_path = f"{subdir}/{filename}"
        absolute_path = str(target_dir / filename)
        
        return relative_path, absolute_path
    
    async def _save_audio_file_async(self, wav_bytes: bytes, filepath: str):
        """
        异步保存音频文件为 MP3 格式
        
        Args:
            wav_bytes: WAV 格式的音频字节数据
            filepath: 保存文件的完整路径
        """
        try:
            # 将音频转换和保存放入线程池执行，避免阻塞事件循环
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._save_audio_file_sync, wav_bytes, filepath)
            self._context.log_debug(f"音频文件已异步保存：{filepath}")
        except Exception as e:
            self._context.log_error(f"异步保存音频文件失败：{filepath}, 错误: {e}")
    
    def _save_audio_file_sync(self, wav_bytes: bytes, filepath: str):
        """
        同步保存音频文件为 MP3 格式（在后台线程中执行）
        
        Args:
            wav_bytes: WAV 格式的音频字节数据
            filepath: 保存文件的完整路径
        """
        audio_segment = AudioSegment.from_wav(io.BytesIO(wav_bytes))
        audio_segment.export(filepath, format="mp3")

    async def on_chunk_received(self, param_name: str, chunk: StreamChunk):
        if param_name == "speech_audio":
            self._latest_audio = chunk.data or None
            return

        if param_name == "speech_ended":
            # 语音已结束，若有缓存的 PCM 音频，执行识别
            if not self._latest_audio:
                return
            await self._recognize_and_emit(self._latest_audio)
            self._latest_audio = None

    async def _recognize_and_emit(self, audio: Dict[str, Any]):
        pcm_bytes: bytes = audio.get("data", b"")
        if not pcm_bytes:
            return

        # 开始AI指标监控
        monitor_id = None
        try:
            result = await call_utcp_tool("ai_metrics_service.start_monitoring", {})
            monitor_id = result.get("monitor_id")
        except Exception as e:
            self._context.log_debug(f"启动AI指标监控失败: {e}")

        # 记录识别开始时间
        start_time = time.time()

        try:
            wav_bytes = convert_pcm_to_wav(pcm_bytes)

            service = self._cfg["service_name"]
            result = await call_utcp_tool(
                f"{service}.recognize_speech",
                {
                    "audio_data": wav_bytes,
                    "audio_format": "wav",
                    "language": self._cfg["language"]
                }
            )
        finally:
            # 完成监控
            if monitor_id:
                try:
                    await call_utcp_tool("ai_metrics_service.finish_monitoring", {
                        "monitor_id": monitor_id,
                        "provider": self._cfg.get("provider_name", "azure"),
                        "model_name": self._cfg["service_name"],
                        "session_id": self._session_id,
                        "input_chars": len(pcm_bytes),  # 音频字节数作为输入
                        "output_chars": len(result.get("text", "")) if result else 0,  # 识别文本长度作为输出
                        "language": self._cfg["language"],
                        "audio_duration_ms": len(pcm_bytes) // (16000 * 2) * 1000 if pcm_bytes else 0  # 估算音频时长
                    })
                except Exception as e:
                    self._context.log_debug(f"完成AI指标监控失败: {e}")
        
        # 将 PCM 数据转换为 MP3 格式并保存到文件（异步，不阻塞主逻辑）
        self._sequence_number += 1
        filename = f"stt_{self._session_id}_{self._sequence_number:04d}.mp3"
        relative_path, absolute_path = self._get_audio_file_paths(filename)
        
        # 计算识别耗时
        recognition_time = time.time() - start_time
        self._context.log_info(f"STT 识别完成，音频大小: {len(pcm_bytes)} 字节，耗时: {recognition_time:.3f}秒，保存文件名：{filename}，结果: {result}")
        
        # 异步保存音频文件（使用绝对路径）
        asyncio.create_task(self._save_audio_file_async(wav_bytes, absolute_path))
        
        self._context.log_info(f"stt result: {result}")
        
        if result and result.get("success", False):
            if not result.get("text") == "":
                # 提取情感识别结果
                emotion = "neutral"
                ser_list = result.get("ser", [])
                if ser_list and len(ser_list) > 0:
                    emotion = ser_list[0]  # 取第一个情感识别结果
                
                # 根据字符置信度处理文本
                processed_text = self._process_text_with_confidence(
                    result.get("text", ""),
                    result.get("char_list", []),
                    result.get("char_confidences", [])
                )
                await self.emit_chunk("recognized_text", {
                    "text": processed_text,
                    "confidence": result.get("confidence", 0.0),
                    "audio_file_path": relative_path,  # 传递相对路径
                    "emotion": emotion  # 传递情感识别结果
                })
        else:
            # await self.emit_chunk("recognized_text", {"text": "", "confidence": 0.0})
            self._context.log_error(f"STT 识别失败: {result}")
            pass
    
    def _process_text_with_confidence(self, text: str, char_list: List[str], char_confidences: List[float]) -> str:
        """
        根据字符置信度标记文本
        - 大于置信度1：直接输出
        - 置信度1和置信度2之间：用[]包住
        - 小于置信度2：用()包住
        连续相同区间的标记符号公用
        """
        # 如果没有字符级信息，直接返回原文本
        if not char_list or not char_confidences or len(char_list) != len(char_confidences):
            return text
        
        thresholds = self._cfg.get("confidence_threshold", [0.8, 0.5])
        threshold1 = thresholds[0] if len(thresholds) > 0 else 0.8
        threshold2 = thresholds[1] if len(thresholds) > 1 else 0.5
        
        result_parts = []
        current_chars = []
        current_type = None  # 'high', 'medium', 'low'
        
        for char, conf in zip(char_list, char_confidences):
            # 确定当前字符的区间类型
            if conf > threshold1:
                char_type = 'high'
            elif conf >= threshold2:
                char_type = 'medium'
            else:
                char_type = 'low'
            
            # 如果类型改变，先处理之前累积的字符
            if current_type is not None and char_type != current_type:
                self._append_grouped_chars(result_parts, current_chars, current_type)
                current_chars = []
            
            current_type = char_type
            current_chars.append(char)
        
        # 处理最后一组
        if current_chars:
            self._append_grouped_chars(result_parts, current_chars, current_type)
        
        return ''.join(result_parts)
    
    def _append_grouped_chars(self, result_parts: List[str], chars: List[str], char_type: str):
        """将字符组添加到结果中，根据类型添加标记"""
        text_segment = ''.join(chars)
        if char_type == 'high':
            result_parts.append(text_segment)
        elif char_type == 'medium':
            result_parts.append(f'[{text_segment}]')
        else:  # 'low'
            result_parts.append(f'({text_segment})')
