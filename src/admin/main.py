#!/usr/bin/env python3
"""
AI Toys 后台管理系统启动脚本

使用方法:
    python src/admin/main.py                    # 开发模式
    python src/admin/main.py --prod             # 生产模式
    python src/admin/main.py --port 8080        # 指定端口
"""

import argparse
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.admin.app import create_app
from src.admin.config import config


def main():
    """主函数 - Quart应用启动"""
    parser = argparse.ArgumentParser(description='AI Toys 后台管理系统')
    parser.add_argument('--host', default=config.HOST, help='服务器主机地址')
    parser.add_argument('--port', type=int, default=config.PORT, help='服务器端口')
    parser.add_argument('--debug', action='store_true', help='启用调试模式')
    parser.add_argument('--prod', action='store_true', help='生产模式')
    
    args = parser.parse_args()
    
    # 创建应用（初始化会在 @app.before_serving 中完成）
    app = create_app()
    
    # 配置应用
    if args.prod:
        app.config['DEBUG'] = False
        app.config['TESTING'] = False
    else:
        app.config['DEBUG'] = args.debug or config.DEBUG
    
    # 验证配置
    validation = config.validate_config()
    if not validation['valid']:
        print("配置验证失败:")
        for error in validation['errors']:
            print(f"  错误: {error}")
        sys.exit(1)
    
    if validation['warnings']:
        print("配置警告:")
        for warning in validation['warnings']:
            print(f"  警告: {warning}")
    
    # 启动应用（Quart会调用 @app.before_serving 进行初始化）
    print(f"启动AI Toys后台管理系统...")
    print(f"访问地址: http://{args.host}:{args.port}")
    print(f"调试模式: {'开启' if app.config['DEBUG'] else '关闭'}")
    
    try:
        app.run(
            host=args.host,
            port=args.port,
            debug=app.config['DEBUG']
        )
    except KeyboardInterrupt:
        print("\n系统已停止")
    except Exception as e:
        print(f"启动失败: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
