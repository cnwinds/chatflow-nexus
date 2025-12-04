-- 创建数据库
CREATE DATABASE IF NOT EXISTS ai_agents;
USE ai_agents;

-- 用户信息表
CREATE TABLE users (
  id INT PRIMARY KEY AUTO_INCREMENT COMMENT '用户ID',
  login_name VARCHAR(50) NOT NULL COMMENT '登录名。手机号/邮箱/用户名/三方平台的唯一标识',
  login_type TINYINT DEFAULT 1 COMMENT '登录类型：1-手机号，2-邮箱，3-用户名，4-Apple，5-Google，6-微信',
  password_hash VARCHAR(255) NOT NULL COMMENT '密码哈希值',
  user_name VARCHAR(50) NOT NULL COMMENT '显示名称',
  description VARCHAR(255) DEFAULT '这个用户很懒，什么也没有留下' COMMENT '用户描述',
  mobile VARCHAR(20) UNIQUE COMMENT '手机号，唯一标识',
  avatar VARCHAR(255) COMMENT '用户头像URL',
  gender TINYINT DEFAULT 0 COMMENT '性别：0-女，1-男',
  user_type TINYINT DEFAULT 0 COMMENT '用户类型：0-普通用户，1-系统用户',
  status TINYINT DEFAULT 1 COMMENT '状态：0-禁用，1-正常，2-已删除',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  INDEX idx_mobile (mobile) COMMENT '手机号索引',
  INDEX idx_user_name (user_name) COMMENT '用户名索引',
  INDEX idx_login_name (login_name) COMMENT '登录名索引',
  INDEX idx_login_type (login_type) COMMENT '登录类型索引',
  INDEX idx_status (status) COMMENT '状态索引'
) COMMENT='用户信息表';

-- 设备信息表
CREATE TABLE devices (
  id INT PRIMARY KEY AUTO_INCREMENT COMMENT '设备ID',
  device_uuid VARCHAR(100) UNIQUE NOT NULL COMMENT '设备唯一编码',
  name VARCHAR(100) NOT NULL COMMENT '设备名称',
  device_type TINYINT NOT NULL COMMENT '设备类型：1-智能音箱，2-智能显示屏，3-机器人，4-车载设备，5-可穿戴设备，0-其他',
  status TINYINT DEFAULT 0 COMMENT '设备状态：0-离线，1-在线，2-休眠，3-正在连接，4-故障',
  binding_status TINYINT DEFAULT 0 COMMENT '绑定状态：0-等待绑定，1-绑定完成',
  battery TINYINT DEFAULT 100 COMMENT '电量百分比(0-100)',
  is_charging BOOLEAN DEFAULT FALSE COMMENT '是否在充电',
  volume TINYINT DEFAULT 50 COMMENT '音量级别(0-100)',
  brightness TINYINT DEFAULT 50 COMMENT '灯光亮度(0-100)',
  ip VARCHAR(50) COMMENT '设备IP地址',
  mac_address VARCHAR(17) COMMENT '设备MAC地址',
  signal_strength TINYINT COMMENT 'WiFi信号强度(0-100)',
  wifi_name VARCHAR(100) COMMENT '当前连接的WiFi名称',
  challenge VARCHAR(128) COMMENT '设备挑战码，用于设备连接时的安全验证',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  last_active TIMESTAMP NULL COMMENT '最后活跃时间',
  INDEX idx_device_uuid (device_uuid) COMMENT '设备编码索引',
  INDEX idx_device_type (device_type) COMMENT '设备类型索引',
  INDEX idx_status (status) COMMENT '状态索引',
  INDEX idx_binding_status (binding_status) COMMENT '绑定状态索引',
  INDEX idx_mac_address (mac_address) COMMENT 'MAC地址索引',
  INDEX idx_challenge (challenge) COMMENT '挑战码索引'
) COMMENT='设备信息表';

-- 用户设备关联表
CREATE TABLE user_devices (
  id INT PRIMARY KEY AUTO_INCREMENT COMMENT '关联ID',
  user_id INT NOT NULL COMMENT '用户ID',
  device_id INT NOT NULL COMMENT '设备ID',
  is_owner BOOLEAN DEFAULT true COMMENT '是否是设备所有者',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
  UNIQUE KEY uk_user_device (user_id, device_id) COMMENT '用户设备唯一约束',
  INDEX idx_user_id (user_id) COMMENT '用户ID索引',
  INDEX idx_device_id (device_id) COMMENT '设备ID索引'
) COMMENT='用户设备关联表';

