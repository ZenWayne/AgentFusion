# this file is used to fetch the sql comment from the sql file, 
# first, it cantains an interface to fetch comment in all tables
# second, it contains an interface to execute the sql command

import re
import asyncio
from typing import Dict, List, Any, Optional, Tuple, Union
from contextlib import asynccontextmanager

from data_layer.base_data_layer import DBDataLayer
from data_layer.data_layer import AgentFusionDataLayer


class SqlCommentExtractor:
    """Utility class for extracting SQL comments and executing SQL commands"""
    
    def __init__(self, db_layer: Optional[Union[DBDataLayer, AgentFusionDataLayer]] = None):
        self.db_layer = db_layer
    
    def extract_comments_from_sql(self, sql_content: str) -> Dict[str, List[str]]:
        """
        Extract comments from SQL command/string
        
        Args:
            sql_content: SQL command or string content
            
        Returns:
            Dict containing different types of comments found
        """
        comments = {
            'inline_comments': [],      # -- comments
            'block_comments': [],       # /* */ comments
            'table_comments': {},       # COMMENT ON TABLE
            'column_comments': {}       # COMMENT ON COLUMN
        }
        
        # Extract inline comments (-- comment)
        inline_pattern = r'--\s*(.+?)(?:\n|$)'
        inline_matches = re.findall(inline_pattern, sql_content, re.MULTILINE)
        comments['inline_comments'] = [match.strip() for match in inline_matches]
        
        # Extract block comments (/* comment */)
        block_pattern = r'/\*(.*?)\*/'
        block_matches = re.findall(block_pattern, sql_content, re.DOTALL)
        comments['block_comments'] = [match.strip() for match in block_matches]
        
        # Extract table comments
        table_comment_pattern = r'COMMENT\s+ON\s+TABLE\s+(\w+)\s+IS\s+\'([^\']*)\''
        table_matches = re.findall(table_comment_pattern, sql_content, re.IGNORECASE)
        comments['table_comments'] = {table: comment for table, comment in table_matches}
        
        # Extract column comments
        column_comment_pattern = r'COMMENT\s+ON\s+COLUMN\s+(\w+)\.(\w+)\s+IS\s+\'([^\']*)\''
        column_matches = re.findall(column_comment_pattern, sql_content, re.IGNORECASE)
        for table, column, comment in column_matches:
            if table not in comments['column_comments']:
                comments['column_comments'][table] = {}
            comments['column_comments'][table][column] = comment
        
        return comments
    
    async def fetch_table_comments_from_db(self, table_name: Optional[str] = None) -> Dict[str, str]:
        """
        Fetch table comments from PostgreSQL system catalogs
        
        Args:
            table_name: Specific table name, if None returns all tables
            
        Returns:
            Dict mapping table names to their comments
        """
        if not self.db_layer:
            raise ValueError("Database layer not initialized")
        
        #CR use orm to rewrite, you need
        base_query = """
        SELECT 
            t.table_name,
            obj_description(c.oid, 'pg_class') as table_comment
        FROM information_schema.tables t
        LEFT JOIN pg_class c ON c.relname = t.table_name
        WHERE t.table_schema = 'public'
        """
        
        params = []
        if table_name:
            base_query += " AND t.table_name = $1"
            params = [table_name]
        
        try:
            records = await self.db_layer.execute_query(base_query, params)
            return {
                record['table_name']: record['table_comment'] or ''
                for record in records
            }
        except Exception as e:
            print(f"Error fetching table comments: {e}")
            return {}
    
    async def fetch_column_comments_from_db(self, table_name: Optional[str] = None) -> Dict[str, Dict[str, str]]:
        """
        Fetch column comments from PostgreSQL system catalogs
        
        Args:
            table_name: Specific table name, if None returns all tables
            
        Returns:
            Dict mapping table names to column comments
        """
        if not self.db_layer:
            raise ValueError("Database layer not initialized")
        
        base_query = """
        SELECT 
            c.table_name,
            c.column_name,
            col_description(pgc.oid, c.ordinal_position) as column_comment
        FROM information_schema.columns c
        LEFT JOIN pg_class pgc ON pgc.relname = c.table_name
        WHERE c.table_schema = 'public'
        """
        
        params = []
        if table_name:
            base_query += " AND c.table_name = $1"
            params = [table_name]
        
        base_query += " ORDER BY c.table_name, c.ordinal_position"
        
        try:
            records = await self.db_layer.execute_query(base_query, params)
            result = {}
            for record in records:
                table = record['table_name']
                column = record['column_name']
                comment = record['column_comment'] or ''
                
                if table not in result:
                    result[table] = {}
                result[table][column] = comment
            
            return result
        except Exception as e:
            print(f"Error fetching column comments: {e}")
            return {}
    
    async def execute_sql(self, sql_command: str, params: Optional[Union[Dict, List]] = None) -> List[Dict[str, Any]]:
        """
        Execute SQL command and return results
        
        Args:
            sql_command: SQL command to execute
            params: Optional parameters for the query
            
        Returns:
            List of dictionaries representing query results
        """
        if not self.db_layer:
            raise ValueError("Database layer not initialized")
        
        try:
            return await self.db_layer.execute_query(sql_command, params)
        except Exception as e:
            print(f"Error executing SQL: {e}")
            raise
    
    async def execute_sql_with_comments(self, sql_content: str, params: Optional[Union[Dict, List]] = None) -> Tuple[List[Dict[str, Any]], Dict[str, List[str]]]:
        """
        Execute SQL and extract comments in one operation
        
        Args:
            sql_content: SQL content with comments
            params: Optional parameters for the query
            
        Returns:
            Tuple of (query results, extracted comments)
        """
        # Extract comments first
        comments = self.extract_comments_from_sql(sql_content)
        
        # Remove comments for execution (keep only the SQL)
        clean_sql = self._clean_sql_for_execution(sql_content)
        
        # Execute the cleaned SQL
        results = await self.execute_sql(clean_sql, params)
        
        return results, comments
    
    def _clean_sql_for_execution(self, sql_content: str) -> str:
        """
        Remove comments from SQL for execution
        
        Args:
            sql_content: SQL with comments
            
        Returns:
            Clean SQL without comments
        """
        # Remove block comments
        sql_content = re.sub(r'/\*.*?\*/', '', sql_content, flags=re.DOTALL)
        
        # Remove inline comments but preserve line breaks
        sql_content = re.sub(r'--.*?(?=\n|$)', '', sql_content, flags=re.MULTILINE)
        
        # Remove COMMENT ON statements (they're not queries)
        sql_content = re.sub(r'COMMENT\s+ON\s+(?:TABLE|COLUMN)\s+[^;]*;', '', sql_content, flags=re.IGNORECASE)
        
        # Clean up extra whitespace
        sql_content = re.sub(r'\n\s*\n', '\n', sql_content)
        sql_content = sql_content.strip()
        
        return sql_content


