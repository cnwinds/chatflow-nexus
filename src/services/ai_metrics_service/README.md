# AI指标服务插件（数据库版本）

## 概述

AI指标服务插件是一个基于UTCP协议实现的AI模型调用性能监控和费用统计服务。该插件已重构为使用MySQL数据库进行数据持久化存储，提供更好的性能、扩展性和并发支持。

## 主要特性

### 🚀 性能优化
- **数据库存储**：使用MySQL替代JSON文件，支持高并发访问
- **索引优化**：针对常用查询字段建立索引，提升查询性能
- **批量操作**：支持批量数据插入和查询
- **连接池**：使用数据库连接池，提高连接效率

### 📊 数据管理
- **自动表创建**：首次使用时自动创建数据库表结构
- **数据清理**：支持自动清理过期数据
- **统计缓存**：缓存常用统计结果，提升查询速度

### 🔧 功能增强
- **模型定价管理**：支持动态更新模型定价信息
- **多维度统计**：支持按时间、模型、会话等维度统计
- **历史数据查询**：支持复杂的历史数据查询和过滤
- **实时监控**：提供实时的性能指标监控

## 数据库表结构

### ai_metrics 表
存储AI模型调用的详细指标数据：

```sql
CREATE TABLE ai_metrics (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    monitor_id VARCHAR(64) NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    session_id VARCHAR(64),
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    
    -- 阶段时间 (毫秒)
    preparation_time FLOAT DEFAULT 0.0,
    api_call_time FLOAT DEFAULT 0.0,
    
    -- Token统计
    prompt_tokens INT DEFAULT 0,
    completion_tokens INT DEFAULT 0,
    total_tokens INT DEFAULT 0,
    
    -- 内容统计
    input_chars INT DEFAULT 0,
    output_chars INT DEFAULT 0,
    
    -- 工具相关
    tool_count INT DEFAULT 0,
    tool_calls_made INT DEFAULT 0,
    
    -- 费用信息
    cost DECIMAL(10,6) DEFAULT 0.0,
    input_cost DECIMAL(10,6) DEFAULT 0.0,
    output_cost DECIMAL(10,6) DEFAULT 0.0,
    
    -- 性能指标
    first_token_time FLOAT,
    http_first_byte_time FLOAT,
    
    -- 索引
    INDEX idx_monitor_id (monitor_id),
    INDEX idx_model_name (model_name),
    INDEX idx_session_id (session_id),
    INDEX idx_start_time (start_time),
    INDEX idx_model_time (model_name, start_time)
);
```

### model_pricing 表
存储模型定价信息：

```sql
CREATE TABLE model_pricing (
    id INT AUTO_INCREMENT PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL UNIQUE,
    input_price_per_1k_tokens DECIMAL(10,6) NOT NULL,
    output_price_per_1k_tokens DECIMAL(10,6) NOT NULL,
    currency VARCHAR(10) DEFAULT 'USD',
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_model_name (model_name)
);
```

### statistics_cache 表
缓存统计结果：

```sql
CREATE TABLE statistics_cache (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cache_key VARCHAR(255) NOT NULL UNIQUE,
    cache_value JSON NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    
    INDEX idx_cache_key (cache_key),
    INDEX idx_expires_at (expires_at)
);
```

## 配置说明

### 服务配置 (default_config.json)

```json
{
  "service_config": {
    "max_history_records": 10000,
    "auto_cleanup_days": 30,
    "backup_interval_hours": 24,
    "enable_cost_calculation": true,
    "storage_type": "database"
  },
  "cost_calculation": {
    "fallback_to_zero_cost": true,
    "custom_pricing": {
      "gpt-4.1": {
        "input_cost_per_token": 0.000002,
        "output_cost_per_token": 0.000008
      }
    }
  },
  "database": {
    "auto_initialize": true,
    "auto_cleanup_enabled": true,
    "cleanup_interval_hours": 24,
    "max_retention_days": 90,
    "enable_statistics_cache": true,
    "cache_ttl_hours": 1
  },
  "performance": {
    "batch_insert_size": 100,
    "query_timeout_seconds": 30,
    "enable_query_logging": false,
    "slow_query_threshold_ms": 1000
  }
}
```

