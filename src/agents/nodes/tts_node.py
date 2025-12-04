"""
TTS 节点

输入:
- text_stream: 流式文本（每个chunk是一句完整的话，空文本表示结束）

输出:
- audio_stream: Opus编码的流式音频(60ms chunk) - 通过external_connection发送到设备
- tts_status: TTS状态通知消息 - 通过external_connection发送到设备
  - state: "start" | "stop" | "sentence_start" | "sentence_end"
  - text: 可选，sentence_start/sentence_end 时包含句子文本
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple
import asyncio
import re
import logging

# 确保可以导入 src 模块（当从外部项目加载时）
_file_path = Path(__file__).resolve()
_project_root = _file_path.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from stream_workflow.core import Node, ParameterSchema, StreamChunk, register_node
from stream_workflow.core.parameter import FieldSchema

from src.agents.utcp_tools import call_utcp_tool_stream, call_utcp_tool
from src.agents.nodes.tts.emotion_parser import EmotionParser


@register_node("tts_node")
class TTSNode(Node):
    """文本转语音节点。
    
    功能: 将文本流转换为语音音频流。接收流式文本输入，按句子进行语音合成，输出 Opus 编码的音频流。
    支持语音切换功能（通过 <voice|voice_name> 标签），支持情绪解析（从文本开头的 emoji 识别情绪），
    支持流式和非流式两种 TTS 合成模式。自动管理音频缓冲和播放速率，确保流畅的音频输出。
    
    配置参数: 无（配置从全局 ai_providers 和用户配置中加载）
    """
    
    EXECUTION_MODE = "streaming"

    INPUT_PARAMS = {
        "text_stream": ParameterSchema(is_streaming=True, schema={"text": "string"}),
        # 新增：中断当前输出（立即停止说话并清空缓存）
        "interrupt": ParameterSchema(is_streaming=True, schema={})
    }

    OUTPUT_PARAMS = {
        "audio_stream": ParameterSchema(is_streaming=True, schema={"data": "bytes"}),
        "tts_status": ParameterSchema(is_streaming=True, schema={"state": "string", "text": "string"})
    }
    
    # 配置参数定义（使用 FieldSchema 格式）
    CONFIG_PARAMS = {}
    
    # 语音命令正则表达式
    VOICE_COMMAND_PATTERN = re.compile(r'<voice\|([^>]+)>')

    async def run(self, context):
        self._user_data = context.get_global_var("user_data")
        self._logger = logging.getLogger(__name__)
        self._session_id = context.get_global_var("session_id")

        self._tts_cfg = self._load_config(context)
        
        # 创建OpusRepackager
        from src.common.utils.audio.opus_repackager import OpusRepackager
        self._repackager = OpusRepackager(
            sample_rate=16000,
            channels=1,
            target_chunk_ms=60.0,
            opus_bitrate=24000
        )
        
        # 创建AudioCodec
        from src.common.utils.audio.audio_codec import AudioCodec
        self._audio_codec = AudioCodec(sample_rate=16000, channels=1)
        
        # 速率控制参数
        self._frame_duration = 0.06  # 60ms
        self._buffer_time = 0.3      # 300ms
        
        # 状态跟踪
        self._total_sentences = 0
        self._is_tts_active = False  # TTS是否正在发送状态
        
        # 初始化情绪解析器
        self._emotion_parser = EmotionParser()

        # 创建AudioSend实例
        agent_id = context.get_global_var("agent_id")
        if agent_id is None:
            raise ValueError("agent_id 未在全局变量中设置")
        self._audio_send = AudioSend(
            agent_id=agent_id,
            emit_chunk=self.emit_chunk,
            frame_duration=self._frame_duration,
            buffer_time=self._buffer_time
        )
        
        # 启动AudioSend的事件处理器
        await self._audio_send.start()
        
        context.log_info(f"TTS 节点初始化完成: {self._tts_cfg}")
        await asyncio.sleep(float("inf"))

    async def shutdown(self):
        """清理节点资源"""
        # 停止音频发送
        if hasattr(self, '_audio_send'):
            await self._audio_send.stop()
        
        # 关闭音频编解码器
        if hasattr(self, '_audio_codec'):
            self._audio_codec.close()
        
        # 关闭OpusRepackager
        if hasattr(self, '_repackager'):
            self._repackager.close()

    def _load_config(self, context) -> Dict[str, Any]:
        """加载TTS配置（参考tts_handler.py:86-124）"""
        # 从全局变量获取合并后的 ai_providers 配置
        ai_providers = context.get_global_var("ai_providers") or {}
        
        # 2. 解析 TTS 服务配置
        service_name = "azure_tts_service"  # 默认值
        use_stream = True  # 默认使用流式
        if ai_providers and "tts" in ai_providers:
            tts_config = ai_providers["tts"]
            if isinstance(tts_config, dict) and tts_config:
                first_key = next(iter(tts_config))
                service_name = tts_config[first_key]
                
                # 检查是否使用流式合成
                if service_name.endswith(".stream"):
                    use_stream = True
                    service_name = service_name[:-7]  # 移除 .stream 后缀
                else:
                    use_stream = False
        
        # 3. 构建TTS配置
        config = {
            "service_name": service_name,
            "provider_name": service_name.split("_")[0],
            "use_stream": use_stream
        }
        
        return config
    
    def _parse_voice_commands(self, text: str) -> List[Tuple[str, str]]:
        """解析文本中的语音命令，返回文本片段和语音的配对列表"""
        if not text:
            return [("", "current")]
        
        # 查找所有语音命令的位置
        matches = list(self.VOICE_COMMAND_PATTERN.finditer(text))
        
        if not matches:
            # 没有语音命令，返回原始文本和当前语音
            return [(text, "current")]
        
        segments = []
        current_voice = "current"  # 当前语音状态
        last_end = 0
        
        for i, match in enumerate(matches):
            voice_name = match.group(1).strip()
            start = match.start()
            end = match.end()
            
            # 添加语音命令前的文本片段
            if start > last_end:
                segment_text = text[last_end:start].strip()
                if segment_text:
                    segments.append((segment_text, current_voice))
            
            # 更新当前语音状态
            current_voice = voice_name
            
            # 更新last_end到当前语音命令的结束位置
            last_end = end
        
        # 处理最后一个语音命令后的文本
        if last_end < len(text):
            segment_text = text[last_end:].strip()
            if segment_text:
                segments.append((segment_text, current_voice))
        
        # 如果没有有效的文本片段，返回空文本和当前语音
        if not segments:
            return [("", "current")]
        
        self._logger.debug(f"解析到 {len(segments)} 个文本片段: {segments}")
        return segments
    
    async def _handle_voice_switch(self, text: str) -> Tuple[List[Tuple[str, str]], str]:
        """处理声音切换标识，返回文本片段和语音的配对列表，以及去掉<voice>控制命令的干净文本"""
        # 解析声音切换命令
        segments = self._parse_voice_commands(text)
        
        # 处理每个文本片段的语音切换
        processed_segments = []
        clean_text_parts = []
        
        for segment_text, voice_name in segments:
            processed_segments.append((segment_text, voice_name))
            
            # 收集非空文本片段用于生成干净文本
            if segment_text:
                clean_text_parts.append(segment_text)
        
        # 合并所有文本片段生成干净文本
        clean_text = " ".join(clean_text_parts)
        
        return processed_segments, clean_text
    
    async def _set_voice(self, voice_name: str) -> bool:
        """设置当前语音并保存到memory"""
        try:
            # 验证语音名称
            if not self._is_valid_voice(voice_name):
                self._logger.warning(f"无效的语音名称: {voice_name}")
                return False
            
            # 检查功能是否启用
            if not self._is_voice_switching_enabled():
                self._logger.info(f"语音切换功能已禁用，尝试切换语音: {voice_name}")
                return False
            
            # 保存到记忆
            self._user_data.set_memory("preferences.current_voice", voice_name)
            self._logger.debug(f"语音状态已保存到记忆: {voice_name}")
            
            return True
            
        except Exception as e:
            self._logger.error(f"设置语音失败: {e}")
            return False
    
    def _is_valid_voice(self, voice_name: str) -> bool:
        """验证语音名称是否有效"""
        if voice_name == "original":
            return True
        
        # 获取可用的克隆声音列表
        available_voices = self._user_data.get_config("clone_voice._voice_names") or []
        return voice_name in available_voices
    
    def _is_voice_switching_enabled(self) -> bool:
        """检查语音切换功能是否启用"""
        enabled = self._user_data.get_config("function_settings.enable_user_clone_voice") or True
        self._logger.debug(f"语音切换功能状态: {enabled}")
        return enabled
    
    async def _get_voice_id(self, voice_name: str) -> str:
        """根据语音名称获取voice_id"""

        original_voice = self._user_data.get_config("profile.character.voice_name") or "default"

        if voice_name == "original":
            return original_voice
        elif voice_name == "current":
            voice_name = self._user_data.get_memory("preferences.current_voice") or original_voice

        voice_ids = self._user_data.get_config("clone_voice._voice_ids") or {}
        return voice_ids.get(voice_name, original_voice)

    async def on_chunk_received(self, param_name: str, chunk: StreamChunk):
        if param_name == "text_stream":
            sentence = (chunk.data or {}).get("text", "")
            if sentence:
                await self._process_sentence(sentence)
            elif sentence == "":  # 空文本表示结束
                # 所有句子处理完成
                await self._audio_send.tts_stop()
                self._emotion_parser.reset_emotion()
                self._is_tts_active = False
        elif param_name == "interrupt":
            # 立即中断当前播放并清空所有缓存
            await self._handle_interrupt()
    
    async def _process_sentence(self, text: str):
        """处理单个句子"""
        # 1. 检查是否需要发送TTS开始消息
        if not self._is_tts_active:
            await self._audio_send.tts_start()
            self._is_tts_active = True

        # 2. 处理声音切换标识，获取文本片段和语音配对，以及干净文本
        segments, clean_text = await self._handle_voice_switch(text)

        # 开始句子语音合成
        await self._audio_send.sentence_start(clean_text)
        # 3. 处理每个文本片段
        for segment_text, voice_name in segments:
            if segment_text:  # 只处理非空文本
                # 解析情绪（从文本开头的emoji）
                final_text, emotion = self._emotion_parser.parse_emotion(segment_text)
                # TTS合成并发送到AudioSend
                await self._synthesize_and_send(final_text, voice_name, emotion)
        # 结束句子语音合成
        await self._audio_send.sentence_end()
        
        self._total_sentences += 1
    
    async def _synthesize_and_send(self, text: str, voice_name: str, emotion: str):
        """TTS合成并发送到AudioSend"""
        # 开始AI指标监控
        monitor_id = None
        try:
            result = await call_utcp_tool("ai_metrics_service.start_monitoring", {})
            monitor_id = result.get("monitor_id")
        except Exception as e:
            self._logger.debug(f"启动AI指标监控失败: {e}")

        # 跟踪音频输出大小
        audio_output_size = 0

        try:
            # 设置语音并保存到memory
            if voice_name != "current":
                await self._set_voice(voice_name)
                self._logger.info(f"语音切换: -> {voice_name}")          # 获取voice_id
            # 获取voice_id
            voice_id = await self._get_voice_id(voice_name)
            # 调用TTS服务
            if self._tts_cfg.get("use_stream", True):
                audio_output_size = await self._stream_synthesis_to_audio_send(text, voice_id, emotion, voice_name)
            else:
                audio_output_size = await self._direct_synthesis_to_audio_send(text, voice_id, emotion, voice_name)
        finally:
            # 完成监控
            if monitor_id:
                try:
                    await call_utcp_tool("ai_metrics_service.finish_monitoring", {
                        "monitor_id": monitor_id,
                        "provider": self._tts_cfg.get("provider_name"),
                        "model_name": self._tts_cfg.get("service_name"),
                        "session_id": self._session_id,
                        "input_chars": len(text),
                        "output_chars": audio_output_size,  # TTS输出为音频文件大小（字节数）
                        "emotion": emotion
                    })
                except Exception as e:
                    self._logger.debug(f"完成AI指标监控失败: {e}")
    
    async def _stream_synthesis_to_audio_send(self, text: str, voice_id: str, emotion: str, role_hint: str = None) -> int:
        """流式TTS合成并发送到AudioSend，返回音频输出大小（字节数）"""
        import asyncio
        
        self._repackager.reset()
        
        # 仅在克隆角色时传入对应的 voice_params（来自 DB 缓存 clone_voice._voice_params）
        voice_params = {}
        try:
            # 确定当前使用的角色名标识
            role_name_for_params = None
            if role_hint == "current":
                current_voice = self._user_data.get_memory("preferences.current_voice") or (self._user_data.get_config("profile.character.voice_name") or "original")
                role_name_for_params = current_voice if current_voice not in ("original", "current") else None
            elif role_hint == "original":
                role_name_for_params = None
            else:
                role_name_for_params = role_hint

            if role_name_for_params:
                clone_params_map = self._user_data.get_config("clone_voice._voice_params") or {}
                if isinstance(clone_params_map, dict):
                    vp = clone_params_map.get(role_name_for_params) or {}
                    if isinstance(vp, dict):
                        voice_params = vp
        except Exception:
            voice_params = {}

        stream = await call_utcp_tool_stream(
            f"{self._tts_cfg['service_name']}.synthesize_speech_stream",
            {"text": text, "voice": voice_id, "emotion": emotion, "voice_params": voice_params}
        )
        
        # 跟踪实际发送的Opus帧大小
        total_audio_size = 0
        metadata_chunk = None
        
        async for chunk in stream:
            if chunk.get("type") == "opus_packet":
                audio_chunk = chunk.get("audio_chunk")
                packet = {
                    "data": audio_chunk,
                    "packet_duration_ms": 20.0
                }
                repackaged = self._repackager.add_packet(packet)
                for opus_chunk in repackaged:
                    if opus_chunk.opus_data:
                        total_audio_size += len(opus_chunk.opus_data)
                    await self._audio_send.add_audio_frame(opus_chunk.opus_data)
            elif chunk.get("type") == "metadata":
                # 保存metadata chunk，其中包含audio_size信息
                metadata_chunk = chunk
        
        # finalize
        final_chunks = self._repackager.finalize()
        for opus_chunk in final_chunks:
            await self._audio_send.add_audio_frame(opus_chunk.opus_data)
            if opus_chunk.opus_data:
                total_audio_size += len(opus_chunk.opus_data)
        
        # 优先使用metadata中的audio_size，如果没有则使用累计的实际发送大小
        if metadata_chunk and "audio_size" in metadata_chunk:
            return metadata_chunk["audio_size"]
        return total_audio_size
    
    async def _direct_synthesis_to_audio_send(self, text: str, voice_id: str, emotion: str, role_hint: str = None) -> int:
        """非流式TTS合成并发送到AudioSend，返回音频输出大小（字节数）"""
        # 仅在克隆角色时传入对应的 voice_params（来自 DB 缓存 clone_voice._voice_params）
        voice_params = {}
        try:
            role_name_for_params = None
            if role_hint == "current":
                current_voice = self._user_data.get_memory("preferences.current_voice") or (self._user_data.get_config("profile.character.voice_name") or "original")
                role_name_for_params = current_voice if current_voice not in ("original", "current") else None
            elif role_hint == "original":
                role_name_for_params = None
            else:
                role_name_for_params = role_hint

            if role_name_for_params:
                clone_params_map = self._user_data.get_config("clone_voice._voice_params") or {}
                if isinstance(clone_params_map, dict):
                    vp = clone_params_map.get(role_name_for_params) or {}
                    if isinstance(vp, dict):
                        voice_params = vp
        except Exception:
            voice_params = {}

        result = await call_utcp_tool(
            f"{self._tts_cfg['service_name']}.synthesize_speech",
            {"text": text, "voice": voice_id, "emotion": emotion, "voice_params": voice_params}
        )
        
        audio_data = (result or {}).get("audio_data", b"")
        audio_output_size = len(audio_data) if audio_data else 0
        
        if audio_data:
            # 将音频数据转换为Opus帧
            opus_frames = await self._convert_audio_to_opus_frames(audio_data)
            
            for frame_info in opus_frames:
                await self._audio_send.add_audio_frame(frame_info["data"])
        
        return audio_output_size
            
    async def _convert_audio_to_opus_frames(self, audio_data: bytes) -> List[Dict[str, Any]]:
        """将Azure TTS返回的音频数据转换为60ms的Opus帧 - 参考tts_handler_helper.py:_convert_audio_to_opus_frames"""
        try:
            if len(audio_data) >= 4 and audio_data[:4] == b'OggS':
                return await self._convert_opus_to_opus_60ms(audio_data)
            else:
                # 处理PCM格式的音频数据
                return await self._convert_pcm_to_opus_60ms(audio_data)
                
        except Exception as e:
            self.context.log_error(f"音频转换失败: {e}")
            # 降级处理：直接使用audio_codec编码
            return await self._convert_pcm_to_opus_60ms(audio_data)

    async def _convert_opus_to_opus_60ms(self, opus_data: bytes) -> List[Dict[str, Any]]:
        # 检查是否是Ogg封装的Opus格式
        if len(opus_data) >= 4 and opus_data[:4] == b'OggS':
            # 使用OpusStreamParser解析Ogg封装的Opus流
            from src.common.utils.audio.opus_stream_parse import OpusStreamParser
            
            parser = OpusStreamParser()
            results = parser.process_chunk(opus_data)
            
            # 处理解析结果，提取Opus packets
            opus_frames = []
            
            for result in results:
                if result['type'] == 'audio':
                    # 获取音频packets
                    packets = result.get('packets', [])
                    
                    # 逐个添加到repackager
                    for packet_info in packets:
                        # packet_info已经包含了'data'和'packet_duration_ms'
                        chunks = self._repackager.add_packet(packet_info)
                        
                        # 收集重打包后的chunks
                        for chunk in chunks:
                            opus_frames.append({
                                "data": chunk.opus_data,
                                "packet_duration_ms": chunk.duration_ms
                            })
            
            # 处理剩余数据（自动填充到60ms）
            final_chunks = self._repackager.finalize()
            for chunk in final_chunks:
                opus_frames.append({
                    "data": chunk.opus_data,
                    "packet_duration_ms": chunk.duration_ms
                })
            
            return opus_frames

    async def _convert_pcm_to_opus_60ms(self, pcm_data: bytes) -> List[Dict[str, Any]]:
        """将PCM音频数据转换为Opus帧"""
        try:
            # 使用成员变量的audio_codec进行编码
            opus_frames_list = await self._audio_codec.encode_opus(pcm_data)
            
            # 将Opus帧列表转换为所需的格式
            opus_frames = []
            frame_duration_ms = 60.0  # Opus标准帧时长
            
            for opus_frame in opus_frames_list:
                if opus_frame:
                    opus_frames.append({
                        "data": opus_frame,
                        "packet_duration_ms": frame_duration_ms
                    })
            
            return opus_frames
            
        except Exception as e:
            self.context.log_error(f"PCM转Opus失败: {e}")
            # 最后的降级处理：返回原始数据
            return [{
                "data": pcm_data,
                "packet_duration_ms": 60.0
            }]
    
    async def _handle_interrupt(self):
        """处理中断：立即停止播放，清空缓存，并发送tts_stop。"""
        try:
            await self._audio_send.interrupt()
            self._repackager.reset()
        finally:
            # 重置本地状态
            self._emotion_parser.reset_emotion()
            self._is_tts_active = False


class AudioSend:
    """音频发送类 - 独立处理音频播放和消息发送"""
    
    def __init__(self, agent_id: int, emit_chunk, frame_duration: float, buffer_time: float):
        self.agent_id = agent_id
        self.emit_chunk = emit_chunk
        self.frame_duration = frame_duration
        self.buffer_time = buffer_time
        
        # 初始化日志记录器
        self._logger = logging.getLogger(__name__)
        
        # 音频队列和状态
        self._audio_queue = None
        self._event_queue = asyncio.Queue()  # 事件队列
        self._is_playing = False
        self._event_task = None  # 事件处理任务
        self._current_sentence = None
        self._is_running = False  # 是否正在运行
        
    async def start(self):
        """启动AudioSend - 启动事件处理器"""
        if not self._is_running:
            self._is_running = True
            self._event_task = asyncio.create_task(self._event_processor())
    
    async def stop(self):
        """停止AudioSend - 停止事件处理器并清理所有资源"""
        if not self._is_running:
            return
        
        self._is_running = False
        self._is_playing = False
        
        # 清空音频队列
        if self._audio_queue is not None:
            try:
                while not self._audio_queue.empty():
                    try:
                        _ = self._audio_queue.get_nowait()
                        self._audio_queue.task_done()
                    except Exception:
                        break
                # 放入结束标记
                try:
                    await self._audio_queue.put(None)
                except Exception:
                    pass
            except Exception:
                pass
            self._audio_queue = None
        
        # 清空事件队列并发送结束标记
        try:
            while not self._event_queue.empty():
                try:
                    _ = self._event_queue.get_nowait()
                    self._event_queue.task_done()
                except Exception:
                    break
            await self._event_queue.put(None)
        except Exception:
            pass
        
        # 等待事件处理任务完成
        if self._event_task:
            try:
                await asyncio.wait_for(self._event_task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                if not self._event_task.done():
                    self._event_task.cancel()
                    try:
                        await self._event_task
                    except asyncio.CancelledError:
                        pass
            except Exception:
                pass
            self._event_task = None
    
    async def _event_processor(self):
        """事件处理器 - 按顺序处理事件"""
        while self._is_running:
            try:
                event_data = await self._event_queue.get()
                if event_data is None:  # 结束标记
                    break
                
                event_type, data = event_data
                await self._process_event(event_type, data)
                self._event_queue.task_done()
                
            except Exception as e:
                self._logger.error(f"事件处理错误: {e}", exc_info=True)
                break
    
    async def _process_event(self, event_type: str, data = None):
        """处理具体事件"""
        if event_type == "audio_data":
            await self._playback_worker(data)
        elif event_type == "tts_start":
            await self.emit_chunk("tts_status", {"state": "start", "text": ""})
        elif event_type == "tts_stop":
            await self.emit_chunk("tts_status", {"state": "stop", "text": ""})
        elif event_type == "sentence_start":
            await self.emit_chunk("tts_status", {"state": "sentence_start", "text": data or ""})
        elif event_type == "sentence_end":
            await self.emit_chunk("tts_status", {"state": "sentence_end", "text": data or ""})
            await asyncio.sleep(0.3)
        else:
            self._logger.warning(f"未知的事件类型: {event_type}")
    
    async def tts_start(self):
        """发送TTS开始消息"""
        await self._event_queue.put(("tts_start", {}))
    
    async def tts_stop(self):
        """发送TTS停止消息"""
        await self._event_queue.put(("tts_stop", {}))

    async def sentence_start(self, text: str):
        """开始句子播放"""
        self._current_sentence = text
        await self._event_queue.put(("sentence_start", self._current_sentence))
        self._audio_queue = asyncio.Queue()
        await self._event_queue.put(("audio_data", self._audio_queue))
    
    async def add_audio_frame(self, frame_data: bytes):
        """添加音频帧到队列"""
        # 中断后_audio_queue可能为None，直接丢弃帧以确保安全
        if self._audio_queue is not None:
            await self._audio_queue.put(frame_data)
    
    async def sentence_end(self):
        """结束语音合成"""
        await self._audio_queue.put(None)
        self._audio_queue = None
        await self._event_queue.put(("sentence_end", self._current_sentence))
    
    async def _playback_worker(self, audio_queue: asyncio.Queue):
        """播放工作器"""
        self._is_playing = True

        import time
        
        # 等待缓冲数据，设置超时防止死循环
        buffer_frames = int(self.buffer_time / self.frame_duration)
        buffer_start_time = time.time()
        while audio_queue.qsize() < buffer_frames:
            # 如果等待时间超过buffer_time的2倍，跳过缓冲
            if time.time() - buffer_start_time > self.buffer_time * 2:
                break
            await asyncio.sleep(0.01)
        
        # 流式发送
        start_time = time.time()
        frame_count = 0
        
        async for frame in self._queue_iterator(audio_queue):
            if not self._is_running:
                break

            target_time = start_time + frame_count * self.frame_duration - self.buffer_time
            current_time = time.time()
            
            sleep_duration = target_time - current_time
            if sleep_duration > 0:
                await asyncio.sleep(sleep_duration)
            
            # 发送音频帧
            await self.emit_chunk("audio_stream", {"data": frame})
            frame_count += 1
        
        # 播放完成
        self._is_playing = False
    
    async def _queue_iterator(self, audio_queue: asyncio.Queue):
        """异步队列迭代器"""
        while True:
            frame = await audio_queue.get()
            if frame is None:  # 结束标记
                audio_queue.task_done()
                break
            yield frame
            audio_queue.task_done()

    async def interrupt(self):
        """立即中断：停止当前播放、清空所有缓存队列，并发送tts_stop。"""
        # 清空当前音频队列并终止播放
        
        was_playing = self._is_playing
        self._is_playing = False

        try:
            if self._audio_queue is not None:
                # 尽量清空已有帧
                try:
                    while not self._audio_queue.empty():
                        _ = self._audio_queue.get_nowait()
                        self._audio_queue.task_done()
                except Exception:
                    pass
                # 放入结束标记使播放线程尽快退出
                try:
                    await self._audio_queue.put(None)
                except Exception:
                    pass
                self._audio_queue = None
        except Exception:
            pass

        # 清空事件队列，避免发送滞后的开始/结束事件
        try:
            while not self._event_queue.empty():
                try:
                    _ = self._event_queue.get_nowait()
                    self._event_queue.task_done()
                except Exception:
                    break
        except Exception:
            pass

        if was_playing:
            # 发送tts_stop，通知设备立即停止
            await self._event_queue.put(("tts_stop", {}))
