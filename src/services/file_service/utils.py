"""
工具函数：编码检测、路径处理、行号处理等
"""

import os
import logging
from pathlib import Path
from typing import Optional, Tuple, List
import chardet

logger = logging.getLogger(__name__)


def detect_encoding(file_path: Path) -> str:
    """
    自动检测文件编码
    
    Args:
        file_path: 文件路径
        
    Returns:
        检测到的编码名称
    """
    try:
        # 先尝试UTF-8
        with open(file_path, 'r', encoding='utf-8') as f:
            f.read()
        return 'utf-8'
    except UnicodeDecodeError:
        pass
    
    # 使用chardet检测
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read(10000)  # 读取前10KB用于检测
            result = chardet.detect(raw_data)
            encoding = result.get('encoding', 'utf-8')
            logger.info(f"检测到文件 {file_path} 的编码: {encoding}")
            return encoding
    except Exception as e:
        logger.warning(f"编码检测失败，使用UTF-8: {e}")
        return 'utf-8'


def validate_relative_path(file_path: str) -> Path:
    """
    验证并规范化相对路径
    
    Args:
        file_path: 相对路径字符串
        
    Returns:
        规范化后的Path对象
        
    Raises:
        ValueError: 如果路径无效或包含不安全字符
    """
    if not file_path:
        raise ValueError("文件路径不能为空")
    
    # 检查是否包含绝对路径标识
    if os.path.isabs(file_path):
        raise ValueError(f"不支持绝对路径: {file_path}")
    
    # 检查路径遍历攻击
    if '..' in file_path:
        raise ValueError(f"路径不能包含 '..': {file_path}")
    
    # 规范化路径
    normalized = Path(file_path).resolve()
    
    # 确保路径在工作目录内（安全检查）
    try:
        cwd = Path.cwd().resolve()
        normalized.relative_to(cwd)
    except ValueError:
        raise ValueError(f"路径超出工作目录范围: {file_path}")
    
    return Path(file_path)


def process_line_range(
    total_lines: int,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None
) -> Tuple[int, int]:
    """
    处理行号范围，返回有效的起始和结束行号
    
    Args:
        total_lines: 文件总行数
        start_line: 起始行号（从1开始，可选）
        end_line: 结束行号（从1开始，可选）
        
    Returns:
        (实际起始行号, 实际结束行号) 从0开始的索引
    """
    # 转换为0-based索引
    start_idx = (start_line - 1) if start_line is not None else 0
    end_idx = end_line if end_line is not None else total_lines
    
    # 验证范围
    if start_line is not None and start_line < 1:
        raise ValueError(f"起始行号必须大于0，当前值: {start_line}")
    if end_line is not None and end_line < 1:
        raise ValueError(f"结束行号必须大于0，当前值: {end_line}")
    if start_line is not None and end_line is not None and start_line > end_line:
        raise ValueError(f"起始行号({start_line})不能大于结束行号({end_line})")
    
    # 限制在有效范围内
    start_idx = max(0, min(start_idx, total_lines))
    end_idx = max(start_idx, min(end_idx, total_lines))
    
    return start_idx, end_idx


def read_file_with_encoding(file_path: Path) -> Tuple[str, str]:
    """
    使用自动检测的编码读取文件
    
    Args:
        file_path: 文件路径
        
    Returns:
        (文件内容, 使用的编码)
    """
    encoding = detect_encoding(file_path)
    
    with open(file_path, 'r', encoding=encoding) as f:
        content = f.read()
    
    return content, encoding


def read_file_lines_with_encoding(
    file_path: Path,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None
) -> Tuple[List[str], str]:
    """
    按行范围读取文件，使用自动检测的编码
    
    Args:
        file_path: 文件路径
        start_line: 起始行号（从1开始，可选）
        end_line: 结束行号（从1开始，可选）
        
    Returns:
        (行列表, 使用的编码)
    """
    encoding = detect_encoding(file_path)
    
    with open(file_path, 'r', encoding=encoding) as f:
        all_lines = f.readlines()
    
    total_lines = len(all_lines)
    start_idx, end_idx = process_line_range(total_lines, start_line, end_line)
    
    selected_lines = all_lines[start_idx:end_idx]
    
    return selected_lines, encoding

