#!/usr/bin/env python3
"""
URL访问服务测试脚本
"""

import asyncio
import sys
import os
import json
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.services.url_access_service.service import URLAccessService


async def test_url_access():
    """测试URL访问服务"""
    print("=" * 80)
    print("URL访问服务测试")
    print("=" * 80)
    
    # 创建服务实例
    config = {
        "service_config": {
            "timeout": 30,
            "enable_javascript": False,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "max_content_length": 10485760
        },
        "extract_options": {
            "extract_images": True,
            "extract_tables": True,
            "extract_links": True,
            "extract_metadata": True,
            "extract_headings": True
        }
    }
    
    service = URLAccessService(config=config)
    service.init()
    
    try:
        # 测试URL
        test_url = "https://feicaiclub.feishu.cn/wiki/JQ8bwixhSimnGFkWTUOcl3jZnBf?fromScene=spaceOverview"
        
        print(f"\n正在访问URL: {test_url}")
        print("-" * 80)
        
        # 调用fetch_url工具
        result = await service.call_tool("fetch_url", {
            "url": test_url,
            "enable_javascript": False,  # 启用JavaScript渲染
            "extract_images": True,
            "extract_tables": True,
            "extract_links": True
        })
        
        # 打印结果摘要
        print("\n" + "=" * 80)
        print("结果摘要")
        print("=" * 80)
        print(f"状态: {result.get('status', 'unknown')}")
        print(f"URL: {result.get('url', 'N/A')}")
        print(f"标题: {result.get('title', 'N/A')}")
        
        # 内容摘要
        content = result.get('content', '')
        if content:
            preview = content[:500] + "..." if len(content) > 500 else content
            print(f"\n正文内容预览 ({len(content)} 字符):")
            print("-" * 80)
            print(preview)
        
        # 元数据
        metadata = result.get('metadata', {})
        if metadata:
            print(f"\n元数据 ({len(metadata)} 项):")
            print("-" * 80)
            for key, value in list(metadata.items())[:10]:  # 只显示前10项
                print(f"  {key}: {value[:100] if isinstance(value, str) and len(value) > 100 else value}")
        
        # 标题
        headings = result.get('headings', [])
        if headings:
            print(f"\n标题列表 ({len(headings)} 个):")
            print("-" * 80)
            for heading in headings[:10]:  # 只显示前10个
                print(f"  H{heading['level']}: {heading['text']}")
        
        # 链接
        links = result.get('links', [])
        if links:
            print(f"\n链接列表 ({len(links)} 个，显示前10个):")
            print("-" * 80)
            for link in links[:10]:
                print(f"  {link.get('text', 'N/A')[:50]}: {link.get('url', 'N/A')}")
        
        # 图片
        images = result.get('images', [])
        if images:
            print(f"\n图片列表 ({len(images)} 个，显示前5个):")
            print("-" * 80)
            for img in images[:5]:
                print(f"  {img.get('alt', 'N/A')[:50]}: {img.get('src', 'N/A')}")
        
        # 表格
        tables = result.get('tables', [])
        if tables:
            print(f"\n表格列表 ({len(tables)} 个):")
            print("-" * 80)
            for i, table in enumerate(tables[:3], 1):  # 只显示前3个表格
                print(f"  表格 {i}:")
                if table.get('headers'):
                    print(f"    表头: {table['headers']}")
                rows = table.get('rows', [])
                print(f"    行数: {len(rows)}")
                if rows:
                    print(f"    第一行: {rows[0]}")
        
        # 保存完整结果到文件
        output_file = "url_access_test_result.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n完整结果已保存到: {output_file}")
        
        print("\n" + "=" * 80)
        print("测试完成")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 关闭服务
        await service.close()


if __name__ == "__main__":
    asyncio.run(test_url_access())

