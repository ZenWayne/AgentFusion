#!/usr/bin/env python3
"""
Script to dump all configuration data from config directory to PostgreSQL database.
This script reads prompt files (.md) and JSON configurations and inserts them into the database.
"""

import os
import json
import hashlib
import psycopg2
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'database': 'agentfusion',
    'user': 'postgres',
    'password': 'postgres',
    'port': 5432
}

class ConfigDumper:
    def __init__(self, db_config: Dict, base_path: str = None):
        """Initialize the configuration dumper."""
        self.db_config = db_config
        self.base_path = Path(base_path) if base_path else Path(__file__).parent
        self.config_path = self.base_path / 'config'
        self.dumped_config_path = self.base_path / 'dumped_config'
        self.conn = None
        self.cursor = None
        
    def connect_db(self):
        """Connect to PostgreSQL database."""
        try:
            self.conn = psycopg2.connect(**self.db_config)
            self.cursor = self.conn.cursor()
            logger.info("Connected to PostgreSQL database")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    def disconnect_db(self):
        """Disconnect from PostgreSQL database."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        logger.info("Disconnected from PostgreSQL database")
    
    def get_or_create_component_type(self, name: str, description: str = None) -> int:
        """Get or create component type and return its ID."""
        self.cursor.execute(
            "SELECT id FROM component_types WHERE name = %s",
            (name,)
        )
        result = self.cursor.fetchone()
        
        if result:
            return result[0]
        
        # Create new component type
        self.cursor.execute(
            "INSERT INTO component_types (name, description) VALUES (%s, %s) RETURNING id",
            (name, description)
        )
        return self.cursor.fetchone()[0]
    
    def get_or_create_model_client(self, config_data: Dict) -> int:
        """Get or create model client and return its ID."""
        label = config_data.get('label', 'unknown')
        
        # Check if model client already exists
        self.cursor.execute(
            "SELECT id FROM model_clients WHERE label = %s",
            (label,)
        )
        result = self.cursor.fetchone()
        
        if result:
            return result[0]
        
        # Create new model client
        component_type_id = self.get_or_create_component_type(
            config_data.get('component_type', 'model'),
            'Model client component'
        )
        
        # Extract model info
        model_info = config_data.get('config', {}).get('model_info', {})
        
        self.cursor.execute("""
            INSERT INTO model_clients (
                label, provider, component_type_id, version, component_version,
                description, model_name, base_url, model_info, config
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            label,
            config_data.get('provider', ''),
            component_type_id,
            config_data.get('version', 1),
            config_data.get('component_version', 1),
            config_data.get('description', ''),
            config_data.get('config', {}).get('model', ''),
            config_data.get('config', {}).get('base_url', ''),
            json.dumps(model_info),
            json.dumps(config_data.get('config', {}))
        ))
        
        return self.cursor.fetchone()[0]
    
    def get_or_create_agent(self, name: str, config_data: Dict = None) -> int:
        """Get or create agent and return its ID."""
        # Check if agent already exists
        self.cursor.execute(
            "SELECT id FROM agents WHERE name = %s",
            (name,)
        )
        result = self.cursor.fetchone()
        
        if result:
            return result[0]
        
        # Create new agent
        component_type_id = self.get_or_create_component_type('agent', 'AI Agent component')
        
        # Get default model client (first one)
        self.cursor.execute("SELECT id FROM model_clients ORDER BY id LIMIT 1")
        model_client_result = self.cursor.fetchone()
        model_client_id = model_client_result[0] if model_client_result else None
        
        if config_data:
            label = config_data.get('label', name)
            provider = config_data.get('provider', 'autogen_agentchat.agents.AssistantAgent')
            description = config_data.get('description', f'Agent for {name}')
            version = config_data.get('version', 1)
            component_version = config_data.get('component_version', 1)
            agent_config = config_data.get('config', {})
        else:
            label = name
            provider = 'autogen_agentchat.agents.AssistantAgent'
            description = f'Agent for {name}'
            version = 1
            component_version = 1
            agent_config = {}
        
        self.cursor.execute("""
            INSERT INTO agents (
                name, label, provider, component_type_id, version, component_version,
                description, model_client_id, config
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            name, label, provider, component_type_id, version, component_version,
            description, model_client_id, json.dumps(agent_config)
        ))
        
        return self.cursor.fetchone()[0]
    
    def create_prompt_with_version(self, prompt_id: str, name: str, content: str, 
                                 category: str, subcategory: str, agent_id: int,
                                 created_by: str = 'system') -> Tuple[int, int]:
        """Create prompt and its first version, return (prompt_id, version_id)."""
        # Create prompt
        self.cursor.execute("""
            INSERT INTO prompts (prompt_id, name, category, subcategory, agent_id, created_by)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (prompt_id, name, category, subcategory, agent_id, created_by))
        
        prompt_table_id = self.cursor.fetchone()[0]
        
        # Create first version
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        
        self.cursor.execute("""
            INSERT INTO prompt_versions (
                prompt_id, version_number, content, content_hash, 
                created_by, is_current, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            prompt_table_id, 1, content, content_hash, 
            created_by, True, 'approved'
        ))
        
        version_id = self.cursor.fetchone()[0]
        
        return prompt_table_id, version_id
    
    def dump_model_clients(self):
        """Dump all model client configurations."""
        logger.info("Dumping model clients...")
        
        model_client_path = self.dumped_config_path / 'model_client'
        if not model_client_path.exists():
            logger.warning(f"Model client path not found: {model_client_path}")
            return
        
        for json_file in model_client_path.glob('*.json'):
            logger.info(f"Processing model client: {json_file.name}")
            
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                
                client_id = self.get_or_create_model_client(config_data)
                logger.info(f"Created/updated model client: {config_data.get('label', 'unknown')} (ID: {client_id})")
                
            except Exception as e:
                logger.error(f"Failed to process {json_file.name}: {e}")
    
    def dump_group_chat_configs(self):
        """Dump group chat configurations."""
        logger.info("Dumping group chat configurations...")
        
        group_chat_path = self.dumped_config_path / 'group_chat'
        if not group_chat_path.exists():
            logger.warning(f"Group chat path not found: {group_chat_path}")
            return
        
        for json_file in group_chat_path.glob('*.json'):
            logger.info(f"Processing group chat config: {json_file.name}")
            
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                
                # Extract participants and create agents
                participants = config_data.get('config', {}).get('participants', [])
                
                for participant in participants:
                    if participant.get('component_type') == 'agent':
                        agent_name = participant.get('config', {}).get('name', 'unknown')
                        agent_id = self.get_or_create_agent(agent_name, participant)
                        
                        # Extract system message as prompt
                        system_message = participant.get('config', {}).get('system_message', '')
                        if system_message:
                            prompt_id = f"{agent_name}_system_message"
                            self.create_prompt_with_version(
                                prompt_id=prompt_id,
                                name=f"{agent_name} System Message",
                                content=system_message,
                                category='agent',
                                subcategory='system_message',
                                agent_id=agent_id
                            )
                            logger.info(f"Created system message prompt for agent: {agent_name}")
                
            except Exception as e:
                logger.error(f"Failed to process {json_file.name}: {e}")
    
    def dump_prompt_files(self):
        """Dump all prompt files from config directory."""
        logger.info("Dumping prompt files...")
        
        # Process agent prompts
        agent_prompts_path = self.config_path / 'prompt' / 'agent'
        if agent_prompts_path.exists():
            for md_file in agent_prompts_path.glob('*.md'):
                self.process_prompt_file(md_file, 'agent')
        
        # Process group chat prompts
        group_chat_prompts_path = self.config_path / 'prompt' / 'group_chat'
        if group_chat_prompts_path.exists():
            for subdir in group_chat_prompts_path.iterdir():
                if subdir.is_dir():
                    for md_file in subdir.glob('*.md'):
                        self.process_prompt_file(md_file, 'group_chat', subdir.name)
        
        # Process UI design prompts
        ui_design_prompts_path = self.config_path / 'prompt' / 'ui_design'
        if ui_design_prompts_path.exists():
            for md_file in ui_design_prompts_path.glob('*.md'):
                self.process_prompt_file(md_file, 'ui_design')
        
        # Process memory prompts
        mem_prompts_path = self.config_path / 'mem'
        if mem_prompts_path.exists():
            for md_file in mem_prompts_path.glob('*.md'):
                self.process_prompt_file(md_file, 'memory')
    
    def process_prompt_file(self, file_path: Path, category: str, subcategory: str = None):
        """Process a single prompt file."""
        logger.info(f"Processing prompt file: {file_path.name}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Generate prompt_id from filename
            prompt_id = file_path.stem
            
            # Extract name from content (first line if it's a header)
            lines = content.split('\n')
            name = lines[0].strip('# ').strip() if lines and lines[0].startswith('#') else prompt_id
            
            # Determine subcategory if not provided
            if subcategory is None:
                subcategory = file_path.stem.replace('_pt', '').replace('_', ' ')
            
            # Create or get agent based on prompt category
            if category == 'agent':
                # Try to match with existing agent names
                agent_name = self.infer_agent_name(prompt_id)
                agent_id = self.get_or_create_agent(agent_name)
            else:
                # Create generic agent for non-agent prompts
                agent_name = f"{category}_{subcategory}_agent"
                agent_id = self.get_or_create_agent(agent_name)
            
            # Create prompt with version
            prompt_table_id, version_id = self.create_prompt_with_version(
                prompt_id=prompt_id,
                name=name,
                content=content,
                category=category,
                subcategory=subcategory,
                agent_id=agent_id
            )
            
            logger.info(f"Created prompt: {name} (ID: {prompt_table_id}, Version: {version_id})")
            
        except Exception as e:
            logger.error(f"Failed to process {file_path.name}: {e}")
    
    def infer_agent_name(self, prompt_id: str) -> str:
        """Infer agent name from prompt ID."""
        # Common mappings
        mapping = {
            'prd_pt': 'prd_agent',
            'prd_spec_pt': 'prd_spec_agent',
            'ui_designer_pt': 'ui_designer',
            'ui_design_pt': 'ui_design_agent',
            'prompt_specialization_pt': 'prompt_specialization_agent',
            'prompt_generalization_pt': 'prompt_generalization_agent',
            'template_extractor_pt': 'template_extractor',
            'file_system_pt': 'file_system_agent',
            'app_prd': 'app_prd_agent'
        }
        
        return mapping.get(prompt_id, prompt_id.replace('_pt', '_agent'))
    
    def run(self):
        """Run the complete dump process."""
        logger.info("Starting configuration dump process...")
        
        try:
            self.connect_db()
            
            # Dump in order of dependencies
            self.dump_model_clients()
            self.dump_group_chat_configs()
            self.dump_prompt_files()
            
            # Commit all changes
            self.conn.commit()
            logger.info("Configuration dump completed successfully!")
            
        except Exception as e:
            logger.error(f"Dump process failed: {e}")
            if self.conn:
                self.conn.rollback()
            raise
        finally:
            self.disconnect_db()

def main():
    """Main function to run the configuration dump."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Dump configuration data to PostgreSQL')
    parser.add_argument('--host', default='localhost', help='Database host')
    parser.add_argument('--port', type=int, default=5432, help='Database port')
    parser.add_argument('--database', default='agentfusion', help='Database name')
    parser.add_argument('--user', default='postgres', help='Database user')
    parser.add_argument('--password', help='Database password')
    parser.add_argument('--config-path', help='Path to config directory')
    
    args = parser.parse_args()
    
    # Build database config
    db_config = {
        'host': args.host,
        'port': args.port,
        'database': args.database,
        'user': args.user,
        'password': args.password or DB_CONFIG.get('password', '')
    }
    
    # Create and run dumper
    dumper = ConfigDumper(db_config, args.config_path)
    dumper.run()

if __name__ == '__main__':
    main() 