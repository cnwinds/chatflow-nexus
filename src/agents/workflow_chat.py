"""
ChatWorkflowManager

核心业务逻辑层，替代 ChatClient：
- 加载设备配置（MemoryConfig）
- 直接创建并管理 WorkflowEngine 实例
- 注入全局变量供所有节点访问
- 桥接 WebSocket 音频与工作流
"""

from typing import Any, Awaitable, Callable, Dict, Optional, Union
import yaml
from pathlib import Path

from stream_workflow.core import WorkflowEngine

from src.common.logging import get_logger

# 触发自定义节点注册
from .nodes import *

# 全局 logger
logger = get_logger(__name__)


class DataProxy:
    """
    通用数据代理类，支持通过属性访问路径，自动累积路径并调用 UserData 方法
    
    示例：c.user.config.profile.character.name 
    等价于：user_data.get_config("profile.character.name")
    """
    
    def __init__(self, user_data: Any, method_name: str, prefix: str = ""):
        """
        初始化数据代理
        
        Args:
            user_data: UserData 实例，提供 get_config() 或 get_memory() 方法
            method_name: 要调用的方法名，如 'get_config' 或 'get_memory'
            prefix: 路径前缀，用于累积完整路径
        """
        self._user_data = user_data
        self._method_name = method_name
        self._prefix = prefix
    
    def _get_value(self, path: str) -> Any:
        """调用 UserData 的方法获取值"""
        if self._user_data is None:
            return None
        if hasattr(self._user_data, self._method_name):
            method = getattr(self._user_data, self._method_name)
            return method(path)
        return None
    
    def __getattr__(self, name: str) -> Any:
        """通过属性名访问数据值，自动累积路径"""

        # 构建完整路径
        full_path = f"{self._prefix}.{name}" if self._prefix else name
        
        # 调用 UserData 方法获取值
        value = self._get_value(full_path)
        
        # 如果值是字典，创建新的代理对象继续累积路径
        if isinstance(value, dict):
            return DataProxy(self._user_data, self._method_name, full_path)
        
        # 直接返回值
        return value
    
    def __repr__(self) -> str:
        """字符串表示"""
        return f"DataProxy(method='{self._method_name}', prefix='{self._prefix}')"


class UserDataWrapper:
    """
    用户数据包装器，用于在 Jinja2 模板中访问用户配置和记忆数据
    
    使用示例：
    - {{ c.user.config.profile.character.name }} 等价于 user_data.get_config("profile.character.name")
    - {{ c.user.memory.preferences.current_voice }} 等价于 user_data.get_memory("preferences.current_voice")
    
    注意：此包装器直接代理到 UserData 的方法，实时获取最新值，不缓存数据
    """
    
    def __init__(self, user_data: Any):
        """
        初始化用户数据包装器
        
        Args:
            user_data: UserData 实例，提供 get_config() 和 get_memory() 方法
        """
        # 保存 user_data 的引用
        self._user_data = user_data
        # 创建配置和记忆代理（prefix 为空，从根路径开始）
        self._config_proxy = DataProxy(user_data, 'get_config')
        self._memory_proxy = DataProxy(user_data, 'get_memory')
    
    @property
    def config(self) -> DataProxy:
        """
        获取配置代理，实时访问最新配置值
        
        Returns:
            DataProxy: 配置代理对象
        """
        return self._config_proxy
    
    @property
    def memory(self) -> DataProxy:
        """
        获取记忆数据代理，实时访问最新记忆值
        
        Returns:
            DataProxy: 记忆数据代理对象
        """
        return self._memory_proxy
    
    def __repr__(self) -> str:
        """字符串表示"""
        return f"UserDataWrapper(config={self.config}, memory={self.memory})"


