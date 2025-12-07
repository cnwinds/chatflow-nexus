"""
音频处理工具函数
"""

import io
import logging
import os
import re
import tempfile
import wave
from typing import Any, Dict, List, Optional, Union, Tuple
from contextlib import contextmanager

import numpy as np
import opuslib_next
import pydub
from pydub import AudioSegment

logger = logging.getLogger(__name__)


@contextmanager
def temp_audio_file(suffix: str = '.wav'):
    """
    临时音频文件上下文管理器
    
    Args:
        suffix: 文件后缀，默认为'.wav'
        
    Yields:
        str: 临时文件路径
        
    Example:
        with temp_audio_file('.wav') as temp_path:
            # 使用临时文件
            pass
        # 文件会自动清理
    """
    temp_file = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
            temp_path = temp_file.name
        yield temp_path
    finally:
        if temp_file and os.path.exists(temp_file.name):
            try:
                os.unlink(temp_file.name)
            except Exception as e:
                logger.warning(f"清理临时文件失败: {e}")

def convert_float32_to_int16(float32_data: np.ndarray) -> np.ndarray:
    """
    将Float32格式的音频数据转换为Int16格式
    
    Args:
        float32_data: Float32格式的音频数据 (-1.0 到 1.0)
        
    Returns:
        Int16格式的音频数据 (-32768 到 32767)
    """
    try:
        # 限制数据范围到 [-1.0, 1.0]
        clipped_data = np.clip(float32_data, -1.0, 1.0)
        
        # 转换为Int16
        int16_data = (clipped_data * 32767).astype(np.int16)
        
        logger.debug(f"转换Float32到Int16: {len(float32_data)} 样本")
        return int16_data
        
    except Exception as e:
        logger.error(f"Float32到Int16转换失败: {e}")
        raise ValueError(f"音频格式转换失败: {e}")


def convert_int16_to_float32(int16_data: np.ndarray) -> np.ndarray:
    """
    将Int16格式的音频数据转换为Float32格式
    
    Args:
        int16_data: Int16格式的音频数据 (-32768 到 32767)
        
    Returns:
        Float32格式的音频数据 (-1.0 到 1.0)
    """
    try:
        # 转换为Float32并归一化
        float32_data = int16_data.astype(np.float32) / 32767.0
        
        logger.debug(f"转换Int16到Float32: {len(int16_data)} 样本")
        return float32_data
        
    except Exception as e:
        logger.error(f"Int16到Float32转换失败: {e}")
        raise ValueError(f"音频格式转换失败: {e}")


def validate_audio_format(data: Union[np.ndarray, bytes], 
                         expected_sample_rate: int = 16000,
                         expected_channels: int = 1) -> bool:
    """
    验证音频数据格式是否符合要求
    
    Args:
        data: 音频数据
        expected_sample_rate: 期望的采样率
        expected_channels: 期望的声道数
        
    Returns:
        是否符合格式要求
    """
    try:
        if isinstance(data, bytes):
            # 检查字节数据长度
            if len(data) == 0:
                return False
            # 对于Opus数据，无法直接验证格式，返回True
            return True
            
        elif isinstance(data, np.ndarray):
            # 检查数组维度
            if data.ndim == 1 and expected_channels == 1:
                return True
            elif data.ndim == 2 and data.shape[1] == expected_channels:
                return True
            else:
                return False
                
        return False
        
    except Exception as e:
        logger.error(f"音频格式验证失败: {e}")
        return False


def calculate_audio_duration(data_length: int, 
                           sample_rate: int = 16000,
                           bytes_per_sample: int = 2) -> float:
    """
    计算音频数据的时长
    
    Args:
        data_length: 数据长度（字节数或样本数）
        sample_rate: 采样率
        bytes_per_sample: 每样本字节数
        
    Returns:
        音频时长（秒）
    """
    try:
        if bytes_per_sample > 1:
            # 如果提供的是字节长度
            samples = data_length // bytes_per_sample
        else:
            # 如果提供的是样本数
            samples = data_length
            
        duration = samples / sample_rate
        return duration
        
    except Exception as e:
        logger.error(f"音频时长计算失败: {e}")
        return 0.0


def create_silence(duration_seconds: float, 
                  sample_rate: int = 16000,
                  dtype: type = np.int16) -> np.ndarray:
    """
    创建指定时长的静音数据
    
    Args:
        duration_seconds: 静音时长（秒）
        sample_rate: 采样率
        dtype: 数据类型
        
    Returns:
        静音音频数据
    """
    try:
        samples = int(duration_seconds * sample_rate)
        silence = np.zeros(samples, dtype=dtype)
        
        logger.debug(f"创建静音数据: {duration_seconds}秒, {samples}样本")
        return silence
        
    except Exception as e:
        logger.error(f"创建静音数据失败: {e}")
        raise ValueError(f"静音数据创建失败: {e}")

