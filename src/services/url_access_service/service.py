#!/usr/bin/env python3
"""
URL访问服务
提供访问URL并返回结构化页面内容的功能
支持静态HTML和JavaScript渲染的页面
"""

import logging
import aiohttp
import asyncio
from typing import Dict, Any, Optional, List, Callable
from functools import wraps
from urllib.parse import urljoin, urlparse
import re

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    logging.warning("beautifulsoup4未安装，URL访问服务将不可用。请运行: pip install beautifulsoup4")

try:
    import html2text
    HTML2TEXT_AVAILABLE = True
except ImportError:
    HTML2TEXT_AVAILABLE = False
    logging.warning("html2text未安装，URL访问服务将不可用。请运行: pip install html2text")

try:
    from playwright.async_api import async_playwright, Browser, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logging.warning("playwright未安装，JavaScript渲染功能将不可用。请运行: pip install playwright && playwright install")

from src.utcp.utcp import UTCPService

logger = logging.getLogger(__name__)


def handle_url_errors(func: Callable) -> Callable:
    """装饰器：统一错误处理"""
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except Exception as e:
            logger.error(f"{func.__name__} 失败: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "message": f"URL访问失败: {str(e)}"
            }
    return wrapper


class URLAccessService(UTCPService):
    """URL访问服务 - 提供访问网页并返回结构化内容的功能"""
    
    def init(self) -> None:
        """插件初始化方法"""
        try:
            self._validate_dependencies()
            self._load_config()
            self._initialize_clients()
        except Exception as e:
            logger.error(f"URL访问服务初始化失败: {e}")
            raise
    
    def _validate_dependencies(self) -> None:
        """验证依赖"""
        if not BS4_AVAILABLE:
            raise ImportError("beautifulsoup4未安装，请运行: pip install beautifulsoup4")
        if not HTML2TEXT_AVAILABLE:
            raise ImportError("html2text未安装，请运行: pip install html2text")
    
    def _load_config(self) -> None:
        """加载配置"""
        self.service_config = self.config.get("service_config", {})
        self.extract_options = self.config.get("extract_options", {})
        
        # 服务配置
        self.timeout = self.service_config.get("timeout", 30)
        self.enable_javascript = self.service_config.get("enable_javascript", False)
        self.user_agent = self.service_config.get("user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        self.max_content_length = self.service_config.get("max_content_length", 10485760)
        
        # Playwright配置
        self.playwright_browser = self.service_config.get("playwright_browser", "chromium")
        self.playwright_headless = self.service_config.get("playwright_headless", True)
        self.playwright_timeout = self.service_config.get("playwright_timeout", 30000)
        
        # 提取选项
        self.extract_images = self.extract_options.get("extract_images", True)
        self.extract_tables = self.extract_options.get("extract_tables", True)
        self.extract_links = self.extract_options.get("extract_links", True)
        self.extract_metadata = self.extract_options.get("extract_metadata", True)
        self.extract_headings = self.extract_options.get("extract_headings", True)
    
    def _initialize_clients(self) -> None:
        """初始化HTTP客户端和Playwright浏览器"""
        # 初始化HTTP会话
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        # 设置请求头，禁用brotli压缩以避免解码问题
        headers = {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate"  # 只接受gzip和deflate，避免brotli
        }
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            headers=headers
        )
        
        # 初始化Playwright（如果启用且可用）
        self.playwright = None
        self.browser = None
        self.browser_type = None
        self._playwright_lock = asyncio.Lock()  # 保护Playwright初始化的锁
        
        if self.enable_javascript and PLAYWRIGHT_AVAILABLE:
            logger.info("Playwright支持已启用，将在首次使用时初始化")
        elif self.enable_javascript and not PLAYWRIGHT_AVAILABLE:
            logger.warning("Playwright未安装，JavaScript渲染功能将不可用")
    
    async def _ensure_playwright(self) -> None:
        """确保Playwright已初始化（线程安全）"""
        # 如果已经初始化，直接返回
        if self.playwright is not None:
            return
        
        # 使用锁保护初始化过程，避免并发时重复初始化
        async with self._playwright_lock:
            # 双重检查：在获取锁后再次检查，避免其他协程已经初始化
            if self.playwright is not None:
                return
            
            if not PLAYWRIGHT_AVAILABLE:
                raise ImportError("Playwright未安装，请运行: pip install playwright && playwright install")
            
            self.playwright = await async_playwright().start()
            
            # 根据配置选择浏览器类型
            if self.playwright_browser == "firefox":
                self.browser_type = self.playwright.firefox
            elif self.playwright_browser == "webkit":
                self.browser_type = self.playwright.webkit
            else:
                self.browser_type = self.playwright.chromium
            
            # 启动浏览器
            self.browser = await self.browser_type.launch(headless=self.playwright_headless)
            logger.info(f"Playwright浏览器已启动: {self.playwright_browser}")
    
    @property
    def name(self) -> str:
        """服务名称"""
        return "url_access_service"
    
    @property
    def description(self) -> str:
        """服务描述"""
        return "提供访问URL并返回结构化页面内容的功能，支持静态HTML和JavaScript渲染的页面"
    
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
        """返回可用工具列表"""
        return [
            # URL访问工具
            self._create_tool_definition(
                "fetch_url", "访问URL并返回结构化的页面内容数据",
                {
                    "url": {
                        "type": "string",
                        "description": "要访问的URL地址"
                    },
                    "enable_javascript": {
                        "type": "boolean",
                        "description": "是否启用JavaScript渲染（覆盖配置）",
                        "default": False
                    },
                    "extract_images": {
                        "type": "boolean",
                        "description": "是否提取图片（覆盖配置）",
                        "default": True
                    },
                    "extract_tables": {
                        "type": "boolean",
                        "description": "是否提取表格（覆盖配置）",
                        "default": True
                    },
                    "extract_links": {
                        "type": "boolean",
                        "description": "是否提取链接（覆盖配置）",
                        "default": True
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "请求超时时间（秒，覆盖配置）",
                        "minimum": 5,
                        "maximum": 300
                    }
                },
                ["url"]
            )
        ]
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """执行URL访问服务工具"""
        tool_handlers = {
            "fetch_url": lambda: self._fetch_url(arguments)
        }
        
        try:
            if tool_name not in tool_handlers:
                raise ValueError(f"未知的URL访问工具: {tool_name}")
            
            return await tool_handlers[tool_name]()
        except Exception as e:
            logger.error(f"执行工具 '{tool_name}' 时出错: {e}")
            return {
                "status": "error",
                "error": str(e),
                "message": f"URL访问操作失败: {str(e)}"
            }
    
    @handle_url_errors
    async def _fetch_url(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """访问URL并提取结构化内容"""
        url = arguments.get("url")
        if not url:
            raise ValueError("URL不能为空")
        
        # 验证URL格式
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"无效的URL格式: {url}")
        
        # 获取参数（覆盖配置）
        enable_javascript = arguments.get("enable_javascript", self.enable_javascript)
        extract_images = arguments.get("extract_images", self.extract_images)
        extract_tables = arguments.get("extract_tables", self.extract_tables)
        extract_links = arguments.get("extract_links", self.extract_links)
        timeout = arguments.get("timeout", self.timeout)
        
        logger.info(f"访问URL: {url}, JavaScript={enable_javascript}")
        
        # 获取页面HTML
        html_content = await self._get_page_html(url, enable_javascript, timeout)
        
        if not html_content:
            raise Exception("无法获取页面内容")
        
        # 检查内容长度
        if len(html_content) > self.max_content_length:
            logger.warning(f"页面内容超过最大长度限制: {len(html_content)} > {self.max_content_length}")
            html_content = html_content[:self.max_content_length]
        
        # 解析HTML并提取结构化数据
        result = self._extract_structured_data(html_content, url, {
            "extract_images": extract_images,
            "extract_tables": extract_tables,
            "extract_links": extract_links,
            "extract_metadata": self.extract_metadata,
            "extract_headings": self.extract_headings
        })
        
        result["url"] = url
        result["status"] = "success"
        
        return result
    
    async def _get_page_html(self, url: str, enable_javascript: bool, timeout: int) -> Optional[str]:
        """获取页面HTML内容"""
        if enable_javascript and PLAYWRIGHT_AVAILABLE:
            return await self._get_page_html_with_playwright(url, timeout)
        else:
            return await self._get_page_html_with_http(url, timeout)
    
    async def _get_page_html_with_http(self, url: str, timeout: int) -> Optional[str]:
        """使用HTTP请求获取页面HTML"""
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    content = await response.text()
                    return content
                else:
                    logger.error(f"HTTP请求失败: {response.status}")
                    raise Exception(f"HTTP请求失败: {response.status}")
        except Exception as e:
            logger.error(f"HTTP请求异常: {e}")
            raise
    
    async def _get_page_html_with_playwright(self, url: str, timeout: int) -> Optional[str]:
        """使用Playwright获取页面HTML（支持JavaScript渲染）"""
        await self._ensure_playwright()
        
        if not self.browser:
            raise Exception("Playwright浏览器未初始化")
        
        page = None
        try:
            page = await self.browser.new_page()
            
            # 设置页面超时时间
            page.set_default_timeout(timeout * 1000)
            
            # 尝试多种等待策略，从宽松到严格
            wait_strategies = ["load", "domcontentloaded", "networkidle"]
            last_error = None
            
            for wait_strategy in wait_strategies:
                try:
                    logger.debug(f"尝试使用等待策略: {wait_strategy}")
                    await page.goto(url, wait_until=wait_strategy, timeout=timeout * 1000)
                    # 成功加载后，等待一小段时间确保JavaScript执行完成
                    await page.wait_for_timeout(1000)
                    html_content = await page.content()
                    logger.info(f"使用等待策略 '{wait_strategy}' 成功获取页面内容")
                    return html_content
                except Exception as e:
                    last_error = e
                    logger.warning(f"等待策略 '{wait_strategy}' 失败: {e}")
                    # 如果不是最后一个策略，继续尝试下一个
                    if wait_strategy != wait_strategies[-1]:
                        continue
                    # 如果是最后一个策略，抛出异常
                    raise
            
            # 如果所有策略都失败，抛出最后一个错误
            if last_error:
                raise last_error
                
        except Exception as e:
            logger.error(f"Playwright获取页面失败: {e}")
            raise
        finally:
            if page:
                await page.close()
    
    def _extract_structured_data(self, html_content: str, base_url: str, options: Dict[str, bool]) -> Dict[str, Any]:
        """从HTML中提取结构化数据"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        result = {
            "title": self._extract_title(soup),
            "content": self._extract_content(soup),
        }
        
        if options.get("extract_metadata", True):
            result["metadata"] = self._extract_metadata(soup)
        
        if options.get("extract_headings", True):
            result["headings"] = self._extract_headings(soup)
        
        if options.get("extract_links", True):
            result["links"] = self._extract_links(soup, base_url)
        
        if options.get("extract_images", True):
            result["images"] = self._extract_images(soup, base_url)
        
        if options.get("extract_tables", True):
            result["tables"] = self._extract_tables(soup)
        
        return result
    
    def _extract_title(self, soup: BeautifulSoup) -> str:
        """提取页面标题"""
        title_tag = soup.find('title')
        if title_tag:
            return title_tag.get_text(strip=True)
        
        # 如果没有title标签，尝试使用h1
        h1_tag = soup.find('h1')
        if h1_tag:
            return h1_tag.get_text(strip=True)
        
        return ""
    
    def _extract_content(self, soup: BeautifulSoup) -> str:
        """提取页面正文内容（使用html2text转换为Markdown格式）"""
        # 获取body内容
        body = soup.find('body')
        if not body:
            body = soup
        
        html_content = str(body)
        
        # 使用html2text提取内容（Markdown格式）
        h = html2text.HTML2Text()
        h.ignore_links = False  # 保留链接
        h.ignore_images = False  # 保留图片
        h.body_width = 0  # 不自动换行，保持原始格式
        h.unicode_snob = True  # 使用Unicode字符
        h.escape_snob = True  # 转义特殊字符
        h.skip_internal_links = False  # 保留内部链接
        h.inline_links = True  # 内联链接格式
        h.wrap_links = False  # 不换行链接
        
        text_content = h.handle(html_content)
        # 清理多余空白行（保留最多2个连续换行）
        text_content = re.sub(r'\n{3,}', '\n\n', text_content)
        text_content = text_content.strip()
        
        return text_content
    
    def _extract_metadata(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """提取元数据"""
        metadata = {}
        
        # 提取meta标签
        meta_tags = soup.find_all('meta')
        for meta in meta_tags:
            name = meta.get('name') or meta.get('property') or meta.get('itemprop')
            content = meta.get('content')
            
            if name and content:
                metadata[name] = content
        
        return metadata
    
    def _extract_headings(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """提取标题（h1-h6）"""
        headings = []
        heading_tags = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        
        for tag in heading_tags:
            level = int(tag.name[1])  # 提取数字部分
            text = tag.get_text(strip=True)
            if text:
                headings.append({
                    "level": level,
                    "text": text
                })
        
        return headings
    
    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
        """提取链接"""
        links = []
        link_tags = soup.find_all('a', href=True)
        
        for tag in link_tags:
            href = tag.get('href')
            text = tag.get_text(strip=True)
            title = tag.get('title', '')
            
            # 转换为绝对URL
            absolute_url = urljoin(base_url, href)
            
            links.append({
                "url": absolute_url,
                "text": text,
                "title": title
            })
        
        return links
    
    def _extract_images(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
        """提取图片"""
        images = []
        img_tags = soup.find_all('img')
        
        for tag in img_tags:
            src = tag.get('src') or tag.get('data-src') or tag.get('data-lazy-src')
            if not src:
                continue
            
            alt = tag.get('alt', '')
            title = tag.get('title', '')
            
            # 转换为绝对URL
            absolute_url = urljoin(base_url, src)
            
            images.append({
                "src": absolute_url,
                "alt": alt,
                "title": title
            })
        
        return images
    
    def _extract_tables(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """提取表格数据"""
        tables = []
        table_tags = soup.find_all('table')
        
        for table in table_tags:
            table_data = {
                "headers": [],
                "rows": []
            }
            
            # 提取表头
            thead = table.find('thead')
            if thead:
                header_row = thead.find('tr')
                if header_row:
                    headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
                    table_data["headers"] = headers
            
            # 提取表格行
            tbody = table.find('tbody') or table
            rows = tbody.find_all('tr')
            
            for row in rows:
                # 跳过表头行
                if row.find_parent('thead'):
                    continue
                
                cells = [td.get_text(strip=True) for td in row.find_all(['td', 'th'])]
                if cells:
                    table_data["rows"].append(cells)
            
            if table_data["headers"] or table_data["rows"]:
                tables.append(table_data)
        
        return tables
    
    async def close(self) -> None:
        """关闭服务"""
        # 关闭HTTP会话
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("HTTP会话已关闭")
        
        # 关闭Playwright浏览器
        if self.browser:
            await self.browser.close()
            logger.info("Playwright浏览器已关闭")
        
        if self.playwright:
            await self.playwright.stop()
            logger.info("Playwright已停止")
        
        logger.info("URL访问服务已关闭")
    
    def __del__(self):
        """析构函数，确保资源被释放"""
        try:
            if hasattr(self, 'session') and self.session and not self.session.closed:
                logger.warning("URLAccessService会话未正确关闭，建议显式调用close()方法")
        except Exception as e:
            logger.debug(f"URLAccessService析构时检查session失败: {e}")

