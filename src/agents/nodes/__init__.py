"""节点注册入口"""

# 导入以触发 @register_node 装饰器注册
from .vad_node import VADNode  # noqa: F401
from .stt_node import STTNode  # noqa: F401
from .agent_node import AgentNode  # noqa: F401
from .tts_node import TTSNode  # noqa: F401
from .post_route_node import PostRouteNode  # noqa: F401
from .route_node import RouteNode  # noqa: F401
from .interrupt_controller_node import InterruptControllerNode  # noqa: F401
from .chat_record_node import ChatRecordNode  # noqa: F401
from .analysis_node import AnalysisNode  # noqa: F401
from .daily_summary_node import DailySummaryNode  # noqa: F401
from .weekly_summary_node import WeeklySummaryNode  # noqa: F401