def convert_wav_file_to_pcm(wav_data: bytes, target_sample_rate: int = 16000) -> Optional[np.ndarray]:
    """
    将WAV格式音频转换为PCM数据
    
    Args:
        wav_data: WAV格式音频数据
        target_sample_rate: 目标采样率
        
    Returns:
        PCM音频数据（numpy数组），如果失败则返回None
    """
    try:
        # 创建内存文件对象
        wav_file = io.BytesIO(wav_data)
        
        # 读取WAV文件
        with wave.open(wav_file, 'rb') as wf:
            # 获取音频参数
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            sample_rate = wf.getframerate()
            n_frames = wf.getnframes()
            
            # 读取音频数据
            audio_data = wf.readframes(n_frames)
            
            # 转换为numpy数组
            if sample_width == 2:  # 16位
                audio_array = np.frombuffer(audio_data, dtype=np.int16)
            elif sample_width == 4:  # 32位
                audio_array = np.frombuffer(audio_data, dtype=np.int32)
            else:  # 8位
                audio_array = np.frombuffer(audio_data, dtype=np.uint8).astype(np.int16) - 128
            
            # 如果是立体声，转换为单声道
            if channels == 2:
                audio_array = audio_array.reshape(-1, 2).mean(axis=1).astype(np.int16)
            
            # 重采样到目标采样率（如果需要）
            if sample_rate != target_sample_rate:
                audio_array = resample_audio(audio_array, sample_rate, target_sample_rate)
            
            logger.debug(f"WAV转PCM成功: {len(audio_array)} 样本, 采样率 {target_sample_rate}Hz")
            return audio_array
            
    except Exception as e:
        logger.error(f"WAV转PCM转换失败: {e}")
        return None


