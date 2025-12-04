"""
数据库异常定义
"""

from ..exceptions import DatabaseError, DatabaseConnectionError, DatabaseQueryError, DatabaseTransactionError

# 重新导出异常，保持模块独立性
__all__ = [
    'DatabaseError',
    'DatabaseConnectionError', 
    'DatabaseQueryError',
    'DatabaseTransactionError'
]