## 使用方法

### 1. 基本监控流程

```python
# 开始监控
result = await service.start_monitoring(model_name="gpt-4.1")
monitor_id = result["monitor_id"]

# 记录准备阶段
await service.record_preparation(
    monitor_id=monitor_id,
    duration_ms=150.5,
    input_chars=1000,
    tool_count=3
)

# 记录API调用
await service.record_api_call(
    monitor_id=monitor_id,
    duration_ms=2500.0,
    prompt_tokens=500,
    completion_tokens=200,
    output_chars=800,
    tool_calls_made=2,
    first_token_time=1200.0,
    http_first_byte_time=800.0
)

# 计算费用
cost_info = await service.calculate_cost(monitor_id, "gpt-4.1")

# 保存指标数据
await service.save_metrics(
    monitor_id=monitor_id,
    model_name="gpt-4.1",
    session_id="session_123"
)
```

### 2. 数据查询和统计

```python
# 获取统计数据
stats = await service.get_statistics(
    model_name="gpt-4.1",
    period="day"
)

# 加载历史数据
history = await service.load_historical_data(
    model_name="gpt-4.1",
    start_time=1640995200,  # 2022-01-01
    end_time=1641081600,    # 2022-01-02
    limit=100
)

# 获取数据统计信息
info = await service.get_data_info()
```

### 3. 模型定价管理

```python
# 获取模型定价
pricing = await service.get_model_pricing("gpt-4.1")

# 更新模型定价
await service.update_model_pricing(
    model_name="gpt-4.1",
    input_price_per_1k_tokens=0.002,
    output_price_per_1k_tokens=0.008,
    currency="USD"
)
```

### 4. 数据维护

```python
# 清理旧数据
result = await service.cleanup_old_data(max_days=30)
```

## 性能优化建议

### 1. 数据库配置
- 确保MySQL配置了适当的缓冲池大小
- 定期优化表结构和索引
- 配置合适的连接池大小

### 2. 查询优化
- 使用索引字段进行查询过滤
- 避免在高峰期进行大量数据查询
- 利用统计缓存减少重复计算

### 3. 数据清理
- 定期清理过期数据
- 监控数据库大小增长
- 设置合适的数据保留策略

## 监控和日志

### 日志级别
- `INFO`：重要操作和状态变化
- `DEBUG`：详细的调试信息
- `WARNING`：警告信息
- `ERROR`：错误信息

### 关键指标
- 数据库连接状态
- 查询执行时间
- 数据插入成功率
- 缓存命中率

## 故障排除

### 常见问题

1. **数据库连接失败**
   - 检查数据库配置
   - 确认数据库服务运行状态
   - 验证网络连接

2. **表创建失败**
   - 检查数据库权限
   - 确认数据库版本兼容性
   - 查看错误日志

3. **查询性能问题**
   - 检查索引是否正确创建
   - 优化查询语句
   - 调整数据库配置

### 调试方法

```python
# 获取详细错误信息
try:
    await service.save_metrics(monitor_id, model_name)
except Exception as e:
    logger.error(f"保存失败: {e}")
    # 检查数据库连接状态
    info = await service.get_data_info()
    print(f"数据库状态: {info}")
```

## 版本历史

### v2.0.0 (当前版本)
- 重构为数据库存储
- 优化查询性能
- 增强统计功能
- 添加UTCP协议支持

### v1.x.x (旧版本)
- 基于JSON文件存储
- 基础监控功能
- 简单统计功能

## 贡献指南

欢迎提交Issue和Pull Request来改进这个插件。在提交代码前，请确保：

1. 代码符合项目规范
2. 添加适当的测试
3. 更新相关文档
4. 遵循编程最佳实践

## 许可证

本项目采用MIT许可证。
