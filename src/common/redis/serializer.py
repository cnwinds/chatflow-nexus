"""
Redis序列化器模块
"""

import json
import pickle
import logging
from typing import Any, Union
from .exceptions import RedisSerializationError

try:
    import msgpack
    MSGPACK_AVAILABLE = True
except ImportError:
    MSGPACK_AVAILABLE = False


class RedisSerializer:
    """Redis序列化器"""
    
    def __init__(self, default_serializer: str = "json", logger: logging.Logger = None):
        """初始化序列化器"""
        self.default_serializer = default_serializer
        self.logger = logger or logging.getLogger(__name__)
        
        # 验证序列化器类型
        if default_serializer not in ["json", "pickle", "msgpack"]:
            raise RedisSerializationError(f"不支持的序列化器类型: {default_serializer}")
        
        if default_serializer == "msgpack" and not MSGPACK_AVAILABLE:
            raise RedisSerializationError("msgpack 序列化器不可用，请安装 msgpack 包")
    
    def serialize(self, obj: Any, serializer: str = None) -> bytes:
        """序列化对象"""
        serializer = serializer or self.default_serializer
        
        try:
            if serializer == "json":
                return self.serialize_json(obj).encode('utf-8')
            elif serializer == "pickle":
                return self.serialize_pickle(obj)
            elif serializer == "msgpack":
                return self.serialize_msgpack(obj)
            else:
                raise RedisSerializationError(f"不支持的序列化器: {serializer}")
                
        except Exception as e:
            error_msg = f"序列化失败 ({serializer}): {e}"
            self.logger.error(error_msg)
            raise RedisSerializationError(error_msg)
    
    def deserialize(self, data: bytes, serializer: str = None) -> Any:
        """反序列化对象"""
        if not data:
            return None
            
        serializer = serializer or self.default_serializer
        
        try:
            if serializer == "json":
                return self.deserialize_json(data.decode('utf-8'))
            elif serializer == "pickle":
                return self.deserialize_pickle(data)
            elif serializer == "msgpack":
                return self.deserialize_msgpack(data)
            else:
                raise RedisSerializationError(f"不支持的序列化器: {serializer}")
                
        except Exception as e:
            error_msg = f"反序列化失败 ({serializer}): {e}"
            self.logger.error(error_msg)
            raise RedisSerializationError(error_msg)
    
    def serialize_json(self, obj: Any) -> str:
        """JSON序列化"""
        try:
            return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
        except (TypeError, ValueError) as e:
            raise RedisSerializationError(f"JSON序列化失败: {e}")
    
    def deserialize_json(self, data: str) -> Any:
        """JSON反序列化"""
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError) as e:
            raise RedisSerializationError(f"JSON反序列化失败: {e}")
    
    def serialize_pickle(self, obj: Any) -> bytes:
        """Pickle序列化"""
        try:
            return pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
        except (pickle.PicklingError, TypeError) as e:
            raise RedisSerializationError(f"Pickle序列化失败: {e}")
    
    def deserialize_pickle(self, data: bytes) -> Any:
        """Pickle反序列化"""
        try:
            return pickle.loads(data)
        except (pickle.UnpicklingError, TypeError) as e:
            raise RedisSerializationError(f"Pickle反序列化失败: {e}")
    
    def serialize_msgpack(self, obj: Any) -> bytes:
        """MessagePack序列化"""
        if not MSGPACK_AVAILABLE:
            raise RedisSerializationError("msgpack 不可用")
        
        try:
            return msgpack.packb(obj, use_bin_type=True)
        except (msgpack.PackException, TypeError) as e:
            raise RedisSerializationError(f"MessagePack序列化失败: {e}")
    
    def deserialize_msgpack(self, data: bytes) -> Any:
        """MessagePack反序列化"""
        if not MSGPACK_AVAILABLE:
            raise RedisSerializationError("msgpack 不可用")
        
        try:
            return msgpack.unpackb(data, raw=False, strict_map_key=False)
        except (msgpack.UnpackException, TypeError) as e:
            raise RedisSerializationError(f"MessagePack反序列化失败: {e}")
    
    def auto_serialize(self, obj: Any) -> tuple[bytes, str]:
        """自动选择最佳序列化方式"""
        # 简单类型直接用JSON
        if isinstance(obj, (str, int, float, bool, list, dict)) and self._is_json_serializable(obj):
            try:
                return self.serialize(obj, "json"), "json"
            except RedisSerializationError:
                pass
        
        # 复杂类型使用pickle
        try:
            return self.serialize(obj, "pickle"), "pickle"
        except RedisSerializationError:
            pass
        
        # 最后尝试msgpack
        if MSGPACK_AVAILABLE:
            try:
                return self.serialize(obj, "msgpack"), "msgpack"
            except RedisSerializationError:
                pass
        
        raise RedisSerializationError("无法序列化对象，所有序列化器都失败")
    
    def _is_json_serializable(self, obj: Any) -> bool:
        """检查对象是否可以JSON序列化"""
        try:
            json.dumps(obj)
            return True
        except (TypeError, ValueError):
            return False
    
    def get_serializer_info(self) -> dict:
        """获取序列化器信息"""
        return {
            "default_serializer": self.default_serializer,
            "available_serializers": {
                "json": True,
                "pickle": True,
                "msgpack": MSGPACK_AVAILABLE
            }
        }