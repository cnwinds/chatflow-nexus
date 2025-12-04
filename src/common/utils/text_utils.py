#!/usr/bin/env python3
"""
文本处理工具函数。
"""

import json
from typing import Optional, Any


def parse_json_from_llm_response(content: Optional[str]) -> Any:
    """
    解析可能包含Markdown代码块的大模型响应，返回JSON对象。

    Args:
        content: 原始响应字符串，可能以```包裹。

    Returns:
        解析后的JSON对象。

    Raises:
        ValueError: 当内容为空或JSON解析失败时抛出。
    """
    if not content or not content.strip():
        raise ValueError("LLM返回内容为空，无法解析JSON")

    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        code_lines = []
        in_code_block = False

        for line in lines:
            marker = line.strip()
            if marker.startswith("```"):
                if not in_code_block:
                    in_code_block = True
                    continue
                break
            if in_code_block:
                code_lines.append(line)

        stripped = "\n".join(code_lines).strip() or stripped

    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        snippet = stripped[:200]
        raise ValueError(f"JSON解析失败: {exc}. 内容片段: {snippet}") from exc