def resample_audio(audio_data: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """
    重采样音频数据
    
    Args:
        audio_data: 原始音频数据
        src_rate: 原始采样率
        dst_rate: 目标采样率
        
    Returns:
        重采样后的音频数据
    """
    try:
        # 简单的线性插值重采样
        ratio = dst_rate / src_rate
        new_length = int(len(audio_data) * ratio)
        
        # 创建新的时间轴
        old_indices = np.arange(len(audio_data))
        new_indices = np.linspace(0, len(audio_data) - 1, new_length)
        
        # 线性插值
        resampled = np.interp(new_indices, old_indices, audio_data)
        
        logger.debug(f"音频重采样成功: {len(audio_data)} -> {len(resampled)} 样本, {src_rate}Hz -> {dst_rate}Hz")
        return resampled.astype(np.int16)
        
    except Exception as e:
        logger.error(f"音频重采样失败: {e}")
        return audio_data


def decode_opus(opus_data: List[bytes]) -> bytes:
    """
    将Opus音频数据解码为PCM数据
    
    Args:
        opus_data: Opus音频数据包列表
        
    Returns:
        PCM音频数据
    """
    try:
        decoder = opuslib_next.Decoder(16000, 1)  # 16kHz, 单声道
        pcm_data = []

        for opus_packet in opus_data:
            try:
                pcm_frame = decoder.decode(opus_packet, 960)  # 960 samples = 60ms
                pcm_data.append(pcm_frame)
            except opuslib_next.OpusError as e:
                logger.error(f"Opus解码错误: {e}", exc_info=True)

        return b"".join(pcm_data)
        
    except Exception as e:
        logger.error(f"Opus解码失败: {e}")
        return b''

async def convert_opus_to_wav(opus_data: bytes) -> bytes:
    """
    将Opus格式转换为WAV格式
    
    Args:
        opus_data: Opus音频数据
        
    Returns:
        WAV音频数据
    """
    try:
        # 将单个Opus数据包转换为列表
        opus_packets = [opus_data]
        
        # 解码Opus数据
        pcm_data = decode_opus(opus_packets)
        
        if not pcm_data:
            logger.error("Opus解码失败")
            return b''
        
        # 使用临时文件上下文管理器
        with temp_audio_file('.wav') as temp_path:
            # 使用通用函数保存WAV文件
            success = save_pcm_to_audio_file(
                pcm_data=pcm_data,
                output_path=temp_path,
                audio_format="wav",
                sample_rate=16000
            )
            
            if not success:
                logger.error("WAV文件保存失败")
                return b''
            
            # 读取WAV文件内容
            with open(temp_path, 'rb') as f:
                wav_data = f.read()
        
        logger.info(f"Opus转WAV成功: {len(opus_data)} -> {len(wav_data)} 字节")
        return wav_data
        
    except Exception as e:
        logger.error(f"Opus转WAV失败: {e}")
        return b''


def convert_pcm_to_wav(pcm_data: bytes, sample_rate: int = 16000) -> bytes:
    """
    将PCM数据转换为WAV格式
    
    Args:
        pcm_data: PCM音频数据
        sample_rate: 采样率
        
    Returns:
        WAV音频数据
    """
    try:
        # 使用临时文件上下文管理器
        with temp_audio_file('.wav') as temp_path:
            # 使用通用函数保存WAV文件
            success = save_pcm_to_audio_file(
                pcm_data=pcm_data,
                output_path=temp_path,
                audio_format="wav",
                sample_rate=sample_rate
            )
            
            if not success:
                logger.error("WAV文件保存失败")
                return b''
            
            # 读取WAV文件内容
            with open(temp_path, 'rb') as f:
                wav_data = f.read()
        
        logger.debug(f"PCM转WAV成功: {len(pcm_data)} 样本 -> {len(wav_data)} 字节")
        return wav_data
        
    except Exception as e:
        logger.error(f"PCM转WAV失败: {e}")
        return b''

def save_pcm_to_audio_file(pcm_data: bytes, output_path: str, 
                          audio_format: str = "wav", 
                          sample_rate: int = 16000,
                          bitrate: str = "64k") -> bool:
    """
    将PCM数据保存为指定格式的音频文件
    
    Args:
        pcm_data: PCM音频数据
        output_path: 输出文件路径
        audio_format: 音频格式 ("wav", "mp3", "ogg", "aac", "flac" 等)
        sample_rate: 采样率
        bitrate: 比特率（用于有损压缩格式）
        
    Returns:
        是否保存成功
    """
    try:
        format_lower = audio_format.lower()
        
        # 无损格式：使用wave库保存
        if format_lower == "wav":
            return _save_wav_format(pcm_data, output_path, sample_rate)
        
        # 压缩格式：使用pydub库保存
        elif format_lower in ["mp3", "ogg", "aac", "flac"]:
            return _save_compressed_format(pcm_data, output_path, format_lower, sample_rate, bitrate)
        
        else:
            logger.error(f"不支持的音频格式: {audio_format}")
            return False
            
    except Exception as e:
        logger.error(f"保存音频文件失败: {e}")
        return False


def _save_wav_format(pcm_data: bytes, output_path: str, sample_rate: int) -> bool:
    """保存WAV格式音频文件"""
    try:
        with wave.open(output_path, "wb") as wf:
            wf.setnchannels(1)  # 单声道
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_data)
        
        logger.debug(f"WAV音频文件已保存: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"保存WAV文件失败: {e}")
        return False


def _save_compressed_format(pcm_data: bytes, output_path: str, audio_format: str, 
                          sample_rate: int, bitrate: str) -> bool:
    """保存压缩格式音频文件"""
    try:
        # 创建AudioSegment对象
        audio_segment = AudioSegment(
            pcm_data,
            frame_rate=sample_rate,
            sample_width=2,    # 16-bit
            channels=1         # 单声道
        )
        
        # 导出为指定格式
        audio_segment.export(output_path, format=audio_format, bitrate=bitrate)
        logger.debug(f"{audio_format.upper()}音频文件已保存: {output_path} (比特率: {bitrate})")
        return True
        
    except Exception as e:
        logger.error(f"保存{audio_format.upper()}文件失败: {e}")
        return False

def split_text_by_sentences(text: str) -> Tuple[str, List[str]]:
    """
    按结束标点分割文本为句子列表。输入的文本为流式追加。
    
    规则：
    1. 遇到结束标点（。！？.!?～…“”"），并且之后出现非结束标点则断句在非标点之前。
    2. <...> 标签会触发断句，标签本身（从 < 到 >）作为独立句子
    
    Args:
        text: 要分割的文本
        
    Returns:
        去掉分隔出句子后的剩余文本  
        句子列表，每个句子完全保留所有空白字符（空格、制表符、换行符等）
    """
    # 结束标点集合
    end_punctuations = set('。！？.!?～…“”"')
    
    sentences = []
    sentence_start = 0
    i = 0
    
    # 检查是否有未闭合的标签
    def has_unclosed_tag_from(start_pos: int) -> bool:
        """从指定位置检查是否有未闭合的 <"""
        for j in range(start_pos, len(text)):
            if text[j] == '<':
                # 检查后面是否有对应的 >
                for k in range(j + 1, len(text)):
                    if text[k] == '>':
                        return False  # 找到了闭合的 >
                return True  # 没找到闭合的 >
        return False
    
    while i < len(text):
        char = text[i]
        
        # 如果遇到 <，需要找到对应的 > 形成完整标签
        if char == '<':
            # 先将 < 之前的内容断句
            before = text[sentence_start:i]
            # 检查是否包含非空白字符
            if before.strip():
                sentences.append(before)
            
            # 查找对应的 >
            j = i + 1
            found_close = False
            while j < len(text):
                if text[j] == '>':
                    # 找到了闭合的 >，提取完整标签
                    tag = text[i:j+1]
                    sentences.append(tag)
                    sentence_start = j + 1
                    i = j + 1
                    found_close = True
                    break
                j += 1
            
            # 如果没找到闭合的 >，说明标签还未完整，等待更多输入
            if not found_close:
                # 未闭合的标签保留在 remaining 中
                break
            
            continue
        
        # 如果当前字符是结束标点
        if char in end_punctuations:
            # 查找下一个非结束标点字符的位置（不跳过任何空白字符）
            j = i + 1
            found_non_end_punct = False
            
            while j < len(text):
                next_char = text[j]
                
                # 如果遇到 <，也视为找到断句点
                if next_char == '<':
                    sentence = text[sentence_start:j]
                    # 检查是否包含非空白字符
                    if sentence.strip():
                        sentences.append(sentence)
                    sentence_start = j
                    found_non_end_punct = True
                    i = j
                    break
                
                # 不跳过任何空白字符，保留所有空格、制表符和换行符
                # 如果遇到非结束标点字符，则在此处断句
                if next_char not in end_punctuations:
                    # 提取句子（从 sentence_start 到 j-1），完全保留所有空白字符
                    sentence = text[sentence_start:j]
                    # 检查是否包含非空白字符
                    if sentence.strip():
                        sentences.append(sentence)
                    sentence_start = j
                    found_non_end_punct = True
                    break
                else:
                    # 继续向后查找（连续的结束标点）
                    j += 1
            
            # 如果找到了断句点，更新 i
            if found_non_end_punct:
                i = j
                continue
        
        i += 1
    
    # 剩余文本（未形成完整句子的部分），完全保留所有空白字符
    remaining_text = text[sentence_start:]
    
    return remaining_text, sentences

# 流式测试辅助函数
def test_streaming(test_name: str, full_text: str, show_detail: bool = True):
    """
    逐字符流式测试函数
    
    Args:
        test_name: 测试名称
        full_text: 完整文本
        show_detail: 是否显示每个字符的详细输出
    """
    print(f"\n{'='*60}")
    print(f"{test_name}")
    print(f"完整文本: {full_text}")
    print(f"{'='*60}")
    
    accumulated = ""
    all_sentences_collected = []
    
    for i, char in enumerate(full_text):
        accumulated += char
        remaining, sentences = split_text_by_sentences(accumulated)
        
        # 检测是否有新句子产生
        new_sentences = sentences[len(all_sentences_collected):]
        
        if show_detail:
            print(f"[{i+1:3d}] 追加字符: '{char}' | 累积: '{accumulated}'")
            if new_sentences:
                print(f"      ✓ 新产生句子: {new_sentences}")
            print(f"      → 剩余文本: '{remaining}'")
            print(f"      → 全部句子: {sentences}")
        elif new_sentences:
            # 简略模式：只在产生新句子时输出
            print(f"[{i+1:3d}] '{char}' → 新句子: {new_sentences}")
        
        all_sentences_collected = sentences.copy()
    
    # 最终结果
    print(f"\n最终结果:")
    print(f"  全部句子: {all_sentences_collected}")
    print(f"  剩余文本: '{remaining}'")
    print()


# 测试代码
if __name__ == "__main__":
    # 测试用例1：标签之前的内容立即断句
    test_streaming(
        "测试1 - 标签前内容立即断句",
        "这是一段文本<tag>标签内容</tag>后面的内容",
        show_detail=False
    )
    
    # 测试用例2：标签前有结束标点
    test_streaming(
        "测试2 - 标签前有结束标点",
        "第一句。第二句！<tag>标签</tag>第三句",
        show_detail=False
    )
    
    # 测试用例3：标签前无标点
    test_streaming(
        "测试3 - 标签前无标点",
        "这是文本<tag>标签</tag>继续",
        show_detail=False
    )
    
    # 测试用例4：未闭合标签（详细模式）
    test_streaming(
        "测试4 - 未闭合标签（详细）",
        "第一句。第二句！<tag>标签内容",
        show_detail=True
    )
    
    # 测试用例5：多个标签
    test_streaming(
        "测试5 - 多个标签",
        "开始<tag1>内容1</tag1>中间<tag2>内容2</tag2>结束",
        show_detail=False
    )
    
    # 测试用例6：标签后立即是结束标点
    test_streaming(
        "测试6 - 标签后立即结束标点",
        "文本<tag>标签</tag>。后续内容。",
        show_detail=False
    )
    
    # 测试用例7：标签内有标点
    test_streaming(
        "测试7 - 标签内有标点",
        "开始。<tag>这里。有标点！</tag>结束。",
        show_detail=False
    )
    
    # 测试用例8：紧邻的标签和标点
    test_streaming(
        "测试8 - 紧邻的标签和标点",
        "文本<tag>标签</tag>。继续。",
        show_detail=False
    )
    
    # 测试用例9：连续标点
    test_streaming(
        "测试9 - 连续标点",
        "真的吗？！！不敢相信。。。太棒了！",
        show_detail=False
    )
    
    # 测试用例10：复杂场景（详细模式）
    test_streaming(
        "测试10 - 复杂场景（详细）",
        "开始。<a>标签A</a>中间文本<b>标签B内。容</b>结束！",
        show_detail=True
    )
    
    # 测试用例11：引号内的标点
    test_streaming(
        "测试11 - 引号内的标点",
        '他说："你好！"然后离开了。',
        show_detail=False
    )
    
    # 测试用例12：引号作为结束标点
    test_streaming(
        "测试12 - 引号作为结束标点",
        '第一句。"这是引用内容。"第二句。',
        show_detail=False
    )
    
    # 测试用例13：换行符
    test_streaming(
        "测试13 - 换行符",
        "第一句。\n第二句！\n第三句？",
        show_detail=False
    )
    
    # 测试用例14：标签+换行符
    test_streaming(
        "测试14 - 标签+换行符",
        "开始。<tag>内容</tag>\n继续。结束！",
        show_detail=False
    )
    
    # 测试用例15：引号+标签
    test_streaming(
        "测试15 - 引号+标签",
        '说："开始<tag>标签</tag>结束。"完成！',
        show_detail=False
    )
    
    # 测试用例16：多行文本+标签（详细）
    test_streaming(
        "测试16 - 多行文本+标签（详细）",
        "第一行。\n<tag>标签内容</tag>\n第二行！",
        show_detail=True
    )
    
    # 测试用例17：复杂引号场景
    test_streaming(
        "测试17 - 复杂引号场景",
        '他问："你好吗？"我答："很好！"结束。',
        show_detail=False
    )
    
    # 测试用例18：引号+换行+标签组合
    test_streaming(
        "测试18 - 引号+换行+标签组合",
        '开始。\n"引用：<tag>内容</tag>结束。"\n继续！',
        show_detail=False
    )
    
    # 测试用例19：省略号+换行
    test_streaming(
        "测试19 - 省略号+换行",
        "思考中…\n明白了。\n开始吧！",
        show_detail=False
    )
    
    # 测试用例20：未闭合标签+引号（详细）
    test_streaming(
        "测试20 - 未闭合标签+引号（详细）",
        '第一句。<tag>内容："引用',
        show_detail=True
    )
    
    # 测试用例21：多层嵌套
    test_streaming(
        "测试21 - 多层嵌套",
        '外层。\n<outer>外标签\n"引用内容。"</outer>\n结束！',
        show_detail=False
    )
    
    # 测试用例22：连续换行
    test_streaming(
        "测试22 - 连续换行",
        "第一句。\n\n\n第二句！",
        show_detail=False
    )
    
    # 测试用例23：标签内换行
    test_streaming(
        "测试23 - 标签内换行",
        "开始。<tag>内容\n有换行。\n</tag>结束！",
        show_detail=False
    )
    
    # 测试用例24：极端组合（详细）
    test_streaming(
        "测试24 - 极端组合（详细）",
        '开始。\n<tag1>"第一段。\n"</tag1>中间！\n<tag2>第二段…</tag2>\n"最后？"',
        show_detail=True
    )
