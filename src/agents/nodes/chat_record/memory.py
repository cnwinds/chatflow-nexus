"""
聊天记录长期记忆管理
"""
import json
import logging
from typing import Any, Dict, List

from src.agents.utcp_tools import call_utcp_tool


class ChatRecordMemory:
    """聊天记录长期记忆管理类"""
    
    def __init__(
        self,
        user_data: Any,
        engine: Any,
        ai_providers: Dict[str, Any],
        memory_extract_system_prompt: str,
        memory_extract_user_prompt: str,
        memory_extract_max_length: int,
        logger: logging.Logger = None
    ):
        self.user_data = user_data
        self.engine = engine
        self.ai_providers = ai_providers
        self.memory_extract_system_prompt = memory_extract_system_prompt
        self.memory_extract_user_prompt = memory_extract_user_prompt
        self.memory_extract_max_length = memory_extract_max_length
        self.logger = logger or logging.getLogger(__name__)
    
    async def extract_memory(self, messages: List[Dict[str, Any]]):
        """提取长期记忆"""
        if not self.memory_extract_system_prompt or not self.memory_extract_user_prompt:
            self.logger.warning("记忆提取提示词未配置")
            return
        
        try:
            # 获取现有记忆
            existing = self._get_existing_memory()
            
            # 构建变量
            vars = self._build_prompt_vars(messages)
            vars["existing_memory"] = json.dumps(existing, ensure_ascii=False, indent=2)
            
            # 渲染提示词
            system_text = self.engine.render_template(self.memory_extract_system_prompt, **vars)
            user_text = self.engine.render_template(self.memory_extract_user_prompt, **vars)
            
            # 调用 LLM
            service, model = self._get_llm_service()
            if not service:
                return
            
            result = await call_utcp_tool(f"{service}.chat_completion", {
                "messages": [
                    {"role": "system", "content": system_text},
                    {"role": "user", "content": user_text}
                ],
                "model": model,
                "max_tokens": 2000,
                "temperature": 0.5,
                "top_p": 1.0
            })
            
            content = (result or {}).get("content", "").strip()
            if not content:
                return
            
            # 解析并保存
            memory_data = self._parse_memory(content)
            memory_data = self._enforce_memory_length(memory_data)
            self._save_memory(memory_data)
            
            self.logger.info(f"记忆提取完成: {len(memory_data)} 个类别")
            
        except Exception as e:
            self.logger.error(f"记忆提取异常: {e}", exc_info=True)
    
    def _get_existing_memory(self) -> Dict[str, Any]:
        """获取现有记忆"""
        memory = self.user_data.get_memory("chat.long_term_memory")
        if not memory:
            return {}
        
        if isinstance(memory, dict):
            return memory
        
        if isinstance(memory, list):
            return self._merge_list_memory(memory)
        
        return {}
    
    def _merge_list_memory(self, memory_list: List) -> Dict[str, Any]:
        """合并列表格式的记忆"""
        merged = {}
        for item in memory_list:
            if not isinstance(item, dict):
                continue
            
            for key, value in item.items():
                if key in merged:
                    # 合并相同键
                    if isinstance(merged[key], list):
                        if isinstance(value, list):
                            merged[key].extend(value)
                        else:
                            merged[key].append(value)
                    else:
                        merged[key] = [merged[key], value] if not isinstance(value, list) else [merged[key]] + value
                else:
                    merged[key] = value if isinstance(value, list) else [value]
        
        return merged
    
    def _parse_memory(self, content: str) -> Dict[str, Any]:
        """解析记忆内容"""
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"summary": content}
    
    def _enforce_memory_length(self, memory_data: Dict[str, Any]) -> Dict[str, Any]:
        """根据配置裁剪记忆长度，避免超出存储限制"""
        if self.memory_extract_max_length <= 0:
            return memory_data

        original_length = len(self._serialize_memory(memory_data))
        if original_length <= self.memory_extract_max_length:
            return memory_data

        trimmed = self._trim_memory_entries(memory_data, self.memory_extract_max_length)
        trimmed_length = len(self._serialize_memory(trimmed))

        if trimmed_length <= self.memory_extract_max_length:
            self.logger.info(
                f"记忆内容超出上限，已裁剪: {original_length} -> {trimmed_length} 字符"
            )
            return trimmed

        summary = {
            "summary": self._truncate_text(
                self._serialize_memory(trimmed), self.memory_extract_max_length
            )
        }
        self.logger.warning(
            "记忆内容经过裁剪仍超出上限，已转换为 summary"
        )
        return summary
    
    def _trim_memory_entries(self, memory_data: Dict[str, Any], max_length: int) -> Dict[str, Any]:
        """逐项裁剪记忆内容，尽量保留结构"""
        normalized = self._normalize_memory_structure(memory_data, max_length)
        if not normalized:
            return {}

        trimmed = {key: values[:] for key, values in normalized.items() if values}
        if not trimmed:
            return {}

        # 轮转删除，优先移除条目数量多的类别
        key_order = sorted(trimmed.keys(), key=lambda k: len(trimmed[k]), reverse=True)
        serialized = self._serialize_memory(trimmed)

        while trimmed and len(serialized) > max_length:
            for key in list(key_order):
                if key not in trimmed or not trimmed[key]:
                    continue
                trimmed[key].pop()
                if not trimmed[key]:
                    trimmed.pop(key, None)
                    key_order = [k for k in key_order if k in trimmed]
                serialized = self._serialize_memory(trimmed) if trimmed else "{}"
                break
            else:
                break

        return trimmed
    
    def _normalize_memory_structure(self, memory_data: Dict[str, Any], max_length: int) -> Dict[str, List[str]]:
        """将记忆内容规范为 {key: List[str]} 形式并裁剪超长文本"""
        normalized: Dict[str, List[str]] = {}
        for key, value in (memory_data or {}).items():
            normalized_values = self._normalize_memory_value(value, max_length)
            if normalized_values:
                normalized[key] = normalized_values
        return normalized
    
    def _normalize_memory_value(self, value: Any, max_length: int) -> List[str]:
        """将任意值转换为字符串列表"""
        if value is None:
            return []

        if isinstance(value, list):
            results = []
            for item in value:
                text = self._stringify_memory_value(item)
                if text:
                    results.append(self._truncate_text(text, max_length))
            return results

        text = self._stringify_memory_value(value)
        return [self._truncate_text(text, max_length)] if text else []
    
    def _stringify_memory_value(self, value: Any) -> str:
        """统一将记忆条目转换为字符串"""
        if value is None:
            return ""
        if isinstance(value, (str, int, float)):
            return str(value).strip()
        try:
            return json.dumps(value, ensure_ascii=False)
        except TypeError:
            return str(value)
    
    def _serialize_memory(self, memory_data: Dict[str, Any]) -> str:
        """将记忆内容序列化为紧凑字符串"""
        try:
            return json.dumps(memory_data or {}, ensure_ascii=False, separators=(",", ":"))
        except TypeError:
            return str(memory_data)
    
    def _truncate_text(self, text: str, max_length: int) -> str:
        """安全地截断文本"""
        if max_length <= 0 or not text:
            return ""
        if len(text) <= max_length:
            return text
        if max_length <= 3:
            return text[:max_length]
        return f"{text[: max_length - 3]}..."
    
    def _save_memory(self, memory_data: Dict[str, Any]):
        """保存记忆"""
        self.user_data.set_memory("chat.long_term_memory", memory_data)
        self.logger.debug(f"保存记忆: {len(memory_data)} 个类别")
    
    def get_memory(self) -> Dict[str, Any]:
        """获取长期记忆"""
        memory = self.user_data.get_memory("chat.long_term_memory")
        if not memory:
            return {}
        
        if isinstance(memory, dict):
            return memory
        elif isinstance(memory, list):
            return {"memories": memory}
        else:
            return {"memory": memory}
    
    def _build_prompt_vars(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """构建提示词变量"""
        return {
            "messages": "\n".join([f"{m['role']}: {m['content']}" for m in messages]),
            "message_count": len(messages),
            "memory_max_length": self.memory_extract_max_length
        }
    
    def _get_llm_service(self) -> tuple:
        """获取 LLM 服务配置"""
        try:
            llm_config = self.ai_providers.get("llm", {})
            model_config = llm_config.get("primary")
            
            if not model_config:
                return ("", "")
            
            if "." in model_config:
                parts = model_config.split(".", 1)
                return (parts[0], parts[1])
            else:
                return (model_config, "primary")
        except Exception:
            return ("", "")









