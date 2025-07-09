# Configuration Dump Script

This script dumps all configuration data from the `config` directory to PostgreSQL database.

## Prerequisites

1. **PostgreSQL Database**: Make sure PostgreSQL is running and the database schema is created
2. **Python Dependencies**: Install required packages

```bash
pip install -r requirements_dump.txt
```

## Database Setup

First, run the SQL schema to create the database structure:

```bash
psql -U postgres -d agentfusion -f progresdb.sql
```

## Usage

### Basic Usage

```bash
python dump_config_to_postgres.py
```

This will use default database settings:
- Host: localhost
- Port: 5432
- Database: agentfusion
- User: postgres
- Password: password

### Custom Database Settings

```bash
python dump_config_to_postgres.py \
  --host your-host \
  --port 5432 \
  --database your-database \
  --user your-user \
  --password your-password
```

### Custom Config Path

```bash
python dump_config_to_postgres.py --config-path /path/to/your/config
```

## What Gets Dumped

The script processes:

1. **Model Clients** (`dumped_config/model_client/*.json`)
   - Creates entries in `model_clients` table
   - Includes model configurations and capabilities

2. **Group Chat Configurations** (`dumped_config/group_chat/*.json`)
   - Creates agents from participants
   - Extracts system messages as prompts

3. **Prompt Files** (`config/prompt/**/*.md`)
   - Creates entries in `prompts` and `prompt_versions` tables
   - Categorizes by directory structure:
     - `config/prompt/agent/` → category: 'agent'
     - `config/prompt/group_chat/` → category: 'group_chat'
     - `config/prompt/ui_design/` → category: 'ui_design'
     - `config/mem/` → category: 'memory'

## Example Output

```
2024-01-15 10:30:00 - INFO - Starting configuration dump process...
2024-01-15 10:30:00 - INFO - Connected to PostgreSQL database
2024-01-15 10:30:00 - INFO - Dumping model clients...
2024-01-15 10:30:01 - INFO - Processing model client: deepseek-chat_DeepSeek.json
2024-01-15 10:30:01 - INFO - Created/updated model client: deepseek-chat_DeepSeek (ID: 1)
2024-01-15 10:30:01 - INFO - Dumping group chat configurations...
2024-01-15 10:30:01 - INFO - Processing group chat config: prompt_flow.json
2024-01-15 10:30:01 - INFO - Created system message prompt for agent: prompt_refiner
2024-01-15 10:30:01 - INFO - Created system message prompt for agent: executor
2024-01-15 10:30:01 - INFO - Dumping prompt files...
2024-01-15 10:30:01 - INFO - Processing prompt file: prd_pt.md
2024-01-15 10:30:01 - INFO - Created prompt: 通用产品需求文档(PRD)框架生成器 (ID: 1, Version: 1)
2024-01-15 10:30:02 - INFO - Configuration dump completed successfully!
```

## Error Handling

The script includes comprehensive error handling:
- Database connection failures
- File reading errors
- JSON parsing errors
- SQL execution errors

All errors are logged with details, and the database transaction is rolled back on failure.

## Database Structure

After running the script, you can query the data:

```sql
-- View all current prompts
SELECT * FROM current_prompt_versions;

-- View all agents and their prompts
SELECT * FROM agent_prompt_mapping;

-- View change history
SELECT * FROM prompt_change_summary;
``` 