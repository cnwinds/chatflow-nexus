"""
情绪解析器

根据文本开头的emoji解析情绪，并维护情绪状态。
"""

import re
import logging
from typing import Optional, Tuple


class EmotionParser:
    """情绪解析器类"""
    
    # emoji到情绪字符串的映射表
    EMOJI_TO_EMOTION = {
        '😊': 'cheerful',      # 快乐
        '😔': 'sad',           # 悲伤  
        '😠': 'angry',         # 愤怒
        '🎉': 'excited',       # 兴奋
        '😨': 'fearful',       # 恐惧
        '🥰': 'affectionate',  # 亲切/关怀
        '😌': 'chat',          # 轻松随意
    }
    
    # 默认情绪
    DEFAULT_EMOTION = 'chat'
    
    def __init__(self):
        self._logger = logging.getLogger(__name__)
        self._current_emotion = self.DEFAULT_EMOTION  # 当前情绪状态
        
        # 构建emoji正则表达式模式
        emoji_pattern = '|'.join(re.escape(emoji) for emoji in self.EMOJI_TO_EMOTION.keys())
        # 仅匹配文本开头的emoji（用于设定情绪）
        self._emoji_start_pattern = re.compile(f'^({emoji_pattern})')
        # 匹配任意emoji（用于删除句中所有情绪符号，不限于映射表）
        # 说明：该范围覆盖常见的表情、符号及扩展区的emoji；不依赖外部库
        self._any_emoji_pattern = re.compile(
            r"[\u2600-\u27BF\U0001F300-\U0001F5FF\U0001F600-\U0001F64F\U0001F680-\U0001F6FF\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF\U0001F900-\U0001F9FF\U0001FA00-\U0001FAFF\U0001FB00-\U0001FBFF]"
        )
        # 匹配常见 ASCII 表情（不限于映射表），用于清理句中情绪符号
        # 覆盖示例：:), :-), :(, :-(, :D, :-D, ;), ;-), :P, :-P, :/ , :-/ , :\\ , :-\\ , XD, xD, T_T, >_<, ^_^, QAQ, Q_Q, o_O, O_o, -_-
        self._ascii_emoticon_pattern = re.compile(
            r"(?:[:;=8][\-^]?[)(D/\\PpOo|])|(?:T_T)|(?:TT)|(?:>_<)|(?:\^_\^)|(?:[xX]D)|(?:QAQ)|(?:Q_Q)|(?:o_O)|(?:O_o)|(?:-_-)",
            re.UNICODE
        )
    
    def parse_emotion(self, text: str) -> Tuple[str, str]:
        """
        解析文本中的情绪
        
        Args:
            text: 输入文本
            
        Returns:
            Tuple[str, str]: (解析后的文本, 情绪字符串)
        """
        if not text:
            return text, self._current_emotion
        
        # 检查文本开头是否有emoji
        match = self._emoji_start_pattern.match(text)
        
        if match:
            # 找到emoji，提取情绪并更新状态
            emoji = match.group(1)
            emotion = self.EMOJI_TO_EMOTION.get(emoji, self.DEFAULT_EMOTION)
            self._current_emotion = emotion
            
            # 移除开头的emoji
            clean_text = text[match.end():].strip()
            
            # 如果清理后的文本开头还有emoji，继续仅清理前缀部分
            while clean_text and self._emoji_start_pattern.match(clean_text):
                next_match = self._emoji_start_pattern.match(clean_text)
                if next_match:
                    clean_text = clean_text[next_match.end():].strip()
                else:
                    break

            # 处理完句首情绪后，删除句中其余的emotion符号（不限于映射表）
            clean_text = self._any_emoji_pattern.sub('', clean_text)
            # 同时删除常见 ASCII 表情
            clean_text = self._ascii_emoticon_pattern.sub('', clean_text).strip()
            
            self._logger.debug(f"检测到情绪emoji: {emoji} -> {emotion}, 文本: '{clean_text}'")
            return clean_text, emotion
        else:
            # 没有emoji，使用当前情绪状态
            self._logger.debug(f"未检测到emoji，使用当前情绪: {self._current_emotion}")
            return text, self._current_emotion
    
    def get_current_emotion(self) -> str:
        """获取当前情绪状态"""
        return self._current_emotion
    
    def reset_emotion(self, emotion: str = None):
        """重置情绪状态"""
        if emotion is None:
            emotion = self.DEFAULT_EMOTION
        self._current_emotion = emotion
        self._logger.debug(f"情绪状态已重置为: {emotion}")
    
    def set_emotion(self, emotion: str):
        """手动设置情绪状态"""
        if emotion in self.EMOJI_TO_EMOTION.values():
            self._current_emotion = emotion
            self._logger.debug(f"情绪状态已设置为: {emotion}")
        else:
            self._logger.warning(f"无效的情绪值: {emotion}")
