"""
工具函数：编码检测、路径处理、行号处理等
"""

import os
import logging
from pathlib import Path
from typing import Optional, Tuple, List, Union
import chardet
import glob

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


def validate_relative_dir_path(dir_path: str) -> Path:
    """
    验证并规范化相对目录路径
    
    Args:
        dir_path: 相对目录路径字符串
        
    Returns:
        规范化后的Path对象
        
    Raises:
        ValueError: 如果路径无效或包含不安全字符
        NotADirectoryError: 如果路径存在但不是目录
    """
    if not dir_path:
        raise ValueError("目录路径不能为空")
    
    # 检查是否包含绝对路径标识
    if os.path.isabs(dir_path):
        raise ValueError(f"不支持绝对路径: {dir_path}")
    
    # 检查路径遍历攻击
    if '..' in dir_path:
        raise ValueError(f"路径不能包含 '..': {dir_path}")
    
    # 规范化路径
    normalized = Path(dir_path).resolve()
    
    # 确保路径在工作目录内（安全检查）
    try:
        cwd = Path.cwd().resolve()
        normalized.relative_to(cwd)
    except ValueError:
        raise ValueError(f"路径超出工作目录范围: {dir_path}")
    
    path = Path(dir_path)
    
    if path.exists() and not path.is_dir():
        raise NotADirectoryError(f"路径不是目录: {dir_path}")
    
    return path


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


def expand_file_paths(file_path: Union[str, List[str]]) -> List[Path]:
    """
    展开文件路径，支持：
    1. 单个文件路径字符串
    2. 文件路径列表
    3. 通配符模式（如 *.py, **/*.md）
    
    Args:
        file_path: 文件路径（字符串、列表或通配符模式）
        
    Returns:
        展开后的文件路径列表（Path对象列表）
        
    Raises:
        ValueError: 如果路径无效或包含不安全字符
    """
    if isinstance(file_path, list):
        # 如果是列表，递归处理每个路径
        all_paths = []
        for path_item in file_path:
            all_paths.extend(expand_file_paths(path_item))
        return all_paths
    
    if not isinstance(file_path, str):
        raise ValueError(f"文件路径必须是字符串或列表，当前类型: {type(file_path)}")
    
    if not file_path:
        raise ValueError("文件路径不能为空")
    
    # 检查是否包含绝对路径标识
    if os.path.isabs(file_path):
        raise ValueError(f"不支持绝对路径: {file_path}")
    
    # 检查路径遍历攻击（在通配符展开前检查）
    if '..' in file_path:
        raise ValueError(f"路径不能包含 '..': {file_path}")
    
    # 检查是否包含通配符
    if '*' in file_path or '?' in file_path or '[' in file_path:
        # 使用glob展开通配符
        cwd = Path.cwd().resolve()
        matched_paths = []
        
        # 使用glob.glob进行模式匹配
        for matched in glob.glob(file_path, recursive=True):
            matched_path = Path(matched)
            
            # 转换为绝对路径以便验证
            abs_path = matched_path.resolve()
            
            # 安全检查：确保匹配的路径在工作目录内
            try:
                rel_path = abs_path.relative_to(cwd)
            except ValueError:
                logger.warning(f"跳过超出工作目录的路径: {matched}")
                continue
            
            # 只返回文件，不返回目录
            if abs_path.is_file():
                # 返回相对路径的Path对象
                matched_paths.append(Path(rel_path))
        
        if not matched_paths:
            logger.warning(f"通配符模式 '{file_path}' 未匹配到任何文件")
        
        return matched_paths
    else:
        # 单个文件路径
        path = validate_relative_path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        if not path.is_file():
            raise ValueError(f"路径不是文件: {file_path}")
        return [path]