class ChatWorkflowManager:
    """聊天工作流管理器 - 核心业务逻辑层"""
    
    def __init__(self, user_id: int, agent_id: int, tts_send: Callable[[bytes], Awaitable[bool]],
            send_tts_start: Callable[[], Awaitable[bool]], 
            send_tts_stop: Callable[[], Awaitable[bool]], 
            send_sentence_start: Callable[[str], Awaitable[bool]], 
            send_sentence_end: Callable[[str], Awaitable[bool]],
            text_response_callback: Optional[Callable[[str], Awaitable[None]]] = None):
        """
        初始化聊天工作流管理器
        
        Args:
            user_id: 用户ID
            agent_id: Agent ID
            tts_send: TTS音频数据发送回调
            send_tts_start: TTS开始回调
            send_tts_stop: TTS停止回调
            send_sentence_start: 句子开始回调
            send_sentence_end: 句子结束回调
            text_response_callback: 文本响应回调（可选），用于接收AI的文本响应
        """
        self.user_id = user_id
        self.agent_id = agent_id
        self.tts_send = tts_send
        self.send_tts_start = send_tts_start
        self.send_tts_stop = send_tts_stop
        self.send_sentence_start = send_sentence_start
        self.send_sentence_end = send_sentence_end
        self.text_response_callback = text_response_callback
        self.user_data: Optional[Any] = None  # UserData 实例
        self.session_id: Optional[str] = None
        self.engine: Optional[WorkflowEngine] = None
        self.context: Optional[Any] = None  # WorkflowContext 实例

    async def attach(self, session_id: str, copilot_mode: Optional[bool] = None, user_data: Optional[Any] = None):
        """加载配置并启动工作流
        
        Args:
            session_id: 会话ID，必传参数
            copilot_mode: 是否启用星宝领航员模式，可选参数
            user_data: 可选的已加载的UserData实例，如果提供则不会重新加载
        """
        # 导入必要的模块（确保在函数中始终可用）
        from src.agents.user_data import UserData
        from src.common.database.manager import get_db_manager
        
        # 1. 通过 agent_id 加载配置（如果未提供）
        if user_data is not None:
            # 使用提供的 user_data
            self.user_data = user_data
        elif self.user_data is None or not self.user_data._config_loaded:
            # 需要创建并加载 user_data
            self.user_data = UserData(get_db_manager())
            if not await self.user_data.load_from_agent_id(self.agent_id):
                return False

        # 2. 读取用户自定义工作流配置
        user_workflow_config = self.get_config("workflow_config")
        
        # 3. 直接创建 WorkflowEngine
        self.engine = WorkflowEngine()
        
        # 4. 加载工作流配置
        config_dict = await self._load_workflow_config(user_workflow_config, copilot_mode)
        self.engine.load_config_dict(config_dict)
        
        # 5. TTS 音频输出
        async def tts_callback(chunk):
            await self.tts_send(chunk.get("data", b""))
        self.engine.add_external_connection("tts", "audio_stream", tts_callback)
        
        # 6. TTS 设备控制消息 - 统一的状态通知回调
        async def tts_status_callback(data):
            state = data.get("state", "")
            if state == "start":
                await self.send_tts_start()
            elif state == "stop":
                await self.send_tts_stop()
            elif state == "sentence_start":
                text = data.get("text", "")
                await self.send_sentence_start(text)
            elif state == "sentence_end":
                text = data.get("text", "")
                await self.send_sentence_end(text)
        self.engine.add_external_connection("tts", "tts_status", tts_status_callback)

        # 7. 文本响应回调（如果提供了回调函数）
        if self.text_response_callback:
            async def text_response_callback_wrapper(chunk):
                """文本响应回调包装器 - 接收完整句子"""
                text = chunk.get("text", "")
                # 处理所有文本，包括空字符串（表示响应完成）
                logger.debug(f"文本响应回调包装器收到chunk: text长度={len(text) if text else 0}, text={text[:50] if text else 'empty'}")
                await self.text_response_callback(text)
            
            # 连接到post_route的sentence_stream获取完整句子流
            # 注意：post_route会将原始文本流分割成完整句子后输出
            logger.info("注册文本响应回调到post_route.sentence_stream")
            self.engine.add_external_connection("post_route", "sentence_stream", text_response_callback_wrapper)
            logger.info("文本响应回调已注册")

        db_manager = get_db_manager()

        # 8. 设置 session_id
        self.session_id = session_id

        # 9. 启动工作流并传入全局变量，保存返回的 context
        initial_data = {
            "user": UserDataWrapper(self.user_data),  # 用于 Jinja2 模板访问
            "user_data": self.user_data,  # 用于节点直接访问 UserData 实例
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "ai_providers": self.user_data.ai_providers,
            "db_manager": db_manager,
            "session_id": self.session_id,
            "copilot_mode": copilot_mode if copilot_mode is not None else False,  # 星宝领航员模式标识
        }
        self.context = await self.engine.start(initial_data=initial_data)
        
        return True
    
    async def _load_workflow_config(self, user_config: Optional[dict] = None, copilot_mode: Optional[bool] = None) -> dict:
        """加载工作流配置
        
        Args:
            user_config: 用户自定义工作流配置，可选
            copilot_mode: 是否启用星宝领航员模式，如果为True则加载workflow_copilot.yaml
        """
        # 根据copilot_mode选择配置文件
        if copilot_mode:
            config_path = Path(__file__).parent / "workflows" / "workflow_copilot.yaml"
        else:
            config_path = Path(__file__).parent / "workflows" / "workflow_chat.yaml"
        
        # 加载配置文件
        with open(config_path, 'r', encoding='utf-8') as f:
            config_dict = yaml.safe_load(f)
        
        # 如果用户提供了自定义配置，合并到默认配置
        if user_config:
            # 这里可以实现配置合并逻辑
            # 暂时直接使用用户配置
            config_dict = user_config
        
        return config_dict
    
    def get_config(self, key: str, default=None):
        """配置读取接口（支持点号路径），供外部使用"""
        if not self.user_data:
            return default
        return self.user_data.get_config(key, default)
        
    async def close_session(self):
        """关闭会话，保存配置"""
        # 1. 触发会话分析任务（在非copilot模式下）
        await self._trigger_session_analysis()
        
        # 2. 保存用户数据
        if self.user_data:
            await self.user_data.save()
        
        # 3. 停止工作流
        await self.detach()
    
    async def _trigger_session_analysis(self):
        """触发会话分析任务"""
        try:
            # 只在非 copilot_mode 下触发分析
            copilot_mode = self.context.get_global_var("copilot_mode") if self.context else False
            if copilot_mode:
                return
            
            # 获取必要的参数
            session_id = self.session_id
            if not session_id:
                return
            
            agent_id = None
            if self.user_data:
                try:
                    agent_id = self.user_data.agent_id
                except Exception as e:
                    logger.debug(f"获取agent_id失败: {e}")
            
            if not agent_id:
                return
            
            # 1. 创建数据库分析任务记录
            from src.agents.nodes.analysis.repository import SessionAnalysisRepository
            repository = SessionAnalysisRepository()
            await repository.create_analysis_task(
                session_id=session_id,
                agent_id=agent_id,
                copilot_mode=False
            )
            
            # 2. 发送分析任务到系统工作流
            from src.agents.workflow_system import get_system_workflow_manager
            system_workflow = await get_system_workflow_manager()
            await system_workflow.send_analysis_task(
                session_id=session_id,
                agent_id=agent_id,
                copilot_mode=False
            )
            
        except Exception as e:
            logger.warning(f"触发会话分析任务失败: {e}")

    async def detach(self):
        """停止工作流"""
        if self.engine:
            await self.engine.stop()
        self.engine = None

    async def push_opus(self, opus_bytes: bytes):
        """推送 Opus 音频帧到工作流 VAD 节点"""
        if not self.engine:
            return
        
        await self.engine.get_node("vad").feed_input_chunk("audio_stream", {"data": opus_bytes})

    async def push_text(self, text: str, emotion: str = "neutral"):
        """推送文本内容到工作流，触发聊天处理流程
        
        工作流处理流程：
        1. 文本输入 → interrupt_controller.recognized_text
        2. interrupt_controller → route.user_text（路由到默认agent）
        3. route → agent1.user_text（默认agent处理）
        4. agent1.response_text_stream → post_route.text_stream
        5. post_route.sentence_stream → tts.text_stream（完整句子流）
        6. 文本响应通过 text_response_callback 回调发送给客户端（从 post_route.sentence_stream 获取完整句子）
        7. TTS状态通过 tts_status_callback 回调发送给客户端
        
        Args:
            text: 用户输入的文本
            emotion: 用户情感状态，默认为 "neutral"
        """
        if not self.engine:
            return
        
        # 向 interrupt_controller 节点推送用户文本输入，包含情感信息
        # interrupt_controller 会处理并路由到 route 节点
        await self.engine.get_node("interrupt_controller").feed_input_chunk("recognized_text", {
            "text": text, 
            "confidence": 1.0,
            "emotion": emotion,
            "audio_file_path": ""
        })