-- 功能模块表
CREATE TABLE modules (
  id INT PRIMARY KEY AUTO_INCREMENT COMMENT '模块ID',
  name VARCHAR(100) NOT NULL COMMENT '模块名称',
  avatar VARCHAR(255) COMMENT '模块头像URL',
  description TEXT COMMENT '模块描述',
  code VARCHAR(50) NOT NULL COMMENT '功能模块代码',
  type VARCHAR(20) NOT NULL COMMENT '功能模块类型：vad, asr, memory, llm, tts, intent',
  is_default BOOLEAN DEFAULT false COMMENT '是否默认',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  UNIQUE KEY uk_code_type (code, type) COMMENT '代码类型唯一约束',
  INDEX idx_type (type) COMMENT '模块类型索引',
  INDEX idx_is_default (is_default) COMMENT '是否默认索引'
) COMMENT='功能模块表';

-- 智能体模板表
CREATE TABLE agent_templates (
  id INT PRIMARY KEY AUTO_INCREMENT COMMENT '模板ID',
  name VARCHAR(100) NOT NULL COMMENT '模板名称',
  description TEXT COMMENT '模板描述',
  avatar VARCHAR(255) COMMENT '模板头像URL',
  gender TINYINT DEFAULT 0 COMMENT '性别：0-女，1-男',
  device_type TINYINT NOT NULL COMMENT '适用设备类型：1-智能音箱，2-智能显示屏，3-机器人，4-车载设备，5-可穿戴设备，0-其他',
  creator_id INT DEFAULT 0 COMMENT '创建者ID，系统模板为0',
  module_params JSON COMMENT '模块配置参数',
  agent_config JSON COMMENT '智能体配置参数',
  status TINYINT DEFAULT 1 COMMENT '状态：0-禁用，1-正常，2-已删除',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  FOREIGN KEY (creator_id) REFERENCES users(id) ON DELETE SET NULL,
  INDEX idx_device_type (device_type) COMMENT '设备类型索引',
  INDEX idx_creator_id (creator_id) COMMENT '创建者索引',
  INDEX idx_name (name) COMMENT '模板名称索引',
  INDEX idx_status (status) COMMENT '状态索引'
) COMMENT='智能体模板表';

--智能体实例表
CREATE TABLE agents (
  id INT PRIMARY KEY AUTO_INCREMENT COMMENT '智能体ID',
  name VARCHAR(100) NOT NULL COMMENT '智能体名称',
  description TEXT COMMENT '智能体描述',
  avatar VARCHAR(255) COMMENT '智能体头像URL',
  gender TINYINT DEFAULT 0 COMMENT '性别：0-女，1-男',
  user_id INT NOT NULL COMMENT '用户ID',
  device_id INT NULL COMMENT '用户设备关联ID，可为空表示未绑定设备',
  template_id INT NOT NULL COMMENT '模板ID',
  device_type TINYINT NOT NULL COMMENT '设备类型：1-智能音箱，2-智能显示屏，3-机器人，4-车载设备，5-可穿戴设备，0-其他',
  module_params JSON COMMENT '模块配置参数',
  agent_config JSON COMMENT '智能体配置参数',
  memory_data JSON COMMENT '智能体记忆',
  status TINYINT DEFAULT 1 COMMENT '状态：0-禁用，1-正常，2-已删除',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE SET NULL,
  FOREIGN KEY (template_id) REFERENCES agent_templates(id),
  INDEX idx_user_id (user_id) COMMENT '用户ID索引',
  INDEX idx_device_id (device_id) COMMENT '用户设备关联ID索引',
  INDEX idx_template_id (template_id) COMMENT '模板ID索引',
  INDEX idx_status (status) COMMENT '状态索引'
) COMMENT='智能体实例表';

-- 聊天消息记录表
CREATE TABLE chat_messages (
  id INT PRIMARY KEY AUTO_INCREMENT COMMENT '消息ID',
  session_id VARCHAR(100) COMMENT '会话ID',
  agent_id INT NOT NULL COMMENT '智能体ID',
  role VARCHAR(20) NOT NULL COMMENT '角色：user, assistant',
  content TEXT NOT NULL COMMENT '消息内容',
  audio_file_path VARCHAR(500) COMMENT '用户说话的声音文件路径（仅role为user时有效）',
  emotion VARCHAR(50) DEFAULT 'neutral' COMMENT '情感标签：neutral, happy, sad, angry, excited等',
  copilot_mode BOOLEAN DEFAULT FALSE COMMENT '是否星宝领航员模式',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE,
  INDEX idx_session_created (session_id, created_at) COMMENT '会话创建时间联合索引',
  INDEX idx_agent_created (agent_id, created_at) COMMENT '智能体创建时间联合索引',
  INDEX idx_agent_copilot_created (agent_id, copilot_mode, created_at) COMMENT '智能体模式创建时间联合索引',
  INDEX idx_role (role) COMMENT '角色索引',
  INDEX idx_emotion (emotion) COMMENT '情感索引'
) COMMENT='聊天消息记录表';

