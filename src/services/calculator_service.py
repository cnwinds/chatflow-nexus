"""
UTCP计算器服务

将原有的MCP计算器功能迁移到UTCP协议的实现。
提供各种数学计算功能，包括基本四则运算、高级数学函数和表达式计算。
"""

import math
import logging
from typing import Dict, Any, List, Union, Callable
from functools import wraps
from src.utcp.utcp import UTCPService

logger = logging.getLogger(__name__)


def handle_calc_errors(func: Callable) -> Callable:
    """装饰器：统一错误处理"""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except Exception as e:
            logger.error(f"{func.__name__} 失败: {e}")
            raise ValueError(f"执行工具 '{func.__name__}' 失败: {str(e)}")
    return wrapper


class CalculatorService(UTCPService):
    """UTCP计算器服务实现"""
    
    def init(self) -> None:
        """插件初始化方法"""
        pass
    
    @property
    def name(self) -> str:
        return "calculator_service"
    
    @property
    def description(self) -> str:
        return "提供各种数学计算功能的智能计算器服务"
    
    def _create_tool_definition(self, name: str, description: str, 
                               properties: Dict[str, Any], required: List[str] = None) -> Dict[str, Any]:
        """创建工具定义的辅助方法"""
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required or []
                }
            }
        }
    
    async def get_tools(self) -> List[Dict[str, Any]]:
        """返回OpenAI格式的可用工具列表"""
        return [
            # 基本四则运算
            self._create_tool_definition(
                "add", "加法运算",
                {
                    "a": {"type": "number", "description": "第一个数字"},
                    "b": {"type": "number", "description": "第二个数字"}
                },
                ["a", "b"]
            ),
            self._create_tool_definition(
                "subtract", "减法运算",
                {
                    "a": {"type": "number", "description": "被减数"},
                    "b": {"type": "number", "description": "减数"}
                },
                ["a", "b"]
            ),
            self._create_tool_definition(
                "multiply", "乘法运算",
                {
                    "a": {"type": "number", "description": "第一个数字"},
                    "b": {"type": "number", "description": "第二个数字"}
                },
                ["a", "b"]
            ),
            self._create_tool_definition(
                "divide", "除法运算",
                {
                    "a": {"type": "number", "description": "被除数"},
                    "b": {"type": "number", "description": "除数"}
                },
                ["a", "b"]
            ),
            
            # 高级数学运算
            self._create_tool_definition(
                "power", "幂运算",
                {
                    "base": {"type": "number", "description": "底数"},
                    "exponent": {"type": "number", "description": "指数"}
                },
                ["base", "exponent"]
            ),
            self._create_tool_definition(
                "square_root", "平方根运算",
                {
                    "number": {
                        "type": "number", 
                        "description": "要开平方根的数字",
                        "minimum": 0
                    }
                },
                ["number"]
            ),
            self._create_tool_definition(
                "factorial", "阶乘运算",
                {
                    "n": {
                        "type": "integer",
                        "description": "要计算阶乘的非负整数",
                        "minimum": 0,
                        "maximum": 20
                    }
                },
                ["n"]
            ),
            
            # 实用计算
            self._create_tool_definition(
                "percentage", "百分比计算",
                {
                    "part": {"type": "number", "description": "部分值"},
                    "whole": {"type": "number", "description": "总值"}
                },
                ["part", "whole"]
            ),
            self._create_tool_definition(
                "calculate_expression", "计算数学表达式",
                {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式字符串（如 '2+3*4'）"
                    }
                },
                ["expression"]
            ),
            self._create_tool_definition(
                "trigonometry", "三角函数计算",
                {
                    "function": {
                        "type": "string",
                        "description": "三角函数名称",
                        "enum": ["sin", "cos", "tan"]
                    },
                    "angle": {"type": "number", "description": "角度值"},
                    "unit": {
                        "type": "string",
                        "description": "角度单位",
                        "enum": ["degrees", "radians"],
                        "default": "degrees"
                    }
                },
                ["function", "angle"]
            ),
        ]
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """使用给定参数执行工具"""
        # 工具映射表
        tool_handlers = {
            "add": lambda: self._add(arguments["a"], arguments["b"]),
            "subtract": lambda: self._subtract(arguments["a"], arguments["b"]),
            "multiply": lambda: self._multiply(arguments["a"], arguments["b"]),
            "divide": lambda: self._divide(arguments["a"], arguments["b"]),
            "power": lambda: self._power(arguments["base"], arguments["exponent"]),
            "square_root": lambda: self._square_root(arguments["number"]),
            "factorial": lambda: self._factorial(arguments["n"]),
            "percentage": lambda: self._percentage(arguments["part"], arguments["whole"]),
            "calculate_expression": lambda: self._calculate_expression(arguments["expression"]),
            "trigonometry": lambda: self._trigonometry(
                arguments["function"], 
                arguments["angle"], 
                arguments.get("unit", "degrees")
            ),
        }
        
        try:
            if tool_name not in tool_handlers:
                raise ValueError(f"未知的工具名称: {tool_name}")
            
            return tool_handlers[tool_name]()
        except KeyError as e:
            raise ValueError(f"缺少必需的参数: {e}")
        except Exception as e:
            logger.error(f"执行工具 '{tool_name}' 时出错: {e}")
            raise ValueError(f"执行工具 '{tool_name}' 失败: {str(e)}")
    
    @handle_calc_errors
    def _add(self, a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
        """加法运算"""
        result = a + b
        logger.info(f"加法计算: {a} + {b} = {result}")
        return result
    
    @handle_calc_errors
    def _subtract(self, a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
        """减法运算"""
        result = a - b
        logger.info(f"减法计算: {a} - {b} = {result}")
        return result
    
    @handle_calc_errors
    def _multiply(self, a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
        """乘法运算"""
        result = a * b
        logger.info(f"乘法计算: {a} × {b} = {result}")
        return result
    
    @handle_calc_errors
    def _divide(self, a: Union[int, float], b: Union[int, float]) -> float:
        """除法运算"""
        if b == 0:
            raise ValueError("除数不能为零")
        result = a / b
        logger.info(f"除法计算: {a} ÷ {b} = {result}")
        return result
    
    @handle_calc_errors
    def _power(self, base: Union[int, float], exponent: Union[int, float]) -> Union[int, float]:
        """幂运算"""
        result = base ** exponent
        logger.info(f"幂运算: {base}^{exponent} = {result}")
        return result
    
    @handle_calc_errors
    def _square_root(self, number: Union[int, float]) -> float:
        """平方根运算"""
        if number < 0:
            raise ValueError("负数不能开平方根")
        result = math.sqrt(number)
        logger.info(f"平方根: √{number} = {result}")
        return result
    
    @handle_calc_errors
    def _factorial(self, n: int) -> int:
        """阶乘运算"""
        if n < 0:
            raise ValueError("负数不能计算阶乘")
        if n > 20:
            raise ValueError("数字太大，超出计算范围")
        result = math.factorial(n)
        logger.info(f"阶乘: {n}! = {result}")
        return result
    
    @handle_calc_errors
    def _percentage(self, part: Union[int, float], whole: Union[int, float]) -> float:
        """百分比计算"""
        if whole == 0:
            raise ValueError("总值不能为零")
        result = (part / whole) * 100
        logger.info(f"百分比: ({part}/{whole}) × 100% = {result}%")
        return result
    
    @handle_calc_errors
    def _calculate_expression(self, expression: str) -> Union[int, float]:
        """计算数学表达式"""
        # 先替换一些常见的数学符号
        expression = expression.replace('×', '*').replace('÷', '/')
        
        # 安全的表达式计算，只允许基本数学运算
        allowed_chars = set('0123456789+-*/.() ')
        if not all(c in allowed_chars for c in expression):
            raise ValueError("表达式包含不允许的字符")
        
        result = eval(expression)
        logger.info(f"表达式计算: {expression} = {result}")
        return result
    
    @handle_calc_errors
    def _trigonometry(self, function: str, angle: Union[int, float], unit: str = "degrees") -> float:
        """三角函数计算"""
        # 转换角度单位
        if unit == "degrees":
            angle_rad = math.radians(angle)
        else:
            angle_rad = angle
        
        if function.lower() == "sin":
            result = math.sin(angle_rad)
        elif function.lower() == "cos":
            result = math.cos(angle_rad)
        elif function.lower() == "tan":
            result = math.tan(angle_rad)
        else:
            raise ValueError(f"不支持的三角函数: {function}")
        
        logger.info(f"三角函数: {function}({angle}°) = {result}")
        return result
    
if __name__ == "__main__":
    """作为HTTP服务器运行"""
    import sys
    import os
    import argparse
    import asyncio
    
    # 添加项目路径
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    
    from utcp.http_server import run_service_as_http_server
    
    # 解析命令行参数
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='localhost', help='服务器主机')
    parser.add_argument('--port', type=int, default=8002, help='服务器端口')
    
    args = parser.parse_args()

    # 启动HTTP服务器
    asyncio.run(run_service_as_http_server(CalculatorService, args.host, args.port))