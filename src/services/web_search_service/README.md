# 智谱Web搜索服务开发文档

## 概述

智谱Web搜索服务是基于智谱AI Web Search API实现的网络搜索服务，提供统一的搜索调用接口。支持结构化搜索结果、多引擎支持、域名过滤、时间范围过滤等功能。

## 功能特性

- ✅ 结构化搜索结果（标题/URL/摘要/网站名/图标等）
- ✅ 多搜索引擎支持（search_std、search_pro、search_pro_sogou、search_pro_quark）
- ✅ 域名过滤（可指定搜索特定域名）
- ✅ 时间范围过滤（支持按天/周/月/年过滤）
- ✅ 摘要字数控制（low/medium/high）
- ✅ 异步调用支持
- ✅ 错误处理和日志记录

## 配置说明

### 基本配置

在 `default_config.json` 中配置以下参数：

```json
{
  "service_config": {
    "default_search_engine": "search_pro",      // 默认搜索引擎
    "default_count": 10,                        // 默认返回结果数量（1-50）
    "default_content_size": "medium",            // 默认摘要字数：low/medium/high
    "default_recency_filter": "noLimit",        // 默认时间过滤：noLimit/day/week/month/year
    "timeout": 30                               // 超时时间（秒）
  },
  "api_config": {
    "api_key": ""                               // 智谱AI API密钥（必需）
  },
  "logging": {
    "level": "INFO",                            // 日志级别
    "enable_detailed_logs": false,              // 是否启用详细日志
    "log_search_queries": true                  // 是否记录搜索查询
  }
}
```

### 必需配置项

