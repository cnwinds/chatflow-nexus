-- 优化 ai_metrics 表索引性能
-- 此脚本用于检查和优化 ai_metrics 表的索引结构

-- 1. 检查当前索引
SELECT 
    TABLE_NAME,
    INDEX_NAME,
    COLUMN_NAME,
    SEQ_IN_INDEX,
    CARDINALITY,
    INDEX_TYPE
FROM 
    INFORMATION_SCHEMA.STATISTICS
WHERE 
    TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'ai_metrics'
ORDER BY 
    INDEX_NAME, SEQ_IN_INDEX;

-- 2. 分析表结构（可选，需要 ANALYZE TABLE 权限）
-- ANALYZE TABLE ai_metrics;

-- 3. 如果发现索引缺失，可以添加以下索引（根据实际查询需求）
-- 注意：索引会增加INSERT开销，但会提升查询性能

-- 如果经常按 end_time 查询，可以添加：
-- CREATE INDEX idx_end_time ON ai_metrics(end_time);

-- 如果经常按 session_id 和 start_time 联合查询，可以添加：
-- CREATE INDEX idx_session_time ON ai_metrics(session_id, start_time);

-- 4. 优化建议：
-- - 如果表数据量很大（百万级），考虑分区表
-- - 如果 result 字段经常为空或很小，考虑使用 VARCHAR 而不是 TEXT
-- - 定期执行 ANALYZE TABLE 更新统计信息
-- - 考虑使用延迟索引更新（MySQL 8.0+）

-- 5. 检查表大小和索引大小
SELECT 
    table_name AS '表名',
    ROUND(((data_length + index_length) / 1024 / 1024), 2) AS '总大小(MB)',
    ROUND((data_length / 1024 / 1024), 2) AS '数据大小(MB)',
    ROUND((index_length / 1024 / 1024), 2) AS '索引大小(MB)',
    table_rows AS '行数'
FROM 
    information_schema.TABLES
WHERE 
    table_schema = DATABASE()
    AND table_name = 'ai_metrics';



