"""
Common test utilities for AgentFusion tests.

This module provides shared fixtures and utilities used across different test modules.
"""

import tempfile
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text, JSON, Text

from data_layer.base_data_layer import DBDataLayer
from data_layer.models.base_model import Base


class SQLiteDBDataLayer(DBDataLayer):
    """SQLite implementation of DBDataLayer for testing"""
    
    def __init__(self, database_url: str = None, show_logger: bool = False):
        if database_url is None:
            # Create a temporary SQLite database for testing
            self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
            database_url = f"sqlite+aiosqlite:///{self.temp_db.name}"
        
        # Initialize without pool since SQLite doesn't use asyncpg
        self.database_url = database_url
        self.pool = None
        self.show_logger = show_logger
        
    async def connect(self):
        """Create SQLAlchemy engine for SQLite"""
        if not hasattr(self, '_engine'):
            self._engine = create_async_engine(
                self.database_url,
                echo=self.show_logger
            )
            self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
            
            # Replace JSONB, ARRAY and UUID columns for SQLite compatibility
            for table in Base.metadata.tables.values():
                for column in table.columns:
                    column_type_str = str(column.type)
                    if hasattr(column.type, '__visit_name__') and column.type.__visit_name__.startswith('JSON'):
                        column.type = JSON()
                    elif (hasattr(column.type, '__visit_name__') and column.type.__visit_name__.startswith('ARRAY')) or 'ARRAY' in column_type_str:
                        column.type = Text()  # Store arrays as text in SQLite
                    elif 'UUID' in column_type_str:
                        column.type = Text()  # Store UUID as text in SQLite
            
            # Create all tables
            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                # Create additional tables for testing
                await self._create_additional_test_tables(conn)
    
    async def _create_additional_test_tables(self, conn):
        """Create additional tables needed for testing"""
        # Additional tables are now handled by the ORM metadata
        # No need for manual table creation as they're included in Base.metadata
        pass
    
    async def disconnect(self):
        """Close SQLAlchemy engine"""
        if hasattr(self, '_engine'):
            await self._engine.dispose()
            
    async def get_session(self):
        """Get SQLAlchemy async session"""
        if not hasattr(self, '_engine'):
            await self.connect()
        return self._session_factory()
    
    async def cleanup(self):
        """Clean up database connections and temp files"""
        await self.disconnect()
        if hasattr(self, 'temp_db'):
            try:
                os.unlink(self.temp_db.name)
            except:
                pass

    # Mock the asyncpg-specific methods since we're using SQLAlchemy for testing
    async def execute_query(self, query: str, params=None):
        async with await self.get_session() as session:
            result = await session.execute(text(query), params or {})
            return [dict(row._mapping) for row in result.fetchall()]
    
    async def execute_single_query(self, query: str, params=None):
        results = await self.execute_query(query, params)
        return results[0] if results else None
    
    async def execute_command(self, query: str, params=None):
        async with await self.get_session() as session:
            result = await session.execute(text(query), params or {})
            await session.commit()
            return str(result.rowcount)