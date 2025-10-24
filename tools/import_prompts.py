#!/usr/bin/env python3
"""
提示词导入脚本

将 config/prompt/ 目录下的 _pt.md 文件导入到数据库中，支持版本管理和外键约束。
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

# 添加项目根目录到 Python 路径，以便导入项目模块
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "python" / "packages" / "agent_fusion" / "src"))

from sqlalchemy import select, update, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from data_layer.base_data_layer import DBDataLayer
from data_layer.models.tables.prompt_table import PromptTable, PromptVersionTable
from data_layer.models.tables.user_table import UserTable

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PromptImporter:
    """提示词导入器"""

    def __init__(self, database_url: str):
        """
        初始化导入器

        Args:
            database_url: 数据库连接URL
        """
        self.db = DBDataLayer(database_url)
        self.admin_user_id: Optional[int] = None
        self.stats = {
            'total_files': 0,
            'created_prompts': 0,
            'updated_prompts': 0,
            'created_versions': 0,
            'errors': 0,
            'error_files': []
        }

    async def connect(self):
        """连接数据库"""
        await self.db.connect()
        logger.info("数据库连接成功")

    async def disconnect(self):
        """断开数据库连接"""
        await self.db.disconnect()
        logger.info("数据库连接已断开")

    async def get_admin_user_id(self, session: AsyncSession) -> int:
        """获取admin用户ID用于外键约束"""
        if self.admin_user_id is not None:
            return self.admin_user_id

        stmt = select(UserTable.id).where(UserTable.username == "admin")
        result = await session.execute(stmt)
        user_id = result.scalar_one_or_none()

        if not user_id:
            raise Exception("Admin user not found in database. Please ensure admin user exists.")

        self.admin_user_id = user_id
        logger.info(f"Found admin user ID: {user_id}")
        return user_id

    async def get_next_version_number(self, session: AsyncSession, prompt_table_id: int) -> int:
        """获取下一个版本号"""
        stmt = select(
            func.coalesce(func.max(PromptVersionTable.version_number), 0) + 1
        ).where(PromptVersionTable.prompt_id == prompt_table_id)

        result = await session.execute(stmt)
        next_version = result.scalar()
        return next_version

    def discover_prompt_files(self, prompt_dir: str) -> List[Tuple[str, str, str]]:
        """
        扫描提示词文件

        Args:
            prompt_dir: 提示词目录路径

        Returns:
            List[Tuple[file_path, prompt_name, category]]: 文件信息列表
        """
        prompt_files = []
        prompt_path = Path(prompt_dir)

        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt directory not found: {prompt_dir}")

        # 遍历所有子目录
        for file_path in prompt_path.rglob("*_pt.md"):
            if file_path.is_file():
                # 获取相对路径作为分类
                relative_path = file_path.relative_to(prompt_path)
                if len(relative_path.parts) > 1:
                    category = relative_path.parts[0]  # 第一级目录作为分类
                else:
                    category = "general"  # 根目录文件归类为general

                # 处理文件名
                filename = file_path.stem  # 去掉.md扩展名
                prompt_name = filename.replace('_pt', '')  # 去掉_pt后缀

                prompt_files.append((str(file_path), prompt_name, category))

        logger.info(f"发现 {len(prompt_files)} 个提示词文件")
        return prompt_files

    async def prompt_exists(self, session: AsyncSession, prompt_name: str) -> Optional[int]:
        """检查提示词是否存在并返回ID"""
        stmt = select(PromptTable.id).where(PromptTable.name == prompt_name)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def import_single_prompt(self, file_path: str, prompt_name: str, category: str) -> bool:
        """导入单个提示词文件"""
        try:
            async with await self.db.get_session() as session:
                admin_user_id = await self.get_admin_user_id(session)

                # 检查提示词是否已存在
                existing_prompt_id = await self.prompt_exists(session, prompt_name)

                # 如果不存在，创建新的提示词记录
                if not existing_prompt_id:
                    new_prompt = PromptTable(
                        prompt_id=f"{prompt_name}_prompt",
                        name=prompt_name,
                        category=category,
                        created_by=admin_user_id,
                        updated_by=admin_user_id
                    )
                    session.add(new_prompt)
                    await session.flush()  # 获取ID
                    existing_prompt_id = new_prompt.id
                    self.stats['created_prompts'] += 1
                    logger.info(f"Created new prompt: {prompt_name}")
                else:
                    self.stats['updated_prompts'] += 1
                    logger.info(f"Updating existing prompt: {prompt_name}")

                # 获取下一个版本号
                next_version = await self.get_next_version_number(session, existing_prompt_id)

                # 读取文件内容
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 创建新版本
                new_version = PromptVersionTable(
                    prompt_id=existing_prompt_id,
                    version_number=next_version,
                    content=content,
                    created_by=admin_user_id,
                    is_current=True
                )
                session.add(new_version)

                # 如果是更新操作，将旧版本设置为非当前
                if next_version > 1:
                    await session.execute(
                        update(PromptVersionTable).where(
                            and_(
                                PromptVersionTable.prompt_id == existing_prompt_id,
                                PromptVersionTable.version_number < next_version
                            )
                        ).values(is_current=False)
                    )
                    logger.info(f"Set old versions as non-current for {prompt_name}")

                await session.commit()
                self.stats['created_versions'] += 1
                logger.info(f"Successfully imported {prompt_name} version {next_version}")
                return True

        except Exception as e:
            logger.error(f"Error importing {prompt_name}: {str(e)}")
            self.stats['errors'] += 1
            self.stats['error_files'].append((prompt_name, str(e)))
            return False

    async def import_all_prompts(self, prompt_dir: str = "config/prompt"):
        """导入所有提示词文件"""
        try:
            # 连接数据库
            await self.connect()

            # 发现所有提示词文件
            prompt_files = self.discover_prompt_files(prompt_dir)
            self.stats['total_files'] = len(prompt_files)

            if not prompt_files:
                logger.warning("No prompt files found to import")
                return

            # 导入每个文件
            for file_path, prompt_name, category in prompt_files:
                await self.import_single_prompt(file_path, prompt_name, category)

            # 输出统计信息
            self.print_statistics()

        except Exception as e:
            logger.error(f"Fatal error during import: {str(e)}")
            raise
        finally:
            await self.disconnect()

    def print_statistics(self):
        """打印导入统计信息"""
        logger.info("=" * 50)
        logger.info("导入完成统计:")
        logger.info(f"总文件数: {self.stats['total_files']}")
        logger.info(f"新创建提示词: {self.stats['created_prompts']}")
        logger.info(f"更新提示词: {self.stats['updated_prompts']}")
        logger.info(f"创建版本数: {self.stats['created_versions']}")
        logger.info(f"错误数: {self.stats['errors']}")

        if self.stats['error_files']:
            logger.error("错误详情:")
            for filename, error in self.stats['error_files']:
                logger.error(f"  {filename}: {error}")

        logger.info("=" * 50)


async def main():
    """主函数"""
    # 数据库连接配置 - 可以从环境变量或配置文件读取
    database_url = os.getenv('DATABASE_URL', 'postgresql+asyncpg://user:password@localhost/agentfusion')

    # 提示词目录
    prompt_dir = os.getenv('PROMPT_DIR', 'config/prompt')

    logger.info("开始导入提示词到数据库")
    logger.info(f"数据库URL: {database_url}")
    logger.info(f"提示词目录: {prompt_dir}")

    try:
        importer = PromptImporter(database_url)
        await importer.import_all_prompts(prompt_dir)

    except Exception as e:
        logger.error(f"导入失败: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())