- `api_config.api_key`: 智谱AI的API密钥，必需配置。可在 [智谱AI开放平台](https://open.bigmodel.cn/usercenter/apikeys) 获取。

### 可选配置项

- `service_config.default_search_engine`: 默认搜索引擎类型
  - `search_std`: 基础版（智谱AI自研），0.01元/次
  - `search_pro`: 高级版（智谱AI自研），0.03元/次
  - `search_pro_sogou`: 搜狗引擎，0.05元/次
  - `search_pro_quark`: 夸克引擎，0.05元/次

## API 文档

### 官方文档链接

- 智谱AI Web Search API文档: https://docs.bigmodel.cn/cn/guide/tools/web-search
- API参考文档: https://docs.bigmodel.cn/api-reference/工具-api/网络搜索

## 工具列表

### 1. web_search

执行网络搜索，获取结构化搜索结果。

**参数：**
- `search_query` (string, 必需): 搜索查询词
- `search_engine` (string, 可选): 搜索引擎类型，默认 "search_pro"
  - `search_std`: 基础版（0.01元/次）
  - `search_pro`: 高级版（0.03元/次）
  - `search_pro_sogou`: 搜狗（0.05元/次）
  - `search_pro_quark`: 夸克（0.05元/次）
- `count` (integer, 可选): 返回结果数量，范围1-50，默认10
- `search_domain_filter` (string, 可选): 域名过滤，只搜索指定域名的内容（如："www.sohu.com"）
- `search_recency_filter` (string, 可选): 时间范围过滤，默认 "noLimit"
  - `noLimit`: 不限时间
  - `day`: 一天内
  - `week`: 一周内
  - `month`: 一月内
  - `year`: 一年内
- `content_size` (string, 可选): 网页摘要字数，默认 "medium"
  - `low`: 较少
  - `medium`: 中等
  - `high`: 较多

**返回：**
```json
{
  "status": "success",
  "query": "搜索查询词",
  "search_engine": "search_pro",
  "results": [
    {
      "title": "搜索结果标题",
      "url": "https://example.com",
      "snippet": "网页摘要内容",
      "site_name": "网站名称",
      "icon": "网站图标URL"
    }
  ],
  "total_results": 10,
  "search_metadata": {
    "count": 10,
    "domain_filter": null,
    "recency_filter": "noLimit",
    "content_size": "medium"
  }
}
```

### 2. health_check

检查Web搜索服务健康状态。

**参数：** 无

**返回：**
```json
{
  "status": "healthy",
  "service": "web_search_service",
  "config_valid": true,
  "api_key_configured": true,
  "default_search_engine": "search_pro",
  "default_count": 10,
  "default_content_size": "medium",
  "default_recency_filter": "noLimit",
  "timeout": 30,
  "client_initialized": true
}
```

## 搜索引擎说明

| 搜索引擎编码 | 特性 | 价格 |
|------------|------|------|
| search_std | 基础版（智谱AI自研）：满足日常查询需求，性价比极高 | 0.01元/次 |
| search_pro | 高级版（智谱AI自研）：多引擎协作显著降低空结果率，召回率和准确率大幅提升 | 0.03元/次 |
| search_pro_sogou | 搜狗：覆盖腾讯生态（新闻/企鹅号）和知乎内容，在百科、医疗等垂直领域权威性强 | 0.05元/次 |
| search_pro_quark | 夸克：精准触达垂直内容 | 0.05元/次 |

## 使用示例

### Python 代码示例

```python
from src.services.web_search_service import WebSearchService

# 创建服务实例（通常由UTCP框架管理）
service = WebSearchService(config, config_manager, logger)

# 初始化服务
service.init()

# 基础搜索
result = await service.call_tool("web_search", {
    "search_query": "2025年4月的财经新闻"
})

if result.get("status") == "success":
    for item in result["results"]:
        print(f"标题: {item.get('title')}")
        print(f"URL: {item.get('url')}")
        print(f"摘要: {item.get('snippet')}")

# 指定域名搜索
result = await service.call_tool("web_search", {
    "search_query": "2025年4月的财经新闻",
    "search_domain_filter": "www.sohu.com",
    "count": 5
})

# 使用搜狗引擎搜索
result = await service.call_tool("web_search", {
    "search_query": "Python编程教程",
    "search_engine": "search_pro_sogou",
    "search_recency_filter": "week",
    "content_size": "high"
})

# 健康检查
health = await service.call_tool("health_check", {})
print(f"服务状态: {health['status']}")
```

### 搜索示例场景

#### 1. 搜索财经新闻（指定域名）

```python
result = await service.call_tool("web_search", {
    "search_query": "2025年4月的重要财经事件、政策变化和市场数据",
    "search_domain_filter": "www.sohu.com",
    "count": 15,
    "search_recency_filter": "month",
    "content_size": "high"
})
```

#### 2. 搜索技术文档（使用搜狗引擎）

```python
result = await service.call_tool("web_search", {
    "search_query": "Python异步编程最佳实践",
    "search_engine": "search_pro_sogou",
    "count": 10,
    "content_size": "high"
})
```

#### 3. 搜索最新资讯（一周内）

```python
result = await service.call_tool("web_search", {
    "search_query": "人工智能最新进展",
    "search_recency_filter": "week",
    "count": 20
})
```

## 错误处理

服务使用统一的错误处理机制，所有错误都会返回标准格式：

```json
{
  "status": "error",
  "error": "错误描述",
  "message": "网络搜索失败: 错误描述"
}
```

常见错误：
- API密钥未配置或无效
- 搜索查询词为空
- 参数值超出范围（如count不在1-50之间）
- API调用失败（网络问题、超时等）
- SDK未安装

## 依赖项

- `zai-sdk`: 智谱AI官方SDK，用于调用Web Search API
- `asyncio`: 异步支持
- `concurrent.futures`: 线程池支持（用于异步执行同步SDK调用）

安装依赖：
```bash
pip install zai-sdk
```

## 注意事项

1. **API密钥安全**: 请妥善保管API密钥，不要提交到代码仓库
2. **费用说明**: 不同搜索引擎有不同的计费标准，请根据需求选择合适的引擎
3. **超时设置**: 默认超时时间为30秒，可根据网络情况调整
4. **结果数量限制**: count参数必须在1-50之间
5. **异步调用**: SDK是同步的，服务内部使用线程池将其包装为异步调用
6. **响应格式**: API返回的响应格式可能因版本而异，服务会尝试适配不同的响应结构

## 开发指南

### 添加新功能

1. 在 `service.py` 中添加新的方法
2. 在 `get_tools()` 中注册新工具
3. 在 `call_tool()` 中添加工具处理逻辑
4. 更新 `default_config.json` 添加相关配置
5. 更新本文档

### 测试

建议编写单元测试和集成测试来验证功能：

```python
import pytest
from src.services.web_search_service import WebSearchService

@pytest.mark.asyncio
async def test_web_search():
    # 测试代码
    pass
```

## 更新日志

### v1.0.0 (2025-01-XX)
- 初始版本
- 支持基本的网络搜索功能
- 支持多搜索引擎
- 支持域名过滤和时间范围过滤
- 支持摘要字数控制
- 异步调用支持

## 相关链接

- [智谱AI开放平台](https://open.bigmodel.cn/)
- [Web Search API文档](https://docs.bigmodel.cn/cn/guide/tools/web-search)
- [API参考文档](https://docs.bigmodel.cn/api-reference/工具-api/网络搜索)
- [产品价格](https://bigmodel.cn/pricing)
- [UTCP框架文档](../utcp/README.md)





