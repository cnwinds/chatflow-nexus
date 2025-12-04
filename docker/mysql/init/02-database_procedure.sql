DELIMITER //

DROP PROCEDURE IF EXISTS create_agent_template;

CREATE PROCEDURE create_agent_template(
    IN p_name VARCHAR(255),
    IN p_description TEXT,
    IN p_avatar VARCHAR(255),
    IN p_gender TINYINT,
    IN p_device_type TINYINT,
    IN p_prompt TEXT,
    IN p_agent_config JSON
)
BEGIN
    DECLARE v_creator_id INT;
    DECLARE v_module_params JSON;
    DECLARE v_agent_config JSON;
    DECLARE v_default_prompt TEXT DEFAULT '';
    DECLARE v_default_agent_config JSON DEFAULT JSON_OBJECT();
    
    -- 获取管理员用户ID
    SELECT id INTO v_creator_id FROM users WHERE user_name = 'admin' LIMIT 1;
    
    -- 使用默认提示词或自定义提示词
    IF p_prompt IS NULL THEN 
        SET p_prompt = v_default_prompt;
    END IF;
    
    -- 处理agent_config：如果为NULL则使用默认配置并设置输入参数
    SET v_agent_config = p_agent_config;
    IF v_agent_config IS NULL THEN
        SET v_agent_config = v_default_agent_config;
    END IF;    
    -- 将输入参数设置到默认配置的对应字段
    -- 设置角色名称
    IF p_name IS NOT NULL THEN
        SET v_agent_config = JSON_SET(v_agent_config, '$.profile.character.name', p_name);
    END IF;
    
    -- 设置角色描述
    IF p_description IS NOT NULL THEN
        SET v_agent_config = JSON_SET(v_agent_config, '$.profile.character.description', p_description);
    END IF;
    
    -- 设置性别
    IF p_gender IS NOT NULL THEN
        SET v_agent_config = JSON_SET(v_agent_config, '$.profile.character.gender', p_gender);
    END IF;
    
    -- 设置头像URL
    IF p_avatar IS NOT NULL THEN
        SET v_agent_config = JSON_SET(v_agent_config, '$.profile.character.avatar', p_avatar);
    END IF;
    
    -- 设置提示词
    SET v_agent_config = JSON_SET(v_agent_config, '$.profile.character.prompt', p_prompt);
    
    -- 构建完整的module_params JSON
    SET v_module_params = JSON_OBJECT();
    
    -- 插入agent_templates记录
    INSERT INTO agent_templates (
        name, 
        description, 
        avatar, 
        gender, 
        device_type, 
        creator_id, 
        module_params,
        agent_config
    ) 
    VALUES (
        p_name, 
        p_description, 
        p_avatar, 
        p_gender, 
        p_device_type, 
        v_creator_id, 
        v_module_params,
        v_agent_config
    );
    
    SELECT LAST_INSERT_ID() AS template_id;
END //

DELIMITER ;
