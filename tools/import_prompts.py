#!/usr/bin/env python3
"""
提示词导入脚本

将 config/prompt/ 目录下的 _pt.md 文件导入到数据库中，支持版本管理和外键约束。
"""

import os
import sys
import asyncio
import logging
import argparse
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Set
from datetime import datetime

# 添加项目根目录到 Python 路径，以便导入项目模块
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "python" / "packages" / "agent_fusion" / "src"))

from sqlalchemy import select, update, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from data_layer.base_data_layer import DBDataLayer
from data_layer.models.tables.prompt_table import PromptTable, PromptVersionTable
from data_layer.models.tables.user_table import UserTable
from data_layer.models.tables.agent_table import AgentTable

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PromptImporter:
    """提示词导入器"""

    def __init__(self, database_url: str, incremental: bool = False, force: bool = False, dry_run: bool = False, path_filter: Optional[str] = None, prompt_name: Optional[str] = None):
        """
        初始化导入器

        Args:
            database_url: 数据库连接URL
            incremental: 是否启用增量导入（仅导入修改过的文件）
            force: 是否强制重新导入所有文件
            dry_run: 是否为预演模式（不实际导入）
            path_filter: 路径过滤器（只导入匹配路径的文件）
            prompt_name: 指定的单个提示词名称（不包含_pt.md后缀）
        """
        self.db = DBDataLayer(database_url)
        self.admin_user_id: Optional[int] = None
        self.incremental = incremental
        self.force = force
        self.dry_run = dry_run
        self.path_filter = path_filter
        self.prompt_name = prompt_name
        self.file_import_history: Dict[str, Dict[str, Any]] = {}  # 记录文件导入历史
        self.stats = {
            'total_files': 0,
            'skipped_files': 0,
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

    def calculate_file_hash(self, file_path: str) -> str:
        """计算文件内容的SHA256哈希值"""
        with open(file_path, 'rb') as f:
            content = f.read()
        return hashlib.sha256(content).hexdigest()

    def get_file_mtime(self, file_path: str) -> datetime:
        """获取文件修改时间"""
        return datetime.fromtimestamp(Path(file_path).stat().st_mtime)

    async def load_import_history(self, session: AsyncSession):
        """加载文件导入历史记录"""
        if not self.incremental:
            return

        # 从prompt_versions表获取最近的导入记录
        stmt = select(
            PromptTable.name,
            PromptVersionTable.content_hash,
            PromptVersionTable.created_at
        ).select_from(
            PromptTable
        ).join(
            PromptVersionTable, PromptTable.id == PromptVersionTable.prompt_id
        ).where(
            PromptVersionTable.is_current == True
        )

        result = await session.execute(stmt)
        for row in result:
            self.file_import_history[row.name] = {
                'content_hash': row.content_hash,
                'imported_at': row.created_at
            }

    def should_import_file(self, file_path: str, prompt_name: str) -> bool:
        """判断文件是否需要导入"""
        # 如果启用强制导入，总是导入
        if self.force:
            return True

        # 如果不是增量模式，总是导入
        if not self.incremental:
            return True

        # 获取文件信息
        current_hash = self.calculate_file_hash(file_path)
        file_mtime = self.get_file_mtime(file_path)

        # 检查是否有导入历史
        if prompt_name not in self.file_import_history:
            return True

        # 检查内容哈希是否有变化
        history = self.file_import_history[prompt_name]
        if history['content_hash'] != current_hash:
            return True

        # 检查文件修改时间是否比导入时间新
        if file_mtime > history['imported_at']:
            return True

        return False

    def matches_path_filter(self, file_path: str) -> bool:
        """检查文件路径是否匹配过滤器"""
        if not self.path_filter:
            return True

        # 标准化路径分隔符
        normalized_path = file_path.replace('\\', '/')
        normalized_filter = self.path_filter.replace('\\', '/')

        # 检查路径是否包含过滤字符串
        return normalized_filter in normalized_path

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

    async def find_agent_id_by_name(self, session: AsyncSession, prompt_name: str, category: str) -> Optional[int]:
        """根据提示词名称或分类查找对应的agent_id"""
        # 首先尝试根据提示词名称直接匹配agent名称
        stmt = select(AgentTable.id).where(AgentTable.name == prompt_name)
        result = await session.execute(stmt)
        agent_id = result.scalar_one_or_none()

        if agent_id:
            logger.info(f"Found agent '{prompt_name}' with ID: {agent_id}")
            return agent_id

        # 如果没有直接匹配，尝试根据分类匹配
        category_mapping = {
            'agent': 'assistant_agent',
            'database': 'database_agent',
            'ui_design': 'ui_designer_agent',
            'prd': 'prd_agent',
            'coder': 'coder_agent',
            'tester': 'tester_agent'
        }

        # 从分类名称中提取可能的agent类型
        agent_type = None
        for key, value in category_mapping.items():
            if key in category.lower() or key in prompt_name.lower():
                agent_type = value
                break

        if agent_type:
            stmt = select(AgentTable.id).where(AgentTable.agent_type == agent_type).limit(1)
            result = await session.execute(stmt)
            agent_id = result.scalar_one_or_none()

            if agent_id:
                logger.info(f"Found agent by type '{agent_type}' with ID: {agent_id}")
                return agent_id

        # 如果还是找不到，尝试查找第一个可用的agent
        stmt = select(AgentTable.id).limit(1)
        result = await session.execute(stmt)
        agent_id = result.scalar_one_or_none()

        if agent_id:
            logger.info(f"Using first available agent with ID: {agent_id}")
            return agent_id

        logger.warning(f"No agent found for prompt '{prompt_name}' (category: {category})")
        return None

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
                # 处理文件名
                filename = file_path.stem  # 去掉.md扩展名
                prompt_name = filename.replace('_pt', '')  # 去掉_pt后缀

                # 如果指定了单个提示词名称，只匹配该提示词
                if self.prompt_name and prompt_name != self.prompt_name:
                    continue

                # 应用路径过滤器
                if not self.matches_path_filter(str(file_path)):
                    continue

                # 获取相对路径作为分类
                relative_path = file_path.relative_to(prompt_path)
                if len(relative_path.parts) > 1:
                    category = relative_path.parts[0]  # 第一级目录作为分类
                else:
                    category = "general"  # 根目录文件归类为general

                prompt_files.append((str(file_path), prompt_name, category))

        # 构建过滤信息消息
        filter_msgs = []
        if self.prompt_name:
            filter_msgs.append(f"prompt name: '{self.prompt_name}'")
        if self.path_filter:
            filter_msgs.append(f"path: '{self.path_filter}'")

        filter_msg = f" (filtered by {', '.join(filter_msgs)})" if filter_msgs else ""
        logger.info(f"发现 {len(prompt_files)} 个提示词文件{filter_msg}")
        return prompt_files

    async def prompt_exists(self, session: AsyncSession, prompt_name: str) -> Optional[int]:
        """检查提示词是否存在并返回ID"""
        stmt = select(PromptTable.id).where(PromptTable.name == prompt_name)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def import_single_prompt(self, file_path: str, prompt_name: str, category: str) -> bool:
        """导入单个提示词文件"""
        try:
            # 检查文件是否需要导入
            if not self.should_import_file(file_path, prompt_name):
                self.stats['skipped_files'] += 1
                logger.info(f"Skipping {prompt_name} (unchanged)")
                return True

            # 如果是预演模式，只显示将要导入的信息
            if self.dry_run:
                logger.info(f"[DRY-RUN] Would import: {prompt_name} from {file_path}")
                self.stats['created_versions'] += 1  # 预演模式下模拟统计
                return True

            async with await self.db.get_session() as session:
                admin_user_id = await self.get_admin_user_id(session)
                agent_id = await self.find_agent_id_by_name(session, prompt_name, category)

                # 检查提示词是否已存在
                existing_prompt_id = await self.prompt_exists(session, prompt_name)

                # 读取文件内容并计算哈希
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                content_hash = self.calculate_file_hash(file_path)

                # 如果不存在，创建新的提示词记录
                if not existing_prompt_id:
                    new_prompt = PromptTable(
                        prompt_id=f"{prompt_name}_prompt",
                        name=prompt_name,  # 确保name与文件名一致
                        category=category,
                        agent_id=agent_id,  # 分配对应的agent_id
                        created_by=admin_user_id,
                        updated_by=admin_user_id
                    )
                    session.add(new_prompt)
                    await session.flush()  # 获取ID
                    existing_prompt_id = new_prompt.id
                    self.stats['created_prompts'] += 1
                    logger.info(f"Created new prompt: {prompt_name} (agent_id: {agent_id})")
                else:
                    # 更新现有记录时，确保agent_id和name保持一致
                    await session.execute(
                        update(PromptTable).where(PromptTable.id == existing_prompt_id).values(
                            name=prompt_name,  # 确保名称一致
                            agent_id=agent_id,  # 更新agent_id
                            updated_by=admin_user_id
                        )
                    )
                    self.stats['updated_prompts'] += 1
                    logger.info(f"Updating existing prompt: {prompt_name} (agent_id: {agent_id})")

                # 获取下一个版本号
                next_version = await self.get_next_version_number(session, existing_prompt_id)

                # 创建新版本，确保prompt_version.prompt_id与prompt.id匹配
                new_version = PromptVersionTable(
                    prompt_id=existing_prompt_id,  # 外键引用prompts.id
                    version_number=next_version,
                    content=content,
                    content_hash=content_hash,
                    created_by=admin_user_id,
                    is_current=True
                )
                session.add(new_version)

                # 如果是更新操作，将旧版本设置为非当前
                if next_version > 1:
                    await session.execute(
                        update(PromptVersionTable).where(
                            and_(
                                PromptVersionTable.prompt_id == existing_prompt_id,  # 确保外键关系正确
                                PromptVersionTable.version_number < next_version
                            )
                        ).values(is_current=False)
                    )
                    logger.info(f"Set old versions as non-current for {prompt_name}")

                await session.commit()
                self.stats['created_versions'] += 1
                logger.info(f"Successfully imported {prompt_name} version {next_version} (prompt.id: {existing_prompt_id}, prompt_version.prompt_id: {existing_prompt_id})")
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

            # 加载导入历史（用于增量导入）
            if not self.dry_run:
                async with await self.db.get_session() as session:
                    await self.load_import_history(session)

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
        mode_parts = []
        if self.incremental:
            mode_parts.append("增量")
        if self.force:
            mode_parts.append("强制")
        if self.dry_run:
            mode_parts.append("预演")
        if self.path_filter:
            mode_parts.append(f"路径过滤({self.path_filter})")

        mode_str = " | ".join(mode_parts) if mode_parts else "完整"
        logger.info(f"导入模式: {mode_str}")
        logger.info("导入完成统计:")
        logger.info(f"总文件数: {self.stats['total_files']}")
        if self.incremental:
            logger.info(f"跳过文件数: {self.stats['skipped_files']}")
        logger.info(f"新创建提示词: {self.stats['created_prompts']}")
        logger.info(f"更新提示词: {self.stats['updated_prompts']}")
        logger.info(f"创建版本数: {self.stats['created_versions']}")
        logger.info(f"错误数: {self.stats['errors']}")

        if self.stats['error_files']:
            logger.error("错误详情:")
            for filename, error in self.stats['error_files']:
                logger.error(f"  {filename}: {error}")

        logger.info("=" * 50)


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="导入提示词文件到数据库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python import_prompts.py                                    # 完整导入所有提示词
  python import_prompts.py --incremental                      # 增量导入（仅修改过的文件）
  python import_prompts.py --path-filter agent/              # 只导入agent目录下的文件
  python import_prompts.py --path-filter ui_design            # 只导入包含ui_design的文件
  python import_prompts.py --prompt-name database_agent       # 只导入database_agent提示词
  python import_prompts.py --prompt-name ui_designer --dry-run # 预演导入ui_designer提示词
  python import_prompts.py --prompt-name prd --incremental     # 增量导入prd提示词
  python import_prompts.py --dry-run                          # 预演模式，查看将要导入的文件
  python import_prompts.py --force                            # 强制重新导入所有文件
  python import_prompts.py --incremental --path-filter agent/ # 增量导入agent目录下的文件
        """
    )

    parser.add_argument(
        '--database-url', '-d',
        default=os.getenv('DATABASE_URL', 'postgresql+asyncpg://user:password@localhost/agentfusion'),
        help='数据库连接URL (默认: DATABASE_URL环境变量)'
    )

    parser.add_argument(
        '--prompt-dir', '-p',
        default=os.getenv('PROMPT_DIR', 'config/prompt'),
        help='提示词文件目录 (默认: PROMPT_DIR环境变量)'
    )

    parser.add_argument(
        '--incremental', '-i',
        action='store_true',
        help='增量导入：仅导入修改过的文件'
    )

    parser.add_argument(
        '--force', '-f',
        action='store_true',
        help='强制重新导入所有文件（忽略增量检查）'
    )

    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='预演模式：显示将要导入的文件但不实际导入'
    )

    parser.add_argument(
        '--path-filter',
        type=str,
        help='路径过滤器：只导入包含指定路径的文件'
    )

    parser.add_argument(
        '--prompt-name',
        type=str,
        help='导入指定的单个提示词名称（不包含_pt.md后缀）'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='详细输出'
    )

    return parser.parse_args()


async def main():
    """主函数"""
    args = parse_arguments()

    # 配置日志级别
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 显示配置信息
    logger.info("开始导入提示词到数据库")
    logger.info(f"数据库URL: {args.database_url}")
    logger.info(f"提示词目录: {args.prompt_dir}")
    logger.info(f"增量模式: {args.incremental}")
    logger.info(f"强制导入: {args.force}")
    logger.info(f"预演模式: {args.dry_run}")
    logger.info(f"路径过滤器: {args.path_filter or '无'}")
    logger.info(f"指定提示词: {args.prompt_name or '无'}")

    # 验证参数组合
    if args.force and args.incremental:
        logger.warning("强制模式将忽略增量检查")

    if args.dry_run:
        logger.info("运行在预演模式，不会实际修改数据库")

    try:
        importer = PromptImporter(
            database_url=args.database_url,
            incremental=args.incremental,
            force=args.force,
            dry_run=args.dry_run,
            path_filter=args.path_filter,
            prompt_name=args.prompt_name
        )
        await importer.import_all_prompts(args.prompt_dir)

    except Exception as e:
        logger.error(f"导入失败: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())