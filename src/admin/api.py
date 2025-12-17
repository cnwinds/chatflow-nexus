"""
后台管理系统API接口

提供RESTful API接口用于前端调用
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from quart import Blueprint, request, jsonify, render_template
import json
import logging

from .simple_auth import create_auth_manager
from .simple_models import create_metrics_service, create_agent_service, create_user_service, create_device_service, create_agent_template_service, create_device_binding_service
from src.common.exceptions import AuthenticationError, ValidationError

# 获取日志记录器
logger = logging.getLogger(__name__)

# 创建蓝图
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# 全局变量，将在初始化时设置
auth_manager = None
metrics_service = None
agent_service = None
user_service = None
device_service = None
agent_template_service = None
device_binding_service = None


def init_services(db_manager):
    """初始化服务 - 在main函数初始化完成后调用"""
    global auth_manager, metrics_service, agent_service, user_service, device_service, agent_template_service, device_binding_service
    
    auth_manager = create_auth_manager(db_manager)
    metrics_service = create_metrics_service(db_manager)
    agent_service = create_agent_service(db_manager)
    user_service = create_user_service(db_manager)
    device_service = create_device_service(db_manager)
    agent_template_service = create_agent_template_service(db_manager)
    device_binding_service = create_device_binding_service(db_manager)


def require_auth(f):
    """延迟认证装饰器 - 在运行时获取auth_manager"""
    from functools import wraps
    
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        if auth_manager is None:
            return jsonify({'error': '认证服务未初始化', 'code': 500}), 500
        if not await auth_manager.is_authenticated():
            return jsonify({'error': '需要登录', 'code': 401}), 401
        return await f(*args, **kwargs)
    return decorated_function


@admin_bp.route('/login', methods=['POST'])
async def login():
    """用户登录接口"""
    try:
        data = await request.get_json()
        login_name = data.get('login_name')
        password = data.get('password')
        
        if not login_name or not password:
            return jsonify({'error': '用户名和密码不能为空'}), 400
        
        result = await auth_manager.login(login_name, password)
        return jsonify(result)
        
    except AuthenticationError as e:
        return jsonify({'error': str(e)}), 401
    except Exception as e:
        return jsonify({'error': f'登录失败: {str(e)}'}), 500


@admin_bp.route('/logout', methods=['POST'])
@require_auth
async def logout():
    """用户登出接口"""
    try:
        result = await auth_manager.logout()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'登出失败: {str(e)}'}), 500


@admin_bp.route('/user/info', methods=['GET'])
@require_auth
async def get_user_info():
    """获取当前用户信息"""
    try:
        user = await auth_manager.get_current_user()
        return jsonify({'success': True, 'user': user})
    except Exception as e:
        return jsonify({'error': f'获取用户信息失败: {str(e)}'}), 500


@admin_bp.route('/metrics/summary', methods=['GET'])
@require_auth
async def get_metrics_summary():
    """获取指标汇总数据"""
    try:
        # 获取查询参数
        days = int(request.args.get('days', 7))
        provider = request.args.get('provider')
        model_name = request.args.get('model_name')
        
        logger.info(f"开始获取指标汇总，天数: {days}, 提供商: {provider}, 模型: {model_name}")
        
        # 计算时间范围
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # 获取汇总数据
        summary_data = await metrics_service.get_provider_model_summary(start_date, end_date)
        
        # 如果指定了提供商或模型，进行过滤
        if provider:
            summary_data = [item for item in summary_data if item.provider == provider]
        if model_name:
            summary_data = [item for item in summary_data if item.model_name == model_name]
        
        # 转换为字典格式
        result = []
        for item in summary_data:
            logger.debug(f"处理数据项: provider={item.provider}, model={item.model_name}, tokens={item.total_tokens} (类型: {type(item.total_tokens)})")
            result.append({
                'provider': item.provider,
                'model_name': item.model_name,
                'total_calls': item.total_calls,
                'avg_total_time': round(item.avg_total_time, 2),
                'p95_total_time': round(item.p95_total_time, 2),
                'max_total_time': round(item.max_total_time, 2),
                'min_total_time': round(item.min_total_time, 2),
                'total_cost': round(item.total_cost, 6),
                'total_tokens': item.total_tokens
            })
        
        logger.info(f"成功获取指标汇总数据: {len(result)} 条记录")
        return jsonify({
            'success': True,
            'data': result,
            'time_range': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'days': days
            }
        })
        
    except Exception as e:
        logger.error(f"获取汇总数据失败: {str(e)}", exc_info=True)
        return jsonify({'error': f'获取汇总数据失败: {str(e)}'}), 500


@admin_bp.route('/metrics/timeseries', methods=['GET'])
@require_auth
async def get_time_series_data():
    """获取时间序列数据用于图表展示"""
    try:
        # 获取查询参数
        days = int(request.args.get('days', 7))
        provider = request.args.get('provider')
        model_name = request.args.get('model_name')
        group_by = request.args.get('group_by', 'day')
        
        logger.info(f"开始获取时间序列数据，天数: {days}, 提供商: {provider}, 模型: {model_name}, 分组: {group_by}")
        
        # 计算时间范围
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # 获取时间序列数据
        time_series_data = await metrics_service.get_time_series_data(
            start_date, end_date, group_by
        )
        
        # 如果指定了提供商或模型，进行过滤
        if provider:
            time_series_data = [item for item in time_series_data if item.provider == provider]
        if model_name:
            time_series_data = [item for item in time_series_data if item.model_name == model_name]
        
        # 按日期和提供商+模型分组
        chart_data = {}
        for item in time_series_data:
            key = f"{item.provider}+{item.model_name}"
            if key not in chart_data:
                chart_data[key] = {
                    'name': key,
                    'data': []
                }
            
            chart_data[key]['data'].append({
                'date': item.date,
                'avg_total_time': round(item.avg_total_time, 2),
                'p95_total_time': round(item.p95_total_time, 2),
                'max_total_time': round(item.max_total_time, 2),
                'min_total_time': round(item.min_total_time, 2),
                'total_calls': item.total_calls,
                'total_cost': round(item.total_cost, 6)
            })
        
        # 转换为列表格式
        result = list(chart_data.values())
        
        logger.info(f"成功获取时间序列数据: {len(result)} 个数据系列")
        return jsonify({
            'success': True,
            'data': result,
            'time_range': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'days': days
            }
        })
        
    except Exception as e:
        logger.error(f"获取时间序列数据失败: {str(e)}", exc_info=True)
        return jsonify({'error': f'获取时间序列数据失败: {str(e)}'}), 500


@admin_bp.route('/metrics/providers', methods=['GET'])
@require_auth
async def get_providers():
    """获取可用的提供商列表"""
    try:
        logger.info("开始获取提供商列表")
        providers = await metrics_service.get_available_providers()
        logger.info(f"成功获取提供商列表: {providers}")
        return jsonify({'success': True, 'data': providers})
    except Exception as e:
        logger.error(f"获取提供商列表失败: {str(e)}", exc_info=True)
        return jsonify({'error': f'获取提供商列表失败: {str(e)}'}), 500


@admin_bp.route('/metrics/models', methods=['GET'])
@require_auth
async def get_models():
    """获取可用的模型列表"""
    try:
        provider = request.args.get('provider')
        logger.info(f"开始获取模型列表，提供商: {provider}")
        models = await metrics_service.get_available_models(provider)
        logger.info(f"成功获取模型列表: {models}")
        return jsonify({'success': True, 'data': models})
    except Exception as e:
        logger.error(f"获取模型列表失败: {str(e)}", exc_info=True)
        return jsonify({'error': f'获取模型列表失败: {str(e)}'}), 500


@admin_bp.route('/metrics/daily-details', methods=['GET'])
@require_auth
async def get_daily_details():
    """获取按天统计的详细数据"""
    try:
        # 获取查询参数
        days = int(request.args.get('days', 7))
        provider = request.args.get('provider')
        model_name = request.args.get('model_name')
        
        logger.info(f"开始获取按天统计详细数据，天数: {days}, 提供商: {provider}, 模型: {model_name}")
        
        # 计算时间范围
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # 获取时间序列数据
        time_series_data = await metrics_service.get_time_series_data(
            start_date, end_date, 'day'
        )
        
        # 如果指定了提供商或模型，进行过滤
        if provider:
            time_series_data = [item for item in time_series_data if item.provider == provider]
        if model_name:
            time_series_data = [item for item in time_series_data if item.model_name == model_name]
        
        # 转换为字典格式，按日期分组
        result = []
        for item in time_series_data:
            result.append({
                'date': item.date,
                'provider': item.provider,
                'model_name': item.model_name,
                'total_calls': item.total_calls,
                'avg_total_time': round(item.avg_total_time, 2),
                'p95_total_time': round(item.p95_total_time, 2),
                'max_total_time': round(item.max_total_time, 2),
                'min_total_time': round(item.min_total_time, 2),
                'total_cost': round(item.total_cost, 6)
            })
        
        # 按日期逆序排序（最新日期在前）
        result.sort(key=lambda x: x['date'], reverse=True)
        
        logger.info(f"成功获取按天统计详细数据: {len(result)} 条记录")
        return jsonify({
            'success': True,
            'data': result,
            'time_range': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'days': days
            }
        })
        
    except Exception as e:
        logger.error(f"获取按天统计详细数据失败: {str(e)}", exc_info=True)
        return jsonify({'error': f'获取按天统计详细数据失败: {str(e)}'}), 500


@admin_bp.route('/dashboard', methods=['GET'])
@require_auth
async def dashboard():
    """后台管理仪表板页面"""
    return await render_template('admin/dashboard.html')


@admin_bp.route('/agents', methods=['GET'])
@require_auth
async def agents_page():
    """Agent管理页面"""
    return await render_template('admin/agents.html')


@admin_bp.route('/api/agents', methods=['GET'])
@require_auth
async def get_agents():
    """获取所有agents列表"""
    try:
        logger.info("开始获取agents列表")
        
        if agent_service is None:
            return jsonify({'error': 'Agent服务未初始化', 'code': 500}), 500
        
        agents = await agent_service.get_all_agents()
        
        # 转换为字典格式
        result = []
        for agent in agents:
            result.append({
                'id': agent.id,
                'name': agent.name,
                'description': agent.description,
                'avatar': agent.avatar,
                'gender': agent.gender,
                'user_id': agent.user_id,
                'device_id': agent.device_id,
                'template_id': agent.template_id,
                'device_type': agent.device_type,
                'status': agent.status,
                'created_at': agent.created_at.isoformat() if agent.created_at else None,
                'updated_at': agent.updated_at.isoformat() if agent.updated_at else None,
                'user_name': agent.user_name,
                'device_uuid': agent.device_uuid,
                'device_name': agent.device_name,
                'agent_config': agent.agent_config,
                'module_params': agent.module_params,
                'memory_data': agent.memory_data
            })
        
        logger.info(f"成功获取agents列表: {len(result)} 条记录")
        return jsonify({'success': True, 'data': result})
        
    except Exception as e:
        logger.error(f"获取agents列表失败: {str(e)}", exc_info=True)
        return jsonify({'error': f'获取agents列表失败: {str(e)}'}), 500


@admin_bp.route('/api/agents/<int:agent_id>', methods=['GET'])
@require_auth
async def get_agent(agent_id):
    """获取单个agent详情"""
    try:
        logger.info(f"开始获取agent详情: {agent_id}")
        
        if agent_service is None:
            return jsonify({'error': 'Agent服务未初始化', 'code': 500}), 500
        
        agent = await agent_service.get_agent_by_id(agent_id)
        
        if not agent:
            return jsonify({'error': 'Agent不存在', 'code': 404}), 404
        
        result = {
            'id': agent.id,
            'name': agent.name,
            'description': agent.description,
            'avatar': agent.avatar,
            'gender': agent.gender,
            'user_id': agent.user_id,
            'device_id': agent.device_id,
            'template_id': agent.template_id,
            'device_type': agent.device_type,
            'status': agent.status,
            'created_at': agent.created_at.isoformat() if agent.created_at else None,
            'updated_at': agent.updated_at.isoformat() if agent.updated_at else None,
            'user_name': agent.user_name,
            'device_uuid': agent.device_uuid,
            'device_name': agent.device_name,
            'agent_config': agent.agent_config,
            'module_params': agent.module_params,
            'memory_data': agent.memory_data
        }
        
        logger.info(f"成功获取agent详情: {agent_id}")
        return jsonify({'success': True, 'data': result})
        
    except Exception as e:
        logger.error(f"获取agent详情失败: {str(e)}", exc_info=True)
        return jsonify({'error': f'获取agent详情失败: {str(e)}'}), 500


@admin_bp.route('/api/agents/<int:agent_id>/config', methods=['PUT'])
@require_auth
async def update_agent_config(agent_id):
    """更新agent配置"""
    try:
        logger.info(f"开始更新agent配置: {agent_id}")
        
        if agent_service is None:
            return jsonify({'error': 'Agent服务未初始化', 'code': 500}), 500
        
        data = await request.get_json()
        if not data:
            return jsonify({'error': '请求数据不能为空'}), 400
        
        config_json = data.get('agent_config')
        if config_json is None:
            return jsonify({'error': 'agent_config字段不能为空'}), 400
        
        # 验证JSON格式
        try:
            if isinstance(config_json, str):
                config_json = json.loads(config_json)
            json.dumps(config_json)  # 验证JSON是否有效
        except (json.JSONDecodeError, TypeError) as e:
            return jsonify({'error': f'JSON格式无效: {str(e)}'}), 400
        
        # 更新配置
        success = await agent_service.update_agent_config(agent_id, config_json)
        
        if not success:
            return jsonify({'error': 'Agent不存在或更新失败'}), 404
        
        logger.info(f"成功更新agent配置: {agent_id}")
        return jsonify({'success': True, 'message': '配置更新成功'})
        
    except Exception as e:
        logger.error(f"更新agent配置失败: {str(e)}", exc_info=True)
        return jsonify({'error': f'更新agent配置失败: {str(e)}'}), 500


@admin_bp.route('/api/agents/<int:agent_id>/memory-data', methods=['PUT'])
@require_auth
async def update_agent_memory_data(agent_id):
    """更新agent记忆数据"""
    try:
        logger.info(f"开始更新agent记忆数据: {agent_id}")
        
        if agent_service is None:
            return jsonify({'error': 'Agent服务未初始化', 'code': 500}), 500
        
        data = await request.get_json()
        if not data:
            return jsonify({'error': '请求数据不能为空'}), 400
        
        memory_data_json = data.get('memory_data')
        if memory_data_json is None:
            return jsonify({'error': 'memory_data字段不能为空'}), 400
        
        # 验证JSON格式
        try:
            if isinstance(memory_data_json, str):
                memory_data_json = json.loads(memory_data_json)
            json.dumps(memory_data_json)  # 验证JSON是否有效
        except (json.JSONDecodeError, TypeError) as e:
            return jsonify({'error': f'JSON格式无效: {str(e)}'}), 400
        
        # 更新记忆数据
        success = await agent_service.update_agent_memory_data(agent_id, memory_data_json)
        
        if not success:
            return jsonify({'error': 'Agent不存在或更新失败'}), 404
        
        logger.info(f"成功更新agent记忆数据: {agent_id}")
        return jsonify({'success': True, 'message': '记忆数据更新成功'})
        
    except Exception as e:
        logger.error(f"更新agent记忆数据失败: {str(e)}", exc_info=True)
        return jsonify({'error': f'更新agent记忆数据失败: {str(e)}'}), 500


@admin_bp.route('/api/agents/<int:agent_id>/basic-info', methods=['PUT'])
@require_auth
async def update_agent_basic_info(agent_id):
    """更新agent基本信息"""
    try:
        logger.info(f"开始更新agent基本信息: {agent_id}")
        
        if agent_service is None:
            return jsonify({'error': 'Agent服务未初始化', 'code': 500}), 500
        
        data = await request.get_json()
        if not data:
            return jsonify({'error': '请求数据不能为空'}), 400
        
        name = data.get('name')
        description = data.get('description')
        avatar = data.get('avatar')
        gender = data.get('gender')
        
        # 验证参数
        if name is None and description is None and avatar is None and gender is None:
            return jsonify({'error': '至少需要提供一个更新字段'}), 400
        
        if name is not None and not name.strip():
            return jsonify({'error': 'Agent名称不能为空'}), 400
        
        if gender is not None and gender not in [0, 1]:
            return jsonify({'error': '性别值无效，只能是0或1'}), 400
        
        # 更新基本信息
        success = await agent_service.update_agent_basic_info(
            agent_id=agent_id,
            name=name,
            description=description,
            avatar=avatar,
            gender=gender
        )
        
        if not success:
            return jsonify({'error': 'Agent不存在或更新失败'}), 404
        
        logger.info(f"成功更新agent基本信息: {agent_id}")
        return jsonify({'success': True, 'message': '基本信息更新成功'})
        
    except Exception as e:
        logger.error(f"更新agent基本信息失败: {str(e)}", exc_info=True)
        return jsonify({'error': f'更新agent基本信息失败: {str(e)}'}), 500


@admin_bp.route('/bind-device', methods=['GET'])
@require_auth
async def bind_device_page():
    """设备绑定页面"""
    return await render_template('admin/bind_device.html')


@admin_bp.route('/users-page', methods=['GET'])
@require_auth
async def users_page():
    """用户管理页面"""
    return await render_template('admin/users.html')


@admin_bp.route('/api/users', methods=['GET'])
@require_auth
async def get_users():
    """获取用户列表"""
    try:
        logger.info("开始获取用户列表")
        
        if user_service is None:
            return jsonify({'error': '用户服务未初始化', 'code': 500}), 500
        
        # 获取查询参数
        user_name = request.args.get('user_name')
        mobile = request.args.get('mobile')
        login_name = request.args.get('login_name')
        user_type = request.args.get('user_type', type=int)
        status = request.args.get('status', type=int)
        
        # 如果有过滤条件，使用过滤查询
        if any([user_name, mobile, login_name, user_type is not None, status is not None]):
            users = await user_service.get_users_with_filter(
                user_name=user_name,
                mobile=mobile,
                login_name=login_name,
                user_type=user_type,
                status=status
            )
        else:
            users = await user_service.get_all_users()
        
        # 转换为字典格式
        result = []
        for user in users:
            result.append({
                'id': user.id,
                'login_name': user.login_name,
                'user_name': user.user_name,
                'mobile': user.mobile,
                'avatar': user.avatar,
                'gender': user.gender,
                'user_type': user.user_type,
                'status': user.status,
                'created_at': user.created_at.isoformat() if user.created_at else None,
                'updated_at': user.updated_at.isoformat() if user.updated_at else None
            })
        
        logger.info(f"成功获取用户列表: {len(result)} 条记录")
        return jsonify({'success': True, 'data': result})
        
    except Exception as e:
        logger.error(f"获取用户列表失败: {str(e)}", exc_info=True)
        return jsonify({'error': f'获取用户列表失败: {str(e)}'}), 500


@admin_bp.route('/api/users/<int:user_id>', methods=['GET'])
@require_auth
async def get_user(user_id):
    """获取单个用户详情"""
    try:
        logger.info(f"开始获取用户详情: {user_id}")
        
        if user_service is None:
            return jsonify({'error': '用户服务未初始化', 'code': 500}), 500
        
        # 先获取所有用户，然后过滤
        users = await user_service.get_all_users()
        user = next((u for u in users if u.id == user_id), None)
        
        if not user:
            return jsonify({'error': '用户不存在', 'code': 404}), 404
        
        result = {
            'id': user.id,
            'login_name': user.login_name,
            'user_name': user.user_name,
            'mobile': user.mobile,
            'avatar': user.avatar,
            'gender': user.gender,
            'user_type': user.user_type,
            'status': user.status,
            'created_at': user.created_at.isoformat() if user.created_at else None,
            'updated_at': user.updated_at.isoformat() if user.updated_at else None
        }
        
        logger.info(f"成功获取用户详情: {user_id}")
        return jsonify({'success': True, 'data': result})
        
    except Exception as e:
        logger.error(f"获取用户详情失败: {str(e)}", exc_info=True)
        return jsonify({'error': f'获取用户详情失败: {str(e)}'}), 500


@admin_bp.route('/api/users/<int:user_id>', methods=['PUT'])
@require_auth
async def update_user(user_id):
    """更新用户信息"""
    try:
        logger.info(f"开始更新用户信息: {user_id}")
        
        if user_service is None:
            return jsonify({'error': '用户服务未初始化', 'code': 500}), 500
        
        data = await request.get_json()
        if not data:
            return jsonify({'error': '请求数据不能为空'}), 400
        
        login_name = data.get('login_name')
        password = data.get('password')
        status = data.get('status')
        
        # 验证参数
        if login_name is None and password is None and status is None:
            return jsonify({'error': '至少需要提供一个更新字段'}), 400
        
        if login_name is not None and not login_name.strip():
            return jsonify({'error': '登录名不能为空'}), 400
        
        if password is not None and len(password) < 6:
            return jsonify({'error': '密码长度不能少于6位'}), 400
        
        if status is not None and status not in [0, 1]:
            return jsonify({'error': '状态值无效，只能是0或1'}), 400
        
        # 更新用户信息
        success = await user_service.update_user(
            user_id=user_id,
            login_name=login_name,
            password=password,
            status=status
        )
        
        if not success:
            return jsonify({'error': '用户不存在或更新失败'}), 404
        
        logger.info(f"成功更新用户信息: {user_id}")
        return jsonify({'success': True, 'message': '用户信息更新成功'})
        
    except Exception as e:
        logger.error(f"更新用户信息失败: {str(e)}", exc_info=True)
        return jsonify({'error': f'更新用户信息失败: {str(e)}'}), 500


@admin_bp.route('/devices-page', methods=['GET'])
@require_auth
async def devices_page():
    """设备管理页面"""
    return await render_template('admin/devices.html')


@admin_bp.route('/api/devices', methods=['GET'])
@require_auth
async def get_devices():
    """获取设备列表"""
    try:
        logger.info("开始获取设备列表")
        
        if device_service is None:
            return jsonify({'error': '设备服务未初始化', 'code': 500}), 500
        
        # 获取查询参数
        device_uuid = request.args.get('device_uuid')
        name = request.args.get('name')
        device_type = request.args.get('device_type', type=int)
        status = request.args.get('status', type=int)
        binding_status = request.args.get('binding_status', type=int)
        
        # 如果有过滤条件，使用过滤查询
        if any([device_uuid, name, device_type is not None, status is not None, binding_status is not None]):
            devices = await device_service.get_devices_with_filter(
                device_uuid=device_uuid,
                name=name,
                device_type=device_type,
                status=status,
                binding_status=binding_status
            )
        else:
            devices = await device_service.get_all_devices()
        
        # 转换为字典格式
        result = []
        for device in devices:
            result.append({
                'id': device.id,
                'device_uuid': device.device_uuid,
                'name': device.name,
                'device_type': device.device_type,
                'status': device.status,
                'binding_status': device.binding_status,
                'battery': device.battery,
                'volume': device.volume,
                'ip': device.ip,
                'signal_strength': device.signal_strength,
                'created_at': device.created_at.isoformat() if device.created_at else None,
                'updated_at': device.updated_at.isoformat() if device.updated_at else None,
                'last_active': device.last_active.isoformat() if device.last_active else None
            })
        
        logger.info(f"成功获取设备列表: {len(result)} 条记录")
        return jsonify({'success': True, 'data': result})
        
    except Exception as e:
        logger.error(f"获取设备列表失败: {str(e)}", exc_info=True)
        return jsonify({'error': f'获取设备列表失败: {str(e)}'}), 500


@admin_bp.route('/api/devices/<int:device_id>', methods=['GET'])
@require_auth
async def get_device(device_id):
    """获取单个设备详情"""
    try:
        logger.info(f"开始获取设备详情: {device_id}")
        
        if device_service is None:
            return jsonify({'error': '设备服务未初始化', 'code': 500}), 500
        
        device = await device_service.get_device_by_id(device_id)
        
        if not device:
            return jsonify({'error': '设备不存在', 'code': 404}), 404
        
        result = {
            'id': device.id,
            'device_uuid': device.device_uuid,
            'name': device.name,
            'device_type': device.device_type,
            'status': device.status,
            'binding_status': device.binding_status,
            'battery': device.battery,
            'volume': device.volume,
            'ip': device.ip,
            'signal_strength': device.signal_strength,
            'created_at': device.created_at.isoformat() if device.created_at else None,
            'updated_at': device.updated_at.isoformat() if device.updated_at else None,
            'last_active': device.last_active.isoformat() if device.last_active else None
        }
        
        logger.info(f"成功获取设备详情: {device_id}")
        return jsonify({'success': True, 'data': result})
        
    except Exception as e:
        logger.error(f"获取设备详情失败: {str(e)}", exc_info=True)
        return jsonify({'error': f'获取设备详情失败: {str(e)}'}), 500


@admin_bp.route('/api/devices/<int:device_id>/users', methods=['GET'])
@require_auth
async def get_device_users(device_id):
    """获取设备关联的用户列表"""
    try:
        logger.info(f"开始获取设备关联用户: {device_id}")
        
        if device_service is None:
            return jsonify({'error': '设备服务未初始化', 'code': 500}), 500
        
        users = await device_service.get_device_users(device_id)
        
        # 转换为字典格式
        result = []
        for user in users:
            result.append({
                'id': user.id,
                'login_name': user.login_name,
                'user_name': user.user_name,
                'mobile': user.mobile,
                'avatar': user.avatar,
                'gender': user.gender,
                'user_type': user.user_type,
                'status': user.status,
                'created_at': user.created_at.isoformat() if user.created_at else None,
                'updated_at': user.updated_at.isoformat() if user.updated_at else None
            })
        
        logger.info(f"成功获取设备关联用户: {len(result)} 条记录")
        return jsonify({'success': True, 'data': result})
        
    except Exception as e:
        logger.error(f"获取设备关联用户失败: {str(e)}", exc_info=True)
        return jsonify({'error': f'获取设备关联用户失败: {str(e)}'}), 500


@admin_bp.route('/api/devices/check/<device_uuid>', methods=['GET'])
@require_auth
async def check_device(device_uuid):
    """检查设备是否存在"""
    try:
        logger.info(f"开始检查设备: {device_uuid}")
        
        if device_service is None:
            return jsonify({'error': '设备服务未初始化', 'code': 500}), 500
        
        device = await device_service.get_device_by_uuid(device_uuid)
        
        if device:
            result = {
                'exists': True,
                'device_id': device.id,
                'name': device.name,
                'device_type': device.device_type,
                'status': device.status,
                'binding_status': device.binding_status,
                'battery': device.battery,
                'volume': device.volume,
                'ip': device.ip,
                'signal_strength': device.signal_strength,
                'created_at': device.created_at.isoformat() if device.created_at else None,
                'last_active': device.last_active.isoformat() if device.last_active else None
            }
        else:
            result = {'exists': False}
        
        logger.info(f"设备检查完成: {device_uuid}, 存在: {device is not None}")
        return jsonify({'success': True, 'data': result})
        
    except Exception as e:
        logger.error(f"检查设备失败: {str(e)}", exc_info=True)
        return jsonify({'error': f'检查设备失败: {str(e)}'}), 500


@admin_bp.route('/api/agent-templates', methods=['GET'])
@require_auth
async def get_agent_templates():
    """获取Agent模板列表"""
    try:
        logger.info("开始获取Agent模板列表")
        
        if agent_template_service is None:
            return jsonify({'error': 'Agent模板服务未初始化', 'code': 500}), 500
        
        templates = await agent_template_service.get_all_templates()
        
        # 转换为字典格式
        result = []
        for template in templates:
            result.append({
                'id': template.id,
                'name': template.name,
                'description': template.description,
                'avatar': template.avatar,
                'gender': template.gender,
                'device_type': template.device_type,
                'creator_id': template.creator_id,
                'status': template.status,
                'created_at': template.created_at.isoformat() if template.created_at else None,
                'updated_at': template.updated_at.isoformat() if template.updated_at else None,
                'module_params': template.module_params,
                'agent_config': template.agent_config
            })
        
        logger.info(f"成功获取Agent模板列表: {len(result)} 条记录")
        return jsonify({'success': True, 'data': result})
        
    except Exception as e:
        logger.error(f"获取Agent模板列表失败: {str(e)}", exc_info=True)
        return jsonify({'error': f'获取Agent模板列表失败: {str(e)}'}), 500


@admin_bp.route('/api/devices/bind', methods=['POST'])
@require_auth
async def bind_device():
    """执行设备绑定操作"""
    try:
        logger.info("开始执行设备绑定")
        
        if device_binding_service is None:
            return jsonify({'error': '设备绑定服务未初始化', 'code': 500}), 500
        
        data = await request.get_json()
        if not data:
            return jsonify({'error': '请求数据不能为空'}), 400
        
        device_uuid = data.get('device_uuid')
        user_id = data.get('user_id')
        template_id = data.get('template_id')
        device_name = data.get('device_name')
        device_type = data.get('device_type', 1)
        
        if not device_uuid or not user_id or not template_id:
            return jsonify({'error': '设备UUID、用户ID和模板ID不能为空'}), 400
        
        # 执行绑定
        result = await device_binding_service.bind_device(
            device_uuid=device_uuid,
            user_id=user_id,
            template_id=template_id,
            device_name=device_name,
            device_type=device_type
        )
        
        logger.info(f"设备绑定成功: {result}")
        return jsonify({'success': True, 'data': result})
        
    except Exception as e:
        logger.error(f"设备绑定失败: {str(e)}", exc_info=True)
        return jsonify({'error': f'设备绑定失败: {str(e)}'}), 500


@admin_bp.route('/agent-templates-page', methods=['GET'])
@require_auth
async def agent_templates_page():
    """Agent模板管理页面"""
    return await render_template('admin/agent_templates.html')


@admin_bp.route('/api/agent-templates/<int:template_id>', methods=['GET'])
@require_auth
async def get_agent_template(template_id):
    """获取单个Agent模板详情"""
    try:
        logger.info(f"开始获取Agent模板详情: {template_id}")
        
        if agent_template_service is None:
            return jsonify({'error': 'Agent模板服务未初始化', 'code': 500}), 500
        
        template = await agent_template_service.get_template_by_id(template_id)
        
        if not template:
            return jsonify({'error': '模板不存在', 'code': 404}), 404
        
        result = {
            'id': template.id,
            'name': template.name,
            'description': template.description,
            'avatar': template.avatar,
            'gender': template.gender,
            'device_type': template.device_type,
            'creator_id': template.creator_id,
            'status': template.status,
            'created_at': template.created_at.isoformat() if template.created_at else None,
            'updated_at': template.updated_at.isoformat() if template.updated_at else None,
            'module_params': template.module_params,
            'agent_config': template.agent_config
        }
        
        logger.info(f"成功获取Agent模板详情: {template_id}")
        return jsonify({'success': True, 'data': result})
        
    except Exception as e:
        logger.error(f"获取Agent模板详情失败: {str(e)}", exc_info=True)
        return jsonify({'error': f'获取Agent模板详情失败: {str(e)}'}), 500


@admin_bp.route('/api/agent-templates', methods=['POST'])
@require_auth
async def create_agent_template():
    """创建新Agent模板"""
    try:
        logger.info("开始创建Agent模板")
        
        if agent_template_service is None:
            return jsonify({'error': 'Agent模板服务未初始化', 'code': 500}), 500
        
        data = await request.get_json()
        if not data:
            return jsonify({'error': '请求数据不能为空'}), 400
        
        name = data.get('name')
        if not name:
            return jsonify({'error': '模板名称不能为空'}), 400
        
        description = data.get('description')
        avatar = data.get('avatar')
        gender = data.get('gender', 0)
        device_type = data.get('device_type', 1)
        creator_id = data.get('creator_id', 0)
        module_params = data.get('module_params', {})
        agent_config = data.get('agent_config', {})
        
        # 验证JSON格式
        try:
            if isinstance(module_params, str):
                module_params = json.loads(module_params)
            if isinstance(agent_config, str):
                agent_config = json.loads(agent_config)
            json.dumps(module_params)  # 验证JSON是否有效
            json.dumps(agent_config)  # 验证JSON是否有效
        except (json.JSONDecodeError, TypeError) as e:
            return jsonify({'error': f'JSON格式无效: {str(e)}'}), 400
        
        template_id = await agent_template_service.create_template(
            name=name,
            description=description,
            avatar=avatar,
            gender=gender,
            device_type=device_type,
            creator_id=creator_id,
            module_params=module_params,
            agent_config=agent_config
        )
        
        logger.info(f"成功创建Agent模板: {template_id}")
        return jsonify({'success': True, 'data': {'id': template_id}, 'message': '模板创建成功'})
        
    except Exception as e:
        logger.error(f"创建Agent模板失败: {str(e)}", exc_info=True)
        return jsonify({'error': f'创建Agent模板失败: {str(e)}'}), 500


@admin_bp.route('/api/agent-templates/<int:template_id>', methods=['PUT'])
@require_auth
async def update_agent_template(template_id):
    """更新Agent模板基本信息和配置"""
    try:
        logger.info(f"开始更新Agent模板: {template_id}")
        
        if agent_template_service is None:
            return jsonify({'error': 'Agent模板服务未初始化', 'code': 500}), 500
        
        data = await request.get_json()
        if not data:
            return jsonify({'error': '请求数据不能为空'}), 400
        
        name = data.get('name')
        description = data.get('description')
        avatar = data.get('avatar')
        gender = data.get('gender')
        device_type = data.get('device_type')
        module_params = data.get('module_params')
        agent_config = data.get('agent_config')
        
        # 验证JSON格式
        if module_params is not None:
            try:
                if isinstance(module_params, str):
                    module_params = json.loads(module_params)
                json.dumps(module_params)  # 验证JSON是否有效
            except (json.JSONDecodeError, TypeError) as e:
                return jsonify({'error': f'模块参数JSON格式无效: {str(e)}'}), 400
        
        # 验证agent_config格式
        if agent_config is not None:
            try:
                if isinstance(agent_config, str):
                    agent_config = json.loads(agent_config)
                json.dumps(agent_config)  # 验证JSON是否有效
            except (json.JSONDecodeError, TypeError) as e:
                return jsonify({'error': f'Agent配置JSON格式无效: {str(e)}'}), 400
        
        success = await agent_template_service.update_template(
            template_id=template_id,
            name=name,
            description=description,
            avatar=avatar,
            gender=gender,
            device_type=device_type,
            module_params=module_params,
            agent_config=agent_config
        )
        
        if not success:
            return jsonify({'error': '模板不存在或更新失败'}), 404
        
        logger.info(f"成功更新Agent模板: {template_id}")
        return jsonify({'success': True, 'message': '模板更新成功'})
        
    except Exception as e:
        logger.error(f"更新Agent模板失败: {str(e)}", exc_info=True)
        return jsonify({'error': f'更新Agent模板失败: {str(e)}'}), 500


@admin_bp.route('/api/agent-templates/<int:template_id>/config', methods=['PUT'])
@require_auth
async def update_agent_template_config(template_id):
    """更新Agent模板配置"""
    try:
        logger.info(f"开始更新Agent模板配置: {template_id}")
        
        if agent_template_service is None:
            return jsonify({'error': 'Agent模板服务未初始化', 'code': 500}), 500
        
        data = await request.get_json()
        if not data:
            return jsonify({'error': '请求数据不能为空'}), 400
        
        agent_config = data.get('agent_config')
        if agent_config is None:
            return jsonify({'error': 'agent_config字段不能为空'}), 400
        
        # 验证JSON格式
        try:
            if isinstance(agent_config, str):
                agent_config = json.loads(agent_config)
            json.dumps(agent_config)  # 验证JSON是否有效
        except (json.JSONDecodeError, TypeError) as e:
            return jsonify({'error': f'JSON格式无效: {str(e)}'}), 400
        
        # 更新配置
        success = await agent_template_service.update_template_config(template_id, agent_config)
        
        if not success:
            return jsonify({'error': '模板不存在或更新失败'}), 404
        
        logger.info(f"成功更新Agent模板配置: {template_id}")
        return jsonify({'success': True, 'message': '配置更新成功'})
        
    except Exception as e:
        logger.error(f"更新Agent模板配置失败: {str(e)}", exc_info=True)
        return jsonify({'error': f'更新Agent模板配置失败: {str(e)}'}), 500


@admin_bp.route('/api/agent-templates/<int:template_id>', methods=['DELETE'])
@require_auth
async def delete_agent_template(template_id):
    """删除Agent模板"""
    try:
        logger.info(f"开始删除Agent模板: {template_id}")
        
        if agent_template_service is None:
            return jsonify({'error': 'Agent模板服务未初始化', 'code': 500}), 500
        
        success = await agent_template_service.delete_template(template_id)
        
        if not success:
            return jsonify({'error': '模板不存在或删除失败'}), 404
        
        logger.info(f"成功删除Agent模板: {template_id}")
        return jsonify({'success': True, 'message': '模板删除成功'})
        
    except Exception as e:
        logger.error(f"删除Agent模板失败: {str(e)}", exc_info=True)
        return jsonify({'error': f'删除Agent模板失败: {str(e)}'}), 500


@admin_bp.route('/api/agents/<int:agent_id>/transfer', methods=['POST'])
@require_auth
async def transfer_agent(agent_id):
    """迁移agent和设备给另一个用户"""
    try:
        logger.info(f"开始迁移Agent: {agent_id}")
        
        if agent_service is None:
            return jsonify({'error': 'Agent服务未初始化', 'code': 500}), 500
        
        data = await request.get_json()
        if not data:
            return jsonify({'error': '请求数据不能为空'}), 400
        
        target_user_id = data.get('target_user_id')
        if not target_user_id:
            return jsonify({'error': '目标用户ID不能为空'}), 400
        
        try:
            target_user_id = int(target_user_id)
        except (ValueError, TypeError):
            return jsonify({'error': '目标用户ID必须是数字'}), 400
        
        # 执行迁移
        result = await agent_service.transfer_agent_to_user(agent_id, target_user_id)
        
        logger.info(f"Agent迁移成功: {result}")
        return jsonify({'success': True, 'data': result})
        
    except Exception as e:
        logger.error(f"迁移Agent失败: {str(e)}", exc_info=True)
        return jsonify({'error': f'迁移Agent失败: {str(e)}'}), 500


@admin_bp.route('/', methods=['GET'])
async def index():
    """后台管理首页"""
    if await auth_manager.is_authenticated():
        return await render_template('admin/dashboard.html')
    else:
        return await render_template('admin/login.html')
