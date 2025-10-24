#!/usr/bin/env python3
"""
验证提示词导入结果的脚本
"""

import os
import sys
import asyncio
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "python" / "packages" / "agent_fusion" / "src"))

from sqlalchemy import select
from data_layer.base_data_layer import DBDataLayer
from data_layer.models.tables.prompt_table import PromptTable, PromptVersionTable


async def verify_import():
    """验证提示词导入结果"""
    database_url = os.getenv('DATABASE_URL', 'postgresql+asyncpg://user:password@localhost/agentfusion')

    db = DBDataLayer(database_url)

    try:
        await db.connect()
        print("✅ 数据库连接成功")

        async with await db.get_session() as session:
            # 查询所有提示词
            stmt = select(
                PromptTable.name,
                PromptTable.category,
                PromptTable.prompt_id
            ).order_by(PromptTable.name)

            result = await session.execute(stmt)
            prompts = result.all()

            print(f"\n📊 导入的提示词总数: {len(prompts)}")
            print("\n📋 提示词列表:")
            print("-" * 60)

            for prompt in prompts:
                print(f"名称: {prompt.name:20} | 类别: {prompt.category:10} | ID: {prompt.prompt_id}")

            print("-" * 60)

            # 查询版本信息
            version_stmt = select(
                PromptTable.name,
                PromptVersionTable.version_number,
                PromptVersionTable.is_current,
                PromptVersionTable.status
            ).select_from(
                PromptTable.__table__.join(
                    PromptVersionTable.__table__,
                    PromptTable.id == PromptVersionTable.prompt_id
                )
            ).order_by(
                PromptTable.name,
                PromptVersionTable.version_number
            )

            version_result = await session.execute(version_stmt)
            versions = version_result.all()

            print(f"\n📈 版本信息统计:")
            total_versions = len(versions)
            current_versions = sum(1 for v in versions if v.is_current)

            print(f"总版本数: {total_versions}")
            print(f"当前版本数: {current_versions}")

            print(f"\n📝 详细版本信息 (前10条):")
            print("-" * 80)
            for i, version in enumerate(versions[:10]):
                current_mark = "✅ 当前" if version.is_current else "⭕ 旧版"
                print(f"{version.name:20} | v{version.version_number:3} | {version.status:8} | {current_mark}")

            if len(versions) > 10:
                print(f"... 还有 {len(versions) - 10} 条版本记录")

            print("-" * 80)

            # 验证特定的一些文件
            expected_prompts = [
                'database_agent', 'assistant_agent', 'file_system',
                'ui_designer', 'prd', 'test'
            ]

            imported_names = {p.name for p in prompts}
            missing = set(expected_prompts) - imported_names

            if missing:
                print(f"\n❌ 缺失的预期提示词: {missing}")
            else:
                print(f"\n✅ 所有预期提示词都已导入")

            print(f"\n🎉 导入验证完成!")

    except Exception as e:
        print(f"❌ 验证过程中出现错误: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(verify_import())