-- 聊天压缩消息表
CREATE TABLE chat_compressed_messages (
  id INT PRIMARY KEY AUTO_INCREMENT COMMENT '压缩记录ID',
  agent_id INT NOT NULL COMMENT '智能体ID',
  compressed_content TEXT NOT NULL COMMENT '压缩后的内容',
  content_last_time TIMESTAMP NOT NULL COMMENT '被压缩的最后一条消息的时间',
  copilot_mode BOOLEAN DEFAULT FALSE COMMENT '是否星宝领航员模式',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE,
  INDEX idx_agent_created (agent_id, created_at) COMMENT '智能体创建时间联合索引',
  INDEX idx_agent_copilot_created (agent_id, copilot_mode, created_at) COMMENT '智能体模式创建时间联合索引'
) COMMENT='聊天压缩消息记录表';

-- 会话分析结果表
CREATE TABLE session_analysis (
  id INT PRIMARY KEY AUTO_INCREMENT COMMENT '分析记录ID',
  session_id VARCHAR(100) NOT NULL COMMENT '会话ID',
  agent_id INT NOT NULL COMMENT '智能体ID',
  conversation_duration INT DEFAULT NULL COMMENT '会话时长（秒）',
  avg_child_sentence_length FLOAT DEFAULT NULL COMMENT '孩子平均句长（字数）',
  analysis_result JSON COMMENT '分析结果JSON（包含session_analysis数组），处理成功时填充',
  status VARCHAR(20) DEFAULT 'pending' COMMENT '处理状态：pending-待处理, processing-处理中, completed-已完成, failed-失败',
  retry_count INT DEFAULT 0 COMMENT '重试次数',
  error_message TEXT COMMENT '错误信息（失败时记录）',
  copilot_mode BOOLEAN DEFAULT FALSE COMMENT '是否星宝领航员模式',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE,
  INDEX idx_session_id (session_id) COMMENT '会话ID索引',
  INDEX idx_agent_id (agent_id) COMMENT '智能体ID索引',
  INDEX idx_status (status) COMMENT '状态索引',
  INDEX idx_status_created (status, created_at) COMMENT '状态和创建时间联合索引',
  UNIQUE KEY uk_session_id (session_id) COMMENT '会话ID唯一索引'
) COMMENT='会话分析结果表';

