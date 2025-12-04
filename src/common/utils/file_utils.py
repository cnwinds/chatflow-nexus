"""
文件工具函数

提供通用的文件操作和文件名生成功能
"""

import uuid
from datetime import datetime
from typing import Tuple


def generate_unique_filename(prefix: str = "file", extension: str = "txt") -> Tuple[str, str]:
    """
    生成唯一文件名和ID
    
    Args:
        prefix: 文件名前缀
        extension: 文件扩展名
        
    Returns:
        (filename, unique_id): 文件名和唯一ID的元组
        
    Examples:
        >>> filename, unique_id = generate_unique_filename("audio", "mp3")
        >>> print(filename)  # "audio_20241201_143022_a1b2c3d4.mp3"
        >>> print(unique_id)  # "a1b2c3d4"
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    filename = f"{prefix}_{timestamp}_{unique_id}.{extension}"
    return filename, unique_id


def generate_audio_filename(audio_format: str) -> Tuple[str, str]:
    """
    生成音频文件名和唯一ID
    
    Args:
        audio_format: 音频格式 ("mp3", "wav", "ogg", "aac" 等)
        
    Returns:
        (filename, unique_id): 音频文件名和唯一ID的元组
        
    Examples:
        >>> filename, unique_id = generate_audio_filename("mp3")
        >>> print(filename)  # "audio_20241201_143022_a1b2c3d4.mp3"
    """
    # 音频格式到文件扩展名的映射
    format_mapping = {
        "mp3": "mp3",
        "wav": "wav",
        "ogg": "ogg", 
        "aac": "aac",
        "flac": "flac"
    }
    
    file_extension = format_mapping.get(audio_format.lower(), "wav")
    return generate_unique_filename("audio", file_extension)


def generate_log_filename(log_type: str = "app") -> Tuple[str, str]:
    """
    生成日志文件名和唯一ID
    
    Args:
        log_type: 日志类型 ("app", "error", "debug", "access" 等)
        
    Returns:
        (filename, unique_id): 日志文件名和唯一ID的元组
        
    Examples:
        >>> filename, unique_id = generate_log_filename("error")
        >>> print(filename)  # "error_20241201_143022_a1b2c3d4.log"
    """
    return generate_unique_filename(log_type, "log")


def generate_temp_filename(extension: str = "tmp") -> Tuple[str, str]:
    """
    生成临时文件名和唯一ID
    
    Args:
        extension: 临时文件扩展名
        
    Returns:
        (filename, unique_id): 临时文件名和唯一ID的元组
        
    Examples:
        >>> filename, unique_id = generate_temp_filename("tmp")
        >>> print(filename)  # "temp_20241201_143022_a1b2c3d4.tmp"
    """
    return generate_unique_filename("temp", extension)


def generate_backup_filename(original_name: str = "data") -> Tuple[str, str]:
    """
    生成备份文件名和唯一ID
    
    Args:
        original_name: 原始文件名（不含扩展名）
        
    Returns:
        (filename, unique_id): 备份文件名和唯一ID的元组
        
    Examples:
        >>> filename, unique_id = generate_backup_filename("config")
        >>> print(filename)  # "backup_20241201_143022_a1b2c3d4.bak"
    """
    return generate_unique_filename("backup", "bak")
