"""
核心组件异常定义

本模块定义了AI Toys项目中所有核心组件使用的异常类型。
所有自定义异常都继承自CoreError基类，提供统一的错误处理接口。
"""


class CoreError(Exception):
    """核心组件错误基类
    
    所有核心组件异常的基类，提供统一的错误处理接口。
    
    Attributes:
        message (str): 错误消息
        error_code (str): 错误代码，用于程序化处理
        context (dict): 错误上下文信息
    """
    
    def __init__(self, message: str, error_code: str = None, context: dict = None):
        """初始化核心错误
        
        Args:
            message: 错误消息
            error_code: 可选的错误代码
            context: 可选的错误上下文信息
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.context = context or {}
    
    def __str__(self) -> str:
        """返回格式化的错误信息"""
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            return f"{self.message} [{self.error_code}] ({context_str})"
        return f"{self.message} [{self.error_code}]"
    
    def to_dict(self) -> dict:
        """将异常转换为字典格式，便于日志记录和API返回"""
        return {
            "error_type": self.__class__.__name__,
            "error_code": self.error_code,
            "message": self.message,
            "context": self.context
        }


class ConfigurationError(CoreError):
    """配置相关错误
    
    用于配置文件加载、解析或验证失败时抛出。
    """
    pass


class PathError(CoreError):
    """路径相关错误
    
    用于文件或目录路径操作失败时抛出。
    """
    pass


class LoggingError(CoreError):
    """日志相关错误
    
    用于日志系统初始化或操作失败时抛出。
    """
    pass


class ValidationError(CoreError):
    """验证相关错误
    
    用于数据验证失败时抛出。
    """
    pass


class AuthenticationError(CoreError):
    """认证相关错误
    
    用于用户认证失败时抛出。
    """
    pass


class EnvironmentError(CoreError):
    """环境变量相关错误
    
    用于环境变量访问或解析失败时抛出。
    """
    pass


class DatabaseError(CoreError):
    """数据库相关错误基类
    
    所有数据库操作相关异常的基类。
    """
    pass


class DatabaseConnectionError(DatabaseError):
    """数据库连接错误
    
    当数据库连接建立失败、连接断开或连接池问题时抛出。
    """
    pass


class DatabaseQueryError(DatabaseError):
    """数据库查询错误
    
    当SQL查询执行失败、语法错误或权限不足时抛出。
    """
    pass


class DatabaseTransactionError(DatabaseError):
    """数据库事务错误
    
    当事务提交、回滚或死锁检测失败时抛出。
    """
    pass


class RedisError(CoreError):
    """Redis相关错误基类
    
    所有Redis操作相关异常的基类。
    """
    pass


class RedisConnectionError(RedisError):
    """Redis连接错误
    
    当Redis连接建立失败、连接断开或连接池问题时抛出。
    """
    pass


class RedisOperationError(RedisError):
    """Redis操作错误
    
    当Redis命令执行失败、权限不足或数据类型错误时抛出。
    """
    pass


class RedisSerializationError(RedisError):
    """Redis序列化错误
    
    当数据序列化或反序列化失败时抛出。
    """
    pass


class BusinessError(CoreError):
    """业务逻辑错误
    
    用于业务逻辑验证失败时抛出。
    """
    def __init__(self, code: int, message: str, context: dict = None):
        """初始化业务错误
        
        Args:
            code: 错误码
            message: 错误消息
            context: 可选的错误上下文信息
        """
        super().__init__(message, str(code), context)
        self.code = code


class VoiceCloneError(CoreError):
    """声音克隆相关错误基类
    
    所有声音克隆操作相关异常的基类。
    """
    pass


class VoiceCloneNotFoundError(VoiceCloneError):
    """声音克隆不存在错误
    
    当请求的声音克隆不存在时抛出。
    """
    pass


class InvalidAudioFormatError(VoiceCloneError):
    """音频格式无效错误
    
    当音频格式不支持或文件损坏时抛出。
    """
    pass


class AudioFileTooLargeError(VoiceCloneError):
    """音频文件过大错误
    
    当音频文件大小超过限制时抛出。
    """
    pass


class AudioDurationTooShortError(VoiceCloneError):
    """音频时长过短错误
    
    当音频时长不满足最小要求时抛出。
    """
    pass


class RoleNameExistsError(VoiceCloneError):
    """角色名已存在错误
    
    当用户尝试创建重复的角色名时抛出。
    """
    pass


class SynthesisFailedError(VoiceCloneError):
    """语音合成失败错误
    
    当语音合成过程失败时抛出。
    """
    pass


class TrainingFailedError(VoiceCloneError):
    """模型训练失败错误
    
    当声音模型训练失败时抛出。
    """
    pass


class StorageFullError(VoiceCloneError):
    """存储空间不足错误
    
    当存储空间不足时抛出。
    """
    pass


class VoiceInUseError(VoiceCloneError):
    """声音正在使用错误
    
    当尝试删除正在使用的声音克隆时抛出。
    """
    pass