-- 声音克隆表
CREATE TABLE voice_clones (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '声音克隆ID',
    user_id BIGINT NOT NULL COMMENT '用户ID',
    role_name VARCHAR(100) NOT NULL COMMENT '角色名称',
    consent_voice_name VARCHAR(100) COMMENT '同意声音名称',
    consent_voice_path VARCHAR(255) COMMENT '同意声音文件路径',
    project_id VARCHAR(255) COMMENT '项目ID',
    consent_id VARCHAR(255) COMMENT '同意ID',
    speaker_profile_id VARCHAR(255) COMMENT '克隆完成后声音的ID',
    personal_voice_id VARCHAR(255) COMMENT '训练和删除声音的ID',
    status TINYINT DEFAULT 0 COMMENT '状态：0-训练中，1-可用，2-失败，3-已删除',
    voice_params JSON NULL COMMENT '克隆声音prosody配置（rate/pitch/range/volume/contour）',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_user_id (user_id),
    INDEX idx_status (status),
    INDEX idx_personal_voice_id (personal_voice_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='声音克隆表';

-- 声音克隆训练声音表
CREATE TABLE voice_clone_training_voices (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '训练声音ID',
    voice_clone_id BIGINT NOT NULL COMMENT '声音克隆ID',
    voice_path VARCHAR(255) NOT NULL COMMENT '训练声音文件路径',
    file_size BIGINT COMMENT '声音文件大小（字节）',
    duration FLOAT COMMENT '声音时长（秒）',
    voice_order INT DEFAULT 0 COMMENT '声音顺序（用于排序）',
    transcribed_text TEXT COMMENT '语音识别文本内容',
    status TINYINT DEFAULT 1 COMMENT '状态：0-已删除，1-正常',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    FOREIGN KEY (voice_clone_id) REFERENCES voice_clones(id) ON DELETE CASCADE,
    INDEX idx_voice_clone_id (voice_clone_id),
    INDEX idx_status (status),
    INDEX idx_voice_order (voice_clone_id, voice_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='声音克隆训练声音表';

-- 设备绑定日志表
CREATE TABLE device_binding_logs (
  id INT PRIMARY KEY AUTO_INCREMENT COMMENT '日志ID',
  user_id INT NOT NULL COMMENT '用户ID',
  device_id INT NOT NULL COMMENT '设备ID',
  action_type TINYINT NOT NULL COMMENT '操作类型：1-绑定，2-解绑，3-分享，4-取消分享',
  challenge VARCHAR(128) COMMENT '挑战码（绑定操作时生成）',
  ip_address VARCHAR(50) COMMENT '操作IP地址',
  user_agent TEXT COMMENT '用户代理信息',
  additional_info JSON COMMENT '额外信息（如分享目标用户等）',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
  INDEX idx_user_id (user_id) COMMENT '用户ID索引',
  INDEX idx_device_id (device_id) COMMENT '设备ID索引',
  INDEX idx_action_type (action_type) COMMENT '操作类型索引',
  INDEX idx_created_at (created_at) COMMENT '操作时间索引',
  INDEX idx_challenge (challenge) COMMENT '挑战码索引'
) COMMENT='设备绑定操作日志表';

-- AI指标记录表
CREATE TABLE ai_metrics (
  id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '指标记录ID',
  monitor_id VARCHAR(64) NOT NULL COMMENT '监控ID',
  provider VARCHAR(50) COMMENT '提供商：openai, anthropic, azure, google等',
  model_name VARCHAR(100) COMMENT '模型名称',
  session_id VARCHAR(64) COMMENT '会话ID',
  start_time TIMESTAMP NOT NULL COMMENT '开始时间',
  end_time TIMESTAMP COMMENT '结束时间',
  
  -- Token统计
  prompt_tokens INT DEFAULT 0 COMMENT '输入token数',
  completion_tokens INT DEFAULT 0 COMMENT '输出token数',
  total_tokens INT DEFAULT 0 COMMENT '总token数',
  
  -- 内容统计
  input_chars INT DEFAULT 0 COMMENT '输入字符数',
  output_chars INT DEFAULT 0 COMMENT '输出字符数',
  
  -- 工具相关
  tool_count INT DEFAULT 0 COMMENT '工具数量',
  tool_calls_made INT DEFAULT 0 COMMENT '工具调用次数',
  
  -- 费用信息
  cost DECIMAL(10,6) DEFAULT 0.0 COMMENT '总费用',
  input_cost DECIMAL(10,6) DEFAULT 0.0 COMMENT '输入费用',
  output_cost DECIMAL(10,6) DEFAULT 0.0 COMMENT '输出费用',
  
  -- 性能指标
  total_time FLOAT DEFAULT 0.0 COMMENT '总耗时（毫秒）',
  http_first_byte_time FLOAT COMMENT 'HTTP首字节时间（毫秒）',
  first_token_time FLOAT COMMENT '第一个token时间（毫秒）',

  -- 调用结果
  result TEXT COMMENT '调用结果内容',
  
  -- 索引
  INDEX idx_monitor_id (monitor_id) COMMENT '监控ID索引',
  INDEX idx_model_name (model_name) COMMENT '模型名称索引',
  INDEX idx_provider (provider) COMMENT '提供商索引',
  INDEX idx_session_id (session_id) COMMENT '会话ID索引',
  INDEX idx_start_time (start_time) COMMENT '开始时间索引',
  INDEX idx_model_time (model_name, start_time) COMMENT '模型时间联合索引',
  INDEX idx_provider_time (provider, start_time) COMMENT '提供商时间联合索引',
  INDEX idx_provider_model (provider, model_name) COMMENT '提供商模型联合索引'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI指标记录表';

-- growth_summary_records 成长记录表
CREATE TABLE IF NOT EXISTS growth_summary_records (
  id INT PRIMARY KEY AUTO_INCREMENT COMMENT '记录ID',
  agent_id INT NOT NULL COMMENT '智能体ID',
  summary_date DATE NOT NULL COMMENT '总结日期',
  summary_type VARCHAR(20) NOT NULL DEFAULT 'daily' COMMENT '总结类型：daily-日总结, weekly-周总结',
  scheduled_time TIME NOT NULL COMMENT '计划执行时间',
  status VARCHAR(20) DEFAULT 'pending' COMMENT '状态：pending-待处理, completed-已完成, failed-失败',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  completed_at TIMESTAMP NULL COMMENT '完成时间',
  summary_content TEXT COMMENT '总结内容（JSON格式）',
  FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE,
  UNIQUE KEY uk_agent_date_type (agent_id, summary_date, summary_type) COMMENT 'agent+日期+类型唯一索引',
  INDEX idx_agent_id (agent_id) COMMENT 'agent ID索引',
  INDEX idx_summary_date (summary_date) COMMENT '总结日期索引',
  INDEX idx_summary_type (summary_type) COMMENT '总结类型索引',
  INDEX idx_status (status) COMMENT '状态索引',
  INDEX idx_status_date (status, summary_date) COMMENT '状态和日期联合索引'
) COMMENT='成长记录表';
