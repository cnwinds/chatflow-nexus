#!/usr/bin/env python3
"""
UTCP猜动物游戏服务
基于UTCP协议实现的猜动物游戏服务，进程内集成版本
"""

import json
import logging
import random
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from functools import wraps
from src.utcp.utcp import UTCPService

# 配置日志
logger = logging.getLogger(__name__)


def handle_game_errors(func: Callable) -> Callable:
    """装饰器：统一错误处理"""
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except Exception as e:
            logger.error(f"{func.__name__} 失败: {e}")
            return {
                "status": "error",
                "error": str(e),
                "message": f"游戏操作失败: {str(e)}"
            }
    return wrapper


class GuessAnimalService(UTCPService):
    """猜动物游戏服务 - UTCP进程内集成版本"""
    
    # 插件不允许写__init__方法，只能通过init方法进行初始化
    
    def init(self) -> None:
        """插件初始化方法"""
        self.service_config = self.config
        
        # 初始化随机数种子，确保每次启动都有不同的随机序列
        random.seed()
        self.game_sessions: Dict[str, Dict[str, Any]] = {}
        self.animals_db: List[Dict[str, Any]] = []
        self._load_animals_database()
    
    @property
    def name(self) -> str:
        """服务名称"""
        return "guess_animal_service"
    
    @property
    def description(self) -> str:
        """服务描述"""
        return "陪伴孩子玩猜动物游戏的智能助手服务"
    
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
        """获取可用工具列表"""
        return [
            # 游戏管理工具
            self._create_tool_definition(
                "start_game", "开始新的猜动物游戏",
                {
                    "player_name": {
                        "type": "string",
                        "description": "玩家姓名",
                        "default": "小朋友"
                    },
                    "difficulty": {
                        "type": "string",
                        "enum": ["easy", "medium", "hard"],
                        "description": "游戏难度",
                        "default": "easy"
                    }
                }
            ),
            
            self._create_tool_definition(
                "get_clue", "获取动物线索",
                {
                    "session_id": {
                        "type": "string",
                        "description": "游戏会话ID"
                    }
                },
                ["session_id"]
            ),
            
            self._create_tool_definition(
                "make_guess", "猜测动物",
                {
                    "session_id": {
                        "type": "string",
                        "description": "游戏会话ID"
                    },
                    "guess": {
                        "type": "string",
                        "description": "猜测的动物名称"
                    }
                },
                ["session_id", "guess"]
            ),
            
            self._create_tool_definition(
                "get_game_status", "获取游戏状态",
                {
                    "session_id": {
                        "type": "string",
                        "description": "游戏会话ID"
                    }
                },
                ["session_id"]
            ),
            
            self._create_tool_definition(
                "end_game", "结束游戏",
                {
                    "session_id": {
                        "type": "string",
                        "description": "游戏会话ID"
                    }
                },
                ["session_id"]
            ),
            
            self._create_tool_definition(
                "get_available_animals", "获取可用动物列表",
                {}
            ),
        ]
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """执行游戏服务工具"""
        # 工具映射表
        tool_handlers = {
            "start_game": lambda: self._start_game(arguments),
            "get_clue": lambda: self._get_clue(arguments),
            "make_guess": lambda: self._make_guess(arguments),
            "get_game_status": lambda: self._get_game_status(arguments),
            "end_game": lambda: self._end_game(arguments),
            "get_available_animals": lambda: self._get_available_animals(),
        }
        
        try:
            if tool_name not in tool_handlers:
                raise ValueError(f"未知的游戏工具: {tool_name}")
            
            return await tool_handlers[tool_name]()
        except Exception as e:
            logger.error(f"执行工具 '{tool_name}' 时出错: {e}")
            return {
                "status": "error",
                "error": str(e),
                "message": f"游戏操作失败: {str(e)}"
            }
    
    def _load_animals_database(self) -> None:
        """加载动物数据库"""
        try:
            # 尝试从多个可能的路径加载动物数据库
            possible_paths = [
                Path("data/animals_database.json"),
                Path(__file__).parent.parent.parent / "data" / "animals_database.json"
            ]
            
            db_path = None
            for path in possible_paths:
                if path.exists():
                    db_path = path
                    break
            
            if db_path and db_path.exists():
                with open(db_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.animals_db = data.get('animals', [])
                    logger.debug(f"从{db_path}加载了{len(self.animals_db)}种动物")
            else:
                # 如果文件不存在，使用默认数据
                self.animals_db = self._get_default_animals()
                logger.debug(f"使用默认动物数据库，包含{len(self.animals_db)}种动物")
                
        except Exception as e:
            logger.error(f"加载动物数据库失败: {e}")
            self.animals_db = self._get_default_animals()
            logger.debug(f"回退到默认动物数据库，包含{len(self.animals_db)}种动物")
    
    def _get_default_animals(self) -> List[Dict[str, Any]]:
        """获取默认动物数据"""
        return [
            {
                "name": "大象",
                "clues": [
                    "它的鼻子特别长哦！",
                    "它非常非常重，走路的时候地面都会咚咚响。",
                    "它有两个大大的耳朵，像扇子一样。",
                    "它生活在非洲和亚洲的草原上。",
                    "它喜欢用鼻子喷水洗澡。"
                ],
                "aliases": ["大象", "象", "小象"]
            },
            {
                "name": "长颈鹿",
                "clues": [
                    "它的脖子特别特别长！",
                    "它是世界上最高的动物。",
                    "它喜欢吃树叶，特别是高高的树叶。",
                    "它身上有漂亮的斑点图案。",
                    "它的舌头也很长，是紫色的。"
                ],
                "aliases": ["长颈鹿", "鹿"]
            },
            {
                "name": "狮子",
                "clues": [
                    "它是草原之王！",
                    "它有漂亮的鬃毛，看起来非常威武。",
                    "它喜欢群居生活，和家族一起生活。",
                    "它的吼声非常大，能传得很远。",
                    "它主要在晚上活动，白天休息。"
                ],
                "aliases": ["狮子", "狮"]
            },
            {
                "name": "熊猫",
                "clues": [
                    "它是中国的国宝！",
                    "它身上有黑白相间的毛。",
                    "它最喜欢吃竹子。",
                    "它的眼睛周围有黑色的眼圈。",
                    "它看起来胖乎乎的，非常可爱。"
                ],
                "aliases": ["熊猫", "大熊猫", "猫熊"]
            },
            {
                "name": "猴子",
                "clues": [
                    "它非常聪明，会模仿人类。",
                    "它喜欢爬树，在树上跳来跳去。",
                    "它有长长的尾巴，可以帮助它保持平衡。",
                    "它喜欢吃水果和坚果。",
                    "它喜欢和同伴一起玩耍。"
                ],
                "aliases": ["猴子", "猴"]
            }
        ]
    
    @handle_game_errors
    async def _start_game(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """开始新游戏"""
        player_name = arguments.get("player_name", "小朋友")
        difficulty = arguments.get("difficulty", "easy")
        
        # 生成会话ID
        session_id = str(uuid.uuid4())
        
        # 随机选择一个动物
        target_animal = random.choice(self.animals_db)
        
        # 创建游戏会话
        self.game_sessions[session_id] = {
            "player_name": player_name,
            "difficulty": difficulty,
            "target_animal": target_animal,
            "clues_used": 0,
            "guesses_made": 0,
            "start_time": datetime.now(),
            "game_state": "playing",
            "max_clues": 5 if difficulty == "easy" else (3 if difficulty == "medium" else 2)
        }
        
        return {
            "status": "success",
            "session_id": session_id,
            "message": f"游戏开始！{player_name}，我已经想好了一个动物，你可以开始猜了！",
            "player_name": player_name,
            "difficulty": difficulty,
            "max_clues": self.game_sessions[session_id]["max_clues"]
        }
    
    @handle_game_errors
    async def _get_clue(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """获取线索"""
        session_id = arguments.get("session_id")
        
        if not session_id:
            raise ValueError("session_id 是必需的")
        
        if session_id not in self.game_sessions:
            raise ValueError("无效的游戏会话ID")
        
        session = self.game_sessions[session_id]
        
        if session["game_state"] != "playing":
            raise ValueError("游戏已经结束")
        
        if session["clues_used"] >= session["max_clues"]:
            return {
                "status": "error",
                "message": "已经用完所有线索了！"
            }
        
        # 获取下一个线索
        target_animal = session["target_animal"]
        clues = target_animal["clues"]
        clue_index = session["clues_used"]
        
        if clue_index >= len(clues):
            return {
                "status": "error",
                "message": "没有更多线索了！"
            }
        
        clue = clues[clue_index]
        session["clues_used"] += 1
        
        return {
            "status": "success",
            "clue": clue,
            "clue_number": session["clues_used"],
            "max_clues": session["max_clues"],
            "remaining_clues": session["max_clues"] - session["clues_used"]
        }
    
    @handle_game_errors
    async def _make_guess(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """猜测动物"""
        session_id = arguments.get("session_id")
        guess = arguments.get("guess", "").strip()
        
        if not session_id:
            raise ValueError("session_id 是必需的")
        
        if not guess:
            raise ValueError("guess 是必需的")
        
        if session_id not in self.game_sessions:
            raise ValueError("无效的游戏会话ID")
        
        session = self.game_sessions[session_id]
        
        if session["game_state"] != "playing":
            raise ValueError("游戏已经结束")
        
        session["guesses_made"] += 1
        target_animal = session["target_animal"]
        
        # 检查猜测是否正确
        is_correct = guess.lower() in [alias.lower() for alias in target_animal["aliases"]]
        
        if is_correct:
            session["game_state"] = "won"
            return {
                "status": "success",
                "correct": True,
                "message": f"恭喜{session['player_name']}！你猜对了！就是{target_animal['name']}！",
                "target_animal": target_animal["name"],
                "guesses_made": session["guesses_made"],
                "clues_used": session["clues_used"]
            }
        else:
            # 提供提示
            hint = "再想想看！"
            if session["guesses_made"] >= 3:
                hint = f"提示：这个动物是{target_animal['name'][0]}开头的！"
            
            return {
                "status": "success",
                "correct": False,
                "message": f"不对哦，{hint}",
                "guesses_made": session["guesses_made"],
                "clues_used": session["clues_used"]
            }
    
    @handle_game_errors
    async def _get_game_status(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """获取游戏状态"""
        session_id = arguments.get("session_id")
        
        if not session_id:
            raise ValueError("session_id 是必需的")
        
        if session_id not in self.game_sessions:
            raise ValueError("无效的游戏会话ID")
        
        session = self.game_sessions[session_id]
        
        return {
            "status": "success",
            "game_state": session["game_state"],
            "player_name": session["player_name"],
            "difficulty": session["difficulty"],
            "guesses_made": session["guesses_made"],
            "clues_used": session["clues_used"],
            "max_clues": session["max_clues"],
            "remaining_clues": session["max_clues"] - session["clues_used"],
            "start_time": session["start_time"].isoformat()
        }
    
    @handle_game_errors
    async def _end_game(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """结束游戏"""
        session_id = arguments.get("session_id")
        
        if not session_id:
            raise ValueError("session_id 是必需的")
        
        if session_id not in self.game_sessions:
            raise ValueError("无效的游戏会话ID")
        
        session = self.game_sessions[session_id]
        target_animal = session["target_animal"]
        
        # 如果游戏还没结束，标记为失败
        if session["game_state"] == "playing":
            session["game_state"] = "lost"
        
        # 计算游戏时长
        end_time = datetime.now()
        duration = (end_time - session["start_time"]).total_seconds()
        
        result = {
            "status": "success",
            "game_state": session["game_state"],
            "target_animal": target_animal["name"],
            "guesses_made": session["guesses_made"],
            "clues_used": session["clues_used"],
            "duration_seconds": int(duration),
            "message": f"游戏结束！答案是{target_animal['name']}。"
        }
        
        # 清理会话
        del self.game_sessions[session_id]
        
        return result
    
    def _get_available_animals(self) -> Dict[str, Any]:
        """获取可用动物列表"""
        animal_names = [animal["name"] for animal in self.animals_db]
        
        return {
            "status": "success",
            "animals": animal_names,
            "total_count": len(animal_names)
        }
    
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
    parser.add_argument('--port', type=int, default=8003, help='服务器端口')
    
    args = parser.parse_args()

    # 启动HTTP服务器
    asyncio.run(run_service_as_http_server(GuessAnimalService, args.host, args.port))