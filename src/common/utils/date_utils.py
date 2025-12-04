"""
日期工具函数

提供公历和农历日期转换和格式化功能
"""

from datetime import datetime
from typing import Optional


def get_current_time(date: Optional[datetime] = None) -> str:
    """
    获取公历当前时间字符串
    
    Args:
        date: 日期对象，如果为None则使用当前日期时间
        
    Returns:
        str: 公历时间字符串，格式如 "2024年12月01日 14:30:25"
        
    Examples:
        >>> get_current_time()
        '2024年12月01日 14:30:25'
    """
    if date is None:
        date = datetime.now()
    return date.strftime("%Y年%m月%d日 %H:%M:%S")


def get_lunar_date_str(date: Optional[datetime] = None) -> str:
    """
    获取农历日期字符串（仅日期部分，不含时间）
    
    Args:
        date: 日期对象，如果为None则使用当前日期
        
    Returns:
        str: 农历日期字符串，格式如 "二零二五年十月初九"
            如果zhdate未安装或转换失败，返回空字符串
        
    Examples:
        >>> get_lunar_date_str()
        '二零二五年十月初九'
    """
    try:
        from zhdate import ZhDate
    except ImportError:
        # 如果zhdate未安装，返回空字符串
        return ""
    
    if date is None:
        date = datetime.now()
    
    try:
        lunar_date = ZhDate.from_datetime(date)
        # chinese() 返回格式: "二零二五年十月初九 乙巳年 (蛇年)"
        # 只提取日期部分（第一个空格之前的内容）
        chinese_str = lunar_date.chinese()
        # 提取日期部分，去掉天干地支和生肖
        date_part = chinese_str.split()[0] if chinese_str else ""
        return date_part
    except Exception:
        # 如果转换失败，返回空字符串
        return ""


def get_current_time_with_lunar() -> str:
    """
    获取包含农历的当前时间字符串（兼容旧版本）
    
    Returns:
        str: 格式如 "2024年12月01日 14:30:25 (农历二零二五年十月初九)"
    """
    now = datetime.now()
    solar_time = get_current_time(now)
    lunar_str = get_lunar_date_str(now)
    
    if lunar_str:
        return f"{solar_time} (农历{lunar_str})"
    else:
        return solar_time

