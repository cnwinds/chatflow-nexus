# AI Toys 后台管理系统

基于AI指标表的后台管理系统，提供性能监控、数据分析和可视化功能。

## 功能特性

### 🔐 用户认证
- 系统用户登录认证
- 基于用户表的权限控制
- 会话管理和安全控制

### 📊 数据可视化
- AI模型性能趋势图（折线图）
- 按提供商+模型分组统计
- 响应时间、调用次数、费用统计
- 交互式图表展示

### 📈 数据分析
- 时间范围筛选（7天、14天、1个月、自定义）
- 提供商和模型过滤
- 实时数据统计
- 详细数据表格

### 🎨 用户界面
- 现代化响应式设计
- Bootstrap 5 + Chart.js
- 移动端友好
- 直观的操作界面

## 系统架构

```
src/admin/
├── __init__.py          # 模块初始化
├── app.py              # Flask应用主文件
├── api.py              # RESTful API接口
├── auth.py             # 用户认证模块
├── models.py           # 数据模型和服务
├── config.py           # 系统配置
├── run.py              # 启动脚本
├── templates/          # HTML模板
│   └── admin/
│       ├── index.html      # 首页
│       ├── login.html      # 登录页
│       ├── dashboard.html   # 仪表板
│       ├── 404.html        # 404错误页
│       └── 500.html        # 500错误页
└── README.md           # 说明文档
```

## 快速开始

### 1. 环境要求

- Python 3.8+
- MySQL 5.7+
- Flask 2.0+

### 2. 安装依赖

```bash
pip install flask flask-cors pymysql
```

### 3. 配置数据库

确保数据库中存在以下表：
- `users` - 用户表（需要系统用户）
- `ai_metrics` - AI指标表

### 4. 创建系统用户

```sql
INSERT INTO users (login_name, password_hash, user_name, user_type, status) 
VALUES ('admin', SHA2('admin123', 256), '系统管理员', 1, 1);
```

### 5. 启动系统

```bash
# 开发模式
python src/admin/run.py

# 生产模式
python src/admin/run.py --prod

# 指定端口
python src/admin/run.py --port 8080
```

### 6. 访问系统

打开浏览器访问：http://localhost:5000

## API接口

### 认证接口

- `POST /admin/login` - 用户登录
- `POST /admin/logout` - 用户登出
- `GET /admin/user/info` - 获取用户信息

### 数据接口

- `GET /admin/metrics/summary` - 获取汇总数据
- `GET /admin/metrics/timeseries` - 获取时间序列数据
- `GET /admin/metrics/providers` - 获取提供商列表
- `GET /admin/metrics/models` - 获取模型列表

### 页面接口

- `GET /admin/` - 登录页面
- `GET /admin/dashboard` - 仪表板页面

## 配置说明

### 环境变量

```bash
# 应用配置
ADMIN_SECRET_KEY=your-secret-key
ADMIN_DEBUG=True
ADMIN_HOST=0.0.0.0
ADMIN_PORT=5000

# 数据库配置
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your-password
DB_NAME=ai_toys

# 会话配置
SESSION_TIMEOUT=3600
```

### 配置文件

系统配置位于 `src/admin/config.py`，支持以下配置：

- 数据库连接配置
- 安全配置
- 会话超时设置
- 图表颜色配置
- 日志配置

## 使用说明

### 1. 登录系统

1. 访问系统首页
2. 使用系统用户账号登录
3. 进入仪表板界面

### 2. 查看性能数据

1. 选择时间范围（7天、14天、1个月或自定义）
2. 选择提供商和模型进行过滤
3. 点击查询按钮获取数据
4. 查看图表和统计信息

### 3. 数据分析

- **统计卡片**：显示总调用次数、平均响应时间、总费用、总Token数
- **趋势图表**：显示不同提供商+模型的性能趋势
- **数据表格**：显示详细的统计数据

## 开发指南

### 添加新的数据源

1. 在 `models.py` 中添加新的数据模型
2. 在 `api.py` 中添加对应的API接口
3. 在前端模板中添加展示逻辑

### 自定义图表

1. 修改 `dashboard.html` 中的图表配置
2. 调整 `config.py` 中的颜色配置
3. 更新数据处理逻辑

### 扩展认证功能

1. 修改 `auth.py` 中的认证逻辑
2. 添加新的权限控制
3. 更新用户界面

## 故障排除

### 常见问题

1. **数据库连接失败**
   - 检查数据库配置
   - 确认数据库服务运行正常
   - 验证用户权限

2. **登录失败**
   - 确认用户类型为系统用户（user_type=1）
   - 检查密码哈希算法
   - 验证用户状态

3. **图表不显示**
   - 检查Chart.js库加载
   - 验证数据格式
   - 查看浏览器控制台错误

### 日志查看

系统日志位于 `logs/admin.log`，包含详细的运行信息和错误日志。

## 技术栈

- **后端**: Flask, SQLAlchemy, PyMySQL
- **前端**: Bootstrap 5, Chart.js, Font Awesome
- **数据库**: MySQL
- **认证**: Session-based Authentication
- **可视化**: Chart.js

## 许可证

MIT License
