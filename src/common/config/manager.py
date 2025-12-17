"""
统一配置管理器 - 简化版本
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional, Union
from .validator import ConfigValidator
from ..exceptions import ConfigurationError, PathError
from ..utils.environment import EnvironmentManager

# 全局配置管理器实例
_config_manager = None

class ConfigManager:
    """统一配置管理器 - 简化版本"""
    
    def __init__(self, runtime_root: Path, service_src_root: Optional[Path] = None, env_prefix: str = 'AI_AGENTS'):
        """初始化配置管理器
        
        Args:
            runtime_root: 运行时根目录路径
            service_src_root: 服务源码根目录路径（可选）
            env_prefix: 环境变量前缀
        """
        self.env_prefix = env_prefix

        # 初始化路径配置
        self._init_paths(runtime_root, service_src_root)
        
        # 初始化环境变量管理器
        self.env_manager = EnvironmentManager(env_prefix)
        
        # 配置缓存
        self._config_cache = {}
    
    def _init_paths(self, runtime_root: Path, service_src_root: Optional[Path] = None):
        """初始化路径配置"""
        # 设置运行时根目录
        self.runtime_root = Path(runtime_root)
        
        # 设置服务源码根目录（如果提供）
        if service_src_root is not None:
            self.service_src_root = Path(service_src_root)
        else:
            # 如果没有提供，设置为None，表示不需要访问服务源码配置
            self.service_src_root = None
        
        # 设置项目根目录（运行时根目录的父目录）
        self.project_root = self.runtime_root.parent
        
        # 设置默认路径
        self.config_dir = self.runtime_root / "config"
        self.data_dir = self.runtime_root / "data"
        self.logs_dir = self.runtime_root / "log"
        self.services_dir = self.service_src_root if self.service_src_root else self.runtime_root / "services"
        
        # 应用环境变量覆盖
        self._apply_env_path_overrides()
    
    def _apply_env_path_overrides(self):
        """应用环境变量路径覆盖"""
        path_mappings = {
            'CONFIG_DIR': 'config_dir',
            'DATA_DIR': 'data_dir', 
            'LOGS_DIR': 'logs_dir',
            'SERVICES_DIR': 'services_dir',
            'RUNTIME_ROOT': 'runtime_root',
            'SERVICE_SRC_ROOT': 'service_src_root'
        }
        
        for env_key, attr_name in path_mappings.items():
            env_value = os.getenv(f"{self.env_prefix}_{env_key}")
            if env_value:
                setattr(self, attr_name, Path(env_value))
    
    def _load_json_file(self, file_path: Path) -> Dict[str, Any]:
        """加载JSON文件
        
        Args:
            file_path: JSON文件路径
            
        Returns:
            加载的配置字典
            
        Raises:
            ConfigurationError: 文件不存在或格式错误
        """
        if not file_path.exists():
            return {}
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 应用环境变量覆盖
            config = self._apply_env_overrides(config, self.env_prefix)
            
            return config
            
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"配置文件 {file_path} 格式错误: {e}")
        except Exception as e:
            raise ConfigurationError(f"加载配置文件 {file_path} 失败: {e}")
    
    def _apply_env_overrides(self, config: Dict, prefix: str = None) -> Dict:
        """应用环境变量覆盖"""
        if not prefix:
            return config
        
        def apply_env_to_dict(d: Dict, current_prefix: str = ""):
            for key, value in d.items():
                env_key = f"{prefix}_{current_prefix}_{key}".upper().replace(".", "_")
                env_value = os.getenv(env_key)
                
                if env_value is not None:
                    # 尝试转换类型
                    if isinstance(value, bool):
                        d[key] = env_value.lower() in ('true', '1', 'yes')
                    elif isinstance(value, int):
                        try:
                            d[key] = int(env_value)
                        except ValueError:
                            pass
                    elif isinstance(value, float):
                        try:
                            d[key] = float(env_value)
                        except ValueError:
                            pass
                    else:
                        d[key] = env_value
                
                # 递归处理嵌套字典
                elif isinstance(value, dict):
                    apply_env_to_dict(value, f"{current_prefix}_{key}" if current_prefix else key)
        
        apply_env_to_dict(config)
        return config
    
    def _process_config_env_vars(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """处理配置中的环境变量替换（${VAR}格式）"""
        if not isinstance(config, dict):
            return config
        
        processed_config = {}
        for key, value in config.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                env_var_name = value[2:-1]
                env_value = os.getenv(env_var_name)
                if env_value is not None:
                    processed_config[key] = env_value
                else:
                    # 如果环境变量未设置，保持原值
                    processed_config[key] = value
            elif isinstance(value, dict):
                # 递归处理嵌套字典
                processed_config[key] = self._process_config_env_vars(value)
            elif isinstance(value, list):
                # 处理列表中的环境变量
                processed_config[key] = [
                    self._process_config_env_vars(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                processed_config[key] = value
        
        return processed_config
    
    def _merge_configs(self, default: Dict, override: Dict) -> Dict:
        """合并配置字典"""
        if not override:
            return default
        
        result = default.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def _get_nested_value(self, data: Dict, key_path: str, default: Any = None) -> Any:
        """根据点分隔的键路径获取嵌套值
        
        Args:
            data: 要搜索的字典
            key_path: 点分隔的键路径，如 "database.host"
            default: 默认值
            
        Returns:
            找到的值或默认值
        """
        if not key_path:
            return data
        
        keys = key_path.split('.')
        current = data
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        
        return current
    
    def get_config(self, key_path: str, default: Any = None) -> Any:
        """获取配置文件中的值
        
        Args:
            key_path: 配置键路径，支持点分隔符，如 "database.host" 或 "redis.port"
            default: 默认值
            
        Returns:
            配置值或默认值
            
        Examples:
            >>> config_manager.get_config("database.host", "localhost")
            "localhost"
            >>> config_manager.get_config("redis.port", 6379)
            6379
        """
        # 解析键路径，第一级是配置文件名
        parts = key_path.split('.', 1)
        config_name = parts[0]
        nested_path = parts[1] if len(parts) > 1 else ""
        
        # 从缓存获取配置
        cache_key = f"config_{config_name}"
        
        if cache_key not in self._config_cache:
            # 加载配置文件
            config_path = self.config_dir / f"{config_name}.json"
            config = self._load_json_file(config_path)
            self._config_cache[cache_key] = config
        
        config = self._config_cache[cache_key]
        
        # 如果没有嵌套路径，返回整个配置
        if not nested_path:
            return config
        
        # 获取嵌套值
        return self._get_nested_value(config, nested_path, default)
    
    def set_config(self, key_path: str, value: Any) -> None:
        """设置配置值
        
        Args:
            key_path: 配置键路径，支持点分隔符
            value: 要设置的值
            
        Examples:
            >>> config_manager.set_config("database", {"host": "localhost", "port": 3306})
            >>> config_manager.set_config("database.host", "new_host")
            >>> config_manager.set_config("redis.port", 6380)
        """
        # 解析键路径，第一级是配置文件名
        parts = key_path.split('.', 1)
        config_name = parts[0]
        nested_path = parts[1] if len(parts) > 1 else ""
        
        # 从缓存获取配置
        cache_key = f"config_{config_name}"
        
        if cache_key not in self._config_cache:
            # 加载配置文件
            config_path = self.config_dir / f"{config_name}.json"
            config = self._load_json_file(config_path)
            self._config_cache[cache_key] = config
        
        config = self._config_cache[cache_key]
        
        # 如果没有嵌套路径，设置整个配置对象
        if not nested_path:
            config.clear()
            if isinstance(value, dict):
                config.update(value)
            else:
                raise ValueError(f"当key不包含'.'时，value必须是字典类型，当前类型: {type(value)}")
        else:
            # 设置嵌套值
            self._set_nested_value(config, nested_path, value)
        
    def _set_nested_value(self, data: Dict, key_path: str, value: Any) -> None:
        """设置嵌套字典中的值
        
        Args:
            data: 要修改的字典
            key_path: 点分隔的键路径，如 "database.host"
            value: 要设置的值
        """
        keys = key_path.split('.')
        current = data
        
        # 遍历到倒数第二个键，确保路径存在
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            elif not isinstance(current[key], dict):
                # 如果当前值不是字典，将其转换为字典
                current[key] = {}
            current = current[key]
        
        # 设置最后一个键的值
        current[keys[-1]] = value
    
    def get_service_config(self, service_name: str, default: Any = None, module_path: Optional[str] = None) -> Any:
        """获取服务配置中的值（集成环境变量替换和配置验证）
        
        Args:
            service_name: 服务名称
            default: 默认值
            module_path: 模块路径（可选），用于加载默认配置文件，如果不提供则使用service_name
            
        Returns:
            处理后的配置值或默认值
            
        Examples:
            >>> config_manager.get_service_config("my_service", {})
            {"database": {"host": "localhost"}, "redis": {"port": 6379}}
            >>> config_manager.get_service_config("my_service.database.host", "localhost")
            "localhost"
        """
        # 从缓存获取服务配置
        cache_key = f"service_{service_name}"
        
        # 如果传入了default参数（通常是services.json中的配置），需要与加载的配置合并
        # 确保传入的配置优先级最高
        if default and isinstance(default, dict):
            # 即使缓存存在，也要重新合并，确保传入的配置生效
            # 加载服务配置（三级配置合并）
            service_config = self._load_service_config(service_name, module_path=module_path)
            # 将传入的配置合并到加载的配置上（优先级最高）
            service_config = self._merge_configs(service_config, default)
        elif cache_key not in self._config_cache:
            # 加载服务配置（三级配置合并）
            service_config = self._load_service_config(service_name, module_path=module_path)
        else:
            # 使用缓存
            service_config = self._config_cache[cache_key]
        
        # 处理环境变量替换
        service_config = self._process_config_env_vars(service_config)
        
        # 配置验证（如果有验证规则）
        if "validation" in service_config:
            try:
                validation_schema = service_config["validation"]
                # 移除验证规则，避免传递给服务
                del service_config["validation"]
                # 验证配置
                self._validate_config(service_config, validation_schema)
            except Exception as e:
                raise ConfigurationError(f"服务 {service_name} 配置验证失败: {e}")
        
        # 更新缓存
        if default and isinstance(default, dict) or cache_key not in self._config_cache:
            self._config_cache[cache_key] = service_config
        
        # 如果service_config为空且default是字典，返回default
        if not service_config and isinstance(default, dict):
            return default
        
        return service_config
    

    
    def _validate_config(self, config: Dict[str, Any], validation_schema: Dict[str, Any]) -> None:
        """验证配置
        
        Args:
            config: 要验证的配置
            validation_schema: 验证模式（ConfigValidator 标准格式）
            
        Raises:
            ConfigurationError: 验证失败时抛出
        """
        # 使用 ConfigValidator 进行验证
        validator = ConfigValidator(config)
        
        # 直接使用 ConfigValidator 的标准格式
        if not validator.validate(validation_schema):
            errors = validator.get_errors()
            raise ConfigurationError(f"配置验证失败: {'; '.join(errors)}")
    
    def _load_service_config(self, service_name: str, module_path: Optional[str] = None) -> Dict[str, Any]:
        """加载服务配置（三级配置合并）
        
        优先级：services.json > runtime配置 > 默认配置
        
        Args:
            service_name: 服务名称
            module_path: 模块路径（可选），用于加载默认配置文件，如果不提供则使用service_name
        """
        # 1. 加载默认配置（服务源码目录）
        # 使用module_path作为目录名，如果没有提供则使用service_name
        # 如果module_path是绝对路径，提取目录名（最后一部分）
        if module_path:
            # 从路径中提取目录名（处理绝对路径和相对路径）
            default_config_dir = Path(module_path).name
        else:
            default_config_dir = service_name
        default_config = self._load_service_default_config(default_config_dir)
        
        # 2. 加载运行时配置
        runtime_config = self._load_service_runtime_config(service_name)
        
        # 3. 加载services.json配置（最高优先级）
        services_config = self._load_service_from_services_config(service_name)
        
        # 4. 按优先级合并配置
        merged_config = self._merge_configs(default_config, runtime_config)
        merged_config = self._merge_configs(merged_config, services_config)
        
        # 5. 应用环境变量覆盖
        env_prefix = f"{service_name.upper()}"
        merged_config = self._apply_env_overrides(merged_config, env_prefix)
        
        return merged_config
    
    def _load_service_default_config(self, config_dir_name: str) -> Dict[str, Any]:
        """加载服务默认配置（服务源码目录）
        
        Args:
            config_dir_name: 配置目录名称（通常是module_path或service_name）
        """
        # 如果没有设置服务源码根目录，返回空配置
        if self.service_src_root is None:
            return {}
        
        service_dir = self.services_dir / config_dir_name
        default_config_path = service_dir / "default_config.json"
        
        if not default_config_path.exists():
            return {}
        
        try:
            with open(default_config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"服务默认配置文件 {default_config_path} 格式错误: {e}")
        except Exception as e:
            raise ConfigurationError(f"加载服务默认配置 {default_config_path} 失败: {e}")
    
    def _load_service_runtime_config(self, service_name: str) -> Dict[str, Any]:
        """加载服务运行时配置（runtime/config/services/{service_name}/config.json）"""
        runtime_config_path = self.config_dir / "services" / service_name / "config.json"
        
        if not runtime_config_path.exists():
            return {}
        
        try:
            with open(runtime_config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"服务运行时配置文件 {runtime_config_path} 格式错误: {e}")
        except Exception as e:
            raise ConfigurationError(f"加载服务运行时配置 {runtime_config_path} 失败: {e}")
    
    def _load_service_from_services_config(self, service_name: str) -> Dict[str, Any]:
        """从services.json加载服务配置（最高优先级）"""
        try:
            services_config_path = self.config_dir / "services.json"
            if not services_config_path.exists():
                return {}
            
            services_config = self._load_json_file(services_config_path)
            return services_config.get(service_name, {}).get("config", {})
            
        except Exception as e:
            # 如果加载失败，返回空配置
            return {}
    
    def reload_config(self, config_name: str = None):
        """重新加载配置缓存"""
        if config_name:
            # 重新加载特定配置
            cache_key = f"config_{config_name}"
            if cache_key in self._config_cache:
                del self._config_cache[cache_key]
        else:
            # 重新加载所有配置
            self._config_cache.clear()


# 全局便捷访问函数
def get_config_manager() -> ConfigManager:
    """获取配置管理器实例
    
    Returns:
        ConfigManager: 配置管理器实例
        
    Raises:
        RuntimeError: 配置管理器未初始化
    """
    global _config_manager
    if _config_manager is None:
        raise RuntimeError("配置管理器未初始化")
    return _config_manager


def get_config(key_path: str, default: Any = None) -> Any:
    """便捷获取配置值
    
    Args:
        key_path: 配置键路径，支持点分隔符
        default: 默认值
        
    Returns:
        配置值或默认值
    """
    config_manager = get_config_manager()
    return config_manager.get_config(key_path, default)


def set_config(key_path: str, value: Any) -> None:
    """便捷设置配置值
    
    Args:
        key_path: 配置键路径，支持点分隔符
        value: 要设置的值
        
    Examples:
        >>> set_config("database", {"host": "localhost", "port": 3306})
        >>> set_config("database.host", "new_host")
        >>> set_config("redis.port", 6380)
    """
    config_manager = get_config_manager()
    config_manager.set_config(key_path, value)


def initialize_config(runtime_root, service_src_root=None, env_prefix=''):
    """初始化配置管理器
    
    Args:
        runtime_root: 运行时根目录路径
        service_src_root: 服务源码根目录路径（可选）
        env_prefix: 环境变量前缀
        
    Returns:
        ConfigManager: 初始化后的配置管理器实例
    """
    global _config_manager
    
    # 创建配置管理器
    config_manager = ConfigManager(
        runtime_root=runtime_root,
        service_src_root=service_src_root,
        env_prefix=env_prefix
    )
    
    # 设置全局实例
    _config_manager = config_manager
    
    return config_manager


def is_config_ready() -> bool:
    """检查配置管理器是否已初始化
    
    Returns:
        bool: 是否已初始化
    """
    global _config_manager
    return _config_manager is not None 