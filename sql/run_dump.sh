#!/bin/bash

# Configuration Dump Script Runner
# This script sets up the environment and runs the configuration dump

set -e  # Exit on error

echo "🚀 Starting AgentFusion Configuration Dump..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements_dump.txt

# Check if PostgreSQL is running
if ! pg_isready -q; then
    echo "❌ PostgreSQL is not running. Please start PostgreSQL first."
    exit 1
fi

# Set default database parameters
DB_HOST=${DB_HOST:-localhost}
DB_PORT=${DB_PORT:-5432}
DB_NAME=${DB_NAME:-agentfusion}
DB_USER=${DB_USER:-postgres}
DB_PASSWORD=${DB_PASSWORD:-password}

echo "🗄️  Database Settings:"
echo "   Host: $DB_HOST"
echo "   Port: $DB_PORT"
echo "   Database: $DB_NAME"
echo "   User: $DB_USER"

# Create database if it doesn't exist
echo "🏗️  Creating database if needed..."
createdb -h $DB_HOST -p $DB_PORT -U $DB_USER $DB_NAME 2>/dev/null || true

# Run the schema creation
echo "📋 Setting up database schema..."
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f progresdb.sql -q

# Run the dump script
echo "📤 Running configuration dump..."
python dump_config_to_postgres.py \
    --host $DB_HOST \
    --port $DB_PORT \
    --database $DB_NAME \
    --user $DB_USER \
    --password $DB_PASSWORD

echo "✅ Configuration dump completed successfully!"
echo ""
echo "🔍 You can now query the data with:"
echo "   psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME"
echo ""
echo "📊 Example queries:"
echo "   SELECT * FROM current_prompt_versions;"
echo "   SELECT * FROM agent_prompt_mapping;"
echo "   SELECT * FROM prompt_change_summary;" 