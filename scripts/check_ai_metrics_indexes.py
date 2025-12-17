#!/usr/bin/env python3
"""
检查 ai_metrics 表的索引情况
用于诊断 INSERT 性能问题
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.common.database import get_db_manager
from src.common.logging import get_logger

logger = get_logger(__name__)


async def check_indexes():
    """检查 ai_metrics 表的索引"""
    try:
        db_manager = get_db_manager()
        
        # 1. 检查所有索引
        logger.info("=" * 60)
        logger.info("检查 ai_metrics 表的索引")
        logger.info("=" * 60)
        
        sql = """
        SELECT 
            INDEX_NAME,
            GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS COLUMNS,
            INDEX_TYPE,
            NON_UNIQUE,
            CARDINALITY
        FROM 
            INFORMATION_SCHEMA.STATISTICS
        WHERE 
            TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'ai_metrics'
        GROUP BY 
            INDEX_NAME, INDEX_TYPE, NON_UNIQUE, CARDINALITY
        ORDER BY 
            INDEX_NAME;
        """
        
        indexes = await db_manager.execute_query(sql)
        
        logger.info(f"\n找到 {len(indexes)} 个索引：\n")
        for idx in indexes:
            unique = "UNIQUE" if idx['NON_UNIQUE'] == 0 else "INDEX"
            logger.info(f"  {idx['INDEX_NAME']:30} {unique:8} ({idx['COLUMNS']})")
            logger.info(f"    Type: {idx['INDEX_TYPE']}, Cardinality: {idx['CARDINALITY']}")
        
        # 2. 检查表大小
        logger.info("\n" + "=" * 60)
        logger.info("表大小信息")
        logger.info("=" * 60)
        
        sql = """
        SELECT 
            table_name AS '表名',
            ROUND(((data_length + index_length) / 1024 / 1024), 2) AS '总大小_MB',
            ROUND((data_length / 1024 / 1024), 2) AS '数据大小_MB',
            ROUND((index_length / 1024 / 1024), 2) AS '索引大小_MB',
            table_rows AS '行数'
        FROM 
            information_schema.TABLES
        WHERE 
            table_schema = DATABASE()
            AND table_name = 'ai_metrics';
        """
        
        table_info = await db_manager.execute_query(sql)
        if table_info:
            info = table_info[0]
            logger.info(f"\n表名: {info['表名']}")
            logger.info(f"总大小: {info['总大小_MB']} MB")
            logger.info(f"数据大小: {info['数据大小_MB']} MB")
            logger.info(f"索引大小: {info['索引大小_MB']} MB")
            logger.info(f"行数: {info['行数']:,}")
            
            # 计算索引占比
            if info['总大小_MB'] > 0:
                index_ratio = (info['索引大小_MB'] / info['总大小_MB']) * 100
                logger.info(f"索引占比: {index_ratio:.2f}%")
        
        # 3. 检查是否有缺失的索引（根据表定义）
        logger.info("\n" + "=" * 60)
        logger.info("索引完整性检查")
        logger.info("=" * 60)
        
        expected_indexes = {
            'PRIMARY': ['id'],
            'idx_monitor_id': ['monitor_id'],
            'idx_model_name': ['model_name'],
            'idx_provider': ['provider'],
            'idx_session_id': ['session_id'],
            'idx_start_time': ['start_time'],
            'idx_model_time': ['model_name', 'start_time'],
            'idx_provider_time': ['provider', 'start_time'],
            'idx_provider_model': ['provider', 'model_name']
        }
        
        existing_indexes = {idx['INDEX_NAME']: idx['COLUMNS'].split(',') for idx in indexes}
        
        missing_indexes = []
        for idx_name, columns in expected_indexes.items():
            if idx_name not in existing_indexes:
                missing_indexes.append((idx_name, columns))
            else:
                existing_cols = existing_indexes[idx_name]
                if set(columns) != set(existing_cols):
                    logger.warning(f"索引 {idx_name} 的列不匹配: 期望 {columns}, 实际 {existing_cols}")
        
        if missing_indexes:
            logger.warning(f"\n发现 {len(missing_indexes)} 个缺失的索引：")
            for idx_name, columns in missing_indexes:
                logger.warning(f"  - {idx_name}: {columns}")
                logger.info(f"\n可以执行以下SQL创建缺失的索引：")
                for idx_name, columns in missing_indexes:
                    cols_str = ', '.join(columns)
                    logger.info(f"CREATE INDEX {idx_name} ON ai_metrics({cols_str});")
        else:
            logger.info("\n✓ 所有预期的索引都存在")
        
        # 4. 性能建议
        logger.info("\n" + "=" * 60)
        logger.info("性能优化建议")
        logger.info("=" * 60)
        
        if table_info and table_info[0]['行数'] > 100000:
            logger.info("1. 表数据量较大，建议：")
            logger.info("   - 考虑使用批量插入（已实现）")
            logger.info("   - 定期清理旧数据")
            logger.info("   - 考虑表分区（如果MySQL版本支持）")
        
        if table_info and table_info[0]['索引大小_MB'] > table_info[0]['数据大小_MB']:
            logger.info("2. 索引大小超过数据大小，建议：")
            logger.info("   - 检查是否有不必要的索引")
            logger.info("   - 考虑合并部分单列索引为联合索引")
        
        logger.info("3. INSERT 性能优化建议：")
        logger.info("   - 使用批量插入（batch_size >= 10）")
        logger.info("   - 如果 result 字段经常为空，考虑使用 VARCHAR 替代 TEXT")
        logger.info("   - 定期执行 ANALYZE TABLE ai_metrics 更新统计信息")
        logger.info("   - 检查数据库配置（innodb_flush_log_at_trx_commit 等）")
        
    except Exception as e:
        logger.error(f"检查索引时出错: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(check_indexes())



