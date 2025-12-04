# URL访问服务

## 概述

URL访问服务提供访问网页并返回结构化页面内容的功能。支持静态HTML页面和JavaScript渲染的页面（通过Playwright）。

## 功能特性

- 访问URL并获取页面内容
- 支持静态HTML页面
- 支持JavaScript渲染的页面（使用Playwright）
- 提取结构化数据：
  - 标题（title, h1-h6）
  - 正文内容（主要文本内容）
  - 链接（所有a标签）
  - 图片（所有img标签）
  - 元数据（meta标签）
  - 表格（table标签的结构化数据）

## 配置说明

### service_config

- `timeout`: 请求超时时间（秒），默认30
- `enable_javascript`: 是否启用JavaScript渲染，默认false
- `user_agent`: 用户代理字符串
- `max_content_length`: 最大内容长度限制（字节），默认10MB
- `playwright_browser`: Playwright浏览器类型（chromium/firefox/webkit），默认chromium
- `playwright_headless`: 是否无头模式，默认true
- `playwright_timeout`: Playwright超时时间（毫秒），默认30000

### extract_options

- `extract_images`: 是否提取图片，默认true
- `extract_tables`: 是否提取表格，默认true
- `extract_links`: 是否提取链接，默认true
- `extract_metadata`: 是否提取元数据，默认true
- `extract_headings`: 是否提取标题，默认true

## 工具说明

### fetch_url

访问URL并返回结构化页面内容。

**参数：**
- `url` (required): 要访问的URL地址
- `enable_javascript` (optional): 是否启用JavaScript渲染（覆盖配置）
- `extract_images` (optional): 是否提取图片（覆盖配置）
- `extract_tables` (optional): 是否提取表格（覆盖配置）
- `extract_links` (optional): 是否提取链接（覆盖配置）
- `timeout` (optional): 请求超时时间（覆盖配置）

**返回数据结构：**
```json
{
  "status": "success",
  "url": "https://example.com",
  "title": "页面标题",
  "content": {
    "text": "页面文本内容",
    "html": "页面HTML内容"
  },
  "metadata": {
    "description": "...",
    "keywords": "...",
    "og:title": "...",
    ...
  },
  "headings": [
    {"level": 1, "text": "标题1"},
    {"level": 2, "text": "标题2"},
    ...
  ],
  "links": [
    {"url": "...", "text": "...", "title": "..."},
    ...
  ],
  "images": [
    {"src": "...", "alt": "...", "title": "..."},
    ...
  ],
  "tables": [
    {
      "headers": [...],
      "rows": [[...], [...]]
    },
    ...
  ]
}
```

### health_check

检查服务健康状态。

## 依赖

- `aiohttp`: HTTP客户端（已存在）
- `beautifulsoup4`: HTML解析
- `html2text`: HTML转Markdown，保持阅读体验
- `playwright`: JavaScript渲染支持（可选）
- `brotli`: Brotli压缩解码支持

## 使用示例

```python
# 访问静态HTML页面
result = await service.call_tool("fetch_url", {
    "url": "https://example.com"
})

# 访问JavaScript渲染的页面
result = await service.call_tool("fetch_url", {
    "url": "https://example.com",
    "enable_javascript": True
})
```

