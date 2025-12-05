#!/usr/bin/env python3
"""
批量替换日志系统脚本

将所有使用 logging.getLogger 的地方替换为统一的 src.common.logging.get_logger
"""

import os
import re
from pathlib import Path

# 需要处理的文件列表（从之前的grep结果）
files_to_process = [
    "src/agents/nodes/analysis_node.py",
    "src/agents/nodes/chat_record_node.py",
    "src/agents/nodes/daily_summary_node.py",
    "src/agents/nodes/weekly_summary_node.py",
    "src/agents/nodes/analysis/analyzer.py",
    "src/agents/nodes/analysis/repository.py",
    "src/agents/nodes/analysis/retry_manager.py",
    "src/agents/nodes/chat_record/compression.py",
    "src/agents/nodes/chat_record/context.py",
    "src/agents/nodes/chat_record/database.py",
    "src/agents/nodes/chat_record/memory.py",
    "src/agents/nodes/chat_record/utils.py",
    "src/agents/nodes/daily_summary/repository.py",
    "src/agents/nodes/tts/emotion_parser.py",
]

def replace_logging_in_file(file_path: str):
    """替换文件中的日志使用"""
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # 1. 替换 import logging 为 from src.common.logging import get_logger（如果还没有导入）
    if 'import logging' in content and 'from src.common.logging import get_logger' not in content:
        # 替换单独的 import logging
        content = re.sub(r'^import logging$', 'from src.common.logging import get_logger', content, flags=re.MULTILINE)
        # 替换与其他导入一起的 import logging
        content = re.sub(r'import logging\n', 'from src.common.logging import get_logger\n', content)
    
    # 2. 替换 logging.getLogger(__name__) 为 get_logger(__name__)
    content = re.sub(r'logging\.getLogger\(__name__\)', 'get_logger(__name__)', content)
    
    # 3. 替换 logging.getLogger(self.__class__.__name__) 为 get_logger(self.__class__.__name__)
    content = re.sub(r'logging\.getLogger\(self\.__class__\.__name__\)', 'get_logger(self.__class__.__name__)', content)
    
    # 4. 替换其他形式的 logging.getLogger(...)
    content = re.sub(r'logging\.getLogger\(([^)]+)\)', r'get_logger(\1)', content)
    
    # 5. 如果文件中有 logger = logging.getLogger(...) 但还没有导入 get_logger，添加导入
    if 'get_logger' in content and 'from src.common.logging import get_logger' not in content:
        # 找到第一个 import 语句的位置
        import_match = re.search(r'^(import |from )', content, re.MULTILINE)
        if import_match:
            insert_pos = import_match.start()
            # 在第一个 import 之前插入
            content = content[:insert_pos] + 'from src.common.logging import get_logger\n' + content[insert_pos:]
        else:
            # 如果没有 import，在文件开头添加
            content = 'from src.common.logging import get_logger\n' + content
    
    if content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"[OK] Processed: {file_path}")
        return True
    else:
        print(f"[SKIP] No changes: {file_path}")
        return False

if __name__ == '__main__':
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    processed = 0
    for file_path in files_to_process:
        full_path = project_root / file_path
        if replace_logging_in_file(str(full_path)):
            processed += 1
    
    print(f"\nDone! Processed {processed} files")