@asynccontextmanager
async def sql_interface_context(database_url: Optional[str] = None, db_layer: Optional[Union[DBDataLayer, AgentFusionDataLayer]] = None):
    """
    Context manager for SQL comment extraction and execution
    
    Args:
        database_url: Database connection URL
        db_layer: Existing database layer instance
    
    Yields:
        SqlCommentExtractor: Configured extractor instance
    """
    if db_layer:
        extractor = SqlCommentExtractor(db_layer)
        yield extractor
    else:
        if database_url:
            db = DBDataLayer(database_url)
        else:
            db = AgentFusionDataLayer(database_url)
        
        await db.connect()

        extractor = SqlCommentExtractor(db)
        yield extractor

async def main():
   import os
   async with sql_interface_context(database_url = os.getenv("DATABASE_URL")) as extractor:
        table_comments = await extractor.fetch_table_comments_from_db()
        print(table_comments)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
    #python -m cli.interface_context

# Usage examples:
# 1. Extract comments from SQL string:
#    extractor = SqlCommentExtractor()
#    comments = extractor.extract_comments_from_sql(sql_string)
#
# 2. Use with context manager:
#    async with sql_interface_context() as extractor:
#        table_comments = await extractor.fetch_table_comments_from_db()
#        results, comments = await extractor.execute_sql_with_comments(sql_string)